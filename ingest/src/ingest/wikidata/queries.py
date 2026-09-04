from __future__ import annotations

import re

from ingest.wikidata.config import MIN_MOVIE_SITELINKS


_QID_PATTERN = re.compile(r"Q\d+")


def movie_query(
    start_year: int,
    end_year: int,
    min_sitelinks: int = MIN_MOVIE_SITELINKS,
) -> str:
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?movie ?label ?sitelinks WHERE {{
  ?movie wdt:P31 wd:Q11424 ;
         wdt:P577 ?release_date ;
         rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  FILTER(?release_date >= "{start_year:04d}-01-01T00:00:00Z"^^xsd:dateTime)
  FILTER(?release_date < "{end_year:04d}-01-01T00:00:00Z"^^xsd:dateTime)
  BIND(wikibase:sitelinks(?movie) AS ?sitelinks)
  FILTER(?sitelinks >= {min_sitelinks})
}}
""".strip()


def movies_without_release_date_query(
    min_sitelinks: int = MIN_MOVIE_SITELINKS,
) -> str:
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?movie ?label ?sitelinks WHERE {{
  ?movie wdt:P31 wd:Q11424 ;
         rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  FILTER NOT EXISTS {{ ?movie wdt:P577 ?release_date . }}
  BIND(wikibase:sitelinks(?movie) AS ?sitelinks)
  FILTER(?sitelinks >= {min_sitelinks})
}}
""".strip()


def cast_member_query(movie_qids: list[str]) -> str:
    return _movie_person_query(movie_qids, "P161")


def director_query(movie_qids: list[str]) -> str:
    return _movie_person_query(movie_qids, "P57")


def person_metadata_query(person_qids: list[str]) -> str:
    values = _values_clause(person_qids)
    return f"""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?person ?label ?sitelinks WHERE {{
  VALUES ?person {{ {values} }}
  ?person rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  OPTIONAL {{ BIND(wikibase:sitelinks(?person) AS ?sitelinks) }}
}}
""".strip()


def _movie_person_query(movie_qids: list[str], property_id: str) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

SELECT ?movie ?person WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie wdt:{property_id} ?person .
}}
""".strip()


def _values_clause(qids: list[str]) -> str:
    if not qids:
        raise ValueError("at least one QID is required")
    if any(not _QID_PATTERN.fullmatch(qid) for qid in qids):
        raise ValueError("VALUES clauses require Wikidata QIDs")
    return " ".join(f"wd:{qid}" for qid in qids)
