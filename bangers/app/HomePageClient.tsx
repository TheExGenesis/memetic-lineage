'use client'

import { useState, useCallback, useEffect, useRef, useTransition, useMemo } from 'react'
import { TweetCard } from './TweetCard'
import { TweetPane } from './TweetPane'
import { VerticalSpine } from './VerticalSpine'
import { Tweet } from '@/lib/types'
import { useUrlSync, useTweetSelection, usePaneNavigation, prefetchAvatars, prefetchMedia, useBangersToggles } from './hooks'
import type { RankingMode, TweetSource } from './hooks'
import { fetchMoreTweetsByYear, searchAllTweets } from './actions/tweets'

const INITIAL_VISIBLE = 15;
const LOAD_MORE_VISIBLE = 20;

// Lazy loading column for tweets with server-side pagination
function LazyTweetColumn({
  column,
  initialTweets,
  onTweetClick,
  rankingMode,
  tweetSource,
  isSearchResult,
}: {
  column: string;
  initialTweets: Tweet[];
  onTweetClick: (tweet: Tweet) => void;
  rankingMode?: RankingMode;
  tweetSource?: TweetSource;
  isSearchResult?: boolean;
}) {
  const [tweets, setTweets] = useState(initialTweets);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreOnServer, setHasMoreOnServer] = useState(true);
  const [isPending, startTransition] = useTransition();
  const loadMoreRef = useRef<HTMLDivElement>(null);
  // Track server pagination offset separately from tweets.length,
  // since initial tweets may include archive-quote tweets not in the byYear ordering
  const serverOffset = useRef(30);

  // Update tweets when initialTweets changes (e.g., on navigation)
  useEffect(() => {
    setTweets(initialTweets);
    setVisibleCount(INITIAL_VISIBLE);
    setHasMoreOnServer(true);
  }, [initialTweets]);

  useEffect(() => {
    if (!loadMoreRef.current) return;

    const observer = new IntersectionObserver(
      async (entries) => {
        if (!entries[0].isIntersecting) return;

        // First, show more already-loaded tweets
        if (visibleCount < tweets.length) {
          setVisibleCount(prev => Math.min(prev + LOAD_MORE_VISIBLE, tweets.length));
          return;
        }

        // Then, fetch more from server if available (but not for search results)
        if (hasMoreOnServer && !isLoadingMore && !isPending && !isSearchResult) {
          setIsLoadingMore(true);
          startTransition(async () => {
            try {
              const moreTweets = await fetchMoreTweetsByYear(column, serverOffset.current);
              if (moreTweets.length === 0) {
                setHasMoreOnServer(false);
              } else {
                serverOffset.current += moreTweets.length;
                setTweets(prev => {
                  const existingIds = new Set(prev.map(t => t.tweet_id));
                  const newTweets = moreTweets.filter(t => !existingIds.has(t.tweet_id));
                  return [...prev, ...newTweets];
                });
                setVisibleCount(prev => prev + moreTweets.length);
              }
            } finally {
              setIsLoadingMore(false);
            }
          });
        }
      },
      { threshold: 0.1, rootMargin: '200px' }
    );

    observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, [visibleCount, tweets.length, hasMoreOnServer, isLoadingMore, isPending, column]);

  // Filter by source and re-sort when ranking/source changes
  const displayTweets = useMemo(() => {
    let filtered = tweetSource === 'archive'
      ? tweets.filter(t => t.is_archive_user)
      : tweets

    if (rankingMode === 'archive_quotes') {
      filtered = [...filtered].sort((a, b) => {
        const aqc = (a.archive_quote_count ?? 0) - (b.archive_quote_count ?? 0)
        if (aqc !== 0) return -aqc
        return (b.favorite_count ?? 0) - (a.favorite_count ?? 0)
      })
    }
    return filtered
  }, [tweets, rankingMode, tweetSource])

  const visibleTweets = displayTweets.slice(0, visibleCount);
  const hasMore = visibleCount < displayTweets.length || hasMoreOnServer;

  return (
    <section className="flex flex-col flex-shrink-0 w-full sm:w-[360px]">
      <h2 className="text-2xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
        {column}
      </h2>
      <div className="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar-hide pb-20">
        {visibleTweets.map((tweet, idx) => (
          <div
            key={`${tweet.tweet_id}-${idx}`}
            onClick={() => onTweetClick(tweet)}
            className="cursor-pointer hover:opacity-80 transition-opacity"
          >
            <TweetCard tweet={tweet} rankingMode={rankingMode} />
          </div>
        ))}
        {hasMore && (
          <div ref={loadMoreRef} className="py-4 text-center text-sm text-gray-400">
            {isLoadingMore || isPending ? 'Loading more tweets...' : 'Scroll to load more'}
          </div>
        )}
      </div>
    </section>
  );
}

