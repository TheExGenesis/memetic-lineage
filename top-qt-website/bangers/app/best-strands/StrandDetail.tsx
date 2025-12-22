'use client';

import { useState, useEffect } from 'react';
import Markdown from 'react-markdown';
import { decode } from 'he';
import { StrandWithTweet, Tweet, EssentialTweet } from '@/lib/types';
import { TweetCard } from '../TweetCard';
import { ThreadView } from '../ThreadView';
import { BackButton } from '../components/BackButton';
import { fetchTweetDetails, getThread, getConversationId } from '@/lib/api';
import { StrandHistogram, HistogramData } from './StrandHistogram';

interface StrandDetailProps {
  strand: StrandWithTweet;
  onBack: () => void;
  onSelectTweet?: (tweet: Tweet) => void;
  onHorizontalScroll?: (dx: number) => void;
}

interface EssentialTweetWithData extends EssentialTweet {
  tweet?: Tweet;
  threadTweets?: Tweet[];
}

const getLevelBadge = (level: 'high' | 'medium' | 'low') => {
  switch (level) {
    case 'high':
      return 'bg-emerald-100 text-emerald-700 border-emerald-300';
    case 'medium':
      return 'bg-amber-100 text-amber-700 border-amber-300';
    case 'low':
      return 'bg-slate-100 text-slate-600 border-slate-300';
  }
};

const getSourceTypeStyle = (sourceType: string) => {
  switch (sourceType) {
    case 'root':
      return 'bg-gray-700 text-white border-gray-800';
    case 'quote_of_root':
      return 'bg-gray-500 text-white border-gray-600';
    case 'semantic_search':
      return 'bg-gray-300 text-gray-800 border-gray-400';
    case 'quote_of_semantic_search':
      return 'bg-gray-200 text-gray-700 border-gray-300';
    default:
      return 'bg-gray-100 text-gray-600 border-gray-300';
  }
};

const getSourceTypeTooltip = (sourceType: string): string => {
  switch (sourceType) {
    case 'root':
      return 'Root: The original seed tweet that generates this strand';
    case 'quote_of_root':
      return 'Quote of Root: Tweets that directly quote the root tweet';
    case 'semantic_search':
      return 'Semantic: Tweets with similar meaning found via semantic search';
    case 'quote_of_semantic_search':
      return 'Quote of Semantic: Tweets that quote the semantically similar tweets';
    default:
      return sourceType;
  }
};

const formatSourceType = (sourceType: string) => {
  switch (sourceType) {
    case 'root': return 'Root';
    case 'semantic_search': return 'Semantic';
    case 'quote_of_root': return 'Qt of Root';
    case 'quote_of_semantic_search': return 'Qt of Semantic';
    default: return sourceType;
  }
};

