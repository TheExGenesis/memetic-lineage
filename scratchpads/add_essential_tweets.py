"""
Fetch missing essential tweets from CA Supabase and add them to bangers_tweets.json.

Essential tweets are identified by the LLM rating process but many aren't in the
"bangers" dataset (which only contains top-quoted tweets). This script fills the gap.

Also fetches conversation threads for all essential tweets so the StrandDetail
component can display full threads, not just individual tweets.
"""

import json
import re
from pathlib import Path

import httpx

SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8"

BANGERS_PATH = Path(__file__).parent.parent / "bangers" / "public" / "bangers_tweets.json"
STRANDS_PATH = Path(__file__).parent.parent / "bangers" / "public" / "strands_data.json"


def _headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def get_essential_tweet_ids() -> set[str]:
    """Get all essential tweet IDs from strands_data.json, fixing float precision."""
    raw = STRANDS_PATH.read_text()
    raw = re.sub(r'"tweet_id":\s*(\d+)', r'"tweet_id": "\1"', raw)
    data = json.loads(raw)

    ids = set()
    for strand in data["strands"]:
        for et in strand["rating"]["essential_tweets"]:
            ids.add(str(et["tweet_id"]))
    return ids


def fetch_tweets(client: httpx.Client, tweet_ids: list[str]) -> list[dict]:
    """Fetch tweet data from CA Supabase in batches."""
    all_tweets = []
    batch_size = 200

    for i in range(0, len(tweet_ids), batch_size):
        batch = tweet_ids[i:i + batch_size]
        url = (
            f"{SUPABASE_URL}/rest/v1/tweets"
            f"?tweet_id=in.({','.join(batch)})"
            f"&select=tweet_id,full_text,created_at,favorite_count,retweet_count,"
            f"account_id,conversation_id,"
            f"all_account(username,all_profile(avatar_media_url))"
        )
        resp = client.get(url, headers=_headers())
        if resp.status_code != 200:
            print(f"  Error batch {i//batch_size}: {resp.status_code} {resp.text[:200]}")
            continue
        all_tweets.extend(resp.json())

    return all_tweets


