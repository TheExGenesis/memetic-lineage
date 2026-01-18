# %%
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set, Tuple

from .conversation_explorer import (
    ConversationTree, EnrichedTweet,
    filter_conversation_trees, render_conversation_trees,
    strand_header_print_factory, print_conversation_threads
)
from diskcache import Cache

from .semantic_search import search_embeddings


def _clean_search_query(text: str) -> str:
    """Remove t.co, twitter.com, and x.com URLs from text for cleaner semantic search.

    These shortened/social URLs don't carry semantic meaning and can pollute search results.
    """
    # Pattern matches URLs starting with http(s):// followed by t.co, twitter.com, or x.com
    url_pattern = r'https?://(?:t\.co|twitter\.com|x\.com)[^\s]*'
    cleaned = re.sub(url_pattern, '', text)
    # Clean up extra whitespace that may result from URL removal
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


from .image_describer import get_image_cache, get_image_descriptions_batch
from .parallel import parallel_map_to_dict


class SemanticSearchFailedError(Exception):
    """Raised when semantic search returns no results for strands."""
    def __init__(self, failed_ids: List[int], total_ids: int):
        self.failed_ids = failed_ids
        self.total_ids = total_ids
        super().__init__(
            f"Semantic search returned no results for {len(failed_ids)}/{total_ids} strands. "
            f"First 5 failed IDs: {failed_ids[:5]}. "
            f"This usually means the Qdrant server is down or embeddings are missing."
        )


def _has_semantic_seeds(seeds: List['StrandSeed']) -> bool:
    """Check if a strand has any semantic search seeds."""
    return any(s.source_type in ('semantic_search', 'quote_of_semantic_search') for s in seeds)


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
    max_k: int = 400,
    threshold: float = 0.5,
    debug: bool = False
) -> List[EnrichedTweet]:
    """Search for semantically similar tweets, filter direct quotes and retweets, sort by quoted_count.

    If filtered results are below limit, retries with doubled k (up to max_k).
    """
    tweet = tweet_dict.get(tweet_id)
    if not tweet:
        return []

    search_params = {
        'k': k,
        'max_k': max_k,
        'threshold': threshold,
        'exclude_keywords': exclude_keywords
    }

    # Try loading from backup first
    backup_tweet_ids = load_semantic_backup(tweet_id, search_params)
    if backup_tweet_ids is not None:
        if debug:
            print(f"[DEBUG] Loaded {len(backup_tweet_ids)} results from backup for tweet {tweet_id}")
        # Reconstruct EnrichedTweet objects from IDs
        backup_tweets = [tweet_dict.get(tid) for tid in backup_tweet_ids if tweet_dict.get(tid)]
        backup_tweets = [t for t in backup_tweets if t is not None]
        if len(backup_tweets) > 0:
            print(f"[DEBUG] Returning {len(backup_tweets)} results from backup for tweet {tweet_id}")
            return sorted(backup_tweets, key=lambda x: x.get('quoted_count', 0) or 0, reverse=True)[:limit]

    # No valid backup - perform search
    filter_obj = {"must_not": [{"key": "text", "match": {"text": kw}} for kw in exclude_keywords]} if exclude_keywords else None

    # Clean search query by removing t.co/twitter.com/x.com URLs
    search_query = _clean_search_query(tweet['full_text'])
    if debug:
        print(f"[DEBUG] Cleaned search query: '{search_query[:100]}...' (original had {len(tweet['full_text'])} chars)")

    current_k = k
    filtered = []

    while current_k <= max_k:
        start_time = time.time()
        results = search_embeddings(search_query, k=current_k, threshold=threshold, exclude_tweet_id=str(tweet_id), filter=filter_obj)
        if debug:
            print(f"[DEBUG] Semantic search (k={current_k}) completed in {time.time() - start_time:.3f}s, found {len(results)} results")

        start_time = time.time()
        result_ids = [int(r['key']) for r in results]
        result_dicts = [tweet_dict.get(rid, None) for rid in result_ids]
        result_dicts = [t for t in result_dicts if t is not None]

        # Filter out direct quotes of the seed tweet and retweets
        filtered = [
            t for t in result_dicts
            if (t.get('quoted_tweet_id') is None or int(t['quoted_tweet_id']) != tweet_id)
            and not t.get('full_text', '').startswith('RT @')
        ]
        if debug:
            print(f"[DEBUG] Filtering completed in {time.time() - start_time:.3f}s, found {len(filtered)} results")

        # If we have enough results or we've hit max_k, stop retrying
        if len(filtered) >= limit or current_k >= max_k:
            break

        # Retry with doubled k
        old_k = current_k
        current_k = min(current_k * 2, max_k)
        if debug:
            print(f"[DEBUG] Only {len(filtered)} results after filtering (need {limit}), retrying with k={current_k} (was {old_k})")

    # Save backup of filtered tweet IDs
    filtered_tweet_ids = [t['tweet_id'] for t in filtered]
    save_semantic_backup(tweet_id, search_params, filtered_tweet_ids)

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
    semantic_results = _semantic_search_for_strands(tweet_id=tweet_id, tweet_dict=tweet_dict, exclude_keywords=exclude_keywords, limit=semantic_limit, debug=debug)
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
    seeds: List[StrandSeed]


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
    image_cache: Optional[Cache] = None,
    depth: int = 10
) -> StrandBuildResult:
    """Build a single strand. For batch processing, use build_strands_phased instead."""
    if image_cache is None:
        image_cache = get_image_cache()
    
    # Phase 1: Seeds
    seeds = get_strand_seeds(tid, tweet_dict, quote_dict, debug=False)
    seed_ids = [s.tweet_id for s in seeds]
    seed_info = {s.tweet_id: s.source_type for s in seeds}
    
    # Phase 2: Filter trees
    filtered_trees = filter_conversation_trees(
        seed_ids, conversation_trees, tweet_dict,
        depth=depth, depth_up=depth, depth_from_root=depth
    )
    
    # Phase 3: Image descriptions (stored directly in cache)
    tree_tids = list(extract_tree_tweet_ids(filtered_trees))
    get_image_descriptions_batch(tree_tids, image_cache, max_workers=2)
    
    # Phase 4: Render
    render_header = strand_header_print_factory(seed_info)
    text = render_conversation_trees(filtered_trees, tweet_dict, render_header, image_cache)
    
    return StrandBuildResult(tid, text, seeds)

