'use client';

import { useState, useEffect } from 'react';
import { Tweet } from '@/lib/types';
import { TweetCard } from './TweetCard';
import { ThreadView } from './ThreadView';
import { getThread, getQuotes, getConversationId, fetchTweetDetails } from '@/lib/api';
import { searchEmbeddings, SemanticSearchResult } from '@/app/actions/search';

interface TweetPaneProps {
  tweet: Tweet;
  onClose: () => void;
  onSelectTweet: (tweet: Tweet) => void;
}

export const TweetPane = ({ tweet, onClose, onSelectTweet }: TweetPaneProps) => {
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
  const [activeTab, setActiveTab] = useState<'qts' | 'thread' | 'vector search'>('thread');
  const [quoteSort, setQuoteSort] = useState<'likes' | 'retweets' | 'date_desc' | 'date_asc'>('likes');
  const [threadTweets, setThreadTweets] = useState<Tweet[]>([]);
  const [quoteTweets, setQuoteTweets] = useState<Tweet[]>([]);
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [initialTabSet, setInitialTabSet] = useState(false);

  // Load thread data on mount to determine default tab
  useEffect(() => {
    const loadInitialThread = async () => {
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
      
      // If thread is empty or only contains the focused tweet, default to QTs
      if (data.length <= 1) {
        setActiveTab('qts');
      }
      setInitialTabSet(true);
    };

    loadInitialThread();
  }, [tweet]);

  // Load data when tab changes
  useEffect(() => {
    if (!initialTabSet) return;

    const loadData = async () => {
      setLoading(true);
      if (activeTab === 'thread') {
        // Thread already loaded in initial effect
      } else if (activeTab === 'qts') {
        const data = await getQuotes(tweet.tweet_id);
        setQuoteTweets(data);
      } else if (activeTab === 'vector search') {
        const results = await searchEmbeddings(tweet.full_text, tweet.tweet_id);
        setSearchResults(results);
      }
      setLoading(false);
    };

    loadData();
  }, [activeTab, tweet, initialTabSet]);

  return (
    // Removed fixed width w-[500px], added w-full h-full to fill parent container
    <div className="flex flex-col w-full h-full border-r border-black bg-white flex-shrink-0 shadow-xl">
      {/* Header / Tabs */}
      <div className="flex border-b border-black sticky top-0 bg-white z-10">
        {['qts', 'thread', 'vector search'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab as any)}
            className={`flex-1 py-3 text-sm font-bold text-center uppercase border-r last:border-r-0 border-black transition-colors ${
              activeTab === tab ? 'bg-black text-white' : 'hover:bg-gray-100'
            }`}
          >
            {tab}
          </button>
        ))}
        <button 
          onClick={onClose} 
          className="px-4 border-l border-black hover:bg-red-500 hover:text-white transition-colors"
          aria-label="Close pane"
        >
           ✕
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
         <div className="mb-6 border-b-4 border-black pb-6">
            <div style={{ maxWidth: '360px' }}>
               <TweetCard 
                 tweet={tweet} 
                 onQuotedTweetClick={handleQuotedTweetSelect}
               />
            </div>
            <a
              href={`/multi-thread-visualizer?seed=${tweet.tweet_id}`}
              className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-black text-white text-sm font-bold uppercase tracking-wide hover:bg-gray-800 transition-colors"
              onClick={(e) => e.stopPropagation()}
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
                <path d="M6 3v12" />
                <circle cx="18" cy="6" r="3" />
                <circle cx="6" cy="18" r="3" />
                <path d="M18 9a9 9 0 0 1-9 9" />
              </svg>
              Explore Strand
            </a>
         </div>

         {!initialTabSet || loading ? (
           <div className="p-8 text-center text-gray-500 animate-pulse">Loading...</div>
         ) : (
           <>
             {activeTab === 'thread' && (
               <ThreadView 
                 tweets={threadTweets} 
                 focusedTweetId={tweet.tweet_id} 
                 onSelectTweet={onSelectTweet} 
                 onSelectQuotedTweet={handleQuotedTweetSelect}
               />
             )}
             
             {activeTab === 'qts' && (
               <div className="flex flex-col gap-4">
                 <div className="flex flex-col gap-2 max-w-[360px]">
                   <label className="text-xs uppercase font-semibold text-gray-500">Order quotes</label>
                   <select
                     value={quoteSort}
                     onChange={(e) => setQuoteSort(e.target.value as typeof quoteSort)}
                     className="border border-black px-3 py-2 text-sm uppercase font-semibold focus:outline-none focus:ring-2 focus:ring-black"
                   >
                     <option value="likes">Likes (desc)</option>
                     <option value="retweets">Retweets (desc)</option>
                     <option value="date_desc">Date (newest first)</option>
                     <option value="date_asc">Date (oldest first)</option>
                   </select>
                 </div>
                 {quoteTweets.length === 0 ? (
                   <div className="text-gray-500 italic text-center mt-4">No quote tweets found.</div>
                 ) : (
                   [...quoteTweets]
                     .sort((a, b) => {
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
                     })
                     .map((qt) => (
                       <div 
                          key={qt.tweet_id} 
                          onClick={() => onSelectTweet(qt)} 
                          className="cursor-pointer transition-opacity hover:opacity-80"
                          style={{ maxWidth: '360px' }}
                       >
                          <TweetCard 
                            tweet={qt} 
                            onQuotedTweetClick={handleQuotedTweetSelect}
                          />
                       </div>
                     ))
                 )}
               </div>
             )}

             {activeTab === 'vector search' && (
               <div className="flex flex-col gap-4">
                 {searchResults.length === 0 ? (
                   <div className="text-gray-500 italic text-center mt-4">No similar tweets found.</div>
                 ) : (
                   searchResults.map((result) => {
                     return (
                       <div 
                          key={result.key} 
                          onClick={() => onSelectTweet(result.tweet)} 
                          className="cursor-pointer transition-opacity hover:opacity-80"
                          style={{ maxWidth: '360px' }}
                       >
                          <div className="text-xs text-gray-400 mb-1 text-right">
                            Similarity: {(result.distance * 100).toFixed(1)}%
                          </div>
                          <TweetCard 
                            tweet={result.tweet} 
                            onQuotedTweetClick={handleQuotedTweetSelect}
                          />
                       </div>
                     );
                   })
                 )}
               </div>
             )}
           </>
         )}
      </div>
    </div>
  );
};
