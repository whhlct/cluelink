from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
