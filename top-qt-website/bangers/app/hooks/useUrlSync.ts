import { useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Tweet } from '@/lib/types'

interface UseUrlSyncOptions {
  tweets: Tweet[]
  onTweetsLoaded: (tweets: Tweet[]) => void
}

export function useUrlSync({ tweets, onTweetsLoaded }: UseUrlSyncOptions) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const tweetMapRef = useRef<Map<string, Tweet>>(new Map())

  // Build tweet map for URL -> tweet lookup
  useEffect(() => {
    const map = new Map<string, Tweet>()
    tweets.forEach(t => map.set(t.tweet_id, t))
    tweetMapRef.current = map
  }, [tweets])

  // Initialize from URL on mount
  useEffect(() => {
    const loadFromUrl = async () => {
      const ids = searchParams.get('tweets')
      if (!ids) return

      const tweetIds = ids.split(',').filter(Boolean)
      const foundTweets: Tweet[] = []
      const missingIds: string[] = []

      for (const id of tweetIds) {
        const tweet = tweetMapRef.current.get(id)
        if (tweet) {
          foundTweets.push(tweet)
        } else {
          missingIds.push(id)
        }
      }

      if (missingIds.length > 0) {
        const { fetchTweetDetails } = await import('@/lib/api')
        const fetchedTweets = await fetchTweetDetails(missingIds)
        
        fetchedTweets.forEach(t => tweetMapRef.current.set(t.tweet_id, t))
        
        const allTweets = tweetIds
          .map(id => tweetMapRef.current.get(id))
          .filter((t): t is Tweet => t !== undefined)
        
        if (allTweets.length > 0) {
          onTweetsLoaded(allTweets)
        }
      } else if (foundTweets.length > 0) {
        onTweetsLoaded(foundTweets)
      }
    }

    loadFromUrl()
  }, [searchParams, onTweetsLoaded])

  const updateUrl = (selectedTweets: Tweet[]) => {
    const ids = selectedTweets.map(t => t.tweet_id).join(',')
    const params = new URLSearchParams()
    if (ids) {
      params.set('tweets', ids)
    }
    router.replace(`?${params.toString()}`, { scroll: false })
  }

  return { updateUrl, tweetMapRef }
}





