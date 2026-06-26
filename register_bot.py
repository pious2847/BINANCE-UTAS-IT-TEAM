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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("data/bot_debug.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Referral options that appear in the React-Select dropdown
REFERRAL_OPTIONS = [
    "Binance App",
    "Binance Communications",
    "Email",
    "X",
    "Instagram",
    "YouTube",
    "Others",
]

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
            return set(df[df['Status'] == 'Success']['Email'].astype(str).str.strip().str.lower().tolist())
        except Exception:
            return set()

    def init_driver(self):
        chrome_options = Options()
        if self.config['settings'].get('headless', False):
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_window_size(1440, 1000)
        return driver

    # ------------------------------------------------------------------ #
    #  Low-level helpers
    # ------------------------------------------------------------------ #

    def js_set_input(self, driver, element_id, text, field_name):
        """
        Fill a plain <input> using JS value injection + React synthetic events.
        Falls back to key-by-key typing if the first attempt doesn't stick.
        """
        try:
            el = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, element_id))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.3)

            # Clear + set value via JS, then fire React's onChange chain
            driver.execute_script("""
                var el = arguments[0];
                var val = arguments[1];
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(el, val);
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.blur();
            """, el, str(text).strip())

            time.sleep(0.2)

            # Verify the value was accepted
            actual = el.get_attribute('value')
            if actual != str(text).strip():
                # Fallback: click + manual typing
                el.click()
                el.send_keys(Keys.CONTROL + "a")
                el.send_keys(Keys.DELETE)
                for char in str(text).strip():
                    el.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.06))
                driver.execute_script("arguments[0].blur();", el)

            logger.info(f"   [Input] {field_name} set to: {str(text).strip()}")
            return True
        except Exception as e:
            logger.error(f"   [Input Error] {field_name}: {str(e)[:120]}")
            return False

    def js_force_select(self, driver, element_id, target_text, field_name):
        """
        Select a native <select> by visible text via JS.
        Finds the element by iterating all selects and matching the id attribute
        directly — avoids CSS-escaping issues with IDs that contain colons.
        """
        # Build JS as a single-quoted string to avoid Python escape clashes
        js = (
            "var rawId = arguments[0];"
            "var target = arguments[1].toLowerCase();"
            "var sel = null;"
            "var all = document.querySelectorAll('select');"
            "for (var j = 0; j < all.length; j++) {"
            "  if (all[j].id === rawId || all[j].name === rawId) { sel = all[j]; break; }"
            "}"
            "if (!sel) throw new Error('Select not found: ' + rawId);"
            "for (var i = 0; i < sel.options.length; i++) {"
            "  if (sel.options[i].text.trim().toLowerCase() === target) {"
            "    sel.selectedIndex = i;"
            "    sel.dispatchEvent(new Event('change', {bubbles: true}));"
            "    sel.blur();"
            "    return 'ok';"
            "  }"
            "}"
            "throw new Error('Option not found: ' + arguments[1]);"
        )
        try:
            driver.execute_script(js, element_id, target_text)
            logger.info(f"   [Select] {field_name} set to: {target_text}")
            time.sleep(0.4)
            return True
        except Exception as e:
            logger.warning(f"   [Select Failed] {field_name}: {str(e)[:120]}")
            return False

    def select_referral(self, driver, value):
        """
        Select the 'How did you hear about us?' React-Select combobox.
        The field renders as a dummy <input> (role=combobox) inside a custom
        dropdown wrapper. We click the visible chevron/control div to open it,
        then click the matching option from the rendered menu.
        Stale-element proof: elements are re-fetched after any wait.
        """
        REFERRAL_ID = "b1fc7e46-8327-4e6a-91f5-10ddae71a8f1"

        # Wait until the field is present
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, REFERRAL_ID))
            )
        except Exception:
            logger.error("   [Referral Error] Field not found within 15s.")
            return False

        try:
            # Scroll the referral field into view first
            dummy_input = driver.find_element(By.ID, REFERRAL_ID)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dummy_input)
            time.sleep(0.5)

            # React-Select needs a real mousedown+click on the chevron indicator div
            # to open the menu. JS click alone doesn't fire the right synthetic events.
            # The indicator container sits inside the control div and has a visible SVG arrow.
            # We try several selectors in order of specificity.
            opened = False
            open_selectors = [
                # The dropdown indicator (chevron) container
                "div[data-cvent-id='async-dropdown-wrapper'] div[class*='indicatorContainer']",
                "div[data-cvent-id='async-dropdown-wrapper'] div[class*='indicator']",
                # The whole control row
                "div[data-cvent-id='async-dropdown-wrapper'] div[class*='control']",
                # The wrapper itself as last resort
                "div[data-cvent-id='async-dropdown-wrapper']",
            ]
            for sel in open_selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.2)
                    # Use ActionChains for a real mouse click
                    ActionChains(driver).move_to_element(el).click().perform()
                    time.sleep(1.8)  # Wait for menu to render
                    # Check if options appeared
                    test = driver.execute_script(
                        "var divs=document.querySelectorAll('div');"
                        "for(var i=0;i<divs.length;i++){"
                        "  if((divs[i].id||'').match(/react-select-\\d+-option-\\d+/)) return true;"
                        "} return false;"
                    )
                    if test:
                        opened = True
                        logger.info(f"   [Referral] Menu opened via: {sel}")
                        break
                except Exception:
                    continue

            if not opened:
                logger.warning("   [Referral] Could not open menu via click, trying keyboard...")
                try:
                    dummy_input = driver.find_element(By.ID, REFERRAL_ID)
                    ActionChains(driver).move_to_element(dummy_input).click().perform()
                    time.sleep(1.5)
                except Exception:
                    pass

            # Debug: log what appeared in the DOM after opening
            try:
                menu_debug = driver.execute_script(
                    "var items = document.querySelectorAll('[id*=react-select],[class*=-option],[class*=MenuList]');"
                    "var out = [];"
                    "for(var i=0;i<Math.min(items.length,20);i++){"
                    "  out.push(items[i].tagName+'|'+items[i].id+'|'+items[i].className.substring(0,60)+'|'+items[i].textContent.substring(0,40));"
                    "}"
                    "return out.join('\\n');"
                )
                logger.info(f"   [Referral Debug] DOM snapshot:\n{menu_debug}")
            except Exception:
                pass

            # Use JS to find individual option elements by react-select's id pattern.
            # React-Select assigns ids like "react-select-2-option-0", "react-select-2-option-1"
            # The JS below collects all elements whose id matches that pattern.
            options_js = (
                "var all = document.querySelectorAll('div');"
                "var opts = [];"
                "for (var i = 0; i < all.length; i++) {"
                "  var id = all[i].id || '';"
                "  if (id.match(/react-select-\\d+-option-\\d+/)) opts.push(all[i]);"
                "}"
                "return opts;"
            )

            # Poll until options appear (menu needs time to render)
            options = []
            for _ in range(8):
                options = driver.execute_script(options_js)
                if options:
                    break
                time.sleep(0.5)

            if not options:
                logger.error("   [Referral Error] Could not find dropdown option elements.")
                return False

            logger.info(f"   [Referral] Found {len(options)} options. Looking for: '{value}'")

            target = value.strip().lower()

            # Get text content of each option via JS to avoid stale reads
            option_texts = driver.execute_script(
                "return arguments[0].map(function(el){ return el.textContent.trim(); });",
                options
            )
            logger.info(f"   [Referral] Options: {option_texts}")

            matched = None
            matched_idx = None
            for i, txt in enumerate(option_texts):
                if txt.lower() == target:
                    matched = options[i]
                    matched_idx = i
                    break
            if matched is None:
                for i, txt in enumerate(option_texts):
                    if target in txt.lower():
                        matched = options[i]
                        matched_idx = i
                        break
            if matched is None:
                matched = options[0]
                logger.warning(f"   [Referral] '{value}' not found, using first: '{option_texts[0]}'")

            # Re-fetch wrapper position in case of any re-render, then click option
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", matched)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", matched)

            time.sleep(0.5)
            logger.info(f"   [Referral] Selected: {value}")
            return True

        except Exception as e:
            logger.error(f"   [Referral Error] {str(e)[:300]}")
            return False

    def click_consent_radio(self, driver, radio_id):
        """Click a radio button via JS, tolerating missing elements."""
        try:
            el = driver.find_element(By.ID, radio_id)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            driver.execute_script("arguments[0].click();", el)
            time.sleep(0.2)
        except Exception:
            pass  # Non-critical; just skip if not found

    # ------------------------------------------------------------------ #
    #  Main registration flow
    # ------------------------------------------------------------------ #

    def register_user(self, user_data):
        first = str(user_data.get('First Name', '')).strip()
        last  = str(user_data.get('Last Name',  '')).strip()
        email = str(user_data.get('Email',      '')).strip()

        logger.info(f"--- PROCESSING: {first} {last} ({email}) ---")

        driver = self.init_driver()
        wait   = WebDriverWait(driver, 40)

        try:
            driver.get(self.config['target_url'])

            # Wait until the First Name field is present and interactive
            wait.until(EC.element_to_be_clickable(
                (By.ID, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1")
            ))
            # Extra buffer for React to finish rendering all fields
            time.sleep(2)

            # --- Step 1: Text fields ---
            self.js_set_input(driver, "56aeaca6-a0ad-4548-8afc-94d8d4361ba1", first, "First Name")
            self.js_set_input(driver, "cfc98829-80b7-41b6-82b5-b968d43ef1c1", last,  "Last Name")
            self.js_set_input(driver, "ff919d05-4281-4d9c-aa0d-82e3722d580d", email, "Email")

            # --- Step 2: Gender (native <select>) ---
            gender_raw   = str(user_data.get('Gender', '')).strip().lower()
            gender_final = "Female" if "female" in gender_raw else "Male"
            self.js_force_select(
                driver, "widget:0aa5a2d5-27e5-443e-9c04-01d7f0c1c98d",
                gender_final, "Gender"
            )

            # --- Step 3: Country (native <select>) ---
            self.js_force_select(
                driver, "bbe011f6-855c-41f2-ac1f-d1cbc6b15af8",
                "Ghana", "Country"
            )

            # Let JS selections settle before touching the React-Select
            time.sleep(1)

            # --- Step 4: Referral (React-Select combobox) ---
            chosen_ref = random.choice(REFERRAL_OPTIONS)
            self.select_referral(driver, chosen_ref)

            # If "Others" chosen, fill the follow-up text box
            if chosen_ref == "Others":
                time.sleep(1.5)
                try:
                    other_input = driver.find_element(
                        By.CSS_SELECTOR,
                        "input[placeholder], input[aria-label*='specify'], "
                        "input[aria-label*='other' i], input[aria-label*='Other' i]"
                    )
                    other_id = other_input.get_attribute("id")
                    self.js_set_input(
                        driver, other_id,
                        self.config['defaults'].get('other_text', 'University of Technology and Applied Sciences'),
                        "Other Source"
                    )
                except Exception:
                    logger.warning("   [Others] Follow-up text box not found, skipping.")

            # --- Step 5: Consent radio buttons ---
            for radio_id in [
                "1e8d0338-89c4-4983-beea-4ffa7ecb6a19-primary_0",
                "b320fbfd-e250-4cc1-bdad-8db06a643ec2-primary_0",
                "0dde9017-0819-4383-a921-fc502bee3cc1-primary_0",
                "7b573551-d547-4f51-adc5-b74686825765-primary_0",
            ]:
                self.click_consent_radio(driver, radio_id)

            time.sleep(0.5)

            # --- Step 6: Click "Next" on Step 1 ---
            next_btn = wait.until(EC.element_to_be_clickable((By.ID, "forward")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", next_btn)
            logger.info("   Clicked 'Next' — watching for modal or page change...")

            # --- Step 7: Check for "already registered" modal ---
            # Give the page up to 8 seconds to either show a modal OR navigate away
            already_registered = False
            for _ in range(16):  # 16 × 0.5s = 8s
                time.sleep(0.5)
                cur_url = driver.current_url

                # If page navigated away from step1, we're on the summary page — good
                if "regProcessStep1" not in cur_url:
                    break

                # Check for a modal / dialog indicating already registered
                modal_text = driver.execute_script(
                    "var modal = document.querySelector("
                    "  '[role=\"dialog\"], [class*=\"modal\"], [class*=\"Modal\"], "
                    "   [class*=\"alert\"], [class*=\"Alert\"]'"
                    ");"
                    "return modal ? modal.innerText : '';"
                )
                if modal_text and any(kw in modal_text.lower() for kw in
                                      ["already", "duplicate", "registered", "exists"]):
                    logger.info(f"   Already-registered modal detected: {modal_text[:120]}")
                    already_registered = True

                    # Dismiss the modal — try common close buttons
                    dismissed = driver.execute_script(
                        "var btns = document.querySelectorAll("
                        "  'button, [role=\"button\"]'"
                        ");"
                        "for (var i = 0; i < btns.length; i++) {"
                        "  var t = btns[i].innerText.toLowerCase();"
                        "  if (t.includes('ok') || t.includes('close') || t.includes('dismiss') ||"
                        "      t.includes('cancel') || t.includes('got it')) {"
                        "    btns[i].click(); return btns[i].innerText;"
                        "  }"
                        "}"
                        "return null;"
                    )
                    logger.info(f"   Modal dismissed via: '{dismissed}'")
                    break
            else:
                # Timed out still on step1 — something is wrong
                raise Exception("Timed out waiting for page to advance from Step 1.")

            # If already registered, log and treat as success (skip, don't re-add to CSV)
            if already_registered:
                logger.info(f"   ALREADY REGISTERED: {email} — skipping.")
                self.log_registration(user_data, "Already Registered")
                return "already_registered"

            time.sleep(2)  # Let summary page fully render
            logger.info(f"   Summary page loaded: {driver.current_url}")

            # --- Step 8: Final submit (button id="submit", not "forward") ---
            # Try "submit" first (page 2 button), then fall back to "forward"
            final_btn = None
            for btn_id in ["submit", "forward"]:
                try:
                    final_btn = wait.until(EC.element_to_be_clickable((By.ID, btn_id)))
                    logger.info(f"   Found final button: id='{btn_id}'")
                    break
                except Exception:
                    continue

            if final_btn is None:
                raise Exception("Could not find final Submit/Next button on summary page.")

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("arguments[0].click();", final_btn)
            logger.info("   Final submit clicked — proceeding to next registration...")

            # --- Step 9: Wait briefly then move on (don't block on confirmation page) ---
            # We just need the page to leave the summary/regPage — success is confirmed
            # by the URL changing away from regPage. We do NOT wait for /confirmation
            # since that wastes time; the submission is already queued server-side.
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: "regPage" not in d.current_url or
                              "confirmation" in d.current_url
                )
            except Exception:
                pass  # If it times out, check the URL anyway

            final_url = driver.current_url
            if "regProcessStep1" in final_url and "regPage" not in final_url:
                raise Exception(f"Submission may have failed. URL: {final_url}")

            logger.info(f"   SUCCESS: {email} | Final URL: {final_url}")
            self.log_registration(user_data, "Success")
            return True

        except Exception as e:
            logger.error(f"   FAILED: {email} | URL: {driver.current_url}")
            logger.error(f"   Error: {str(e)[:300]}")
            self.log_registration(user_data, f"Failed: {str(e)[:200]}")
            return False
        finally:
            driver.quit()

    def log_registration(self, user_data, status):
        first = str(user_data.get('First Name', '')).strip()
        last  = str(user_data.get('Last Name',  '')).strip()
        email = str(user_data.get('Email',      '')).strip()
        with open(self.log_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), first, last, email, status])

    def run(self):
        df = pd.read_excel(self.config['excel_path'])
        df.columns = [str(c).strip() for c in df.columns]

        # Filter out already-successfully-registered emails
        mask = ~df['Email'].astype(str).str.strip().str.lower().isin(self.registered_emails)
        to_process = df[mask].copy()

        print(f"\nTotal pending: {len(to_process)} records")
        limit = input("How many to process this session? (blank = all): ").strip()
        if limit.isdigit():
            to_process = to_process.head(int(limit))

        success_count  = 0
        fail_count     = 0
        already_count  = 0
        session_successes = []  # track successful rows for the session summary

        for idx, (_, row) in enumerate(to_process.iterrows(), start=1):
            print(f"\n[{idx}/{len(to_process)}]", flush=True)
            result = self.register_user(row.to_dict())
            if result is True:
                success_count += 1
                session_successes.append(row.to_dict())
                if self.config['settings'].get('manual_ip_rotation', False):
                    input(">>> Rotate your IP now, then press ENTER to continue...")
            elif result == "already_registered":
                already_count += 1
                # No IP rotation needed; no delay either — just move on
            else:
                fail_count += 1

            delay = random.uniform(
                self.config['settings'].get('min_delay', 2),
                self.config['settings'].get('max_delay', 5)
            )
            logger.info(f"   Sleeping {delay:.1f}s before next record...")
            time.sleep(delay)

        # --- Write session summary ---
        self._write_session_summary(session_successes, success_count, fail_count, already_count)
        logger.info(
            f"\n=== SESSION COMPLETE | "
            f"Success: {success_count} | "
            f"Already Registered: {already_count} | "
            f"Failed: {fail_count} ==="
        )

    def _write_session_summary(self, successes, success_count, fail_count, already_count=0):
        """
        Writes two files after each session:
          data/session_TIMESTAMP.csv  — clean CSV of everyone registered this session
          data/session_TIMESTAMP.txt  — human-readable summary with counts and name list
        """
        timestamp   = time.strftime('%Y-%m-%d_%H-%M-%S')
        summary_dir = os.path.dirname(self.log_path)
        csv_path    = os.path.join(summary_dir, f"session_{timestamp}.csv")
        txt_path    = os.path.join(summary_dir, f"session_{timestamp}.txt")

        # --- CSV: one row per successful registrant (no duplicates) ---
        seen_emails = set()
        unique_successes = []
        for s in successes:
            em = str(s.get('Email', '')).strip().lower()
            if em not in seen_emails:
                seen_emails.add(em)
                unique_successes.append(s)

        if unique_successes:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['First Name', 'Last Name', 'Email', 'Registered At'])
                reg_time = time.strftime('%Y-%m-%d %H:%M:%S')
                for s in unique_successes:
                    writer.writerow([
                        str(s.get('First Name', '')).strip(),
                        str(s.get('Last Name',  '')).strip(),
                        str(s.get('Email',      '')).strip(),
                        reg_time,
                    ])
            logger.info(f"   Session CSV saved: {csv_path}")
        else:
            logger.info("   No new successes this session — skipping CSV.")

        # --- TXT: human-readable summary ---
        total = success_count + fail_count + already_count
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("=" * 52 + "\n")
            f.write("     REGISTRATION SESSION SUMMARY\n")
            f.write("=" * 52 + "\n")
            f.write(f"  Date/Time        : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Successful       : {success_count}\n")
            f.write(f"  Already Registered: {already_count}\n")
            f.write(f"  Failed           : {fail_count}\n")
            f.write(f"  Total Processed  : {total}\n")
            f.write("=" * 52 + "\n\n")

            if unique_successes:
                f.write("Newly Registered Participants:\n")
                f.write("-" * 52 + "\n")
                for i, s in enumerate(unique_successes, start=1):
                    first = str(s.get('First Name', '')).strip()
                    last  = str(s.get('Last Name',  '')).strip()
                    email = str(s.get('Email',      '')).strip()
                    f.write(f"  {i:>3}. {first} {last} — {email}\n")
            else:
                f.write("  No new successful registrations this session.\n")

        logger.info(f"   Session summary saved: {txt_path}")


if __name__ == "__main__":
    bot = RegistrationBot('config.json')
    bot.run()
