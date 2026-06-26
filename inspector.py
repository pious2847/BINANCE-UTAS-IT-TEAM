import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def inspect_page():
    print("Initializing Chrome...")
    options = Options()
    # options.add_argument("--headless") # run headful so we can see it and bypass some anti-bot checks if needed
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        url = "https://www.binance.events/event/a483c41e-d3f9-4fe3-ba5c-5e1a61f4e56b/regProcessStep1"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        print("Waiting 15 seconds for page content to load...")
        time.sleep(15)
        
        print("=== INPUT ELEMENTS ===")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        for i, el in enumerate(inputs):
            print(f"Input {i}:")
            print(f"  ID:          {el.get_attribute('id')}")
            print(f"  Name:        {el.get_attribute('name')}")
            print(f"  Type:        {el.get_attribute('type')}")
            print(f"  Placeholder: {el.get_attribute('placeholder')}")
            print(f"  Class:       {el.get_attribute('class')}")
            print(f"  Value:       {el.get_attribute('value')}")
            print(f"  Aria-Label:  {el.get_attribute('aria-label')}")
            
        print("=== SELECT ELEMENTS ===")
        selects = driver.find_elements(By.TAG_NAME, "select")
        for i, el in enumerate(selects):
            print(f"Select {i}:")
            print(f"  ID:          {el.get_attribute('id')}")
            print(f"  Name:        {el.get_attribute('name')}")
            print(f"  Class:       {el.get_attribute('class')}")
            
        print("=== TEXTAREA ELEMENTS ===")
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        for i, el in enumerate(textareas):
            print(f"Textarea {i}:")
            print(f"  ID:          {el.get_attribute('id')}")
            print(f"  Name:        {el.get_attribute('name')}")
            print(f"  Class:       {el.get_attribute('class')}")

        print("=== BUTTONS ===")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, el in enumerate(buttons):
            print(f"Button {i}:")
            print(f"  ID:          {el.get_attribute('id')}")
            print(f"  Class:       {el.get_attribute('class')}")
            print(f"  Text:        {el.text}")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

if __name__ == '__main__':
    inspect_page()
