# Import necessary libraries
import sys
import time
import random
import re
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from flask import Flask, request, render_template_string, redirect, url_for

# --- Configuration ---

# Configure logging - Set level to ERROR to only show critical issues
logging.basicConfig(
    level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress selenium/webdriver_manager messages below CRITICAL
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)

# --- Constants for Consistent Output ---
DEFAULT_RESULT = {
    'status': 'N/A',
    'make': 'N/A',
    'model': 'N/A',
    'colour': 'N/A',
    'year': 'N/A',
    'error': None,  # Add an error field for debugging/user feedback
}

# --- Selenium WebDriver Setup ---


def setup_driver():
  """Sets up a *new* Selenium WebDriver instance with stealth."""
  # logger.info("Setting up new WebDriver instance...") # Suppressed by level
  service = Service(ChromeDriverManager().install())
  chrome_options = webdriver.ChromeOptions()
  chrome_options.add_argument('--headless')  # Use headless mode
  chrome_options.add_argument('--no-sandbox')
  chrome_options.add_argument('--disable-dev-shm-usage')
  chrome_options.add_argument('--disable-blink-features=AutomationControlled')
  chrome_options.add_experimental_option(
      'excludeSwitches', ['enable-automation', 'enable-logging']
  )
  chrome_options.add_experimental_option('useAutomationExtension', False)
  # Disable images for faster loading
  prefs = {'profile.managed_default_content_settings.images': 2}
  chrome_options.add_experimental_option('prefs', prefs)
  chrome_options.add_argument('--log-level=3')  # Suppress console logs
  chrome_options.add_argument('--silent')

  # Randomize user agent
  chrome_versions = [
      '120.0.0.0',
      '119.0.0.0',
      '118.0.0.0',
      '121.0.0.0',
      '122.0.0.0',
      '123.0.0.0',
  ]  # Keep updated
  chrome_version = random.choice(chrome_versions)
  user_agent = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36'
  chrome_options.add_argument(f'--user-agent={user_agent}')

  try:
    driver = webdriver.Chrome(service=service, options=chrome_options)
    # Apply stealth settings
    stealth(
        driver,
        languages=['en-US', 'en'],
        vendor='Google Inc.',
        platform='Win32',
        webgl_vendor='Intel Inc.',
        renderer='Intel Iris OpenGL Engine',
        fix_hairline=True,
        run_on_insecure_origins=True,
    )
    # logger.info("New WebDriver instance setup complete.") # Suppressed by level
    return driver
  except WebDriverException as e:
    logger.error(f'WebDriver setup failed: {e}', exc_info=False)
    print(
        f'Error - WebDriver setup failed ({e.__class__.__name__}). Check drivers/chrome compatibility.',
        file=sys.stderr,
    )
    return None  # Indicate failure
  except Exception as e:
    logger.error(f'Unexpected error during WebDriver setup: {e}', exc_info=True)
    print('Error - Unexpected error during WebDriver setup.', file=sys.stderr)
    return None  # Indicate failure


# --- State-Specific Rego Check Functions ---

# --- ACT ---
def _fetch_vehicle_details_act(driver):
  """Fetches vehicle details from the ACT vehicle details page."""
  details = {}
  try:
    wait = WebDriverWait(driver, 10)
    details['make'] = (
        wait.until(EC.presence_of_element_located((By.ID, 'vehicleMake')))
        .get_attribute('value')
        .strip()
    )
    details['model'] = (
        wait.until(EC.presence_of_element_located((By.ID, 'vehicleModel')))
        .get_attribute('value')
        .strip()
    )
    details['colour'] = (
        wait.until(EC.presence_of_element_located((By.ID, 'vehicleColour')))
        .get_attribute('value')
        .strip()
    )
    manufacture_date = (
        wait.until(EC.presence_of_element_located((By.ID, 'manufacturingDate')))
        .get_attribute('value')
        .strip()
    )
    parts = manufacture_date.split('/')
    details['year'] = parts[1] if len(parts) == 2 else 'N/A'
    return details
  except (TimeoutException, NoSuchElementException, IndexError) as e:
    logger.error(f'Error fetching ACT vehicle details: {e}')
    return None


