# Developer 3 — Frontend (Next.js)

**Role:** Frontend Developer
**Focus:** Next.js web application (product browsing, comparison UI, admin panel)
**Dependencies:** Needs API endpoints from Dev 2 (can develop against mock data / OpenAPI spec first)

---

## Context

You are building the user-facing web application: a price-comparison interface where users browse perfumes and instantly see prices across 3 retailers (Primor, Sephora, Nocibe). The app also has a simple admin page to trigger scrapes manually.

Tech stack: Next.js 14+ (App Router), React, TypeScript, Tailwind CSS. Server components where possible for product pages. The API lives at `http://localhost:8000/api/`.

---

## Key Files You Own

```
web/
├── package.json
├── next.config.js
├── tsconfig.json
├── tailwind.config.ts
├── .env.local
└── src/
    ├── app/
    │   ├── layout.tsx          ← Root layout (nav, footer)
    │   ├── page.tsx            ← Home (redirect to /products or landing)
    │   ├── products/
    │   │   ├── page.tsx        ← Product grid with search/filter
    │   │   └── [id]/
    │   │       └── page.tsx    ← Product detail + price comparison
    │   └── admin/
    │       └── scrape/
    │           └── page.tsx    ← Admin scrape trigger panel
    ├── components/
    │   ├── ProductCard.tsx
    │   ├── ProductGrid.tsx
    │   ├── PriceComparisonTable.tsx
    │   ├── SearchBar.tsx
    │   ├── FilterPanel.tsx
    │   ├── SiteBadge.tsx
    │   └── AdminTokenInput.tsx
    └── lib/
        ├── api.ts              ← API client (fetch wrapper)
        └── types.ts            ← TypeScript interfaces (from OpenAPI)
```

---

## TO-DO List

### Phase 0 — Scaffold (Priority: CRITICAL — do in parallel with Dev 2)

- [ ] **Initialize Next.js project** in `web/`
  - `npx create-next-app@latest web --typescript --tailwind --app --src-dir`
  - Verify `npm run dev` boots on port 3000
- [ ] **Configure `next.config.js`**
  - Remote image patterns for CDN domains:
    ```js
    images: {
      remotePatterns: [
        { protocol: 'https', hostname: '**.primor.eu' },
        { protocol: 'https', hostname: '**.sephora.fr' },
        { protocol: 'https', hostname: '**.nocibe.fr' },
        { protocol: 'https', hostname: 'rcm.frizbit.com' },
      ]
    }
    ```
  - API rewrites (proxy `/api/**` to backend in dev)
- [ ] **Set up `.env.local`**
  ```
  NEXT_PUBLIC_API_URL=http://localhost:8000
  ```
- [ ] **Create root layout** (`src/app/layout.tsx`)
  - Navigation bar with logo/title ("Perfume Price Comparator"), link to /products, link to /admin/scrape
  - Clean, minimal design with Tailwind

### Phase 6 — API Client & Types (Priority: HIGH)

- [ ] **Create `lib/types.ts`** — TypeScript interfaces matching API responses
  ```typescript
  interface CanonicalProduct {
    id: string;
    brand: string;
    name: string;
    size_ml: number | null;
    gender: 'men' | 'women' | 'unisex' | null;
    image_url: string | null;
  }

  interface Listing {
    id: string;
    site: 'primor' | 'sephora' | 'nocibe';
    url: string;
    name_on_site: string;
    image_url: string | null;
    latest_price: number;
    in_stock: boolean;
    last_seen_at: string;
  }

  interface ProductListItem extends CanonicalProduct {
    cheapest_price: number;
    cheapest_site: string;
  }

  interface ProductDetail extends CanonicalProduct {
    listings: Listing[];
  }

  interface PriceHistoryEntry {
    listing_id: string;
    site: string;
    price: number;
    in_stock: boolean;
    scraped_at: string;
  }

  interface ScrapeJob {
    job_id: string;
    status: 'running' | 'done' | 'failed';
    items_added: number;
    items_updated: number;
    items_errored: number;
    started_at: string;
    finished_at: string | null;
  }
  ```
- [ ] **Create `lib/api.ts`** — Fetch wrapper
  - `getProducts(params)` → paginated product list
  - `getProduct(id)` → product detail with listings
  - `getProductHistory(id)` → price history
  - `getBrands()` → brand list
  - `triggerScrape(sites, adminToken)` → job ID
  - `getScrapeStatus(jobId, adminToken)` → job status
  - Handle errors gracefully (return typed error objects)

