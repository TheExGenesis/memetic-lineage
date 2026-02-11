# %%
#!/usr/bin/env python3

"""
Serendipity Metric - Analyze first interactions between users

This script:
1. Loads tweet_dict and conversation_trees from cache
2. Finds all reply interactions between pairs of users
3. Builds a history of interactions for each user pair (ordered consistently)
"""

# %%
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict
from dotenv import load_dotenv
from tqdm import tqdm

# Handle notebook vs script context
try:
    SCRATCHPADS_DIR = Path(__file__).parent
except NameError:
    SCRATCHPADS_DIR = Path.cwd()
    if SCRATCHPADS_DIR.name != 'scratchpads':
        SCRATCHPADS_DIR = SCRATCHPADS_DIR / 'scratchpads'

# Ensure lib is importable
if str(SCRATCHPADS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCHPADS_DIR))

from diskcache import Cache
from lib.strand_caches import load_caches, SCRATCHPADS_DIR as DATA_DIR
from lib.serendipity import (
    Interaction,
    PairHistory,
    parse_date,
    make_pair_key,
    get_or_build_interaction_history,
    get_first_interaction,
    get_user_interactions,
    print_interaction_stats,
    find_most_active_pairs,
    find_first_twoway_interactions,
    print_twoway_thread,
)

load_dotenv(SCRATCHPADS_DIR.parent / ".env")

# Cache for directional history (expensive to compute)
_directional_history_cache: Optional[Dict] = None


def get_or_build_directional_history(pair_history: PairHistory, force_rebuild: bool = False) -> Dict:
    """Get cached directional history or build it."""
    global _directional_history_cache
    
    if _directional_history_cache is None or force_rebuild:
        print("Building directional history (will be cached)...")
        _directional_history_cache = build_directional_history(pair_history)
        print(f"Cached {len(_directional_history_cache):,} pairs")
    else:
        print(f"Using cached directional history ({len(_directional_history_cache):,} pairs)")
    
    return _directional_history_cache


# ============================================================
# PLOTTING FUNCTIONS (kept here as they have heavy dependencies)
# ============================================================

