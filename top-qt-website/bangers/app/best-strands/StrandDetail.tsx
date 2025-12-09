'use client';

import { useState, useEffect } from 'react';
import { StrandWithTweet, Tweet, EssentialTweet } from '@/lib/types';
import { TweetCard } from '../TweetCard';
import { ThreadView } from '../ThreadView';
import { fetchTweetDetails, getThread, getConversationId } from '@/lib/api';

interface StrandDetailProps {
  strand: StrandWithTweet;
  onBack: () => void;
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

export function StrandDetail({ strand, onBack }: StrandDetailProps) {
  const [essentialTweetsData, setEssentialTweetsData] = useState<EssentialTweetWithData[]>([]);
  const [loading, setLoading] = useState(true);
  const [columnWidth, setColumnWidth] = useState(380);

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
      <header className="bg-white border-b-2 border-black p-4 flex-shrink-0">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <button
                onClick={onBack}
                className="p-2 hover:bg-gray-100 transition-colors border border-transparent hover:border-black"
                title="Back to strands"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M19 12H5" />
                  <path d="M12 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className="text-2xl font-bold tracking-tight">Strand Detail</h1>
                <p className="text-sm text-gray-600">
                  {strand.rating.essential_tweets.length} essential tweets
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-500 uppercase">Column Width</label>
                <input
                  type="range"
                  min={300}
                  max={600}
                  value={columnWidth}
                  onChange={e => setColumnWidth(Number(e.target.value))}
                  className="w-24"
                />
                <span className="text-xs font-mono w-12">{columnWidth}px</span>
              </div>
              
              <a
                href={`/multi-thread-visualizer?seed=${strand.seed_tweet_id}`}
                className="px-4 py-2 bg-black text-white font-bold text-sm uppercase hover:bg-gray-800 transition-colors"
              >
                Recreate Strand
              </a>
            </div>
          </div>

          {/* Strand Info */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Seed Tweet */}
            <div className="bg-gray-50 border border-gray-200 p-4">
              <h3 className="text-xs uppercase font-bold text-gray-500 mb-3">Seed Tweet</h3>
              {strand.seedTweet ? (
                <TweetCard tweet={strand.seedTweet} />
              ) : (
                <p className="text-sm text-gray-500">Tweet not found</p>
              )}
            </div>

            {/* Summary */}
            <div className="bg-gray-50 border border-gray-200 p-4">
              <h3 className="text-xs uppercase font-bold text-gray-500 mb-3">Analysis</h3>
              <p className="text-sm leading-relaxed text-gray-700">
                {strand.rating.reasoning_summary}
              </p>
            </div>

            {/* Scores */}
            <div className="bg-gray-50 border border-gray-200 p-4">
              <h3 className="text-xs uppercase font-bold text-gray-500 mb-3">Scores</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center">
                  <div className="text-3xl font-bold">{strand.rating.rating}</div>
                  <div className="text-xs uppercase text-gray-500">Overall</div>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase text-gray-500">Evolution</span>
                    <span className={`px-2 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.evolution)}`}>
                      {strand.rating.evolution}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase text-gray-500">Cohesion</span>
                    <span className={`px-2 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.cohesion)}`}>
                      {strand.rating.cohesion}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase text-gray-500">Utility</span>
                    <span className={`px-2 py-0.5 text-xs font-semibold uppercase border rounded ${getLevelBadge(strand.rating.utility)}`}>
                      {strand.rating.utility}
                    </span>
                  </div>
                </div>
              </div>
            </div>
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
                        onSelectTweet={() => {}}
                        onSelectQuotedTweet={async () => {}}
                      />
                    ) : etData.tweet ? (
                      <TweetCard tweet={etData.tweet} />
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

