import sys
import time # Import time for potential slight delay if needed
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
import re # Import the regular expression module

# Configure logging - Set level to ERROR to only show critical issues
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress selenium/webdriver_manager messages below CRITICAL
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)

def setup_driver():
    """Sets up a *new* Selenium WebDriver instance."""
    # logger.info("Setting up new WebDriver instance...") # Suppressed by level
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
    # Randomize user agent for each instance
    chrome_versions = ['120.0.0.0', '119.0.0.0', '118.0.0.0', '121.0.0.0'] # Keep updated
    chrome_version = random.choice(chrome_versions)
    user_agent = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36'
    chrome_options.add_argument(f'--user-agent={user_agent}')

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        # Apply stealth settings to this new instance
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                run_on_insecure_origins=True
        )
        # logger.info("New WebDriver instance setup complete.") # Suppressed by level
        return driver
    except WebDriverException as e:
        # Handle potential driver/browser mismatch or other setup errors
        logger.error(f"WebDriver setup failed: {e}", exc_info=False) # Log less traceback noise
        print(f"Error - WebDriver setup failed ({e.__class__.__name__}). Check drivers/chrome compatibility.", file=sys.stderr)
        return None # Indicate failure
    except Exception as e:
        logger.error(f"Unexpected error during WebDriver setup: {e}", exc_info=True)
        print("Error - Unexpected error during WebDriver setup.", file=sys.stderr)
        return None # Indicate failure


def fetch_vehicle_details(driver):
    """Fetches vehicle details from the vehicle details page."""
    details = {}
    try:
        wait = WebDriverWait(driver, 10)

        # Extract Make
        make_element = wait.until(EC.presence_of_element_located((By.ID, "vehicleMake")))
        details['make'] = make_element.get_attribute('value').strip()

        # Extract Model
        model_element = wait.until(EC.presence_of_element_located((By.ID, "vehicleModel")))
        details['model'] = model_element.get_attribute('value').strip()

        # Extract Colour
        colour_element = wait.until(EC.presence_of_element_located((By.ID, "vehicleColour")))
        details['colour'] = colour_element.get_attribute('value').strip()

        # Extract Year from Manufacture Date
        manufacture_date_element = wait.until(EC.presence_of_element_located((By.ID, "manufacturingDate")))
        manufacture_date = manufacture_date_element.get_attribute('value').strip()
        # Assuming the format is MM/YYYY, we extract the year part
        parts = manufacture_date.split('/')
        if len(parts) == 2:
            details['year'] = parts[1]
        else:
            details['year'] = None

        return details
    except (TimeoutException, NoSuchElementException) as e:
        logger.error(f"Error fetching vehicle details: {e}")
        return None

