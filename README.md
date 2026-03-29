# Deal Scraper API v2.0

Real-time deal scraper across **Amazon.in**, **Flipkart**, and **Myntra** — returns structured product-level data with filtering and pagination.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file (optional, for proxy):
```
PROXY_HOST=...
PROXY_PORT=...
PROXY_USER=...
PROXY_PASS=...
```

## Run

```bash
uvicorn main:app --reload --port 8000
```

## API Endpoints

### GET /deals/best-deals

Fetch deals across all platforms with optional filters.

**Query Parameters:**

| Param        | Type   | Default | Description                                 |
|--------------|--------|---------|---------------------------------------------|
| search       | string | —       | Product name or brand keyword                |
| platforms    | string | —       | Comma-separated: `Amazon,Flipkart,Myntra`    |
| categories   | string | —       | Comma-separated: `Electronics,Fashion`       |
| brands       | string | —       | Comma-separated: `Samsung,Nike`              |
| minDiscount  | number | —       | Minimum discount % (e.g. 40, 50, 75)        |
| minRating    | number | —       | Minimum star rating (e.g. 3, 4)             |
| noCostEMI    | string | —       | `"true"` to filter EMI-eligible only         |
| page         | number | 1       | Page number                                  |
| limit        | number | 20      | Items per page (max 100)                     |

**Example:**
```
GET /deals/best-deals?platforms=Amazon,Flipkart&minDiscount=40&page=1&limit=10
```

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "title": "boAt Rockerz 450 Bluetooth Headphone",
      "brand": "boAt",
      "discountType": "57% off",
      "discountPercent": 57,
      "price": 999.0,
      "originalPrice": 2499.0,
      "category": "Electronics",
      "images": ["https://..."],
      "platformName": "Amazon",
      "platformLink": "https://amazon.in/...",
      "rating": 4.2,
      "ratingCount": 12450,
      "noCostEMI": true,
      "affiliateUrl": "https://amazon.in/...",
      "createdAt": "2026-03-27T09:05:00.000Z",
      "updatedAt": "2026-03-27T09:05:00.000Z"
    }
  ],
  "total": 45,
  "page": 1,
  "limit": 10
}
```

### GET /deals/top-categories

Returns the top 8 product categories from current deals.

```json
{ "categories": ["Electronics", "Fashion", "Footwear", "Beauty", ...] }
```

### GET /deals/top-brands

Returns the top 8 brands from current deals.

```json
{ "brands": ["Samsung", "Nike", "boAt", "Apple", ...] }
```

## Project Structure

```
├── main.py                  # FastAPI app with /deals/* endpoints
├── models/
│   └── deal.py              # DealItem Pydantic model + helpers
├── scrapers/
│   ├── amazon.py            # Amazon.in scraper (BS4 + requests)
│   ├── flipkart.py          # Flipkart scraper (Playwright)
│   └── myntra.py            # Myntra scraper (internal API)
├── services/
│   └── deal_service.py      # Fetch, filter, paginate, aggregate
├── core/
│   ├── config.py            # Proxy configuration
│   └── http_client.py       # Shared HTTP session factory
└── requirements.txt
```

## Notes

- Scraping is done fresh on every request (no caching).
- Fields like `rating`, `ratingCount`, `noCostEMI`, `category` are best-effort — they may be `null` if the source page doesn't expose them.
- Flipkart requires Playwright (headless Chromium) due to reCAPTCHA.
- A proxy is recommended for production use to avoid IP blocks.
