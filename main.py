# ===== main.py =====

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

import sys
import ast
import json
import time
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
from helpers import generate_pagination_urls, collect_links_from_page, extract_job_details, handle_login
from resume_parser import load_or_create_resume_profile

import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"cuDNN version: {torch.backends.cudnn.version()}")

base_dir = os.path.dirname(os.path.abspath(__file__))
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
output_folder = os.path.join(base_dir, "outputs", f"run_{timestamp}")
os.makedirs(output_folder, exist_ok=True)

run = "B"
AUTO_APPLY = True

if run == "A":
    config_path = os.path.join(base_dir, "config-old.json")
    new_filename = f"job_crawl_summary_A_{timestamp}.html"
    log_file = os.path.join(output_folder, f"output_A_{timestamp}.log")
elif run == "B":
    config_path = os.path.join(base_dir, "config.json")
    new_filename = f"job_crawl_summary_B_{timestamp}.html"
    log_file = os.path.join(output_folder, f"output_B_{timestamp}.log")
else:
    config_path = os.path.join(base_dir, "config - Mayuri.json")
    new_filename = f"job_crawl_summary_M_{timestamp}.html"
    log_file = os.path.join(output_folder, f"output_M_{timestamp}.log")

with open(config_path, "r") as f:
    config = json.load(f)

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
    driver, page_urls, job_links_xpath, progress_callback, skip_patterns = args
    all_links = set()

    logger.info(f"Worker started with {len(page_urls)} pages to scrape")

    for idx, page_url in enumerate(page_urls):
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
    driver, job_urls, progress_callback = args
    jobs = []

    for url in job_urls:
        job_data = extract_job_details(driver, url)
        if job_data:
            jobs.append(job_data)
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

with open("links.txt", "r") as f:
    lk = ast.literal_eval(f.read())
    logger.info(f"Links: {repr(lk)}")

all_pagination_urls = []
for l in lk:
    base_url = l[1]
    max_pages = l[0]
    pagination_urls = generate_pagination_urls(base_url, max_pages)
    all_pagination_urls.extend(pagination_urls)

logger.info(f"Total pagination URLs: {len(all_pagination_urls)}")

chunk_size = max(1, len(all_pagination_urls) // len(drivers))
url_chunks = []
for i in range(len(drivers) - 1):
    url_chunks.append(all_pagination_urls[i * chunk_size:(i + 1) * chunk_size])
url_chunks.append(all_pagination_urls[(len(drivers) - 1) * chunk_size:])

logger.info("Collecting job links in parallel...")

skip_url_patterns = ["soul-ai", "benovymed"]

all_job_links = set()
total_pages = len(all_pagination_urls)

with tqdm(total=total_pages, desc="Scraping Pages", unit="page") as pbar:
    with ThreadPoolExecutor(max_workers=len(drivers)) as executor:
        futures = [
            executor.submit(
                collect_links_worker,
                (driver, chunk, job_links_xpath, lambda: pbar.update(1), skip_url_patterns)
            )
            for driver, chunk in zip(drivers, url_chunks)
        ]

        for future in as_completed(futures):
            links = future.result()
            all_job_links.update(links)

logger.info(f"Total unique job links collected: {len(all_job_links)}")

# ─────────────────────────────────────────────────────────
# Job detail scraping
# ─────────────────────────────────────────────────────────

job_links_list = list(all_job_links)
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
            executor.submit(scrape_jobs_worker, (driver, chunk, lambda: pbar.update(1)))
            for driver, chunk in zip(drivers, job_chunks)
        ]

        for future in as_completed(futures):
            jobs = future.result()
            for job in jobs:
                key = (
                    job.get("Job Title", "").strip().lower(),
                    job.get("Company Name", "").strip().lower(),
                    job.get("location", "").strip().lower()
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    data.append(job)

logger.info(f"Total unique jobs scraped: {len(data)}")

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

logger.info("Starting smart scoring...")

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

scorer = SmartScorer()

for job in tqdm(data, desc="Scoring Jobs"):
    try:
        v3 = job.get("matchscore_api", {})
        v4 = job.get("v4_data", {})

        job_parsed = parse_job_data(job, v3, v4)
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

logger.info("Smart scoring completed.")

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

    from AutoApply.auto_apply_new import (
        load_cache, load_qa, extract_skill_summary,
        apply_to_job, handle_screening,
        AppliedCache, FailedLogger,
        cache_set, PROFILE, MAX_SUCCESS,
    )

    # ── Setup shared state ──────────────────────────────────
    qa_cache_path  = os.path.join(base_dir, "AutoApply", "qa_cache.json")
    master_qa_path = os.path.join(base_dir, "AutoApply", "master_qa.json")

    cache         = load_cache(qa_cache_path)
    qa            = load_qa(master_qa_path)
    skill_summary = extract_skill_summary(resume_text)
    applied_cache = AppliedCache()
    failed_logger = FailedLogger()

    logger.info(f"QA cache: {len(cache)} entries | QA master: {len(qa)} entries | Applied: {len(applied_cache.cache)}")
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
        if score <= 0.5:
            stats["score_filtered"] += 1
            continue

        if job.get("extApp"):
            stats["extapp_filtered"] += 1
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

    total = len(jobs_to_apply)

    logger.info("========== AUTO-APPLY FILTER FUNNEL ==========")
    logger.info(f"Total jobs input:             {len(data)}")
    logger.info(f"Filtered by score <=0.5:      {stats['score_filtered']}")
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
                    cache, qa, failed_logger,
                )
                apply_results[url] = result
                logger.info(f"  Screening result: {result}")

                if result == "applied":
                    applied_cache.mark(url)
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

    logger.info(f"Auto-apply done. Applied: {success_count} | Cache: {len(cache)} entries")

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