def plot_user_interactions(
    username: str,
    pair_history: Dict[Tuple[str, str], List[Interaction]],
    bin_days: int = 30
):
    """
    Plot interaction intensity over time for a specific user.
    Shows a histogram of interactions binned by time period.
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from collections import Counter
    
    interactions = get_user_interactions(username, pair_history)
    
    if not interactions:
        print(f"No interactions found for @{username}")
        return
    
    # Extract and parse dates
    parsed_interactions = []
    for other, interaction in interactions:
        dt = parse_date(interaction['created_at'])
        if dt:
            parsed_interactions.append((other, dt))
    
    if not parsed_interactions:
        print(f"No dated interactions found for @{username}")
        return
    
    dates = [dt for _, dt in parsed_interactions]
    other_users = [other for other, _ in parsed_interactions]
    
    # Count interactions per other user for coloring
    user_counts = Counter(other_users)
    top_users = [u for u, _ in user_counts.most_common(10)]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    
    # Top plot: histogram of all interactions over time
    ax1.hist(dates, bins=50, edgecolor='black', alpha=0.7)
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Interactions')
    ax1.set_title(f'@{username} - Interaction Intensity Over Time')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Bottom plot: stacked by top interaction partners
    user_dates = {u: [] for u in top_users}
    user_dates['other'] = []
    
    for other, dt in parsed_interactions:
        if other in top_users:
            user_dates[other].append(dt)
        else:
            user_dates['other'].append(dt)
    
    # Create stacked histogram data
    all_dates_list = [user_dates[u] for u in top_users + ['other'] if user_dates.get(u)]
    labels = [f'@{u}' for u in top_users if user_dates.get(u)] + (['other'] if user_dates.get('other') else [])
    
    if all_dates_list:
        ax2.hist(all_dates_list, bins=50, stacked=True, label=labels, edgecolor='black', alpha=0.7)
        ax2.legend(loc='upper left', fontsize=8)
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Interactions')
    ax2.set_title(f'@{username} - By Interaction Partner (Top 10)')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    plt.show()
    
    # Print summary
    print(f"\n@{username} interaction summary:")
    print(f"  Total interactions: {len(interactions)}")
    print(f"  Unique partners: {len(user_counts)}")
    if dates:
        print(f"  Date range: {min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}")
    print(f"\n  Top 10 partners:")
    for u, count in user_counts.most_common(10):
        print(f"    @{u}: {count}")


def plot_user_interactions_interactive(
    username: str,
    pair_history: PairHistory,
    bin_days: int = 7,
    top_n: int = 15,
    smooth_window: int = 12
):
    """
    Interactive plotly line plot of interaction intensity over time.
    Shows cumulative and per-period interactions with log scale option.
    
    Args:
        smooth_window: Rolling average window size (number of bins). Higher = smoother.
    """
    import plotly.graph_objects as go
    from collections import Counter, defaultdict
    import pandas as pd
    import numpy as np
    
    interactions = get_user_interactions(username, pair_history)
    
    if not interactions:
        print(f"No interactions found for @{username}")
        return
    
    # Parse dates
    parsed_interactions = []
    for other, interaction in interactions:
        dt = parse_date(interaction['created_at'])
        if dt:
            parsed_interactions.append((other, dt))
    
    if not parsed_interactions:
        print(f"No dated interactions found for @{username}")
        return
    
    # Count by user
    user_counts = Counter(other for other, _ in parsed_interactions)
    top_users = [u for u, _ in user_counts.most_common(top_n)]
    
    # Bin interactions by time period
    min_date = min(dt for _, dt in parsed_interactions)
    max_date = max(dt for _, dt in parsed_interactions)
    
    # Create complete time bins (including zeros)
    date_range = pd.date_range(start=min_date, end=max_date, freq=f'{bin_days}D')
    
    # Count interactions per user per bin (including zeros for gaps)
    user_timeseries = {u: {d: 0 for d in date_range} for u in top_users + ['other']}
    
    for other, dt in parsed_interactions:
        # Find which bin this falls into
        bin_idx = (dt - min_date).days // bin_days
        if bin_idx < len(date_range):
            bin_date = date_range[bin_idx]
            
            if other in top_users:
                user_timeseries[other][bin_date] += 1
            else:
                user_timeseries['other'][bin_date] += 1
    
    # Create figure
    fig = go.Figure()
    
    # Color palette
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5'
    ]
    
    # Add line for each user
    for i, user in enumerate(top_users + ['other']):
        ts = user_timeseries[user]
        if not ts or sum(ts.values()) == 0:
            continue
        
        sorted_dates = sorted(ts.keys())
        counts = np.array([ts[d] for d in sorted_dates], dtype=float)
        
        # Apply smoothing using rolling mean
        if smooth_window > 1 and len(counts) > smooth_window:
            smoothed = pd.Series(counts).rolling(
                window=smooth_window, 
                min_periods=1, 
                center=True
            ).mean().values
        else:
            smoothed = counts
        
        color = colors[i % len(colors)]
        label = f'@{user}' if user != 'other' else 'other'
        
        # Line plot - smoothed, log scale
        fig.add_trace(
            go.Scatter(
                x=sorted_dates,
                y=smoothed,
                mode='lines',
                name=label,
                line=dict(color=color, width=2),
                hovertemplate=f'{label}<br>%{{x|%Y-%m-%d}}<br>%{{y:.1f}} avg interactions<extra></extra>'
            )
        )
    
    # Update layout
    fig.update_layout(
        title=f'@{username} - Interactions ({bin_days}-day bins, {smooth_window}-period smoothing)',
        height=500,
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        yaxis=dict(type='log', title='Interactions (log)'),
        xaxis=dict(title='Date')
    )
    
    fig.show()
    
    # Print summary
    print(f"\n@{username} interaction summary:")
    print(f"  Total interactions: {len(parsed_interactions)}")
    print(f"  Unique partners: {len(user_counts)}")
    print(f"  Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"\n  Top {top_n} partners:")
    for u, count in user_counts.most_common(top_n):
        print(f"    @{u}: {count}")


def build_directional_history(
    pair_history: PairHistory,
    target_user: Optional[str] = None
) -> Dict[Tuple[str, str], Dict[str, List[datetime]]]:
    """
    Build a data structure with interactions separated by direction.
    
    Returns:
        {pair_key: {'a_to_b': [datetime, ...], 'b_to_a': [datetime, ...]}}
        where pair_key = (user_a, user_b) with user_a < user_b alphabetically
    """
    target_lower = target_user.lower() if target_user else None
    
    # {pair_key: {'a_to_b': [], 'b_to_a': []}}
    directional = defaultdict(lambda: {'a_to_b': [], 'b_to_a': []})
    
    keys = pair_history.keys() if isinstance(pair_history, dict) else list(pair_history)
    
    for pair_key in keys:
        user_a, user_b = pair_key  # Already sorted alphabetically
        
        # Filter by target user if specified
        if target_lower and user_a != target_lower and user_b != target_lower:
            continue
        
        history = pair_history[pair_key]
        for interaction in history:
            dt = parse_date(interaction['created_at'])
            if not dt:
                continue
            
            from_user = interaction['from_user'].lower()
            to_user = interaction['to_user'].lower()
            
            if from_user == user_a and to_user == user_b:
                directional[pair_key]['a_to_b'].append(dt)
            elif from_user == user_b and to_user == user_a:
                directional[pair_key]['b_to_a'].append(dt)
    
    # Sort dates for efficient lookup
    for pair_key in directional:
        directional[pair_key]['a_to_b'].sort()
        directional[pair_key]['b_to_a'].sort()
    
    return dict(directional)


def compute_alive_stats(
    pair_history: PairHistory,
    window_days: int = 60,
    bin_days: int = 7,
    target_user: Optional[str] = None,
    tweet_dict: Optional[Dict] = None,
    reply_threshold: int = 3,
    exclude_users: Optional[List[str]] = None
) -> Dict:
    """
    Compute alive relationship statistics over time. OPTIMIZED for large datasets.
    
    A relationship is ALIVE at time T if within [T-window, T]:
    - There is at least one A->B interaction AND
    - There is at least one B->A interaction
    
    A relationship is ACTIVE_REPLY at time T if within [T-window, T]:
    - There are at least `reply_threshold` total interactions (any direction)
    
    Returns dict with:
        - dates: list of datetime checkpoints
        - alive_counts: number of alive relationships at each checkpoint
        - active_users: number of users with at least one alive relationship
        - relationships_per_user: alive_counts / active_users (normalized)
        - active_reply_relations: relationships with >= reply_threshold interactions
        - active_reply_users: users with at least one active_reply relationship
        - active_reply_per_user: active_reply_relations / active_reply_users (normalized)
        - tweet_volume: total tweets per bin (if tweet_dict provided)
    """
    import pandas as pd
    import numpy as np
    
    print("Building directional history...")
    directional = build_directional_history(pair_history, target_user)
    
    # Filter out excluded users
    if exclude_users:
        exclude_set = {u.lower() for u in exclude_users}
        original_count = len(directional)
        directional = {
            pair_key: pair_data 
            for pair_key, pair_data in directional.items()
            if pair_key[0] not in exclude_set and pair_key[1] not in exclude_set
        }
        print(f"Filtered out {original_count - len(directional):,} pairs containing excluded users ({len(exclude_users)} users)")
    
    if not directional:
        print("No interactions found")
        return {'dates': [], 'alive_counts': [], 'active_users': [], 'relationships_per_user': []}
    
    print(f"Total pairs to check: {len(directional):,}")
    
    # Convert to timestamps for faster comparison
    print("Converting to timestamps...")
    pair_timestamps_bidirectional = {}  # For alive (bidirectional) check
    pair_timestamps_all = {}  # For active_reply (any direction) check
    all_timestamps: List[float] = []
    
    for pair_key, pair_data in directional.items():
        a_to_b_ts = np.array([dt.timestamp() for dt in pair_data['a_to_b']], dtype=np.float64)
        b_to_a_ts = np.array([dt.timestamp() for dt in pair_data['b_to_a']], dtype=np.float64)
        
        # Store ALL pairs for active_reply computation (combine both directions)
        combined_ts = np.sort(np.concatenate([a_to_b_ts, b_to_a_ts]))
        if len(combined_ts) > 0:
            pair_timestamps_all[pair_key] = combined_ts
            all_timestamps.extend(combined_ts)
        
        # Only keep pairs that have BOTH directions (potential for being alive)
        if len(a_to_b_ts) > 0 and len(b_to_a_ts) > 0:
            pair_timestamps_bidirectional[pair_key] = (np.sort(a_to_b_ts), np.sort(b_to_a_ts))
    
    if not pair_timestamps_all:
        print("No pairs found")
        return {'dates': [], 'alive_counts': [], 'active_users': [], 'relationships_per_user': [],
                'active_reply_relations': [], 'active_reply_users': [], 'active_reply_per_user': []}
    
    print(f"Total pairs: {len(pair_timestamps_all):,}")
    print(f"Bidirectional pairs: {len(pair_timestamps_bidirectional):,}")
    
    min_ts = min(all_timestamps)
    max_ts = max(all_timestamps)
    min_date = datetime.fromtimestamp(min_ts)
    max_date = datetime.fromtimestamp(max_ts)
    
    print(f"Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    
    # Create time checkpoints
    window_seconds = window_days * 24 * 3600
    bin_seconds = bin_days * 24 * 3600
    
    checkpoints = np.arange(min_ts, max_ts + bin_seconds, bin_seconds)
    n_checkpoints = len(checkpoints)
    print(f"Time points to evaluate: {n_checkpoints}")
    
    # Track alive counts and active users per checkpoint
    alive_counts = np.zeros(n_checkpoints, dtype=np.int32)
    # For active users: track which users have alive relationships at each checkpoint
    active_users_per_checkpoint: List[set] = [set() for _ in range(n_checkpoints)]
    
    print("Counting alive relationships (bidirectional)...")
    
    for pair_key, (a_ts, b_ts) in tqdm(pair_timestamps_bidirectional.items(), desc="Counting alive pairs"):
        user_a, user_b = pair_key
        
        # For each checkpoint, find the largest a_ts that's <= checkpoint
        a_idx = np.searchsorted(a_ts, checkpoints, side='right') - 1
        a_valid = (a_idx >= 0)
        a_in_window = np.zeros(n_checkpoints, dtype=bool)
        a_in_window[a_valid] = a_ts[a_idx[a_valid]] >= (checkpoints[a_valid] - window_seconds)
        
        # Same for b_ts
        b_idx = np.searchsorted(b_ts, checkpoints, side='right') - 1
        b_valid = (b_idx >= 0)
        b_in_window = np.zeros(n_checkpoints, dtype=bool)
        b_in_window[b_valid] = b_ts[b_idx[b_valid]] >= (checkpoints[b_valid] - window_seconds)
        
        # Pair is alive where both are in window
        alive = a_in_window & b_in_window
        alive_counts += alive.astype(np.int32)
        
        # Track active users at each checkpoint where this pair is alive
        alive_indices = np.where(alive)[0]
        for idx in alive_indices:
            active_users_per_checkpoint[idx].add(user_a)
            active_users_per_checkpoint[idx].add(user_b)
    
    # Convert to counts
    active_user_counts = [len(s) for s in active_users_per_checkpoint]
    
    # Compute normalized metric (relationships per active user)
    relationships_per_user = []
    for alive, active in zip(alive_counts, active_user_counts):
        if active > 0:
            # Each relationship involves 2 users, so divide by 2 for per-user metric
            relationships_per_user.append((alive * 2) / active)
        else:
            relationships_per_user.append(0.0)
    
    # ========================================
    # Compute active_reply_relations (>= reply_threshold interactions in window, any direction)
    # VECTORIZED: compute counts for all checkpoints at once per pair
    # ========================================
    print(f"Counting active_reply relationships (>= {reply_threshold} interactions, vectorized)...")
    
    active_reply_counts = np.zeros(n_checkpoints, dtype=np.int32)
    active_reply_users_per_checkpoint: List[set] = [set() for _ in range(n_checkpoints)]
    
    # Precompute window starts for all checkpoints
    window_starts = checkpoints - window_seconds
    
    for pair_key, all_ts in tqdm(pair_timestamps_all.items(), desc="Counting active_reply pairs"):
        user_a, user_b = pair_key
        
        # Vectorized: find count of interactions in window for ALL checkpoints at once
        # left_idx[i] = first index where all_ts >= window_starts[i]
        # right_idx[i] = first index where all_ts > checkpoints[i]
        left_idx = np.searchsorted(all_ts, window_starts, side='left')
        right_idx = np.searchsorted(all_ts, checkpoints, side='right')
        counts_in_window = right_idx - left_idx
        
        # Find checkpoints where this pair meets the threshold
        meets_threshold = counts_in_window >= reply_threshold
        active_reply_counts += meets_threshold.astype(np.int32)
        
        # Track users at checkpoints where threshold is met
        active_indices = np.where(meets_threshold)[0]
        for idx in active_indices:
            active_reply_users_per_checkpoint[idx].add(user_a)
            active_reply_users_per_checkpoint[idx].add(user_b)
    
    active_reply_user_counts = [len(s) for s in active_reply_users_per_checkpoint]
    
    # Compute normalized metric
    active_reply_per_user = []
    for reply_count, reply_users in zip(active_reply_counts, active_reply_user_counts):
        if reply_users > 0:
            active_reply_per_user.append((reply_count * 2) / reply_users)
        else:
            active_reply_per_user.append(0.0)
    
    # Convert back to dates
    dates = [datetime.fromtimestamp(ts) for ts in checkpoints]
    
    # Compute tweet volume per bin if tweet_dict provided
    tweet_volume = None
    if tweet_dict is not None:
        print("Computing tweet volume per bin...")
        tweet_volume = np.zeros(n_checkpoints, dtype=np.int32)
        
        keys = list(tweet_dict)
        for key in tqdm(keys, desc="Counting tweets"):
            tweet = tweet_dict[key]
            created_at = tweet.get('created_at')
            if created_at:
                dt = parse_date(created_at)
                if dt:
                    tweet_ts = dt.timestamp()
                    # Find which bin this falls into
                    bin_idx = np.searchsorted(checkpoints, tweet_ts, side='right') - 1
                    if 0 <= bin_idx < n_checkpoints:
                        tweet_volume[bin_idx] += 1
        
        tweet_volume_list = tweet_volume.tolist()
        print(f"  Peak tweet volume: {max(tweet_volume_list):,}")
        tweet_volume = tweet_volume_list
    
    # Debug: verify values are different
    alive_list = alive_counts.tolist()
    active_reply_list = active_reply_counts.tolist()
    print(f"\nDone!")
    print(f"  Peak alive relationships: {max(alive_list)}")
    print(f"  Peak active users: {max(active_user_counts)}")
    print(f"  Peak active_reply relationships: {max(active_reply_list)}")
    print(f"  Peak active_reply users: {max(active_reply_user_counts)}")
    print(f"  Sample checkpoint (last): alive={alive_list[-1]}, active_reply={active_reply_list[-1]}")
    
    result = {
        'dates': dates,
        'alive_counts': alive_list,
        'active_users': active_user_counts,
        'relationships_per_user': relationships_per_user,
        'active_reply_relations': active_reply_list,
        'active_reply_users': active_reply_user_counts,
        'active_reply_per_user': active_reply_per_user,
        'window_days': window_days,
        'reply_threshold': reply_threshold,
        'target_user': target_user,
    }
    
    if tweet_volume is not None:
        result['tweet_volume'] = tweet_volume
    
    return result


def plot_alive_stats(
    stats: Dict,
    metric: str = 'alive_counts',
    smooth_window: int = 4,
    log_scale: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    title_suffix: Optional[str] = "",
    stats2: Optional[Dict] = None,
    label1: str = "Series 1",
    label2: str = "Series 2",
):
    """
    Plot alive relationship statistics. Can compare two stats dicts.
    
    Args:
        stats: Output from compute_alive_stats()
        metric: What to plot:
            - 'alive_counts': Total alive relationships
            - 'active_users': Number of users with at least one alive relationship
            - 'relationships_per_user': Alive relationships normalized by active users
            - 'tweet_volume': Total tweets per bin (if computed)
        smooth_window: Rolling average window
        log_scale: Use log scale on y-axis
        start_date: Filter to dates >= this (format: 'YYYY-MM-DD')
        end_date: Filter to dates <= this (format: 'YYYY-MM-DD')
        stats2: Optional second stats dict to compare
        label1: Label for first stats (used when stats2 is provided)
        label2: Label for second stats (used when stats2 is provided)
    """
    import plotly.graph_objects as go
    import pandas as pd
    import numpy as np
    
    # Lazily compute per-tweet metrics if needed
    def ensure_per_tweet_metrics(s):
        """Compute alive_per_tweet and active_reply_per_tweet if not present."""
        if 'tweet_volume' not in s or s['tweet_volume'] is None:
            return  # Can't compute without tweet_volume
        
        tweets = np.array(s['tweet_volume'], dtype=float)
        tweets_safe = np.where(tweets > 0, tweets, np.nan)
        
        if 'alive_per_tweet' not in s:
            alive = np.array(s['alive_counts'], dtype=float)
            s['alive_per_tweet'] = (alive / tweets_safe).tolist()
        
        if 'active_reply_per_tweet' not in s:
            reply = np.array(s['active_reply_relations'], dtype=float)
            s['active_reply_per_tweet'] = (reply / tweets_safe).tolist()
    
    # Ensure per-tweet metrics exist if requested
    if metric in ('alive_per_tweet', 'active_reply_per_tweet'):
        ensure_per_tweet_metrics(stats)
        if stats2 is not None:
            ensure_per_tweet_metrics(stats2)
    
    def process_stats(s, start_date, end_date, smooth_window):
        """Extract and filter data from stats dict."""
        dates = s['dates']
        if not dates:
            return None, None, None
        
        data = np.array(s[metric], dtype=float)
        
        # Apply date filters
        if start_date or end_date:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None
            
            mask = []
            for d in dates:
                in_range = True
                if start_dt and d < start_dt:
                    in_range = False
                if end_dt and d > end_dt:
                    in_range = False
                mask.append(in_range)
            
            dates = [d for d, m in zip(dates, mask) if m]
            data = data[mask]
            
            if len(dates) == 0:
                return None, None, None
        
        # Smooth
        if smooth_window > 1 and len(data) > smooth_window:
            smoothed = pd.Series(data).rolling(
                window=smooth_window,
                min_periods=1,
                center=True
            ).mean().values
        else:
            smoothed = data
        
        return dates, data, smoothed
    
    dates1, data1, smoothed1 = process_stats(stats, start_date, end_date, smooth_window)
    if dates1 is None:
        print("No data to plot for stats1")
        return
    
    # Title based on metric
    window_days = stats.get('window_days', '?')
    target_user = stats.get('target_user')
    
    metric_labels = {
        'alive_counts': 'Alive Relationships (bidirectional)',
        'active_users': 'Active Users (with alive relationship)',
        'relationships_per_user': 'Alive Relationships per User',
        'active_reply_relations': 'Active Reply Relations (≥threshold)',
        'active_reply_users': 'Active Reply Users',
        'active_reply_per_user': 'Active Reply Relations per User',
        'tweet_volume': 'Tweet Volume',
        'alive_per_tweet': 'Alive Relationships per Tweet',
        'active_reply_per_tweet': 'Active Reply Relations per Tweet',
    }
    metric_label = metric_labels.get(metric, metric) 
    
    title = f"{metric_label} Over Time ({window_days}-day window)" 
    if 'active_reply' in metric:
        reply_threshold = stats.get('reply_threshold', '?')
        title = title.replace('≥threshold', f'≥{reply_threshold}')
    if target_user:
        title = f"@{target_user} - " + title
    if start_date or end_date:
        date_range_str = f"{start_date or 'start'} to {end_date or 'end'}"
        title += f" [{date_range_str}]"

    if title_suffix:
        title += f"<br>{title_suffix}"
    
    fig = go.Figure()
    
    # Colors for two series
    colors = [('#1f77b4', 'lightblue'), ('#ff7f0e', '#ffcc99')]  # Blue and Orange
    
    if stats2 is None:
        # Single series mode (original behavior)
        fig.add_trace(go.Scatter(
            x=dates1,
            y=data1,
            mode='lines',
            name='Raw',
            line=dict(color=colors[0][1], width=1),
            opacity=0.5,
            hovertemplate='%{x|%Y-%m-%d}<br>Raw: %{y:,.0f}<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=dates1,
            y=smoothed1,
            mode='lines',
            name=f'Smoothed ({smooth_window}x)',
            line=dict(color=colors[0][0], width=2.5),
            hovertemplate='%{x|%Y-%m-%d}<br>Smoothed: %{y:,.1f}<extra></extra>'
        ))
    else:
        # Comparison mode - two series
        dates2, data2, smoothed2 = process_stats(stats2, start_date, end_date, smooth_window)
        
        # Series 1 - smoothed only for cleaner comparison
        fig.add_trace(go.Scatter(
            x=dates1,
            y=smoothed1,
            mode='lines',
            name=label1,
            line=dict(color=colors[0][0], width=2.5),
            hovertemplate=f'{label1}<br>%{{x|%Y-%m-%d}}<br>Value: %{{y:,.1f}}<extra></extra>'
        ))
        
        if dates2 is not None:
            # Series 2
            fig.add_trace(go.Scatter(
                x=dates2,
                y=smoothed2,
                mode='lines',
                name=label2,
                line=dict(color=colors[1][0], width=2.5),
                hovertemplate=f'{label2}<br>%{{x|%Y-%m-%d}}<br>Value: %{{y:,.1f}}<extra></extra>'
            ))
        else:
            print("No data for stats2 in date range")
    
    fig.update_layout(
        title=title,
        xaxis_title='Date',
        yaxis_title=metric_label + (' (log)' if log_scale else ''),
        height=450,
        hovermode='x',
        yaxis=dict(type='log' if log_scale else 'linear'),
        xaxis=dict(
            tickformat='%Y-%m-%d',
            hoverformat='%Y-%m-%d'
        )
    )
    
    fig.show()
    
    # Stats
    valid_data1 = [d for d in data1 if d > 0]
    if valid_data1:
        label = label1 if stats2 else metric_label
        print(f"\nStats for {label}:")
        print(f"  Peak: {max(data1):.2f}")
        print(f"  Average: {np.mean(valid_data1):.2f}")
        print(f"  Current: {data1[-1]:.2f}")
    
    if stats2 is not None and dates2 is not None:
        valid_data2 = [d for d in data2 if d > 0]
        if valid_data2:
            print(f"\nStats for {label2}:")
            print(f"  Peak: {max(data2):.2f}")
            print(f"  Average: {np.mean(valid_data2):.2f}")
            print(f"  Current: {data2[-1]:.2f}")


def plot_relationships_distribution(
    pair_history: PairHistory,
    start_date: str,
    end_date: str,
    reply_threshold: int = 3,
    log_scale: bool = True,
    max_relationships: int = 50,
    exclude_users: Optional[List[str]] = None
):
    """
    Plot distribution of relationships per user over a time period.
    
    For each user, counts how many alive and active_reply relationships they have
    during the period, then plots histograms of these counts.
    
    Args:
        pair_history: The pair history dict
        start_date: Start of period (YYYY-MM-DD)
        end_date: End of period (YYYY-MM-DD)
        reply_threshold: Min interactions for active_reply
        log_scale: Use log scale on y-axis
        max_relationships: Cap x-axis at this value (bins everything above)
        exclude_users: List of usernames to exclude from analysis
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import numpy as np
    from collections import defaultdict
    
    # Use timestamps for comparison to avoid timezone issues
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()
    
    print(f"Computing relationships for period {start_date} to {end_date}...")
    
    # Use cached directional history
    directional = get_or_build_directional_history(pair_history)
    
    # Filter out excluded users
    exclude_set = {u.lower() for u in exclude_users} if exclude_users else set()
    if exclude_set:
        original_count = len(directional)
        directional = {
            pair_key: pair_data 
            for pair_key, pair_data in directional.items()
            if pair_key[0] not in exclude_set and pair_key[1] not in exclude_set
        }
        print(f"Filtered out {original_count - len(directional):,} pairs containing excluded users")
    
    # Track relationships per user
    alive_per_user = defaultdict(int)
    active_reply_per_user = defaultdict(int)

    
    for pair_key, pair_data in tqdm(directional.items(), desc="Processing pairs"):
        user_a, user_b = pair_key
        
        # Use timestamps to avoid timezone comparison issues
        a_to_b = [dt for dt in pair_data['a_to_b'] if start_ts <= dt.timestamp() <= end_ts]
        b_to_a = [dt for dt in pair_data['b_to_a'] if start_ts <= dt.timestamp() <= end_ts]
        all_interactions = a_to_b + b_to_a
        
        # Check if ALIVE during period (bidirectional within window)
        # Simplified: just check if both directions have at least 1 interaction in period
        is_alive = len(a_to_b) > 0 and len(b_to_a) > 0
        
        # Check if ACTIVE_REPLY (>= threshold total interactions in period)
        is_active_reply = len(all_interactions) >= reply_threshold
        
        if is_alive:
            alive_per_user[user_a] += 1
            alive_per_user[user_b] += 1
        
        if is_active_reply:
            active_reply_per_user[user_a] += 1
            active_reply_per_user[user_b] += 1
    
    # Get all users who have at least one relationship
    all_users = set(alive_per_user.keys()) | set(active_reply_per_user.keys())
    all_users_list = list(all_users)
    
    # Create count arrays (capped at max_relationships)
    alive_counts = [min(alive_per_user.get(u, 0), max_relationships) for u in all_users_list]
    active_reply_counts = [min(active_reply_per_user.get(u, 0), max_relationships) for u in all_users_list]
    
    # Group users by relationship count for hover text
    def build_bin_data(counts, users, max_rel):
        """Build histogram data with usernames for hover."""
        from collections import defaultdict
        bin_users = defaultdict(list)
        for user, count in zip(users, counts):
            bin_users[count].append(user)
        
        x_vals = list(range(0, max_rel + 1))
        y_vals = [len(bin_users[x]) for x in x_vals]
        hover_texts = []
        for x in x_vals:
            users_in_bin = bin_users[x]
            n = len(users_in_bin)
            if n == 0:
                hover_texts.append(f"{x} relationships: 0 users")
            elif n <= 10:
                names = ", ".join(f"@{u}" for u in sorted(users_in_bin)[:5])
                hover_texts.append(f"{x} relationships: {n} users<br>{names}")
            else:
                hover_texts.append(f"{x} relationships: {n} users")
        return x_vals, y_vals, hover_texts
    
    alive_x, alive_y, alive_hover = build_bin_data(alive_counts, all_users_list, max_relationships)
    reply_x, reply_y, reply_hover = build_bin_data(active_reply_counts, all_users_list, max_relationships)
    
    # Create subplots
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            f'Alive Relationships per User',
            f'Active Reply (≥{reply_threshold}) Relationships per User'
        )
    )
    
    # Alive distribution (bar chart for custom hover)
    fig.add_trace(
        go.Bar(
            x=alive_x,
            y=alive_y,
            name='Alive',
            marker_color='steelblue',
            hovertext=alive_hover,
            hoverinfo='text'
        ),
        row=1, col=1
    )
    
    # Active reply distribution
    fig.add_trace(
        go.Bar(
            x=reply_x,
            y=reply_y,
            name='Active Reply',
            marker_color='coral',
            hovertext=reply_hover,
            hoverinfo='text'
        ),
        row=1, col=2
    )
    
    fig.update_layout(
        title=f'Distribution of Relationships per User ({start_date} to {end_date})',
        height=450,
        showlegend=False
    )
    
    fig.update_xaxes(title_text='Number of Relationships', row=1, col=1)
    fig.update_xaxes(title_text='Number of Relationships', row=1, col=2)
    fig.update_yaxes(title_text='Number of Users', type='log' if log_scale else 'linear', row=1, col=1)
    fig.update_yaxes(title_text='Number of Users', type='log' if log_scale else 'linear', row=1, col=2)
    
    fig.show()
    
    # Print summary stats
    print(f"\nPeriod: {start_date} to {end_date}")
    print(f"Total users with relationships: {len(all_users):,}")
    
    print(f"\nAlive relationships (bidirectional):")
    alive_nonzero = [c for c in alive_counts if c > 0]
    if alive_nonzero:
        print(f"  Users with ≥1: {len(alive_nonzero):,}")
        print(f"  Mean: {np.mean(alive_nonzero):.1f}")
        print(f"  Median: {np.median(alive_nonzero):.0f}")
        print(f"  Max: {max(alive_per_user.values())}")
    
    print(f"\nActive reply relationships (≥{reply_threshold} interactions):")
    reply_nonzero = [c for c in active_reply_counts if c > 0]
    if reply_nonzero:
        print(f"  Users with ≥1: {len(reply_nonzero):,}")
        print(f"  Mean: {np.mean(reply_nonzero):.1f}")
        print(f"  Median: {np.median(reply_nonzero):.0f}")
        print(f"  Max: {max(active_reply_per_user.values())}")
    
    return {
        'alive_per_user': dict(alive_per_user),
        'active_reply_per_user': dict(active_reply_per_user),
    }


