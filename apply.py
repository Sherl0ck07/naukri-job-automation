import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import os
import datetime
run = "B"

# ===== Paths & Output Setup =====
base_dir = os.path.dirname(os.path.abspath(__file__))

# Create timestamp for outputs
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
# ===== Load Config & Define Filenames =====
if run == "A":
    config_path = os.path.join(base_dir, "config-old.json")
    new_filename = f"job_crawl_summary_A_{timestamp}.html"
else:
    config_path = os.path.join(base_dir, "config.json")
    new_filename = f"job_crawl_summary_B_{timestamp}.html"

# Load config file
with open(config_path, "r") as f:
    config = json.load(f)

# ===== Extract Config Parameters =====
resume_path = config.get("resume_path")
username = config.get("username")
password = config.get("password")

# --- Chrome options ---
options = Options()
options.add_experimental_option("prefs", {
    "credentials_enable_service": False,
    "profile.password_manager_enabled": False,
    "profile.managed_default_content_settings.images": 2
})
options.add_argument("--start-maximized")
options.add_experimental_option('excludeSwitches', ['enable-logging'])
options.add_argument("--log-level=3")

# Silence ChromeDriver logs
service = Service(log_path='NUL')  # Windows null device
driver = webdriver.Chrome(service=service, options=options)


# ===== Login to Naukri =====
driver.get("https://www.naukri.com/nlogin/login")

WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "usernameField"))).send_keys(username)
WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "passwordField"))).send_keys(password)
WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))).click()

# --- Load JSON data ---
json_path = r"C:\Users\imjad\Desktop\case study\st\oneClickShell\outputs\run_20250816_144833\job_data_20250816_144833.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# --- Filter & sort data ---
data = sorted(
    (job for job in data
     if isinstance(job, dict)
     and isinstance(job.get("score"), (float, int))
     and job.get("score") is not None
     and job.get("score") > 0.5),  # threshold
    key=lambda x: x["score"],
    reverse=True
)

# --- Auto-apply jobs ---
wait = WebDriverWait(driver, 10)  # 10 seconds wait

for job in data:
    if not job.get("extApp") and job.get("skillMatch"):
        try:
            driver.get(job["URL"])

            # Wait for the "Apply" button to be clickable
            apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "apply-button")))
            apply_btn.click()

            from selenium.common.exceptions import TimeoutException

            # Wait for either chatbot drawer (failure) or success icon
            try:
                # Wait up to 5 seconds for the failure element (chatbot) first
                wait_short = WebDriverWait(driver, 5)
                chatbot = wait_short.until(EC.presence_of_element_located((By.CLASS_NAME, "chatbot_DrawerContentWrapper")))
                # If we reach here, chatbot appeared → mark as failed
                job["auto_apply_status"] = False
                print(f"Auto-apply blocked by chatbot: {job['Job Title']}")
            except TimeoutException:
                # Chatbot did not appear → check for success icon
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "img[alt='success-icon']")))
                    job["auto_apply_status"] = True
                    print(f"Applied successfully: {job['Job Title']}")
                except TimeoutException:
                    job["auto_apply_status"] = False
                    print(f"Apply failed: {job['Job Title']}")

        except (NoSuchElementException, TimeoutException) as e:
            job["auto_apply_status"] = False
            print(f"Error applying to job {job['Job Title']}: {str(e)}")

            

driver.quit()

# --- Save updated JSON ---
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

from report import generate_html
base_dir = os.path.dirname(json_path)
new_filename = os.path.join(base_dir, new_filename)


generate_html(data,new_filename)