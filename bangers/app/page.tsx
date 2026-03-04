import { Suspense } from 'react';
import { HomePageClient } from './HomePageClient';
import { Tweet } from '@/lib/types';
import { getAvailableYears, getTweetsByYear, getTopArchiveQuoteTweets, getSnapshotDate } from '@/lib/localData';

/**
 * Fetch initial tweets for all years from local data.
 * Includes both top-by-total-quotes and top-by-archive-quotes so
 * the client has enough data for both ranking modes.
 */
async function fetchTweetsByPeriod(): Promise<Tweet[]> {
  try {
    const years = await getAvailableYears();
    const allTweets: Tweet[] = [];
    const seenIds = new Set<string>();

    for (const year of years) {
      // Top 30 by total quote count (default byYear ordering)
      const byTotal = await getTweetsByYear(year, 0, 30);
      for (const t of byTotal) {
        if (!seenIds.has(t.tweet_id)) {
          seenIds.add(t.tweet_id);
          allTweets.push(t);
        }
      }

      // Top 30 by archive quote count (for archive view)
      const byArchive = await getTopArchiveQuoteTweets(year, 30);
      for (const t of byArchive) {
        if (!seenIds.has(t.tweet_id)) {
          seenIds.add(t.tweet_id);
          allTweets.push(t);
        }
      }
    }

    return allTweets;
  } catch (error) {
    console.error('Error loading tweets from local data:', error);
    return [];
  }
}

export default async function Home() {
  const tweets = await fetchTweetsByPeriod();
  const snapshotDate = await getSnapshotDate();

  if (tweets.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center max-w-md p-8">
          <h1 className="text-2xl font-bold mb-4">Data Unavailable</h1>
          <p className="text-gray-600 mb-6">
            The tweet data file could not be loaded.
            Run the data generation script to create it:
          </p>
          <pre className="bg-gray-100 p-4 text-left text-sm mb-6 overflow-x-auto">
            cd scratchpads{'\n'}
            uv run python 23_generate_bangers_data.py
          </pre>
          <a
            href="/best-strands"
            className="inline-block px-6 py-3 bg-black text-white font-medium hover:bg-gray-800 transition-colors"
          >
            Explore Strands Instead →
          </a>
        </div>
      </div>
    );
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <HomePageClient tweets={tweets} snapshotDate={snapshotDate} />
    </Suspense>
  );
}
