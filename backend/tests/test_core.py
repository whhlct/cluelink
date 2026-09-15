import unittest

from backend.core import CoreGraph, GraphEdge, GraphNode


class CoreGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = CoreGraph(
            {
                "p1": GraphNode("p1", "Anchor Person", "person", 100),
                "m1": GraphNode("m1", "First Movie", "movie", 60),
                "p2": GraphNode("p2", "Second Person", "person", 50),
                "m2": GraphNode("m2", "Target Movie", "movie", 90),
            },
            {
                "p1": [GraphEdge("m1", "acted_in")],
                "m1": [GraphEdge("p1", "acted_in"), GraphEdge("p2", "acted_in")],
                "p2": [GraphEdge("m1", "acted_in"), GraphEdge("m2", "directed")],
                "m2": [GraphEdge("p2", "directed")],
            },
        )

    def test_shortest_path_respects_depth(self) -> None:
        self.assertIsNone(self.graph.shortest_path("p1", "m2", max_depth=2))
        self.assertEqual(self.graph.shortest_path("p1", "m2", max_depth=3), ["p1", "m1", "p2", "m2"])

    def test_search_and_pageview_thresholds(self) -> None:
        self.assertEqual([node.id for node in self.graph.search("movie")], ["m2", "m1"])
        self.assertEqual(self.graph.percentile("movie", 0.5), 60)
        self.assertEqual([node.id for node in self.graph.nodes_of_type("person", 100)], ["p1"])


if __name__ == "__main__":
    unittest.main()
