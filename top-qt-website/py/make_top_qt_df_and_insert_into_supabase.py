# %%
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client

# Determine the script directory or current working directory
try:
    SCRIPT_DIR = Path(__file__).parent
except NameError:
    # Fallback for interactive mode (e.g., Jupyter/REPL)
    SCRIPT_DIR = Path(os.getcwd())

# Try to find .env in parent directories
ENV_PATH = SCRIPT_DIR.parent / '.env'
if not ENV_PATH.exists():
    # Fallback: look in current directory
    ENV_PATH = SCRIPT_DIR / '.env'

print(f"Looking for .env at: {ENV_PATH}")
load_dotenv(dotenv_path=ENV_PATH)

# Adjust this path to match your local data location
# Assuming data is in a folder 'data' at the project root relative to this script
# ../../../data/ca_dump_nov_15.parquet relative to py/ folder
DATA_PATH = SCRIPT_DIR.parent.parent.parent / "data/ca_dump_nov_15.parquet"

# table in the top qt app supabase db
"""create table public.community_archive_tweets (
  tweet_id bigint primary key,
  created_at timestamptz not null,
  full_text text,
  username text,
  favorite_count int default 0,
  retweet_count int default 0,
  quote_count int default 0,
  year int,
  quoted_tweet_id bigint,
  avatar_media_url text,
  conversation_id bigint,
  media_urls text[]
);

-- Index for fast querying of top QTs
create index tweets_quote_count_idx on public.community_archive_tweets (quote_count desc);
create index tweets_year_idx on public.community_archive_tweets (year);

    """

def get_uploaded_account_ids():
  """Fetch account_ids from archive_upload and optin tables in Community Archive DB."""
  print("Fetching uploaded account IDs from Community Archive Supabase...")
  
  ca_url = os.getenv("CA_SUPABASE_URL")
  ca_key = os.getenv("CA_SUPABASE_ANON_KEY")
  
  if not ca_url or not ca_key:
    print("Error: CA_SUPABASE_URL and CA_SUPABASE_ANON_KEY must be set in .env")
    return set()
  
  ca_supabase = create_client(ca_url, ca_key)
  
  account_ids = set()
  
  # Get account_ids from archive_upload table
  try:
    response = ca_supabase.table('archive_upload').select('account_id').execute()
    archive_account_ids = set(row['account_id'] for row in response.data)
    account_ids.update(archive_account_ids)
    print(f"Found {len(archive_account_ids)} accounts with uploads")
  except Exception as e:
    print(f"Error fetching account IDs from archive_upload: {e}")
  
  # Get twitter_user_id from optin table (where twitter_user_id is not null)
  try:
    response = ca_supabase.table('optin').select('twitter_user_id').execute()
    optin_account_ids = set(
      row['twitter_user_id'] 
      for row in response.data 
      if row['twitter_user_id'] is not None
    )
    account_ids.update(optin_account_ids)
    print(f"Found {len(optin_account_ids)} accounts from optin table")
  except Exception as e:
    print(f"Error fetching account IDs from optin: {e}")
  
  print(f"Total unique account IDs: {len(account_ids)}")
  return account_ids


def count_quotes(tweets_df, uploaded_account_ids):
  """
  Count how many times each tweet is quoted by others (excluding self-quotes).
  Only count tweets from accounts that have uploaded.
  """
  print("Calculating quote counts...")
  
  # Filter to only tweets from uploaded accounts
  tweets_from_uploaded = tweets_df[tweets_df['account_id'].isin(uploaded_account_ids)]
  print(f"Filtered to {len(tweets_from_uploaded)} tweets from uploaded accounts")
  
  # Get the account_id for each quoted tweet
  quoted_tweet_authors = tweets_from_uploaded[['tweet_id', 'account_id']].rename(
    columns={'tweet_id': 'quoted_tweet_id', 'account_id': 'quoted_author_id'}
  )
  
  # Merge to get both the quoting user and the quoted tweet's author
  # We only care about tweets that actually quote something
  quotes = tweets_from_uploaded[tweets_from_uploaded['quoted_tweet_id'].notna()]
  
  tweets_with_authors = quotes.merge(
    quoted_tweet_authors, 
    on='quoted_tweet_id', 
    how='left'
  )
  
  # Filter to only quotes where account_id != quoted_author_id (exclude self-quotes)
  # We keep rows where quoted_author_id is NaN (external tweets) or different from account_id
  non_self_quotes = tweets_with_authors[
    (tweets_with_authors['account_id'] != tweets_with_authors['quoted_author_id']) | 
    (tweets_with_authors['quoted_author_id'].isna())
  ]
  
  # Count number of times tweets are quoted
  quoted_counts = non_self_quotes.groupby('quoted_tweet_id').size().reset_index(
    name='quoted_count'
  ).sort_values(by='quoted_count', ascending=False)
  
  return quoted_counts

