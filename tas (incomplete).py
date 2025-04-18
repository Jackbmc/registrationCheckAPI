import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
import logging
import random
import re

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)

def setup_driver():
    """Sets up a new Selenium WebDriver instance."""
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
        logger.error(f"WebDriver setup failed: {e}", exc_info=False)
        print(f"Error - WebDriver setup failed ({e.__class__.__name__}). Check drivers/chrome compatibility.", file=sys.stderr)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during WebDriver setup: {e}", exc_info=True)
        print("Error - Unexpected error during WebDriver setup.", file=sys.stderr)
        return None

def check_tas_rego(driver, plate_number):
    """
    Checks Tasmania registration status and fetches vehicle details,
    outputting only make, model, colour, and year.
    """
    try:
        url = 'https://www.transport.tas.gov.au/rego-status/'
        driver.set_page_load_timeout(30)  # Increased timeout
        try:
            driver.get(url)
        except TimeoutException:
            logger.error(f"Timeout loading Tasmania registration page: {url}")
            return {"status": "invalid_page_timeout"}

        wait = WebDriverWait(driver, 20)  # Increased wait

        plate_input = wait.until(EC.presence_of_element_located((By.NAME, "plate")))
        search_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "form.form-plate input[type='submit']")))

        plate_input.clear()
        plate_input.send_keys(plate_number)

        # Execute the JavaScript onclick event directly
        driver.execute_script("arguments[0].click();", search_button)
        time.sleep(2) # Added a short explicit wait after clicking

        # Wait for the results container to be present
        results_container = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "container")))
        details = {}
        rows = results_container.find_elements(By.CLASS_NAME, "row")

        for row in rows:
            columns = row.find_elements(By.CLASS_NAME, "column")
            if len(columns) == 2:
                label = columns[0].text.strip()
                value_span = columns[1].find_elements(By.TAG_NAME, "span")
                value = value_span[0].text.strip() if value_span else ""
                details[label.lower().replace(' ', '_')] = value

        extracted_data = {}
        extracted_data['make'] = details.get('vehicle_make')
        extracted_data['model'] = details.get('vehicle_model')
        extracted_data['colour'] = details.get('colour')
        extracted_data['year'] = details.get('manufacture_year')
        status_text = details.get('registration_status', '').lower()

        if "registered" in status_text:
            return {"status": "registered", **extracted_data}
        elif "expired" in status_text or "cancelled" in status_text:
            return {"status": "unregistered"}
        else:
            return {"status": "unknown"}

    except TimeoutException:
        logger.warning("Timeout waiting for Tasmania results.")
        return {"status": "timeout"}
    except NoSuchElementException:
        logger.error("Could not find expected elements on the Tasmania page.")
        return {"status": "element_not_found"}
    except WebDriverException as e:
        logger.error(f"WebDriver error during Tasmania check: {e}", exc_info=False)
        return {"status": "webdriver_error"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during Tasmania check: {e}", exc_info=True)
        return {"status": "exception"}
    # No finally block here - driver is quit in main loop

def main():
    """Runs the interactive loop for Tasmania registration checks."""
    print("Tasmania Registration Checker. Type 'quit' to exit.")
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
                result = check_tas_rego(driver, plate)
                print(result)
            else:
                pass

        except EOFError:
            print("\nExiting.")
            break
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop iteration: {e}", exc_info=True)
            print("Error - An unexpected issue occurred. Please try again or quit.", file=sys.stderr)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error quitting WebDriver instance: {e}", exc_info=False)

if __name__ == "__main__":
    main()