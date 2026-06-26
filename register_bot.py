import pandas as pd
import json
import time
import random
import os
import csv
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data/bot_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RegistrationBot:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.log_path = self.config['log_path']
        self.ensure_log_exists()
        self.registered_emails = self.load_registered_emails()
        self.referral_sources = ["Social Media", "Friend", "Binance App", "Twitter", "Telegram", "Email", "Others"]

    def ensure_log_exists(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'First Name', 'Last Name', 'Email', 'Status'])

    def load_registered_emails(self):
        try:
            df = pd.read_csv(self.log_path)
            return set(df['Email'].astype(str).str.lower().tolist())
        except: return set()

    def init_driver(self):
        chrome_options = Options()
        if self.config['settings']['headless']:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_window_size(1440, 1000)
        return driver

    def js_input(self, driver, element_id, value, field_name):
        """Forces values and triggers events. Returns current value in field."""
        try:
            el = driver.find_element(By.ID, element_id)
            driver.execute_script("""
                var el = arguments[0];
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            """, el, value)
            logger.info(f"   [Input] {field_name} set to: {value}")
            return el.get_attribute("value")
        except Exception as e:
            logger.error(f"   [Input Error] {field_name}: {str(e)}")
            return ""

    def validate_and_fill(self, driver, user_data, chosen_ref):
        """Fills the form and verifies that fields are not empty."""
        logger.info("   Filling Form Step 1...")
        
        # Fill Text Fields
        self.js_input(driver, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1", user_data['First Name'], "First Name")
        self.js_input(driver, "cfc98829-80b7-41b6-82b5-b968d43ef1c1", user_data['Last Name'], "Last Name")
        self.js_input(driver, "ff919d05-4281-4d9c-aa0d-82e3722d580d", user_data['Email'], "Email")
        
        # Handle Dropdowns
        gender_raw = str(user_data.get('Gender', 'Male')).strip().lower()
        gender_final = "Female" if "female" in gender_raw else "Male"
        self.js_select(driver, "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d", gender_final, "Gender")
        
        self.js_select(driver, "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8", "Ghana", "Country")
        
        # Handle Referral
        self.handle_referral_react(driver, chosen_ref)
        return True

    def js_select(self, driver, element_id, text, field_name):
        try:
            el = driver.find_element(By.CSS_SELECTOR, f"select[id='{element_id}']")
            driver.execute_script("""
                var sel = arguments[0];
                var text = arguments[1];
                for (var i = 0; i < sel.options.length; i++) {
                    if (sel.options[i].text.toLowerCase().includes(text.toLowerCase())) {
                        sel.selectedIndex = i;
                        break;
                    }
                }
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            """, el, text)
            logger.info(f"   [Select] {field_name} set to: {text}")
        except: 
            logger.warning(f"   [Select Failed] {field_name} could not be set to: {text}")

    def handle_referral_react(self, driver, value):
        try:
            container = driver.find_element(By.ID, "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1")
            driver.execute_script("arguments[0].click();", container)
            time.sleep(1)
            actions = ActionChains(driver)
            actions.send_keys(value)
            actions.pause(1.5)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            logger.info(f"   [Referral] Selected: {value}")
        except: 
            logger.warning(f"   [Referral Failed] Could not select: {value}")

    def register_user(self, user_data):
        # PRINT USER RECORD FOR VISUAL CHECK
        logger.info(f"--- DATA RECORD: {user_data['First Name']} {user_data['Last Name']} ({user_data['Email']}) | Gender: {user_data.get('Gender')} ---")
        
        driver = self.init_driver()
        wait = WebDriverWait(driver, 40)
        
        try:
            driver.get(self.config['target_url'])
            
            # Initial Wait for Site Load
            try: wait.until(EC.invisibility_of_element_located((By.ID, "initialPageLoadSpinner")))
            except: pass
            time.sleep(5)

            chosen_ref = random.choice(self.referral_sources)

            # --- VALIDATION LOOP ---
            max_retries = 3
            for attempt in range(max_retries):
                self.validate_and_fill(driver, user_data, chosen_ref)
                
                if chosen_ref == "Others":
                    try:
                        other_box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']:not([id*='-'])")))
                        self.js_input(driver, other_box.get_attribute("id"), "University of Technology and Applied Sciences", "University Name")
                    except: pass

                # Safety check for error messages
                time.sleep(2)
                errors = driver.find_elements(By.XPATH, "//*[contains(text(), 'is required')]")
                if len(errors) == 0:
                    logger.info("   Form validated successfully.")
                    break
                logger.warning(f"   Validation failed (Attempt {attempt+1}), errors detected. Retrying...")

            # Click consents
            consent_ids = ["1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0", "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0", "7b573551-d547-4f51-adc5-b74686825765-primary_0"]
            if self.config['defaults']['marketing_consent']:
                consent_ids.append("b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0")

            for cid in consent_ids:
                try: driver.execute_script("arguments[0].click();", driver.find_element(By.ID, cid))
                except: pass

            # Proceed to Summary
            time.sleep(1)
            logger.info("   Clicking 'Next' to move to Summary page...")
            driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "forward"))

            # --- SUMMARY PAGE HANDLING ---
            # Wait for Page 1 elements to disappear and summary to load
            time.sleep(6) 
            logger.info("   Summary page loaded. Searching for final Submit button...")
            
            final_btn = wait.until(EC.element_to_be_clickable((By.ID, "forward")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", final_btn)
            time.sleep(1.5)
            driver.execute_script("arguments[0].click();", final_btn)
            logger.info("   Final Submission clicked.")

            # Success Verification
            wait.until(EC.url_contains("confirmation"))
            logger.info(f"   SUCCESS: Registration complete for {user_data['Email']}")
            self.log_registration(user_data, "Success")
            return True

        except Exception as e:
            logger.error(f"   FAILED: {user_data['Email']} | Error: {str(e)}")
            self.log_registration(user_data, f"Failed: {str(e)}")
            return False
        finally:
            try: driver.quit()
            except: pass

    def log_registration(self, user_data, status):
        with open(self.log_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), user_data['First Name'], user_data['Last Name'], user_data['Email'], status])

    def run(self):
        df = pd.read_excel(self.config['excel_path'])
        df.columns = [str(c).strip() for c in df.columns]
        to_process = df[~df['Email'].str.lower().isin(self.registered_emails)]
        
        logger.info(f"--- Session Started: {len(to_process)} New Records ---")
        limit = input("Quantity to process? (Enter for all): ")
        if limit: to_process = to_process.head(int(limit))

        for _, row in to_process.iterrows():
            if self.register_user(row.to_dict()):
                if self.config['settings']['manual_ip_rotation']:
                    input(">>> PAUSE: Rotate IP and press ENTER to continue...")
            time.sleep(random.uniform(3, 7))

if __name__ == "__main__":
    bot = RegistrationBot('config.json')
    bot.run()