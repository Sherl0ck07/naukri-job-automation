#========= helpers.py =========

import sys
from tqdm import tqdm
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from score import resume_jd_similarity,embed
import time
from selenium.common.exceptions import TimeoutException

from urllib.parse import urlparse, urlunparse

def build_page_url(base_url, page):
    """
    Build the correct pagination URL from the given base_url and page number.
    """
    if page == 1:
        return base_url
    
    # Split URL
    parsed = urlparse(base_url)
    path = parsed.path  # e.g. "/freelancing-freelancer-jobs"
    
    if not path.endswith("-jobs"):
        raise ValueError(f"Unexpected URL format: {base_url}")
    
    # Add -{page} before the query
    page_path = path + f"-{page}"
    
    return urlunparse(parsed._replace(path=page_path))


# ===== Collect Job Links =====
def collect_job_links(driver,job_links_xpath,max_pages=100):
    base_url = driver.current_url 
    
    job_links = set()

    # Wrap page loop in tqdm
    for page in tqdm(range(1, max_pages + 1), desc="Collecting job links", unit="page"):

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.XPATH, job_links_xpath))
            )
            new_links = {
                link.get_attribute("href")
                for link in driver.find_elements(By.XPATH, job_links_xpath)
                if link.get_attribute("href")
            }
            job_links.update(new_links)


            try:
                page_url = build_page_url(base_url, page+1)
                driver.get(page_url)

            except Exception as e:
                tqdm.write(f"Error on page {page+1} {e}")

        except Exception as e:
            tqdm.write(f"Error on page {page+1} {e}")

    return list(job_links)

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

def check_status(driver,wait,label_text):
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
    
# ===== Extract Job Details =====
def extract_job_details(driver,url):
    try:
        driver.get(url)

        try:
            job_desc_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//section[contains(@class, 'job-desc')]"))
            )
            job_description = job_desc_element.text.strip()
        except:
            job_description = "N/A"

        try:
            job_title = driver.find_element(By.XPATH, "//h1").text.strip()
        except:
            job_title = "N/A"

        try:
            location = driver.find_element(By.XPATH, "//span[contains(@class, 'location')]").text.strip()
        except:
            location = "N/A"

        try:
            company_name = driver.find_element(By.XPATH, "//div[contains(@class, 'comp-name')]/a").text.strip()
        except:
            company_name = "N/A"

        try:
            age_span = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Posted:')]/following-sibling::span"))
            )
            age_text = age_span.text.strip()
        except:
            age_text = "N/A"


        try:
            applicants_span = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Applicants:')]/following-sibling::span"))
            )
            applicants_text = applicants_span.text.strip()
        except:
            applicants_text = "N/A"

        extApp = "Apply on company site" in driver.page_source

        if match_block_exists(driver):
            earlyApplicant = check_status(driver, WebDriverWait(driver, 2), "Early Applicant")
            skillMatch = check_status(driver, WebDriverWait(driver, 2), "Keyskills")
            locationMatch = check_status(driver, WebDriverWait(driver, 2), "Location")
            experienceMatch = check_status(driver, WebDriverWait(driver, 2), "Work Experience")
        else:
            earlyApplicant = False
            skillMatch = False
            locationMatch = False
            experienceMatch = False
            

        # Now store everything in job_details dict
        job_details = {
            "Job Title": job_title,
            "age": age_text,
            "URL": url,
            "job_description": job_description,
            "Company Name": company_name,
            "location": location,
            "extApp": extApp,
            "skillMatch": skillMatch,
            "earlyApplicant": earlyApplicant,
            "locationMatch": locationMatch,
            "experienceMatch": experienceMatch,
            "applicants_text": applicants_text
        }

        
        return job_details

    except Exception as e:
        
        return None
    

def scrape_jobs(data,driver,job_links_xpath,n):
    global job_links, failed_count
    job_links = collect_job_links(driver, job_links_xpath, max_pages=n)
    total_jobs = len(job_links)

    job_count = 0
    failed_count = 0

    with tqdm(total=total_jobs, desc="Scraping Jobs", unit="job", file=sys.stdout) as pbar:
        for idx, job_url in enumerate(job_links):
            job_data = extract_job_details(driver,job_url)

            if job_data:
                data.append(job_data)
                job_count += 1
            else:
                failed_count += 1
                tqdm.write(f"Failed {idx + 1}/{total_jobs}: Skipped")

            pbar.update(1)

   

def add_similarity_score(job, resume_embed,jd_text,model_):
    try:
        jd_text = job.get("job_description", "")
        if jd_text and jd_text != "N/A":
            # Compute all scores
            job["score"] = resume_jd_similarity(resume_embed,embed(model_,jd_text))

        else:
            job["score"] = None

    except Exception as e:
        job["score"] = None
        print(f"Error computing score for job {job.get('Job Title','N/A')}: {e}")

    return job


def handle_login(driver, username, password, logger):
    wait = WebDriverWait(driver, 12)

    # check if already logged in (profile name visible)
    try:
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.info__heading[title]"))
        )
        logger.info("Already logged in.")
        return
    except TimeoutException:
        logger.info("Not logged in. Logging in now...")

    # username
    username_input = wait.until(
        EC.element_to_be_clickable((By.ID, "usernameField"))
    )
    username_input.clear()
    username_input.send_keys(username)

    # password
    password_input = wait.until(
        EC.element_to_be_clickable((By.ID, "passwordField"))
    )
    password_input.clear()
    password_input.send_keys(password)

    # login button
    login_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))
    )
    login_button.click()

    # confirm login by waiting for profile element
    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.info__heading[title]"))
    )

    logger.info("Login successful.")
