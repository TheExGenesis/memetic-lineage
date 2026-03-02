"""Phase 1: Build strands from top quoted tweets."""

import json

from pandas import read_parquet

from pipeline.config import STRANDS_DIR, QUOTED_COUNTS_CACHE_PATH
from pipeline.helpers import get_built_strand_ids, get_rated_strand_ids
from pipeline.lib.strand_builder import build_strands_phased
from pipeline.lib.image_describer import get_image_cache


def run(
    tweet_dict: dict,
    quote_dict: dict,
    conversation_trees: dict,
    force_rebuild: bool = False,
) -> int:
    """Build strands from top quoted tweets. Returns count of newly built strands."""
    print("\n" + "=" * 60)
    print("PHASE 1: Build Strands")
    print("=" * 60)

    # Load target tweet IDs
    print("Loading top quoted tweet IDs...")
    quoted_count_tweets = read_parquet(QUOTED_COUNTS_CACHE_PATH).sort_values('quoted_count', ascending=False)
    all_target_ids = quoted_count_tweets[quoted_count_tweets.quoted_count > 5]['quoted_tweet_id'].astype(int).tolist()
    print(f"Found {len(all_target_ids)} tweet IDs with >5 quotes")

    # Filter out already processed
    rated_ids = get_rated_strand_ids()
    built_ids = get_built_strand_ids()

    if force_rebuild:
        strand_target_ids = sorted(all_target_ids)
    else:
        strand_target_ids = sorted([tid for tid in all_target_ids if tid not in rated_ids and tid not in built_ids])

    print(f"Already rated: {len(rated_ids)}, already built: {len(built_ids)}")
    print(f"Remaining to build: {len(strand_target_ids)}")

    if not strand_target_ids:
        print("All strands already built!")
        return 0

    # Build strands
    image_cache = get_image_cache()
    strand_results = build_strands_phased(
        strand_target_ids,
        tweet_dict,
        quote_dict,
        conversation_trees,
        image_cache,
        depth=10,
        seeds_workers=4,
        trees_workers=8,
        images_workers=2
    )

    # Save to strands/ directory
    STRANDS_DIR.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    empty_count = 0

    for tid, result in strand_results.items():
        if result.thread_text.strip():
            with open(STRANDS_DIR / f"{tid}.json", "w") as f:
                json.dump({
                    "tweet_id": result.tweet_id,
                    "thread_text": result.thread_text,
                    "seeds": [{"tweet_id": s.tweet_id, "source_type": s.source_type} for s in result.seeds]
                }, f, indent=2)
            saved_count += 1
        else:
            empty_count += 1

    print(f"Saved {saved_count} strand files to {STRANDS_DIR}/")
    if empty_count:
        print(f"[WARN] Skipped {empty_count} empty strands")

    return saved_count
