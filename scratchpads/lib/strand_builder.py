# %%
from dataclasses import dataclass
from typing import Dict, List, Literal

from .conversation_explorer import ConversationTree, EnrichedTweet, print_conversation_threads
from .semantic_search import search_embeddings

# %%
@dataclass
class StrandSeed:
    tweet_id: int
    source_type: Literal['root', 'semantic_search', 'quote_of_root', 'quote_of_semantic_search']
import time 
def _semantic_search_for_strands(
    tweet_id: int,
    tweet_dict: Dict[int, EnrichedTweet],
    exclude_keywords: List[str] = [],
    limit: int = 20,
    k: int = 100,
    threshold: float = 0.5,
    debug: bool = False
) -> List[EnrichedTweet]:
    """Search for semantically similar tweets, filter direct quotes and retweets, sort by quoted_count."""
    tweet = tweet_dict.get(tweet_id)
    if not tweet:
        return []
    
    filter_obj = {"must_not": [{"key": "text", "match": {"text": kw}} for kw in exclude_keywords]} if exclude_keywords else None
    
    start_time = time.time()
    results = search_embeddings(tweet['full_text'], k=k, threshold=threshold, exclude_tweet_id=str(tweet_id), filter=filter_obj)
    if debug:
        print(f"[DEBUG] Semantic search completed in {time.time() - start_time:.3f}s, found {len(results)} results")
    result_ids = [int(r['key']) for r in results]
    result_dicts = [tweet_dict[rid] for rid in result_ids if rid in tweet_dict]
    
    start_time = time.time()
    # Filter out direct quotes of the seed tweet and retweets
    filtered = [
        t for t in result_dicts
        if (t.get('quoted_tweet_id') is None or int(t['quoted_tweet_id']) != tweet_id)
        and not t.get('full_text', '').startswith('RT @')
    ]
    if debug:
        print(f"[DEBUG] Filtering completed in {time.time() - start_time:.3f}s, found {len(filtered)} results")
    return sorted(filtered, key=lambda x: x.get('quoted_count', 0) or 0, reverse=True)[:limit]

def get_strand_seeds(
    tweet_id: int,
    tweet_dict: Dict[int, EnrichedTweet],
    quote_tweets_dict: Dict[int, List[int]],
    exclude_keywords: List[str] = [],
    semantic_limit: int = 20,
    debug: bool = False
) -> List[StrandSeed]:
    """
    Get all seed tweet IDs belonging to a strand.
    
    Combines: root tweet, quotes of root, semantic search results, quotes of semantic results.
    """
    import time
    
    if debug:
        start_time = time.time()
        print(f"[DEBUG] Starting get_strand_seeds for tweet_id={tweet_id}")
    
    # Phase 1: Semantic search
    if debug:
        phase_start = time.time()
    semantic_results = _semantic_search_for_strands(tweet_id=tweet_id, tweet_dict=tweet_dict, exclude_keywords=exclude_keywords, debug=debug)
    if debug:
        print(f"[DEBUG] Semantic search completed in {time.time() - phase_start:.3f}s, found {len(semantic_results)} results")
    
    # Phase 2: Build seeds list
    if debug:
        phase_start = time.time()
    seeds = [StrandSeed(tweet_id=tweet_id, source_type='root')]
    
    # Quotes of root
    root_quotes = quote_tweets_dict.get(tweet_id, [])
    seeds.extend(
        StrandSeed(tweet_id=qid, source_type='quote_of_root')
        for qid in root_quotes
    )
    if debug:
        print(f"[DEBUG] Added root and {len(root_quotes)} quotes of root in {time.time() - phase_start:.3f}s")
    
    # Phase 3: Semantic search results and their quotes
    if debug:
        phase_start = time.time()
    for t in semantic_results:
        seeds.append(StrandSeed(tweet_id=t['tweet_id'], source_type='semantic_search'))
        seeds.extend(
            StrandSeed(tweet_id=qid, source_type='quote_of_semantic_search')
            for qid in quote_tweets_dict.get(t['tweet_id'], [])
        )
    if debug:
        print(f"[DEBUG] Added semantic results and their quotes in {time.time() - phase_start:.3f}s")

    # Phase 4: Dedupe while preserving order
    if debug:
        phase_start = time.time()
        pre_dedupe_count = len(seeds)
    seen = set()
    deduped_seeds = []
    for seed in seeds:
        if seed.tweet_id not in seen:
            seen.add(seed.tweet_id)
            deduped_seeds.append(seed)
    if debug:
        print(f"[DEBUG] Deduplication completed in {time.time() - phase_start:.3f}s, removed {pre_dedupe_count - len(deduped_seeds)} duplicates")
        print(f"[DEBUG] Total time: {time.time() - start_time:.3f}s, final seed count: {len(deduped_seeds)}")
    
    return deduped_seeds

def get_strand_conversation_string(
    tweet_id: int,
    tweet_dict: Dict[int, EnrichedTweet],
    quote_tweets_dict: Dict[int, List[int]],
    conversation_trees: Dict[int, ConversationTree],
    depth: int = 10,
    **kwargs
) -> str:
    """
    Get conversation threads for all tweets in a strand as a formatted string.
    
    kwargs passed to get_strand_tweet_ids (exclude_keywords, semantic_limit).
    """
    seeds = get_strand_seeds(tweet_id, tweet_dict, quote_tweets_dict, **kwargs)
    tweet_ids = [s.tweet_id for s in seeds]
    return print_conversation_threads(tweet_ids, conversation_trees, tweet_dict, depth)


# %%
