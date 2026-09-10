from dataclasses import dataclass
from datetime import datetime


@dataclass
class EntityMetrics:
    entity_id: str

    sitelink_count: int | None = None
    wikipedia_pageviews_30d: int | None = None
    wikipedia_pageviews_365d: int | None = None
    wikipedia_pageviews_fetched_at: datetime | None = None

    tmdb_popularity: float | None = None
    tmdb_vote_count: int | None = None

    graph_degree: int | None = None
    popularity_score: float | None = None