def load_tweets_data():
  """Load tweets from parquet file."""
  print(f"Loading data from {DATA_PATH}...")
  try:
    tweets = pd.read_parquet(DATA_PATH, dtype_backend='pyarrow')
    print(f"Loaded {len(tweets)} tweets")
    return tweets
  except FileNotFoundError:
    print(f"Error: File not found at {DATA_PATH}")
    print("Please update the DATA_PATH variable in the script.")
    return None

def merge_quote_counts(tweets_df, quoted_counts, uploaded_account_ids):
  """Merge quote counts back to original tweets from uploaded accounts."""
  print("Merging counts...")
  
  # Filter to only tweets from uploaded accounts
  tweets_from_uploaded = tweets_df[tweets_df['account_id'].isin(uploaded_account_ids)]
  
  # Rename column to avoid collision with 'quoted_tweet_id' in tweets_df
  # 'quoted_tweet_id' in quoted_counts is the ID that WAS quoted (which matches tweet_id)
  quoted_counts_renamed = quoted_counts.rename(columns={'quoted_tweet_id': 'target_tweet_id'})
  
  tweets_with_counts = tweets_from_uploaded.merge(
    quoted_counts_renamed,
    left_on='tweet_id',
    right_on='target_tweet_id',
    how='inner'  # Inner join: only keep tweets that have been quoted at least once
  )
  
  # Drop the temporary join key
  tweets_with_counts = tweets_with_counts.drop(columns=['target_tweet_id'])
  
  print(f"After merge: {len(tweets_with_counts)} tweets with quotes from uploaded accounts")
  return tweets_with_counts

def prepare_for_upload(tweets_with_counts):
  """Prepare dataframe for database upload."""
  print("Preparing data for upload...")
  
  # Convert columns to native Python types for JSON serialization
  tweets_with_counts['created_at'] = pd.to_datetime(tweets_with_counts['created_at'])
  tweets_with_counts['year'] = tweets_with_counts['created_at'].dt.year
  
  # Fill NaNs
  tweets_with_counts['favorite_count'] = tweets_with_counts['favorite_count'].fillna(0)
  tweets_with_counts['retweet_count'] = tweets_with_counts['retweet_count'].fillna(0)
  
  # Select and rename columns to match Supabase schema
  # Note: 'quoted_count' is renamed to 'quote_count' to match the DB schema
  df_to_upload = tweets_with_counts[[
    'tweet_id', 
    'created_at', 
    'full_text', 
    'username', 
    'favorite_count', 
    'retweet_count', 
    'quoted_count',
    'year',
    'quoted_tweet_id', 
    'avatar_media_url',
    'conversation_id'
  ]].copy()
  
  # Rename quoted_count to quote_count to match DB schema
  df_to_upload = df_to_upload.rename(columns={'quoted_count': 'quote_count'})
  
  # Sort by quote count to ensure top tweets are processed first/logged
  df_to_upload = df_to_upload.sort_values('quote_count', ascending=False)
  
  # Convert datetime to string for JSON
  df_to_upload['created_at'] = df_to_upload['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S%z')
  
  # Replace NaN with None (null in JSON/DB)
  df_to_upload = df_to_upload.replace({np.nan: None})
  
  # Deduplicate by tweet_id to prevent batch upload errors
  initial_count = len(df_to_upload)
  df_to_upload = df_to_upload.drop_duplicates(subset=['tweet_id'])
  if len(df_to_upload) < initial_count:
    print(f"Dropped {initial_count - len(df_to_upload)} duplicate tweet records")

  return df_to_upload

