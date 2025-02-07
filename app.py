from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium_stealth import stealth
import time
import logging
import os
import random
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
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    
    # Add geolocation and permissions for Sydney, Australia
    chrome_options.add_argument('--use-fake-ui-for-media-stream')
    chrome_options.add_argument('--use-fake-device-for-media-stream')
    chrome_options.add_argument('--geolocation=141.0,-33.8') # Sydney coordinates
    
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Add permissions
    chrome_options.add_experimental_option('prefs', {
        'profile.default_content_setting_values': {
            'notifications': 1,
            'geolocation': 1,
            'media_stream_mic': 1,
            'media_stream_camera': 1
        }
    })
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    chrome_options.add_argument(f'--window-size={random.randint(1050,1200)},{random.randint(800,1000)}')
    chrome_options.add_argument('--start-maximized')
    
    # Use a random recent Chrome version
    chrome_versions = ['120.0.0.0', '119.0.0.0', '118.0.0.0']
    chrome_version = random.choice(chrome_versions)
    user_agent = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36'
    chrome_options.add_argument(f'--user-agent={user_agent}')
    
    service = Service('/usr/local/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Apply stealth mode
    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    
    return driver

def check_nsw_rego(plate_number):
    driver = setup_driver()
    
    try:
        logger.info(f"Checking NSW registration for plate: {plate_number}")
        
        # Set additional headers
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": driver.execute_script("return navigator.userAgent"),
            "platform": "Win32",
            "acceptLanguage": "en-US,en;q=0.9",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
        })
        
        # Load the page and wait for it to be fully initialized
        driver.get('https://check-registration.service.nsw.gov.au/frc?isLoginRequired=true')
        time.sleep(random.uniform(2, 4))
        
        # Wait for reCAPTCHA iframe to be present and switch to it
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title='reCAPTCHA']"))
            )
            # Switch back to main content
            driver.switch_to.default_content()
            logger.info("reCAPTCHA element loaded")
        except TimeoutException:
            logger.warning("reCAPTCHA element not found, continuing anyway")
        
        # Enter plate number with human-like typing
        plate_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "plateNumberInput"))
        )
        plate_input.clear()
        for char in plate_number:
            plate_input.send_keys(char)
            time.sleep(random.uniform(0.1, 0.3))
        
        # Add some random mouse movement and pause
        time.sleep(random.uniform(0.5, 1.0))
        
        # Scroll the page a bit like a human would
        driver.execute_script("window.scrollBy(0, 100);")
        time.sleep(random.uniform(0.3, 0.7))
        
        # Click terms checkbox with natural delay
        terms_checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "termsAndConditions"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);")
        time.sleep(random.uniform(0.3, 0.7))
        driver.execute_script("arguments[0].click();", terms_checkbox)
        
        # Add more natural delay
        time.sleep(random.uniform(0.8, 1.5))
        
        # Scroll to and click the check registration button
        check_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Check registration')]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);")
        time.sleep(random.uniform(0.3, 0.7))
        driver.execute_script("arguments[0].click();", check_button)
        
        time.sleep(5)
        
        # Wait for vehicle info section to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, f"vehicle-{plate_number}-O"))
            )
            logger.info("Vehicle info section loaded")
            
            # First check if the vehicle is registered by looking for the expiry text
            try:
                expiry_text = driver.find_element(By.XPATH, "//p[contains(@class, 'sc-iQKALj')]/strong[contains(text(), 'Registration expires')]")
                if expiry_text:
                    logger.info(f"Found registration expiry: {expiry_text.text}")
                    return "registered"
            except NoSuchElementException:
                logger.info("No registration expiry text found")
                
        except TimeoutException:
            # Check for reCAPTCHA error
            try:
                recaptcha_error = driver.find_element(By.XPATH, "//*[contains(text(), 'Please complete the reCAPTCHA')]")
                if recaptcha_error:
                    logger.error("reCAPTCHA check required")
                    return "invalid"
            except NoSuchElementException:
                pass
                
            try:
                error = driver.find_element(By.XPATH, "//*[contains(text(), 'No vehicles found')]")
                if error:
                    logger.info("Vehicle not found")
                    return "invalid"
            except NoSuchElementException:
                pass
                
            logger.error("Timeout waiting for results")
            return "invalid"
            
        # If we got here, the vehicle info loaded but no registration expiry found
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