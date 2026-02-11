# %%
"""
Relation Genesis Analysis - LLM analysis of pair first interactions

Analyzes how relationships formed: initiation patterns, dynamics, catalysts.
Uses Groq API with moonshotai/kimi-k2-instruct-0905 for structured output.
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional
from enum import Enum

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field

# Handle notebook vs script context
try:
    SCRATCHPADS_DIR = Path(__file__).parent
except NameError:
    SCRATCHPADS_DIR = Path.cwd()
    if SCRATCHPADS_DIR.name != 'scratchpads':
        SCRATCHPADS_DIR = SCRATCHPADS_DIR / 'scratchpads'

if str(SCRATCHPADS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCHPADS_DIR))

# Import directly to avoid pulling in heavy dependencies
from lib.parallel import parallel_map_to_dict  # noqa: E402

load_dotenv(SCRATCHPADS_DIR.parent / ".env")

# %%
# === Configuration ===

PAIR_SAMPLES_DIR = SCRATCHPADS_DIR / "data" / "pair_samples"
OUTPUT_DIR = SCRATCHPADS_DIR / "data" / "pair_genesis_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "openai/gpt-oss-120b"
MAX_WORKERS = 2  # Conservative for rate limits


# %%
# === Tag Definitions ===

class GenesisTag(str, Enum):
    # Connection Origin
    IN_PERSON_EVENT = "in_person_event"
    MATCHMAKER = "matchmaker"
    RANDOM_REPLY = "random_reply"
    QUOTE_TWEET_BOOST = "quote_tweet_boost"
    
    # Initiation Pattern
    ASYMMETRIC_PURSUIT = "asymmetric_pursuit"
    LONG_LURK_FIRST_REPLY = "long_lurk_first_reply"
    
    # Interaction Energy
    PLAYFUL_BANTER = "playful_banter"
    INTELLECTUAL_RIFF = "intellectual_riff"
    MENTORSHIP_VIBE = "mentorship_vibe"
    SUPPORTIVE_HYPE = "supportive_hype"
    
    # Context
    GEOGRAPHIC_HINT = "geographic_hint"
    
    # Outcome
    FERTILE = "fertile"
    
    # Temporal Shape
    SLOW_BURN = "slow_burn"
    INSTANT_CLICK = "instant_click"


TAG_DESCRIPTIONS = {
    "in_person_event": "Reference to meeting IRL (conference, party, city)",
    "matchmaker": "Third person visibly introduced them",
    "random_reply": "Met through reply on someone else's viral thread (neither is the OP)",
    "quote_tweet_boost": "One person QT'd the other to amplify/introduce them",
    "asymmetric_pursuit": "One person clearly reached out first/repeatedly",
    "long_lurk_first_reply": "First interaction after apparent long follow period",
    "playful_banter": "Jokes, memes, light teasing",
    "intellectual_riff": "Building on ideas, substantive back-and-forth",
    "mentorship_vibe": "Clear senior/junior dynamic",
    "supportive_hype": "Encouragement, celebration of each other",
    "geographic_hint": "Mentions of same city/region suggest offline proximity. E.g. inviting someone to a local event, mentioning a local landmark, etc.",
    "fertile": "Something emerged: ongoing intellectual engagement, project, collaboration",
    "slow_burn": "Relationship developed gradually over months",
    "instant_click": "High-frequency engagement from first interaction",
}


# %%
# === Pydantic Models ===

class RelationshipGenesis(BaseModel):
    """Structured analysis of how a relationship formed."""
    
    # Core narrative
    genesis_narrative: str = Field(
        description="2-3 sentences on HOW they connected - the process, not the content. "
                    "Focus on dynamics: who initiated, was it symmetric, what sparked it."
                    "If you see a long history of asymetrical interactions, assume that you only see one side of a conversation. Flag this in the summary."
    )

    neutral_genesis_narrative: str = Field(
        description="2-3 sentences on HOW they connected - the process, not the content. Same as genesis_narrative, but without mentioning any names, handles or usernames, or any specific details about the conversation."
    )

    missing_data_score: int = Field(
        ge=1, le=5,
        description="How likely is it that some tweets are missing from the thread you observe? (e.g. broken conversation trees, long assymetrical interactions). 1=series of tweets from one user that seem to respond to missing tweets of the other user, 5=several chains of tweets from both sides. You should use the extreme of the spectrum to score this. There should be little 3."
    )
    
    # Initiation
    initiator: Literal["person_a", "person_b", "mutual", "unclear"] = Field(
        description="Who initiated the relationship. person_a is the first handle in the pair."
    )
    
    # Dynamics
    symmetry_score: int = Field(
        ge=1, le=5,
        description="1=very asymmetric (one-sided), 5=perfectly balanced exchange"
    )
    
    interaction_energy: Literal[
        "playful", "intellectual", "supportive", "transactional", "mixed"
    ] = Field(
        description="Primary vibe of their interactions"
    )
    
    # Tags
    tags: list[str] = Field(
        description="Tags from the taxonomy that apply to this relationship"
    )
    
    # Confidence
    confidence: Literal["high", "medium", "low"] = Field(
        description="How much signal is in the data to make these judgments"
    )



class PairAnalysisResult(BaseModel):
    """Full result including metadata."""
    pair_id: str
    person_a: str
    person_b: str
    first_interaction_date: str  # ISO format
    total_interactions: int
    analysis: RelationshipGenesis


# %%
# === Prompt ===

SYSTEM_PROMPT = f"""You are analyzing the genesis of Twitter relationships - how two people first connected and what their early dynamics were like.

