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
  const [threadTweets, setThreadTweets] = useState<Tweet[]>([]);
  const [quoteTweets, setQuoteTweets] = useState<Tweet[]>([]);
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      if (activeTab === 'thread') {
        let convId = tweet.conversation_id;
        
        if (!convId) {
           // Fix type mismatch: getConversationId returns string | null, but convId expects string | undefined
           const id = await getConversationId(tweet.tweet_id);
           convId = id || undefined;
        }
        
        if (convId) {
            const data = await getThread(convId);
            setThreadTweets(data);
        } else {
            // Fallback: just show this tweet as thread if no conversation found
            setThreadTweets([tweet]);
        }
      } else if (activeTab === 'qts') {
        const data = await getQuotes(tweet.tweet_id);
        setQuoteTweets(data);
      } else if (activeTab === 'vector search') {
        // Perform vector search using the tweet's text
        const results = await searchEmbeddings(tweet.full_text, tweet.tweet_id);
        setSearchResults(results);
      }
      setLoading(false);
    };

    loadData();
  }, [activeTab, tweet]);

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
         </div>

         {loading ? (
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
                 {quoteTweets.length === 0 ? (
                   <div className="text-gray-500 italic text-center mt-4">No quote tweets found.</div>
                 ) : (
                   quoteTweets.map(qt => (
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
