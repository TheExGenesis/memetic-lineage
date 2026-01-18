# %%
"""
Interactive scatter plot of tweet embeddings
Matches the web visualization in best-strands
"""

import json
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
import colorsys
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import KernelDensity
import alphashape
from datetime import datetime
from scipy import ndimage
from skimage import measure

# ===== TUNABLE PARAMETERS =====
# Adjust these values and re-run to see different visualizations

# Color palette
PALETTE = 'neon'  # Options: 'vibrant', 'pastel', 'deep', 'muted', 'neon', 'original'

# Chronological edges between consecutive essential/root tweets
EDGE_DISTANCE_THRESHOLD = 1.0  # Max distance to connect consecutive tweets (higher = more edges)
SHOW_EDGES = True  # Set to False to disable edges

# Envelopes around tweet clusters
ENVELOPE_TYPE = 'alpha'  # Options: 'alpha' (alpha shapes) or 'kde' (kernel density estimation)
# ENVELOPE_TYPE = 'kde'  # Options: 'alpha' (alpha shapes) or 'kde' (kernel density estimation)
CLUSTER_EPS = 1.0  # DBSCAN distance threshold for clustering (higher = larger clusters)
ALPHA_SHAPE_ALPHA = 4.0  # Alpha shape tightness (higher = tighter fit, lower = more convex)
KDE_BANDWIDTH = 0.05  # KDE bandwidth/smoothness (higher = smoother, more spread out)
KDE_LEVEL = 0.01  # KDE contour level (lower = larger envelope, higher = tighter)
MIN_CLUSTER_SIZE = 3  # Minimum tweets required to form a cluster
SHOW_ENVELOPES = True  # Set to False to disable envelopes

# Text labels
SHOW_ROOT_LABELS = True  # Set to False to hide text labels on root tweets (reduces clutter when zoomed out)

# Styling
ENVELOPE_FILL_OPACITY = 0.12
ENVELOPE_BORDER_OPACITY = 0.35
EDGE_OPACITY = 0.25
EDGE_WIDTH = 2.5

# ===== END PARAMETERS =====

# Load embedding data
data_path = Path(__file__).parent / "data/tweet_embeddings_atlas.parquet"
print(f"Loading data from {data_path}")
"""Index(['tweet_id', 'strand_id', 'annotation', 'tweet_type', 'text', 'date',
       'seed_type', 'likes', 'retweets', 'projection_x', 'projection_y',
       'is_essential', 'is_root'],
      dtype='object')"""
data = pd.read_parquet(data_path)
data.head()
print(f"Loaded {len(data['projection_x'])} points")

# Extract data
x = np.array(data['projection_x'])
y = np.array(data['projection_y'])
tweet_ids = data['tweet_id']
strand_ids = data['strand_id']
is_essential = np.array(data['is_essential'])
is_root = np.array(data['is_root'])
text = data['text']
# %%
# Helper functions for hover text formatting
def format_hover_text(row):
    """Format rich hover text with metadata"""
    # Format date if available
    date_str = datetime.fromisoformat(row['date']).strftime('%Y-%m-%d %H:%M') if pd.notnull(row['date']) else 'Unknown date'

    # Extract username from annotation if available
    annotation_str = str(row['annotation']) if pd.notnull(row['annotation']) else ''
    username = annotation_str.split(':')[0] if ':' in annotation_str else 'Unknown'

    # Tweet type
    tweet_type = row['tweet_type'] if pd.notnull(row['tweet_type']) else 'Tweet'

    # Build hover text with line breaks
    hover = f"<b>[{tweet_type}] @{username}</b><br>"
    hover += f"📅 {date_str}<br>"
    hover += f"🧬 Strand: {row['strand_id']}"

    if pd.notnull(row['likes']) or pd.notnull(row['retweets']):
        likes = int(row['likes']) if pd.notnull(row['likes']) else 0
        retweets = int(row['retweets']) if pd.notnull(row['retweets']) else 0
        hover += f" | ❤️ {likes} 🔄 {retweets}"

    hover += "<br>"

    if annotation_str and annotation_str != 'nan':
        hover += f"<i>{annotation_str[:100]}</i><br>"

    hover += "─" * 40 + "<br>"

    # Tweet text (wrap long text)
    text = str(row['text'])
    if len(text) > 200:
        text = text[:200] + "..."
    hover += text.replace('\n', '<br>')

    return hover

