"""
scrapers/sephora.py
===================
Scraper for www.sephora.fr — hardest of the three.

Strategy
--------
1. Use **Playwright** (async, headless Chromium) to load category pages.
2. Intercept XHR/Fetch calls to Sephora's internal catalog API
   (``/api/catalog/...``) and collect the JSON product payloads directly —
   no HTML parsing of the product grid needed.
3. Paginate by scrolling or via the API's ``page`` / ``offset`` parameter
   (detected from the intercepted request URL pattern).
4. Fallback per PDP: if the catalog API payload is incomplete, parse
   ``<script type="application/ld+json">`` on the product detail page.

Risk
----
Sephora uses Akamai / Imperva bot-detection.  Tips to reduce blocking:
  - Run at low volume (few categories at a time).
  - Use a realistic viewport and User-Agent.
  - Set PLAYWRIGHT_HEADLESS=false during debugging to watch what happens.

If blocking becomes persistent: lower scrape frequency, consider a
residential-proxy service, or drop Sephora from v1 and document the gap.

Dependencies: ``playwright`` (sync or async).  Install browsers with::

    playwright install chromium
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
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from .base import BaseScraper, RawListing
from .utils import USER_AGENT, polite_delay

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SITE = "sephora"
BASE_URL = "https://www.sephora.fr"
HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"

CATEGORY_URLS: list[str] = [
    f"{BASE_URL}/parfums/parfums-femme/",
    f"{BASE_URL}/parfums/parfums-homme/",
    f"{BASE_URL}/parfums/parfums-mixtes/",
    f"{BASE_URL}/parfums/coffrets-et-sets/",
]

# Pattern that matches Sephora's catalog API calls.
_CATALOG_API_RE = re.compile(r'/api/catalog/', re.IGNORECASE)
_SIZE_ML_RE = re.compile(r'(\d+)\s?ml', re.IGNORECASE)
_MAX_PAGES = 30


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class SephoraScraper(BaseScraper):
    """Scraper for www.sephora.fr — Playwright + XHR intercept + JSON-LD fallback."""

    site = SITE

    def list_category_urls(self) -> list[str]:
        return list(CATEGORY_URLS)

    def scrape_category(self, url: str) -> Iterable[RawListing]:
        """Synchronous entry point — runs the async logic internally."""
        return list(asyncio.run(self._async_scrape_category(url)))

    def scrape_product(self, listing_url: str) -> RawListing:
        """Synchronous entry point for single-product refresh."""
        result = asyncio.run(self._async_scrape_pdp(listing_url))
        if result is None:
            raise RuntimeError(f"Failed to scrape Sephora product at {listing_url}")
        return result

    # -- Async implementation ------------------------------------------------

    async def _async_scrape_category(self, url: str) -> list[RawListing]:
        listings: list[RawListing] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=HEADLESS)
            context = await self._make_context(browser)
            page = await context.new_page()

            intercepted: list[dict] = []

            async def handle_response(response: Any) -> None:  # noqa: ANN001
                if _CATALOG_API_RE.search(response.url):
                    try:
                        body = await response.json()
                        intercepted.append(body)
                        logger.debug("[sephora] intercepted API response: %s", response.url)
                    except Exception:
                        pass  # non-JSON response; ignore

            page.on("response", handle_response)

            for page_num in range(1, _MAX_PAGES + 1):
                page_url = _page_url(url, page_num)
                logger.info("[sephora] loading page %d: %s", page_num, page_url)

                try:
                    await page.goto(page_url, wait_until="networkidle", timeout=45_000)
                except Exception as exc:
                    logger.warning("[sephora] page load error on page %d: %s", page_num, exc)
                    break

                # Give XHR calls time to settle.
                await page.wait_for_timeout(2_000)

                # Parse whatever was intercepted so far.
                for payload in intercepted:
                    batch = self._extract_listings_from_api(payload)
                    listings.extend(batch)
                intercepted.clear()

                # If we got nothing from the API, try JSON-LD fallback on PDPs.
                if not listings and page_num == 1:
                    logger.info("[sephora] no API intercepts — trying JSON-LD on PDPs")
                    pdp_urls = await self._collect_pdp_urls(page)
                    for pdp_url in pdp_urls:
                        listing = await self._async_scrape_pdp(pdp_url, context=context)
                        if listing:
                            listings.append(listing)
                    break  # JSON-LD path handles its own pagination

                # Check for next page.
                if not await self._has_next_page(page):
                    break

                polite_delay()

            await browser.close()

        logger.info("[sephora] category %s → %d listings", url, len(listings))
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

            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            content = await page.content()
            await page.close()

            return _parse_json_ld_from_html(url, content)

        except Exception as exc:
            logger.warning("[sephora] PDP scrape failed at %s: %s", url, exc)
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
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            },
        )

    def _extract_listings_from_api(self, payload: Any) -> list[RawListing]:
        """Parse an intercepted Sephora catalog API response."""
        listings: list[RawListing] = []
        # Sephora API shapes vary; try common patterns.
        products = (
            payload.get("products")
            or payload.get("items")
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
        """Map a single Sephora API product dict to a RawListing."""
        try:
            name: str = product.get("name") or product.get("displayName") or ""
            brand: str = (
                product.get("brand", {}).get("name", "")
                if isinstance(product.get("brand"), dict)
                else str(product.get("brand") or "")
            )
            sku: str = str(
                product.get("productId")
                or product.get("sku")
                or product.get("id")
                or ""
            )
            url: str = product.get("url") or product.get("productUrl") or ""
            if url and not url.startswith("http"):
                url = urljoin(BASE_URL, url)

            image_url: str | None = (
                product.get("image")
                or product.get("heroImage")
                or (product.get("images") or [None])[0]
            )

            # Price: look inside currentSku.listPrice or directly.
            raw_price = (
                product.get("currentSku", {}).get("listPrice")
                or product.get("price")
                or product.get("listPrice")
                or 0
            )
            # Strip currency symbols: "89,90 €" → "89.90"
            raw_price_str = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
            try:
                price = Decimal(raw_price_str) if raw_price_str else Decimal("0")
            except InvalidOperation:
                price = Decimal("0")

            if price <= 0:
                return None

            in_stock_raw = product.get("isAvailable") or product.get("inStock") or True
            in_stock = bool(in_stock_raw)
            size_ml = _extract_size_ml(name)

            if not name or not sku:
                return None

            return RawListing(
                site=SITE,
                site_product_id=sku,
                url=url or f"{BASE_URL}/product/{sku}",
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
            logger.error("[sephora] API product parse error: %s | %s", exc, product)
            return None

    async def _collect_pdp_urls(self, page: Page) -> list[str]:
        """Extract product page URLs from the rendered category page."""
        links = await page.eval_on_selector_all(
            "a[href*='/product/']",
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
        """Return True if a 'next page' control is visible."""
        try:
            next_btn = await page.query_selector(
                "button[aria-label='Page suivante'], a[aria-label='Next page'], [data-testid='pagination-next']"
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

def _page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}page={page}"


def _parse_json_ld_from_html(url: str, html: str) -> RawListing | None:
    """Extract product data from JSON-LD blocks in raw HTML text."""
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
            return _map_json_ld(url, obj)
    return None


def _map_json_ld(url: str, obj: dict) -> RawListing | None:
    try:
        name: str = obj.get("name") or ""
        brand_raw = obj.get("brand") or {}
        brand = brand_raw.get("name", "") if isinstance(brand_raw, dict) else str(brand_raw)
        image = obj.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""

        offers = obj.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        raw_price = offers.get("price") or offers.get("lowPrice") or 0
        raw_str = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
        try:
            price = Decimal(raw_str) if raw_str else Decimal("0")
        except InvalidOperation:
            price = Decimal("0")

        if price <= 0 or not name:
            return None

        avail: str = str(offers.get("availability", "")).lower()
        in_stock = "instock" in avail or avail == ""
        sku = str(obj.get("sku") or obj.get("productID") or urlparse(url).path.split("/")[-1])
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
        logger.error("[sephora] JSON-LD map error at %s: %s", url, exc)
        return None


def _extract_size_ml(name: str) -> int | None:
    match = _SIZE_ML_RE.search(name)
    return int(match.group(1)) if match else None
