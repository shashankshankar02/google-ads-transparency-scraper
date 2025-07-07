# Google Ads Transparency Scraper API

A FastAPI-based REST API for scraping Google Ads Transparency data. This API allows you to fetch advertising data for any domain, including information about active ads, advertisers, and creative details.

## Features

- Scrape Google Ads Transparency data for multiple domains
- Get detailed information about ad creatives
- Async processing for better performance
- Rate limiting and error handling
- Comprehensive API documentation

## API Endpoints

### POST /scrape
Scrape ads data for given domains

Request body:
```json
{
    "domains": ["example.com"],
    "max_concurrency": 1
}
```

Response:
```json
[
    {
        "advertiser_id": "string",
        "creative_id": "string",
        "ads_running": boolean,
        "first_shown": "string",
        "last_shown": "string",
        "regions": ["string"],
        "languages": ["string"],
        "platform_types": ["string"],
        "ad_format_types": ["string"],
        "advertiser_info": {}
    }
]
```

### GET /
Get API information and documentation

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export APIFY_TOKEN=your_token_here
export APIFY_DEFAULT_DATASET_ID=your_dataset_id
```

3. Run the API:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

## Usage with RapidAPI

This API is available on RapidAPI marketplace. To use it:

1. Sign up for a RapidAPI account
2. Subscribe to the API
3. Use your API key in the X-RapidAPI-Key header

## Error Handling

The API includes comprehensive error handling:
- 400: Bad Request - Invalid input
- 404: Not Found - Domain not found
- 429: Too Many Requests - Rate limit exceeded
- 500: Internal Server Error - Processing error

## Rate Limits

- Free tier: 100 requests/day
- Pro tier: 1000 requests/day
- Enterprise: Custom limits

## Support

For support, please contact [your contact information] 