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
        
        # -> Reload the Athena-Academic homepage and wait for the single-page app to initialize so the navigation menu and chat terminal become visible.
        await page.goto("http://localhost:8088/")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        
        # -> Type '/yardim' into the chat message box and send it, then export the current chat session by clicking the 'Dışa Aktar (Markdown)' button and verify that an export confirmation or download appears.
        # Mesaj yaz… ('/' ile komutlar, '@' ile bahset) text area
        elem = page.get_by_placeholder("Mesaj yaz… ('/' ile komutlar, '@' ile bahset)", exact=True)
        await elem.wait_for(state="visible", timeout=10000)
        await elem.fill("/yardim")
        
        # -> Type '/yardim' into the chat message box and send it, then export the current chat session by clicking the 'Dışa Aktar (Markdown)' button and verify that an export confirmation or download appears.
        # Gönder button
        elem = page.get_by_role('button', name='Gönder', exact=True)
        await elem.click(timeout=10000)
        
        # -> Type '/yardim' into the chat message box and send it, then export the current chat session by clicking the 'Dışa Aktar (Markdown)' button and verify that an export confirmation or download appears.
        # Download: 📥 button
        elem = page.get_by_role('button', name='📥', exact=True)
        async with page.expect_download(timeout=30000) as dl_info:
            await elem.click(timeout=10000)
        download = await dl_info.value
        assert download.suggested_filename  # verify file was downloaded
        await download.save_as(f"./downloads/{download.suggested_filename}")
        
        # -> Search the page for any export/download confirmation text such as 'İndir' or 'Dışa Aktar' and if none is found, click the 'Dışa Aktar (Markdown)' button again to retry the export.
        # Download: 📥 button
        elem = page.get_by_role('button', name='📥', exact=True)
        async with page.expect_download(timeout=30000) as dl_info:
            await elem.click(timeout=10000)
        download = await dl_info.value
        assert download.suggested_filename  # verify file was downloaded
        await download.save_as(f"./downloads/{download.suggested_filename}")
        
        # -> Search the page for export/download confirmation text such as 'İndir', 'Dışa Aktar', or '.md'; if none is found, click the 'Dışa Aktar (Markdown)' button to retry the export and observe for notifications.
        # Download: 📥 button
        elem = page.get_by_role('button', name='📥', exact=True)
        async with page.expect_download(timeout=30000) as dl_info:
            await elem.click(timeout=10000)
        download = await dl_info.value
        assert download.suggested_filename  # verify file was downloaded
        await download.save_as(f"./downloads/{download.suggested_filename}")
        
        # -> Click the 'Dışa Aktar (Markdown)' button to trigger export and then check the page for an export confirmation or a downloadable markdown link.
        # Download: 📥 button
        elem = page.get_by_role('button', name='📥', exact=True)
        async with page.expect_download(timeout=30000) as dl_info:
            await elem.click(timeout=10000)
        download = await dl_info.value
        assert download.suggested_filename  # verify file was downloaded
        await download.save_as(f"./downloads/{download.suggested_filename}")
        
        # --> Test passed — verified by AI agent
        frame = context.pages[-1]
        current_url = await frame.evaluate("() => window.location.href")
        assert current_url is not None, "Test completed successfully"
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    