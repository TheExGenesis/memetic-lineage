# %%
import time
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set, Tuple

from .conversation_explorer import (
    ConversationTree, EnrichedTweet, 
    filter_conversation_trees, render_conversation_trees,
    strand_header_print_factory, print_conversation_threads
)
from .semantic_search import search_embeddings
from .image_describer import MediaDescription, get_image_descriptions_batch
from .parallel import parallel_map_to_dict

# %%
@dataclass
class StrandSeed:
    tweet_id: int
    source_type: Literal['root', 'semantic_search', 'quote_of_root', 'quote_of_semantic_search']


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
    start_time = time.time()
    result_ids = [int(r['key']) for r in results]
    result_dicts = [tweet_dict.get(rid,None) for rid in result_ids]
    result_dicts = [t for t in result_dicts if t is not None]
    
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


# --- Phase-Level Pipeline ---

@dataclass
class StrandBuildResult:
    tweet_id: int
    thread_text: str
    seed_ids: List[int]


def extract_tree_tweet_ids(filtered_trees: Dict[int, ConversationTree]) -> Set[int]:
    """Extract all tweet IDs from filtered conversation trees."""
    all_ids: Set[int] = set()
    for tree in filtered_trees.values():
        all_ids.update(tree["parents"].keys())
        all_ids.update(tree["parents"].values())
        all_ids.update(tree["children"].keys())
        for children in tree["children"].values():
            all_ids.update(children)
        if tree.get("root"):
            all_ids.add(tree["root"])
    return all_ids


def build_strand_single(
    tid: int,
    tweet_dict: Dict[int, EnrichedTweet],
    quote_dict: Dict[int, List[int]],
    conversation_trees: Dict[int, ConversationTree],
    image_cache: Dict[int, List[MediaDescription]],
    depth: int = 10
) -> Tuple[StrandBuildResult, Dict[int, List[MediaDescription]]]:
    """
    Build a single strand. Returns (result, new_image_cache_entries).
    
    For batch processing, use build_strands_phased instead.
    """
    # Phase 1: Seeds
    seeds = get_strand_seeds(tid, tweet_dict, quote_dict, debug=False)
    seed_ids = [s.tweet_id for s in seeds]
    seed_info = {s.tweet_id: s.source_type for s in seeds}
    
    # Phase 2: Filter trees
    filtered_trees = filter_conversation_trees(
        seed_ids, conversation_trees, tweet_dict,
        depth=depth, depth_up=depth, depth_from_root=depth
    )
    
    # Phase 3: Image descriptions
    tree_tids = list(extract_tree_tweet_ids(filtered_trees))
    new_images = get_image_descriptions_batch(tree_tids, image_cache, max_workers=2)
    merged_cache = {**image_cache, **new_images}
    
    # Phase 4: Render
    render_header = strand_header_print_factory(seed_info)
    text = render_conversation_trees(filtered_trees, tweet_dict, render_header, merged_cache)
    
    return StrandBuildResult(tid, text, seed_ids), new_images


def build_strands_phased(
    tweet_ids: List[int],
    tweet_dict: Dict[int, EnrichedTweet],
    quote_dict: Dict[int, List[int]],
    conversation_trees: Dict[int, ConversationTree],
    image_cache: Dict[int, List[MediaDescription]],
    depth: int = 10,
    seeds_workers: int = 4,
    trees_workers: int = 8,
    images_workers: int = 2
) -> Tuple[Dict[int, StrandBuildResult], Dict[int, List[MediaDescription]]]:
    """
    Build multiple strands using phase-level parallelism.
    
    Each phase completes before the next starts:
    1. Seeds (IO-bound, moderate concurrency)
    2. Filter trees (CPU-bound, high concurrency)
    3. Image descriptions (IO-bound, low concurrency for rate limits)
    4. Render (CPU-bound, sequential)
    
    Returns:
        Tuple of (results_dict keyed by tweet_id, updated_image_cache)
    """
    # Phase 1: Get seeds for all tweet_ids
    def get_seeds_for_tid(tid: int) -> List[StrandSeed]:
        return get_strand_seeds(tid, tweet_dict, quote_dict, debug=False)
    
    seeds_by_tid, seeds_failed = parallel_map_to_dict(
        tweet_ids, get_seeds_for_tid,
        max_workers=seeds_workers, desc="Phase 1: Seeds"
    )
    
    # Phase 2: Filter trees for all
    def filter_trees_for_tid(tid: int) -> Dict[int, ConversationTree]:
        seeds = seeds_by_tid.get(tid, [])
        seed_ids = [s.tweet_id for s in seeds]
        return filter_conversation_trees(
            seed_ids, conversation_trees, tweet_dict,
            depth=depth, depth_up=depth, depth_from_root=depth
        )
    
    trees_by_tid, trees_failed = parallel_map_to_dict(
        [t for t in tweet_ids if t not in seeds_failed],
        filter_trees_for_tid,
        max_workers=trees_workers, desc="Phase 2: Filter trees"
    )
    
    # Phase 3: Batch collect + dedupe + fetch images
    all_tree_tids: Set[int] = set()
    for trees in trees_by_tid.values():
        all_tree_tids.update(extract_tree_tweet_ids(trees))
    
    new_images = get_image_descriptions_batch(
        list(all_tree_tids), image_cache,
        max_workers=images_workers
    )
    merged_cache = {**image_cache, **new_images}
    
    # Phase 4: Render all (sequential, fast)
    results: Dict[int, StrandBuildResult] = {}
    for tid in tweet_ids:
        if tid in seeds_failed or tid in trees_failed:
            continue
        
        seeds = seeds_by_tid.get(tid, [])
        trees = trees_by_tid.get(tid, {})
        seed_info = {s.tweet_id: s.source_type for s in seeds}
        seed_ids = [s.tweet_id for s in seeds]
        
        render_header = strand_header_print_factory(seed_info)
        text = render_conversation_trees(trees, tweet_dict, render_header, merged_cache)
        
        results[tid] = StrandBuildResult(tid, text, seed_ids)
    
    failed_count = len(seeds_failed) + len(trees_failed)
    if failed_count:
        print(f"[WARN] {failed_count} strands failed (seeds: {len(seeds_failed)}, trees: {len(trees_failed)})")
    
    return results, merged_cache


# %%
