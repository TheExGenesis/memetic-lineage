"""
Export comprehensive tweet embedding data for web visualization
Combines embeddings, full tweet metadata, and strand ratings into a single JSON
"""

import pandas as pd
import json
from pathlib import Path
from diskcache import Cache
from typing import Dict, Any
import sys

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
PARQUET_FILE = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_CACHE_DIR = SCRIPT_DIR / "tweet_dict.diskcache"
RATED_STRANDS_DIR = DATA_DIR / "rated_strands"
OUTPUT_DIR = SCRIPT_DIR.parent / "top-qt-website/bangers/public/data"

print(f"Loading embedding data from {PARQUET_FILE}")
df = pd.read_parquet(PARQUET_FILE)
print(f"Loaded {len(df)} tweets across {df['strand_id'].nunique()} strands")

# Load tweet metadata from disk cache
print(f"\nLoading tweet metadata from {TWEET_CACHE_DIR}")
tweet_cache = Cache(str(TWEET_CACHE_DIR))
print(f"Tweet cache has {len(tweet_cache)} entries")

# Load strand ratings
print(f"\nLoading strand ratings from {RATED_STRANDS_DIR}")
strand_ratings: Dict[str, float] = {}
strand_names: Dict[str, str] = {}

if RATED_STRANDS_DIR.exists():
    for strand_file in RATED_STRANDS_DIR.glob("*.json"):
        try:
            with open(strand_file, 'r') as f:
                strand_data = json.load(f)
                seed_id = str(strand_data.get('seed_tweet_id', ''))

                # Try to get rating (might be in different formats)
                rating = None
                if 'rating' in strand_data:
                    rating = float(strand_data['rating'])
                elif 'overall_rating' in strand_data:
                    rating = float(strand_data['overall_rating'])

                # Get strand name (file name without .json)
                name = strand_file.stem

                if seed_id and rating is not None:
                    strand_ratings[seed_id] = rating
                    strand_names[seed_id] = name
        except Exception as e:
            print(f"Warning: Failed to load {strand_file.name}: {e}")
            continue

print(f"Loaded {len(strand_ratings)} strand ratings")

# Build comprehensive tweet data
print("\nBuilding comprehensive tweet data...")
tweet_data = {
    'x': [],
    'y': [],
    'tweet_id': [],
    'strand_id': [],
    'is_essential': [],
    'is_root': [],
    'username': [],
    'full_text': [],
    'avatar_url': [],
    'created_at': [],
    'likes': [],
    'retweets': [],
    'strand_rating': [],
    'strand_name': [],
}

tweets_with_metadata = 0
tweets_without_metadata = 0

for idx, row in df.iterrows():
    tweet_id = str(row['tweet_id'])

    # Try to get full tweet data from cache
    cached_tweet = tweet_cache.get(tweet_id)

    if cached_tweet:
        tweets_with_metadata += 1
        username = cached_tweet.get('user', {}).get('screen_name', 'unknown')
        full_text = cached_tweet.get('full_text', row.get('text', ''))
        avatar_url = cached_tweet.get('user', {}).get('profile_image_url_https', '')
        created_at = cached_tweet.get('created_at', row.get('date', ''))
        likes = cached_tweet.get('favorite_count', row.get('likes', 0))
        retweets = cached_tweet.get('retweet_count', row.get('retweets', 0))
    else:
        tweets_without_metadata += 1
        # Fallback to parquet data or defaults
        # The annotation field sometimes contains username info
        annotation = str(row.get('annotation', ''))
        if ':' in annotation:
            username = annotation.split(':')[0].strip('@')
        else:
            username = 'unknown'

        full_text = row.get('text', '')
        avatar_url = ''
        created_at = str(row.get('date', ''))
        likes = int(row.get('likes', 0)) if pd.notnull(row.get('likes')) else 0
        retweets = int(row.get('retweets', 0)) if pd.notnull(row.get('retweets')) else 0

    # Get strand info
    strand_id_str = str(row['strand_id'])
    strand_rating = strand_ratings.get(strand_id_str, 0.0)
    strand_name = strand_names.get(strand_id_str, '')

    # Add to arrays
    tweet_data['x'].append(float(row['projection_x']))
    tweet_data['y'].append(float(row['projection_y']))
    tweet_data['tweet_id'].append(tweet_id)
    tweet_data['strand_id'].append(strand_id_str)
    tweet_data['is_essential'].append(bool(row['is_essential']))
    tweet_data['is_root'].append(bool(row['is_root']))
    tweet_data['username'].append(username)
    tweet_data['full_text'].append(full_text)
    tweet_data['avatar_url'].append(avatar_url)
    tweet_data['created_at'].append(created_at)
    tweet_data['likes'].append(int(likes))
    tweet_data['retweets'].append(int(retweets))
    tweet_data['strand_rating'].append(float(strand_rating))
    tweet_data['strand_name'].append(strand_name)

    # Progress indicator
    if (idx + 1) % 5000 == 0:
        print(f"  Processed {idx + 1}/{len(df)} tweets...")

print(f"\nMetadata stats:")
print(f"  Tweets with full metadata: {tweets_with_metadata}")
print(f"  Tweets with fallback data: {tweets_without_metadata}")

# Build strand summary
print("\nBuilding strand summary...")
strand_summary = {}
for strand_id in df['strand_id'].unique():
    strand_id_str = str(strand_id)
    strand_tweets = df[df['strand_id'] == strand_id]

    strand_summary[strand_id_str] = {
        'id': strand_id_str,
        'name': strand_names.get(strand_id_str, ''),
        'rating': float(strand_ratings.get(strand_id_str, 0.0)),
        'tweet_count': int(len(strand_tweets)),
        'root_count': int(strand_tweets['is_root'].sum()),
        'essential_count': int(strand_tweets['is_essential'].sum()),
    }

# Save to JSON
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

tweet_data_file = OUTPUT_DIR / "tweet_embeddings_full.json"
print(f"\nSaving tweet data to {tweet_data_file}")
with open(tweet_data_file, 'w') as f:
    json.dump(tweet_data, f)

file_size_mb = tweet_data_file.stat().st_size / (1024 * 1024)
print(f"  Saved {len(tweet_data['x'])} tweets ({file_size_mb:.1f} MB)")

strand_summary_file = OUTPUT_DIR / "strand_summary.json"
print(f"\nSaving strand summary to {strand_summary_file}")
with open(strand_summary_file, 'w') as f:
    json.dump(strand_summary, f, indent=2)

strand_summary_size_kb = strand_summary_file.stat().st_size / 1024
print(f"  Saved {len(strand_summary)} strands ({strand_summary_size_kb:.1f} KB)")

print("\n✅ Export complete!")
print("\nNext steps:")
print("1. Update embeddingDataLoader.ts to load tweet_embeddings_full.json")
print("2. Extend EmbeddingData interface with new fields")
print("3. Update PlotlyEditor to use strand-based coloring")
