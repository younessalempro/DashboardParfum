# Developer 2 — Backend API & Database

**Role:** Backend/Infrastructure Developer
**Focus:** PostgreSQL schema, FastAPI endpoints, Docker setup, project bootstrap
**Dependencies:** None (you kick things off). Dev 1 and Dev 3 depend on your work.

---

## Context

You are responsible for the infrastructure backbone: the database schema, migrations, FastAPI REST API, Docker Compose setup, and project scaffolding. You provide the data layer that Dev 1 (scrapers) writes to and Dev 3 (frontend) reads from.

The system uses PostgreSQL with SQLAlchemy ORM, Alembic for migrations, and FastAPI for the REST layer. Everything runs locally via Docker Compose in v1.

---

## Key Files You Own

```
docker-compose.yml
.env.example
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/               ← migrations
├── app/
│   ├── main.py            ← FastAPI entry point
│   ├── config.py          ← pydantic-settings for env loading
│   ├── db.py              ← SQLAlchemy engine + session factory
│   ├── models/            ← SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── canonical_product.py
│   │   ├── listing.py
│   │   ├── price_snapshot.py
│   │   ├── scrape_job.py
│   │   ├── scrape_error.py
│   │   └── match_review_queue.py
│   ├── schemas/           ← Pydantic request/response schemas
│   │   ├── product.py
│   │   ├── listing.py
│   │   └── admin.py
│   └── routers/
│       ├── products.py
│       └── admin.py
└── tests/
```

---

## TO-DO List

### Phase 0 — Bootstrap (Priority: CRITICAL — blocks everyone)

- [ ] **Initialize git repo** with proper `.gitignore` (Python, Node, .env, __pycache__, node_modules, .next)
- [ ] **Create `docker-compose.yml`**
  - Services: `postgres` (image: postgres:16, port 5432, volume for data persistence), optional `pgadmin`
  - Service: `api` (build from `backend/`, port 8000, depends_on postgres)
  - Service: `web` (build from `web/`, port 3000, depends_on api)
  - Shared `.env` file for secrets
- [ ] **Create `.env.example`**
  ```
  DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/parfums
  ADMIN_TOKEN=change-me
  SCRAPER_USER_AGENT="Mozilla/5.0 (compatible; PerfumeWatch/0.1)"
  SCRAPER_REQUEST_DELAY_MS=750
  PLAYWRIGHT_HEADLESS=true
  ```
- [ ] **Scaffold `backend/`**
  - `pyproject.toml` with deps: fastapi, uvicorn, sqlalchemy, psycopg, alembic, pydantic, pydantic-settings, ruff, pytest, httpx
  - `app/main.py`: FastAPI app with CORS middleware + health endpoint
  - `app/config.py`: pydantic-settings class loading from `.env`
  - `app/db.py`: async engine + sessionmaker (or sync if simpler for v1)
  - `alembic.ini` + `alembic/env.py` wired to `config.DATABASE_URL`
- [ ] **Sanity check:** `GET /api/health` returns `{"status": "ok"}` from the container

### Phase 1 — Database Models & Migrations (Priority: HIGH)

- [ ] **Define SQLAlchemy models:**

  **`canonical_product`**
  | Column | Type | Constraints |
  |---|---|---|
  | id | UUID | PK, default uuid4 |
  | brand | text | NOT NULL |
  | name | text | NOT NULL |
  | size_ml | int | Nullable |
  | gender | enum (men, women, unisex) | Nullable |
  | image_url | text | Nullable |
  | created_at | timestamptz | default now() |
  | **Unique:** `(brand, name, size_ml)` |

  **`listing`**
  | Column | Type | Constraints |
  |---|---|---|
  | id | UUID | PK |
  | canonical_product_id | UUID FK | Nullable |
  | site | enum (primor, sephora, nocibe) | NOT NULL |
  | site_product_id | text | NOT NULL |
  | url | text | |
  | name_on_site | text | |
  | brand_on_site | text | |
  | image_url | text | |
  | last_seen_at | timestamptz | |
  | **Unique:** `(site, site_product_id)` |

  **`price_snapshot`** (append-only)
  | Column | Type | Constraints |
  |---|---|---|
  | id | bigint | PK, auto-increment |
  | listing_id | UUID FK | NOT NULL |
  | price | numeric(10,2) | NOT NULL |
  | currency | char(3) | default 'EUR' |
  | in_stock | boolean | |
  | scraped_at | timestamptz | default now() |
  | **Index:** `(listing_id, scraped_at DESC)` |

  **`scrape_job`**
  | Column | Type |
  |---|---|
  | id | UUID PK |
  | status | enum (running, done, failed) |
  | sites | text[] |
  | started_at | timestamptz |
  | finished_at | timestamptz (nullable) |
  | items_added | int default 0 |
  | items_updated | int default 0 |
  | items_errored | int default 0 |

  **`scrape_error`**
  | Column | Type |
  |---|---|
  | id | bigint PK |
  | job_id | UUID FK → scrape_job |
  | site | text |
  | url | text |
  | error_message | text |
  | traceback | text |
  | created_at | timestamptz |

  **`match_review_queue`**
  | Column | Type |
  |---|---|
  | id | bigint PK |
  | listing_id | UUID FK |
  | candidate_canonical_id | UUID FK |
  | score | float |
  | status | enum (pending, approved, rejected) |
  | created_at | timestamptz |