### Phase 6 — Product List Page (`/products`) (Priority: HIGH)

- [ ] **Search bar component** — Text input with debounced search (300ms)
- [ ] **Filter panel component**
  - Brand dropdown (populated from `GET /api/brands`)
  - Gender filter (men / women / unisex / all)
  - Price range slider (min / max in EUR)
  - Sort selector (price asc, price desc, name A-Z)
- [ ] **Product card component**
  - Product image (Next.js `<Image>` with fallback placeholder)
  - Brand name (small, muted)
  - Product name + size
  - Lowest price in bold
  - "from [site]" badge (colored per site: Primor=green, Sephora=black, Nocibe=purple)
- [ ] **Product grid** — Responsive grid (1 col mobile, 2 tablet, 3-4 desktop)
- [ ] **Pagination** — "Load more" button or infinite scroll
- [ ] **Empty state** — "No perfumes found" with suggestion to adjust filters
- [ ] **Loading state** — Skeleton cards while fetching

### Phase 6 — Product Detail Page (`/products/[id]`) (Priority: HIGH)

- [ ] **Hero section** — Large product image, brand, name, size, gender badge
- [ ] **Price comparison table**
  | Site | Price | In stock | Last updated | Action |
  |---|---|---|---|---|
  | Primor | 89,90 € | ✓ | 2 min ago | [Visit →] |
  | Sephora | 95,00 € | ✓ | 2 min ago | [Visit →] |
  | Nocibe | 92,50 € | ✗ | 2 min ago | [Visit →] |

  - Highlight cheapest price row
  - "Visit →" opens retailer URL in new tab
  - Show "Out of stock" in red when `in_stock` is false
  - Relative timestamps ("2 min ago", "1 hour ago")
- [ ] **Price history section** (optional, nice-to-have for v1)
  - Simple line chart showing price over time per site
  - Use a lightweight chart lib (e.g., recharts) or skip for v1
- [ ] **Loading / error states**

### Phase 6 — Admin Scrape Page (`/admin/scrape`) (Priority: MEDIUM)

- [ ] **Admin token input**
  - Text input for the admin token
  - Store in `localStorage` for convenience (fine for personal use)
  - Show warning: "This token is stored locally"
- [ ] **Scrape trigger buttons**
  - "Scrape Primor", "Scrape Sephora", "Scrape Nocibe", "Scrape All"
  - Disabled while a job is running
- [ ] **Job status display**
  - Poll `GET /api/admin/scrape/{job_id}` every 2s while status is "running"
  - Show: status badge, items added/updated/errored, duration
  - Job log (list of recent jobs)
- [ ] **Error display** — Show error details if job fails

### Polish & UX (Priority: MEDIUM)

- [ ] **Responsive design** — Works well on mobile, tablet, desktop
- [ ] **Dark mode support** (optional) — Tailwind dark: classes
- [ ] **SEO basics** — Page titles, meta descriptions for product pages
- [ ] **Favicon + basic branding**
- [ ] **Error boundary** — Catch and display errors gracefully
- [ ] **404 page** — Custom not-found for invalid product IDs

---

## Technical Notes

- **Dependencies:** next, react, typescript, tailwind, possibly recharts (for price history chart)
- **Server Components:** Use for `/products` and `/products/[id]` (data fetching on server). Use client components only for interactive bits (search input, filters, admin panel).
- **Image optimization:** Use `next/image` with the `remotePatterns` config. Always provide width/height or use `fill` layout. Add a placeholder/fallback for missing images.
- **Coordinate with Dev 2:** Get the OpenAPI spec ASAP to generate/validate your TypeScript types. Agree on response shapes. Ask for example JSON responses to build mock data.
- **Mock data for development:** Create a `lib/mockData.ts` with sample products so you can build UI before the API is ready.
- **EUR formatting:** Use `Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })` for price display.
- **Site colors/badges:** Primor = #4CAF50 (green), Sephora = #000000 (black), Nocibe = #6B21A8 (purple)

---

## Definition of Done

1. `npm run dev` boots without errors; all pages render
2. `/products` shows a filterable, searchable grid of perfumes
3. `/products/[id]` shows the comparison table with prices from all sites
4. `/admin/scrape` can trigger a scrape and shows live job status
5. All pages have proper loading, empty, and error states
6. Responsive layout works on mobile and desktop
7. Images load correctly from all 3 retailer CDNs
