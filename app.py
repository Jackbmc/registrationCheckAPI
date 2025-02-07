from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
import time
import logging
import os
import sys

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def setup_driver():
    # Setup Chrome options
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    
    # Let Selenium handle driver path automatically
    return webdriver.Chrome(options=chrome_options)

def check_nsw_rego(plate_number):
    driver = setup_driver()
    
    try:
        # Navigate to the registration check page
        driver.get('https://check-registration.service.nsw.gov.au/frc?isLoginRequired=true')
        time.sleep(3)  # Increased initial wait
        
        # Enter plate number
        plate_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "plateNumberInput"))
        )
        plate_input.clear()
        plate_input.send_keys(plate_number)
        
        # Click terms checkbox
        terms_checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "termsAndConditions"))
        )
        driver.execute_script("arguments[0].click();", terms_checkbox)
        
        # Click check registration button
        check_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Check registration')]"))
        )
        driver.execute_script("arguments[0].click();", check_button)
        
        time.sleep(5)  # Increased wait for results
        
        # First check for error messages indicating invalid registration
        error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'No vehicles found')]")
        if error_elements:
            return "invalid"
            
        # Look for registration status with more general selectors
        status_elements = driver.find_elements(By.XPATH, "//div[contains(text(), 'Registration expires')]")
        if status_elements:
            return "registered"
            
        # If no expiry date found, check for registered text
        status_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Registered')]")
        if status_elements:
            return "registered"
            
        # If neither found, consider it unregistered
        return "unregistered"
            
    except Exception as e:
        logger.error(f"Error checking NSW rego: {str(e)}")
        return "invalid"
    finally:
        driver.quit()

def check_act_rego(plate_number):
    driver = setup_driver()
    
    try:
        driver.get('https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage?0')
        time.sleep(2)
        
        plate_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "plateNumber"))
        )
        plate_input.clear()
        plate_input.send_keys(plate_number)
        
        privacy_checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "privacyCheck"))
        )
        driver.execute_script("arguments[0].click();", privacy_checkbox)
        
        next_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "id3"))
        )
        driver.execute_script("arguments[0].click();", next_button)
        
        time.sleep(2)
        
        try:
            error_message = driver.find_element(By.CSS_SELECTOR, ".feedbackPanel span").text
            if "No matching Registration details" in error_message:
                return "invalid"
        except NoSuchElementException:
            pass
            
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Currently Registered')]"))
            )
            return "registered"
        except TimeoutException:
            return "unregistered"
            
    except Exception as e:
        return "invalid"
    finally:
        driver.quit()

@app.route('/')
def hello_world():
    return "Hello world!"

@app.route('/check-rego')
def check_rego():
    state = request.args.get('state', '').upper()
    plate = request.args.get('plate', '')
    
    if not state or not plate:
        return jsonify({
            "status": "error",
            "message": "Both state and plate parameters are required"
        }), 400
        
    if state not in ['ACT', 'NSW']:
        return jsonify({
            "status": "error",
            "message": "State must be either ACT or NSW"
        }), 400
    
    try:
        status = check_act_rego(plate) if state == 'ACT' else check_nsw_rego(plate)
        return jsonify({
            "status": "success",
            "data": {
                "state": state,
                "plate": plate,
                "registration_status": status
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Check if script is being run with command line arguments
    if len(sys.argv) > 1:
        if len(sys.argv) != 3:
            print("Usage: python app.py <state> <plate>")
            print("Example: python app.py NSW ABC123")
            sys.exit(1)
            
        state = sys.argv[1].upper()
        plate = sys.argv[2]
        
        if state not in ['ACT', 'NSW']:
            print("Error: State must be either ACT or NSW")
            sys.exit(1)
            
        print(f"Checking {state} registration for plate: {plate}")
        status = check_act_rego(plate) if state == 'ACT' else check_nsw_rego(plate)
        print(f"Registration status: {status}")
    else:
        # Run as web server
        app.run(host='0.0.0.0', port=5000)