- [ ] **Generate Alembic migration** (`alembic revision --autogenerate -m "initial schema"`)
- [ ] **Create seed script** (`backend/scripts/seed.py`)
  - Insert one fake canonical_product + one listing + one price_snapshot
  - Verify schema works end-to-end
  - Use as smoke test for Dev 1's writes

### Phase 5 — API Endpoints (Priority: HIGH)

- [ ] **`GET /api/products`** — Paginated product list
  - Query params: `q` (search), `brand`, `gender`, `min_price`, `max_price`, `sort` (price_asc, price_desc, name)
  - Response: canonical product + cheapest current price + which site has it
  - Use a subquery or CTE to get latest price per listing
  - Default page size: 20, max: 100
- [ ] **`GET /api/products/{id}`** — Product detail
  - Returns: canonical product info + all listings with their latest price, stock status, URL, last_updated
- [ ] **`GET /api/products/{id}/history`** — Price history
  - All price_snapshots for all listings of this product
  - Optional query param: `days` (default 30)
- [ ] **`GET /api/brands`** — Distinct brand list for filter dropdown
  - Returns: `[{"brand": "dior", "count": 42}, ...]`
- [ ] **`POST /api/admin/scrape`** — Trigger scrape
  - Body: `{"sites": ["primor", "sephora", "nocibe"]}`
  - Auth: `X-Admin-Token` header must match `ADMIN_TOKEN` env var
  - Creates a `scrape_job` record, launches scrape in a BackgroundTask
  - Returns: `{"job_id": "..."}`
- [ ] **`GET /api/admin/scrape/{job_id}`** — Job status
  - Returns: status, counts, duration
- [ ] **Auto-generate OpenAPI schema** and verify it's clean
  - Export as JSON for Dev 3 to generate TypeScript types

### Infrastructure Tasks

- [ ] **CORS configuration** — Allow frontend origin (localhost:3000)
- [ ] **Error handling middleware** — Consistent JSON error responses
- [ ] **Logging** — Structured logs (job ID, site, duration)
- [ ] **README.md** — Setup instructions (docker compose up, run migrations, seed)

---

## Technical Notes

- **Key Python dependencies:** fastapi, uvicorn[standard], sqlalchemy[asyncio], psycopg[binary], alembic, pydantic, pydantic-settings
- **Database URL format:** `postgresql+psycopg://user:pass@localhost:5432/parfums`
- **Coordinate with Dev 1:** They write to your models. Agree on the upsert interface early (e.g., a `crud.upsert_listing()` function they can import).
- **Coordinate with Dev 3:** They consume your API. Share the OpenAPI spec as soon as endpoints are up. They need the response shapes to build the frontend.
- **Auth for v1:** Simple `X-Admin-Token` header on `/admin/*` routes. No user accounts.

---

## Definition of Done

1. `docker compose up` boots PostgreSQL + API cleanly
2. Migrations run without errors; seed script populates test data
3. All 6 API endpoints return correct data with proper status codes
4. OpenAPI spec is generated and shared with Dev 3
5. CORS allows frontend access; error responses are consistent JSON
6. Dev 1 can import and call DB write functions successfully
