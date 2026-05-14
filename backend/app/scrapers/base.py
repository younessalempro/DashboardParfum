"""
scrapers/base.py
================
Abstract BaseScraper interface and the RawListing data contract shared by
all site scrapers.  Every scraper must subclass BaseScraper and implement the
three abstract methods.
"""
from __future__ import annotations

import abc
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

class RawListing(BaseModel):
    """Normalised product data emitted by every scraper.

    ``raw_payload`` carries the full source object (dict from JSON, parsed
    HTML attrs, etc.) so that future debugging never requires a re-scrape.
    """

    site: str                               # scraper identity, e.g. "primor"
    site_product_id: str                    # SKU / site-internal ID
    url: str                                # canonical product page URL
    name: str                               # name as it appears on the site
    brand: str                              # brand as it appears on the site
    image_url: str | None = None        # source image URL (no binary)
    price: Decimal                          # listing price
    currency: str = "EUR"
    in_stock: bool = True
    size_ml: int | None = None          # extracted from name when possible
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"price must be > 0, got {v}")
        return v

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper()

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseScraper(abc.ABC):
    """All site scrapers must implement this interface.

    Typical flow orchestrated by ``runner.py``::

        scraper = PrimorScraper()
        for cat_url in scraper.list_category_urls():
            for listing in scraper.scrape_category(cat_url):
                yield listing

    ``scrape_product`` is available for targeted single-product refreshes and
    is used as a fallback when category-level data is incomplete.
    """

    # Must be overridden by concrete subclasses.
    site: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "site", ""):
            raise TypeError(f"{cls.__name__} must define a non-empty class attribute 'site'")

    # -- abstract interface --------------------------------------------------

    @abc.abstractmethod
    def list_category_urls(self) -> list[str]:
        """Return all category/listing page URLs to scrape."""

    @abc.abstractmethod
    def scrape_category(self, url: str) -> Iterable[RawListing]:
        """Scrape a single category/listing page and yield RawListing objects."""

    @abc.abstractmethod
    def scrape_product(self, listing_url: str) -> RawListing:
        """Scrape a single product detail page and return a RawListing."""
