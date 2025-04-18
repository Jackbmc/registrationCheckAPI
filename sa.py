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
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)

def setup_driver():
    service = Service(ChromeDriverManager().install())
    chrome_options = webdriver.ChromeOptions()
    # chrome_options.add_argument('--headless')
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
        print(f"Error - WebDriver setup failed ({e.__class__.__name__}).", file=sys.stderr)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during WebDriver setup: {e}", exc_info=True)
        print("Error - Unexpected error during WebDriver setup.", file=sys.stderr)
        return None

def check_sa_rego(driver, plate_number):
    try:
        url = 'https://account.ezyreg.sa.gov.au/account/check-registration.htm'
        driver.set_page_load_timeout(40)
        try:
            driver.get(url)
            time.sleep(1)
        except TimeoutException:
            logger.error(f"Timeout loading SA registration page: {url}")
            return {"status": "invalid_page_timeout", "make": "N/A", "model": "N/A", "colour": "N/A", "year": "N/A"}

        wait = WebDriverWait(driver, 45)  # Increased overall wait time

        try:
            plate_input = wait.until(EC.visibility_of_element_located((By.ID, "plateNumber")))
            time.sleep(0.5)
            plate_input.clear()
            plate_input.send_keys(plate_number)
            time.sleep(0.2)

            continue_button = wait.until(EC.element_to_be_clickable((By.ID, "step-1-2-submit")))
            time.sleep(0.5)
            driver.execute_script("arguments[0].scrollIntoView(true);", continue_button)
            driver.execute_script("arguments[0].click();", continue_button)

            # Wait for the "Make" label to be present within the results container
            results_container_locator = (By.ID, "registration-details-single")
            wait.until(EC.presence_of_element_located((By.XPATH, f"//div[@id='registration-details-single']//div[@class='form-group']/div[@class='col-sm-6 col-xs-6 strong text-right']/div[@class='form-control-static'][contains(text(), 'Make')]")))
            container = driver.find_element(*results_container_locator)

            def get_value(cont, label):
                try:
                    label_element = cont.find_element(By.XPATH, f".//div[@class='form-group']/div[@class='col-sm-6 col-xs-6 strong text-right']/div[@class='form-control-static'][contains(text(), '{label}')]/following::div[@class='col-sm-6 col-xs-6 text-left']/div[@class='form-control-static']")
                    return label_element.text.strip()
                except NoSuchElementException:
                    return "N/A"
                except Exception as e:
                    logger.error(f"Error getting value for {label}: {e}", exc_info=True)
                    return "N/A"

            make = get_value(container, "Make")
            model = get_value(container, "Body Type")
            colour = get_value(container, "Primary Colour")
            year = "N/A" # Year is not present on this page

            return {
                "status": "registered",
                "make": make,
                "model": model,
                "colour": colour,
                "year": year
            }

        except TimeoutException as te:
            logger.error(f"Timeout during interaction or loading results: {te}", exc_info=True)
            return {"status": "timeout", "make": "N/A", "model": "N/A", "colour": "N/A", "year": "N/A"}
        except NoSuchElementException as nsee:
            logger.error(f"Element not found: {nsee}", exc_info=True)
            return {"status": "element_not_found", "make": "N/A", "model": "N/A", "colour": "N/A", "year": "N/A"}
        except Exception as e:
            logger.error(f"Error during SA check: {e}", exc_info=True)
            return {"status": "error", "make": "N/A", "model": "N/A", "colour": "N/A", "year": "N/A"}

    except Exception as e:
        logger.error(f"Unexpected error in SA check function: {e}", exc_info=True)
        return {"status": "unexpected_error", "make": "N/A", "model": "N/A", "colour": "N/A", "year": "N/A"}

def main():
    print("SA Registration Checker. Type 'quit' to exit.")
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
                result = check_sa_rego(driver, plate)
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
                    logger.error(f"Error quitting WebDriver: {e}", exc_info=False)

if __name__ == "__main__":
    main()