def format_root_label(row):
    """Format label for root points: username + first 6 words"""
    # Extract username from annotation if available
    annotation_str = str(row['annotation']) if pd.notnull(row['annotation']) else ''
    username = annotation_str.split(':')[0] if ':' in annotation_str else 'Unknown'

    # Get first 6 words of tweet
    text = str(row['text'])
    words = text.split()[:6]
    short_text = ' '.join(words)
    if len(words) == 6 and len(text.split()) > 6:
        short_text += '...'

    return f"@{username}: {short_text}"

# Helper functions for color generation
def get_strand_colors(x, y, strand_ids, is_essential, is_root, palette='vibrant'):
    """
    Generate colors based on strand median positions
    Each strand gets one color based on the median position of its root/essential points

    Palettes:
    - 'vibrant': High saturation, medium lightness (original but more saturated)
    - 'pastel': Lower saturation, higher lightness
    - 'deep': High saturation, lower lightness
    - 'muted': Lower saturation, medium lightness
    - 'neon': Maximum saturation, high lightness
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
        'original': (0.55, 0.70),  # Your original values
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
        strand_colors_map[strand_id] = f'rgb({int(r*255)},{int(g*255)},{int(b*255)})'

    # Assign colors to each point based on its strand
    colors = [strand_colors_map[sid] for sid in strand_ids]

    return colors

def get_timestamp_from_tweet_id(tweet_id):
    """Extract timestamp from Twitter snowflake ID"""
    TWITTER_EPOCH = 1288834974657
    tweet_id_int = int(tweet_id)
    timestamp = ((tweet_id_int >> 22) + TWITTER_EPOCH) / 1000  # Convert to seconds
    return timestamp

def adjust_saturation_by_age(rgb_str, timestamp, min_timestamp, max_timestamp):
    """Adjust color saturation based on age (older = less saturated)"""
    # Parse RGB
    rgb = rgb_str.replace('rgb(', '').replace(')', '').split(',')
    r, g, b = int(rgb[0]) / 255, int(rgb[1]) / 255, int(rgb[2]) / 255

    # Calculate age factor (0 = oldest, 1 = newest)
    if max_timestamp == min_timestamp:
        age_factor = 1
    else:
        age_factor = (timestamp - min_timestamp) / (max_timestamp - min_timestamp)

    # Saturation multiplier: 30% to 100%
    saturation_multiplier = 0.3 + (age_factor * 0.7)

    # Calculate grayscale value
    gray = 0.299 * r + 0.587 * g + 0.114 * b

    # Blend towards gray based on age
    new_r = gray + (r - gray) * saturation_multiplier
    new_g = gray + (g - gray) * saturation_multiplier
    new_b = gray + (b - gray) * saturation_multiplier

    return f'rgb({int(new_r*255)},{int(new_g*255)},{int(new_b*255)})'

def create_chronological_edges(data, base_colors, distance_threshold):
    """
    Create edges between chronologically consecutive essential/root tweets
    Only draws edges if tweets are within distance_threshold of each other

    Returns list of edge traces
    """
    edge_traces = []

    # Get unique strands
    unique_strands = data['strand_id'].unique()

    for strand_id in unique_strands:
        # Filter to this strand's essential/root tweets
        strand_data = data[
            (data['strand_id'] == strand_id) &
            (data['is_essential'] | data['is_root'])
        ].copy()

        if len(strand_data) < 2:
            continue

        # Sort by date
        strand_data = strand_data.sort_values('date')

        # Get strand color (use first tweet's color)
        strand_indices = data[data['strand_id'] == strand_id].index
        if len(strand_indices) > 0:
            strand_color = base_colors[strand_indices[0]]
        else:
            strand_color = 'rgb(128,128,128)'

        # Create edges between consecutive tweets
        edge_x = []
        edge_y = []

        for i in range(len(strand_data) - 1):
            tweet1 = strand_data.iloc[i]
            tweet2 = strand_data.iloc[i + 1]

            # Calculate distance
            dist = np.sqrt(
                (tweet2['projection_x'] - tweet1['projection_x'])**2 +
                (tweet2['projection_y'] - tweet1['projection_y'])**2
            )

            # Only draw edge if within threshold
            if dist <= distance_threshold:
                edge_x.extend([tweet1['projection_x'], tweet2['projection_x'], None])
                edge_y.extend([tweet1['projection_y'], tweet2['projection_y'], None])

        # Add edge trace if we have any edges
        if edge_x:
            edge_traces.append(go.Scattergl(
                x=edge_x,
                y=edge_y,
                mode='lines',
                line=dict(
                    color=strand_color,
                    width=EDGE_WIDTH,
                ),
                opacity=EDGE_OPACITY,
                showlegend=False,
                hoverinfo='skip',
            ))

    return edge_traces

def export_annotations(fig, filename='plot_annotations.json'):
    """
    Export drawing annotations/shapes to JSON file

    Usage:
        export_annotations(fig, 'my_annotations.json')
    """
    import json

    # Extract shapes from figure layout
    shapes = fig.layout.shapes if fig.layout.shapes else []

    # Convert to JSON-serializable format
    shapes_data = []
    for shape in shapes:
        shapes_data.append({
            'type': shape.type,
            'x0': shape.x0,
            'y0': shape.y0,
            'x1': shape.x1,
            'y1': shape.y1,
            'line': {
                'color': shape.line.color if shape.line else None,
                'width': shape.line.width if shape.line else None,
            },
            'fillcolor': shape.fillcolor if hasattr(shape, 'fillcolor') else None,
        })

    # Save to file
    with open(filename, 'w') as f:
        json.dump({'shapes': shapes_data}, f, indent=2)

    print(f"Exported {len(shapes_data)} annotations to {filename}")

def load_annotations(fig, filename='plot_annotations.json'):
    """
    Load drawing annotations/shapes from JSON file

    Usage:
        load_annotations(fig, 'my_annotations.json')
    """
    import json

    # Load from file
    with open(filename, 'r') as f:
        data = json.load(f)

    shapes_data = data.get('shapes', [])

    # Add shapes to figure
    for shape_dict in shapes_data:
        fig.add_shape(
            type=shape_dict['type'],
            x0=shape_dict['x0'],
            y0=shape_dict['y0'],
            x1=shape_dict['x1'],
            y1=shape_dict['y1'],
            line=dict(
                color=shape_dict['line']['color'],
                width=shape_dict['line']['width'],
            ),
            fillcolor=shape_dict.get('fillcolor'),
        )

    print(f"Loaded {len(shapes_data)} annotations from {filename}")

    return fig

def create_alpha_shape_envelopes(data, base_colors, cluster_eps, alpha_value, min_cluster_size):
    """
    Create alpha shape envelopes around clusters of essential/root tweets within each strand

    Uses DBSCAN to find clusters, then creates alpha shapes for each cluster

    Returns list of envelope traces
    """
    envelope_traces = []

    # Get unique strands
    unique_strands = data['strand_id'].unique()

    for strand_id in unique_strands:
        # Get only essential/root tweets in this strand
        strand_data = data[
            (data['strand_id'] == strand_id) &
            (data['is_essential'] | data['is_root'])
        ]

        if len(strand_data) < min_cluster_size:
            continue

        # Extract positions
        positions = strand_data[['projection_x', 'projection_y']].values

        # Cluster using DBSCAN
        clustering = DBSCAN(eps=cluster_eps, min_samples=min_cluster_size).fit(positions)
        labels = clustering.labels_

        # Get strand color
        strand_indices = data[data['strand_id'] == strand_id].index
        if len(strand_indices) > 0:
            strand_color = base_colors[strand_indices[0]]
        else:
            strand_color = 'rgb(128,128,128)'

        # Extract RGB values for alpha-blended fill
        rgb = strand_color.replace('rgb(', '').replace(')', '').split(',')
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        fill_color = f'rgba({r},{g},{b},{ENVELOPE_FILL_OPACITY})'
        border_color = f'rgba({r},{g},{b},{ENVELOPE_BORDER_OPACITY})'

        # Create alpha shape for each cluster
        unique_labels = set(labels)
        for label in unique_labels:
            if label == -1:  # Skip noise points
                continue

            # Get points in this cluster
            cluster_mask = labels == label
            cluster_points = positions[cluster_mask]

            if len(cluster_points) < 3:  # Need at least 3 points for alpha shape
                continue

            try:
                # Create alpha shape
                alpha_shape = alphashape.alphashape(cluster_points, alpha_value)

                # Extract boundary coordinates
                if hasattr(alpha_shape, 'exterior'):
                    # It's a Polygon
                    coords = list(alpha_shape.exterior.coords)
                    envelope_x = [c[0] for c in coords]
                    envelope_y = [c[1] for c in coords]

                    # Add envelope trace
                    envelope_traces.append(go.Scattergl(
                        x=envelope_x,
                        y=envelope_y,
                        mode='lines',
                        fill='toself',
                        fillcolor=fill_color,
                        line=dict(
                            color=border_color,
                            width=1.5,
                        ),
                        showlegend=False,
                        hoverinfo='skip',
                    ))
                elif hasattr(alpha_shape, 'geoms'):
                    # It's a MultiPolygon
                    for poly in alpha_shape.geoms:
                        coords = list(poly.exterior.coords)
                        envelope_x = [c[0] for c in coords]
                        envelope_y = [c[1] for c in coords]

                        envelope_traces.append(go.Scattergl(
                            x=envelope_x,
                            y=envelope_y,
                            mode='lines',
                            fill='toself',
                            fillcolor=fill_color,
                            line=dict(
                                color=border_color,
                                width=1.5,
                            ),
                            showlegend=False,
                            hoverinfo='skip',
                        ))

            except Exception as e:
                # Skip if alpha shape fails (e.g., collinear points)
                print(f"  Warning: Could not create alpha shape for strand {strand_id}, cluster {label}: {e}")
                continue

    return envelope_traces

def create_kde_envelopes(data, base_colors, cluster_eps, bandwidth, level, min_cluster_size):
    """
    Create KDE-based envelopes around clusters of essential/root tweets within each strand

    Uses DBSCAN to find clusters, then creates density contours for each cluster

    Returns list of envelope traces
    """
    envelope_traces = []

    # Get unique strands
    unique_strands = data['strand_id'].unique()

    for strand_id in unique_strands:
        # Get only essential/root tweets in this strand
        strand_data = data[
            (data['strand_id'] == strand_id) &
            (data['is_essential'] | data['is_root'])
        ]

        if len(strand_data) < min_cluster_size:
            continue

        # Extract positions
        positions = strand_data[['projection_x', 'projection_y']].values

        # Cluster using DBSCAN
        clustering = DBSCAN(eps=cluster_eps, min_samples=min_cluster_size).fit(positions)
        labels = clustering.labels_

        # Get strand color
        strand_indices = data[data['strand_id'] == strand_id].index
        if len(strand_indices) > 0:
            strand_color = base_colors[strand_indices[0]]
        else:
            strand_color = 'rgb(128,128,128)'

        # Extract RGB values for alpha-blended fill
        rgb = str|and_color.replace('rgb(', '').replace(')', '').split(',')
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        fill_color = f'rgba({r},{g},{b},{ENVELOPE_FILL_OPACITY})'
        border_color = f'rgba({r},{g},{b},{ENVELOPE_BORDER_OPACITY})'

        # Create KDE contour for each cluster
        unique_labels = set(labels)
        for label in unique_labels:
            if label == -1:  # Skip noise points
                continue

            # Get points in this cluster
            cluster_mask = labels == label
            cluster_points = positions[cluster_mask]

            if len(cluster_points) < 3:  # Need at least 3 points
                continue

            try:
                # Create a grid for KDE evaluation
                x_min, x_max = cluster_points[:, 0].min() - 2, cluster_points[:, 0].max() + 2
                y_min, y_max = cluster_points[:, 1].min() - 2, cluster_points[:, 1].max() + 2

                xx, yy = np.meshgrid(
                    np.linspace(x_min, x_max, 100),
                    np.linspace(y_min, y_max, 100)
                )

                # Fit KDE
                kde = KernelDensity(bandwidth=bandwidth, kernel='gaussian')
                kde.fit(cluster_points)

                # Evaluate KDE on grid
                grid_points = np.c_[xx.ravel(), yy.ravel()]
                log_density = kde.score_samples(grid_points)
                density = np.exp(log_density).reshape(xx.shape)

                # Normalize density
                density = density / density.max()

                # Find contours at specified level
                contours = measure.find_contours(density, level)

                # Convert contours to plot coordinates
                for contour in contours:
                    # Map contour coordinates back to original space
                    contour_x = np.interp(contour[:, 1], np.arange(100), np.linspace(x_min, x_max, 100))
                    contour_y = np.interp(contour[:, 0], np.arange(100), np.linspace(y_min, y_max, 100))

                    # Add envelope trace
                    envelope_traces.append(go.Scattergl(
                        x=contour_x,
                        y=contour_y,
                        mode='lines',
                        fill='toself',
                        fillcolor=fill_color,
                        line=dict(
                            color=border_color,
                            width=1.5,
                        ),
                        showlegend=False,
                        hoverinfo='skip',
                    ))

            except Exception as e:
                # Skip if KDE fails
                print(f"  Warning: Could not create KDE envelope for strand {strand_id}, cluster {label}: {e}")
                continue

    return envelope_traces

# Generate base colors by strand (using only root and essential tweets)
print(f"Generating strand-based colors with '{PALETTE}' palette...")
base_colors = get_strand_colors(x, y, strand_ids, is_essential, is_root, palette=PALETTE)

# Generate hover text for all tweets
print("Generating enhanced hover labels...")
hover_texts = data.apply(format_hover_text, axis=1).tolist()

# Separate points by type
regular_mask = ~is_essential & ~is_root
essential_mask = is_essential & ~is_root
root_mask = is_root

# Create traces
traces = []

# Add envelopes first (so they're at the very back)
if SHOW_ENVELOPES:
    if ENVELOPE_TYPE == 'kde':
        print(f"Creating KDE envelopes (DBSCAN eps: {CLUSTER_EPS}, bandwidth: {KDE_BANDWIDTH}, level: {KDE_LEVEL})...")
        envelope_traces = create_kde_envelopes(
            data, base_colors, CLUSTER_EPS, KDE_BANDWIDTH, KDE_LEVEL, MIN_CLUSTER_SIZE
        )
        traces.extend(envelope_traces)
        print(f"  Created {len(envelope_traces)} KDE envelopes")
    else:  # default to alpha shapes
        print(f"Creating alpha shape envelopes (DBSCAN eps: {CLUSTER_EPS}, alpha: {ALPHA_SHAPE_ALPHA})...")
        envelope_traces = create_alpha_shape_envelopes(
            data, base_colors, CLUSTER_EPS, ALPHA_SHAPE_ALPHA, MIN_CLUSTER_SIZE
        )
        traces.extend(envelope_traces)
        print(f"  Created {len(envelope_traces)} alpha shape envelopes")

# Add chronological edges (on top of envelopes, behind points)
if SHOW_EDGES:
    print(f"Creating chronological edges (threshold: {EDGE_DISTANCE_THRESHOLD})...")
    edge_traces = create_chronological_edges(data, base_colors, EDGE_DISTANCE_THRESHOLD)
    traces.extend(edge_traces)
    print(f"  Created {len(edge_traces)} edge groups")

# Regular tweets - small dots with low opacity
print(f"Regular tweets: {regular_mask.sum()}")
if regular_mask.sum() > 0:
    traces.append(go.Scattergl(
        x=x[regular_mask],
        y=y[regular_mask],
        mode='markers',
        name='Tweets',
        text=[hover_texts[i] for i in range(len(hover_texts)) if regular_mask[i]],
        hoverinfo='text',
        marker=dict(
            size=5,
            color=[base_colors[i] for i in range(len(base_colors)) if regular_mask[i]],
            opacity=0.3,
        ),
    ))

# Essential tweets - medium circles with age-based desaturation
print(f"Essential tweets: {essential_mask.sum()}")
if essential_mask.sum() > 0:
    # Extract timestamps for essential tweets
    essential_indices = np.where(essential_mask)[0]
    essential_timestamps = [get_timestamp_from_tweet_id(tweet_ids[i]) for i in essential_indices]
    min_timestamp = min(essential_timestamps)
    max_timestamp = max(essential_timestamps)

    # Apply saturation adjustment
    essential_colors = [
        adjust_saturation_by_age(
            base_colors[idx],
            timestamp,
            min_timestamp,
            max_timestamp
        )
        for idx, timestamp in zip(essential_indices, essential_timestamps)
    ]

    traces.append(go.Scattergl(
        x=x[essential_mask],
        y=y[essential_mask],
        mode='markers',
        name='Essential',
        text=[hover_texts[i] for i in range(len(hover_texts)) if essential_mask[i]],
        hoverinfo='text',
        marker=dict(
            size=10,
            color=essential_colors,
            opacity=0.9,
            line=dict(color='black', width=1),
        ),
    ))

# Root tweets - large diamonds
print(f"Root tweets: {root_mask.sum()}")
if root_mask.sum() > 0:
    traces.append(go.Scattergl(
        x=x[root_mask],
        y=y[root_mask],
        mode='markers',
        name='Root',
        text=[hover_texts[i] for i in range(len(hover_texts)) if root_mask[i]],
        hoverinfo='text',
        marker=dict(
            size=14,
            symbol='diamond',
            color=[base_colors[i] for i in range(len(base_colors)) if root_mask[i]],
            opacity=1.0,
            line=dict(color='black', width=2),
        ),
    ))

    # Add text labels for root tweets (optional)
    if SHOW_ROOT_LABELS:
        root_data = data[data['is_root']]
        root_labels = root_data.apply(format_root_label, axis=1).tolist()

        traces.append(go.Scattergl(
            x=x[root_mask],
            y=y[root_mask],
            mode='text',
            name='Root Labels',
            text=root_labels,
            textposition='top center',
            textfont=dict(
                size=9,
                color='black',
                family='Arial, sans-serif',
            ),
            showlegend=False,
            hoverinfo='skip',
        ))

# Create figure
fig = go.Figure(data=traces)

# Update layout
fig.update_layout(
    title=dict(
        text=f'UMAP of Strand Tweets - {PALETTE.capitalize()} Palette',
        font=dict(size=20, color='#333'),
        y=0.98,
    ),
    xaxis=dict(
        title='UMAP Dimension 1',
        showgrid=True,
        gridcolor='#eee',
        scaleanchor='y',
        scaleratio=1,
    ),
    yaxis=dict(
        title='UMAP Dimension 2',
        showgrid=True,
        gridcolor='#eee',
    ),
    showlegend=True,
    legend=dict(
        x=1,
        y=1,
        xanchor='right',
        bgcolor='rgba(255,255,255,0.8)',
    ),
    paper_bgcolor='white',
    plot_bgcolor='white',
    dragmode='pan',
    hovermode='closest',
    height=720,
    # Drawing/annotation configuration
    newshape=dict(
        line=dict(color='red', width=2),
        fillcolor='rgba(255,0,0,0.2)',
        opacity=0.8,
    ),
)

# Update config for scroll zoom and drawing tools
config = {
    'scrollZoom': True,
    'displayModeBar': True,
    'modeBarButtonsToAdd': ['drawline', 'drawrect', 'drawopenpath', 'drawcircle', 'eraseshape'],
    'toImageButtonOptions': {
        'format': 'png',
        'filename': 'tweet_umap_plot',
        'height': 1080,
        'width': 1920,
        'scale': 2
    },
}

print("Opening interactive plot...")
fig.show(config=config)

print("\n" + "="*70)
print("INTERACTIVE PLOT FEATURES")
print("="*70)

print("\n📊 VISUALIZATION:")
print(f"  • Color palette: {PALETTE}")
print("  • Colors based on strand median position (root/essential tweets)")
print("  • Essential tweets: age-based desaturation (older = grayer)")
print("  • Root tweets: labeled with username + first 6 words")
if SHOW_EDGES:
    print(f"  • Chronological edges between consecutive tweets (threshold: {EDGE_DISTANCE_THRESHOLD})")
if SHOW_ENVELOPES:
    if ENVELOPE_TYPE == 'kde':
        print(f"  • KDE envelopes around essential/root clusters (eps: {CLUSTER_EPS}, bandwidth: {KDE_BANDWIDTH}, level: {KDE_LEVEL})")
    else:
        print(f"  • Alpha shape envelopes around essential/root clusters (eps: {CLUSTER_EPS}, alpha: {ALPHA_SHAPE_ALPHA})")

print("\n🖱️  INTERACTION:")
print("  • Scroll to zoom")
print("  • Drag to pan")
print("  • Click legend to toggle trace visibility")
print("  • Hover for detailed tweet information")

print("\n✏️  ANNOTATION TOOLS (use toolbar buttons):")
print("  • Draw Line - connect points with lines")
print("  • Draw Rectangle - highlight regions")
print("  • Draw Open Path - freehand drawing")
print("  • Draw Circle - circular regions")
print("  • Erase Shape - remove drawn annotations/shapes")
print("\n  ⚠️  Note: Plotly doesn't support deleting individual data points.")
print("      You can hide entire traces using the legend, but not individual points.")

print("\n💾 SAVE/LOAD ANNOTATIONS:")
print("  # Save annotations after drawing:")
print("  export_annotations(fig, 'my_annotations.json')")
print("")
print("  # Load annotations in a new plot:")
print("  load_annotations(fig, 'my_annotations.json')")

print("\n⚙️  TUNABLE PARAMETERS (edit at top of file and re-run):")
print("  • PALETTE - color scheme ('vibrant', 'pastel', 'deep', 'muted', 'neon', 'original')")
print("  • ENVELOPE_TYPE - envelope method ('alpha' or 'kde')")
print("  • EDGE_DISTANCE_THRESHOLD - max distance to draw edges between tweets")
print("  • CLUSTER_EPS - DBSCAN distance for clustering tweets")
print("  • ALPHA_SHAPE_ALPHA - alpha shape tightness (higher = tighter)")
print("  • KDE_BANDWIDTH - KDE smoothness (higher = smoother/wider)")
print("  • KDE_LEVEL - KDE contour level (lower = larger, higher = tighter)")
print("  • MIN_CLUSTER_SIZE - minimum tweets to form a cluster")
print("  • SHOW_EDGES, SHOW_ENVELOPES, SHOW_ROOT_LABELS - toggle features on/off")
print("\n  💡 Tip: Set SHOW_ROOT_LABELS=False for cleaner zoomed-out view.")
print("         Alpha shapes = geometric hulls, KDE = smooth density contours.")

print("\n" + "="*70)

# %%
