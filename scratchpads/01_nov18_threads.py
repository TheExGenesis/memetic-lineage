# %%
# let's enrich tweets with threads and QTs

# %%
import supabase

import pandas as pd
import numpy as np
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone  
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# %%
# Load columns with names containing "_id" as str to preserve full precision

id_columns = ['tweet_id', 'reply_to_tweet_id', 'reply_to_user_id', 'quoted_tweet_id', 'conversation_id',]
tweets = pd.read_parquet('../data/2025-09-03_enriched_tweets.parquet', dtype_backend='pyarrow')
tweets

# %%
tweets = pd.read_parquet('enriched_tweets.parquet', dtype_backend='pyarrow')
tweets.head()

# %%
# print types of columns
print(tweets.dtypes)
"""
tweet_id                       int64[pyarrow]
account_id                     int64[pyarrow]
username                large_string[pyarrow]
account_display_name    large_string[pyarrow]
created_at              large_string[pyarrow]
full_text               large_string[pyarrow]
retweet_count                  int64[pyarrow]
favorite_count                 int64[pyarrow]
reply_to_tweet_id              int64[pyarrow]
reply_to_user_id               int64[pyarrow]
reply_to_username       large_string[pyarrow]
quoted_tweet_id                int64[pyarrow]
conversation_id                int64[pyarrow]
avatar_media_url        large_string[pyarrow]
archive_upload_id              int64[pyarrow]
dtype: object
"""

# %%
# Convert created_at to datetime
tweets['created_at'] = pd.to_datetime(tweets['created_at'])
print(f"created_at dtype after conversion: {tweets['created_at'].dtype}")

# %%
from collections import defaultdict
import sys

# Increase max col width for better output readability
pd.set_option('display.max_colwidth', None)
# %%
def get_thread_for_tweet(
    tweet_id, 
    tweets: pd.DataFrame, 
    debug: bool = False,
) -> str:
    """
    Returns the sequence of tweets in a thread upstream of the given tweet,
    i.e., this tweet, its parent, its parent's parent, etc. up to the root.
    Returns a pretty-formatted string, oldest-to-newest (root first).
    """
    obs = {}  # observability dictionary for logging

    if tweets.empty or "tweet_id" not in tweets.columns:
        if debug:
            print(f"[get_thread_for_tweet][tweet_id={tweet_id}] tweets DataFrame empty or missing 'tweet_id' column", file=sys.stderr)
        return ""

    # Create a mapping for quick lookups
    tweets_indexed = tweets.set_index('tweet_id')

    current_id = tweet_id
    thread_chain = []
    visited = set()
    step = 0

    while current_id and current_id in tweets_indexed.index:
        if current_id in visited:
            # Avoid infinite loop in case of data error/cycle
            if debug:
                print(f"[get_thread_for_tweet][tweet_id={tweet_id}][step={step}] Cycle detected at tweet_id={current_id}.", file=sys.stderr)
            break
        visited.add(current_id)
        row = tweets_indexed.loc[current_id]
        thread_chain.append(row)
        parent_id = row.get("reply_to_tweet_id")

        if debug:
            print(
                f"[get_thread_for_tweet][tweet_id={tweet_id}][step={step}] Added: tweet_id={current_id}, parent_id={parent_id}, username={row.get('username')}, text={(row.get('full_text') or '')[:30]}...",
                file=sys.stderr,
            )

        # Climb to parent (the tweet this one replied to)
        if pd.isna(parent_id) or parent_id not in tweets_indexed.index:
            if debug:
                if pd.isna(parent_id):
                    print(
                        f"[get_thread_for_tweet][tweet_id={tweet_id}][step={step}] Finished: parent_id is NaN.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[get_thread_for_tweet][tweet_id={tweet_id}][step={step}] Finished: parent_id {parent_id} not found in tweets.",
                        file=sys.stderr,
                    )
            break
        current_id = parent_id
        step += 1

    # thread_chain is newest to oldest, so reverse for root-first order
    if debug:
        print(
            f"[get_thread_for_tweet][tweet_id={tweet_id}] Completed chain of length {len(thread_chain)} (reversed for output).",
            file=sys.stderr,
        )

    thread_chain.reverse()
    lines = []
    for depth, row in enumerate(thread_chain):
        created_at = row.get("created_at")
        if pd.notna(created_at):
            pretty_date = pd.Timestamp(created_at).strftime('%Y-%m-%d %H:%M')
        else:
            pretty_date = "unknown"
        username = row.get("username") or "unknown"
        full_text = row.get("full_text") or ""
        prefix = '    ' * depth + ('└─ ' if depth > 0 else '')
        lines.append(
            f"{prefix}{username}: {full_text} ({pretty_date}) {row.name}"
        )
        if debug:
            print(
                f"[get_thread_for_tweet][tweet_id={tweet_id}][line={depth}] prefix='{prefix}', username='{username}', tweet_id={row.name}",
                file=sys.stderr,
            )
    if debug:
        print(f"[get_thread_for_tweet][tweet_id={tweet_id}] Output ready.", file=sys.stderr)
    return "\n".join(lines)


