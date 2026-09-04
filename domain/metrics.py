from dataclasses import dataclass


@dataclass
class EntityMetrics:
    entity_id: str

    sitelink_count: int | None = None
    pageviews_30d: int | None = None
    pageviews_365d: int | None = None

    tmdb_popularity: float | None = None
    tmdb_vote_count: int | None = None

    graph_degree: int | None = None
    popularity_score: float | None = None
