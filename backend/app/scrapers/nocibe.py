"""
scrapers/nocibe.py
==================
Scraper for www.nocibe.fr

Investigation findings (2026-05)
---------------------------------
Nocibé runs an ICM (Intershop Commerce Management) React SPA.
Both category listing pages and PDPs require full JavaScript execution:

* Category pages  → products are loaded via XHR after JS boots; the static
  HTML shell contains no product cards.
* PDPs            → blocked by Imperva/Akamai with 403 for plain HTTP
  clients, even with curl_cffi Chrome impersonation.
* Category page   → returns HTTP 404 (locale redirect artefact) but the
  full JS-rendered HTML still arrives, so we must NOT raise_for_status on
  these requests.

Strategy (Playwright, same pattern as sephora.py)
--------------------------------------------------
1. Use Playwright (headless Chromium) to navigate each category URL.
2. Intercept XHR/Fetch responses that match the Nocibé product-listing API
   pattern (``/v2/personalizedSearch/`` or ``/search``).
3. Parse the intercepted JSON payloads for product data.
4. If no API interception succeeds (API shape changed), fall back to
   parsing ``<script type="application/ld+json">`` on individual PDPs.
5. Handle pagination via the ``page`` query parameter.

Category URL structure (verified 2026-05)
------------------------------------------
The correct perfume category paths are:
  /parfum-femme          (women's fragrances)
  /parfum-homme          (men's fragrances)
  /parfum-mixte          (unisex fragrances)
  /coffret-parfum        (fragrance gift sets)
These redirect to /fr/<slug> internally but the bare slugs work fine as
entry points in a real browser.

Risk
----
Nocibé uses Imperva/Akamai bot protection — same risk profile as Sephora.
If blocking is persistent: reduce scrape frequency, or downgrade to
a best-effort parse of the category HTML (which does contain a
``window.__INITIAL_STATE__`` blob, but the product list key is empty
until the XHR populates it client-side).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .base import BaseScraper, RawListing
from .utils import USER_AGENT, polite_delay

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SITE = "nocibe"
BASE_URL = "https://www.nocibe.fr"
HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"

# Verified working category slugs (2026-05).  The site redirects these to
# /fr/<slug> internally; Playwright follows the redirect transparently.
CATEGORY_URLS: list[str] = [
    f"{BASE_URL}/parfum-femme",
    f"{BASE_URL}/parfum-homme",
    f"{BASE_URL}/parfum-mixte",
    f"{BASE_URL}/coffret-parfum",
]

# XHR patterns that carry product listing payloads.
_PRODUCT_API_RE = re.compile(
    r"(/v2/personalizedSearch/|/search\?|/products\?|/catalog/products)", re.IGNORECASE
)

_SIZE_ML_RE = re.compile(r"(\d+)\s?ml", re.IGNORECASE)
_MAX_PAGES = 30


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class NocibeScraper(BaseScraper):
    """Scraper for www.nocibe.fr — Playwright + XHR intercept + JSON-LD fallback."""

    site = SITE

    def list_category_urls(self) -> list[str]:
        return list(CATEGORY_URLS)

    def scrape_category(self, url: str) -> Iterable[RawListing]:
        """Synchronous entry point — runs the async implementation."""
        return list(asyncio.run(self._async_scrape_category(url)))

    def scrape_product(self, listing_url: str) -> RawListing:
        """Synchronous entry point for single-product refresh."""
        result = asyncio.run(self._async_scrape_pdp(listing_url))
        if result is None:
            raise RuntimeError(f"Failed to scrape Nocibé product at {listing_url}")
        return result

    # -- Async implementation ------------------------------------------------

    async def _async_scrape_category(self, url: str) -> list[RawListing]:
        listings: list[RawListing] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=HEADLESS)
            context = await self._make_context(browser)
            page = await context.new_page()

            intercepted: list[dict] = []

            async def handle_response(response: Any) -> None:
                if _PRODUCT_API_RE.search(response.url):
                    try:
                        body = await response.json()
                        intercepted.append({"url": response.url, "body": body})
                        logger.debug("[nocibe] intercepted API: %s", response.url)
                    except Exception:
                        pass

            page.on("response", handle_response)

            for page_num in range(1, _MAX_PAGES + 1):
                page_url = _build_page_url(url, page_num)
                logger.info("[nocibe] loading page %d: %s", page_num, page_url)

                try:
                    # Nocibé category pages return HTTP 404 (locale-redirect
                    # artefact) but deliver full content — ignore status code.
                    await page.goto(
                        page_url,
                        wait_until="networkidle",
                        timeout=45_000,
                    )
                except Exception as exc:
                    logger.warning("[nocibe] page load error on page %d: %s", page_num, exc)
                    break

                await page.wait_for_timeout(2_000)

                # Parse intercepted API responses.
                for item in intercepted:
                    batch = self._extract_listings_from_api(item["body"])
                    listings.extend(batch)
                intercepted.clear()

                # If no API intercepts on page 1, try JSON-LD on PDPs.
                if not listings and page_num == 1:
                    logger.info("[nocibe] no API intercepts — falling back to PDP JSON-LD")
                    pdp_urls = await self._collect_pdp_urls(page)
                    for pdp_url in pdp_urls:
                        listing = await self._async_scrape_pdp(pdp_url, context=context)
                        if listing:
                            listings.append(listing)
                    break

                if not await self._has_next_page(page):
                    break

                polite_delay()

            await browser.close()

        logger.info("[nocibe] category %s → %d listings", url, len(listings))
        return listings

    async def _async_scrape_pdp(
        self,
        url: str,
        *,
        context: BrowserContext | None = None,
    ) -> RawListing | None:
        """Open a PDP and extract data from JSON-LD."""
        own_browser: Browser | None = None
        own_context: BrowserContext | None = None

        try:
            if context is None:
                pw_instance = await async_playwright().__aenter__()
                own_browser = await pw_instance.chromium.launch(headless=HEADLESS)
                own_context = await self._make_context(own_browser)
                ctx = own_context
            else:
                ctx = context

            pdp_page = await ctx.new_page()
            await pdp_page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            content = await pdp_page.content()
            await pdp_page.close()

            return _parse_json_ld_from_html(url, content)

        except Exception as exc:
            logger.warning("[nocibe] PDP scrape failed at %s: %s", url, exc)
            return None
        finally:
            if own_context:
                await own_context.close()
            if own_browser:
                await own_browser.close()

    # -- Helpers -------------------------------------------------------------

    async def _make_context(self, browser: Browser) -> BrowserContext:
        return await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="fr-FR",
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
        )

    def _extract_listings_from_api(self, payload: Any) -> list[RawListing]:
        """Parse an intercepted Nocibé product-listing API response."""
        listings: list[RawListing] = []
        # Try several common shapes from ICM / personalizedSearch APIs.
        products = (
            payload.get("products")
            or payload.get("items")
            or payload.get("hits")
            or payload.get("data", {}).get("products")
            or []
        )
        if not isinstance(products, list):
            return listings
        for product in products:
            listing = self._map_api_product(product)
            if listing:
                listings.append(listing)
        return listings

    def _map_api_product(self, product: dict) -> RawListing | None:
        """Map a single Nocibé API product dict to a RawListing."""
        try:
            name: str = (
                product.get("name")
                or product.get("displayName")
                or product.get("title")
                or ""
            )
            brand_raw = product.get("brand") or {}
            brand: str = (
                brand_raw.get("name", "")
                if isinstance(brand_raw, dict)
                else str(brand_raw or "")
            )
            sku: str = str(
                product.get("sku")
                or product.get("productId")
                or product.get("code")
                or product.get("id")
                or ""
            )
            url: str = product.get("url") or product.get("productUrl") or ""
            if url and not url.startswith("http"):
                url = urljoin(BASE_URL, url)

            image_url: str | None = (
                product.get("image")
                or product.get("imageUrl")
                or (product.get("images") or [None])[0]
            )

            raw_price = (
                product.get("salePrice")
                or product.get("listPrice")
                or product.get("price")
                or 0
            )
            raw_price_str = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
            try:
                price = Decimal(raw_price_str) if raw_price_str else Decimal("0")
            except InvalidOperation:
                price = Decimal("0")

            if price <= 0 or not name or not sku:
                return None

            in_stock = bool(product.get("inStock", product.get("isAvailable", True)))
            size_ml = _extract_size_ml(name)

            return RawListing(
                site=SITE,
                site_product_id=sku,
                url=url or f"{BASE_URL}/fr/p/{sku}",
                name=name,
                brand=brand,
                image_url=str(image_url) if image_url else None,
                price=price,
                currency="EUR",
                in_stock=in_stock,
                size_ml=size_ml,
                raw_payload=product,
            )
        except Exception as exc:
            logger.error("[nocibe] API product parse error: %s | %s", exc, product)
            return None

    async def _collect_pdp_urls(self, page: Page) -> list[str]:
        """Extract product URLs from the rendered category page."""
        # Nocibé product links follow the pattern /fr/p/<numeric-id>
        links = await page.eval_on_selector_all(
            "a[href*='/p/']",
            "els => els.map(e => e.href)",
        )
        seen: set[str] = set()
        unique: list[str] = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique.append(link)
        return unique

    async def _has_next_page(self, page: Page) -> bool:
        """Return True if a visible 'next page' control exists."""
        try:
            next_btn = await page.query_selector(
                "[aria-label='Page suivante'], [aria-label='Next page'], "
                "[data-testid='pagination-next'], .pagination__next"
            )
            if next_btn:
                disabled = await next_btn.get_attribute("disabled")
                return disabled is None
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _build_page_url(base_url: str, page: int) -> str:
    """Append ``?page=N`` to *base_url* (page 1 → no param)."""
    if page == 1:
        return base_url
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)
    qs["page"] = [str(page)]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def _sku_from_url(url: str) -> str:
    """Best-effort SKU extraction from a Nocibé product URL (/fr/p/<id>)."""
    match = re.search(r"/p/(\w+)", url)
    if match:
        return match.group(1)
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def _extract_size_ml(name: str) -> int | None:
    match = _SIZE_ML_RE.search(name)
    return int(match.group(1)) if match else None


def _parse_json_ld_from_html(url: str, html: str) -> RawListing | None:
    """Extract a RawListing from JSON-LD blocks in raw HTML (PDP fallback)."""
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            data: Any = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue

        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict) or obj.get("@type") not in ("Product", "product"):
                continue

            try:
                name: str = obj.get("name") or ""
                brand_raw = obj.get("brand") or {}
                brand: str = (
                    brand_raw.get("name", "")
                    if isinstance(brand_raw, dict)
                    else str(brand_raw)
                )
                image = obj.get("image") or ""
                if isinstance(image, list):
                    image = image[0] if image else ""

                offers = obj.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                raw_price = offers.get("price") or offers.get("lowPrice") or 0
                try:
                    price = Decimal(str(raw_price))
                except InvalidOperation:
                    continue

                if price <= 0 or not name:
                    continue

                availability = str(offers.get("availability", "")).lower()
                in_stock = "instock" in availability or availability == ""
                sku = str(obj.get("sku") or obj.get("productID") or _sku_from_url(url))
                size_ml = _extract_size_ml(name)

                return RawListing(
                    site=SITE,
                    site_product_id=sku,
                    url=url,
                    name=name,
                    brand=brand,
                    image_url=str(image) if image else None,
                    price=price,
                    currency="EUR",
                    in_stock=in_stock,
                    size_ml=size_ml,
                    raw_payload=obj,
                )
            except Exception as exc:
                logger.error("[nocibe] JSON-LD map error at %s: %s", url, exc)

    return None
