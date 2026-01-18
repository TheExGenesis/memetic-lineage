# %%
"""Semantic search backup utilities for caching search results."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

SCRATCHPADS_DIR = Path(__file__).parent.parent


def get_backup_path(root_tweet_id: int) -> Path:
    """Get backup file path for root tweet."""
    return SCRATCHPADS_DIR / 'data' / 'semantic_search_backups' / f'{root_tweet_id}.json'


def save_semantic_backup(root_tweet_id: int, search_params: dict, tweet_ids: List[int]) -> None:
    """Save filtered semantic search results to backup file."""
    backup_path = get_backup_path(root_tweet_id)
    backup_path.parent.mkdir(exist_ok=True)

    data = {
        'root_tweet_id': root_tweet_id,
        'timestamp': datetime.now().isoformat(),
        'search_params': search_params,
        'semantic_tweet_ids': tweet_ids
    }

    try:
        with open(backup_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save semantic backup for {root_tweet_id}: {e}")


def load_semantic_backup(root_tweet_id: int, search_params: dict) -> Optional[List[int]]:
    """Load backup if valid and fresh, else return None."""
    backup_path = get_backup_path(root_tweet_id)
    if not backup_path.exists():
        return None

    try:
        with open(backup_path) as f:
            data = json.load(f)

        # Check freshness (24 hours)
        backup_time = datetime.fromisoformat(data['timestamp'])
        if (datetime.now() - backup_time).total_seconds() > 24 * 3600:
            return None

        # Check parameters match
        if data['search_params'] != search_params:
            return None
        
        if len(data['semantic_tweet_ids']) <= 0:
            return None

        return data['semantic_tweet_ids']
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        # Corrupt or inaccessible backup - remove and return None
        print(f"[WARN] Removing corrupt semantic backup for {root_tweet_id}: {e}")
        backup_path.unlink(missing_ok=True)
        return None


def cleanup_old_backups(max_age_hours: int = 24 * 7) -> int:
    """Remove backup files older than max_age_hours. Returns count of removed files."""
    backup_dir = SCRATCHPADS_DIR / 'data' / 'semantic_search_backups'
    if not backup_dir.exists():
        return 0

    removed_count = 0
    cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

    for backup_file in backup_dir.glob('*.json'):
        try:
            if backup_file.stat().st_mtime < cutoff_time:
                backup_file.unlink()
                removed_count += 1
        except OSError:
            continue  # Skip files we can't remove

    return removed_count


# %%