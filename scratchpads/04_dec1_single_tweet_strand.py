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
from tqdm import tqdm
import pickle
# Load environment variables
load_dotenv()
# %%
#ENRICHED_TWEETS_PATH = '/Users/frsc/Documents/Projects/data/2025-09-03_enriched_tweets.parquet' # for francisco
ENRICHED_TWEETS_PATH = '~/data/enriched_tweets.parquet' # for alexandre

tweets = pd.read_parquet(ENRICHED_TWEETS_PATH, dtype_backend='pyarrow')
tweets = tweets.set_index('tweet_id', drop=False)
# %% General plan

# make_fishbones(seeds):
# - fishbones = []
# - For seed in seeds:
#     - quotes = get_all_quotes(seed)
#     - threads = make_thread(quotes)
#         - # maybe modify the function, so that non-roots also give their whole thread
#     - fishbones.append(thread)
# - return fishbones.sort_thread(by=root_date)

# get_strand(tweet_id):
# - other_seeds = filtered_semantic_search(tweet_id)
# - fishbones = make_fishbones(other_seeds + tweet_id)
# - display(fishbones)

# %%

tweet_id = 1796556282339443189

# %%

# make tweets into a list of tweets as a dict where each key is a column name
#tweets_list = tweets.to_dict(orient='records')


# %%



# %%
# Convert DataFrame to list of dicts - use pandas built-in method (much faster)
# This is orders of magnitude faster than nested loops (typically 100-1000x faster)
print("Converting tweets DataFrame to list of dictionaries...")
tweets_list = tweets.to_dict(orient='records')
print(f"Converted {len(tweets_list)} tweets successfully.")


# %%

del(tweets)
# Alternative if to_dict doesn't work (still much faster than nested loops):
# tweets_list = [dict(zip(tweets.columns, row)) for row in tqdm(tweets.itertuples(index=False), 
#                                                                 desc="Converting tweets to list", 
#                                                                 total=len(tweets))]

# %% check if the file exists, else save tweet_dict and tweets_list to a pickle file 

TWEETS_LIST_CACHE = 'tweets_list_cache.pkl'

if not os.path.exists(TWEETS_LIST_CACHE):
    with open(TWEETS_LIST_CACHE, 'wb') as f:
        pickle.dump(tweets_list, f)
elif os.path.exists(TWEETS_LIST_CACHE):
    print("Loading cached tweets_list...")
    with open(TWEETS_LIST_CACHE, 'rb') as f:
        tweets_list = pickle.load(f)


# %%

tweet_dict = {tweet['tweet_id']: tweet for tweet in tweets_list}

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
import pickle
import os

# Define paths for cached data
TWEET_DICT_CACHE = 'tweet_dict_cache.pkl'
REPLY_TREES_CACHE = 'complete_reply_trees_cache.pkl'

# Check if cached files exist and load them
if os.path.exists(TWEET_DICT_CACHE) and os.path.exists(REPLY_TREES_CACHE):
    print("Loading cached tweet_dict and complete_reply_trees...")
    with open(TWEET_DICT_CACHE, 'rb') as f:
        tweet_dict = pickle.load(f)
    with open(REPLY_TREES_CACHE, 'rb') as f:
        complete_reply_trees = pickle.load(f)
    print("Cached data loaded successfully.")
else:
    print("Cache not found. Saving tweet_dict and complete_reply_trees...")
    # Save the computed data for future use
    with open(TWEET_DICT_CACHE, 'wb') as f:
        pickle.dump(tweet_dict, f)
    with open(REPLY_TREES_CACHE, 'wb') as f:
        pickle.dump(complete_reply_trees, f)
    print("Data cached successfully.")

# %%