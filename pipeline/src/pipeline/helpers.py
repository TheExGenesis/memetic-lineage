"""Shared helper functions used across pipeline phases."""

import json
from typing import Set

from pipeline.config import STRANDS_DIR, RATED_DIR


def _to_int_id(tid) -> int:
    """Convert a tweet ID (string, int, or scientific notation) to int."""
    if isinstance(tid, int):
        return tid
    return int(float(tid))


def _to_str_id(tid) -> str:
    """Convert a tweet ID to a clean string (no scientific notation)."""
    return str(_to_int_id(tid))


def _is_valid(val) -> bool:
    """Check if a value is non-null and non-NaN (handles pandas/numpy/pyarrow NA)."""
    if val is None:
        return False
    try:
        if val != val:  # NaN check
            return False
    except (TypeError, ValueError):
        pass
    return True


def _tweet_dict_to_bangers(t: dict) -> dict:
    """Convert a tweet_dict entry to the bangers JSON format."""
    tid = _to_str_id(t['tweet_id'])
    result = {
        'tweet_id': tid,
        'full_text': t.get('full_text', '') or '',
        'username': t.get('username', 'unknown') or 'unknown',
        'created_at': str(t.get('created_at', '') or ''),
        'favorite_count': int(t.get('favorite_count', 0) or 0),
        'retweet_count': int(t.get('retweet_count', 0) or 0),
    }
    # Optional fields
    avatar = t.get('avatar_media_url')
    if _is_valid(avatar):
        result['avatar_media_url'] = str(avatar)
    reply_to = t.get('reply_to_tweet_id')
    if _is_valid(reply_to):
        result['reply_to_tweet_id'] = _to_str_id(reply_to)
    return result


def get_built_strand_ids() -> Set[int]:
    """Get IDs of strands that have been built."""
    if not STRANDS_DIR.exists():
        return set()
    return {int(f.stem) for f in STRANDS_DIR.glob("*.json") if f.stem.isdigit()}


def get_rated_strand_ids() -> Set[int]:
    """Get IDs of strands that have been rated."""
    if not RATED_DIR.exists():
        return set()
    return {int(f.stem) for f in RATED_DIR.glob("*.json") if f.stem.isdigit()}


def load_rated_strand(strand_id: int) -> dict:
    """Load a single rated strand."""
    path = RATED_DIR / f"{strand_id}.json"
    with open(path) as f:
        return json.load(f)


def save_rated_strand(strand_id: int, data: dict):
    """Save a single rated strand."""
    path = RATED_DIR / f"{strand_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_all_rated_strands() -> dict[int, dict]:
    """Load all rated strands."""
    strands = {}
    for path in RATED_DIR.glob("*.json"):
        try:
            strand_id = int(path.stem)
            with open(path) as f:
                strands[strand_id] = json.load(f)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[WARN] Failed to load {path.name}: {e}")
    return strands
