from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class TMDBMovie:
    tmdb_id: int
    title: str

    original_title: str | None = None
    release_date: date | None = None

    popularity: float | None = None
    vote_count: int | None = None
    vote_average: float | None = None

    imdb_id: str | None = None


@dataclass
class TMDBPerson:
    tmdb_id: int
    name: str

    popularity: float | None = None
    known_for_department: str | None = None

    imdb_id: str | None = None


@dataclass
class TMDBCastCredit:
    movie_id: int
    person_id: int

    character: str | None = None
    order: int | None = None


@dataclass
class TMDBCrewCredit:
    movie_id: int
    person_id: int

    department: str | None = None
    job: str | None = None
