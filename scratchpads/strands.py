#!/usr/bin/env python3
"""
Unified Strand Processing Pipeline

Combines all strand processing steps into a single script:
1. Build strands from top quoted tweets
2. Rate strands with LLM
3. Generate summaries (title + summary)
4. Generate histograms (tweet distribution over time)
4.5. Generate tweet embeddings (per-tweet for atlas visualization)
4.6. Generate atlas parquet (UMAP on tweet embeddings)
5. Export to frontend (histograms + semantic map + atlas)
6. Generate seriation order (topic sorting)
7. Generate chronological summary text file
8. Generate bangers_tweets.json (self-quote-filtered counts + quote relationships)

Usage:
    python strands.py                    # Run full pipeline
    python strands.py --bangers-only     # Only generate bangers_tweets.json (Phase 8)
    python strands.py --skip-build       # Skip building (use existing strands/)
    python strands.py --skip-rate        # Skip rating (use existing rated_strands/)
    python strands.py --skip-umap        # Skip UMAP (expensive, not always needed)
    python strands.py --skip-tweet-embeddings  # Skip tweet embedding generation
    python strands.py --skip-atlas-parquet     # Skip atlas parquet generation
    python strands.py --skip-bangers     # Skip bangers data generation
    python strands.py --enrich-only      # Only add summaries/histograms to existing rated strands
    python strands.py --export-only      # Only export to frontend
    python strands.py --parquet /path/to/tweets.parquet  # Custom parquet path
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Set

from dotenv import load_dotenv
from pandas import read_parquet
from tqdm import tqdm

# Local imports
from lib.strand_caches import (
    get_quote_tweets_dict, get_filtered_quote_tweets_dict,
    load_caches, generate_filtered_quote_cache,
    DEFAULT_PARQUET_PATH,
)
from lib.strand_builder import build_strands_phased
from lib.strand_rater import rate_strands_batch
from lib.image_describer import get_image_cache
from lib.histogram import generate_histogram, generate_histogram_export
from lib.parallel import parallel_map_to_dict
from lib.count_quotes import count_quotes

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

# Paths
DATA_DIR = Path(__file__).parent / "data"
TOP_IDS_PATH = DATA_DIR / "top_quoted_tweet_ids.json"
STRANDS_DIR = DATA_DIR / "strands"
RATED_DIR = DATA_DIR / "rated_strands"
DEBUG_DIR = DATA_DIR / "debug_responses"
QUOTED_COUNTS_CACHE_PATH = DATA_DIR / "quoted_counts_cache.parquet"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "strand_summary_embeddings.json"
LABEL_CONFIG_PATH = DATA_DIR / "strand_label_config.json"
ATLAS_PARQUET_PATH = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_EMBEDDINGS_DIR = DATA_DIR / "all_tweet_embeddings"

# Frontend export paths
FRONTEND_PUBLIC_DIR = Path(__file__).parent.parent / "bangers" / "public"
ATLAS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "atlas_data.json"
HISTOGRAM_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_histograms.json"
SEMANTIC_MAP_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_semantic_map.json"
SERIATION_ORDER_PATH = FRONTEND_PUBLIC_DIR / "strand_seriation_order.json"
STRANDS_DATA_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strands_data.json"
BANGERS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "bangers_tweets.json"
VALID_ACCOUNTS_PATH = DATA_DIR / "valid_account_ids_cache.json"
ALL_SUMMARIES_PATH = DATA_DIR / "all_summaries_chronological.txt"


def get_built_strand_ids() -> Set[int]:
    """Get IDs of strands that have been built."""
    if not STRANDS_DIR.exists():
        return set()
    return {int(f.stem) for f in STRANDS_DIR.glob("*.json") if f.stem.isdigit()}


def get_rated_strand_ids() -> Set[int]:
    """Get IDs of strands that have been rated."""
    if not RATED_DIR.exists():
        return set()
    return {int(f.stem) for f in RATED_DIR.glob("*.json") if f.stem.isdigit()}


def load_rated_strand(strand_id: int) -> dict:
    """Load a single rated strand."""
    path = RATED_DIR / f"{strand_id}.json"
    with open(path) as f:
        return json.load(f)


def save_rated_strand(strand_id: int, data: dict):
    """Save a single rated strand."""
    path = RATED_DIR / f"{strand_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_all_rated_strands() -> dict[int, dict]:
    """Load all rated strands."""
    strands = {}
    for path in RATED_DIR.glob("*.json"):
        try:
            strand_id = int(path.stem)
            with open(path) as f:
                strands[strand_id] = json.load(f)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[WARN] Failed to load {path.name}: {e}")
    return strands


# =============================================================================
# Phase 1: Build Strands
# =============================================================================

def phase_build_strands(
    tweet_dict: dict,
    quote_dict: dict,
    conversation_trees: dict,
    force_rebuild: bool = False
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


# =============================================================================
# Phase 2: Rate Strands
# =============================================================================

def phase_rate_strands(
    model_name: str = "anthropic/claude-sonnet-4.5",
    max_workers: int = 32
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


# =============================================================================
# Phase 3: Generate Summaries
# =============================================================================

def _generate_summary_for_strand(strand_data: dict, model_name: str) -> dict:
    """Generate title and summary for a single strand."""
    import os
    from openai import OpenAI
    from pydantic import BaseModel

    class StrandSummary(BaseModel):
        title: str
        summary: str

    SUMMARIZER_PROMPT = """You extract what's ACTUALLY INTERESTING from twitter discourse threads.

Given strand metadata and tweets, write:
1. A punchy title (max 60 chars) - think newsletter subject line, not academic paper
2. A summary (1-3 paragraphs) that:
   - Opens with the juiciest insight or most quotable take
   - Names specific people and their specific claims
   - Tracks the arc: what triggered it, what peaked, what died
   - Ends with why would someone care

Write like you're telling a friend about drama you witnessed. Dense, specific, zero fluff.