def check_act_rego(driver, plate_number):
  """Checks ACT registration status."""
  result = DEFAULT_RESULT.copy()
  try:
    url = 'https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage?0'
    driver.set_page_load_timeout(25)
    driver.get(url)

    wait = WebDriverWait(driver, 15)
    plate_input = wait.until(EC.presence_of_element_located((By.ID, 'plateNumber')))
    privacy_checkbox = wait.until(
        EC.element_to_be_clickable((By.ID, 'privacyCheck'))
    )
    next_button = wait.until(EC.element_to_be_clickable((By.ID, 'id3')))

    plate_input.clear()
    plate_input.send_keys(plate_number)
    driver.execute_script('arguments[0].scrollIntoView(true);', privacy_checkbox)
    driver.execute_script('arguments[0].click();', privacy_checkbox)
    time.sleep(0.2)  # Brief pause
    driver.execute_script('arguments[0].scrollIntoView(true);', next_button)
    driver.execute_script('arguments[0].click();', next_button)

    error_locator = (By.CSS_SELECTOR, '.feedbackPanelERROR span')
    success_table_locator = (
        By.CSS_SELECTOR,
        '.panel.panel-info .panel-body table.table-bordered tbody tr.even',
    )

    try:
      element_found = WebDriverWait(driver, 12).until(
          EC.any_of(
              EC.presence_of_element_located(error_locator),
              EC.presence_of_element_located(success_table_locator),
          )
      )
      # Check for error first
      try:
        error_message = driver.find_element(*error_locator).text
        if 'No matching Registration details' in error_message:
          result['status'] = 'invalid'
          result['error'] = 'No matching registration details found.'
        else:
          result['status'] = 'error'
          result['error'] = f'Unknown error message: {error_message}'
        return result
      except NoSuchElementException:
        # No error message, proceed to check for success
        pass

      # Check for success table
      try:
        result_row = driver.find_element(*success_table_locator)
        status_text = result_row.find_element(
            By.CSS_SELECTOR, 'td:last-child'
        ).text.strip()

        details = None
        try:
          vehicle_link = result_row.find_element(
              By.CSS_SELECTOR, 'td:first-child a'
          ).get_attribute('href')
          driver.get(vehicle_link)
          details = _fetch_vehicle_details_act(driver)
        except Exception as detail_err:
          logger.error(f'Could not navigate/fetch ACT details: {detail_err}')
          result['error'] = 'Found registration, but failed to fetch details.'

        if status_text == 'Currently Registered':
          result['status'] = 'registered'
        elif status_text == 'Currently Suspended':
          result['status'] = 'suspended'
        else:
          result['status'] = 'unknown'
          result['error'] = f'Unknown status text: {status_text}'

        if details:
          result.update(details) # Update result with fetched details
        return result

      except NoSuchElementException:
        result['status'] = 'error'
        result['error'] = 'Logic Error: Neither error nor success table found.'
        return result

    except TimeoutException:
      result['status'] = 'unregistered' # Or potentially timeout
      result['error'] = 'Timeout waiting for results page or specific elements.'
      return result

  except TimeoutException as e:
    logger.error(f'Timeout during ACT check: {e}', exc_info=False)
    result['status'] = 'error'
    result['error'] = 'Page load or interaction timeout.'
    return result
  except WebDriverException as e:
      logger.error(f"WebDriverException during ACT check: {e}", exc_info=False)
      result['status'] = 'error'
      result['error'] = f'WebDriver error: {e.__class__.__name__}'
      return result
  except Exception as e:
    logger.error(f'Unexpected error during ACT check: {e}', exc_info=True)
    result['status'] = 'error'
    result['error'] = f'An unexpected error occurred: {e.__class__.__name__}.'
    return result


