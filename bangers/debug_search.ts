import { fetchTweetDetails } from './lib/api';

// Mocking the search function since it's a server action and we want to run it in isolation 
// or just calling the API directly like the action does.

async function debugSearch() {
  const searchTerm = "psychedelics, meditation";
  console.log(`Searching for: "${searchTerm}"`);

  try {
    const response = await fetch('http://embed.tweetstack.app/embeddings/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        searchTerm,
        k: 5,
        threshold: 0.5
      }),
    });

    if (!response.ok) {
      console.error('Search API error:', await response.text());
      return;
    }

    const data = await response.json();
    if (!data.success || !Array.isArray(data.results)) {
      console.error('Invalid response format', data);
      return;
    }

    const results = data.results;
    console.log(`Found ${results.length} results.`);
    
    if (results.length > 0) {
        console.log('First result structure:', JSON.stringify(results[0], null, 2));
    }

    // Check ID extraction
    const metadataIds = results.map((r: any) => r.metadata?.tweet_id);
    const keyIds = results.map((r: any) => r.key);
    
    console.log('IDs from metadata.tweet_id:', metadataIds);
    console.log('IDs from key:', keyIds);

    // Try to enrich using keys if metadata IDs are missing
    const idsToFetch = (metadataIds[0] ? metadataIds : keyIds).filter(Boolean);
    console.log(`Attempting to fetch details for ${idsToFetch.length} IDs...`);
    
    // We can't easily call lib/api.ts functions here because of environment variables and TS execution context
    // unless we set them up.
    // But checking the IDs above is the most critical step.
    
  } catch (error) {
    console.error('Debug script error:', error);
  }
}

debugSearch();

