import { promises as fs } from 'fs';
import path from 'path';
import { StrandWithTweet } from '@/lib/types';

const STRANDS_DATA_PATH = path.join(process.cwd(), 'public/strands_data.json');

let strandsCache: StrandWithTweet[] | null = null;

export async function loadAllStrands(): Promise<StrandWithTweet[]> {
  if (strandsCache) return strandsCache;

  try {
    let data = await fs.readFile(STRANDS_DATA_PATH, 'utf-8');

    // Fix bare numeric tweet IDs before JSON.parse to avoid float64 precision loss.
    // Matches "tweet_id": 1423006703495176194 and converts to "tweet_id": "1423006703495176194"
    data = data.replace(/"tweet_id":\s*(\d+)/g, '"tweet_id": "$1"');

    const parsed = JSON.parse(data);
    strandsCache = parsed.strands;
    return strandsCache!;
  } catch (e) {
    console.error('Failed to load strands_data.json:', e);
    return [];
  }
}

export async function loadStrandBySeed(seedId: string): Promise<StrandWithTweet | null> {
  const strands = await loadAllStrands();
  return strands.find(s => s.seed_tweet_id === seedId) || null;
}
