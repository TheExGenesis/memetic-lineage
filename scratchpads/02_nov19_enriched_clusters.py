
#%% mapping tweet_id => cluster_ID or cluster_ID => tweet_ids

import json
# Load the mapping from tweet_id to cluster_id
with open('../index_to_cluster_mapping.json', 'r') as f:
    index_to_cluster = json.load(f)

# Convert keys and values to integers
index_to_cluster = {int(k): int(v) for k, v in index_to_cluster.items()}

print(f"Loaded mapping for {len(index_to_cluster)} tweet IDs to clusters")

# %%

from conversation_explorer import ConversationExplorer, count_quotes


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
ENRICHED_TWEETS_PATH = '/Users/frsc/Documents/Projects/data/2025-09-03_enriched_tweets.parquet'
tweets = pd.read_parquet(ENRICHED_TWEETS_PATH, dtype_backend='pyarrow')

# Set tweet_id as index for efficient selection
tweets = tweets.set_index('tweet_id', drop=False)

# Filter tweets to only those whose tweet_ids are in index_to_cluster
# clustered_tweet_ids = list(index_to_cluster.keys())
# tweets = tweets.loc[tweets.index.intersection(clustered_tweet_ids)]
# print(f"Filtered to {len(tweets)} tweets that are in clusters")

tweets.head()


# %%
# TODO make ConversationExplorer print quote_counts
# quoted_counts = count_quotes(tweets)
# tweets = tweets.merge(
#     quoted_counts,
#     left_on='tweet_id',
#     right_on='quoted_tweet_id',
#     how='left',
#     suffixes=('', '_drop')
# )
# # Drop the duplicate quoted_tweet_id column from the merge
# tweets = tweets.drop(columns=['quoted_tweet_id_drop'], errors='ignore')
# # Fill NaN values with 0 for tweets that were never quoted
# tweets['quoted_count'] = tweets['quoted_count'].fillna(0).astype(int)



# %%
import time

start_time = time.time()
real_explorer = ConversationExplorer(tweets)
explorer_init_time = time.time() - start_time
print(f"ConversationExplorer initialization took {explorer_init_time:.2f} seconds")

# %%

target_real_id = 1322462839622291463
# Fallback to first tweet
start_time = time.time()
tree_output = real_explorer.print_tree(target_real_id)
tree_time = time.time() - start_time
print(f"print_tree took {tree_time:.2f} seconds")

print(tree_output)
# %%

# for later

prompt = "Can you identify strands of coherent discourse evolving over time in this history of tweets clustered for around a common theme. Add quotes for each of the step of your analysis"

# %%
# Print all tweets for cluster 418
target_cluster = 418
print(f"Finding items for cluster {target_cluster}...")

# Filter keys for this cluster
cluster_keys = [int(k) for k, v in index_to_cluster.items() if int(v) == target_cluster]
print(f"Found {len(cluster_keys)} items in cluster {target_cluster}")
# %%
output = real_explorer.print_tree(cluster_keys[816])
# %%

if cluster_keys:
    target_tweet_ids = cluster_keys
    print(f"Identified {len(target_tweet_ids)} tweet IDs for processing.")
        
    output = real_explorer.print_tree(target_tweet_ids)

    # Write to file
    output_file = f"cluster_{target_cluster}_tweets.txt"
    with open(output_file, "w") as f:
        f.write(output)

    print(f"Output written to {output_file}")
else:
    print("No tweets found for this cluster.")

# %%
# make tweets into a list of tweets as a dict where each key is a column name
tweets_list = tweets.to_dict(orient='records')
# %%
from conversation_explorer import build_conversation_trees, build_incomplete_conversation_trees
conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is not None]
trees =  build_conversation_trees(conversation_tweet_list)
# %%
non_conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is None]

# %%
incomplete_trees =  build_incomplete_conversation_trees(non_conversation_tweet_list)