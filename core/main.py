# ===== main.py =====

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
import sys
import ast
import json
import time
import queue
import datetime
import logging
import warnings

logging.getLogger().setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from report import generate_html
from score import extract_text_from_pdf, embed, chunk_text, SmartScorer, parse_job_data, ResumeProfile
from helpers import generate_pagination_urls, collect_links_from_page, extract_job_details, handle_login, extract_job_id
from job_cache import JobScrapeCache  # ← CACHE
from resume_parser import load_or_create_resume_profile

import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"cuDNN version: {torch.backends.cudnn.version()}")

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))   # oneClickShell/core/
base_dir  = os.path.dirname(_CORE_DIR)                    # oneClickShell/

timestamp     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
output_folder = os.path.join(base_dir, "outputs", f"run_{timestamp}")
os.makedirs(output_folder, exist_ok=True)

run        = "A"
AUTO_APPLY = True
FREELANCE  = False   # True → detect & filter freelance jobs, score with FreelanceScorer
RERANKER   = True    # True → cross-encoder reranks top-60 jobs_to_apply before applying
NEBIUS     = True    # True → use Nebius cloud LLM instead of local Ollama

# ── Nebius API key — read from oneClickShell/key.key ─────────────────────
_nebius_key_path = os.path.join(base_dir, "key.key")
try:
    with open(_nebius_key_path, "r", encoding="utf-8") as _f:
        NEBIUS_API_KEY = _f.read().strip()
except Exception:
    NEBIUS_API_KEY = None
    NEBIUS = False

# ── Per-run profile resolution ────────────────────────────────────────────
if run == "A":
    profile_dir         = os.path.join(base_dir, "profiles", "pandurang")
    cache_file          = "job_cache_A.json"
    config_path         = os.path.join(profile_dir, "config_A.json")
    links_path          = os.path.join(profile_dir, "links.txt")
    resume_profile_path = os.path.join(profile_dir, "resume_profile_pandurang.json")
    new_filename        = f"job_crawl_summary_A_{timestamp}.html"
    log_file            = os.path.join(output_folder, f"output_A_{timestamp}.log")
elif run == "B":
    profile_dir         = os.path.join(base_dir, "profiles", "pandurang")
    cache_file          = "job_cache_B.json"
    config_path         = os.path.join(profile_dir, "config_B.json")
    links_path          = os.path.join(profile_dir, "links.txt")
    resume_profile_path = os.path.join(profile_dir, "resume_profile_pandurang.json")
    new_filename        = f"job_crawl_summary_B_{timestamp}.html"
    log_file            = os.path.join(output_folder, f"output_B_{timestamp}.log")
else:  
    profile_dir         = os.path.join(base_dir, "profiles", "mayuri")
    cache_file          = "job_cache.json"
    config_path         = os.path.join(profile_dir, "config.json")
    links_path          = os.path.join(profile_dir, "links.txt")
    resume_profile_path = os.path.join(profile_dir, "resume_profile_mayuri.json")
    new_filename        = f"job_crawl_summary_M_{timestamp}.html"
    log_file            = os.path.join(output_folder, f"output_M_{timestamp}.log")





with open(config_path, "r") as f:
    config = json.load(f)

# ← CACHE: init per-profile cache (prunes expired entries on startup)
job_cache = JobScrapeCache(profile_dir, cache_file)
job_cache.start_background_flush(interval_seconds=30)  # writes every 30s, never blocks workers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="a", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)

resume_path = config.get("resume_path")
username = config.get("username")
password = config.get("password")

output_file_path = os.path.join(output_folder, new_filename)

logger.info(f"Resume Path: {resume_path}")
logger.info(f"Username: {username}")
logger.info(f"Output File Path: {output_file_path}")

NUM_DRIVERS = 4

def create_driver(driver_id):
    options = Options()
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.managed_default_content_settings.images": 2
    })
    options.add_argument("--start-maximized")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--log-level=3")

    # IMPORTANT: Enable performance logging to capture network requests
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    service = Service(log_path='NUL')
    return webdriver.Chrome(service=service, options=options)


