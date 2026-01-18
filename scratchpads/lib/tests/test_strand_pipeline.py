"""
Comprehensive tests for the strand processing pipeline.

Tests cover:
1. URL cleaning for semantic search queries
2. Semantic backup caching (save, load, invalidation)
3. Semantic search retry logic when filtered results < limit
4. Histogram generation from thread text
5. Pipeline resumption / crash recovery
6. Strand file I/O operations
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch, call

# Module imports - these will be imported when tests run
# We use pytest fixtures to set up the environment


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory structure."""
    data_dir = tmp_path / "data"
    strands_dir = data_dir / "strands"
    rated_dir = data_dir / "rated_strands"
    backup_dir = data_dir / "semantic_search_backups"

    data_dir.mkdir()
    strands_dir.mkdir()
    rated_dir.mkdir()
    backup_dir.mkdir()

    return {
        "root": tmp_path,
        "data": data_dir,
        "strands": strands_dir,
        "rated": rated_dir,
        "backups": backup_dir,
    }


@pytest.fixture
def sample_tweet_dict():
    """Sample tweet dictionary for testing."""
    return {
        1001: {
            "tweet_id": 1001,
            "full_text": "Check out this amazing article https://t.co/abc123 about AI",
            "quoted_tweet_id": None,
            "quoted_count": 50,
            "username": "user1",
        },
        1002: {
            "tweet_id": 1002,
            "full_text": "RT @someone: This is a retweet",
            "quoted_tweet_id": None,
            "quoted_count": 10,
            "username": "user2",
        },
        1003: {
            "tweet_id": 1003,
            "full_text": "Direct quote of 1001",
            "quoted_tweet_id": 1001,  # Direct quote of seed
            "quoted_count": 5,
            "username": "user3",
        },
        1004: {
            "tweet_id": 1004,
            "full_text": "Related discussion about AI and ML",
            "quoted_tweet_id": None,
            "quoted_count": 30,
            "username": "user4",
        },
        1005: {
            "tweet_id": 1005,
            "full_text": "Another related tweet",
            "quoted_tweet_id": None,
            "quoted_count": 20,
            "username": "user5",
        },
    }


@pytest.fixture
def sample_rated_strand():
    """Sample rated strand data."""
    return {
        "seed_tweet_id": 1001,
        "thread_text": """
[2023-01-15] @user1: First tweet
[2023-01-20] @user2: Reply to first
[2023-02-10] @user3: Another reply
[2023-02-15] @user4: More discussion
[2024-06-01] @user5: Late addition
""",
        "seeds": [
            {"tweet_id": 1001, "source_type": "root"},
            {"tweet_id": 1004, "source_type": "semantic_search"},
        ],
        "rating": {
            "rating": 7,
            "essential_tweets": [
                {"tweet_id": "1001", "annotation": "Original insight"}
            ]
        },
        "title": "AI Discussion Thread",
        "summary": "A discussion about AI developments.",
        "histogram": {
            "counts": [0] * 132,  # 11 years * 12 months
            "total_tweets": 5,
            "date_range": {"start": "2015-01", "end": "2025-12"}
        }
    }


# =============================================================================
# 1. URL Cleaning Tests
# =============================================================================

class TestUrlCleaning:
    """Tests for _clean_search_query function."""

    def test_removes_t_co_urls(self):
        """t.co URLs should be removed."""
        from lib.strand_builder import _clean_search_query

        text = "Check this https://t.co/abc123 out"
        result = _clean_search_query(text)
        assert result == "Check this out"

    def test_removes_twitter_com_urls(self):
        """twitter.com URLs should be removed."""
        from lib.strand_builder import _clean_search_query

        text = "Visit https://twitter.com/user/status/123456 for details"
        result = _clean_search_query(text)
        assert result == "Visit for details"

    def test_removes_x_com_urls(self):
        """x.com URLs should be removed."""
        from lib.strand_builder import _clean_search_query

        text = "See https://x.com/username/status/789 here"
        result = _clean_search_query(text)
        assert result == "See here"

    def test_preserves_other_urls(self):
        """Non-Twitter URLs should be preserved."""
        from lib.strand_builder import _clean_search_query

        text = "Read https://example.com/article about this topic"
        result = _clean_search_query(text)
        assert result == "Read https://example.com/article about this topic"

    def test_handles_multiple_twitter_urls(self):
        """Multiple Twitter URLs in same text."""
        from lib.strand_builder import _clean_search_query

        text = "Link 1: https://t.co/a and link 2: https://x.com/b and more"
        result = _clean_search_query(text)
        assert result == "Link 1: and link 2: and more"

    def test_handles_mixed_urls(self):
        """Mix of Twitter and non-Twitter URLs."""
        from lib.strand_builder import _clean_search_query

        text = "Twitter https://t.co/a and website https://example.com/b"
        result = _clean_search_query(text)
        assert "https://example.com/b" in result
        assert "t.co" not in result

    def test_handles_no_urls(self):
        """Text without URLs should pass through unchanged."""
        from lib.strand_builder import _clean_search_query

        text = "Just a regular tweet about something interesting"
        result = _clean_search_query(text)
        assert result == text

    def test_handles_empty_string(self):
        """Empty string should return empty string."""
        from lib.strand_builder import _clean_search_query

        result = _clean_search_query("")
        assert result == ""

    def test_collapses_multiple_spaces(self):
        """Multiple spaces after URL removal should be collapsed."""
        from lib.strand_builder import _clean_search_query

        text = "Before   https://t.co/abc   after"
        result = _clean_search_query(text)
        # Should have single space, not multiple
        assert "  " not in result

    def test_handles_http_without_s(self):
        """http:// (not https://) URLs should also be removed."""
        from lib.strand_builder import _clean_search_query

        text = "Old link http://t.co/old123 here"
        result = _clean_search_query(text)
        assert "t.co" not in result


