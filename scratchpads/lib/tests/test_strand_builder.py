"""Tests for strand_builder.py pure functions."""
import pytest
from dataclasses import asdict

from lib.strand_builder import extract_tree_tweet_ids, StrandSeed


class TestExtractTreeTweetIds:
    def test_extracts_all_ids(self, sample_conversation_tree):
        trees = {100: sample_conversation_tree}
        result = extract_tree_tweet_ids(trees)
        assert result == {1001, 1002, 1003}

    def test_multiple_trees(self):
        trees = {
            100: {
                "root": 1,
                "parents": {2: 1},
                "children": {1: [2], 2: []},
            },
            200: {
                "root": 10,
                "parents": {11: 10},
                "children": {10: [11], 11: []},
            },
        }
        result = extract_tree_tweet_ids(trees)
        assert result == {1, 2, 10, 11}

    def test_empty_trees(self):
        result = extract_tree_tweet_ids({})
        assert result == set()

    def test_tree_without_root(self):
        tree = {
            "root": None,
            "parents": {2: 1},
            "children": {1: [2], 2: []},
        }
        result = extract_tree_tweet_ids({100: tree})
        assert 1 in result
        assert 2 in result

    def test_tree_with_multiple_children(self):
        tree = {
            "root": 1,
            "parents": {2: 1, 3: 1, 4: 2},
            "children": {1: [2, 3], 2: [4], 3: [], 4: []},
        }
        result = extract_tree_tweet_ids({100: tree})
        assert result == {1, 2, 3, 4}


class TestStrandSeed:
    def test_dataclass_fields(self):
        seed = StrandSeed(tweet_id=123, source_type="root")
        assert seed.tweet_id == 123
        assert seed.source_type == "root"

    def test_serialization_to_dict(self):
        seed = StrandSeed(tweet_id=456, source_type="semantic_search")
        d = asdict(seed)
        assert d == {"tweet_id": 456, "source_type": "semantic_search"}

    def test_all_source_types(self):
        types = ["root", "semantic_search", "quote_of_root", "quote_of_semantic_search"]
        for t in types:
            seed = StrandSeed(tweet_id=1, source_type=t)
            assert seed.source_type == t

    def test_json_serializable(self):
        import json
        seed = StrandSeed(tweet_id=789, source_type="quote_of_root")
        json_str = json.dumps(asdict(seed))
        parsed = json.loads(json_str)
        assert parsed == {"tweet_id": 789, "source_type": "quote_of_root"}

