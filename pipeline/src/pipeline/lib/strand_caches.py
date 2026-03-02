# %%
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from diskcache import Cache
from tqdm import tqdm

from .conversation_explorer import (
    build_conversation_trees,
    build_incomplete_conversation_trees,
)

# Resolve paths relative to project root (pipeline/src/pipeline/lib/../../..)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SCRATCHPADS_DIR = PROJECT_ROOT / 'scratchpads'

QUOTED_COUNTS_CACHE = SCRATCHPADS_DIR / 'quoted_counts_cache.parquet'
TWEET_DICT_DISKCACHE = SCRATCHPADS_DIR / 'tweet_dict.diskcache'
REPLY_TREES_DISKCACHE = SCRATCHPADS_DIR / 'reply_trees.diskcache'
QUOTE_TWEETS_DISKCACHE = SCRATCHPADS_DIR / 'quote_tweets.diskcache'
FILTERED_QUOTE_TWEETS_DISKCACHE = SCRATCHPADS_DIR / 'filtered_quote_tweets.diskcache'

DEFAULT_PARQUET_PATH = os.environ.get(
    'ENRICHED_TWEETS_PATH',
    str(PROJECT_ROOT.parent / 'data' / 'ca_jan_2026.parquet')
)

_tweet_dict: Optional[Cache] = None
_reply_trees: Optional[Cache] = None
_quote_tweets_dict: Optional[Cache] = None
_filtered_quote_tweets_dict: Optional[Cache] = None