def login_driver(driver_id, username, password, logger):
    try:
        driver = create_driver(driver_id)
        driver.get("https://www.naukri.com/nlogin/login")
        handle_login(driver, username, password, logger)
        return driver, driver_id, True
    except Exception as e:
        logger.error(f"Driver {driver_id} login failed: {e}")
        return None, driver_id, False


def collect_links_worker(args):
    driver, page_queue, job_links_xpath, progress_callback, skip_patterns = args
    all_links = set()

    while True:
        try:
            page_url = page_queue.get_nowait()
        except queue.Empty:
            break
        links = collect_links_from_page(driver, page_url, job_links_xpath)
        all_links.update(links)
        if progress_callback:
            progress_callback()

    filtered_links = {
        link for link in all_links
        if not any(pattern in link for pattern in skip_patterns)
    }

    return filtered_links


def scrape_jobs_worker(args):
    driver, job_urls, progress_callback, job_cache = args
    jobs = []

    for url in job_urls:
        job_data = extract_job_details(driver, url)
        if job_data:
            jobs.append(job_data)
            job_cache.set_one(job_data)  # in-memory only — background thread flushes
        if progress_callback:
            progress_callback()

    return jobs


# ─────────────────────────────────────────────────────────
# Model setup
# ─────────────────────────────────────────────────────────

device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")

model_ = SentenceTransformer('TechWolf/JobBERT-v3').to(device)

# ─────────────────────────────────────────────────────────
# Resume extraction + structured profile
#
# Flow:
#   1. Extract raw text from PDF
#   2. Check config for "resume_profile_path"
#      ├── Found + file exists → load JSON directly (fast)
#      └── Not found / missing → call Ollama llama3.1:8b to parse,
#          save resume_profile.json next to resume, write path into config
# ─────────────────────────────────────────────────────────

resume_text = extract_text_from_pdf(resume_path)
logger.info("Resume text extracted from PDF")

resume_profile_data = load_or_create_resume_profile(config, config_path, resume_text)

resume_embed = embed(model_, resume_text)
logger.info("Resume embedded")

# ─────────────────────────────────────────────────────────
# Driver initialization + login
# ─────────────────────────────────────────────────────────

logger.info(f"Initializing {NUM_DRIVERS} drivers and logging in...")

drivers = []
with ThreadPoolExecutor(max_workers=NUM_DRIVERS) as executor:
    login_futures = [
        executor.submit(login_driver, i, username, password, logger)
        for i in range(NUM_DRIVERS)
    ]

    for future in as_completed(login_futures):
        driver, driver_id, success = future.result()
        if success and driver:
            drivers.append(driver)
            logger.info(f"Driver {driver_id} logged in successfully")
        else:
            logger.error(f"Driver {driver_id} failed to login")

if len(drivers) < NUM_DRIVERS:
    logger.warning(f"Only {len(drivers)}/{NUM_DRIVERS} drivers logged in successfully")