# =============================================================================
# 2. Semantic Backup Caching Tests
# =============================================================================

class TestSemanticBackupCaching:
    """Tests for semantic search backup save/load/invalidation."""

    def test_save_and_load_backup(self, temp_data_dir):
        """Backup should be saveable and loadable."""
        from lib.semantic_backups import save_semantic_backup, load_semantic_backup, get_backup_path

        # Patch the backup directory
        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            tweet_id = 12345
            search_params = {"k": 100, "max_k": 200, "threshold": 0.5, "exclude_keywords": []}
            result_ids = [1001, 1002, 1003, 1004, 1005]

            # Save
            save_semantic_backup(tweet_id, search_params, result_ids)

            # Load
            loaded = load_semantic_backup(tweet_id, search_params)

            assert loaded is not None
            assert loaded == result_ids

    def test_load_returns_none_when_no_backup(self, temp_data_dir):
        """Loading non-existent backup should return None."""
        from lib.semantic_backups import load_semantic_backup

        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            search_params = {"k": 100, "max_k": 200, "threshold": 0.5, "exclude_keywords": []}
            loaded = load_semantic_backup(99999, search_params)

            assert loaded is None

    def test_backup_invalidation_by_params(self, temp_data_dir):
        """Backup with different params should return None."""
        from lib.semantic_backups import save_semantic_backup, load_semantic_backup

        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            tweet_id = 12345
            params_v1 = {"k": 100, "max_k": 200, "threshold": 0.5, "exclude_keywords": []}
            params_v2 = {"k": 200, "max_k": 400, "threshold": 0.5, "exclude_keywords": []}  # Different k
            result_ids = [1001, 1002]

            # Save with params_v1
            save_semantic_backup(tweet_id, params_v1, result_ids)

            # Load with params_v2 - should return None (params don't match)
            loaded = load_semantic_backup(tweet_id, params_v2)

            assert loaded is None

    def test_backup_invalidation_by_time(self, temp_data_dir):
        """Backup older than 24 hours should return None."""
        from lib.semantic_backups import save_semantic_backup, load_semantic_backup, get_backup_path

        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            tweet_id = 12345
            search_params = {"k": 100, "max_k": 200, "threshold": 0.5, "exclude_keywords": []}
            result_ids = [1001, 1002]

            # Save backup
            save_semantic_backup(tweet_id, search_params, result_ids)

            # Manually modify timestamp to be 25 hours old
            backup_path = get_backup_path(tweet_id)
            with open(backup_path) as f:
                data = json.load(f)

            old_time = datetime.now() - timedelta(hours=25)
            data["timestamp"] = old_time.isoformat()

            with open(backup_path, "w") as f:
                json.dump(data, f)

            # Load should return None (too old)
            loaded = load_semantic_backup(tweet_id, search_params)

            assert loaded is None

    def test_backup_with_empty_results_returns_none(self, temp_data_dir):
        """Backup with empty results should return None on load."""
        from lib.semantic_backups import save_semantic_backup, load_semantic_backup

        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            tweet_id = 12345
            search_params = {"k": 100, "max_k": 200, "threshold": 0.5, "exclude_keywords": []}

            # Save empty results
            save_semantic_backup(tweet_id, search_params, [])

            # Load should return None
            loaded = load_semantic_backup(tweet_id, search_params)

            assert loaded is None

    def test_cleanup_old_backups(self, temp_data_dir):
        """Cleanup should remove files older than max_age_hours."""
        from lib.semantic_backups import cleanup_old_backups
        import os
        import time

        backup_dir = temp_data_dir["root"] / "data" / "semantic_search_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create some backup files
        old_file = backup_dir / "111.json"
        new_file = backup_dir / "222.json"

        old_file.write_text('{"test": "old"}')
        new_file.write_text('{"test": "new"}')

        # Set old_file mtime to 8 days ago
        old_mtime = time.time() - (8 * 24 * 3600)
        os.utime(old_file, (old_mtime, old_mtime))

        with patch('lib.semantic_backups.SCRATCHPADS_DIR', temp_data_dir["root"]):
            removed = cleanup_old_backups(max_age_hours=24 * 7)  # 7 days

        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()