def generate_caches(parquet_path: Optional[str] = None, output_dir: Optional[str] = None) -> Dict[str, Path]:
    """Generate tweet_dict, reply_trees, and quote_tweets caches from enriched_tweets parquet.

    Args:
        parquet_path: Path to parquet file (default: ENRICHED_TWEETS_PATH env var or ~/data/enriched_tweets.parquet)
        output_dir: Directory to save caches (default: scratchpads directory, will overwrite existing)

    Returns:
        Dict with paths to created caches
    """
    import pandas as pd
    from .count_quotes import count_quotes

    path = Path(parquet_path or DEFAULT_PARQUET_PATH).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    # Determine output paths
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tweet_dict_path = out_dir / 'tweet_dict.diskcache'
        reply_trees_path = out_dir / 'reply_trees.diskcache'
        quote_tweets_path = out_dir / 'quote_tweets.diskcache'
        quoted_counts_path = out_dir / 'quoted_counts_cache.parquet'
    else:
        out_dir = SCRATCHPADS_DIR
        tweet_dict_path = TWEET_DICT_DISKCACHE
        reply_trees_path = REPLY_TREES_DISKCACHE
        quote_tweets_path = QUOTE_TWEETS_DISKCACHE
        quoted_counts_path = QUOTED_COUNTS_CACHE

    print(f"Output directory: {out_dir}")

    print(f"Loading tweets from {path}...")
    t0 = time.time()
    tweets = pd.read_parquet(path, dtype_backend='pyarrow')
    tweets = tweets.set_index('tweet_id', drop=False)
    print(f"Loaded {len(tweets):,} tweets in {time.time()-t0:.1f}s")

    # Quoted counts
    if quoted_counts_path.exists():
        print("Loading quoted counts from cache...")
        quoted_counts = pd.read_parquet(quoted_counts_path)
    else:
        print("Calculating quoted counts...")
        quoted_counts = count_quotes(tweets)
        quoted_counts = quoted_counts.groupby('quoted_tweet_id', as_index=False)['quoted_count'].sum()
        quoted_counts.to_parquet(quoted_counts_path)

    tweets = tweets.merge(
        quoted_counts,
        left_index=True,
        right_on='quoted_tweet_id',
        how='left',
        suffixes=('', '_drop')
    )
    tweets = tweets.drop(columns=['quoted_tweet_id_drop'], errors='ignore')
    tweets['quoted_count'] = tweets['quoted_count'].fillna(0).astype(int)
    if tweets.index.name == 'index':
        tweets = tweets.reset_index(drop=False)
    tweets = tweets.set_index('tweet_id', drop=False)
    tweets.index.name = 'index'

    print("Converting to list of dicts...")
    tweets_list = tweets.to_dict(orient='records')
    del tweets

    # Build tweet_dict
    print(f"Writing tweet_dict to {tweet_dict_path}...")
    t0 = time.time()
    tweet_dict = {t['tweet_id']: t for t in tweets_list}
    with Cache(str(tweet_dict_path), size_limit=15 * 1024**3) as cache:
        cache.clear()
        for k, v in tqdm(tweet_dict.items(), desc="tweet_dict", file=sys.stdout, mininterval=0.5):
            cache[k] = v
    print(f"Saved {len(tweet_dict):,} tweets in {time.time()-t0:.1f}s")

    # Build quote_tweets index
    print(f"Writing quote_tweets to {quote_tweets_path}...")
    t0 = time.time()
    quote_tweets_dict: Dict[int, List[int]] = {}
    for tweet in tweet_dict.values():
        quoted_id = tweet.get('quoted_tweet_id')
        if quoted_id is not None:
            quote_tweets_dict.setdefault(quoted_id, []).append(tweet['tweet_id'])
    with Cache(str(quote_tweets_path), size_limit=800 * 1024**2) as cache:
        cache.clear()
        for k, v in tqdm(quote_tweets_dict.items(), desc="quote_tweets", file=sys.stdout, mininterval=0.5):
            cache[k] = v
    print(f"Saved {len(quote_tweets_dict):,} quote mappings in {time.time()-t0:.1f}s")
    del tweet_dict

    # Build conversation trees
    print("Building conversation trees...")
    t0 = time.time()
    conversation_tweets = [t for t in tweets_list if t['conversation_id'] is not None]
    trees = build_conversation_trees(conversation_tweets)

    non_conv_tweets = [t for t in tweets_list if t['conversation_id'] is None]
    incomplete_trees = build_incomplete_conversation_trees(non_conv_tweets, [])

    complete_reply_trees = {**trees, **incomplete_trees}

    print(f"Writing reply_trees to {reply_trees_path}...")
    with Cache(str(reply_trees_path), size_limit=8 * 1024**3) as cache:
        cache.clear()
        for k, v in tqdm(complete_reply_trees.items(), desc="reply_trees", file=sys.stdout, mininterval=0.5):
            cache[k] = v
    print(f"Saved {len(complete_reply_trees):,} trees in {time.time()-t0:.1f}s")

    print(f"\nCaches saved to {out_dir}")

    return {
        'tweet_dict': tweet_dict_path,
        'reply_trees': reply_trees_path,
        'quote_tweets': quote_tweets_path,
        'quoted_counts': quoted_counts_path,
    }


def load_caches(auto_generate: bool = True) -> tuple[Cache, Cache]:
    """Load cached tweet_dict and complete_reply_trees as diskcache objects."""
    global _tweet_dict, _reply_trees
    if _tweet_dict is not None and _reply_trees is not None:
        return _tweet_dict, _reply_trees

    if not TWEET_DICT_DISKCACHE.exists() or not REPLY_TREES_DISKCACHE.exists():
        if auto_generate:
            print("Cache files not found. Generating from parquet...")
            generate_caches()
        else:
            raise FileNotFoundError(
                f"Cache files not found. Set ENRICHED_TWEETS_PATH env var and call generate_caches(), or run:\n"
                f"  from lib.strand_caches import generate_caches; generate_caches('/path/to/enriched_tweets.parquet')"
            )
    
    print("Opening diskcache stores...")
    _tweet_dict = Cache(str(TWEET_DICT_DISKCACHE))
    _reply_trees = Cache(str(REPLY_TREES_DISKCACHE))
    print(f"Loaded {len(_tweet_dict)} tweets and {len(_reply_trees)} reply trees")
    return _tweet_dict, _reply_trees


