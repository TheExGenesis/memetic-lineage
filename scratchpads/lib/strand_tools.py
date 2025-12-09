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
    print_conversation_threads,
)
from lib.semantic_search import search_embeddings

SCRATCHPADS_DIR = Path(__file__).parent.parent
TWEET_DICT_CACHE = SCRATCHPADS_DIR / 'tweet_dict_cache.pkl'
REPLY_TREES_CACHE = SCRATCHPADS_DIR / 'complete_reply_trees_cache.pkl'
QUOTED_COUNTS_CACHE = SCRATCHPADS_DIR / 'quoted_counts_cache.parquet'

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
    
    print("Saving caches...")
    with open(TWEET_DICT_CACHE, 'wb') as f:
        pickle.dump(tweet_dict, f)
    with open(REPLY_TREES_CACHE, 'wb') as f:
        pickle.dump(complete_reply_trees, f)
    
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
    print(f"Loaded {len(_tweet_dict)} tweets and {len(_reply_trees)} reply trees")
    return _tweet_dict, _reply_trees


def get_quote_tweets_dict() -> Dict[int, List[int]]:
    """Build and cache index: quoted_tweet_id -> list of quoting tweet_ids."""
    global _quote_tweets_dict
    if _quote_tweets_dict is not None:
        return _quote_tweets_dict
    
    tweet_dict, _ = load_caches()
    print("Building quote_tweets_dict index...")
    _quote_tweets_dict = {}
    for tweet in tweet_dict.values():
        quoted_id = tweet.get('quoted_tweet_id')
        if quoted_id is not None:
            _quote_tweets_dict.setdefault(quoted_id, []).append(tweet['tweet_id'])
    print(f"Built quote index with {len(_quote_tweets_dict)} quoted tweets")
    return _quote_tweets_dict


def semantic_search_for_strands(
    tweet_id: int,
    k: int = 1000,
    threshold: float = 0.5,
    top_n: int = 20,
    exclude_keywords: List[str] = []
) -> List[EnrichedTweet]:
    """Find semantically similar tweets, filtered and ranked by quoted_count."""
    tweet_dict, _ = load_caches()
    
    if tweet_id not in tweet_dict:
        return []
    
    seed_text = tweet_dict[tweet_id]['full_text']
    filter_clause = {"must_not": [{"key": "text", "match": {"text": kw}} for kw in exclude_keywords]} if exclude_keywords else None
    
    results = search_embeddings(
        seed_text,
        k=k,
        threshold=threshold,
        exclude_tweet_id=str(tweet_id),
        filter=filter_clause
    )
    
    result_ids = [int(r['key']) for r in results]
    result_dicts = [tweet_dict[rid] for rid in result_ids if rid in tweet_dict]
    
    # Filter out direct quotes of the seed
    filtered = [
        r for r in result_dicts
        if r.get('quoted_tweet_id') is None or int(r['quoted_tweet_id']) != tweet_id
    ]
    
    # Sort by quoted_count descending, take top_n
    return sorted(filtered, key=lambda x: x.get('quoted_count', 0), reverse=True)[:top_n]


def build_strand_seeds(
    tweet_id: int,
    include_semantic: bool = True,
    include_quotes: bool = True,
    semantic_top_n: int = 20
) -> List[int]:
    """
    Build enriched list of seed tweet IDs for a strand:
    - Root tweet
    - Quotes of root
    - Semantic neighbors
    - Quotes of semantic neighbors
    """
    tweet_dict, _ = load_caches()
    quote_dict = get_quote_tweets_dict()
    
    seeds: List[int] = []
    
    # 1. Root tweet
    if tweet_id in tweet_dict:
        seeds.append(tweet_id)
    
    # 2. Quotes of root
    if include_quotes:
        seeds.extend(quote_dict.get(tweet_id, []))
    
    # 3. Semantic neighbors
    if include_semantic:
        neighbors = semantic_search_for_strands(tweet_id, top_n=semantic_top_n)
        neighbor_ids = [n['tweet_id'] for n in neighbors]
        seeds.extend(neighbor_ids)
        
        # 4. Quotes of semantic neighbors
        if include_quotes:
            for nid in neighbor_ids:
                seeds.extend(quote_dict.get(nid, []))
    
    # Dedupe while preserving order
    seen = set()
    unique_seeds = []
    for s in seeds:
        if s not in seen:
            seen.add(s)
            unique_seeds.append(s)
    
    return unique_seeds


def get_thread_texts(
    tweet_ids: List[int],
    depth: int = 10,
    enrich: bool = True,
    semantic_top_n: int = 20
) -> List[str]:
    """
    Generate conversation thread text for each tweet_id.
    
    Args:
        tweet_ids: List of seed tweet IDs
        depth: Depth limit for thread traversal
        enrich: If True, expand each seed with semantic neighbors and quotes
        semantic_top_n: Number of semantic neighbors to include per seed
    
    Returns:
        List of thread text strings, one per input tweet_id
    """
    tweet_dict, reply_trees = load_caches()
    
    results: List[str] = []
    for tid in tweet_ids:
        if enrich:
            expanded_seeds = build_strand_seeds(tid, semantic_top_n=semantic_top_n)
        else:
            expanded_seeds = [tid]
        
        thread_text = print_conversation_threads(
            tweet_ids=expanded_seeds,
            conversation_trees=reply_trees,
            tweets=tweet_dict,
            depth=depth
        )
        results.append(thread_text)
    return results


def get_thread_text(tweet_id: int, depth: int = 10, enrich: bool = True) -> str:
    """Single tweet convenience wrapper."""
    return get_thread_texts([tweet_id], depth=depth, enrich=enrich)[0]
