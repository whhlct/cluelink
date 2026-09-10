"""Rename pageview metrics and record fetch time."""

from alembic import op
import sqlalchemy as sa


revision = "0004_wikipedia_pageview_metrics"
down_revision = "0003_wikipedia_sitelink_stages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "entity_metrics",
        "pageviews_30d",
        new_column_name="wikipedia_pageviews_30d",
    )
    op.alter_column(
        "entity_metrics",
        "pageviews_365d",
        new_column_name="wikipedia_pageviews_365d",
    )
    op.add_column(
        "entity_metrics",
        sa.Column("wikipedia_pageviews_fetched_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("entity_metrics", "wikipedia_pageviews_fetched_at")
    op.alter_column(
        "entity_metrics",
        "wikipedia_pageviews_365d",
        new_column_name="pageviews_365d",
    )
    op.alter_column(
        "entity_metrics",
        "wikipedia_pageviews_30d",
        new_column_name="pageviews_30d",
    )
