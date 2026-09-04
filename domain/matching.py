from dataclasses import dataclass

from domain.enums import Source


@dataclass
class EntityMatch:
    source_a: Source
    source_a_id: str

    source_b: Source
    source_b_id: str

    confidence: float
    match_method: str
