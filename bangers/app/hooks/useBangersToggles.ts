'use client'

import { useState, useEffect, useCallback } from 'react'

export type TweetSource = 'everyone' | 'archive'
export type RankingMode = 'all_quotes' | 'archive_quotes'

export function useBangersToggles() {
  const [tweetSource, setTweetSource] = useState<TweetSource>('archive')
  const [rankingMode, setRankingMode] = useState<RankingMode>('archive_quotes')
  const [loaded, setLoaded] = useState(false)

  // Load from localStorage on mount
  useEffect(() => {
    const savedSource = localStorage.getItem('bangersSource') as TweetSource | null
    const savedRanking = localStorage.getItem('bangersRanking') as RankingMode | null
    if (savedSource === 'everyone' || savedSource === 'archive') setTweetSource(savedSource)
    if (savedRanking === 'all_quotes' || savedRanking === 'archive_quotes') setRankingMode(savedRanking)
    setLoaded(true)
  }, [])

  const setSource = useCallback((value: TweetSource) => {
    setTweetSource(value)
    localStorage.setItem('bangersSource', value)
  }, [])

  const setRanking = useCallback((value: RankingMode) => {
    setRankingMode(value)
    localStorage.setItem('bangersRanking', value)
  }, [])

  return { tweetSource, rankingMode, setSource, setRanking, loaded }
}
