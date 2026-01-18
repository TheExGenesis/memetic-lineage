# %%
"""
Interactive DataMapPlot visualization of tweet embeddings
Clean, beautiful visualization of strand stories with automatic label placement
"""

import pandas as pd
import numpy as np
from pathlib import Path
import datamapplot

# ===== PARAMETERS =====
LABEL_FONT_SIZE = 10
POINT_SIZE = 3
LABEL_OVER_POINTS = True  # Show labels on top of points
LABEL_ONLY_ROOTS = True  # Only show labels for root tweets (cleaner)
LABEL_FORMAT = 'username_preview'  # 'username_preview', 'strand_id', or 'date'

# ===== END PARAMETERS =====

# Load embedding data
data_path = Path(__file__).parent / "data/tweet_embeddings_atlas.parquet"
print(f"Loading data from {data_path}")
data = pd.read_parquet(data_path)
print(f"Loaded {len(data)} tweets across {data['strand_id'].nunique()} strands")

# Extract coordinates
coords = data[['projection_x', 'projection_y']].values

# Prepare labels and hover text
labels = []
hover_data = []

for idx, row in data.iterrows():
    username = str(row['annotation']).split(':')[0] if pd.notnull(row['annotation']) else 'Unknown'
    date_str = str(row['date'])[:10] if pd.notnull(row['date']) else 'Unknown date'
    text_preview = str(row['text'])[:60]
    words = text_preview.split()[:6]
    short_text = ' '.join(words) + ('...' if len(text_preview.split()) > 6 else '')

    # Create label based on format
    if LABEL_ONLY_ROOTS and not row['is_root']:
        # Don't label non-root tweets
        label = ""
    else:
        if LABEL_FORMAT == 'username_preview':
            label = f"@{username}: {short_text}"
        elif LABEL_FORMAT == 'strand_id':
            label = f"Strand {row['strand_id']}"
        elif LABEL_FORMAT == 'date':
            label = f"{date_str}"
        else:
            label = short_text

    labels.append(label)

    # Create rich hover text for all points
    hover = f"<b>[{row['tweet_type']}] @{username}</b><br>"
    hover += f"📅 {date_str} | 🧬 Strand {row['strand_id']}<br>"
    if pd.notnull(row['likes']):
        hover += f"❤️ {int(row['likes'])} 🔄 {int(row['retweets'])}<br>"
    hover += f"<br>{str(row['text'])[:200]}"

    hover_data.append(hover)

print("\nCreating interactive DataMapPlot...")
print(f"Visualizing {len(data['strand_id'].unique())} unique strands...")

# %%
# Create interactive plot with minimal parameters
# datamapplot will handle label placement and coloring automatically
try:
    fig = datamapplot.create_interactive_plot(
        coords,
        labels,
        hover_text=hover_data,
    )
except Exception as e:
    print(f"Error with hover_text, trying without: {e}")
    # Try without hover text if that's causing issues
    fig = datamapplot.create_interactive_plot(
        coords,
        labels,
    )

def fix_iframe_compatibility(html_path):
    """
    Fix datamapplot HTML for iframe embedding by replacing viewport units with percentages.

    DataMapPlot uses 100vw/100vh which don't work correctly in iframes.
    This replaces them with 100% for proper iframe rendering.
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace viewport units with percentage units
    content = content.replace('width: 100vw;', 'width: 100%;')
    content = content.replace('height: 100vh;', 'height: 100%;')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)

# Save to HTML in both locations
# 1. Local scratchpads for development
local_output = Path(__file__).parent / "tweet_datamapplot.html"
fig.save(str(local_output))
fix_iframe_compatibility(local_output)
print(f"📄 Saved local copy: {local_output}")

# 2. Bangers public directory for web embedding
web_output = Path(__file__).parent.parent / "top-qt-website/bangers/public/data/tweet_datamapplot.html"
web_output.parent.mkdir(parents=True, exist_ok=True)
fig.save(str(web_output))
fix_iframe_compatibility(web_output)
print(f"🌐 Saved web copy: {web_output}")

output_path = web_output  # Use web output for final message

print(f"\n✅ Interactive plot saved to: {output_path}")
print("\nOpen the HTML file in your browser to explore!")
print("\n📊 Features:")
print("  • Zoom and pan with mouse/trackpad")
print("  • Hover over points for detailed tweet information")
print(f"  • {sum(data['is_root'])} root tweets labeled (main stories)")
print(f"  • {data['strand_id'].nunique()} strands visualized")
print("  • Clean, automatic label placement by datamapplot")

print("\n⚙️  Customize:")
print("  • LABEL_ONLY_ROOTS - show all labels or just roots")
print("  • LABEL_FORMAT - 'username_preview', 'strand_id', or 'date'")
print("  • LABEL_FONT_SIZE, POINT_SIZE - adjust appearance")

print("\n💡 This visualization focuses on the 'main stories' - the root tweets")
print("   that started each conversation strand in your community.")

# %%
