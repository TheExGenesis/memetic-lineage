'use client';

import { useState, useCallback, useRef, useEffect, memo } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import Image from 'next/image';
import Markdown from 'react-markdown';
import { decode } from 'he';
import { StrandWithTweet, Tweet } from '@/lib/types';
import { StrandDetail } from './StrandDetail';
import { TweetPane } from '../TweetPane';
import { VerticalSpine } from '../VerticalSpine';
import { BackButton } from '../components/BackButton';
import { fetchTweetDetails } from '@/lib/api';
import { StrandHistogram, HistogramData } from './StrandHistogram';
import { StrandSemanticMap } from './StrandSemanticMap';

interface BestStrandsClientProps {
  strands: StrandWithTweet[];
}

const SPINE_WIDTH_PX = 48;

const formatDate = (dateStr?: string) => {
  if (!dateStr) return 'Unknown';
  try {
    return new Date(dateStr).toISOString().split('T')[0];
  } catch {
    return 'Unknown';
  }
};

const getRatingColor = (rating: number) => {
  if (rating >= 8) return 'bg-green-100 text-green-800 border-green-300';
  if (rating >= 6) return 'bg-yellow-100 text-yellow-800 border-yellow-300';
  return 'bg-gray-100 text-gray-800 border-gray-300';
};

const ExpandableText = ({ text, maxLength, className }: { text: string; maxLength: number; className?: string }) => {
  const [expanded, setExpanded] = useState(false);
  const decodedText = decode(text);
  const isLong = decodedText.length > maxLength;

  if (!isLong) {
    return <p className={className}>{decodedText}</p>;
  }

  return (
    <div>
      <p className={className}>
        {expanded ? decodedText : decodedText.slice(0, maxLength) + '...'}
      </p>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setExpanded(!expanded);
        }}
        className="text-xs text-blue-600 hover:underline mt-1"
      >
        {expanded ? 'Show less' : 'Show more'}
      </button>
    </div>
  );
};

const getFirstParagraph = (text: string): string => {
  // Split by double newlines or paragraph breaks and get first chunk
  const paragraphs = text.split(/\n\n+/);
  return paragraphs[0] || text;
};

const ExpandableSummaryMarkdown = ({ text, className }: { text: string; className?: string }) => {
  const [expanded, setExpanded] = useState(false);
  const firstPara = getFirstParagraph(text);
  const hasMore = text.length > firstPara.length;
  const displayText = expanded ? text : firstPara;

  return (
    <div>
      <div className={className}>
        <Markdown
          components={{
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
            em: ({ children }) => <em className="italic">{children}</em>,
            a: ({ href, children }) => (
              <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>
                {children}
              </a>
            ),
          }}
        >
          {displayText}
        </Markdown>
        {!expanded && hasMore && <span className="text-gray-500">...</span>}
      </div>
      {hasMore && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
          className="text-xs text-blue-600 hover:underline mt-1"
        >
          {expanded ? 'Show less' : 'Read more'}
        </button>
      )}
    </div>
  );
};

const TweetText = ({ text }: { text: string }) => (
  <ExpandableText text={text} maxLength={280} className="text-sm text-gray-700 whitespace-pre-line leading-relaxed" />
);

// Memoized strand card to prevent re-renders when histogramData or other parent state changes
interface StrandCardProps {
  strand: StrandWithTweet;
  histogramData: HistogramData | null;
  onSelect: () => void;
}

