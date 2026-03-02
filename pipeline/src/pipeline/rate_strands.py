"""Phase 2: Rate strands with LLM."""

import json

from pipeline.config import STRANDS_DIR, RATED_DIR, DEBUG_DIR
from pipeline.helpers import get_rated_strand_ids
from pipeline.lib.strand_rater import rate_strands_batch


def run(
    model_name: str = "anthropic/claude-sonnet-4.5",
    max_workers: int = 32,
) -> int:
    """Rate strands using LLM. Returns count of newly rated strands."""
    print("\n" + "=" * 60)
    print("PHASE 2: Rate Strands")
    print("=" * 60)

    # Load strands that need rating
    rated_ids = get_rated_strand_ids()
    strands_data = {}

    for path in STRANDS_DIR.glob("*.json"):
        try:
            tid = int(path.stem)
            if tid in rated_ids:
                continue
            with open(path) as f:
                data = json.load(f)
            if data.get("thread_text", "").strip():
                strands_data[tid] = {
                    "thread_text": data["thread_text"],
                    "seeds": data.get("seeds", [])
                }
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[WARN] Failed to load {path.name}: {e}")

    print(f"Found {len(strands_data)} strands to rate")

    if not strands_data:
        print("No strands to rate!")
        return 0

    RATED_DIR.mkdir(parents=True, exist_ok=True)

    rated = rate_strands_batch(
        strands_data,
        model_name=model_name,
        provider="openrouter",
        max_workers=max_workers,
        output_dir=RATED_DIR,
        max_retries=2,
        debug_dir=DEBUG_DIR,
    )

    print(f"Rated {len(rated)} strands")
    return len(rated)
