# %%
import os
import re
import csv
from pathlib import Path
from typing import TypedDict
import httpx
from groq import Groq
from dotenv import load_dotenv

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
DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "image_cache.csv"

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

def load_img_cache(cache_path: Path = DEFAULT_CACHE_PATH) -> dict[str, list[MediaDescription]]:
    cache: dict[str, list[MediaDescription]] = {}
    if not cache_path.exists():
        return cache
    with open(cache_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row["tweet_id"]
            cache.setdefault(tid, []).append({
                "tweet_id": tid,
                "tweet_text": row["tweet_text"],
                "media_url": row["media_url"],
                "description": row["description"],
            })
    return cache

def save_img_cache(cache: dict[str, list[MediaDescription]], cache_path: Path = DEFAULT_CACHE_PATH) -> None:
    """Save the entire cache dict to CSV file, overwriting the existing file."""
    if not cache:
        return
    
    # Collect all entries from cache
    all_entries: list[MediaDescription] = []
    for entries in cache.values():
        all_entries.extend(entries)
    
    if not all_entries:
        return
    
    # Overwrite the file with all cache entries
    with open(cache_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tweet_id", "tweet_text", "media_url", "description"])
        writer.writeheader()
        writer.writerows(all_entries)

def save_to_cache(entries: list[MediaDescription], cache_path: Path = DEFAULT_CACHE_PATH) -> None:
    """Legacy function for backward compatibility. Use save_cache for bulk saves."""
    file_exists = cache_path.exists()
    with open(cache_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tweet_id", "tweet_text", "media_url", "description"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(entries)

def describe_image(image_url: str, tweet_text: str) -> str:
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

def get_image_descriptions(
    tweet_id: int,
    verbose: bool = True,
) -> list[MediaDescription]:
    """
    Get image descriptions for a tweet and add them to the cache dict in place.
    
    Args:
        tweet_id_or_url: Tweet ID or URL
        verbose: If True, print progress messages
    """
    tweet_id_str = str(tweet_id)

    if verbose:
        print(f"Processing tweet {tweet_id_str}")
    
    if verbose:
        print(f"Fetching tweet {tweet_id_str} from Supabase")
    tweet = fetch_tweet(tweet_id_str)
    if not tweet:
        return []
    
    if verbose:
        print(f"Fetching media for tweet {tweet_id_str} from Supabase")
    media_rows = fetch_tweet_media(tweet_id_str)
    if not media_rows:
        return []
    
    if verbose:
        print(f"Describing images for tweet {tweet_id_str}")
    results: list[MediaDescription] = []
    for m in media_rows:
        desc = describe_image(m["media_url"], tweet["full_text"])
        results.append({
            "tweet_id": tweet_id_str,
            "tweet_text": tweet["full_text"],
            "media_url": m["media_url"],
            "description": desc,
        })
    
    return results


# %%
