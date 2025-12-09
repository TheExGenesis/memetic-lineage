import { fetchTweetDetails, getThread, getConversationId } from '@/lib/api';
import { Tweet } from '@/lib/types';

type SourceType = 'root' | 'quote_of_root' | 'semantic_match' | 'quote_of_semantic_match';

export interface ThreadColumn {
  targetIds: string[];
  conversationId: string | null;
  tweets: Tweet[];
  rootDate: Date;
  sourceType?: SourceType;
}

/**
 * Loads thread columns for a list of tweet IDs.
 * Each tweet ID becomes a column showing its full thread context.
 * 
 * @param tweetIds - Array of tweet IDs to load threads for
 * @param sourceTypeMap - Optional map from tweet ID to source type for coloring
 * @returns Array of ThreadColumn objects sorted by root date
 */
export async function loadThreadColumns(
  tweetIds: string[],
  sourceTypeMap?: Map<string, SourceType>
): Promise<ThreadColumn[]> {
  if (tweetIds.length === 0) return [];

  // Fetch all target tweets first to get their dates
  const targetTweets = await fetchTweetDetails(tweetIds);
  const targetTweetMap = new Map(targetTweets.map(t => [t.tweet_id, t]));

  // Group tweets by conversation to avoid duplicate thread fetches
  const conversationGroups = new Map<string, { tweetIds: string[]; sourceType?: SourceType }>();
  const orphanTweets: { tweet: Tweet; sourceType?: SourceType }[] = [];

  // First, get conversation IDs for all tweets
  const conversationPromises = tweetIds.map(async (id) => {
    const convId = await getConversationId(id);
    return { id, convId };
  });

  const conversationResults = await Promise.all(conversationPromises);

  for (const { id, convId } of conversationResults) {
    const sourceType = sourceTypeMap?.get(id);
    const tweet = targetTweetMap.get(id);

    if (!tweet) continue;

    if (convId) {
      const existing = conversationGroups.get(convId);
      if (existing) {
        existing.tweetIds.push(id);
        // Keep the "most important" source type
        if (!existing.sourceType && sourceType) {
          existing.sourceType = sourceType;
        }
      } else {
        conversationGroups.set(convId, { tweetIds: [id], sourceType });
      }
    } else {
      // Tweet is not part of a known conversation
      orphanTweets.push({ tweet, sourceType });
    }
  }

  // Fetch threads for each conversation
  const columns: ThreadColumn[] = [];

  for (const [convId, group] of conversationGroups) {
    const threadTweets = await getThread(convId);
    
    if (threadTweets.length === 0) continue;

    // Find root date (earliest tweet in thread)
    const sortedByDate = [...threadTweets].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
    const rootDate = new Date(sortedByDate[0].created_at);

    columns.push({
      targetIds: group.tweetIds,
      conversationId: convId,
      tweets: threadTweets,
      rootDate,
      sourceType: group.sourceType,
    });
  }

  // Add orphan tweets as single-tweet columns
  for (const { tweet, sourceType } of orphanTweets) {
    columns.push({
      targetIds: [tweet.tweet_id],
      conversationId: null,
      tweets: [tweet],
      rootDate: new Date(tweet.created_at),
      sourceType,
    });
  }

  // Sort columns by root date (oldest first)
  columns.sort((a, b) => a.rootDate.getTime() - b.rootDate.getTime());

  return columns;
}

