"""Add checkpoints for Wikipedia pageview ingest."""

from alembic import op
import sqlalchemy as sa


revision = "0005_wikipedia_pageview_stages"
down_revision = "0004_wikipedia_pageview_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wikipedia_pageview_stages",
        sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("wikipedia_pageview_stages")
