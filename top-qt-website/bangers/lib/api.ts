import { supabaseCa } from './supabase';
import { Tweet } from './types';

// Simple in-memory caches to avoid redundant fetches
const tweetCache = new Map<string, Tweet>();
const threadCache = new Map<string, Tweet[]>();
const quotesCache = new Map<string, Tweet[]>();
const conversationIdCache = new Map<string, string | null>();

// Cache TTL in milliseconds (5 minutes)
const CACHE_TTL = 5 * 60 * 1000;
const cacheTimestamps = new Map<string, number>();

function isCacheValid(key: string): boolean {
  const timestamp = cacheTimestamps.get(key);
  if (!timestamp) return false;
  return Date.now() - timestamp < CACHE_TTL;
}

function setCacheTimestamp(key: string) {
  cacheTimestamps.set(key, Date.now());
}

// Generic batch fetcher - reduces duplicate batching logic
async function batchFetch<T, R>(
  ids: T[],
  fetchFn: (batch: T[]) => Promise<R[]>,
  batchSize: number = 200
): Promise<R[]> {
  if (ids.length === 0) return [];
  
  const results: R[] = [];
  for (let i = 0; i < ids.length; i += batchSize) {
    const batch = ids.slice(i, i + batchSize);
    const batchResults = await fetchFn(batch);
    results.push(...batchResults);
  }
  return results;
}

// Helper to fetch user details (username, avatar) for a list of account IDs
async function fetchUserDetails(accountIds: string[]) {
  if (accountIds.length === 0) return { usernameMap: new Map(), avatarMap: new Map() };

  const uniqueAccountIds = [...new Set(accountIds.filter(Boolean))];
  
  // Batch fetch if needed, but for user details usually okay to fetch 100s
  // We'll assume batching is handled by caller or simple enough here
  
  const { data: accountsData } = await supabaseCa
    .from('all_account')
    .select('account_id, username')
    .in('account_id', uniqueAccountIds);

  const { data: profilesData } = await supabaseCa
    .from('all_profile')
    .select('account_id, avatar_media_url')
    .in('account_id', uniqueAccountIds);

  const usernameMap = new Map(accountsData?.map((a: any) => [a.account_id, a.username]));
  const avatarMap = new Map(profilesData?.map((p: any) => [p.account_id, p.avatar_media_url]));

  return { usernameMap, avatarMap };
}