# %%
test_tweet_id = int(1456556213802618881)
thread_text = get_thread_for_tweet(test_tweet_id, tweets, debug=True)

# %%
def count_quotes(tweets_df):
    """
    Count how many times each tweet is quoted by others (excluding self-quotes).
    
    Args:
        tweets_df: DataFrame with columns 'quoted_tweet_id', 'tweet_id', 'account_id'
    
    Returns:
        DataFrame with columns 'quoted_tweet_id' and 'quoted_count', sorted by count descending
    """
    # Filter out self-quotes: only count quotes where the quoting user differs from the quoted tweet's author
    # First, get the account_id for each quoted tweet
    quoted_tweet_authors = tweets_df[['tweet_id', 'account_id']].rename(
        columns={'tweet_id': 'quoted_tweet_id', 'account_id': 'quoted_author_id'}
    )
    
    # Merge to get both the quoting user and the quoted tweet's author
    tweets_with_authors = tweets_df.merge(
        quoted_tweet_authors, 
        on='quoted_tweet_id', 
        how='left'
    )
    
    # Filter to only quotes where account_id != quoted_author_id (exclude self-quotes)
    non_self_quotes = tweets_with_authors[
        tweets_with_authors['account_id'] != tweets_with_authors['quoted_author_id']
    ]
    
    # Count number of times tweets are quoted (by others)
    quoted_counts = non_self_quotes.groupby('quoted_tweet_id').size().reset_index(
        name='quoted_count'
    ).sort_values(by='quoted_count', ascending=False)
    
    return quoted_counts


# %%
# Patch tweets with quote counts
quoted_counts = count_quotes(tweets)
tweets = tweets.merge(
    quoted_counts,
    left_on='tweet_id',
    right_on='quoted_tweet_id',
    how='left',
    suffixes=('', '_drop')
)
# Drop the duplicate quoted_tweet_id column from the merge
tweets = tweets.drop(columns=['quoted_tweet_id_drop'], errors='ignore')
# Fill NaN values with 0 for tweets that were never quoted
tweets['quoted_count'] = tweets['quoted_count'].fillna(0).astype(int)


# quotes are high signal
# but visa qts himself a lot
# %%
def format_tweet(tweet_row):
    """Format a tweet as a string with its metrics."""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"Date: {tweet_row['created_at']}")
    lines.append(f"User: @{tweet_row['username']}")
    lines.append(f"URL: https://twitter.com/{tweet_row['username']}/status/{tweet_row['tweet_id']}")
    lines.append(f"\nTweet text:")
    lines.append(f"  {tweet_row['full_text']}")
    
    # Add quoted tweet if available
    if pd.notna(tweet_row.get('quoted_tweet_id')):
        quoted_text = tweet_row.get('quoted_full_text', 'N/A')
        lines.append(f"\nQuoted tweet:")
        lines.append(f"  {quoted_text}")
    
    lines.append(f"\nMetrics:")
    lines.append(f"  Quotes: {tweet_row.get('quoted_count', 0)}")
    lines.append(f"  Likes: {tweet_row.get('favorite_count', 0)}")
    lines.append(f"  Retweets: {tweet_row.get('retweet_count', 0)}")
    lines.append(f"{'='*80}")
    return '\n'.join(lines)

