import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import logging

# Set up logging
logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self, download_path: str):
        self.download_path = download_path
        os.makedirs(download_path, exist_ok=True)
        
    async def download_videos(self, url: str, skip_basenames=None):
        if skip_basenames is None:
            skip_basenames = set()

        async with async_playwright() as p:
            # Launch browser with specific arguments to improve compatibility
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-sandbox',
                ]
            )
            context = await browser.new_context(
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080}  # Set large viewport
            )
            page = await context.new_page()

            try:
                logger.info(f"🌐 Navigating to URL: {url}")
                await page.goto(url, timeout=120000)  # Increased timeout
                logger.info("🔍 Waiting for file list to load...")
                await page.wait_for_selector('.ReactVirtualized__Table__row', timeout=60000)  # Increased timeout
            except PlaywrightTimeout:
                logger.error("⌛ Timeout waiting for file list to load.")
                await browser.close()
                return

            rows = await page.query_selector_all('.ReactVirtualized__Table__row:not(.ReactVirtualized__Table__headerRow)')
            logger.info(f"📦 Found {len(rows)} items to process.")

            for i, row in enumerate(rows):
                try:
                    logger.debug(f"Processing row {i+1}/{len(rows)}")
                    await row.scroll_into_view_if_needed()
                    
                    # CRUCIAL: Hover over the row to make buttons visible
                    await row.hover()
                    await asyncio.sleep(1.5)  # Increased delay for UI to respond
                    
                    name_element = await row.query_selector('.item-name')
                    if not name_element:
                        logger.warning("Name element not found in row")
                        continue
                        
                    file_name = (await name_element.inner_text()).strip()
                    file_ext = os.path.splitext(file_name)[1].lower()
                    base_name = os.path.splitext(file_name)[0]

                    # Skip folders, non-MP4 files, and already downloaded files
                    folder_icon = await row.query_selector('.icon-folder')
                    if folder_icon or file_ext != '.mp4' or base_name in skip_basenames:
                        logger.info(f"⏩ Skipping: {file_name}")
                        continue

                    logger.info(f"\n🔄 Processing {file_name} ({i+1}/{len(rows)})")

                    # Click more options button
                    more_options_btn = await row.query_selector('button.more-options-btn')
                    if not more_options_btn:
                        logger.warning(f"❌ More Options button not found for {file_name}")
                        continue

                    # Wait for button to be actionable
                    await more_options_btn.wait_for_element_state("stable", timeout=15000)
                    await more_options_btn.click()
                    
                    # Wait for menu to appear
                    await page.wait_for_selector('[role="menu"]', state='visible', timeout=20000)

                    # Download file
                    download_btn = await page.query_selector('[role="menuitem"]:has-text("Download")')
                    if not download_btn:
                        logger.warning(f"❌ Download button not found for {file_name}")
                        await page.keyboard.press('Escape')
                        continue

                    logger.info(f"⬇️ Downloading {file_name}...")
                    async with page.expect_download(timeout=120000) as download_info:  # 2 min timeout
                        await download_btn.click()
                    download = await download_info.value

                    # Save video
                    dest_path = os.path.join(self.download_path, file_name)
                    await download.save_as(dest_path)
                    logger.info(f"🎥 Saved video: {dest_path}")
                    yield dest_path

                    await page.keyboard.press('Escape')
                    await asyncio.sleep(2)  # Increased delay between downloads

                except Exception as e:
                    logger.error(f"⚠️ Error processing item: {str(e)}")
                    try:
                        await page.keyboard.press('Escape')
                    except:
                        pass
                    await asyncio.sleep(2)

            await browser.close()