def check_act_rego(driver, plate_number):
    """
    Checks ACT registration status and attempts to fetch vehicle details.
    Returns a dictionary containing status and vehicle details.
    """
    try:
        # logger.info(f"Checking ACT registration for plate: {plate_number}") # Suppressed by level
        url = 'https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage?0'
        driver.set_page_load_timeout(25) # Slightly longer timeout for initial load
        try:
            driver.get(url)
        except TimeoutException:
            logger.error(f"Timeout loading ACT registration page: {url}")
            return {"status": "invalid_page_timeout"}

        # Use WebDriverWait for all element interactions
        wait = WebDriverWait(driver, 15) # Wait up to 15 seconds for elements

        # Locate elements reliably
        plate_input = wait.until(EC.presence_of_element_located((By.ID, "plateNumber")))
        # Ensure checkbox is clickable, not just present
        privacy_checkbox = wait.until(EC.element_to_be_clickable((By.ID, "privacyCheck")))
        next_button = wait.until(EC.element_to_be_clickable((By.ID, "id3")))

        # logger.info("ACT page loaded, elements located.") # Suppressed by level

        # Interact with elements
        plate_input.clear()
        plate_input.send_keys(plate_number)
        # Use JS click as it can be more robust sometimes
        driver.execute_script("arguments[0].scrollIntoView(true);", privacy_checkbox)
        driver.execute_script("arguments[0].click();", privacy_checkbox)
        # Brief pause might help ensure state update before next click on some sites
        time.sleep(0.1)
        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
        driver.execute_script("arguments[0].click();", next_button)
        # logger.info("ACT form submitted.") # Suppressed by level

        # --- Wait for Results ---
        error_locator = (By.CSS_SELECTOR, ".feedbackPanelERROR span")
        success_table_locator = (By.CSS_SELECTOR, ".panel.panel-info .panel-body table.table-bordered tbody tr.even")

        # logger.info("Waiting for ACT results or error message...") # Suppressed by level
        try:
            element_found = WebDriverWait(driver, 12).until( # Slightly longer wait for result page
                EC.any_of(
                    EC.presence_of_element_located(error_locator),
                    EC.presence_of_element_located(success_table_locator)
                )
            )
            # logger.info("Result or error element found on page.") # Suppressed by level

            try:
                error_message_element = driver.find_element(*error_locator)
                error_message = error_message_element.text
                if "No matching Registration details" in error_message:
                    return {"status": "invalid"}
                else:
                    logger.warning(f"ACT Unknown/unexpected error message found: {error_message}")
                    return {"status": "invalid_unknown_error"}
            except NoSuchElementException:
                try:
                    result_row = driver.find_element(*success_table_locator)
                    status_element = result_row.find_element(By.CSS_SELECTOR, "td:last-child")
                    status_text = status_element.text.strip()

                    if status_text == "Currently Registered":
                        vehicle_link_element = result_row.find_element(By.CSS_SELECTOR, "td:first-child a")
                        vehicle_link = vehicle_link_element.get_attribute('href')
                        driver.get(vehicle_link)
                        vehicle_details = fetch_vehicle_details(driver)
                        if vehicle_details:
                            return {"status": "registered", **vehicle_details}
                        else:
                            return {"status": "registered", "details_error": "Could not fetch vehicle details"}
                    elif status_text == "Currently Suspended":
                        vehicle_link_element = result_row.find_element(By.CSS_SELECTOR, "td:first-child a")
                        vehicle_link = vehicle_link_element.get_attribute('href')
                        driver.get(vehicle_link)
                        vehicle_details = fetch_vehicle_details(driver)
                        if vehicle_details:
                            return {"status": "suspended", **vehicle_details}
                        else:
                            return {"status": "suspended", "details_error": "Could not fetch vehicle details"}
                    else:
                        logger.warning(f"ACT Unknown registration status: {status_text}")
                        return {"status": "unknown", "status_text": status_text}

                except NoSuchElementException:
                     logger.error("Logic Error: Neither error nor success table found after wait condition met.")
                     return {"status": "invalid_logic_error"}

        except TimeoutException:
             # logger.warning("Timeout waiting for ACT result/error. Assuming unregistered or page issue.") # Suppressed by level
             return {"status": "unregistered"}

    except TimeoutException as e:
        logger.error(f"Timeout during ACT check interaction: {e}", exc_info=False)
        return {"status": "invalid_interaction_timeout"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during ACT check: {e}", exc_info=True)
        return {"status": "invalid_exception"}
    # No finally block here - driver is quit in main loop


def main():
    """Runs the interactive loop, setting up/tearing down driver for each check."""
    print("ACT Registration Checker. Type 'quit' to exit.")
    while True:
        driver = None # Ensure driver is reset for each loop iteration
        try:
            user_input = input("Enter plate: ")
            if user_input.lower() == 'quit':
                break

            plate = user_input.strip().upper()
            if not plate:
                continue

            # Setup driver *inside* the loop for this specific check
            driver = setup_driver()

            # Proceed only if driver setup was successful
            if driver:
                result = check_act_rego(driver, plate)
                print(result)
            else:
                # Error message already printed by setup_driver on failure
                # Optionally wait a moment before prompting again if setup fails often
                # time.sleep(1)
                pass # Continue loop to allow user to try again or quit

        except EOFError:
            print("\nExiting.")
            break
        except KeyboardInterrupt:
             print("\nExiting.")
             break
        except Exception as e:
            # Catch any other unexpected errors during the loop iteration
            logger.error(f"Unexpected error in main loop iteration: {e}", exc_info=True)
            print("Error - An unexpected issue occurred. Please try again or quit.", file=sys.stderr)
        finally:
            # Quit the driver specific to *this iteration* if it exists
            if driver:
                try:
                    driver.quit()
                    # logger.info("WebDriver instance quit.") # Suppressed by level
                except Exception as e:
                    # Catch errors during quit (e.g., if browser already crashed)
                    logger.error(f"Error quitting WebDriver instance: {e}", exc_info=False)

if __name__ == "__main__":
    main()
