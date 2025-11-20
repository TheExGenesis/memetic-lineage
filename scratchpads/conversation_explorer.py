# %%
import pandas as pd
import numpy as np
from collections import defaultdict
from typing import TypedDict, Optional, Annotated
from pandas import DataFrame
from datetime import datetime
from dataclasses import dataclass
from typing import (
    Dict,
    Tuple,
    List,
    Callable,
    Any,
    Union,
    Optional,
    TypedDict,
    Set,
)

import tqdm


class EnrichedTweet(TypedDict):
    tweet_id: int
    account_id: int
    username: str
    created_at: datetime
    full_text: str
    retweet_count: int
    favorite_count: int
    reply_to_tweet_id: Optional[int]
    reply_to_user_id: Optional[int]
    reply_to_username: Optional[str]
    conversation_id: Optional[int]
    account_display_name: Optional[str]
    avatar_media_url: Optional[str]
    archive_upload_id: Optional[str]
    quoted_tweet_id: Optional[int]
    quoted_count: Optional[int]


# Type aliases for each stage
EnrichedTweetDF = Annotated[DataFrame, EnrichedTweet]


class ConversationTree(TypedDict):
    root: int
    children: Dict[int, List[int]]
    parents: Dict[int, int]
    paths: Dict[int, List[int]]


def build_conversation_trees(
    tweets: List[EnrichedTweet]
) -> Dict[int, ConversationTree]:
    """
    Organize tweets into conversation trees. Takes only tweets with conversation_id not None.
    Returns dict of conversation_id -> {
        'root': tweet_id of root,
        'children': dict of tweet_id -> list of child tweet_ids,
        'parents': dict of tweet_id -> parent tweet_id,
        'paths': dict of leaf_id -> list of tweet_ids from root to leaf
    }
    """
    print(f"Building trees from {len(tweets)} conversation tweets")
    conversations: Dict[int, ConversationTree] = {}

    # Organize tweets by conversation
    for tweet in tqdm.tqdm(tweets, desc="Building conversations"):
        conv_id = tweet["conversation_id"]
        if conv_id is None:
            raise ValueError(f"Conversation ID is None for tweet {tweet['tweet_id']}")
        if conv_id is not None and conv_id not in conversations:
            conversations[conv_id] = {  
                "children": defaultdict(list),
                "parents": {},
                "root": None,
                "paths": {},
            }

        tweet_id = tweet["tweet_id"]

        reply_to = tweet.get("reply_to_tweet_id")
        if reply_to:
            conversations[conv_id]["children"][reply_to].append(tweet_id)
            conversations[conv_id]["parents"][tweet_id] = reply_to
        else:
            conversations[conv_id]["root"] = tweet_id

    # Build paths iteratively
    for conv in tqdm.tqdm(conversations.values(), desc="Building paths"):
        root = conv["root"]
        if not root:
            continue

        visited = set()  # Track visited tweet IDs
        stack = [(root, [root])]

        while stack:
            current_id, path = stack.pop()
            children = conv["children"].get(current_id, [])

            if not children:
                conv["paths"][current_id] = path
            else:
                # Only process unvisited children
                unvisited = [c for c in children if c not in visited]
                if unvisited:
                    for child_id in unvisited:
                        visited.add(child_id)
                        stack.append((child_id, path + [child_id]))

    # After building paths
    total_paths = sum(len(conv["paths"]) for conv in conversations.values())
    print(
        f"Built {total_paths} conversation paths across {len(conversations)} trees"
    )
    return conversations


