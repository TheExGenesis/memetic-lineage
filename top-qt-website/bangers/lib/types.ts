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
