# Google Ads Transparency Scraper

This [Apify](https://apify.com) actor scrapes Google's Ad Transparency Center to check if domains are running ads and extracts ad creatives with OCR text extraction.

## Features

- Checks if domains are running Google Ads
- Extracts ad creatives (images and videos)
- Performs OCR on image ads to extract text
- Handles YouTube video thumbnails and links
- Provides detailed statistics and progress tracking
- Configurable concurrency for faster processing
- Robust error handling and retries

## Input

The actor accepts the following input parameters:

```jsonc
{
    "domains": [
        "example.com",
        "example.org"
    ],
    "maxConcurrency": 1 // Optional, default: 1, max: 10
}
```

- `domains`: Array of domains to check for ads (required)
- `maxConcurrency`: Maximum number of domains to process concurrently (optional)

## Output

The actor saves results to its default dataset. Each item contains:

```jsonc
{
    "domain": "example.com",
    "ads_running": true,
    "creatives": [
        {
            "type": "image",
            "url": "https://..."
        },
        {
            "type": "video",
            "url": "https://..."
        }
    ],
    "ad_texts": [
        "Extracted text from image 1",
        "Extracted text from image 2"
    ],
    "error": null, // Error message if scraping failed
    "timestamp": "2024-03-21T12:34:56.789Z"
}
```

## Usage

1. Create a new task for the actor
2. Provide input:
   ```json
   {
       "domains": ["example.com"],
       "maxConcurrency": 1
   }
   ```
3. Run the task
4. Get results from the dataset

## Performance and Limits

- Memory: 4096 MB
- Timeout: 4 hours
- Concurrency: 1-10 domains in parallel
- Rate limiting: 2 second delay between requests

## Dependencies

- Python 3.9
- Chrome browser
- Tesseract OCR
- Key Python packages:
  - selenium
  - pytesseract
  - aiohttp
  - Pillow
  - apify-client

## Error Handling

The actor implements robust error handling:

- Automatic retries for transient errors
- Graceful degradation for OCR failures
- Detailed error reporting in output
- Progress tracking and statistics

## Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install system dependencies:
   ```bash
   apt-get install tesseract-ocr
   ```

3. Run locally:
   ```bash
   python main.py
   ```

## License

Apache 2.0 