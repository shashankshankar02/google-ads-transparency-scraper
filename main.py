"""
Google Ads Transparency Scraper

This module scrapes Google's Ad Transparency Center to check if domains are running ads
and extracts ad creatives with OCR text extraction.
"""

import asyncio
import logging
from datetime import datetime, timezone
from functools import wraps
from io import BytesIO
from typing import Dict, List, Optional, Tuple, cast, Callable, Any
import os

import aiohttp
from PIL import Image
import pytesseract
import tenacity
from apify_client import ApifyClient
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chromedriver_autoinstaller

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry_on_exception(*exception_types, max_tries: int = 3):
    """Decorator that retries a function on specified exceptions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return tenacity.retry(
                stop=tenacity.stop_after_attempt(max_tries),
                retry=tenacity.retry_if_exception_type(exception_types),
                wait=tenacity.wait_exponential(multiplier=1, min=4, max=10)
            )(func)(*args, **kwargs)
        return wrapper
    return decorator

class Stats:
    """Tracks and reports scraping statistics."""
    def __init__(self):
        self.domains_processed = 0
        self.domains_with_ads = 0
        self.total_creatives = 0
        self.failed_domains = 0
        self.start_time = datetime.now()

    def log_progress(self, total_domains: int) -> None:
        """Logs current progress and statistics."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        success_rate = self.domains_processed - self.failed_domains
        success_rate = success_rate / max(self.domains_processed, 1)
        logger.info(
            "Progress: %d/%d domains processed | Success rate: %.1f%% | "
            "Domains with ads: %d | Total creatives: %d | Time elapsed: %.1fs",
            self.domains_processed, total_domains, success_rate * 100,
            self.domains_with_ads, self.total_creatives, elapsed
        )

