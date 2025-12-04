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
from lib.count_quotes import count_quotes

# Load environment variables
load_dotenv()
# %%
ENRICHED_TWEETS_PATH = '/Users/frsc/Documents/Projects/data/2025-09-03_enriched_tweets.parquet' # for francisco
# ENRICHED_TWEETS_PATH = '~/data/enriched_tweets.parquet' # for alexandre

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
# Check if quoted counts cache exists
quoted_counts_cache_path = Path('quoted_counts_cache.parquet')

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
OVERRIDE_CACHE = False
# Check if cached files exist and load them
if os.path.exists(TWEET_DICT_CACHE) and os.path.exists(REPLY_TREES_CACHE) and not OVERRIDE_CACHE:
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
# let's make an index  quoted_tweet_id -> quote tweets
quote_tweets_dict = {}
for tweet in tweet_dict.values():
    if tweet['quoted_tweet_id'] is not None:
        quote_tweets_dict[tweet['quoted_tweet_id']] = quote_tweets_dict.get(tweet['quoted_tweet_id'], []) + [tweet['tweet_id']]
# %%
# okay let's produce a strand.

from lib.semantic_search import search_embeddings
# %%
tweet_id = 1742494880625016921
results = search_embeddings(tweet_dict[tweet_id]['full_text'], k=1000, threshold=0.5, exclude_tweet_id=tweet_id,
    #                         filter={"must_not": [
    # { "key": "text", "match": { "text": "community" } },
    # { "key": "text", "match": { "text": "communities" } },
    # { "key": "text", "match": { "text": "build" } },
    # { "key": "text", "match": { "text": "building" } },
    # { "key": "text", "match": { "text": "builder" } },
    # { "key": "text", "match": { "text": "scale" } },
    
    # ]}
)
# %%
print('\n'.join(list(map(lambda x: f'{x["distance"]} - {x["key"]} - {x["metadata"]["text"]}', results))))
# %%
result_ids = [int(result['key']) for result in results]
print(len(result_ids))
result_dicts = [tweet_dict[result_id] for result_id in result_ids if result_id in tweet_dict]
print(len(result_dicts))
# %%
# print ones that aren't in tweet_dict
print('\n'.join([str(r) for r in results if int(r['key']) not in tweet_dict]))
# %%
def semantic_search_for_strands(tweet_id, exclude_tweet_ids=[], exclude_keywords=[]):
    
    results = search_embeddings(tweet_dict[tweet_id]['full_text'], k=1000, threshold=0.5, exclude_tweet_id=str(tweet_id), filter={"must_not": [{"key": "text", "match": {"text": keyword}} for keyword in exclude_keywords]})
    

    result_ids = [int(result['key']) for result in results]
    result_dicts = [tweet_dict[result_id] for result_id in result_ids if result_id in tweet_dict]
    filtered_result_dicts = [result_dict for result_dict in result_dicts if (int(result_dict['quoted_tweet_id']) != tweet_id if result_dict['quoted_tweet_id'] is not None else True)]
    good_result_dicts = sorted(filtered_result_dicts, key=lambda x: x['quoted_count'], reverse=True)[:20]
    return good_result_dicts
# %%
good_semantic_result_dicts = semantic_search_for_strands(tweet_id)
print(len(good_semantic_result_dicts))
# %%
print('\n===\n'.join([f'{r["tweet_id"]} - {r["quoted_count"]} - {r["full_text"][:100]}...' for r in good_semantic_result_dicts]))
# %%
from lib.conversation_explorer import EnrichedTweet
from typing import Literal
from dataclasses import dataclass

@dataclass
class StrandSeed:
    tweet_id: int
    source_type: Literal['root', 'semantic_search', 'quote_of_root', 'quote_of_semantic_search'] 
    
# %%
# let's skip filtering semantic search results with LLMs for now

# we take search results, we find all the tweets that are quoting them with quote_tweets_dict, and then we use each of those as seeds to print threads
strand_seeds =  [StrandSeed(tweet_id=tweet_id, source_type='root')] + [
    StrandSeed(tweet_id=seed_tweet_id, source_type='quote_of_root') 
    for seed_tweet_id in quote_tweets_dict.get(tweet_id, [])
] + [
    StrandSeed(tweet_id=tweet['tweet_id'], source_type='semantic_search') 
    for tweet in good_semantic_result_dicts
] + [
    StrandSeed(tweet_id=seed_tweet_id, source_type='quote_of_semantic_search') 
    for tweet in good_semantic_result_dicts
    for seed_tweet_id in quote_tweets_dict.get(tweet['tweet_id'], [])
]
print(len(strand_seeds))
# %%
from lib.conversation_explorer import print_conversation_threads

conversation_threads = print_conversation_threads(
    tweet_ids=[1742495745800839479, 1743549769853669625],
    conversation_trees=complete_reply_trees,
    tweets=tweet_dict,
    depth=10
)
print(conversation_threads)
# write to file for convenience
# with open('conversation_threads.txt', 'w') as f:
#     f.write(conversation_threads)
# %%
print(','.join([str(seed.tweet_id) for seed in strand_seeds]))
# /multi-thread-visualizer?tweet_ids=1742494880625016921,1766341602870439953,1743553890916683831,1904114702143406303,1904047011277549651,1742737462516961459,1742500854802907205,1743080673613869124,1743555207852589493,1766279606351605884,1743078860714065945,1742532614215303314,1766613778307613096,1742621652586836197,1942262762656153873,1743008082081333327,1743529282092114427,1942260183125655617,1802971123136835720,1742555103033282639,1742497228407652396,1742791214934683660,1823179794940322030,1716140468751204826,1796691790608613791,1333199165589864449,1742496635899220139,1662169476521918473,1568102136067522560,1106499777880117248,1828043128139309328,1241409748156776448,1742542390722757024,1743036689227067568,1742583689035600274,1742520437303574676,1742505647026172179,1464240020169109504,1742495067695116459,1097450506484678657,17605701792,2332251318,1437660721676967945,1718975693671780673,1788628945434239416,1788626702303731824,1742602108925333640,1716527363549233374,1896954590270259411,1832538740234797111,1832372146514886734,1805306207529230515,1333199309408509953,1743544377534799999,1662170980628742164,1568102636855128064,1106591531073363968,1828187749746385258,1241740706353491968,1241516112023638022,1241410050788384768,1242456603523153920
