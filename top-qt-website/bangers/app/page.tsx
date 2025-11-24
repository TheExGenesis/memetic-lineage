import { supabase } from '@/lib/supabase';

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
}

export const revalidate = 3600; // Revalidate every hour

const TweetCard = ({ tweet }: { tweet: Tweet }) => {
  return (
    <div className="border-b border-black pb-4 mb-4 last:border-b-0 break-inside-avoid">
      <div className="flex items-start gap-3 mb-2">
        <div className="w-8 h-8 bg-gray-200 rounded-full overflow-hidden flex-shrink-0 border border-black">
          {tweet.avatar_media_url && (
            <img src={tweet.avatar_media_url} alt={tweet.username} className="w-full h-full object-cover" />
          )}
        </div>
        <div>
          <div className="font-bold text-sm">@{tweet.username}</div>
          <div className="text-xs text-gray-600">{new Date(tweet.created_at).toLocaleDateString()}</div>
        </div>
      </div>
      <p className="text-sm leading-relaxed mb-3">{tweet.full_text}</p>
      <div className="flex gap-4 text-xs text-gray-500 font-mono">
        <span>♥ {tweet.favorite_count}</span>
        <span>↻ {tweet.retweet_count}</span>
        <span>❝ {tweet.quote_count}</span>
      </div>
    </div>
  );
};

export default async function Home() {
  const { data: tweets, error } = await supabase
    .from('community_archive_tweets')
    .select('*')
    .order('year', { ascending: false })
    .order('favorite_count', { ascending: false });

  if (error) {
    console.error('Supabase Error:', error);
  }

  if (!tweets) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No tweets found or error connecting to Supabase.</p>
      </div>
    );
  }

  // Group tweets by year
  const groups: Record<number, Tweet[]> = {};
  tweets.forEach((tweet: Tweet) => {
    if (!groups[tweet.year]) {
      groups[tweet.year] = [];
    }
    groups[tweet.year].push(tweet);
  });
  
  // Sort years descending
  const tweetsByYear = Object.keys(groups).sort((a, b) => Number(b) - Number(a)).map(year => ({
    year: Number(year),
    tweets: groups[Number(year)]
  }));

  return (
    <div className="min-h-screen p-8 bg-white text-black">
      <header className="mb-12 border-b-4 border-black pb-4">
        <h1 className="text-6xl font-bold tracking-tighter">bangers</h1>
        <p className="text-xl italic mt-2">of the Community Archive</p>
      </header>

      <main className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {tweetsByYear.map(({ year, tweets }) => (
          <section key={year} className="flex flex-col">
            <h2 className="text-4xl font-bold mb-6 border-b-2 border-black pb-2 sticky top-0 bg-white z-10">
              {year}
            </h2>
            <div className="flex flex-col gap-2">
              {tweets.map(tweet => (
                <TweetCard key={tweet.tweet_id} tweet={tweet} />
              ))}
            </div>
          </section>
        ))}
      </main>
      
      <footer className="mt-20 py-8 border-t border-black text-center text-sm">
        <p>© {new Date().getFullYear()} Bangers Archive. All rights reserved.</p>
      </footer>
    </div>
  );
}
