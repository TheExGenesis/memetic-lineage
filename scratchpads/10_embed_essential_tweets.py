# %%

import json
import re
from pathlib import Path
from typing import Optional

DATA_DIR = Path("data")
RATED_DIR = DATA_DIR / "rated_strands"
EMBEDDINGS_DIR = DATA_DIR / "essential_tweet_embeddings"

def parse_tweet_from_thread_text(thread_text: str, tweet_id: int) -> Optional[str]:
    """
    Extract tweet text (including image descriptions) from thread_text by tweet_id.
    
    Thread format (can have tree prefixes like │, ├──, └──):
    [│   ]TWEET_ID [DATE] @username 💜 likes 🔁 retweets
    [│   ]Tweet text...
    [│   ]Images:
    [│   ]  - [Image #0] description
    ↓ (or === or ├── or └──)
    """
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')
    
    # Find the line containing this tweet_id (allowing tree prefixes like │, ├──, └──)
    # Pattern: optional tree chars, then tweet_id, then space and [
    tweet_header_pattern = re.compile(rf'^[│├└─\s]*{tweet_id_str}\s+\[')
    
    start_idx = None
    for i, line in enumerate(lines):
        if tweet_header_pattern.match(line):
            start_idx = i
            break
    
    if start_idx is None:
        return None
    
    # Determine the tree prefix for this tweet (e.g., "│   " or "")
    # We'll strip this prefix from content lines
    header_line = lines[start_idx]
    prefix_match = re.match(rf'^([│├└─\s]*){tweet_id_str}', header_line)
    tree_prefix = prefix_match.group(1) if prefix_match else ""
    
    # Collect lines until we hit the next tweet header or separator
    content_lines = []
    next_tweet_pattern = re.compile(r'^[│├└─\s]*\d{15,}\s+\[')
    separators = {'===', '↓'}
    
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        
        # Strip the tree prefix if present
        if tree_prefix and line.startswith(tree_prefix):
            stripped_line = line[len(tree_prefix):]
        else:
            stripped_line = line
        
        stripped = stripped_line.strip()
        
        # Stop at separators
        if stripped in separators:
            break
        
        # Stop at next tweet header
        if next_tweet_pattern.match(line):
            break
            
        # Stop at tree branch to next tweet (├── or └── followed by tweet ID)
        if re.match(r'^[│\s]*[├└]──\s*\d{15,}\s+\[', line):
            break
        
        content_lines.append(stripped)
    
    text = '\n'.join(content_lines).strip()
    
    # Remove [Quoting @...] blocks
    text = re.sub(r'\[Quoting @[^\]]+\]', '', text)
    
    # Clean up any resulting double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def load_rated_strand(filepath: Path) -> dict:
    """Load a rated strand JSON, fixing large integer tweet IDs."""
    json_text = filepath.read_text()
    # Fix large integers that might lose precision
    fixed = re.sub(r'"tweet_id":\s*(\d+)', r'"tweet_id": "\1"', json_text)
    fixed = re.sub(r'"seed_tweet_id":\s*(\d+)', r'"seed_tweet_id": "\1"', fixed)
    return json.loads(fixed)


def build_embedding_text(tweet_text: str, annotation: str) -> str:
    """Combine tweet text and annotation for embedding."""
    return f"""Tweet:
{tweet_text}

Annotation:
{annotation}"""

# %%

# Cell 1: Print text to be embedded for 5 strands

strand_files = sorted(RATED_DIR.glob("*.json"))[:5]
print(f"Loading {len(strand_files)} strands...\n")

all_embedding_texts = {}  # {strand_id: [{tweet_id, text_to_embed, annotation}, ...]}

