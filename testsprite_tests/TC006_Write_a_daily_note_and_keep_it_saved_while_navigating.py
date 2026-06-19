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
        
        # -> Type a short daily note into the 'GÜNÜM NOTU' editor and confirm the auto-save indicator shows 'Kaydedildi'.
        # Görevler link
        elem = page.get_by_role('link', name='Görevler', exact=True)
        await elem.click(timeout=10000)
        
        # -> Click the 'Günüm' navigation link to return to the Dashboard so the daily note editor and the auto-save indicator can be inspected.
        # Günüm link
        elem = page.get_by_role('link', name='Günüm', exact=True)
        await elem.click(timeout=10000)
        
        # --> Assertions to verify final state
        
        # --> Verify the auto-save indicator shows that the note is saved
        # Assert: The auto-save indicator shows 'Kaydedildi'.
        await expect(page.locator("xpath=/html/body/div[1]/div/main/div/div[1]/div[2]/div[1]/div[1]/span[2]").nth(0)).to_have_text("Kaydedildi", timeout=15000), "The auto-save indicator shows 'Kaydedildi'."
        
        # --> Verify the daily note content is still present
        # Assert: The daily note content 'Günlük not testi — 2026-06-19' is present on the dashboard.
        await expect(page.locator("xpath=/html/body/div[1]/div/main/div/div[1]/div[2]/div[1]/div[2]/div/div/div/p").nth(0)).to_have_text("G\u00fcnl\u00fck not testi \u2014 2026-06-19", timeout=15000), "The daily note content 'G\u00fcnl\u00fck not testi \u2014 2026-06-19' is present on the dashboard."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    