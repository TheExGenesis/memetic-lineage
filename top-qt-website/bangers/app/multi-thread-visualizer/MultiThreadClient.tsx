'use client'

import { useState } from 'react'
import { Tweet } from '@/lib/types'
import { ThreadView } from '../ThreadView'

type SourceType = 'root' | 'quote_of_root' | 'semantic_match' | 'quote_of_semantic_match'

interface ThreadColumn {
  targetIds: string[]
  conversationId: string | null
  tweets: Tweet[]
  rootDate: Date
  sourceType?: SourceType
}

interface StrandInfo {
  rootTweetId: string
  rootTweetText?: string
  seedCount: number
  breakdown: {
    root: number
    quoteOfRoot: number
    semanticMatch: number
    quoteOfSemanticMatch: number
  }
}

interface MultiThreadClientProps {
  columns: ThreadColumn[]
  strandInfo?: StrandInfo
}

export const MultiThreadClient = ({ columns, strandInfo }: MultiThreadClientProps) => {
  const [columnWidth, setColumnWidth] = useState(400)
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [copied, setCopied] = useState(false)

  const allTweetIds = columns.flatMap(col => col.targetIds)
  
  const copyIdsToClipboard = () => {
    const idsString = allTweetIds.join(',')
    navigator.clipboard.writeText(idsString)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const formatDate = (d: Date) => d.toISOString().split('T')[0]

  const noop = () => {}
  const noopAsync = async () => {}

  return (
    <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
      <header className="p-4 border-b border-black flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <a
              href="/"
              className="p-2 hover:bg-gray-100 transition-colors border border-transparent hover:border-black"
              title="Back to home"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M19 12H5" />
                <path d="M12 19l-7-7 7-7" />
              </svg>
            </a>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                {strandInfo ? 'Strand Explorer' : 'Multi Thread Visualizer'}
              </h1>
              <p className="text-sm text-gray-600">{columns.length} threads, sorted by root date</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={copyIdsToClipboard}
              className="text-xs uppercase font-semibold px-3 py-1 border border-black hover:bg-black hover:text-white transition-colors"
            >
              {copied ? '✓ Copied!' : `Copy ${allTweetIds.length} IDs`}
            </button>
            {strandInfo && (
              <button
                onClick={() => setShowBreakdown(!showBreakdown)}
                className="text-xs uppercase font-semibold px-3 py-1 border border-black hover:bg-black hover:text-white transition-colors"
              >
                {showBreakdown ? 'Hide' : 'Show'} breakdown
              </button>
            )}
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500 uppercase">Width</label>
              <input
                type="range"
                min={280}
                max={600}
                value={columnWidth}
                onChange={e => setColumnWidth(Number(e.target.value))}
                className="w-24"
              />
              <span className="text-xs font-mono w-10">{columnWidth}px</span>
            </div>
          </div>
        </div>
        
        {strandInfo && showBreakdown && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="text-xs text-gray-500 mb-2">
              Root tweet: <span className="font-mono">{strandInfo.rootTweetId}</span>
            </div>
            {strandInfo.rootTweetText && (
              <div className="text-sm text-gray-700 mb-2 italic truncate max-w-2xl">
                &ldquo;{strandInfo.rootTweetText.slice(0, 150)}...&rdquo;
              </div>
            )}
            <div className="flex gap-4 text-xs">
              <span className="px-2 py-1 bg-blue-100 text-blue-800">
                Root: {strandInfo.breakdown.root}
              </span>
              <span className="px-2 py-1 bg-green-100 text-green-800">
                Quotes of root: {strandInfo.breakdown.quoteOfRoot}
              </span>
              <span className="px-2 py-1 bg-purple-100 text-purple-800">
                Semantic matches: {strandInfo.breakdown.semanticMatch}
              </span>
              <span className="px-2 py-1 bg-orange-100 text-orange-800">
                Quotes of matches: {strandInfo.breakdown.quoteOfSemanticMatch}
              </span>
            </div>
          </div>
        )}
      </header>

      <div className="flex-1 overflow-x-auto overflow-y-hidden flex">
        {columns.map((col, idx) => {
          const isEven = idx % 2 === 0
          const bgClass = isEven ? 'bg-gray-50' : 'bg-white'
          
          // Header color based on source type
          const getHeaderStyles = (sourceType?: SourceType) => {
            switch (sourceType) {
              case 'root':
                return 'bg-blue-100 border-blue-300'
              case 'quote_of_root':
                return 'bg-green-100 border-green-300'
              case 'semantic_match':
                return 'bg-purple-100 border-purple-300'
              case 'quote_of_semantic_match':
                return 'bg-orange-100 border-orange-300'
              default:
                return 'bg-white border-gray-300'
            }
          }
          
          const getHeaderTextColor = (sourceType?: SourceType) => {
            switch (sourceType) {
              case 'root':
                return 'text-blue-800'
              case 'quote_of_root':
                return 'text-green-800'
              case 'semantic_match':
                return 'text-purple-800'
              case 'quote_of_semantic_match':
                return 'text-orange-800'
              default:
                return 'text-gray-500'
            }
          }

          return (
            <div
              key={col.conversationId ?? col.targetIds.join(',')}
              className={`flex-shrink-0 h-full border-r border-black flex flex-col ${bgClass}`}
              style={{ width: columnWidth }}
            >
              <div className={`p-3 border-b flex-shrink-0 ${getHeaderStyles(col.sourceType)}`}>
                <div className={`text-xs uppercase tracking-wide ${getHeaderTextColor(col.sourceType)}`}>
                  Root: {formatDate(col.rootDate)}
                </div>
                <div className={`text-sm font-mono truncate ${getHeaderTextColor(col.sourceType)}`} title={col.targetIds.join(', ')}>
                  Targets: {col.targetIds.length > 1 ? `${col.targetIds.length} tweets` : col.targetIds[0]}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-3">
                <ThreadView
                  tweets={col.tweets}
                  focusedTweetIds={col.targetIds}
                  onSelectTweet={noop}
                  onSelectQuotedTweet={noopAsync}
                />
              </div>
            </div>
          )
        })}
      </div>

      <style jsx global>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-hide {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  )
}
