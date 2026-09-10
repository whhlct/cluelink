"""Add Wikidata movie metadata storage."""

from alembic import op
import sqlalchemy as sa


revision = "0002_movie_metadata"
down_revision = "0001_wikidata_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entity_external_ids", sa.Column("namespace", sa.String(), nullable=True))
    op.execute("UPDATE entity_external_ids SET namespace = source")
    op.alter_column("entity_external_ids", "namespace", nullable=False)
    op.drop_constraint("entity_external_ids_pkey", "entity_external_ids", type_="primary")
    op.create_primary_key(
        "entity_external_ids_pkey",
        "entity_external_ids",
        ["source", "namespace", "value"],
    )

    op.create_table(
        "movie_releases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("movie_entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("precision", sa.Integer(), nullable=False),
        sa.Column("publication_place_entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(), nullable=False),
    )
    op.create_table(
        "wikidata_movie_metadata_stages",
        sa.Column("batch_key", sa.String(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("wikidata_movie_metadata_stages")
    op.drop_table("movie_releases")
    op.drop_constraint("entity_external_ids_pkey", "entity_external_ids", type_="primary")
    op.create_primary_key("entity_external_ids_pkey", "entity_external_ids", ["source", "value"])
    op.drop_column("entity_external_ids", "namespace")
