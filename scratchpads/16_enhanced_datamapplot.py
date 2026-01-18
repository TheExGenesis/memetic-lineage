# %%
"""
Enhanced DataMapPlot visualization with:
- Each strand gets its own color
- Tweet styling based on type (normal/essential/root)
- Full tweet metadata in hover tooltips
- Strand ratings integrated
"""

import pandas as pd
import numpy as np
from pathlib import Path
import datamapplot
import json
from diskcache import Cache
from typing import Dict
import colorsys

# ===== PARAMETERS =====
LABEL_ONLY_ROOTS = True
OUTPUT_HTML = "tweet_datamapplot_enhanced.html"
PALETTE = 'vibrant'  # 'vibrant', 'pastel', 'deep', 'muted', 'neon', 'original'
# ===== END PARAMETERS =====

# Helper function for strand-based colors (from 13_dec19_interactive_plot.py)
def get_strand_colors(x, y, strand_ids, is_essential, is_root, palette='vibrant'):
    """
    Generate colors based on strand median positions
    Each strand gets one color based on the median position of its root/essential points
    """
    # Calculate center of mass (mean position of all points)
    center_x = x.mean()
    center_y = y.mean()

    # Palette configurations (lightness, saturation)
    palette_configs = {
        'vibrant': (0.50, 0.95),   # Bright and saturated
        'pastel': (0.75, 0.50),    # Light and soft
        'deep': (0.40, 0.90),      # Dark and rich
        'muted': (0.55, 0.50),     # Subdued
        'neon': (0.60, 1.0),       # Maximum saturation
        'original': (0.55, 0.70),  # Original values
    }

    lightness, saturation = palette_configs.get(palette, palette_configs['vibrant'])

    # Calculate median position for each strand using only root and essential tweets
    unique_strands = list(set(strand_ids))
    strand_colors_map = {}

    for strand_id in unique_strands:
        # Get all points in this strand
        strand_mask = np.array([sid == strand_id for sid in strand_ids])

        # Filter for only root and essential tweets in this strand
        important_mask = strand_mask & (is_essential | is_root)

        if important_mask.sum() > 0:
            # Use only root/essential tweets for color calculation
            strand_x = x[important_mask]
            strand_y = y[important_mask]
        else:
            # Fallback: if no root/essential tweets, use all tweets in strand
            strand_x = x[strand_mask]
            strand_y = y[strand_mask]

        # Calculate median position (less sensitive to outliers than mean)
        median_x = np.median(strand_x)
        median_y = np.median(strand_y)

        # Calculate angle from center for median position
        angle = np.arctan2(median_y - center_y, median_x - center_x)

        # Convert angle to hue (0-360)
        hue = ((angle + np.pi) / (2 * np.pi)) * 360

        # Convert to RGB using HSL
        r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
        strand_colors_map[strand_id] = f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

    return strand_colors_map

print("=" * 60)
print("ENHANCED DATAMAPPLOT VISUALIZATION")
print("=" * 60)

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
PARQUET_FILE = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_CACHE_DIR = SCRIPT_DIR / "tweet_dict.diskcache"
RATED_STRANDS_DIR = DATA_DIR / "rated_strands"
UMAP_TWEETS_JSON = SCRIPT_DIR.parent / "top-qt-website/bangers/public/umap_tweets.json"

# Load embedding data
print(f"\n[1/6] Loading embedding data from {PARQUET_FILE}")
data = pd.read_parquet(PARQUET_FILE)
print(f"  ✓ Loaded {len(data)} tweets across {data['strand_id'].nunique()} strands")

# Load strand titles from umap_tweets.json
print(f"\n[2/6] Loading strand titles from {UMAP_TWEETS_JSON}")
with open(UMAP_TWEETS_JSON, 'r') as f:
    umap_data = json.load(f)
    umap_tweets = umap_data.get('points', [])

# Create strand_id -> strand_title mapping
strand_titles = {}
for tweet_data in umap_tweets:
    strand_id = str(tweet_data['strand_id'])
    strand_title = tweet_data.get('strand_title', '')
    if strand_id and strand_title:
        strand_titles[strand_id] = strand_title

print(f"  ✓ Loaded {len(strand_titles)} strand titles")

# Load tweet metadata from disk cache
print(f"\n[3/6] Loading tweet metadata from {TWEET_CACHE_DIR}")
tweet_cache = Cache(str(TWEET_CACHE_DIR))

