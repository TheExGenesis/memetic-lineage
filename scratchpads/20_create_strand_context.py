#!/usr/bin/env python3
"""
Create lightweight strand data for LLM context:
1. rated_strands_lite/ - same files without thread_text and seeds
2. all_strands_context.json - merged file with all strand metadata
"""

import json
from pathlib import Path


def main():
    data_dir = Path("data")
    rated_strands_dir = data_dir / "rated_strands"
    lite_dir = data_dir / "rated_strands_lite"

    # Create lite directory
    lite_dir.mkdir(exist_ok=True)

    all_strands = []

    # Process each rated strand
    for strand_file in sorted(rated_strands_dir.glob("*.json")):
        with open(strand_file) as f:
            strand = json.load(f)

        # Create lite version (remove thread_text and seeds)
        lite_strand = {
            "seed_tweet_id": strand["seed_tweet_id"],
            "title": strand.get("title", ""),
            "summary": strand.get("summary", ""),
            "rating": strand.get("rating", {}),
        }

        # Write lite version
        lite_file = lite_dir / strand_file.name
        with open(lite_file, "w") as f:
            json.dump(lite_strand, f, indent=2)

        # Add to merged list
        all_strands.append(lite_strand)

        print(f"Processed: {strand_file.name}")

    # Write merged context file
    context_file = data_dir / "all_strands_context.json"
    with open(context_file, "w") as f:
        json.dump(all_strands, f, indent=2)

    # Calculate sizes
    original_size = sum(f.stat().st_size for f in rated_strands_dir.glob("*.json"))
    lite_size = sum(f.stat().st_size for f in lite_dir.glob("*.json"))
    context_size = context_file.stat().st_size

    print(f"\n--- Summary ---")
    print(f"Strands processed: {len(all_strands)}")
    print(f"Original size: {original_size / 1024 / 1024:.2f} MB")
    print(f"Lite dir size: {lite_size / 1024:.2f} KB")
    print(f"Context file size: {context_size / 1024:.2f} KB")
    print(f"Size reduction: {(1 - lite_size / original_size) * 100:.1f}%")
    print(f"\nOutput:")
    print(f"  - {lite_dir}/")
    print(f"  - {context_file}")


if __name__ == "__main__":
    main()
