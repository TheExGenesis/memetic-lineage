'use client';

import { useState } from 'react';

interface Tweet {
  tweet_id: number;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count: number;
  year: number;
  quoted_tweet_id?: number;
  avatar_media_url?: string;
  conversation_id?: number;
}

export const TweetCard = ({ tweet }: { tweet: Tweet }) => {
  const [expanded, setExpanded] = useState(false);
  const tweetUrl = `https://twitter.com/${tweet.username}/status/${tweet.tweet_id}`;
  
  const shouldTruncate = tweet.full_text.length > 280;
  const displayText = expanded || !shouldTruncate 
    ? tweet.full_text 
    : tweet.full_text.slice(0, 280) + '...';

  return (
    <div className="border-b border-black pb-4 mb-4 last:border-b-0 break-inside-avoid">
      <div className="flex items-start gap-3 mb-2">
        <div className="w-8 h-8 bg-gray-200 rounded-full overflow-hidden flex-shrink-0 border border-black">
          {tweet.avatar_media_url && (
            <img src={tweet.avatar_media_url} alt={tweet.username} className="w-full h-full object-cover" />
          )}
        </div>
        <div className="flex-1">
          <div className="font-bold text-sm">@{tweet.username}</div>
          <a 
            href={tweetUrl} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-xs text-gray-600 hover:underline"
          >
            {new Date(tweet.created_at).toISOString().split('T')[0]}
          </a>
        </div>
      </div>
      
      <div className="text-sm leading-relaxed mb-3 whitespace-pre-line">
        {displayText}
      </div>
      
      {shouldTruncate && (
        <button 
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-blue-600 hover:underline mb-2"
        >
          {expanded ? 'Show less' : 'Read more'}
        </button>
      )}
      
      <div className="flex gap-4 text-xs text-gray-500 font-mono">
        <span>♥ {tweet.favorite_count}</span>
        <span>↻ {tweet.retweet_count}</span>
        <span>❝ {tweet.quote_count}</span>
      </div>
    </div>
  );
};

