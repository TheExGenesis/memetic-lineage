'use server';

import { fetchTweetDetails } from '@/lib/api';
import { supabaseCa } from '@/lib/supabase';
import { Tweet } from '@/lib/types';

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


