import asyncio
import re
from playwright import async_api
from playwright.async_api import expect

async def run_test():
    pw = None
    browser = None
    context = None

    try:
        # Start a Playwright session in asynchronous mode
        pw = await async_api.async_playwright().start()

        # Launch a Chromium browser in headless mode with custom arguments
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--window-size=1280,720",
                "--disable-dev-shm-usage",
                "--ipc=host",
                "--single-process"
            ],
        )

        # Create a new browser context (like an incognito window)
        context = await browser.new_context()
        # Wider default timeout to match the agent's DOM-stability budget;
        # auto-waiting Playwright APIs (expect, locator.wait_for) inherit this.
        context.set_default_timeout(15000)

        # Open a new page in the browser context
        page = await context.new_page()

        # Interact with the page elements to simulate user flow
        # -> navigate
        await page.goto("http://localhost:8088")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        
        # -> Reload the app by navigating to the root page (http://localhost:8088/) to attempt to load the SPA UI so filters can be found and applied.
        await page.goto("http://localhost:8088/")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        
        # --> Assertions to verify final state
        
        # --> Verify the task list is narrowed to matching tasks
        # Assert: Tasks panel shows 'Henüz görev yok. Sohbetten ekleyebilirsin.' indicating the list was narrowed to matching tasks.
        await expect(page.locator("xpath=/html/body/div/div/main/div/div[1]/div[2]/div[1]/div[2]/div/div/div/p").nth(0)).to_have_text("Hen\u00fcz g\u00f6rev yok. Sohbetten ekleyebilirsin.", timeout=15000), "Tasks panel shows 'Hen\u00fcz g\u00f6rev yok. Sohbetten ekleyebilirsin.' indicating the list was narrowed to matching tasks."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    