def build_strands_phased(
    tweet_ids: List[int],
    tweet_dict: Dict[int, EnrichedTweet],
    quote_dict: Dict[int, List[int]],
    conversation_trees: Dict[int, ConversationTree],
    image_cache: Optional[Cache] = None,
    depth: int = 10,
    seeds_workers: int = 4,
    trees_workers: int = 8,
    images_workers: int = 2,
    debug: bool = False
) -> Dict[int, StrandBuildResult]:
    """
    Build multiple strands using phase-level parallelism.
    
    Each phase completes before the next starts:
    1. Seeds (IO-bound, moderate concurrency)
    2. Filter trees (CPU-bound, high concurrency)
    3. Image descriptions (IO-bound, low concurrency for rate limits)
    4. Render (CPU-bound, sequential)
    
    Returns:
        Dict of results keyed by tweet_id
    """
    if image_cache is None:
        image_cache = get_image_cache()
    
    print(f"[build_strands_phased] Starting with {len(tweet_ids)} tweet IDs")
    print(f"[build_strands_phased] Workers: seeds={seeds_workers}, trees={trees_workers}, images={images_workers}")

    # Cleanup old semantic search backups (older than 7 days)
    removed_backups = cleanup_old_backups(max_age_hours=24 * 7)
    if removed_backups > 0:
        print(f"[build_strands_phased] Cleaned up {removed_backups} old semantic search backups")

    # Phase 1: Get seeds for all tweet_ids
    print("[Phase 1] Getting seeds...")
    def get_seeds_for_tid(tid: int) -> List[StrandSeed]:
        return get_strand_seeds(tid, tweet_dict, quote_dict, debug=debug)
    
    seeds_by_tid, seeds_failed = parallel_map_to_dict(
        tweet_ids, get_seeds_for_tid,
        max_workers=seeds_workers, desc="Phase 1: Seeds"
    )
    print(f"[Phase 1] Got seeds for {len(seeds_by_tid)} strands, {len(seeds_failed)} failed")

    # Validate semantic search worked - fail fast if no semantic matches found
    no_semantic_ids = [
        tid for tid, seeds in seeds_by_tid.items()
        if not _has_semantic_seeds(seeds)
    ]
    if no_semantic_ids:
        # If ALL strands have no semantic matches, this is a system failure
        if len(no_semantic_ids) == len(seeds_by_tid):
            raise SemanticSearchFailedError(no_semantic_ids, len(tweet_ids))
        # If only some failed, warn but continue (some tweets may legitimately have no matches)
        print(f"[WARN] {len(no_semantic_ids)} strands have no semantic matches (may be expected for some)")

    # Phase 2: Filter trees for all
    print("[Phase 2] Filtering conversation trees...")
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
    print(f"[Phase 2] Filtered trees for {len(trees_by_tid)} strands, {len(trees_failed)} failed")
    
    # Phase 3: Batch collect + dedupe + fetch images
    print("[Phase 3] Collecting tweet IDs from trees...")
    all_tree_tids: Set[int] = set()
    for trees in trees_by_tid.values():
        all_tree_tids.update(extract_tree_tweet_ids(trees))
    
    print(f"[Phase 3] Found {len(all_tree_tids)} unique tweet IDs across all trees")
    print(f"[Phase 3] Fetching image descriptions (cache has {len(image_cache)} entries)...")
    get_image_descriptions_batch(list(all_tree_tids), image_cache, max_workers=images_workers)
    print(f"[Phase 3] Image cache now has {len(image_cache)} entries")
    
    # Phase 4: Render all (sequential, fast)
    print("[Phase 4] Rendering strands...")
    results: Dict[int, StrandBuildResult] = {}
    for tid in tweet_ids:
        if tid in seeds_failed or tid in trees_failed:
            continue
        
        seeds = seeds_by_tid.get(tid, [])
        trees = trees_by_tid.get(tid, {})
        seed_info = {s.tweet_id: s.source_type for s in seeds}
        
        render_header = strand_header_print_factory(seed_info)
        text = render_conversation_trees(trees, tweet_dict, render_header, image_cache)
        
        results[tid] = StrandBuildResult(tid, text, seeds)
    
    print(f"[Phase 4] Rendered {len(results)} strands")
    
    failed_count = len(seeds_failed) + len(trees_failed)
    if failed_count:
        print(f"[WARN] {failed_count} strands failed (seeds: {len(seeds_failed)}, trees: {len(trees_failed)})")
    
    print(f"[build_strands_phased] Complete: {len(results)} successful, {failed_count} failed")
    return results


# %%
