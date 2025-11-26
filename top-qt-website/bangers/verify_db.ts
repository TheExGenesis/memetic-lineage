import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

// Load env vars from .env.local
dotenv.config({ path: '.env.local' });

const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL;
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_ANON_KEY;

if (!caUrl || !caKey) {
    console.error('Missing env vars');
    process.exit(1);
}

const supabaseCa = createClient(caUrl, caKey);

async function verifyTweetData() {
    // Use the ID from the screenshot (visakanv tweet)
    // We need to find the ID. The screenshot shows date 2025-10-26 which seems futuristic or misparsed?
    // Wait, the user provided ID 1742494880625016921 in previous turn.
    // But the screenshot shows @visakanv. 
    // Let's try to find the tweet from the text in the screenshot if possible, or use the previous ID.
    // Text: "as i spend more time away from the internet"
    
    console.log('Searching for tweet by text content...');
    const { data: searchData, error: searchError } = await supabaseCa
        .from('tweets')
        .select('tweet_id, full_text, conversation_id')
        .ilike('full_text', '%as i spend more time away from the internet%')
        .limit(1);

    let targetId = '1742494880625016921'; // Default to the one we tested before if search fails
    
    if (searchData && searchData.length > 0) {
        console.log('Found tweet from screenshot:', searchData[0]);
        targetId = searchData[0].tweet_id;
    } else {
        console.log('Could not find tweet by text, using fallback ID:', targetId);
    }

    console.log(`\n--- TESTING ID: ${targetId} ---`);

    // 1. Check Conversations Table
    console.log('1. Querying conversations table...');
    const { data: convData, error: convError } = await supabaseCa
        .from('conversations')
        .select('*')
        .eq('tweet_id', targetId);
        
    if (convError) console.error('Conversations Error:', convError);
    else console.log('Conversations Data:', convData);

    // 2. Check Quote Tweets Table
    console.log('\n2. Querying quote_tweets table...');
    const { data: quotesData, error: quotesError } = await supabaseCa
        .from('quote_tweets')
        .select('*')
        .eq('quoted_tweet_id', targetId);

    if (quotesError) console.error('Quotes Error:', quotesError);
    else console.log('Quotes Data:', quotesData);
    
    // 3. Check Permissions / RLS on 'tweets' table
    console.log('\n3. Querying tweets table directly...');
    const { data: tweetData, error: tweetError } = await supabaseCa
        .from('tweets')
        .select('*')
        .eq('tweet_id', targetId);
        
    if (tweetError) console.error('Tweets Error:', tweetError);
    else console.log('Tweets Data found:', tweetData?.length);
}

verifyTweetData();

