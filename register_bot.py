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

    def get_random_user_agent(self):
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        return random.choice(user_agents)

    def init_driver(self):
        chrome_options = Options()
        if self.config['settings']['headless']:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument(f"user-agent={self.get_random_user_agent()}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_window_size(1440, 1000)
        return driver

    def js_click(self, driver, element):
        """Forces a click on hidden elements using JavaScript."""
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)

    def human_delay(self, mult=1.0):
        time.sleep(random.uniform(self.config['settings']['min_delay'], self.config['settings']['max_delay']) * mult)

    def register_user(self, user_data):
        driver = self.init_driver()
        wait = WebDriverWait(driver, 25)
        
        try:
            driver.get(self.config['target_url'])
            
            # 1. First Name
            first_name = wait.until(EC.presence_of_element_located((By.ID, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1")))
            first_name.send_keys(user_data['First Name'])
            
            # 2. Last Name
            driver.find_element(By.ID, "cfc98829-80b7-41b6-82b5-b968d43ef1c1").send_keys(user_data['Last Name'])
            
            # 3. Email
            driver.find_element(By.ID, "ff919d05-4281-4d9c-aa0d-82e3722d580d").send_keys(user_data['Email'])
            self.human_delay(0.5)

            # 4. Country of Residence
            country_el = driver.find_element(By.ID, "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8")
            Select(country_el).select_by_visible_text(self.config['defaults']['country'])
            
            # 5. How did you hear about us? (Handling Dummy Input)
            # We click the container instead of the input to ensure focus
            how_heard_container = driver.find_element(By.ID, "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1")
            self.js_click(driver, how_heard_container)
            self.human_delay(0.3)
            # Use ActionChains to type directly into the focused component
            actions = ActionChains(driver)
            actions.send_keys(self.config['defaults']['how_heard'])
            actions.pause(1)
            actions.send_keys(Keys.ENTER)
            actions.perform()

            # 6-9. Radio Button Consents (Using JS Click for hidden inputs)
            consent_ids = [
                "1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0", # Age
                "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0", # Photos
                "7b573551-d547-4f51-adc5-b74686825765-primary_0"  # Privacy
            ]
            
            # Optional Marketing Consent
            if self.config['defaults']['marketing_consent']:
                consent_ids.insert(1, "b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0")

            for cid in consent_ids:
                el = driver.find_element(By.ID, cid)
                self.js_click(driver, el)
                time.sleep(0.2)

            self.human_delay(1.5)
            
            # 10. Submit
            btn_next = driver.find_element(By.ID, "forward")
            self.js_click(driver, btn_next)
            
            # Verification
            wait.until(EC.url_contains("regProcessStep2"))
            print(f"SUCCESS: {user_data['Email']}")
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
        
        print(f"--- Registration Session Started ---")
        print(f"Pending Records: {len(to_process)}")
        
        limit = input("Number of registrations to perform (Enter for ALL): ")
        if limit:
            to_process = to_process.head(int(limit))

        for index, row in to_process.iterrows():
            print(f"Processing: {row['Email']}")
            success = self.register_user(row.to_dict())
            
            if success and self.config['settings']['manual_ip_rotation']:
                input(">>> Change IP/VPN now, then press ENTER...")
            
            time.sleep(random.uniform(3, 7))

if __name__ == "__main__":
    bot = RegistrationBot('config.json')
    bot.run()