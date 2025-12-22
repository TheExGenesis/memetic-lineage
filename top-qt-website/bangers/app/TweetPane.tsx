'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { Tweet } from '@/lib/types';
import { TweetCard } from './TweetCard';
import { ThreadView } from './ThreadView';
import { getThread, getQuotes, getConversationId, fetchTweetDetails } from '@/lib/api';
import { searchEmbeddings, SemanticSearchResult } from '@/app/actions/search';

interface TweetPaneProps {
  tweet: Tweet;
  onClose: () => void;
  onSelectTweet: (tweet: Tweet) => void;
  onHorizontalScroll?: (dx: number) => void;
}

const INITIAL_ITEMS = 10;
const LOAD_MORE_ITEMS = 20;

// Lazy loading list component
function LazyList<T>({
  items,
  renderItem,
  loading,
  emptyMessage
}: {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  loading: boolean;
  emptyMessage: string;
}) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_ITEMS);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loadMoreRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && visibleCount < items.length) {
          setVisibleCount(prev => Math.min(prev + LOAD_MORE_ITEMS, items.length));
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, [visibleCount, items.length]);

  // Reset visible count when items change
  useEffect(() => {
    setVisibleCount(INITIAL_ITEMS);
  }, [items]);

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="border border-gray-200 p-4 rounded animate-pulse">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 bg-gray-200 rounded-full" />
              <div className="h-4 w-24 bg-gray-200 rounded" />
            </div>
            <div className="space-y-2">
              <div className="h-4 w-full bg-gray-100 rounded" />
              <div className="h-4 w-3/4 bg-gray-100 rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return <div className="text-gray-500 italic text-center py-8">{emptyMessage}</div>;
  }

  const visibleItems = items.slice(0, visibleCount);
  const hasMore = visibleCount < items.length;

  return (
    <div className="space-y-4">
      {visibleItems.map((item, index) => renderItem(item, index))}
      {hasMore && (
        <div ref={loadMoreRef} className="py-4 text-center text-sm text-gray-400">
          Loading more...
        </div>
      )}
    </div>
  );
}

