# %%
"""
UMAP visualization of strand summaries
Embeds each strand's summary, projects to 2D, plots with titles as labels
"""

import json
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
import colorsys
import pandas as pd
import umap
import os
import requests
from dotenv import load_dotenv

# ===== TUNABLE PARAMETERS =====
PALETTE = 'nausicaa'  # Toxic Forest color scheme
BANNER_WIDTH = 1200
BANNER_HEIGHT = 400  # 1:3 aspect ratio

# Number of labels to show (spatially distributed)
TOP_N_LABELS = 12

# UMAP parameters
UMAP_N_NEIGHBORS = 10
UMAP_MIN_DIST = 0.1

# Font settings (match Bangers)
FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TITLE_COLOR = '#1a1a1a'
LABEL_COLOR = '#333333'

# ===== END PARAMETERS =====

# Load environment for OpenRouter
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
EMBEDDING_MODEL = "openai/text-embedding-3-small"

DATA_DIR = Path(__file__).parent / "data"
RATED_DIR = DATA_DIR / "rated_strands"

# %%
# Load tweet_dict for root tweet info
from lib.strand_caches import load_caches
tweet_dict, _ = load_caches()

# %%
# Load all rated strands
print("Loading rated strands...")
strand_files = sorted(RATED_DIR.glob("*.json"))
print(f"Found {len(strand_files)} strand files")

strands = []
for filepath in strand_files:
    with open(filepath) as f:
        data = json.load(f)

    seed_tweet_id = str(data['seed_tweet_id'])

    # Get root tweet info from tweet_dict
    tweet_info = tweet_dict.get(int(seed_tweet_id), {})

    # Count seeds and estimate tweets from thread_text
    seeds = data.get('seeds', [])
    thread_text = data.get('thread_text', '')
    # Rough tweet count from thread
    tweet_count = thread_text.count('[20')  # Matches date patterns like [2018-...

    strands.append({
        'seed_tweet_id': seed_tweet_id,
        'title': data.get('title', 'Untitled'),
        'summary': data.get('summary', ''),
        'rating': data.get('rating', {}),
        # Root tweet info
        'username': tweet_info.get('username', 'unknown'),
        'full_text': tweet_info.get('full_text', ''),
        'likes': tweet_info.get('favorite_count', 0),
        'retweets': tweet_info.get('retweet_count', 0),
        'created_at': tweet_info.get('created_at', ''),
        # Strand stats
        'seeds_count': len(seeds),
        'tweets_count': tweet_count,
    })

print(f"Loaded {len(strands)} strands")

# %%
# Check if we have cached embeddings
CACHE_PATH = DATA_DIR / "strand_summary_embeddings.json"

if CACHE_PATH.exists():
    print(f"Loading cached embeddings from {CACHE_PATH}")
    with open(CACHE_PATH) as f:
        cached = json.load(f)
    cache_lookup = {e['seed_tweet_id']: e['embedding'] for e in cached['embeddings']}
    embeddings = []
    for s in strands:
        if s['seed_tweet_id'] in cache_lookup:
            embeddings.append(cache_lookup[s['seed_tweet_id']])
        else:
            embeddings.append(None)
    missing = [i for i, e in enumerate(embeddings) if e is None]
else:
    print("No cached embeddings found, will generate all...")
    embeddings = [None] * len(strands)
    missing = list(range(len(strands)))

# %%
# Generate missing embeddings
def get_embeddings_batch(texts, batch_size=50):
    """Get embeddings via OpenRouter API"""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}...")
        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": batch}
        )
        response.raise_for_status()
        data = response.json()
        all_embeddings.extend([d['embedding'] for d in data['data']])
    return all_embeddings

if missing:
    print(f"Generating {len(missing)} embeddings...")
    texts_to_embed = [strands[i]['summary'] for i in missing]
    new_embeddings = get_embeddings_batch(texts_to_embed)
    for idx, emb in zip(missing, new_embeddings):
        embeddings[idx] = emb

    cache_data = {
        'model': EMBEDDING_MODEL,
        'embeddings': [
            {'seed_tweet_id': s['seed_tweet_id'], 'embedding': e}
            for s, e in zip(strands, embeddings)
        ]
    }
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache_data, f)
    print(f"Saved embeddings to {CACHE_PATH}")

