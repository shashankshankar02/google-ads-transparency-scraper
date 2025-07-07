from fastapi import FastAPI, HTTPException, Request, Depends
from typing import List, Optional, Dict, Any
import uvicorn
from pydantic import BaseModel
import asyncio
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

app = FastAPI(
    title="Google Ads Transparency Scraper",
    description="API to scrape Google Ads Transparency data for given domains",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting setup
RATE_LIMIT_SECONDS = 60
MAX_REQUESTS = 10  # Requests per minute
request_history: Dict[str, List[float]] = {}

# API key header
API_KEY_HEADER = APIKeyHeader(name="X-RapidAPI-Key")

class ScrapeRequest(BaseModel):
    domains: List[str]
    max_concurrency: Optional[int] = 1

class Creative(BaseModel):
    advertiser_id: str
    creative_id: str
    ads_running: bool
    first_shown: str
    last_shown: str
    regions: List[str]
    languages: List[str]
    platform_types: List[str]
    ad_format_types: List[str]
    advertiser_info: Dict[str, Any]

def check_rate_limit(api_key: str) -> None:
    now = time.time()
    if api_key not in request_history:
        request_history[api_key] = []
    
    # Clean old requests
    request_history[api_key] = [req_time for req_time in request_history[api_key] 
                               if now - req_time < RATE_LIMIT_SECONDS]
    
    if len(request_history[api_key]) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    
    request_history[api_key].append(now)

async def setup_browser() -> webdriver.Remote:
    print("Setting up browser...")
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    
    # Set capabilities through options
    chrome_options.set_capability('browserName', 'chrome')
    chrome_options.set_capability('browserVersion', 'latest')
    chrome_options.set_capability('timeouts', {
        'implicit': 10000,
        'pageLoad': 20000,
        'script': 10000
    })
    
    # Get browserless token from environment variable
    browserless_token = os.getenv('BROWSERLESS_TOKEN')
    if not browserless_token:
        raise ValueError("BROWSERLESS_TOKEN environment variable is required")
    
    print("Connecting to browserless.io...")
    # Configure remote WebDriver to use browserless.io CDP endpoint
    remote_url = f'wss://production-sfo.browserless.io?token={browserless_token}'
    
    try:
        driver = webdriver.Remote(
            command_executor=remote_url,
            options=chrome_options
        )
        print("Browser setup complete!")
        return driver
    except Exception as e:
        print(f"Error setting up browser: {str(e)}")
        raise

async def process_domain(domain: str, driver: webdriver.Remote) -> List[Dict[str, Any]]:
    try:
        print(f"Processing domain: {domain}")
        url = f"https://adstransparency.google.com/advertiser/{domain}?region=anywhere"
        print(f"Navigating to URL: {url}")
        
        driver.set_page_load_timeout(30)  # 30 seconds timeout for page load
        driver.implicitly_wait(10)  # 10 seconds implicit wait
        
        driver.get(url)
        print("Page loaded, waiting for 3 seconds...")
        await asyncio.sleep(3)  # Allow page to load
        
        print("Returning test data for now")
        return [{
            "advertiser_id": domain,
            "creative_id": "test",
            "ads_running": True,
            "first_shown": "2024-01-01",
            "last_shown": "2024-01-31",
            "regions": ["US"],
            "languages": ["en"],
            "platform_types": ["web"],
            "ad_format_types": ["display"],
            "advertiser_info": {"name": "Test Advertiser"}
        }]
    except Exception as e:
        print(f"Error processing domain {domain}: {str(e)}")
        return []

@app.post("/scrape", response_model=List[Creative])
async def scrape_domains(
    request: ScrapeRequest,
    api_key: str = Depends(API_KEY_HEADER)
) -> List[Dict[str, Any]]:
    try:
        # Check rate limit
        check_rate_limit(api_key)
        
        results = []
        driver = await setup_browser()
        
        try:
            for domain in request.domains:
                domain_results = await process_domain(domain, driver)
                if isinstance(domain_results, list):
                    results.extend(domain_results)
            return results
        finally:
            if driver:
                driver.quit()
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root(api_key: str = Depends(API_KEY_HEADER)) -> Dict[str, Any]:
    check_rate_limit(api_key)
    return {
        "name": "Google Ads Transparency Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/scrape": "POST - Scrape ads data for given domains",
            "/": "GET - This documentation"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 