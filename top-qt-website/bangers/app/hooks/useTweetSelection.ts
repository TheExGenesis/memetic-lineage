import { useState, useCallback } from 'react'
import { Tweet } from '@/lib/types'

interface UseTweetSelectionOptions {
  onSelectionChange?: (tweets: Tweet[]) => void
}

export function useTweetSelection({ onSelectionChange }: UseTweetSelectionOptions = {}) {
  const [selectedTweets, setSelectedTweets] = useState<Tweet[]>([])

  const handleTweetClick = useCallback((tweet: Tweet, depth: number) => {
    const newStack = depth === -1 ? [] : selectedTweets.slice(0, depth + 1)
    newStack.push(tweet)
    setSelectedTweets(newStack)
    onSelectionChange?.(newStack)
  }, [selectedTweets, onSelectionChange])

  const handleClosePane = useCallback((index: number) => {
    const newStack = selectedTweets.slice(0, index)
    setSelectedTweets(newStack)
    onSelectionChange?.(newStack)
  }, [selectedTweets, onSelectionChange])

  const handleSpineClick = useCallback((index: number) => {
    const newStack = index === -1 ? [] : selectedTweets.slice(0, index + 1)
    setSelectedTweets(newStack)
    onSelectionChange?.(newStack)
  }, [selectedTweets, onSelectionChange])

  const setTweets = useCallback((tweets: Tweet[]) => {
    setSelectedTweets(tweets)
  }, [])

  return {
    selectedTweets,
    setTweets,
    handleTweetClick,
    handleClosePane,
    handleSpineClick,
  }
}





