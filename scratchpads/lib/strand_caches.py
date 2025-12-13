# %%
import os
import joblib
from pathlib import Path
from typing import Dict, List, Optional, Union

from diskcache import Cache

from lib.conversation_explorer import (
    ConversationTree,
    EnrichedTweet,
    build_conversation_trees,
    build_incomplete_conversation_trees,
)

SCRATCHPADS_DIR = Path(__file__).parent.parent

# Legacy joblib paths (for migration)
TWEET_DICT_CACHE = SCRATCHPADS_DIR / 'tweet_dict_cache.joblib'
REPLY_TREES_CACHE = SCRATCHPADS_DIR / 'complete_reply_trees_cache.joblib'
QUOTED_COUNTS_CACHE = SCRATCHPADS_DIR / 'quoted_counts_cache.parquet'
QUOTE_TWEETS_DICT_CACHE = SCRATCHPADS_DIR / 'quote_tweets_dict_cache.joblib'

# Diskcache paths
TWEET_DICT_DISKCACHE = SCRATCHPADS_DIR / 'tweet_dict.diskcache'
REPLY_TREES_DISKCACHE = SCRATCHPADS_DIR / 'reply_trees.diskcache'
QUOTE_TWEETS_DISKCACHE = SCRATCHPADS_DIR / 'quote_tweets.diskcache'

DEFAULT_PARQUET_PATH = os.environ.get(
    'ENRICHED_TWEETS_PATH',
    str(Path.home() / 'data' / 'enriched_tweets.parquet')
)

_tweet_dict: Optional[Cache] = None
_reply_trees: Optional[Cache] = None
_quote_tweets_dict: Optional[Cache] = None


def generate_caches(parquet_path: Optional[str] = None) -> None:
    """Generate tweet_dict and reply_trees caches from enriched_tweets parquet."""
    import pandas as pd
    from lib.count_quotes import count_quotes
    
    path = Path(parquet_path or DEFAULT_PARQUET_PATH).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    
    print(f"Loading tweets from {path}...")
    tweets = pd.read_parquet(path, dtype_backend='pyarrow')
    tweets = tweets.set_index('tweet_id', drop=False)
    
    # Quoted counts
    if QUOTED_COUNTS_CACHE.exists():
        print("Loading quoted counts from cache...")
        quoted_counts = pd.read_parquet(QUOTED_COUNTS_CACHE)
    else:
        print("Calculating quoted counts...")
        quoted_counts = count_quotes(tweets)
        quoted_counts = quoted_counts.groupby('quoted_tweet_id', as_index=False)['quoted_count'].sum()
        quoted_counts.to_parquet(QUOTED_COUNTS_CACHE)
    
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
    
    print("Building conversation trees...")
    conversation_tweets = [t for t in tweets_list if t['conversation_id'] is not None]
    trees = build_conversation_trees(conversation_tweets)
    
    non_conv_tweets = [t for t in tweets_list if t['conversation_id'] is None]
    incomplete_trees = build_incomplete_conversation_trees(non_conv_tweets, [])
    
    complete_reply_trees = {**trees, **incomplete_trees}
    tweet_dict = {t['tweet_id']: t for t in tweets_list}
    quote_tweets_dict: Dict[int, List[int]] = {}
    for tweet in tweet_dict.values():
        quoted_id = tweet.get('quoted_tweet_id')
        if quoted_id is not None:
            quote_tweets_dict.setdefault(quoted_id, []).append(tweet['tweet_id'])
    
    print("Saving caches...")
    joblib.dump(tweet_dict, TWEET_DICT_CACHE, compress=0)
    joblib.dump(complete_reply_trees, REPLY_TREES_CACHE, compress=0)
    joblib.dump(quote_tweets_dict, QUOTE_TWEETS_DICT_CACHE, compress=0)
    
    print(f"Caches saved to {SCRATCHPADS_DIR}")


def load_caches(auto_generate: bool = True) -> tuple[Cache, Cache]:
    """Load cached tweet_dict and complete_reply_trees as diskcache objects."""
    global _tweet_dict, _reply_trees
    if _tweet_dict is not None and _reply_trees is not None:
        return _tweet_dict, _reply_trees

    if not TWEET_DICT_DISKCACHE.exists() or not REPLY_TREES_DISKCACHE.exists():
        if auto_generate and (TWEET_DICT_CACHE.exists() and REPLY_TREES_CACHE.exists()):
            print("Diskcache not found but joblib exists. Run migrate_to_diskcache() first.")
            raise FileNotFoundError("Run migrate_to_diskcache() to convert joblib caches")
        elif auto_generate:
            print("Cache files not found. Generating from parquet...")
            generate_caches()
            migrate_to_diskcache()
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
        if QUOTE_TWEETS_DICT_CACHE.exists():
            print("Diskcache not found but joblib exists. Run migrate_to_diskcache() first.")
            raise FileNotFoundError("Run migrate_to_diskcache() to convert joblib caches")
        raise FileNotFoundError("Quote tweets cache not found. Run generate_caches() and migrate_to_diskcache().")
    
    print("Opening quote_tweets diskcache...")
    _quote_tweets_dict = Cache(str(QUOTE_TWEETS_DISKCACHE))
    print(f"Loaded quote index with {len(_quote_tweets_dict)} quoted tweets")
    return _quote_tweets_dict


def migrate_to_diskcache() -> None:
    """Migrate existing joblib caches to diskcache format."""
    import sys
    import time
    from tqdm import tqdm
    
    if not TWEET_DICT_CACHE.exists():
        raise FileNotFoundError(f"Joblib cache not found: {TWEET_DICT_CACHE}")
    
    migrations = [
        (QUOTE_TWEETS_DICT_CACHE, QUOTE_TWEETS_DISKCACHE, "quote_tweets", 800 * 1024**3),
        (REPLY_TREES_CACHE, REPLY_TREES_DISKCACHE, "reply_trees", 8 * 1024**3),
        (TWEET_DICT_CACHE, TWEET_DICT_DISKCACHE, "tweet_dict", 15 * 1024**3),
    ]
    
    for joblib_path, diskcache_path, name, size_limit in migrations:
        print(f"\n{'='*50}", flush=True)
        print(f"[{name}] Loading from joblib...", flush=True)
        t0 = time.time()
        data = joblib.load(joblib_path)
        print(f"[{name}] Loaded {len(data):,} items in {time.time()-t0:.1f}s", flush=True)
        
        print(f"[{name}] Writing to diskcache (size_limit={size_limit/1024**3:.1f}GB)...", flush=True)
        t0 = time.time()
        with Cache(str(diskcache_path), size_limit=size_limit) as cache:
            for k, v in tqdm(data.items(), desc=name, file=sys.stdout, mininterval=0.5):
                cache[k] = v
        print(f"[{name}] Done in {time.time()-t0:.1f}s", flush=True)
        del data
    
    print(f"\n{'='*50}", flush=True)
    print("Migration complete!", flush=True)


# %%