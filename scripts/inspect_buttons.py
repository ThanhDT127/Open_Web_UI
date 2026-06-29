import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        await page.goto("http://localhost:8081")
        await asyncio.sleep(2)
        await page.fill('input[type="email"]', "admin@example.com")
        await page.fill('input[type="password"]', "admin")
        await page.click('button[type="submit"]')
        await asyncio.sleep(5)
        
        buttons = await page.query_selector_all('button')
        print(f"=== Found {len(buttons)} buttons ===")
        for i, btn in enumerate(buttons):
            id_attr = await btn.get_attribute('id')
            aria_label = await btn.get_attribute('aria-label')
            title = await btn.get_attribute('title')
            class_attr = await btn.get_attribute('class')
            html = await btn.inner_html()
            html_snippet = html.replace('\n', '').replace('\t', '')[:80]
            
            output_str = f"Btn {i}: id={id_attr}, label={aria_label}, title={title}, class={class_attr}, html={html_snippet}"
            # Safe print for CP1252
            print(output_str.encode("ascii", "backslashreplace").decode("ascii"))
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