def plot_alive_relationships(
    pair_history: PairHistory,
    window_days: int = 60,
    bin_days: int = 7,
    target_user: Optional[str] = None,
    smooth_window: int = 4,
    log_scale: bool = True,
    metric: str = 'alive_counts'
):
    """
    Convenience function: compute stats and plot in one call.
    
    Args:
        metric: 'alive_counts', 'active_users', or 'relationships_per_user'
    """
    stats = compute_alive_stats(
        pair_history,
        window_days=window_days,
        bin_days=bin_days,
        target_user=target_user
    )
    plot_alive_stats(stats, metric=metric, smooth_window=smooth_window, log_scale=log_scale)
    return stats


# %%

print("Loading caches...")
tweet_dict, conversation_trees = load_caches(auto_generate=False)

print(f"Loaded {len(tweet_dict)} tweets and {len(conversation_trees)} conversation trees")

# %%
# Get or build interaction history
pair_history = get_or_build_interaction_history(tweet_dict)

# Print stats
# %%
print_interaction_stats(pair_history)
# %%
# Show most active pairs
print(f"\n{'='*60}")
print("TOP 20 MOST ACTIVE USER PAIRS")
print(f"{'='*60}")
top_pairs = find_most_active_pairs(pair_history)
for (user_a, user_b), count in top_pairs:
    print(f"  @{user_a} <-> @{user_b}: {count:,} interactions")

