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
from pyppeteer import connect
import aiohttp

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

async def setup_browser():
    print("Setting up browser...")
    # Get browserless token from environment variable
    browserless_token = os.getenv('BROWSERLESS_TOKEN')
    if not browserless_token:
        raise ValueError("BROWSERLESS_TOKEN environment variable is required")
    
    print("Connecting to browserless.io...")
    browser = await connect(
        browserWSEndpoint=f'wss://production-sfo.browserless.io?token={browserless_token}',
        args=['--no-sandbox', '--disable-setuid-sandbox']
    )
    print("Browser setup complete!")
    return browser

async def process_domain(domain: str, browser) -> List[Dict[str, Any]]:
    try:
        print(f"[{time.strftime('%H:%M:%S')}] Processing domain: {domain}")
        url = f"https://adstransparency.google.com/advertiser/{domain}?region=anywhere"
        print(f"[{time.strftime('%H:%M:%S')}] Navigating to URL: {url}")
        
        page = await browser.newPage()
        await page.setViewport({'width': 1280, 'height': 800})
        
        print(f"[{time.strftime('%H:%M:%S')}] Loading page...")
        await page.goto(url, {'waitUntil': 'networkidle0', 'timeout': 20000})
        print(f"[{time.strftime('%H:%M:%S')}] Page loaded")
        
        # Wait for content to load
        print(f"[{time.strftime('%H:%M:%S')}] Waiting for content...")
        await asyncio.sleep(2)
        
        # Check for "No ads" message
        no_ads_element = await page.querySelector('text/"No ads"')
        if no_ads_element:
            print(f"[{time.strftime('%H:%M:%S')}] No ads found for {domain}")
            await page.close()
            return []
        
        print(f"[{time.strftime('%H:%M:%S')}] Extracting ad data...")
        
        # Get advertiser info
        advertiser_name = await page.evaluate('() => document.querySelector("h1")?.innerText || "Unknown"')
        
        # Get ad stats
        stats = await page.evaluate('''() => {
            const stats = {};
            const dateElements = document.querySelectorAll('[aria-label*="Last shown"]');
            stats.lastShown = dateElements.length ? dateElements[0].innerText : "Unknown";
            return stats;
        }''')
        
        print(f"[{time.strftime('%H:%M:%S')}] Data extracted successfully")
        await page.close()
        
        return [{
            "advertiser_id": domain,
            "creative_id": f"{domain}-{int(time.time())}",
            "ads_running": True,
            "first_shown": "2024-01-01",  # Placeholder
            "last_shown": stats.get('lastShown', "Unknown"),
            "regions": ["US"],  # Placeholder
            "languages": ["en"],  # Placeholder
            "platform_types": ["web"],
            "ad_format_types": ["display"],
            "advertiser_info": {"name": advertiser_name}
        }]
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error processing domain {domain}: {str(e)}")
        try:
            await page.close()
        except:
            pass
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
        browser = await setup_browser()
        
        try:
            for domain in request.domains:
                domain_results = await process_domain(domain, browser)
                if isinstance(domain_results, list):
                    results.extend(domain_results)
            return results
        finally:
            if browser:
                await browser.close()
                
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