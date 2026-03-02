export interface Tweet {
  tweet_id: string;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count?: number; // Optional as it might not be in all DB responses
  archive_quote_count?: number;
  is_archive_user?: boolean;
  reply_to_tweet_id?: string;
  reply_to_user_id?: string;
  reply_to_username?: string;
  conversation_id?: string;
  avatar_media_url?: string;
  media_urls?: string[];
  // For compatibility with HomePageClient grouping
  column?: string; 
  year?: number;
  quoted_tweet_id?: string;
  quoted_tweet?: {
    tweet_id: string;
    created_at: string;
    full_text: string;
    username: string;
    favorite_count: number;
    retweet_count: number;
    avatar_media_url?: string;
    media_urls?: string[];
  };
}

export interface EssentialTweet {
  tweet_id: string; // String to preserve precision for large Twitter IDs
  annotation: string;
}

export type StrandSeedSourceType = 'root' | 'semantic_search' | 'quote_of_root' | 'quote_of_semantic_search';

export interface StrandSeed {
  tweet_id: string;
  source_type: StrandSeedSourceType;
}

export interface StrandRating {
  reasoning_summary: string;
  rating: number;
  evolution: 'high' | 'medium' | 'low';
  cohesion: 'high' | 'medium' | 'low';
  utility: 'high' | 'medium' | 'low';
  essential_tweets: EssentialTweet[];
}

export interface Strand {
  seed_tweet_id: string; // String to preserve precision for large Twitter IDs
  thread_text: string;
  seeds: StrandSeed[];
  rating: StrandRating;
  title?: string;
  summary?: string; // Markdown-formatted summary
}

// Extended strand with fetched tweet data for display
export interface StrandWithTweet extends Strand {
  seedTweet?: Tweet;
}
