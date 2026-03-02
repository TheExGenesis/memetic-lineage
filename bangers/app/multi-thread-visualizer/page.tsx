import { Suspense } from 'react'
import { MultiThreadClient } from './MultiThreadClient'
import { StrandSearchForm } from './StrandSearchForm'
import { findStrandSeeds } from '@/app/actions/search'
import { loadThreadColumns } from './loadThreadColumns'

export default async function MultiThreadVisualizerPage({
  searchParams
}: {
  searchParams: Promise<{ tweet_ids?: string; seed?: string }>
}) {
  const params = await searchParams
  
  // Handle seed param - run the strand discovery pipeline
  if (params.seed) {
    const { seeds, rootTweet, error } = await findStrandSeeds(params.seed)
    
    if (error || seeds.length === 0) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center p-8 text-center gap-6">
          <div>
            <h1 className="text-2xl font-bold mb-4">Strand Explorer</h1>
            <p className="text-red-600 mb-4">
              {error || 'No strands found for this tweet.'}
            </p>
          </div>
          <StrandSearchForm />
        </div>
      )
    }

    const tweetIds = seeds.map(s => s.tweetId)
    const seedMap = new Map(seeds.map(s => [s.tweetId, s.sourceType]))
    const columns = await loadThreadColumns(tweetIds, seedMap)

    return (
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strands...</div>}>
        <MultiThreadClient 
          columns={columns} 
          strandInfo={{
            rootTweetId: params.seed,
            rootTweetText: rootTweet?.full_text,
            seedCount: seeds.length,
            breakdown: {
              root: seeds.filter(s => s.sourceType === 'root').length,
              quoteOfRoot: seeds.filter(s => s.sourceType === 'quote_of_root').length,
              semanticMatch: seeds.filter(s => s.sourceType === 'semantic_match').length,
              quoteOfSemanticMatch: seeds.filter(s => s.sourceType === 'quote_of_semantic_match').length,
            }
          }}
        />
      </Suspense>
    )
  }

  // Handle tweet_ids param - direct visualization
  const raw = params.tweet_ids ?? ''
  const tweetIds = raw
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)

  if (tweetIds.length === 0) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8 text-center gap-8">
        <div>
          <h1 className="text-3xl font-bold mb-2 tracking-tight">Strand Explorer</h1>
          <p className="text-gray-600 mb-8">
            Discover related threads through quotes and semantic similarity
          </p>
        </div>
        <StrandSearchForm />
        <div className="text-xs text-gray-400 mt-8 border-t border-gray-200 pt-4">
          Or pass tweet IDs directly via <code className="bg-gray-100 px-1">?tweet_ids=123,456,789</code>
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
