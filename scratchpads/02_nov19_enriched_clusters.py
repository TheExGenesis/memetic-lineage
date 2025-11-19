
#%% mapping tweet_id => cluster_ID or cluster_ID => tweet_ids

import json

# Load the mapping from tweet_id to cluster_id
with open('index_to_cluster_mapping.json', 'r') as f:
    index_to_cluster = json.load(f)

# Convert keys and values to integers
index_to_cluster = {int(k): int(v) for k, v in index_to_cluster.items()}

print(f"Loaded mapping for {len(index_to_cluster)} tweet IDs to clusters")

# %%

from scratchpads.conversation_explorer import ConversationExplorer, count_quotes


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

# %%
tweets = pd.read_parquet('enriched_tweets.parquet', dtype_backend='pyarrow')
tweets.head()


# %%

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



# %%

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

# for later

prompt = "Can you identify strands of coherent discourse evolving over time in this history of tweets clustered for around a common theme. Add quotes for each of the step of your analysis"

# %%
# Print all tweets for cluster 418
target_cluster = 418
print(f"Finding items for cluster {target_cluster}...")

# Filter keys for this cluster
cluster_keys = [int(k) for k, v in index_to_cluster.items() if int(v) == target_cluster]
print(f"Found {len(cluster_keys)} items in cluster {target_cluster}")

if cluster_keys:
    # Determine if keys are indices or tweet_ids
    first_key = cluster_keys[0]
    is_tweet_id = (first_key > 1_000_000_000)

    target_tweet_ids = []
    if is_tweet_id:
        print("Keys detected as Tweet IDs.")
        target_tweet_ids = cluster_keys
    else:
        print("Keys detected as DataFrame Indices.")
        # Filter valid indices
        valid_indices = [i for i in cluster_keys if i < len(tweets)]
        target_tweet_ids = tweets.iloc[valid_indices]['tweet_id'].tolist()

    print(f"Identified {len(target_tweet_ids)} tweet IDs for processing.")
    
    # Use the existing explorer
    print("Generating output tree...")
    # Reuse real_explorer if available, else create one
    if 'real_explorer' in locals():
        explorer = real_explorer
    else:
        explorer = ConversationExplorer(tweets)
        
    output = explorer.print_tree(target_tweet_ids)

    # Write to file
    output_file = f"cluster_{target_cluster}_tweets.txt"
    with open(output_file, "w") as f:
        f.write(output)

    print(f"Output written to {output_file}")
else:
    print("No tweets found for this cluster.")

# %%
