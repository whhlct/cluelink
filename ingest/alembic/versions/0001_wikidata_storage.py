"""create Wikidata ingest storage

Revision ID: 0001_wikidata_storage
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_wikidata_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("entities", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.Text(), nullable=False), sa.Column("entity_type", sa.String(), nullable=False), sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("description", sa.Text()), sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.create_table("entity_external_ids", sa.Column("source", sa.String(), primary_key=True), sa.Column("value", sa.String(), primary_key=True), sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False))
    op.create_table("entity_metrics", sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True), sa.Column("sitelink_count", sa.Integer()), sa.Column("pageviews_30d", sa.Integer()), sa.Column("pageviews_365d", sa.Integer()), sa.Column("tmdb_popularity", sa.Float()), sa.Column("tmdb_vote_count", sa.Integer()), sa.Column("graph_degree", sa.Integer()), sa.Column("popularity_score", sa.Float()))
    op.create_table("wikidata_movie_stages", sa.Column("stage_key", sa.String(), primary_key=True))
    op.create_table("wikidata_selected_movies", sa.Column("qid", sa.String(), primary_key=True), sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False))
    op.create_table("wikidata_raw_relations", sa.Column("movie_qid", sa.String(), primary_key=True), sa.Column("person_qid", sa.String(), primary_key=True), sa.Column("relation_type", sa.String(), primary_key=True), sa.Column("source_relation_id", sa.String(), primary_key=True))
    op.create_table("wikidata_relation_batches", sa.Column("batch_key", sa.String(), primary_key=True))
    op.create_table("wikidata_people", sa.Column("qid", sa.String(), primary_key=True))
    op.create_table("wikidata_person_stages", sa.Column("qid", sa.String(), primary_key=True))
    op.create_table("relations", sa.Column("source_entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True), sa.Column("target_entity_id", sa.String(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True), sa.Column("relation_type", sa.String(), primary_key=True), sa.Column("source", sa.String(), primary_key=True), sa.Column("source_relation_id", sa.String()), sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"))


def downgrade() -> None:
    for table in ("relations", "wikidata_person_stages", "wikidata_people", "wikidata_relation_batches", "wikidata_raw_relations", "wikidata_selected_movies", "wikidata_movie_stages", "entity_metrics", "entity_external_ids", "entities"):
        op.drop_table(table)
