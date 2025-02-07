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
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress selenium messages
logging.getLogger('selenium').setLevel(logging.CRITICAL)

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
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    service = Service('/usr/local/bin/chromedriver')
    
    return webdriver.Chrome(service=service, options=chrome_options)

def check_nsw_rego(plate_number):
    driver = setup_driver()
    
    try:
        driver.get('https://check-registration.service.nsw.gov.au/frc?isLoginRequired=true')
        time.sleep(3)  # Increased wait time
        
        plate_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "plateNumberInput"))
        )
        plate_input.clear()
        plate_input.send_keys(plate_number)
        
        terms_checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "termsAndConditions"))
        )
        driver.execute_script("arguments[0].click();", terms_checkbox)
        
        check_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Check registration')]"))
        )
        driver.execute_script("arguments[0].click();", check_button)
        
        logger.info("Waiting for results...")
        time.sleep(8)  # Increased wait time to ensure page loads completely
        
        # Wait for any status element to be present
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "fPcfgp"))
            )
        except TimeoutException:
            logger.info("Timeout waiting for status element")
        
        # First check for any error messages
        error_patterns = [
            "//*[contains(text(), 'No vehicles found')]",
            "//*[contains(text(), 'not found')]",
            "//*[contains(text(), 'Invalid')]"
        ]
        
        for pattern in error_patterns:
            error_elements = driver.find_elements(By.XPATH, pattern)
            if error_elements:
                logger.info(f"Found error message: {error_elements[0].text}")
                return "invalid"
        
        # Try multiple approaches to find registration status
        try:
            # Method 1: Direct class lookup
            elements = driver.find_elements(By.CLASS_NAME, "fPcfgp")
            logger.info(f"Found {len(elements)} elements with class fPcfgp")
            for element in elements:
                logger.info(f"Element text: {element.text}")
                if "Registered" in element.text:
                    return "registered"

            # Method 2: Look for green success icon near registration status
            success_elements = driver.find_elements(By.XPATH, "//svg[contains(@id, 'registration-icon')]/../following-sibling::div")
            logger.info(f"Found {len(success_elements)} elements with registration icon")
            for element in success_elements:
                logger.info(f"Success element text: {element.text}")
                if "Registered" in element.text:
                    return "registered"
                    
            # Method 3: Look for registration expiry text
            expiry_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Expires:')]")
            logger.info(f"Found {len(expiry_elements)} expiry elements")
            if expiry_elements:
                return "registered"
                
            # Take screenshot for debugging
            driver.save_screenshot('debug.png')
            logger.info("Saved debug screenshot")
            
        except Exception as e:
            logger.error(f"Error while checking registration status: {str(e)}")
            
        return "unregistered"
            
    except Exception as e:
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
    app.run(host='0.0.0.0', port=5000)