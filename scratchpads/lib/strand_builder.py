from dataclasses import dataclass
from typing import Dict, List, Literal

from .conversation_explorer import ConversationTree, EnrichedTweet, print_conversation_threads
from .semantic_search import search_embeddings


@dataclass
class StrandSeed:
    tweet_id: int
    source_type: Literal['root', 'semantic_search', 'quote_of_root', 'quote_of_semantic_search']


def _semantic_search_for_strands(
    tweet_id: int,
    tweet_dict: Dict[int, EnrichedTweet],
    exclude_keywords: List[str] = [],
    limit: int = 20
) -> List[EnrichedTweet]:
    """Search for semantically similar tweets, filter direct quotes, sort by quoted_count."""
    tweet = tweet_dict.get(tweet_id)
    if not tweet:
        return []
    
    filter_obj = {"must_not": [{"key": "text", "match": {"text": kw}} for kw in exclude_keywords]} if exclude_keywords else None
    results = search_embeddings(tweet['full_text'], k=1000, threshold=0.5, exclude_tweet_id=str(tweet_id), filter=filter_obj)
    
    result_ids = [int(r['key']) for r in results]
    result_dicts = [tweet_dict[rid] for rid in result_ids if rid in tweet_dict]
    
    # Filter out direct quotes of the seed tweet
    filtered = [
        t for t in result_dicts
        if t.get('quoted_tweet_id') is None or int(t['quoted_tweet_id']) != tweet_id
    ]
    
    return sorted(filtered, key=lambda x: x.get('quoted_count', 0) or 0, reverse=True)[:limit]


def get_strand_tweet_ids(
    tweet_id: int,
    tweet_dict: Dict[int, EnrichedTweet],
    quote_tweets_dict: Dict[int, List[int]],
    exclude_keywords: List[str] = [],
    semantic_limit: int = 20
) -> List[StrandSeed]:
    """
    Get all tweet IDs belonging to a strand.
    
    Combines: root tweet, quotes of root, semantic search results, quotes of semantic results.
    """
    semantic_results = _semantic_search_for_strands(tweet_id, tweet_dict, exclude_keywords, semantic_limit)
    
    seeds = [StrandSeed(tweet_id=tweet_id, source_type='root')]
    
    # Quotes of root
    seeds.extend(
        StrandSeed(tweet_id=qid, source_type='quote_of_root')
        for qid in quote_tweets_dict.get(tweet_id, [])
    )
    
    # Semantic search results and their quotes
    for t in semantic_results:
        seeds.append(StrandSeed(tweet_id=t['tweet_id'], source_type='semantic_search'))
        seeds.extend(
            StrandSeed(tweet_id=qid, source_type='quote_of_semantic_search')
            for qid in quote_tweets_dict.get(t['tweet_id'], [])
        )
    
    return seeds


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
    seeds = get_strand_tweet_ids(tweet_id, tweet_dict, quote_tweets_dict, **kwargs)
    tweet_ids = [s.tweet_id for s in seeds]
    return print_conversation_threads(tweet_ids, conversation_trees, tweet_dict, depth)

