'use server'

import { createClient } from '@supabase/supabase-js'

const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_KEY

const supabase = caUrl && caKey ? createClient(caUrl, caKey) : null

/**
 * Fetch media URLs for a list of tweet IDs from the Community Archive.
 * Queries tweet_media table filtering for photos only.
 *
 * Returns a map of tweet_id -> media_url[].
 */
export async function fetchTweetMedia(
  tweetIds: string[]
): Promise<Record<string, string[]>> {
  if (!supabase || tweetIds.length === 0) return {}

  const unique = [...new Set(tweetIds)]
  const BATCH_SIZE = 200
  const result: Record<string, string[]> = {}

  for (let i = 0; i < unique.length; i += BATCH_SIZE) {
    const batch = unique.slice(i, i + BATCH_SIZE)

    const { data, error } = await supabase
      .from('tweet_media')
      .select('tweet_id, media_url')
      .in('tweet_id', batch)
      .eq('media_type', 'photo')

    if (error) {
      console.error('[media] Error fetching tweet media:', error.message)
      continue
    }

    if (data) {
      for (const row of data) {
        if (row.media_url && row.tweet_id) {
          const tid = String(row.tweet_id)
          if (!result[tid]) result[tid] = []
          result[tid].push(row.media_url)
        }
      }
    }
  }

  return result
}
