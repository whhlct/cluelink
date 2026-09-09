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
PREFIX schema: <http://schema.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?movie ?label (COUNT(DISTINCT ?sitelink) AS ?sitelinks) WHERE {{
  ?movie wdt:P31 wd:Q11424 ;
         wdt:P577 ?release_date ;
         rdfs:label ?label .
  ?sitelink schema:about ?movie .
  FILTER(LANG(?label) = "en")
  FILTER(?release_date >= "{start_year:04d}-01-01T00:00:00Z"^^xsd:dateTime)
  FILTER(?release_date < "{end_year:04d}-01-01T00:00:00Z"^^xsd:dateTime)
}}
GROUP BY ?movie ?label
HAVING(COUNT(DISTINCT ?sitelink) >= {min_sitelinks})
""".strip()


def movies_without_release_date_query(
    min_sitelinks: int = MIN_MOVIE_SITELINKS,
) -> str:
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT ?movie ?label (COUNT(DISTINCT ?sitelink) AS ?sitelinks) WHERE {{
  ?movie wdt:P31 wd:Q11424 ;
         rdfs:label ?label .
  ?sitelink schema:about ?movie .
  FILTER(LANG(?label) = "en")
  FILTER NOT EXISTS {{ ?movie wdt:P577 ?release_date . }}
}}
GROUP BY ?movie ?label
HAVING(COUNT(DISTINCT ?sitelink) >= {min_sitelinks})
""".strip()


def cast_member_query(movie_qids: list[str]) -> str:
    return _movie_person_query(movie_qids, "P161")


def director_query(movie_qids: list[str]) -> str:
    return _movie_person_query(movie_qids, "P57")


def person_metadata_query(person_qids: list[str]) -> str:
    values = _values_clause(person_qids)
    return f"""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT ?person ?label (COUNT(DISTINCT ?sitelink) AS ?sitelinks) WHERE {{
  VALUES ?person {{ {values} }}
  ?person rdfs:label ?label .
  OPTIONAL {{ ?sitelink schema:about ?person . }}
  FILTER(LANG(?label) = "en")
}}
GROUP BY ?person ?label
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
