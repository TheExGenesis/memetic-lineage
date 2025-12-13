# %%
"""
Top Quoted Strands Pipeline

Uses phase-level parallelism to build and rate strands from top quoted tweets.
Functions moved to lib/: strand_builder.py, strand_rater.py, image_describer.py
"""
import json
from pathlib import Path
from typing import Set, TypedDict

from dotenv import load_dotenv

from lib.strand_caches import get_quote_tweets_dict, load_caches
from lib.strand_builder import build_strands_phased, StrandBuildResult
from lib.strand_rater import rate_strands_batch
from lib.image_describer import load_img_cache, save_img_cache, DEFAULT_CACHE_PATH

# %%
load_dotenv(Path(__file__).parent.parent / ".env")

DATA_DIR = Path(__file__).parent / "data"
TOP_IDS_PATH = DATA_DIR / "top_quoted_tweet_ids.json"
STRANDS_DIR = DATA_DIR / "strands"
RATED_DIR = DATA_DIR / "rated_strands"
DEBUG_DIR = DATA_DIR / "debug_responses"


def load_top_tweet_ids() -> list[int]:
    with open(TOP_IDS_PATH) as f:
        return json.load(f)


def get_built_strand_ids(strands_dir: Path) -> Set[int]:
    """Get IDs of strands that have been built (file exists)."""
    if not strands_dir.exists():
        return set()
    return {int(f.stem) for f in strands_dir.glob("*.json") if f.stem.isdigit()}


def get_rated_strand_ids(rated_dir: Path) -> Set[int]:
    """Get IDs of strands that have been rated."""
    if not rated_dir.exists():
        return set()
    return {int(f.stem) for f in rated_dir.glob("*.json") if f.stem.isdigit()}


# %%
# Load caches
quote_dict = get_quote_tweets_dict()
tweet_dict, conversation_trees = load_caches()

print("Loading top quoted tweet IDs...")
top_tweet_ids = load_top_tweet_ids()
high_half_life_qt_tweet_ids = top_tweet_ids[:100]
print(f"Found {len(high_half_life_qt_tweet_ids)} tweet IDs")

# %%
# Configuration
image_cache = load_img_cache(DEFAULT_CACHE_PATH)
depth = 10

# Filter out already-built strands (skip building, not rating)
rated_ids = get_rated_strand_ids(RATED_DIR)
built_ids = get_built_strand_ids(STRANDS_DIR)
# %%
all_target_ids = high_half_life_qt_tweet_ids  # Process all 100
strand_target_tweet_ids = sorted([tid for tid in all_target_ids if tid not in rated_ids and tid not in built_ids])

print(f"Already rated: {len(rated_ids)}, already built: {len(built_ids)}")
print(f"Remaining to build: {len(strand_target_tweet_ids)} strands")
# %%
# from lib.strand_builder import build_strands_phased, get_strand_seeds
# from lib.parallel import parallel_map_to_dict
# from lib.strand_builder import StrandSeed

# def get_seeds_for_tid(tid: int) -> list[StrandSeed]:
#     return get_strand_seeds(tid, tweet_dict, quote_dict, debug=False)

# seeds_by_tid, seeds_failed = parallel_map_to_dict(
#     strand_target_tweet_ids, get_seeds_for_tid,
#     max_workers=4, desc="Phase 1: Seeds"
# )
# print(f"[Phase 1] Got seeds for {len(seeds_by_tid)} strands, {len(seeds_failed)} failed")
# %%
if not strand_target_tweet_ids:
    print("All strands already processed!")
else:
    # Phase 1-4: Build strands using phased pipeline
    print("Building strands with phase-level parallelism...")
    strand_results, updated_cache = build_strands_phased(
        strand_target_tweet_ids,
        tweet_dict,
        quote_dict,
        conversation_trees,
        image_cache,
        depth=depth,
        seeds_workers=4,
        trees_workers=8,
        images_workers=2
    )

    # Save updated image cache
    save_img_cache(updated_cache, DEFAULT_CACHE_PATH)
    print(f"Built {len(strand_results)} strands, updated image cache")

    # Save only non-empty strand texts to individual files
    STRANDS_DIR.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    empty_count = 0
    for tid, result in strand_results.items():
        if result.thread_text.strip():
            with open(STRANDS_DIR / f"{tid}.json", "w") as f:
                json.dump({"tweet_id": result.tweet_id, "thread_text": result.thread_text, "seed_ids": result.seed_ids}, f, indent=2)
            saved_count += 1
        else:
            empty_count += 1
    
    print(f"Saved {saved_count} strand files to {STRANDS_DIR}/")
    if empty_count:
        print(f"[WARN] Skipped {empty_count} empty strands (not saved)")

# %%
# Load all non-empty strands for rating (including previously built ones)
class StrandData(TypedDict):
    thread_text: str
    seed_ids: list[int]


def load_strands_for_rating(strands_dir: Path, rated_dir: Path) -> dict[int, StrandData]:
    """Load strands (text + seed_ids) that haven't been rated yet."""
    rated_ids = set()
    if rated_dir.exists():
        for f in rated_dir.glob("*.json"):
            try:
                rated_ids.add(int(f.stem))
            except ValueError:
                print(f"[WARN] Could not parse rated file name: {f.name}")
                pass
    
    strands = {}
    if strands_dir.exists():
        for f in strands_dir.glob("*.json"):
            try:
                tid = int(f.stem)
                if tid in rated_ids:
                    continue
                data = json.loads(f.read_text())
                text = data.get("thread_text", "")
                if text.strip():
                    strands[tid] = {
                        "thread_text": text,
                        "seed_ids": data.get("seed_ids", [])
                    }
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[ERROR] Failed to load strand {f.name}: {e}")
                pass
    
    return strands


strands_data = load_strands_for_rating(STRANDS_DIR, RATED_DIR)
print(f"Found {len(strands_data)} strands to rate")
# %%
from lib.strand_rater import rate_strand

first_tid = list(strands_data.keys())[0]
res = rate_strand(
    thread_text=strands_data[first_tid]["thread_text"],
    tweet_id=first_tid,
    model_name="anthropic/claude-sonnet-4",
    provider="openrouter",
    max_retries=1,
    base_temperature=0.7,
    debug_dir=DEBUG_DIR,
)
res
# %%
# Rate strands using LLM
if strands_data:
    print("Rating strands...")
    rated = rate_strands_batch(
        strands_data,
        model_name="anthropic/claude-sonnet-4.5",
        provider="openrouter",
        max_workers=2,
        output_dir=RATED_DIR,
        max_retries=2,
        debug_dir=DEBUG_DIR,
    )
    print(f"Rated {len(rated)} strands, saved to {RATED_DIR}/")
else:
    print("No strands to rate")

# %%
