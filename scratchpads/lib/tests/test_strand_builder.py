"""Tests for strand_builder.py pure functions."""
import pytest
from dataclasses import asdict
from unittest.mock import patch, MagicMock

from lib.strand_builder import (
    extract_tree_tweet_ids,
    StrandSeed,
    get_strand_seeds,
    _has_semantic_seeds,
    SemanticSearchFailedError,
)


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


class TestHasSemanticSeeds:
    """Tests for _has_semantic_seeds helper function."""

    def test_returns_true_for_semantic_search(self):
        seeds = [
            StrandSeed(tweet_id=1, source_type="root"),
            StrandSeed(tweet_id=2, source_type="semantic_search"),
        ]
        assert _has_semantic_seeds(seeds) is True

    def test_returns_true_for_quote_of_semantic(self):
        seeds = [
            StrandSeed(tweet_id=1, source_type="root"),
            StrandSeed(tweet_id=2, source_type="quote_of_semantic_search"),
        ]
        assert _has_semantic_seeds(seeds) is True

    def test_returns_false_for_only_root_and_quotes(self):
        seeds = [
            StrandSeed(tweet_id=1, source_type="root"),
            StrandSeed(tweet_id=2, source_type="quote_of_root"),
        ]
        assert _has_semantic_seeds(seeds) is False

    def test_returns_false_for_empty_list(self):
        assert _has_semantic_seeds([]) is False

    def test_returns_false_for_only_root(self):
        seeds = [StrandSeed(tweet_id=1, source_type="root")]
        assert _has_semantic_seeds(seeds) is False


class TestSemanticSearchFailedError:
    """Tests for SemanticSearchFailedError exception."""

    def test_stores_failed_ids(self):
        err = SemanticSearchFailedError(failed_ids=[1, 2, 3], total_ids=10)
        assert err.failed_ids == [1, 2, 3]
        assert err.total_ids == 10

    def test_message_includes_count(self):
        err = SemanticSearchFailedError(failed_ids=[1, 2, 3], total_ids=10)
        assert "3/10" in str(err)

    def test_message_shows_first_five_ids(self):
        err = SemanticSearchFailedError(failed_ids=[1, 2, 3, 4, 5, 6, 7], total_ids=20)
        assert "[1, 2, 3, 4, 5]" in str(err)