export const HomePageClient = ({ tweets, snapshotDate }: { tweets: Tweet[]; snapshotDate?: string }) => {
  const [showTip, setShowTip] = useState(false) // Start hidden to avoid flash
  const [searchQuery, setSearchQuery] = useState('')
  const { tweetSource, rankingMode, setSource, setRanking, loaded: togglesLoaded } = useBangersToggles()

  // Load dismissed states from localStorage
  useEffect(() => {
    const tipDismissed = localStorage.getItem('homeTipDismissed');
    setShowTip(tipDismissed !== 'true');
  }, []);

  // Prefetch avatars and media for initial tweets
  useEffect(() => {
    const usernames = tweets.map(t => t.username).filter(Boolean);
    if (usernames.length > 0) prefetchAvatars(usernames);
    const tweetIds = tweets.map(t => t.tweet_id).filter(Boolean);
    if (tweetIds.length > 0) prefetchMedia(tweetIds);
  }, [tweets]);

  const {
    selectedTweets,
    setTweets,
    handleTweetClick,
    handleClosePane,
    handleSpineClick,
  } = useTweetSelection()

  const { updateUrl } = useUrlSync({
    tweets,
    onTweetsLoaded: setTweets,
  })

  const {
    scrollContainerRef,
    isHomeCollapsed,
    activePaneStyle,
  } = usePaneNavigation(selectedTweets.length)

  // URL-first navigation: only update URL, let useUrlSync update state
  // This prevents double-loading by making URL the single source of truth
  const onTweetClick = useCallback((tweet: Tweet, depth: number) => {
    const newStack = depth === -1 ? [tweet] : [...selectedTweets.slice(0, depth + 1), tweet]
    updateUrl(newStack)
  }, [selectedTweets, updateUrl])

  const onClosePane = useCallback((index: number) => {
    updateUrl(selectedTweets.slice(0, index))
  }, [selectedTweets, updateUrl])

  const onSpineClick = useCallback((index: number) => {
    const newStack = index === -1 ? [] : selectedTweets.slice(0, index + 1)
    updateUrl(newStack)
  }, [selectedTweets, updateUrl])

  // Server-side search across all tweets (not just initial batch)
  const [searchResults, setSearchResults] = useState<Tweet[] | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const query = searchQuery.trim()
    if (!query) {
      setSearchResults(null)
      return
    }

    // Debounce search requests
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    setIsSearching(true)
    searchTimerRef.current = setTimeout(async () => {
      const results = await searchAllTweets(query, 200)
      setSearchResults(results)
      setIsSearching(false)
    }, 300)

    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    }
  }, [searchQuery])

  const filteredTweets = searchResults !== null ? searchResults : tweets

  // Group tweets by column
  const groups: Record<string, Tweet[]> = {}
  filteredTweets.forEach((tweet: Tweet) => {
    const col = tweet.column || 'Unknown'
    if (!groups[col]) {
      groups[col] = []
    }
    groups[col].push(tweet)
  })

  // Sort columns by year (descending - most recent first)
  const sortColumns = (a: string, b: string) => {
    const aNum = Number(a)
    const bNum = Number(b)

    if (!isNaN(aNum) && !isNaN(bNum)) {
      return bNum - aNum
    }

    return a.localeCompare(b)
  }

  const tweetsByColumn = Object.keys(groups).sort(sortColumns).map(column => ({
    column: column,
    tweets: groups[column]
  }))

  return (
    <div className="h-[100dvh] flex flex-col bg-white text-black overflow-hidden">
      
      <div 
        ref={scrollContainerRef}
        className="flex flex-1 overflow-x-auto overflow-y-hidden scrollbar-hide"
      >
        {/* Root Pane / Home Spine */}
        {isHomeCollapsed ? (
            <VerticalSpine 
                label="Bangers Home" 
                onClick={() => onSpineClick(-1)} 
            />
        ) : (
            <div
                className={`flex flex-col flex-shrink-0 h-full border-r border-black transition-all duration-500 ease-in-out bg-gray-50 w-screen min-w-0`}
            >
                <div className="p-4 sm:p-8 h-full flex flex-col overflow-hidden">
                    <header className="mb-8 border-b-4 border-black pb-4 flex-shrink-0">
                        <div className="flex items-center justify-between mb-2">
                            <h1 className="text-4xl font-bold tracking-tighter">bangers</h1>
                            <div className="flex items-center gap-4">
                                <a
                                    href="/best-strands"
                                    className="text-base font-bold underline hover:opacity-70 transition-opacity"
                                >
                                    Strands
                                </a>
                                <a
                                    href="/about"
                                    className="text-base font-bold underline hover:opacity-70 transition-opacity"
                                >
                                    About
                                </a>
                            </div>
                        </div>
                        <p className="text-sm text-gray-600 mb-1">
                            The most-quoted tweets from the{' '}
                            <a href="https://communityarchive.org" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-70">Community Archive</a>
                            {snapshotDate ? `, as of ${snapshotDate}` : ''}.
                            Quote tweets are a signal for ideas that were load-bearing enough to build on.
                        </p>
                        <div className="text-sm text-gray-500 mb-3">
                            by{' '}
                            <a href="https://twitter.com/exgenesis" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-70">@exgenesis</a>
                            {' '}& {' '}
                            <a href="https://twitter.com/A_Variengien" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-70">@A_Variengien</a>
                        </div>
                        <div className="flex items-center gap-2 mb-3">
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Search tweets..."
                                className="flex-1 max-w-md px-3 py-2 border-2 border-black text-sm focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-1"
                            />
                            {searchQuery && (
                                <button
                                    onClick={() => setSearchQuery('')}
                                    className="px-3 py-2 border-2 border-black text-sm font-medium hover:bg-gray-100 transition-colors"
                                >
                                    Clear
                                </button>
                            )}
                            {searchQuery && (
                                <span className="text-sm text-gray-500">
                                    {isSearching ? 'Searching...' : `${filteredTweets.length} result${filteredTweets.length !== 1 ? 's' : ''}`}
                                </span>
                            )}
                        </div>
                        {togglesLoaded && (
                            <div className="flex flex-wrap items-center gap-3 mb-3">
                                <div className="flex items-center gap-1 text-xs">
                                    <span className="text-gray-500 mr-1">Show:</span>
                                    <button
                                        onClick={() => setSource('everyone')}
                                        className={`px-2 py-1 border border-black text-xs font-medium transition-colors ${
                                            tweetSource === 'everyone' ? 'bg-black text-white' : 'bg-white text-black hover:bg-gray-100'
                                        }`}
                                    >
                                        Everyone
                                    </button>
                                    <button
                                        onClick={() => setSource('archive')}
                                        className={`px-2 py-1 border border-black text-xs font-medium transition-colors ${
                                            tweetSource === 'archive' ? 'bg-black text-white' : 'bg-white text-black hover:bg-gray-100'
                                        }`}
                                    >
                                        Archive users
                                    </button>
                                </div>
                                <div className="flex items-center gap-1 text-xs">
                                    <span className="text-gray-500 mr-1">Rank by:</span>
                                    <button
                                        onClick={() => setRanking('all_quotes')}
                                        className={`px-2 py-1 border border-black text-xs font-medium transition-colors ${
                                            rankingMode === 'all_quotes' ? 'bg-black text-white' : 'bg-white text-black hover:bg-gray-100'
                                        }`}
                                    >
                                        All quotes
                                    </button>
                                    <button
                                        onClick={() => setRanking('archive_quotes')}
                                        className={`px-2 py-1 border border-black text-xs font-medium transition-colors ${
                                            rankingMode === 'archive_quotes' ? 'bg-black text-white' : 'bg-white text-black hover:bg-gray-100'
                                        }`}
                                    >
                                        Archive quotes
                                    </button>
                                </div>
                            </div>
                        )}
                        {showTip && (
                            <div className="text-xs text-gray-500 border-l-2 border-gray-300 pl-3 py-1 flex items-center justify-between gap-3">
                                <span>Click any tweet to explore its quotes, replies, and thread context.</span>
                                <button
                                    onClick={() => {
                                        setShowTip(false);
                                        localStorage.setItem('homeTipDismissed', 'true');
                                    }}
                                    className="text-gray-400 hover:text-gray-600 font-bold text-sm leading-none flex-shrink-0"
                                    aria-label="Dismiss"
                                >
                                    ×
                                </button>
                            </div>
                        )}
                    </header>
                    
                    <main className="flex flex-col sm:flex-row gap-8 overflow-y-auto sm:overflow-y-hidden sm:overflow-x-auto flex-1 scrollbar-hide">
                        {tweetsByColumn.map(({ column, tweets: columnTweets }) => (
                          <LazyTweetColumn
                            key={searchResults !== null ? `search-${column}` : column}
                            column={column}
                            initialTweets={columnTweets}
                            onTweetClick={(tweet) => onTweetClick(tweet, -1)}
                            rankingMode={rankingMode}
                            tweetSource={tweetSource}
                            isSearchResult={searchResults !== null}
                          />
                        ))}
                        
                        <section className="flex flex-col flex-shrink-0 w-full sm:w-[360px]">
                            <h2 className="text-2xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
                                About
                            </h2>
                            <div className="flex flex-col gap-6 overflow-y-auto flex-1 scrollbar-hide text-base leading-relaxed pb-20">
                                <div>
                                <h3 className="font-bold text-lg mb-2">The Community Archive</h3>
                                <p>
                                    The Community Archive is a crowdsourced database of Twitter history. 
                                    Over 1 billion tweets from 2006-2024, preserved by the community, for the community.
                                </p>
                                </div>
                                
                                <div>
                                <h3 className="font-bold text-lg mb-2">What are Bangers?</h3>
                                <p className="mb-3">
                                    Tweets that resonated so deeply they were quoted extensively—specifically 
                                    by people other than the OP. We rank by quote count from third parties.
                                </p>
                                </div>
                                
                                <div>
                                <h3 className="font-bold text-lg mb-2">Help Preserve Twitter</h3>
                                <p className="mb-3">
                                    <strong>Upload your archive:</strong> Visit{' '}
                                    <a 
                                    href="https://communityarchive.org" 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="underline font-semibold hover:opacity-70"
                                    >
                                    communityarchive.org
                                    </a>
                                </p>
                                <p className="mb-3">
                                    <strong>Browser extension:</strong> Save tweets as you browse. Available for{' '}
                                    <a 
                                    href="https://chromewebstore.google.com/detail/community-archive/hphgcnankimmomjiakdpcdjeiknbobmo" 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="underline font-semibold hover:opacity-70"
                                    >
                                    Chrome
                                    </a>
                                    .
                                </p>
                                </div>

                                <div className="border-t-2 border-black pt-6 mt-4">
                                <a 
                                    href="/about"
                                    className="block text-center bg-black text-white font-bold py-3 px-6 hover:bg-gray-800 transition-colors"
                                >
                                    Read More →
                                </a>
                                </div>
                            </div>
                        </section>
                    </main>
                </div>
            </div>
        )}

        {/* Stacked Panes */}
        {selectedTweets.map((tweet, index) => {
            const isLast = index === selectedTweets.length - 1

            if (!isLast) {
                return (
                    <VerticalSpine 
                        key={`${tweet.tweet_id}-${index}`}
                        tweet={tweet}
                        onClick={() => onSpineClick(index)}
                    />
                )
            }

            return (
                <div 
                  key={`${tweet.tweet_id}-${index}`} 
                  className="flex-shrink-0 h-full"
                  style={activePaneStyle}
                >
                    <TweetPane 
                        tweet={tweet}
                        onClose={() => onClosePane(index)}
                        onSelectTweet={(t) => onTweetClick(t, index)}
                    />
                </div>
            )
        })}

      </div>
      
      <style jsx global>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-hide {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  )
}
