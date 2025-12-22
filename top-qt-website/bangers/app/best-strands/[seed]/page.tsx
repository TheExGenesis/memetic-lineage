import { Suspense } from 'react'
import { promises as fs } from 'fs'
import path from 'path'
import { fetchTweetDetails } from '@/lib/api'
import { Strand, StrandWithTweet } from '@/lib/types'
import { BestStrandsClient } from '../BestStrandsClient'

// Path to rated strands in scratchpads
const RATED_STRANDS_DIR = path.join(
  process.cwd(),
  '../../scratchpads/data/rated_strands'
)

function parseStrandJson(jsonText: string): Strand {
  const fixedJson = jsonText
    .replace(/"seed_tweet_id":\s*(\d+)/g, '"seed_tweet_id": "$1"')
    .replace(/"tweet_id":\s*(\d+)/g, '"tweet_id": "$1"')

  const parsed = JSON.parse(fixedJson)

  if (!parsed.seeds && parsed.seed_ids) {
    parsed.seeds = parsed.seed_ids.map((id: string | number) => ({
      tweet_id: String(id),
      source_type: 'root' as const,
    }))
  }
  parsed.seeds = parsed.seeds || []

  return parsed
}

async function loadStrandsWithTweets(): Promise<StrandWithTweet[]> {
  let files: string[]
  try {
    files = await fs.readdir(RATED_STRANDS_DIR)
  } catch (e) {
    console.error('Could not read rated_strands directory:', e)
    return []
  }

  const jsonFiles = files.filter(f => f.endsWith('.json'))
  const strands: Strand[] = []
  for (const file of jsonFiles) {
    try {
      const filePath = path.join(RATED_STRANDS_DIR, file)
      const jsonText = await fs.readFile(filePath, 'utf-8')
      const strand = parseStrandJson(jsonText)
      strands.push(strand)
    } catch (e) {
      console.error(`Error parsing ${file}:`, e)
    }
  }

  if (strands.length === 0) return []

  const seedTweetIds = strands.map(s => s.seed_tweet_id)
  const seedTweets = await fetchTweetDetails(seedTweetIds)
  const tweetMap = new Map(seedTweets.map(t => [t.tweet_id, t]))

  const strandsWithTweets: StrandWithTweet[] = strands.map(strand => ({
    ...strand,
    seedTweet: tweetMap.get(strand.seed_tweet_id),
  }))

  strandsWithTweets.sort((a, b) => b.rating.rating - a.rating.rating)
  return strandsWithTweets
}

export default async function BestStrandBySeedPage() {
  const strands = await loadStrandsWithTweets()

  if (strands.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No strands found.</p>
      </div>
    )
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strands...</div>}>
      <BestStrandsClient strands={strands} />
    </Suspense>
  )
}

