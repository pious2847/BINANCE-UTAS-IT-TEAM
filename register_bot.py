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
        
        # Options for randomizing "How did you hear about us?"
        self.referral_sources = [
            "Social Media", 
            "Friend", 
            "Binance App", 
            "Twitter", 
            "Telegram", 
            "Email", 
            "University Club"
        ]

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
        except:
            return set()

    def init_driver(self):
        chrome_options = Options()
        if self.config['settings']['headless']:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_window_size(random.choice([1366, 1440, 1920]), 1000)
        return driver

    def js_click(self, driver, element):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)

    def select_react_dropdown(self, driver, element_id, value):
        """Handles React-Select components for Gender/Referral"""
        try:
            container = driver.find_element(By.ID, element_id)
            self.js_click(driver, container)
            time.sleep(0.8)
            
            actions = ActionChains(driver)
            actions.send_keys(value)
            time.sleep(1)
            actions.send_keys(Keys.ENTER)
            actions.perform()
            time.sleep(0.5)
        except Exception as e:
            print(f"   ! Dropdown Warning ({element_id}): {e}")

    def register_user(self, user_data):
        driver = self.init_driver()
        wait = WebDriverWait(driver, 25)
        
        try:
            driver.get(self.config['target_url'])
            
            # --- Personal Info ---
            wait.until(EC.presence_of_element_located((By.ID, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1"))).send_keys(user_data['First Name'])
            driver.find_element(By.ID, "cfc98829-80b7-41b6-82b5-b968d43ef1c1").send_keys(user_data['Last Name'])
            driver.find_element(By.ID, "ff919d05-4281-4d9c-aa0d-82e3722d580d").send_keys(user_data['Email'])
            
            # --- Gender (From Excel) ---
            # Mapping Excel values to Select options (Male/Female)
            gender_val = str(user_data.get('Gender', 'Male')).strip().capitalize()
            if gender_val not in ["Male", "Female"]: gender_val = "Male" # Fallback
            
            try:
                gender_el = driver.find_element(By.ID, "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d")
                Select(gender_el).select_by_visible_text(gender_val)
            except:
                self.select_react_dropdown(driver, "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d", gender_val)

            # --- Country ---
            country_el = driver.find_element(By.ID, "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8")
            Select(country_el).select_by_visible_text(self.config['defaults']['country'])
            
            # --- Referral (Randomized) ---
            random_source = random.choice(self.referral_sources)
            self.select_react_dropdown(driver, "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1", random_source)

            # --- Consent Radios ---
            consent_ids = [
                "1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0", 
                "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0", 
                "7b573551-d547-4f51-adc5-b74686825765-primary_0"
            ]
            if self.config['defaults']['marketing_consent']:
                consent_ids.append("b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0")

            for cid in consent_ids:
                self.js_click(driver, driver.find_element(By.ID, cid))

            # --- Final Submit ---
            time.sleep(1)
            self.js_click(driver, driver.find_element(By.ID, "forward"))
            
            # Verify success (URL change)
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
        to_process = df[~df['Email'].str.lower().isin(self.registered_emails)]
        
        print(f"--- Session Summary ---")
        print(f"New Records: {len(to_process)}")
        
        limit = input("Enter quantity to register (Press Enter for ALL): ")
        if limit: to_process = to_process.head(int(limit))

        for _, row in to_process.iterrows():
            print(f"Processing: {row['Email']} ({row.get('Gender', 'N/A')})")
            if self.register_user(row.to_dict()):
                print(f"SUCCESS!")
                if self.config['settings']['manual_ip_rotation']:
                    input(">>> PROMPT: Change IP/VPN now. Press ENTER to continue...")
            time.sleep(random.uniform(3, 6))

if __name__ == "__main__":
    bot = RegistrationBot('config.json')
    bot.run()