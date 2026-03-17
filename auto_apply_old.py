import os
import re
import json
import time
import random
from datetime import datetime, timezone
from difflib import get_close_matches

from ollama import chat
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# ── Config ──────────────────────────────────────────────────

OLLAMA_MODEL = "qwen2.5:7b"

# ══════════════════════════════════════════════════════════════
#  APPLY TO JOB
# ══════════════════════════════════════════════════════════════

SELECTORS = {
    "bot_messages": "li.botItem span",
    "radio_inputs": "input.ssrc__radio",
    "checkbox_inputs": "input.ssrc__checkbox",
    "text_input": "div.textArea[contenteditable='true']",
    "chips": ".chatbot_Chip span",
    "save_btn": "div.sendMsg",
    "applied": "div.applied-job-content",
}

MAX_STEPS = 15
POLL_INTERVAL = 1.0
POLL_RETRIES = 10
POST_SUBMIT_DELAY = 2.0

DELAY_BETWEEN_JOBS = (3, 6)
DELAY_AFTER_SCREENING = (2, 4)
DELAY_ON_ERROR = (5, 10)


# ══════════════════════════════════════════════════════════════
#  APPLY TO JOB
# ══════════════════════════════════════════════════════════════

def detect_platform_error(driver):
    try:
        page_text = driver.page_source.lower()
    except Exception:
        return False

    error_signatures = [
        "there was an error while processing your request",
        "please try again later",
        "maximum number of applies",
        "daily apply limit",
        "you have reached the limit",
        "today's limit reached",
        "too many requests",
        "temporarily blocked",
        "access denied",
        "service unavailable",
        "something went wrong",
    ]
    return any(sig in page_text for sig in error_signatures)


def apply_to_job(driver, logger):
    wait = WebDriverWait(driver, 15)

    try:
        wait.until(lambda d: (
            d.find_elements(By.ID, "already-applied") or
            d.find_elements(By.ID, "apply-button")
        ))
    except TimeoutException:
        logger.warning("No apply state detected.")
        return "no_apply_state"

    already = [e for e in driver.find_elements(By.ID, "already-applied") if e.is_displayed()]
    if already:
        logger.info("Job already applied.")
        return "already_applied"

    try:
        apply_btn = driver.find_element(By.ID, "apply-button")
        btn_text = apply_btn.text.strip().lower()

        if "applied" in btn_text:
            logger.info("Job already applied (button text).")
            return "already_applied"

        if "apply" not in btn_text:
            logger.warning(f"Unexpected button text: {btn_text}")
            return "unexpected_button_state"

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", apply_btn)
        logger.info("Apply button clicked.")
        time.sleep(2)

        if detect_platform_error(driver):
            logger.error("Platform error or daily limit reached.")
            return "platform_error"

    except Exception as e:
        logger.error(f"Error during apply click: {e}")
        return "apply_click_error"

    try:
        wait.until(lambda d: (
            d.find_elements(By.CSS_SELECTOR, "div.applied-job-content") or
            d.find_elements(By.CSS_SELECTOR, "div.chatbot_DrawerContentWrapper")
        ))

        if driver.find_elements(By.CSS_SELECTOR, "div.applied-job-content"):
            logger.info("Application successful.")
            return "applied"

        if driver.find_elements(By.CSS_SELECTOR, "div.chatbot_DrawerContentWrapper"):
            logger.info("Screening questions detected.")
            return "screening"

    except TimeoutException:
        logger.warning("No post-apply state detected.")
        return "unknown"


# ══════════════════════════════════════════════════════════════
#  MASTER Q&A
# ══════════════════════════════════════════════════════════════

def normalize_question(q):
    return re.sub(r'\s+', ' ', q.strip().lower().rstrip('?')).strip()


def load_master_qa(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {normalize_question(r["question"]): r for r in raw}


def save_master_qa(path, qa_map):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(qa_map.values()), f, indent=2)


def lookup_qa(qa_map, question, options=None):
    key = normalize_question(question)
    if key not in qa_map:
        return None
    entry = qa_map[key]
    answer = entry["answer"]
    if options and answer not in options:
        matched, _, _ = fuzzy_match_option(answer, options)
        return matched
    return answer


def upsert_qa(qa_map, question, answer, input_type, options=None):
    key = normalize_question(question)
    qa_map[key] = {
        "question": question.strip(),
        "answer": answer,
        "input_type": input_type,
        "options": options or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════
#  OLLAMA
# ══════════════════════════════════════════════════════════════

def ask_ollama(prompt):
    response = chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.message.content.strip()


def find_related_qa(qa_map, question, top_n=5):
    q_norm = normalize_question(question)
    q_words = set(q_norm.split())
    scored = []
    for key, entry in qa_map.items():
        overlap = len(q_words & set(key.split()))
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_n]]