for filepath in strand_files:
    strand = load_rated_strand(filepath)
    strand_id = strand['seed_tweet_id']
    thread_text = strand['thread_text']
    essential_tweets = strand['rating']['essential_tweets']
    
    print(f"{'='*80}")
    print(f"STRAND: {strand_id}")
    print(f"Summary: {strand['rating']['reasoning_summary'][:100]}...")
    print(f"Essential tweets: {len(essential_tweets)}")
    print(f"{'='*80}\n")
    
    strand_embeddings = []
    
    for et in essential_tweets:
        tweet_id = et['tweet_id']
        annotation = et['annotation']
        
        # Extract tweet text from thread_text
        tweet_text = parse_tweet_from_thread_text(thread_text, int(tweet_id))
        
        if tweet_text:
            text_to_embed = build_embedding_text(tweet_text, annotation)
            strand_embeddings.append({
                'tweet_id': tweet_id,
                'annotation': annotation,
                'text_to_embed': text_to_embed
            })
            
            print(f"--- Tweet {tweet_id} ---")
            print(f"Annotation: {annotation}")
            print(f"Tweet text:\n{tweet_text[:500]}{'...' if len(tweet_text) > 500 else ''}")
            print()
        else:
            print(f"[WARN] Could not find tweet {tweet_id} in thread_text")
    
    all_embedding_texts[strand_id] = strand_embeddings
    print(f"\n")

# Summary
total_tweets = sum(len(v) for v in all_embedding_texts.values())
print(f"\n{'='*80}")
print(f"Total: {len(all_embedding_texts)} strands, {total_tweets} essential tweets to embed")

# %%

# Cell 2: Generate embeddings and save results

import os
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path("..") / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"  # or "text-embedding-3-large" for higher quality

