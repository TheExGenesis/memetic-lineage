
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
# Load environment variables
load_dotenv()
# %%
# ENRICHED_TWEETS_PATH = '/Users/frsc/Documents/Projects/data/2025-09-03_enriched_tweets.parquet' # for francisco
ENRICHED_TWEETS_PATH = '../enriched_tweets.parquet' # for alexandre

tweets = pd.read_parquet(ENRICHED_TWEETS_PATH, dtype_backend='pyarrow')

# Set tweet_id as index for efficient selection


# Filter tweets to only those whose tweet_ids are in index_to_cluster
# clustered_tweet_ids = list(index_to_cluster.keys())
# tweets = tweets.loc[tweets.index.intersection(clustered_tweet_ids)]
# print(f"Filtered to {len(tweets)} tweets that are in clusters")

tweets.head()

# %%
# TODO make ConversationExplorer print quote_counts
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
tweets = tweets.set_index('tweet_id', drop=False)

# %%
# make tweets into a list of tweets as a dict where each key is a column name
tweets_list = tweets.to_dict(orient='records')
# %%

conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is not None]
# %%
trees =  build_conversation_trees(conversation_tweet_list)
# %%
non_conversation_tweet_list = [tweet for tweet in tweets_list if tweet['conversation_id'] is None]

# %%
incomplete_trees =  build_incomplete_conversation_trees(non_conversation_tweet_list, [])

# %% merge complete conversation trees, incomplete conversation trees, and quote trees
complete_reply_trees = {**trees, **incomplete_trees}

# %%

# quote_trees = build_quote_trees(tweets_list) # not used for now but it runs without errors


# %%
tweet_dict = {tweet['tweet_id']: tweet for tweet in tweets_list}

# %%

# get all the values in index_to_cluster with value 

cluster_id = 528
cluster_tweet_ids = [k for k, v in index_to_cluster.items() if v == cluster_id]

# %%


# %%

import time
start_time = time.time()
printed_threads = print_conversation_threads(cluster_tweet_ids, complete_reply_trees, tweet_dict, depth=5)
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
# save printed_threads to a file
with open(f'printed_threads_{cluster_id}.txt', 'w') as f:
    f.write(printed_threads)

# %%

# One root and a few leaves. Should print one thread
print(print_conversation_threads([1796457722940162500, 1796556282339443189, 1796580473625518379], complete_reply_trees, tweet_dict, depth=10))


# %%

# A few leaves  from the same thread with some partial overlap in path


# One root and a few leaves. Should print two path to root
print(print_conversation_threads([1796556282339443189, 1796580473625518379, 1796572316425662603], complete_reply_trees, tweet_dict, depth=5))


# %%
