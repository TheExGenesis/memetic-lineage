'use client'

import { Tweet } from '@/lib/types'
import { TweetCard } from './TweetCard'
import { useMemo, useState, useCallback } from 'react'
import { pipe } from 'fp-ts/function'
import * as A from 'fp-ts/Array'
import * as Ord from 'fp-ts/Ord'
import * as N from 'fp-ts/number'

interface ThreadViewProps {
  tweets: Tweet[]
  focusedTweetId?: string
  focusedTweetIds?: string[]
  onSelectTweet: (tweet: Tweet) => void
  onSelectQuotedTweet: (quotedId: string) => Promise<void>
  columnClassName?: string
  defaultCollapsed?: Set<string>
}

type TweetMap = Map<string, Tweet>
type ChildrenMap = Map<string, string[]>
type ParentMap = Map<string, string>

interface TreeData {
  tweetMap: TweetMap
  childrenMap: ChildrenMap
  parentMap: ParentMap
  rootIds: string[]
  focusedPath: Set<string>
}

const buildTreeData = (tweets: Tweet[], focusedIds: string[]): TreeData => {
  const tweetMap: TweetMap = new Map(tweets.map(t => [t.tweet_id, t]))
  const childrenMap: ChildrenMap = new Map()
  const parentMap: ParentMap = new Map()
  const tweetIds = new Set(tweets.map(t => t.tweet_id))
  const rootIds: string[] = []

  tweets.forEach(t => {
    const parentId = t.reply_to_tweet_id
    if (parentId && tweetIds.has(parentId)) {
      parentMap.set(t.tweet_id, parentId)
      const children = childrenMap.get(parentId) || []
      children.push(t.tweet_id)
      childrenMap.set(parentId, children)
    } else {
      rootIds.push(t.tweet_id)
    }
  })

  const byDate: Ord.Ord<{ id: string; tweet: Tweet | undefined }> = pipe(
    N.Ord,
    Ord.contramap((x: { id: string; tweet: Tweet | undefined }) =>
      x.tweet ? new Date(x.tweet.created_at).getTime() : 0
    )
  )

  const sortByDate = (ids: string[]) =>
    pipe(
      ids,
      A.map(id => ({ id, tweet: tweetMap.get(id) })),
      A.filter((x): x is { id: string; tweet: Tweet } => x.tweet !== undefined),
      A.sort(byDate),
      A.map(x => x.id)
    )

  rootIds.sort((a, b) => {
    const ta = tweetMap.get(a)
    const tb = tweetMap.get(b)
    return new Date(ta?.created_at || 0).getTime() - new Date(tb?.created_at || 0).getTime()
  })

  childrenMap.forEach((children, parentId) => {
    childrenMap.set(parentId, sortByDate(children))
  })

  const focusedPath = new Set<string>()
  for (const fid of focusedIds) {
    let cur: string | undefined = fid
    while (cur) {
      focusedPath.add(cur)
      cur = parentMap.get(cur)
    }
  }

  return { tweetMap, childrenMap, parentMap, rootIds, focusedPath }
}

const reorderForFocusedBranch = (
  ids: string[],
  focusedPath: Set<string>
): string[] => {
  const inPath = ids.filter(id => focusedPath.has(id))
  const notInPath = ids.filter(id => !focusedPath.has(id))
  return [...inPath, ...notInPath]
}

const INDENT_PX = 12
const LINE_COLOR = '#d1d5db'