# =============================================================================
# 3. Semantic Search Retry Logic Tests
# =============================================================================

class TestSemanticSearchRetry:
    """Tests for semantic search retry when filtered results < limit."""

    def test_retry_doubles_k_when_under_limit(self, sample_tweet_dict):
        """Should retry with doubled k when filtered results are below limit."""
        from lib.strand_builder import _semantic_search_for_strands

        # Mock search_embeddings to return results that get filtered down
        call_count = []

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            call_count.append(k)
            # Return fewer results initially, more on retry
            if k == 100:
                # 15 results, but some will be filtered out
                return [{"key": str(1002 + i)} for i in range(15)]
            else:
                # More results on retry
                return [{"key": str(1002 + i)} for i in range(30)]

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    # Tweet dict where 1002 is RT (filtered), 1003 is direct quote (filtered)
                    tweet_dict = {
                        1001: {
                            "tweet_id": 1001,
                            "full_text": "Original tweet",
                            "quoted_tweet_id": None,
                            "quoted_count": 50,
                        },
                        **{
                            1002 + i: {
                                "tweet_id": 1002 + i,
                                "full_text": f"Related tweet {i}",
                                "quoted_tweet_id": None,
                                "quoted_count": 10 - i,
                            }
                            for i in range(30)
                        }
                    }
                    # Make first few results be RTs or direct quotes
                    tweet_dict[1002]["full_text"] = "RT @someone: This is filtered"
                    tweet_dict[1003]["quoted_tweet_id"] = 1001

                    results = _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=tweet_dict,
                        limit=20,
                        k=100,
                        max_k=400,
                        debug=False
                    )

        # Should have retried with higher k
        assert len(call_count) >= 1
        # If first call returned fewer than limit after filtering, should have retried

    def test_no_retry_when_limit_met(self, sample_tweet_dict):
        """Should not retry when we have enough results."""
        from lib.strand_builder import _semantic_search_for_strands

        call_count = []

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            call_count.append(k)
            # Return 25 good results on first try
            return [{"key": str(2000 + i)} for i in range(25)]

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    tweet_dict = {
                        1001: {
                            "tweet_id": 1001,
                            "full_text": "Original tweet",
                            "quoted_tweet_id": None,
                        },
                        **{
                            2000 + i: {
                                "tweet_id": 2000 + i,
                                "full_text": f"Good tweet {i}",
                                "quoted_tweet_id": None,
                                "quoted_count": 10,
                            }
                            for i in range(25)
                        }
                    }

                    results = _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=tweet_dict,
                        limit=20,
                        k=100,
                        max_k=400
                    )

        # Should only call once since we got enough results
        assert len(call_count) == 1

    def test_respects_max_k_limit(self):
        """Retry should stop at max_k, not go forever."""
        from lib.strand_builder import _semantic_search_for_strands

        call_ks = []

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            call_ks.append(k)
            # Always return just 5 results (below any limit)
            return [{"key": str(i)} for i in range(5)]

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    tweet_dict = {
                        1001: {
                            "tweet_id": 1001,
                            "full_text": "Test tweet",
                            "quoted_tweet_id": None,
                        },
                        **{i: {"tweet_id": i, "full_text": f"Tweet {i}", "quoted_tweet_id": None, "quoted_count": 1} for i in range(5)}
                    }

                    _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=tweet_dict,
                        limit=50,  # High limit we'll never reach
                        k=100,
                        max_k=200  # Should stop here
                    )

        # Should have called with 100, then 200, then stopped
        assert max(call_ks) <= 200

    def test_uses_cleaned_query(self):
        """Should use URL-cleaned query for semantic search."""
        from lib.strand_builder import _semantic_search_for_strands

        captured_queries = []

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            captured_queries.append(query)
            return []

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    tweet_dict = {
                        1001: {
                            "tweet_id": 1001,
                            "full_text": "Check https://t.co/abc123 this article",
                            "quoted_tweet_id": None,
                        }
                    }

                    _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=tweet_dict,
                        limit=20,
                        k=100,
                        max_k=200
                    )

        assert len(captured_queries) >= 1
        # Query should not contain t.co URL
        assert "t.co" not in captured_queries[0]
        assert "Check" in captured_queries[0]
        assert "article" in captured_queries[0]


