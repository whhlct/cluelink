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
PREFIX wd: <http://www.wikidata.org/entity/>

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
PREFIX wd: <http://www.wikidata.org/entity/>

SELECT ?movie ?person WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie wdt:{property_id} ?person .
}}
""".strip()


def movie_imdb_id_query(movie_qids: list[str]) -> str:
    return _movie_value_query(movie_qids, "P345", "imdb_id")


def movie_genre_query(movie_qids: list[str]) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?movie ?genre ?genre_label WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie wdt:P136 ?genre .
  ?genre rdfs:label ?genre_label .
  FILTER(LANG(?genre_label) = "en")
}}
""".strip()


def movie_duration_query(movie_qids: list[str]) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?movie ?duration ?duration_unit WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie p:P2047 ?duration_statement .
  ?duration_statement psv:P2047 ?duration_value .
  ?duration_value wikibase:quantityAmount ?duration ;
                  wikibase:quantityUnit ?duration_unit .
}}
""".strip()


def movie_mpaa_rating_query(movie_qids: list[str]) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?movie ?rating ?rating_label WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie wdt:P1657 ?rating .
  ?rating rdfs:label ?rating_label .
  FILTER(LANG(?rating_label) = "en")
}}
""".strip()


def movie_release_query(movie_qids: list[str]) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?movie ?release_date ?precision ?place ?place_label WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie p:P577 ?release_statement .
  ?release_statement psv:P577 ?release_value .
  ?release_value wikibase:timeValue ?release_date ;
                 wikibase:timePrecision ?precision .
  OPTIONAL {{
    ?release_statement pq:P291 ?place .
    OPTIONAL {{
      ?place rdfs:label ?place_label .
      FILTER(LANG(?place_label) = "en")
    }}
  }}
}}
""".strip()


def enwiki_sitelink_query(entity_qids: list[str]) -> str:
    values = _values_clause(entity_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>

SELECT ?entity ?article WHERE {{
  VALUES ?entity {{ {values} }}
  ?article schema:about ?entity ;
           schema:isPartOf <https://en.wikipedia.org/> .
}}
""".strip()


def _movie_value_query(movie_qids: list[str], property_id: str, value_name: str) -> str:
    values = _values_clause(movie_qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

SELECT ?movie ?{value_name} WHERE {{
  VALUES ?movie {{ {values} }}
  ?movie wdt:{property_id} ?{value_name} .
}}
""".strip()


def _values_clause(qids: list[str]) -> str:
    if not qids:
        raise ValueError("at least one QID is required")
    if any(not _QID_PATTERN.fullmatch(qid) for qid in qids):
        raise ValueError("VALUES clauses require Wikidata QIDs")
    return " ".join(f"wd:{qid}" for qid in qids)
