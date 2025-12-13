# %%
from typing import TypedDict, Optional, List
import requests
from requests.exceptions import RequestException

from .retry import with_retry


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


@with_retry(max_retries=3, base_delay=1.0, retryable_errors=(RequestException,))
def _search_embeddings_request(payload: dict) -> dict:
    """Make the HTTP request to search API. Raises on failure."""
    url = 'http://embed.tweetstack.app/embeddings/search'
    response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
    response.raise_for_status()
    return response.json()


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
    payload = {
        'searchTerm': search_term,
        'k': k,
        'threshold': threshold
    }
    if filter is not None:
        payload['filter'] = filter
    
    try:
        data = _search_embeddings_request(payload)
    except RequestException as e:
        print(f'Search API error after retries: {e}')
        return []
    
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