# =============================================================================
# 4. Histogram Generation Tests
# =============================================================================

class TestHistogramGeneration:
    """Tests for histogram generation from thread text."""

    def test_parses_dates_correctly(self):
        """Should correctly parse [YYYY-MM-DD] format dates."""
        from lib.histogram import generate_histogram

        thread_text = """
[2023-01-15] @user1: First tweet
[2023-01-20] @user2: Second tweet same month
[2023-02-10] @user3: Different month
"""
        result = generate_histogram(thread_text)

        assert result["total_tweets"] == 3
        # Jan 2023 should have 2, Feb 2023 should have 1
        jan_2023_idx = (2023 - 2015) * 12 + 0  # January is month 0
        feb_2023_idx = (2023 - 2015) * 12 + 1

        assert result["counts"][jan_2023_idx] == 2
        assert result["counts"][feb_2023_idx] == 1

    def test_handles_empty_text(self):
        """Empty text should return zeroed histogram."""
        from lib.histogram import generate_histogram

        result = generate_histogram("")

        assert result["total_tweets"] == 0
        assert all(c == 0 for c in result["counts"])

    def test_handles_no_dates(self):
        """Text without dates should return zeroed histogram."""
        from lib.histogram import generate_histogram

        thread_text = "Just some text without any date markers"
        result = generate_histogram(thread_text)

        assert result["total_tweets"] == 0

    def test_ignores_out_of_range_dates(self):
        """Dates outside 2015-2025 range should be ignored."""
        from lib.histogram import generate_histogram

        thread_text = """
[2014-12-01] @user1: Too old
[2020-06-15] @user2: In range
[2026-01-01] @user3: Too new
"""
        result = generate_histogram(thread_text)

        assert result["total_tweets"] == 1  # Only the 2020 tweet

    def test_date_range_format(self):
        """Date range should have correct format."""
        from lib.histogram import generate_histogram

        result = generate_histogram("[2020-01-01] test")

        assert result["date_range"]["start"] == "2015-01"
        assert result["date_range"]["end"] == "2025-12"

    def test_counts_array_length(self):
        """Counts array should cover full date range."""
        from lib.histogram import generate_histogram

        result = generate_histogram("")

        # 11 years (2015-2025) * 12 months = 132
        expected_months = (2025 - 2015 + 1) * 12
        assert len(result["counts"]) == expected_months


class TestHistogramExport:
    """Tests for histogram export generation."""

    def test_generates_months_array(self):
        """Export should include complete months array."""
        from lib.histogram import generate_histogram_export

        strands = {
            "1001": {
                "histogram": {
                    "counts": [0] * 132,
                    "total_tweets": 5,
                    "date_range": {"start": "2015-01", "end": "2025-12"}
                }
            }
        }

        export = generate_histogram_export(strands)

        assert "months" in export
        assert len(export["months"]) == 132
        assert export["months"][0]["date"] == "2015-01"

    def test_includes_all_strands(self):
        """Export should include all provided strands."""
        from lib.histogram import generate_histogram_export

        strands = {
            "1001": {"histogram": {"counts": [1] * 132, "total_tweets": 10}},
            "1002": {"histogram": {"counts": [2] * 132, "total_tweets": 20}},
        }

        export = generate_histogram_export(strands)

        assert "1001" in export["strands"]
        assert "1002" in export["strands"]

    def test_handles_missing_histogram(self):
        """Should handle strands without histogram gracefully."""
        from lib.histogram import generate_histogram_export

        strands = {
            "1001": {}  # No histogram
        }

        export = generate_histogram_export(strands)

        assert "1001" in export["strands"]
        # Should have default zeros
        assert export["strands"]["1001"]["histogram"] == [0] * 132


# =============================================================================
# 5. Pipeline Resumption Tests
# =============================================================================

