import { useState, useEffect, useRef } from 'react'
import { fetchTweetMedia } from '@/app/actions/media'

// Module-level cache shared across all hook instances
const mediaCache = new Map<string, string[]>()
// Track tweet IDs we've already requested
const requestedIds = new Set<string>()
// Batch queue
let pendingIds: string[] = []
let batchTimer: ReturnType<typeof setTimeout> | null = null
let batchResolvers: Array<() => void> = []

function flushBatch() {
  if (pendingIds.length === 0) return

  const ids = [...pendingIds]
  const resolvers = [...batchResolvers]
  pendingIds = []
  batchResolvers = []
  batchTimer = null

  fetchTweetMedia(ids).then((result) => {
    for (const [tweetId, urls] of Object.entries(result)) {
      mediaCache.set(tweetId, urls)
    }
    // Mark IDs with no media so we don't re-fetch
    for (const id of ids) {
      if (!mediaCache.has(id)) {
        mediaCache.set(id, [])
      }
    }
    resolvers.forEach((r) => r())
  }).catch(() => {
    // On error, remove from requestedIds so they can be retried
    for (const id of ids) {
      requestedIds.delete(id)
    }
    resolvers.forEach((r) => r())
  })
}

function queueTweetId(tweetId: string): Promise<void> {
  if (requestedIds.has(tweetId)) {
    return Promise.resolve()
  }
  requestedIds.add(tweetId)
  pendingIds.push(tweetId)

  return new Promise<void>((resolve) => {
    batchResolvers.push(resolve)
    if (batchTimer) clearTimeout(batchTimer)
    batchTimer = setTimeout(flushBatch, 50)
  })
}

/**
 * Hook that returns media URLs for a tweet ID.
 * Automatically batches and caches requests.
 */
export function useMediaUrls(tweetId: string): string[] | undefined {
  const [urls, setUrls] = useState<string[] | undefined>(() => mediaCache.get(tweetId))
  const idRef = useRef(tweetId)
  idRef.current = tweetId

  useEffect(() => {
    const cached = mediaCache.get(tweetId)
    if (cached !== undefined) {
      setUrls(cached)
      return
    }

    let cancelled = false
    queueTweetId(tweetId).then(() => {
      if (!cancelled && idRef.current === tweetId) {
        setUrls(mediaCache.get(tweetId))
      }
    })

    return () => {
      cancelled = true
    }
  }, [tweetId])

  return urls
}

/**
 * Prefetch media for a list of tweet IDs.
 */
export function prefetchMedia(tweetIds: string[]) {
  // On re-mount (e.g. back navigation), requestedIds may contain IDs
  // whose fetch completed but the component wasn't mounted to receive them.
  // Clear stale entries so they get re-queued.
  for (const id of tweetIds) {
    if (requestedIds.has(id) && !mediaCache.has(id)) {
      requestedIds.delete(id)
    }
  }

  const uncached = tweetIds.filter(
    (id) => !mediaCache.has(id) && !requestedIds.has(id)
  )
  if (uncached.length === 0) return

  for (const id of uncached) {
    requestedIds.add(id)
  }
  pendingIds.push(...uncached)

  if (batchTimer) clearTimeout(batchTimer)
  batchTimer = setTimeout(flushBatch, 10)
}