# --- QLD ---
def check_qld_rego(driver, plate_number):
  """Checks QLD registration status."""
  result = DEFAULT_RESULT.copy()
  try:
    url = 'https://www.service.transport.qld.gov.au/checkrego/public/Welcome.xhtml'
    driver.set_page_load_timeout(30)
    driver.get(url)

    wait = WebDriverWait(driver, 20) # Increased wait

    # Click Continue (might change ID)
    continue_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Continue')] | //input[@value='Continue']"))) # More robust selector
    driver.execute_script('arguments[0].click();', continue_button)

    # Click Accept T&Cs (might change ID)
    accept_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'accept the conditions')] | //input[@value='I accept the conditions']")))
    driver.execute_script('arguments[0].click();', accept_button)

    # Enter Plate Number
    plate_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@id, 'plateNumber')]"))) # More robust selector
    plate_input.clear()
    plate_input.send_keys(plate_number)
    time.sleep(0.2)

    # Click Search/Confirm (might change ID)
    search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Confirm')] | //input[@value='Confirm'] | //button[contains(., 'Search')]"))) # More robust selector
    driver.execute_script('arguments[0].click();', search_button)

    # --- Check for Results or Error ---
    result_section_locator = (By.CSS_SELECTOR, "dl.data")
    error_message_locator = (By.CSS_SELECTOR, ".alert-error, .alert-danger, .msg-error, .feedbackPanelERROR") # Common error message selectors

    try:
        # Wait for either the result section OR an error message
        element_found = WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located(result_section_locator),
                EC.presence_of_element_located(error_message_locator)
            )
        )

        # Check if an error message appeared
        try:
            error_element = driver.find_element(*error_message_locator)
            error_text = error_element.text.strip()
            logger.warning(f"QLD Error Message Found: {error_text}")
            # Common invalid plate messages
            if "no record found" in error_text.lower() or "plate number not found" in error_text.lower():
                 result['status'] = 'invalid'
                 result['error'] = 'No record found for this plate.'
            else:
                result['status'] = 'error'
                result['error'] = f"Registration check failed: {error_text}"
            return result
        except NoSuchElementException:
             # No error message found, assume success section is present
             pass

        # Process Success Section
        try:
            data_dl = driver.find_element(*result_section_locator)
            items = data_dl.find_elements(By.TAG_NAME, 'dd')
            # Example format: 2020 MAZDA MAZDA6 SEDAN
            # Sometimes other fields appear first, try finding the description
            desc_text = "N/A"
            for item in items:
                 text = item.text.strip()
                 # Look for a pattern like YYYY MAKE MODEL
                 if re.match(r"^\d{4}\s+[A-Z\s]+", text):
                      desc_text = text
                      break

            if desc_text != "N/A":
                match = re.match(r"(\d{4})\s+(\w+)\s+(.+)", desc_text)
                if match:
                    year, make, model = match.groups()
                    result['status'] = 'registered' # Assume registered if details found
                    result['year'] = year.strip()
                    result['make'] = make.strip()
                    result['model'] = model.strip()
                    # QLD doesn't provide colour reliably here
                    result['colour'] = 'N/A'
                else:
                    result['status'] = 'registered' # Still found details, just couldn't parse
                    result['error'] = 'Could not parse vehicle description format.'
            else:
                 result['status'] = 'registered' # Found the section, but maybe no description DD
                 result['error'] = 'Could not find vehicle description in results.'

            # Check for Expiry/Status if available (IDs/Classes might change)
            try:
                expiry_element = driver.find_element(By.XPATH, "//dt[contains(text(), 'Expiry date')]/following-sibling::dd")
                expiry_date_str = expiry_element.text.strip()
                # You might want to parse this date to check if expired
                # For now, just finding details implies registered unless an explicit error was found
            except NoSuchElementException:
                pass # Expiry date not found or page structure changed

            return result

        except NoSuchElementException:
             result['status'] = 'error'
             result['error'] = 'Results section structure not found.'
             return result

    except TimeoutException:
      # This means neither results nor error appeared in time
      result['status'] = 'unregistered' # Or timeout/error
      result['error'] = 'Timeout waiting for QLD results or error message.'
      return result


  except TimeoutException as e:
    logger.error(f'Timeout during QLD check: {e}', exc_info=False)
    result['status'] = 'error'
    result['error'] = 'Page load or interaction timeout.'
    return result
  except WebDriverException as e:
      logger.error(f"WebDriverException during QLD check: {e}", exc_info=False)
      result['status'] = 'error'
      result['error'] = f'WebDriver error: {e.__class__.__name__}'
      return result
  except Exception as e:
    logger.error(f'Unexpected error during QLD check: {e}', exc_info=True)
    result['status'] = 'error'
    result['error'] = f'An unexpected error occurred: {e.__class__.__name__}.'
    return result