class TestPipelineResumption:
    """Tests for pipeline crash recovery and resumption."""

    def test_get_built_strand_ids(self, temp_data_dir):
        """Should correctly identify already-built strands."""
        # Create some strand files
        (temp_data_dir["strands"] / "1001.json").write_text("{}")
        (temp_data_dir["strands"] / "1002.json").write_text("{}")
        (temp_data_dir["strands"] / "invalid.json").write_text("{}")  # Non-numeric name

        # Patch STRANDS_DIR
        with patch('strands.STRANDS_DIR', temp_data_dir["strands"]):
            from strands import get_built_strand_ids

            built = get_built_strand_ids()

        assert built == {1001, 1002}
        assert "invalid" not in built

    def test_get_rated_strand_ids(self, temp_data_dir):
        """Should correctly identify already-rated strands."""
        # Create some rated files
        (temp_data_dir["rated"] / "1001.json").write_text("{}")
        (temp_data_dir["rated"] / "1003.json").write_text("{}")

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import get_rated_strand_ids

            rated = get_rated_strand_ids()

        assert rated == {1001, 1003}

    def test_phase_build_skips_rated_strands(self, temp_data_dir):
        """Phase 1 should skip strands that are already rated."""
        # Create a rated strand
        rated_data = {"seed_tweet_id": 1001, "rating": {"rating": 7}}
        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(rated_data))

        # Mock dependencies
        with patch('strands.STRANDS_DIR', temp_data_dir["strands"]):
            with patch('strands.RATED_DIR', temp_data_dir["rated"]):
                from strands import get_built_strand_ids, get_rated_strand_ids

                rated_ids = get_rated_strand_ids()
                built_ids = get_built_strand_ids()

                all_target_ids = [1001, 1002, 1003]
                strand_target_ids = [
                    tid for tid in all_target_ids
                    if tid not in rated_ids and tid not in built_ids
                ]

        # 1001 should be skipped (already rated)
        assert 1001 not in strand_target_ids
        assert 1002 in strand_target_ids
        assert 1003 in strand_target_ids

    def test_phase_build_skips_built_strands(self, temp_data_dir):
        """Phase 1 should skip strands that are already built."""
        # Create a built (but not rated) strand
        built_data = {"tweet_id": 1001, "thread_text": "test", "seeds": []}
        (temp_data_dir["strands"] / "1001.json").write_text(json.dumps(built_data))

        with patch('strands.STRANDS_DIR', temp_data_dir["strands"]):
            with patch('strands.RATED_DIR', temp_data_dir["rated"]):
                from strands import get_built_strand_ids, get_rated_strand_ids

                rated_ids = get_rated_strand_ids()
                built_ids = get_built_strand_ids()

                all_target_ids = [1001, 1002, 1003]
                strand_target_ids = [
                    tid for tid in all_target_ids
                    if tid not in rated_ids and tid not in built_ids
                ]

        assert 1001 not in strand_target_ids
        assert 1002 in strand_target_ids

    def test_phase_rate_skips_rated_strands(self, temp_data_dir):
        """Phase 2 should only rate unrated strands."""
        # Create built strands
        (temp_data_dir["strands"] / "1001.json").write_text(
            json.dumps({"thread_text": "test1"})
        )
        (temp_data_dir["strands"] / "1002.json").write_text(
            json.dumps({"thread_text": "test2"})
        )

        # Create one rated strand
        (temp_data_dir["rated"] / "1001.json").write_text(
            json.dumps({"rating": {"rating": 7}})
        )

        with patch('strands.STRANDS_DIR', temp_data_dir["strands"]):
            with patch('strands.RATED_DIR', temp_data_dir["rated"]):
                from strands import get_rated_strand_ids

                rated_ids = get_rated_strand_ids()
                strands_data = {}

                for path in temp_data_dir["strands"].glob("*.json"):
                    tid = int(path.stem)
                    if tid in rated_ids:
                        continue
                    with open(path) as f:
                        data = json.load(f)
                    if data.get("thread_text", "").strip():
                        strands_data[tid] = data

        # Only 1002 should need rating
        assert 1001 not in strands_data
        assert 1002 in strands_data

    def test_phase_summary_skips_strands_with_summaries(self, temp_data_dir, sample_rated_strand):
        """Phase 3 should skip strands that already have summaries."""
        # Strand with summary
        (temp_data_dir["rated"] / "1001.json").write_text(
            json.dumps({**sample_rated_strand, "title": "Has Title", "summary": "Has summary"})
        )

        # Strand without summary
        strand_no_summary = {**sample_rated_strand, "seed_tweet_id": 1002}
        del strand_no_summary["title"]
        del strand_no_summary["summary"]
        (temp_data_dir["rated"] / "1002.json").write_text(json.dumps(strand_no_summary))

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import load_all_rated_strands

            all_strands = load_all_rated_strands()
            pending = [
                sid for sid, data in all_strands.items()
                if not data.get("title") or not data.get("summary")
            ]

        assert 1001 not in pending
        assert 1002 in pending

    def test_phase_histogram_skips_strands_with_histograms(self, temp_data_dir, sample_rated_strand):
        """Phase 4 should skip strands that already have histograms."""
        # Strand with histogram
        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(sample_rated_strand))

        # Strand without histogram
        strand_no_hist = {**sample_rated_strand, "seed_tweet_id": 1002}
        del strand_no_hist["histogram"]
        (temp_data_dir["rated"] / "1002.json").write_text(json.dumps(strand_no_hist))

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import load_all_rated_strands

            all_strands = load_all_rated_strands()
            need_histogram = [
                sid for sid, data in all_strands.items()
                if not data.get("histogram")
            ]

        assert 1001 not in need_histogram
        assert 1002 in need_histogram


