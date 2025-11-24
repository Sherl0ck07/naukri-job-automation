import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- Block detection ----------
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


# ---------- Load JSON ----------
file_path = r"C:\Users\imjad\Desktop\case study\st\oneClickShell\outputs\run_20251111_073319\job_data_20251111_073319.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)


# ---------- Selenium driver ----------
driver = webdriver.Chrome()

# ---------- Process each job entry ----------
for job in data:
    url = job.get("URL") or job.get("url")  # handle both cases

    if not url:
        continue
    
    try:
        driver.get(url)

        # Check if match block exists
        exists = match_block_exists(driver, timeout=2)

        if exists:
            print(url)
        else:
            pass

    except Exception as e:
        print("Error opening URL:", url, "|", str(e))

driver.quit()