# --- SA ---
def check_sa_rego(driver, plate_number):
  """Checks SA registration status."""
  result = DEFAULT_RESULT.copy()
  try:
    url = 'https://account.ezyreg.sa.gov.au/account/check-registration.htm'
    driver.set_page_load_timeout(40) # SA can be slow
    driver.get(url)
    #time.sleep(1) # Small pause might help rendering

    wait = WebDriverWait(driver, 45) # Increased overall wait time

    # Wait for Cloudflare or other checks if they appear
    # This requires more advanced handling if Cloudflare is active

    plate_input = wait.until(EC.visibility_of_element_located((By.ID, "plateNumber")))
    #time.sleep(0.5) # Small pauses between actions
    plate_input.clear()
    plate_input.send_keys(plate_number)
    #time.sleep(0.2)

    # Use JavaScript click for reliability
    continue_button = wait.until(EC.element_to_be_clickable((By.ID, "step-1-2-submit")))
    #time.sleep(0.5)
    driver.execute_script("arguments[0].scrollIntoView(true);", continue_button)
    driver.execute_script("arguments[0].click();", continue_button)

    # --- Wait for Results or Error ---
    results_container_locator = (By.ID, "registration-details-single")
    error_message_locator = (By.CSS_SELECTOR, ".alert-danger .error-message, div.error") # Example error selectors

    try:
        # Wait for either results container OR error message
        element_found = WebDriverWait(driver, 25).until( # Wait for result page elements
            EC.any_of(
                EC.presence_of_element_located(results_container_locator),
                EC.presence_of_element_located(error_message_locator)
            )
        )

        # Check for error message first
        try:
            error_element = driver.find_element(*error_message_locator)
            error_text = error_element.text.strip()
            logger.warning(f"SA Error Message Found: {error_text}")
            if "registration plate number not found" in error_text.lower() or "not valid" in error_text.lower():
                 result['status'] = 'invalid'
                 result['error'] = 'Plate number not found or invalid.'
            else:
                 result['status'] = 'error'
                 result['error'] = f"Registration check failed: {error_text}"
            return result
        except NoSuchElementException:
            # No error found, proceed to check results container
            pass

        # Process Results Container
        try:
            # Wait specifically for an element *within* the results container to ensure it's loaded
            wait.until(EC.presence_of_element_located((By.XPATH, f"//div[@id='registration-details-single']//div[contains(text(), 'Make')]")))
            container = driver.find_element(*results_container_locator)

            def get_value(cont, label):
                try:
                    # More specific XPath to find the value associated with the label
                    value_element = cont.find_element(By.XPATH, f".//div[contains(@class, 'form-group')][.//div[contains(text(), '{label}')]]//div[contains(@class, 'text-left')]/div")
                    return value_element.text.strip()
                except NoSuchElementException:
                    return "N/A"

            result['make'] = get_value(container, "Make")
            # SA uses "Body Type" for model
            result['model'] = get_value(container, "Body Type")
            result['colour'] = get_value(container, "Primary Colour")
            # SA page doesn't show Year
            result['year'] = "N/A"
            # If we get details, assume registered (unless expiry indicates otherwise - needs parsing)
            result['status'] = "registered"

            # Optionally check expiry date if needed
            # expiry_date = get_value(container, "Expiry Date")
            # Add parsing logic here if required

            return result

        except NoSuchElementException:
             result['status'] = 'error'
             result['error'] = 'Results container structure not found or missing expected elements.'
             return result
        except TimeoutException:
             result['status'] = 'error'
             result['error'] = 'Timeout waiting for elements within the results container.'
             return result


    except TimeoutException:
        # This means neither results nor error appeared in time
        result['status'] = 'unregistered' # Or timeout/error
        result['error'] = 'Timeout waiting for SA results or error message.'
        return result


  except TimeoutException as e:
    logger.error(f'Timeout during SA check: {e}', exc_info=False)
    result['status'] = 'error'
    result['error'] = 'Page load or interaction timeout.'
    return result
  except WebDriverException as e:
      logger.error(f"WebDriverException during SA check: {e}", exc_info=False)
      result['status'] = 'error'
      result['error'] = f'WebDriver error: {e.__class__.__name__}'
      return result
  except Exception as e:
    logger.error(f'Unexpected error during SA check: {e}', exc_info=True)
    result['status'] = 'error'
    result['error'] = f'An unexpected error occurred: {e.__class__.__name__}.'
    return result


