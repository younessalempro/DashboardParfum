"""SQLAlchemy ORM models — import all so Alembic can detect them."""
from app.models.canonical_product import CanonicalProduct  # noqa: F401
from app.models.listing import Listing  # noqa: F401
from app.models.match_review_queue import MatchReviewQueue  # noqa: F401
from app.models.price_snapshot import PriceSnapshot  # noqa: F401
from app.models.scrape_error import ScrapeError  # noqa: F401
from app.models.scrape_job import ScrapeJob  # noqa: F401

__all__ = [
    "CanonicalProduct",
    "Listing",
    "PriceSnapshot",
    "ScrapeJob",
    "ScrapeError",
    "MatchReviewQueue",
]