export async function fetchTweetDetails(tweetIds: string[]): Promise<Tweet[]> {
  if (tweetIds.length === 0) return [];

  // Check cache for already-fetched tweets
  const cachedTweets: Tweet[] = [];
  const missingIds: string[] = [];

  for (const id of tweetIds) {
    const cacheKey = `tweet:${id}`;
    if (tweetCache.has(id) && isCacheValid(cacheKey)) {
      cachedTweets.push(tweetCache.get(id)!);
    } else {
      missingIds.push(id);
    }
  }

  // If all tweets are cached, return them in order
  if (missingIds.length === 0) {
    return tweetIds.map(id => tweetCache.get(id)!);
  }

  // Fetch only missing tweets in batches
  const allTweets = await batchFetch(missingIds, async (batch) => {
    const { data, error } = await supabaseCa
      .from('tweets')
      .select(`
        tweet_id, created_at, full_text, favorite_count, retweet_count,
        reply_to_tweet_id, reply_to_user_id, reply_to_username,
        account_id,
        tweet_media ( media_url, media_type )
      `)
      .in('tweet_id', batch);

    if (error) {
      console.error('Error fetching tweets batch:', error);
      return [];
    }
    return data || [];
  });
  
  if (allTweets.length === 0) return [];

  // Sort by date
  allTweets.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

  // Fetch user details
  const accountIds = allTweets.map((t: any) => t.account_id);
  const { usernameMap, avatarMap } = await fetchUserDetails(accountIds);

  // Fetch quote tweet mappings
  const quoteResults = await batchFetch(tweetIds, async (batch) => {
    const { data } = await supabaseCa
      .from('quote_tweets')
      .select('tweet_id, quoted_tweet_id')
      .in('tweet_id', batch);
    return data || [];
  });
  
  const quoteMap = new Map<string, string>();
  quoteResults.forEach((q: any) => quoteMap.set(q.tweet_id, q.quoted_tweet_id));

  // Fetch details for the quoted tweets
  const quotedTweetIds = Array.from(new Set(Array.from(quoteMap.values()).filter(Boolean)));
  const quotedTweetsMap = new Map<string, any>();

  if (quotedTweetIds.length > 0) {
    const quotedTweets = await batchFetch(quotedTweetIds, async (batch) => {
      const { data } = await supabaseCa
        .from('tweets')
        .select(`
          tweet_id, created_at, full_text, favorite_count, retweet_count,
          account_id,
          tweet_media ( media_url, media_type )
        `)
        .in('tweet_id', batch);
      return data || [];
    });

    // Fetch user details for quoted tweets
    const qAccountIds = quotedTweets.map((t: any) => t.account_id);
    const { usernameMap: qUserMap, avatarMap: qAvatarMap } = await fetchUserDetails(qAccountIds);

    quotedTweets.forEach((qt: any) => {
      quotedTweetsMap.set(qt.tweet_id, {
        tweet_id: qt.tweet_id,
        created_at: qt.created_at,
        full_text: qt.full_text,
        favorite_count: qt.favorite_count,
        retweet_count: qt.retweet_count,
        username: qUserMap.get(qt.account_id) || 'unknown',
        avatar_media_url: qAvatarMap.get(qt.account_id),
        media_urls: qt.tweet_media?.map((m: any) => m.media_url)
      });
    });
  }

  const newTweets = allTweets.map((t: any) => {
    const quotedId = quoteMap.get(t.tweet_id);
    return {
        tweet_id: t.tweet_id,
        created_at: t.created_at,
        full_text: t.full_text,
        favorite_count: t.favorite_count,
        retweet_count: t.retweet_count,
        reply_to_tweet_id: t.reply_to_tweet_id,
        reply_to_user_id: t.reply_to_user_id,
        reply_to_username: t.reply_to_username,
        username: usernameMap.get(t.account_id) || 'unknown',
        avatar_media_url: avatarMap.get(t.account_id),
        media_urls: t.tweet_media?.map((m: any) => m.media_url),
        quoted_tweet_id: quotedId,
        quoted_tweet: quotedId ? quotedTweetsMap.get(quotedId) : undefined
    };
  }) as Tweet[];

  // Cache the newly fetched tweets
  newTweets.forEach(tweet => {
    tweetCache.set(tweet.tweet_id, tweet);
    setCacheTimestamp(`tweet:${tweet.tweet_id}`);
  });

  // Return all tweets in original order (cached + new)
  return tweetIds.map(id => tweetCache.get(id) || newTweets.find(t => t.tweet_id === id)!);
}

export async function getThread(conversationId: string): Promise<Tweet[]> {
  // Check cache first
  const cacheKey = `thread:${conversationId}`;
  if (threadCache.has(conversationId) && isCacheValid(cacheKey)) {
    return threadCache.get(conversationId)!;
  }

  const { data: convData, error: convError } = await supabaseCa
    .from('conversations')
    .select('tweet_id')
    .eq('conversation_id', conversationId);

  if (convError) {
    console.error('Error fetching conversation IDs:', convError);
    return [];
  }

  if (!convData || convData.length === 0) {
      return [];
  }

  const tweetIds = convData.map((c: any) => c.tweet_id);
  const tweets = await fetchTweetDetails(tweetIds);

  // Add conversation_id to all
  const result = tweets.map(t => ({ ...t, conversation_id: conversationId }));

  // Cache result
  threadCache.set(conversationId, result);
  setCacheTimestamp(cacheKey);

  return result;
}

export async function getQuotes(tweetId: string): Promise<Tweet[]> {
  // Check cache first
  const cacheKey = `quotes:${tweetId}`;
  if (quotesCache.has(tweetId) && isCacheValid(cacheKey)) {
    return quotesCache.get(tweetId)!;
  }

  const { data: quotesData, error: quotesError } = await supabaseCa
    .from('quote_tweets')
    .select('tweet_id')
    .eq('quoted_tweet_id', tweetId);

  if (quotesError) {
    console.error('Error fetching quotes:', quotesError);
    return [];
  }

  if (!quotesData || quotesData.length === 0) {
    // Cache empty results too
    quotesCache.set(tweetId, []);
    setCacheTimestamp(cacheKey);
    return [];
  }

  const tweetIds = quotesData.map((q: any) => q.tweet_id);
  const result = await fetchTweetDetails(tweetIds);

  // Cache result
  quotesCache.set(tweetId, result);
  setCacheTimestamp(cacheKey);

  return result;
}

