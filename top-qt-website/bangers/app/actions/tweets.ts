'use server';

import { supabaseTopQt, supabaseCa } from '@/lib/supabase';
import { Tweet } from '@/lib/types';

const TWEETS_PER_PAGE = 30;

export async function fetchMoreTweetsByYear(
  year: string,
  offset: number
): Promise<Tweet[]> {
  const yearNum = parseInt(year, 10);
  if (isNaN(yearNum)) return [];

  const { data, error } = await supabaseTopQt
    .from('community_archive_tweets')
    .select('*')
    .eq('year', yearNum)
    .order('quote_count', { ascending: false })
    .range(offset, offset + TWEETS_PER_PAGE - 1);

  if (error || !data) {
    console.error(`Error fetching tweets for year ${year}:`, error);
    return [];
  }

  // Add column field and convert IDs to strings
  const tweets = data.map((tweet: any) => ({
    ...tweet,
    column: String(tweet.year),
    tweet_id: String(tweet.tweet_id),
    quoted_tweet_id: tweet.quoted_tweet_id ? String(tweet.quoted_tweet_id) : undefined,
    conversation_id: tweet.conversation_id ? String(tweet.conversation_id) : undefined,
  }));

  if (tweets.length === 0) return [];

  // Fetch media for these tweets
  const tweetIds = tweets.map((t: any) => t.tweet_id);
  const { data: mediaData } = await supabaseCa
    .from('tweet_media')
    .select('tweet_id, media_url')
    .in('tweet_id', tweetIds);

  // Create media map
  const mediaMap = new Map<string, string[]>();
  mediaData?.forEach((m: any) => {
    const id = String(m.tweet_id);
    if (!mediaMap.has(id)) mediaMap.set(id, []);
    mediaMap.get(id)!.push(m.media_url);
  });

  // Attach media to tweets
  tweets.forEach((tweet: any) => {
    tweet.media_urls = mediaMap.get(tweet.tweet_id) || [];
  });

  // Fetch quoted tweets if any
  const quotedTweetIds = tweets
    .filter((t: any) => t.quoted_tweet_id)
    .map((t: any) => t.quoted_tweet_id);

  if (quotedTweetIds.length > 0) {
    const { data: quotedTweets } = await supabaseCa
      .from('tweets')
      .select('tweet_id, full_text, created_at, account_id')
      .in('tweet_id', quotedTweetIds);

    if (quotedTweets && quotedTweets.length > 0) {
      // Fetch account info for quoted tweets
      const accountIds = [...new Set(quotedTweets.map((t: any) => t.account_id))];
      const { data: accounts } = await supabaseCa
        .from('all_account')
        .select('account_id, username')
        .in('account_id', accountIds);

      const { data: profiles } = await supabaseCa
        .from('all_profile')
        .select('account_id, avatar_media_url')
        .in('account_id', accountIds);

      const accountMap = new Map(accounts?.map((a: any) => [a.account_id, a.username]) || []);
      const profileMap = new Map(profiles?.map((p: any) => [p.account_id, p.avatar_media_url]) || []);

      // Fetch media for quoted tweets
      const { data: quotedMedia } = await supabaseCa
        .from('tweet_media')
        .select('tweet_id, media_url')
        .in('tweet_id', quotedTweetIds);

      const quotedMediaMap = new Map<string, string[]>();
      quotedMedia?.forEach((m: any) => {
        const id = String(m.tweet_id);
        if (!quotedMediaMap.has(id)) quotedMediaMap.set(id, []);
        quotedMediaMap.get(id)!.push(m.media_url);
      });

      const quotedMap = new Map(
        quotedTweets.map((qt: any) => [
          String(qt.tweet_id),
          {
            tweet_id: String(qt.tweet_id),
            full_text: qt.full_text,
            created_at: qt.created_at,
            username: accountMap.get(qt.account_id) || 'unknown',
            avatar_media_url: profileMap.get(qt.account_id),
            media_urls: quotedMediaMap.get(String(qt.tweet_id)) || [],
          },
        ])
      );

      tweets.forEach((tweet: any) => {
        if (tweet.quoted_tweet_id) {
          tweet.quoted_tweet = quotedMap.get(tweet.quoted_tweet_id);
        }
      });
    }
  }

  return tweets as Tweet[];
}
