"""Shared fixtures for strand pipeline tests."""
import sys
from pathlib import Path

# Add scratchpads to path for imports
SCRATCHPADS_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(SCRATCHPADS_DIR))

import pytest
from diskcache import Cache


@pytest.fixture
def tmp_diskcache(tmp_path):
    """Create a temporary diskcache for testing."""
    cache_path = tmp_path / "test_cache.diskcache"
    cache = Cache(str(cache_path))
    yield cache
    cache.close()


@pytest.fixture
def sample_conversation_tree():
    """Sample ConversationTree structure for testing."""
    return {
        "root": 1001,
        "parents": {1002: 1001, 1003: 1002},
        "children": {1001: [1002], 1002: [1003], 1003: []},
    }


@pytest.fixture
def sample_tweet_dict():
    """Minimal tweet data for testing."""
    return {
        1001: {
            "tweet_id": 1001,
            "full_text": "Root tweet",
            "username": "user1",
            "quoted_tweet_id": None,
            "quoted_count": 5,
        },
        1002: {
            "tweet_id": 1002,
            "full_text": "Reply to root",
            "username": "user2",
            "quoted_tweet_id": None,
            "quoted_count": 0,
        },
        1003: {
            "tweet_id": 1003,
            "full_text": "RT @someone This is a retweet",
            "username": "user3",
            "quoted_tweet_id": 1001,
            "quoted_count": 0,
        },
    }

