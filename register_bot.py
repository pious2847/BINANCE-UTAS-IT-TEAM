"""
Binance Africa University Tour — Automated Registration Bot (v2.0)
==================================================================
Reads student contact data from a CSV file and registers each user
on the Binance event registration form using Selenium.

Features:
  - CSV data loading with Gender column support
  - Robust field filling with retry logic
  - Random "How did you hear about us?" selection
  - Field value verification after filling
  - Screenshot-on-failure for debugging
  - Structured logging with file + console output
  - Dry-run mode for safe testing
  - Progress tracking
"""

import pandas as pd
import json
import time
import random
import os
import csv
import logging
import sys
from datetime import datetime
from functools import wraps

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementNotInteractableException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager


# ─── Element IDs (from live page inspection) ────────────────────────
FIELD_IDS = {
    "first_name": "56aeaca6-a0ad-4548-8afc-94d8d4361ba1",
    "last_name": "cfc98829-80b7-41b6-82b5-b968d43ef1c1",
    "email": "ff919d05-4281-4d9c-aa0d-82e3722d580d",
    "gender": "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d",
    "country": "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8",
    "how_heard": "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1",
    "consent_age": "1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0",
    "consent_marketing": "b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0",
    "consent_photos": "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0",
    "consent_privacy": "7b573551-d547-4f51-adc5-b74686825765-primary_0",
    "btn_next": "forward",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


# ─── Helpers ─────────────────────────────────────────────────────────

def setup_logger(log_path: str) -> logging.Logger:
    """Create a logger that writes to both console and a debug log file."""
    logger = logging.getLogger("RegistrationBot")
    logger.setLevel(logging.DEBUG)

    # Console handler (INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"))

    # File handler (DEBUG+)
    debug_log = os.path.join(os.path.dirname(log_path), "bot_debug.log")
    fh = logging.FileHandler(debug_log, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 1.5):
    """Decorator that retries a function on Selenium exceptions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (
                    StaleElementReferenceException,
                    ElementNotInteractableException,
                    NoSuchElementException,
                    TimeoutException,
                ) as e:
                    last_exc = e
                    wait_time = delay * (backoff ** (attempt - 1))
                    logger = logging.getLogger("RegistrationBot")
                    logger.warning(
                        f"  ↻ Retry {attempt}/{max_attempts} for {func.__name__}: "
                        f"{type(e).__name__} — waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
            raise last_exc
        return wrapper
    return decorator


# ─── Main Bot Class ──────────────────────────────────────────────────

class RegistrationBot:
    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.log_path = self.config["log_path"]
        self.screenshot_dir = self.config.get("screenshot_dir", "data/screenshots")
        self.dry_run = self.config["settings"].get("dry_run", False)
        self.max_retries = self.config["settings"].get("max_retries", 3)

        self.logger = setup_logger(self.log_path)
        self.ensure_directories()
        self.registered_emails = self._load_registered_emails()

        if self.dry_run:
            self.logger.info("🔒 DRY-RUN MODE — forms will be filled but NOT submitted")

    # ── Setup ────────────────────────────────────────────────────────

    def ensure_directories(self):
        """Create output directories if they don't exist."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "First Name", "Last Name", "Email", "Gender", "Status"])

    def _load_registered_emails(self) -> set:
        """Load already-registered emails from the log CSV to skip duplicates."""
        try:
            df = pd.read_csv(self.log_path)
            emails = set(df["Email"].astype(str).str.strip().str.lower().tolist())
            self.logger.info(f"📋 Loaded {len(emails)} previously registered emails")
            return emails
        except Exception:
            return set()

    # ── Browser ──────────────────────────────────────────────────────

    def _init_driver(self) -> webdriver.Chrome:
        """Initialize Chrome with anti-detection options."""
        chrome_options = Options()
        if self.config["settings"]["headless"]:
            chrome_options.add_argument("--headless=new")

        ua = random.choice(USER_AGENTS)
        chrome_options.add_argument(f"user-agent={ua}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options,
        )
        # Remove navigator.webdriver flag
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        driver.set_window_size(1440, 1000)
        driver.set_page_load_timeout(self.config["settings"].get("page_load_timeout", 30))
        self.logger.debug(f"  Browser initialized (UA: {ua[:50]}…)")
        return driver

    # ── Interaction helpers ──────────────────────────────────────────

    def _human_delay(self, multiplier: float = 1.0):
        """Sleep for a random human-like duration."""
        lo = self.config["settings"]["min_delay"]
        hi = self.config["settings"]["max_delay"]
        time.sleep(random.uniform(lo, hi) * multiplier)

    def _js_click(self, driver, element):
        """Scroll element into view and click via JavaScript."""
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", element)

    def _save_screenshot(self, driver, label: str):
        """Save a timestamped screenshot for debugging."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{ts}.png"
        path = os.path.join(self.screenshot_dir, filename)
        driver.save_screenshot(path)
        self.logger.debug(f"  📸 Screenshot saved: {path}")
        return path

    # ── Field fillers (each retryable) ───────────────────────────────

    @retry(max_attempts=3, delay=1.0)
    def _fill_text_field(self, driver, wait, field_id: str, value: str, field_name: str):
        """Fill a text input, verify the value was set."""
        element = wait.until(EC.presence_of_element_located((By.ID, field_id)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.2)
        element.clear()
        element.send_keys(value)
        self._human_delay(0.3)

        # Verify
        actual = element.get_attribute("value")
        if actual.strip().lower() != value.strip().lower():
            self.logger.warning(f"  ⚠ {field_name} verification failed: expected '{value}', got '{actual}'")
            # Try again via JS
            driver.execute_script(
                "arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
                element,
            )
            element.send_keys(value)
            time.sleep(0.3)
        self.logger.debug(f"  ✓ {field_name}: {value}")

    @retry(max_attempts=3, delay=1.0)
    def _select_dropdown(self, driver, wait, field_id: str, value: str, field_name: str):
        """Select an option from a standard <select> dropdown."""
        element = wait.until(EC.presence_of_element_located((By.ID, field_id)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
        select = Select(element)
        select.select_by_visible_text(value)
        self._human_delay(0.3)

        # Verify
        selected = select.first_selected_option.text
        if selected.strip().lower() != value.strip().lower():
            raise ElementNotInteractableException(
                f"{field_name} selection failed: expected '{value}', got '{selected}'"
            )
        self.logger.debug(f"  ✓ {field_name}: {value}")

    @retry(max_attempts=3, delay=1.5)
    def _select_combobox(self, driver, wait, field_id: str, value: str, field_name: str):
        """Handle the custom React combobox (How did you hear about us?)."""
        # Find and click the combobox container
        container = wait.until(EC.presence_of_element_located((By.ID, field_id)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", container)
        time.sleep(0.5)
        self._js_click(driver, container)
        time.sleep(0.8)

        # Type the value to filter the dropdown
        actions = ActionChains(driver)
        actions.send_keys(value)
        actions.perform()
        time.sleep(1.0)

        # Use ArrowDown + Enter to select the first matching option
        actions2 = ActionChains(driver)
        actions2.send_keys(Keys.ARROW_DOWN)
        actions2.pause(0.5)
        actions2.send_keys(Keys.ENTER)
        actions2.perform()
        time.sleep(0.5)

        self.logger.debug(f"  ✓ {field_name}: {value}")

    @retry(max_attempts=3, delay=0.5)
    def _click_consent(self, driver, element_id: str, label: str):
        """Click a consent radio button using JS click (they're often hidden)."""
        element = driver.find_element(By.ID, element_id)
        self._js_click(driver, element)
        time.sleep(0.2)
        self.logger.debug(f"  ✓ Consent: {label}")

    # ── Registration flow ────────────────────────────────────────────

    def register_user(self, user_data: dict) -> bool:
        """Execute the full registration flow for one user."""
        email = user_data["Email"].strip()
        first_name = str(user_data["First Name"]).strip()
        last_name = str(user_data["Last Name"]).strip()
        gender = str(user_data.get("Gender", self.config["defaults"]["gender"])).strip()

        # Pick a random "How heard" option
        how_heard = random.choice(self.config["defaults"]["how_heard_options"])

        self.logger.info(f"▶ Registering: {first_name} {last_name} ({email})")
        self.logger.info(f"  Gender: {gender} | How heard: {how_heard}")

        driver = self._init_driver()
        wait = WebDriverWait(driver, 25)

        try:
            # ── Navigate to form ─────────────────────────────────────
            driver.get(self.config["target_url"])
            self.logger.info("  ⏳ Waiting for page to load...")
            wait.until(EC.presence_of_element_located((By.ID, FIELD_IDS["first_name"])))
            self._human_delay(0.5)
            self.logger.info("  ✓ Page loaded")

            # ── 1. First Name ────────────────────────────────────────
            self._fill_text_field(driver, wait, FIELD_IDS["first_name"], first_name, "First Name")

            # ── 2. Last Name ─────────────────────────────────────────
            self._fill_text_field(driver, wait, FIELD_IDS["last_name"], last_name, "Last Name")

            # ── 3. Email ─────────────────────────────────────────────
            self._fill_text_field(driver, wait, FIELD_IDS["email"], email, "Email")

            # ── 4. Gender (optional, standard <select>) ─────────────
            if gender and gender.lower() not in ("", "nan", "none"):
                try:
                    self._select_dropdown(driver, wait, FIELD_IDS["gender"], gender, "Gender")
                except Exception as e:
                    self.logger.warning(f"  ⚠ Gender selection skipped (optional): {e}")

            # ── 5. Country of Residence ──────────────────────────────
            self._select_dropdown(
                driver, wait, FIELD_IDS["country"],
                self.config["defaults"]["country"], "Country"
            )

            # ── 6. How did you hear about us? (custom combobox) ──────
            self._select_combobox(
                driver, wait, FIELD_IDS["how_heard"],
                how_heard, "How Heard"
            )

            # ── 7–10. Consent radio buttons ──────────────────────────
            consent_ids = [
                (FIELD_IDS["consent_age"], "Age (18+)"),
                (FIELD_IDS["consent_photos"], "Photos/Video"),
                (FIELD_IDS["consent_privacy"], "Data Privacy"),
            ]
            # Optional marketing consent
            if self.config["defaults"]["marketing_consent"]:
                consent_ids.insert(1, (FIELD_IDS["consent_marketing"], "Marketing"))

            for cid, label in consent_ids:
                self._click_consent(driver, cid, label)

            self._human_delay(1.0)

            # ── Take pre-submit screenshot ───────────────────────────
            self._save_screenshot(driver, f"pre_submit_{email.split('@')[0]}")

            # ── 11. Submit ───────────────────────────────────────────
            if self.dry_run:
                self.logger.info("  🔒 DRY-RUN: Skipping submit — all fields filled successfully")
                self._log_registration(user_data, gender, "DryRun-Success")
                return True

            btn_next = driver.find_element(By.ID, FIELD_IDS["btn_next"])
            self._js_click(driver, btn_next)
            self.logger.info("  ⏳ Submitted — waiting for confirmation...")

            # ── 12. Verify confirmation ──────────────────────────────
            try:
                wait.until(EC.url_contains("regProcessStep2"))
                self.logger.info(f"  ✅ SUCCESS: {email} registered!")
                self._save_screenshot(driver, f"success_{email.split('@')[0]}")
                self._log_registration(user_data, gender, "Success")
                return True
            except TimeoutException:
                # Check if we landed on the confirmation page
                current_url = driver.current_url
                if "confirmation" in current_url.lower() or "regProcessStep2" in current_url:
                    self.logger.info(f"  ✅ SUCCESS (confirmation page): {email}")
                    self._save_screenshot(driver, f"success_{email.split('@')[0]}")
                    self._log_registration(user_data, gender, "Success")
                    return True
                else:
                    self.logger.error(f"  ❌ Submission may have failed — URL: {current_url}")
                    self._save_screenshot(driver, f"uncertain_{email.split('@')[0]}")
                    self._log_registration(user_data, gender, f"Uncertain: {current_url}")
                    return False

        except Exception as e:
            self.logger.error(f"  ❌ FAILED: {email} | {type(e).__name__}: {str(e)[:200]}")
            if self.config["settings"].get("screenshot_on_failure", True):
                self._save_screenshot(driver, f"failed_{email.split('@')[0]}")
            self._log_registration(user_data, gender, f"Failed: {type(e).__name__}: {str(e)[:200]}")
            return False

        finally:
            driver.quit()
            self.logger.debug("  Browser closed")

    # ── Logging ──────────────────────────────────────────────────────

    def _log_registration(self, user_data: dict, gender: str, status: str):
        """Append a row to the registration log CSV."""
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(user_data.get("First Name", "")).strip(),
                str(user_data.get("Last Name", "")).strip(),
                str(user_data.get("Email", "")).strip(),
                gender,
                status,
            ])

    # ── Main run loop ────────────────────────────────────────────────

    def run(self):
        """Load data, filter already-registered, and process registrations."""
        csv_path = self.config["csv_path"]
        self.logger.info(f"📂 Loading data from: {csv_path}")

        # Load CSV
        df = pd.read_csv(csv_path, encoding="utf-8")
        self.logger.info(f"   Total records in file: {len(df)}")

        # Validate required columns
        required_cols = ["First Name", "Last Name", "Email"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            self.logger.error(f"❌ Missing required columns: {missing}")
            self.logger.error(f"   Available columns: {list(df.columns)}")
            return

        # Clean email column
        df["Email"] = df["Email"].astype(str).str.strip().str.lower()

        # Filter out already-registered
        to_process = df[~df["Email"].isin(self.registered_emails)].copy()
        self.logger.info(f"   Already registered: {len(df) - len(to_process)}")
        self.logger.info(f"   Pending: {len(to_process)}")

        if to_process.empty:
            self.logger.info("🎉 All users have already been registered!")
            return

        # Ask how many to process
        print()
        limit_input = input("How many registrations to perform? (Enter for ALL): ").strip()
        if limit_input:
            to_process = to_process.head(int(limit_input))

        total = len(to_process)
        success_count = 0
        fail_count = 0

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"  REGISTRATION SESSION — {total} user(s) to process")
        if self.dry_run:
            self.logger.info(f"  MODE: DRY-RUN (no submissions)")
        self.logger.info(f"{'='*60}\n")

        for idx, (_, row) in enumerate(to_process.iterrows(), start=1):
            self.logger.info(f"\n[{idx}/{total}] ────────────────────────────────────────")
            success = self.register_user(row.to_dict())

            if success:
                success_count += 1
            else:
                fail_count += 1

            # Progress summary
            self.logger.info(
                f"  📊 Progress: {idx}/{total} | "
                f"✅ {success_count} succeeded | ❌ {fail_count} failed"
            )

            # Manual IP rotation
            if success and not self.dry_run and self.config["settings"]["manual_ip_rotation"]:
                print()
                input(">>> Change your IP/VPN now, then press ENTER to continue...")
                print()

            # Random delay between registrations
            if idx < total:
                delay = random.uniform(3, 7)
                self.logger.info(f"  ⏳ Waiting {delay:.1f}s before next registration...")
                time.sleep(delay)

        # ── Final summary ────────────────────────────────────────────
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"  SESSION COMPLETE")
        self.logger.info(f"  Total: {total} | ✅ Success: {success_count} | ❌ Failed: {fail_count}")
        self.logger.info(f"  Log: {self.log_path}")
        self.logger.info(f"{'='*60}")


# ─── Entry Point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    bot = RegistrationBot("config.json")
    bot.run()