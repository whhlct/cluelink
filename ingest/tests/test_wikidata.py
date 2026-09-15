import asyncio
import unittest
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path

import httpx

from domain.enums import RelationType
from ingest.wikidata.models import qid_from_entity_uri
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.movies import parse_movie_bindings
from ingest.wikidata.monthly_pageviews import (
    aggregate_enwiki_monthly_pageviews,
    monthly_dump,
    parse_monthly_pageview_line,
    previous_month,
)
from ingest.wikidata.movie_metadata import (
    parse_duration_bindings,
    parse_genre_bindings,
    parse_imdb_id_bindings,
    parse_mpaa_rating_bindings,
    parse_release_bindings,
)
from ingest.wikidata.people import parse_person_bindings
from ingest.wikidata.pageviews import calculate_pageview_totals
from ingest.wikidata.queries import movie_query
from ingest.wikidata.relations import parse_relation_bindings
from ingest.wikidata.wikipedia_sitelinks import parse_enwiki_sitelink_bindings


class WikidataIngestTests(unittest.TestCase):
    def test_qid_from_entity_uri(self):
        self.assertEqual(
            qid_from_entity_uri("http://www.wikidata.org/entity/Q25188"), "Q25188"
        )

    def test_movie_parsing_applies_default_sitelink_threshold(self):
        movies = parse_movie_bindings([
            {"movie": {"value": "http://www.wikidata.org/entity/Q1"}, "label": {"value": "Included"}, "sitelinks": {"value": "20"}},
            {"movie": {"value": "http://www.wikidata.org/entity/Q2"}, "label": {"value": "Excluded"}, "sitelinks": {"value": "19"}},
        ])
        self.assertEqual([(movie.qid, movie.sitelink_count) for movie in movies], [("Q1", 20)])
        self.assertIn("HAVING(COUNT(DISTINCT ?sitelink) >= 20)", movie_query(2000, 2001))

    def test_person_parsing(self):
        people = parse_person_bindings([
            {"person": {"value": "http://www.wikidata.org/entity/Q3"}, "label": {"value": "Person"}, "sitelinks": {"value": "7"}}
        ])
        self.assertEqual((people[0].qid, people[0].sitelink_count), ("Q3", 7))

    def test_relation_mapping_keeps_person_to_movie_direction(self):
        bindings = [{"movie": {"value": "http://www.wikidata.org/entity/Q10"}, "person": {"value": "http://www.wikidata.org/entity/Q20"}}]
        cast = parse_relation_bindings(bindings, RelationType.ACTED_IN, "P161")[0]
        director = parse_relation_bindings(bindings, RelationType.DIRECTED, "P57")[0]
        self.assertEqual((cast.person_qid, cast.movie_qid, cast.relation_type), ("Q20", "Q10", RelationType.ACTED_IN))
        self.assertEqual((director.person_qid, director.movie_qid, director.relation_type), ("Q20", "Q10", RelationType.DIRECTED))

    def test_relation_parsing_skips_non_entity_values(self):
        relationships = parse_relation_bindings([
            {"movie": {"value": "http://www.wikidata.org/entity/Q10"}, "person": {"value": "http://www.wikidata.org/.well-known/genid/unknown"}}
        ], RelationType.ACTED_IN, "P161")
        self.assertEqual(relationships, [])

    def test_movie_metadata_parsing(self):
        movie = "http://www.wikidata.org/entity/Q10"
        self.assertEqual(parse_imdb_id_bindings([
            {"movie": {"value": movie}, "imdb_id": {"value": "tt0111161"}}
        ]), {"Q10": {"tt0111161"}})
        self.assertEqual(parse_genre_bindings([
            {
                "movie": {"value": movie},
                "genre": {"value": "http://www.wikidata.org/entity/Q130232"},
                "genre_label": {"value": "drama"},
            }
        ])[0].qid, "Q130232")
        self.assertEqual(parse_duration_bindings([
            {
                "movie": {"value": movie},
                "duration": {"value": "142"},
                "duration_unit": {"value": "http://www.wikidata.org/entity/Q7727"},
            }
        ])["Q10"], {"duration": [{"value": 142.0, "unit": "Q7727"}]})
        self.assertEqual(parse_mpaa_rating_bindings([
            {
                "movie": {"value": movie},
                "rating": {"value": "http://www.wikidata.org/entity/Q118867"},
                "rating_label": {"value": "R"},
            }
        ])["Q10"], {"mpaa_film_rating": [{"qid": "Q118867", "label": "R"}]})
        release = parse_release_bindings([
            {
                "movie": {"value": movie},
                "release_date": {"value": "+1994-09-10T00:00:00Z"},
                "precision": {"value": "11"},
                "place": {"value": "http://www.wikidata.org/entity/Q30"},
                "place_label": {"value": "United States"},
            }
        ])[0]
        self.assertEqual((release.release_date.isoformat(), release.precision, release.publication_place_qid), ("1994-09-10", 11, "Q30"))

    def test_english_wikipedia_sitelink_parsing_keeps_underscored_title(self):
        sitelinks = parse_enwiki_sitelink_bindings([
            {
                "entity": {"value": "http://www.wikidata.org/entity/Q120"},
                "article": {"value": "https://en.wikipedia.org/wiki/The_Dark_Knight_(film)"},
            }
        ])
        self.assertEqual(sitelinks, {"Q120": "The_Dark_Knight_(film)"})

    def test_pageview_totals_use_30_day_window_within_365_day_response(self):
        totals = calculate_pageview_totals([
            {"timestamp": "2025080100", "views": 10},
            {"timestamp": "2025070200", "views": 20},
            {"timestamp": "2025070100", "views": 30},
        ], end=date(2025, 8, 1))
        self.assertEqual((totals.pageviews_30d, totals.pageviews_365d), (10, 60))

    def test_monthly_pageview_dump_uses_previous_month_and_expected_filename(self):
        self.assertEqual(previous_month(date(2026, 9, 9)), date(2026, 8, 1))
        dump = monthly_dump(date(2026, 8, 1))
        self.assertEqual(dump.compressed_path.name, "pageviews-202608-user.bz2")
        self.assertEqual(dump.extracted_path.name, "pageviews-202608-user")

    def test_monthly_pageview_aggregation_sums_access_types_per_title(self):
        self.assertEqual(
            parse_monthly_pageview_line(b"en.wikipedia The_Dark_Knight_(film) 123 desktop 10 A10\n"),
            ("en.wikipedia", "The_Dark_Knight_(film)", "123", "desktop", 10),
        )
        with TemporaryDirectory() as directory:
            dump = monthly_dump(date(2026, 8, 1), Path(directory))
            dump.extracted_path.write_bytes(
                b"en.wikipedia The_Dark_Knight_(film) 123 desktop 10 A10\n"
                b"en.wikipedia The_Dark_Knight_(film) 123 mobile-web 5 A5\n"
                b"en.wikipedia Zed 124 desktop 2 A2\n"
                b"fr.wikipedia Zed 124 desktop 100 A100\n"
            )
            aggregate_enwiki_monthly_pageviews(dump)
            self.assertEqual(
                dump.aggregate_path.read_text(encoding="utf-8"),
                "The_Dark_Knight_(film)\t15\nZed\t2\n",
            )

    def test_wdqs_client_retries_transient_response(self):
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, json={"results": {"bindings": [{"movie": {"value": "Q1"}}]}}, request=request)

        async def query():
            client = WDQSClient(retry_count=1, retry_backoff_seconds=0)
            await client._client.aclose()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                return await client.query("SELECT * WHERE {}")
            finally:
                await client.aclose()

        self.assertEqual(asyncio.run(query()), [{"movie": {"value": "Q1"}}])
        self.assertEqual(attempts, 2)

    def test_wdqs_client_retries_invalid_json_response(self):
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(200, text="temporarily unavailable", request=request)
            return httpx.Response(200, json={"results": {"bindings": []}}, request=request)

        async def query():
            client = WDQSClient(retry_count=1, retry_backoff_seconds=0)
            await client._client.aclose()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                return await client.query("SELECT * WHERE {}")
            finally:
                await client.aclose()

        self.assertEqual(asyncio.run(query()), [])
        self.assertEqual(attempts, 2)
