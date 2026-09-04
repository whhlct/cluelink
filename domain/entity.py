from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.enums import EntityType


@dataclass(frozen=True)
class ExternalId:
    source: str
    value: str


@dataclass
class Entity:
    id: str
    name: str
    entity_type: EntityType

    external_ids: list[ExternalId] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
