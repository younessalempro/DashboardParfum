# Perfume Price Comparator — Project Context & TO-DO

**Owner:** Youness
**Last updated:** 2026-05-09
**Status:** Planning / pre-implementation

---

## 1. Project objective

Build a system that:

1. **Scrapes** product data (name, brand, image, price, stock, URL) from a fixed set of perfume retailers.
2. **Stores** the data in a PostgreSQL database with timestamped price snapshots.
3. **Matches** the same perfume across sites (so "Dior Sauvage 100 ml" on primor.eu, sephora.fr, and nocibe.fr resolve to a single canonical product).
4. **Exposes** the data via a FastAPI backend.
5. **Displays** a price-comparison web app (Next.js) where the user can browse a perfume and instantly see the price on each site.

This document is the source of truth for scope, architecture, and remaining work. No code yet — that comes after sign-off on this plan.

---

## 2. Scope decisions (locked)

| Decision | Choice | Notes |
|---|---|---|
| Target sites | **primor.eu**, **sephora.fr**, **nocibe.fr** | Add more later via the scraper plugin pattern. |
| Database | **PostgreSQL** | Relational fits price-history + cross-site joins. |
| Backend | **FastAPI** (Python) | Reuses existing scraping code (requests/BS4). |
| Frontend | **Next.js** (React + TypeScript) | App router, server components for product pages. |
| Scrape cadence | **On-demand only** (v1) | Manual trigger via API/CLI. Cron is a later phase. |
| Hosting | TBD (out of scope for v1) | Local Docker Compose first. |

### Non-goals (v1)

- No automatic checkout / cart integration.
- No user accounts, wishlists, or alerts.
- No mobile app.
- No multi-currency support — everything in EUR.
- No historical analytics dashboards (just "current price per site" + raw history table).

---

## 3. Architecture overview

```
┌──────────────────────────────────────────────────────────────────┐
│                       Next.js frontend                          │
│            /products  /products/[id]  /admin/scrape             │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST (JSON)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                       FastAPI backend                           │
│   /api/products   /api/products/{id}   /api/admin/scrape        │
└───┬──────────────────────────┬─────────────────────────────┬────┘
    │ SQLAlchemy               │ trigger                    │
    ▼                          ▼                            ▼
┌─────────────┐   ┌────────────────────────────┐   ┌──────────────┐
│ PostgreSQL  │   │   Scraper orchestrator      │   │   Matcher    │
│ (products,  │◄──│  (primor / sephora / nocibé)│──►│  (canonical  │
│  listings,  │   │  → normalized JSON          │   │   product    │
│  prices)    │   └────────────────────────────┘   │   resolution)│
└─────────────┘                                    └──────────────┘
```

Three logical components:

- **Scrapers** — one Python module per site, each implementing the same `BaseScraper` interface that emits a list of normalized `RawListing` records.
- **Matcher** — given a `RawListing`, finds (or creates) the canonical product it belongs to, using a deterministic key first and fuzzy fallback second.
- **API + DB + frontend** — standard CRUD + read paths, plus a single privileged "trigger scrape" endpoint.

---

## 4. Repository layout (proposed)

```
Parfums/
├── README.md
├── CONTEXT.md                  ← this file
├── docker-compose.yml          ← postgres + api + web for local dev
├── .env.example
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/                ← migrations
│   ├── app/
│   │   ├── main.py             ← FastAPI entry
│   │   ├── config.py
│   │   ├── db.py               ← engine + session
│   │   ├── models/             ← SQLAlchemy ORM
│   │   ├── schemas/            ← Pydantic
│   │   ├── routers/
│   │   │   ├── products.py
│   │   │   └── admin.py
│   │   ├── matcher/
│   │   │   ├── normalize.py
│   │   │   └── resolver.py
│   │   └── scrapers/
│   │       ├── base.py         ← BaseScraper interface
│   │       ├── primor.py
│   │       ├── sephora.py
│   │       ├── nocibe.py
│   │       └── runner.py       ← orchestrates a full scrape pass
│   └── tests/
│
└── web/
    ├── package.json
    ├── next.config.js
    ├── tsconfig.json
    └── src/
        ├── app/
        │   ├── products/
        │   │   ├── page.tsx
        │   │   └── [id]/page.tsx
        │   └── admin/
        │       └── scrape/page.tsx
        ├── components/
        └── lib/api.ts
```

