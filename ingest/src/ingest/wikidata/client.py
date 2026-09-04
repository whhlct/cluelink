from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ingest.wikidata.config import (
    WDQS_ENDPOINT,
    WDQS_REQUEST_TIMEOUT,
    WDQS_RETRY_BACKOFF_SECONDS,
    WDQS_RETRY_COUNT,
    wdqs_user_agent,
)


logger = logging.getLogger(__name__)


class WDQSClientError(RuntimeError):
    pass


class WDQSClient:
    def __init__(
        self,
        endpoint: str = WDQS_ENDPOINT,
        retry_count: int = WDQS_RETRY_COUNT,
        timeout: float = WDQS_REQUEST_TIMEOUT,
        retry_backoff_seconds: float = WDQS_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.endpoint = endpoint
        self.retry_count = retry_count
        self.retry_backoff_seconds = retry_backoff_seconds
        self._client = httpx.AsyncClient(
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": wdqs_user_agent(),
            },
            timeout=timeout,
        )

    async def __aenter__(self) -> WDQSClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def query(self, sparql: str) -> list[dict[str, dict[str, str]]]:
        for attempt in range(self.retry_count + 1):
            try:
                response = await self._client.get(
                    self.endpoint,
                    params={"query": sparql, "format": "json"},
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise WDQSClientError(
                        f"WDQS returned transient HTTP {response.status_code}"
                    )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                return payload["results"]["bindings"]
            except (httpx.RequestError, WDQSClientError) as error:
                if attempt == self.retry_count:
                    raise WDQSClientError(
                        f"WDQS query failed after {attempt + 1} attempts: {error}"
                    ) from error

                delay = self.retry_backoff_seconds * (2**attempt)
                logger.warning(
                    "WDQS request failed (%s); retrying in %.1f seconds (%d/%d)",
                    error,
                    delay,
                    attempt + 1,
                    self.retry_count,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as error:
                raise WDQSClientError(
                    f"WDQS returned HTTP {error.response.status_code}: {error.response.text}"
                ) from error
            except (KeyError, ValueError) as error:
                raise WDQSClientError("WDQS returned an invalid JSON bindings response") from error

        raise AssertionError("unreachable")
