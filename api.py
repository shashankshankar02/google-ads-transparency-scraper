from fastapi import FastAPI, HTTPException, Request, Depends
from typing import List, Optional
import uvicorn
from pydantic import BaseModel
import asyncio
from main import process_domain, setup_browser
from apify_client import ApifyClient
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
import time

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
request_history = {}

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
    advertiser_info: dict

def check_rate_limit(api_key: str):
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

@app.post("/scrape", response_model=List[Creative])
async def scrape_domains(
    request: ScrapeRequest,
    api_key: str = Depends(API_KEY_HEADER)
):
    try:
        # Check rate limit
        check_rate_limit(api_key)
        
        # Initialize Apify client
        apify_client = ApifyClient(token=os.environ.get('APIFY_TOKEN'))
        dataset_client = apify_client.dataset(os.environ.get('APIFY_DEFAULT_DATASET_ID'))
        
        results = []
        driver = await setup_browser()
        
        try:
            for domain in request.domains:
                domain_results = await process_domain(domain, driver, dataset_client)
                results.extend(domain_results)
            return results
        finally:
            if driver:
                await driver.close()
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root(api_key: str = Depends(API_KEY_HEADER)):
    check_rate_limit(api_key)
    return {
        "name": "Google Ads Transparency Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/scrape": "POST - Scrape ads data for given domains",
            "/": "GET - This documentation"
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 