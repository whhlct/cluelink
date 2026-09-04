from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.enums import RelationType, Source


@dataclass
class Relation:
    source_entity_id: str
    target_entity_id: str
    relation_type: RelationType
    source: Source

    source_relation_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