def build_prompt(question, resume_context, qa_map=None, options=None):
    base = f"Job screening question:\n{question}\n\nCandidate Profile:\n{resume_context}\n\n"

    if qa_map:
        related = find_related_qa(qa_map, question)
        if related:
            qa_lines = "\n".join(
                f"Q: {r['question']} → A: {r['answer']}" for r in related
            )
            base += f"Previously answered questions by this candidate:\n{qa_lines}\n\n"

    if options:
        base += f"Available Options (return EXACTLY one):\n{options}\n\n"
        base += "Return ONLY the exact option text. No explanation."
    else:
        base += "If numeric expected, return only the number. Otherwise return a concise answer.\nNo explanation."
    return base


def get_answer(question, resume_context, qa_map, options=None):
    cached = lookup_qa(qa_map, question, options)
    if cached:
        return cached, "master_qa"
    prompt = build_prompt(question, resume_context, qa_map, options)
    answer = ask_ollama(prompt)
    return answer, "ollama"


# ══════════════════════════════════════════════════════════════
#  SCREENING UTILS
# ══════════════════════════════════════════════════════════════

def fuzzy_match_option(answer, options):
    if answer in options:
        return answer, False, None

    lowered = [o.lower() for o in options]
    matches = get_close_matches(answer.lower(), lowered, n=1, cutoff=0.5)
    if matches:
        idx = lowered.index(matches[0])
        return options[idx], True, f"fuzzy_matched: '{answer}' -> '{options[idx]}'"

    return options[0], True, f"no_match: '{answer}' -> fallback '{options[0]}'"


def save_step(log_path, record):
    data = load_steps(log_path)
    data.append(record)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_steps(log_path):
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_record(job_url, step, question, input_type, options=None, answer="",
                fallback_used=False, fallback_reason=None, source="ollama"):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_url": job_url,
        "step": step,
        "question": question,
        "input_type": input_type,
        "options": options or [],
        "selected_answer": answer,
        "answer_source": source,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "model": OLLAMA_MODEL,
    }


def capture_chatbot_html(driver):
    try:
        container = driver.find_element(By.CSS_SELECTOR, "div.chatbot_DrawerContentWrapper")
        return container.get_attribute("outerHTML")
    except Exception:
        return driver.page_source


def save_unknown_source(driver, step, dump_dir="screening_dumps"):
    os.makedirs(dump_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(dump_dir, f"unknown_step{step}_{ts}.html")
    html = capture_chatbot_html(driver)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


def click_submit(driver):
    btn = driver.find_element(By.CSS_SELECTOR, SELECTORS["save_btn"])
    driver.execute_script("arguments[0].click();", btn)


def wait_for_new_question(driver, last_question):
    for _ in range(POLL_RETRIES):
        msgs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["bot_messages"])
        if msgs:
            current = msgs[-1].text.strip()
            if current and current != last_question:
                return current
        time.sleep(POLL_INTERVAL)
    return None


# ══════════════════════════════════════════════════════════════
#  INPUT HANDLERS
# ══════════════════════════════════════════════════════════════

def handle_radio(driver, question, resume_context, qa_map):
    inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["radio_inputs"])
    options = [r.get_attribute("value") for r in inputs]

    raw, source = get_answer(question, resume_context, qa_map, options)
    answer, fallback, reason = fuzzy_match_option(raw, options)

    radio = driver.find_element(By.XPATH, f'//input[@value="{answer}"]')
    driver.execute_script("arguments[0].click();", radio)
    click_submit(driver)

    upsert_qa(qa_map, question, answer, "radio", options)
    return options, answer, fallback, reason, source


def handle_text(driver, question, resume_context, qa_map):
    wait = WebDriverWait(driver, 15)
    box = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["text_input"])))

    answer, source = get_answer(question, resume_context, qa_map)

    driver.execute_script("arguments[0].innerText = '';", box)
    box.send_keys(answer)
    click_submit(driver)

    upsert_qa(qa_map, question, answer, "text")
    return answer, source


