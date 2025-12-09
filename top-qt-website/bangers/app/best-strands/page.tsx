import { Suspense } from 'react';
import { promises as fs } from 'fs';
import path from 'path';
import { fetchTweetDetails } from '@/lib/api';
import { Strand, StrandWithTweet } from '@/lib/types';
import { BestStrandsClient } from './BestStrandsClient';

// Parse JSON while preserving large integer tweet IDs as strings
function parseStrandsJson(jsonText: string): Strand[] {
  // Replace numeric tweet_id values with string versions to preserve precision
  // This regex matches "tweet_id": followed by a number (without quotes)
  const fixedJson = jsonText
    .replace(/"seed_tweet_id":\s*(\d+)/g, '"seed_tweet_id": "$1"')
    .replace(/"tweet_id":\s*(\d+)/g, '"tweet_id": "$1"');
  
  return JSON.parse(fixedJson);
}

async function loadStrandsWithTweets(): Promise<StrandWithTweet[]> {
  // Read the JSON file as text to preserve large integer precision
  const jsonPath = path.join(process.cwd(), 'app/data/top_quoted_strands.json');
  const jsonText = await fs.readFile(jsonPath, 'utf-8');
  const strands = parseStrandsJson(jsonText);
  
  // Extract all seed tweet IDs (already strings now)
  const seedTweetIds = strands.map(s => s.seed_tweet_id);
  
  // Fetch all seed tweets in one batch
  const seedTweets = await fetchTweetDetails(seedTweetIds);
  const tweetMap = new Map(seedTweets.map(t => [t.tweet_id, t]));
  
  // Combine strands with their seed tweets
  const strandsWithTweets: StrandWithTweet[] = strands.map(strand => ({
    ...strand,
    seedTweet: tweetMap.get(strand.seed_tweet_id),
  }));
  
  // Sort by rating (descending)
  strandsWithTweets.sort((a, b) => b.rating.rating - a.rating.rating);
  
  return strandsWithTweets;
}

export default async function BestStrandsPage() {
  const strands = await loadStrandsWithTweets();
  
  if (strands.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No strands found.</p>
      </div>
    );
  }
  
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strands...</div>}>
      <BestStrandsClient strands={strands} />
    </Suspense>
  );
}