# =============================================================================
# 6. Strand File I/O Tests
# =============================================================================

class TestStrandFileIO:
    """Tests for strand file save/load operations."""

    def test_save_rated_strand(self, temp_data_dir, sample_rated_strand):
        """Should correctly save rated strand to file."""
        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import save_rated_strand

            save_rated_strand(1001, sample_rated_strand)

        saved_path = temp_data_dir["rated"] / "1001.json"
        assert saved_path.exists()

        with open(saved_path) as f:
            loaded = json.load(f)

        assert loaded["seed_tweet_id"] == 1001
        assert loaded["title"] == "AI Discussion Thread"

    def test_load_rated_strand(self, temp_data_dir, sample_rated_strand):
        """Should correctly load rated strand from file."""
        # Save strand first
        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(sample_rated_strand))

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import load_rated_strand

            loaded = load_rated_strand(1001)

        assert loaded["seed_tweet_id"] == 1001
        assert loaded["title"] == "AI Discussion Thread"

    def test_load_all_rated_strands(self, temp_data_dir, sample_rated_strand):
        """Should load all rated strands."""
        # Save multiple strands
        strand1 = {**sample_rated_strand, "seed_tweet_id": 1001}
        strand2 = {**sample_rated_strand, "seed_tweet_id": 1002, "title": "Second Strand"}

        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(strand1))
        (temp_data_dir["rated"] / "1002.json").write_text(json.dumps(strand2))

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import load_all_rated_strands

            all_strands = load_all_rated_strands()

        assert len(all_strands) == 2
        assert 1001 in all_strands
        assert 1002 in all_strands
        assert all_strands[1002]["title"] == "Second Strand"

    def test_load_all_handles_corrupt_files(self, temp_data_dir, sample_rated_strand):
        """Should skip corrupt JSON files gracefully."""
        # Good strand
        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(sample_rated_strand))

        # Corrupt JSON
        (temp_data_dir["rated"] / "1002.json").write_text("not valid json {{{")

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import load_all_rated_strands

            all_strands = load_all_rated_strands()

        # Should have loaded the good one, skipped the corrupt one
        assert len(all_strands) == 1
        assert 1001 in all_strands

    def test_save_updates_existing_strand(self, temp_data_dir, sample_rated_strand):
        """Saving should update existing strand file."""
        # Save initial version
        (temp_data_dir["rated"] / "1001.json").write_text(json.dumps(sample_rated_strand))

        # Update and save
        updated = {**sample_rated_strand, "title": "Updated Title"}

        with patch('strands.RATED_DIR', temp_data_dir["rated"]):
            from strands import save_rated_strand, load_rated_strand

            save_rated_strand(1001, updated)
            loaded = load_rated_strand(1001)

        assert loaded["title"] == "Updated Title"


# =============================================================================
# 7. Integration Tests (Mocked)
# =============================================================================

