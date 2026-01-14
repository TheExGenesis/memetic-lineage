#!/usr/bin/env python3
"""
Interactive Plotly scatter plot of strands:
- X-axis: Time (from root tweet ID)
- Y-axis: Seriation order
- Shows strand images on hover/click
"""
# %%
import base64
import json
import re
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
from PIL import Image

# Paths
FRESH_STRANDS_DIR = Path(__file__).parent / "data" / "fresh_rated_strands"
STRAND_IMGS_DIR = Path(__file__).parent / "data" / "strand_imgs"
SERIATION_ORDER_PATH = Path(__file__).parent.parent / "top-qt-website" / "bangers" / "public" / "strand_seriation_order.json"
OUTPUT_HTML = Path(__file__).parent / "data" / "strand_timeline.html"


def tweet_id_to_timestamp(tweet_id: int) -> datetime:
    """Convert Twitter snowflake ID to datetime."""
    # Twitter epoch: 1288834974657 (Nov 4, 2010)
    twitter_epoch = 1288834974657
    timestamp_ms = ((tweet_id >> 22) + twitter_epoch)
    return datetime.fromtimestamp(timestamp_ms / 1000)


def load_seriation_order() -> tuple[dict[str, int], dict[str, float]]:
    """Load seriation order mapping seed_id -> position and seed_id -> cumulative_distance."""
    with open(SERIATION_ORDER_PATH) as f:
        data = json.load(f)
    
    order = data.get("order", [])
    
    # Create position mapping
    position_map = {item["id"]: idx for idx, item in enumerate(order)}
    
    # Create cumulative distance mapping
    cumulative_distance = 0.0
    distance_map = {}
    for item in order:
        distance_map[item["id"]] = cumulative_distance
        cumulative_distance += item.get("distance", 0.0)
    
    return position_map, distance_map


def image_to_base64(img_path: Path, max_size: int = 400) -> str:
    """Convert image to base64 data URL, resized for web."""
    img = Image.open(img_path)
    # Resize for faster loading
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def extract_date_from_thread(thread_text: str, seed_tweet_id: int) -> datetime | None:
    """Extract the date for the seed tweet from thread_text.
    
    Looks for the pattern: seed_tweet_id [YYYY-MM-DD]
    """
    # Look for the seed tweet ID followed by a date in brackets
    pattern = rf'{seed_tweet_id}\s*\[(\d{{4}}-\d{{2}}-\d{{2}})\]'
    match = re.search(pattern, thread_text)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    
    # Fallback: just get the first date in the thread
    match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', thread_text)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    return None