def print_tweet(tweet_row):
    """Print a formatted view of a tweet with its metrics."""
    print(format_tweet(tweet_row))

# %%
# Get top 20 quoted tweets per year
tweets['year'] = tweets['created_at'].dt.year
top_quoted_by_year = []
with open('top_quoted_tweets_by_year.txt', 'w', encoding='utf-8') as f:
    for year in sorted(tweets['year'].unique()):
        year_tweets = tweets[tweets['year'] == year]
        # year_top_quoted = get_top_quoted_tweets(year_tweets, min_quote_count=1)
        # year_top_quoted = year_top_quoted.head(20)
        # year_top_quoted['year'] = year
        # top_quoted_by_year.append(year_top_quoted)
        
        f.write(f"\n\n{'#'*80}\n")
        f.write(f"### Top 20 quoted tweets for {year} ###\n")
        f.write(f"{'#'*80}\n")
        
        # for _, tweet in year_top_quoted.iterrows():
        #     f.write(format_tweet(tweet))
        #     f.write('\n')

# Combine all years
# all_top_quoted_by_year = pd.concat(top_quoted_by_year, ignore_index=True)
# %%
# all_top_quoted_by_year
# %%
# let's count how many tweets have the same conversation_id, get a dict of conversation_id to count. then let's implement a function that prints a thread with all its children as a tree (cli tree style) given a conversation_id which corresponds to the tweet_id of the root. Also prints the time-span of the thread (date of original post and date of most recent leaf). Find leaves via reply_to_tweet_id. Probably good to make a dict of reply_to_tweet_id to tweet_id[]
# %%
# count how many tweets have the same conversation_id, excluding replies by the original author
# First, get the author of each conversation (the root tweet)
conversation_authors = tweets[['conversation_id', 'account_id']].drop_duplicates('conversation_id').rename(
    columns={'account_id': 'conversation_author_id'}
)

# Merge to get the conversation author for each tweet
tweets_with_conv_author = tweets.merge(
    conversation_authors,
    on='conversation_id',
    how='left'
)

# Filter to only count replies by people other than the original author
other_author_replies = tweets_with_conv_author[
    tweets_with_conv_author['account_id'] != tweets_with_conv_author['conversation_author_id']
]

# Count replies by others per conversation
conversation_counts = other_author_replies.groupby('conversation_id').size().reset_index(name='count')
conversation_counts
# %%
# print the top 10 conversation_ids by count
print(conversation_counts.sort_values(by='count', ascending=False).head(10))
# %%
# let's print the root tweets that have top conversation_ids
top_conversation_tweets = tweets[tweets['tweet_id'].isin(conversation_counts.sort_values(by='count', ascending=False).head(10)['conversation_id'])]
for _, tweet in top_conversation_tweets.iterrows():
    print_tweet(tweet)
# %%

