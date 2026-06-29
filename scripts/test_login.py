import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        # Log browser console messages
        page.on("console", lambda msg: print(f"Browser Console: [{msg.type}] {msg.text}"))
        
        print("Navigating to http://localhost:8081...")
        await page.goto("http://localhost:8081", timeout=30000)
        await asyncio.sleep(3)
        
        print("Current URL:", page.url)
        
        print("Filling credentials...")
        await page.fill('input[type="email"]', "admin@example.com")
        await page.fill('input[type="password"]', "admin")
        
        print("Clicking submit...")
        await page.click('button[type="submit"]')
        
        print("Waiting 5 seconds for page load...")
        await asyncio.sleep(5)
        
        print("Current URL after login attempt:", page.url)
        
        # Capture error text if any is visible on screen
        try:
            error_element = await page.query_selector('.error, [class*="error"]')
            if error_element:
                text = await error_element.inner_text()
                print(f"Error element text found on screen: {text}")
        except Exception as err:
            print(f"No error element detected: {err}")
            
        print("Taking screenshot...")
        await page.screenshot(path="d:/Works/openwebui_clone/screenshot_dashboard.png")
        print("Screenshot saved to d:/Works/openwebui_clone/screenshot_dashboard.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