You will receive a file showing the first interactions between two Twitter users. Your job is to analyze:
1. HOW they connected (the process, not the content)
2. Who initiated and whether it was symmetric
3. What kind of energy characterized their early exchanges
4. Any contextual clues about how they found each other

## Important Note:
The data is not exhaustive. Some users are not consistently part of the dataset (e.g. only a few tweets but not the bulk of their tweets). When you see a long history of asymetrical interactions, assume that you only see one side of a conversation. Flag this in the summary. Update your confidence accordingly.

## Available Tags (only use these):
{chr(10).join(f'- {tag}: {desc}' for tag, desc in TAG_DESCRIPTIONS.items())}

## Important Guidelines:
- Focus on the PROCESS of connection, not the topics they discussed
- Take into account the number of interactions and the time between the first and last interaction. Most relationships are likely to be minors, one-off exchanges. Your response should reflect this, e.g. intellectual_riff is not a good tag if there are only 2-3 interactions.
- Look for signals: who replied first, response times, tone shifts
- "random_reply" means they met on someone ELSE's viral thread (neither is the author)
- "fertile" means something substantive emerged (intellectual partnership, projects, etc.)
- Be conservative with tags - only apply if there's clear evidence
- If data is sparse, say confidence is "low"

Output valid JSON matching the schema."""


# %%
# === File Parsing ===

def parse_pair_file(file_path: Path) -> dict:
    """Extract metadata and content from a pair file."""
    content = file_path.read_text()
    
    # Extract pair handles from filename
    # Format: pair_handle1_handle2.txt
    filename = file_path.stem
    parts = filename.replace("pair_", "").split("_")
    
    # Handle edge cases with underscores in handles
    # Try to find the split point by looking at the content
    header_match = re.search(r'PAIR: @(\S+) <-> @(\S+)', content)
    if header_match:
        person_a = header_match.group(1)
        person_b = header_match.group(2)
    else:
        # Fallback: split in half
        mid = len(parts) // 2
        person_a = "_".join(parts[:mid])
        person_b = "_".join(parts[mid:])
    
    # Extract total interactions
    interactions_match = re.search(r'Total interactions: (\d+)', content)
    total_interactions = int(interactions_match.group(1)) if interactions_match else 0
    
    # Extract first interaction date
    # Look for date patterns like [2025-03-02] or 2025-03-02
    date_matches = re.findall(r'\[?(\d{4}-\d{2}-\d{2})\]?', content)
    first_date = min(date_matches) if date_matches else "unknown"
    
    return {
        "pair_id": filename,
        "person_a": person_a,
        "person_b": person_b,
        "total_interactions": total_interactions,
        "first_interaction_date": first_date,
        "content": content,
    }


# %%
# === Groq Client ===

def get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    return Groq(api_key=api_key)


CLIENT = get_groq_client()


# %%
# === Analysis Function ===

def analyze_pair(file_path: Path) -> PairAnalysisResult:
    """Analyze a single pair file and return structured result."""
    
    # Check cache first
    cache_path = OUTPUT_DIR / f"{file_path.stem}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
            return PairAnalysisResult.model_validate(data)
    
    # Parse file
    parsed = parse_pair_file(file_path)
    
    # Truncate content if too long (keep first ~15k chars)
    content = parsed["content"]
    if len(content) > 150000:
        content = content[:150000] + "\n\n[... truncated for length ...]"
    
    # Call Groq
    response = CLIENT.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.3,
        reasoning_effort="medium",
        max_tokens=2048,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "relationship_genesis",
                "schema": RelationshipGenesis.model_json_schema()
            }
        }
    )
    
    raw_response = response.choices[0].message.content
    
    # Parse response
    try:
        analysis_data = json.loads(raw_response)
        analysis = RelationshipGenesis.model_validate(analysis_data)
    except Exception as e:
        raise ValueError(f"Failed to parse LLM response: {e}\nRaw: {raw_response[:500]}")
    
    # Build result
    result = PairAnalysisResult(
        pair_id=parsed["pair_id"],
        person_a=parsed["person_a"],
        person_b=parsed["person_b"],
        first_interaction_date=parsed["first_interaction_date"],
        total_interactions=parsed["total_interactions"],
        analysis=analysis,
    )
    
    # Cache result
    with open(cache_path, "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    
    return result


# %%
# === Main Processing ===

def get_all_pair_files() -> list[Path]:
    """Get all pair files from the samples directory."""
    return sorted(PAIR_SAMPLES_DIR.glob("pair_*.txt"))


def get_interaction_count(file_path: Path) -> int:
    """Quick extraction of interaction count from file header."""
    with open(file_path) as f:
        # Only read first 500 chars to find the header
        header = f.read(500)
    match = re.search(r'Total interactions: (\d+)', header)
    return int(match.group(1)) if match else 0


def get_all_pair_files_sorted_by_interactions() -> list[tuple[Path, int]]:
    """Get all pair files sorted by interaction count (descending)."""
    files = get_all_pair_files()
    pairs_with_counts = [(f, get_interaction_count(f)) for f in files]
    pairs_with_counts.sort(key=lambda x: x[1], reverse=True)
    return pairs_with_counts


def analyze_all_pairs(max_workers: int = MAX_WORKERS, limit: Optional[int] = None, overwrite: bool = False) -> dict[str, PairAnalysisResult]:
    """Analyze all pair files with parallel processing, starting with highest interaction counts."""
    
    # Get files sorted by interaction count (descending)
    pairs_with_counts = get_all_pair_files_sorted_by_interactions()
    
    if limit:
        pairs_with_counts = pairs_with_counts[:limit]
    
    files = [f for f, _ in pairs_with_counts]
    
    print(f"Found {len(files)} pair files to analyze")
    if pairs_with_counts:
        top_count = pairs_with_counts[0][1]
        bottom_count = pairs_with_counts[-1][1] if len(pairs_with_counts) > 1 else top_count
        print(f"Interaction range: {bottom_count} to {top_count}")
    
    # Check how many are already cached
    cached = sum(1 for f in files if (OUTPUT_DIR / f"{f.stem}.json").exists() and not overwrite)
    print(f"Already cached: {cached}, remaining: {len(files) - cached}")
    
    results, failed = parallel_map_to_dict(
        files,
        analyze_pair,
        max_workers=max_workers,
        desc="Analyzing pairs"
    )
    
    if failed:
        print(f"\n[WARN] {len(failed)} pairs failed to analyze")
        for f in failed[:10]:
            print(f"  - {f.stem}")
    
    # Convert Path keys to string keys
    return {f.stem: r for f, r in results.items()}


# %%
# === Run Analysis ===

if __name__ == "__main__":
    # Test with a small batch first
    results = analyze_all_pairs(limit=1000, overwrite=False)
    
    print(f"\nAnalyzed {len(results)} pairs")
    for pair_id, result in list(results.items())[:3]:
        print(f"\n{'='*60}")
        print(f"Pair: @{result.person_a} <-> @{result.person_b}")
        print(f"First interaction: {result.first_interaction_date}")
        print(f"Total interactions: {result.total_interactions}")
        print(f"Initiator: {result.analysis.initiator}")
        print(f"Symmetry: {result.analysis.symmetry_score}/5")
        print(f"Energy: {result.analysis.interaction_energy}")
        print(f"Tags: {', '.join(result.analysis.tags)}")
        print(f"Confidence: {result.analysis.confidence}")
        print(f"\nNarrative: {result.analysis.genesis_narrative}")

# %%
# Run on all pairs (uncomment when ready)
# results = analyze_all_pairs()

# %%
# === Distribution Plot ===

def plot_interaction_distribution():
    """Plot log-log distribution of interactions per relationship."""
    import matplotlib.pyplot as plt
    import numpy as np
    
    pairs_with_counts = get_all_pair_files_sorted_by_interactions()
    counts = [c for _, c in pairs_with_counts]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Histogram with log-spaced bins
    bins = np.logspace(0, np.log10(max(counts) + 1), 50)
    ax.hist(counts, bins=bins, edgecolor='black', alpha=0.7)
    
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('Number of Interactions')
    ax.set_ylabel('Number of Pairs')
    ax.set_title(f'Distribution of Interactions per Relationship (n={len(counts):,})')
    ax.grid(True, alpha=0.3)
    
    # Add some stats
    median_count = np.median(counts)
    mean_count = np.mean(counts)
    ax.axvline(median_count, color='red', linestyle='--', label=f'Median: {median_count:.0f}')
    ax.axvline(mean_count, color='orange', linestyle='--', label=f'Mean: {mean_count:.1f}')
    ax.legend()
    
    plt.tight_layout()
    plt.show()
    
    # Print summary stats
    print(f"Total pairs: {len(counts):,}")
    print(f"Interaction range: {min(counts)} - {max(counts)}")
    print(f"Median: {median_count:.0f}")
    print(f"Mean: {mean_count:.1f}")
    print(f"Pairs with 10+ interactions: {sum(1 for c in counts if c >= 10):,}")
    print(f"Pairs with 50+ interactions: {sum(1 for c in counts if c >= 50):,}")
    print(f"Pairs with 100+ interactions: {sum(1 for c in counts if c >= 100):,}")


# %%
# Run the plot
plot_interaction_distribution()

# %%