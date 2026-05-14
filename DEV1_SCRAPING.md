# Developer 1 — Scraping & Matching Engine

**Role:** Scraper Developer
**Focus:** Data acquisition pipeline (scrapers + product matcher)
**Dependencies:** Needs DB models from Dev 2 before writing to the database (can develop against interfaces/mocks first)

---

## Context

You are responsible for the entire data ingestion layer: scraping product data from 3 perfume retailers (Primor, Nocibe, Sephora) and resolving scraped items into canonical products. Your code lives in `backend/app/scrapers/` and `backend/app/matcher/`.

The system scrapes product data (name, brand, image, price, stock, URL) from each site, normalizes it into a common `RawListing` Pydantic model, then passes it through a matcher that resolves each listing to a unique `canonical_product` in PostgreSQL.

---

## Key Files You Own

```
backend/app/scrapers/
├── base.py         ← BaseScraper abstract class + RawListing model
├── primor.py       ← Primor scraper (requests + regex)
├── sephora.py      ← Sephora scraper (Playwright + XHR intercept)
├── nocibe.py       ← Nocibe scraper (requests + BeautifulSoup + JSON-LD)
└── runner.py       ← Orchestrator: calls scrapers → matcher → DB writes

backend/app/matcher/
├── normalize.py    ← Text normalization, size extraction, brand canonicalization
└── resolver.py     ← Deterministic key match → fuzzy fallback → review queue
```

---

## TO-DO List

### Phase 2 — Scraper Framework (Priority: HIGH) ✅

- [x] **Define `BaseScraper` abstract class** in `scrapers/base.py`
  - Methods: `list_category_urls() -> list[str]`, `scrape_category(url) -> Iterable[RawListing]`, `scrape_product(listing_url) -> RawListing`
  - Property: `site: str`
- [x] **Define `RawListing` Pydantic model** in `scrapers/base.py`
  - Fields: `site_product_id`, `url`, `name`, `brand`, `image_url`, `price` (Decimal), `currency` (default "EUR"), `in_stock` (bool), `size_ml` (Optional[int]), `raw_payload` (dict for debug)
- [x] **Implement request utilities** in `scrapers/utils.py`
  - Rate limiter: random delay 0.5–1.5s between requests
  - Realistic User-Agent string (from env: `SCRAPER_USER_AGENT`)
  - Retry with exponential backoff on 5xx / 429 (max 3 attempts)
  - `robots.txt` check at scraper startup (fail loudly if disallowed)
- [x] **Implement `scrapers/runner.py`**
  - Iterate each scraper's `list_category_urls()`
  - Collect `RawListing` items per category
  - Push each through the matcher (call `resolver.resolve(raw_listing)`)
  - Upsert `listing` record + append `price_snapshot`
  - Log counts: added / updated / errored per site
  - Record job status in `scrape_job` table (coordinate schema with Dev 2)
  - Write failures to `scrape_error` table
  - `--dry-run` CLI flag for testing without DB

### Phase 3 — Site Scrapers (Priority: HIGH) ✅

- [x] **Primor** (`scrapers/primor.py`)
  - Regex-extract `"skus":[...]` from category pages
  - Fetch structured data from `https://rcm.frizbit.com/feed/9aF3/{sku}`
  - Yields `RawListing` objects — no pandas/Excel
  - Pure `requests` + regex, no JS rendering needed
- [x] **Nocibe** (`scrapers/nocibe.py`)
  - Category pages: `requests` + `BeautifulSoup` with `?page=N` pagination
  - Product detail pages: JSON-LD parser + HTML fallback
  - Extracts: name, brand, price, image, stock status, size
- [x] **Sephora** (`scrapers/sephora.py`)
  - Playwright (headless Chromium), async implementation
  - XHR intercept on `/api/catalog/...` endpoint
  - JSON-LD fallback on individual PDPs
  - Risk documented: Akamai/Imperva blocking → Plan B: lower frequency or drop from v1
- [x] **Smoke tests for each scraper** (`tests/scrapers/`) — 73 tests, all passing
  - Mocked HTTP — no real network calls
  - Assert all required `RawListing` fields are populated
  - Assert prices are valid Decimals > 0
  - Assert URLs are well-formed

### Phase 4 — Matcher (Priority: HIGH) ✅

- [x] **Build `matcher/normalize.py`**
  - Lowercase + strip accents (`unicodedata` NFD)
  - Remove punctuation, collapse spaces
  - Extract `size_ml` via regex `(\d+)\s?ml`
  - Strip size token from working name
  - Brand canonicalization table (30+ brands: `"christian dior" → "dior"`, `"yves saint laurent" → "ysl"`, etc.)
- [x] **Build `matcher/resolver.py`**
  - Step 1: Deterministic match on `(brand_normalized, name_normalized, size_ml)`
  - Step 2: Fuzzy search within same `brand_normalized` using `rapidfuzz.token_sort_ratio`
    - Score ≥ 92 → auto-merge
    - Score 80–91 → insert into `match_review_queue`
    - Score < 80 → create new `canonical_product`
  - Dry-run mode (no DB) returns deterministic synthetic UUID via `uuid5`
- [ ] **Validation against labeled sample** ← NEXT
  - Create/obtain a hand-labeled sample of ~100 products matched across 3 sites
  - Run matcher against the sample
  - Target: ≥ 95% precision
  - Document false positives and false negatives

---

## Technical Notes

- **Python dependencies you'll need:** `requests`, `beautifulsoup4`, `playwright`, `rapidfuzz`, `pydantic`, `lxml`
- **Env vars you consume:** `SCRAPER_USER_AGENT`, `SCRAPER_REQUEST_DELAY_MS`, `PLAYWRIGHT_HEADLESS`
- **Coordinate with Dev 2** on: SQLAlchemy model interfaces (you write to `listing`, `price_snapshot`, `scrape_job`, `scrape_error`, `match_review_queue`)
- **Coordinate with Dev 3** on: nothing directly — your output is DB records that Dev 2's API exposes
- **Image handling:** Store source image URLs only (no binary download). Frontend handles display via Next.js `<Image>`.

---

## Definition of Done

1. All 3 scrapers produce valid `RawListing` objects for at least 20 products each
2. Runner orchestrates full scrape pass and writes to DB without errors
3. Matcher resolves 95%+ of a labeled sample correctly
4. Rate limiting, retry logic, and robots.txt checks are in place
5. Failures are logged to `scrape_error` table with actionable context
