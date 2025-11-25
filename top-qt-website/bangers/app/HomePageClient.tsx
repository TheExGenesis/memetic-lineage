'use client';

import { TweetCard } from './TweetCard';

interface Tweet {
  tweet_id: string;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count: number;
  year: number;
  quoted_tweet_id?: string;
  avatar_media_url?: string;
  conversation_id?: string;
  media_urls?: string[];
  column: string;
  quoted_tweet?: {
    tweet_id: string;
    created_at: string;
    full_text: string;
    username: string;
    favorite_count: number;
    retweet_count: number;
    avatar_media_url?: string;
    media_urls?: string[];
  };
}

export const HomePageClient = ({ tweets }: { tweets: Tweet[] }) => {
  // Group tweets by column
  const groups: Record<string, Tweet[]> = {};
  tweets.forEach((tweet: Tweet) => {
    if (!groups[tweet.column]) {
      groups[tweet.column] = [];
    }
    groups[tweet.column].push(tweet);
  });

  // Custom sort function that handles both numeric years and string labels
  const sortColumns = (a: string, b: string) => {
    const aNum = Number(a);
    const bNum = Number(b);
    
    if (!isNaN(aNum) && !isNaN(bNum)) {
      return bNum - aNum; // Descending order for years
    }
    
    // Handle special string columns
    const order = ['Last Week', 'Last Month'];
    const aIndex = order.indexOf(a);
    const bIndex = order.indexOf(b);
    
    // If both are in the order array, sort by their position
    if (aIndex !== -1 && bIndex !== -1) {
      return aIndex - bIndex;
    }
    
    // If only one is in the order array, it comes first
    if (aIndex !== -1) return -1;
    if (bIndex !== -1) return 1;
    
    // Otherwise, alphabetical sort
    return a.localeCompare(b);
  };

  const tweetsByColumn = Object.keys(groups).sort(sortColumns).map(column => ({
    column: column,
    tweets: groups[column]
  }));

  console.log(`tweetsByColumn: ${tweetsByColumn.map(c => c.column).join(', ')}`);
  
  return (
    <div className="h-screen flex flex-col p-8 bg-white text-black overflow-hidden">
      <header className="mb-8 border-b-4 border-black pb-4 flex-shrink-0">
        <h1 className="text-6xl font-bold tracking-tighter">bangers</h1>
        <p className="text-xl italic mt-2">from the Community Archive</p>
      </header>
      <main className="flex gap-8 overflow-x-auto flex-1 scrollbar-hide">
        {tweetsByColumn.map(({ column, tweets }) => (
          <section key={column} className="flex flex-col flex-shrink-0 w-[360px]">
            <h2 className="text-4xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
              {column}
            </h2>
            <div className="flex flex-col gap-2 overflow-y-auto flex-1 scrollbar-hide">
              {tweets.map(tweet => (
                <TweetCard key={tweet.tweet_id} tweet={tweet} />
              ))}
            </div>
          </section>
        ))}
        
        <section className="flex flex-col flex-shrink-0 w-[360px]">
          <h2 className="text-4xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
            About
          </h2>
          <div className="flex flex-col gap-6 overflow-y-auto flex-1 scrollbar-hide text-base leading-relaxed">
            <div>
              <h3 className="font-bold text-lg mb-2">The Community Archive</h3>
              <p>
                The Community Archive is a crowdsourced database of Twitter history. 
                Over 1 billion tweets from 2006-2024, preserved by the community, for the community.
              </p>
            </div>
            
            <div>
              <h3 className="font-bold text-lg mb-2">How We Selected These</h3>
              <p>
                These are the most quoted tweets—but with a twist. We ranked by quote tweets 
                <em> not from the original poster</em>, revealing which tweets sparked the most 
                independent conversation.
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
                {' '}to contribute your Twitter data.
              </p>
              <p>
                <strong>Auto-archive tweets:</strong> Install the{' '}
                <a 
                  href="https://chromewebstore.google.com/detail/community-archive/mjahlpgldaddoigfghcepfpeilkhjhma" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="underline font-semibold hover:opacity-70"
                >
                  browser extension
                </a>
                {' '}to save tweets as you browse.
              </p>
            </div>
          </div>
        </section>
      </main>
      
      <style jsx>{`
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

