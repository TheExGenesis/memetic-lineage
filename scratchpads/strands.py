#!/usr/bin/env python3
"""
Unified Strand Processing Pipeline

Combines all strand processing steps into a single script:
1. Build strands from top quoted tweets
2. Rate strands with LLM
3. Generate summaries (title + summary)
4. Generate histograms (tweet distribution over time)
5. Export to frontend (histograms + semantic map)

Usage:
    python strands.py                    # Run full pipeline
    python strands.py --skip-build       # Skip building (use existing strands/)
    python strands.py --skip-rate        # Skip rating (use existing rated_strands/)
    python strands.py --skip-umap        # Skip UMAP (expensive, not always needed)
    python strands.py --enrich-only      # Only add summaries/histograms to existing rated strands
    python strands.py --export-only      # Only export to frontend
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Set

from dotenv import load_dotenv
from pandas import read_parquet

# Local imports
from lib.strand_caches import get_quote_tweets_dict, load_caches
from lib.strand_builder import build_strands_phased
from lib.strand_rater import rate_strands_batch
from lib.image_describer import get_image_cache
from lib.histogram import generate_histogram, generate_histogram_export
from lib.parallel import parallel_map_to_dict

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

# Frontend export paths
FRONTEND_PUBLIC_DIR = Path(__file__).parent.parent / "top-qt-website" / "bangers" / "public"
ATLAS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "atlas_data.json"
HISTOGRAM_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_histograms.json"
SEMANTIC_MAP_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_semantic_map.json"
SERIATION_ORDER_PATH = FRONTEND_PUBLIC_DIR / "strand_seriation_order.json"


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
    max_workers: int = 2
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
    max_workers: int = 3,
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
# Phase 5: Export to Frontend
# =============================================================================

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
        print("  Run 11_embedding_atlas.py to generate tweet-level embeddings first.")
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
    parser.add_argument("--enrich-only", action="store_true", help="Only add summaries/histograms")
    parser.add_argument("--export-only", action="store_true", help="Only export to frontend")
    parser.add_argument("--force", action="store_true", help="Force regenerate all")
    parser.add_argument("--rating-model", default="anthropic/claude-sonnet-4.5", help="Model for rating")
    parser.add_argument("--summary-model", default="openai/gpt-4o-mini", help="Model for summaries")
    args = parser.parse_args()

    print("=" * 60)
    print("STRAND PROCESSING PIPELINE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    errors = []

    # Shortcut modes
    if args.export_only:
        args.skip_build = args.skip_rate = args.skip_summary = args.skip_histogram = True
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