Output JSON with fields: title, summary"""

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

    data_for_llm = {
        "seed_tweet_id": strand_data["seed_tweet_id"],
        "rating": strand_data.get("rating", {}),
        "thread_text": strand_data.get("thread_text", "")
    }

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SUMMARIZER_PROMPT},
            {"role": "user", "content": f"<strand_data>\n{json.dumps(data_for_llm, indent=2)}\n</strand_data>"},
        ],
        temperature=0.7,
        max_completion_tokens=1024,
        response_format={"type": "json_object"},
    )

    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Empty response from LLM")

    parsed = json.loads(content.strip())
    return {
        "title": parsed.get("title", "Untitled"),
        "summary": parsed.get("summary", "")
    }


def phase_generate_summaries(
    model_name: str = "openai/gpt-4o-mini",
    max_workers: int = 32,
    force_regenerate: bool = False
) -> int:
    """Generate summaries for strands missing title/summary. Updates rated_strands in-place."""
    print("\n" + "=" * 60)
    print("PHASE 3: Generate Summaries")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    # Find strands missing summaries
    pending = []
    for strand_id, data in all_strands.items():
        if force_regenerate or not data.get("title") or not data.get("summary"):
            pending.append(strand_id)

    print(f"Found {len(pending)} strands needing summaries")

    if not pending:
        print("All strands have summaries!")
        return 0

    def process_one(strand_id: int) -> dict:
        data = all_strands[strand_id]
        result = _generate_summary_for_strand(data, model_name)

        # Update strand data in-place
        data["title"] = result["title"]
        data["summary"] = result["summary"]

        # Save immediately
        save_rated_strand(strand_id, data)
        return result

    results, failed = parallel_map_to_dict(
        pending, process_one,
        max_workers=max_workers,
        desc="Generating summaries"
    )

    if failed:
        print(f"[WARN] {len(failed)} strands failed: {list(failed.keys())[:5]}...")

    print(f"Generated summaries for {len(results)} strands")
    return len(results)


# =============================================================================
# Phase 4: Generate Histograms
# =============================================================================

def phase_generate_histograms(force_regenerate: bool = False) -> int:
    """Generate histograms for strands. Updates rated_strands in-place."""
    print("\n" + "=" * 60)
    print("PHASE 4: Generate Histograms")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    # Find strands missing histograms
    updated_count = 0

    for strand_id, data in all_strands.items():
        if not force_regenerate and data.get("histogram"):
            continue

        thread_text = data.get("thread_text", "")
        if not thread_text:
            print(f"[WARN] Strand {strand_id} has no thread_text")
            continue

        histogram = generate_histogram(thread_text)
        data["histogram"] = histogram

        save_rated_strand(strand_id, data)
        updated_count += 1

    print(f"Generated histograms for {updated_count} strands")
    return updated_count


# =============================================================================
# Phase 4.5: Generate Tweet Embeddings (per-tweet for atlas)
# =============================================================================

def _extract_tweet_ids_from_thread(thread_text: str) -> list[int]:
    """Extract all tweet IDs from thread_text."""
    import re
    tweet_ids = []
    pattern = re.compile(r'^[│├└─\s]*(\d{15,})\s+\[')
    for line in thread_text.split('\n'):
        match = pattern.match(line)
        if match:
            tweet_ids.append(int(match.group(1)))
    return tweet_ids


def _parse_tweet_from_thread(thread_text: str, tweet_id: int) -> dict | None:
    """Extract tweet text, date, likes, retweets from thread_text by tweet_id."""
    import re
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')

    # Find header line
    header_pattern = re.compile(rf'^[│├└─\s]*{tweet_id_str}\s+\[')
    start_idx = None
    for i, line in enumerate(lines):
        if header_pattern.match(line):
            start_idx = i
            break

    if start_idx is None:
        return None

    header_line = lines[start_idx]

    # Extract date [YYYY-MM-DD]
    date_match = re.search(rf'{tweet_id_str}\s+\[([0-9-]+)\]', header_line)
    date = date_match.group(1) if date_match else None

    # Extract likes/retweets: 💜 N 🔁 M
    stats_match = re.search(r'💜\s+(\d+)\s+🔁\s+(\d+)', header_line)
    likes = int(stats_match.group(1)) if stats_match else None
    retweets = int(stats_match.group(2)) if stats_match else None

    # Get tree prefix
    prefix_match = re.match(rf'^([│├└─\s]*){tweet_id_str}', header_line)
    tree_prefix = prefix_match.group(1) if prefix_match else ""

    # Collect content lines
    content_lines = []
    next_tweet_pattern = re.compile(r'^[│├└─\s]*\d{15,}\s+\[')
    separators = {'===', '↓'}

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped_line = line[len(tree_prefix):] if tree_prefix and line.startswith(tree_prefix) else line
        stripped = stripped_line.strip()

        if stripped in separators:
            break
        if next_tweet_pattern.match(line):
            break
        if re.match(r'^[│\s]*[├└]──\s*\d{15,}\s+\[', line):
            break

        content_lines.append(stripped)

    text = '\n'.join(content_lines).strip()
    text = re.sub(r'\n{3,}', '\n\n', text)

    return {
        'text': text.strip(),
        'date': date,
        'likes': likes,
        'retweets': retweets,
    }


def _clean_tweet_text(text: str) -> str:
    """Clean tweet text for embedding."""
    import re
    # Remove tree connectors
    text = re.sub(r'^[│├└─\s]+', '', text, flags=re.MULTILINE)
    # Remove leading @mentions
    text = re.sub(r'^(@\w+\s*)+', '', text.strip())
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove arrows
    text = re.sub(r'↓', '', text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _build_embedding_text(tweet_text: str, annotation: str = None) -> str | None:
    """Combine tweet text and annotation for embedding."""
    cleaned = _clean_tweet_text(tweet_text)
    if len(cleaned) < 10:
        return None

    if annotation:
        return f"Tweet:\n{cleaned}\n\nAnnotation:\n{annotation}"
    return f"Tweet:\n{cleaned}"


def phase_generate_tweet_embeddings(
    max_workers: int = 32,
    force_regenerate: bool = False
) -> int:
    """Generate per-tweet embeddings for atlas visualization using parallel processing."""
    import os
    from openai import OpenAI

    print("\n" + "=" * 60)
    print("PHASE 4.5: Generate Tweet Embeddings")
    print("=" * 60)

    TWEET_EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    # Find strands needing embeddings
    all_strands = load_all_rated_strands()
    existing = {int(p.stem) for p in TWEET_EMBEDDINGS_DIR.glob("*.json") if p.stem.isdigit()}

    if force_regenerate:
        pending = list(all_strands.keys())
    else:
        pending = [sid for sid in all_strands.keys() if sid not in existing]

    print(f"Found {len(all_strands)} rated strands, {len(existing)} already have tweet embeddings")
    print(f"Processing {len(pending)} strands with {max_workers} parallel workers")

    if not pending:
        print("All strands already have tweet embeddings!")
        return 0

    # Setup API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[ERROR] OPENROUTER_API_KEY not found")
        return 0

    EMBEDDING_MODEL = "openai/text-embedding-3-large"

    def process_single_strand(strand_id: int) -> bool:
        """Process a single strand - returns True on success."""
        # Create client per-thread for thread safety
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                all_embeddings.extend([d.embedding for d in response.data])
            return all_embeddings

        strand = all_strands[strand_id]
        thread_text = strand.get("thread_text", "")
        if not thread_text:
            return False

        # Get essential tweets lookup
        essential_lookup = {}
        if "rating" in strand and "essential_tweets" in strand["rating"]:
            for et in strand["rating"]["essential_tweets"]:
                tid = str(et.get("tweet_id", ""))
                essential_lookup[tid] = et.get("annotation", "")

        # Extract all tweets
        tweet_ids = _extract_tweet_ids_from_thread(thread_text)
        tweets_to_embed = []

        for tid in tweet_ids:
            parsed = _parse_tweet_from_thread(thread_text, tid)
            if not parsed or not parsed["text"]:
                continue

            tid_str = str(tid)
            is_essential = tid_str in essential_lookup
            is_root = tid_str == str(strand_id)
            annotation = essential_lookup.get(tid_str)

            text_to_embed = _build_embedding_text(parsed["text"], annotation)
            if text_to_embed is None:
                continue

            tweet_type = "regular"
            if is_root and is_essential:
                tweet_type = "root_essential"
            elif is_root:
                tweet_type = "root_regular"
            elif is_essential:
                tweet_type = "essential"

            tweets_to_embed.append({
                "tweet_id": tid_str,
                "annotation": annotation,
                "tweet_text": _clean_tweet_text(parsed["text"]),
                "text_to_embed": text_to_embed,
                "tweet_type": tweet_type,
                "date": parsed["date"],
                "likes": parsed["likes"],
                "retweets": parsed["retweets"],
            })

        if not tweets_to_embed:
            return False

        # Generate embeddings
        texts = [t["text_to_embed"] for t in tweets_to_embed]
        embeddings = get_embeddings_batch(texts)

        # Build result
        results = []
        for i, tweet in enumerate(tweets_to_embed):
            results.append({
                "tweet_id": tweet["tweet_id"],
                "annotation": tweet["annotation"],
                "tweet_text": tweet["tweet_text"],
                "text_embedded": tweet["text_to_embed"],
                "tweet_type": tweet["tweet_type"],
                "date": tweet["date"],
                "likes": tweet["likes"],
                "retweets": tweet["retweets"],
                "embedding": embeddings[i],
            })

        # Save
        output = {
            "seed_tweet_id": str(strand_id),
            "model": EMBEDDING_MODEL,
            "all_tweet_embeddings": results,
        }
        with open(TWEET_EMBEDDINGS_DIR / f"{strand_id}.json", "w") as f:
            json.dump(output, f)

        return True

    # Process in parallel
    results, failed = parallel_map_to_dict(
        pending,
        process_single_strand,
        max_workers=max_workers,
        desc="Generating tweet embeddings"
    )

    processed = sum(1 for v in results.values() if v)
    if failed:
        print(f"[WARN] {len(failed)} strands failed to process")
    print(f"Generated tweet embeddings for {processed} strands")
    return processed


# =============================================================================
# Phase 4.6: Generate Atlas Parquet (UMAP on tweet embeddings)
# =============================================================================

def phase_generate_atlas_parquet(force_regenerate: bool = False) -> bool:
    """Run UMAP on tweet embeddings and save to parquet for atlas."""
    import numpy as np
    import pandas as pd
    import umap

    print("\n" + "=" * 60)
    print("PHASE 4.6: Generate Atlas Parquet")
    print("=" * 60)

    # Check if we need to regenerate
    if not force_regenerate and ATLAS_PARQUET_PATH.exists():
        # Check if parquet is up to date with embeddings
        embedding_files = list(TWEET_EMBEDDINGS_DIR.glob("*.json"))
        if embedding_files:
            newest_embedding = max(f.stat().st_mtime for f in embedding_files)
            parquet_mtime = ATLAS_PARQUET_PATH.stat().st_mtime
            if parquet_mtime > newest_embedding:
                print("Atlas parquet is up to date, skipping")
                return True

    # Load all tweet embeddings
    embedding_files = sorted(TWEET_EMBEDDINGS_DIR.glob("*.json"))
    if not embedding_files:
        print("[ERROR] No tweet embedding files found")
        return False

    print(f"Loading embeddings from {len(embedding_files)} files...")

    all_embeddings = []
    all_metadata = []

    from tqdm import tqdm
    for filepath in tqdm(embedding_files, desc="Loading embeddings"):
        with open(filepath) as f:
            data = json.load(f)

        strand_id = data["seed_tweet_id"]
        embeddings_data = data.get("all_tweet_embeddings", [])

        for item in embeddings_data:
            all_embeddings.append(item["embedding"])
            all_metadata.append({
                "tweet_id": item["tweet_id"],
                "strand_id": strand_id,
                "annotation": item.get("annotation", "") or "",
                "tweet_type": item.get("tweet_type", "unknown"),
                "text": item.get("text_embedded", item.get("tweet_text", "")),
                "date": item.get("date"),
                "likes": item.get("likes"),
                "retweets": item.get("retweets"),
            })

    print(f"Loaded {len(all_embeddings)} tweet embeddings from {len(embedding_files)} strands")

    if len(all_embeddings) < 2:
        print("[ERROR] Need at least 2 embeddings for UMAP")
        return False

    # Run UMAP
    print("Running UMAP projection...")
    X = np.array(all_embeddings)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=10,
        min_dist=0.1,
        random_state=42,
        verbose=True,
    )
    embedding_2d = reducer.fit_transform(X)

    # Create DataFrame
    df = pd.DataFrame(all_metadata)
    df["projection_x"] = embedding_2d[:, 0]
    df["projection_y"] = embedding_2d[:, 1]
    df["is_essential"] = df["tweet_type"].isin(["essential", "root_essential"])
    df["is_root"] = df["tweet_type"].isin(["root_essential", "root_regular"])

    # Save parquet
    df.to_parquet(ATLAS_PARQUET_PATH, index=False)
    print(f"Saved atlas parquet: {ATLAS_PARQUET_PATH}")
    print(f"  {len(df)} tweets from {df['strand_id'].nunique()} strands")

    return True


# =============================================================================
# Phase 5: Export to Frontend
# =============================================================================

def phase_export_strands_data() -> bool:
    """Export all strands with seed tweets to a single static JSON.

    This eliminates 252 file reads + Supabase call on each page load.
    """
    print("\n" + "=" * 60)
    print("PHASE 5: Export Strands Data")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    tweet_dict, _ = load_caches()

    print(f"Loaded {len(all_strands)} rated strands")

    strands_with_tweets = []
    for strand_id, data in all_strands.items():
        # Get seed tweet from tweet_dict
        seed_tweet = tweet_dict.get(strand_id)
        seed_tweet_data = None
        if seed_tweet:
            seed_tweet_data = {
                'tweet_id': str(strand_id),
                'full_text': seed_tweet.get('full_text', ''),
                'created_at': seed_tweet.get('created_at', ''),
                'username': seed_tweet.get('username', 'unknown'),
                'avatar_media_url': seed_tweet.get('profile_image_url', seed_tweet.get('avatar_media_url')),
                'media_urls': seed_tweet.get('media_urls', []),
                'like_count': seed_tweet.get('favorite_count', seed_tweet.get('like_count', 0)) or 0,
                'retweet_count': seed_tweet.get('retweet_count', 0) or 0,
            }

        strands_with_tweets.append({
            'seed_tweet_id': str(strand_id),
            'title': data.get('title'),
            'summary': data.get('summary'),
            'seeds': data.get('seeds', []),
            'rating': data.get('rating', {}),
            'seedTweet': seed_tweet_data,
        })

    # Sort by rating descending
    strands_with_tweets.sort(
        key=lambda s: s['rating'].get('rating', 0) if isinstance(s['rating'], dict) else 0,
        reverse=True
    )

    output = {
        'generatedAt': datetime.now().isoformat(),
        'count': len(strands_with_tweets),
        'strands': strands_with_tweets,
    }

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(STRANDS_DATA_EXPORT_PATH, 'w') as f:
        json.dump(output, f)

    file_size = STRANDS_DATA_EXPORT_PATH.stat().st_size / 1024
    print(f"Exported {len(strands_with_tweets)} strands to {STRANDS_DATA_EXPORT_PATH} ({file_size:.1f} KB)")
    return True


def phase_export_histograms() -> bool:
    """Export histogram data to frontend."""
    print("\n" + "=" * 60)
    print("PHASE 5a: Export Histograms")
    print("=" * 60)

    all_strands = load_all_rated_strands()

    # Check all have histograms
    missing = [sid for sid, data in all_strands.items() if not data.get("histogram")]
    if missing:
        print(f"[ERROR] {len(missing)} strands missing histograms!")
        print(f"  First few: {missing[:5]}")
        return False

    # Generate export
    export_data = generate_histogram_export({str(k): v for k, v in all_strands.items()})

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTOGRAM_EXPORT_PATH, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(all_strands)} strand histograms to {HISTOGRAM_EXPORT_PATH}")
    return True


def phase_export_semantic_map() -> bool:
    """Export UMAP semantic map to frontend."""
    print("\n" + "=" * 60)
    print("PHASE 5b: Export Semantic Map (UMAP)")
    print("=" * 60)

    import os
    import numpy as np
    import requests
    import umap

    all_strands = load_all_rated_strands()
    tweet_dict, _ = load_caches()

    # Check all have summaries (needed for embeddings)
    missing = [sid for sid, data in all_strands.items() if not data.get("summary")]
    if missing:
        print(f"[ERROR] {len(missing)} strands missing summaries!")
        return False

    # Sort by strand_id for consistent ordering
    strand_ids = sorted(all_strands.keys())
    strands_list = [all_strands[sid] for sid in strand_ids]

    print(f"Processing {len(strands_list)} strands for UMAP...")

    # Load cached embeddings
    embeddings = [None] * len(strands_list)
    if EMBEDDINGS_CACHE_PATH.exists():
        with open(EMBEDDINGS_CACHE_PATH) as f:
            cached = json.load(f)
        cache_lookup = {int(e['seed_tweet_id']): e['embedding'] for e in cached.get('embeddings', [])}
        for i, s in enumerate(strands_list):
            emb = cache_lookup.get(s['seed_tweet_id'])
            if emb:
                embeddings[i] = emb

    # Find missing embeddings
    missing_indices = [i for i, e in enumerate(embeddings) if e is None]

    if missing_indices:
        print(f"Generating {len(missing_indices)} new embeddings...")
        texts = [strands_list[i].get('summary', '') for i in missing_indices]

        # Batch embed
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        batch_size = 50
        new_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = requests.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": "openai/text-embedding-3-small", "input": batch}
            )
            response.raise_for_status()
            new_embeddings.extend([d['embedding'] for d in response.json()['data']])

        for idx, emb in zip(missing_indices, new_embeddings):
            embeddings[idx] = emb

        # Save updated cache
        cache_data = {
            'model': 'openai/text-embedding-3-small',
            'embeddings': [
                {'seed_tweet_id': str(s['seed_tweet_id']), 'embedding': e}
                for s, e in zip(strands_list, embeddings)
            ]
        }
        with open(EMBEDDINGS_CACHE_PATH, 'w') as f:
            json.dump(cache_data, f)
        print(f"Saved embeddings to {EMBEDDINGS_CACHE_PATH}")

    # Run UMAP
    print("Running UMAP...")
    X = np.array(embeddings)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=10,
        min_dist=0.1,
        metric='cosine',
        random_state=42
    )
    embedding_2d = reducer.fit_transform(X)

    # Scale to banner aspect ratio (3:1)
    BANNER_WIDTH = 1200
    BANNER_HEIGHT = 400

    raw_x = embedding_2d[:, 0]
    raw_y = embedding_2d[:, 1]
    x_norm = (raw_x - raw_x.min()) / (raw_x.max() - raw_x.min() + 1e-9)
    y_norm = (raw_y - raw_y.min()) / (raw_y.max() - raw_y.min() + 1e-9)
    x = x_norm * (BANNER_WIDTH / BANNER_HEIGHT)
    y = y_norm

    # Load label config
    label_texts = {}
    labeled_indices = []
    if LABEL_CONFIG_PATH.exists():
        with open(LABEL_CONFIG_PATH) as f:
            label_config = json.load(f)
        config_lookup = {c['seed_tweet_id']: c for c in label_config}

        for i, s in enumerate(strands_list):
            config = config_lookup.get(str(s['seed_tweet_id']))
            if config and config.get('displayed'):
                labeled_indices.append(i)
                label_texts[str(s['seed_tweet_id'])] = config.get('custom_label') or config.get('title', '')

    # Generate colors based on position
    import colorsys
    center_x, center_y = x.mean(), y.mean()
    colors = []
    for xi, yi in zip(x, y):
        angle = np.arctan2(yi - center_y, xi - center_x)
        hue = (angle + np.pi) / (2 * np.pi)
        r, g, b = colorsys.hls_to_rgb(hue, 0.50, 0.85)
        colors.append(f'rgb({int(r*255)},{int(g*255)},{int(b*255)})')

    # Build export data
    export_data = {
        'width': BANNER_WIDTH,
        'height': BANNER_HEIGHT,
        'points': []
    }

    for i, s in enumerate(strands_list):
        tweet_info = tweet_dict.get(s['seed_tweet_id'], {})
        strand_id_str = str(s['seed_tweet_id'])

        export_data['points'].append({
            'seed_tweet_id': strand_id_str,
            'title': s.get('title', 'Untitled'),
            'label': label_texts.get(strand_id_str),
            'x': float(x[i]),
            'y': float(y[i]),
            'color': colors[i],
            'username': tweet_info.get('username', 'unknown'),
            'likes': tweet_info.get('favorite_count', 0) or 0,
            'retweets': tweet_info.get('retweet_count', 0) or 0,
            'seeds_count': len(s.get('seeds', [])),
            'tweets_count': s.get('histogram', {}).get('total_tweets', 0),
            'full_text': (tweet_info.get('full_text', '') or '')[:200],
            'summary': (s.get('summary', '') or '')[:300],
        })

    export_data['labeled_indices'] = labeled_indices

    with open(SEMANTIC_MAP_EXPORT_PATH, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported semantic map to {SEMANTIC_MAP_EXPORT_PATH}")
    return True


def phase_export_atlas() -> bool:
    """Export detailed atlas data (tweet-level UMAP) to frontend."""
    print("\n" + "=" * 60)
    print("PHASE 5c: Export Atlas Data")
    print("=" * 60)

    import re
    import numpy as np
    import pandas as pd
    from tqdm import tqdm

    # Check if parquet exists
    if not ATLAS_PARQUET_PATH.exists():
        print(f"[WARN] Atlas parquet not found at {ATLAS_PARQUET_PATH}")
        print("  Run pipeline without --skip-tweet-embeddings and --skip-atlas-parquet to generate it.")
        return False

    # Load parquet
    print(f"Loading UMAP projections from {ATLAS_PARQUET_PATH}...")
    df = pd.read_parquet(ATLAS_PARQUET_PATH)
    print(f"Loaded {len(df)} tweets with projections")

    # Load rated strands for metadata
    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands for metadata")

    # Load tweet_dict for usernames
    tweet_dict, _ = load_caches()

    # Build strand metadata
    strands_meta = {}
    for strand_id, data in all_strands.items():
        strand_id_str = str(strand_id)

        # Get essential tweets with annotations
        essential_tweets = {}
        if 'rating' in data and 'essential_tweets' in data['rating']:
            for et in data['rating']['essential_tweets']:
                tweet_id = str(et.get('tweet_id', ''))
                annotation = et.get('annotation', '')
                if tweet_id:
                    essential_tweets[tweet_id] = annotation

        root_tweet = tweet_dict.get(strand_id)
        root_username = root_tweet.get('username', 'unknown') if root_tweet else 'unknown'

        strands_meta[strand_id_str] = {
            'title': data.get('title', 'Untitled'),
            'summary': data.get('summary', ''),
            'label': data.get('label', data.get('title', '')),
            'username': root_username,
            'essential_tweets': essential_tweets,
            'rating': data.get('rating', {}).get('rating', 5) if isinstance(data.get('rating'), dict) else 5,
        }

    # Helper to get username
    def get_username(tweet_id_str: str) -> str:
        try:
            tweet = tweet_dict.get(int(tweet_id_str))
            return tweet.get('username', 'unknown') if tweet else 'unknown'
        except (ValueError, TypeError):
            return 'unknown'

    # Build tweets data
    print("Building atlas data...")
    tweets_data = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing tweets"):
        tweet_id = str(row['tweet_id'])
        strand_id = str(row['strand_id'])

        strand_meta = strands_meta.get(strand_id, {})
        is_essential = row.get('is_essential', False) or row.get('tweet_type', '') in ['essential', 'root_essential']
        is_root = row.get('is_root', False) or row.get('tweet_type', '') in ['root_essential', 'root_regular']

        username = get_username(tweet_id)
        annotation = strand_meta.get('essential_tweets', {}).get(tweet_id, '') if is_essential else ''

        likes = int(row.get('likes', 0)) if pd.notna(row.get('likes')) else 0
        retweets = int(row.get('retweets', 0)) if pd.notna(row.get('retweets')) else 0

        text = str(row.get('text', ''))
        if text.startswith('Tweet:\n'):
            text = text[7:]
        # Strip out "Annotation:" section if present (it's stored separately)
        if '\n\nAnnotation:\n' in text:
            text = text.split('\n\nAnnotation:\n')[0]

        tweets_data.append({
            'id': tweet_id,
            'sid': strand_id,
            'txt': text[:300],
            'dt': str(row.get('date', ''))[:10] if pd.notna(row.get('date')) else '',
            'lk': likes,
            'rt': retweets,
            'x': round(float(row['projection_x']), 4),
            'y': round(float(row['projection_y']), 4),
            'e': 1 if is_essential else 0,
            'r': 1 if is_root else 0,
            'u': username,
            'a': annotation[:200] if annotation else '',
        })

    # Compute strand colors
    NAUSICAA_COLORS = [
        '#6b3fa0', '#8352b5', '#5e4fa2', '#3288bd', '#21a0a0',
        '#41b6ab', '#66c2a4', '#78c679', '#addd8e', '#f4a742',
        '#d94f6b', '#b5456e', '#8c4799',
    ]

    strand_tweets = {}
    for t in tweets_data:
        sid = t['sid']
        if sid not in strand_tweets:
            strand_tweets[sid] = []
        strand_tweets[sid].append(t)

    all_x = [t['x'] for t in tweets_data]
    all_y = [t['y'] for t in tweets_data]
    center_x = np.mean(all_x)
    center_y = np.mean(all_y)

    strand_colors = {}
    for strand_id, tweets in strand_tweets.items():
        important = [t for t in tweets if t['e'] or t['r']]
        to_use = important if important else tweets
        xs = [t['x'] for t in to_use]
        ys = [t['y'] for t in to_use]
        median_x = np.median(xs)
        median_y = np.median(ys)
        angle = np.arctan2(median_y - center_y, median_x - center_x)
        t_val = (angle + np.pi) / (2 * np.pi)
        idx = int(t_val * len(NAUSICAA_COLORS)) % len(NAUSICAA_COLORS)
        strand_colors[strand_id] = NAUSICAA_COLORS[idx]

    # Build strands output
    strands_output = {}
    for strand_id, meta in strands_meta.items():
        strands_output[strand_id] = {
            'title': meta['title'],
            'label': meta['title'],
            'summary': meta['summary'][:500],
            'username': meta['username'],
            'color': strand_colors.get(strand_id, '#888888'),
            'score': meta.get('rating', 5),
        }

    # Add color to tweets
    for t in tweets_data:
        t['c'] = strand_colors.get(t['sid'], '#888888')

    # Output
    output = {
        'tweets': tweets_data,
        'strands': strands_output,
        'palette': NAUSICAA_COLORS,
    }

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(ATLAS_EXPORT_PATH, 'w') as f:
        json.dump(output, f)

    file_size = ATLAS_EXPORT_PATH.stat().st_size / (1024 * 1024)
    print(f"Exported {len(tweets_data)} tweets to {ATLAS_EXPORT_PATH} ({file_size:.1f} MB)")
    print(f"  Strands in parquet: {df['strand_id'].nunique()}")
    print(f"  Strands with metadata: {len(strands_meta)}")
    return True


# =============================================================================
# Phase 6: Generate Seriation Order
# =============================================================================

def phase_generate_seriation() -> bool:
    """Generate seriation order - strands sorted by semantic similarity (greedy nearest neighbor)."""
    print("\n" + "=" * 60)
    print("PHASE 6: Generate Seriation Order")
    print("=" * 60)

    import numpy as np

    # Load embeddings
    if not EMBEDDINGS_CACHE_PATH.exists():
        print(f"[ERROR] Embeddings cache not found at {EMBEDDINGS_CACHE_PATH}")
        return False

    with open(EMBEDDINGS_CACHE_PATH) as f:
        cache_data = json.load(f)

    embeddings_list = cache_data.get('embeddings', [])
    print(f"Loaded {len(embeddings_list)} strand embeddings")

    if len(embeddings_list) < 2:
        print("[ERROR] Need at least 2 strands for seriation")
        return False

    # Load ratings to find starting point
    all_strands = load_all_rated_strands()

    # Build lookup: seed_tweet_id -> (embedding, rating)
    strand_data = {}
    for entry in embeddings_list:
        seed_id = str(entry['seed_tweet_id'])
        embedding = np.array(entry['embedding'])
        strand = all_strands.get(int(seed_id), {})
        rating_obj = strand.get('rating', {})
        rating = rating_obj.get('rating', 5) if isinstance(rating_obj, dict) else 5
        strand_data[seed_id] = {
            'embedding': embedding,
            'rating': rating,
        }

    # Normalize embeddings for cosine similarity
    for data in strand_data.values():
        norm = np.linalg.norm(data['embedding'])
        if norm > 0:
            data['embedding'] = data['embedding'] / norm

    # Start with a high-scoring strand
    start_id = max(strand_data.keys(), key=lambda x: strand_data[x]['rating'])
    print(f"Starting seriation from strand {start_id} (rating: {strand_data[start_id]['rating']})")

    # Greedy nearest neighbor seriation
    remaining = set(strand_data.keys())
    order = []
    current_id = start_id
    remaining.remove(current_id)
    order.append({'id': current_id, 'distance': 0.0})

    while remaining:
        current_emb = strand_data[current_id]['embedding']

        # Find nearest remaining strand
        best_id = None
        best_dist = float('inf')

        for candidate_id in remaining:
            candidate_emb = strand_data[candidate_id]['embedding']
            # Cosine distance = 1 - cosine similarity
            similarity = np.dot(current_emb, candidate_emb)
            distance = 1 - similarity
            if distance < best_dist:
                best_dist = distance
                best_id = candidate_id

        if best_id is None:
            break

        order.append({'id': best_id, 'distance': round(float(best_dist), 6)})
        remaining.remove(best_id)
        current_id = best_id

    print(f"Generated seriation order for {len(order)} strands")

    # Compute some stats
    distances = [o['distance'] for o in order[1:]]  # Skip first (distance=0)
    if distances:
        print(f"  Distance stats: min={min(distances):.4f}, max={max(distances):.4f}, mean={np.mean(distances):.4f}")

    # Save to frontend
    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'order': order,
        'start_id': start_id,
        'count': len(order),
    }
    with open(SERIATION_ORDER_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Exported seriation order to {SERIATION_ORDER_PATH}")
    return True


# =============================================================================
# Phase 7: Generate Chronological Summary Text File
# =============================================================================

def phase_generate_chronological_summary() -> bool:
    """Generate a single text file with all strand summaries in chronological order."""
    print("\n" + "=" * 60)
    print("PHASE 7: Generate Chronological Summary")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    if not all_strands:
        print("[ERROR] No rated strands found")
        return False

    # Sort by tweet ID numerically (tweet IDs are chronologically ordered)
    sorted_ids = sorted(all_strands.keys(), key=lambda x: int(x))

    lines = []
    total = len(sorted_ids)

    for idx, strand_id in enumerate(sorted_ids, 1):
        data = all_strands[strand_id]

        # Extract fields
        title = data.get("title", "Untitled")
        summary = data.get("summary", "")
        rating_obj = data.get("rating", {})
        histogram = data.get("histogram", {})

        # Rating components
        if isinstance(rating_obj, dict):
            rating_num = rating_obj.get("rating", "?")
            evolution = rating_obj.get("evolution", "?")
            cohesion = rating_obj.get("cohesion", "?")
            utility = rating_obj.get("utility", "?")
            reasoning = rating_obj.get("reasoning_summary", "")
            essential_tweets = rating_obj.get("essential_tweets", [])
        else:
            rating_num = "?"
            evolution = cohesion = utility = "?"
            reasoning = ""
            essential_tweets = []

        # Total tweets from histogram
        total_tweets = histogram.get("total_tweets", 0)

        # Format the entry
        lines.append(f"═══ [{idx}/{total}] ═══")
        lines.append(f"ID: {strand_id}")
        lines.append(f"TITLE: {title}")
        lines.append(f"RATING: {rating_num}/10 | Evolution: {evolution} | Cohesion: {cohesion} | Utility: {utility} | TWEETS: {total_tweets}")
        lines.append("")
        lines.append(f"SUMMARY: {summary}")
        lines.append("")

        if reasoning:
            lines.append(f"REASONING: {reasoning}")
            lines.append("")

        if essential_tweets:
            lines.append(f"ESSENTIAL TWEETS ({len(essential_tweets)}):")
            for et in essential_tweets:
                tweet_id = et.get("tweet_id", "?")
                annotation = et.get("annotation", "")
                lines.append(f"  • {tweet_id}: {annotation}")
            lines.append("")

        lines.append("─" * 80)
        lines.append("")

    # Write to file
    with open(ALL_SUMMARIES_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"Exported {total} strand summaries to {ALL_SUMMARIES_PATH}")
    return True


# =============================================================================
# Phase 8: Generate Bangers Data (bangers_tweets.json)
# =============================================================================

def _load_valid_account_ids() -> set:
    """Load valid account IDs from cache (archive users)."""
    if not VALID_ACCOUNTS_PATH.exists():
        print(f"  [WARN] {VALID_ACCOUNTS_PATH} not found, archive_quote_count will be 0")
        return set()
    with open(VALID_ACCOUNTS_PATH) as f:
        data = json.load(f)
    ids = set(str(aid) for aid in data.get('account_ids', []))
    print(f"  Loaded {len(ids)} valid account IDs")
    return ids


def _to_int_id(tid) -> int:
    """Convert a tweet ID (string, int, or scientific notation) to int."""
    if isinstance(tid, (int,)):
        return tid
    return int(float(tid))


def _to_str_id(tid) -> str:
    """Convert a tweet ID to a clean string (no scientific notation)."""
    return str(_to_int_id(tid))


def _is_valid(val) -> bool:
    """Check if a value is non-null and non-NaN (handles pandas/numpy/pyarrow NA)."""
    if val is None:
        return False
    try:
        if val != val:  # NaN check (works for float NaN, numpy NaN, etc.)
            return False
    except (TypeError, ValueError):
        pass
    return True


def _tweet_dict_to_bangers(t: dict) -> dict:
    """Convert a tweet_dict entry to the bangers JSON format."""
    tid = _to_str_id(t['tweet_id'])
    result = {
        'tweet_id': tid,
        'full_text': t.get('full_text', '') or '',
        'username': t.get('username', 'unknown') or 'unknown',
        'created_at': str(t.get('created_at', '') or ''),
        'favorite_count': int(t.get('favorite_count', 0) or 0),
        'retweet_count': int(t.get('retweet_count', 0) or 0),
    }
    # Optional fields
    avatar = t.get('avatar_media_url')
    if _is_valid(avatar):
        result['avatar_media_url'] = str(avatar)
    reply_to = t.get('reply_to_tweet_id')
    if _is_valid(reply_to):
        result['reply_to_tweet_id'] = _to_str_id(reply_to)
    return result


def phase_generate_bangers_data(parquet_path: str = None) -> bool:
    """Generate bangers_tweets.json for the website frontend.

    Loads tweet data from diskcaches (tweet_dict + filtered_quote_tweets),
    finds all tweets quoted by community archive users, and outputs
    bangers_tweets.json with quote relationships, conversations, and year index.

    This is a standalone phase that only depends on diskcaches being generated.
    It does NOT depend on strands/atlas data.
    """
    from collections import defaultdict

    import pandas as pd

    print("\n" + "=" * 60)
    print("PHASE 8: Generate Bangers Data")
    print("=" * 60)

    # ---- Load diskcaches ----
    print("Loading diskcaches...")
    tweet_dict, reply_trees = load_caches(auto_generate=False)
    filtered_qt = get_filtered_quote_tweets_dict()
    print(f"  tweet_dict: {len(tweet_dict):,} tweets")
    print(f"  filtered_quote_tweets: {len(filtered_qt):,} quoted tweets")

    # ---- Load valid account IDs (archive users) ----
    valid_account_ids = set(_load_valid_account_ids())  # already strings
    print(f"  Archive accounts: {len(valid_account_ids)}")

    # ---- Build account_id lookup from parquet (fast: only 2 columns) ----
    # Load as strings to avoid float64 precision loss on large IDs
    print("\nLoading account_id mapping from parquet...")
    import time as _time
    t0 = _time.time()
    pq_path = Path(parquet_path or DEFAULT_PARQUET_PATH).expanduser()
    account_df = pd.read_parquet(pq_path, columns=['tweet_id', 'account_id'])
    account_df = account_df.drop_duplicates('tweet_id')
    account_df['tweet_id'] = account_df['tweet_id'].astype(str)
    account_df['account_id'] = account_df['account_id'].astype(str)
    tweet_account_map = dict(zip(account_df['tweet_id'], account_df['account_id']))
    del account_df
    print(f"  Loaded {len(tweet_account_map):,} tweet->account mappings in {_time.time()-t0:.1f}s")

    # ---- Find all quoted tweets and compute both quote counts ----
    print("\nBuilding quote relationships (all users + archive users)...")
    t0 = _time.time()
    all_tweets = {}     # tweet_id (str) -> tweet data dict
    quotes_of = {}      # quoted_tweet_id -> [archive quoting_tweet_ids] (for TweetPane display)
    quoted_by = {}      # quoting_tweet_id -> quoted_tweet_id (archive quotes only)
    quote_count_all = {}      # quoted_tweet_id (str) -> total quote count from all users
    quote_count_archive = {}  # quoted_tweet_id (str) -> quote count from archive users only
    tweet_ids_to_fetch = set()  # collect all tweet IDs we need from tweet_dict

    for quoted_int_id in tqdm(filtered_qt.iterkeys(), desc="quote_rels",
                              total=len(filtered_qt), file=sys.stdout, mininterval=1.0):
        quoting_ids = filtered_qt[quoted_int_id]
        if not quoting_ids:
            continue

        quoted_str = _to_str_id(quoted_int_id)

        # Count ALL quotes (already self-quote filtered by filtered_qt)
        quote_count_all[quoted_str] = len(quoting_ids)

        # Filter to archive user quotes for archive_quote_count and quotesOf display
        archive_quoting_ids = []
        for qid in quoting_ids:
            qid_str = str(int(qid)) if not isinstance(qid, str) else qid
            quoting_account = tweet_account_map.get(qid_str)
            if quoting_account is not None and quoting_account in valid_account_ids:
                archive_quoting_ids.append(qid)

        quote_count_archive[quoted_str] = len(archive_quoting_ids)

        # Include ALL quoted tweets (not just those with archive quotes)
        tweet_ids_to_fetch.add(quoted_int_id)

        # quotesOf only stores archive-user quote IDs (for TweetPane display)
        if archive_quoting_ids:
            quoting_str_ids = [_to_str_id(qid) for qid in archive_quoting_ids]
            quotes_of[quoted_str] = quoting_str_ids
            for qid, qid_str in zip(archive_quoting_ids, quoting_str_ids):
                quoted_by[qid_str] = quoted_str
                tweet_ids_to_fetch.add(_to_int_id(qid))

    elapsed_filter = _time.time() - t0
    print(f"  Tweets with any quotes: {len(quote_count_all):,}")
    print(f"  quotesOf (archive): {len(quotes_of):,} tweets have quotes from archive users")
    print(f"  quotedBy (archive): {len(quoted_by):,} entries")
    print(f"  Need to fetch {len(tweet_ids_to_fetch):,} tweets from diskcache")
    print(f"  Filtering took {elapsed_filter:.1f}s")

    # ---- Fetch tweet data from diskcache ----
    print("\nFetching tweet data from tweet_dict diskcache...")
    t0 = _time.time()
    for int_tid in tqdm(tweet_ids_to_fetch, desc="fetch_tweets",
                        file=sys.stdout, mininterval=1.0):
        str_tid = _to_str_id(int_tid)
        if str_tid in all_tweets:
            continue
        tweet_data = tweet_dict.get(int_tid)
        if tweet_data:
            t = _tweet_dict_to_bangers(tweet_data)
            # Set quoted_tweet_id if this is a quoting tweet
            if str_tid in quoted_by:
                t['quoted_tweet_id'] = quoted_by[str_tid]
            all_tweets[str_tid] = t

    print(f"  Fetched {len(all_tweets):,} tweets in {_time.time()-t0:.1f}s")

    # Set both quote counts and archive user flag
    for tid, tweet in all_tweets.items():
        tweet['quote_count'] = quote_count_all.get(tid, 0)
        tweet['archive_quote_count'] = quote_count_archive.get(tid, 0)
        tweet['is_archive_user'] = tweet_account_map.get(tid, '') in valid_account_ids

    # ---- Build conversation mappings from tweet_dict ----
    print("\nBuilding conversation mappings...")
    conversations_by_id = defaultdict(list)
    tweet_to_conversation = {}

    for tid, tweet in all_tweets.items():
        int_tid = _to_int_id(tid)
        t = tweet_dict.get(int_tid)
        if not t:
            continue
        conv_id = t.get('conversation_id')
        if _is_valid(conv_id):
            conv_str = _to_str_id(conv_id)
            tweet_to_conversation[tid] = conv_str
            conversations_by_id[conv_str].append(tid)

    print(f"  Conversations: {len(conversations_by_id):,}")
    print(f"  Tweets in conversations: {len(tweet_to_conversation):,}")

    # ---- Build reply mappings from tweet_dict ----
    print("Building reply mappings...")
    replies = {}
    for tid in all_tweets:
        int_tid = _to_int_id(tid)
        t = tweet_dict.get(int_tid)
        if not t:
            continue
        reply_to = t.get('reply_to_tweet_id')
        if _is_valid(reply_to):
            replies[tid] = _to_str_id(reply_to)
    print(f"  Replies: {len(replies):,}")

    # ---- Build year index ----
    print("\nBuilding year index (sorted by quote_count from all users)...")
    by_year = defaultdict(list)
    for tid, tweet in all_tweets.items():
        created_at = tweet.get('created_at', '')
        qc = tweet.get('quote_count', 0) or 0  # all-users quote count
        fav = tweet.get('favorite_count', 0) or 0

        year = None
        if created_at:
            try:
                year = int(str(created_at)[:4])
            except (ValueError, TypeError):
                pass

        if year and 2006 <= year <= 2026:
            by_year[str(year)].append((tid, (qc, fav)))

    # Sort each year descending by (quote_count, favorite_count), cap to MAX_PER_YEAR
    MAX_PER_YEAR = 500
    by_year_sorted = {}
    for year, tweets_list in sorted(by_year.items(), reverse=True):
        sorted_ids = [tid for tid, _ in sorted(tweets_list, key=lambda x: x[1], reverse=True)]
        by_year_sorted[year] = sorted_ids[:MAX_PER_YEAR]

    for year in sorted(by_year_sorted.keys(), reverse=True)[:5]:
        total = len([t for t in by_year[year]])
        capped = len(by_year_sorted[year])
        top_tid = by_year_sorted[year][0] if by_year_sorted[year] else None
        if top_tid:
            top = all_tweets.get(top_tid, {})
            print(f"  {year}: {capped}/{total} tweets (top: @{top.get('username', '?')} qc={top.get('quote_count', 0)} archive_qc={top.get('archive_quote_count', 0)})")

    # ---- Prune to only reachable tweets ----
    # Include: tweets in byYear + their quoting tweets (for TweetPane display)
    print("\nPruning to reachable tweets...")
    reachable_ids = set()
    for year_ids in by_year_sorted.values():
        reachable_ids.update(year_ids)

    # Add quoting tweets for reachable quoted tweets
    for tid in list(reachable_ids):
        if tid in quotes_of:
            reachable_ids.update(quotes_of[tid])

    # Add quoted tweets for reachable quoting tweets
    for tid in list(reachable_ids):
        if tid in quoted_by:
            reachable_ids.add(quoted_by[tid])

    pruned_tweets = {tid: all_tweets[tid] for tid in reachable_ids if tid in all_tweets}
    pruned_quotes_of = {tid: ids for tid, ids in quotes_of.items() if tid in reachable_ids}
    pruned_quoted_by = {tid: qid for tid, qid in quoted_by.items() if tid in reachable_ids}
    pruned_conversations = {cid: [t for t in tids if t in reachable_ids]
                            for cid, tids in conversations_by_id.items()
                            if any(t in reachable_ids for t in tids)}
    pruned_t2c = {tid: cid for tid, cid in tweet_to_conversation.items() if tid in reachable_ids}
    pruned_replies = {tid: pid for tid, pid in replies.items() if tid in reachable_ids}

    print(f"  Full dataset: {len(all_tweets):,} tweets")
    print(f"  Pruned to: {len(pruned_tweets):,} reachable tweets")
    print(f"  quotesOf: {len(pruned_quotes_of):,}, quotedBy: {len(pruned_quoted_by):,}")

    # ---- Clean tweet data for JSON output ----
    # Remove any pandas types that aren't JSON-serializable
    for tid, tweet in pruned_tweets.items():
        for key, val in tweet.items():
            if hasattr(val, 'item'):  # numpy scalar
                tweet[key] = val.item()
            elif pd.notna(val) is False:
                tweet[key] = None

    # ---- Output ----
    output = {
        'generatedAt': datetime.now().isoformat(),
        'tweetCount': len(pruned_tweets),
        'tweets': pruned_tweets,
        'byYear': by_year_sorted,
        'quoteRelationships': {
            'quotesOf': pruned_quotes_of,
            'quotedBy': pruned_quoted_by,
        },
        'conversations': pruned_conversations,
        'tweetToConversation': pruned_t2c,
        'replies': pruned_replies,
    }

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting to {BANGERS_EXPORT_PATH}...")
    with open(BANGERS_EXPORT_PATH, 'w') as f:
        json.dump(output, f, default=str)

    size_mb = BANGERS_EXPORT_PATH.stat().st_size / (1024 * 1024)
    print(f"  File size: {size_mb:.1f} MB")
    print(f"  Tweets: {len(pruned_tweets):,}")
    print(f"  Years: {len(by_year_sorted)}")
    print(f"  Quote relationships: {len(pruned_quotes_of):,} quotesOf, {len(pruned_quoted_by):,} quotedBy")
    print(f"  Conversations: {len(pruned_conversations):,}")
    print("Phase 8 complete!")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Unified Strand Processing Pipeline")
    parser.add_argument("--skip-build", action="store_true", help="Skip building strands")
    parser.add_argument("--skip-rate", action="store_true", help="Skip rating strands")
    parser.add_argument("--skip-summary", action="store_true", help="Skip generating summaries")
    parser.add_argument("--skip-histogram", action="store_true", help="Skip generating histograms")
    parser.add_argument("--skip-umap", action="store_true", help="Skip UMAP export")
    parser.add_argument("--skip-atlas", action="store_true", help="Skip atlas export")
    parser.add_argument("--skip-tweet-embeddings", action="store_true", help="Skip tweet embeddings generation")
    parser.add_argument("--skip-atlas-parquet", action="store_true", help="Skip atlas parquet (UMAP on tweets)")
    parser.add_argument("--enrich-only", action="store_true", help="Only add summaries/histograms")
    parser.add_argument("--export-only", action="store_true", help="Only export to frontend")
    parser.add_argument("--skip-bangers", action="store_true", help="Skip bangers data generation")
    parser.add_argument("--bangers-only", action="store_true", help="Only generate bangers data")
    parser.add_argument("--force", action="store_true", help="Force regenerate all")
    parser.add_argument("--parquet", type=str, default=None, help="Path to tweets parquet file (default: ENRICHED_TWEETS_PATH env var)")
    parser.add_argument("--rating-model", default="anthropic/claude-sonnet-4.5", help="Model for rating")
    parser.add_argument("--summary-model", default="openai/gpt-5.2", help="Model for summaries")
    args = parser.parse_args()

    print("=" * 60)
    print("STRAND PROCESSING PIPELINE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    errors = []

    # Shortcut modes
    if args.bangers_only:
        args.skip_build = args.skip_rate = args.skip_summary = args.skip_histogram = True
        args.skip_tweet_embeddings = args.skip_atlas_parquet = True
        args.skip_umap = args.skip_atlas = True
    if args.export_only:
        args.skip_build = args.skip_rate = args.skip_summary = args.skip_histogram = True
        args.skip_tweet_embeddings = args.skip_atlas_parquet = True
    if args.enrich_only:
        args.skip_build = args.skip_rate = True

    # Phase 1: Build
    if not args.skip_build:
        try:
            tweet_dict, conversation_trees = load_caches()
            quote_dict = get_quote_tweets_dict()
            phase_build_strands(tweet_dict, quote_dict, conversation_trees, force_rebuild=args.force)
        except Exception as e:
            errors.append(f"Phase 1 (Build): {e}")
            print(f"[ERROR] Phase 1 failed: {e}")

    # Phase 2: Rate
    if not args.skip_rate:
        try:
            phase_rate_strands(model_name=args.rating_model)
        except Exception as e:
            errors.append(f"Phase 2 (Rate): {e}")
            print(f"[ERROR] Phase 2 failed: {e}")

    # Phase 3: Summaries
    if not args.skip_summary:
        try:
            phase_generate_summaries(model_name=args.summary_model, force_regenerate=args.force)
        except Exception as e:
            errors.append(f"Phase 3 (Summary): {e}")
            print(f"[ERROR] Phase 3 failed: {e}")

    # Phase 4: Histograms
    if not args.skip_histogram:
        try:
            phase_generate_histograms(force_regenerate=args.force)
        except Exception as e:
            errors.append(f"Phase 4 (Histogram): {e}")
            print(f"[ERROR] Phase 4 failed: {e}")

    # Phase 4.5: Tweet Embeddings (per-tweet for atlas)
    if not args.skip_tweet_embeddings:
        try:
            phase_generate_tweet_embeddings(force_regenerate=args.force)
        except Exception as e:
            errors.append(f"Phase 4.5 (Tweet Embeddings): {e}")
            print(f"[ERROR] Phase 4.5 failed: {e}")

    # Phase 4.6: Atlas Parquet (UMAP on tweet embeddings)
    if not args.skip_atlas_parquet:
        try:
            phase_generate_atlas_parquet(force_regenerate=args.force)
        except Exception as e:
            errors.append(f"Phase 4.6 (Atlas Parquet): {e}")
            print(f"[ERROR] Phase 4.6 failed: {e}")

    if not args.bangers_only:
        # Phase 5: Export strands data (combined JSON with seed tweets)
        try:
            if not phase_export_strands_data():
                errors.append("Phase 5 (Export Strands Data): Failed")
        except Exception as e:
            errors.append(f"Phase 5 (Export Strands Data): {e}")
            print(f"[ERROR] Phase 5 failed: {e}")

        # Phase 5a: Export histograms
        try:
            if not phase_export_histograms():
                errors.append("Phase 5a (Export Histograms): Missing histogram data")
        except Exception as e:
            errors.append(f"Phase 5a (Export Histograms): {e}")
            print(f"[ERROR] Phase 5a failed: {e}")

        # Phase 5b: Export UMAP
        if not args.skip_umap:
            try:
                if not phase_export_semantic_map():
                    errors.append("Phase 5b (Export UMAP): Missing summary data")
            except Exception as e:
                errors.append(f"Phase 5b (Export UMAP): {e}")
                print(f"[ERROR] Phase 5b failed: {e}")

        # Phase 5c: Export Atlas
        if not args.skip_atlas:
            try:
                if not phase_export_atlas():
                    print("[WARN] Phase 5c: Atlas parquet not available, skipping")
            except Exception as e:
                errors.append(f"Phase 5c (Export Atlas): {e}")
                print(f"[ERROR] Phase 5c failed: {e}")

        # Phase 6: Generate Seriation Order
        try:
            if not phase_generate_seriation():
                print("[WARN] Phase 6: Could not generate seriation order")
        except Exception as e:
            errors.append(f"Phase 6 (Seriation): {e}")
            print(f"[ERROR] Phase 6 failed: {e}")

        # Phase 7: Generate Chronological Summary
        try:
            if not phase_generate_chronological_summary():
                print("[WARN] Phase 7: Could not generate chronological summary")
        except Exception as e:
            errors.append(f"Phase 7 (Chronological Summary): {e}")
            print(f"[ERROR] Phase 7 failed: {e}")

    # Phase 8: Generate Bangers Data
    if not args.skip_bangers:
        try:
            phase_generate_bangers_data(parquet_path=args.parquet)
        except Exception as e:
            errors.append(f"Phase 8 (Bangers Data): {e}")
            print(f"[ERROR] Phase 8 failed: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"Finished: {datetime.now().isoformat()}")
    print("=" * 60)

    if errors:
        print(f"\n[ERRORS] {len(errors)} phase(s) had errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\nAll phases completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
