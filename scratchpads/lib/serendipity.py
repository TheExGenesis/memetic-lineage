# %%
"""
Serendipity utilities - Functions for analyzing first interactions between users.

This module provides:
- Interaction history building and caching
- Pair analysis utilities
- A->B->A pattern detection
- Export utilities for pair samples
"""

import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, TypedDict, Union

from diskcache import Cache
from tqdm import tqdm

from .strand_caches import SCRATCHPADS_DIR as DATA_DIR
from .conversation_explorer import print_conversation_threads


# Diskcache path for interaction history
INTERACTION_HISTORY_DISKCACHE = DATA_DIR / 'interaction_history.diskcache'


class Interaction(TypedDict):
    """A single interaction (reply) between two users."""
    tweet_id: int
    from_user: str
    to_user: str
    created_at: Optional[datetime]
    reply_to_tweet_id: Optional[int]
    full_text: str


# Type alias for pair history - can be a dict or a Cache
PairHistory = Union[Cache, Dict[Tuple[str, str], List[Interaction]]]


def parse_date(d) -> Optional[datetime]:
    """Parse a date that might be datetime, string, or None."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d
    if isinstance(d, str):
        # Try common formats
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        # Try pandas timestamp string
        try:
            from pandas import Timestamp
            return Timestamp(d).to_pydatetime()
        except:
            pass
    return None


def make_pair_key(user_a: str, user_b: str) -> Tuple[str, str]:
    """Create a consistent ordered pair key for two usernames."""
    a, b = sorted([user_a.lower(), user_b.lower()])
    return (a, b)


def _format_interaction_date(dt_val: Optional[datetime]) -> str:
    """Format a datetime for display, handling None and string types."""
    if dt_val is None:
        return '?'
    if hasattr(dt_val, 'strftime'):
        return dt_val.strftime('%Y-%m-%d %H:%M')
    return str(dt_val)[:16]


# ============================================================
# INTERACTION HISTORY BUILDING
# ============================================================

def build_interaction_history(tweet_dict, max_tweets: Optional[int] = None) -> Dict[Tuple[str, str], List[Interaction]]:
    """
    Build a dictionary mapping user pairs to their interaction history.
    
    Keys are tuples of (user_a, user_b) ordered alphabetically (lowercase).
    Values are lists of Interaction objects, sorted by created_at.
    """
    pair_history: Dict[Tuple[str, str], List[Interaction]] = defaultdict(list)
    i = 0
    print(f"Processing {len(tweet_dict)} tweets to find interactions...")
    
    for tweet_id in tqdm(tweet_dict, desc="Finding reply interactions"):
        
        if max_tweets is not None and i > max_tweets:
            break
        i += 1
        tweet = tweet_dict[tweet_id]
        
        # Skip if not a reply
        reply_to_tweet_id = tweet.get('reply_to_tweet_id')
        if reply_to_tweet_id is None:
            continue
        
        from_user = tweet.get('username')
        to_user = tweet.get('reply_to_username')
        
        # Skip if missing user info
        if not from_user or not to_user:
            continue
        
        # Skip self-replies (threads)
        if from_user.lower() == to_user.lower():
            continue
        
        created_at = tweet.get('created_at')
        full_text = tweet.get('full_text', '')
        
        interaction: Interaction = {
            'tweet_id': tweet_id,
            'from_user': from_user,
            'to_user': to_user,
            'created_at': created_at,
            'reply_to_tweet_id': reply_to_tweet_id,
            'full_text': full_text[:500] if full_text else '',
        }
        
        pair_key = make_pair_key(from_user, to_user)
        pair_history[pair_key].append(interaction)
    
    # Sort each pair's history by created_at
    print("Sorting interaction histories by date...")
    for pair_key in tqdm(pair_history, desc="Sorting"):
        pair_history[pair_key].sort(
            key=lambda x: x['created_at'] if x['created_at'] else datetime.min
        )
    
    return dict(pair_history)


def get_or_build_interaction_history(
    tweet_dict=None,
    force_rebuild: bool = False
) -> PairHistory:
    """
    Load interaction history from cache if it exists, otherwise build and save it.
    
    Args:
        tweet_dict: The tweet dictionary (only needed if cache doesn't exist or force_rebuild=True)
        force_rebuild: If True, rebuild even if cache exists
    
    Returns:
        Cache object (if loading from cache) or dict (if just built).
        Both support pair_history[pair_key] -> List[Interaction]
    """
    cache_exists = INTERACTION_HISTORY_DISKCACHE.exists()
    
    if cache_exists and not force_rebuild:
        print(f"Opening interaction history cache at {INTERACTION_HISTORY_DISKCACHE}...")
        cache = Cache(str(INTERACTION_HISTORY_DISKCACHE))
        print(f"Loaded cache with {len(cache)} user pairs")
        return cache
    
    # Build from scratch
    if tweet_dict is None:
        raise ValueError("tweet_dict is required when cache doesn't exist or force_rebuild=True")
    
    print("Building interaction history from tweets...")
    pair_history = build_interaction_history(tweet_dict)
    
    # Save to diskcache
    print(f"Saving interaction history to {INTERACTION_HISTORY_DISKCACHE}...")
    with Cache(str(INTERACTION_HISTORY_DISKCACHE), size_limit=2 * 1024**3) as cache:
        cache.clear()
        for k, v in tqdm(pair_history.items(), desc="Saving to diskcache"):
            cache[k] = v
    print(f"Saved {len(pair_history)} user pairs to diskcache")
    
    return pair_history


def get_first_interaction(pair_history: Dict[Tuple[str, str], List[Interaction]], 
                          user_a: str, 
                          user_b: str) -> Optional[Interaction]:
    """Get the first interaction between two users."""
    pair_key = make_pair_key(user_a, user_b)
    history = pair_history.get(pair_key, [])
    return history[0] if history else None


def get_user_interactions(
    username: str, 
    pair_history: PairHistory
) -> List[Tuple[str, Interaction]]:
    """
    Get all interactions involving a specific user.
    
    Returns list of (other_user, interaction) tuples, sorted by date.
    """
    username_lower = username.lower()
    interactions = []
    
    # Handle both Cache and dict
    keys = pair_history.keys() if isinstance(pair_history, dict) else list(pair_history)
    
    for pair_key in keys:
        user_a, user_b = pair_key
        if user_a == username_lower or user_b == username_lower:
            other_user = user_b if user_a == username_lower else user_a
            history = pair_history[pair_key]
            for interaction in history:
                interactions.append((other_user, interaction))
    
    interactions.sort(key=lambda x: parse_date(x[1]['created_at']) or datetime.min)
    return interactions


# ============================================================
# STATISTICS AND ANALYSIS
# ============================================================

def print_interaction_stats(pair_history: PairHistory):
    """Print statistics about the interaction history."""
    total_pairs = len(pair_history)
    
    # Handle both Cache and dict - Cache doesn't have .values()
    if isinstance(pair_history, Cache):
        interaction_counts = [len(pair_history[k]) for k in pair_history]
    else:
        interaction_counts = [len(v) for v in pair_history.values()]
    
    total_interactions = sum(interaction_counts)
    
    print(f"\n{'='*60}")
    print("INTERACTION HISTORY STATS")
    print(f"{'='*60}")
    print(f"Total unique user pairs: {total_pairs:,}")
    print(f"Total interactions (replies): {total_interactions:,}")
    print(f"Average interactions per pair: {total_interactions / total_pairs:.2f}")
    print(f"Max interactions for a pair: {max(interaction_counts):,}")
    print(f"Pairs with only 1 interaction: {sum(1 for c in interaction_counts if c == 1):,}")
    print(f"Pairs with 10+ interactions: {sum(1 for c in interaction_counts if c >= 10):,}")
    print(f"Pairs with 100+ interactions: {sum(1 for c in interaction_counts if c >= 100):,}")


def find_most_active_pairs(pair_history: PairHistory, 
                           top_n: int = 20) -> List[Tuple[Tuple[str, str], int]]:
    """Find the pairs with the most interactions."""
    if isinstance(pair_history, Cache):
        pairs_by_count = sorted(
            [(k, len(pair_history[k])) for k in pair_history],
            key=lambda x: -x[1]
        )
    else:
        pairs_by_count = sorted(
            [(k, len(v)) for k, v in pair_history.items()],
            key=lambda x: -x[1]
        )
    return pairs_by_count[:top_n]


def find_first_twoway_interactions(
    pair_history: PairHistory,
    min_exchanges: int = 2
) -> List[Tuple[Tuple[str, str], List[Interaction]]]:
    """
    Find pairs where both users have replied to each other (A->B and B->A).
    
    Returns list of (pair_key, interactions) for pairs with bidirectional exchanges.
    """
    twoway_pairs = []
    
    # Handle both Cache and dict
    keys = pair_history.keys() if isinstance(pair_history, dict) else list(pair_history)
    
    for pair_key in keys:
        history = pair_history[pair_key]
        if len(history) < min_exchanges:
            continue
        
        user_a, user_b = pair_key
        a_to_b = any(i['from_user'].lower() == user_a and i['to_user'].lower() == user_b for i in history)
        b_to_a = any(i['from_user'].lower() == user_b and i['to_user'].lower() == user_a for i in history)
        
        if a_to_b and b_to_a:
            twoway_pairs.append((pair_key, history))
    
    # Sort by date of first interaction
    twoway_pairs.sort(key=lambda x: x[1][0]['created_at'] if x[1][0]['created_at'] else datetime.min)
    return twoway_pairs


# ============================================================
# A->B->A PATTERN DETECTION
# ============================================================

def find_aba_patterns(interactions: List[Interaction], max_count: int = 20) -> List[Tuple[Interaction, Interaction, Optional[Interaction]]]:
    """
    Find A->B->A patterns: sequences where user A replies to B, then B replies back to A.
    
    Returns list of (A->B interaction, B->A interaction, A->B second interaction) tuples.
    """
    patterns: List[Tuple[Interaction, Interaction, Optional[Interaction]]] = []
    
    for i in range(len(interactions) - 1):
        if len(patterns) >= max_count:
            break
            
        curr = interactions[i]
        curr_from = curr['from_user'].lower()
        curr_to = curr['to_user'].lower()
        
        # Look for the response: B->A
        for j in range(i + 1, len(interactions)):
            next_int = interactions[j]
            next_from = next_int['from_user'].lower()
            next_to = next_int['to_user'].lower()
            
            # Check if this is B replying to A
            if next_from == curr_to and next_to == curr_from:
                # Found an A->B->A pattern! Now look for A's response
                for k in range(j + 1, len(interactions)):
                    third = interactions[k]
                    third_from = third['from_user'].lower()
                    third_to = third['to_user'].lower()
                    
                    if third_from == curr_from and third_to == curr_to:
                        patterns.append((curr, next_int, third))
                        break
                else:
                    # No third message, still record the A->B, B->A pair with None
                    patterns.append((curr, next_int, None))
                break
    
    return patterns[:max_count]


def render_aba_patterns(patterns: List[Tuple[Interaction, Interaction, Optional[Interaction]]]) -> str:
    """Render A->B->A patterns in a readable format."""
    lines = []
    lines.append(f"A→B→A INTERACTION PATTERNS ({len(patterns)} found)")
    lines.append("=" * 70)
    
    for idx, (first, second, third) in enumerate(patterns):
        lines.append(f"\n--- Exchange #{idx + 1} ---")
        
        # First message: A -> B
        date1_str = _format_interaction_date(first['created_at'])
        lines.append(f"[A→B] {date1_str} @{first['from_user']} → @{first['to_user']}")
        lines.append(f"      Tweet: {first['tweet_id']}")
        text1 = first['full_text'].replace('\n', '\n      ')
        lines.append(f"      {text1}")
        
        # Second message: B -> A
        date2_str = _format_interaction_date(second['created_at'])
        lines.append(f"")
        lines.append(f"[B→A] {date2_str} @{second['from_user']} → @{second['to_user']}")
        lines.append(f"      Tweet: {second['tweet_id']}")
        text2 = second['full_text'].replace('\n', '\n      ')
        lines.append(f"      {text2}")
        
        # Third message: A -> B (if exists)
        if third:
            date3_str = _format_interaction_date(third['created_at'])
            lines.append(f"")
            lines.append(f"[A→B] {date3_str} @{third['from_user']} → @{third['to_user']}")
            lines.append(f"      Tweet: {third['tweet_id']}")
            text3 = third['full_text'].replace('\n', '\n      ')
            lines.append(f"      {text3}")
    
    return "\n".join(lines)


# ============================================================
# TREE RENDERING
# ============================================================

def render_interaction_tree(
    interactions: List[Interaction], 
    tweet_dict,
    conversation_trees,
    max_count: int = 100
) -> str:
    """
    Render the first N interactions as a conversation tree visualization.
    Uses the actual conversation tree structure from the data.
    """
    shown = interactions[:max_count]
    
    if not shown:
        return "(No interactions found)"
    
    lines = []
    lines.append(f"CONVERSATION TREE ({len(shown)} of {len(interactions)} interactions)")
    lines.append("=" * 70)
    
    # Get tweet IDs for the interactions
    tweet_ids = [i['tweet_id'] for i in shown]
    
    # Also include the tweets they're replying to
    reply_ids = [i['reply_to_tweet_id'] for i in shown if i['reply_to_tweet_id']]
    all_ids = list(set(tweet_ids + reply_ids))
    
    # Use the conversation tree renderer
    tree_text = print_conversation_threads(
        all_ids,
        conversation_trees,
        tweet_dict,
        depth=5
    )
    
    if tree_text and tree_text.strip():
        lines.append(tree_text)
    else:
        # Fallback: print interactions directly if tree rendering fails
        lines.append("\n(Conversation tree not available, showing raw interactions)\n")
        for idx, interaction in enumerate(shown):
            from_user = interaction['from_user']
            to_user = interaction['to_user']
            created_at = interaction['created_at']
            tweet_id = interaction['tweet_id']
            text = interaction['full_text'][:200].replace('\n', ' ')
            
            date_str = _format_interaction_date(created_at)
            arrow = f"@{from_user} → @{to_user}"
            
            lines.append(f"[{idx+1:3d}] {date_str} | {arrow}")
            lines.append(f"      Tweet ID: {tweet_id}")
            lines.append(f"      {text}{'...' if len(interaction['full_text']) > 200 else ''}")
            lines.append("")
    
    return "\n".join(lines)


def print_twoway_thread(
    pair_key: Tuple[str, str],
    pair_history: PairHistory,
    tweet_dict,
    conversation_trees,
    max_interactions: int = 10
):
    """
    Print the conversation thread(s) for a two-way interaction pair.
    Shows the first few exchanges between the two users.
    """
    history = pair_history.get(pair_key, [])
    if not history:
        print(f"No interactions found for pair {pair_key}")
        return
    
    user_a, user_b = pair_key
    print(f"\n{'='*70}")
    print(f"TWO-WAY INTERACTION: @{user_a} <-> @{user_b}")
    print(f"Total interactions: {len(history)}")
    print(f"{'='*70}")
    
    # Get tweet IDs for the first few interactions
    interactions_to_show = history[:max_interactions]
    tweet_ids = [i['tweet_id'] for i in interactions_to_show]
    
    # Also include the tweets they're replying to
    reply_ids = [i['reply_to_tweet_id'] for i in interactions_to_show if i['reply_to_tweet_id']]
    all_ids = list(set(tweet_ids + reply_ids))
    
    # Try using the conversation tree renderer
    thread_text = print_conversation_threads(
        all_ids,
        conversation_trees,
        tweet_dict,
        depth=3
    )
    
    if thread_text and thread_text.strip():
        print(thread_text)
    else:
        # Fallback: print interactions directly
        print("\n(Conversation tree not available, showing raw interactions)\n")
        for i, interaction in enumerate(interactions_to_show):
            dt = parse_date(interaction['created_at'])
            date_str = dt.strftime('%Y-%m-%d %H:%M') if dt else 'unknown'
            print(f"--- [{i+1}] {date_str} ---")
            print(f"@{interaction['from_user']} -> @{interaction['to_user']}")
            print(f"Tweet ID: {interaction['tweet_id']} (reply to: {interaction['reply_to_tweet_id']})")
            print(f"{interaction['full_text']}")
            print()


# ============================================================
# EXPORT UTILITIES
# ============================================================

def export_pair_files(
    pair_history: PairHistory,
    tweet_dict,
    conversation_trees,
    num_pairs: Optional[int] = None,
    output_dir: Optional[Path] = None,
    seed: Optional[int] = None
) -> List[Tuple[str, str]]:
    """
    Export first interactions for random pairs to individual files.
    
    Each file contains:
    - Tree of first 100 Interaction events (rendered as conversation trees)
    - First 20 A->B->A interaction patterns
    
    Returns:
        List of selected pair keys
    """
    from datetime import datetime as dt
    
    if output_dir is None:
        output_dir = DATA_DIR / 'pair_samples'
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
    # Get all pair keys
    if isinstance(pair_history, Cache):
        all_keys = list(pair_history.iterkeys())
    else:
        all_keys = list(pair_history.keys())
    
    print(f"Found {len(all_keys)} total pairs")
    
    # Filter to pairs with at least some interactions (ideally bidirectional)
    valid_keys = []
    for key in tqdm(all_keys, desc="Filtering valid pairs"):
        history = pair_history[key]
        if len(history) >= 5:  # At least 5 interactions
            # Check for bidirectionality
            user_a, user_b = key
            has_a_to_b = any(i['from_user'].lower() == user_a for i in history)
            has_b_to_a = any(i['from_user'].lower() == user_b for i in history)
            if has_a_to_b and has_b_to_a:
                valid_keys.append(key)
    
    print(f"Found {len(valid_keys)} valid bidirectional pairs (from {len(all_keys)} total)")
    
    # Random sample
    if seed is not None:
        random.seed(seed)
    if num_pairs is None:
        num_pairs = len(valid_keys)
    selected_keys = random.sample(valid_keys, min(num_pairs, len(valid_keys)))
    
    print(f"Exporting {len(selected_keys)} pairs to {output_dir}")
    
    for pair_key in tqdm(selected_keys, desc="Exporting pairs"):
        user_a, user_b = pair_key
        history = pair_history[pair_key]
        
        # Build file content
        content_lines = []
        content_lines.append(f"PAIR: @{user_a} <-> @{user_b}")
        content_lines.append(f"Total interactions: {len(history)}")
        content_lines.append(f"Generated: {dt.now().isoformat()}")
        content_lines.append("")
        content_lines.append("")
        
        # Section 1: Interaction tree (using conversation tree renderer)
        tree_str = render_interaction_tree(
            history, 
            tweet_dict, 
            conversation_trees, 
            max_count=100
        )
        content_lines.append(tree_str)
        content_lines.append("")
        content_lines.append("")
        
        # Section 2: A->B->A patterns
        patterns = find_aba_patterns(history, max_count=20)
        patterns_str = render_aba_patterns(patterns)
        content_lines.append(patterns_str)
        
        # Write file
        filename = f"pair_{user_a}_{user_b}.txt"
        filepath = output_dir / filename
        filepath.write_text("\n".join(content_lines))
    
    print(f"Done! Files written to {output_dir}")
    return selected_keys
