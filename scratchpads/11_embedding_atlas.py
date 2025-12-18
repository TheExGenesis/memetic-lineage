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


def build_embedding_text(tweet_text: str, annotation: str = None) -> str:
    """Combine tweet text and annotation for embedding."""
    if annotation:
        return f"""Tweet:
{tweet_text}

Annotation:
{annotation}"""
    else:
        return f"""Tweet:
{tweet_text}"""

# %%

# Cell 1: Print text to be embedded for 5 strands

strand_files = sorted(RATED_DIR.glob("*.json"))
print(f"Loading {len(strand_files)} strands...\n")

all_embedding_texts = {}  # {strand_id: [{tweet_id, text_to_embed, annotation, tweet_type}, ...]}

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
            
            # Check if it's the root tweet
            if tweet_id_str == strand_id:
                tweet_type = "root_essential" if tweet_type == "essential" else "root_regular"
            
            strand_embeddings.append({
                'tweet_id': tweet_id_str,
                'annotation': annotation,
                'text_to_embed': text_to_embed,
                'tweet_type': tweet_type
            })

        else:
            print(f"[WARN] Could not find tweet {tweet_id} in thread_text")
    
    all_embedding_texts[strand_id] = strand_embeddings
    print(f"Processed {len(strand_embeddings)} tweets ({len(essential_tweets)} essential, {len(strand_embeddings) - len(essential_tweets)} regular)\n")

# Summary
total_tweets = sum(len(v) for v in all_embedding_texts.values())
essential_count = sum(len([t for t in v if t['tweet_type'] in ['essential', 'root_essential']]) for v in all_embedding_texts.values())
regular_count = total_tweets - essential_count

print(f"\n{'='*80}")
print(f"Total: {len(all_embedding_texts)} strands, {total_tweets} tweets to embed")
print(f"  - Essential tweets: {essential_count}")
print(f"  - Regular tweets: {regular_count}")

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

# Run UMAP
print("Running UMAP projection...")
reducer = umap.UMAP(
    n_components=2,
    n_neighbors=15,
    min_dist=0.1,
    metric='cosine',
    random_state=42,
    verbose=True
)
embedding_2d = reducer.fit_transform(X)

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
