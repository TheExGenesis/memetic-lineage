export interface Tweet {
  tweet_id: string;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count?: number; // Optional as it might not be in all DB responses
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
}

// Extended strand with fetched tweet data for display
export interface StrandWithTweet extends Strand {
  seedTweet?: Tweet;
}

// Graph visualization types
export interface GraphNode {
  tweet_id: string;
  strand_id: string;
  strand_index: number;
  is_root: boolean;
  order_in_strand: number;
  // Precomputed positions from Python force layout:
  precomputed_x?: number;
  precomputed_y?: number;
  // Enriched at runtime from Supabase:
  avatar_url?: string;
  username?: string;
  full_text?: string;
  created_at?: string;
  media_urls?: string[];
  // For d3-force simulation (added at runtime):
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  weight?: number;
}

export interface StrandMeta {
  strand_id: string;
  strand_index: number;
  root_tweet_id: string;
  reasoning_summary: string;
  rating: number;
}

export interface GraphData {
  nodes: GraphNode[];
  intraStrandEdges: GraphEdge[];
  interStrandEdges: GraphEdge[];
  strandMeta: StrandMeta[];
}
