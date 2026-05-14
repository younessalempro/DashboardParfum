"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-09

Creates all six tables:
  canonical_product, listing, price_snapshot,
  scrape_job, scrape_error, match_review_queue
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums (idempotent via DO block — PG14 lacks CREATE TYPE IF NOT EXISTS)
    # Use postgresql.ENUM(create_type=False) in column defs so SA never double-creates.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE gender_enum AS ENUM ('men', 'women', 'unisex');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE site_enum AS ENUM ('primor', 'sephora', 'nocibe');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE scrape_job_status_enum AS ENUM ('running', 'done', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE review_status_enum AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # --- canonical_product ---
    op.create_table(
        "canonical_product",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("size_ml", sa.Integer, nullable=True),
        sa.Column(
            "gender",
            postgresql.ENUM("men", "women", "unisex", name="gender_enum", create_type=False),
            nullable=True,
        ),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("brand", "name", "size_ml", name="uq_canonical_brand_name_size"),
    )
    op.create_index("ix_canonical_product_brand", "canonical_product", ["brand"])

    # --- listing ---
    op.create_table(
        "listing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "canonical_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "site",
            postgresql.ENUM("primor", "sephora", "nocibe", name="site_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("site_product_id", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("name_on_site", sa.Text, nullable=True),
        sa.Column("brand_on_site", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("site", "site_product_id", name="uq_listing_site_product"),
    )
    op.create_index("ix_listing_canonical_product_id", "listing", ["canonical_product_id"])
    op.create_index("ix_listing_site", "listing", ["site"])

    # --- price_snapshot ---
    op.create_table(
        "price_snapshot",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="EUR"),
        sa.Column("in_stock", sa.Boolean, nullable=True),
        sa.Column(
            "scraped_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_price_snapshot_listing_scraped",
        "price_snapshot",
        ["listing_id", sa.text("scraped_at DESC")],
    )
    op.create_index("ix_price_snapshot_scraped_at", "price_snapshot", ["scraped_at"])

    # --- scrape_job ---
    op.create_table(
        "scrape_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "status",
            postgresql.ENUM("running", "done", "failed", name="scrape_job_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("sites", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("items_added", sa.Integer, server_default="0", nullable=False),
        sa.Column("items_updated", sa.Integer, server_default="0", nullable=False),
        sa.Column("items_errored", sa.Integer, server_default="0", nullable=False),
    )

    # --- scrape_error ---
    op.create_table(
        "scrape_error",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("traceback", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_scrape_error_job_id", "scrape_error", ["job_id"])

    # --- match_review_queue ---
    op.create_table(
        "match_review_queue",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_canonical_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "approved", "rejected", name="review_status_enum", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_match_review_queue_listing_id", "match_review_queue", ["listing_id"])
    op.create_index("ix_match_review_queue_status", "match_review_queue", ["status"])


def downgrade() -> None:
    op.drop_table("match_review_queue")
    op.drop_table("scrape_error")
    op.drop_table("scrape_job")
    op.drop_table("price_snapshot")
    op.drop_table("listing")
    op.drop_table("canonical_product")

    op.execute("DROP TYPE IF EXISTS review_status_enum")
    op.execute("DROP TYPE IF EXISTS scrape_job_status_enum")
    op.execute("DROP TYPE IF EXISTS site_enum")
    op.execute("DROP TYPE IF EXISTS gender_enum")