# --- VIC ---
def check_vic_rego(driver, plate_number):
  """Checks VIC registration status."""
  result = DEFAULT_RESULT.copy()
  try:
    url = 'https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration/vehicle-registration-enquiry/'
    driver.set_page_load_timeout(30)
    driver.get(url)

    wait = WebDriverWait(driver, 20)

    # Handle potential cookie banner/interstitials if they appear
    # try:
    #     cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "cookie-accept-button-id"))) # Example ID
    #     cookie_button.click()
    #     time.sleep(0.5)
    # except TimeoutException:
    #     pass # No cookie banner

    # Locate elements (IDs/selectors might change)
    input_field = wait.until(EC.presence_of_element_located((By.ID, "RegistrationNumbercar")))
    # The submit button might be an input or button tag
    submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.mvc-form__actions-btn[type='submit'], button.mvc-form__actions-btn[type='submit']")))

    input_field.clear()
    input_field.send_keys(plate_number)
    time.sleep(0.2)
    driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
    driver.execute_script("arguments[0].click();", submit_button)

    # --- Wait for Results or Error ---
    results_module_locator = (By.CLASS_NAME, "form-module") # Container for results
    # Error messages might appear in different ways
    error_panel_locator = (By.CSS_SELECTOR, ".notification--error, .panel-error, .alert-danger, .field-validation-error")

    try:
        element_found = WebDriverWait(driver, 15).until(
             EC.any_of(
                 EC.presence_of_element_located(results_module_locator),
                 EC.presence_of_element_located(error_panel_locator)
             )
        )

        # Check for error message first
        try:
            error_element = driver.find_element(*error_panel_locator)
            error_text = error_element.text.strip()
            # Check common error messages
            if "No registration details found" in error_text or "enter a valid registration" in error_text.lower():
                 result['status'] = 'invalid'
                 result['error'] = 'No registration details found or invalid plate format.'
            else:
                 result['status'] = 'error'
                 result['error'] = f'Registration check failed: {error_text}'
            return result
        except NoSuchElementException:
             # No error found, proceed to process results
             pass

        # Process Results Module
        try:
            # Ensure the results module is fully present
            results_module = wait.until(EC.visibility_of_element_located(results_module_locator))

            details = {}
            items = results_module.find_elements(By.CSS_SELECTOR, ".vhr-panel__list-item-container") # Specific to VIC structure
            if not items: # Fallback if the structure changed slightly
                 items = results_module.find_elements(By.XPATH, ".//div[contains(@class, 'list-item')]") # Generic list item

            current_status = "registered" # Default assumption if details found

            for item in items:
                try:
                    # Use more robust XPath to get dt and dd regardless of exact structure inside
                    label_el = item.find_element(By.XPATH, ".//dt | .//*[contains(@class,'label')]")
                    value_el = item.find_element(By.XPATH, ".//dd | .//*[contains(@class,'value')]")
                    label = label_el.text.strip().lower()
                    value = value_el.text.strip()

                    if not value or value == '-': # Skip empty values
                        continue

                    if label == "make":
                        details['make'] = value
                    elif label == "year":
                        details['year'] = value
                    elif label == "colour" or label == "primary colour":
                        details['colour'] = value
                    elif label == "body type":
                        # VIC uses "Body Type" for model
                        details['model'] = value
                    elif "status" in label or "sanctions" in label: # Check for status indicators
                        if value.lower() != "none" and value.lower() != "registered" and value.lower() != "current":
                             # If sanctions exist or status is not 'None'/'Registered', mark as suspended/other
                             current_status = value.lower() # Use the specific status if available (e.g., suspended, cancelled)

                except NoSuchElementException:
                    continue # Skip item if dt/dd not found

            if not details: # If no details were extracted at all
                 result['status'] = 'error'
                 result['error'] = 'Results module found, but could not extract any vehicle details.'
                 return result

            result.update(details)
            # Set status based on findings (defaults to registered if no specific status found)
            result['status'] = current_status if current_status != "registered" else "registered"
            return result

        except (NoSuchElementException, TimeoutException):
            result['status'] = 'error'
            result['error'] = 'Could not find or process the results module structure.'
            return result


    except TimeoutException:
        # This means neither results nor error appeared
        # VIC often shows this for unregistered plates without a specific error message
        result['status'] = 'unregistered'
        result['error'] = 'Timeout waiting for VIC results or error message (may indicate unregistered plate).'
        return result

  except TimeoutException as e:
    logger.error(f'Timeout during VIC check: {e}', exc_info=False)
    result['status'] = 'error'
    result['error'] = 'Page load or interaction timeout.'
    return result
  except WebDriverException as e:
      logger.error(f"WebDriverException during VIC check: {e}", exc_info=False)
      result['status'] = 'error'
      result['error'] = f'WebDriver error: {e.__class__.__name__}'
      return result
  except Exception as e:
    logger.error(f'Unexpected error during VIC check: {e}', exc_info=True)
    result['status'] = 'error'
    result['error'] = f'An unexpected error occurred: {e.__class__.__name__}.'
    return result


