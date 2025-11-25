// TODO
/* 
- scroll columns independently
- render images
- columns for last month and last week
- link previews
- about tab explaining what's the CA, what we did (sort by QTs not from the OP), tease next research?, call to action (upload to the CA, install browser extension)
- render QTs by looking quoted tweet from CA 
- inspect tweets quoting any given tweet by hovering (get the from the CA)
*/
import { supabaseTopQt, supabaseCa } from '@/lib/supabase';
import { HomePageClient } from './HomePageClient';

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


async function fetchTweetsByYear() {
  // Get min and max year
  const { data: minYearData, error: yearError } = await supabaseTopQt
    .from('community_archive_tweets')
    .select('year')
    .order('year', { ascending: true })
    .limit(1)
    .single();

  const { data: maxYearData, error: maxYearError } = await supabaseTopQt
    .from('community_archive_tweets')
    .select('year')
    .order('year', { ascending: false })
    .limit(1)
    .single();

  if (yearError || maxYearError || !minYearData || !maxYearData) {
    console.error('Error fetching year range:', yearError || maxYearError);
    return [];
  }

  const minYear = minYearData.year;
  const maxYear = maxYearData.year;

  // Generate array of all years
  const years = [];
  for (let year = maxYear; year >= minYear; year--) {
    years.push(year);
  }

  // Fetch top 100 tweets for each year
  const tweetsByYearPromises = years.map(async (year) => {
    const { data, error } = await supabaseTopQt
      .from('community_archive_tweets')
      .select('*')
      .eq('year', year)
      .order('quote_count', { ascending: false })
      .limit(100);

    if (error) {
      console.error(`Error fetching tweets for year ${year}:`, error);
      return [];
    }

    return data || [];
  });

  const tweetsByYear = await Promise.all(tweetsByYearPromises);
  const tweets = tweetsByYear.flat();

  // Fetch media for all tweets from Community Archive
  if (tweets.length > 0) {
    const tweetIds = tweets.map((t: Tweet) => String(t.tweet_id));
    const { data: mediaData } = await supabaseCa
      .from('tweet_media')
      .select('tweet_id, media_url')
      .in('tweet_id', tweetIds);

    // Create a map of tweet_id to first media_url
    const mediaMap = new Map<string, string>();
    mediaData?.forEach((m: { tweet_id: string; media_url: string }) => {
      if (!mediaMap.has(m.tweet_id)) {
        mediaMap.set(m.tweet_id, m.media_url);
      }
    });

    // Add media_url to tweets
    tweets.forEach((tweet: Tweet) => {
      tweet.media_url = mediaMap.get(String(tweet.tweet_id));
    });
  }

  return tweets;
}

export default async function Home() {
  const tweets = await fetchTweetsByYear();

  if (tweets.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No tweets found or error connecting to Supabase.</p>
      </div>
    );
  }

  return <HomePageClient tweets={tweets} />;
}