export async function getConversationId(tweetId: string): Promise<string | null> {
  // Check cache first
  const cacheKey = `convId:${tweetId}`;
  if (conversationIdCache.has(tweetId) && isCacheValid(cacheKey)) {
    return conversationIdCache.get(tweetId)!;
  }

  const { data, error } = await supabaseCa
    .from('conversations')
    .select('conversation_id')
    .eq('tweet_id', tweetId)
    .limit(1)
    .order('conversation_id');

  if (error) {
    console.error('Error fetching conversation_id:', error);
    return null;
  }

  const result = (!data || data.length === 0) ? null : (data[0].conversation_id || null);

  // Cache result
  conversationIdCache.set(tweetId, result);
  setCacheTimestamp(cacheKey);

  return result;
}

// Batch fetch conversation IDs for multiple tweets at once
export async function getConversationIds(tweetIds: string[]): Promise<Map<string, string | null>> {
  const result = new Map<string, string | null>();
  const missingIds: string[] = [];

  // Check cache first
  for (const id of tweetIds) {
    const cacheKey = `convId:${id}`;
    if (conversationIdCache.has(id) && isCacheValid(cacheKey)) {
      result.set(id, conversationIdCache.get(id)!);
    } else {
      missingIds.push(id);
    }
  }

  if (missingIds.length === 0) {
    return result;
  }

  // Batch fetch missing IDs
  const data = await batchFetch(missingIds, async (batch) => {
    const { data, error } = await supabaseCa
      .from('conversations')
      .select('tweet_id, conversation_id')
      .in('tweet_id', batch);

    if (error) {
      console.error('Error batch fetching conversation_ids:', error);
      return [];
    }
    return data || [];
  });

  // Build map from results
  const fetchedMap = new Map<string, string>();
  data.forEach((row: any) => {
    fetchedMap.set(row.tweet_id, row.conversation_id);
  });

  // Update cache and result for all missing IDs
  for (const id of missingIds) {
    const convId = fetchedMap.get(id) || null;
    conversationIdCache.set(id, convId);
    setCacheTimestamp(`convId:${id}`);
    result.set(id, convId);
  }

  return result;
}

// Batch fetch threads for multiple conversation IDs at once
export async function getThreadsBatch(conversationIds: string[]): Promise<Map<string, Tweet[]>> {
  const result = new Map<string, Tweet[]>();
  const missingConvIds: string[] = [];

  // Check cache first
  for (const convId of conversationIds) {
    const cacheKey = `thread:${convId}`;
    if (threadCache.has(convId) && isCacheValid(cacheKey)) {
      result.set(convId, threadCache.get(convId)!);
    } else {
      missingConvIds.push(convId);
    }
  }

  if (missingConvIds.length === 0) {
    return result;
  }

  // Batch fetch all tweet IDs for all conversations
  const convTweetData = await batchFetch(missingConvIds, async (batch) => {
    const { data, error } = await supabaseCa
      .from('conversations')
      .select('conversation_id, tweet_id')
      .in('conversation_id', batch);

    if (error) {
      console.error('Error batch fetching conversation tweets:', error);
      return [];
    }
    return data || [];
  });

  // Group tweet IDs by conversation
  const convToTweetIds = new Map<string, string[]>();
  convTweetData.forEach((row: any) => {
    if (!convToTweetIds.has(row.conversation_id)) {
      convToTweetIds.set(row.conversation_id, []);
    }
    convToTweetIds.get(row.conversation_id)!.push(row.tweet_id);
  });

  // Fetch all tweets at once
  const allTweetIds = Array.from(new Set(convTweetData.map((row: any) => row.tweet_id)));
  const allTweets = await fetchTweetDetails(allTweetIds);
  const tweetMap = new Map(allTweets.map(t => [t.tweet_id, t]));

  // Build result map
  for (const convId of missingConvIds) {
    const tweetIds = convToTweetIds.get(convId) || [];
    const tweets = tweetIds
      .map(id => tweetMap.get(id))
      .filter((t): t is Tweet => t !== undefined)
      .map(t => ({ ...t, conversation_id: convId }));

    // Sort by date
    tweets.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

    result.set(convId, tweets);
    threadCache.set(convId, tweets);
    setCacheTimestamp(`thread:${convId}`);
  }

  return result;
}
