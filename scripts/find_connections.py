import time
from playwright.sync_api import sync_playwright

def main():
    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Logging in...")
        page.goto("http://localhost:8081/auth")
        page.locator('input[type="email"], input[name="email"]').first.fill("admin@example.com")
        page.locator('input[type="password"]').first.fill("admin")
        page.locator('button[type="submit"]').first.click()
        
        time.sleep(5)
        
        print("Navigating to Admin Settings...")
        page.goto("http://localhost:8081/admin/settings")
        time.sleep(4)
        
        # Lấy tất cả thẻ a
        print("--- ALL LINKS (a) ---")
        links = page.locator('a').all()
        for idx, el in enumerate(links):
            try:
                print(f"Link {idx}: text='{el.text_content().strip()}', href='{el.get_attribute('href')}'")
            except Exception as e:
                pass
                
        # Lấy tất cả thẻ button
        print("--- ALL BUTTONS (button) ---")
        buttons = page.locator('button').all()
        for idx, el in enumerate(buttons):
            try:
                print(f"Button {idx}: text='{el.text_content().strip()}'")
            except Exception as e:
                pass
                
        browser.close()

if __name__ == "__main__":
    main()
