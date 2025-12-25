# %%
"""
Generate atlas_data.json for the detailed strand atlas visualization.

This script:
1. Loads the UMAP-projected tweet embeddings from parquet
2. Loads rated strands for metadata (essential tweets, summaries, etc.)
3. Loads tweet_dict.diskcache for proper usernames
4. Outputs atlas_data.json for the frontend

Usage:
    python 22_generate_atlas_data.py
"""

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from diskcache import Cache
from tqdm import tqdm

# Paths
SCRATCHPADS_DIR = Path(__file__).parent
DATA_DIR = SCRATCHPADS_DIR / "data"
RATED_DIR = DATA_DIR / "rated_strands"
PARQUET_PATH = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_DICT_PATH = SCRATCHPADS_DIR / "tweet_dict.diskcache"
OUTPUT_PATH = SCRATCHPADS_DIR.parent / "top-qt-website/bangers/public/atlas_data.json"

# %%
# Load tweet_dict for username lookups
print(f"Loading tweet_dict from {TWEET_DICT_PATH}...")
tweet_dict = Cache(str(TWEET_DICT_PATH))
print(f"Loaded {len(tweet_dict)} tweets")

# %%
# Load UMAP-projected embeddings
print(f"Loading UMAP projections from {PARQUET_PATH}...")
df = pd.read_parquet(PARQUET_PATH)
print(f"Loaded {len(df)} tweets with projections")
print(f"Columns: {df.columns.tolist()}")

# %%
# Load all rated strands for metadata
print(f"Loading rated strands from {RATED_DIR}...")
strand_files = sorted(RATED_DIR.glob("*.json"))
print(f"Found {len(strand_files)} strand files")

strands_meta = {}  # strand_id -> {title, summary, label, essential_tweets: {tweet_id: annotation}}

for filepath in tqdm(strand_files, desc="Loading strands"):
    with open(filepath) as f:
        text = f.read()
        # Fix large integers that might lose precision
        text = re.sub(r'"tweet_id":\s*(\d+)', r'"tweet_id": "\1"', text)
        text = re.sub(r'"seed_tweet_id":\s*(\d+)', r'"seed_tweet_id": "\1"', text)
        data = json.loads(text)

    strand_id = str(data['seed_tweet_id'])

    # Get essential tweets with their annotations
    essential_tweets = {}
    if 'rating' in data and 'essential_tweets' in data['rating']:
        for et in data['rating']['essential_tweets']:
            tweet_id = str(et.get('tweet_id', ''))
            annotation = et.get('annotation', '')
            if tweet_id:
                essential_tweets[tweet_id] = annotation

    # Get root tweet info from tweet_dict
    root_tweet = tweet_dict.get(int(strand_id))
    root_username = root_tweet.get('username', 'unknown') if root_tweet else 'unknown'

    strands_meta[strand_id] = {
        'title': data.get('title', 'Untitled'),
        'summary': data.get('summary', ''),
        'label': data.get('label', data.get('title', '')[:30]),
        'username': root_username,
        'essential_tweets': essential_tweets,
        'rating': data.get('rating', {}).get('rating', 5),
    }

print(f"Loaded metadata for {len(strands_meta)} strands")

# %%
# Helper to get username from tweet_dict
def get_username(tweet_id: str) -> str:
    """Look up username from tweet_dict.diskcache"""
    try:
        tweet = tweet_dict.get(int(tweet_id))
        if tweet:
            return tweet.get('username', 'unknown')
    except (ValueError, TypeError):
        pass
    return 'unknown'

# %%
# Build the atlas data
print("Building atlas data...")

