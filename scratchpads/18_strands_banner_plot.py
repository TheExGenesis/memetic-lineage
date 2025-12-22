# %%
"""
Banner plot for strands page - 1:2 horizontal aspect ratio
Shows only root tweets with top 10 labeled
"""

import numpy as np
import plotly.graph_objects as go
from pathlib import Path
import colorsys
import pandas as pd

# ===== TUNABLE PARAMETERS =====
PALETTE = 'neon'
BANNER_WIDTH = 1200
BANNER_HEIGHT = 600  # 1:2 aspect ratio (height:width)

# Number of top tweets to label
TOP_N_LABELS = 10

# ===== END PARAMETERS =====

# Load embedding data
data_path = Path(__file__).parent / "data/tweet_embeddings_atlas.parquet"
print(f"Loading data from {data_path}")
data = pd.read_parquet(data_path)
print(f"Loaded {len(data)} total points")
# %%
# Filter to only root tweets
root_data = data[data['is_root'] == True].copy()
print(f"Root tweets: {len(root_data)}")

# %%
from lib.strand_caches import load_caches

tweet_dict, _ = load_caches()
"""e.g.
{'tweet_id': 967114911401652225,
 'account_id': 1584642529,
 'username': 'eigenrobot',
 'account_display_name': 'eigenrobot',
 'created_at': '2018-02-23 19:12:17+00',
 'full_text': "everything 👏  is 👏  monocausal 👏 and 👏 specifically 👏 results 👏 from 👏 whatever 👏 shit 👏 I'm 👏 on 👏 about 👏 at 👏 any 👏 given 👏 time",
 'retweet_count': 2028,
 'favorite_count': 8873,
 'reply_to_tweet_id': None,
 'reply_to_user_id': None,
 'reply_to_username': None,
 'quoted_tweet_id': None,
 'conversation_id': 967114911401652225,
 'avatar_media_url': 'https://pbs.twimg.com/profile_images/1721210613869740032/YWD1qX3H_normal.jpg',
 'archive_upload_id': 225}

"""
# %%
# Extract data
x = np.array(root_data['projection_x'])
y = np.array(root_data['projection_y'])
strand_ids = root_data['strand_id']
likes = root_data['likes'].fillna(0)

# Enrich root_data with tweet_dict info
def get_tweet_info(row):
    """Get username and full_text from tweet_dict"""
    tweet_id = int(row['tweet_id'])  # Convert to int for lookup
    if tweet_id in tweet_dict:
        tweet = tweet_dict[tweet_id]
        return pd.Series({
            'username': tweet.get('username', 'unknown'),
            'full_text': tweet.get('full_text', row['text']),
        })
    return pd.Series({
        'username': 'unknown',
        'full_text': row['text'],
    })

tweet_info = root_data.apply(get_tweet_info, axis=1)
root_data['username'] = tweet_info['username']
root_data['full_text'] = tweet_info['full_text']

# %%
def select_spatially_distributed_labels(root_data, x, y, likes, n_labels, grid_cols=5):
    """
    Select labels that are spread out in 2D space.
    Divides space into grid cells, picks highest-scoring tweet from each cell.
    """
    # Calculate grid dimensions based on aspect ratio
    x_range = x.max() - x.min()
    y_range = y.max() - y.min()
    aspect = x_range / y_range if y_range > 0 else 1

    # More columns for wider aspect ratio
    grid_rows = max(2, int(grid_cols / aspect))

    # Create grid cell assignments
    x_bins = np.linspace(x.min(), x.max() + 0.001, grid_cols + 1)
    y_bins = np.linspace(y.min(), y.max() + 0.001, grid_rows + 1)

    x_cell = np.digitize(x, x_bins) - 1
    y_cell = np.digitize(y, y_bins) - 1

    # For each cell, find the tweet with highest likes
    cell_best = {}  # (x_cell, y_cell) -> (index, likes)

    for i, idx in enumerate(root_data.index):
        cell = (x_cell[i], y_cell[i])
        tweet_likes = likes.iloc[i]

        if cell not in cell_best or tweet_likes > cell_best[cell][1]:
            cell_best[cell] = (idx, tweet_likes)

    # Sort cells by their best tweet's likes, take top n_labels
    sorted_cells = sorted(cell_best.items(), key=lambda x: x[1][1], reverse=True)
    selected_indices = [cell_best[cell][0] for cell, _ in sorted_cells[:n_labels]]

    return selected_indices

# Get spatially distributed top tweets
selected_indices = select_spatially_distributed_labels(
    root_data, x, y, likes, TOP_N_LABELS, grid_cols=5
)

print(f"Selected {len(selected_indices)} spatially distributed tweets:")
for idx in selected_indices:
    row = root_data.loc[idx]
    print(f"  - @{row['username']}: {int(row['likes'])} likes - {row['full_text'][:50]}...")

