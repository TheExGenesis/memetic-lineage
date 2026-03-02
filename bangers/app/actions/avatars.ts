'use server'

import { createClient } from '@supabase/supabase-js'

const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_KEY

const supabase = caUrl && caKey ? createClient(caUrl, caKey) : null

/**
 * Fetch avatar URLs for a list of usernames from the Community Archive.
 * Queries all_account JOIN all_profile to get the latest avatar_media_url.
 *
 * Returns a map of username -> avatar_media_url.
 */
export async function fetchAvatars(
  usernames: string[]
): Promise<Record<string, string>> {
  if (!supabase || usernames.length === 0) return {}

  const unique = [...new Set(usernames)]

  // Supabase has a limit on IN clause size, batch in chunks of 200
  const BATCH_SIZE = 200
  const result: Record<string, string> = {}

  for (let i = 0; i < unique.length; i += BATCH_SIZE) {
    const batch = unique.slice(i, i + BATCH_SIZE)

    const { data, error } = await supabase
      .from('all_account')
      .select('username, all_profile(avatar_media_url)')
      .in('username', batch)

    if (error) {
      console.error('[avatars] Error fetching avatars:', error.message)
      continue
    }

    if (data) {
      for (const row of data) {
        // all_profile is returned as an array (one-to-many), take the first
        const profiles = row.all_profile as
          | { avatar_media_url: string | null }[]
          | { avatar_media_url: string | null }
          | null
        let avatarUrl: string | null = null

        if (Array.isArray(profiles) && profiles.length > 0) {
          avatarUrl = profiles[0].avatar_media_url
        } else if (profiles && !Array.isArray(profiles)) {
          avatarUrl = profiles.avatar_media_url
        }

        if (avatarUrl && row.username) {
          result[row.username] = avatarUrl
        }
      }
    }
  }

  return result
}
