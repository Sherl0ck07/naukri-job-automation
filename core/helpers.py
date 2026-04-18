#========= helpers.py =========

import re
import sys
import json
import time
from tqdm import tqdm
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from urllib.parse import urlparse, urlunparse


def build_page_url(base_url, page):
    if page == 1:
        return base_url
    
    parsed = urlparse(base_url)
    path = parsed.path

    page_path = path + f"-{page}"
    
    return urlunparse(parsed._replace(path=page_path))


def generate_pagination_urls(base_url, max_pages):
    urls = []
    for page in range(1, max_pages + 1):
        url = build_page_url(base_url, page)
        urls.append(url)
    return urls


def collect_links_from_page(driver, page_url, job_links_xpath):
    try:
        driver.get(page_url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.XPATH, job_links_xpath))
        )

        links = set()
        elements = driver.find_elements(By.XPATH, job_links_xpath)
        for link in elements:
            href = link.get_attribute("href")
            if href:
                # Normalize: strip query params and fragment so the same job
                # URL with different tracking params doesn't count as two jobs.
                parsed = urlparse(href)
                clean = urlunparse(parsed._replace(query='', fragment=''))
                links.add(clean)

        return links
    except Exception as e:
        return set()


def match_block_exists(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(text(), 'Job match score')]")
            )
        )
        return True
    except:
        return False


def check_status(driver, wait, label_text):
    try:
        wait.until(EC.presence_of_all_elements_located((
            By.XPATH,
            f"//div[span[contains(text(), '{label_text}')]]//i"
        )))
        return bool(driver.find_elements(
            By.XPATH,
            f"//div[span[contains(text(), '{label_text}')]]//i[contains(@class, 'ni-icon-check_circle')]"
        ))
    except:
        return False


def extract_job_id(job_url: str) -> str:
    """Extract numeric job ID from Naukri job URL.

    Primary:  standard format — 10+ digit ID before '?' or end of string.
    Fallback: last numeric sequence of 6+ digits in the URL path, for
              non-standard or shortened Naukri URLs that still contain an ID.
    """
    match = re.search(r'-(\d{10,})(?:\?|$)', job_url)
    if match:
        return match.group(1)
    path = urlparse(job_url).path
    numbers = re.findall(r'\d{6,}', path)
    if numbers:
        return numbers[-1]
    return None


def capture_all_job_apis(driver, job_id: str = None) -> dict:
    """
    Single log read — captures both v3 matchscore and v4 job data.
    Returns {"v3": {...}, "v4": {...}}
    """
    result = {"v3": {}, "v4": {}}

    try:
        logs = driver.get_log("performance")

        for entry in logs:
            try:
                message = json.loads(entry["message"])["message"]

                if message.get("method") != "Network.responseReceived":
                    continue

                response   = message.get("params", {}).get("response", {})
                url        = response.get("url", "")
                request_id = message.get("params", {}).get("requestId")

                is_v3 = "v3/job" in url and "matchscore" in url
                is_v4 = "/jobapi/v4/job/" in url and (job_id is None or job_id in url)

                if not (is_v3 or is_v4):
                    continue

                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody",
                        {"requestId": request_id}
                    )
                    if body and body.get("body"):
                        parsed = json.loads(body["body"])
                        if is_v3:
                            result["v3"] = parsed
                        elif is_v4:
                            result["v4"] = parsed
                except:
                    pass

                # Early exit once both captured
                if result["v3"] and result["v4"]:
                    break

            except:
                continue
    except:
        pass

    return result


# Keep for backward compatibility
def capture_matchscore_api(driver, wait_time=3):
    return capture_all_job_apis(driver).get("v3", {})


