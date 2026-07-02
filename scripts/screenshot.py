import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        print("Navigating to http://localhost:8081...")
        try:
            await page.goto("http://localhost:8081", timeout=30000)
            await asyncio.sleep(5)  # Wait for Svelte app to load client-side JavaScript
            
            print("Taking screenshot...")
            await page.screenshot(path="d:/Works/openwebui_clone/screenshot.png")
            print("Screenshot saved successfully to d:/Works/openwebui_clone/screenshot.png")
        except Exception as e:
            print(f"Error occurred: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
