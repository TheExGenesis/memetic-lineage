"""Phase 0: Generate bangers_tweets.json for the website frontend.

Loads tweet data from diskcaches (tweet_dict + filtered_quote_tweets),
finds all tweets quoted by community archive users, and outputs
bangers_tweets.json with quote relationships, conversations, and year index.

This is a standalone phase that only depends on diskcaches being generated.
It does NOT depend on strands/atlas data.
"""

import json
import sys
import time as _time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from pipeline.config import BANGERS_EXPORT_PATH, FRONTEND_PUBLIC_DIR, VALID_ACCOUNTS_PATH
from pipeline.helpers import _to_int_id, _to_str_id, _is_valid, _tweet_dict_to_bangers
from pipeline.lib.strand_caches import (
    load_caches, get_filtered_quote_tweets_dict, DEFAULT_PARQUET_PATH,
)


def _load_valid_account_ids() -> set:
    """Load valid account IDs from cache (archive users)."""
    if not VALID_ACCOUNTS_PATH.exists():
        print(f"  [WARN] {VALID_ACCOUNTS_PATH} not found, archive_quote_count will be 0")
        return set()
    with open(VALID_ACCOUNTS_PATH) as f:
        data = json.load(f)
    ids = set(str(aid) for aid in data.get('account_ids', []))
    print(f"  Loaded {len(ids)} valid account IDs")
    return ids


