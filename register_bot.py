import pandas as pd
import json
import time
import random
import os
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

class RegistrationBot:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.log_path = self.config['log_path']
        self.ensure_log_exists()
        self.registered_emails = self.load_registered_emails()
        self.referral_sources = ["Social Media", "Friend", "Binance App", "Twitter", "Telegram", "Email", "Other"]

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

    def js_click(self, driver, element):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)

    def robust_type(self, driver, element_id, text):
        """Types text and ensures focus is removed afterward to prevent text leakage."""
        wait = WebDriverWait(driver, 10)
        el = wait.until(EC.presence_of_element_located((By.ID, element_id)))
        self.js_click(driver, el)
        time.sleep(0.2)
        el.send_keys(Keys.CONTROL + "a")
        el.send_keys(Keys.BACKSPACE)
        for char in str(text):
            el.send_keys(char)
            time.sleep(random.uniform(0.01, 0.03))
        # Remove focus from field
        el.send_keys(Keys.TAB)
        time.sleep(0.3)

    def force_select_dropdown(self, driver, element_id, target_value):
        """Forces selection on React and Standard Selects."""
        wait = WebDriverWait(driver, 10)
        try:
            container = wait.until(EC.element_to_be_clickable((By.ID, element_id)))
            
            if container.tag_name == 'select':
                # Standard HTML Select (Gender / Country)
                s = Select(container)
                s.select_by_visible_text(target_value)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", container)
            else:
                # React Custom Dropdown (How Heard)
                self.js_click(driver, container)
                time.sleep(0.8)
                actions = ActionChains(driver)
                actions.send_keys(target_value)
                actions.pause(1)
                actions.send_keys(Keys.ENTER)
                actions.perform()
            time.sleep(0.5)
        except Exception as e:
            print(f"   ! Warning: Failed to select {target_value} on {element_id}")

    def register_user(self, user_data):
        driver = self.init_driver()
        wait = WebDriverWait(driver, 30)
        
        try:
            driver.get(self.config['target_url'])
            
            # Wait for spinner
            try: wait.until(EC.invisibility_of_element_located((By.ID, "initialPageLoadSpinner")))
            except: pass
            time.sleep(2)

            # 1. First/Last/Email
            self.robust_type(driver, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1", user_data['First Name'])
            self.robust_type(driver, "cfc98829-80b7-41b6-82b5-b968d43ef1c1", user_data['Last Name'])
            self.robust_type(driver, "ff919d05-4281-4d9c-aa0d-82e3722d580d", user_data['Email'])

            # 2. Gender Selection (Robust)
            gender_raw = str(user_data.get('Gender', 'Male')).strip().lower()
            gender_final = "Female" if "female" in gender_raw else "Male"
            print(f"   Gender: {gender_final}")
            self.force_select_dropdown(driver, "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d", gender_final)

            # 3. Country (Fixed to Ghana)
            print(f"   Country: Ghana")
            self.force_select_dropdown(driver, "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8", "Ghana")

            # 4. Referral (How did you hear about us?)
            chosen_ref = random.choice(self.referral_sources)
            print(f"   Referral: {chosen_ref}")
            self.force_select_dropdown(driver, "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1", chosen_ref)
            
            if chosen_ref == "Other":
                time.sleep(1.5)
                # Select the box that doesn't have the hyphenated ID
                other_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']:not([id*='-'])")))
                self.robust_type(driver, other_box.get_attribute("id"), "University Of Technology And Applied Sciences, Navorongo")

            # 5. Consent Radios (JS click to ensure they are hit)
            consent_ids = [
                "1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0", 
                "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0", 
                "7b573551-d547-4f51-adc5-b74686825765-primary_0"
            ]
            if self.config['defaults']['marketing_consent']:
                consent_ids.append("b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0")

            for cid in consent_ids:
                try:
                    el = driver.find_element(By.ID, cid)
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.3)
                except: pass

            # 6. Final Submit
            time.sleep(1)
            submit_btn = driver.find_element(By.ID, "forward")
            driver.execute_script("arguments[0].click();", submit_btn)
            
            # Wait for Step 2
            wait.until(EC.url_contains("regProcessStep2"))
            self.log_registration(user_data, "Success")
            return True

        except Exception as e:
            print(f"FAILED: {user_data['Email']} | Error: {str(e)}")
            self.log_registration(user_data, f"Failed: {str(e)}")
            return False
        finally:
            driver.quit()

    def log_registration(self, user_data, status):
        with open(self.log_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), user_data['First Name'], user_data['Last Name'], user_data['Email'], status])

    def run(self):
        df = pd.read_excel(self.config['excel_path'])
        df.columns = [str(c).strip() for c in df.columns]
        to_process = df[~df['Email'].str.lower().isin(self.registered_emails)]
        
        print(f"--- Session: {len(to_process)} records ---")
        limit = input("Quantity? (Enter for all): ")
        if limit: to_process = to_process.head(int(limit))

        for _, row in to_process.iterrows():
            print(f"-> {row['Email']}")
            if self.register_user(row.to_dict()):
                print("   SUCCESS!")
                if self.config['settings']['manual_ip_rotation']:
                    input(">>> Rotated IP? Press ENTER...")
            time.sleep(random.uniform(2, 4))

if __name__ == "__main__":
    bot = RegistrationBot('config.json')
    bot.run()