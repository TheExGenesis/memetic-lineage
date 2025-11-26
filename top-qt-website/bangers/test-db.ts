import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

// Load env vars from .env.local
dotenv.config({ path: '.env.local' });

const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL;
const caKey = process.env.NEXT_PUBLIC_SUPABASE_KEY;

if (!caUrl || !caKey) {
    console.error('Missing env vars');
    process.exit(1);
}

const supabaseCa = createClient(caUrl, caKey);

async function testFetch() {
    const TEST_ID = '1742494880625016921';
    console.log(`Testing with Tweet ID: ${TEST_ID}`);
    
    // 1. Check conversations table for this specific tweet
    const { data: convData, error: convError } = await supabaseCa
        .from('conversations')
        .select('*')
        .eq('tweet_id', TEST_ID);
        
    if (convError) {
        console.error('Error fetching from conversations table:', convError);
    } else {
        console.log('Conversations table result:', convData);
        if (convData && convData.length > 0) {
            const convId = convData[0].conversation_id;
            console.log(`Found conversation_id: ${convId}`);
            
             // Get all tweet_ids in this conversation
            const { data: threadIds, error: threadIdsError } = await supabaseCa
                .from('conversations')
                .select('tweet_id')
                .eq('conversation_id', convId);

            if (threadIdsError) {
                 console.error('Error fetching thread IDs:', threadIdsError);
            } else {
                 console.log(`Found ${threadIds.length} tweets in conversation.`);
                 const ids = threadIds.map(t => t.tweet_id);
                 
                 // Fetch details
                 const { data: threadTweets, error: threadTweetsError } = await supabaseCa
                    .from('tweets')
                    .select('tweet_id, full_text, created_at, reply_to_tweet_id, reply_to_user_id, reply_to_username, account_id')
                    .in('tweet_id', ids)
                    .order('created_at');
                    
                 if (threadTweetsError) {
                     console.error('Error fetching thread tweets:', threadTweetsError);
                 } else {
                     console.log('Thread structure:');
                     threadTweets.forEach(t => {
                         console.log(`- [${t.tweet_id}] (reply_to: ${t.reply_to_tweet_id}) ${t.full_text.slice(0, 50)}...`);
                     });
                 }
            }
        } else {
            console.log('No conversation_id found for this tweet.');
        }
    }

    // 2. Check for Quote Tweets
    console.log('\nChecking for quotes of this tweet...');
    const { data: quotesData, error: quotesError } = await supabaseCa
        .from('quote_tweets')
        .select('*')
        .eq('quoted_tweet_id', TEST_ID);
        
    if (quotesError) {
        console.error('Error fetching quote_tweets:', quotesError);
    } else {
        console.log(`Found ${quotesData?.length || 0} quotes:`, quotesData);
    }
}

testFetch();