class TestPipelineIntegration:
    """Integration tests with mocked external dependencies."""

    def test_semantic_search_uses_backup_when_available(self, sample_tweet_dict):
        """Semantic search should use backup and skip API call."""
        from lib.strand_builder import _semantic_search_for_strands

        backup_ids = [1004, 1005]
        search_called = []

        def mock_search(*args, **kwargs):
            search_called.append(True)
            return []

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=backup_ids):
                with patch('lib.strand_builder.save_semantic_backup'):
                    results = _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=sample_tweet_dict,
                        limit=20,
                        k=100,
                        max_k=200
                    )

        # Search should NOT have been called (used backup)
        assert len(search_called) == 0
        # Should have returned results from backup
        assert len(results) > 0

    def test_semantic_search_saves_backup_after_search(self):
        """Semantic search should save backup after successful search."""
        from lib.strand_builder import _semantic_search_for_strands

        save_calls = []

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            return [{"key": str(i)} for i in range(10)]

        def mock_save(tweet_id, params, ids):
            save_calls.append((tweet_id, params, ids))

        tweet_dict = {
            1001: {"tweet_id": 1001, "full_text": "Test", "quoted_tweet_id": None},
            **{i: {"tweet_id": i, "full_text": f"Tweet {i}", "quoted_tweet_id": None, "quoted_count": 1} for i in range(10)}
        }

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup', mock_save):
                    _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=tweet_dict,
                        limit=20,
                        k=100,
                        max_k=200
                    )

        # Should have called save
        assert len(save_calls) == 1
        assert save_calls[0][0] == 1001  # tweet_id

    def test_filters_out_direct_quotes_of_seed(self, sample_tweet_dict):
        """Should filter out tweets that are direct quotes of the seed tweet."""
        from lib.strand_builder import _semantic_search_for_strands

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            # Return the direct quote (1003) among results
            return [{"key": "1003"}, {"key": "1004"}, {"key": "1005"}]

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    results = _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=sample_tweet_dict,
                        limit=20,
                        k=100,
                        max_k=200
                    )

        result_ids = [r["tweet_id"] for r in results]
        # 1003 is a direct quote of 1001, should be filtered
        assert 1003 not in result_ids
        assert 1004 in result_ids
        assert 1005 in result_ids

    def test_filters_out_retweets(self, sample_tweet_dict):
        """Should filter out retweets (RT @...)."""
        from lib.strand_builder import _semantic_search_for_strands

        def mock_search(query, k, threshold, exclude_tweet_id, filter):
            # Return the retweet (1002) among results
            return [{"key": "1002"}, {"key": "1004"}, {"key": "1005"}]

        with patch('lib.strand_builder.search_embeddings', mock_search):
            with patch('lib.strand_builder.load_semantic_backup', return_value=None):
                with patch('lib.strand_builder.save_semantic_backup'):
                    results = _semantic_search_for_strands(
                        tweet_id=1001,
                        tweet_dict=sample_tweet_dict,
                        limit=20,
                        k=100,
                        max_k=200
                    )

        result_ids = [r["tweet_id"] for r in results]
        # 1002 is a retweet, should be filtered
        assert 1002 not in result_ids
        assert 1004 in result_ids


# =============================================================================
# 8. Seriation Algorithm Tests
# =============================================================================