---

## 5. Data model

Three core tables. Snapshot of intent — finalize in migration step.

### `canonical_product`
The deduplicated, "real-world" perfume entity.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK |  |
| `brand` | text | Normalized form (e.g., `dior`). |
| `name` | text | Normalized display name. |
| `size_ml` | int | Extracted from product title. Nullable for non-volumed items. |
| `gender` | enum (`men`, `women`, `unisex`) | Nullable. |
| `image_url` | text | Best image picked across sites. |
| `created_at` | timestamptz | |

**Unique:** `(brand, name, size_ml)`.

### `listing`
A site-specific product page. One canonical product can have 0..N listings (one per site).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `canonical_product_id` | UUID FK → `canonical_product.id` | Nullable while awaiting match review. |
| `site` | enum (`primor`, `sephora`, `nocibe`) | |
| `site_product_id` | text | SKU or site-specific ID. |
| `url` | text | Product page URL. |
| `name_on_site` | text | Raw, un-normalized name. |
| `brand_on_site` | text | |
| `image_url` | text | |
| `last_seen_at` | timestamptz | |

**Unique:** `(site, site_product_id)`.

### `price_snapshot`
Append-only price log. Even with on-demand scraping we keep history.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `listing_id` | UUID FK → `listing.id` | |
| `price` | numeric(10,2) | |
| `currency` | char(3) | `EUR`. |
| `in_stock` | boolean | |
| `scraped_at` | timestamptz | Default `now()`. |

**Index:** `(listing_id, scraped_at desc)` for "latest price per listing" queries.

### Useful view (later, optional)

`v_latest_prices` — for each `listing`, the latest `price_snapshot`. Materialize if read load grows.

---

## 6. Scraping strategy

### 6.1 Common framework

All scrapers implement:

```
class BaseScraper:
    site: str
    def list_category_urls(self) -> list[str]: ...
    def scrape_category(self, url: str) -> Iterable[RawListing]: ...
    def scrape_product(self, listing_url: str) -> RawListing: ...
```

`RawListing` is a Pydantic model with: `site_product_id`, `url`, `name`, `brand`, `image_url`, `price`, `currency`, `in_stock`, `size_ml` (optional), `raw_payload` (full JSON for debug).

The runner (`scrapers/runner.py`):

1. Iterates `BaseScraper.list_category_urls()`.
2. For each category, collects raw listings.
3. Pushes each through the matcher → upserts `listing` + appends a `price_snapshot`.
4. Logs counts (added / updated / errored) per site.

Politeness rules (every scraper):

- Random delay 0.5–1.5 s between requests.
- Realistic `User-Agent` string.
- Respect `robots.txt` (check at startup, fail loudly if disallowed).
- Retry on 5xx / 429 with exponential backoff (max 3 attempts).
- Persist failures to a `scrape_errors` table for debugging.

### 6.2 Per-site notes

**Primor (fr.primor.eu)** — *Already partially working in your existing script.*
- Strategy: list category pages → regex-extract `"skus":[...]` → fetch `https://rcm.frizbit.com/feed/9aF3/{sku}` for structured data.
- Stable pattern, no JS rendering needed.
- Action: port your existing script into `scrapers/primor.py` behind the `BaseScraper` interface; replace `pandas`/Excel output with `RawListing` yields.

**Sephora.fr** — *Hardest of the three.*
- Heavy JS rendering, Akamai/Imperva bot protection, regional redirects.
- Likely strategy: **Playwright** (headless Chromium) — load category page, intercept the XHR call that returns the product list JSON (Sephora ships a `/api/catalog/...` style endpoint), then page through it.
- Fallback: parse `<script type="application/ld+json">` blocks on individual product pages.
- Risk: may get blocked. Plan to cache aggressively and run at low volume.

