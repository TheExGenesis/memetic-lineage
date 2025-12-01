
#%% mapping tweet_id => cluster_ID or cluster_ID => tweet_ids

import json
# Load the mapping from tweet_id to cluster_id
with open('../index_to_cluster_mapping.json', 'r') as f:
    index_to_cluster = json.load(f)

# Convert keys and values to integers
index_to_cluster = {int(k): int(v) for k, v in index_to_cluster.items()}

print(f"Loaded mapping for {len(index_to_cluster)} tweet IDs to clusters")

# %%

import pandas as pd
import numpy as np
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone  
import os
import json
from pathlib import Path
from dotenv import load_dotenv

from lib.conversation_explorer import build_conversation_trees, build_incomplete_conversation_trees, build_quote_trees, print_conversation_threads
from lib.count_quotes import count_quotes
from lib.create_ascii_chart import create_ascii_chart
# Load environment variables
load_dotenv()
# %%
#ENRICHED_TWEETS_PATH = '/Users/frsc/Documents/Projects/data/2025-09-03_enriched_tweets.parquet' # for francisco
ENRICHED_TWEETS_PATH = '~/data/enriched_tweets.parquet' # for alexandre

tweets = pd.read_parquet(ENRICHED_TWEETS_PATH, dtype_backend='pyarrow')
tweets = tweets.set_index('tweet_id', drop=False)
# %%

tweets.index.name = 'index'

# Filter tweets to only those whose tweet_ids are in index_to_cluster
# clustered_tweet_ids = list(index_to_cluster.keys())
# tweets = tweets.loc[tweets.index.intersection(clustered_tweet_ids)]
# print(f"Filtered to {len(tweets)} tweets that are in clusters")


# %% drop duplicate values in the index
tweets = tweets[~tweets.index.duplicated(keep='first')]


tweets.head()

# %%
# Check if quoted counts cache exists
quoted_counts_cache_path = Path('../quoted_counts_cache.parquet')

if quoted_counts_cache_path.exists():
    print("Loading quoted counts from cache...")
    quoted_counts = pd.read_parquet(quoted_counts_cache_path)
else:
    print("Calculating quoted counts...")
    quoted_counts = count_quotes(tweets)
    quoted_counts = quoted_counts.groupby('quoted_tweet_id', as_index=False)['quoted_count'].sum()
    # Save to cache
    quoted_counts.to_parquet(quoted_counts_cache_path)
    print(f"Saved quoted counts cache to {quoted_counts_cache_path}")

tweets = tweets.merge(
    quoted_counts,
    left_index=True,
    right_on='quoted_tweet_id',
    how='left',
    suffixes=('', '_drop')
)
# Drop the duplicate quoted_tweet_id column from the merge
tweets = tweets.drop(columns=['quoted_tweet_id_drop'], errors='ignore')
# Fill NaN values with 0 for tweets that were never quoted
tweets['quoted_count'] = tweets['quoted_count'].fillna(0).astype(int)
# Reset index if index name is 'index' to avoid ambiguity when setting it again
if tweets.index.name == 'index':
    tweets = tweets.reset_index(drop=False)
# Now set tweet_id as index (it should only be a column at this point)
tweets = tweets.set_index('tweet_id', drop=False)
tweets.index.name = 'index'

# # %%
# # make tweets into a list of tweets as a dict where each key is a column name
# tweets_list = tweets.to_dict(orient='records')
# # %%

# conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is not None]
# # %%
# trees =  build_conversation_trees(conversation_tweet_list)
# # %%
# non_conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is None]

# # %%
# incomplete_trees =  build_incomplete_conversation_trees(non_conversation_tweet_list, [])

# # %% merge complete conversation trees, incomplete conversation trees, and quote trees
# complete_reply_trees = {**trees, **incomplete_trees}

# %%
from typing import List, Tuple
from datetime import datetime
import numpy as np