def get_embedding(text: str) -> list[float]:
    """Get embedding for a single text."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding

def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Get embeddings for multiple texts in batches."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )
        all_embeddings.extend([d.embedding for d in response.data])
    return all_embeddings


# Process ALL strands (not just the 5 preview ones)
all_strand_files = sorted(RATED_DIR.glob("*.json"))
print(f"Processing {len(all_strand_files)} strands...")

EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

for filepath in tqdm(all_strand_files, desc="Strands"):
    strand = load_rated_strand(filepath)
    strand_id = strand['seed_tweet_id']
    thread_text = strand['thread_text']
    essential_tweets = strand['rating']['essential_tweets']
    
    # Skip if already processed
    output_path = EMBEDDINGS_DIR / f"{strand_id}.json"
    if output_path.exists():
        continue
    
    # Build texts to embed
    results = []
    texts_to_embed = []
    
    for et in essential_tweets:
        tweet_id = et['tweet_id']
        annotation = et['annotation']
        tweet_text = parse_tweet_from_thread_text(thread_text, int(tweet_id))
        
        if tweet_text:
            text_to_embed = build_embedding_text(tweet_text, annotation)
            texts_to_embed.append(text_to_embed)
            results.append({
                'tweet_id': tweet_id,
                'annotation': annotation,
                'tweet_text': tweet_text,
                'text_embedded': text_to_embed,
                'embedding': None  # Will be filled
            })
    
    if not texts_to_embed:
        print(f"[WARN] No texts to embed for strand {strand_id}")
        continue
    
    # Get embeddings in batch
    embeddings = get_embeddings_batch(texts_to_embed)
    
    # Attach embeddings to results
    for i, emb in enumerate(embeddings):
        results[i]['embedding'] = emb
    
    # Save to file
    output_data = {
        'seed_tweet_id': strand_id,
        'model': EMBEDDING_MODEL,
        'essential_tweet_embeddings': results
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

print(f"\nDone! Embeddings saved to {EMBEDDINGS_DIR}/")

# %%

# Cell 3: Verify results

embedding_files = list(EMBEDDINGS_DIR.glob("*.json"))
print(f"Total embedding files: {len(embedding_files)}")

# Sample one file to show structure
if embedding_files:
    sample = json.loads(embedding_files[0].read_text())
    print(f"\nSample file: {embedding_files[0].name}")
    print(f"  seed_tweet_id: {sample['seed_tweet_id']}")
    print(f"  model: {sample['model']}")
    print(f"  essential_tweets: {len(sample['essential_tweet_embeddings'])}")
    
    if sample['essential_tweet_embeddings']:
        first = sample['essential_tweet_embeddings'][0]
        print(f"\n  First embedding:")
        print(f"    tweet_id: {first['tweet_id']}")
        print(f"    annotation: {first['annotation'][:80]}...")
        print(f"    embedding dim: {len(first['embedding'])}")
        print(f"    embedding sample: {first['embedding'][:5]}...")

# %%

# Cell 4: UMAP visualization - tweets colored by strand

import numpy as np
import umap
import matplotlib.pyplot as plt

# Load all embeddings
all_embeddings = []
all_strand_ids = []
all_tweet_ids = []
all_annotations = []
all_texts = []

def wrap_text(text: str, width: int = 100) -> str:
    """Insert line breaks every `width` characters for readability."""
    lines = []
    for line in text.split('\n'):
        while len(line) > width:
            # Find a good break point (space) near the width
            break_idx = line.rfind(' ', 0, width)
            if break_idx == -1:
                break_idx = width
            lines.append(line[:break_idx])
            line = line[break_idx:].lstrip()
        lines.append(line)
    return '<br>'.join(lines)

embedding_files = sorted(EMBEDDINGS_DIR.glob("*.json"))
print(f"Loading embeddings from {len(embedding_files)} files...")

for filepath in embedding_files:
    data = json.loads(filepath.read_text())
    strand_id = data['seed_tweet_id']
    
    for item in data['essential_tweet_embeddings']:
        all_embeddings.append(item['embedding'])
        all_strand_ids.append(strand_id)
        all_tweet_ids.append(item['tweet_id'])
        all_annotations.append(item['annotation'][:50] + "...")
        # Add wrapped text for hover
        text_embedded = item.get('text_embedded', item.get('tweet_text', ''))
        all_texts.append(wrap_text(text_embedded))

print(f"Loaded {len(all_embeddings)} embeddings from {len(set(all_strand_ids))} strands")

# Convert to numpy array
X = np.array(all_embeddings)
print(f"Embedding matrix shape: {X.shape}")

# %%

# Run UMAP
print("Running UMAP dimensionality reduction...")
reducer = umap.UMAP(
    n_components=2,
    n_neighbors=15,
    min_dist=0.1,
    metric='cosine',
    random_state=42
)
embedding_2d = reducer.fit_transform(X)
print(f"UMAP output shape: {embedding_2d.shape}")

# %%

# Create color mapping for strands
unique_strands = list(set(all_strand_ids))
strand_to_idx = {s: i for i, s in enumerate(unique_strands)}
colors = [strand_to_idx[s] for s in all_strand_ids]

# Plot
plt.figure(figsize=(14, 10))
scatter = plt.scatter(
    embedding_2d[:, 0], 
    embedding_2d[:, 1], 
    c=colors, 
    cmap='tab20',
    alpha=0.7,
    s=50
)

plt.title(f"UMAP of Essential Tweet Embeddings\n({len(all_embeddings)} tweets from {len(unique_strands)} strands)", fontsize=14)
plt.xlabel("UMAP 1")
plt.ylabel("UMAP 2")

# Add colorbar with strand count
cbar = plt.colorbar(scatter, label="Strand index")

plt.tight_layout()
plt.savefig(DATA_DIR / "essential_tweets_umap.png", dpi=150, bbox_inches='tight')
plt.show()

print(f"\nPlot saved to {DATA_DIR / 'essential_tweets_umap.png'}")

# %%

# Interactive version with hover info (optional)
try:
    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd
    
    df = pd.DataFrame({
        'umap_1': embedding_2d[:, 0],
        'umap_2': embedding_2d[:, 1],
        'strand_id': all_strand_ids,
        'tweet_id': all_tweet_ids,
        'annotation': all_annotations,
        'text': all_texts
    })
    
    fig = px.scatter(
        df, 
        x='umap_1', 
        y='umap_2', 
        color='strand_id',
        hover_data=['tweet_id', 'annotation'],
        custom_data=['text', 'strand_id'],
        title=f"Essential Tweet Embeddings ({len(df)} tweets, {df['strand_id'].nunique()} strands)"
    )
    
    # Custom hover template with embedded text
    fig.update_traces(
        marker=dict(size=8, opacity=0.7),
        hovertemplate="<b>Tweet:</b> %{customdata[0]}<br><br>" +
                      "<b>Strand:</b> %{customdata[1]}<br>" +
                      "<extra></extra>"
    )
    fig.update_layout(width=1200, height=800)
    
    # Save interactive HTML
    fig.write_html(DATA_DIR / "essential_tweets_umap.html")
    print(f"Interactive plot saved to {DATA_DIR / 'essential_tweets_umap.html'}")
    
    fig.show()
except ImportError:
    print("Install plotly for interactive version: pip install plotly")

# %%

# Cell: Diagnose missing tweets (essential tweets not found in thread_text)

print("Checking for missing essential tweets...")
missing_tweets = []

for filepath in sorted(RATED_DIR.glob("*.json")):
    strand = load_rated_strand(filepath)
    strand_id = strand['seed_tweet_id']
    thread_text = strand['thread_text']
    
    for et in strand['rating']['essential_tweets']:
        tweet_id = et['tweet_id']
        # Check if tweet_id exists in thread_text
        if str(tweet_id) not in thread_text:
            missing_tweets.append({
                'strand_id': strand_id,
                'tweet_id': tweet_id,
                'annotation': et['annotation']
            })

if missing_tweets:
    print(f"\nFound {len(missing_tweets)} essential tweets NOT in thread_text (likely LLM hallucinations):\n")
    for m in missing_tweets:
        print(f"Strand: {m['strand_id']}")
        print(f"  Tweet ID: {m['tweet_id']}")
        print(f"  Annotation: {m['annotation'][:100]}...")
        print()
else:
    print("All essential tweets found in their thread_text!")

# %%

# Cell: Compute strand-level UMAP positions for visualization initialization
# Average the embeddings per strand, then UMAP to 2D

print("Computing strand-level UMAP positions...")

# Load all embeddings and group by strand
strand_embeddings = {}  # {strand_id: [embeddings]}

embedding_files = sorted(EMBEDDINGS_DIR.glob("*.json"))
for filepath in embedding_files:
    data = json.loads(filepath.read_text())
    strand_id = data['seed_tweet_id']
    embeddings = [item['embedding'] for item in data['essential_tweet_embeddings']]
    strand_embeddings[strand_id] = embeddings

print(f"Loaded embeddings for {len(strand_embeddings)} strands")

# Compute average embedding per strand
strand_ids = list(strand_embeddings.keys())
avg_embeddings = []

for strand_id in strand_ids:
    embs = strand_embeddings[strand_id]
    avg = np.mean(embs, axis=0)
    avg_embeddings.append(avg)

avg_embeddings = np.array(avg_embeddings)
print(f"Average embedding matrix shape: {avg_embeddings.shape}")

# Run UMAP on the 100 strand-level embeddings
print("Running UMAP on strand-level embeddings...")
strand_reducer = umap.UMAP(
    n_components=2,
    n_neighbors=10,  # Smaller since we only have 100 points
    min_dist=0.3,    # More spread out
    metric='cosine',
    random_state=42
)
strand_positions_2d = strand_reducer.fit_transform(avg_embeddings)
print(f"UMAP output shape: {strand_positions_2d.shape}")

# Scale to reasonable pixel coordinates for visualization
# Target: spread across ~3000x2000 canvas with some margin
x_min, x_max = strand_positions_2d[:, 0].min(), strand_positions_2d[:, 0].max()
y_min, y_max = strand_positions_2d[:, 1].min(), strand_positions_2d[:, 1].max()

# Normalize to [0, 1] then scale
CANVAS_WIDTH = 3500
CANVAS_HEIGHT = 2000
MARGIN = 200

x_scaled = (strand_positions_2d[:, 0] - x_min) / (x_max - x_min) * (CANVAS_WIDTH - 2*MARGIN) + MARGIN
y_scaled = (strand_positions_2d[:, 1] - y_min) / (y_max - y_min) * (CANVAS_HEIGHT - 2*MARGIN) + MARGIN

# Build output: {strand_id: {x, y}}
strand_umap_positions = {}
for i, strand_id in enumerate(strand_ids):
    strand_umap_positions[strand_id] = {
        'x': float(x_scaled[i]),
        'y': float(y_scaled[i]),
        'umap_raw_x': float(strand_positions_2d[i, 0]),
        'umap_raw_y': float(strand_positions_2d[i, 1]),
    }

# Save to JSON
output_path = DATA_DIR / "strand_umap_positions.json"
with open(output_path, 'w') as f:
    json.dump(strand_umap_positions, f, indent=2)

print(f"\nSaved strand UMAP positions to {output_path}")
print(f"Canvas size: {CANVAS_WIDTH}x{CANVAS_HEIGHT}")
print(f"X range: {x_scaled.min():.0f} - {x_scaled.max():.0f}")
print(f"Y range: {y_scaled.min():.0f} - {y_scaled.max():.0f}")

# Quick visualization
plt.figure(figsize=(12, 8))
plt.scatter(x_scaled, y_scaled, c=range(len(strand_ids)), cmap='tab20', s=100, alpha=0.7)
plt.xlabel('X (pixels)')
plt.ylabel('Y (pixels)')
plt.title(f'Strand UMAP Positions ({len(strand_ids)} strands)')
plt.gca().invert_yaxis()  # Invert Y to match screen coordinates
plt.tight_layout()
plt.savefig(DATA_DIR / "strand_umap_positions.png", dpi=150)
plt.show()

# %%

# Cell: Force-directed graph simulation in Python
# Create worm-like strand visualization using NetworkX force layout

import networkx as nx
from scipy.spatial.distance import cosine

print("Building force-directed graph...")

# Load graph data
embedding_files = sorted(EMBEDDINGS_DIR.glob("*.json"))
all_nodes = []
all_embeddings = {}
intra_edges = []
strand_to_nodes = {}

# Build nodes and intra-strand edges
for filepath in embedding_files:
    data = json.loads(filepath.read_text())
    strand_id = data['seed_tweet_id']
    strand_to_nodes[strand_id] = []
    
    for i, tweet in enumerate(data['essential_tweet_embeddings']):
        node_id = tweet['tweet_id']
        all_nodes.append(node_id)
        all_embeddings[node_id] = tweet['embedding']
        strand_to_nodes[strand_id].append(node_id)
        
        # Intra-strand edge to previous tweet
        if i > 0:
            prev_node = data['essential_tweet_embeddings'][i-1]['tweet_id']
            intra_edges.append((prev_node, node_id, {'type': 'intra', 'weight': 2.0}))

print(f"Nodes: {len(all_nodes)}, Intra-strand edges: {len(intra_edges)}")

# Build inter-strand edges (k=3 nearest neighbors)
K = 3
inter_edges = []
node_to_strand = {node: strand for strand, nodes in strand_to_nodes.items() for node in nodes}

print("Computing k-nearest neighbors for inter-strand edges (vectorized)...")

# Create embedding matrix and strand array
embedding_matrix = np.array([all_embeddings[node] for node in all_nodes])
node_strands = np.array([node_to_strand[node] for node in all_nodes])

# Normalize embeddings for cosine similarity
embedding_matrix_norm = embedding_matrix / np.linalg.norm(embedding_matrix, axis=1, keepdims=True)

# Compute all pairwise cosine similarities at once
similarity_matrix = np.dot(embedding_matrix_norm, embedding_matrix_norm.T)

nb_sim_edges = 0
# For each node, find k nearest neighbors from different strands
for i, node in enumerate(all_nodes):
    node_strand = node_to_strand[node]
    
    # Mask out same-strand nodes and self
    same_strand_mask = node_strands == node_strand
    same_strand_mask[i] = True  # Also mask self
    
    # Get similarities for this node
    sims = similarity_matrix[i].copy()
    sims[same_strand_mask] = -np.inf  # Mask out same-strand nodes
    
    # Get top K indices
    top_k_indices = np.argsort(sims)[-K:][::-1]
    
    # Add edges
    for j in top_k_indices:
        if sims[j] != -np.inf:  # Valid neighbor
            other_node = all_nodes[j]
            sim = sims[j]
            inter_edges.append((node, other_node, {'type': 'inter', 'weight': sim if sim > 0.60 else 0.0}))
            if sim > 0.60:
                nb_sim_edges +=1

print(f"Number of inter-strand edges: {nb_sim_edges}")
# %%
print(f"Inter-strand edges: {len(inter_edges)}")

# Create NetworkX graph
G = nx.Graph()
G.add_nodes_from(all_nodes)
G.add_edges_from(intra_edges)
G.add_edges_from(inter_edges)

# Use UMAP positions as initial layout
initial_pos = {}
strand_umap_positions_data = json.loads((DATA_DIR / 'strand_umap_positions.json').read_text())

for strand_id, nodes in strand_to_nodes.items():
    umap_pos = strand_umap_positions_data.get(strand_id, {'x': 1500, 'y': 1000})
    center_x = umap_pos['x']
    center_y = umap_pos['y']
    
    # Spread nodes horizontally around UMAP position
    num_nodes = len(nodes)
    node_spacing = 28
    chain_width = (num_nodes - 1) * node_spacing
    start_x = center_x - chain_width / 2
    
    for i, node in enumerate(nodes):
        initial_pos[node] = np.array([start_x + i * node_spacing, center_y])

print("Running force-directed layout...")

# Run spring layout with custom parameters
# We'll use spring_layout but configure it to match our D3 forces
# k controls the optimal distance between nodes - smaller k = more repulsion
pos = nx.spring_layout(
    G,
    pos=initial_pos,
    k=25.0,  # Increased from 20.0 - larger k = stronger repulsion between nodes
    iterations=200,  # Number of iterations
    weight='weight',  # Use edge weights
    scale=None,  # Don't scale the output
    center=(1750, 1000),  # Center of canvas
    seed=42,
)

print("Layout complete!")

# %%
# Save positions
node_positions = {}
for node, (x, y) in pos.items():
    node_positions[node] = {'x': float(x), 'y': float(y)}

output_path = DATA_DIR / 'force_layout_positions.json'
with open(output_path, 'w') as f:
    json.dump(node_positions, f, indent=2)

print(f"Saved positions to {output_path}")

# %%
# Visualize
fig, ax = plt.subplots(figsize=(16, 10))

# Assign colors by strand
strand_ids = list(strand_to_nodes.keys())
strand_colors = plt.cm.tab20(np.linspace(0, 1, min(20, len(strand_ids))))
node_colors = []
for node in all_nodes:
    strand = node_to_strand[node]
    strand_idx = strand_ids.index(strand) % 20
    node_colors.append(strand_colors[strand_idx])

# Draw inter-strand edges (very faint)
inter_edge_list = [(u, v) for u, v, d in G.edges(data=True) if d.get('type') == 'inter']
nx.draw_networkx_edges(
    G, pos, edgelist=inter_edge_list,
    alpha=0.05, width=0.3, edge_color='gray', ax=ax
)

# Draw intra-strand edges (clear)
intra_edge_list = [(u, v) for u, v, d in G.edges(data=True) if d.get('type') == 'intra']
for u, v in intra_edge_list:
    strand = node_to_strand[u]
    strand_idx = strand_ids.index(strand) % 20
    color = strand_colors[strand_idx]
    x_vals = [pos[u][0], pos[v][0]]
    y_vals = [pos[u][1], pos[v][1]]
    ax.plot(x_vals, y_vals, color=color, alpha=0.8, linewidth=2, zorder=1)

# Draw nodes
xs = [pos[node][0] for node in all_nodes]
ys = [pos[node][1] for node in all_nodes]
ax.scatter(xs, ys, c=node_colors, s=50, alpha=0.9, edgecolors='white', linewidths=0.5, zorder=2)

ax.set_xlim(0, 3500)
ax.set_ylim(0, 2000)
ax.invert_yaxis()
ax.set_aspect('equal')
ax.set_title(f'Force-Directed Strand Graph ({len(all_nodes)} nodes, {len(strand_ids)} strands)', fontsize=14)
ax.axis('off')

plt.tight_layout()
plt.savefig(DATA_DIR / 'force_layout_graph.png', dpi=150, bbox_inches='tight')
plt.show()

print("Visualization saved to force_layout_graph.png")

# %%

# %%

# %%
# Create interactive Plotly version
try:
    import plotly.graph_objects as go
    
    print("\nCreating interactive visualization...")
    
    fig = go.Figure()
    
    # Add inter-strand edges (very faint)
    for u, v, d in G.edges(data=True):
        if d.get('type') == 'inter':
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            fig.add_trace(go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode='lines',
                line=dict(color='lightgray', width=0.3),
                opacity=0.15,
                hoverinfo='skip',
                showlegend=False
            ))
    
    # Add intra-strand edges (colored by strand)
    for strand_id, nodes in strand_to_nodes.items():
        strand_idx = strand_ids.index(strand_id) % 20
        color = f'rgb({int(strand_colors[strand_idx][0]*255)}, {int(strand_colors[strand_idx][1]*255)}, {int(strand_colors[strand_idx][2]*255)})'
        
        edge_x = []
        edge_y = []
        for i in range(len(nodes) - 1):
            u, v = nodes[i], nodes[i+1]
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        if edge_x:
            fig.add_trace(go.Scatter(
                x=edge_x,
                y=edge_y,
                mode='lines',
                line=dict(color=color, width=2),
                opacity=0.8,
                hoverinfo='skip',
                showlegend=False
            ))
    
    # Add nodes (colored by strand)
    for strand_id, nodes in strand_to_nodes.items():
        strand_idx = strand_ids.index(strand_id) % 20
        color = f'rgb({int(strand_colors[strand_idx][0]*255)}, {int(strand_colors[strand_idx][1]*255)}, {int(strand_colors[strand_idx][2]*255)})'
        
        node_x = [pos[node][0] for node in nodes]
        node_y = [pos[node][1] for node in nodes]
        node_text = [f"Tweet: {node}<br>Strand: {strand_id[:8]}..." for node in nodes]
        
        fig.add_trace(go.Scatter(
            x=node_x,
            y=node_y,
            mode='markers',
            marker=dict(
                size=8,
                color=color,
                line=dict(color='white', width=0.5)
            ),
            text=node_text,
            hoverinfo='text',
            showlegend=False
        ))
    
    fig.update_layout(
        title=f'Interactive Force-Directed Strand Graph ({len(all_nodes)} nodes, {len(strand_ids)} strands)',
        width=1400,
        height=900,
        xaxis=dict(range=[0, 3500], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[2000, 0], showgrid=False, zeroline=False, showticklabels=False, scaleanchor='x'),
        plot_bgcolor='white',
        hovermode='closest'
    )
    
    # Save interactive HTML
    fig.write_html(DATA_DIR / 'force_layout_graph_interactive.html')
    print("Interactive visualization saved to force_layout_graph_interactive.html")
    
    fig.show()
    
except ImportError:
    print("Plotly not available for interactive visualization")

# %%
