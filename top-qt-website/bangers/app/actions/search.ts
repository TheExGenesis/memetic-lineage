'use server';

import { fetchTweetDetails, getQuotes } from '@/lib/api';
import { supabaseCa } from '@/lib/supabase';
import { Tweet } from '@/lib/types';

export interface StrandSeed {
  tweetId: string;
  sourceType: 'root' | 'quote_of_root' | 'semantic_match' | 'quote_of_semantic_match';
}

export interface FindStrandSeedsResult {
  seeds: StrandSeed[];
  rootTweet: Tweet | null;
  error?: string;
}

/**
 * Finds related "strand" tweets for a given root tweet ID:
 * 1. The root tweet itself
 * 2. All quote tweets of the root
 * 3. Top semantic matches (sorted by likes)
 * 4. All quote tweets of the semantic matches
 */
export async function findStrandSeeds(
  rootTweetId: string,
  topSemanticCount: number = 20
): Promise<FindStrandSeedsResult> {
  try {
    // 1. Fetch root tweet details
    const rootTweets = await fetchTweetDetails([rootTweetId]);
    if (rootTweets.length === 0) {
      return { seeds: [], rootTweet: null, error: 'Root tweet not found' };
    }
    const rootTweet = rootTweets[0];

    const seeds: StrandSeed[] = [
      { tweetId: rootTweetId, sourceType: 'root' }
    ];

    // 2. Get all quote tweets of the root
    const rootQuotes = await getQuotes(rootTweetId);
    for (const qt of rootQuotes) {
      seeds.push({ tweetId: qt.tweet_id, sourceType: 'quote_of_root' });
    }

    // 3. Run semantic search on root tweet text
    const semanticResults = await searchEmbeddings(rootTweet.full_text, rootTweetId);
    
    // Sort by favorite_count (likes) and take top N
    const topSemanticMatches = semanticResults
      .sort((a, b) => (b.tweet.favorite_count ?? 0) - (a.tweet.favorite_count ?? 0))
      .slice(0, topSemanticCount);

    for (const match of topSemanticMatches) {
      seeds.push({ tweetId: match.tweet.tweet_id, sourceType: 'semantic_match' });
    }

    // 4. Get quotes of each semantic match (parallel)
    const matchQuotesResults = await Promise.all(
      topSemanticMatches.map(match => getQuotes(match.tweet.tweet_id))
    );
    
    for (const matchQuotes of matchQuotesResults) {
      for (const qt of matchQuotes) {
        seeds.push({ tweetId: qt.tweet_id, sourceType: 'quote_of_semantic_match' });
      }
    }

    // Remove duplicates while preserving order
    const seen = new Set<string>();
    const uniqueSeeds = seeds.filter(seed => {
      if (seen.has(seed.tweetId)) return false;
      seen.add(seed.tweetId);
      return true;
    });

    return { seeds: uniqueSeeds, rootTweet };
  } catch (error) {
    console.error('findStrandSeeds error:', error);
    return { seeds: [], rootTweet: null, error: String(error) };
  }
}

interface RawSearchResult {
  key: string;
  distance: number;
  metadata: {
    text: string;
    username?: string;
    tweet_id?: string;
    created_at?: string;
    favorite_count?: number;
    retweet_count?: number;
    avatar_media_url?: string;
  };
}

export interface SemanticSearchResult {
  key: string;
  distance: number;
  tweet: Tweet;
}

export async function searchEmbeddings(searchTerm: string, baseTweetId?: string): Promise<SemanticSearchResult[]> {
  try {
    const response = await fetch('http://embed.tweetstack.app/embeddings/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        searchTerm,
        k: 100,
        threshold: 0.5
      }),
      next: { revalidate: 0 }
    });

    if (!response.ok) {
      console.error('Search API error:', await response.text());
      return [];
    }

    const data = await response.json();
    if (!data.success || !Array.isArray(data.results)) {
      return [];
    }

    const rawResults: RawSearchResult[] = data.results;
    let tweetIds = rawResults
      .map((result) => result.metadata?.tweet_id ?? result.key) // Fallback to key as the tweet_id
      .filter((id): id is string => Boolean(id));
    
    const retweetIds = new Set<string>();
    if (baseTweetId) {
      tweetIds = tweetIds.filter((id) => id !== baseTweetId);

      const { data: retweetRows, error: retweetError } = await supabaseCa
        .from('retweets')
        .select('tweet_id')
        .eq('retweeted_tweet_id', baseTweetId);

      if (retweetError) {
        console.error('Error fetching retweets for semantic search:', retweetError);
      } else {
        retweetRows?.forEach((row) => {
          if (row?.tweet_id) {
            retweetIds.add(row.tweet_id);
          }
        });
        tweetIds = tweetIds.filter((id) => !retweetIds.has(id));
      }
    }

    const enrichedTweets = tweetIds.length > 0 ? await fetchTweetDetails(tweetIds) : [];
    const tweetMap = new Map(enrichedTweets.map((t) => [t.tweet_id, t]));

    console.log('enrichedTweets', enrichedTweets);

    return rawResults
      .map((result) => {
        const tweetId = result.metadata?.tweet_id ?? result.key;
        const enriched = tweetMap.get(tweetId);
        if (!enriched) return null;
        if (retweetIds.has(tweetId)) return null;
        if (baseTweetId) {
          if (tweetId === baseTweetId) return null;
          if (enriched.quoted_tweet_id === baseTweetId) return null;
        }
        if (enriched.full_text.startsWith('RT @')) return null;

        return {
          key: result.key,
          distance: result.distance,
          tweet: enriched
        };
      })
      .filter((item): item is SemanticSearchResult => Boolean(item));
  } catch (error) {
    console.error('Search action error:', error);
    return [];
  }
}