def build_incomplete_conversation_trees(
    found_tweets: List[EnrichedTweet], found_liked: List[EnrichedTweet]
) -> Dict[int, ConversationTree]:
    """
    Build conversation trees from incomplete reply chains.

    Args:
        found_tweets: list of tweet data
        found_liked: list of liked tweet data

    Returns:
        Dict of root_id -> {
            'root': root_id,
            'children': dict of tweet_id -> list of child ids,
            'parents': dict of tweet_id -> parent id,
            'paths': dict of leaf_id -> list of tweet_ids from root to leaf
        }
    """
    # Combine tweets and build parent relationships
    all_tweets = {tweet["tweet_id"]: tweet for tweet in found_tweets + found_liked}
    parents = {}
    children = defaultdict(list)
    visited = set()  # Track visited nodes to prevent cycles

    # Build parent/child relationships with cycle check
    for tweet in tqdm.tqdm(found_tweets, desc="Building parent/child relationships"):
        tweet_id = tweet["tweet_id"]
        reply_to = tweet.get("reply_to_tweet_id")
        if reply_to and reply_to in all_tweets:
            if reply_to not in visited and tweet_id not in visited:
                parents[tweet_id] = reply_to
                children[reply_to].append(tweet_id)
                visited.update({tweet_id, reply_to})

    # Find roots (tweets with no parents that exist in our data)
    found_tweet_ids = {tweet["tweet_id"] for tweet in found_tweets}
    roots = {
        tid: tweet
        for tid, tweet in all_tweets.items()
        if tid not in parents and tid in found_tweet_ids
    }

    trees = {}
    # Build tree for each root with depth limit
    for i, root_id in tqdm.tqdm(enumerate(roots), desc="Building trees", total=len(roots)):
        tree = {
            "root": root_id,
            "children": defaultdict(list),
            "parents": {},
            "paths": {},
        }

        # BFS with cycle protection and depth limit
        from collections import deque
        queue = deque([(root_id, [root_id], 0)])
        while queue:
            current_id, path, depth = queue.popleft()

            # Safety against infinite loops
            if depth > 100:  # Max depth for any reasonable conversation
                print(f"Max depth reached at {current_id}")
                break

            # Process children with cycle check
            for child_id in children.get(current_id, []):
                if child_id not in tree["parents"]:  # Prevent re-parenting
                    tree["parents"][child_id] = current_id
                    tree["children"][current_id].append(child_id)
                    queue.append((child_id, path + [child_id], depth + 1))

            # Record path if leaf node
            if not children.get(current_id):
                tree["paths"][current_id] = path

        trees[root_id] = tree

    print(f"Built {len(trees)} incomplete trees")
    return trees

# %%

def build_quote_trees(tweets: List[EnrichedTweet]) -> Dict[int, ConversationTree]:
    """Build trees of quote tweet relationships.
    
    Args:
        tweets: List of tweets with quoted_tweet_id field
        
    Returns:
        Dict of root_id -> ConversationTree for quote relationships
    """
    print("Building quote trees...")
    
    # Build quote relationships
    all_tweets = {tweet["tweet_id"]: tweet for tweet in tweets}
    parents = {}
    children = defaultdict(list)
    
    # Build parent/child relationships for quotes
    for tweet in tqdm.tqdm(tweets, desc="Building quote relationships"):
        tweet_id = tweet["tweet_id"]
        quoted_id = tweet.get("quoted_tweet_id")
        
        if quoted_id in all_tweets:
            parents[tweet_id] = quoted_id
            children[quoted_id].append(tweet_id)
    
    # Find roots (tweets with no parents)
    roots = [tid for tid in children.keys() if tid not in parents]
    
    trees = {}
    # Build tree for each root
    for root_id in tqdm.tqdm(roots, desc="Building trees", total=len(roots)):
        tree = {
            "root": root_id,
            "children": defaultdict(list),
            "parents": {},
            "paths": {},
        }
        
        # BFS to build tree
        from collections import deque
        queue = deque([(root_id, [root_id], 0)])
        while queue:
            current_id, path, depth = queue.popleft()
            
            # Safety against infinite loops
            if depth > 100:
                print(f"Max depth reached at {current_id}")
                break
            
            # Process children
            for child_id in children.get(current_id, []):
                if child_id not in tree["parents"]:
                    tree["parents"][child_id] = current_id
                    tree["children"][current_id].append(child_id)
                    queue.append((child_id, path + [child_id], depth + 1))

            # Record path if leaf node
            if not children.get(current_id):
                tree["paths"][current_id] = path
        
        trees[root_id] = tree
    
    print(f"Built {len(trees)} quote trees")
    return trees