# Try to find correct key format
sample_tweet_id = str(data.iloc[0]['tweet_id'])
cached_tweet = tweet_cache.get(sample_tweet_id)
if not cached_tweet:
    # Try as int
    cached_tweet = tweet_cache.get(int(sample_tweet_id))
    if cached_tweet:
        print(f"  ℹ Using integer keys for cache lookups")
        USE_INT_KEYS = True
    else:
        print(f"  ⚠ Warning: Could not find tweets in cache (tried both str and int keys)")
        USE_INT_KEYS = None
else:
    print(f"  ℹ Using string keys for cache lookups")
    USE_INT_KEYS = False

# Load strand ratings
print(f"\n[4/6] Loading strand ratings from {RATED_STRANDS_DIR}")
strand_ratings: Dict[str, float] = {}
strand_data_full: Dict[str, dict] = {}

if RATED_STRANDS_DIR.exists():
    for strand_file in RATED_STRANDS_DIR.glob("*.json"):
        try:
            with open(strand_file, 'r') as f:
                strand_json = json.load(f)
                seed_id = str(strand_json.get('seed_tweet_id', ''))

                # Extract numeric rating (it's nested in a dict)
                rating_obj = strand_json.get('rating', {})
                if isinstance(rating_obj, dict):
                    rating = float(rating_obj.get('rating', 0))
                else:
                    rating = float(rating_obj) if rating_obj else 0

                if seed_id and rating:
                    strand_ratings[seed_id] = rating
                    strand_data_full[seed_id] = strand_json
        except Exception as e:
            continue

print(f"  ✓ Loaded {len(strand_ratings)} strand ratings")

# Build comprehensive tweet data
print(f"\n[5/6] Building visualization data...")

# Extract coordinates
coords = data[['projection_x', 'projection_y']].values

# Build labels using strand titles
labels_for_display = []
for idx, row in data.iterrows():
    strand_id = str(row['strand_id'])
    # Use strand_title from umap_tweets.json
    strand_title = strand_titles.get(strand_id, f"Strand {strand_id}")
    labels_for_display.append(strand_title)

labels_for_display = np.array(labels_for_display)

# Build marker sizes based on tweet type
# MUCH BIGGER sizes, emphasizing roots over essentials
marker_sizes = np.zeros(len(data))
for idx, row in data.iterrows():
    if row['is_root']:
        marker_sizes[idx] = 20  # Large for roots
    elif row['is_essential']:
        marker_sizes[idx] = 14  # Medium-large for essential
    else:
        marker_sizes[idx] = 5   # Small for normal

# Build marker alpha (opacity) based on tweet type
# Root and essential: same high opacity
# Normal: 30% opacity (low)
marker_alphas = np.zeros(len(data))
for idx, row in data.iterrows():
    if row['is_root'] or row['is_essential']:
        marker_alphas[idx] = 1.0  # Full opacity for roots AND essential
    else:
        marker_alphas[idx] = 0.3  # 30% opacity for normal tweets

# Build rich hover tooltips
hover_data = []
tweets_with_metadata = 0
tweets_without_metadata = 0

for idx, row in data.iterrows():
    tweet_id = str(row['tweet_id'])

    # Try to get full tweet data from cache
    cached_tweet = None
    if USE_INT_KEYS is not None:
        if USE_INT_KEYS:
            cached_tweet = tweet_cache.get(int(tweet_id))
        else:
            cached_tweet = tweet_cache.get(tweet_id)

    # Extract tweet data
    if cached_tweet:
        tweets_with_metadata += 1
        # Username is at top level, not nested in 'user'
        username = cached_tweet.get('username', 'unknown')
        full_text = cached_tweet.get('full_text', row.get('text', ''))
        likes = cached_tweet.get('favorite_count', row.get('likes', 0))
        retweets = cached_tweet.get('retweet_count', row.get('retweets', 0))
        created_at = cached_tweet.get('created_at', row.get('date', ''))
    else:
        tweets_without_metadata += 1
        # Fallback to parquet data
        annotation = str(row.get('annotation', ''))
        if ':' in annotation:
            username = annotation.split(':')[0].strip('@')
        else:
            username = 'unknown'
        full_text = row.get('text', '')
        likes = int(row.get('likes', 0)) if pd.notnull(row.get('likes')) else 0
        retweets = int(row.get('retweets', 0)) if pd.notnull(row.get('retweets')) else 0
        created_at = str(row.get('date', ''))[:10] if pd.notnull(row.get('date')) else ''

    # Get strand info
    strand_id_str = str(row['strand_id'])
    strand_rating = strand_ratings.get(strand_id_str, 0)

    # Determine tweet type prefix
    if row['is_root']:
        type_prefix = '[ROOT] '
    elif row['is_essential']:
        type_prefix = '[ESSENTIAL] '
    else:
        type_prefix = ''

    # Format date
    date_str = created_at[:10] if created_at else 'Unknown'

    # Truncate text for hover (first 150 chars)
    text_preview = full_text[:150] + ('...' if len(full_text) > 150 else '')

    # Build plain text hover tooltip
    hover = f"{type_prefix}@{username} • {date_str}\n\n{text_preview}\n\n❤️ {likes:,}  🔄 {retweets:,}  Strand: {strand_id_str}"
    if strand_rating > 0:
        hover += f"  ⭐ {strand_rating}/10"

    hover_data.append(hover)

    # Progress indicator
    if (idx + 1) % 5000 == 0:
        print(f"  Processed {idx + 1}/{len(data)} tweets...")

