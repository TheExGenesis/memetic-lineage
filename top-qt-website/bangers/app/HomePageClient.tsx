'use client'

import { useState, useCallback, useEffect, useRef, useTransition } from 'react'
import { TweetCard } from './TweetCard'
import { TweetPane } from './TweetPane'
import { VerticalSpine } from './VerticalSpine'
import { Tweet } from '@/lib/types'
import { useUrlSync, useTweetSelection, usePaneNavigation } from './hooks'
import { fetchMoreTweetsByYear } from './actions/tweets'

const INITIAL_VISIBLE = 15;
const LOAD_MORE_VISIBLE = 20;

// Lazy loading column for tweets with server-side pagination
function LazyTweetColumn({
  column,
  initialTweets,
  onTweetClick
}: {
  column: string;
  initialTweets: Tweet[];
  onTweetClick: (tweet: Tweet) => void;
}) {
  const [tweets, setTweets] = useState(initialTweets);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreOnServer, setHasMoreOnServer] = useState(true);
  const [isPending, startTransition] = useTransition();
  const loadMoreRef = useRef<HTMLDivElement>(null);

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

        // Then, fetch more from server if available
        if (hasMoreOnServer && !isLoadingMore && !isPending) {
          setIsLoadingMore(true);
          startTransition(async () => {
            try {
              const moreTweets = await fetchMoreTweetsByYear(column, tweets.length);
              if (moreTweets.length === 0) {
                setHasMoreOnServer(false);
              } else {
                setTweets(prev => [...prev, ...moreTweets]);
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

  const visibleTweets = tweets.slice(0, visibleCount);
  const hasMore = visibleCount < tweets.length || hasMoreOnServer;

  return (
    <section className="flex flex-col flex-shrink-0 w-[360px]">
      <h2 className="text-2xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
        {column}
      </h2>
      <div className="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar-hide pb-20">
        {visibleTweets.map(tweet => (
          <div
            key={tweet.tweet_id}
            onClick={() => onTweetClick(tweet)}
            className="cursor-pointer hover:opacity-80 transition-opacity"
          >
            <TweetCard tweet={tweet} />
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

export const HomePageClient = ({ tweets }: { tweets: Tweet[] }) => {
  const [showTip, setShowTip] = useState(false) // Start hidden to avoid flash
  const [showDataNote, setShowDataNote] = useState(false) // Start hidden to avoid flash

  // Load dismissed states from localStorage
  useEffect(() => {
    const tipDismissed = localStorage.getItem('homeTipDismissed');
    const dataDismissed = localStorage.getItem('homeDataNoteDismissed');
    setShowTip(tipDismissed !== 'true');
    setShowDataNote(dataDismissed !== 'true');
  }, []);

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

  // Group tweets by column
  const groups: Record<string, Tweet[]> = {}
  tweets.forEach((tweet: Tweet) => {
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
    <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
      
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
                className={`flex flex-col flex-shrink-0 h-full border-r border-black transition-all duration-500 ease-in-out bg-gray-50`}
                style={{ 
                    width: '100vw',
                    minWidth: '500px' 
                }}
            >
                <div className="p-8 h-full flex flex-col overflow-hidden">
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
                        <div className="text-sm italic mb-1">from the Community Archive</div>
                        <div className="text-sm mb-3">
                            by{' '}
                            <a href="https://twitter.com/exgenesis" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-70">@exgenesis</a>
                            {' '}& {' '}
                            <a href="https://twitter.com/A_Variengien" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-70">@A_Variengien</a>
                        </div>
                        {showTip && (
                            <div className="text-sm bg-yellow-50 border-2 border-yellow-400 px-3 py-2 rounded flex items-center justify-between gap-3">
                                <div>
                                    💡 <span className="font-semibold">Tip:</span> Click any tweet to open an explorer with quotes, replies, and context
                                </div>
                                <button
                                    onClick={() => {
                                        setShowTip(false);
                                        localStorage.setItem('homeTipDismissed', 'true');
                                    }}
                                    className="text-yellow-700 hover:text-yellow-900 font-bold text-lg leading-none"
                                    aria-label="Close tip"
                                >
                                    ×
                                </button>
                            </div>
                        )}
                        {showDataNote && (
                            <div className="text-xs bg-blue-50 border border-blue-200 px-3 py-2 rounded mt-2 text-blue-700 flex items-center justify-between gap-2">
                                <span>ℹ️ Data snapshot from early December 2025</span>
                                <button
                                    onClick={() => {
                                        setShowDataNote(false);
                                        localStorage.setItem('homeDataNoteDismissed', 'true');
                                    }}
                                    className="text-blue-600 hover:text-blue-800 font-bold text-lg leading-none"
                                    aria-label="Dismiss"
                                >
                                    ×
                                </button>
                            </div>
                        )}
                    </header>
                    
                    <main className="flex gap-8 overflow-x-auto flex-1 scrollbar-hide">
                        {tweetsByColumn.map(({ column, tweets: columnTweets }) => (
                          <LazyTweetColumn
                            key={column}
                            column={column}
                            initialTweets={columnTweets}
                            onTweetClick={(tweet) => onTweetClick(tweet, -1)}
                          />
                        ))}
                        
                        <section className="flex flex-col flex-shrink-0 w-[360px]">
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