def main():
    print("Loading seriation order...")
    seriation_order, distance_map = load_seriation_order()
    print(f"Found {len(seriation_order)} strands in seriation order")
    print(f"Total cumulative distance: {max(distance_map.values()):.2f}")
    
    # Collect data for plotting
    data_points = []
    
    print("Loading strand data...")
    for json_path in sorted(FRESH_STRANDS_DIR.glob("*.json")):
        seed_id = json_path.stem
        
        if seed_id not in seriation_order:
            continue
        
        with open(json_path) as f:
            strand_data = json.load(f)
        
        # Get seed tweet ID
        tweet_id = strand_data.get("seed_tweet_id", int(seed_id))
        
        # Extract date from thread_text by finding the seed tweet ID's date
        thread_text = strand_data.get("thread_text", "")
        timestamp = extract_date_from_thread(thread_text, tweet_id)
        
        # Fallback to Twitter snowflake ID conversion if no date found
        if not timestamp:
            timestamp = tweet_id_to_timestamp(tweet_id)
        
        # Get seriation position and cumulative distance
        seriation_idx = seriation_order[seed_id]
        cumulative_dist = distance_map[seed_id]
        
        # Get title and other metadata
        title = strand_data.get("title", "Untitled")
        rating = strand_data.get("rating", {}).get("rating", 0)
        
        # Find corresponding image
        img_path = STRAND_IMGS_DIR / f"{seriation_idx:03d}_{seed_id}.png"
        
        data_points.append({
            "seed_id": seed_id,
            "timestamp": timestamp,
            "seriation_idx": seriation_idx,
            "cumulative_dist": cumulative_dist,
            "title": title,
            "rating": rating,
            "img_path": img_path if img_path.exists() else None,
        })
    
    print(f"Collected {len(data_points)} data points")
    
    # Sort by seriation order
    data_points.sort(key=lambda x: x["seriation_idx"])
    
    # Prepare plot data
    x_dates = [p["timestamp"] for p in data_points]
    y_distances = [p["cumulative_dist"] for p in data_points]  # Use cumulative distance for Y
    
    # Create hover text and encode images
    hover_texts = []
    image_data_urls = []
    
    print("Encoding images for plot (this may take a moment)...")
    for i, p in enumerate(data_points):
        hover_text = f"<b>{p['title'][:50]}...</b><br>Rating: {p['rating']}/10<br>Date: {p['timestamp'].strftime('%Y-%m-%d')}<br>Seriation: #{p['seriation_idx']}<br>Cumulative Dist: {p['cumulative_dist']:.3f}"
        hover_texts.append(hover_text)
        
        # Encode image as base64
        if p["img_path"] and p["img_path"].exists():
            try:
                img_b64 = image_to_base64(p["img_path"], max_size=600)
                image_data_urls.append(img_b64)
            except Exception as e:
                print(f"  [WARN] Failed to encode {p['img_path'].name}: {e}")
                image_data_urls.append("")
        else:
            image_data_urls.append("")
        
        if (i + 1) % 50 == 0:
            print(f"  Encoded {i + 1}/{len(data_points)} images...")
    
    # Create the figure
    fig = go.Figure()
    
    # Add scatter trace
    fig.add_trace(go.Scatter(
        x=x_dates,
        y=y_distances,  # Use cumulative distance for Y axis
        mode='markers',
        marker=dict(
            size=14,
            color=[p["rating"] for p in data_points],
            colorscale='RdYlGn',
            showscale=True,
            colorbar=dict(title="Rating"),
            cmin=0,
            cmax=10,
        ),
        text=hover_texts,
        hoverinfo='text',
        customdata=image_data_urls,
    ))
    
    # Update layout
    fig.update_layout(
        title="Strand Timeline (X: Root Tweet Date, Y: Cumulative Distance - similar strands are close)",
        xaxis_title="Root Tweet Date",
        yaxis_title="Cumulative Embedding Distance (similar strands cluster together)",
        hovermode='closest',
        template='plotly_dark',
        width=1400,
        height=900,
        xaxis=dict(
            rangeslider=dict(visible=True),
            type="date",
        ),
        yaxis=dict(
            autorange="reversed",  # 0 at top, so similar strands are near each other
        ),
    )
    
    # Add custom JavaScript for image popup on click
    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                buttons=[
                    dict(
                        label="Reset View",
                        method="relayout",
                        args=[{"xaxis.autorange": True, "yaxis.autorange": True}]
                    )
                ],
                x=0.0,
                y=1.15,
            )
        ]
    )
    
    # Save as HTML with custom JS for image display
    html_content = fig.to_html(include_plotlyjs=True, full_html=True)
    
    # Inject custom CSS and JS for image popup
    custom_js = """
    <style>
        #image-popup {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 10000;
            background: #1a1a2e;
            padding: 10px;
            border-radius: 10px;
            box-shadow: 0 0 30px rgba(0,0,0,0.8);
            max-width: 90vw;
            max-height: 90vh;
        }
        #image-popup img {
            max-width: 100%;
            max-height: 85vh;
            border-radius: 5px;
        }
        #image-popup .close-btn {
            position: absolute;
            top: -15px;
            right: -15px;
            background: #ff4757;
            color: white;
            border: none;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            cursor: pointer;
            font-size: 18px;
        }
        #overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 9999;
        }
    </style>
    <div id="overlay" onclick="closePopup()"></div>
    <div id="image-popup">
        <button class="close-btn" onclick="closePopup()">×</button>
        <img id="popup-image" src="" alt="Strand Image">
    </div>
    <script>
        function closePopup() {
            document.getElementById('image-popup').style.display = 'none';
            document.getElementById('overlay').style.display = 'none';
        }
        
        // Close on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closePopup();
        });
        
        // Listen for plotly click events
        document.addEventListener('DOMContentLoaded', function() {
            var plot = document.querySelector('.plotly-graph-div');
            if (plot) {
                plot.on('plotly_click', function(data) {
                    var point = data.points[0];
                    var imgDataUrl = point.customdata;
                    if (imgDataUrl && imgDataUrl.startsWith('data:image')) {
                        document.getElementById('popup-image').src = imgDataUrl;
                        document.getElementById('overlay').style.display = 'block';
                        document.getElementById('image-popup').style.display = 'block';
                    }
                });
            }
        });
    </script>
    """
    
    # Insert before </body>
    html_content = html_content.replace("</body>", custom_js + "</body>")
    
    # Save
    with open(OUTPUT_HTML, "w") as f:
        f.write(html_content)
    
    print(f"\nSaved interactive plot to: {OUTPUT_HTML}")
    print("Open in browser to view. Click on points to see strand images.")


if __name__ == "__main__":
    main()

# %%