# --- Master Function ---

STATE_CHECK_FUNCTIONS = {
    'ACT': check_act_rego,
    'QLD': check_qld_rego,
    'SA': check_sa_rego,
    'VIC': check_vic_rego,
    # Add other states here if implemented
}


def get_vehicle_info(state, plate_number):
  """
    Gets vehicle registration info for a given state and plate number.

    Args:
        state (str): The Australian state/territory (e.g., 'ACT', 'QLD').
        plate_number (str): The vehicle registration plate number.

    Returns:
        dict: A dictionary containing vehicle information with keys:
              'status', 'make', 'model', 'colour', 'year', 'error'.
              Values will be 'N/A' if not found or applicable.
              'error' contains details if an issue occurred during the check.
    """
  result = DEFAULT_RESULT.copy() # Start with default N/A values
  plate_number = plate_number.strip().upper()
  state = state.strip().upper()

  if not plate_number:
      result['status'] = 'error'
      result['error'] = 'Plate number cannot be empty.'
      return result

  if state not in STATE_CHECK_FUNCTIONS:
    result['status'] = 'error'
    result['error'] = f'State "{state}" is not supported.'
    return result

  driver = None
  try:
    driver = setup_driver()
    if not driver:
      result['status'] = 'error'
      result['error'] = 'Failed to initialize the WebDriver.'
      return result

    # Call the appropriate state function
    check_function = STATE_CHECK_FUNCTIONS[state]
    state_result = check_function(driver, plate_number)

    # Merge results, ensuring all keys are present
    for key in DEFAULT_RESULT:
         result[key] = state_result.get(key, DEFAULT_RESULT[key]) # Use state result if available, else default

    return result

  except Exception as e:
    logger.error(
        f'Unexpected error in get_vehicle_info for {state} - {plate_number}: {e}',
        exc_info=True,
    )
    result['status'] = 'error'
    result['error'] = f'An unexpected system error occurred: {e.__class__.__name__}'
    return result
  finally:
    # Ensure the driver is always quit if it was initialized
    if driver:
      try:
        driver.quit()
      except Exception as e:
        logger.error(f'Error quitting WebDriver instance: {e}', exc_info=False)


# --- Flask Web Application ---

app = Flask(__name__)

