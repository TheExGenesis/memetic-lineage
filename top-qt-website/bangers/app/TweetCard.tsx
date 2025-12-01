'use client'

import { useState } from 'react'
import { decode } from 'he'
import { Tweet } from '@/lib/types'

type TweetCardProps = {
  tweet: Tweet;
  onQuotedTweetClick?: (quotedTweetId: string) => void;
};

export const TweetCard = ({ tweet, onQuotedTweetClick }: TweetCardProps) => {
  const [expanded, setExpanded] = useState(false)
  const tweetUrl = `https://twitter.com/${tweet.username}/status/${tweet.tweet_id}`
  // Only truncate if significantly longer to avoid close calls
  const TRUNCATE_LENGTH = 280
  const shouldTruncate = tweet.full_text.length > TRUNCATE_LENGTH

  // Use a fixed truncation for initial render to avoid hydration mismatch
  // Then let React take over state
  const getDisplayText = (text: string, isExpanded: boolean) => {
    if (!shouldTruncate || isExpanded) return text
    return text.slice(0, TRUNCATE_LENGTH) + '...'
  }

  const displayText = getDisplayText(tweet.full_text, expanded)

  // Handle fallback for formatted date if created_at is invalid (though it should be valid)
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toISOString().split('T')[0]
    } catch {
      return dateStr
    }
  }

  return (
    <div className="border-b border-black pb-4 mb-4 last:border-b-0 break-inside-avoid">
      <div className="flex items-start gap-3 mb-2">
        <div className="w-8 h-8 bg-gray-200 rounded-full overflow-hidden flex-shrink-0 border border-black">
          {tweet.avatar_media_url && (
            <img
              src={tweet.avatar_media_url}
              alt={tweet.username}
              className="w-full h-full object-cover"
            />
          )}
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <div>
          <div className="font-bold text-sm">@{tweet.username}</div>
              <div className="text-xs text-gray-600">
                {formatDate(tweet.created_at)}
              </div>
            </div>
            <a
              href={tweetUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-blue-600 transition-colors opacity-60 hover:opacity-100"
              onClick={(e) => e.stopPropagation()}
              title="View on Twitter"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </div>
        </div>
      </div>

      <div className="text-sm leading-relaxed mb-3 whitespace-pre-line">
        {decode(displayText)}
      </div>

      {shouldTruncate && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            setExpanded(!expanded)
          }}
          className="text-xs text-blue-600 hover:underline mb-2"
        >
          {expanded ? 'Show less' : 'Read more'}
        </button>
      )}

      {/* Render Images */}
      {tweet.media_urls && tweet.media_urls.length > 0 && (() => {
        const uniqueUrls = Array.from(new Set(tweet.media_urls))
        return (
          <div
            className={`grid gap-2 mb-3 ${uniqueUrls.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}
          >
            {uniqueUrls.map((url, i) => (
              <div
                key={i}
                className="rounded-lg overflow-hidden border border-gray-200"
              >
                <img
                  src={url}
                  alt="Tweet media"
                  className="w-full h-auto object-cover max-h-96"
                />
              </div>
            ))}
          </div>
        )
      })()}

      {/* Render Quoted Tweet */}
      {tweet.quoted_tweet && tweet.quoted_tweet_id && (
        <div
          className="border border-gray-300 rounded-lg p-3 mb-3 hover:bg-gray-50 transition-colors"
          onClick={(e) => {
            if (!onQuotedTweetClick) return;
            e.stopPropagation();
            onQuotedTweetClick(tweet.quoted_tweet_id!);
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <div className="w-5 h-5 bg-gray-200 rounded-full overflow-hidden flex-shrink-0">
              {tweet.quoted_tweet.avatar_media_url && (
                <img
                  src={tweet.quoted_tweet.avatar_media_url}
                  alt={tweet.quoted_tweet.username}
                  className="w-full h-full object-cover"
                />
              )}
            </div>
            <span className="font-bold text-xs">
              @{tweet.quoted_tweet.username}
            </span>
            <span className="text-xs text-gray-500">
              {formatDate(tweet.quoted_tweet.created_at)}
            </span>
          </div>
          <div className="text-sm mb-2">
            {decode(tweet.quoted_tweet.full_text)}
          </div>
          {tweet.quoted_tweet.media_urls &&
            tweet.quoted_tweet.media_urls.length > 0 && (
              <div className="rounded overflow-hidden border border-gray-200">
                <img
                  src={tweet.quoted_tweet.media_urls[0]}
                  alt="Quoted media"
                  className="w-full h-32 object-cover"
                />
              </div>
            )}
        </div>
      )}

      <div className="flex gap-4 text-xs text-gray-500 font-mono">
        <span>♥ {tweet.favorite_count}</span>
        <span>↻ {tweet.retweet_count}</span>
        {tweet.quote_count !== undefined && <span>❝ {tweet.quote_count}</span>}
      </div>
    </div>
  )
}