def print_conversation_threads(
    tweet_ids: List[int],
    conversation_trees: Dict[int, ConversationTree],
    tweets: Dict[int, EnrichedTweet],
    depth: int = 5
) -> str:
    """
    Efficiently print conversation threads for a list of tweet IDs.
    
    Args:
        tweet_ids: List of tweet IDs to display threads for
        conversation_trees: Pre-computed conversation trees
        tweets: Dictionary of tweet data keyed by tweet_id
        depth: Depth limit for displaying threads (ancestors or descendants)
        
    Returns:
        String representation of the threads formatted like 'tree' command
    """
    output_lines = []
    
    # Pre-filter: map conversation_id -> set of relevant tweet_ids
    conv_to_targets = defaultdict(set)
    for tid in tweet_ids:
        if tid not in tweets:
            continue
        conv_id = tweets[tid].get("conversation_id")
        # If conv_id exists and we have a tree for it
        if conv_id and conv_id in conversation_trees:
            conv_to_targets[conv_id].add(tid)
        else:
            # For standalone tweets or those without trees, we can skip 
            # or handle them if needed. The request focuses on threads.
            pass 

    # Sort conversations to make output deterministic
    sorted_conv_ids = sorted(conv_to_targets.keys())

    for conv_id in sorted_conv_ids:
        target_ids = conv_to_targets[conv_id]
        tree = conversation_trees[conv_id]
        
        # 1. Identify all nodes to display for this conversation
        nodes_to_show = set()
        
        for tid in target_ids:
            # Always include the target itself
            nodes_to_show.add(tid)
            
            if tid == tree["root"]:
                # If target is root, show whole thread down to depth
                queue = [(tid, 0)]
                while queue:
                    curr, curr_depth = queue.pop(0)
                    if curr_depth < depth:
                        children = tree["children"].get(curr, [])
                        for child in children:
                            if child not in nodes_to_show:
                                nodes_to_show.add(child)
                                queue.append((child, curr_depth + 1))
            else:
                # If target is reply, show path to root (upwards) up to depth
                curr = tid
                d = 0
                while d < depth:
                    parent = tree["parents"].get(curr)
                    if parent is None:
                        break
                    nodes_to_show.add(parent)
                    curr = parent
                    d += 1
        
        # 2. Identify "display roots" for this partial tree
        # A display root is a node in nodes_to_show whose parent is NOT in nodes_to_show
        display_roots = []
        for node in nodes_to_show:
            parent = tree["parents"].get(node)
            if parent is None or parent not in nodes_to_show:
                display_roots.append(node)
        
        display_roots.sort() 
        
        # 3. Render each component
        for root in display_roots:
            output_lines.extend(_render_tree_node(root, nodes_to_show, tree, tweets))
            output_lines.append("") 

    return "\n".join(output_lines)


def _render_tree_node(
    node_id: int,
    visible_nodes: Set[int],
    tree: ConversationTree,
    tweets: Dict[int, EnrichedTweet],
    prefix: str = "",
    is_last_child: bool = True,
    is_root_of_view: bool = True
) -> List[str]:
    lines = []
    tweet = tweets.get(node_id)
    if not tweet:
        return []

    # Prepare node content
    stats_parts = []
    if tweet.get("favorite_count"):
        stats_parts.append(f"💜 {tweet['favorite_count']}")
    if tweet.get("retweet_count"):
        stats_parts.append(f"🔁 {tweet['retweet_count']}")
    if tweet.get("quoted_count"):
        stats_parts.append(f"💬 {tweet['quoted_count']}")
    
    stats_str = " ".join(stats_parts)
    username = tweet.get("username", "unknown")
    
    # Handle quoted text
    quoted_text_block = []
    q_id = tweet.get("quoted_tweet_id")
    if q_id is not None:
        q_tweet = tweets.get(q_id)
        if q_tweet:
            q_text = q_tweet.get("full_text", "").replace("\n", " ")
            quoted_text_block.append(f"  [Quoting @{q_tweet.get('username')}: {q_text}]")
        else:
             quoted_text_block.append(f"  [Quoting Tweet {q_id} (missing)]")

    # Format main text
    full_text = tweet.get("full_text", "")
    text_lines = full_text.split("\n")
    
    connector = ""
    if not is_root_of_view:
        connector = "└── " if is_last_child else "├── "
    
    header = f"{connector}{node_id} @{username} {stats_str}"
    lines.append(prefix + header)
    
    # Determine indentation for content and children
    if is_root_of_view:
        child_prefix = prefix
        content_prefix = prefix
    else:
        child_prefix = prefix + ("    " if is_last_child else "│   ")
        content_prefix = child_prefix 
    
    for line in text_lines:
        lines.append(f"{content_prefix}{line}")
        
    for q_line in quoted_text_block:
        lines.append(f"{content_prefix}{q_line}")
        
    # Process children
    children = [c for c in tree["children"].get(node_id, []) if c in visible_nodes]
    children.sort()
    
    for i, child in enumerate(children):
        is_last = (i == len(children) - 1)
        lines.extend(_render_tree_node(
            child, 
            visible_nodes, 
            tree, 
            tweets, 
            child_prefix, 
            is_last, 
            is_root_of_view=False
        ))
        
    return lines



# %%