def validate_data(df_to_upload):
  """Validate the prepared data before upload."""
  print("\n=== Data Validation ===")
  
  # Check for required columns
  required_cols = ['tweet_id', 'created_at', 'full_text', 'username', 'quote_count']
  missing_cols = [col for col in required_cols if col not in df_to_upload.columns]
  if missing_cols:
    print(f"❌ Missing required columns: {missing_cols}")
    return False
  print(f"✓ All required columns present")
  
  # Check for null tweet_ids
  null_ids = df_to_upload['tweet_id'].isna().sum()
  if null_ids > 0:
    print(f"❌ Found {null_ids} null tweet_ids")
    return False
  print(f"✓ No null tweet_ids")
  
  # Check quote counts are positive
  if (df_to_upload['quote_count'] <= 0).any():
    print(f"❌ Found non-positive quote counts")
    return False
  print(f"✓ All quote counts are positive")
  
  # Show summary statistics
  print(f"\n=== Summary Statistics ===")
  print(f"Total records: {len(df_to_upload)}")
  print(f"Date range: {df_to_upload['created_at'].min()} to {df_to_upload['created_at'].max()}")
  print(f"Quote count range: {df_to_upload['quote_count'].min()} to {df_to_upload['quote_count'].max()}")
  print(f"Unique users: {df_to_upload['username'].nunique()}")
  print(f"Years covered: {sorted(df_to_upload['year'].unique())}")
  
  # Show top 10 most quoted tweets
  print(f"\n=== Top 10 Most Quoted Tweets ===")
  top_10 = df_to_upload.head(10)
  for idx, row in top_10.iterrows():
    print(f"\n{row['quote_count']} quotes - @{row['username']} ({row['created_at']})")
    text_preview = row['full_text'][:100] + "..." if len(row['full_text']) > 100 else row['full_text']
    print(f"  {text_preview}")
  
  return True

def upload_to_supabase(df_to_upload, supabase):
  """Upload prepared dataframe to Supabase."""
  records = df_to_upload.to_dict(orient='records')
  
  total_records = len(records)
  print(f"\n=== Uploading to Supabase ===")
  print(f"Total records to upload: {total_records}")
  
  # 4. Insert in batches
  batch_size = 1000
  print(f"Uploading in batches of {batch_size}...")
  
  for i in range(0, total_records, batch_size):
    batch = records[i:i + batch_size]
    try:
      # upsert=True allows overwriting if we run this multiple times
      supabase.table('community_archive_tweets').upsert(batch).execute()
      print(f"Uploaded {i + len(batch)}/{total_records}")
    except Exception as e:
      print(f"Error uploading batch starting at index {i}: {e}")
      # Optional: break or continue depending on desired strictness
      
  print("Done!")

def process_and_upload():
  load_dotenv()
  
  url = os.getenv("SUPABASE_URL")
  key = os.getenv("SUPABASE_KEY")
  
  if not url or not key:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return

  supabase = create_client(url, key)

  # Step 0: Get uploaded account IDs from Community Archive DB
  uploaded_account_ids = get_uploaded_account_ids()
  if not uploaded_account_ids:
    print("No uploaded accounts found. Aborting.")
    return

  # Step 1: Load data
  tweets = load_tweets_data()
  if tweets is None:
    return

  # Step 2: Calculate quote counts (only for uploaded accounts)
  quoted_counts = count_quotes(tweets, uploaded_account_ids)
  
  # Step 3: Merge counts (only for uploaded accounts)
  tweets_with_counts = merge_quote_counts(tweets, quoted_counts, uploaded_account_ids)
  
  # Step 4: Prepare for upload
  df_to_upload = prepare_for_upload(tweets_with_counts)
  
  # Step 5: Validate data
  if not validate_data(df_to_upload):
    print("\n❌ Validation failed. Aborting upload.")
    return
  
  # Step 6: Confirm before upload
  print("\n" + "="*50)
  response = input("Proceed with upload? (yes/no): ")
  if response.lower() != 'yes':
    print("Upload cancelled.")
    return
  
  # Step 7: Upload
  upload_to_supabase(df_to_upload, supabase)

# %%
if __name__ == "__main__":
  process_and_upload()
# %%
# For interactive testing
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)
uploaded_account_ids = get_uploaded_account_ids()
# %%
tweets = load_tweets_data()

# %%
quoted_counts = count_quotes(tweets, uploaded_account_ids)
  
# Step 3: Merge counts
tweets_with_counts = merge_quote_counts(tweets, quoted_counts, uploaded_account_ids)

# Step 4: Prepare for upload
df_to_upload = prepare_for_upload(tweets_with_counts)
# %%
  # Step 5: Validate data
if not validate_data(df_to_upload):
    print("\n❌ Validation failed. Aborting upload.")
  
  # Step 6: Confirm before upload
print("\n" + "="*50)
response = input("Proceed with upload? (yes/no): ")
if response.lower() != 'yes':
    print("Upload cancelled.")

# Step 7: Upload
upload_to_supabase(df_to_upload, supabase)

# %%
# max col width
pd.set_option('display.max_colwidth', None)
