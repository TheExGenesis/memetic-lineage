import { describe, it, expect, vi, beforeEach } from 'vitest'

// Test batchFetch utility in isolation (extracted for testing)
async function batchFetch<T, R>(
  ids: T[],
  fetchFn: (batch: T[]) => Promise<R[]>,
  batchSize: number = 200
): Promise<R[]> {
  if (ids.length === 0) return []
  
  const results: R[] = []
  for (let i = 0; i < ids.length; i += batchSize) {
    const batch = ids.slice(i, i + batchSize)
    const batchResults = await fetchFn(batch)
    results.push(...batchResults)
  }
  return results
}

describe('batchFetch', () => {
  it('returns empty array for empty input', async () => {
    const fetchFn = vi.fn()
    const result = await batchFetch([], fetchFn)
    expect(result).toEqual([])
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it('processes single batch when under limit', async () => {
    const ids = [1, 2, 3]
    const fetchFn = vi.fn().mockResolvedValue(['a', 'b', 'c'])
    
    const result = await batchFetch(ids, fetchFn, 10)
    
    expect(result).toEqual(['a', 'b', 'c'])
    expect(fetchFn).toHaveBeenCalledTimes(1)
    expect(fetchFn).toHaveBeenCalledWith([1, 2, 3])
  })

  it('splits into multiple batches when over limit', async () => {
    const ids = [1, 2, 3, 4, 5]
    const fetchFn = vi.fn()
      .mockResolvedValueOnce(['a', 'b'])
      .mockResolvedValueOnce(['c', 'd'])
      .mockResolvedValueOnce(['e'])
    
    const result = await batchFetch(ids, fetchFn, 2)
    
    expect(result).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(fetchFn).toHaveBeenCalledTimes(3)
    expect(fetchFn).toHaveBeenNthCalledWith(1, [1, 2])
    expect(fetchFn).toHaveBeenNthCalledWith(2, [3, 4])
    expect(fetchFn).toHaveBeenNthCalledWith(3, [5])
  })

  it('handles exact batch size boundary', async () => {
    const ids = [1, 2, 3, 4]
    const fetchFn = vi.fn()
      .mockResolvedValueOnce(['a', 'b'])
      .mockResolvedValueOnce(['c', 'd'])
    
    const result = await batchFetch(ids, fetchFn, 2)
    
    expect(result).toEqual(['a', 'b', 'c', 'd'])
    expect(fetchFn).toHaveBeenCalledTimes(2)
  })
})

// Mock Supabase for fetchTweetDetails tests
vi.mock('./supabase', () => ({
  supabaseCa: {
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        in: vi.fn(() => Promise.resolve({ data: [], error: null })),
        eq: vi.fn(() => Promise.resolve({ data: [], error: null })),
      })),
    })),
  },
}))

describe('fetchTweetDetails', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns empty array for empty input', async () => {
    const { fetchTweetDetails } = await import('./api')
    const result = await fetchTweetDetails([])
    expect(result).toEqual([])
  })
})








