"""
Page Inspector — Discovers all form elements on the Binance registration page.

Enumerates all inputs, selects (with options), textareas, buttons, and
custom combobox components. Saves results to a JSON file for reference.
"""

import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


TARGET_URL = "https://www.binance.events/event/a483c41e-d3f9-4fe3-ba5c-5e1a61f4e56b/regProcessStep1"


def inspect_page():
    print("Initializing Chrome...")
    options = Options()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    results = {"url": TARGET_URL, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "elements": {}}

    try:
        print(f"Navigating to {TARGET_URL}...")
        driver.get(TARGET_URL)

        print("Waiting 15 seconds for page content to load...")
        time.sleep(15)

        # ── Inputs ───────────────────────────────────────────────
        print("\n=== INPUT ELEMENTS ===")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        input_data = []
        for i, el in enumerate(inputs):
            entry = {
                "index": i,
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "type": el.get_attribute("type"),
                "placeholder": el.get_attribute("placeholder"),
                "class": el.get_attribute("class"),
                "value": el.get_attribute("value"),
                "aria_label": el.get_attribute("aria-label"),
                "required": el.get_attribute("required"),
            }
            input_data.append(entry)
            print(f"\nInput {i}:")
            for k, v in entry.items():
                if v:
                    print(f"  {k:15s}: {v}")
        results["elements"]["inputs"] = input_data

        # ── Selects (with options) ───────────────────────────────
        print("\n=== SELECT ELEMENTS ===")
        selects = driver.find_elements(By.TAG_NAME, "select")
        select_data = []
        for i, el in enumerate(selects):
            options_list = []
            for opt in el.find_elements(By.TAG_NAME, "option"):
                options_list.append({
                    "value": opt.get_attribute("value"),
                    "text": opt.text,
                    "selected": opt.is_selected(),
                })
            entry = {
                "index": i,
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "class": el.get_attribute("class"),
                "options": options_list,
            }
            select_data.append(entry)
            print(f"\nSelect {i}:")
            print(f"  {'id':15s}: {entry['id']}")
            print(f"  {'name':15s}: {entry['name']}")
            print(f"  {'options':15s}: {len(options_list)} options")
            for opt in options_list[:10]:
                marker = " ← selected" if opt["selected"] else ""
                print(f"    - {opt['text']}{marker}")
            if len(options_list) > 10:
                print(f"    ... and {len(options_list) - 10} more")
        results["elements"]["selects"] = select_data

        # ── Textareas ────────────────────────────────────────────
        print("\n=== TEXTAREA ELEMENTS ===")
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        textarea_data = []
        for i, el in enumerate(textareas):
            entry = {
                "index": i,
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "class": el.get_attribute("class"),
            }
            textarea_data.append(entry)
            print(f"\nTextarea {i}:")
            for k, v in entry.items():
                if v:
                    print(f"  {k:15s}: {v}")
        results["elements"]["textareas"] = textarea_data

        # ── Buttons ──────────────────────────────────────────────
        print("\n=== BUTTONS ===")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        button_data = []
        for i, el in enumerate(buttons):
            entry = {
                "index": i,
                "id": el.get_attribute("id"),
                "class": el.get_attribute("class"),
                "text": el.text,
                "type": el.get_attribute("type"),
            }
            button_data.append(entry)
            print(f"\nButton {i}:")
            for k, v in entry.items():
                if v:
                    print(f"  {k:15s}: {v}")
        results["elements"]["buttons"] = button_data

        # ── Custom combobox components ───────────────────────────
        print("\n=== COMBOBOX / AUTOCOMPLETE ELEMENTS ===")
        combos = driver.find_elements(By.CSS_SELECTOR, '[role="combobox"], [role="listbox"], [aria-autocomplete]')
        combo_data = []
        for i, el in enumerate(combos):
            entry = {
                "index": i,
                "id": el.get_attribute("id"),
                "role": el.get_attribute("role"),
                "aria_label": el.get_attribute("aria-label"),
                "class": el.get_attribute("class"),
            }
            combo_data.append(entry)
            print(f"\nCombobox {i}:")
            for k, v in entry.items():
                if v:
                    print(f"  {k:15s}: {v}")
        results["elements"]["comboboxes"] = combo_data

        # ── Labels ───────────────────────────────────────────────
        print("\n=== LABELS ===")
        labels = driver.find_elements(By.TAG_NAME, "label")
        label_data = []
        for i, el in enumerate(labels):
            entry = {
                "index": i,
                "for": el.get_attribute("for"),
                "text": el.text[:100],
                "class": el.get_attribute("class"),
            }
            label_data.append(entry)
            if el.text.strip():
                print(f"  Label {i}: for='{entry['for']}' → \"{el.text[:80]}\"")
        results["elements"]["labels"] = label_data

        # ── Save results to JSON ─────────────────────────────────
        output_path = os.path.join("data", "page_inspection.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Inspection results saved to: {output_path}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    inspect_page()
