import { Tweet } from '@/lib/types';
import { TweetCard } from './TweetCard';
import { useMemo } from 'react';

interface ThreadViewProps {
  tweets: Tweet[];
  focusedTweetId: string;
  onSelectTweet: (tweet: Tweet) => void;
  onSelectQuotedTweet?: (quotedTweetId: string) => void;
}

export const ThreadView = ({ tweets, focusedTweetId, onSelectTweet, onSelectQuotedTweet }: ThreadViewProps) => {
  const { rootIds, childrenMap } = useMemo(() => {
    const childrenMap = new Map<string, string[]>();
    const tweetIds = new Set(tweets.map(t => t.tweet_id));
    const rootIds: string[] = [];

    tweets.forEach(t => {
      const parentId = t.reply_to_tweet_id;
      if (parentId && tweetIds.has(parentId)) {
        const children = childrenMap.get(parentId) || [];
        children.push(t.tweet_id);
        childrenMap.set(parentId, children);
      } else {
        rootIds.push(t.tweet_id);
      }
    });
    
    // Sort roots by date
    rootIds.sort((a, b) => {
       const ta = tweets.find(t => t.tweet_id === a);
       const tb = tweets.find(t => t.tweet_id === b);
       return new Date(ta?.created_at || 0).getTime() - new Date(tb?.created_at || 0).getTime();
    });

    return { rootIds, childrenMap };
  }, [tweets]);

  const renderNode = (tweetId: string, depth: number = 0) => {
    const tweet = tweets.find(t => t.tweet_id === tweetId);
    if (!tweet) return null;
    
    const children = childrenMap.get(tweetId) || [];
    // Sort children by date
    children.sort((a, b) => {
       const ta = tweets.find(t => t.tweet_id === a);
       const tb = tweets.find(t => t.tweet_id === b);
       return new Date(ta?.created_at || 0).getTime() - new Date(tb?.created_at || 0).getTime();
    });

    const isFocused = tweetId === focusedTweetId;

    return (
      <div key={tweetId} className="flex flex-col relative">
        <div className="flex gap-2">
             {/* Thread line visual */}
             {depth > 0 && (
                 <div className="flex-shrink-0 w-6 flex justify-center">
                      <div className="w-px bg-gray-300 h-full"></div>
                 </div>
             )}
             
             <div 
               className={`flex-1 cursor-pointer transition-colors ${isFocused ? 'ring-2 ring-blue-500 rounded p-1' : ''}`} 
               style={{ maxWidth: '360px' }} 
               onClick={(e) => {
                 e.stopPropagation();
                 onSelectTweet(tweet);
               }}
             >
                <TweetCard 
                  tweet={tweet} 
                  onQuotedTweetClick={onSelectQuotedTweet}
                />
             </div>
        </div>

        <div className={`${depth > 0 ? 'pl-8' : ''}`}>
             {children.map(childId => renderNode(childId, depth + 1))}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4 pb-20">
      {rootIds.map(rootId => renderNode(rootId))}
    </div>
  );
};
