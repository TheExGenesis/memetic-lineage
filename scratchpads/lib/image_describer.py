# %%
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import httpx
from diskcache import Cache
from dotenv import load_dotenv
from groq import Groq

from .parallel import parallel_map_to_dict
from .retry import with_retry

load_dotenv(Path(__file__).parent.parent.parent / ".env")


class MediaDescription(TypedDict):
    tweet_id: str
    tweet_text: str
    media_url: str
    description: str


SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
SUPABASE_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8"
)

SCRATCHPADS_DIR = Path(__file__).parent.parent
IMAGE_CACHE_DISKCACHE = SCRATCHPADS_DIR / "image_cache.diskcache"
LEGACY_CSV_PATH = SCRATCHPADS_DIR / "image_cache.csv"

_image_cache: Optional[Cache] = None

def _headers() -> dict[str, str]:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_tweet(tweet_id: str) -> dict | None:
    url = f"{SUPABASE_URL}/rest/v1/tweets?tweet_id=eq.{tweet_id}&select=tweet_id,full_text"
    resp = httpx.get(url, headers=_headers())
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def fetch_tweet_media(tweet_id: str) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/tweet_media?tweet_id=eq.{tweet_id}&media_type=eq.photo&select=media_url"
    resp = httpx.get(url, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def get_image_cache() -> Cache:
    """Get or open the image cache diskcache."""
    global _image_cache
    if _image_cache is not None:
        return _image_cache
    
    _image_cache = Cache(str(IMAGE_CACHE_DISKCACHE), size_limit=1 * 1024**3)
    print(f"Opened image cache with {len(_image_cache)} entries")
    return _image_cache



@with_retry(max_retries=3, base_delay=2.0)
def describe_image(image_url: str, tweet_text: str) -> str:
    """Describe an image using Groq vision model. Retries on transient errors."""
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Describe this image briefly. For images with text, exhaustively transcribe the text. For diagrams and memes, describe them as if you want someone else to reproduce them. For visual pictures stick to 1-2 sentences. Tweet context: \"{tweet_text}\""},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }],
        temperature=0.7,
        max_completion_tokens=512,
    )
    return completion.choices[0].message.content or ""


def get_image_descriptions(tweet_id: int, verbose: bool = True) -> List[MediaDescription]:
    """Fetch and describe images for a tweet. Returns list of MediaDescription."""
    tweet_id_str = str(tweet_id)

    if verbose:
        print(f"Processing tweet {tweet_id_str}")
    
    tweet = fetch_tweet(tweet_id_str)
    if not tweet:
        return []
    
    media_rows = fetch_tweet_media(tweet_id_str)
    if not media_rows:
        return []
    
    if verbose:
        print(f"Describing {len(media_rows)} images for tweet {tweet_id_str}")
    
    results: List[MediaDescription] = []
    for m in media_rows:
        desc = describe_image(m["media_url"], tweet["full_text"])
        results.append({
            "tweet_id": tweet_id_str,
            "tweet_text": tweet["full_text"],
            "media_url": m["media_url"],
            "description": desc,
        })
    
    return results


def get_image_descriptions_batch(
    tweet_ids: List[int],
    cache: Optional[Cache] = None,
    max_workers: int = 2,
    verbose: bool = False
) -> None:
    """
    Get image descriptions for multiple tweets, storing directly in cache.
    
    Args:
        tweet_ids: List of tweet IDs to get descriptions for
        cache: Diskcache to use (defaults to global image cache)
        max_workers: Parallel workers (keep low for Groq rate limits)
        verbose: Print progress messages
    """
    if cache is None:
        cache = get_image_cache()
    
    # Filter to only uncached tweet IDs (int keys)
    missing_ids = [tid for tid in tweet_ids if tid not in cache]
    
    if not missing_ids:
        if verbose:
            print("All tweet IDs already in cache")
        return
    
    if verbose:
        print(f"Fetching descriptions for {len(missing_ids)} tweets (skipped {len(tweet_ids) - len(missing_ids)} cached)")
    
    def fetch_one(tid: int) -> List[MediaDescription]:
        try:
            return get_image_descriptions(tid, verbose=False)
        except Exception as e:
            print(f"[ERROR] Image descriptions for {tid}: {e}")
            return [{
                "tweet_id": str(tid),
                "tweet_text": "",
                "media_url": "",
                "description": "[PIC NOT AVAILABLE]",
            }]
    
    results, failed = parallel_map_to_dict(
        missing_ids, fetch_one,
        max_workers=max_workers,
        desc="Fetching image descriptions"
    )
    
    # Store all results in cache (including empty lists to avoid re-fetching)
    for tid, descs in results.items():
        cache[tid] = descs


# %%
