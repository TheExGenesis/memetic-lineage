"""
Build conversation/thread data for essential tweets by walking reply chains
from the CA Supabase. Updates bangers_tweets.json with conversations and
tweetToConversation mappings.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import httpx

SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0.UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8"

BANGERS_PATH = Path(__file__).parent.parent / "bangers" / "public" / "bangers_tweets.json"
STRANDS_PATH = Path(__file__).parent.parent / "bangers" / "public" / "strands_data.json"


def _headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def get_essential_tweet_ids() -> set[str]:
    raw = STRANDS_PATH.read_text()
    raw = re.sub(r'"tweet_id":\s*(\d+)', r'"tweet_id": "\1"', raw)
    data = json.loads(raw)
    ids = set()
    for strand in data["strands"]:
        for et in strand["rating"]["essential_tweets"]:
            ids.add(str(et["tweet_id"]))
    return ids


def batch_fetch(client: httpx.Client, tweet_ids: list[str], select: str) -> list[dict]:
    """Fetch tweets by ID with given select fields."""
    all_results = []
    batch_size = 200
    for i in range(0, len(tweet_ids), batch_size):
        batch = tweet_ids[i:i + batch_size]
        url = (
            f"{SUPABASE_URL}/rest/v1/tweets"
            f"?tweet_id=in.({','.join(batch)})"
            f"&select={select}"
        )
        resp = client.get(url, headers=_headers())
        if resp.status_code == 200:
            all_results.extend(resp.json())
        else:
            print(f"  Error: {resp.status_code} {resp.text[:200]}")
    return all_results


def batch_fetch_replies(client: httpx.Client, parent_ids: list[str], select: str) -> list[dict]:
    """Fetch tweets where reply_to_tweet_id is in the given set."""
    all_results = []
    batch_size = 200
    for i in range(0, len(parent_ids), batch_size):
        batch = parent_ids[i:i + batch_size]
        url = (
            f"{SUPABASE_URL}/rest/v1/tweets"
            f"?reply_to_tweet_id=in.({','.join(batch)})"
            f"&select={select}"
            f"&order=created_at.asc"
            f"&limit=1000"
        )
        resp = client.get(url, headers=_headers())
        if resp.status_code == 200:
            all_results.extend(resp.json())
        else:
            print(f"  Error: {resp.status_code} {resp.text[:200]}")
    return all_results


def raw_to_record(t: dict) -> dict:
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


FULL_SELECT = (
    "tweet_id,full_text,created_at,favorite_count,retweet_count,"
    "account_id,reply_to_tweet_id,"
    "all_account(username,all_profile(avatar_media_url))"
)


def main():
    print("Loading data...")
    essential_ids = get_essential_tweet_ids()
    bangers = json.loads(BANGERS_PATH.read_text())
    existing_convs = set(bangers.get("conversations", {}).keys())
    tweet_to_conv = bangers.get("tweetToConversation", {})

    # Find essential tweets without conversation data
    needs_conv = [tid for tid in essential_ids if tid not in tweet_to_conv]
    print(f"  Essential tweets needing conversation data: {len(needs_conv)}")

    if not needs_conv:
        print("All essential tweets already have conversation data!")
        return

    client = httpx.Client(timeout=30)

    # Step 1: Fetch essential tweets to get reply_to_tweet_id
    print(f"\nStep 1: Fetching reply chain data for {len(needs_conv)} tweets...")
    raw = batch_fetch(client, needs_conv, "tweet_id,reply_to_tweet_id,account_id")
    print(f"  Got {len(raw)} tweets")

    reply_map = {}  # tweet_id -> reply_to_tweet_id
    account_map = {}  # tweet_id -> account_id
    for t in raw:
        tid = str(t["tweet_id"])
        reply_map[tid] = str(t["reply_to_tweet_id"]) if t.get("reply_to_tweet_id") else None
        account_map[tid] = str(t["account_id"]) if t.get("account_id") else None

    # Step 2: Walk up reply chains to find roots
    print("\nStep 2: Walking up reply chains to find roots...")
    # For each essential tweet, walk up to find the root
    tweet_to_root = {}  # essential_tweet_id -> root_tweet_id
    tweets_to_fetch = set()  # Parents we need to fetch

    for tid in needs_conv:
        if tid not in reply_map:
            # Tweet not in Supabase, skip
            continue
        chain = [tid]
        current = tid
        max_depth = 20
        while reply_map.get(current) and max_depth > 0:
            parent = reply_map[current]
            chain.append(parent)
            if parent not in reply_map:
                tweets_to_fetch.add(parent)
            current = parent
            max_depth -= 1

    # Fetch missing parents in batches until we reach all roots
    rounds = 0
    while tweets_to_fetch:
        rounds += 1
        to_fetch = list(tweets_to_fetch)
        tweets_to_fetch = set()
        print(f"  Round {rounds}: fetching {len(to_fetch)} parent tweets...")
        parents = batch_fetch(client, to_fetch, "tweet_id,reply_to_tweet_id,account_id")
        for t in parents:
            tid = str(t["tweet_id"])
            reply_map[tid] = str(t["reply_to_tweet_id"]) if t.get("reply_to_tweet_id") else None
            account_map[tid] = str(t["account_id"]) if t.get("account_id") else None
            if reply_map[tid] and reply_map[tid] not in reply_map:
                tweets_to_fetch.add(reply_map[tid])
        if rounds > 10:
            print("  Hit max rounds, stopping chain walk")
            break

    # Now resolve roots for each essential tweet
    for tid in needs_conv:
        if tid not in reply_map:
            continue
        current = tid
        visited = {current}
        while reply_map.get(current):
            parent = reply_map[current]
            if parent in visited:
                break
            visited.add(parent)
            current = parent
        tweet_to_root[tid] = current

    unique_roots = set(tweet_to_root.values())
    print(f"  Found {len(unique_roots)} unique conversation roots for {len(tweet_to_root)} tweets")

    # Step 3: Build threads by walking DOWN from each root
    # Fetch all replies to root tweets, then replies to those, etc.
    print(f"\nStep 3: Building threads from {len(unique_roots)} roots...")

    all_conv_tweets = {}  # tweet_id -> raw tweet data
    conv_members = defaultdict(set)  # root_id -> set of tweet_ids in conversation

    # Add roots to conversations
    for root_id in unique_roots:
        conv_members[root_id].add(root_id)

    # Iteratively find all replies
    current_parents = list(unique_roots)
    depth = 0
    while current_parents and depth < 15:
        depth += 1
        print(f"  Depth {depth}: finding replies to {len(current_parents)} tweets...")
        replies = batch_fetch_replies(client, current_parents, FULL_SELECT)
        if not replies:
            break

        # Filter to same-account replies only (thread continuation by original author)
        # Plus any replies from essential tweet accounts
        essential_accounts = set(account_map.get(tid) for tid in needs_conv if account_map.get(tid))
        next_parents = []
        for t in replies:
            tid = str(t["tweet_id"])
            parent_id = str(t["reply_to_tweet_id"])
            t_account = str(t.get("account_id", ""))

            # Find which root this belongs to
            root_id = None
            for rid, members in conv_members.items():
                if parent_id in members:
                    root_id = rid
                    break

            if not root_id:
                continue

            # Get the root's account
            root_account = account_map.get(root_id)

            # Include if: same author as root (thread continuation),
            # or same author as an essential tweet in this conv,
            # or the tweet itself is an essential tweet
            is_thread = t_account == root_account
            is_essential = tid in essential_ids
            is_essential_account = t_account in essential_accounts

            if is_thread or is_essential or is_essential_account:
                all_conv_tweets[tid] = t
                conv_members[root_id].add(tid)
                account_map[tid] = t_account
                reply_map[tid] = parent_id
                next_parents.append(tid)

        current_parents = next_parents
        print(f"    Found {len(replies)} replies, kept {len(next_parents)} thread tweets")

    # Step 4: Fetch full data for root tweets we don't have yet
    roots_to_fetch = [rid for rid in unique_roots if rid not in all_conv_tweets and rid not in bangers["tweets"]]
    if roots_to_fetch:
        print(f"\nStep 4: Fetching {len(roots_to_fetch)} root tweet details...")
        root_data = batch_fetch(client, roots_to_fetch, FULL_SELECT)
        for t in root_data:
            tid = str(t["tweet_id"])
            all_conv_tweets[tid] = t

    client.close()

    # Step 5: Merge into bangers_tweets.json
    print(f"\nStep 5: Merging into bangers_tweets.json...")

    conversations = bangers.get("conversations", {})
    tweet_to_conv = bangers.get("tweetToConversation", {})
    replies_map = bangers.get("replies", {})

    # Add new tweets and build conversation entries
    new_tweets_added = 0
    new_convs_added = 0

    for root_id, members in conv_members.items():
        if len(members) < 1:
            continue

        # Add conversation
        sorted_members = sorted(members)
        conversations[root_id] = sorted_members
        new_convs_added += 1

        # Map each member to conversation
        for tid in members:
            tweet_to_conv[tid] = root_id

            # Add tweet record if missing
            if tid not in bangers["tweets"] and tid in all_conv_tweets:
                bangers["tweets"][tid] = raw_to_record(all_conv_tweets[tid])
                new_tweets_added += 1

            # Add reply mapping
            if reply_map.get(tid):
                replies_map[tid] = reply_map[tid]

    # Also map essential tweets that are their own root (single tweets)
    for tid in needs_conv:
        if tid not in tweet_to_conv and tid in reply_map and reply_map[tid] is None:
            tweet_to_conv[tid] = tid
            if tid not in conversations:
                conversations[tid] = [tid]

    bangers["conversations"] = conversations
    bangers["tweetToConversation"] = tweet_to_conv
    bangers["replies"] = replies_map
    bangers["tweetCount"] = len(bangers["tweets"])

    print(f"  New conversations: {new_convs_added}")
    print(f"  New tweets added: {new_tweets_added}")
    print(f"  Total tweets: {bangers['tweetCount']}")

    # Save
    print("\nSaving...")
    BANGERS_PATH.write_text(json.dumps(bangers))

    # Verify
    found = sum(1 for tid in essential_ids if tid in tweet_to_conv)
    multi = sum(1 for tid in essential_ids if tid in tweet_to_conv and len(conversations.get(tweet_to_conv[tid], [])) > 1)
    print(f"\nVerification:")
    print(f"  Essential tweets with conversation data: {found}/{len(essential_ids)}")
    print(f"  Essential tweets with multi-tweet threads: {multi}/{len(essential_ids)}")


if __name__ == "__main__":
    main()
