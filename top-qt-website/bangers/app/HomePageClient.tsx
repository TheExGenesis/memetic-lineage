'use client';

import { TweetCard } from './TweetCard';

interface Tweet {
  tweet_id: number;
  created_at: string;
  full_text: string;
  username: string;
  favorite_count: number;
  retweet_count: number;
  quote_count: number;
  year: number;
  quoted_tweet_id?: number;
  avatar_media_url?: string;
  conversation_id?: number;
  media_url?: string;
  column: string; 
}

export const HomePageClient = ({ tweets }: { tweets: Tweet[] }) => {
  // Group tweets by year
  const groups: Record<string, Tweet[]> = {};
  tweets.forEach((tweet: Tweet) => {
    if (!groups[tweet.column]) {
      groups[tweet.column] = [];
    }
    groups[tweet.column].push(tweet);
  });
  // print random sample of tweets
  console.log(`random sample of tweets: ${tweets.slice(0, 25).map(tweet => tweet.created_at).join('\n')}`);

  // Custom sort function that handles both numeric years and string labels
  const sortColumns = (a: string, b: string) => {
    // Check if both are numeric years
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
  // Sort years descending
  const tweetsByYear = Object.keys(groups).sort(sortColumns).map(column => ({
    column: column,
    tweets: groups[column]
  }));
  // Reverse the order to show oldest tweets on the left

  console.log(`tweetsByYear: ${tweetsByYear.map(year => year.column).join(', ')}`);
  return (
    <div className="h-screen flex flex-col p-8 bg-white text-black overflow-hidden">
      <header className="mb-8 border-b-4 border-black pb-4 flex-shrink-0">
        <h1 className="text-6xl font-bold tracking-tighter">bangers</h1>
        <p className="text-xl italic mt-2">from the Community Archive</p>
      </header>


      <main className="flex gap-8 overflow-x-auto flex-1 scrollbar-hide">
        {tweetsByYear.map(({ column, tweets }) => (
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

