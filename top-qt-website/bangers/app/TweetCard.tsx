'use client';

import { useState } from 'react';
import { Tweet } from '@/lib/types';

export const TweetCard = ({ tweet }: { tweet: Tweet }) => {
  const [expanded, setExpanded] = useState(false);
  const tweetUrl = `https://twitter.com/${tweet.username}/status/${tweet.tweet_id}`;
  
  // Only truncate if significantly longer to avoid close calls
  const TRUNCATE_LENGTH = 280;
  const shouldTruncate = tweet.full_text.length > TRUNCATE_LENGTH;
  
  // Use a fixed truncation for initial render to avoid hydration mismatch
  // Then let React take over state
  const getDisplayText = (text: string, isExpanded: boolean) => {
      if (!shouldTruncate || isExpanded) return text;
      return text.slice(0, TRUNCATE_LENGTH) + '...';
  };

  const displayText = getDisplayText(tweet.full_text, expanded);

  // Handle fallback for formatted date if created_at is invalid (though it should be valid)
  const formatDate = (dateStr: string) => {
    try {
        return new Date(dateStr).toISOString().split('T')[0];
    } catch (e) {
        return dateStr;
    }
  };

  return (
    <div className="border-b border-black pb-4 mb-4 last:border-b-0 break-inside-avoid bg-white">
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
            onClick={(e) => e.stopPropagation()} 
          >
            {formatDate(tweet.created_at)}
          </a>
        </div>
      </div>
      
      <div className="text-sm leading-relaxed mb-3 whitespace-pre-line">
        {displayText}
      </div>
      
      {shouldTruncate && (
        <button 
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
          className="text-xs text-blue-600 hover:underline mb-2"
        >
          {expanded ? 'Show less' : 'Read more'}
        </button>
      )}
      
      <div className="flex gap-4 text-xs text-gray-500 font-mono">
        <span>♥ {tweet.favorite_count}</span>
        <span>↻ {tweet.retweet_count}</span>
        {tweet.quote_count !== undefined && <span>❝ {tweet.quote_count}</span>}
      </div>
    </div>
  );
};
