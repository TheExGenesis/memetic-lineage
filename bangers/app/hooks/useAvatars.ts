import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAvatars } from '@/app/actions/avatars'

// Module-level cache shared across all hook instances
const avatarCache = new Map<string, string>()
// Track usernames we've already requested (to avoid duplicate fetches)
const requestedUsernames = new Set<string>()
// Batch queue for pending requests
let pendingUsernames: string[] = []
let batchTimer: ReturnType<typeof setTimeout> | null = null
let batchResolvers: Array<() => void> = []

function flushBatch() {
  if (pendingUsernames.length === 0) return

  const usernames = [...pendingUsernames]
  const resolvers = [...batchResolvers]
  pendingUsernames = []
  batchResolvers = []
  batchTimer = null

  fetchAvatars(usernames).then((result) => {
    for (const [username, url] of Object.entries(result)) {
      avatarCache.set(username, url)
    }
    // Notify all waiting hooks
    resolvers.forEach((r) => r())
  })
}

function queueUsername(username: string): Promise<void> {
  if (requestedUsernames.has(username)) {
    return Promise.resolve()
  }
  requestedUsernames.add(username)
  pendingUsernames.push(username)

  return new Promise<void>((resolve) => {
    batchResolvers.push(resolve)
    // Debounce: wait 50ms to collect more usernames before firing
    if (batchTimer) clearTimeout(batchTimer)
    batchTimer = setTimeout(flushBatch, 50)
  })
}

/**
 * Hook that returns an avatar URL for a username.
 * Automatically batches and caches requests to the community archive.
 */
export function useAvatar(username: string): string | undefined {
  const [url, setUrl] = useState<string | undefined>(() => avatarCache.get(username))
  const usernameRef = useRef(username)
  usernameRef.current = username

  useEffect(() => {
    // Check cache first
    const cached = avatarCache.get(username)
    if (cached) {
      setUrl(cached)
      return
    }

    let cancelled = false
    queueUsername(username).then(() => {
      if (!cancelled && usernameRef.current === username) {
        setUrl(avatarCache.get(username))
      }
    })

    return () => {
      cancelled = true
    }
  }, [username])

  return url
}

/**
 * Prefetch avatars for a list of usernames.
 * Call this early to warm the cache before components render.
 */
export function prefetchAvatars(usernames: string[]) {
  const uncached = usernames.filter(
    (u) => !avatarCache.has(u) && !requestedUsernames.has(u)
  )
  if (uncached.length === 0) return

  for (const u of uncached) {
    requestedUsernames.add(u)
  }
  pendingUsernames.push(...uncached)

  if (batchTimer) clearTimeout(batchTimer)
  // Flush immediately for prefetch
  batchTimer = setTimeout(flushBatch, 10)
}
