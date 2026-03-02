'use client'

import { useState, useEffect, useRef, memo } from 'react'
import { Tweet } from '@/lib/types'
import { ThreadView } from '../ThreadView'
import { BackButton } from '../components/BackButton'

type SourceType = 'root' | 'quote_of_root' | 'semantic_match' | 'quote_of_semantic_match'

const INITIAL_COLUMNS = 8;
const LOAD_MORE_COLUMNS = 5;

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

// Memoized column component to prevent re-renders
const ThreadColumn = memo(function ThreadColumn({
  column,
  columnWidth,
  isEven,
  formatDate
}: {
  column: ThreadColumn;
  columnWidth: number;
  isEven: boolean;
  formatDate: (d: Date) => string;
}) {
  const bgClass = isEven ? 'bg-gray-50' : 'bg-white';

  const getHeaderStyles = (sourceType?: SourceType) => {
    switch (sourceType) {
      case 'root': return 'bg-blue-100 border-blue-300';
      case 'quote_of_root': return 'bg-green-100 border-green-300';
      case 'semantic_match': return 'bg-purple-100 border-purple-300';
      case 'quote_of_semantic_match': return 'bg-orange-100 border-orange-300';
      default: return 'bg-white border-gray-300';
    }
  };

  const getHeaderTextColor = (sourceType?: SourceType) => {
    switch (sourceType) {
      case 'root': return 'text-blue-800';
      case 'quote_of_root': return 'text-green-800';
      case 'semantic_match': return 'text-purple-800';
      case 'quote_of_semantic_match': return 'text-orange-800';
      default: return 'text-gray-500';
    }
  };

  const noop = () => {};
  const noopAsync = async () => {};

  return (
    <div
      className={`flex-shrink-0 h-full border-r border-black flex flex-col ${bgClass}`}
      style={{ width: columnWidth }}
    >
      <div className={`p-3 border-b flex-shrink-0 ${getHeaderStyles(column.sourceType)}`}>
        <div className={`text-xs uppercase tracking-wide ${getHeaderTextColor(column.sourceType)}`}>
          Root: {formatDate(column.rootDate)}
        </div>
        <div className={`text-sm font-mono truncate ${getHeaderTextColor(column.sourceType)}`} title={column.targetIds.join(', ')}>
          Targets: {column.targetIds.length > 1 ? `${column.targetIds.length} tweets` : column.targetIds[0]}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <ThreadView
          tweets={column.tweets}
          focusedTweetIds={column.targetIds}
          onSelectTweet={noop}
          onSelectQuotedTweet={noopAsync}
        />
      </div>
    </div>
  );
});

export const MultiThreadClient = ({ columns, strandInfo }: MultiThreadClientProps) => {
  const [columnWidth, setColumnWidth] = useState(400)
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [copied, setCopied] = useState(false)
  const [visibleCount, setVisibleCount] = useState(INITIAL_COLUMNS)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Lazy load more columns on horizontal scroll
  useEffect(() => {
    if (!loadMoreRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && visibleCount < columns.length) {
          setVisibleCount(prev => Math.min(prev + LOAD_MORE_COLUMNS, columns.length));
        }
      },
      { threshold: 0.1, rootMargin: '400px' }
    );

    observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, [visibleCount, columns.length]);

  const allTweetIds = columns.flatMap(col => col.targetIds)
  
  const copyIdsToClipboard = () => {
    const idsString = allTweetIds.join(',')
    navigator.clipboard.writeText(idsString)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const formatDate = (d: Date) => d.toISOString().split('T')[0]

  return (
    <div className="h-screen flex flex-col bg-white text-black overflow-hidden">
      <header className="p-4 border-b border-black flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <BackButton fallbackHref="/" />
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

      <div ref={scrollContainerRef} className="flex-1 overflow-x-auto overflow-y-hidden flex">
        {columns.slice(0, visibleCount).map((col, idx) => (
          <ThreadColumn
            key={col.conversationId ?? col.targetIds.join(',')}
            column={col}
            columnWidth={columnWidth}
            isEven={idx % 2 === 0}
            formatDate={formatDate}
          />
        ))}
        {visibleCount < columns.length && (
          <div
            ref={loadMoreRef}
            className="flex-shrink-0 h-full flex items-center justify-center bg-gray-100 border-r border-black"
            style={{ width: 200 }}
          >
            <div className="text-center text-gray-500">
              <div className="text-sm font-medium">Loading more...</div>
              <div className="text-xs mt-1">
                {columns.length - visibleCount} columns remaining
              </div>
            </div>
          </div>
        )}
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