**Nocibé.fr** — *Mid-difficulty.*
- Mostly server-rendered, some JS. JSON-LD product schema is reliably present on PDPs.
- Strategy: `requests` + `BeautifulSoup` for category pages → JSON-LD parse on each PDP.
- Likely no Playwright needed unless category listings are paginated via JS.

### 6.3 Image handling

- Store the **source image URL** in `listing.image_url`, not the binary.
- Frontend uses Next.js `<Image>` with `remotePatterns` allowlist for the three CDNs.
- Optional later: download + serve from our own CDN to avoid hotlink breakage.

---

## 7. Product matching

The same "Dior Sauvage 100 ml EDP" must be one `canonical_product` across all three sites.

### Step 1 — Normalize
- Lowercase.
- Strip accents (`é → e`).
- Remove punctuation.
- Extract `size_ml` from the name with a regex (`(\d+)\s?ml`).
- Strip the size from the working name.

### Step 2 — Deterministic key
Try to match on `(brand_normalized, name_normalized, size_ml)`. 95 %+ of matches should hit here.

### Step 3 — Fuzzy fallback
Within the same `brand_normalized`, compare candidate names with `rapidfuzz.token_sort_ratio`:
- ≥ 92 → auto-merge.
- 80–92 → write to `match_review_queue` table; UI flags it for manual approval.
- < 80 → create a new `canonical_product`.

### Step 4 — Manual override
Admin UI page (later phase) to merge/split canonical products by hand.

---

## 8. API surface (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/products` | Paginated list. Query: `q`, `brand`, `gender`, `min_price`, `max_price`, `sort`. Returns canonical product + cheapest current price + which site has it. |
| GET | `/api/products/{id}` | Full canonical product + per-site listing (price, in-stock, link, last_updated). |
| GET | `/api/products/{id}/history` | All `price_snapshot`s for the product across sites. |
| GET | `/api/brands` | Distinct brand list (for filter dropdown). |
| POST | `/api/admin/scrape` | Trigger on-demand scrape. Body: `{ "sites": ["primor", "sephora", "nocibe"] }`. Returns `job_id`. |
| GET | `/api/admin/scrape/{job_id}` | Job status: `running` / `done` / `failed` + counts. |

Auth: simple shared-secret header (`X-Admin-Token`) on `/admin/*` for v1.

---

## 9. Frontend pages (Next.js)

- **`/products`** — Grid view. Search bar, brand filter, gender filter, price range slider. Each card: image, brand, name, lowest price, "from {site}" badge.
- **`/products/[id]`** — Detail page. Big image, title, description (if scraped), and a comparison table:

  | Site | Price | In stock | Last updated | |
  |---|---|---|---|---|
  | Primor | 89,90 € | ✓ | 2 min ago | [Visit →] |
  | Sephora | 95,00 € | ✓ | 2 min ago | [Visit →] |
  | Nocibé | 92,50 € | ✗ | 2 min ago | [Visit →] |

- **`/admin/scrape`** — Button per site + "Scrape all". Shows job log. Requires the admin token (entered in a settings panel and stored in `localStorage` — fine for personal use; revisit for production).

---

## 10. Configuration & secrets

