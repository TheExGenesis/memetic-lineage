"""
Account Explorer - Get all tweets and conversations for a specific account.

This module retrieves all tweets by a user along with their full conversation context:
- All tweets authored by the account
- Full thread context (parent tweets they replied to, replies to their tweets)
- Quote tweets of their tweets (who quoted them)
- Tweets they quote tweeted

Usage:
    from lib.account_explorer import get_account_tweets, get_account_conversations

    # Get all tweets and conversations for a username
    result = get_account_conversations("visakanv")

    # Or by account_id
    result = get_account_conversations(account_id=123456)

    # Access the data
    print(f"Found {len(result.user_tweets)} tweets by user")
    print(f"Found {len(result.all_tweet_ids)} total tweets in conversations")
    print(result.rendered_text)  # Nice thread-formatted output
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from collections import defaultdict
from tqdm import tqdm

from .conversation_explorer import (
    EnrichedTweet,
    ConversationTree,
    render_conversation_trees,
    _render_header_default,
)
from .strand_caches import load_caches, get_quote_tweets_dict


@dataclass
class AccountConversationsResult:
    """Result of fetching all conversations for an account."""
    username: str
    account_id: int
    user_tweets: List[EnrichedTweet]
    # All tweet IDs involved in conversations (user's tweets + context)
    all_tweet_ids: Set[int]
    # Conversation trees filtered to relevant context
    conversation_trees: Dict[int, ConversationTree]
    # Tweet data for all involved tweets
    tweet_dict: Dict[int, EnrichedTweet]
    # Tweets that quote this user's tweets
    quotes_of_user: List[EnrichedTweet]
    # Tweets the user quoted
    user_quoted: List[EnrichedTweet]
    # Pre-rendered text output
    rendered_text: str = ""

    def summary(self) -> str:
        return (
            f"Account: @{self.username} (id={self.account_id})\n"
            f"  User's tweets: {len(self.user_tweets)}\n"
            f"  Total tweets in context: {len(self.all_tweet_ids)}\n"
            f"  Conversations: {len(self.conversation_trees)}\n"
            f"  Quotes of user: {len(self.quotes_of_user)}\n"
            f"  User quoted others: {len(self.user_quoted)}"
        )


def get_account_tweets(
    username: Optional[str] = None,
    account_id: Optional[int] = None,
) -> tuple[List[EnrichedTweet], int, str]:
    """
    Get all tweets by a specific account from the disk cache.

    Args:
        username: Twitter username (without @)
        account_id: Account ID (numeric)

    Returns:
        Tuple of (list of tweets, account_id, username)
    """
    if username is None and account_id is None:
        raise ValueError("Must provide either username or account_id")

    tweet_dict, _ = load_caches()

    user_tweets = []
    found_account_id = None
    found_username = None

    # Scan through all tweets to find matches
    # This is O(n) but the disk cache is indexed, and we need all tweets anyway
    print(f"Scanning for tweets by {'@' + username if username else 'account_id=' + str(account_id)}...")

    for tweet_id in tqdm(tweet_dict.iterkeys(), desc="Scanning tweets", total=len(tweet_dict)):
        tweet = tweet_dict[tweet_id]

        # Match by username or account_id
        if username and tweet.get("username", "").lower() == username.lower():
            user_tweets.append(tweet)
            if found_account_id is None:
                found_account_id = tweet.get("account_id")
                found_username = tweet.get("username")
        elif account_id and tweet.get("account_id") == account_id:
            user_tweets.append(tweet)
            if found_username is None:
                found_username = tweet.get("username")
                found_account_id = account_id

    if not user_tweets:
        raise ValueError(f"No tweets found for {'@' + username if username else 'account_id=' + str(account_id)}")

    # Sort by date
    user_tweets.sort(key=lambda t: t.get("created_at") or "")

    print(f"Found {len(user_tweets)} tweets by @{found_username}")
    return user_tweets, found_account_id, found_username


def get_account_conversations(
    username: Optional[str] = None,
    account_id: Optional[int] = None,
    include_quotes: bool = True,
    depth_up: int = 20,
    depth_down: int = 10,
    render: bool = True,
) -> AccountConversationsResult:
    """
    Get all tweets and full conversation context for an account.

    This retrieves:
    1. All tweets authored by the account
    2. Parent tweets in threads the user replied to (up to depth_up levels)
    3. Replies to the user's tweets (up to depth_down levels)
    4. Tweets that quote the user's tweets
    5. Tweets the user quote tweeted

    Args:
        username: Twitter username (without @)
        account_id: Account ID (numeric)
        include_quotes: Whether to include quote tweet relationships
        depth_up: How many parent tweets to include above user's tweets
        depth_down: How many reply levels to include below user's tweets
        render: Whether to pre-render the text output

    Returns:
        AccountConversationsResult with all data and rendered text
    """
    # Get user's tweets
    user_tweets, found_account_id, found_username = get_account_tweets(
        username=username, account_id=account_id
    )

    tweet_dict, reply_trees = load_caches()

    # Collect all tweet IDs we need
    all_tweet_ids: Set[int] = set()
    conversation_trees: Dict[int, ConversationTree] = {}
    local_tweet_dict: Dict[int, EnrichedTweet] = {}

    # Add user's tweets
    user_tweet_ids = {t["tweet_id"] for t in user_tweets}
    all_tweet_ids.update(user_tweet_ids)
    for t in user_tweets:
        local_tweet_dict[t["tweet_id"]] = t

    print("Building conversation context...")

    # For each user tweet, get the conversation tree and extract relevant context
    conv_ids_seen = set()

    for tweet in tqdm(user_tweets, desc="Processing conversations"):
        tweet_id = tweet["tweet_id"]
        conv_id = tweet.get("conversation_id")

        # Try conversation_id first, fall back to tweet_id for roots
        tree_key = conv_id if conv_id else tweet_id

        if tree_key in conv_ids_seen:
            continue
        conv_ids_seen.add(tree_key)

        tree = reply_trees.get(tree_key)
        if tree is None:
            # Try using tweet_id as key (for root tweets)
            tree = reply_trees.get(tweet_id)

        if tree is None:
            continue

        # Build filtered tree with context around user's tweets in this conversation
        user_tweets_in_conv = [tid for tid in user_tweet_ids if _tweet_in_tree(tid, tree)]

        if not user_tweets_in_conv:
            continue

        # Collect ancestors and descendants for each user tweet
        nodes_to_include = set()

        for tid in user_tweets_in_conv:
            nodes_to_include.add(tid)

            # Walk up to ancestors
            curr = tid
            for _ in range(depth_up):
                parent = tree["parents"].get(curr)
                if parent is None:
                    break
                nodes_to_include.add(parent)
                curr = parent

            # Walk down to descendants (BFS)
            queue = [(tid, 0)]
            while queue:
                curr, d = queue.pop(0)
                if d >= depth_down:
                    continue
                for child in tree["children"].get(curr, []):
                    if child not in nodes_to_include:
                        nodes_to_include.add(child)
                        queue.append((child, d + 1))

        # Build filtered tree
        filtered_children = defaultdict(list)
        filtered_parents = {}

        for node in nodes_to_include:
            parent = tree["parents"].get(node)
            if parent is not None and parent in nodes_to_include:
                filtered_parents[node] = parent
                filtered_children[parent].append(node)

        conversation_trees[tree_key] = {
            "root": tree.get("root"),
            "children": dict(filtered_children),
            "parents": filtered_parents,
        }

        all_tweet_ids.update(nodes_to_include)

    # Fetch all needed tweets
    print("Fetching tweet data...")
    for tid in tqdm(all_tweet_ids, desc="Loading tweets"):
        if tid not in local_tweet_dict:
            t = tweet_dict.get(tid)
            if t:
                local_tweet_dict[tid] = t

    # Handle quote tweets
    quotes_of_user = []
    user_quoted = []

    if include_quotes:
        print("Processing quote tweets...")
        quote_tweets_dict = get_quote_tweets_dict()

        # Find tweets that quote the user's tweets
        for tid in tqdm(user_tweet_ids, desc="Finding quotes of user"):
            quoting_ids = quote_tweets_dict.get(tid, [])
            for qid in quoting_ids:
                q_tweet = tweet_dict.get(qid)
                if q_tweet and q_tweet["tweet_id"] not in user_tweet_ids:
                    quotes_of_user.append(q_tweet)
                    all_tweet_ids.add(qid)
                    local_tweet_dict[qid] = q_tweet

        # Find tweets the user quoted
        for tweet in user_tweets:
            quoted_id = tweet.get("quoted_tweet_id")
            if quoted_id:
                quoted_tweet = tweet_dict.get(quoted_id)
                if quoted_tweet:
                    user_quoted.append(quoted_tweet)
                    all_tweet_ids.add(quoted_id)
                    local_tweet_dict[quoted_id] = quoted_tweet

    # Build quote context trees (quotes as separate "conversations")
    if quotes_of_user:
        print("Building quote context trees...")
        quote_trees = _build_quote_context_trees(
            user_tweet_ids, quotes_of_user, local_tweet_dict
        )
        conversation_trees.update(quote_trees)

    # Render
    rendered_text = ""
    if render:
        print("Rendering conversations...")

        def user_highlight_header(tweet: EnrichedTweet) -> str:
            base = _render_header_default(tweet)
            if tweet.get("account_id") == found_account_id:
                return f">>> {base} <<<"
            return base

        rendered_text = render_conversation_trees(
            conversation_trees,
            local_tweet_dict,
            render_header=user_highlight_header,
        )

    result = AccountConversationsResult(
        username=found_username,
        account_id=found_account_id,
        user_tweets=user_tweets,
        all_tweet_ids=all_tweet_ids,
        conversation_trees=conversation_trees,
        tweet_dict=local_tweet_dict,
        quotes_of_user=quotes_of_user,
        user_quoted=user_quoted,
        rendered_text=rendered_text,
    )

    print(result.summary())
    return result


def _tweet_in_tree(tweet_id: int, tree: ConversationTree) -> bool:
    """Check if a tweet is part of a conversation tree."""
    if tree.get("root") == tweet_id:
        return True
    if tweet_id in tree.get("parents", {}):
        return True
    if tweet_id in tree.get("children", {}):
        return True
    # Check if it's a child of any node
    for children in tree.get("children", {}).values():
        if tweet_id in children:
            return True
    return False


def _build_quote_context_trees(
    user_tweet_ids: Set[int],
    quotes_of_user: List[EnrichedTweet],
    tweet_dict: Dict[int, EnrichedTweet],
) -> Dict[int, ConversationTree]:
    """
    Build pseudo-conversation trees for quote tweet relationships.

    Creates trees where the quoted tweet is the "root" and quoting tweets
    are "children", allowing them to be rendered together.
    """
    quote_trees = {}

    # Group quotes by the tweet they quoted
    quotes_by_target: Dict[int, List[int]] = defaultdict(list)
    for qt in quotes_of_user:
        quoted_id = qt.get("quoted_tweet_id")
        if quoted_id and quoted_id in user_tweet_ids:
            quotes_by_target[quoted_id].append(qt["tweet_id"])

    # Create a tree for each quoted tweet
    for quoted_id, quoting_ids in quotes_by_target.items():
        # Use a unique key to avoid collision with reply trees
        tree_key = f"quote_{quoted_id}"

        children = {quoted_id: quoting_ids}
        parents = {qid: quoted_id for qid in quoting_ids}

        quote_trees[tree_key] = {
            "root": quoted_id,
            "children": children,
            "parents": parents,
        }

    return quote_trees


def save_account_conversations(
    result: AccountConversationsResult,
    output_path: Optional[str] = None,
) -> str:
    """
    Save rendered conversations to a file.

    Args:
        result: AccountConversationsResult from get_account_conversations
        output_path: Path to save to (default: scratchpads/data/accounts/{username}.txt)

    Returns:
        Path to saved file
    """
    from pathlib import Path

    if output_path is None:
        scratchpads_dir = Path(__file__).parent.parent
        output_dir = scratchpads_dir / "data" / "accounts"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{result.username}_conversations.txt"

    output_path = Path(output_path)

    # Build header
    header = f"""# Conversations for @{result.username}
# Account ID: {result.account_id}
# Generated: {__import__('datetime').datetime.now().isoformat()}
#
{result.summary()}

{'=' * 80}

"""

    content = header + result.rendered_text

    output_path.write_text(content)
    print(f"Saved to {output_path}")
    return str(output_path)


# Convenience function for quick exploration
def explore_account(username: str, save: bool = True) -> AccountConversationsResult:
    """
    Quick exploration of an account's conversations.

    Args:
        username: Twitter username (without @)
        save: Whether to save the output to a file

    Returns:
        AccountConversationsResult with all data
    """
    result = get_account_conversations(username=username)

    if save:
        save_account_conversations(result)

    return result
