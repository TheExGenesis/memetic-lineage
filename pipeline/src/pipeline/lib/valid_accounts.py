# %%
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
SUPABASE_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8"
)

SCRATCHPADS_DIR = Path(__file__).parent.parent
CACHE_PATH = SCRATCHPADS_DIR / "data" / "valid_account_ids_cache.json"


def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _fetch_paginated(table: str, column: str, page_size: int = 1000) -> set[str]:
    """Fetch all values of a column from a table with pagination."""
    result: set[str] = set()
    offset = 0
    
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={column}&limit={page_size}&offset={offset}"
        resp = httpx.get(url, headers=_headers(), timeout=60.0)
        resp.raise_for_status()
        rows = resp.json()
        
        if not rows:
            break
        
        for row in rows:
            val = row.get(column)
            if val is not None:
                result.add(str(val))
        
        if len(rows) < page_size:
            break
        offset += page_size
    
    return result


def fetch_valid_account_ids() -> set[str]:
    """Fetch account_ids from archive_upload and twitter_user_ids from optin."""
    print("Fetching account_ids from archive_upload...")
    archive_ids = _fetch_paginated("archive_upload", "account_id")
    print(f"  Found {len(archive_ids)} accounts with archives")
    
    print("Fetching twitter_user_ids from optin...")
    optin_ids = _fetch_paginated("optin", "twitter_user_id")
    print(f"  Found {len(optin_ids)} accounts in optin")
    
    combined = archive_ids | optin_ids
    print(f"Total unique valid accounts: {len(combined)}")
    return combined


def save_cache(account_ids: set[str]) -> None:
    """Save account_ids to cache file."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "fetched_at": datetime.utcnow().isoformat(),
        "account_ids": sorted(account_ids)
    }
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(account_ids)} account_ids to {CACHE_PATH}")


def load_cache() -> Optional[set[str]]:
    """Load account_ids from cache file if exists."""
    if not CACHE_PATH.exists():
        return None
    with open(CACHE_PATH, "r") as f:
        data = json.load(f)
    account_ids = set(data["account_ids"])
    print(f"Loaded {len(account_ids)} account_ids from cache (fetched {data['fetched_at']})")
    return account_ids


def get_valid_account_ids(force_refresh: bool = False) -> set[str]:
    """Get valid account_ids, using cache if available."""
    if not force_refresh:
        cached = load_cache()
        if cached is not None:
            return cached
    
    account_ids = fetch_valid_account_ids()
    save_cache(account_ids)
    return account_ids

