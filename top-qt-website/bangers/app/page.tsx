// TODO
/* 
- inspect tweets quoting any given tweet by hovering (get the from the CA)
- about tab explaining what's the CA, what we did (sort by QTs not from the OP), tease next research?, call to action (upload to the CA, install browser extension)
- link previews
*/
import { supabaseTopQt, supabaseCa } from '@/lib/supabase';
import { HomePageClient } from './HomePageClient';

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
  const yearTweets = tweetsByYear.flat();
  
  // Add column field to year-based tweets
  yearTweets.forEach((tweet: Tweet) => {
    tweet.column = String(tweet.year);
  });
  
  console.log(`year tweets: ${yearTweets.length}`);
  console.log(`sample 3 year tweets: ${JSON.stringify(yearTweets.slice(0, 3), null, 2)}`);
  
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
  (lastMonthTweets || []).forEach((tweet: Tweet) => {
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
  (lastWeekTweets || []).forEach((tweet: Tweet) => {
    tweet.column = 'Last Week';
  });
  
  console.log(`last week tweets: ${(lastWeekTweets || []).length}`);
  console.log(`last month tweets: ${(lastMonthTweets || []).length}`);
  
  // Combine all tweets
  const tweets = [...yearTweets, ...(lastMonthTweets || []), ...(lastWeekTweets || [])];
  console.log(`total tweets: ${tweets.length}`);

  // Enrich tweets with media and quoted tweets from Community Archive
  if (tweets.length > 0) {
    const tweetIds = tweets.map((t: Tweet) => t.tweet_id);
    console.log(`tweetIds: ${tweetIds.length}`);
    console.log(`sample 5 tweetIds: ${tweetIds.slice(0, 5)}`);
    // Chunk tweet IDs to respect Supabase's 1000 item limit
    const chunkSize = 500;
    const tweetIdChunks = [];
    for (let i = 0; i < tweetIds.length; i += chunkSize) {
      tweetIdChunks.push(tweetIds.slice(i, i + chunkSize));
    }
    console.log(`tweetIdChunks: ${tweetIdChunks.length}`);
    // Fetch media using joined query in chunks
    const mediaMap = new Map<string, string[]>();
    for (let i = 0; i < tweetIdChunks.length; i++) {
      const chunk = tweetIdChunks[i];
      const { data: tweetsWithMedia, error: mediaError } = await supabaseCa
        .from('tweet_media')
          .select('tweet_id, media_url, media_type')
        .in('tweet_id', chunk);

      if (mediaError) {
        console.error('Error fetching media:', mediaError);
      } else {
        console.log(`Queried ${tweetsWithMedia?.length || 0} media items in chunk ${i} of ${tweetIdChunks.length}, length of chunk: ${chunk.length}`);
        // chunk sample
        console.log(`chunk sample: ${JSON.stringify(chunk.slice(0, 3), null, 2)}`);

        console.log(`tweetsWithMedia: ${JSON.stringify(tweetsWithMedia?.slice(0, 3), null, 2)}`);

        console.log(`mediaMap: ${JSON.stringify(Array.from(mediaMap.entries()), null, 2)}`);
        
        // Add to media map - group all media URLs by tweet_id
        tweetsWithMedia?.forEach((mediaItem: { tweet_id: string; media_url: string; media_type: string }) => {
          if (!mediaMap.has(mediaItem.tweet_id)) {
            mediaMap.set(mediaItem.tweet_id, []);
          }
          mediaMap.get(mediaItem.tweet_id)!.push(mediaItem.media_url);
        });
      }
    }
    console.log(`Found media for ${mediaMap.size} tweets`);

    // Get quote tweet relationships in chunks
    const quoteMap = new Map<string, string>();
    for (const chunk of tweetIdChunks) {
      const { data: quoteTweetRels } = await supabaseCa
        .from('quote_tweets')
        .select('tweet_id, quoted_tweet_id')
        .in('tweet_id', chunk);

      quoteTweetRels?.forEach((qt: { tweet_id: string; quoted_tweet_id: string }) => 
        quoteMap.set(qt.tweet_id, qt.quoted_tweet_id));
    }

    // Fetch quoted tweets
    const quotedTweetIds = Array.from(new Set(Array.from(quoteMap.values()).filter(Boolean)));

    const quotedTweetsMap = new Map<string, Tweet['quoted_tweet']>();
    
    if (quotedTweetIds.length > 0) {
      // Chunk quoted tweet IDs
      const quotedIdChunks = [];
      for (let i = 0; i < quotedTweetIds.length; i += chunkSize) {
        quotedIdChunks.push(quotedTweetIds.slice(i, i + chunkSize));
      }

      type QuotedTweetData = {
        tweet_id: string;
        account_id: string;
        created_at: string;
        full_text: string;
        favorite_count: number;
        retweet_count: number;
        tweet_media: { media_url: string; media_type: string }[];
      };
      const allQuotedData: QuotedTweetData[] = [];
      for (const chunk of quotedIdChunks) {
        const { data: quotedData, error: quotedError } = await supabaseCa
          .from('tweets')
          .select(`
            tweet_id,
            account_id,
            created_at,
            full_text,
            favorite_count,
            retweet_count,
            tweet_media (
              media_url,
              media_type
            )
          `)
          .in('tweet_id', chunk);

        if (quotedError) {
          console.error('Error fetching quoted tweets:', quotedError);
        } else {
          console.log(`Fetched ${quotedData?.length || 0} quoted tweets in chunk`);
          if (quotedData) {
            allQuotedData.push(...quotedData);
          }
        }
      }

      if (allQuotedData.length > 0) {
        // Fetch account data for quoted tweets in chunks
        const accountIds = allQuotedData.map((t: { account_id: string }) => t.account_id).filter(Boolean);
        const accountIdChunks = [];
        for (let i = 0; i < accountIds.length; i += chunkSize) {
          accountIdChunks.push(accountIds.slice(i, i + chunkSize));
        }

        const accountMap = new Map<string, { username: string; account_display_name: string }>();
        for (const chunk of accountIdChunks) {
          const { data: accountData } = await supabaseCa
            .from('all_account')
            .select('account_id, username, account_display_name')
            .in('account_id', chunk);

          accountData?.forEach((a: { account_id: string; username: string; account_display_name: string }) => 
            accountMap.set(a.account_id, a));
        }

        // Fetch profile/avatar data for quoted tweets in chunks
        const profileMap = new Map<string, string>();
        for (const chunk of accountIdChunks) {
          const { data: profileData } = await supabaseCa
            .from('all_profile')
            .select('account_id, avatar_media_url')
            .in('account_id', chunk);

          profileData?.forEach((p: { account_id: string; avatar_media_url: string }) =>   
            profileMap.set(p.account_id, p.avatar_media_url));
        }

        allQuotedData.forEach((qt) => {
          const account = accountMap.get(qt.account_id);
          quotedTweetsMap.set(qt.tweet_id, {
            tweet_id: qt.tweet_id,
            created_at: qt.created_at,
            full_text: qt.full_text,
            username: account?.username || '',
            favorite_count: qt.favorite_count,
            retweet_count: qt.retweet_count,
            avatar_media_url: profileMap.get(qt.account_id),
            media_urls: qt.tweet_media && qt.tweet_media.length > 0 ? qt.tweet_media.map(m => m.media_url) : undefined
          });
        });
      }
    }

    // Add media_urls and quoted_tweet to tweets
    tweets.forEach((tweet: Tweet) => {
      tweet.media_urls = mediaMap.get(tweet.tweet_id);
      const quotedId = quoteMap.get(tweet.tweet_id);
      if (quotedId) {
        tweet.quoted_tweet_id = quotedId;
        tweet.quoted_tweet = quotedTweetsMap.get(quotedId);
      }
    });
  }

  return tweets;
}

async function fetchQuotingTweets(tweetIds: string[]) {
  if (tweetIds.length === 0) return [];

  const chunkSize = 500;
  const tweetIdChunks = [];
  for (let i = 0; i < tweetIds.length; i += chunkSize) {
    tweetIdChunks.push(tweetIds.slice(i, i + chunkSize));
  }

  const quotingTweetIds: string[] = [];
  for (const chunk of tweetIdChunks) {
    const { data: quoteRels } = await supabaseCa
      .from('quote_tweets')
      .select('tweet_id')
      .in('quoted_tweet_id', chunk);

    if (quoteRels) {
      quotingTweetIds.push(...quoteRels.map(q => q.tweet_id));
    }
  }

  if (quotingTweetIds.length === 0) return [];

  const quotingIdChunks = [];
  for (let i = 0; i < quotingTweetIds.length; i += chunkSize) {
    quotingIdChunks.push(quotingTweetIds.slice(i, i + chunkSize));
  }

  type TweetData = {
    tweet_id: string;
    account_id: string;
    created_at: string;
    full_text: string;
    favorite_count: number;
    retweet_count: number;
    tweet_media: { media_url: string; media_type: string }[];
  };

  const allTweets: TweetData[] = [];
  for (const chunk of quotingIdChunks) {
    const { data: tweetsData } = await supabaseCa
      .from('tweets')
      .select(`
        tweet_id,
        account_id,
        created_at,
        full_text,
        favorite_count,
        retweet_count,
        tweet_media (
          media_url,
          media_type
        )
      `)
      .in('tweet_id', chunk);

    if (tweetsData) {
      allTweets.push(...tweetsData);
    }
  }

  if (allTweets.length === 0) return [];

  const accountIds = allTweets.map(t => t.account_id).filter(Boolean);
  const accountIdChunks = [];
  for (let i = 0; i < accountIds.length; i += chunkSize) {
    accountIdChunks.push(accountIds.slice(i, i + chunkSize));
  }

  const accountMap = new Map<string, { username: string; account_display_name: string }>();
  for (const chunk of accountIdChunks) {
    const { data: accountData } = await supabaseCa
      .from('all_account')
      .select('account_id, username, account_display_name')
      .in('account_id', chunk);

    accountData?.forEach(a => accountMap.set(a.account_id, a));
  }

  const profileMap = new Map<string, string>();
  for (const chunk of accountIdChunks) {
    const { data: profileData } = await supabaseCa
      .from('all_profile')
      .select('account_id, avatar_media_url')
      .in('account_id', chunk);

    profileData?.forEach(p => profileMap.set(p.account_id, p.avatar_media_url));
  }

  return allTweets.map(t => {
    const account = accountMap.get(t.account_id);
    return {
      tweet_id: t.tweet_id,
      created_at: t.created_at,
      full_text: t.full_text,
      username: account?.username || '',
      favorite_count: t.favorite_count,
      retweet_count: t.retweet_count,
      avatar_media_url: profileMap.get(t.account_id),
      media_urls: t.tweet_media && t.tweet_media.length > 0 ? t.tweet_media.map(m => m.media_url) : undefined
    };
  });
}

export default async function Home() {
  // Test CA database connection - fetch a single tweet
  const { data: testTweet, error } = await supabaseCa
    .from('tweets')
    .select(`
      tweet_id,
      tweet_media (
        media_url,
        media_type
      )
    `).in('tweet_id', ['1600065172906790912'])
    .limit(1)
    .single();

    

  console.log('CA Database test:');
  console.log('Error:', error);
  console.log('Tweet:', testTweet);

  const tweets = await fetchTweetsByPeriod();
  console.log(`tweets: ${tweets.length}`);
      if (tweets.length > 0) {
        const tweetsWithMedia = tweets.filter((tweet) => tweet.media_urls !== undefined);
        console.log(`Tweets with defined media_urls: ${tweetsWithMedia.length} out of ${tweets.length}`);
      } else {
        console.log('no tweets');
      }

  if (tweets.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No tweets found or error connecting to Supabase.</p>
      </div>
    );
  }
  console.log(`tweets: ${tweets.length}`);
  // sample 5 tweets print fully
  // console.log(`sample 3 tweets: ${JSON.stringify(tweets.slice(0,  3), null, 2)}`);
  return <HomePageClient tweets={tweets} />;
}