# Example: show first interaction for top pair
if top_pairs:
    (user_a, user_b), _ = top_pairs[0]
    first = get_first_interaction(pair_history, user_a, user_b)
    if first:
        print(f"\n{'='*60}")
        print(f"FIRST INTERACTION: @{user_a} <-> @{user_b}")
        print(f"{'='*60}")
        print(f"  Date: {first['created_at']}")
        print(f"  From: @{first['from_user']} -> @{first['to_user']}")
        print(f"  Tweet ID: {first['tweet_id']}")
        print(f"  Text: {first['full_text'][:200]}...")

# %%
# ============================================================
# MANUAL INSPECTION: Pick a username to analyze
# ============================================================

# Change this to the username you want to inspect
TARGET_USERNAME = "33asr"

# %%
# ============================================================
# INTERACTIVE PLOT (Plotly with log scale, smoothed)
# ============================================================

# smooth_window=12 means 12-week rolling average with weekly bins
plot_user_interactions_interactive(TARGET_USERNAME, pair_history, bin_days=7, top_n=10, smooth_window=10)

# %%
# ============================================================
# VIEW THREADS FOR A SPECIFIC PAIR
# ============================================================

# Enter the two usernames you want to inspect (without @)
USER_A = "exgenesis"
USER_B = "visakanv"