def wiener_index(tree: dict) -> float:
    """
    Calculate Wiener index (structural virality): average pairwise distance in tree.
    
    tree: dict with keys 'children', 'parents', 'root'
    returns: float - average pairwise distance, or 0 if tree has <= 1 node
    """
    children = tree['children']
    root = tree['root']
    
    if root is None:
        return 0.0
    
    # BFS to compute distances from root to all nodes
    nodes = [root]
    queue = [root]
    visited = {root}
    
    while queue:
        node = queue.pop(0)
        for child in children.get(node, []):
            if child not in visited:
                visited.add(child)
                nodes.append(child)
                queue.append(child)
    
    if len(nodes) <= 1:
        return 0.0
    
    # Compute all pairwise distances using BFS from each node
    total_distance = 0
    pair_count = 0
    
    for start in nodes:
        distances = {start: 0}
        queue = [start]
        
        while queue:
            curr = queue.pop(0)
            curr_dist = distances[curr]
            
            # Check parent
            parent = tree['parents'].get(curr)
            if parent and parent not in distances:
                distances[parent] = curr_dist + 1
                queue.append(parent)
            
            # Check children
            for child in children.get(curr, []):
                if child not in distances:
                    distances[child] = curr_dist + 1
                    queue.append(child)
        
        for end in nodes:
            if end > start:  # avoid double counting
                total_distance += distances[end]
                pair_count += 1
    
    return total_distance / pair_count if pair_count > 0 else 0.0

def temporal_half_life(timestamps: List, percentile: float = 0.5) -> float:
    """
    Calculate temporal half-life: time from first timestamp until percentile of events occurred.
    
    timestamps: List[datetime|str] - chronologically ordered or unordered timestamps
    percentile: float - fraction of total events (0.5 for half-life, 0.8 for 80%)
    returns: float - hours from first to percentile threshold
    """
    if not timestamps or len(timestamps) < 2:
        return 0.0
    
    # Convert to datetime if strings
    parsed_ts = [pd.to_datetime(ts) if isinstance(ts, str) else ts for ts in timestamps]
    sorted_ts = sorted(parsed_ts)
    first_time = sorted_ts[0]
    target_idx = int(len(sorted_ts) * percentile)
    target_time = sorted_ts[target_idx]
    
    return (target_time - first_time).total_seconds() / 3600.0  # hours

def calculate_quote_half_lives(tweets_df: pd.DataFrame, percentile: float = 0.5) -> pd.Series:
    """
    Calculate temporal half-life for all tweets based on their quote tweets.
    
    tweets_df: DataFrame with 'quoted_tweet_id', 'created_at', indexed by tweet_id
    percentile: float - fraction threshold (0.5 for half-life, 0.8 for 80%)
    returns: Series indexed by tweet_id with half-life in hours (NaN for tweets with <2 quotes)
    """
    # Group by quoted_tweet_id to get all quotes for each tweet
    quote_groups = tweets_df[tweets_df['quoted_tweet_id'].notna()].groupby('quoted_tweet_id')
    half_lives = {}
    for quoted_id, group in quote_groups:
        # Get the author of the quoted tweet
        quoted_author = tweets_df.loc[quoted_id, 'account_id'] if quoted_id in tweets_df.index else None
        
        # Filter out quotes from the same author
        if quoted_author is not None:
            
            try:
                group = group[group['account_id'] != quoted_author]
            except:
                print("KeyError: quoted_author", quoted_author)
                print("quoted_id", quoted_id)
                print("--------------------------------")
                print("group", group)
                print("--------------------------------")
                raise
        
        if len(group) >= 2:  # need at least 2 for meaningful half-life
            timestamps = group['created_at'].tolist()
            half_lives[quoted_id] = temporal_half_life(timestamps, percentile)
    return pd.Series(half_lives, name=f'half_life_p{int(percentile*100)}')
# %% Calculate half-lives for all quoted tweets.
half_life_path = '../half_life_50.pkl'
OVERWRITE_HALF_LIFE_CALCULATION = False

PERCENTILE = 0.8

if OVERWRITE_HALF_LIFE_CALCULATION or not os.path.exists(half_life_path):
    print("Calculating half-lives...")
    half_life_50 = calculate_quote_half_lives(tweets, percentile=PERCENTILE)
    os.makedirs(os.path.dirname(half_life_path), exist_ok=True)
    half_life_50.to_pickle(half_life_path)
    print(f"Saved half-life results to {half_life_path}")
else:
    print(f"Loading existing half-life results from {half_life_path}")
    half_life_50 = pd.read_pickle(half_life_path)

print(f"\nCalculated half-lives for {len(half_life_50)} tweets")
print(f"Stats for 50% half-life (hours):")
print(half_life_50.describe())
#
# Merge back into tweets dataframe
tweets['half_life_hours'] = tweets.index.map(half_life_50)
# %%

