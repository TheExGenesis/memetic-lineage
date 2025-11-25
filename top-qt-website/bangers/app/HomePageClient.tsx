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
}

export const HomePageClient = ({ tweets }: { tweets: Tweet[] }) => {
  // Group tweets by year
  const groups: Record<number, Tweet[]> = {};
  tweets.forEach((tweet: Tweet) => {
    if (!groups[tweet.year]) {
      groups[tweet.year] = [];
    }
    groups[tweet.year].push(tweet);
  });
  // print random sample of tweets
  console.log(`random sample of tweets: ${tweets.slice(0, 25).map(tweet => tweet.created_at).join('\n')}`);

  // Sort years descending
  const tweetsByYear = Object.keys(groups).sort((a, b) => Number(b) - Number(a)).map(year => ({
    year: Number(year),
    tweets: groups[Number(year)]
  }));

  console.log(`tweetsByYear: ${tweetsByYear.map(year => year.year).join(', ')}`);
  return (
    <div className="h-screen flex flex-col p-8 bg-white text-black overflow-hidden">
      <header className="mb-8 border-b-4 border-black pb-4 flex-shrink-0">
        <h1 className="text-6xl font-bold tracking-tighter">bangers</h1>
        <p className="text-xl italic mt-2">of the Community Archive</p>
      </header>

      <main className="flex gap-8 overflow-x-auto flex-1 scrollbar-hide">
        {tweetsByYear.map(({ year, tweets }) => (
          <section key={year} className="flex flex-col flex-shrink-0 w-[360px]">
            <h2 className="text-4xl font-bold mb-6 border-b-2 border-black pb-2 flex-shrink-0">
              {year}
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

