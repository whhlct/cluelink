"""Store monthly Wikipedia pageview totals."""

from alembic import op
import sqlalchemy as sa


revision = "0006_wikipedia_monthly_pageviews"
down_revision = "0005_wikipedia_pageview_stages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wikipedia_monthly_pageviews",
        sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("pageviews", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("wikipedia_monthly_pageviews")
