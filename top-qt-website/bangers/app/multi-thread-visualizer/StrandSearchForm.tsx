'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export const StrandSearchForm = () => {
  const router = useRouter()
  const [tweetId, setTweetId] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = tweetId.trim()
    if (!trimmed) return
    
    setIsLoading(true)
    router.push(`/multi-thread-visualizer?seed=${trimmed}`)
  }

  // Extract tweet ID from various URL formats
  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text')
    // Match twitter.com/user/status/ID or x.com/user/status/ID patterns
    const match = pasted.match(/(?:twitter\.com|x\.com)\/\w+\/status\/(\d+)/)
    if (match) {
      e.preventDefault()
      setTweetId(match[1])
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-md">
      <div className="flex flex-col gap-4">
        <div>
          <label htmlFor="tweet-id" className="block text-sm font-bold uppercase mb-2">
            Tweet ID or URL
          </label>
          <input
            id="tweet-id"
            type="text"
            value={tweetId}
            onChange={e => setTweetId(e.target.value)}
            onPaste={handlePaste}
            placeholder="1234567890 or paste tweet URL"
            className="w-full px-4 py-3 border-2 border-black font-mono text-lg focus:outline-none focus:ring-2 focus:ring-black"
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          disabled={!tweetId.trim() || isLoading}
          className="w-full py-3 bg-black text-white font-bold uppercase tracking-wide hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? 'Finding strands...' : 'Explore Strand'}
        </button>
      </div>
      
      <div className="mt-6 text-sm text-gray-600">
        <p className="font-semibold mb-2">This will find:</p>
        <ul className="list-disc list-inside space-y-1">
          <li>Quote tweets of the root tweet</li>
          <li>Semantically similar tweets (top by likes)</li>
          <li>Quote tweets of those similar tweets</li>
        </ul>
      </div>
    </form>
  )
}