print(f"Have {len(embeddings)} embeddings")

# %%
# Run UMAP
print("Running UMAP...")
X = np.array(embeddings)
print(f"Embedding matrix shape: {X.shape}")

reducer = umap.UMAP(
    n_components=2,
    n_neighbors=UMAP_N_NEIGHBORS,
    min_dist=UMAP_MIN_DIST,
    metric='cosine',
    random_state=42
)
embedding_2d = reducer.fit_transform(X)
print(f"UMAP output shape: {embedding_2d.shape}")

# Rescale coordinates to fit 1:3 aspect ratio (stretch x, squish y)
raw_x = embedding_2d[:, 0]
raw_y = embedding_2d[:, 1]

# Normalize to 0-1
x_norm = (raw_x - raw_x.min()) / (raw_x.max() - raw_x.min() + 1e-9)
y_norm = (raw_y - raw_y.min()) / (raw_y.max() - raw_y.min() + 1e-9)

# Scale to match aspect ratio (width:height = 3:1)
# Stretch x by 3x relative to y to maximize horizontal spread
aspect_ratio = BANNER_WIDTH / BANNER_HEIGHT  # 3.0
x = x_norm * aspect_ratio
y = y_norm

print(f"Rescaled to aspect ratio {aspect_ratio:.1f}:1")

# %%
# Create DataFrame
df = pd.DataFrame({
    'seed_tweet_id': [s['seed_tweet_id'] for s in strands],
    'title': [s['title'] for s in strands],
    'summary': [s['summary'] for s in strands],
    'username': [s['username'] for s in strands],
    'full_text': [s['full_text'] for s in strands],
    'likes': [s['likes'] for s in strands],
    'retweets': [s['retweets'] for s in strands],
    'seeds_count': [s['seeds_count'] for s in strands],
    'tweets_count': [s['tweets_count'] for s in strands],
    'x': x,
    'y': y,
})

def get_score(s):
    rating = s.get('rating', {})
    if isinstance(rating, dict):
        return rating.get('overall_score', 5)
    return 5

df['score'] = [get_score(s) for s in strands]
print(df[['title', 'username', 'likes']].head())

# %%
# Color generation - multiple palettes
def get_position_colors(x, y, palette='nausicaa'):
    """Generate colors based on position angle from center"""
    center_x = x.mean()
    center_y = y.mean()

    # Nausicaa Toxic Forest palette - radial gradient of Sea of Decay colors
    if palette == 'nausicaa':
        # Colors inspired by the Toxic Forest/Sea of Decay - MORE SATURATED
        # Rich purples -> vivid teals -> luminous greens -> glowing coral -> back to purple
        nausicaa_colors = [
            '#6b3fa0',  # rich purple (spore clouds)
            '#8352b5',  # bright violet
            '#5e4fa2',  # deep indigo
            '#3288bd',  # ocean blue
            '#21a0a0',  # vivid teal (toxic pools)
            '#41b6ab',  # bright cyan-teal
            '#66c2a4',  # seafoam
            '#78c679',  # luminous green (giant fungi)
            '#addd8e',  # bright lime (Ohmu glow)
            '#d4e34d',  # yellow-green (pollen)
            '#f4a742',  # golden amber
            '#e8704f',  # bright coral (decay)
            '#d94f6b',  # vivid pink-coral
            '#b5456e',  # magenta-rose
            '#8c4799',  # purple-magenta (back to start)
        ]

        colors = []
        for xi, yi in zip(x, y):
            angle = np.arctan2(yi - center_y, xi - center_x)
            # Map angle to color index
            t = (angle + np.pi) / (2 * np.pi)  # 0 to 1
            idx = int(t * len(nausicaa_colors)) % len(nausicaa_colors)
            colors.append(nausicaa_colors[idx])
        return colors

    # HSL-based palettes
    palette_configs = {
        'vibrant': (0.50, 0.85),
        'pastel': (0.70, 0.55),
        'deep': (0.40, 0.80),
        'muted': (0.55, 0.45),
        'neon': (0.55, 1.0),
    }

    lightness, saturation = palette_configs.get(palette, (0.50, 0.85))

    colors = []
    for xi, yi in zip(x, y):
        angle = np.arctan2(yi - center_y, xi - center_x)
        hue = ((angle + np.pi) / (2 * np.pi))
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        colors.append(f'rgb({int(r*255)},{int(g*255)},{int(b*255)})')

    return colors

