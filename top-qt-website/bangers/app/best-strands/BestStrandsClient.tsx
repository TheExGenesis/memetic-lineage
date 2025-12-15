'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { StrandWithTweet, Tweet } from '@/lib/types';
import { StrandDetail } from './StrandDetail';
import { TweetPane } from '../TweetPane';
import { VerticalSpine } from '../VerticalSpine';

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

const getLevelBadge = (level: 'high' | 'medium' | 'low') => {
  switch (level) {
    case 'high':
      return 'bg-emerald-100 text-emerald-700';
    case 'medium':
      return 'bg-amber-100 text-amber-700';
    case 'low':
      return 'bg-slate-100 text-slate-600';
  }
};

export function BestStrandsClient({ strands }: BestStrandsClientProps) {
  const [selectedStrand, setSelectedStrand] = useState<StrandWithTweet | null>(null);
  const [selectedTweets, setSelectedTweets] = useState<Tweet[]>([]);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

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

  const handleTweetClick = useCallback((tweet: Tweet, depth: number) => {
    const newStack = depth === -1 ? [] : selectedTweets.slice(0, depth + 1);
    newStack.push(tweet);
    setSelectedTweets(newStack);
  }, [selectedTweets]);

  const handleClosePane = useCallback((index: number) => {
    setSelectedTweets(selectedTweets.slice(0, index));
  }, [selectedTweets]);

  const handleSpineClick = useCallback((index: number) => {
    const newStack = index === -1 ? [] : selectedTweets.slice(0, index + 1);
    setSelectedTweets(newStack);
  }, [selectedTweets]);

  const handleBackFromStrand = useCallback(() => {
    setSelectedStrand(null);
    setSelectedTweets([]);
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
          <div className="flex items-center gap-4 mb-2">
            <a
              href="/"
              className="p-2 hover:bg-gray-100 transition-colors border border-transparent hover:border-black"
              title="Back to home"
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
            </a>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Best Strands</h1>
              <p className="text-sm text-gray-600">
                Curated conversation strands, rated by evolution, cohesion, and utility
              </p>
            </div>
          </div>
        </header>

        <div className="mb-4 bg-blue-50 border border-blue-200 rounded px-4 py-2 text-sm text-blue-800">
          <span className="font-semibold">Note:</span> Data is from a static snapshot taken in early December 2025.
          Strand ratings are generated by AI analysis of conversation threads.
        </div>

        <div className="bg-white border-2 border-black shadow-[4px_4px_0_0_#000]">
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-black bg-gray-100">
                <th className="text-left p-4 font-bold text-sm uppercase tracking-wide">Seed Tweet</th>
                <th className="text-left p-4 font-bold text-sm uppercase tracking-wide">Summary</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-20">Rating</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-24">Evolution</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-24">Cohesion</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-24">Utility</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-28">Date</th>
                <th className="text-center p-4 font-bold text-sm uppercase tracking-wide w-24">Seeds</th>
              </tr>
            </thead>
            <tbody>
              {strands.map((strand, idx) => {
                const seedTweet = strand.seedTweet;
                const tweetPreview = seedTweet
                  ? seedTweet.full_text.slice(0, 100) + (seedTweet.full_text.length > 100 ? '...' : '')
                  : 'Tweet not found';
                const summaryPreview = strand.rating.reasoning_summary.slice(0, 120) +
                  (strand.rating.reasoning_summary.length > 120 ? '...' : '');

                return (
                  <tr
                    key={strand.seed_tweet_id}
                    onClick={() => setSelectedStrand(strand)}
                    className={`border-b border-gray-200 cursor-pointer transition-colors hover:bg-yellow-50 ${
                      idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'
                    }`}
                  >
                    <td className="p-4">
                      <div className="max-w-xs">
                        {seedTweet && (
                          <div className="flex items-center gap-2 mb-1">
                            {seedTweet.avatar_media_url && (
                              <img
                                src={seedTweet.avatar_media_url}
                                alt={seedTweet.username}
                                className="w-5 h-5 rounded-full"
                              />
                            )}
                            <span className="font-bold text-xs">@{seedTweet.username}</span>
                          </div>
                        )}
                        <p className="text-sm text-gray-700 line-clamp-2">{tweetPreview}</p>
                      </div>
                    </td>
                    <td className="p-4">
                      <p className="text-sm text-gray-600 line-clamp-2">{summaryPreview}</p>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-block px-3 py-1 text-lg font-bold border ${getRatingColor(strand.rating.rating)}`}>
                        {strand.rating.rating}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-block px-2 py-1 text-xs font-semibold uppercase rounded ${getLevelBadge(strand.rating.evolution)}`}>
                        {strand.rating.evolution}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-block px-2 py-1 text-xs font-semibold uppercase rounded ${getLevelBadge(strand.rating.cohesion)}`}>
                        {strand.rating.cohesion}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-block px-2 py-1 text-xs font-semibold uppercase rounded ${getLevelBadge(strand.rating.utility)}`}>
                        {strand.rating.utility}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className="text-sm font-mono text-gray-600">
                        {formatDate(seedTweet?.created_at)}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className="text-sm font-mono text-gray-600">
                        {strand.seeds?.length || 0}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-8 text-center text-sm text-gray-500">
          {strands.length} strands curated from the Community Archive
        </div>
      </div>
    </div>
  );
}