# %%
class ConversationExplorer:
    def __init__(self, tweets_df: pd.DataFrame):
        # 1. Pre-index the dataframe for O(1) lookups (Critical for performance)
        print("Indexing tweets...")
        self.df = tweets_df.set_index('tweet_id')
        
        # 2. Pre-build adjacency list for O(1) child lookup
        # This avoids filtering the whole DF to find replies
        print("Building conversation graph...")
        self.children_map = defaultdict(list)
        
        # Vectorized approach is faster than iterating rows
        if 'reply_to_tweet_id' in tweets_df.columns:
             # Filter for rows that are replies and not NA
             # We specifically select columns to avoid overhead
             replies = tweets_df[tweets_df['reply_to_tweet_id'].notna()][['tweet_id', 'reply_to_tweet_id']]
             
             # Iterate over the filtered DataFrame (much smaller than 300k if not all are replies)
             for tid, parent_id in zip(replies['tweet_id'], replies['reply_to_tweet_id']):
                 self.children_map[int(parent_id)].append(tid)

    def print_tree(self, 
                   tweet_ids, 
                   depth_up: int | None = None, 
                   depth_down: int | None = None, 
                   debug: bool = False,
                   _visited_annexes: set | None = None,
                   _printed_ids: set | None = None) -> str:
        
        if _visited_annexes is None: _visited_annexes = set()
        if _printed_ids is None: _printed_ids = set()
        
        # Normalize input
        if isinstance(tweet_ids, (int, float, str, np.integer)):
            tweet_ids = [int(tweet_ids)]
        else:
            tweet_ids = [int(tid) for tid in tweet_ids]
            
        valid_seeds = [tid for tid in tweet_ids if tid in self.df.index]
        if not valid_seeds: return "No valid tweet IDs found."

        # Group seeds by conversation ID
        seeds_by_conv = defaultdict(list)
        for tid in valid_seeds:
            conv_id = self.df.loc[tid].get('conversation_id')
            if pd.notna(conv_id):
                seeds_by_conv[int(conv_id)].append(tid)
            else:
                seeds_by_conv[tid].append(tid)

        lines = []
        annex_ids_to_process = []

        for conv_id, conv_seeds in seeds_by_conv.items():
            # Determine visible set using graph traversal (BFS/DFS) with pre-computed maps
            visible_ids = set()
            
            def traverse_up(curr_id, steps_left):
                if curr_id not in self.df.index: return
                visible_ids.add(curr_id)
                if steps_left is not None and steps_left <= 0: return
                
                parent_id = self.df.loc[curr_id].get('reply_to_tweet_id')
                if pd.notna(parent_id):
                    traverse_up(int(parent_id), None if steps_left is None else steps_left - 1)

            def traverse_down(curr_id, steps_left):
                visible_ids.add(curr_id)
                if steps_left is not None and steps_left <= 0: return
                
                # O(1) lookup instead of filtering
                children = self.children_map.get(curr_id, [])
                for child_id in children:
                    if child_id in self.df.index: # Ensure child exists in data
                         traverse_down(child_id, None if steps_left is None else steps_left - 1)

            for seed in conv_seeds:
                traverse_up(seed, depth_up)
                traverse_down(seed, depth_down)

            _printed_ids.update(visible_ids)

            # Identify roots of the *visible* forest
            print_roots = []
            for vid in visible_ids:
                parent = self.df.loc[vid].get('reply_to_tweet_id')
                # If parent is missing or parent is not in the visible set, this is a root
                if pd.isna(parent) or int(parent) not in visible_ids:
                    print_roots.append(vid)
            print_roots.sort()

            def print_quote(q_id, indent):
                if q_id not in self.df.index:
                    lines.append(f"{indent}[Quoted tweet {q_id} not found]")
                    return
                    
                row = self.df.loc[q_id]
                username = row.get('username') or "unknown"
                text = row.get('full_text') or ""
                created_at = row.get('created_at')
                date = pd.Timestamp(created_at).strftime('%Y-%m-%d') if pd.notna(created_at) else "?"
                
                lines.append(f"{indent}@{username} ({date}) [Quoted id:{q_id}]:")
                for line in text.split('\n'):
                    lines.append(f"{indent}  {line}")
                
                need_annex = True
                if depth_up == 0 and depth_down == 0:
                    need_annex = False
                
                if q_id in _printed_ids:
                    need_annex = False
                    
                if need_annex:
                    lines.append(f"{indent}(See Annex below for full context)")
                    if q_id not in _visited_annexes:
                         annex_ids_to_process.append(q_id)
                         _visited_annexes.add(q_id)
                
                next_q = row.get('quoted_tweet_id')
                if pd.notna(next_q):
                    print_quote(int(next_q), indent + "    ┃ ")

            def format_node(tid, depth, prefix, is_last_child):
                row = self.df.loc[tid]
                created_at = row.get('created_at')
                pretty_date = pd.Timestamp(created_at).strftime('%Y-%m-%d %H:%M') if pd.notna(created_at) else "unknown"
                username = row.get('username') or "unknown"
                full_text = row.get('full_text') or ""
                
                metrics = f"❤️ {row.get('favorite_count', 0)} 🔁 {row.get('retweet_count', 0)}"
                quoted_cnt = row.get('quoted_count', 0)
                if pd.notna(quoted_cnt) and quoted_cnt > 0:
                     metrics += f" 💬 {int(quoted_cnt)}"
                     
                if depth == 0:
                    curr_prefix = ""
                    child_prefix = "" 
                else:
                    curr_prefix = prefix + ("└── " if is_last_child else "├── ")
                    child_prefix = prefix + ("    " if is_last_child else "│   ")
                    
                lines.append(f"{curr_prefix}@{username} ({pretty_date}) {metrics} [id:{tid}]")
                
                text_indent = child_prefix + ("    " if depth == 0 else "") 
                if depth == 0: text_indent = "    "
                
                for line in full_text.split('\n'):
                    lines.append(f"{text_indent}{line}")
                    
                quoted_id = row.get('quoted_tweet_id')
                if pd.notna(quoted_id):
                    quoted_id = int(quoted_id)
                    print_quote(quoted_id, text_indent + "    ┃ ")
                    
                # Use pre-built children map
                children = [c for c in self.children_map.get(tid, []) if c in visible_ids]
                children.sort()
                
                for i, child in enumerate(children):
                    is_last = (i == len(children) - 1)
                    next_prefix = prefix + ("    " if is_last_child else "│   ")
                    if depth == 0: next_prefix = "" 
                    format_node(child, depth + 1, next_prefix, is_last)

            if not print_roots:
                lines.append("No visible tweets found.")

            for root in print_roots:
                format_node(root, 0, "", True)
                lines.append("") 

        # Process Annexes (Recursive call to method)
        for annex_id in annex_ids_to_process:
            lines.append(f"\n>>> Annex: Context for Quoted Tweet {annex_id} <<<")
            # Call the method on self
            annex_text = self.print_tree(
                [annex_id], 
                depth_up=depth_up, 
                depth_down=depth_down, 
                debug=debug,
                _visited_annexes=_visited_annexes,
                _printed_ids=_printed_ids
            )
            lines.append(annex_text)

        return "\n".join(lines)

