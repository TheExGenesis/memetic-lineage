'use server';

import { getTweetsByYear, hasMoreTweets } from '@/lib/localData';
import { Tweet } from '@/lib/types';

const TWEETS_PER_PAGE = 30;

/**
 * Fetch more tweets for a specific year with pagination.
 * Data is loaded from local JSON file.
 */
export async function fetchMoreTweetsByYear(
  year: string,
  offset: number
): Promise<Tweet[]> {
  try {
    const tweets = await getTweetsByYear(year, offset, TWEETS_PER_PAGE);
    return tweets;
  } catch (error) {
    console.error(`Error fetching tweets for year ${year}:`, error);
    return [];
  }
}

/**
 * Check if more tweets are available for a year.
 */
export async function checkHasMoreTweets(
  year: string,
  currentOffset: number
): Promise<boolean> {
  try {
    return await hasMoreTweets(year, currentOffset + TWEETS_PER_PAGE);
  } catch (error) {
    console.error(`Error checking more tweets for year ${year}:`, error);
    return false;
  }
}
