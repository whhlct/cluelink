import asyncio
import unittest

import httpx

from domain.enums import RelationType
from ingest.wikidata.models import qid_from_entity_uri
from ingest.wikidata.client import WDQSClient
from ingest.wikidata.movies import parse_movie_bindings
from ingest.wikidata.people import parse_person_bindings
from ingest.wikidata.queries import movie_query
from ingest.wikidata.relations import parse_relation_bindings


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