export function StrandDetail({ strand, onBack, onSelectTweet, onHorizontalScroll }: StrandDetailProps) {
  const [essentialTweetsData, setEssentialTweetsData] = useState<EssentialTweetWithData[]>([]);
  const [loading, setLoading] = useState(true);
  const [columnWidth, setColumnWidth] = useState(380);
  const [copied, setCopied] = useState(false);
  const [histogramData, setHistogramData] = useState<HistogramData | null>(null);

  const copyPlainText = async () => {
    await navigator.clipboard.writeText(strand.thread_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Fetch histogram data
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

  useEffect(() => {
    async function loadEssentialTweets() {
      setLoading(true);
      
      // Get all essential tweet IDs (already strings from parsed JSON)
      const tweetIds = strand.rating.essential_tweets.map(et => et.tweet_id);
      
      // Fetch all tweets at once
      const tweets = await fetchTweetDetails(tweetIds);
      const tweetMap = new Map(tweets.map(t => [t.tweet_id, t]));
      
      // For each essential tweet, get its thread context
      const essentialData: EssentialTweetWithData[] = await Promise.all(
        strand.rating.essential_tweets.map(async (et) => {
          const tweetId = et.tweet_id;
          const tweet = tweetMap.get(tweetId);
          
          let threadTweets: Tweet[] = [];
          if (tweet) {
            // Try to get conversation context
            const convId = await getConversationId(tweetId);
            if (convId) {
              threadTweets = await getThread(convId);
            } else {
              threadTweets = [tweet];
            }
          }
          
          return {
            ...et,
            tweet,
            threadTweets,
          };
        })
      );
      
      // Sort by tweet creation date
      essentialData.sort((a, b) => {
        const dateA = a.tweet?.created_at ? new Date(a.tweet.created_at).getTime() : 0;
        const dateB = b.tweet?.created_at ? new Date(b.tweet.created_at).getTime() : 0;
        return dateA - dateB;
      });
      
      setEssentialTweetsData(essentialData);
      setLoading(false);
    }
    
    loadEssentialTweets();
  }, [strand]);

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      return new Date(dateStr).toISOString().split('T')[0];
    } catch {
      return '';
    }
  };

  return (
    <div className="relative bg-gray-50 h-full overflow-y-auto">
      {/* Header */}
      <header className="bg-white border-b-2 border-black p-3">
        <div className="max-w-full mx-auto">
          {/* Top row: navigation and actions */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <button
                onClick={onBack}
                className="p-1.5 hover:bg-gray-100 transition-colors border border-transparent hover:border-black"
                title="Back to strands"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5" />
                  <path d="M12 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className="text-lg font-bold tracking-tight">
                  {strand.title || 'Strand Detail'}
                </h1>
                <span className="text-sm text-gray-500">
                  {strand.rating.essential_tweets.length} essential tweets
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-gray-500">Width</label>
                <input
                  type="range"
                  min={300}
                  max={600}
                  value={columnWidth}
                  onChange={e => setColumnWidth(Number(e.target.value))}
                  className="w-20"
                />
                <span className="text-xs font-mono w-10">{columnWidth}</span>
              </div>

              <button
                onClick={copyPlainText}
                className="px-3 py-1.5 border border-black text-xs font-bold hover:bg-gray-100 transition-colors flex items-center gap-1.5"
                title="Copy plain text"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                {copied ? 'Copied!' : 'Copy text'}
              </button>

              <a
                href={`/multi-thread-visualizer?seed=${strand.seed_tweet_id}`}
                className="px-3 py-1.5 bg-black text-white text-xs font-bold hover:bg-gray-800 transition-colors flex items-center gap-1.5"
                title="View all seed data including quotes and semantic matches"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 3v12" />
                  <circle cx="18" cy="6" r="3" />
                  <circle cx="6" cy="18" r="3" />
                  <path d="M18 9a9 9 0 0 1-9 9" />
                </svg>
                Explore seeds
              </a>
            </div>
          </div>

          {/* Info row: seed tweet, stats columns, analysis card */}
          <div className="flex gap-3 border border-gray-200 bg-gray-50 p-2">
            {/* Seed Tweet */}
            <div
              className={`flex items-start gap-2 flex-shrink-0 w-64 border-r border-gray-200 pr-3 ${onSelectTweet ? 'cursor-pointer hover:bg-gray-100' : ''}`}
              onClick={() => strand.seedTweet && onSelectTweet?.(strand.seedTweet)}
            >
              {strand.seedTweet ? (
                <>
                  {strand.seedTweet.avatar_media_url && (
                    <img src={strand.seedTweet.avatar_media_url} alt="" className="w-8 h-8 rounded-full flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="text-xs font-bold">@{strand.seedTweet.username}</div>
                    <div className="text-xs text-gray-600 whitespace-pre-line line-clamp-4">
                      {decode(strand.seedTweet.full_text)}
                    </div>
                  </div>
                </>
              ) : (
                <span className="text-xs text-gray-400">No seed tweet</span>
              )}
            </div>

            {/* Rating & Metrics - stacked vertically */}
            <div className="flex flex-col gap-1.5 border-r border-gray-200 pr-3">
              <div className="flex items-center gap-1">
                <div className="text-2xl font-bold">{strand.rating.rating}</div>
                <div className="text-xs text-gray-500">/10</div>
              </div>
              <span
                className={`px-1.5 py-0.5 text-xs font-medium border rounded cursor-help ${getLevelBadge(strand.rating.cohesion)}`}
                title="Cohesion: How coherent and unified is the strand's narrative?"
              >
                Cohesion: {strand.rating.cohesion}
              </span>
              <span
                className={`px-1.5 py-0.5 text-xs font-medium border rounded cursor-help ${getLevelBadge(strand.rating.evolution)}`}
                title="Evolution: How does the idea develop and progress over time?"
              >
                Evolution: {strand.rating.evolution}
              </span>
              <span
                className={`px-1.5 py-0.5 text-xs font-medium border rounded cursor-help ${getLevelBadge(strand.rating.utility)}`}
                title="Utility: How valuable and insightful are the perspectives?"
              >
                Utility: {strand.rating.utility}
              </span>
            </div>

            {/* Seeds breakdown - stacked vertically */}
            <div className="flex flex-col gap-1 border-r border-gray-200 pr-3">
              <span className="text-xs text-gray-500 font-medium">Seeds ({strand.seeds?.length || 0})</span>
              {strand.seeds && strand.seeds.length > 0 ? (
                Object.entries(
                  strand.seeds.reduce((acc, s) => {
                    acc[s.source_type] = (acc[s.source_type] || 0) + 1;
                    return acc;
                  }, {} as Record<string, number>)
                ).map(([type, count]) => (
                  <span
                    key={type}
                    className={`px-1.5 py-0.5 text-xs font-medium border rounded cursor-help ${getSourceTypeStyle(type)}`}
                    title={getSourceTypeTooltip(type)}
                  >
                    {formatSourceType(type)}: {count}
                  </span>
                ))
              ) : (
                <span className="text-xs text-gray-400">none</span>
              )}
            </div>

            {/* Summary - as right card, fully expanded */}
            <div className="flex-1 p-2 bg-white border border-gray-200 rounded">
              <p className="text-xs font-medium text-gray-500 mb-1">Summary</p>
              <div className="text-sm leading-relaxed text-gray-700">
                <Markdown
                  components={{
                    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                    em: ({ children }) => <em className="italic">{children}</em>,
                    a: ({ href, children }) => (
                      <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
                        {children}
                      </a>
                    ),
                  }}
                >
                  {strand.summary || strand.rating.reasoning_summary}
                </Markdown>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Histogram Section */}
      <div className="p-4 bg-white border-b-2 border-black">
        <div className="max-w-full mx-auto">
          {histogramData && (
            <StrandHistogram
              strandData={histogramData.strands[strand.seed_tweet_id] || null}
              months={histogramData.months}
              showHeader={true}
            />
          )}
        </div>
      </div>

      {/* Essential Tweets Visualization */}
      <div className="p-4 bg-gray-50">
        <div className="mb-4">
          <h2 className="text-lg font-bold">Essential Tweets Timeline</h2>
          <p className="text-sm text-gray-600">Chronologically ordered key moments in this strand&apos;s evolution</p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-gray-500 animate-pulse">Loading essential tweets...</div>
          </div>
        ) : (
          <div
            className="flex overflow-x-auto pb-4"
            style={{ minHeight: 'calc(100vh - 280px)' }}
          >
            {essentialTweetsData.map((etData, idx) => {
              const isEven = idx % 2 === 0;
              const bgClass = isEven ? 'bg-white' : 'bg-gray-50';

              return (
                <div
                  key={etData.tweet_id}
                  className={`flex-shrink-0 border-r border-gray-200 flex flex-col ${bgClass}`}
                  style={{ width: columnWidth, height: '100%' }}
                >
                  {/* Column Header with Annotation */}
                  <div className="p-3 border-b border-gray-200 bg-blue-50 flex-shrink-0">
                    <div className="text-xs text-blue-600 font-semibold uppercase mb-1">
                      {formatDate(etData.tweet?.created_at)} • #{idx + 1}
                    </div>
                    <div className="text-sm text-gray-700 leading-snug">
                      {etData.annotation}
                    </div>
                  </div>

                  {/* Thread View - scrollable column */}
                  <div className="flex-1 overflow-y-auto p-3">
                    {etData.threadTweets && etData.threadTweets.length > 0 ? (
                      <ThreadView
                        tweets={etData.threadTweets}
                        focusedTweetId={etData.tweet_id}
                        onSelectTweet={onSelectTweet || (() => {})}
                        onSelectQuotedTweet={async () => {}}
                      />
                    ) : etData.tweet ? (
                      <div
                        className={onSelectTweet ? 'cursor-pointer hover:opacity-80' : ''}
                        onClick={() => etData.tweet && onSelectTweet?.(etData.tweet)}
                      >
                        <TweetCard tweet={etData.tweet} />
                      </div>
                    ) : (
                      <div className="text-sm text-gray-500 text-center py-8">
                        Tweet not found
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
