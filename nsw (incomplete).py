#gets blocked by CAPTCHA

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

def fetch_nsw_vehicle_details(driver):
    """Fetches vehicle details from the NSW vehicle details page."""
    details = {}
    try:
        wait = WebDriverWait(driver, 10)
        sections = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "section.SectionPage-sc-1753i6j-0 div.sc-cmthru")))
        if sections:
            info_divs = sections[0].find_elements(By.CSS_SELECTOR, "div.sc-cLQEGU")
            info_dict = {}
            for i in range(0, len(info_divs), 2):
                if i + 1 < len(info_divs):
                    label = info_divs[i].text.strip().lower()
                    value = info_divs[i+1].text.strip()
                    info_dict[label] = value

            details['make'] = info_dict.get('make')
            details['model'] = info_dict.get('model')
            details['colour'] = info_dict.get('colour')
            details['year'] = info_dict.get('manufacture year')

        return details
    except (TimeoutException, NoSuchElementException) as e:
        logger.error(f"Error fetching NSW vehicle details: {e}")
        return None

def check_nsw_rego(driver, plate_number):
    """
    Checks NSW registration status and attempts to fetch vehicle details.
    Returns a dictionary containing status and vehicle details.
    """
    try:
        url = 'https://check-registration.service.nsw.gov.au/frc?ISLOGINREQUIRED=TRUE'
        driver.set_page_load_timeout(25)
        try:
            driver.get(url)
        except TimeoutException:
            logger.error(f"Timeout loading NSW registration page: {url}")
            return {"status": "invalid_page_timeout"}

        wait = WebDriverWait(driver, 20) # Increased wait time

        try:
            # Wait for the plate number input field to be present and interactable
            plate_input = wait.until(EC.presence_of_element_located((By.ID, "plateNumberInput")))
            plate_input.clear()
            plate_input.send_keys(plate_number)
            logger.info("Plate number entered.")

            # Wait for the label associated with the checkbox to be clickable
            checkbox_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='termsAndConditions']")))
            driver.execute_script("arguments[0].scrollIntoView(true);", checkbox_label)
            checkbox_label.click() # Try clicking the label
            logger.info("Terms and conditions accepted (via label click).")
            time.sleep(0.2) # Slight pause after clicking

            # Wait for the "Check registration" button to be clickable
            check_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.sc-esjQYD button#id-2")))
            driver.execute_script("arguments[0].scrollIntoView(true);", check_button)
            driver.execute_script("arguments[0].click();", check_button)
            logger.info("Check registration button clicked.")

            # --- Wait for Results Page ---
            registration_expiry_locator = (By.CSS_SELECTOR, "p.sc-iQKALj strong")
            error_locator = (By.CSS_SELECTOR, ".sc-gFaBFf")

            try:
                WebDriverWait(driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located(error_locator),
                        EC.presence_of_element_located(registration_expiry_locator)
                    )
                )
                logger.info("Results page loaded or error found.")

                try:
                    error_message_element = driver.find_element(*error_locator)
                    error_message = error_message_element.text.strip()
                    if "No matching registration found" in error_message:
                        return {"status": "invalid"}
                    else:
                        logger.warning(f"NSW Unknown/unexpected error message: {error_message}")
                        return {"status": "invalid_unknown_error", "error_message": error_message}
                except NoSuchElementException:
                    try:
                        expiry_element = driver.find_element(*registration_expiry_locator)
                        expiry_text = expiry_element.text.strip().lower()
                        if "expires" in expiry_text:
                            vehicle_details = fetch_nsw_vehicle_details(driver)
                            if vehicle_details:
                                return {"status": "registered", **vehicle_details}
                            else:
                                return {"status": "registered", "details_error": "Could not fetch vehicle details"}
                        else:
                            logger.warning(f"NSW Unknown registration status text: {expiry_text}")
                            return {"status": "unknown", "status_text": expiry_text}
                    except NoSuchElementException:
                        logger.error("Logic Error: Neither error nor expiry found after wait.")
                        return {"status": "invalid_logic_error"}

            except TimeoutException:
                logger.warning("Timeout waiting for NSW result/error.")
                return {"status": "unregistered"}

        except TimeoutException:
            logger.error("Timeout waiting for elements on the initial form page.")
            return {"status": "invalid_form_timeout"}

    except TimeoutException as e:
        logger.error(f"Timeout during NSW check interaction: {e}", exc_info=False)
        return {"status": "invalid_interaction_timeout"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during NSW check: {e}", exc_info=True)
        return {"status": "invalid_exception"}

def main():
    """Runs the interactive loop for NSW registration checks."""
    print("NSW Registration Checker. Type 'quit' to exit.")
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
                result = check_nsw_rego(driver, plate)
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