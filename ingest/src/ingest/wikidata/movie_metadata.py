from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date

from ingest.wikidata.client import WDQSClient
from ingest.wikidata.config import MOVIE_METADATA_REQUEST_BATCH_SIZE, RELATION_BATCH_SIZE
from ingest.wikidata.models import WikidataGenre, WikidataMovieRelease, qid_from_entity_uri
from ingest.wikidata.queries import (
    movie_duration_query,
    movie_genre_query,
    movie_imdb_id_query,
    movie_mpaa_rating_query,
    movie_release_query,
)
from ingest.wikidata.relations import _async_batches
from ingest.wikidata.storage import PostgresWikidataStore


logger = logging.getLogger(__name__)


def parse_imdb_id_bindings(bindings: Iterable[dict[str, dict[str, str]]]) -> dict[str, set[str]]:
    imdb_ids: dict[str, set[str]] = defaultdict(set)
    for binding in bindings:
        try:
            imdb_ids[qid_from_entity_uri(binding["movie"]["value"])].add(binding["imdb_id"]["value"])
        except (KeyError, ValueError):
            logger.warning("Skipping invalid IMDb ID binding: %s", binding)
    return dict(imdb_ids)


def parse_genre_bindings(bindings: Iterable[dict[str, dict[str, str]]]) -> list[WikidataGenre]:
    genres: list[WikidataGenre] = []
    for binding in bindings:
        try:
            genres.append(WikidataGenre(
                movie_qid=qid_from_entity_uri(binding["movie"]["value"]),
                qid=qid_from_entity_uri(binding["genre"]["value"]),
                label=binding["genre_label"]["value"],
            ))
        except (KeyError, ValueError):
            logger.warning("Skipping invalid genre binding: %s", binding)
    return genres


def parse_duration_bindings(bindings: Iterable[dict[str, dict[str, str]]]) -> dict[str, dict[str, object]]:
    durations: dict[str, set[tuple[float, str]]] = defaultdict(set)
    for binding in bindings:
        try:
            movie_qid = qid_from_entity_uri(binding["movie"]["value"])
            duration = float(binding["duration"]["value"])
            unit = binding["duration_unit"]["value"]
            try:
                unit = qid_from_entity_uri(unit)
            except ValueError:
                pass
            durations[movie_qid].add((duration, unit))
        except (KeyError, ValueError):
            logger.warning("Skipping invalid duration binding: %s", binding)

    return {
        movie_qid: {"duration": [{"value": value, "unit": unit} for value, unit in sorted(values)]}
        for movie_qid, values in durations.items()
    }


def parse_mpaa_rating_bindings(bindings: Iterable[dict[str, dict[str, str]]]) -> dict[str, dict[str, object]]:
    ratings: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for binding in bindings:
        try:
            movie_qid = qid_from_entity_uri(binding["movie"]["value"])
            rating_qid = qid_from_entity_uri(binding["rating"]["value"])
            ratings[movie_qid].add((rating_qid, binding["rating_label"]["value"]))
        except (KeyError, ValueError):
            logger.warning("Skipping invalid MPAA rating binding: %s", binding)

    return {
        movie_qid: {
            "mpaa_film_rating": [
                {"qid": rating_qid, "label": label}
                for rating_qid, label in sorted(values)
            ]
        }
        for movie_qid, values in ratings.items()
    }


def parse_release_bindings(bindings: Iterable[dict[str, dict[str, str]]]) -> list[WikidataMovieRelease]:
    releases: list[WikidataMovieRelease] = []
    for binding in bindings:
        try:
            movie_qid = qid_from_entity_uri(binding["movie"]["value"])
            release_date = date.fromisoformat(binding["release_date"]["value"].lstrip("+")[:10])
            precision = int(binding["precision"]["value"])
        except (KeyError, ValueError):
            logger.warning("Skipping invalid release binding: %s", binding)
            continue

        place_value = binding.get("place", {}).get("value")
        try:
            publication_place_qid = qid_from_entity_uri(place_value) if place_value else None
        except ValueError:
            publication_place_qid = None

        releases.append(WikidataMovieRelease(
            movie_qid=movie_qid,
            release_date=release_date,
            precision=precision,
            publication_place_qid=publication_place_qid,
            publication_place_label=binding.get("place_label", {}).get("value"),
        ))
    return releases


async def ingest_movie_metadata(
    client: WDQSClient,
    store: PostgresWikidataStore,
    batch_size: int = RELATION_BATCH_SIZE,
) -> None:
    batch_number = 0
    async for movie_qids in _async_batches(store.iter_selected_movie_qids(), batch_size):
        batch_number += 1
        batch_key = hashlib.sha256(",".join(movie_qids).encode()).hexdigest()
        if await store.movie_metadata_batch_complete(batch_key):
            continue

        logger.info("Starting movie metadata batch %d (%d movies)", batch_number, len(movie_qids))
        imdb_ids = parse_imdb_id_bindings(await _query_metadata(client, movie_imdb_id_query, movie_qids))
        genres = parse_genre_bindings(await _query_metadata(client, movie_genre_query, movie_qids))
        durations = parse_duration_bindings(await _query_metadata(client, movie_duration_query, movie_qids))
        ratings = parse_mpaa_rating_bindings(await _query_metadata(client, movie_mpaa_rating_query, movie_qids))
        releases = parse_release_bindings(await _query_metadata(client, movie_release_query, movie_qids))
        attributes = _merge_attributes(durations, ratings)

        await store.upsert_movie_metadata(imdb_ids, genres, releases, attributes)
        await store.mark_movie_metadata_batch_complete(batch_key)
        logger.info(
            "Completed movie metadata batch %d: %d IMDb IDs, %d genres, %d releases",
            batch_number,
            sum(map(len, imdb_ids.values())),
            len(genres),
            len(releases),
        )


def _merge_attributes(*attribute_sets: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for attribute_set in attribute_sets:
        for movie_qid, attributes in attribute_set.items():
            merged.setdefault(movie_qid, {}).update(attributes)
    return merged


async def _query_metadata(
    client: WDQSClient,
    query_factory: Callable[[list[str]], str],
    movie_qids: list[str],
) -> list[dict[str, dict[str, str]]]:
    bindings: list[dict[str, dict[str, str]]] = []
    for start in range(0, len(movie_qids), MOVIE_METADATA_REQUEST_BATCH_SIZE):
        query_qids = movie_qids[start:start + MOVIE_METADATA_REQUEST_BATCH_SIZE]
        bindings.extend(await client.query(query_factory(query_qids)))
    return bindings
