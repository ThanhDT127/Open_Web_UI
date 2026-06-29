import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        print("Navigating and logging in...")
        await page.goto("http://localhost:8081")
        await asyncio.sleep(2)
        await page.fill('input[type="email"]', "admin@example.com")
        await page.fill('input[type="password"]', "admin")
        await page.click('button[type="submit"]')
        await asyncio.sleep(5)
        
        # Cách 1: Click nút Controls ở góc trên bên phải
        print("Clicking Controls button...")
        try:
            await page.click('button[aria-label="Controls"]')
            await asyncio.sleep(2)
            await page.screenshot(path="d:/Works/openwebui_clone/screenshot_controls.png")
            print("Controls screenshot saved successfully.")
            
            # Đóng Controls sidebar để chuẩn bị chụp menu tiếp theo
            await page.click('button[aria-label="Controls"]')
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error clicking Controls: {str(e)}")
            
        # Cách 2: Click nút Integrations (+) ở dưới thanh nhập liệu
        print("Clicking Integrations button...")
        try:
            await page.click('button#integration-menu-button')
            await asyncio.sleep(2)
            await page.screenshot(path="d:/Works/openwebui_clone/screenshot_integrations.png")
            print("Integrations screenshot saved successfully.")
        except Exception as e:
            print(f"Error clicking Integrations: {str(e)}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
