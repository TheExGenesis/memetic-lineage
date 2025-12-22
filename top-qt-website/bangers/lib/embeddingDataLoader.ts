/**
 * Cached loader for tweet embeddings data
 * Fetches and parses the JSON once, then caches in memory for subsequent requests
 */

export interface EmbeddingData {
  x: number[];
  y: number[];
  tweet_id: string[];
  strand_id: string[];
  is_essential: boolean[];
  is_root: boolean[];
  text: string[];
}

// Module-level cache - persists across component re-renders
let cachedData: EmbeddingData | null = null;
let loadingPromise: Promise<EmbeddingData> | null = null;

/**
 * Load tweet embedding data with in-memory caching
 * Multiple simultaneous calls will share the same fetch/parse operation
 */
export async function loadEmbeddingData(): Promise<EmbeddingData> {
  // Return cached data if available
  if (cachedData) {
    return cachedData;
  }

  // If already loading, return the existing promise
  if (loadingPromise) {
    return loadingPromise;
  }

  // Start loading and cache the promise
  loadingPromise = (async () => {
    try {
      const startTime = performance.now();

      // Fetch the data
      const response = await fetch('/data/tweet_embeddings_compact.json');

      if (!response.ok) {
        throw new Error(`Failed to fetch embeddings: ${response.statusText}`);
      }

      const fetchTime = performance.now() - startTime;
      console.log(`[EmbeddingLoader] Fetch completed in ${fetchTime.toFixed(0)}ms`);

      // Parse JSON (this is the slow part for large files)
      const parseStartTime = performance.now();
      const data: EmbeddingData = await response.json();
      const parseTime = performance.now() - parseStartTime;

      console.log(`[EmbeddingLoader] Parse completed in ${parseTime.toFixed(0)}ms`);
      console.log(`[EmbeddingLoader] Total load time: ${(performance.now() - startTime).toFixed(0)}ms`);
      console.log(`[EmbeddingLoader] Loaded ${data.x.length} points`);

      // Cache the result
      cachedData = data;
      loadingPromise = null;

      return data;
    } catch (error) {
      // Clear the loading promise on error so retry is possible
      loadingPromise = null;
      throw error;
    }
  })();

  return loadingPromise;
}

/**
 * Clear the cached data (useful for testing or forced refresh)
 */
export function clearEmbeddingCache(): void {
  cachedData = null;
  loadingPromise = null;
}

/**
 * Check if data is currently cached
 */
export function isEmbeddingDataCached(): boolean {
  return cachedData !== null;
}
