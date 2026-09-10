"""Add English Wikipedia sitelink ingest checkpoints."""

from alembic import op
import sqlalchemy as sa


revision = "0003_wikipedia_sitelink_stages"
down_revision = "0002_movie_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wikidata_wikipedia_sitelink_stages",
        sa.Column("batch_key", sa.String(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("wikidata_wikipedia_sitelink_stages")