if len(drivers) == 0:
    logger.error("No drivers available. Exiting.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────
# Link collection
# ─────────────────────────────────────────────────────────

job_links_xpath = "/html/body/div/div/main/div[1]/div[2]/div[2]/div/div/div/div[1]/h2/a"

with open(links_path, "r") as f:
    lk = ast.literal_eval(f.read())
    logger.info(f"Links: {repr(lk)}")

all_pagination_urls = []
for l in lk:
    base_url = l[1]
    max_pages = l[0]
    pagination_urls = generate_pagination_urls(base_url, max_pages)
    all_pagination_urls.extend(pagination_urls)

logger.info(f"Total pagination URLs: {len(all_pagination_urls)}")

logger.info("Collecting job links in parallel...")

skip_url_patterns = ["soul-ai", "benovymed"]

# Shared queue — fast drivers steal work from slow ones automatically
page_queue = queue.Queue()
for _url in all_pagination_urls:
    page_queue.put(_url)

all_job_links = set()
total_pages = len(all_pagination_urls)

with tqdm(total=total_pages, desc="Scraping Pages", unit="page") as pbar:
    with ThreadPoolExecutor(max_workers=len(drivers)) as executor:
        futures = [
            executor.submit(
                collect_links_worker,
                (driver, page_queue, job_links_xpath, lambda: pbar.update(1), skip_url_patterns)
            )
            for driver in drivers
        ]

        for future in as_completed(futures):
            links = future.result()
            all_job_links.update(links)

logger.info(f"Total unique job links collected: {len(all_job_links)}")

# ← CACHE: split links into already-cached vs needs-scraping
# skillMatch jobs older than REFRESH_AFTER_DAYS are re-scraped to refresh
# earlyApplicant, applicants_text, and match data (these change daily).
REFRESH_AFTER_DAYS = 3

cached_jobs: list = []
urls_to_scrape: list = []
refreshed_count = 0

for link in all_job_links:
    jid = extract_job_id(link)
    if jid and job_cache.is_cached(jid):
        job_data = job_cache.get(jid)  # includes _cached_at
        if job_data.get("skillMatch") and job_cache.is_stale(jid, REFRESH_AFTER_DAYS):
            urls_to_scrape.append(link)
            refreshed_count += 1
        else:
            cached_jobs.append(job_data)
    else:
        urls_to_scrape.append(link)

logger.info(f"Cache hit:     {len(cached_jobs)} jobs loaded from cache")
logger.info(f"Cache miss:    {len(urls_to_scrape)} jobs queued for scraping")
logger.info(f"Force-refresh: {refreshed_count} stale skillMatch jobs re-queued")

# ─────────────────────────────────────────────────────────
# Job detail scraping
# ─────────────────────────────────────────────────────────

job_links_list = list(urls_to_scrape)  # ← CACHE: only scrape uncached URLs
chunk_size = max(1, len(job_links_list) // len(drivers))

job_chunks = []
for i in range(len(drivers) - 1):
    job_chunks.append(job_links_list[i * chunk_size:(i + 1) * chunk_size])
job_chunks.append(job_links_list[(len(drivers) - 1) * chunk_size:])

logger.info("Scraping job details in parallel...")

data = []
seen_keys = set()
total_jobs = len(job_links_list)

with tqdm(total=total_jobs, desc="Collecting Job Data", unit="job") as pbar:
    with ThreadPoolExecutor(max_workers=len(drivers)) as executor:
        futures = [
            executor.submit(scrape_jobs_worker, (driver, chunk, lambda: pbar.update(1), job_cache))
            for driver, chunk in zip(drivers, job_chunks)
        ]

        for future in as_completed(futures):
            jobs = future.result()
            for job in jobs:
                key = (
                    job.get("Job Title", "").strip().lower(),
                    job.get("Company Name", "").strip().lower(),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    data.append(job)

logger.info(f"Total unique jobs scraped: {len(data)}")

# Final flush — captures anything the background thread hasn't written yet.
job_cache.flush()
logger.info(f"Cache updated: {len(data)} scraped → {job_cache.stats()['total_entries']} total entries in cache")

# Deduplicate by job_id: scraped (fresh) overwrites cached (stale).
# Jobs without a job_id are kept as-is (safety net, should not happen).
merged: dict = {}
for job in cached_jobs:
    jid = job.get("job_id")
    if jid:
        merged[jid] = job
for job in data:
    jid = job.get("job_id")
    if jid:
        merged[jid] = job  # fresh scrape wins
no_id_jobs = [j for j in data if not j.get("job_id")]
data = list(merged.values()) + no_id_jobs
logger.info(f"Total jobs after deduplicated merge: {len(data)}")

# ─────────────────────────────────────────────────────────
# Driver cleanup
# ─────────────────────────────────────────────────────────

if AUTO_APPLY:
    apply_driver = drivers.pop()
    for driver in drivers:
        try:
            driver.quit()
        except:
            pass
    logger.info("Reserved 1 driver for auto-apply. Quit the rest.")
else:
    apply_driver = None
    for driver in drivers:
        try:
            driver.quit()
        except:
            pass

# ─────────────────────────────────────────────────────────
# Smart Scoring
# ─────────────────────────────────────────────────────────

logger.info("Starting scoring...")

# Build ResumeProfile from Ollama-parsed structured data
resume_profile = ResumeProfile(
    skills=resume_profile_data.get("resume_skills", []),
    total_experience_years=resume_profile_data.get("total_experience_years", 0.0),
    sections=resume_profile_data.get("resume_sections", {}),
    education_level=resume_profile_data.get("education_level", ""),
    location=resume_profile_data.get("preferred_location", ""),
    preferred_work_mode=resume_profile_data.get("preferred_work_mode", "hybrid"),
    full_text=resume_text,
    willing_to_relocate=resume_profile_data.get("willing_to_relocate", True),
)

# Chunk + encode resume once — reused across all jobs in semantic signal
resume_chunks = chunk_text(resume_text, max_tokens=200)
with torch.no_grad():
    resume_embeddings = model_.encode(
        resume_chunks,
        batch_size=32,
        convert_to_tensor=True,
        normalize_embeddings=True,
    ).to(device)

# Attach embeddings so scorer can access them without re-encoding
resume_profile.sections["_embeddings"] = resume_embeddings

# ── Freelance mode: detect + filter, then use FreelanceScorer ──────────────
from score import precompute_resume_embeddings, precompute_job_embeddings

if FREELANCE:
    from freelance_score import is_freelance_job, FreelanceScorer
    before = len(data)
    data   = [j for j in data if is_freelance_job(j)]
    logger.info(f"Freelance filter: {len(data)}/{before} jobs detected as freelance/part-time")
    scorer = FreelanceScorer()
else:
    scorer = SmartScorer()

# Pre-encode resume skills + sections — runs for ALL modes (required by both scorers)
precompute_resume_embeddings(resume_profile, model_, device)

# ── Parse + batch pre-encode job embeddings (ALL modes) ────────────────────
job_parsed_map = {}
for idx, job in enumerate(data):
    v3 = job.get("matchscore_api", {})
    v4 = job.get("v4_data", {})
    job_parsed_map[idx] = parse_job_data(job, v3, v4)

parsed_list = list(job_parsed_map.values())
precompute_job_embeddings(parsed_list, model_, device)
logger.info(f"Job embeddings precomputed for {len(parsed_list)} jobs.")

# ── Score ───────────────────────────────────────────────────────────────────
for idx, job in enumerate(tqdm(data, desc="Scoring Jobs")):
    try:
        job_parsed = job_parsed_map[idx]
        result     = scorer.score(resume_profile, job_parsed, model_)

        job["total_score"]     = result["total_score"]
        job["grade"]           = result["grade"]
        job["score_breakdown"] = result["breakdown"]
        job["missing_skills"]  = result["missing_skills"]
        job["salary_insight"]  = result["salary_insight"]
        job["score_flags"]     = result["flags"]
        job["apply_priority"]  = result["apply_priority"]

        # Keep legacy `score` field (0-1) so report.py stays compatible
        job["score"] = round(result["total_score"] / 100, 4)

    except Exception as e:
        logger.warning(f"Scoring failed for {job.get('URL', '')}: {e}")
        job["score"] = None
        job["total_score"] = None

logger.info("Scoring completed.")

# ─────────────────────────────────────────────────────────
# Save raw JSON
# ─────────────────────────────────────────────────────────

json_filename = f"job_data_{timestamp}.json"
json_path = os.path.join(output_folder, json_filename)

with open(json_path, "w", encoding="utf-8") as jf:
    json.dump(data, jf, ensure_ascii=False, indent=2)

logger.info(f"Job data JSON saved at {json_path}")

# ─────────────────────────────────────────────────────────
# Filtering + sorting
# ─────────────────────────────────────────────────────────

logger.info("Filtering jobs with skill match priority...")

if FREELANCE:
    # No score floor — all detected freelance jobs included.
    # Naukri skillMatch bucket first, then by total_score desc.
    skill_matched_jobs = []
    other_jobs = []
    for job in data:
        if not isinstance(job, dict) or not isinstance(job.get("score"), (float, int)):
            continue
        if job.get("skillMatch"):
            skill_matched_jobs.append(job)
        else:
            other_jobs.append(job)
    skill_matched_jobs.sort(key=lambda x: x.get("total_score") or 0, reverse=True)
    other_jobs.sort(key=lambda x: x.get("total_score") or 0, reverse=True)
    filtered_data = skill_matched_jobs + other_jobs
    logger.info(f"Freelance jobs in report: {len(filtered_data)} (skill-matched: {len(skill_matched_jobs)}, other: {len(other_jobs)})")
else:
    skill_matched_jobs = []
    other_jobs = []

    for job in data:
        if not isinstance(job, dict):
            continue

        score = job.get("score")
        skill_match = job.get("skillMatch", False)

        if not isinstance(score, (float, int)) or score is None:
            continue

        if skill_match:
            skill_matched_jobs.append(job)
        elif score > 0.5:
            other_jobs.append(job)

    # Sort by total_score (richer signal), fallback to legacy score * 100
    skill_matched_jobs.sort(key=lambda x: x.get("total_score") or (x.get("score", 0) * 100), reverse=True)
    other_jobs.sort(key=lambda x: x.get("total_score") or (x.get("score", 0) * 100), reverse=True)

    filtered_data = skill_matched_jobs + other_jobs

    logger.info(f"Skill-matched jobs: {len(skill_matched_jobs)}")
    logger.info(f"Other jobs (score > 0.5): {len(other_jobs)}")
    logger.info(f"Total jobs in report: {len(filtered_data)}")

if not FREELANCE:
    if skill_matched_jobs:
        logger.info(f"Skill-matched score range: {skill_matched_jobs[-1].get('total_score', 0):.1f} - {skill_matched_jobs[0].get('total_score', 0):.1f}")
    if other_jobs:
        logger.info(f"Other jobs score range: {other_jobs[-1].get('total_score', 0):.1f} - {other_jobs[0].get('total_score', 0):.1f}")

new_filename = os.path.join(output_folder, new_filename)

# ─────────────────────────────────────────────────────────
# Auto-apply
# ─────────────────────────────────────────────────────────

apply_results = {}

if AUTO_APPLY and apply_driver:
    logger.info("AUTO_APPLY enabled. Starting auto-apply pipeline...")

    from auto_apply.auto_apply_new import (
        QAStore, extract_skill_summary,
        apply_to_job, handle_screening,
        AppliedCache, FailedLogger,
        PROFILE, MAX_SUCCESS,
        set_active_profile, set_llm_backend,
    )

    # ── Sync auto_apply profile to main.py run ──────────────────────────
    _profile_key_map = {"A": "A_NEW", "B": "B_OLD", "M": "C_MAYURI"}
    set_active_profile(_profile_key_map.get(run, "C_MAYURI"))
    logger.info(f"Auto-apply profile set to: {_profile_key_map.get(run)}")

    # ── LLM backend: Nebius if key present, else Ollama ─────────────────
    set_llm_backend(use_nebius=NEBIUS, api_key=NEBIUS_API_KEY)

    # ── Setup shared state ──────────────────────────────────
    qa_store_path = os.path.join(profile_dir, "qa_store.json")

    qa_store      = QAStore(qa_store_path)   # auto-migrates from qa_cache + master_qa on first run
    skill_summary = extract_skill_summary(resume_text)
    applied_cache = AppliedCache()
    failed_logger = FailedLogger()

    logger.info(f"QA store: {len(qa_store.entries)} entries | Applied: {len(applied_cache.cache)}")
    logger.info(f"Skill summary: {skill_summary}")

    # ── Filter and deduplicate jobs ─────────────────────────
    SKIP_URL_KEYWORDS = [["data", "analyst"]]

    stats = {
        "score_filtered":     0,
        "extapp_filtered":    0,
        "already_applied":    0,
        "url_keyword_skip":   0,
        "duplicates_removed": 0,
    }

    best = {}
    for job in data:
        score = job.get("score") or 0

        # extApp always skipped — beyond auto-apply capabilities
        if job.get("extApp"):
            stats["extapp_filtered"] += 1
            continue

        # Full-time mode: skip low-score jobs.
        # Freelance mode: skip only if semantic fit is near-zero (clearly unrelated domain).
        if FREELANCE:
            sem = job.get("score_breakdown", {}).get("semantic", 0)
            if sem < 20:
                stats["score_filtered"] += 1
                continue
        elif score <= 0.38:
            stats["score_filtered"] += 1
            continue

        url = job.get("URL", "")
        if applied_cache.is_applied(url):
            stats["already_applied"] += 1
            continue

        if any(all(kw in url.lower() for kw in pair) for pair in SKIP_URL_KEYWORDS):
            stats["url_keyword_skip"] += 1
            continue

        key = (job.get("Job Title"), job.get("Company Name"))
        if key in best:
            stats["duplicates_removed"] += 1

        if not best.get(key) or score > best[key].get("score", 0):
            best[key] = job

    for job in best.values():
        job["skillMatch"] = bool(job.get("skillMatch"))

    jobs_to_apply = sorted(
        best.values(),
        key=lambda x: (
            not x.get("skillMatch", False),
            -(x.get("total_score") or x.get("score", 0) * 100)
        )
    )

    if RERANKER and jobs_to_apply:
        from reranker import rerank_jobs
        resume_summary = resume_profile.sections.get("summary", "")
        jobs_to_apply  = rerank_jobs(
            resume_summary = resume_summary,
            resume_skills  = resume_profile.skills,
            jobs           = jobs_to_apply,
            device         = device,
            top_n          = 60,
        )

    total = len(jobs_to_apply)

    logger.info(f"========== AUTO-APPLY FILTER FUNNEL ({'FREELANCE' if FREELANCE else 'FULL-TIME'}) ==========")
    logger.info(f"Total jobs input:             {len(data)}")
    logger.info(f"{'Filtered by semantic < 20:' if FREELANCE else 'Filtered by score <=0.38:'}     {stats['score_filtered']}")
    logger.info(f"Filtered extApp=True:         {stats['extapp_filtered']}")
    logger.info(f"Filtered already applied:     {stats['already_applied']}")
    logger.info(f"Filtered by URL keywords:     {stats['url_keyword_skip']}")
    logger.info(f"Duplicates removed:           {stats['duplicates_removed']}")
    logger.info(f"Jobs to process:              {total}")
    logger.info("===============================================")

    # ── Apply loop ──────────────────────────────────────────
    success_count  = 0
    consec_errors  = 0
    ERROR_STATUSES = {"no_apply_state", "platform_error", "apply_click_error", "unknown"}

    for idx, job in enumerate(jobs_to_apply, 1):
        url     = job.get("URL", "")
        title   = job.get("Job Title", "")
        company = job.get("Company Name", "")

        try:
            logger.info(f"[{idx}/{total}] {title} @ {company}")
            logger.info(f"  URL: {url}")

            apply_driver.get(url)
            status = apply_to_job(apply_driver, url, failed_logger)

            if status in ERROR_STATUSES:
                logger.info(f"  Skipped (status={status})")
                consec_errors += 1
                if consec_errors >= 8:
                    logger.error("Daily limit likely reached. Stopping.")
                    break
                continue

            consec_errors = 0

            if status in ("already_applied", "applied"):
                applied_cache.mark(url)
                apply_results[url] = status
                if status == "applied":
                    success_count += 1
                    logger.info(f"  Applied [{success_count}/{MAX_SUCCESS}]")
                    if success_count >= MAX_SUCCESS:
                        break
                continue

            if status == "screening":
                result = handle_screening(
                    apply_driver, url, resume_text, skill_summary,
                    qa_store, failed_logger,
                )
                apply_results[url] = result
                logger.info(f"  Screening result: {result}")

                if result == "applied":
                    applied_cache.mark(url)
                    qa_store.confirm_session()   # mark all answers used here as confirmed
                    success_count += 1
                    logger.info(f"  Applied [{success_count}/{MAX_SUCCESS}]")
                    if success_count >= MAX_SUCCESS:
                        break
                continue

            logger.info(f"  Skipped (status={status})")
            apply_results[url] = status

        except Exception as e:
            logger.error(f"  Error on {url}: {e}")
            failed_logger.log(url, "exception", str(e))
            apply_results[url] = "error"

    logger.info(f"Auto-apply done. Applied: {success_count} | QA store: {len(qa_store.entries)} entries")

    try:
        apply_driver.quit()
    except:
        pass

elif AUTO_APPLY and not apply_driver:
    logger.error("AUTO_APPLY enabled but no driver available.")
else:
    logger.info("AUTO_APPLY disabled. Skipping.")

if apply_results:
    for job in data:
        url = job.get("URL", "")
        if url in apply_results:
            job["apply_status"] = apply_results[url]

# ─────────────────────────────────────────────────────────
# HTML Report
# ─────────────────────────────────────────────────────────

generate_html(filtered_data, new_filename)
logger.info(f"HTML report generated at {new_filename}")