const StrandCard = memo(function StrandCard({ strand, histogramData, onSelect }: StrandCardProps) {
  const seedTweet = strand.seedTweet;
  const strandHistogram = histogramData?.strands[strand.seed_tweet_id];

  return (
    <div
      onClick={onSelect}
      className="bg-white border-2 border-black shadow-[4px_4px_0_0_#000] cursor-pointer transition-[box-shadow,transform] duration-150 will-change-transform hover:shadow-[6px_6px_0_0_#000] hover:-translate-y-0.5"
    >
      <div className="flex items-stretch">
        {/* Tweet Card - Left side (~35%) */}
        <div className="w-[35%] p-4 border-r-2 border-black flex flex-col">
          {seedTweet ? (
            <>
              <div className="flex items-center gap-2 mb-2">
                {seedTweet.avatar_media_url && (
                  <img
                    src={seedTweet.avatar_media_url}
                    alt={seedTweet.username}
                    className="w-8 h-8 rounded-full"
                  />
                )}
                <div>
                  <span className="font-bold text-sm">@{seedTweet.username}</span>
                  <a
                    href={`https://twitter.com/${seedTweet.username}/status/${seedTweet.tweet_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-xs text-gray-500 font-mono hover:text-blue-600 hover:underline block"
                  >
                    {formatDate(seedTweet.created_at)}
                  </a>
                </div>
              </div>
              <TweetText text={seedTweet.full_text} />
              {/* Tweet images */}
              {seedTweet.media_urls && seedTweet.media_urls.length > 0 && (() => {
                const uniqueUrls = Array.from(new Set(seedTweet.media_urls))
                return (
                  <div
                    className={`grid gap-2 mt-3 ${uniqueUrls.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}
                  >
                    {uniqueUrls.map((url, i) => (
                      <div
                        key={i}
                        className="rounded-lg overflow-hidden border border-gray-200 relative aspect-video"
                      >
                        <Image
                          src={url}
                          alt="Tweet media"
                          fill
                          sizes="300px"
                          className="object-cover"
                        />
                      </div>
                    ))}
                  </div>
                )
              })()}
            </>
          ) : (
            <p className="text-sm text-gray-400">Tweet not found</p>
          )}
        </div>

        {/* Summary Card - Right side (~65%) */}
        <div className="w-[65%] p-4 flex flex-col">
          {/* Header with title, rating and scores */}
          <div className="mb-2">
            {strand.title && (
              <h2 className="text-base font-bold text-gray-900 mb-1">{strand.title}</h2>
            )}
            <div className="flex items-center gap-3">
              <span className={`inline-block px-2 py-0.5 text-sm font-bold border ${getRatingColor(strand.rating.rating)}`}>
                {strand.rating.rating}
              </span>
              <div className="flex gap-2 text-xs">
                <span className="cursor-help text-gray-600" title="Cohesion: How coherent and unified is the strand's narrative?">
                  Cohesion: <span className="font-medium">{strand.rating.cohesion}</span>
                </span>
                <span className="cursor-help text-gray-600" title="Evolution: How does the idea develop and progress over time?">
                  Evolution: <span className="font-medium">{strand.rating.evolution}</span>
                </span>
                <span className="cursor-help text-gray-600" title="Utility: How valuable and insightful are the perspectives?">
                  Utility: <span className="font-medium">{strand.rating.utility}</span>
                </span>
              </div>
            </div>
          </div>
          {/* Summary text - expandable */}
          <div className="flex-1 flex flex-col">
            <ExpandableSummaryMarkdown
              text={strand.summary || strand.rating.reasoning_summary}
              className="text-sm text-gray-700 leading-relaxed"
            />
          </div>
          {/* Histogram */}
          <div className="mt-3">
            {histogramData && strandHistogram && (
              <StrandHistogram
                strandData={strandHistogram}
                months={histogramData.months}
                showHeader={false}
              />
            )}
          </div>
          {/* Timeline info and click indicator */}
          <div className="mt-3 text-xs text-gray-400 flex items-center gap-2">
            {strandHistogram && (
              <>
                <span>
                  ({strandHistogram.total_tweets} tweets derived from {strand.seeds?.length || 0} seeds)
                </span>
                <span>•</span>
              </>
            )}
            <span className="flex items-center gap-1">
              Click to explore timeline
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14" />
                <path d="M12 5l7 7-7 7" />
              </svg>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
});

const INITIAL_STRANDS = 10;
const LOAD_MORE_STRANDS = 10;

