'use client'

import { useState } from 'react'
import { Tweet } from '@/lib/types'
import { ThreadView } from '../ThreadView'

interface ThreadColumn {
  targetIds: string[]
  conversationId: string | null
  tweets: Tweet[]
  rootDate: Date
}

interface MultiThreadClientProps {
  columns: ThreadColumn[]
}

export const MultiThreadClient = ({ columns }: MultiThreadClientProps) => {
  const [columnWidth, setColumnWidth] = useState(400)

  const formatDate = (d: Date) => d.toISOString().split('T')[0]

  const noop = () => {}
  const noopAsync = async () => {}

  return (
    <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
      <header className="p-4 border-b border-black flex-shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Multi Thread Visualizer</h1>
          <p className="text-sm text-gray-600">{columns.length} threads, sorted by root date</p>
        </div>
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
      </header>

      <div className="flex-1 overflow-x-auto overflow-y-hidden flex">
        {columns.map((col, idx) => {
          const isEven = idx % 2 === 0
          const bgClass = isEven ? 'bg-gray-50' : 'bg-white'

          return (
            <div
              key={col.conversationId ?? col.targetIds.join(',')}
              className={`flex-shrink-0 h-full border-r border-black flex flex-col ${bgClass}`}
              style={{ width: columnWidth }}
            >
              <div className="p-3 border-b border-gray-300 flex-shrink-0">
                <div className="text-xs text-gray-500 uppercase tracking-wide">
                  Root: {formatDate(col.rootDate)}
                </div>
                <div className="text-sm font-mono truncate" title={col.targetIds.join(', ')}>
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
