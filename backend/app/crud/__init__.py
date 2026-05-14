"""CRUD helpers — import these from scrapers and routers."""
from app.crud.listings import upsert_listing  # noqa: F401
from app.crud.products import (  # noqa: F401
    get_brands,
    get_product_detail,
    get_product_history,
    get_products,
)
from app.crud.scrape_jobs import (  # noqa: F401
    complete_job,
    create_job,
    fail_job,
    get_job,
    log_error,
)