def handle_multiselect(driver, question, resume_context, qa_map):
    inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["checkbox_inputs"])
    options = [i.get_attribute("value") for i in inputs]

    raw, source = get_answer(question, resume_context, qa_map, options)

    selected = [x.strip() for x in str(raw).split(",")]
    selected_clean = []
    for s in selected:
        matched, _, _ = fuzzy_match_option(s, options)
        selected_clean.append(matched)

    for opt in selected_clean:
        checkbox = driver.find_element(By.XPATH, f'//input[@value="{opt}"]')
        driver.execute_script("arguments[0].click();", checkbox)

    click_submit(driver)
    upsert_qa(qa_map, question, selected_clean, "multiselect", options)
    return options, selected_clean, source


def handle_chips(driver, question, resume_context, qa_map):
    chips = driver.find_elements(By.CSS_SELECTOR, SELECTORS["chips"])
    chip_texts = [c.text.strip() for c in chips]
    skip_keywords = {"skip", "skip this question"}

    non_skip = [(i, t) for i, t in enumerate(chip_texts) if t.lower() not in skip_keywords]

    if non_skip:
        idx, text = non_skip[0]
        driver.execute_script("arguments[0].click();", chips[idx])
        upsert_qa(qa_map, question, text, "chip", chip_texts)
        return chip_texts, text, "chip", "direct"

    try:
        wait = WebDriverWait(driver, 5)
        box = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["text_input"])))
        answer, source = get_answer(question, resume_context, qa_map)
        driver.execute_script("arguments[0].innerText = '';", box)
        box.send_keys(answer)
        click_submit(driver)
        upsert_qa(qa_map, question, answer, "text_with_chip_skip", chip_texts)
        return chip_texts, answer, "text_with_chip_skip", source
    except Exception:
        driver.execute_script("arguments[0].click();", chips[0])
        upsert_qa(qa_map, question, chip_texts[0], "chip", chip_texts)
        return chip_texts, chip_texts[0], "chip", "fallback"


# ══════════════════════════════════════════════════════════════
#  SCREENING HANDLER
# ══════════════════════════════════════════════════════════════

def handle_screening(driver, logger, resume_context, job_url,
                     log_path="screening_logs.json",
                     master_qa_path="master_qa.json"):
    logger.info("Starting screening handler...")
    qa_map = load_master_qa(master_qa_path)
    logger.info(f"Master Q&A loaded: {len(qa_map)} entries")
    last_question = None

    for step_num in range(1, MAX_STEPS + 1):
        question = wait_for_new_question(driver, last_question)
        if not question:
            logger.warning("Timed out waiting for new question.")
            save_master_qa(master_qa_path, qa_map)
            return "timeout"

        last_question = question
        logger.info(f"[Step {step_num}] {question}")

        terminal_phrases = [
            "thank you for your responses",
            "thank you for your response",
            "application submitted",
            "successfully applied",
        ]

        if any(p in question.lower() for p in terminal_phrases):
            logger.info("Terminal confirmation detected.")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["applied"]))
                )
                logger.info("Application completed successfully.")
                save_master_qa(master_qa_path, qa_map)
                return "applied"
            except TimeoutException:
                logger.warning("Terminal message but no applied div.")
                save_master_qa(master_qa_path, qa_map)
                return "terminal_no_applied_div"

        checkbox_inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["checkbox_inputs"])
        radio_inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["radio_inputs"])
        text_inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["text_input"])
        chips = driver.find_elements(By.CSS_SELECTOR, SELECTORS["chips"])

        if checkbox_inputs:
            options, answer, source = handle_multiselect(driver, question, resume_context, qa_map)
            record = make_record(job_url, step_num, question, "multiselect",
                                 options=options, answer=str(answer), source=source)

        elif radio_inputs:
            options, answer, fallback, reason, source = handle_radio(
                driver, question, resume_context, qa_map)
            record = make_record(job_url, step_num, question, "radio",
                                 options, answer, fallback, reason, source)

        elif text_inputs:
            try:
                answer, source = handle_text(driver, question, resume_context, qa_map)
                record = make_record(job_url, step_num, question, "text",
                                     answer=answer, source=source)
            except Exception as e:
                logger.warning(f"Text input failed: {e}")
                save_master_qa(master_qa_path, qa_map)
                return "text_input_error"

        elif chips:
            chip_texts, answer, input_type, source = handle_chips(
                driver, question, resume_context, qa_map)
            record = make_record(job_url, step_num, question, input_type,
                                 chip_texts, answer, source=source)

        else:
            dump_path = save_unknown_source(driver, step_num)
            logger.warning(f"Unknown input type. Source saved: {dump_path}")
            record = make_record(job_url, step_num, question, "unknown")
            record["source_dump"] = dump_path
            save_step(log_path, record)
            save_master_qa(master_qa_path, qa_map)
            return "unknown_input"

        logger.info(f"  -> {answer} (via {source})")
        save_step(log_path, record)
        save_master_qa(master_qa_path, qa_map)
        time.sleep(POST_SUBMIT_DELAY)

        if driver.find_elements(By.CSS_SELECTOR, SELECTORS["applied"]):
            logger.info("Application completed.")
            return "applied"

    logger.warning("Max screening steps reached.")
    save_master_qa(master_qa_path, qa_map)
    return "max_steps_reached"


