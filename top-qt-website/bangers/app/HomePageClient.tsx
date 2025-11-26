'use client';

import { useState, useRef, useEffect } from 'react';
import { TweetCard } from './TweetCard';
import { TweetPane } from './TweetPane';
import { VerticalSpine } from './VerticalSpine';
import { Tweet } from '@/lib/types';

export const HomePageClient = ({ tweets }: { tweets: Tweet[] }) => {
  const [selectedTweets, setSelectedTweets] = useState<Tweet[]>([]);
  const [showTip, setShowTip] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Group tweets by column
  const groups: Record<string, Tweet[]> = {};
  tweets.forEach((tweet: Tweet) => {
    const col = tweet.column || 'Unknown';
    if (!groups[col]) {
      groups[col] = [];
    }
    groups[col].push(tweet);
  });

  const sortColumns = (a: string, b: string) => {
    const aNum = Number(a);
    const bNum = Number(b);
    
    if (!isNaN(aNum) && !isNaN(bNum)) {
      return bNum - aNum;
    }
    
    const order = ['Last Week', 'Last Month'];
    const aIndex = order.indexOf(a);
    const bIndex = order.indexOf(b);
    
    if (aIndex !== -1 && bIndex !== -1) {
      return aIndex - bIndex;
    }
    
    if (aIndex !== -1) return -1;
    if (bIndex !== -1) return 1;
    
    return a.localeCompare(b);
  };

  const tweetsByColumn = Object.keys(groups).sort(sortColumns).map(column => ({
    column: column,
    tweets: groups[column]
  }));

  const handleTweetClick = (tweet: Tweet, depth: number) => {
     const newStack = depth === -1 ? [] : selectedTweets.slice(0, depth + 1);
     newStack.push(tweet);
     setSelectedTweets(newStack);
  };

  const handleClosePane = (index: number) => {
    setSelectedTweets(selectedTweets.slice(0, index));
  };

  const handleSpineClick = (index: number) => {
      // Navigate back to this pane being the active one
      // index -1 means home
      if (index === -1) {
          setSelectedTweets([]);
      } else {
          setSelectedTweets(selectedTweets.slice(0, index + 1));
      }
  };

  useEffect(() => {
    // Scroll to the right when a new pane is added
    if (scrollContainerRef.current && selectedTweets.length > 0) {
        setTimeout(() => {
            scrollContainerRef.current?.scrollTo({
                left: scrollContainerRef.current.scrollWidth,
                behavior: 'smooth'
            });
        }, 100);
    }
  }, [selectedTweets.length]);

  const isHomeCollapsed = selectedTweets.length > 0;
  
  // Calculate width for the active pane to take available space
  // Standard spine width is w-12 (48px/3rem)
  const spineWidthPx = 48;
  const collapsedWidth = isHomeCollapsed ? (selectedTweets.length * spineWidthPx) : 0;
  
  // We want the active pane to fill the rest of the screen width, but min 500px
  // We can use calc(100vw - collapsedWidth)
  const activePaneStyle = isHomeCollapsed 
    ? { width: `calc(100vw - ${collapsedWidth}px)`, minWidth: '500px' }
    : { width: '500px' }; // Should not happen for active pane in collapsed mode but typescript safety

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
                onClick={() => handleSpineClick(-1)} 
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
                            <a 
                                href="/about"
                                className="text-base font-bold underline hover:opacity-70 transition-opacity"
                            >
                                About
                            </a>
                        </div>
                        <div className="text-sm italic mb-3">from the Community Archive</div>
                        {showTip && (
                            <div className="text-sm bg-yellow-50 border-2 border-yellow-400 px-3 py-2 rounded flex items-center justify-between gap-3">
                                <div>
                                    💡 <span className="font-semibold">Tip:</span> Click any tweet to open an explorer with quotes, replies, and context
                                </div>
                                <button 
                                    onClick={() => setShowTip(false)}
                                    className="text-yellow-700 hover:text-yellow-900 font-bold text-lg leading-none"
                                    aria-label="Close tip"
                                >
                                    ×
                                </button>
                            </div>
                        )}
                    </header>
                    
                    <main className="flex gap-8 overflow-x-auto flex-1 scrollbar-hide">
                        {tweetsByColumn.map(({ column, tweets }) => (
                        <section key={column} className="flex flex-col flex-shrink-0 w-[360px]">
                            <h2 className="text-2xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
                            {column}
                            </h2>
                            <div className="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar-hide pb-20">
                            {tweets.map(tweet => (
                                <div key={tweet.tweet_id} onClick={() => handleTweetClick(tweet, -1)} className="cursor-pointer hover:opacity-80 transition-opacity">
                                    <TweetCard tweet={tweet} />
                                </div>
                            ))}
                            </div>
                        </section>
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
                                    {' '}and{' '}
                                    <a 
                                    href="https://addons.mozilla.org/en-US/firefox/addon/community-archive/" 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="underline font-semibold hover:opacity-70"
                                    >
                                    Firefox
                                    </a>.
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
            // Only the last selected tweet is expanded
            const isLast = index === selectedTweets.length - 1;

            if (!isLast) {
                // Render Spine for non-active panes
                return (
                    <VerticalSpine 
                        key={`${tweet.tweet_id}-${index}`}
                        tweet={tweet}
                        onClick={() => handleSpineClick(index)}
                    />
                );
            }

            // Render Full Pane for active pane
            return (
                <div 
                  key={`${tweet.tweet_id}-${index}`} 
                  className="flex-shrink-0 h-full"
                  style={activePaneStyle}
                >
                    <TweetPane 
                        tweet={tweet}
                        onClose={() => handleClosePane(index)}
                        onSelectTweet={(t) => handleTweetClick(t, index)}
                    />
                </div>
            );
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
  );
};
