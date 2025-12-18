# %%

import json
import re
import requests
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
    
    # Extract all tweet IDs from the thread
    all_tweet_ids = extract_all_tweet_ids_from_thread(thread_text)
    
    # Create lookup for essential tweets
    essential_lookup = {et['tweet_id']: et['annotation'] for et in essential_tweets}
    
    # Build texts to embed
    results = []
    texts_to_embed = []
    
    for tweet_id in all_tweet_ids:
        tweet_id_str = str(tweet_id)
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
            
            texts_to_embed.append(text_to_embed)
            results.append({
                'tweet_id': tweet_id_str,
                'annotation': annotation,
                'tweet_text': tweet_text,
                'text_embedded': text_to_embed,
                'tweet_type': tweet_type,
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
        'all_tweet_embeddings': results  # Renamed from 'essential_tweet_embeddings'
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
    
    # Handle both old and new format
    if 'all_tweet_embeddings' in sample:
        embeddings = sample['all_tweet_embeddings']
        print(f"  all_tweets: {len(embeddings)}")
        
        # Count by type
        type_counts = {}
        for emb in embeddings:
            tweet_type = emb.get('tweet_type', 'unknown')
            type_counts[tweet_type] = type_counts.get(tweet_type, 0) + 1
        
        print(f"  tweet types: {dict(type_counts)}")
        
    else:
        # Old format fallback
        embeddings = sample['essential_tweet_embeddings']
        print(f"  essential_tweets: {len(embeddings)}")
    
    if embeddings:
        first = embeddings[0]
        print(f"\n  First embedding:")
        print(f"    tweet_id: {first['tweet_id']}")
        print(f"    tweet_type: {first.get('tweet_type', 'N/A')}")
        annotation = first.get('annotation')
        if annotation:
            print(f"    annotation: {annotation[:80]}...")
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
    
    # Handle both old and new format
    if 'all_tweet_embeddings' in data:
        embeddings = data['all_tweet_embeddings']
    else:
        # Old format fallback
        embeddings = data['essential_tweet_embeddings']
    
    for item in embeddings:
        all_embeddings.append(item['embedding'])
        all_strand_ids.append(strand_id)
        all_tweet_ids.append(item['tweet_id'])
        all_annotations.append(item.get('annotation', 'No annotation'))
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

# Cell: Generate strand titles using Groq
from groq import Groq

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_strand_title(tweet_texts_and_annotations: list[tuple[str, str]], strand_id: str) -> str:
    """Generate a concise title for a strand based on tweet texts and annotations."""
    
    # Build content for the prompt
    content_parts = []
    for i, (tweet_text, annotation) in enumerate(tweet_texts_and_annotations, 1):
        content_parts.append(f"Tweet {i}:")
        content_parts.append(f"Text: {tweet_text[:2000]}...")
        content_parts.append(f"Annotation: {annotation}")
        content_parts.append("")
    
    content = "\n".join(content_parts)
    
    system_prompt = """You are a content curator. Given a collection of tweets and their annotations from a Twitter thread, generate a concise title that captures the main theme or topic. The title should be 3 words or less and capture the essence of what this thread is about.

Focus on the juice of the topic, use the words from the tweets, not generic terms. Simply output the title, no formatting or punctuation. Don't think for very long."""

    user_prompt = f"""Here are the essential tweets and annotations from a Twitter thread:

{content}

Generate a title for this thread in 3 words or less that captures its main theme:"""

    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=500
        )
        print(f"User prompt: {user_prompt}")
        print(f"Completion: {completion.choices[0]}")
        title = completion.choices[0].message.content
        print(f"Title: {title}")
        # Clean up title - remove quotes, periods, etc.
        title = title.strip('"\'.,!?')
        return title
        
    except Exception as e:
        print(f"Error generating title for strand {strand_id}: {e}")
        return "Thread"

# Generate titles for all strands
print("Generating titles for strands...")
strand_titles = {}

# Group tweets by strand
strands_content = {}
for i, (tweet_id, strand_id, text) in enumerate(zip(all_tweet_ids, all_strand_ids, all_texts)):
    if strand_id not in strands_content:
        strands_content[strand_id] = []
    
    # Get annotation for this tweet
    annotation = all_annotations[i]
    # Remove <br> tags and clean up text
    clean_text = text.replace('<br>', ' ').strip()
    strands_content[strand_id].append((clean_text, annotation))

# Generate titles
for strand_id, content_list in list(strands_content.items()):
    print(f"Generating title for strand {strand_id}...")
    title = generate_strand_title(content_list, strand_id)
    strand_titles[strand_id] = title
    print(f"  → {title}")

print(f"\nGenerated {len(strand_titles)} strand titles")


# %%


# %%

# Cell: Get embedding from Qdrant database by tweet ID

import sys
import requests
sys.path.append('../')  # Add parent directory to path for lib imports

try:
    from lib.semantic_search import _search_embeddings_request
    print("Using existing search functions from lib")
except ImportError:
    print("Creating standalone search function...")
    
    def _search_embeddings_request(payload: dict) -> dict:
        """Make the HTTP request to search API. Raises on failure."""
        url = 'http://embed.tweetstack.app/embeddings/'
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        response.raise_for_status()
        return response.json()


def get_embedding_by_tweet_id(tweet_id: str) -> Optional[dict]:
    """
    Retrieve embedding from Qdrant database by tweet ID.
    
    Args:
        tweet_id: The tweet ID to search for
        
    Returns:
        Dictionary with embedding data if found, None otherwise
        Format: {
            'key': str,
            'vector': list[float],
            'metadata': dict
        }
    """
    # Try to get the embedding by filtering for the specific tweet_id
    # We'll use an empty search term and filter by tweet_id
    payload = {
        'searchTerm': '',  # Empty search term
        'k': 1,  # Only need one result
        'threshold': 0.0,  # Accept any distance since we're looking for exact match
        'filter': {
            'must': [
                {
                    'key': 'tweet_id',
                    'match': {'value': tweet_id}
                }
            ]
        }
    }
    
    try:
        print(f"Searching for tweet_id: {tweet_id}")
        response = _search_embeddings_request(payload)
        
        if not response.get('success'):
            print(f"API returned success=False: {response}")
            return None
            
        results = response.get('results', [])
        if not results:
            print(f"No results found for tweet_id: {tweet_id}")
            return None
            
        # Get the first result
        result = results[0]
        print(f"Found embedding for tweet_id: {tweet_id}")
        print(f"  Key: {result.get('key')}")
        print(f"  Distance: {result.get('distance')}")
        print(f"  Metadata keys: {list(result.get('metadata', {}).keys())}")
        
        return {
            'key': result.get('key'),
            'distance': result.get('distance'),
            'metadata': result.get('metadata', {}),
            # Note: The search API doesn't return the actual vector, just similarity results
        }
        
    except Exception as e:
        print(f"Error retrieving embedding for tweet_id {tweet_id}: {e}")
        return None


# First, let's explore the API endpoints
print("Exploring embeddings API endpoints...")

def test_embeddings_api():
    """Test different endpoints to understand the API structure."""
    base_url = 'http://embed.tweetstack.app'
    
    endpoints_to_test = [
        '/embeddings/',
        '/embeddings',
        '/embeddings/keys',
        '/embeddings/metadata'
    ]
    
    for endpoint in endpoints_to_test:
        try:
            print(f"\nTesting GET {endpoint}")
            response = requests.post(f"{base_url}{endpoint}", timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"List length: {len(data)}")
                        if data:
                            print(f"First item: {data[0]}")
                    else:
                        print(f"Response: {data}")
                except:
                    text = response.text[:200]
                    print(f"Response (text): {text}...")
            else:
                print(f"Error: {response.text[:100]}")
                
        except requests.RequestException as e:
            print(f"Request failed: {e}")

test_embeddings_api()

# Test with one tweet ID from our data
print("\n" + "="*60)
print("Testing embedding retrieval from Qdrant...")

# Get a tweet ID from our processed data to test with
if 'all_tweet_ids' in locals() and all_tweet_ids:
    test_tweet_id = "1486704973840855041"
    print(f"\nTesting with tweet_id: {test_tweet_id}")
    
    result = get_embedding_by_tweet_id(test_tweet_id)
    
    if result:
        print(f"\n✓ Successfully retrieved embedding!")
        print(f"Key: {result['key']}")
        print(f"Distance: {result['distance']}")
        print(f"Metadata: {result['metadata']}")
    else:
        print(f"\n✗ Could not retrieve embedding for tweet_id: {test_tweet_id}")
        print("This might mean:")
        print("- The tweet is not in the Qdrant database")
        print("- The metadata field name is different")
        print("- The API endpoint structure is different")
else:
    print("No tweet IDs available for testing. Run the previous cells first.")

# %%

# %%

# MANUAL EXPORT CELL - Run this after reviewing plots above
# Exports UMAP positions with metadata for frontend visualization

def export_umap_positions(
    embedding_2d,
    all_tweet_ids,
    all_strand_ids,
    all_texts,
    all_annotations,
    output_path=None
):
    """
    Export UMAP positions to JSON for frontend.
    Includes position relaxation to avoid overlaps and space for envelopes.
    """
    if output_path is None:
        output_path = Path("../top-qt-website/bangers/public/umap_tweets.json")
    
    print("Preparing export data...")
    
    # Load rated strands for metadata
    rated_cache = {}
    for rf in RATED_DIR.glob("*.json"):
        rated_cache[rf.stem] = load_rated_strand(rf)
    
    def has_image_in_thread(strand_id: str, tweet_id: str) -> bool:
        s = rated_cache.get(str(strand_id))
        if not s:
            return False
        tid = str(tweet_id)
        lines = s['thread_text'].split('\n')
        found = False
        for i, l in enumerate(lines):
            if tid in l:
                found = True
            if found:
                window = lines[i:i+8]
                if any(x.strip().startswith('Images:') for x in window):
                    return True
                if any(x.strip().startswith('[Image #') for x in window):
                    return True
                break
        return False
    
    # Normalize UMAP coords to [0,1]
    x_min, x_max = embedding_2d[:, 0].min(), embedding_2d[:, 0].max()
    y_min, y_max = embedding_2d[:, 1].min(), embedding_2d[:, 1].max()
    norm_x = (embedding_2d[:, 0] - x_min) / (x_max - x_min + 1e-9)
    norm_y = (embedding_2d[:, 1] - y_min) / (y_max - y_min + 1e-9)
    
    # Relax positions to avoid overlaps
    print("Relaxing positions to avoid overlaps...")
    pts = list(zip(norm_x, norm_y))
    
    def relax_positions(points, min_dist=0.02, iterations=300, step=0.4):
        pts = np.array(points)
        n = len(pts)
        
        # Pre-calculate tweet types for distance adjustments
        is_root = np.array([str(all_tweet_ids[i]) == str(all_strand_ids[i]) for i in range(n)])
        has_image = np.array([has_image_in_thread(str(all_strand_ids[i]), str(all_tweet_ids[i])) for i in range(n)])
        
        for iteration in range(iterations):
            if iteration % 10 == 0:
                print(f"Iteration {iteration} of {iterations}")
            
            # Vectorized distance calculation
            diff = pts[:, np.newaxis, :] - pts[np.newaxis, :, :]  # (n, n, 2)
            dist_sq = np.sum(diff**2, axis=2)  # (n, n)
            
            # Avoid division by zero
            dist_sq = np.maximum(dist_sq, 1e-6)
            dist = np.sqrt(dist_sq)
            
            # Calculate dynamic minimum distances based on tweet types
            base_dist_matrix = np.full((n, n), min_dist)
            
            # Special tweet multiplier (same for root and image tweets)
            special_multiplier = 1.
            special_mask = (has_image[:, np.newaxis]) | (has_image[np.newaxis, :])
            base_dist_matrix[special_mask] *= special_multiplier
            
            # Zero out diagonal to ignore self-interactions
            np.fill_diagonal(base_dist_matrix, 0)
            np.fill_diagonal(dist, np.inf)
            
            # Calculate repulsion forces
            overlap_mask = dist < base_dist_matrix
            push_strength = np.zeros_like(dist)
            push_strength[overlap_mask] = (base_dist_matrix[overlap_mask] - dist[overlap_mask]) / dist[overlap_mask]
            
            # Force vectors
            force_x = np.sum(diff[:, :, 0] * push_strength, axis=1)
            force_y = np.sum(diff[:, :, 1] * push_strength, axis=1)
            
            # Apply forces
            displacement = np.column_stack([force_x, force_y]) * step
            pts += displacement
            
            # Check convergence
            total_movement = np.sum(np.abs(displacement))
            if total_movement < 1e-6:
                print(f"Converged at iteration {iteration}")
                break
        
        return [(x, y) for x, y in pts]
    
    relaxed_pts = relax_positions(pts)
    
    # Add padding
    pad = 0.03
    relaxed_pts = [(
        pad + (1 - 2*pad) * x,
        pad + (1 - 2*pad) * y
    ) for x, y in relaxed_pts]
    
    # Build output records
    records = []
    for i, (x, y) in enumerate(relaxed_pts):
        tid = str(all_tweet_ids[i])
        sid = str(all_strand_ids[i])
        rated = rated_cache.get(sid)
        
        records.append({
            'tweet_id': tid,
            'strand_id': sid,
            'umap_x': float(x),
            'umap_y': float(y),
            'has_image': has_image_in_thread(sid, tid),
            'is_root': tid == sid,
            'media_url': None,  # Fallback; frontend will use if missing
            'text_snippet': all_texts[i].replace('<br>', ' '),
            'annotation': all_annotations[i],
            'username': rated.get('seedTweet', {}).get('username') if rated else None,
            'avatar_media_url': rated.get('seedTweet', {}).get('avatar_media_url') if rated else None,
            'strand_title': strand_titles.get(sid, '')
        })
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({'points': records}, f, indent=2)
    
    print(f"✓ Exported {len(records)} tweet positions to {output_path}")
    return records

# %%
# Uncomment and run this cell after viewing plots:
exported = export_umap_positions(embedding_2d, all_tweet_ids, all_strand_ids, all_texts, all_annotations)

# %%

# Plot the exported (relaxed) positions
def plot_relaxed_positions(records):
    """Visualize the relaxed tweet positions colored by strand."""
    import matplotlib.pyplot as plt
    
    # Extract data
    xs = [r['umap_x'] for r in records]
    ys = [r['umap_y'] for r in records]
    strand_ids = [r['strand_id'] for r in records]
    
    # Color mapping
    unique_strands = sorted(set(strand_ids))
    strand_to_idx = {s: i for i, s in enumerate(unique_strands)}
    colors = [strand_to_idx[s] for s in strand_ids]
    
    # Plot
    fig, ax = plt.subplots(figsize=(14, 10))
    scatter = ax.scatter(
        xs, ys,
        c=colors,
        cmap='tab20',
        alpha=0.7,
        s=60,
        edgecolors='white',
        linewidths=0.5
    )
    
    # Highlight root tweets
    root_xs = [r['umap_x'] for r in records if r['is_root']]
    root_ys = [r['umap_y'] for r in records if r['is_root']]
    ax.scatter(root_xs, root_ys, s=120, facecolors='none', edgecolors='black', linewidths=2, alpha=0.8, label='Root tweets')
    
    # Highlight tweets with images
    img_xs = [r['umap_x'] for r in records if r['has_image']]
    img_ys = [r['umap_y'] for r in records if r['has_image']]
    ax.scatter(img_xs, img_ys, s=40, marker='s', facecolors='none', edgecolors='red', linewidths=1, alpha=0.6, label='Has image')
    
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_aspect('equal')
    ax.set_xlabel('X (normalized & relaxed)')
    ax.set_ylabel('Y (normalized & relaxed)')
    ax.set_title(f'Relaxed Tweet Positions\n({len(records)} tweets, {len(unique_strands)} strands)', fontsize=14)
    ax.legend(loc='upper right')
    ax.grid(alpha=0.2)
    
    plt.tight_layout()
    plt.savefig(DATA_DIR / "essential_tweets_relaxed.png", dpi=150, bbox_inches='tight')
    plt.show()
    
    print(f"Plot saved to {DATA_DIR / 'essential_tweets_relaxed.png'}")
    print(f"Root tweets: {len(root_xs)}, Tweets with images: {len(img_xs)}")

# Uncomment to plot after export:
plot_relaxed_positions(exported)

# %%