def get_quote_tweets_dict() -> Cache:
    """Load quote_tweets index as diskcache: quoted_tweet_id -> list of quoting tweet_ids."""
    global _quote_tweets_dict
    if _quote_tweets_dict is not None:
        return _quote_tweets_dict
    
    if not QUOTE_TWEETS_DISKCACHE.exists():
        raise FileNotFoundError("Quote tweets cache not found. Run generate_caches().")
    
    print("Opening quote_tweets diskcache...")
    _quote_tweets_dict = Cache(str(QUOTE_TWEETS_DISKCACHE))
    print(f"Loaded quote index with {len(_quote_tweets_dict)} quoted tweets")
    return _quote_tweets_dict


def generate_filtered_quote_cache(parquet_path: Optional[str] = None, output_dir: Optional[str] = None) -> Path:
    """Generate self-quote-filtered quote_tweets diskcache.

    Maps quoted_tweet_id -> [quoting_tweet_ids] where the quoting user != quoted tweet author.
    This is the authoritative source for quote relationships (no self-quotes).

    Args:
        parquet_path: Path to parquet file (default: DEFAULT_PARQUET_PATH)
        output_dir: Directory to save cache (default: scratchpads directory)

    Returns:
        Path to the created diskcache
    """
    import pandas as pd

    path = Path(parquet_path or DEFAULT_PARQUET_PATH).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    if output_dir:
        out_path = Path(output_dir) / 'filtered_quote_tweets.diskcache'
    else:
        out_path = FILTERED_QUOTE_TWEETS_DISKCACHE

    print(f"Loading tweets from {path} for filtered quote cache...")
    t0 = time.time()
    df = pd.read_parquet(path, columns=['tweet_id', 'account_id', 'quoted_tweet_id'], dtype_backend='pyarrow')
    df = df.drop_duplicates('tweet_id')
    print(f"Loaded {len(df):,} tweets in {time.time()-t0:.1f}s")

    # Filter to rows with quotes
    quotes = df[df['quoted_tweet_id'].notna()].copy()
    print(f"Found {len(quotes):,} quote tweets")

    # Get author of quoted tweets via lookup
    author_map = df.set_index('tweet_id')['account_id']
    quotes['quoted_author_id'] = quotes['quoted_tweet_id'].map(author_map)

    # Filter self-quotes
    non_self = quotes[quotes['account_id'] != quotes['quoted_author_id']]
    self_quote_count = len(quotes) - len(non_self)
    print(f"After self-quote filter: {len(non_self):,} quotes ({self_quote_count:,} self-quotes removed)")

    # Build index: quoted_tweet_id -> [quoting_tweet_ids]
    quote_index: Dict[int, List[int]] = {}
    for quoted_id, group in non_self.groupby('quoted_tweet_id'):
        quote_index[quoted_id] = group['tweet_id'].tolist()

    # Save to diskcache
    print(f"Writing filtered quote_tweets to {out_path}...")
    with Cache(str(out_path), size_limit=800 * 1024**2) as cache:
        cache.clear()
        for k, v in tqdm(quote_index.items(), desc="filtered_quote_tweets", file=sys.stdout, mininterval=0.5):
            cache[k] = v

    print(f"Saved {len(quote_index):,} filtered quote mappings in {time.time()-t0:.1f}s")
    return out_path


def get_filtered_quote_tweets_dict() -> Cache:
    """Load self-quote-filtered quote_tweets index as diskcache.

    Maps quoted_tweet_id -> list of quoting tweet_ids (self-quotes excluded).
    """
    global _filtered_quote_tweets_dict
    if _filtered_quote_tweets_dict is not None:
        return _filtered_quote_tweets_dict

    if not FILTERED_QUOTE_TWEETS_DISKCACHE.exists():
        raise FileNotFoundError(
            "Filtered quote tweets cache not found. Run generate_filtered_quote_cache() first."
        )

    print("Opening filtered_quote_tweets diskcache...")
    _filtered_quote_tweets_dict = Cache(str(FILTERED_QUOTE_TWEETS_DISKCACHE))
    print(f"Loaded filtered quote index with {len(_filtered_quote_tweets_dict)} quoted tweets")
    return _filtered_quote_tweets_dict


# %%
