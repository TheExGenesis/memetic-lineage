# %%
# let's enrich tweets with threads and QTs

# %%
import supabase

import pandas as pd
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
        year_top_quoted = get_top_quoted_tweets(year_tweets, min_quote_count=1)
        year_top_quoted = year_top_quoted.head(20)
        year_top_quoted['year'] = year
        top_quoted_by_year.append(year_top_quoted)
        
        f.write(f"\n\n{'#'*80}\n")
        f.write(f"### Top 20 quoted tweets for {year} ###\n")
        f.write(f"{'#'*80}\n")
        
        for _, tweet in year_top_quoted.iterrows():
            f.write(format_tweet(tweet))
            f.write('\n')

# Combine all years
all_top_quoted_by_year = pd.concat(top_quoted_by_year, ignore_index=True)
# %%
all_top_quoted_by_year
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
def print_conversation_tree(conversation_id, tweets_df, debug=False):
    """
    Print a conversation thread as a tree, given the conversation_id (which is the root tweet_id).
    Shows all replies in a tree structure and prints the time-span of the thread.
    
    Args:
        conversation_id: The tweet_id of the root tweet (conversation_id)
        tweets_df: DataFrame with tweet data
        debug: Enable debug logging
    
    Returns:
        String representation of the conversation tree
    """
    # Filter tweets in this conversation
    conversation_tweets = tweets_df[tweets_df['conversation_id'] == conversation_id]
    
    if conversation_tweets.empty:
        return f"No tweets found for conversation_id {conversation_id}"
    
    # Build children mapping for this conversation
    children_map = defaultdict(list)
    tweets_indexed = conversation_tweets.set_index('tweet_id')
    
    for tweet_id, row in tweets_indexed.iterrows():
        parent_id = row.get('reply_to_tweet_id')
        if pd.notna(parent_id) and parent_id in tweets_indexed.index:
            children_map[parent_id].append(tweet_id)
    
    # Find root tweet (should be the conversation_id itself)
    root_tweet_id = conversation_id
    if root_tweet_id not in tweets_indexed.index:
        return f"Root tweet {root_tweet_id} not found in conversation"
    
    # Calculate time span
    dates = conversation_tweets['created_at'].dropna()
    if not dates.empty:
        earliest = dates.min()
        latest = dates.max()
        time_span = f"{earliest.strftime('%Y-%m-%d %H:%M')} to {latest.strftime('%Y-%m-%d %H:%M')}"
        duration = latest - earliest
    else:
        time_span = "unknown"
        duration = timedelta(0)
    
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"Conversation: {conversation_id}")
    lines.append(f"Time span: {time_span}")
    lines.append(f"Duration: {duration}")
    lines.append(f"Total tweets: {len(conversation_tweets)}")
    lines.append(f"{'='*80}\n")
    
    # Recursive function to print tree
    def print_tweet_tree(tweet_id, depth=0, prefix="", is_last=True):
        if tweet_id not in tweets_indexed.index:
            return
        
        row = tweets_indexed.loc[tweet_id]
        created_at = row.get('created_at')
        if pd.notna(created_at):
            pretty_date = pd.Timestamp(created_at).strftime('%Y-%m-%d %H:%M')
        else:
            pretty_date = "unknown"
        
        username = row.get('username') or "unknown"
        full_text = row.get('full_text') or ""
        
        # Get metrics
        favorite_count = row.get('favorite_count', 0)
        retweet_count = row.get('retweet_count', 0)
        quoted_count = row.get('quoted_count', 0) if pd.notna(row.get('quoted_count')) else 0
        
        # Build metrics string with icons
        metrics = f"❤️ {favorite_count} 🔁 {retweet_count}"
        if quoted_count > 0:
            metrics += f" 💬 {quoted_count}"
        
        # Tree formatting
        if depth == 0:
            tree_prefix = ""
        else:
            tree_prefix = prefix + ("└── " if is_last else "├── ")
        
        # Calculate the indentation for text continuation lines
        text_indent = prefix + ('    ' if is_last else '│   ')
        
        # Format the header line with username, date, and metrics
        lines.append(f"{tree_prefix}@{username} ({pretty_date}) {metrics}")
        
        # Handle multi-line text with proper indentation
        text_lines = full_text.split('\n')
        for text_line in text_lines:
            lines.append(f"{text_indent}{text_line}")
        
        lines.append(f"{text_indent}[tweet_id: {tweet_id}]")
        
        # Print children
        children = children_map.get(tweet_id, [])
        for i, child_id in enumerate(children):
            is_last_child = (i == len(children) - 1)
            child_prefix = prefix + ("    " if is_last else "│   ")
            print_tweet_tree(child_id, depth + 1, child_prefix, is_last_child)
    
    # Start from root
    print_tweet_tree(root_tweet_id)
    
    return "\n".join(lines)

# %%
tree_output = print_conversation_tree(int(1919772733724098716), tweets, debug=True)
print(tree_output)  

# %%