# Spatial distribution for labels
def select_spatially_distributed_labels(df, n_labels, grid_cols=5):
    """Select labels spread out in 2D space, preferring higher scores"""
    x = df['x'].values
    y = df['y'].values
    scores = df['likes'].values  # Use likes as score

    x_range = x.max() - x.min()
    y_range = y.max() - y.min()
    aspect = x_range / y_range if y_range > 0 else 1
    grid_rows = max(2, int(grid_cols / aspect))

    x_bins = np.linspace(x.min(), x.max() + 0.001, grid_cols + 1)
    y_bins = np.linspace(y.min(), y.max() + 0.001, grid_rows + 1)

    x_cell = np.digitize(x, x_bins) - 1
    y_cell = np.digitize(y, y_bins) - 1

    cell_best = {}
    for i in range(len(df)):
        cell = (x_cell[i], y_cell[i])
        score = scores[i]
        if cell not in cell_best or score > cell_best[cell][1]:
            cell_best[cell] = (i, score)

    sorted_cells = sorted(cell_best.items(), key=lambda c: c[1][1], reverse=True)
    selected_indices = [cell_best[cell][0] for cell, _ in sorted_cells[:n_labels]]

    return selected_indices

# %%
# Generate colors and select labels
print(f"Generating colors with '{PALETTE}' palette...")
colors = get_position_colors(x, y, palette=PALETTE)
df['color'] = colors

selected_indices = select_spatially_distributed_labels(df, TOP_N_LABELS, grid_cols=5)
print(f"Selected {len(selected_indices)} labels:")
for idx in selected_indices:
    row = df.iloc[idx]
    print(f"  - @{row['username']}: {row['title'][:40]}...")