def fetch_conversations(client: httpx.Client, conv_ids: list[str]) -> list[dict]:
    """Fetch all tweets in given conversations from CA Supabase."""
    all_tweets = []
    batch_size = 50  # Smaller batches since conversations can be large

    for i in range(0, len(conv_ids), batch_size):
        batch = conv_ids[i:i + batch_size]
        url = (
            f"{SUPABASE_URL}/rest/v1/tweets"
            f"?conversation_id=in.({','.join(batch)})"
            f"&select=tweet_id,full_text,created_at,favorite_count,retweet_count,"
            f"account_id,conversation_id,"
            f"all_account(username,all_profile(avatar_media_url))"
            f"&order=created_at.asc"
            f"&limit=1000"
        )
        resp = client.get(url, headers=_headers())
        if resp.status_code != 200:
            print(f"  Error conv batch {i//batch_size}: {resp.status_code} {resp.text[:200]}")
            continue
        data = resp.json()
        all_tweets.extend(data)
        if (i // batch_size) % 10 == 0:
            print(f"  Conv batch {i//batch_size + 1}/{(len(conv_ids) + batch_size - 1) // batch_size}: {len(data)} tweets")

    return all_tweets


def raw_to_record(t: dict) -> dict:
    """Convert a Supabase tweet row to bangers_tweets.json format."""
    tid = str(t["tweet_id"])
    username = "unknown"
    avatar_url = None

    account = t.get("all_account")
    if account:
        if isinstance(account, list) and len(account) > 0:
            account = account[0]
        if isinstance(account, dict):
            username = account.get("username", "unknown")
            profiles = account.get("all_profile", [])
            if isinstance(profiles, list) and len(profiles) > 0:
                avatar_url = profiles[0].get("avatar_media_url")
            elif isinstance(profiles, dict):
                avatar_url = profiles.get("avatar_media_url")

    return {
        "tweet_id": tid,
        "full_text": t.get("full_text", ""),
        "username": username,
        "created_at": t.get("created_at", ""),
        "favorite_count": t.get("favorite_count", 0),
        "retweet_count": t.get("retweet_count", 0),
        "avatar_media_url": avatar_url,
        "quote_count": 0,
        "archive_quote_count": 0,
        "is_archive_user": True,
    }


def main():
    print("Loading data...")
    essential_ids = get_essential_tweet_ids()
    bangers = json.loads(BANGERS_PATH.read_text())
    existing_ids = set(bangers["tweets"].keys())

    print(f"  Essential tweets: {len(essential_ids)}")
    print(f"  Existing tweets: {len(existing_ids)}")

    # Find essential tweets missing from bangers
    missing_ids = essential_ids - existing_ids
    print(f"  Missing essential tweets: {len(missing_ids)}")

    # Find essential tweets without conversation data
    essential_without_conv = [
        tid for tid in essential_ids
        if tid not in bangers.get("tweetToConversation", {})
    ]
    print(f"  Essential tweets without conversation data: {len(essential_without_conv)}")

    client = httpx.Client(timeout=30)

    # Step 1: Fetch missing essential tweets
    if missing_ids:
        print(f"\nStep 1: Fetching {len(missing_ids)} missing tweets...")
        raw_tweets = fetch_tweets(client, list(missing_ids))
        print(f"  Retrieved: {len(raw_tweets)} tweets")

        for t in raw_tweets:
            record = raw_to_record(t)
            bangers["tweets"][record["tweet_id"]] = record

    # Step 2: Get conversation_ids for all essential tweets that lack them
    if essential_without_conv:
        print(f"\nStep 2: Fetching conversation_ids for {len(essential_without_conv)} essential tweets...")
        raw_essential = fetch_tweets(client, essential_without_conv)
        print(f"  Retrieved: {len(raw_essential)}")

        # Collect conversation_ids
        conv_id_map = {}  # tweet_id -> conversation_id
        for t in raw_essential:
            tid = str(t["tweet_id"])
            cid = str(t.get("conversation_id", ""))
            if cid and cid != tid:
                # Only track conversations with multiple tweets
                conv_id_map[tid] = cid
            elif cid:
                # Self-conversation (single tweet) - still map it
                conv_id_map[tid] = cid

        unique_conv_ids = set(conv_id_map.values())
        # Filter out conversations we already have
        existing_convs = set(bangers.get("conversations", {}).keys())
        new_conv_ids = unique_conv_ids - existing_convs
        print(f"  Unique conversations: {len(unique_conv_ids)}, new: {len(new_conv_ids)}")

        # Step 3: Fetch all tweets in new conversations
        if new_conv_ids:
            print(f"\nStep 3: Fetching threads for {len(new_conv_ids)} conversations...")
            conv_tweets = fetch_conversations(client, list(new_conv_ids))
            print(f"  Retrieved: {len(conv_tweets)} conversation tweets")

            # Add conversation tweets to bangers
            conversations = bangers.get("conversations", {})
            tweet_to_conv = bangers.get("tweetToConversation", {})

            # Group by conversation_id
            conv_groups: dict[str, list[str]] = {}
            for t in conv_tweets:
                tid = str(t["tweet_id"])
                cid = str(t.get("conversation_id", ""))
                if not cid:
                    continue

                # Add tweet record if not already present
                if tid not in bangers["tweets"]:
                    bangers["tweets"][tid] = raw_to_record(t)

                # Build conversation groups
                if cid not in conv_groups:
                    conv_groups[cid] = []
                conv_groups[cid].append(tid)

                # Map tweet to conversation
                tweet_to_conv[tid] = cid

            # Add conversations
            for cid, tids in conv_groups.items():
                conversations[cid] = tids

            bangers["conversations"] = conversations
            bangers["tweetToConversation"] = tweet_to_conv

            print(f"  Added {len(conv_groups)} conversations ({len(conv_tweets)} tweets)")

        # Also add tweetToConversation for essential tweets with self-conversations
        tweet_to_conv = bangers.get("tweetToConversation", {})
        for tid, cid in conv_id_map.items():
            if tid not in tweet_to_conv:
                tweet_to_conv[tid] = cid
        bangers["tweetToConversation"] = tweet_to_conv

    client.close()

    # Save
    bangers["tweetCount"] = len(bangers["tweets"])
    print(f"\nSaving... Total tweets: {bangers['tweetCount']}")
    BANGERS_PATH.write_text(json.dumps(bangers))
    print("Done!")

    # Verify
    convs = bangers.get("tweetToConversation", {})
    found_conv = sum(1 for tid in essential_ids if tid in convs)
    print(f"\nVerification: {found_conv}/{len(essential_ids)} essential tweets have conversation data")


if __name__ == "__main__":
    main()