class TestGetStrandSeeds:
    """Tests for get_strand_seeds aggregation logic."""

    @pytest.fixture
    def tweet_dict_for_seeds(self):
        """Tweet dict with various relationships for testing seed aggregation."""
        return {
            # Root tweet
            1001: {
                "tweet_id": 1001,
                "full_text": "This is the root tweet about AI",
                "quoted_tweet_id": None,
                "quoted_count": 50,
                "username": "root_user",
            },
            # Direct quote of root
            1002: {
                "tweet_id": 1002,
                "full_text": "Quoting the root",
                "quoted_tweet_id": 1001,
                "quoted_count": 10,
                "username": "quoter1",
            },
            # Another quote of root
            1003: {
                "tweet_id": 1003,
                "full_text": "Another quote of root",
                "quoted_tweet_id": 1001,
                "quoted_count": 5,
                "username": "quoter2",
            },
            # Semantic search result
            2001: {
                "tweet_id": 2001,
                "full_text": "Related AI discussion",
                "quoted_tweet_id": None,
                "quoted_count": 30,
                "username": "semantic1",
            },
            # Quote of semantic result
            2002: {
                "tweet_id": 2002,
                "full_text": "Quoting the related tweet",
                "quoted_tweet_id": 2001,
                "quoted_count": 2,
                "username": "quoter3",
            },
            # Another semantic result
            2003: {
                "tweet_id": 2003,
                "full_text": "More AI stuff",
                "quoted_tweet_id": None,
                "quoted_count": 20,
                "username": "semantic2",
            },
        }

    @pytest.fixture
    def quote_dict(self):
        """Quote tweets dict: tweet_id -> list of tweet_ids that quote it."""
        return {
            1001: [1002, 1003],  # Root is quoted by 1002 and 1003
            2001: [2002],        # Semantic result 2001 is quoted by 2002
        }

    def test_includes_root_as_first_seed(self, tweet_dict_for_seeds, quote_dict):
        """Root tweet should always be first seed."""
        with patch('lib.strand_builder._semantic_search_for_strands', return_value=[]):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        assert len(seeds) >= 1
        assert seeds[0].tweet_id == 1001
        assert seeds[0].source_type == "root"

    def test_includes_quotes_of_root(self, tweet_dict_for_seeds, quote_dict):
        """Direct quotes of root should be included as quote_of_root."""
        with patch('lib.strand_builder._semantic_search_for_strands', return_value=[]):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        seed_ids = {s.tweet_id for s in seeds}
        assert 1002 in seed_ids
        assert 1003 in seed_ids

        quote_seeds = [s for s in seeds if s.source_type == "quote_of_root"]
        quote_ids = {s.tweet_id for s in quote_seeds}
        assert quote_ids == {1002, 1003}

    def test_includes_semantic_search_results(self, tweet_dict_for_seeds, quote_dict):
        """Semantic search results should be included."""
        mock_semantic_results = [
            tweet_dict_for_seeds[2001],
            tweet_dict_for_seeds[2003],
        ]

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=mock_semantic_results):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        semantic_seeds = [s for s in seeds if s.source_type == "semantic_search"]
        semantic_ids = {s.tweet_id for s in semantic_seeds}
        assert semantic_ids == {2001, 2003}

    def test_includes_quotes_of_semantic_results(self, tweet_dict_for_seeds, quote_dict):
        """Quotes of semantic search results should be included."""
        mock_semantic_results = [tweet_dict_for_seeds[2001]]

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=mock_semantic_results):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        quote_of_semantic = [s for s in seeds if s.source_type == "quote_of_semantic_search"]
        assert len(quote_of_semantic) == 1
        assert quote_of_semantic[0].tweet_id == 2002

    def test_deduplicates_seeds(self, tweet_dict_for_seeds, quote_dict):
        """Duplicate tweet IDs should be removed, keeping first occurrence."""
        # Simulate semantic search returning the root tweet (which is already included)
        mock_semantic_results = [
            tweet_dict_for_seeds[1001],  # Duplicate of root
            tweet_dict_for_seeds[2001],
        ]

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=mock_semantic_results):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        # Count occurrences of each tweet_id
        id_counts = {}
        for s in seeds:
            id_counts[s.tweet_id] = id_counts.get(s.tweet_id, 0) + 1

        # Each ID should appear exactly once
        for tid, count in id_counts.items():
            assert count == 1, f"Tweet {tid} appears {count} times"

    def test_preserves_order_root_first(self, tweet_dict_for_seeds, quote_dict):
        """Order should be: root, quotes of root, semantic, quotes of semantic."""
        mock_semantic_results = [tweet_dict_for_seeds[2001]]

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=mock_semantic_results):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        source_types = [s.source_type for s in seeds]

        # Root should come first
        assert source_types[0] == "root"

        # Find indices of each type
        root_idx = source_types.index("root")
        quote_root_indices = [i for i, t in enumerate(source_types) if t == "quote_of_root"]
        semantic_indices = [i for i, t in enumerate(source_types) if t == "semantic_search"]

        # Quotes of root should come before semantic
        if quote_root_indices and semantic_indices:
            assert max(quote_root_indices) < min(semantic_indices)

    def test_handles_missing_root_tweet(self, quote_dict):
        """Should handle case where root tweet is not in tweet_dict."""
        empty_tweet_dict = {}

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=[]):
            seeds = get_strand_seeds(9999, empty_tweet_dict, quote_dict)

        # Should still have root seed even if tweet data is missing
        assert len(seeds) >= 1
        assert seeds[0].tweet_id == 9999
        assert seeds[0].source_type == "root"

    def test_handles_no_quotes(self, tweet_dict_for_seeds):
        """Should work when there are no quotes of root."""
        empty_quote_dict = {}

        with patch('lib.strand_builder._semantic_search_for_strands', return_value=[]):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, empty_quote_dict)

        assert len(seeds) == 1
        assert seeds[0].source_type == "root"

    def test_handles_no_semantic_results(self, tweet_dict_for_seeds, quote_dict):
        """Should work when semantic search returns nothing."""
        with patch('lib.strand_builder._semantic_search_for_strands', return_value=[]):
            seeds = get_strand_seeds(1001, tweet_dict_for_seeds, quote_dict)

        # Should have root + quotes of root
        source_types = {s.source_type for s in seeds}
        assert "root" in source_types
        assert "quote_of_root" in source_types
        assert "semantic_search" not in source_types