# %%
# Helper: wrap text for hover
def wrap_text(text, width=50):
    """Insert <br> every ~width chars at word boundaries"""
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > width and current_line:
            lines.append(' '.join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1
    if current_line:
        lines.append(' '.join(current_line))
    return '<br>'.join(lines)

def format_hover_text(row):
    """Format hover: root tweet text + summary + metadata"""
    username = row['username']
    likes = int(row['likes']) if row['likes'] else 0
    retweets = int(row['retweets']) if row['retweets'] else 0
    seeds = int(row['seeds_count']) if row['seeds_count'] else 0
    tweets = int(row['tweets_count']) if row['tweets_count'] else 0

    # Title
    hover = f"<b>{row['title']}</b><br><br>"

    # Root tweet text (wrapped)
    text = row['full_text'] or ''
    if len(text) > 180:
        text = text[:180] + "..."
    hover += f"{wrap_text(text)}<br><br>"

    # Summary (first 280 chars)
    summary = row['summary'] or ''
    if len(summary) > 280:
        summary = summary[:280] + "..."
    hover += f"<span style='color:#444; font-style:italic'>{wrap_text(summary)}</span><br><br>"

    # Metadata line
    hover += f"<span style='color:#666'>@{username} · ❤️ {likes:,} · 🔄 {retweets:,}</span><br>"
    hover += f"<span style='color:#666'>{seeds} seeds · {tweets} tweets</span>"

    return hover

hover_texts = df.apply(format_hover_text, axis=1).tolist()

# %%
# Create plot
traces = []

# All strands as scatter points
traces.append(go.Scattergl(
    x=df['x'],
    y=df['y'],
    mode='markers',
    name='Strands',
    text=hover_texts,
    hoverinfo='text',
    marker=dict(
        size=12,
        symbol='circle',
        color=df['color'],
        opacity=0.85,
        line=dict(color='white', width=1),
    ),
))

# Highlight selected strands
selected_df = df.iloc[selected_indices]
traces.append(go.Scattergl(
    x=selected_df['x'],
    y=selected_df['y'],
    mode='markers',
    name='Labeled',
    hoverinfo='skip',
    marker=dict(
        size=14,
        symbol='circle',
        color=selected_df['color'].tolist(),
        opacity=1.0,
        line=dict(color='#1a1a1a', width=2),
    ),
))

fig = go.Figure(data=traces)

# Add labels as annotations (pixel offset stays constant on zoom)
for idx in selected_indices:
    row = df.iloc[idx]
    fig.add_annotation(
        x=row['x'],
        y=row['y'],
        text=row['title'],
        showarrow=False,
        yshift=18,  # Fixed pixel offset above point
        font=dict(
            size=10,
            color=LABEL_COLOR,
            family=FONT_FAMILY,
        ),
        bgcolor='rgba(255,255,255,0.8)',
        borderpad=2,
    )

# Add padding to axes so labels have room
x_range = x.max() - x.min()
y_range = y.max() - y.min()
x_pad = x_range * 0.08
y_pad = y_range * 0.12  # More padding at top for labels

fig.update_layout(
    title=dict(
        text='Strand Semantic Map',
        font=dict(size=18, color=TITLE_COLOR, family=FONT_FAMILY),
        y=0.98,
        x=0.5,
        xanchor='center',
    ),
    xaxis=dict(
        showgrid=False,
        showticklabels=False,
        zeroline=False,
        range=[x.min() - x_pad, x.max() + x_pad],
    ),
    yaxis=dict(
        showgrid=False,
        showticklabels=False,
        zeroline=False,
        range=[y.min() - y_pad, y.max() + y_pad],
    ),
    showlegend=False,
    paper_bgcolor='#fafafa',
    plot_bgcolor='#fafafa',
    dragmode='pan',
    hovermode='closest',
    width=BANNER_WIDTH,
    height=BANNER_HEIGHT,
    margin=dict(l=30, r=30, t=50, b=30),
    font=dict(family=FONT_FAMILY),
    hoverlabel=dict(
        bgcolor='white',
        font_size=12,
        font_family=FONT_FAMILY,
    ),
)

config = {
    'scrollZoom': True,
    'displayModeBar': True,
}

print(f"\nPlot dimensions: {BANNER_WIDTH}x{BANNER_HEIGHT}")
print("Opening interactive plot...")
fig.show(config=config)

# %%
# Export data for frontend
def export_for_frontend():
    """Export UMAP positions and metadata to JSON for the web frontend"""
    export_data = {
        'width': BANNER_WIDTH,
        'height': BANNER_HEIGHT,
        'points': []
    }

    for i, row in df.iterrows():
        export_data['points'].append({
            'seed_tweet_id': row['seed_tweet_id'],
            'title': row['title'],
            'x': float(row['x']),
            'y': float(row['y']),
            'color': row['color'],
            'username': row['username'],
            'likes': int(row['likes']) if row['likes'] else 0,
            'retweets': int(row['retweets']) if row['retweets'] else 0,
            'seeds_count': int(row['seeds_count']) if row['seeds_count'] else 0,
            'tweets_count': int(row['tweets_count']) if row['tweets_count'] else 0,
            'full_text': (row['full_text'] or '')[:200],
            'summary': (row['summary'] or '')[:300],
        })

    # Also export which indices are labeled
    export_data['labeled_indices'] = selected_indices

    output_path = Path("../top-qt-website/bangers/public/strand_semantic_map.json")
    with open(output_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(export_data['points'])} strands to {output_path}")

export_for_frontend()

# %%
