import { Suspense } from 'react'
import { promises as fs } from 'fs'
import path from 'path'
import { notFound } from 'next/navigation'
import { fetchTweetDetails } from '@/lib/api'
import { Strand, StrandWithTweet } from '@/lib/types'
import { StrandDetailPage } from './StrandDetailPage'

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

async function loadSingleStrand(seedId: string): Promise<StrandWithTweet | null> {
  const filePath = path.join(RATED_STRANDS_DIR, `${seedId}.json`)

  try {
    const jsonText = await fs.readFile(filePath, 'utf-8')
    const strand = parseStrandJson(jsonText)

    // Fetch only this strand's seed tweet
    const seedTweets = await fetchTweetDetails([strand.seed_tweet_id])
    const seedTweet = seedTweets[0]

    return {
      ...strand,
      seedTweet,
    }
  } catch (e) {
    console.error(`Error loading strand ${seedId}:`, e)
    return null
  }
}

interface PageProps {
  params: Promise<{ seed: string }>
}

export default async function StrandByIdPage({ params }: PageProps) {
  const { seed } = await params
  const strand = await loadSingleStrand(seed)

  if (!strand) {
    notFound()
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strand...</div>}>
      <StrandDetailPage strand={strand} />
    </Suspense>
  )
}
