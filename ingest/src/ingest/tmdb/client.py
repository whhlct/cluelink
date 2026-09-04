from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ingest.tmdb.models import TMDBDiscoverMoviePage, TMDBMovie


class TMDBAPIError(RuntimeError):
    pass


class TMDBClient:
    base_url = "https://api.themoviedb.org/3"

    def __init__(self, api_token: str | None = None, timeout: float = 30.0) -> None:
        self.api_token = api_token or os.environ.get("TMDB_API_KEY")
        self.timeout = timeout

        if not self.api_token:
            raise ValueError("TMDB_API_KEY must be set or provided as api_token")

    def discover_movie(
        self,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
    ) -> TMDBDiscoverMoviePage:
        payload = self._get("/discover/movie", params)
        results = [self._movie_from_payload(movie) for movie in payload["results"]]

        return TMDBDiscoverMoviePage(
            page=payload["page"],
            results=results,
            total_pages=payload["total_pages"],
            total_results=payload["total_results"],
        )

    def _get(
        self,
        path: str,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
    ) -> dict[str, Any]:
        query = {
            key: self._query_value(value)
            for key, value in (params or {}).items()
            if value is not None
        }
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise TMDBAPIError(f"TMDB returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise TMDBAPIError(f"Could not reach TMDB: {error.reason}") from error

    @staticmethod
    def _query_value(value: str | int | float | bool | date) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _movie_from_payload(payload: Mapping[str, Any]) -> TMDBMovie:
        release_date = payload.get("release_date")

        return TMDBMovie(
            tmdb_id=payload["id"],
            title=payload["title"],
            original_title=payload.get("original_title"),
            release_date=date.fromisoformat(release_date) if release_date else None,
            popularity=payload.get("popularity"),
            vote_count=payload.get("vote_count"),
            vote_average=payload.get("vote_average"),
        )