def extract_job_details(driver, url):
    try:
        job_id = extract_job_id(url)

        # Clear performance logs before loading page
        try:
            driver.get_log("performance")
        except:
            pass
        
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        # Check for expired / unavailable job page early — no point scraping further
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "job you are looking for is" in page_text.lower():
                return None
        except:
            pass

        try:
            job_desc_element = wait.until(
                EC.presence_of_element_located((By.XPATH, "//section[contains(@class, 'job-desc')]"))
            )
            job_description = job_desc_element.text.strip()
        except:
            job_description = "N/A"

        # Check if already applied
        try:
            already_applied = driver.find_element(By.ID, "already-applied")
            if already_applied:
                return None
        except:
            pass
        # 
        try:
            walkin = driver.find_element(By.ID, "walkin-button")
            if walkin:
                return None
        except:
            pass

        try:
            job_title = driver.find_element(By.XPATH, "//h1").text.strip()
        except:
            job_title = "N/A"

        try:
            location = driver.find_element(By.XPATH, "//span[contains(@class, 'location')]").text.strip()
        except:
            location = "N/A"

        try:
            wfh_element = driver.find_element(
                By.XPATH, "//div[contains(@class, 'wfhmode')]"
            )
            work_mode = wfh_element.text.strip()
        except:
            work_mode = "N/A"

        try:
            company_name = driver.find_element(By.XPATH, "//div[contains(@class, 'comp-name')]/a").text.strip()
        except:
            company_name = "N/A"

        try:
            age_span = wait.until(
                EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Posted:')]/following-sibling::span"))
            )
            age_text = age_span.text.strip()
        except:
            age_text = "N/A"

        try:
            applicants_span = wait.until(
                EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Applicants:')]/following-sibling::span"))
            )
            applicants_text = applicants_span.text.strip()
        except:
            applicants_text = "N/A"

        extApp = "Apply on company site" in driver.page_source

        skills = []
        try:
            skill_div = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'key-skill')]"))
            )
            span_elements = skill_div.find_elements(By.XPATH, ".//span")

            for span in span_elements:
                text = span.text.strip()
                if text:
                    skills.append(text)

        except:
            skills = []

        # Single log read — captures both v3 and v4
        api_data = capture_all_job_apis(driver, job_id=job_id)
        matchscore_data = api_data.get("v3", {})
        v4_data         = api_data.get("v4", {})

        skills_match_count = matchscore_data.get("Keyskills", 0)
        skill_mismatch = matchscore_data.get("skillMismatch", "")
        work_experience_match = matchscore_data.get("workExperience", False)
        industry_match = matchscore_data.get("industry", False)
        location_match_api = matchscore_data.get("location", False)
        early_applicant_api = matchscore_data.get("earlyApplicant", False)
        education_match = matchscore_data.get("education", False)
        functional_area_match = matchscore_data.get("functionalArea", False)
        
        if not matchscore_data and match_block_exists(driver):
            short_wait = WebDriverWait(driver, 2)
            earlyApplicant = check_status(driver, short_wait, "Early Applicant")
            skillMatch = check_status(driver, short_wait, "Keyskills")
            locationMatch = check_status(driver, short_wait, "Location")
            experienceMatch = check_status(driver, short_wait, "Work Experience")
        else:
            earlyApplicant = early_applicant_api
            skillMatch = skills_match_count > 0
            locationMatch = location_match_api
            experienceMatch = work_experience_match

        job_details = {
            "job_id": job_id,
            "Job Title": job_title,
            "age": age_text,
            "URL": url,
            "job_description": job_description,
            "Company Name": company_name,
            "location": location,
            "work_mode": work_mode, 
            "extApp": extApp,
            "applicants_text": applicants_text,

            "skills": skills,

            # Boolean match fields
            "skillMatch": skillMatch,
            "earlyApplicant": earlyApplicant,
            "locationMatch": locationMatch,
            "experienceMatch": experienceMatch,
            
            # Additional API fields
            "industryMatch": industry_match,
            "educationMatch": education_match,
            "functionalAreaMatch": functional_area_match,
            "keyskillsCount": skills_match_count,
            "skillMismatch": skill_mismatch,
            
            "matchscore_api": matchscore_data,  # v3
            "v4_data": v4_data,                 # v4 — full job details
        }

        return job_details

    except Exception as e:
        return None


def handle_login(driver, username, password, logger):
    wait = WebDriverWait(driver, 50)

    username_input = wait.until(
        EC.element_to_be_clickable((By.ID, "usernameField"))
    )
    username_input.clear()
    username_input.send_keys(username)

    password_input = wait.until(
        EC.element_to_be_clickable((By.ID, "passwordField"))
    )
    password_input.clear()
    password_input.send_keys(password)

    login_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))
    )
    login_button.click()

    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.info__heading[title]"))
    )

    logger.info("Login successful.")