class TestSeriationAlgorithm:
    """Tests for phase_generate_seriation greedy nearest-neighbor algorithm."""

    @pytest.fixture
    def seriation_data_dir(self, tmp_path):
        """Set up temp directories for seriation tests."""
        data_dir = tmp_path / "data"
        rated_dir = data_dir / "rated_strands"
        frontend_dir = tmp_path / "frontend" / "public"

        data_dir.mkdir()
        rated_dir.mkdir()
        frontend_dir.mkdir(parents=True)

        return {
            "root": tmp_path,
            "data": data_dir,
            "rated": rated_dir,
            "frontend": frontend_dir,
            "embeddings_cache": data_dir / "strand_summary_embeddings.json",
            "seriation_output": frontend_dir / "strand_seriation_order.json",
        }

    def test_seriation_visits_all_strands_once(self, seriation_data_dir):
        """Seriation should visit every strand exactly once."""
        import numpy as np

        # Create 5 strands with embeddings
        embeddings = []
        for i in range(5):
            # Create distinct embeddings pointing in different directions
            emb = np.zeros(10)
            emb[i % 10] = 1.0
            embeddings.append({
                "seed_tweet_id": str(1000 + i),
                "embedding": emb.tolist()
            })

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        # Create rated strand files
        for i in range(5):
            strand = {
                "seed_tweet_id": 1000 + i,
                "rating": {"rating": 5 + i},  # Different ratings
            }
            (seriation_data_dir["rated"] / f"{1000 + i}.json").write_text(json.dumps(strand))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        result = phase_generate_seriation()

        assert result is True

        # Load and check output
        output = json.loads(seriation_data_dir["seriation_output"].read_text())

        # Should have all 5 strands
        assert output["count"] == 5
        assert len(output["order"]) == 5

        # Each strand should appear exactly once
        visited_ids = [o["id"] for o in output["order"]]
        assert len(set(visited_ids)) == 5

    def test_seriation_starts_from_highest_rated(self, seriation_data_dir):
        """Seriation should start from the highest rated strand."""
        import numpy as np

        embeddings = []
        for i in range(3):
            emb = np.random.randn(10).tolist()
            embeddings.append({
                "seed_tweet_id": str(2000 + i),
                "embedding": emb
            })

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        # Strand 2001 has highest rating (9)
        ratings = [5, 9, 3]
        for i in range(3):
            strand = {
                "seed_tweet_id": 2000 + i,
                "rating": {"rating": ratings[i]},
            }
            (seriation_data_dir["rated"] / f"{2000 + i}.json").write_text(json.dumps(strand))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        phase_generate_seriation()

        output = json.loads(seriation_data_dir["seriation_output"].read_text())

        # First strand should be 2001 (highest rated)
        assert output["start_id"] == "2001"
        assert output["order"][0]["id"] == "2001"
        assert output["order"][0]["distance"] == 0.0

    def test_seriation_uses_cosine_distance(self, seriation_data_dir):
        """Seriation should use cosine distance (1 - cosine similarity)."""
        import numpy as np

        # Create embeddings where nearest neighbor is predictable
        # Strand A: [1, 0, 0]
        # Strand B: [0.9, 0.1, 0] - very similar to A
        # Strand C: [0, 0, 1] - orthogonal to A
        embeddings = [
            {"seed_tweet_id": "3000", "embedding": [1.0, 0.0, 0.0]},
            {"seed_tweet_id": "3001", "embedding": [0.9, 0.1, 0.0]},
            {"seed_tweet_id": "3002", "embedding": [0.0, 0.0, 1.0]},
        ]

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        # All same rating so 3000 is chosen (first in sorted order)
        for i in range(3):
            strand = {
                "seed_tweet_id": 3000 + i,
                "rating": {"rating": 5},
            }
            (seriation_data_dir["rated"] / f"{3000 + i}.json").write_text(json.dumps(strand))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        phase_generate_seriation()

        output = json.loads(seriation_data_dir["seriation_output"].read_text())
        order_ids = [o["id"] for o in output["order"]]

        # After 3000, nearest should be 3001 (similar), then 3002 (orthogonal)
        assert order_ids[0] == "3000"
        assert order_ids[1] == "3001"  # Most similar to 3000
        assert order_ids[2] == "3002"  # Orthogonal, visited last

    def test_seriation_handles_single_strand(self, seriation_data_dir):
        """Seriation should handle edge case of single strand."""
        embeddings = [
            {"seed_tweet_id": "4000", "embedding": [1.0, 0.0, 0.0]},
        ]

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        strand = {"seed_tweet_id": 4000, "rating": {"rating": 7}}
        (seriation_data_dir["rated"] / "4000.json").write_text(json.dumps(strand))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        # Should return False for < 2 strands
                        result = phase_generate_seriation()

        assert result is False

    def test_seriation_distances_are_valid(self, seriation_data_dir):
        """All distances should be between 0 and 2 (valid cosine distance range)."""
        import numpy as np

        embeddings = []
        for i in range(4):
            emb = np.random.randn(10).tolist()
            embeddings.append({
                "seed_tweet_id": str(5000 + i),
                "embedding": emb
            })

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        for i in range(4):
            strand = {"seed_tweet_id": 5000 + i, "rating": {"rating": 5}}
            (seriation_data_dir["rated"] / f"{5000 + i}.json").write_text(json.dumps(strand))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        phase_generate_seriation()

        output = json.loads(seriation_data_dir["seriation_output"].read_text())

        for entry in output["order"]:
            distance = entry["distance"]
            # Cosine distance is 1 - similarity, ranges from 0 (identical) to 2 (opposite)
            assert 0.0 <= distance <= 2.0, f"Invalid distance: {distance}"

        # First entry should have distance 0 (starting point)
        assert output["order"][0]["distance"] == 0.0

    def test_seriation_returns_false_when_no_embeddings(self, seriation_data_dir):
        """Should return False when embeddings cache doesn't exist."""
        # Don't create embeddings file

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            from strands import phase_generate_seriation

            result = phase_generate_seriation()

        assert result is False

    def test_seriation_handles_missing_rating(self, seriation_data_dir):
        """Should handle strands with missing or malformed rating."""
        embeddings = [
            {"seed_tweet_id": "6000", "embedding": [1.0, 0.0]},
            {"seed_tweet_id": "6001", "embedding": [0.0, 1.0]},
        ]

        cache_data = {"model": "test", "embeddings": embeddings}
        seriation_data_dir["embeddings_cache"].write_text(json.dumps(cache_data))

        # One strand has no rating field
        strand1 = {"seed_tweet_id": 6000}  # No rating
        strand2 = {"seed_tweet_id": 6001, "rating": {"rating": 8}}

        (seriation_data_dir["rated"] / "6000.json").write_text(json.dumps(strand1))
        (seriation_data_dir["rated"] / "6001.json").write_text(json.dumps(strand2))

        with patch('strands.EMBEDDINGS_CACHE_PATH', seriation_data_dir["embeddings_cache"]):
            with patch('strands.RATED_DIR', seriation_data_dir["rated"]):
                with patch('strands.FRONTEND_PUBLIC_DIR', seriation_data_dir["frontend"]):
                    with patch('strands.SERIATION_ORDER_PATH', seriation_data_dir["seriation_output"]):
                        from strands import phase_generate_seriation

                        result = phase_generate_seriation()

        # Should succeed, starting from 6001 (has higher rating than default 5)
        assert result is True

        output = json.loads(seriation_data_dir["seriation_output"].read_text())
        assert output["start_id"] == "6001"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
