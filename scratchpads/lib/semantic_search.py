# %%
from typing import TypedDict, Optional, List
import requests


class RawSearchResultMetadata(TypedDict, total=False):
    text: str
    username: Optional[str]
    tweet_id: Optional[str]
    created_at: Optional[str]
    favorite_count: Optional[int]
    retweet_count: Optional[int]
    avatar_media_url: Optional[str]


class RawSearchResult(TypedDict):
    key: str
    distance: float
    metadata: RawSearchResultMetadata


class SemanticSearchResult(TypedDict):
    key: str
    distance: float
    metadata: RawSearchResultMetadata


def search_embeddings(
    search_term: str,
    k: int = 100,
    threshold: float = 0.5,
    exclude_tweet_id: Optional[str] = None,
    filter: Optional[dict] = None
) -> List[SemanticSearchResult]:
    """Search embeddings for semantically similar tweets.
    
    Args:
        search_term: Text to search for
        k: Number of results to return (default 100)
        threshold: Distance threshold (default 0.5)
        exclude_tweet_id: Optional tweet ID to exclude from results
        filter: Optional Qdrant-style filter object with must/should/must_not clauses
                Example: {
                    "must": [...],      # AND - all conditions must match
                    "should": [...],    # OR - at least one condition must match
                    "must_not": [...]   # NOT - none of the conditions must match
                }
        
    Returns:
        List of search results with key, distance, and metadata
    """
    url = 'http://embed.tweetstack.app/embeddings/search'
    
    payload = {
        'searchTerm': search_term,
        'k': k,
        'threshold': threshold
    }
    
    if filter is not None:
        payload['filter'] = filter
    
    response = requests.post(
        url,
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    if not response.ok:
        print(f'Search API error: {response.text}')
        return []
    
    data = response.json()
    if not data.get('success') or not isinstance(data.get('results'), list):
        return []
    
    raw_results: List[RawSearchResult] = data['results']
    
    # Filter out base tweet if provided
    if exclude_tweet_id:
        raw_results = [
            r for r in raw_results
            if r.get('metadata', {}).get('tweet_id') != exclude_tweet_id
            and r.get('key') != exclude_tweet_id
        ]
    
    return [
        {
            'key': r['key'],
            'distance': r['distance'],
            'metadata': r.get('metadata', {})
        }
        for r in raw_results
    ]

# %%