export const TweetPane = ({ tweet, onClose, onSelectTweet, onHorizontalScroll }: TweetPaneProps) => {
  const [threadTweets, setThreadTweets] = useState<Tweet[]>([]);
  const [quoteTweets, setQuoteTweets] = useState<Tweet[]>([]);
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>([]);
  const [threadLoading, setThreadLoading] = useState(true);
  const [quotesLoading, setQuotesLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(true);
  const [quoteSort, setQuoteSort] = useState<'likes' | 'retweets' | 'date_desc' | 'date_asc'>('likes');

  const findTweetById = (id: string): Tweet | undefined => {
    return (
      threadTweets.find((t) => t.tweet_id === id) ||
      quoteTweets.find((t) => t.tweet_id === id) ||
      searchResults.find((r) => r.tweet.tweet_id === id)?.tweet
    );
  };

  const handleQuotedTweetSelect = async (quotedId: string) => {
    const existing = findTweetById(quotedId);
    if (existing) {
      onSelectTweet(existing);
      return;
    }

    const fetched = await fetchTweetDetails([quotedId]);
    if (fetched.length > 0) {
      onSelectTweet(fetched[0]);
    }
  };

  // Load all three data sources - prioritize thread
  useEffect(() => {
    // Load thread first (priority)
    const loadThread = async () => {
      setThreadLoading(true);
      let convId = tweet.conversation_id;

      if (!convId) {
        const id = await getConversationId(tweet.tweet_id);
        convId = id || undefined;
      }

      let data: Tweet[] = [];
      if (convId) {
        data = await getThread(convId);
      } else {
        data = [tweet];
      }

      setThreadTweets(data);
      setThreadLoading(false);
    };

    // Load quotes (parallel with search)
    const loadQuotes = async () => {
      setQuotesLoading(true);
      const data = await getQuotes(tweet.tweet_id);
      setQuoteTweets(data);
      setQuotesLoading(false);
    };

    // Load vector search (parallel with quotes)
    const loadSearch = async () => {
      setSearchLoading(true);
      const results = await searchEmbeddings(tweet.full_text, tweet.tweet_id);
      setSearchResults(results);
      setSearchLoading(false);
    };

    // Start thread first, then others in parallel
    loadThread();
    // Small delay to prioritize thread, then load others
    setTimeout(() => {
      loadQuotes();
      loadSearch();
    }, 100);
  }, [tweet]);

  // Sort quotes (memoized to prevent re-sorting on every render)
  const sortedQuotes = useMemo(() => {
    return [...quoteTweets].sort((a, b) => {
      switch (quoteSort) {
        case 'likes':
          return (b.favorite_count ?? 0) - (a.favorite_count ?? 0);
        case 'retweets':
          return (b.retweet_count ?? 0) - (a.retweet_count ?? 0);
        case 'date_desc':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'date_asc':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        default:
          return 0;
      }
    });
  }, [quoteTweets, quoteSort]);

  return (
    <div
      className="flex flex-col w-full h-full min-h-0 bg-white"
      onWheel={(e) => {
        if (!onHorizontalScroll) return;
        const absX = Math.abs(e.deltaX);
        const absY = Math.abs(e.deltaY);
        if (absX > absY || e.shiftKey) {
          e.preventDefault();
          e.stopPropagation();
          onHorizontalScroll(e.deltaX || (e.shiftKey ? e.deltaY : 0));
        }
      }}
    >
      {/* Header with selected tweet */}
      <div className="border-b-2 border-black p-4 bg-white flex-shrink-0">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1" style={{ maxWidth: '400px' }}>
            <TweetCard
              tweet={tweet}
              onQuotedTweetClick={handleQuotedTweetSelect}
            />
          </div>
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 border border-transparent hover:border-black transition-colors"
              aria-label="Close pane"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
            <a
              href={`/multi-thread-visualizer?seed=${tweet.tweet_id}`}
              className="inline-flex items-center gap-2 px-3 py-2 bg-black text-white text-xs font-bold uppercase tracking-wide hover:bg-gray-800 transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 3v12" />
                <circle cx="18" cy="6" r="3" />
                <circle cx="6" cy="18" r="3" />
                <path d="M18 9a9 9 0 0 1-9 9" />
              </svg>
              Explore Strand
            </a>
          </div>
        </div>
      </div>

      {/* Three columns */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Thread Column */}
        <div className="flex-1 flex flex-col border-r border-gray-200 min-w-0">
          <div className="p-3 border-b border-gray-200 bg-gray-50 flex-shrink-0">
            <h3 className="font-bold text-sm uppercase tracking-wide">Thread</h3>
            <p className="text-xs text-gray-500">{threadLoading ? 'Loading...' : `${threadTweets.length} tweets`}</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
            {threadLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => (
                  <div key={i} className="border border-gray-200 p-4 rounded animate-pulse">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-8 h-8 bg-gray-200 rounded-full" />
                      <div className="h-4 w-24 bg-gray-200 rounded" />
                    </div>
                    <div className="space-y-2">
                      <div className="h-4 w-full bg-gray-100 rounded" />
                      <div className="h-4 w-3/4 bg-gray-100 rounded" />
                    </div>
                  </div>
                ))}
              </div>
            ) : threadTweets.length === 0 ? (
              <div className="text-gray-500 italic text-center py-8">No thread found</div>
            ) : (
              <ThreadView
                tweets={threadTweets}
                focusedTweetId={tweet.tweet_id}
                onSelectTweet={onSelectTweet}
                onSelectQuotedTweet={handleQuotedTweetSelect}
              />
            )}
          </div>
        </div>

        {/* Quotes Column */}
        <div className="flex-1 flex flex-col border-r border-gray-200 min-w-0">
          <div className="p-3 border-b border-gray-200 bg-gray-50 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm uppercase tracking-wide">Quote Tweets</h3>
                <p className="text-xs text-gray-500">{quotesLoading ? 'Loading...' : `${quoteTweets.length} quotes`}</p>
              </div>
              <select
                value={quoteSort}
                onChange={(e) => setQuoteSort(e.target.value as typeof quoteSort)}
                className="text-xs border border-gray-300 px-2 py-1 rounded"
              >
                <option value="likes">By Likes</option>
                <option value="retweets">By RTs</option>
                <option value="date_desc">Newest</option>
                <option value="date_asc">Oldest</option>
              </select>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
            <LazyList
              items={sortedQuotes}
              loading={quotesLoading}
              emptyMessage="No quote tweets found"
              renderItem={(qt) => (
                <div
                  key={qt.tweet_id}
                  onClick={() => onSelectTweet(qt)}
                  className="cursor-pointer transition-opacity hover:opacity-80"
                >
                  <TweetCard
                    tweet={qt}
                    onQuotedTweetClick={handleQuotedTweetSelect}
                  />
                </div>
              )}
            />
          </div>
        </div>

        {/* Vector Search Column */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="p-3 border-b border-gray-200 bg-gray-50 flex-shrink-0">
            <h3 className="font-bold text-sm uppercase tracking-wide">Similar Tweets</h3>
            <p className="text-xs text-gray-500">{searchLoading ? 'Loading...' : `${searchResults.length} results`}</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
            <LazyList
              items={searchResults}
              loading={searchLoading}
              emptyMessage="No similar tweets found"
              renderItem={(result) => (
                <div
                  key={result.key}
                  onClick={() => onSelectTweet(result.tweet)}
                  className="cursor-pointer transition-opacity hover:opacity-80"
                >
                  <div className="text-xs text-gray-400 mb-1 text-right">
                    Similarity: {(result.distance * 100).toFixed(1)}%
                  </div>
                  <TweetCard
                    tweet={result.tweet}
                    onQuotedTweetClick={handleQuotedTweetSelect}
                  />
                </div>
              )}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
