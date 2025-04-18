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

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress selenium/webdriver_manager messages
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
        logger.error(f"WebDriver setup failed: {e}")
        print(f"Error - WebDriver setup failed ({e.__class__.__name__}). Check drivers/chrome compatibility.", file=sys.stderr)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during WebDriver setup: {e}")
        print("Error - Unexpected error during WebDriver setup.", file=sys.stderr)
        return None


def fetch_vehicle_details_vic(driver):
    """Extracts vehicle details from VIC result page."""
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "form-module")))

        details = {}
        items = driver.find_elements(By.CSS_SELECTOR, ".vhr-panel__list-item-container")
        for item in items:
            try:
                label = item.find_element(By.TAG_NAME, "dt").text.strip().lower()
                value = item.find_element(By.TAG_NAME, "dd").text.strip()
                if label == "make":
                    details['make'] = value
                elif label == "year":
                    details['year'] = value
                elif label == "colour":
                    details['colour'] = value
                elif label == "body type":
                    details['model'] = value  # Not a true model, but closest match
                elif label == "sanctions applicable":
                    details['status'] = "suspended" if value.lower() != "none" else "registered"
            except Exception as e:
                continue

        # Fallback if no "sanctions" field
        if 'status' not in details:
            details['status'] = "registered"

        return details if details else None
    except Exception as e:
        logger.error(f"Error fetching VIC vehicle details: {e}")
        return None


def check_vic_rego(driver, plate_number):
    """
    Checks VIC registration status and fetches vehicle details.
    Returns a dictionary with status and vehicle details.
    """
    try:
        url = 'https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration/vehicle-registration-enquiry/'
        driver.set_page_load_timeout(25)
        try:
            driver.get(url)
        except TimeoutException:
            logger.error("Timeout loading VIC registration page")
            return {"status": "invalid_page_timeout"}

        wait = WebDriverWait(driver, 15)

        input_field = wait.until(EC.presence_of_element_located((By.ID, "RegistrationNumbercar")))
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.mvc-form__actions-btn[type='submit']")))

        input_field.clear()
        input_field.send_keys(plate_number)
        time.sleep(0.1)
        driver.execute_script("arguments[0].click();", submit_button)

        # Wait for either results or error panel
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "form-module")))
            details = fetch_vehicle_details_vic(driver)
            if details:
                return details
            else:
                return {"status": "unknown", "details_error": "No details found"}
        except TimeoutException:
            return {"status": "unregistered"}

    except TimeoutException as e:
        logger.error(f"Timeout during VIC check interaction: {e}")
        return {"status": "invalid_interaction_timeout"}
    except Exception as e:
        logger.error(f"Unexpected error during VIC check: {e}", exc_info=True)
        return {"status": "invalid_exception"}


def main():
    """Main loop for checking VIC registration."""
    print("VIC Registration Checker. Type 'quit' to exit.")
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
                result = check_vic_rego(driver, plate)
                print(result)

        except EOFError:
            print("\nExiting.")
            break
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            print("Error - An unexpected issue occurred. Please try again or quit.", file=sys.stderr)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error quitting WebDriver: {e}")

if __name__ == "__main__":
    main()
