from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class GraphNode:
    id: str
    name: str
    entity_type: str
    pageviews: int | None

    def payload(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "entity_type": self.entity_type}


@dataclass(frozen=True)
class GraphEdge:
    other_id: str
    relation_type: str


class CoreGraph:
    def __init__(self, nodes: dict[str, GraphNode], adjacency: dict[str, list[GraphEdge]]) -> None:
        self.nodes = nodes
        self.adjacency = adjacency

    @classmethod
    async def load(cls, session: AsyncSession) -> CoreGraph:
        node_rows = await session.execute(text("""
            WITH latest AS (SELECT max(month) AS month FROM wikipedia_monthly_pageviews)
            SELECT e.id, e.name, e.entity_type, p.pageviews
            FROM entities e
            LEFT JOIN latest l ON true
            LEFT JOIN wikipedia_monthly_pageviews p ON p.entity_id = e.id AND p.month = l.month
            WHERE e.entity_type IN ('person', 'movie')
        """))
        nodes = {
            row.id: GraphNode(row.id, row.name, row.entity_type, row.pageviews)
            for row in node_rows
        }
        adjacency: dict[str, list[GraphEdge]] = {node_id: [] for node_id in nodes}
        relation_rows = await session.execute(text("""
            SELECT source_entity_id, target_entity_id, relation_type
            FROM relations
            WHERE relation_type IN ('acted_in', 'directed') AND source = 'wikidata'
        """))
        for row in relation_rows:
            if row.source_entity_id in nodes and row.target_entity_id in nodes:
                adjacency[row.source_entity_id].append(GraphEdge(row.target_entity_id, row.relation_type))
                adjacency[row.target_entity_id].append(GraphEdge(row.source_entity_id, row.relation_type))
        return cls(nodes, adjacency)

    def edge(self, source_id: str, target_id: str) -> GraphEdge | None:
        return next((edge for edge in self.adjacency.get(source_id, []) if edge.other_id == target_id), None)

    def shortest_path(self, source_id: str, target_id: str, max_depth: int = 8) -> list[str] | None:
        if source_id == target_id:
            return [source_id]
        queue: deque[list[str]] = deque([[source_id]])
        visited = {source_id}
        while queue:
            path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue
            for edge in self.adjacency.get(path[-1], []):
                if edge.other_id in visited:
                    continue
                candidate = [*path, edge.other_id]
                if edge.other_id == target_id:
                    return candidate
                visited.add(edge.other_id)
                queue.append(candidate)
        return None

    def search(self, query: str, entity_type: str | None = None, limit: int = 10) -> list[GraphNode]:
        normalized = query.casefold().strip()
        if not normalized:
            return []
        results = [
            node for node in self.nodes.values()
            if normalized in node.name.casefold() and (entity_type is None or node.entity_type == entity_type)
        ]
        return sorted(results, key=lambda node: (node.pageviews or 0, node.name), reverse=True)[:limit]

    def percentile(self, entity_type: str, percentile: float) -> float:
        values = sorted(node.pageviews for node in self.nodes.values() if node.entity_type == entity_type and node.pageviews is not None)
        if not values:
            return 0
        return values[min(len(values) - 1, int((len(values) - 1) * percentile))]

    def nodes_of_type(self, entity_type: str, minimum_pageviews: float) -> Iterable[GraphNode]:
        return (
            node for node in self.nodes.values()
            if node.entity_type == entity_type and (node.pageviews or 0) >= minimum_pageviews
        )


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(self._async_url(database_url))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _async_url(url: str) -> str:
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        return url

    async def dispose(self) -> None:
        await self.engine.dispose()
