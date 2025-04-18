import sys
import time
import random
import re
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)

def setup_driver():
    service = Service(ChromeDriverManager().install())
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')

    chrome_versions = ['120.0.0.0', '119.0.0.0', '118.0.0.0', '121.0.0.0']
    chrome_version = random.choice(chrome_versions)
    user_agent = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36'
    chrome_options.add_argument(f'--user-agent={user_agent}')

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                run_on_insecure_origins=True
        )
        return driver
    except WebDriverException as e:
        logger.error(f"WebDriver setup failed: {e}")
        print(f"Error - WebDriver setup failed: {e}", file=sys.stderr)
        return None

def fetch_qld_details(driver):
    try:
        wait = WebDriverWait(driver, 10)
        data_dl = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "dl.data")))
        items = data_dl.find_elements(By.TAG_NAME, "dd")
        if len(items) >= 3:
            desc_text = items[2].text.strip()
            # Example: "2020 MAZDA MAZDA6 SEDAN"
            match = re.match(r"(\d{4})\s+(\w+)\s+(.+)", desc_text)
            if match:
                year, make, model = match.groups()
                return {
                    "status": "registered",
                    "year": year,
                    "make": make,
                    "model": model,
                    "colour": "N/A"
                }
        return {"status": "registered", "details_error": "Could not parse vehicle description"}
    except Exception as e:
        logger.error(f"Failed to fetch vehicle details: {e}")
        return {"status": "registered", "details_error": "Could not fetch vehicle details"}

def check_qld_rego(driver, plate_number):
    try:
        url = "https://www.service.transport.qld.gov.au/checkrego/public/Welcome.xhtml"
        driver.get(url)

        # Step 1: Click Continue
        wait = WebDriverWait(driver, 15)
        continue_button = wait.until(EC.element_to_be_clickable((By.ID, "checkRegoAboutThisService:aboutThisServiceForm:continueButton")))
        driver.execute_script("arguments[0].click();", continue_button)

        # Step 2: Click Accept
        accept_button = wait.until(EC.element_to_be_clickable((By.ID, "tAndCForm:confirmButton")))
        driver.execute_script("arguments[0].click();", accept_button)

        # Step 3: Enter Plate Number
        plate_input = wait.until(EC.presence_of_element_located((By.ID, "vehicleSearchForm:plateNumber")))
        plate_input.clear()
        plate_input.send_keys(plate_number)

        # Step 4: Click Search
        search_button = wait.until(EC.element_to_be_clickable((By.ID, "vehicleSearchForm:confirmButton")))
        driver.execute_script("arguments[0].click();", search_button)

        # Step 5: Wait and fetch details
        return fetch_qld_details(driver)

    except TimeoutException as e:
        logger.error(f"Timeout: {e}")
        return {"status": "timeout"}
    except Exception as e:
        logger.error(f"Unexpected error during QLD check: {e}")
        return {"status": "error"}

def main():
    print("QLD Registration Checker. Type 'quit' to exit.")
    while True:
        driver = None
        try:
            user_input = input("Enter plate: ")
            if user_input.lower() == 'quit':
                break

            plate = user_input.strip().upper()
            if not plate:
                continue

            driver = setup_driver()
            if driver:
                result = check_qld_rego(driver, plate)
                print(result)
        except EOFError:
            print("\nExiting.")
            break
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print("Error - An unexpected issue occurred. Please try again.", file=sys.stderr)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error quitting WebDriver: {e}")

if __name__ == "__main__":
    main()
