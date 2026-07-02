import time
import os
from playwright.sync_api import sync_playwright

def main():
    artifact_dir = r"C:\Users\RD03590\.gemini\antigravity\brain\39c5d0c2-f92d-4af3-8e9c-7b72f9754552"
    
    if not os.path.exists(artifact_dir):
        os.makedirs(artifact_dir)
        
    print("Starting Playwright verification...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        # 1. Login
        print("Navigating to login page...")
        page.goto("http://localhost:8081/auth")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        print("Filling credentials...")
        page.locator('input[type="email"], input[name="email"]').first.fill("admin@example.com")
        page.locator('input[type="password"]').first.fill("admin")
        page.locator('button[type="submit"]').first.click()
        
        print("Waiting for dashboard...")
        time.sleep(5)
        
        # 2. Đi trực tiếp tới trang cài đặt Integrations
        print("Navigating directly to Integrations Settings URL...")
        page.goto("http://localhost:8081/admin/settings/integrations")
        time.sleep(5)
        
        # Chụp ảnh màn hình cài đặt Integrations
        settings_path = os.path.join(artifact_dir, "screenshot_cleanup_connections.png")
        page.screenshot(path=settings_path)
        print(f"Saved integrations settings screenshot to {settings_path}")
        
        # 3. Đi tới trang Workspace Tools
        print("Navigating to Workspace Tools...")
        page.goto("http://localhost:8081/workspace/tools")
        time.sleep(4)
        
        # Chụp ảnh màn hình danh sách Tools
        tools_path = os.path.join(artifact_dir, "screenshot_cleanup_tools.png")
        page.screenshot(path=tools_path)
        print(f"Saved workspace tools screenshot to {tools_path}")
        
        browser.close()
        print("Playwright verification completed successfully.")

if __name__ == "__main__":
    main()
