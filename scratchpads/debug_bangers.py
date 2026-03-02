"""Debug script to check bangers_tweets.json data and diskcaches."""
import json
from pathlib import Path
from diskcache import Cache

SCRIPT_DIR = Path(__file__).parent
BANGERS_DIR = SCRIPT_DIR.parent / "bangers"
data_path = BANGERS_DIR / "public" / "bangers_tweets.json"

print("=" * 60)
print("PART 1: Checking generated bangers_tweets.json")
print("=" * 60)

print(f"\nLoading {data_path}...")
with open(data_path) as f:
    data = json.load(f)

tweets = data['tweets']
by_year = data['byYear']

# Count tweets with archive_quote_count > 0
has_aqc = sum(1 for t in tweets.values() if t.get('archive_quote_count', 0) > 0)
print(f"\nTweets with archive_quote_count > 0: {has_aqc} / {len(tweets)}")

# Check 2024 top 10
print("\n2024 Top 10:")
top_2024 = by_year.get('2024', [])[:10]
for i, tid in enumerate(top_2024):
    t = tweets.get(tid, {})
    aqc = t.get('archive_quote_count', 0)
    qc = t.get('quote_count', 0)
    fav = t.get('favorite_count', 0)
    user = t.get('username', '?')
    text = (t.get('full_text', '') or '')[:50]
    print(f"  {i+1}. @{user}: aqc={aqc}, qc={qc}, fav={fav}")
    print(f"     {text}...")

# Show distribution of archive_quote_count
print("\nArchive quote count distribution:")
aqc_values = [t.get('archive_quote_count', 0) or 0 for t in tweets.values()]
non_zero = [v for v in aqc_values if v > 0]
if non_zero:
    print(f"  Non-zero count: {len(non_zero)}")
    print(f"  Max: {max(non_zero)}")
    print(f"  Top 10 values: {sorted(non_zero, reverse=True)[:10]}")
else:
    print("  No tweets have archive_quote_count > 0!")

print("\n" + "=" * 60)
print("PART 2: Checking raw diskcaches")
print("=" * 60)

# Check diskcaches exist
TWEET_DICT_PATH = SCRIPT_DIR / "tweet_dict.diskcache"
QUOTE_TWEETS_PATH = SCRIPT_DIR / "quote_tweets.diskcache"
VALID_ACCOUNTS_PATH = SCRIPT_DIR / "data" / "valid_account_ids_cache.json"

print(f"\ntweet_dict.diskcache exists: {TWEET_DICT_PATH.exists()}")
print(f"quote_tweets.diskcache exists: {QUOTE_TWEETS_PATH.exists()}")
print(f"valid_account_ids_cache.json exists: {VALID_ACCOUNTS_PATH.exists()}")

if not TWEET_DICT_PATH.exists() or not QUOTE_TWEETS_PATH.exists():
    print("\nERROR: Diskcaches not found! Cannot continue.")
    exit(1)

# Load valid accounts
print("\nLoading valid account IDs...")
with open(VALID_ACCOUNTS_PATH, 'r') as f:
    valid_data = json.load(f)
valid_account_ids = set(valid_data.get('account_ids', []))
print(f"  {len(valid_account_ids)} valid account IDs")
print(f"  Sample IDs: {list(valid_account_ids)[:5]}")

# Load caches
print("\nLoading tweet_dict.diskcache...")
tweet_dict = Cache(str(TWEET_DICT_PATH))
print(f"  {len(tweet_dict)} tweets")

print("\nLoading quote_tweets.diskcache...")
quote_tweets = Cache(str(QUOTE_TWEETS_PATH))
print(f"  {len(quote_tweets)} quoted tweets")

# Check a few entries from quote_tweets
print("\nSample quote_tweets entries:")
sample_count = 0
for quoted_id in quote_tweets.iterkeys():
    if sample_count >= 3:
        break
    quoting_ids = quote_tweets.get(quoted_id, [])
    print(f"  quoted_id={quoted_id} (type={type(quoted_id).__name__}): {len(quoting_ids)} quotes")
    sample_count += 1

# Check a sample tweet from tweet_dict
print("\nSample tweet_dict entry:")
for tid in tweet_dict.iterkeys():
    tweet = tweet_dict.get(tid)
    print(f"  tweet_id={tid} (type={type(tid).__name__})")
    print(f"  Keys: {list(tweet.keys())[:10]}...")
    print(f"  account_id={tweet.get('account_id')} (type={type(tweet.get('account_id')).__name__})")
    break

# Test archive quote counting for one tweet
print("\n" + "=" * 60)
print("PART 3: Testing archive quote count for a sample")
print("=" * 60)

sample_count = 0
total_archive_quotes_found = 0
for quoted_id in quote_tweets.iterkeys():
    if sample_count >= 100:
        break
    quoting_ids = quote_tweets.get(quoted_id, [])
    archive_count = 0
    for quoting_id in quoting_ids:
        quoting_tweet = tweet_dict.get(quoting_id)
        if quoting_tweet:
            account_id = str(quoting_tweet.get('account_id', ''))
            if account_id in valid_account_ids:
                archive_count += 1
    if archive_count > 0:
        total_archive_quotes_found += archive_count
        print(f"  {quoted_id}: {archive_count} archive quotes (of {len(quoting_ids)} total)")
    sample_count += 1

print(f"\nIn first 100 quoted tweets: found {total_archive_quotes_found} archive quotes")

tweet_dict.close()
quote_tweets.close()

print("\n" + "=" * 60)
print("DIAGNOSIS")
print("=" * 60)
if has_aqc == 0:
    print("Issue: No tweets in bangers_tweets.json have archive_quote_count > 0")
    print("Possible causes:")
    print("  1. Diskcaches empty or missing data")
    print("  2. valid_account_ids not matching account_ids in tweets")
    print("  3. Tweet IDs in all_tweets don't match those in quote_tweets")
else:
    print(f"Found {has_aqc} tweets with archive quotes")
    print("The ranking should be working. Check if the top 2024 tweets have aqc > 0")
