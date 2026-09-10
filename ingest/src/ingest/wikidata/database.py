from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class EntityExternalIdRow(Base):
    __tablename__ = "entity_external_ids"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    namespace: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)


class EntityMetricsRow(Base):
    __tablename__ = "entity_metrics"

    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    sitelink_count: Mapped[int | None] = mapped_column(Integer)
    pageviews_30d: Mapped[int | None] = mapped_column(Integer)
    pageviews_365d: Mapped[int | None] = mapped_column(Integer)
    tmdb_popularity: Mapped[float | None]
    tmdb_vote_count: Mapped[int | None] = mapped_column(Integer)
    graph_degree: Mapped[int | None] = mapped_column(Integer)
    popularity_score: Mapped[float | None]


class WikidataMovieStageRow(Base):
    __tablename__ = "wikidata_movie_stages"
    stage_key: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataMovieMetadataStageRow(Base):
    __tablename__ = "wikidata_movie_metadata_stages"
    batch_key: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataWikipediaSitelinkStageRow(Base):
    __tablename__ = "wikidata_wikipedia_sitelink_stages"
    batch_key: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataSelectedMovieRow(Base):
    __tablename__ = "wikidata_selected_movies"
    qid: Mapped[str] = mapped_column(String, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)


class WikidataRawRelationRow(Base):
    __tablename__ = "wikidata_raw_relations"
    movie_qid: Mapped[str] = mapped_column(String, primary_key=True)
    person_qid: Mapped[str] = mapped_column(String, primary_key=True)
    relation_type: Mapped[str] = mapped_column(String, primary_key=True)
    source_relation_id: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataRelationBatchRow(Base):
    __tablename__ = "wikidata_relation_batches"
    batch_key: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataPersonRow(Base):
    __tablename__ = "wikidata_people"
    qid: Mapped[str] = mapped_column(String, primary_key=True)


class WikidataPersonStageRow(Base):
    __tablename__ = "wikidata_person_stages"
    qid: Mapped[str] = mapped_column(String, primary_key=True)


class RelationRow(Base):
    __tablename__ = "relations"
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    source_relation_id: Mapped[str | None] = mapped_column(String)
    attributes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class MovieReleaseRow(Base):
    __tablename__ = "movie_releases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    movie_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    precision: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_place_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String, nullable=False)
