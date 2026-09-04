from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from domain.enums import RelationType


_QID_PATTERN = re.compile(r"Q\d+")
_ENTITY_URI_PATTERN = re.compile(r"https?://www\.wikidata\.org/entity/(Q\d+)")


def qid_from_entity_uri(value: str) -> str:
    if _QID_PATTERN.fullmatch(value):
        return value

    match = _ENTITY_URI_PATTERN.fullmatch(value)
    if match:
        return match.group(1)

    raise ValueError(f"Not a Wikidata entity URI: {value}")


@dataclass
class WikidataEntity:
    qid: str

    label: str | None = None
    description: str | None = None
    aliases: list[str] = field(default_factory=list)

    instance_of: list[str] = field(default_factory=list)
    claims: dict[str, list[Any]] = field(default_factory=dict)

    sitelink_count: int | None = None
    enwiki_title: str | None = None


@dataclass(frozen=True)
class WikidataMovieRecord:
    qid: str
    label: str
    sitelink_count: int


@dataclass(frozen=True)
class WikidataPersonRecord:
    qid: str
    label: str
    sitelink_count: int | None


@dataclass(frozen=True)
class WikidataRelationship:
    movie_qid: str
    person_qid: str
    relation_type: RelationType
    source_relation_id: str