# How many interactions to show
MAX_INTERACTIONS = 40

pair_key = make_pair_key(USER_A, USER_B)
print_twoway_thread(pair_key, pair_history, tweet_dict, conversation_trees, max_interactions=MAX_INTERACTIONS)

# %%
# ============================================================
# ALIVE RELATIONSHIPS - ENTIRE NETWORK
# ============================================================


user_to_exclude = []
# ["eigenrobot", "nosilverv", "defenderofbasic", "richdecibels", "qiaochuyuan", "exgenesis", "repligate", "tyleralterman", "algekalipso"]
# Compute stats once (expensive), then plot different metrics
# Pass tweet_dict to also compute tweet volume
stats = compute_alive_stats(
    pair_history,
    window_days=60,  # 2 months
    bin_days=7,      # weekly samples
    target_user=None,  # None = entire network
    tweet_dict=tweet_dict,
    reply_threshold=5,  # For active_reply_relations
    exclude_users=user_to_exclude
)
# %%
stats2 = compute_alive_stats(
    pair_history,
    window_days=60,  # 2 months
    bin_days=7,      # weekly samples
    target_user=None,  # None = entire network
    tweet_dict=None,
    reply_threshold=5,  # For active_reply_relations
)

# %%
# Plot 1: Total alive relationships
plot_alive_stats(
    stats,
    metric="alive_counts",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
    title_suffix=f"Exclude: {', '.join(user_to_exclude)}",
)