tweets_data = []
for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing tweets"):
    tweet_id = str(row['tweet_id'])
    strand_id = str(row['strand_id'])

    # Get strand metadata
    strand_meta = strands_meta.get(strand_id, {})

    # Check if this is an essential tweet
    is_essential = row.get('is_essential', False) or row.get('tweet_type', '') in ['essential', 'root_essential']
    is_root = row.get('is_root', False) or row.get('tweet_type', '') in ['root_essential', 'root_regular']

    # Get the actual username from tweet_dict
    username = get_username(tweet_id)

    # Get annotation for essential tweets
    annotation = ''
    if is_essential and strand_meta:
        annotation = strand_meta.get('essential_tweets', {}).get(tweet_id, '')

    # Get likes/retweets
    likes = int(row.get('likes', 0)) if pd.notna(row.get('likes')) else 0
    retweets = int(row.get('retweets', 0)) if pd.notna(row.get('retweets')) else 0

    # Get tweet text (clean it up)
    text = str(row.get('text', ''))
    if text.startswith('Tweet:\n'):
        text = text[7:]

    tweets_data.append({
        'id': tweet_id,
        'sid': strand_id,
        'txt': text[:300],  # Truncate long texts
        'dt': str(row.get('date', ''))[:10] if pd.notna(row.get('date')) else '',
        'lk': likes,
        'rt': retweets,
        'x': round(float(row['projection_x']), 4),
        'y': round(float(row['projection_y']), 4),
        'e': 1 if is_essential else 0,
        'r': 1 if is_root else 0,
        'u': username,
        'a': annotation[:200] if annotation else '',  # Annotation for essential tweets
    })

print(f"Processed {len(tweets_data)} tweets")

# %%
# Build strand metadata for the frontend
print("Building strand metadata...")

# Get unique strand colors based on position (same logic as frontend)
import numpy as np

NAUSICAA_COLORS = [
    '#6b3fa0', '#8352b5', '#5e4fa2', '#3288bd', '#21a0a0',
    '#41b6ab', '#66c2a4', '#78c679', '#addd8e', '#f4a742',
    '#d94f6b', '#b5456e', '#8c4799',
]

# Calculate strand centers and colors
strand_tweets = {}
for t in tweets_data:
    sid = t['sid']
    if sid not in strand_tweets:
        strand_tweets[sid] = []
    strand_tweets[sid].append(t)

# Global center
all_x = [t['x'] for t in tweets_data]
all_y = [t['y'] for t in tweets_data]
center_x = np.mean(all_x)
center_y = np.mean(all_y)

strand_colors = {}
for strand_id, tweets in strand_tweets.items():
    # Use important tweets (essential/root) for center calculation
    important = [t for t in tweets if t['e'] or t['r']]
    to_use = important if important else tweets

    xs = [t['x'] for t in to_use]
    ys = [t['y'] for t in to_use]
    median_x = np.median(xs)
    median_y = np.median(ys)

    angle = np.arctan2(median_y - center_y, median_x - center_x)
    t = (angle + np.pi) / (2 * np.pi)
    idx = int(t * len(NAUSICAA_COLORS)) % len(NAUSICAA_COLORS)
    strand_colors[strand_id] = NAUSICAA_COLORS[idx]

# Build strands dict for frontend
strands_output = {}
for strand_id, meta in strands_meta.items():
    strands_output[strand_id] = {
        'title': meta['title'],
        'label': meta['label'][:40],
        'summary': meta['summary'][:500],
        'username': meta['username'],
        'color': strand_colors.get(strand_id, '#888888'),
        'score': meta.get('rating', 5),
    }

# Add color to each tweet
for t in tweets_data:
    t['c'] = strand_colors.get(t['sid'], '#888888')

# %%
# Output the atlas data
print(f"Writing to {OUTPUT_PATH}...")

output = {
    'tweets': tweets_data,
    'strands': strands_output,
    'palette': NAUSICAA_COLORS,
}

with open(OUTPUT_PATH, 'w') as f:
    json.dump(output, f)

file_size = OUTPUT_PATH.stat().st_size / (1024 * 1024)
print(f"Done! Wrote {len(tweets_data)} tweets to {OUTPUT_PATH} ({file_size:.1f} MB)")

# %%
# Summary stats
essential_count = sum(1 for t in tweets_data if t['e'])
root_count = sum(1 for t in tweets_data if t['r'])
with_annotation = sum(1 for t in tweets_data if t.get('a'))
with_username = sum(1 for t in tweets_data if t['u'] != 'unknown')

print(f"\nSummary:")
print(f"  Total tweets: {len(tweets_data)}")
print(f"  Essential tweets: {essential_count}")
print(f"  Root tweets: {root_count}")
print(f"  With annotations: {with_annotation}")
print(f"  With usernames: {with_username}/{len(tweets_data)} ({100*with_username/len(tweets_data):.1f}%)")
print(f"  Strands: {len(strands_output)}")
