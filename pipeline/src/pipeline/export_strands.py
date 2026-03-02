"""Phase 5: Export strands data, histograms, semantic map, and atlas to frontend."""

import colorsys
import json
import re
from datetime import datetime

import numpy as np

from pipeline.config import (
    ATLAS_EXPORT_PATH, ATLAS_PARQUET_PATH, EMBEDDINGS_CACHE_PATH,
    FRONTEND_PUBLIC_DIR, HISTOGRAM_EXPORT_PATH, LABEL_CONFIG_PATH,
    SEMANTIC_MAP_EXPORT_PATH, STRANDS_DATA_EXPORT_PATH,
)
from pipeline.helpers import load_all_rated_strands
from pipeline.lib.histogram import generate_histogram_export
from pipeline.lib.strand_caches import load_caches


def run_strands_data() -> bool:
    """Export all strands with seed tweets to a single static JSON."""
    print("\n" + "=" * 60)
    print("PHASE 5: Export Strands Data")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    tweet_dict, _ = load_caches()

    print(f"Loaded {len(all_strands)} rated strands")

    strands_with_tweets = []
    for strand_id, data in all_strands.items():
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


def run_histograms() -> bool:
    """Export histogram data to frontend."""
    print("\n" + "=" * 60)
    print("PHASE 5a: Export Histograms")
    print("=" * 60)

    all_strands = load_all_rated_strands()

    missing = [sid for sid, data in all_strands.items() if not data.get("histogram")]
    if missing:
        print(f"[ERROR] {len(missing)} strands missing histograms!")
        print(f"  First few: {missing[:5]}")
        return False

    export_data = generate_histogram_export({str(k): v for k, v in all_strands.items()})

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTOGRAM_EXPORT_PATH, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(all_strands)} strand histograms to {HISTOGRAM_EXPORT_PATH}")
    return True


def run_semantic_map() -> bool:
    """Export UMAP semantic map to frontend."""
    import os
    import requests
    import umap

    print("\n" + "=" * 60)
    print("PHASE 5b: Export Semantic Map (UMAP)")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    tweet_dict, _ = load_caches()

    missing = [sid for sid, data in all_strands.items() if not data.get("summary")]
    if missing:
        print(f"[ERROR] {len(missing)} strands missing summaries!")
        return False

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

    missing_indices = [i for i, e in enumerate(embeddings) if e is None]

    if missing_indices:
        print(f"Generating {len(missing_indices)} new embeddings...")
        texts = [strands_list[i].get('summary', '') for i in missing_indices]

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


def run_atlas() -> bool:
    """Export detailed atlas data (tweet-level UMAP) to frontend."""
    import pandas as pd
    from tqdm import tqdm

    print("\n" + "=" * 60)
    print("PHASE 5c: Export Atlas Data")
    print("=" * 60)

    if not ATLAS_PARQUET_PATH.exists():
        print(f"[WARN] Atlas parquet not found at {ATLAS_PARQUET_PATH}")
        print("  Run pipeline without --skip-tweet-embeddings and --skip-atlas-parquet to generate it.")
        return False

    print(f"Loading UMAP projections from {ATLAS_PARQUET_PATH}...")
    df = pd.read_parquet(ATLAS_PARQUET_PATH)
    print(f"Loaded {len(df)} tweets with projections")

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands for metadata")

    tweet_dict, _ = load_caches()

    # Build strand metadata
    strands_meta = {}
    for strand_id, data in all_strands.items():
        strand_id_str = str(strand_id)

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

    for t in tweets_data:
        t['c'] = strand_colors.get(t['sid'], '#888888')

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
