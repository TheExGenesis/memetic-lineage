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
