from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, unquote

import httpx

from domain import EntityMetrics
from ingest.wikidata.config import (
    WIKIPEDIA_PAGEVIEW_BATCH_SIZE,
    WIKIPEDIA_PAGEVIEW_CONCURRENCY,
    WIKIPEDIA_PAGEVIEW_REQUESTS_PER_MINUTE,
    WDQS_REQUEST_TIMEOUT,
    WDQS_RETRY_BACKOFF_SECONDS,
    WDQS_RETRY_COUNT,
    wdqs_user_agent,
)
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)
_PAGEVIEW_ENDPOINT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


class WikipediaPageviewError(RuntimeError):
    pass


class RequestRateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._interval = 60 / requests_per_minute
        self._next_request_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + self._interval
        if wait_seconds:
            await asyncio.sleep(wait_seconds)


class WikipediaPageviewClient:
    def __init__(
        self,
        requests_per_minute: int = WIKIPEDIA_PAGEVIEW_REQUESTS_PER_MINUTE,
        retry_count: int = WDQS_RETRY_COUNT,
        retry_backoff_seconds: float = WDQS_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.retry_count = retry_count
        self.retry_backoff_seconds = retry_backoff_seconds
        self._limiter = RequestRateLimiter(requests_per_minute)
        self._client = httpx.AsyncClient(
            headers={"Accept": "application/json", "User-Agent": wdqs_user_agent()},
            timeout=WDQS_REQUEST_TIMEOUT,
        )

    async def __aenter__(self) -> WikipediaPageviewClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_daily_pageviews(self, article: str, start: date, end: date) -> list[dict[str, Any]]:
        encoded_article = quote(unquote(article), safe="")
        url = "/".join((
            _PAGEVIEW_ENDPOINT,
            "en.wikipedia",
            "all-access",
            "user",
            encoded_article,
            "daily",
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
        ))

        for attempt in range(self.retry_count + 1):
            try:
                await self._limiter.acquire()
                response = await self._client.get(url)
                if response.status_code == 404:
                    return []
                if response.status_code == 429 or response.status_code >= 500:
                    raise WikipediaPageviewError(
                        f"Wikimedia returned transient HTTP {response.status_code}"
                    )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                items = payload["items"]
                if not isinstance(items, list):
                    raise TypeError("items is not a list")
                return items
            except (httpx.RequestError, WikipediaPageviewError) as error:
                if attempt == self.retry_count:
                    raise WikipediaPageviewError(
                        f"Wikimedia pageview request failed after {attempt + 1} attempts: {error}"
                    ) from error
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
            except httpx.HTTPStatusError as error:
                raise WikipediaPageviewError(
                    f"Wikimedia returned HTTP {error.response.status_code}: {error.response.text[:200]}"
                ) from error
            except (KeyError, TypeError, ValueError) as error:
                raise WikipediaPageviewError("Wikimedia returned an invalid pageview response") from error

        raise AssertionError("unreachable")


@dataclass(frozen=True)
class WikipediaPageviewTotals:
    pageviews_30d: int
    pageviews_365d: int


def calculate_pageview_totals(items: Iterable[dict[str, Any]], end: date) -> WikipediaPageviewTotals:
    thirty_day_start = end - timedelta(days=29)
    pageviews_30d = pageviews_365d = 0
    for item in items:
        try:
            item_date = datetime.strptime(str(item["timestamp"])[:8], "%Y%m%d").date()
            views = int(item["views"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping invalid Wikimedia pageview item: %s", item)
            continue
        pageviews_365d += views
        if item_date >= thirty_day_start:
            pageviews_30d += views
    return WikipediaPageviewTotals(pageviews_30d, pageviews_365d)


async def ingest_wikipedia_pageviews(
    store: PostgresWikidataStore,
    batch_size: int = WIKIPEDIA_PAGEVIEW_BATCH_SIZE,
    concurrency: int = WIKIPEDIA_PAGEVIEW_CONCURRENCY,
) -> None:
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=364)
    sitelinks = [sitelink async for sitelink in store.iter_pending_wikipedia_pageviews()]
    total = len(sitelinks)
    if not total:
        logger.info("No English Wikipedia pageviews are pending")
        return

    logger.info(
        "Fetching pageviews for %d articles from %s through %s at up to %d requests/minute",
        total,
        start,
        end,
        WIKIPEDIA_PAGEVIEW_REQUESTS_PER_MINUTE,
    )
    started_at = time.monotonic()
    completed = failed = 0
    error_counts: Counter[str] = Counter()
    semaphore = asyncio.Semaphore(concurrency)

    async with WikipediaPageviewClient() as client:
        for batch_start in range(0, total, batch_size):
            batch = sitelinks[batch_start:batch_start + batch_size]
            tasks = [asyncio.create_task(
                _fetch_pageview_metric(client, semaphore, entity_id, article, start, end)
            ) for entity_id, article in batch]
            metrics: list[EntityMetrics] = []

            for task in asyncio.as_completed(tasks):
                completed += 1
                try:
                    metrics.append(await task)
                except WikipediaPageviewError as error:
                    failed += 1
                    error_counts[str(error)] += 1

                if completed % 50 == 0 or completed == total:
                    elapsed = time.monotonic() - started_at
                    logger.info(
                        "Wikipedia pageviews: %d/%d complete (%.1f%%), %.2f requests/sec, %d failed",
                        completed,
                        total,
                        completed / total * 100,
                        completed / elapsed if elapsed else 0.0,
                        failed,
                    )

            await store.upsert_wikipedia_pageview_metrics(metrics)

    if error_counts:
        logger.warning("Wikipedia pageview failures by error: %s", dict(error_counts))
    logger.info("Wikipedia pageview ingest complete: %d fetched, %d failed", total - failed, failed)


async def _fetch_pageview_metric(
    client: WikipediaPageviewClient,
    semaphore: asyncio.Semaphore,
    entity_id: str,
    article: str,
    start: date,
    end: date,
) -> EntityMetrics:
    async with semaphore:
        items = await client.fetch_daily_pageviews(article, start, end)
    totals = calculate_pageview_totals(items, end)
    return EntityMetrics(
        entity_id=entity_id,
        wikipedia_pageviews_30d=totals.pageviews_30d,
        wikipedia_pageviews_365d=totals.pageviews_365d,
        wikipedia_pageviews_fetched_at=datetime.now(timezone.utc),
    )