# We picked 80% half-life because it gives us longer lasting tweets and helps ignore bursts
# max col width
# pd.set_option('display.max_colwidth', None)
# filter top 50 by quoted_count and then sort by hours for each year
tweets_with_year = tweets[tweets.half_life_hours.notna()].copy()
tweets_with_year['created_at'] = pd.to_datetime(tweets_with_year['created_at'])
tweets_with_year['year'] = tweets_with_year['created_at'].dt.year

# %%
def print_top_tweets_by_year(year=None, N=50):
    """Print top 50 tweets by quoted_count for a given year (or all years if None), sorted by half_life_hours"""
    if year is None:
        year_tweets = tweets_with_year
        year_label = "All Years"
    else:
        year_tweets = tweets_with_year[tweets_with_year['year'] == year]
        year_label = f"Year {year}"
    
    top_50_quoted_count = year_tweets.sort_values(by='quoted_count', ascending=False).head(N)
    
    output_lines = []
    output_lines.append(f"\n=== {year_label} ===")

    #print(top_50_quoted_count.sort_values(by='quoted_count', ascending=False).head(50))
    # print the usernames, the full text, the quoted count, and the half life hours sorted by half life hours in a table
    sorted_tweets = top_50_quoted_count.sort_values(by='half_life_hours', ascending=False).head(N)

    
    # Display timeseries for each quoted tweet
    output_lines.append(f"\n{'='*70}")
    output_lines.append(f"Quote Distribution Timeseries for Top Tweets in {year_label}")
    output_lines.append(f"{'='*70}\n")

    # get the min and max dates of the tweets quoting any of the top 50 tweets
    min_date = tweets[tweets['quoted_tweet_id'].isin(sorted_tweets.index)]['created_at'].min()
    max_date = tweets[tweets['quoted_tweet_id'].isin(sorted_tweets.index)]['created_at'].max()
    
    for idx, (tweet_id, tweet_row) in enumerate(sorted_tweets.iterrows(), 1):
        # Get the dates of tweets quoting this tweet
        quoting_dates = tweets[tweets['quoted_tweet_id'] == tweet_id]['created_at']
        
        if len(quoting_dates) > 0:
            half_life_str = f"{tweet_row.get('half_life_hours', 0):.2f}" if pd.notna(tweet_row.get('half_life_hours')) else "N/A"
            output_lines.append(f"\n[{idx}/{len(sorted_tweets)}] Tweet ID: {tweet_id}")
            output_lines.append(f"Author: @{tweet_row.get('username', 'unknown')}")

            output_lines.append(f"Created at: {tweet_row.get('created_at', 'N/A')}")


            output_lines.append(f"Quoted count: {tweet_row['quoted_count']} | Half-life ({PERCENTILE*100}%): {half_life_str} hours")
            full_text = str(tweet_row.get('full_text', 'N/A'))
            text_preview = full_text[:500] + "..." if len(full_text) > 500 else full_text
            output_lines.append(f"Text: {text_preview}")
            output_lines.append("\nQuote timeline:")
            output_lines.append(create_ascii_chart(quoting_dates, min_date=min_date, max_date=max_date))
            output_lines.append("\n" + "-"*70)
    
    return "\n".join(output_lines)


# for year in sorted(tweets_with_year['year'].unique()):
#     print_top_tweets_by_year(year)
# %%

all_year = print_top_tweets_by_year(None, N=100)

# %% Add to a file

with open('top_quoted_tweets_by_year.txt', 'w') as f:
    f.write(all_year)

# I think half life doesn something, it gives us longer lasting tweets and helps ignore bursts

# half life is too coarse: confuses recency of tweets with burstiness

# %%
# for the top quoted_count tweet, call create_ascii_chart with a list of dates of tweets quoting it
top_quoted_count_tweet_id = tweets[tweets.quoted_count.notna()].sort_values(by='quoted_count', ascending=False).head(1)['tweet_id'].values[0]
top_quoted_count_tweet = tweets.loc[top_quoted_count_tweet_id]
# get the dates of tweets quoting it
quoting_dates = tweets[tweets['quoted_tweet_id'] == top_quoted_count_tweet_id]['created_at']
# call create_ascii_chart with the quoting dates
print(create_ascii_chart(quoting_dates))

# %%
# %%


columns = ["tweet_id", "created_at", "quoted_tweet_id", "quoted_count", "half_life_hours"]
tweets[columns].head()
# %%