`.env` (never committed; ship `.env.example`):

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/parfums
ADMIN_TOKEN=change-me
SCRAPER_USER_AGENT="Mozilla/5.0 (compatible; PerfumeWatch/0.1)"
SCRAPER_REQUEST_DELAY_MS=750
PLAYWRIGHT_HEADLESS=true
```

---

## 11. Risks & open questions

1. **Sephora may block us.** Plan B: lower scrape frequency, residential UA, or drop Sephora from v1.
2. **Legal / ToS.** Each site's ToS likely prohibits scraping. This project is for personal use; don't host the data publicly without review.
3. **Cross-site product matching accuracy.** Need a small labeled sample (~100 perfumes manually matched across 3 sites) to validate the matcher before trusting it.
4. **Image hotlinking.** CDN links may expire. Keep an eye on broken images; consider self-hosting later.
5. **EUR-only assumption.** All three target sites are `.fr`/`.eu` — fine for now.
6. **Size variants.** "Dior Sauvage" comes in 50 / 100 / 200 ml — these are *different* canonical products in our schema. Make sure category scraping captures size.

---

## 12. TO-DO list

Phased, in dependency order. Check off as we go.

### Phase 0 — Bootstrap
- [ ] Initialize git repo, add `.gitignore`, `README.md`.
- [ ] Create `docker-compose.yml` with `postgres` (+ optional `pgadmin`).
- [ ] Scaffold `backend/` (FastAPI + SQLAlchemy + Alembic + ruff + pytest).
- [ ] Scaffold `web/` (Next.js + TypeScript + Tailwind).
- [ ] Wire `.env` loading (pydantic-settings).
- [ ] Sanity check: `GET /api/health` returns OK from FastAPI; `npm run dev` boots Next.js.

### Phase 1 — Database
- [ ] Define SQLAlchemy models for `canonical_product`, `listing`, `price_snapshot`, `scrape_job`, `scrape_error`, `match_review_queue`.
- [ ] Generate first Alembic migration.
- [ ] Add seed script (one fake product end-to-end) to validate schema.

### Phase 2 — Scraper framework
- [ ] Implement `BaseScraper` interface + `RawListing` Pydantic model.
- [ ] Implement `scrapers/runner.py` (calls scrapers, pushes to matcher, writes DB, records job).
- [ ] Add request-level utilities: rate limiter, UA, retry/backoff, robots.txt check.

### Phase 3 — Site scrapers
- [ ] **Primor** — port your existing regex + Frizbit logic into `scrapers/primor.py`. (Fastest win — start here.)
- [ ] **Nocibé** — `requests` + JSON-LD parser.
- [ ] **Sephora** — Playwright-based scraper, with fallback to JSON-LD.
- [ ] Smoke test each: scrape ~20 products, assert all required fields present.

### Phase 4 — Matcher
- [ ] Build `normalize.py` (accent strip, size extraction, brand canonicalization table).
- [ ] Build `resolver.py` — deterministic match → fuzzy match → review queue.
- [ ] Validate against a hand-labeled sample of ~100 products across 3 sites; aim for ≥ 95 % precision.

### Phase 5 — API
- [ ] `GET /api/products` (with filters, pagination, sort).
- [ ] `GET /api/products/{id}` (with per-site listings + latest prices).
- [ ] `GET /api/products/{id}/history`.
- [ ] `GET /api/brands`.
- [ ] `POST /api/admin/scrape` + `GET /api/admin/scrape/{job_id}` (run scraper in a background task).
- [ ] OpenAPI schema reviewed; auto-generate TS client for the frontend.

### Phase 6 — Frontend
- [ ] API client (`web/src/lib/api.ts`) + shared types.
- [ ] `/products` grid with search/filter/sort.
- [ ] `/products/[id]` detail page with comparison table.
- [ ] `/admin/scrape` page.
- [ ] Loading / empty / error states everywhere.
- [ ] Image domain allowlist in `next.config.js`.

### Phase 7 — Validation & polish
- [ ] End-to-end test: trigger scrape → product appears in UI with prices from all 3 sites.
- [ ] Manual matcher review pass; merge/split obvious mistakes.
- [ ] Add basic logging dashboard (job duration, item counts per site).
- [ ] README with run instructions.

### Phase 8 — Future / optional
- [ ] Daily cron (move from on-demand to scheduled).
- [ ] Price-drop email alerts.
- [ ] Per-user accounts and wishlists.
- [ ] More retailers (Marionnaud, Notino, Origines).
- [ ] Self-hosted image CDN.

---

## 13. Immediate next step

Phase 0 — bootstrap the repo skeleton and `docker-compose.yml`. Once that boots cleanly, Phase 1 (DB schema + migration) and Phase 3.1 (Primor scraper port) can run in parallel.
