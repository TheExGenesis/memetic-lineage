# %%
import os
import pickle
from pathlib import Path
from typing import Dict, List, Optional

from lib.conversation_explorer import (
    ConversationTree,
    EnrichedTweet,
    build_conversation_trees,
    build_incomplete_conversation_trees,
)

SCRATCHPADS_DIR = Path(__file__).parent.parent
TWEET_DICT_CACHE = SCRATCHPADS_DIR / 'tweet_dict_cache.pkl'
REPLY_TREES_CACHE = SCRATCHPADS_DIR / 'complete_reply_trees_cache.pkl'
QUOTED_COUNTS_CACHE = SCRATCHPADS_DIR / 'quoted_counts_cache.parquet'
QUOTE_TWEETS_DICT_CACHE = SCRATCHPADS_DIR / 'quote_tweets_dict_cache.pkl'

DEFAULT_PARQUET_PATH = os.environ.get(
    'ENRICHED_TWEETS_PATH',
    str(Path.home() / 'data' / 'enriched_tweets.parquet')
)

_tweet_dict: Optional[Dict[int, EnrichedTweet]] = None
_reply_trees: Optional[Dict[int, ConversationTree]] = None
_quote_tweets_dict: Optional[Dict[int, List[int]]] = None


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
    with open(TWEET_DICT_CACHE, 'wb') as f:
        pickle.dump(tweet_dict, f)
    with open(REPLY_TREES_CACHE, 'wb') as f:
        pickle.dump(complete_reply_trees, f)
    with open(QUOTE_TWEETS_DICT_CACHE, 'wb') as f:
        pickle.dump(quote_tweets_dict, f)
    
    print(f"Caches saved to {SCRATCHPADS_DIR}")


def load_caches(auto_generate: bool = True) -> tuple[Dict[int, EnrichedTweet], Dict[int, ConversationTree]]:
    """Load cached tweet_dict and complete_reply_trees. Caches in module globals."""
    global _tweet_dict, _reply_trees
    if _tweet_dict is not None and _reply_trees is not None:
        return _tweet_dict, _reply_trees

    if not TWEET_DICT_CACHE.exists() or not REPLY_TREES_CACHE.exists():
        if auto_generate:
            print("Cache files not found. Generating from parquet...")
            generate_caches()
        else:
            raise FileNotFoundError(
                f"Cache files not found. Set ENRICHED_TWEETS_PATH env var and call generate_caches(), or run:\n"
                f"  from lib.strand_tools import generate_caches; generate_caches('/path/to/enriched_tweets.parquet')"
            )
    
    print("Loading cached tweet_dict and complete_reply_trees...")
    with open(TWEET_DICT_CACHE, 'rb') as f:
        _tweet_dict = pickle.load(f)
    with open(REPLY_TREES_CACHE, 'rb') as f:
        _reply_trees = pickle.load(f)
    assert _tweet_dict is not None and _reply_trees is not None
    print(f"Loaded {len(_tweet_dict)} tweets and {len(_reply_trees)} reply trees")
    return _tweet_dict, _reply_trees


def get_quote_tweets_dict() -> Dict[int, List[int]]:
    """Build and cache index: quoted_tweet_id -> list of quoting tweet_ids."""
    global _quote_tweets_dict
    if _quote_tweets_dict is not None:
        return _quote_tweets_dict
    
    if QUOTE_TWEETS_DICT_CACHE.exists():
        print("Loading quote_tweets_dict from cache...")
        with open(QUOTE_TWEETS_DICT_CACHE, 'rb') as f:
            _quote_tweets_dict = pickle.load(f)
        print(f"Loaded quote index with {len(_quote_tweets_dict)} quoted tweets")
        return _quote_tweets_dict
    
    tweet_dict, _ = load_caches()
    print("Building quote_tweets_dict index...")
    _quote_tweets_dict = {}
    for tweet in tweet_dict.values():
        quoted_id = tweet.get('quoted_tweet_id')
        if quoted_id is not None:
            _quote_tweets_dict.setdefault(quoted_id, []).append(tweet['tweet_id'])
    with open(QUOTE_TWEETS_DICT_CACHE, 'wb') as f:
        pickle.dump(_quote_tweets_dict, f)
    print(f"Built quote index with {len(_quote_tweets_dict)} quoted tweets")
    return _quote_tweets_dict


# %%