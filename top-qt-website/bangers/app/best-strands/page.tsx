import { Suspense } from 'react';
import { promises as fs } from 'fs';
import path from 'path';
import { fetchTweetDetails } from '@/lib/api';
import { Strand, StrandWithTweet, GraphData, GraphNode } from '@/lib/types';
import { BestStrandsClient } from './BestStrandsClient';

// Path to rated strands in scratchpads
const RATED_STRANDS_DIR = path.join(
  process.cwd(), 
  '../../scratchpads/data/rated_strands'
);

// Path to graph data in public folder
const GRAPH_DATA_PATH = path.join(process.cwd(), 'public/graph-data.json');

// Parse a single strand JSON, fixing large integer tweet IDs
function parseStrandJson(jsonText: string): Strand {
  const fixedJson = jsonText
    .replace(/"seed_tweet_id":\s*(\d+)/g, '"seed_tweet_id": "$1"')
    .replace(/"tweet_id":\s*(\d+)/g, '"tweet_id": "$1"');
  
  const parsed = JSON.parse(fixedJson);
  
  // Handle both old format (seed_ids: number[]) and new format (seeds: {tweet_id, source_type}[])
  if (!parsed.seeds && parsed.seed_ids) {
    parsed.seeds = parsed.seed_ids.map((id: string | number) => ({
      tweet_id: String(id),
      source_type: 'root' as const, // Old data doesn't have source_type
    }));
  }
  parsed.seeds = parsed.seeds || [];
  
  return parsed;
}

async function loadStrandsWithTweets(): Promise<StrandWithTweet[]> {
  // Read all JSON files from the rated_strands directory
  let files: string[];
  try {
    files = await fs.readdir(RATED_STRANDS_DIR);
  } catch (e) {
    console.error('Could not read rated_strands directory:', e);
    return [];
  }
  
  const jsonFiles = files.filter(f => f.endsWith('.json'));
  
  // Load and parse all strand files
  const strands: Strand[] = [];
  for (const file of jsonFiles) {
    try {
      const filePath = path.join(RATED_STRANDS_DIR, file);
      const jsonText = await fs.readFile(filePath, 'utf-8');
      const strand = parseStrandJson(jsonText);
      strands.push(strand);
    } catch (e) {
      console.error(`Error parsing ${file}:`, e);
    }
  }
  
  if (strands.length === 0) {
    return [];
  }
  
  // Extract all seed tweet IDs
  const seedTweetIds = strands.map(s => s.seed_tweet_id);
  
  // Fetch all seed tweets in one batch
  const seedTweets = await fetchTweetDetails(seedTweetIds);
  const tweetMap = new Map(seedTweets.map(t => [t.tweet_id, t]));
  
  // Combine strands with their seed tweets
  const strandsWithTweets: StrandWithTweet[] = strands.map(strand => ({
    ...strand,
    seedTweet: tweetMap.get(strand.seed_tweet_id),
  }));
  
  // Sort by rating (descending)
  strandsWithTweets.sort((a, b) => b.rating.rating - a.rating.rating);
  
  return strandsWithTweets;
}

async function loadGraphData(): Promise<GraphData | null> {
  try {
    const jsonText = await fs.readFile(GRAPH_DATA_PATH, 'utf-8');
    const graphData: GraphData = JSON.parse(jsonText);
    
    // Extract all unique tweet IDs from nodes
    const tweetIds = graphData.nodes.map(n => n.tweet_id);
    
    // Fetch tweet details in batch
    const tweets = await fetchTweetDetails(tweetIds);
    const tweetMap = new Map(tweets.map(t => [t.tweet_id, t]));
    
    // Enrich nodes with tweet data
    graphData.nodes = graphData.nodes.map((node: GraphNode) => {
      const tweet = tweetMap.get(node.tweet_id);
      if (tweet) {
        return {
          ...node,
          avatar_url: tweet.avatar_media_url,
          username: tweet.username,
          full_text: tweet.full_text,
          created_at: tweet.created_at,
          media_urls: tweet.media_urls,
        };
      }
      return node;
    });
    
    return graphData;
  } catch (e) {
    console.error('Could not load graph data:', e);
    return null;
  }
}

export default async function BestStrandsPage() {
  // Load both strands and graph data in parallel
  const [strands, graphData] = await Promise.all([
    loadStrandsWithTweets(),
    loadGraphData(),
  ]);
  
  if (strands.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>No strands found.</p>
      </div>
    );
  }
  
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading strands...</div>}>
      <BestStrandsClient strands={strands} graphData={graphData} />
    </Suspense>
  );
}