export function BestStrandsClient({ strands }: BestStrandsClientProps) {
  const [selectedStrand, setSelectedStrand] = useState<StrandWithTweet | null>(null);
  const [selectedTweets, setSelectedTweets] = useState<Tweet[]>([]);
  const [noteDismissed, setNoteDismissed] = useState(true); // Start hidden to avoid flash
  const [histogramData, setHistogramData] = useState<HistogramData | null>(null);
  const [visibleStrandsCount, setVisibleStrandsCount] = useState(INITIAL_STRANDS);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const tweetCacheRef = useRef<Map<string, Tweet>>(new Map());
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();

  // Check localStorage for dismissed note on mount
  useEffect(() => {
    const dismissed = localStorage.getItem('bestStrandsNoteDismissed');
    setNoteDismissed(dismissed === 'true');
  }, []);

  // Fetch histogram data once for all strands
  useEffect(() => {
    async function loadHistogramData() {
      try {
        const response = await fetch('/strand_histograms.json');
        if (response.ok) {
          const data: HistogramData = await response.json();
          setHistogramData(data);
        }
      } catch (err) {
        console.error('Failed to load histogram data:', err);
      }
    }
    loadHistogramData();
  }, []);

  // Lazy load more strands on scroll
  useEffect(() => {
    if (!loadMoreRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && visibleStrandsCount < strands.length) {
          setVisibleStrandsCount(prev => Math.min(prev + LOAD_MORE_STRANDS, strands.length));
        }
      },
      { threshold: 0.1, rootMargin: '200px' }
    );

    observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, [visibleStrandsCount, strands.length]);

  // Calculate pane width based on selected tweets
  const collapsedWidth = selectedTweets.length > 0 ? selectedTweets.length * SPINE_WIDTH_PX : 0;
  const activePaneStyle = {
    width: selectedTweets.length > 0 ? `calc(100vw - ${collapsedWidth}px)` : '500px',
    minWidth: '500px',
  };

  // Auto-scroll when new panes are added
  useEffect(() => {
    if (scrollContainerRef.current && selectedTweets.length > 0) {
      setTimeout(() => {
        scrollContainerRef.current?.scrollTo({
          left: scrollContainerRef.current.scrollWidth,
          behavior: 'smooth',
        });
      }, 100);
    }
  }, [selectedTweets.length]);

  // Sync selected strand with path param (/best-strands/[seed])
  useEffect(() => {
    const seedParam = (params as Record<string, string | undefined>)?.seed;
    if (!seedParam) {
      if (selectedStrand) {
        setSelectedStrand(null);
        setSelectedTweets([]);
      }
      return;
    }
    if (!selectedStrand || selectedStrand.seed_tweet_id !== seedParam) {
      const found = strands.find(s => s.seed_tweet_id === seedParam);
      if (found) {
        setSelectedStrand(found);
        // Don't clear tweets here - let the search params sync handle it
      }
    }
  }, [params, strands, selectedStrand]);

  // Sync selected tweets with URL search params (?tweets=id1,id2)
  useEffect(() => {
    const loadTweetsFromUrl = async () => {
      const tweetIds = searchParams.get('tweets');
      if (!tweetIds) {
        if (selectedTweets.length > 0) {
          setSelectedTweets([]);
        }
        return;
      }

      const ids = tweetIds.split(',').filter(Boolean);
      const tweetsToLoad: Tweet[] = [];
      const missingIds: string[] = [];

      for (const id of ids) {
        const cached = tweetCacheRef.current.get(id);
        if (cached) {
          tweetsToLoad.push(cached);
        } else {
          missingIds.push(id);
        }
      }

      if (missingIds.length > 0) {
        const fetched = await fetchTweetDetails(missingIds);
        fetched.forEach(t => tweetCacheRef.current.set(t.tweet_id, t));
        // Rebuild in correct order
        const allTweets = ids
          .map(id => tweetCacheRef.current.get(id))
          .filter((t): t is Tweet => t !== undefined);
        setSelectedTweets(allTweets);
      } else {
        setSelectedTweets(tweetsToLoad);
      }
    };

    loadTweetsFromUrl();
  }, [searchParams]);

  // Helper to update URL with tweet selection
  const updateTweetUrl = useCallback((tweets: Tweet[]) => {
    // Cache tweets before updating URL
    tweets.forEach(t => tweetCacheRef.current.set(t.tweet_id, t));

    const seedParam = (params as Record<string, string | undefined>)?.seed;
    const basePath = seedParam ? `/best-strands/${seedParam}` : '/best-strands';

    if (tweets.length === 0) {
      router.push(basePath);
    } else {
      const ids = tweets.map(t => t.tweet_id).join(',');
      router.push(`${basePath}?tweets=${ids}`);
    }
  }, [params, router]);

  const selectStrand = useCallback((strand: StrandWithTweet) => {
    router.push(`/best-strands/${strand.seed_tweet_id}`);
  }, [router]);

  // URL-first navigation: update URL, let effect sync state
  const handleTweetClick = useCallback((tweet: Tweet, depth: number) => {
    const newStack = depth === -1 ? [tweet] : [...selectedTweets.slice(0, depth + 1), tweet];
    updateTweetUrl(newStack);
  }, [selectedTweets, updateTweetUrl]);

  const handleClosePane = useCallback((index: number) => {
    updateTweetUrl(selectedTweets.slice(0, index));
  }, [selectedTweets, updateTweetUrl]);

  const handleSpineClick = useCallback((index: number) => {
    const newStack = index === -1 ? [] : selectedTweets.slice(0, index + 1);
    updateTweetUrl(newStack);
  }, [selectedTweets, updateTweetUrl]);

  const handleBackFromStrand = useCallback(() => {
    // Use browser back if we have history, otherwise navigate to strands list
    if (window.history.length > 1) {
      router.back();
    } else {
      router.push('/best-strands');
    }
  }, [router]);

  // Forward horizontal wheel deltas from inner panes to the outer scroller
  const forwardHorizontalWheel = useCallback((dx: number) => {
    if (!scrollContainerRef.current) return;
    scrollContainerRef.current.scrollLeft += dx;
  }, []);

  // When viewing a strand with tweet panes
  if (selectedStrand) {
    const hasSelectedTweets = selectedTweets.length > 0;

    return (
      <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
        <div
          ref={scrollContainerRef}
          className="flex flex-1 min-h-0 overflow-x-auto overflow-y-hidden scrollbar-hide touch-pan-x"
          style={{ overscrollBehaviorY: 'none' as any }}
        >
          {/* Strand Detail as main pane or spine */}
          {hasSelectedTweets ? (
            <VerticalSpine
              label={`Strand: ${selectedStrand.seedTweet?.username || 'Unknown'}`}
              onClick={() => setSelectedTweets([])}
            />
          ) : (
            <div className="flex flex-col flex-shrink-0 h-full w-full min-h-0">
              <StrandDetail
                strand={selectedStrand}
                onBack={handleBackFromStrand}
                onSelectTweet={(tweet) => handleTweetClick(tweet, -1)}
                onHorizontalScroll={forwardHorizontalWheel}
              />
            </div>
          )}

          {/* Stacked Tweet Panes */}
          {selectedTweets.map((tweet, index) => {
            const isLast = index === selectedTweets.length - 1;

            if (!isLast) {
              return (
                <VerticalSpine
                  key={`${tweet.tweet_id}-${index}`}
                  tweet={tweet}
                  onClick={() => handleSpineClick(index)}
                />
              );
            }

            return (
              <div
                key={`${tweet.tweet_id}-${index}`}
                className="flex flex-col flex-shrink-0 h-full min-h-0"
                style={activePaneStyle}
              >
                <TweetPane
                  tweet={tweet}
                  onClose={() => handleClosePane(index)}
                  onSelectTweet={(t) => handleTweetClick(t, index)}
                  onHorizontalScroll={forwardHorizontalWheel}
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
  }

  // Strand list view
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <header className="mb-8 border-b-4 border-black pb-4">
          <div className="flex items-center justify-between gap-4 mb-2">
            <div className="flex items-center gap-4">
              <BackButton fallbackHref="/" />
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Strands</h1>
                <div className="text-sm text-gray-600 max-w-4xl mt-2">
                  <p className="leading-relaxed">
                    <strong className="text-gray-900">Strands are units of narrative</strong>—stories worth telling that exist{' '}
                    <em>one level above</em> individual tweets or threads, connecting multiple conversations into coherent narratives.
                  </p>
                  <div className="mt-3 space-y-1.5">
                    <p className="flex gap-2">
                      <span className="text-gray-400">1.</span>
                      <span><strong className="text-gray-700">Start with bangers</strong> — high-impact tweets with many quote tweets</span>
                    </p>
                    <p className="flex gap-2">
                      <span className="text-gray-400">2.</span>
                      <span><strong className="text-gray-700">Find semantic neighbors</strong> — thematically related but structurally disconnected tweets</span>
                    </p>
                    <p className="flex gap-2">
                      <span className="text-gray-400">3.</span>
                      <span><strong className="text-gray-700">Gather connected content</strong> — quotes and replies that form the full conversation</span>
                    </p>
                    <p className="flex gap-2">
                      <span className="text-gray-400">4.</span>
                      <span><strong className="text-gray-700">Analyze with LLM</strong> — rated on <em>cohesion</em>, <em>evolution</em>, and <em>utility</em></span>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>

        {!noteDismissed && (
          <div className="mb-4 bg-blue-50 border border-blue-200 rounded px-4 py-2 text-sm text-blue-800 flex items-start justify-between gap-2">
            <p>
              <span className="font-semibold">Note:</span> Data is from a static snapshot taken in early December 2025.
              Strand ratings are generated by AI analysis of conversation threads.
            </p>
            <button
              onClick={() => {
                setNoteDismissed(true);
                localStorage.setItem('bestStrandsNoteDismissed', 'true');
              }}
              className="text-blue-600 hover:text-blue-800 p-1 -mr-1 -mt-0.5"
              title="Dismiss"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6L6 18" />
                <path d="M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Semantic Map */}
        <StrandSemanticMap />

        <div className="flex flex-col gap-4">
          {strands.slice(0, visibleStrandsCount).map((strand) => (
            <StrandCard
              key={strand.seed_tweet_id}
              strand={strand}
              histogramData={histogramData}
              onSelect={() => selectStrand(strand)}
            />
          ))}
          {visibleStrandsCount < strands.length && (
            <div ref={loadMoreRef} className="py-8 text-center text-sm text-gray-400">
              Loading more strands...
            </div>
          )}
        </div>

        <div className="mt-8 text-center text-sm text-gray-500">
          Showing {Math.min(visibleStrandsCount, strands.length)} of {strands.length} strands
        </div>
      </div>
    </div>
  );
}