# ══════════════════════════════════════════════════════════════
#  APPLY SUMMARY
# ══════════════════════════════════════════════════════════════

def save_apply_summary(summary_path, results):
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


# ══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def run_auto_apply(driver, job_data, logger, output_folder, base_dir, resume_text):

    # ── Filter and sort jobs ────────────────────────────────
    apply_jobs = [
        job for job in job_data
        if not job.get("extApp", False)
        and job.get("skillMatch", False)
    ]
    apply_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)

    apply_urls = [(job["URL"], job.get("Job Title", ""), job.get("Company Name", "")) for job in apply_jobs]
    total = len(apply_urls)
    logger.info(f"Auto-apply: {total} jobs to process")

    if total == 0:
        logger.info("No jobs matched for auto-apply.")
        return {}

    # ── Paths ───────────────────────────────────────────────
    screening_log = os.path.join(output_folder, "screening_logs.json")
    master_qa = os.path.join(base_dir, "master_qa.json")
    summary_path = os.path.join(output_folder, "apply_summary.json")

    # ── Counters ────────────────────────────────────────────
    results = []
    url_status_map = {}
    counts = {
        "applied": 0,
        "already_applied": 0,
        "screening_applied": 0,
        "screening_failed": 0,
        "error": 0,
        "skipped": 0,
        "platform_error": 0,
    }

    start_time = time.time()

    # ── Apply loop ──────────────────────────────────────────
    for idx, (url, title, company) in enumerate(apply_urls, 1):
        entry = {
            "index": idx,
            "url": url,
            "title": title,
            "company": company,
            "status": None,
            "screening_result": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            logger.info(f"[{idx}/{total}] {title} @ {company}")
            logger.info(f"  URL: {url}")

            driver.get(url)
            time.sleep(random.uniform(1.5, 3.0))

            status = apply_to_job(driver, logger)
            entry["status"] = status

            if status == "applied":
                counts["applied"] += 1

            elif status == "already_applied":
                counts["already_applied"] += 1

            elif status == "screening":
                screening_result = handle_screening(
                    driver, logger, resume_text, url,
                    log_path=screening_log,
                    master_qa_path=master_qa,
                )
                entry["screening_result"] = screening_result
                logger.info(f"  Screening result: {screening_result}")

                if screening_result == "applied":
                    counts["screening_applied"] += 1
                else:
                    counts["screening_failed"] += 1

                time.sleep(random.uniform(*DELAY_AFTER_SCREENING))

            elif status == "platform_error":
                counts["platform_error"] += 1
                logger.error("Platform error detected. Pausing 60s...")
                time.sleep(60)

            else:
                counts["skipped"] += 1

        except Exception as e:
            logger.error(f"  Error: {e}")
            entry["status"] = "error"
            entry["error"] = str(e)
            counts["error"] += 1
            time.sleep(random.uniform(*DELAY_ON_ERROR))

        results.append(entry)

        # Track final status per URL
        final_status = entry.get("screening_result") or entry.get("status") or "unknown"
        url_status_map[url] = final_status

        save_apply_summary(summary_path, {
            "counts": counts,
            "elapsed_seconds": round(time.time() - start_time),
            "total_jobs": total,
            "results": results,
        })

        time.sleep(random.uniform(*DELAY_BETWEEN_JOBS))

    elapsed = round(time.time() - start_time)

    logger.info("=" * 50)
    logger.info("AUTO-APPLY SUMMARY")
    logger.info(f"  Total jobs:        {total}")
    logger.info(f"  Applied:           {counts['applied']}")
    logger.info(f"  Screening applied: {counts['screening_applied']}")
    logger.info(f"  Already applied:   {counts['already_applied']}")
    logger.info(f"  Screening failed:  {counts['screening_failed']}")
    logger.info(f"  Skipped:           {counts['skipped']}")
    logger.info(f"  Errors:            {counts['error']}")
    logger.info(f"  Platform errors:   {counts['platform_error']}")
    logger.info(f"  Time elapsed:      {elapsed}s")
    logger.info(f"  Summary saved:     {summary_path}")
    logger.info("=" * 50)

    return url_status_map