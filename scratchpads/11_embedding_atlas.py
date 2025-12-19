# %%

import json
import re
import requests
from pathlib import Path
from typing import Optional

DATA_DIR = Path("data")
RATED_DIR = DATA_DIR / "rated_strands"
EMBEDDINGS_DIR = DATA_DIR / "all_tweet_embeddings"

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


def extract_all_tweet_ids_from_thread(thread_text: str) -> list[int]:
    """Extract all tweet IDs from thread_text."""
    lines = thread_text.split('\n')
    tweet_ids = []
    
    # Pattern to match tweet headers: optional tree chars, then tweet_id, then space and [
    tweet_header_pattern = re.compile(r'^[│├└─\s]*(\d{15,})\s+\[')
    
    for line in lines:
        match = tweet_header_pattern.match(line)
        if match:
            tweet_id = int(match.group(1))
            tweet_ids.append(tweet_id)
    
    return tweet_ids


def parse_tweet_date_from_thread_text(thread_text: str, tweet_id: int) -> Optional[str]:
    """Extract tweet date from thread_text by tweet_id."""
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')
    
    # Pattern: TWEET_ID [YYYY-MM-DD] @username ...
    date_pattern = re.compile(rf'^[│├└─\s]*{tweet_id_str}\s+\[([0-9-]+)\]')
    
    for line in lines:
        match = date_pattern.match(line)
        if match:
            return match.group(1)
    
    return None


def parse_seed_type_from_thread_text(thread_text: str, tweet_id: int) -> Optional[str]:
    """Extract seed type from thread_text by tweet_id."""
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')
    
    # Find the line containing this tweet_id
    for line in lines:
        if tweet_id_str in line and '[' in line:
            # Pattern: [(SEED) type=TYPE]
            seed_pattern = re.compile(r'\[(SEED)\s+type=([^\]]+)\]')
            match = seed_pattern.search(line)
            if match:
                return match.group(2)  # Return the type part
            break
    
    return None


def parse_likes_retweets_from_thread_text(thread_text: str, tweet_id: int) -> tuple[Optional[int], Optional[int]]:
    """Extract likes and retweets count from thread_text by tweet_id."""
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')
    
    # Pattern: TWEET_ID [DATE] @username 💜 likes 🔁 retweets
    likes_retweets_pattern = re.compile(rf'^[│├└─\s]*{tweet_id_str}\s+\[[^\]]+\]\s+@\w+\s+💜\s+(\d+)\s+🔁\s+(\d+)')
    
    for line in lines:
        match = likes_retweets_pattern.search(line)
        if match:
            likes = int(match.group(1))
            retweets = int(match.group(2))
            return likes, retweets
    
    return None, None


def clean_tweet_text(tweet_text: str) -> str:
    """Clean tweet text for embedding."""
    import re
    
    # First, remove tree connectors and whitespace at start
    text = re.sub(r'^[│├└─\s]+', '', tweet_text, flags=re.MULTILINE)
    text = text.strip()
    
    # Remove all @mentions from the beginning until we hit a non-mention word
    text = re.sub(r'^(@\w+\s*)+', '', text)
    
    # Remove URLs/links (http/https)
    text = re.sub(r'https?://\S+', '', text)
    
    # Remove down arrow (↓) 
    text = re.sub(r'↓', '', text)
    
    # Clean up multiple whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def build_embedding_text(tweet_text: str, annotation: str = None) -> str:
    """Combine tweet text and annotation for embedding."""
    # Clean the tweet text first
    cleaned_text = clean_tweet_text(tweet_text)
    
    # Skip if less than 10 characters after cleaning
    if len(cleaned_text) < 10:
        return None
    
    if annotation:
        return f"""Tweet:
{cleaned_text}

Annotation:
{annotation}"""
    else:
        return f"""Tweet:
{cleaned_text}"""

# %%

# Cell 1: Get all the text to embed for the atlas

strand_files = sorted(RATED_DIR.glob("*.json"))
print(f"Loading {len(strand_files)} strands...\n")

all_embedding_texts = {}  # {strand_id: [{tweet_id, text_to_embed, annotation, tweet_type}, ...]}