def run(parquet_path: str = None) -> bool:
    """Generate bangers_tweets.json for the website frontend."""
    print("\n" + "=" * 60)
    print("PHASE 0: Generate Bangers Data")
    print("=" * 60)

    # ---- Load diskcaches ----
    print("Loading diskcaches...")
    tweet_dict, reply_trees = load_caches(auto_generate=False)
    filtered_qt = get_filtered_quote_tweets_dict()
    print(f"  tweet_dict: {len(tweet_dict):,} tweets")
    print(f"  filtered_quote_tweets: {len(filtered_qt):,} quoted tweets")

    # ---- Load valid account IDs (archive users) ----
    valid_account_ids = set(_load_valid_account_ids())  # already strings
    print(f"  Archive accounts: {len(valid_account_ids)}")

    # ---- Build account_id lookup from parquet (fast: only 2 columns) ----
    print("\nLoading account_id mapping from parquet...")
    t0 = _time.time()
    pq_path = Path(parquet_path or DEFAULT_PARQUET_PATH).expanduser()
    account_df = pd.read_parquet(pq_path, columns=['tweet_id', 'account_id'])
    account_df = account_df.drop_duplicates('tweet_id')
    account_df['tweet_id'] = account_df['tweet_id'].astype(str)
    account_df['account_id'] = account_df['account_id'].astype(str)
    tweet_account_map = dict(zip(account_df['tweet_id'], account_df['account_id']))
    del account_df
    print(f"  Loaded {len(tweet_account_map):,} tweet->account mappings in {_time.time()-t0:.1f}s")

    # ---- Find all quoted tweets and compute both quote counts ----
    print("\nBuilding quote relationships (all users + archive users)...")
    t0 = _time.time()
    all_tweets = {}     # tweet_id (str) -> tweet data dict
    quotes_of = {}      # quoted_tweet_id -> [archive quoting_tweet_ids]
    quoted_by = {}      # quoting_tweet_id -> quoted_tweet_id (archive quotes only)
    quote_count_all = {}      # quoted_tweet_id (str) -> total quote count
    quote_count_archive = {}  # quoted_tweet_id (str) -> archive user quote count
    tweet_ids_to_fetch = set()

    for quoted_int_id in tqdm(filtered_qt.iterkeys(), desc="quote_rels",
                              total=len(filtered_qt), file=sys.stdout, mininterval=1.0):
        quoting_ids = filtered_qt[quoted_int_id]
        if not quoting_ids:
            continue

        quoted_str = _to_str_id(quoted_int_id)

        # Count ALL quotes (already self-quote filtered by filtered_qt)
        quote_count_all[quoted_str] = len(quoting_ids)

        # Filter to archive user quotes
        archive_quoting_ids = []
        for qid in quoting_ids:
            qid_str = str(int(qid)) if not isinstance(qid, str) else qid
            quoting_account = tweet_account_map.get(qid_str)
            if quoting_account is not None and quoting_account in valid_account_ids:
                archive_quoting_ids.append(qid)

        quote_count_archive[quoted_str] = len(archive_quoting_ids)

        # Include ALL quoted tweets
        tweet_ids_to_fetch.add(quoted_int_id)

        # quotesOf only stores archive-user quote IDs
        if archive_quoting_ids:
            quoting_str_ids = [_to_str_id(qid) for qid in archive_quoting_ids]
            quotes_of[quoted_str] = quoting_str_ids
            for qid, qid_str in zip(archive_quoting_ids, quoting_str_ids):
                quoted_by[qid_str] = quoted_str
                tweet_ids_to_fetch.add(_to_int_id(qid))

    elapsed_filter = _time.time() - t0
    print(f"  Tweets with any quotes: {len(quote_count_all):,}")
    print(f"  quotesOf (archive): {len(quotes_of):,} tweets have quotes from archive users")
    print(f"  quotedBy (archive): {len(quoted_by):,} entries")
    print(f"  Need to fetch {len(tweet_ids_to_fetch):,} tweets from diskcache")
    print(f"  Filtering took {elapsed_filter:.1f}s")

    # ---- Fetch tweet data from diskcache ----
    print("\nFetching tweet data from tweet_dict diskcache...")
    t0 = _time.time()
    for int_tid in tqdm(tweet_ids_to_fetch, desc="fetch_tweets",
                        file=sys.stdout, mininterval=1.0):
        str_tid = _to_str_id(int_tid)
        if str_tid in all_tweets:
            continue
        tweet_data = tweet_dict.get(int_tid)
        if tweet_data:
            t = _tweet_dict_to_bangers(tweet_data)
            if str_tid in quoted_by:
                t['quoted_tweet_id'] = quoted_by[str_tid]
            all_tweets[str_tid] = t

    print(f"  Fetched {len(all_tweets):,} tweets in {_time.time()-t0:.1f}s")

    # Set both quote counts and archive user flag
    for tid, tweet in all_tweets.items():
        tweet['quote_count'] = quote_count_all.get(tid, 0)
        tweet['archive_quote_count'] = quote_count_archive.get(tid, 0)
        tweet['is_archive_user'] = tweet_account_map.get(tid, '') in valid_account_ids

    # ---- Build conversation mappings from tweet_dict ----
    print("\nBuilding conversation mappings...")
    conversations_by_id = defaultdict(list)
    tweet_to_conversation = {}

    for tid, tweet in all_tweets.items():
        int_tid = _to_int_id(tid)
        t = tweet_dict.get(int_tid)
        if not t:
            continue
        conv_id = t.get('conversation_id')
        if _is_valid(conv_id):
            conv_str = _to_str_id(conv_id)
            tweet_to_conversation[tid] = conv_str
            conversations_by_id[conv_str].append(tid)

    print(f"  Conversations: {len(conversations_by_id):,}")
    print(f"  Tweets in conversations: {len(tweet_to_conversation):,}")

    # ---- Build reply mappings from tweet_dict ----
    print("Building reply mappings...")
    replies = {}
    for tid in all_tweets:
        int_tid = _to_int_id(tid)
        t = tweet_dict.get(int_tid)
        if not t:
            continue
        reply_to = t.get('reply_to_tweet_id')
        if _is_valid(reply_to):
            replies[tid] = _to_str_id(reply_to)
    print(f"  Replies: {len(replies):,}")

    # ---- Build year index ----
    print("\nBuilding year index (sorted by quote_count from all users)...")
    by_year = defaultdict(list)
    for tid, tweet in all_tweets.items():
        created_at = tweet.get('created_at', '')
        qc = tweet.get('quote_count', 0) or 0
        fav = tweet.get('favorite_count', 0) or 0

        year = None
        if created_at:
            try:
                year = int(str(created_at)[:4])
            except (ValueError, TypeError):
                pass

        if year and 2006 <= year <= 2026:
            by_year[str(year)].append((tid, (qc, fav)))

    MAX_PER_YEAR = 500
    by_year_sorted = {}
    for year, tweets_list in sorted(by_year.items(), reverse=True):
        sorted_ids = [tid for tid, _ in sorted(tweets_list, key=lambda x: x[1], reverse=True)]
        by_year_sorted[year] = sorted_ids[:MAX_PER_YEAR]

    for year in sorted(by_year_sorted.keys(), reverse=True)[:5]:
        total = len([t for t in by_year[year]])
        capped = len(by_year_sorted[year])
        top_tid = by_year_sorted[year][0] if by_year_sorted[year] else None
        if top_tid:
            top = all_tweets.get(top_tid, {})
            print(f"  {year}: {capped}/{total} tweets (top: @{top.get('username', '?')} qc={top.get('quote_count', 0)} archive_qc={top.get('archive_quote_count', 0)})")

    # ---- Prune to only reachable tweets ----
    print("\nPruning to reachable tweets...")
    reachable_ids = set()
    for year_ids in by_year_sorted.values():
        reachable_ids.update(year_ids)

    for tid in list(reachable_ids):
        if tid in quotes_of:
            reachable_ids.update(quotes_of[tid])

    for tid in list(reachable_ids):
        if tid in quoted_by:
            reachable_ids.add(quoted_by[tid])

    pruned_tweets = {tid: all_tweets[tid] for tid in reachable_ids if tid in all_tweets}
    pruned_quotes_of = {tid: ids for tid, ids in quotes_of.items() if tid in reachable_ids}
    pruned_quoted_by = {tid: qid for tid, qid in quoted_by.items() if tid in reachable_ids}
    pruned_conversations = {cid: [t for t in tids if t in reachable_ids]
                            for cid, tids in conversations_by_id.items()
                            if any(t in reachable_ids for t in tids)}
    pruned_t2c = {tid: cid for tid, cid in tweet_to_conversation.items() if tid in reachable_ids}
    pruned_replies = {tid: pid for tid, pid in replies.items() if tid in reachable_ids}

    print(f"  Full dataset: {len(all_tweets):,} tweets")
    print(f"  Pruned to: {len(pruned_tweets):,} reachable tweets")
    print(f"  quotesOf: {len(pruned_quotes_of):,}, quotedBy: {len(pruned_quoted_by):,}")

    # ---- Clean tweet data for JSON output ----
    for tid, tweet in pruned_tweets.items():
        for key, val in tweet.items():
            if hasattr(val, 'item'):  # numpy scalar
                tweet[key] = val.item()
            elif pd.notna(val) is False:
                tweet[key] = None

    # ---- Output ----
    output = {
        'generatedAt': datetime.now().isoformat(),
        'tweetCount': len(pruned_tweets),
        'tweets': pruned_tweets,
        'byYear': by_year_sorted,
        'quoteRelationships': {
            'quotesOf': pruned_quotes_of,
            'quotedBy': pruned_quoted_by,
        },
        'conversations': pruned_conversations,
        'tweetToConversation': pruned_t2c,
        'replies': pruned_replies,
    }

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting to {BANGERS_EXPORT_PATH}...")
    with open(BANGERS_EXPORT_PATH, 'w') as f:
        json.dump(output, f, default=str)

    size_mb = BANGERS_EXPORT_PATH.stat().st_size / (1024 * 1024)
    print(f"  File size: {size_mb:.1f} MB")
    print(f"  Tweets: {len(pruned_tweets):,}")
    print(f"  Years: {len(by_year_sorted)}")
    print(f"  Quote relationships: {len(pruned_quotes_of):,} quotesOf, {len(pruned_quoted_by):,} quotedBy")
    print(f"  Conversations: {len(pruned_conversations):,}")
    print("Phase 0 complete!")
    return True