export const ThreadView = ({
  tweets,
  focusedTweetId,
  focusedTweetIds,
  onSelectTweet,
  onSelectQuotedTweet,
  columnClassName,
  defaultCollapsed
}: ThreadViewProps) => {
  const resolvedFocusedIds = focusedTweetIds ?? (focusedTweetId ? [focusedTweetId] : [])
  const focusedSet = useMemo(() => new Set(resolvedFocusedIds), [resolvedFocusedIds])

  const treeData = useMemo(
    () => buildTreeData(tweets, resolvedFocusedIds),
    [tweets, resolvedFocusedIds]
  )

  const [collapsed, setCollapsed] = useState<Set<string>>(
    () => defaultCollapsed ?? new Set()
  )

  const toggleCollapse = useCallback((id: string) => {
    setCollapsed(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const { tweetMap, childrenMap, focusedPath, rootIds } = treeData

  const renderNode = (
    tweetId: string,
    depth: number,
    isLastChild: boolean,
    ancestorLines: boolean[]
  ): React.ReactNode => {
    const tweet = tweetMap.get(tweetId)
    if (!tweet) return null

    let children = childrenMap.get(tweetId) || []
    children = reorderForFocusedBranch(children, focusedPath)
    const hasChildren = children.length > 0
    const isCollapsed = collapsed.has(tweetId)
    const isFocused = focusedSet.has(tweetId)

    return (
      <div key={tweetId} className="relative">
        <div className="flex items-stretch">
          {ancestorLines.map((showLine, i) => (
            <div
              key={i}
              className="flex-shrink-0 relative"
              style={{ width: INDENT_PX }}
            >
              {showLine && (
                <div
                  className="absolute top-0 bottom-0 left-1/2"
                  style={{
                    width: 1,
                    backgroundColor: LINE_COLOR,
                    transform: 'translateX(-50%)'
                  }}
                />
              )}
            </div>
          ))}

          {depth > 0 && (
            <div
              className="flex-shrink-0 relative"
              style={{ width: INDENT_PX }}
            >
              <div
                className="absolute top-0 left-1/2"
                style={{
                  width: 1,
                  height: '50%',
                  backgroundColor: LINE_COLOR,
                  transform: 'translateX(-50%)'
                }}
              />
              <div
                className="absolute top-1/2 left-1/2"
                style={{
                  width: INDENT_PX / 2,
                  height: 1,
                  backgroundColor: LINE_COLOR,
                  transform: 'translateY(-50%)'
                }}
              />
              {!isLastChild && (
                <div
                  className="absolute top-1/2 bottom-0 left-1/2"
                  style={{
                    width: 1,
                    backgroundColor: LINE_COLOR,
                    transform: 'translateX(-50%)'
                  }}
                />
              )}
            </div>
          )}

          {hasChildren ? (
            <button
              onClick={e => {
                e.stopPropagation()
                toggleCollapse(tweetId)
              }}
              className="flex-shrink-0 w-5 h-5 flex items-center justify-center text-xs text-gray-500 hover:text-black self-start mt-2"
              aria-label={isCollapsed ? 'Expand' : 'Collapse'}
            >
              {isCollapsed ? '▶' : '▼'}
            </button>
          ) : (
            <div className="flex-shrink-0 w-5 h-5 self-start mt-2" />
          )}

          <div
            className={`flex-1 cursor-pointer transition-colors ${isFocused ? 'ring-2 ring-blue-500 rounded p-1' : ''}`}
            style={{ maxWidth: 360 }}
            onClick={e => {
              e.stopPropagation()
              onSelectTweet(tweet)
            }}
          >
            <TweetCard tweet={tweet} onQuotedTweetClick={onSelectQuotedTweet} />
          </div>
        </div>

        {hasChildren && !isCollapsed && (
          <div>
            {children.map((childId, idx) => {
              const isLast = idx === children.length - 1
              const nextAncestorLines =
                depth > 0
                  ? [...ancestorLines, !isLastChild]
                  : ancestorLines
              return renderNode(childId, depth + 1, isLast, nextAncestorLines)
            })}
          </div>
        )}
      </div>
    )
  }

  const orderedRoots = reorderForFocusedBranch(rootIds, focusedPath)

  return (
    <div className={`flex flex-col gap-4 pb-20 ${columnClassName ?? ''}`}>
      {orderedRoots.map((rootId, idx) =>
        renderNode(rootId, 0, idx === orderedRoots.length - 1, [])
      )}
    </div>
  )
}
