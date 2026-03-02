"""
Generate bangers_tweets.json for local-first website operation.

Sources:
1. atlas_data.json - 37k tweets with text, usernames, UMAP coords
2. strands_data.json - 252 strands with full seedTweet objects
3. rated_strands/*.json - Thread text with conversation structure
4. tweet_dict.diskcache - Full tweet data with account_id
5. quote_tweets.diskcache - Quote relationships
6. valid_account_ids_cache.json - Archive user account IDs

Output: top-qt-website/bangers/public/bangers_tweets.json

Key metrics:
- archive_quote_count: Number of quotes from people in the archive (primary ranking metric)
- quote_count: Total number of quotes (secondary metric)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

from diskcache import Cache


SCRIPT_DIR = Path(__file__).parent
BANGERS_DIR = SCRIPT_DIR.parent / "bangers"
PUBLIC_DIR = BANGERS_DIR / "public"
RATED_STRANDS_DIR = SCRIPT_DIR / "data" / "rated_strands"
VALID_ACCOUNTS_PATH = SCRIPT_DIR / "data" / "valid_account_ids_cache.json"
TWEET_DICT_PATH = SCRIPT_DIR / "tweet_dict.diskcache"
QUOTE_TWEETS_PATH = SCRIPT_DIR / "quote_tweets.diskcache"


def parse_thread_text(thread_text: str) -> dict:
    """
    Parse ASCII tree thread_text to extract tweet IDs, relationships, and metadata.

    Format example:
    1037715339314847747 [2018-09-06] @visakanv 💜 645 🔁 177 [(SEED) type=root]
    The courage to be disliked...
    ├── 1037718768032641025 [2018-09-06] @visakanv 💜 73 🔁 5
    │   Youth tells philosopher...
    │   ↓
    │   1037718770234474496 [2018-09-06] @visakanv 💜 55 🔁 1
    │   ...

    Returns dict with:
    - tweets: {tweet_id: {username, likes, retweets, date, text, seed_type}}
    - replies: {tweet_id: parent_tweet_id}
    - conversation_ids: {tweet_id: root_tweet_id}
    """
    tweets = {}
    replies = {}  # child -> parent
    conversation_ids = {}

    # Pattern to match tweet headers
    # Format: ID [DATE] @username 💜 LIKES 🔁 RTS [optional tags]
    header_pattern = re.compile(
        r'(\d{15,20})\s*\[(\d{4}-\d{2}-\d{2})\]\s*@(\w+)\s*💜\s*(\d+)\s*🔁\s*(\d+)(?:\s*\[(.*?)\])?'
    )

    lines = thread_text.split('\n')
    current_tweet_id = None
    current_text_lines = []
    indent_stack = []  # Stack of (indent_level, tweet_id) for tracking parent-child
    root_id = None

    def save_current_tweet():
        nonlocal current_tweet_id, current_text_lines
        if current_tweet_id and current_tweet_id in tweets:
            # Clean up text - remove tree characters and join
            text = '\n'.join(current_text_lines).strip()
            # Remove leading tree characters
            text = re.sub(r'^[│├└─↓\s]+', '', text, flags=re.MULTILINE)
            text = text.strip()
            if text:
                tweets[current_tweet_id]['text'] = text

    for line in lines:
        # Check for tweet header
        match = header_pattern.search(line)
        if match:
            # Save previous tweet's text
            save_current_tweet()

            tweet_id = match.group(1)
            date = match.group(2)
            username = match.group(3)
            likes = int(match.group(4))
            retweets = int(match.group(5))
            tags = match.group(6) or ""

            # Determine indent level by counting tree characters
            indent_match = re.match(r'^([│├└\s─]*)', line)
            indent_str = indent_match.group(1) if indent_match else ""
            # Normalize indent - count significant tree chars
            indent_level = indent_str.count('├') + indent_str.count('└') + indent_str.count('│')

            # Track root
            if root_id is None:
                root_id = tweet_id

            # Determine parent based on indent
            parent_id = None
            while indent_stack and indent_stack[-1][0] >= indent_level:
                indent_stack.pop()
            if indent_stack:
                parent_id = indent_stack[-1][1]

            indent_stack.append((indent_level, tweet_id))

            # Parse seed type from tags
            seed_type = None
            if 'type=' in tags:
                seed_match = re.search(r'type=(\w+)', tags)
                if seed_match:
                    seed_type = seed_match.group(1)

            tweets[tweet_id] = {
                'tweet_id': tweet_id,
                'date': date,
                'username': username,
                'likes': likes,
                'retweets': retweets,
                'seed_type': seed_type,
                'text': '',
            }

            if parent_id:
                replies[tweet_id] = parent_id

            conversation_ids[tweet_id] = root_id
            current_tweet_id = tweet_id
            current_text_lines = []

        elif current_tweet_id:
            # This is content for the current tweet
            # Skip lines that are just tree structure
            cleaned = re.sub(r'^[│├└─\s]+', '', line)
            if cleaned.strip() and not cleaned.strip().startswith('↓'):
                current_text_lines.append(cleaned)

    # Save last tweet
    save_current_tweet()

    return {
        'tweets': tweets,
        'replies': replies,
        'conversation_ids': conversation_ids,
    }


def load_atlas_data() -> dict:
    """Load and parse atlas_data.json."""
    print("Loading atlas_data.json...")
    atlas_path = PUBLIC_DIR / "atlas_data.json"
    with open(atlas_path, 'r') as f:
        data = json.load(f)

    tweets = {}
    for t in data.get('tweets', []):
        tweet_id = str(t['id'])
        tweets[tweet_id] = {
            'tweet_id': tweet_id,
            'strand_id': str(t.get('sid', '')),
            'full_text': t.get('txt', ''),
            'username': t.get('u', 'unknown'),
            'favorite_count': t.get('lk', 0),
            'retweet_count': t.get('rt', 0),
            'created_at': t.get('dt', ''),
            'annotation': t.get('a', ''),
            'is_essential': t.get('e', 0) == 1,
            'x': t.get('x'),
            'y': t.get('y'),
        }

    print(f"  Loaded {len(tweets)} tweets from atlas_data.json")
    return tweets


def load_strands_data() -> dict:
    """Load strands_data.json for seed tweets with full Tweet objects."""
    print("Loading strands_data.json...")
    strands_path = PUBLIC_DIR / "strands_data.json"
    with open(strands_path, 'r') as f:
        data = json.load(f)

    tweets = {}
    strands = []

    for strand in data.get('strands', []):
        seed_tweet = strand.get('seedTweet', {})
        if seed_tweet:
            tweet_id = str(seed_tweet.get('tweet_id', ''))
            if tweet_id:
                tweets[tweet_id] = {
                    'tweet_id': tweet_id,
                    'created_at': seed_tweet.get('created_at', ''),
                    'full_text': seed_tweet.get('full_text', ''),
                    'username': seed_tweet.get('username', 'unknown'),
                    'avatar_media_url': seed_tweet.get('avatar_media_url'),
                    'favorite_count': seed_tweet.get('favorite_count', 0),
                    'retweet_count': seed_tweet.get('retweet_count', 0),
                    'quote_count': seed_tweet.get('quote_count'),
                    'media_urls': seed_tweet.get('media_urls', []),
                }

        strands.append({
            'seed_tweet_id': str(strand.get('seed_tweet_id', '')),
            'title': strand.get('title', ''),
            'seeds': strand.get('seeds', []),
        })

    print(f"  Loaded {len(tweets)} seed tweets from strands_data.json")
    return tweets, strands


def load_rated_strands() -> tuple:
    """Load all rated strands and extract tweet data from thread_text."""
    print("Loading rated strands...")

    all_tweets = {}
    all_replies = {}
    all_conversations = {}
    quote_relationships = defaultdict(list)  # quoted_id -> [quoting_ids]

    strand_files = list(RATED_STRANDS_DIR.glob("*.json"))
    print(f"  Found {len(strand_files)} strand files")

    for strand_file in strand_files:
        with open(strand_file, 'r') as f:
            strand = json.load(f)

        seed_id = str(strand.get('seed_tweet_id', ''))
        thread_text = strand.get('thread_text', '')
        seeds = strand.get('seeds', [])

        # Parse thread text for tweet data
        if thread_text:
            parsed = parse_thread_text(thread_text)

            for tid, tweet_data in parsed['tweets'].items():
                if tid not in all_tweets:
                    all_tweets[tid] = {
                        'tweet_id': tid,
                        'created_at': tweet_data['date'] + 'T00:00:00Z' if tweet_data.get('date') else '',
                        'full_text': tweet_data.get('text', ''),
                        'username': tweet_data.get('username', 'unknown'),
                        'favorite_count': tweet_data.get('likes', 0),
                        'retweet_count': tweet_data.get('retweets', 0),
                    }

            all_replies.update(parsed['replies'])
            all_conversations.update(parsed['conversation_ids'])

        # Extract quote relationships from seeds
        for seed in seeds:
            seed_tid = str(seed.get('tweet_id', seed.get('id', '')))
            source_type = seed.get('source_type', seed.get('type', ''))

            # quote_of_root means this tweet quotes the root
            if source_type == 'quote_of_root' and seed_id:
                quote_relationships[seed_id].append(seed_tid)
            # quote_of_semantic_search - these quote some semantic match
            # We don't have the original quoted tweet ID easily, skip for now

    print(f"  Extracted {len(all_tweets)} tweets from thread_text")
    print(f"  Found {len(all_replies)} reply relationships")
    print(f"  Found {sum(len(v) for v in quote_relationships.values())} quote relationships")

    return all_tweets, all_replies, all_conversations, dict(quote_relationships)


def merge_tweet_data(*sources) -> dict:
    """Merge tweet data from multiple sources, preferring more complete data."""
    merged = {}

    for source in sources:
        for tid, tweet in source.items():
            if tid not in merged:
                merged[tid] = tweet.copy()
            else:
                # Merge, preferring non-empty values
                existing = merged[tid]
                for key, value in tweet.items():
                    if value and (not existing.get(key) or existing.get(key) in ['', 0, [], 'unknown']):
                        existing[key] = value

    return merged


def load_valid_account_ids() -> set:
    """Load valid account IDs from cache (archive_upload + optin users)."""
    print("Loading valid account IDs...")
    if not VALID_ACCOUNTS_PATH.exists():
        print("  Warning: valid_account_ids_cache.json not found")
        return set()

    with open(VALID_ACCOUNTS_PATH, 'r') as f:
        data = json.load(f)

    account_ids = set(data.get('account_ids', []))
    print(f"  Loaded {len(account_ids)} valid account IDs (fetched {data.get('fetched_at', 'unknown')})")
    return account_ids


def compute_archive_quote_counts(valid_account_ids: set) -> dict:
    """
    Compute quote counts from archive users only.

    Uses tweet_dict.diskcache and quote_tweets.diskcache to:
    1. Get all quote relationships
    2. Filter to only count quotes from valid (archive) accounts

    Returns: {quoted_tweet_id: archive_quote_count}
    """
    print("\nComputing archive quote counts...")

    if not TWEET_DICT_PATH.exists():
        print("  Warning: tweet_dict.diskcache not found")
        return {}

    if not QUOTE_TWEETS_PATH.exists():
        print("  Warning: quote_tweets.diskcache not found")
        return {}

    # Load caches
    print("  Loading tweet_dict.diskcache...")
    tweet_dict = Cache(str(TWEET_DICT_PATH))
    print(f"    {len(tweet_dict)} tweets")

    print("  Loading quote_tweets.diskcache...")
    quote_tweets = Cache(str(QUOTE_TWEETS_PATH))
    print(f"    {len(quote_tweets)} quoted tweets with quotes")

    # Compute archive quote counts
    print("  Computing archive quote counts...")
    archive_counts = {}
    total_quotes = {}

    for quoted_id in tqdm(quote_tweets.iterkeys(), total=len(quote_tweets), desc="  Processing"):
        quoting_ids = quote_tweets.get(quoted_id, [])

        # Count total quotes
        total_quotes[str(quoted_id)] = len(quoting_ids)

        # Count archive quotes (from valid accounts only)
        archive_count = 0
        for quoting_id in quoting_ids:
            quoting_tweet = tweet_dict.get(quoting_id)
            if quoting_tweet:
                account_id = str(quoting_tweet.get('account_id', ''))
                if account_id in valid_account_ids:
                    archive_count += 1

        if archive_count > 0:
            archive_counts[str(quoted_id)] = archive_count

    tweet_dict.close()
    quote_tweets.close()

    print(f"  Found {len(archive_counts)} tweets with archive quotes")
    print(f"  Total tweets with any quotes: {len(total_quotes)}")

    # Show top 10 by archive quote count
    top_10 = sorted(archive_counts.items(), key=lambda x: -x[1])[:10]
    print("\n  Top 10 by archive quote count:")
    for tid, count in top_10:
        print(f"    {tid}: {count} archive quotes")

    return archive_counts, total_quotes


def build_by_year(tweets: dict) -> dict:
    """Build tweet IDs sorted by archive_quote_count for each year.

    Primary sort: archive_quote_count (quotes from archive users)
    Secondary sort: quote_count (total quotes)
    Tertiary: favorite_count (likes)
    """
    by_year = defaultdict(list)

    for tid, tweet in tweets.items():
        created_at = tweet.get('created_at', '')
        archive_quote_count = tweet.get('archive_quote_count', 0) or 0
        quote_count = tweet.get('quote_count', 0) or 0
        favorite_count = tweet.get('favorite_count', 0) or 0

        # Extract year from created_at
        year = None
        if created_at:
            try:
                if 'T' in created_at:
                    year = int(created_at[:4])
                elif len(created_at) >= 4:
                    year = int(created_at[:4])
            except (ValueError, TypeError):
                pass

        if year:
            # Sort key: (archive_quote_count, quote_count, favorite_count)
            sort_key = (archive_quote_count, quote_count, favorite_count)
            by_year[str(year)].append((tid, sort_key))

    # Sort each year by sort_key descending
    result = {}
    for year, tweets_list in by_year.items():
        sorted_ids = [tid for tid, _ in sorted(tweets_list, key=lambda x: x[1], reverse=True)]
        result[year] = sorted_ids

    return result


def main():
    # Load valid account IDs first
    valid_account_ids = load_valid_account_ids()

    # Compute archive quote counts from diskcaches
    archive_counts, total_counts = compute_archive_quote_counts(valid_account_ids)

    # Load all data sources
    atlas_tweets = load_atlas_data()
    strands_tweets, strands = load_strands_data()
    thread_tweets, replies, conversations, quotes_of = load_rated_strands()

    # Merge all tweet data
    print("\nMerging tweet data...")
    all_tweets = merge_tweet_data(strands_tweets, atlas_tweets, thread_tweets)
    print(f"  Total unique tweets: {len(all_tweets)}")

    # Add archive_quote_count and quote_count to tweets
    print("\nAdding quote counts to tweets...")
    tweets_with_archive_quotes = 0
    for tid, tweet in all_tweets.items():
        # Set archive_quote_count (primary ranking metric)
        if tid in archive_counts:
            tweet['archive_quote_count'] = archive_counts[tid]
            tweets_with_archive_quotes += 1

        # Set quote_count (total quotes) if not already set
        if tid in total_counts:
            if not tweet.get('quote_count'):
                tweet['quote_count'] = total_counts[tid]
    print(f"  {tweets_with_archive_quotes} tweets have archive quotes")

    # Build year index (now sorted by archive_quote_count)
    print("\nBuilding year index (sorted by archive_quote_count)...")
    by_year = build_by_year(all_tweets)
    for year in sorted(by_year.keys(), reverse=True)[:5]:
        # Show top tweet for each year
        top_tid = by_year[year][0] if by_year[year] else None
        if top_tid:
            top_tweet = all_tweets.get(top_tid, {})
            aqc = top_tweet.get('archive_quote_count', 0)
            print(f"  {year}: {len(by_year[year])} tweets (top: {aqc} archive quotes)")
        else:
            print(f"  {year}: {len(by_year[year])} tweets")

    # Build quote relationships (bidirectional)
    print("\nBuilding quote relationships...")
    quoted_by = {}  # quote_tweet -> original_tweet
    for original_id, quote_ids in quotes_of.items():
        for quote_id in quote_ids:
            quoted_by[quote_id] = original_id
    print(f"  quotesOf entries: {len(quotes_of)}")
    print(f"  quotedBy entries: {len(quoted_by)}")

    # Build conversation mapping
    print("\nBuilding conversation mappings...")
    conversations_by_id = defaultdict(list)
    for tweet_id, conv_id in conversations.items():
        conversations_by_id[conv_id].append(tweet_id)
    print(f"  Conversations: {len(conversations_by_id)}")

    # Build output structure
    output = {
        'generatedAt': datetime.now().isoformat(),
        'tweetCount': len(all_tweets),
        'tweets': all_tweets,
        'byYear': by_year,
        'quoteRelationships': {
            'quotesOf': quotes_of,
            'quotedBy': quoted_by,
        },
        'conversations': dict(conversations_by_id),
        'tweetToConversation': conversations,
        'replies': replies,
    }

    # Write output
    output_path = PUBLIC_DIR / "bangers_tweets.json"
    print(f"\nWriting to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f)

    # Get file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  File size: {size_mb:.2f} MB")
    print("\nDone!")


if __name__ == "__main__":
    main()