# Basic HTML template with CSS for styling
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AUS Rego Check</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; margin: 20px; background-color: #f8f9fa; color: #212529; }
        .container { max-width: 650px; margin: 30px auto; background: #ffffff; padding: 25px 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); border: 1px solid #dee2e6; }
        h1 { text-align: center; color: #495057; margin-bottom: 25px; font-weight: 500; }
        form { display: flex; flex-direction: column; gap: 18px; }
        label { font-weight: 500; margin-bottom: 5px; display: block; color: #495057; }
        input[type="text"] { padding: 12px; border: 1px solid #ced4da; border-radius: 4px; font-size: 1rem; width: 100%; box-sizing: border-box; }
        input[type="text"]:focus { border-color: #80bdff; outline: 0; box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25); }
        .state-options { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 5px; }
        .state-options label { margin-right: 15px; font-weight: normal; display: inline-flex; align-items: center; cursor: pointer; margin-bottom: 0; color: #212529; }
        input[type="radio"] { margin-right: 6px; cursor: pointer; transform: scale(1.1); }
        button[type="submit"] { padding: 12px 20px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1.05rem; font-weight: 500; transition: background-color 0.2s ease, transform 0.1s ease; width: 100%; margin-top: 10px; }
        button[type="submit"]:hover { background-color: #0056b3; }
        button[type="submit"]:active { transform: scale(0.98); }
        button[type="submit"]:disabled { background-color: #6c757d; cursor: not-allowed; }
        .results-section { margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px; }
        .results-table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .results-table th, .results-table td { border: 1px solid #dee2e6; padding: 12px; text-align: left; vertical-align: top; }
        .results-table th { background-color: #f8f9fa; font-weight: 500; width: 35%; color: #495057; }
        .results-table td { background-color: #fff; }
        /* Status styling */
        .status-registered { color: #28a745; font-weight: bold; }
        .status-suspended { color: #fd7e14; font-weight: bold; }
        .status-invalid { color: #dc3545; font-weight: bold; }
        .status-unregistered, .status-cancelled, .status-expired { color: #6c757d; font-weight: bold; }
        .status-error { color: #dc3545; font-weight: bold; }
        .status-timeout { color: #17a2b8; font-weight: bold; }
        .status-unknown { color: #6f42c1; font-weight: bold; }
        /* Error message */
        .error-message { color: #721c24; background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 12px; border-radius: 4px; margin-top: 20px; margin-bottom: 15px; }
        .notes-cell { color: #856404; background-color: #fff3cd; border-color: #ffeeba; font-style: italic; } /* Warning/Info Style */
        /* Loader Styles */
        #loader { display: none; /* Hidden by default */ text-align: center; padding: 20px 0; }
        .spinner { margin: 0 auto; width: 40px; height: 40px; border: 4px solid #f3f3f3; /* Light grey */ border-top: 4px solid #007bff; /* Blue */ border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .loading-text { margin-top: 10px; color: #495057; font-weight: 500; }

        @media (max-width: 600px) {
              .container { margin: 15px; padding: 20px; }
              h1 { font-size: 1.5rem; }
              .state-options label { margin-right: 10px; font-size: 0.95rem; }
              button[type="submit"] { padding: 10px 15px; }
              .results-table th, .results-table td { padding: 8px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Australian Vehicle Registration Check</h1>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form id="rego-form" action="{{ url_for('check_rego') }}" method="post">
            <div>
                <label for="plate">Plate Number:</label>
                <input type="text" id="plate" name="plate" value="{{ plate or '' }}" required pattern="[A-Za-z0-9]+" title="Plate number should only contain letters and numbers." placeholder="e.g., ABC123">
            </div>
            <div>
                <label>State:</label>
                <div class="state-options">
                    {% for state_code in supported_states %}
                    <label>
                        <input type="radio" name="state" value="{{ state_code }}" {% if state_code == state %}checked{% endif %} required>
                        {{ state_code }}
                    </label>
                    {% endfor %}
                </div>
            </div>
            <button type="submit">Check Registration</button>
        </form>

        <div id="loader">
            <div class="spinner"></div>
            <div class="loading-text">Checking Registration... Please wait.</div>
        </div>

        <div id="results-output" {% if not result %}style="display: none;"{% endif %}> {# Hide initially if no result #}
            {% if result %}
            <div class="results-section">
                <h2>Results for {{ plate }} ({{ state }})</h2>
                {% if result.error and result.status in ['error', 'timeout'] %}
                    <div class="error-message">
                        <strong>Error:</strong> {{ result.error }}
                    </div>
                {% endif %}
                <table class="results-table">
                     <tbody>
                        <tr>
                            <th>Status</th>
                            <td><span class="status-{{ result.status | lower | replace(' ', '-') }}">{{ result.status | capitalize }}</span></td>
                        </tr>
                        <tr><th>Make</th><td>{{ result.make if result.make != 'N/A' else '-' }}</td></tr>
                        <tr><th>Model / Body Type</th><td>{{ result.model if result.model != 'N/A' else '-' }}</td></tr>
                        <tr><th>Colour</th><td>{{ result.colour if result.colour != 'N/A' else '-' }}</td></tr>
                        <tr><th>Year</th><td>{{ result.year if result.year != 'N/A' else '-' }}</td></tr>
                        {% if result.error and result.status not in ['error', 'timeout'] %} {# Show non-critical errors/notes #}
                         <tr><th>Notes</th><td class="notes-cell">{{ result.error }}</td></tr>
                        {% endif %}
                     </tbody>
                </table>
            </div>
            {% endif %}
        </div>

    </div> {# End Container #}

    <script>
        const form = document.getElementById('rego-form');
        const loader = document.getElementById('loader');
        const resultsOutput = document.getElementById('results-output');
        const submitButton = form.querySelector('button[type=submit]');

        form.addEventListener('submit', function() {
            // Hide previous results and show loader
            resultsOutput.style.display = 'none';
            loader.style.display = 'block';
            // Disable button
            submitButton.disabled = true;
            submitButton.textContent = 'Checking...'; // Optional: change button text

            // No explicit JS timeout here, relies on page reload to show result/error
            // Loader will disappear when the new page loads.
        });

        // Optional: If page reloads with an error state, ensure button is re-enabled
        // This happens implicitly because the button state is not persisted across reloads,
        // but good practice if using AJAX later.
        window.addEventListener('load', () => {
             if (submitButton.disabled) {
                  submitButton.disabled = false;
                  submitButton.textContent = 'Check Registration';
             }
             // If results are being shown on load, ensure loader is hidden
             if (resultsOutput.style.display !== 'none') {
                 loader.style.display = 'none';
             }
        });

    </script>

</body>
</html>
"""


@app.route('/', methods=['GET'])
def index():
  """Displays the main form."""
  supported_states = list(STATE_CHECK_FUNCTIONS.keys())
  return render_template_string(HTML_TEMPLATE, supported_states=supported_states)


@app.route('/check', methods=['POST'])
def check_rego():
  """Handles the form submission and displays results."""
  plate = request.form.get('plate', '').strip().upper()
  state = request.form.get('state', '').strip().upper()
  supported_states = list(STATE_CHECK_FUNCTIONS.keys())
  result_data = None

  if not plate or not state:
    # Should be caught by 'required' in HTML, but handle anyway
    return redirect(url_for('index')) # Redirect back if invalid input

  if state not in supported_states:
     # Handle case where an invalid state is somehow submitted
     # Render template with an error message specific to state validity
     error_result = DEFAULT_RESULT.copy()
     error_result['status'] = 'error'
     error_result['error'] = f'Selected state "{state}" is not supported.'
     return render_template_string(
         HTML_TEMPLATE,
         supported_states=supported_states,
         plate=plate,
         state=state,
         result=error_result
     )


  # Call the main function to get vehicle info
  print(f"Checking Plate: {plate}, State: {state}") # Log to console
  result_data = get_vehicle_info(state, plate)
  print(f"Result: {result_data}") # Log result to console

  # Render the same template but include the results
  return render_template_string(
      HTML_TEMPLATE,
      supported_states=supported_states,
      plate=plate,
      state=state,
      result=result_data,
  )


# --- Main Execution ---
if __name__ == '__main__':
  # Note: For development only. Use a proper WSGI server like Gunicorn for production.
  print("Starting Flask development server...")
  print("Access the checker at http://127.0.0.1:5000/")
  app.run(debug=False, host='0.0.0.0') # Run on all interfaces, disable debug for stability
  # Use debug=True for development if needed, but it can cause issues with Selenium reloads.