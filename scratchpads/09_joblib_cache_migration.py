# %%
"""Migrate joblib caches to diskcache for fast per-key KV access."""
import time
from pathlib import Path

SCRATCHPADS_DIR = Path(__file__).parent

# %%
# Run migration from joblib -> diskcache
from lib.strand_caches import migrate_to_diskcache

migrate_to_diskcache()

# %%
# Benchmark: diskcache vs joblib loading
def benchmark_diskcache():
    import joblib
    from diskcache import Cache
    from lib.strand_caches import (
        TWEET_DICT_CACHE, REPLY_TREES_CACHE, QUOTE_TWEETS_DICT_CACHE,
        TWEET_DICT_DISKCACHE, REPLY_TREES_DISKCACHE, QUOTE_TWEETS_DISKCACHE,
    )
    
    print("=== Joblib full load times ===")
    for path, name in [
        (TWEET_DICT_CACHE, "tweet_dict"),
        (REPLY_TREES_CACHE, "reply_trees"),
        (QUOTE_TWEETS_DICT_CACHE, "quote_dict"),
    ]:
        if not path.exists():
            print(f"  {name}: not found")
            continue
        t0 = time.time()
        data = joblib.load(path, mmap_mode='r')
        print(f"  {name}: {time.time() - t0:.3f}s ({len(data)} items)")
    
    print("\n=== Diskcache open times ===")
    for path, name in [
        (TWEET_DICT_DISKCACHE, "tweet_dict"),
        (REPLY_TREES_DISKCACHE, "reply_trees"),
        (QUOTE_TWEETS_DISKCACHE, "quote_dict"),
    ]:
        if not path.exists():
            print(f"  {name}: not found")
            continue
        t0 = time.time()
        cache = Cache(str(path))
        open_time = time.time() - t0
        print(f"  {name}: {open_time:.3f}s to open ({len(cache)} items)")
        cache.close()
    
    print("\n=== Single key access comparison ===")
    # Get a sample key from each
    tweet_cache = Cache(str(TWEET_DICT_DISKCACHE))
    sample_key = next(iter(tweet_cache))
    tweet_cache.close()
    
    # Joblib: must load entire dict
    t0 = time.time()
    tweet_dict = joblib.load(TWEET_DICT_CACHE, mmap_mode='r')
    _ = tweet_dict[sample_key]
    print(f"  Joblib (load all + access): {time.time() - t0:.3f}s")
    
    # Diskcache: direct key access
    t0 = time.time()
    tweet_cache = Cache(str(TWEET_DICT_DISKCACHE))
    _ = tweet_cache[sample_key]
    tweet_cache.close()
    print(f"  Diskcache (open + access): {time.time() - t0:.3f}s")

# %%
benchmark_diskcache()

# %%
# Test the new load functions
from lib.strand_caches import load_caches, get_quote_tweets_dict

t0 = time.time()
tweet_dict, conversation_trees = load_caches()
quote_dict = get_quote_tweets_dict()
print(f"\nLoaded all caches in {time.time() - t0:.3f}s")
print(f"  {len(tweet_dict)} tweets, {len(conversation_trees)} trees, {len(quote_dict)} quote mappings")

# %%
# Test single key access
sample_tid = next(iter(tweet_dict))
t0 = time.time()
tweet = tweet_dict[sample_tid]
print(f"\nSingle tweet lookup: {time.time() - t0:.6f}s")
print(f"  Tweet {sample_tid}: {tweet['full_text'][:80]}...")
# %%