print(f"\n  Stats:")
print(f"    • Tweets with full metadata: {tweets_with_metadata}")
print(f"    • Tweets with fallback data: {tweets_without_metadata}")
print(f"    • Regular tweets: {len(data[~data['is_essential'] & ~data['is_root']])}")
print(f"    • Essential tweets: {len(data[data['is_essential'] & ~data['is_root']])}")
print(f"    • Root tweets: {len(data[data['is_root']])}")

# Generate color palette for strands using datamapplot-style coloring
print(f"\n[6/6] Creating interactive plot with datamapplot...")
print(f"  Generating strand colors with '{PALETTE}' palette...")

# Extract numpy arrays for color generation
x = data['projection_x'].values
y = data['projection_y'].values
strand_ids = data['strand_id'].tolist()
is_essential = data['is_essential'].values
is_root = data['is_root'].values

# Generate strand colors using the datamapplot-style function
strand_colors = get_strand_colors(x, y, strand_ids, is_essential, is_root, palette=PALETTE)

# Create label_color_map: map display labels (strand titles) to strand colors
label_color_map = {}
for idx, row in data.iterrows():
    display_label = labels_for_display[idx]
    strand_id = row['strand_id']
    strand_color = strand_colors[strand_id]

    # Map this display label to the strand's color
    if display_label not in label_color_map:
        label_color_map[display_label] = strand_color

print(f"  ✓ Generated {len(strand_colors)} strand colors")
print(f"  ✓ Mapped {len(label_color_map)} unique strand titles to colors")

# Use datamapplot to create the visualization
# Pass labels_for_display (tweet text) for cluster labels
# Pass label_color_map to ensure same-strand tweets have same color
try:
    fig = datamapplot.create_interactive_plot(
        coords,
        labels_for_display,  # Display tweet text as labels
        hover_text=hover_data,
        marker_size_array=marker_sizes,
        marker_alpha_array=marker_alphas,
        label_color_map=label_color_map,  # Map text labels to strand colors
        height=900,
        width="100%",
        color_label_text=True,  # Color the label text
    )

    output_path = SCRIPT_DIR / OUTPUT_HTML
    fig.save(str(output_path))

    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"\n📊 Interactive plot saved to:")
    print(f"   {output_path}")
    print(f"\n🎨 Visualization Features:")
    print(f"   • {data['strand_id'].nunique()} strands, each with unique color ({PALETTE} palette)")
    print(f"   • Cluster labels show strand titles from umap_tweets.json")
    print(f"   • Root tweets: LARGE (20px), 100% opacity, same color as essential")
    print(f"   • Essential tweets: Medium-large (14px), 100% opacity, same color as root")
    print(f"   • Regular tweets: Small (5px), 30% opacity (low)")
    print(f"   • Plain text hover tooltips with @username, text, likes, date, strand ID")
    print(f"   • Colors based on strand median position (datamapplot-style)")
    print(f"   • Usernames loaded from tweet_dict.diskcache")
    print(f"\n💡 Tips:")
    print(f"   • Zoom in to see individual tweets clearly")
    print(f"   • Hover over points for detailed tweet information")
    print(f"   • Larger points are root/essential tweets (much more prominent)")
    print(f"   • Regular tweets have low opacity for visual de-emphasis")
    print(f"   • Each color represents a different strand/conversation")
    print(f"   • Cluster labels show human-readable strand titles")
    print(f"\n{'='*60}")

except Exception as e:
    print(f"\n❌ Error creating plot: {e}")
    import traceback
    traceback.print_exc()

# %%