class AdScraper:
    """Scrapes Google's Ad Transparency Center for ad information."""
    def __init__(self, client: ApifyClient, max_retries: int = 3, timeout: int = 30):
        """Initialize the scraper with configuration."""
        self.client = client
        self.max_retries = max_retries
        self.timeout = timeout
        self.stats = Stats()
        self.session: Optional[aiohttp.ClientSession] = None
        self.driver: Optional[webdriver.Chrome] = None
        self.dataset_client = None

    async def init_session(self) -> None:
        """Initialize the aiohttp session."""
        self.session = aiohttp.ClientSession()

    async def close_session(self) -> None:
        """Close the aiohttp session if it exists."""
        if self.session:
            await self.session.close()

    def init_driver(self) -> None:
        """Initialize the Chrome WebDriver."""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        chromedriver_autoinstaller.install()
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.timeout)

    def close_driver(self) -> None:
        """Close the Chrome WebDriver if it exists."""
        if self.driver:
            try:
                self.driver.quit()
            except WebDriverException as e:
                logger.warning("Error closing driver: %s", e)

    def _process_video_creative(self, card) -> Optional[Dict[str, str]]:
        """Process a video creative from an ad card."""
        try:
            iframe = card.find_element(By.TAG_NAME, 'iframe')
            video_url = iframe.get_attribute('src')
            if video_url:
                return {'type': 'video', 'url': video_url}
        except NoSuchElementException:
            pass
        return None

    def _process_image_creative(self, card) -> Optional[Dict[str, str]]:
        """Process an image creative from an ad card."""
        try:
            img_url = card.find_element(By.TAG_NAME, 'img').get_attribute('src')
            if not img_url:
                return None

            # Check for YouTube thumbnail
            if 'i.ytimg.com/vi/' in img_url:
                parts = img_url.split('/')
                if 'vi' in parts:
                    video_id_index = parts.index('vi') + 1
                    if video_id_index < len(parts):
                        video_id = parts[video_id_index]
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        return {'type': 'video', 'url': video_url}

            return {'type': 'image', 'url': img_url}
        except NoSuchElementException:
            pass
        return None

    @retry_on_exception(TimeoutException, WebDriverException)
    def extract_creatives_info(self) -> List[Dict[str, str]]:
        """Extract creative information from the current page."""
        if not self.driver:
            logger.error("Driver not initialized")
            return []

        creatives = []
        try:
            driver = cast(webdriver.Chrome, self.driver)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//creative-preview'))
            )

            ad_cards = driver.find_elements(By.XPATH, '//creative-preview')
            for card in ad_cards:
                try:
                    # Try video first, then image
                    creative = (
                        self._process_video_creative(card) or
                        self._process_image_creative(card)
                    )
                    if creative:
                        creatives.append(creative)
                except WebDriverException as e:
                    logger.warning("Error processing creative: %s", e)

        except WebDriverException as e:
            logger.error("Error extracting creatives: %s", e)

        return creatives

    def clean_domain(self, domain: str) -> str:
        """Clean a domain by removing protocol and www prefix."""
        return domain.replace('http://', '').replace('https://', '').replace('www.', '').strip('/')

    @retry_on_exception(TimeoutException, WebDriverException)
    async def check_ads_transparency(self, domain: str) -> Tuple[str, List[Dict[str, str]]]:
        """Check if a domain is running ads and extract creative information."""
        if not self.driver:
            logger.error("Driver not initialized")
            return "Error", []

        cleaned_domain = self.clean_domain(domain)
        base_url = "https://adstransparency.google.com/"
        params = f"?region=US&domain={cleaned_domain}&preset-date=Last+30+days"
        url = base_url + params

        try:
            driver = cast(webdriver.Chrome, self.driver)
            driver.get(url)
            WebDriverWait(driver, 10).until(
                lambda d: "No ads found" in d.page_source or "ads" in d.page_source.lower()
            )

            if "No ads found" in driver.page_source:
                return "No", []
            if "ads" in driver.page_source.lower():
                creatives = self.extract_creatives_info()
                return "Yes", creatives
            return "Unknown", []

        except WebDriverException as e:
            logger.error("Error checking ads transparency for %s: %s", domain, e)
            raise

    async def extract_text_from_image(self, image_url: str) -> str:
        """Extract text from an image using OCR."""
        if not self.session:
            logger.error("Session not initialized")
            return ''

        try:
            async with self.session.get(image_url, timeout=10) as response:
                if response.status != 200:
                    return ''

                image_data = await response.read()
                img = Image.open(BytesIO(image_data))
                text = pytesseract.image_to_string(img)
                return text.strip() if text else ''

        except (aiohttp.ClientError, IOError) as e:
            logger.warning("Error extracting text from image %s: %s", image_url, e)
            return ''

    async def process_domain(self, domain: str) -> None:
        """Process a single domain and store results in the dataset."""
        try:
            logger.info("Processing %s...", domain)
            ads_running, creatives = await self.check_ads_transparency(domain)

            # Update statistics
            self.stats.domains_processed += 1
            if ads_running == "Yes":
                self.stats.domains_with_ads += 1
                self.stats.total_creatives += len(creatives)

            # Extract text from creatives concurrently
            ad_texts = []
            if creatives:
                text_tasks = [
                    self.extract_text_from_image(creative['url'])
                    for creative in creatives
                    if creative['type'] == 'image'
                ]
                if text_tasks:
                    ad_texts = await asyncio.gather(*text_tasks)

            # Prepare the result
            result = {
                'domain': domain,
                'ads_running': ads_running == "Yes",  # Convert to boolean
                'creatives': creatives,
                'ad_texts': ad_texts,
                'timestamp': datetime.now(timezone.utc).isoformat()  # Use timezone-aware UTC time
            }

            # Push to dataset using the default dataset
            dataset_client = self.client.dataset(os.environ['APIFY_DEFAULT_DATASET_ID'])
            dataset_client.push_items([result])

        except Exception as e:
            logger.error("Error processing domain %s: %s", domain, e)
            self.stats.failed_domains += 1

async def process_with_semaphore(semaphore: asyncio.Semaphore, 
                               func: Callable, 
                               *args: Any, 
                               **kwargs: Any) -> Any:
    """Process a function with a semaphore for concurrency control."""
    async with semaphore:
        return await func(*args, **kwargs)

async def main() -> None:
    """Main entry point for the scraper."""
    # Initialize the ApifyClient
    apify_client = ApifyClient(os.environ['APIFY_TOKEN'])

    # Get input from the default key-value store
    key_value_store = apify_client.key_value_store(os.environ['APIFY_DEFAULT_KEY_VALUE_STORE_ID'])
    actor_input = key_value_store.get_record('INPUT') or {}
    input_data = actor_input.get('value', {})
    domains = input_data.get('domains', ['www.drinkmoment.com'])
    max_concurrency = int(input_data.get('maxConcurrency', 1))

    # Initialize scraper
    scraper = AdScraper(apify_client)
    await scraper.init_session()
    scraper.init_driver()

    try:
        # Create tasks for each domain with concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)
        tasks = [
            process_with_semaphore(semaphore, scraper.process_domain, domain)
            for domain in domains
        ]

        # Process domains concurrently
        await asyncio.gather(*tasks)

        # Log final statistics
        scraper.stats.log_progress(len(domains))

    finally:
        # Cleanup
        await scraper.close_session()
        scraper.close_driver()

if __name__ == "__main__":
    asyncio.run(main()) 