from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from domain import Entity, EntityMetrics, Relation
from domain.enums import RelationType
from ingest.wikidata.database import (
    EntityExternalIdRow, EntityMetricsRow, EntityRow, RelationRow,
    WikidataMovieStageRow, WikidataPersonRow, WikidataPersonStageRow,
    WikidataRawRelationRow, WikidataRelationBatchRow, WikidataSelectedMovieRow,
)
from ingest.wikidata.models import WikidataRelationship


class PostgresWikidataStore:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(_async_database_url(database_url))
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def __aenter__(self) -> PostgresWikidataStore:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._engine.dispose()

    @staticmethod
    def canonical_id_for_qid(qid: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cluelink:wikidata:{qid}"))

    async def upsert_entity(self, entity: Entity) -> bool:
        async with self._sessions.begin() as session:
            is_new = await session.get(EntityRow, entity.id) is None
            await session.execute(insert(EntityRow).values(
                id=entity.id, name=entity.name, entity_type=entity.entity_type.value,
                aliases=entity.aliases, description=entity.description, attributes=entity.attributes,
            ).on_conflict_do_update(index_elements=[EntityRow.id], set_={
                "name": entity.name, "entity_type": entity.entity_type.value,
                "aliases": entity.aliases, "description": entity.description,
                "attributes": entity.attributes,
            }))
            for external_id in entity.external_ids:
                await session.execute(insert(EntityExternalIdRow).values(
                    entity_id=entity.id, source=external_id.source, value=external_id.value,
                ).on_conflict_do_update(
                    index_elements=[EntityExternalIdRow.source, EntityExternalIdRow.value],
                    set_={"entity_id": entity.id},
                ))
        return is_new

    async def upsert_metrics(self, metrics: EntityMetrics) -> None:
        values = asdict(metrics)
        async with self._sessions.begin() as session:
            await session.execute(insert(EntityMetricsRow).values(**values).on_conflict_do_update(
                index_elements=[EntityMetricsRow.entity_id],
                set_={key: value for key, value in values.items() if key != "entity_id"},
            ))

    async def mark_movie_selected(self, qid: str, entity_id: str) -> None:
        await self._upsert(insert(WikidataSelectedMovieRow).values(qid=qid, entity_id=entity_id).on_conflict_do_update(
            index_elements=[WikidataSelectedMovieRow.qid], set_={"entity_id": entity_id}
        ))

    async def movie_stage_complete(self, stage_key: str) -> bool:
        return await self._exists(select(WikidataMovieStageRow.stage_key).where(WikidataMovieStageRow.stage_key == stage_key))

    async def mark_movie_stage_complete(self, stage_key: str) -> None:
        await self._upsert(insert(WikidataMovieStageRow).values(stage_key=stage_key).on_conflict_do_nothing())

    async def iter_selected_movie_qids(self) -> AsyncIterator[str]:
        async for value in self._stream(select(WikidataSelectedMovieRow.qid).order_by(WikidataSelectedMovieRow.qid)):
            yield value

    async def relation_batch_complete(self, batch_key: str) -> bool:
        return await self._exists(select(WikidataRelationBatchRow.batch_key).where(WikidataRelationBatchRow.batch_key == batch_key))

    async def upsert_raw_relationships(self, relationships: Iterable[WikidataRelationship]) -> None:
        async with self._sessions.begin() as session:
            for relation in relationships:
                await session.execute(insert(WikidataRawRelationRow).values(
                    movie_qid=relation.movie_qid, person_qid=relation.person_qid,
                    relation_type=relation.relation_type.value, source_relation_id=relation.source_relation_id,
                ).on_conflict_do_nothing())
                await session.execute(insert(WikidataPersonRow).values(qid=relation.person_qid).on_conflict_do_nothing())

    async def mark_relation_batch_complete(self, batch_key: str) -> None:
        await self._upsert(insert(WikidataRelationBatchRow).values(batch_key=batch_key).on_conflict_do_nothing())

    async def iter_pending_person_qids(self) -> AsyncIterator[str]:
        query = select(WikidataPersonRow.qid).outerjoin(
            WikidataPersonStageRow, WikidataPersonRow.qid == WikidataPersonStageRow.qid
        ).where(WikidataPersonStageRow.qid.is_(None)).order_by(WikidataPersonRow.qid)
        async for value in self._stream(query):
            yield value

    async def mark_people_processed(self, qids: Iterable[str]) -> None:
        async with self._sessions.begin() as session:
            for qid in qids:
                await session.execute(insert(WikidataPersonStageRow).values(qid=qid).on_conflict_do_nothing())

    async def iter_raw_relationships(self) -> AsyncIterator[WikidataRelationship]:
        query = select(WikidataRawRelationRow).order_by(
            WikidataRawRelationRow.movie_qid, WikidataRawRelationRow.person_qid, WikidataRawRelationRow.relation_type
        )
        async with self._sessions() as session:
            stream = await session.stream_scalars(query)
            async for row in stream:
                yield WikidataRelationship(row.movie_qid, row.person_qid, RelationType(row.relation_type), row.source_relation_id)

    async def entity_id_for_wikidata_qid(self, qid: str) -> str | None:
        async with self._sessions() as session:
            return await session.scalar(select(EntityExternalIdRow.entity_id).where(
                EntityExternalIdRow.source == "wikidata", EntityExternalIdRow.value == qid
            ))

    async def upsert_relation(self, relation: Relation) -> bool:
        async with self._sessions.begin() as session:
            result = await session.execute(insert(RelationRow).values(
                source_entity_id=relation.source_entity_id, target_entity_id=relation.target_entity_id,
                relation_type=relation.relation_type.value, source=relation.source.value,
                source_relation_id=relation.source_relation_id, attributes=relation.attributes,
            ).on_conflict_do_nothing().returning(RelationRow.source_entity_id))
            return result.scalar_one_or_none() is not None

    async def _exists(self, query: object) -> bool:
        async with self._sessions() as session:
            return await session.scalar(query) is not None  # type: ignore[arg-type]

    async def _upsert(self, statement: object) -> None:
        async with self._sessions.begin() as session:
            await session.execute(statement)  # type: ignore[arg-type]

    async def _stream(self, query: object) -> AsyncIterator[str]:
        async with self._sessions() as session:
            stream = await session.stream_scalars(query)  # type: ignore[arg-type]
            async for value in stream:
                yield value


def _async_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url
