# %%
from lib.strand_rating_prompt import STRAND_RATER_PROMPT

# we want to get sets of tweets (strands) for each of the top -burstiness top QT tweets
# and then send them to an LLM with the STRAND_RATER_PROMPT

TOP_QT_TWEETS_PATH = '/Users/frsc/Documents/Projects/memetic-lineage/scratchpads/data/top_quoted_tweets_all_time.txt'