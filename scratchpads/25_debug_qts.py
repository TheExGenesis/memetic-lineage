# %%
import pandas as pd
path='/Users/frsc/Documents/Projects/data/ca_jan_2026.parquet'
tweets = pd.read_parquet(path, dtype_backend='pyarrow')
tweets.head()

# %%
from pathlib import Path
# Paths
DATA_DIR = Path(__file__).parent / "data"
TOP_IDS_PATH = DATA_DIR / "top_quoted_tweet_ids.json"
STRANDS_DIR = DATA_DIR / "strands"
RATED_DIR = DATA_DIR / "rated_strands"
DEBUG_DIR = DATA_DIR / "debug_responses"
QUOTED_COUNTS_CACHE_PATH = DATA_DIR / "quoted_counts_cache.parquet"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "strand_summary_embeddings.json"
LABEL_CONFIG_PATH = DATA_DIR / "strand_label_config.json"
ATLAS_PARQUET_PATH = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_EMBEDDINGS_DIR = DATA_DIR / "all_tweet_embeddings"

# Frontend export paths
FRONTEND_PUBLIC_DIR = Path(__file__).parent.parent / "bangers" / "public"
ATLAS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "atlas_data.json"
HISTOGRAM_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_histograms.json"
SEMANTIC_MAP_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_semantic_map.json"
SERIATION_ORDER_PATH = FRONTEND_PUBLIC_DIR / "strand_seriation_order.json"
STRANDS_DATA_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strands_data.json"
BANGERS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "bangers_tweets.json"
VALID_ACCOUNTS_PATH = DATA_DIR / "valid_account_ids_cache.json"
ALL_SUMMARIES_PATH = DATA_DIR / "all_summaries_chronological.txt"

# %%

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
quoted_counts = count_quotes(tweets)
# %%
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
tweets['year'] = pd.to_datetime(tweets['created_at']).dt.year
# %%
for year in sorted(tweets['year'].unique()):
        year_tweets = tweets[tweets['year'] == year]
        year_top_quoted = year_tweets.sort_values(by='quoted_count', ascending=False).head(20) 
        
        print(f"\n\n{'#'*80}\n")
        print(f"### Top 20 quoted tweets for {year} ###")
        print(f"{'#'*80}\n")
        print(year_top_quoted[['tweet_id', 'quoted_count']])
# %%
year=2025
year_tweets = tweets[tweets['year'] == year]
# %%
from lib.strand_caches import load_caches
tweet_dict, conversation_trees = load_caches()
# %%
tweets[tweets.quoted_tweet_id == 1949101947874640253]
# %%

VALID_ACCOUNTS_PATH = Path('/Users/frsc/Documents/Projects/memetic-lineage/scratchpads/data/valid_account_ids_cache.json')
import json
def _load_valid_account_ids() -> set:
    """Load valid account IDs from cache (archive users)."""
    if not VALID_ACCOUNTS_PATH.exists():
        print(f"  [WARN] {VALID_ACCOUNTS_PATH} not found, archive_quote_count will be 0")
        return set()
    with open(VALID_ACCOUNTS_PATH) as f:
        data = json.load(f)
    ids = set(str(aid) for aid in data.get('account_ids', []))
    print(f"  Loaded {len(ids)} valid account IDs")
    return ids
valid_account_ids = set(_load_valid_account_ids())
# %%
from lib.strand_caches import get_filtered_quote_tweets_dict

filtered_qt = get_filtered_quote_tweets_dict()
# %%
tweets[tweets.quoted_tweet_id.notna()]
# %%
tweets[tweets.quoted_tweet_id == 1949101947874640253]
# %%
ks = filtered_qt.iterkeys()
# %%
ks = list(ks)
# %%
ks[0]
# %%
filtered_qt[ks[0]]
# %%
filtered_qt[ks[1]]
# %%

# %%
