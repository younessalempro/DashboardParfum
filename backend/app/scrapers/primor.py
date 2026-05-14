"""
scrapers/primor.py
==================
Scraper for fr.primor.eu

Investigation findings (2026-05)
---------------------------------
Strategy revised after live testing:

PRIMARY — Category page → PDP links → JSON-LD + spConfig volume map
  The category pages (curl_cffi required to bypass Cloudflare TLS check)
  embed ~60 PDP links per page as standard <a href> elements.
  Each PDP returns HTTP 200 with:
    * ``application/ld+json`` structured data (name, brand, offers array,
      one offer per size variant with variant SKU and price).
    * A Magento ``spConfig`` JS blob containing attribute 854 ("volumen")
      which maps each variant SKU to its volume in ml.

  We combine both sources to emit ONE RawListing per size variant so
  that the product catalogue knows the exact volume for each price point.

SECONDARY — Frizbit feed (supplemental, limited coverage)
  ``GET https://rcm.frizbit.com/feed/9aF3/{sku}``
  Only a subset of SKUs (~30 %) are in the Frizbit feed (featured/promoted
  products). Not useful as the sole data source.

Category URL structure (as of 2026-05)
---------------------------------------
The site migrated from ``/parfums/parfums-femme/`` to a locale-prefixed
scheme. Working URLs:
  https://fr.primor.eu/fr_fr/parfums-pour-femme
  https://fr.primor.eu/fr_fr/parfums-pour-homme
  https://fr.primor.eu/fr_fr/coffrets-de-parfum-pour-femme
  https://fr.primor.eu/fr_fr/coffrets-de-parfum-pour-homme

PDP URL pattern:
  https://fr.primor.eu/fr_fr/<brand>-<name>-<parentSKU>.html

JSON-LD Product schema on PDPs (verified 2026-05):
  name:         "Libre Eau de Parfum Rechargeable"
  brand.name:   "Yves Saint Laurent"
  offers:       array, one entry per size variant
    offers[i].sku:          "4AF05713"  (variant SKU)
    offers[i].price:        "44.37"
    offers[i].availability: "http://schema.org/InStock"

spConfig JS blob (verified 2026-05):
  attributes.854.code:    "volumen"
  attributes.854.options: [{label: "50", skus: ["4AF05713"]}, ...]
  The label is the volume in ml (integer string).
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, RawListing
from .utils import build_cffi_session, build_session, check_robots, polite_get

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SITE = "primor"
BASE_URL = "https://fr.primor.eu"
FRIZBIT_FEED = "https://rcm.frizbit.com/feed/9aF3/{sku}"

# Category URLs — locale-prefixed scheme, verified 2026-05.
CATEGORY_URLS: list[str] = [
    f"{BASE_URL}/fr_fr/parfums-pour-femme",
    f"{BASE_URL}/fr_fr/parfums-pour-homme",
    f"{BASE_URL}/fr_fr/coffrets-de-parfum-pour-femme",
    f"{BASE_URL}/fr_fr/coffrets-de-parfum-pour-homme",
]

# PDP link pattern: /fr_fr/<any-slug>-<numeric-id>.html
_PDP_LINK_RE = re.compile(r"/fr_fr/[a-z0-9-]+-\d+\.html$", re.IGNORECASE)

# Regex to extract size in ml from a product name (fallback only).
_SIZE_ML_RE = re.compile(r"(\d+)\s?ml", re.IGNORECASE)

# Regex to extract the SKU array embedded in category HTML (Frizbit path).
_SKU_RE = re.compile(r'"skus"\s*:\s*(\[[^\]]+\])')


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class PrimorScraper(BaseScraper):
    """Scraper for fr.primor.eu.

    Primary path: curl_cffi category page → PDP links → JSON-LD + spConfig volume.
    One RawListing is emitted per size variant (each with its own SKU, price, size_ml).
    """

    site = SITE

    def __init__(self) -> None:
        self._session = build_cffi_session()
        self._frizbit_session = build_session()
        self._robots_checked: set[str] = set()

    # -- BaseScraper interface -----------------------------------------------

    def list_category_urls(self) -> list[str]:
        return list(CATEGORY_URLS)

    def scrape_category(self, url: str) -> Iterable[RawListing]:
        """Scrape a category page and yield one RawListing per product variant."""
        if BASE_URL not in self._robots_checked:
            check_robots(url)
            self._robots_checked.add(BASE_URL)

        logger.info("[primor] scraping category: %s", url)
        try:
            resp = polite_get(self._session, url, check_robots_first=False)
        except Exception as exc:
            logger.error("[primor] failed to fetch category %s: %s", url, exc)
            return

        soup = BeautifulSoup(resp.text, "lxml")
        pdp_links = self._extract_pdp_links(soup)
        logger.info("[primor] found %d PDP links in %s", len(pdp_links), url)

        for pdp_url in pdp_links:
            yield from self._scrape_pdp(pdp_url)

    def scrape_product(self, listing_url: str) -> RawListing:
        """Targeted refresh: return the cheapest variant from a PDP."""
        listings = list(self._scrape_pdp(listing_url))
        if not listings:
            raise RuntimeError(f"Failed to scrape product at {listing_url}")
        return min(listings, key=lambda l: l.price)

    # -- Private helpers -----------------------------------------------------

    def _extract_pdp_links(self, soup: BeautifulSoup) -> list[str]:
        """Return deduplicated absolute PDP URLs from a category page."""
        seen: set[str] = set()
        unique: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            abs_href = href if href.startswith("http") else urljoin(BASE_URL, href)
            if _PDP_LINK_RE.search(urlparse(abs_href).path) and abs_href not in seen:
                seen.add(abs_href)
                unique.append(abs_href)
        return unique

    def _scrape_pdp(self, url: str) -> Iterable[RawListing]:
        """Fetch a PDP and yield one RawListing per size variant."""
        try:
            resp = polite_get(self._session, url, check_robots_first=False)
        except Exception as exc:
            logger.warning("[primor] failed to fetch PDP %s: %s", url, exc)
            return

        soup = BeautifulSoup(resp.text, "lxml")
        sku_to_ml = _extract_sku_to_ml(resp.text)
        yield from self._parse_json_ld(url, soup, sku_to_ml)

    def _parse_json_ld(
        self,
        url: str,
        soup: BeautifulSoup,
        sku_to_ml: dict[str, int],
    ) -> Iterable[RawListing]:
        """Extract one RawListing per offer variant from JSON-LD on a PDP."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data: Any = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            candidates = data if isinstance(data, list) else [data]
            for obj in candidates:
                if not isinstance(obj, dict) or obj.get("@type") not in ("Product", "product"):
                    continue
                yield from self._map_json_ld_variants(url, obj, sku_to_ml)
                return  # only process the first Product block

    def _map_json_ld_variants(
        self,
        url: str,
        obj: dict,
        sku_to_ml: dict[str, int],
    ) -> Iterable[RawListing]:
        """Yield one RawListing per offer in the JSON-LD Product object."""
        try:
            name: str = obj.get("name") or ""
            brand_raw = obj.get("brand") or {}
            brand: str = (
                brand_raw.get("name", "") if isinstance(brand_raw, dict) else str(brand_raw)
            )
            image = obj.get("image") or ""
            if isinstance(image, list):
                image = image[0] if image else ""

            if not name:
                return

            offers = obj.get("offers") or {}
            if isinstance(offers, dict):
                offers = [offers]
            if not isinstance(offers, list) or not offers:
                return

            emitted: set[str] = set()

            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                try:
                    raw_price = offer.get("price") or offer.get("lowPrice") or 0
                    raw_price_str = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
                    try:
                        price = Decimal(raw_price_str) if raw_price_str else Decimal("0")
                    except InvalidOperation:
                        continue
                    if price <= 0:
                        continue

                    availability: str = str(offer.get("availability", "")).lower()
                    in_stock = "instock" in availability or availability == ""

                    variant_sku: str = str(offer.get("sku") or offer.get("productID") or "")
                    if not variant_sku:
                        variant_sku = _sku_from_url(url)
                    if variant_sku in emitted:
                        continue
                    emitted.add(variant_sku)

                    # Size: spConfig map first, fall back to name regex.
                    size_ml: int | None = sku_to_ml.get(variant_sku) or _extract_size_ml(name)
                    currency: str = str(offer.get("priceCurrency", "EUR"))

                    yield RawListing(
                        site=SITE,
                        site_product_id=variant_sku,
                        url=url,
                        name=name,
                        brand=brand,
                        image_url=str(image) if image else None,
                        price=price,
                        currency=currency,
                        in_stock=in_stock,
                        size_ml=size_ml,
                        raw_payload={**obj, "_offer": offer},
                    )
                except Exception as exc:
                    logger.warning("[primor] offer parse error at %s: %s", url, exc)

        except Exception as exc:
            logger.error("[primor] JSON-LD map error at %s: %s", url, exc)

    def _map_json_ld(self, url: str, obj: dict) -> RawListing | None:
        """Return first variant RawListing (backward-compat for tests)."""
        listings = list(self._map_json_ld_variants(url, obj, {}))
        return listings[0] if listings else None

    # -- Frizbit supplemental ------------------------------------------------

    def _extract_skus(self, html: str) -> list[str]:
        skus: list[str] = []
        for match in _SKU_RE.finditer(html):
            try:
                batch: list[str] = json.loads(match.group(1))
                skus.extend(str(s) for s in batch)
            except json.JSONDecodeError as exc:
                logger.warning("[primor] could not parse SKU array: %s", exc)
        seen: set[str] = set()
        unique: list[str] = []
        for s in skus:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    def _fetch_frizbit(self, sku: str) -> RawListing | None:
        feed_url = FRIZBIT_FEED.format(sku=sku)
        try:
            resp = polite_get(self._frizbit_session, feed_url, check_robots_first=False)
            data: dict = resp.json()
        except Exception as exc:
            logger.warning("[primor] Frizbit fetch failed for SKU %s: %s", sku, exc)
            return None
        return self._parse_frizbit(sku, data)

    def _parse_frizbit(self, sku: str, data: dict) -> RawListing | None:
        """Convert a Frizbit feed payload to a RawListing.

        Actual Frizbit field names (verified against live API 2026-05):
          product_name, product_brand, product_sale_price, product_image,
          product_url, product_instock.
        Old names (title/brand/price/url/availability) kept as fallbacks.
        """
        try:
            name: str = (
                data.get("product_name") or data.get("title") or data.get("name") or ""
            )
            brand: str = data.get("product_brand") or data.get("brand") or ""
            image_url: str | None = (
                data.get("product_image") or data.get("image") or data.get("image_link")
            )
            product_url: str = (
                data.get("product_url") or data.get("url") or data.get("link") or ""
            )
            raw_price = (
                data.get("product_sale_price")
                or data.get("product_price")
                or data.get("price")
                or data.get("sale_price")
                or 0
            )
            try:
                price = Decimal(str(raw_price))
            except InvalidOperation:
                logger.warning("[primor] invalid Frizbit price '%s' for SKU %s", raw_price, sku)
                return None

            availability: str = str(
                data.get("product_instock") or data.get("availability", "in_stock")
            ).lower()
            in_stock = availability in ("in_stock", "1") or "in_stock" in availability
            size_ml = _extract_size_ml(name)

            if not name or not product_url or price <= 0:
                logger.warning("[primor] incomplete Frizbit data for SKU %s", sku)
                return None

            return RawListing(
                site=SITE,
                site_product_id=sku,
                url=product_url,
                name=name,
                brand=brand,
                image_url=image_url,
                price=price,
                currency="EUR",
                in_stock=in_stock,
                size_ml=size_ml,
                raw_payload=data,
            )
        except Exception as exc:
            logger.error("[primor] Frizbit parse error for SKU %s: %s", sku, exc)
            return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_sku_to_ml(html: str) -> dict[str, int]:
    """Parse the Magento spConfig JS blob and return {variant_sku: size_ml}.

    Primor PDPs embed a ``spConfig`` object with attribute 854 (code
    ``"volumen"``).  Each option has ``label`` (the ml value as string) and
    ``skus`` (list of variant SKUs at that volume).
    """
    sku_to_ml: dict[str, int] = {}

    # Locate the position of "volumen" attribute, then find its "options": [
    # We use a bracket-counter to extract the full outer array (avoids
    # non-greedy regex stopping inside a nested SKU array).
    vol_m = re.search(
        r'"code"\s*:\s*"volumen".*?"options"\s*:\s*\[',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not vol_m:
        return sku_to_ml

    # Walk forward from the opening '[' counting brackets to find the closing ']'
    start = vol_m.end() - 1  # index of the opening '['
    depth = 0
    end = start
    for i, ch in enumerate(html[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    else:
        return sku_to_ml  # unbalanced — give up

    options_str = html[start : end + 1]

    # Parse each option: extract label and the full skus array.
    # Each option object looks like: {"id":"...","label":"30","skus":["SKU-A",...]}
    for m in re.finditer(
        r'"label"\s*:\s*"(\d+)"[^}]*?"skus"\s*:\s*(\[[^\]]*\])',
        options_str,
        re.DOTALL | re.IGNORECASE,
    ):
        ml_str, skus_json = m.group(1), m.group(2)
        try:
            skus = json.loads(skus_json)
            ml = int(ml_str)
            for s in skus:
                sku_to_ml[str(s)] = ml
        except (json.JSONDecodeError, ValueError):
            pass

    return sku_to_ml


def _sku_from_url(url: str) -> str:
    """Extract the parent numeric ID from a Primor PDP URL."""
    match = re.search(r"-(\d+)\.html", url)
    if match:
        return match.group(1)
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def _extract_size_ml(name: str) -> int | None:
    match = _SIZE_ML_RE.search(name)
    return int(match.group(1)) if match else None