for filepath in tqdm(strand_files, desc="Loading strands"):
    strand = load_rated_strand(filepath)
    strand_id = strand['seed_tweet_id']
    thread_text = strand['thread_text']
    essential_tweets = strand['rating']['essential_tweets']

    
    # Extract all tweet IDs from the thread
    all_tweet_ids = extract_all_tweet_ids_from_thread(thread_text)
    print(f"Total tweets in thread: {len(all_tweet_ids)}")
    
    # Create lookup for essential tweets
    essential_lookup = {et['tweet_id']: et['annotation'] for et in essential_tweets}
    
    strand_embeddings = []
    
    for tweet_id in all_tweet_ids:
        tweet_id_str = str(tweet_id)
        
        # Extract tweet text from thread_text
        tweet_text = parse_tweet_from_thread_text(thread_text, tweet_id)
        
        if tweet_text:
            # Determine tweet type and annotation
            if tweet_id_str in essential_lookup:
                tweet_type = "essential"
                annotation = essential_lookup[tweet_id_str]
                text_to_embed = build_embedding_text(tweet_text, annotation)
            else:
                tweet_type = "regular"
                annotation = None
                text_to_embed = build_embedding_text(tweet_text)
            
            # Skip if text is too short after cleaning
            if text_to_embed is None:
                continue
            
            # Check if it's the root tweet
            if tweet_id_str == strand_id:
                tweet_type = "root_essential" if tweet_type == "essential" else "root_regular"
            
            strand_embeddings.append({
                'tweet_id': tweet_id_str,
                'annotation': annotation,
                'original_tweet_text': tweet_text,
                'text_to_embed': text_to_embed,
                'tweet_type': tweet_type
            })

        else:
            print(f"[WARN] Could not find tweet {tweet_id} in thread_text")
    
    all_embedding_texts[strand_id] = strand_embeddings

# Summary
total_tweets = sum(len(v) for v in all_embedding_texts.values())
essential_count = sum(len([t for t in v if t['tweet_type'] in ['essential', 'root_essential']]) for v in all_embedding_texts.values())
regular_count = total_tweets - essential_count

print(f"\n{'='*80}")
print(f"Total: {len(all_embedding_texts)} strands, {total_tweets} tweets to embed")
print(f"  - Essential tweets: {essential_count}")
print(f"  - Regular tweets: {regular_count}")

# %%

# Cell 1.5: Show 100 random cleaned texts
import random

# Gather all text to embed from all strands
all_texts = []
for strand_id, strand_embeddings in all_embedding_texts.items():
    for item in strand_embeddings:
        all_texts.append(item['text_to_embed'])

print(f"Total texts after cleaning: {len(all_texts)}")

# Show 100 random texts
random.seed(42)  # For reproducibility
sample_texts = random.sample(all_texts, min(100, len(all_texts)))

print(f"\n{'='*80}")
print(f"SHOWING {len(sample_texts)} RANDOM CLEANED TEXTS:")
print(f"{'='*80}\n")

for i, text in enumerate(sample_texts, 1):
    print(f"--- {i:3d} ---")
    print(text)
    print()

# %%

