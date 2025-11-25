// TODO
/* 
- scroll columns independently DONE
- render images
- columns for last month and last week DONE
- link previews
- about tab explaining what's the CA, what we did (sort by QTs not from the OP), tease next research?, call to action (upload to the CA, install browser extension)
- render QTs by looking quoted tweet from CA 
- inspect tweets quoting any given tweet by hovering (get the from the CA)
*/
import { supabaseTopQt, supabaseCa } from '@/lib/supabase';
import { HomePageClient } from './HomePageClient';
import { Tweet } from '@/lib/types';

async function fetchTweetsByPeriod() {
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
  
  // Add column field to year-based tweets
  tweets.forEach((tweet: any) => {
    tweet.column = String(tweet.year);
  });
  
  // Calculate date ranges
  const now = new Date();
  const lastWeekDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const lastMonthDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  
  // Fetch last month tweets
  const { data: lastMonthTweets } = await supabaseTopQt
    .from('community_archive_tweets')
    .select('*')
    .gte('created_at', lastMonthDate.toISOString())
    .order('quote_count', { ascending: false })
    .limit(100);
  
  // Add column field to last month tweets
  (lastMonthTweets || []).forEach((tweet: any) => {
    tweet.column = 'Last Month';
  });
  
  // Fetch last week tweets
  const { data: lastWeekTweets } = await supabaseTopQt
    .from('community_archive_tweets')
    .select('*')
    .gte('created_at', lastWeekDate.toISOString())
    .order('quote_count', { ascending: false })
    .limit(100);
  
  // Add column field to last week tweets
  (lastWeekTweets || []).forEach((tweet: any) => {
    tweet.column = 'Last Week';
  });
  
  // Combine all tweets
  const allTweets = [...tweets, ...(lastMonthTweets || []), ...(lastWeekTweets || [])];

  // Fetch media for all tweets from Community Archive
  if (allTweets.length > 0) {
    const tweetIds = allTweets.map((t: any) => String(t.tweet_id));
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

    // Add media_url to ALL tweet arrays
    allTweets.forEach((tweet: any) => {
      // Convert IDs to string
      tweet.tweet_id = String(tweet.tweet_id);
      if (tweet.quoted_tweet_id) tweet.quoted_tweet_id = String(tweet.quoted_tweet_id);
      if (tweet.conversation_id) tweet.conversation_id = String(tweet.conversation_id);
      
      const mediaUrl = mediaMap.get(tweet.tweet_id);
      if (mediaUrl) {
         if (!tweet.media_urls) tweet.media_urls = [];
         tweet.media_urls.push(mediaUrl);
      }
    });
  }

  return allTweets as Tweet[];
}

export default async function Home() {
  const tweets = await fetchTweetsByPeriod();

  if (tweets.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No tweets found or error connecting to Supabase.</p>
      </div>
    );
  }

  return <HomePageClient tweets={tweets} />;
}
