'use server';

interface SearchResult {
  key: string;
  distance: number;
  metadata: {
    text: string;
    username?: string;
    tweet_id?: string;
    // ... other fields
  };
}

export async function searchEmbeddings(searchTerm: string): Promise<SearchResult[]> {
  try {
    const response = await fetch('http://embed.tweetstack.app/embeddings/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        searchTerm,
        k: 20,
        threshold: 0.5
      }),
    });

    if (!response.ok) {
      console.error('Search API error:', await response.text());
      return [];
    }

    const data = await response.json();
    if (data.success && Array.isArray(data.results)) {
      return data.results;
    }
    
    return [];
  } catch (error) {
    console.error('Search action error:', error);
    return [];
  }
}


