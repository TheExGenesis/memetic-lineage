import { Suspense } from 'react'
import { getThread, getConversationId, fetchTweetDetails } from '@/lib/api'
import { Tweet } from '@/lib/types'
import { MultiThreadClient } from './MultiThreadClient'

interface ThreadColumn {
  targetIds: string[]
  conversationId: string | null
  tweets: Tweet[]
  rootDate: Date
}

async function loadThreadColumns(tweetIds: string[]): Promise<ThreadColumn[]> {
  const convIdToColumn = new Map<string, ThreadColumn>()
  const standaloneColumns: ThreadColumn[] = []

  for (const id of tweetIds) {
    const convId = await getConversationId(id)

    if (convId && convIdToColumn.has(convId)) {
      convIdToColumn.get(convId)!.targetIds.push(id)
      continue
    }

    let tweets: Tweet[] = []
    if (convId) {
      tweets = await getThread(convId)
    }

    if (tweets.length === 0) {
      const fetched = await fetchTweetDetails([id])
      if (fetched.length > 0) {
        tweets = fetched
      }
    }

    if (tweets.length === 0) continue

    const rootDate = tweets.reduce(
      (earliest, t) => {
        const d = new Date(t.created_at)
        return d < earliest ? d : earliest
      },
      new Date(tweets[0].created_at)
    )

    const col: ThreadColumn = { targetIds: [id], conversationId: convId, tweets, rootDate }

    if (convId) {
      convIdToColumn.set(convId, col)
    } else {
      standaloneColumns.push(col)
    }
  }

  const allColumns = [...convIdToColumn.values(), ...standaloneColumns]
  allColumns.sort((a, b) => a.rootDate.getTime() - b.rootDate.getTime())

  return allColumns
}

export default async function MultiThreadVisualizerPage({
  searchParams
}: {
  searchParams: Promise<{ tweet_ids?: string }>
}) {
  const params = await searchParams
  const raw = params.tweet_ids ?? ''
  const tweetIds = raw
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)

  if (tweetIds.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8 text-center">
        <div>
          <h1 className="text-2xl font-bold mb-4">Multi Thread Visualizer</h1>
          <p className="text-gray-600">
            Pass tweet IDs via <code className="bg-gray-100 px-1">?tweet_ids=123,456,789</code>
          </p>
        </div>
      </div>
    )
  }

  const columns = await loadThreadColumns(tweetIds)

  if (columns.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8 text-center">
        <p className="text-gray-600">No threads found for the given tweet IDs.</p>
      </div>
    )
  }

  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <MultiThreadClient columns={columns} />
    </Suspense>
  )
}