# Helper function for color generation
def get_strand_colors(x, y, strand_ids, palette='neon'):
    """Generate colors based on strand position"""
    center_x = x.mean()
    center_y = y.mean()

    palette_configs = {
        'vibrant': (0.50, 0.95),
        'pastel': (0.75, 0.50),
        'deep': (0.40, 0.90),
        'muted': (0.55, 0.50),
        'neon': (0.60, 1.0),
    }

    lightness, saturation = palette_configs.get(palette, palette_configs['neon'])

    unique_strands = list(set(strand_ids))
    strand_colors_map = {}

    for strand_id in unique_strands:
        strand_mask = np.array([sid == strand_id for sid in strand_ids])
        strand_x = x[strand_mask]
        strand_y = y[strand_mask]

        median_x = np.median(strand_x)
        median_y = np.median(strand_y)

        angle = np.arctan2(median_y - center_y, median_x - center_x)
        hue = ((angle + np.pi) / (2 * np.pi)) * 360

        r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
        strand_colors_map[strand_id] = f'rgb({int(r*255)},{int(g*255)},{int(b*255)})'

    colors = [strand_colors_map[sid] for sid in strand_ids]
    return colors

def format_label_text(username, text_str, max_words=6):
    """Format label: @username: first N words of tweet"""
    words = str(text_str).split()[:max_words]
    short_text = ' '.join(words)
    if len(words) == max_words and len(str(text_str).split()) > max_words:
        short_text += '...'
    return f"@{username}: {short_text}"

def format_hover_text(row):
    """Format hover text with tweet info"""
    username = row.get('username', 'Unknown')

    likes_val = int(row['likes']) if pd.notnull(row['likes']) else 0
    retweets_val = int(row['retweets']) if pd.notnull(row['retweets']) else 0

    hover = f"<b>@{username}</b><br>"
    hover += f"❤️ {likes_val} 🔄 {retweets_val}<br>"
    hover += "─" * 30 + "<br>"

    text = str(row.get('full_text', row['text']))
    if len(text) > 150:
        text = text[:150] + "..."
    hover += text.replace('\n', '<br>')

    return hover

# Generate colors
print(f"Generating colors with '{PALETTE}' palette...")
colors = get_strand_colors(x, y, strand_ids, palette=PALETTE)

# Generate hover text
hover_texts = root_data.apply(format_hover_text, axis=1).tolist()

# Create traces
traces = []

# All root tweets as scatter points
traces.append(go.Scattergl(
    x=x,
    y=y,
    mode='markers',
    name='Root Tweets',
    text=hover_texts,
    hoverinfo='text',
    marker=dict(
        size=12,
        symbol='diamond',
        color=colors,
        opacity=0.9,
        line=dict(color='white', width=1),
    ),
))

# Get positions for selected tweets
top_x = np.array(root_data.loc[selected_indices, 'projection_x'])
top_y = np.array(root_data.loc[selected_indices, 'projection_y'])

# Format labels with username and tweet text
top_labels = [
    format_label_text(
        root_data.loc[idx, 'username'],
        root_data.loc[idx, 'full_text']
    )
    for idx in selected_indices
]
top_colors = [colors[list(root_data.index).index(idx)] for idx in selected_indices]

# Calculate y offset for labels (percentage of y range)
y_range = y.max() - y.min()
label_y_offset = y_range * 0.04  # 4% of y range above point

# Add text labels offset above points
traces.append(go.Scattergl(
    x=top_x,
    y=top_y + label_y_offset,  # Offset labels above points
    mode='text',
    name='Labels',
    text=top_labels,
    textposition='top center',
    textfont=dict(
        size=9,
        color='#333',
        family='Arial, sans-serif',
    ),
    showlegend=False,
    hoverinfo='skip',
))

# Highlight markers for selected tweets (slightly larger)
traces.append(go.Scattergl(
    x=top_x,
    y=top_y,
    mode='markers',
    name='Labeled',
    hoverinfo='skip',
    marker=dict(
        size=16,
        symbol='diamond',
        color=top_colors,
        opacity=1.0,
        line=dict(color='black', width=2),
    ),
))

# Create figure
fig = go.Figure(data=traces)

# Update layout for 1:2 banner aspect ratio
fig.update_layout(
    title=dict(
        text='Strand Root Tweets',
        font=dict(size=18, color='#333'),
        y=0.98,
    ),
    xaxis=dict(
        showgrid=False,
        showticklabels=False,
        zeroline=False,
        scaleanchor='y',
        scaleratio=1,
    ),
    yaxis=dict(
        showgrid=False,
        showticklabels=False,
        zeroline=False,
    ),
    showlegend=False,
    paper_bgcolor='white',
    plot_bgcolor='white',
    dragmode='pan',
    hovermode='closest',
    width=BANNER_WIDTH,
    height=BANNER_HEIGHT,
    margin=dict(l=20, r=20, t=40, b=20),
)

# Config
config = {
    'scrollZoom': True,
    'displayModeBar': True,
}

print(f"\nPlot dimensions: {BANNER_WIDTH}x{BANNER_HEIGHT} (1:2 aspect ratio)")
print("Opening interactive plot...")
fig.show(config=config)

# %%