# %%
# Plot 2: Number of active users (users with at least one alive relationship)
plot_alive_stats(
    stats,
    metric="active_users",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 3: Relationships per active user (NORMALIZED)
plot_alive_stats(
    stats,
    metric="relationships_per_user",
    stats2=stats2,
    label1="Excluding top 10 users",
    label2="All users",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 4: Total tweet volume over time
plot_alive_stats(
    stats,
    metric="tweet_volume",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 5: Active reply relations
plot_alive_stats(
    stats,
    metric="active_reply_relations",
    stats2=stats2,
    label1="Excluding top 10 users",
    label2="All users",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 6: Active reply users
plot_alive_stats(
    stats,
    metric="active_reply_users",
    title_suffix=f"replies >= 5",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 7: Active reply relations per user
plot_alive_stats(
    stats,
    metric="active_reply_per_user",
   stats2=stats2,
    label1="Excluding top 10 users",
    label2="All users",
    smooth_window=0,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
    title_suffix=f"replies >= 5",
)

# %%
# ============================================================
# DISTRIBUTION OF RELATIONSHIPS PER USER (for a specific period)
# ============================================================

# Plot distribution of how many relationships each user has
dist_data = plot_relationships_distribution(
    pair_history,
    start_date='2018-01-01',
    end_date='2024-09-01',
    reply_threshold=5,
    log_scale=True,
    max_relationships=200
)

# Top 10 accounts by active reply relationships
top_reply = sorted(dist_data['active_reply_per_user'].items(), key=lambda x: x[1], reverse=True)[:10]
print("\nTop 10 accounts by active reply relationships:")
for i, (user, count) in enumerate(top_reply, 1):
    print(f"  {i:2}. @{user}: {count} relationships")

# Top 10 accounts by alive (bidirectional) relationships
top_alive = sorted(dist_data['alive_per_user'].items(), key=lambda x: x[1], reverse=True)[:10]
print("\nTop 10 accounts by alive (bidirectional) relationships:")
for i, (user, count) in enumerate(top_alive, 1):
    print(f"  {i:2}. @{user}: {count} relationships")

# %%
# ============================================================
# RELATIONSHIPS PER TWEET
# ============================================================

# Plot 8: Alive relationships per tweet
plot_alive_stats(
    stats,
    metric="alive_per_tweet",
    smooth_window=4,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
# Plot 9: Active reply relations per tweet
plot_alive_stats(
    stats,
    metric="active_reply_per_tweet",
    smooth_window=4,
    log_scale=False,
    start_date="2018-01-01",
    end_date="2024-09-01",
)

# %%
