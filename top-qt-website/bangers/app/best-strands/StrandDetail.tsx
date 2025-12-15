'use client';

import { useState, useEffect } from 'react';
import { StrandWithTweet, Tweet, EssentialTweet } from '@/lib/types';
import { TweetCard } from '../TweetCard';
import { ThreadView } from '../ThreadView';
import { fetchTweetDetails, getThread, getConversationId } from '@/lib/api';

interface StrandDetailProps {
  strand: StrandWithTweet;
  onBack: () => void;
  onSelectTweet?: (tweet: Tweet) => void;
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
      return 'bg-purple-100 text-purple-700 border-purple-300';
    case 'semantic_search':
      return 'bg-blue-100 text-blue-700 border-blue-300';
    case 'quote_of_root':
      return 'bg-orange-100 text-orange-700 border-orange-300';
    case 'quote_of_semantic_search':
      return 'bg-teal-100 text-teal-700 border-teal-300';
    default:
      return 'bg-gray-100 text-gray-600 border-gray-300';
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

export function StrandDetail({ strand, onBack, onSelectTweet }: StrandDetailProps) {
  const [essentialTweetsData, setEssentialTweetsData] = useState<EssentialTweetWithData[]>([]);
  const [loading, setLoading] = useState(true);
  const [columnWidth, setColumnWidth] = useState(380);
  const [copied, setCopied] = useState(false);

  const copyPlainText = async () => {
    await navigator.clipboard.writeText(strand.thread_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

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
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b-2 border-black p-3 flex-shrink-0">
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
              <h1 className="text-lg font-bold tracking-tight">Strand Detail</h1>
              <span className="text-sm text-gray-500">
                {strand.rating.essential_tweets.length} essential tweets
              </span>
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
                className="px-3 py-1.5 border border-black text-xs font-bold uppercase hover:bg-gray-100 transition-colors flex items-center gap-1.5"
                title="Copy plain text"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                {copied ? 'Copied!' : 'Copy Text'}
              </button>

              <a
                href={`/multi-thread-visualizer?seed=${strand.seed_tweet_id}`}
                className="px-3 py-1.5 bg-black text-white text-xs font-bold uppercase hover:bg-gray-800 transition-colors flex items-center gap-1.5"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 3v12" />
                  <circle cx="18" cy="6" r="3" />
                  <circle cx="6" cy="18" r="3" />
                  <path d="M18 9a9 9 0 0 1-9 9" />
                </svg>
                Explore
              </a>
            </div>
          </div>

          {/* Compact info row: seed tweet, score, metrics, seeds */}
          <div className="flex items-stretch gap-3 border border-gray-200 bg-gray-50 p-2">
            {/* Seed Tweet - compact */}
            <div
              className={`flex items-center gap-2 flex-shrink-0 max-w-xs border-r border-gray-200 pr-3 ${onSelectTweet ? 'cursor-pointer hover:bg-gray-100' : ''}`}
              onClick={() => strand.seedTweet && onSelectTweet?.(strand.seedTweet)}
            >
              {strand.seedTweet ? (
                <>
                  {strand.seedTweet.avatar_media_url && (
                    <img src={strand.seedTweet.avatar_media_url} alt="" className="w-8 h-8 rounded-full flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="text-xs font-bold">@{strand.seedTweet.username}</div>
                    <div className="text-xs text-gray-600 truncate max-w-[200px]">
                      {strand.seedTweet.full_text.slice(0, 60)}{strand.seedTweet.full_text.length > 60 ? '...' : ''}
                    </div>
                  </div>
                </>
              ) : (
                <span className="text-xs text-gray-400">No seed tweet</span>
              )}
            </div>

            {/* Overall Score */}
            <div className="flex items-center gap-2 border-r border-gray-200 pr-3">
              <div className="text-2xl font-bold">{strand.rating.rating}</div>
              <div className="text-xs uppercase text-gray-500">/10</div>
            </div>

            {/* Metrics badges */}
            <div className="flex items-center gap-2 border-r border-gray-200 pr-3">
              <span className={`px-1.5 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.evolution)}`}>
                E:{strand.rating.evolution}
              </span>
              <span className={`px-1.5 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.cohesion)}`}>
                C:{strand.rating.cohesion}
              </span>
              <span className={`px-1.5 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.utility)}`}>
                U:{strand.rating.utility}
              </span>
            </div>

            {/* Seeds breakdown */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-gray-500">Seeds ({strand.seeds?.length || 0}):</span>
              {strand.seeds && strand.seeds.length > 0 ? (
                Object.entries(
                  strand.seeds.reduce((acc, s) => {
                    acc[s.source_type] = (acc[s.source_type] || 0) + 1;
                    return acc;
                  }, {} as Record<string, number>)
                ).map(([type, count]) => (
                  <span
                    key={type}
                    className={`px-1.5 py-0.5 text-xs font-semibold border rounded ${getSourceTypeStyle(type)}`}
                  >
                    {formatSourceType(type)}: {count}
                  </span>
                ))
              ) : (
                <span className="text-xs text-gray-400">none</span>
              )}
            </div>
          </div>

          {/* Analysis - full width below */}
          <div className="mt-2 p-2 bg-white border border-gray-200">
            <p className="text-sm leading-relaxed text-gray-700">
              <span className="font-semibold text-gray-500 uppercase text-xs mr-2">Analysis:</span>
              {strand.rating.reasoning_summary}
            </p>
          </div>
        </div>
      </header>

      {/* Essential Tweets Visualization */}
      <div className="flex-1 overflow-hidden">
        <div className="p-4 border-b border-gray-200 bg-white">
          <h2 className="text-lg font-bold">Essential Tweets Timeline</h2>
          <p className="text-sm text-gray-600">Chronologically ordered key moments in this strand&apos;s evolution</p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-gray-500 animate-pulse">Loading essential tweets...</div>
          </div>
        ) : (
          <div className="flex overflow-x-auto overflow-y-hidden h-full pb-4">
            {essentialTweetsData.map((etData, idx) => {
              const isEven = idx % 2 === 0;
              const bgClass = isEven ? 'bg-white' : 'bg-gray-50';

              return (
                <div
                  key={etData.tweet_id}
                  className={`flex-shrink-0 h-full border-r border-gray-200 flex flex-col ${bgClass}`}
                  style={{ width: columnWidth }}
                >
                  {/* Column Header with Annotation */}
                  <div className="p-3 border-b border-gray-200 bg-blue-50 flex-shrink-0">
                    <div className="text-xs text-blue-600 font-semibold uppercase mb-1">
                      {formatDate(etData.tweet?.created_at)} • #{idx + 1}
                    </div>
                    <div className="text-sm text-gray-700 italic leading-snug">
                      {etData.annotation}
                    </div>
                  </div>

                  {/* Thread View */}
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

