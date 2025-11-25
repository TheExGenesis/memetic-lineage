'use client';

import { useState } from 'react';
import Image from 'next/image';

const decodeHtml = (html: string): string => {
  if (typeof document === 'undefined') {
    return html
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#039;/g, "'");
  }
  const txt = document.createElement('textarea');
  txt.innerHTML = html;
  return txt.value;
};

interface Tweet {
  tweet_id: string;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count: number;
  year: number;
  quoted_tweet_id?: string;
  avatar_media_url?: string;
  conversation_id?: string;
  media_urls?: string[];
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

export const TweetCard = ({ tweet }: { tweet: Tweet }) => {
  const [expanded, setExpanded] = useState(false);
  const tweetUrl = `https://twitter.com/${tweet.username}/status/${tweet.tweet_id}`;
  
  const decodedText = decodeHtml(tweet.full_text);
  const shouldTruncate = decodedText.length > 280;
  const displayText = expanded || !shouldTruncate 
    ? decodedText 
    : decodedText.slice(0, 280) + '...';

  return (
    <div className="border-b border-black pb-4 mb-4 last:border-b-0 break-inside-avoid">
      <div className="flex items-start gap-3 mb-2">
        <div className="w-8 h-8 bg-gray-200 rounded-full overflow-hidden flex-shrink-0 border border-black">
          {tweet.avatar_media_url && (
            <Image 
              src={tweet.avatar_media_url} 
              alt={tweet.username} 
              width={32}
              height={32}
              className="w-full h-full object-cover" 
              unoptimized
            />
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

      {tweet.media_urls && tweet.media_urls.length > 0 && (
        <div className="mb-3 space-y-2">
          {tweet.media_urls.map((url, idx) => (
            <div key={idx} className="rounded overflow-hidden border border-black">
              <Image 
                src={url} 
                alt={`Tweet media ${idx + 1}`}
                width={600}
                height={400}
                className="w-full h-auto object-contain"
                unoptimized
              />
            </div>
          ))}
        </div>
      )}

      {tweet.quoted_tweet && (
        <div className="mb-3 border border-gray-400 rounded p-2 bg-gray-50">
          <div className="flex items-start gap-2 mb-1">
            {tweet.quoted_tweet.avatar_media_url && (
              <div className="w-6 h-6 bg-gray-200 rounded-full overflow-hidden flex-shrink-0 border border-gray-300">
                <Image 
                  src={tweet.quoted_tweet.avatar_media_url} 
                  alt={tweet.quoted_tweet.username} 
                  width={24}
                  height={24}
                  className="w-full h-full object-cover" 
                  unoptimized
                />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-bold">@{tweet.quoted_tweet.username}</div>
              <div className="text-xs text-gray-600">
                {new Date(tweet.quoted_tweet.created_at).toISOString().split('T')[0]}
              </div>
            </div>
          </div>
          <div className="text-xs leading-relaxed mb-2 whitespace-pre-line">
            {decodeHtml(tweet.quoted_tweet.full_text)}
          </div>
          {tweet.quoted_tweet.media_urls && tweet.quoted_tweet.media_urls.length > 0 && (
            <div className="mb-2 space-y-1">
              {tweet.quoted_tweet.media_urls.map((url, idx) => (
                <div key={idx} className="rounded overflow-hidden border border-gray-300">
                  <Image 
                    src={url} 
                    alt={`Quoted tweet media ${idx + 1}`}
                    width={300}
                    height={200}
                    className="w-full h-auto object-contain"
                    unoptimized
                  />
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-3 text-xs text-gray-500 font-mono">
            <span>♥ {tweet.quoted_tweet.favorite_count}</span>
            <span>↻ {tweet.quoted_tweet.retweet_count}</span>
          </div>
        </div>
      )}
      
      <div className="flex gap-4 text-xs text-gray-500 font-mono">
        <span>♥ {tweet.favorite_count}</span>
        <span>↻ {tweet.retweet_count}</span>
        <span>❝ {tweet.quote_count}</span>
      </div>
    </div>
  );
};