# Cell 1.6: Generate embeddings and save results
import os
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv(Path("..") / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-large"  # or "text-embedding-3-large" for higher quality

def get_embeddings_batch(texts: list[str], batch_size: int = 500) -> list[list[float]]:
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

# Create all_tweet_embeddings directory
ALL_EMBEDDINGS_DIR = DATA_DIR / "all_tweet_embeddings"
ALL_EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

print(f"Processing {len(all_embedding_texts)} strands for embedding...")

for strand_id, strand_embeddings in tqdm(all_embedding_texts.items(), desc="Strands"):
    # Skip if already processed
    output_path = ALL_EMBEDDINGS_DIR / f"{strand_id}.json"
    if output_path.exists():
        print(f"[SKIP] {strand_id} already exists")
        continue
    
    if not strand_embeddings:
        print(f"[WARN] No texts to embed for strand {strand_id}")
        continue
    
    # Extract texts to embed
    texts_to_embed = [item['text_to_embed'] for item in strand_embeddings]
    
    # Get embeddings in batch
    print(f"Embedding {len(texts_to_embed)} texts for strand {strand_id}")
    embeddings = get_embeddings_batch(texts_to_embed)
    
    # Build results with embeddings
    results = []
    for i, item in enumerate(strand_embeddings):
        results.append({
            'tweet_id': item['tweet_id'],
            'annotation': item['annotation'],
            'tweet_text': clean_tweet_text(item['original_tweet_text']),
            'text_embedded': item['text_to_embed'],
            'tweet_type': item['tweet_type'],
            'embedding': embeddings[i]
        })
    
    # Save to file
    output_data = {
        'seed_tweet_id': strand_id,
        'model': EMBEDDING_MODEL,
        'all_tweet_embeddings': results
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

print(f"\nDone! Embeddings saved to {ALL_EMBEDDINGS_DIR}/")

# %%

# Cell 2: Load embeddings from all_tweet_embeddings folder and create UMAP + parquet for embedding-atlas
import numpy as np
import pandas as pd
import umap
from tqdm import tqdm

# Load all embeddings from the saved JSON files
print("Loading embeddings from all_tweet_embeddings folder...")

# First, load all rated strands to get thread_text for date/seed type parsing
print("Loading rated strands for metadata extraction...")
rated_strands = {}
for strand_file in tqdm(RATED_DIR.glob("*.json"), desc="Loading rated strands"):
    strand = load_rated_strand(strand_file)
    strand_id = strand['seed_tweet_id']
    rated_strands[strand_id] = strand

all_embeddings = []
all_metadata = []

embedding_files = sorted(EMBEDDINGS_DIR.glob("*.json"))
print(f"Found {len(embedding_files)} embedding files")

for filepath in tqdm(embedding_files, desc="Loading embeddings"):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    strand_id = data['seed_tweet_id']
    strand_data = rated_strands.get(strand_id)
    thread_text = strand_data['thread_text'] if strand_data else None
    
    # Handle both old and new format
    if 'all_tweet_embeddings' in data:
        embeddings_data = data['all_tweet_embeddings']
    else:
        # Old format fallback
        embeddings_data = data['essential_tweet_embeddings']
    
    for item in embeddings_data:
        # Extract embedding vector
        embedding = item['embedding']
        all_embeddings.append(embedding)
        
        # Parse tweet date, seed type, likes and retweets
        tweet_id = int(item['tweet_id']) if item['tweet_id'].isdigit() else None
        tweet_date = None
        seed_type = None
        likes = None
        retweets = None
        
        if thread_text and tweet_id:
            tweet_date = parse_tweet_date_from_thread_text(thread_text, tweet_id)
            seed_type = parse_seed_type_from_thread_text(thread_text, tweet_id)
            likes, retweets = parse_likes_retweets_from_thread_text(thread_text, tweet_id)
        
        # Extract metadata
        all_metadata.append({
            'tweet_id': item['tweet_id'],
            'strand_id': strand_id,
            'annotation': item.get('annotation', '') or '',
            'tweet_type': item.get('tweet_type', 'unknown'),
            'text': item.get('text_embedded', item.get('tweet_text', '')),
            'date': tweet_date,
            'seed_type': seed_type,
            'likes': likes,
            'retweets': retweets
        })

print(f"Loaded {len(all_embeddings)} embeddings from {len(embedding_files)} files")

# Convert to numpy array for UMAP
X = np.array(all_embeddings)
print(f"Embedding matrix shape: {X.shape}")
# %%
# Choose projection method: 'umap', 'tsne', or 'pacmap'
projection_method = 'umap'

if projection_method == 'umap':
    print("Running UMAP projection...")
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=10,
        min_dist=0.1,
        random_state=42,
        verbose=True,
    )
    embedding_2d = reducer.fit_transform(X)
elif projection_method == 'tsne':
    print("Running t-SNE projection...")
    from sklearn.manifold import TSNE
    reducer = TSNE(
        n_components=2,
        perplexity=10,          # Controls local vs global structure (5-50 typical)
        learning_rate=200,      # Higher = faster convergence (10-1000 typical)
        n_iter=1000,           # Number of iterations
        random_state=42,
        verbose=1
    )
    embedding_2d = reducer.fit_transform(X)
elif projection_method == 'pacmap':
    print("Running PaCMAP projection...")
    import pacmap
    reducer = pacmap.PaCMAP(
        n_components=2,
        n_neighbors=10,         # Number of neighbors to consider
        MN_ratio=0.5,          # Mid-near point ratio (0.5 = balanced)
        FP_ratio=2.0,          # Further point ratio (2.0 = good separation)
        random_state=42
    )
    # PaCMAP recommends PCA initialization for better results
    embedding_2d = reducer.fit_transform(X, init="pca")

# Create DataFrame with all data
print("Creating DataFrame...")
df = pd.DataFrame(all_metadata)
df['projection_x'] = embedding_2d[:, 0]
df['projection_y'] = embedding_2d[:, 1]

# Add some additional useful columns
df['is_essential'] = df['tweet_type'].isin(['essential', 'root_essential'])
df['is_root'] = df['tweet_type'].isin(['root_essential', 'root_regular'])

print(f"DataFrame shape: {df.shape}")
print(f"Columns: {list(df.columns)}")

# Show tweet type distribution
print(f"\nTweet type distribution:")
print(df['tweet_type'].value_counts())

# Show data completeness
print(f"\nData completeness:")
print(f"Tweets with dates: {df['date'].notna().sum()}/{len(df)} ({df['date'].notna().sum()/len(df)*100:.1f}%)")
print(f"Tweets with seed types: {df['seed_type'].notna().sum()}/{len(df)} ({df['seed_type'].notna().sum()/len(df)*100:.1f}%)")
print(f"Tweets with likes/retweets: {df['likes'].notna().sum()}/{len(df)} ({df['likes'].notna().sum()/len(df)*100:.1f}%)")

# Show seed type distribution
if df['seed_type'].notna().sum() > 0:
    print(f"\nSeed type distribution:")
    print(df['seed_type'].value_counts())

# Save as parquet for embedding-atlas
output_parquet = DATA_DIR / "tweet_embeddings_atlas.parquet"
df.to_parquet(output_parquet, index=False)
print(f"\nSaved parquet file: {output_parquet}")

# Show sample of the data
print("\nSample data:")
print(df[['tweet_id', 'strand_id', 'tweet_type', 'date', 'likes', 'retweets', 'seed_type']].head())

print(f"\nTo visualize with embedding-atlas, run:")
print(f"uvx embedding-atlas {output_parquet} --x projection_x --y projection_y --text text")

# %%

# Cell 3: Import parquet and create plotly scatter plot
import plotly.graph_objects as go
import plotly.express as px

# Load the parquet file
parquet_path = DATA_DIR / "tweet_embeddings_atlas.parquet"
df_viz = pd.read_parquet(parquet_path)

print(f"Loaded {len(df_viz)} points from parquet")

# Create scatter plot with plotly, colored by strand_id
fig = go.Figure()

fig.add_trace(go.Scattergl(
    x=df_viz['projection_x'],
    y=df_viz['projection_y'],
    mode='markers',
    marker=dict(
        color=df_viz['strand_id'].astype('category').cat.codes,
        colorscale='viridis',
        size=6,
        opacity=0.7,
        showscale=True,
        colorbar=dict(title="Strand ID")
    ),
    text=df_viz['text'],
    hovertemplate='<b>%{text}</b><br>' +
                 'Tweet ID: %{customdata[0]}<br>' +
                 'Strand ID: %{customdata[1]}<br>' +
                 'Type: %{customdata[2]}<br>' +
                 'Date: %{customdata[3]}<br>' +
                 'Likes: %{customdata[4]}<br>' +
                 'Retweets: %{customdata[5]}<br>' +
                 '<extra></extra>',
    customdata=df_viz[['tweet_id', 'strand_id', 'tweet_type', 'date', 'likes', 'retweets']].values,
    showlegend=False
))

method_name = projection_method.upper()
fig.update_layout(
    title=f'Tweet Embeddings {method_name} Projection (Colored by Strand ID)',
    xaxis_title=f'{method_name} Dimension 1',
    yaxis_title=f'{method_name} Dimension 2',
    width=1000,
    height=700,
    dragmode='pan'
)

# Configure scroll wheel zoom
config = {
    'scrollZoom': True,
    'displayModeBar': True,
    'toImageButtonOptions': {
        'format': 'png',
        'filename': 'tweet_embeddings_umap',
        'height': 700,
        'width': 1000,
        'scale': 1
    }
}

fig.show(config=config)

# %%
