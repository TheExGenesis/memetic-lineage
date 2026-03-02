# %%
from typing import Optional


def count_quotes(tweets_df, valid_account_ids: Optional[set[str]] = None):
    """
    Count how many times each tweet is quoted by others (excluding self-quotes).
    
    Args:
        tweets_df: DataFrame with columns 'quoted_tweet_id', 'tweet_id', 'account_id'
        valid_account_ids: Optional set of account_ids to filter quoting users by
    
    Returns:
        DataFrame with columns 'quoted_tweet_id' and 'quoted_count', sorted by count descending
    """
    df = tweets_df
    
    # Filter to only quotes from valid accounts if provided
    if valid_account_ids is not None:
        df = df[df['account_id'].astype(str).isin(valid_account_ids)]
    
    # Filter out self-quotes: only count quotes where the quoting user differs from the quoted tweet's author
    # First, get the account_id for each quoted tweet
    quoted_tweet_authors = df[['tweet_id', 'account_id']].rename(
        columns={'tweet_id': 'quoted_tweet_id', 'account_id': 'quoted_author_id'}
    )
    
    # Merge to get both the quoting user and the quoted tweet's author
    tweets_with_authors = df.merge(
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
