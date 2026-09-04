from __future__ import annotations

import os
from datetime import date
from typing import Any, AsyncIterator, Mapping

import httpx

from ingest.tmdb.models import (
    TMDBCastCredit,
    TMDBCrewCredit,
    TMDBDiscoverMoviePage,
    TMDBMovie,
    TMDBMovieCredits,
)


class TMDBAPIError(RuntimeError):
    pass


class TMDBClient:
    base_url = "https://api.themoviedb.org/3"

    def __init__(self, api_token: str | None = None, timeout: float = 30.0) -> None:
        self.api_token = api_token or os.environ.get("TMDB_API_KEY")
        self.timeout = timeout

        if not self.api_token:
            raise ValueError("TMDB_API_KEY must be set or provided as api_token")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_token}",
            },
            timeout=self.timeout,
        )

    async def __aenter__(self) -> TMDBClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def discover_movie(
        self,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
    ) -> TMDBDiscoverMoviePage:
        payload = await self._get("/discover/movie", params)
        results = [self._movie_from_payload(movie) for movie in payload["results"]]

        return TMDBDiscoverMoviePage(
            page=payload["page"],
            results=results,
            total_pages=payload["total_pages"],
            total_results=payload["total_results"],
        )

    async def movie_credits(
        self,
        movie_id: int,
        language: str | None = None,
    ) -> TMDBMovieCredits:
        params = {"language": language} if language else None
        payload = await self._get(f"/movie/{movie_id}/credits", params)
        returned_movie_id = payload["id"]

        return TMDBMovieCredits(
            movie_id=returned_movie_id,
            cast=[
                TMDBCastCredit(
                    movie_id=returned_movie_id,
                    person_id=credit["id"],
                    character=credit.get("character"),
                    order=credit.get("order"),
                )
                for credit in payload["cast"]
            ],
            crew=[
                TMDBCrewCredit(
                    movie_id=returned_movie_id,
                    person_id=credit["id"],
                    department=credit.get("department"),
                    job=credit.get("job"),
                )
                for credit in payload["crew"]
            ],
        )

    async def discover_movies(
        self,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
        limit: int | None = None,
    ) -> list[TMDBMovie]:
        return [movie async for movie in self.iter_discover_movies(params, limit)]

    async def iter_discover_movies(
        self,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[TMDBMovie]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        query = dict(params or {})
        page_number = int(query.pop("page", 1))
        movie_count = 0

        while limit is None or movie_count < limit:
            page = await self.discover_movie({**query, "page": page_number})
            for movie in page.results:
                yield movie
                movie_count += 1

                if limit is not None and movie_count >= limit:
                    return

            if not page.results or page_number >= page.total_pages:
                break

            page_number += 1

    async def _get(
        self,
        path: str,
        params: Mapping[str, str | int | float | bool | date | None] | None = None,
    ) -> dict[str, Any]:
        query = {
            key: self._query_value(value)
            for key, value in (params or {}).items()
            if value is not None
        }

        try:
            response = await self._client.get(
                path,
                params=query,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            response = error.response
            raise TMDBAPIError(
                f"TMDB returned HTTP {response.status_code}: {response.text}"
            ) from error
        except httpx.RequestError as error:
            raise TMDBAPIError(f"Could not reach TMDB: {error}") from error
        except ValueError as error:
            raise TMDBAPIError("TMDB returned an invalid JSON response") from error

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
