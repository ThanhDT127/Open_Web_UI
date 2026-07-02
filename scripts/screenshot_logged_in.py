import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        print("Navigating to http://localhost:8081...")
        await page.goto("http://localhost:8081", timeout=30000)
        await asyncio.sleep(3)
        
        print("Logging in with test admin...")
        try:
            # Locate fields and fill
            await page.fill('input[type="email"]', "admin@example.com")
            await page.fill('input[type="password"]', "admin")
            
            # Click submit button
            await page.click('button[type="submit"]')
            print("Login submitted. Waiting for redirection...")
            await asyncio.sleep(5)
            
            # Save dashboard screenshot
            print("Taking dashboard screenshot...")
            await page.screenshot(path="d:/Works/openwebui_clone/screenshot_dashboard.png")
            print("Dashboard screenshot saved to d:/Works/openwebui_clone/screenshot_dashboard.png")
            
            # Let's try to find and click the Chat Controls button (often a button in the header)
            # In OpenWebUI, it's typically a button with controls/settings icon or selector
            # Let's search for buttons on the page to find the controls selector
            buttons = await page.query_selector_all('button')
            print(f"Found {len(buttons)} buttons on the page.")
            
            # Click the Controls toggle button (often has aria-label="Controls" or similar)
            # We will try clicking the top-right button which is typically Chat Controls
            # Playwright can select using CSS selectors like button[id="chat-controls-button"] or by text/icon
            controls_clicked = False
            for btn in buttons:
                aria_label = await btn.get_attribute('aria-label')
                title = await btn.get_attribute('title')
                id_attr = await btn.get_attribute('id')
                html = await btn.inner_html()
                
                # Check for "Controls", "Chat Controls", or slider SVG path
                if aria_label and "controls" in aria_label.lower():
                    await btn.click()
                    print(f"Clicked button by aria-label: {aria_label}")
                    controls_clicked = True
                    break
                elif title and "controls" in title.lower():
                    await btn.click()
                    print(f"Clicked button by title: {title}")
                    controls_clicked = True
                    break
                elif id_attr and "controls" in id_attr.lower():
                    await btn.click()
                    print(f"Clicked button by id: {id_attr}")
                    controls_clicked = True
                    break
                    
            if not controls_clicked:
                # If we couldn't find by attribute, try to click a generic top-right header button or search for it
                print("Could not identify controls button via attributes. Trying a click based on SVG or position...")
                # In OpenWebUI v0.3.x, the Chat Controls button is in the top right header, let's look for header buttons
                header_buttons = await page.query_selector_all('header button')
                if header_buttons:
                    # Usually the controls button is the last or second to last button in header
                    await header_buttons[-1].click()
                    print("Clicked the last button in the header as fallback.")
                    controls_clicked = True
            
            if controls_clicked:
                await asyncio.sleep(2)
                print("Taking controls sidebar screenshot...")
                await page.screenshot(path="d:/Works/openwebui_clone/screenshot_controls.png")
                print("Controls sidebar screenshot saved to d:/Works/openwebui_clone/screenshot_controls.png")
            
        except Exception as e:
            print(f"Error during execution: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