# %%
# Tests with synthetic data
def run_synthetic_tests():
    print("Running tests with synthetic data...")
    
    # Create synthetic dataframe matching schema
    base_time = pd.Timestamp("2025-01-01 12:00:00+00:00")
    
    data = [
        # Root tweet (ID 1) - Quotes Tweet 10
        {
            "tweet_id": 1, "account_id": 101, "username": "alice", "account_display_name": "Alice",
            "created_at": base_time, "full_text": "Root tweet about AI.",
            "reply_to_tweet_id": None, "conversation_id": 1, "quoted_tweet_id": 10
        },
        # Reply to Root (ID 2)
        {
            "tweet_id": 2, "account_id": 102, "username": "bob", "account_display_name": "Bob",
            "created_at": base_time + timedelta(minutes=5), "full_text": "Interesting point, Alice.",
            "reply_to_tweet_id": 1, "conversation_id": 1, "quoted_tweet_id": None
        },
        # Reply to Root (ID 3) - Another branch
        {
            "tweet_id": 3, "account_id": 103, "username": "charlie", "account_display_name": "Charlie",
            "created_at": base_time + timedelta(minutes=10), "full_text": "I disagree completely.",
            "reply_to_tweet_id": 1, "conversation_id": 1, "quoted_tweet_id": None
        },
        # Reply to Bob (ID 4) - Depth 2
        {
            "tweet_id": 4, "account_id": 101, "username": "alice", "account_display_name": "Alice",
            "created_at": base_time + timedelta(minutes=15), "full_text": "Thanks Bob!",
            "reply_to_tweet_id": 2, "conversation_id": 1, "quoted_tweet_id": None
        },
        # Reply to Root that quotes an external tweet (ID 5)
        {
            "tweet_id": 5, "account_id": 104, "username": "dave", "account_display_name": "Dave",
            "created_at": base_time + timedelta(minutes=20), "full_text": "Look at this external context.",
            "reply_to_tweet_id": 1, "conversation_id": 1, "quoted_tweet_id": 900
        },
        # Reply to Dave (ID 6)
        {
            "tweet_id": 6, "account_id": 102, "username": "bob", "account_display_name": "Bob",
            "created_at": base_time + timedelta(minutes=25), "full_text": "I see the external context.",
            "reply_to_tweet_id": 5, "conversation_id": 1, "quoted_tweet_id": None
        },
        # Tweet 10: Separate Root - Quotes Tweet 2 (Cross-thread)
        {
            "tweet_id": 10, "account_id": 107, "username": "grace", "account_display_name": "Grace",
            "created_at": base_time + timedelta(minutes=30), "full_text": "Another separate thread.",
            "reply_to_tweet_id": None, "conversation_id": 10, "quoted_tweet_id": 2
        },
        # External Tweet (ID 900) - Quoted by 5
        {
            "tweet_id": 900, "account_id": 105, "username": "eve", "account_display_name": "Eve",
            "created_at": base_time - timedelta(days=1), "full_text": "External tweet being quoted.",
            "reply_to_tweet_id": None, "conversation_id": 900, "quoted_tweet_id": 901
        },
        # Nested Quote (ID 901) - Quoted by 900
        {
            "tweet_id": 901, "account_id": 106, "username": "frank", "account_display_name": "Frank",
            "created_at": base_time - timedelta(days=2), "full_text": "Deep nested wisdom.",
            "reply_to_tweet_id": None, "conversation_id": 901, "quoted_tweet_id": None
        }
    ]
    
    # Fill missing columns with defaults
    default_cols = {
        "retweet_count": 0, "favorite_count": 0, "reply_to_user_id": None, 
        "reply_to_username": None, "avatar_media_url": "", "archive_upload_id": 0, 
        "quoted_count": 0, "account_id": 0
    }
    
    for row in data:
        for k, v in default_cols.items():
            if k not in row:
                row[k] = v
                
    df_synth = pd.DataFrame(data)
    
    # Initialize Explorer
    explorer = ConversationExplorer(df_synth)
    
    print("\n--- Test 1: Full Tree with Cross-Thread Quotes (Seed: 1) ---")
    print(explorer.print_tree(1))
    print("\nEXPECTED: Tree 1 with children 2, 3, 5. 5 quotes 900. 1 quotes 10.")
    print("          Annex 10 (root). 10 quotes 2. 2 is ALREADY printed in Main Tree 1, so NO Annex 2.")
    print("          Annex 900. 900 quotes 901. Annex 901.")

    print("\n--- Test 2: Multiple Focus Tweets (Seeds: 1, 10) ---")
    print(explorer.print_tree([1, 10]))
    print("\nEXPECTED: Two main conversation blocks (1 and 10).")
    
    print("\n--- Test 3: Subtree with Quote (Seed: 5) ---")
    print(explorer.print_tree(5))
    print("\nEXPECTED: Tree starting at 5 (reply to 1). 5 quotes 900. Annex 900.")

run_synthetic_tests()  

# %%
# Test with real data from the loaded dataframe
print("\n==========================================")
print("--- Test with Real Data from 'tweets' DF ---")
# Using a known ID from earlier in the file

real_explorer = ConversationExplorer(tweets)

# %%

target_real_id = 1322462839622291463
if 'tweets' in locals() and not tweets.empty:

    
    if target_real_id in tweets['tweet_id'].values:
        print(f"Printing tree for specific real tweet {target_real_id}")
        print(real_explorer.print_tree(target_real_id))
    else:
        # Fallback to first tweet
        fallback_id = tweets.iloc[0]['tweet_id']
        print(f"Specific ID not found. Printing tree for first available tweet {fallback_id}")
        print(real_explorer.print_tree(fallback_id))
else:
    print("Tweets dataframe not available or empty.")

# %%
