# %%
import pandas as pd
import numpy as np
from collections import defaultdict
from typing import TypedDict, Optional, Annotated, List
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


def filter_conversation_trees(
    tweet_ids: List[int],
    conversation_trees: Dict[int, ConversationTree],
    tweet_dict: Dict[int, EnrichedTweet],
    depth: int = 5,
    depth_up: int | None = None,
    depth_from_root: int | None = None
) -> Dict[int, ConversationTree]:
    """
    Filter conversation trees to include only subtrees relevant to the given tweet IDs.
    
    Args:
        tweet_ids: List of tweet IDs to filter trees for
        conversation_trees: Pre-computed conversation trees
        tweet_dict: Dictionary of tweet data keyed by tweet_id
        depth: Depth limit for including descendants
        depth_up: Depth limit for including ancestors
        depth_from_root: Depth limit for including descendants from root
        
    Returns:
        Dict mapping conversation_id -> filtered ConversationTree
    """
    if depth_up is None:
        depth_up = depth
    if depth_from_root is None:
        depth_from_root = depth
    filtered_trees = {}
    
    # Pre-filter: map conversation_id -> set of relevant tweet_ids
    conv_to_targets = defaultdict(set)
    for tid in tweet_ids:
        if tid not in tweet_dict:
            continue
        conv_id = tweet_dict[tid].get("conversation_id")
        if conv_id and conv_id in conversation_trees:
            conv_to_targets[conv_id].add(tid)

    for conv_id, target_ids in conv_to_targets.items():
        tree = conversation_trees[conv_id]
        
        # Identify all nodes to include
        nodes_to_include = set()
        
        for tid in target_ids:
            nodes_to_include.add(tid)
            
            # Walk ancestors up to depth limit
            curr = tid
            ancestor_depth = 0
            while ancestor_depth < depth_up:
                parent = tree["parents"].get(curr)
                if parent is None:
                    break
                nodes_to_include.add(parent)
                curr = parent
                ancestor_depth += 1
            

            # Add descendants up to depth
            queue = [(tid, depth_from_root if tid in conversation_trees else depth)]
            while queue:
                curr, curr_depth = queue.pop(0)
                if curr_depth > 0:
                    for child in tree["children"].get(curr, []):
                        if child not in nodes_to_include:
                            nodes_to_include.add(child)
                            queue.append((child, curr_depth - 1))
        
        # Build filtered tree structure
        filtered_children = defaultdict(list)
        filtered_parents = {}
        
        for node in nodes_to_include:
            # Include parent relationship if parent is also in filtered set
            parent = tree["parents"].get(node)
            if parent is not None and parent in nodes_to_include:
                filtered_parents[node] = parent
                filtered_children[parent].append(node)
        
        # Determine root (original root if included, otherwise None)
        original_root = tree.get("root")
        filtered_root = original_root if original_root in nodes_to_include else None
        
        # Build paths for filtered tree
        filtered_paths = {}
        if filtered_root:
            visited = set()
            stack = [(filtered_root, [filtered_root])]
            while stack:
                current_id, path = stack.pop()
                children = filtered_children.get(current_id, [])
                if not children:
                    filtered_paths[current_id] = path
                else:
                    unvisited = [c for c in children if c not in visited]
                    if unvisited:
                        for child_id in unvisited:
                            visited.add(child_id)
                            stack.append((child_id, path + [child_id]))
        
        filtered_trees[conv_id] = {
            "root": filtered_root,
            "children": filtered_children,
            "parents": filtered_parents,
            "paths": filtered_paths,
        }
    
    return filtered_trees



# we want to pass a function as a parameter of _render_tree_node to render the header
def _render_header_default(tweet: EnrichedTweet) -> str:
    username = tweet.get("username", "unknown")
    
    # Format date
    date_str = ""
    created_at = tweet.get("created_at")
    if created_at:
        if hasattr(created_at, 'strftime'):
            date_str = created_at.strftime("%Y-%m-%d")
        else:
            # Fallback for string or other types
            date_str = str(created_at)[:10]
        
    # Prepare node content
    stats_parts = []
    if tweet.get("favorite_count"):
        stats_parts.append(f"💜 {tweet['favorite_count']}")
    if tweet.get("retweet_count"):
        stats_parts.append(f"🔁 {tweet['retweet_count']}")
    if tweet.get("quoted_count"):
        stats_parts.append(f"💬 {tweet['quoted_count']}")
    stats_str = " ".join(stats_parts)
        
    return f"{tweet['tweet_id']} [{date_str}] @{username} {stats_str}"


def strand_header_print_factory(seed_info: Dict[int, str]) -> Callable[[EnrichedTweet], str]:
    def print_header(tweet: EnrichedTweet) -> str:
        base = _render_header_default(tweet)
        seed_type_str = seed_info.get(tweet.get("tweet_id"), "")
        if seed_type_str:
            return f'{base} [(SEED) type={seed_type_str}]'
        else:
            return base
    return print_header


def render_conversation_trees(
    filtered_trees: Dict[int, ConversationTree],
    tweet_dict: Dict[int, EnrichedTweet],
    render_header: Callable[[EnrichedTweet], str] = _render_header_default
) -> str:
    """
    Render filtered conversation trees to a string representation.
    
    Args:
        filtered_trees: Dict mapping conversation_id -> filtered ConversationTree
        tweet_dict: Dictionary of tweet data keyed by tweet_id
        
    Returns:
        String representation of the threads formatted like 'tree' command
    """
    output_lines = []
    
    # Sort conversations to make output deterministic
    sorted_conv_ids = sorted(filtered_trees.keys())
    
    for conv_id in sorted_conv_ids:
        tree = filtered_trees[conv_id]
        
        # Collect all nodes in the filtered tree
        nodes_to_show = set(tree["parents"].keys())
        nodes_to_show.update(tree["parents"].values())
        for children_list in tree["children"].values():
            nodes_to_show.update(children_list)
        if tree["root"] is not None:
            nodes_to_show.add(tree["root"])
        
        # Identify display roots (nodes whose parent is not in filtered set)
        display_roots = []
        for node in nodes_to_show:
            parent = tree["parents"].get(node)
            if parent is None or parent not in nodes_to_show:
                display_roots.append(node)
        
        display_roots.sort()
        
        # Render each component
        for root in display_roots:
            output_lines.extend(_render_tree_node(root, nodes_to_show, tree, tweet_dict, render_header=render_header))
            output_lines.append("\n===\n")
    
    return "\n".join(output_lines)

def _render_tree_node(
    node_id: int,
    visible_nodes: Set[int],
    tree: ConversationTree,
    tweets: Dict[int, EnrichedTweet],
    prefix: str = "",
    is_last_child: bool = True,
    is_root_of_view: bool = True,
    render_header: Callable[[EnrichedTweet], str] = _render_header_default,
    is_linear_continuation: bool = False
) -> List[str]:
    lines = []
    tweet = tweets.get(node_id)
    if not tweet:
        return []

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
    if not is_root_of_view and not is_linear_continuation:
        connector = "└── " if is_last_child else "├── "
    
    header = f"{connector}{render_header(tweet)}"
    lines.append(prefix + header)
    
    # Determine indentation for content and children
    if is_root_of_view or is_linear_continuation:
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
    
    if len(children) == 1:
        lines.append(f"{content_prefix}↓")
        lines.extend(_render_tree_node(
            children[0], 
            visible_nodes, 
            tree, 
            tweets, 
            child_prefix, 
            is_last_child=True, 
            is_root_of_view=False,
            render_header=render_header,
            is_linear_continuation=True
        ))
    else:
        for i, child in enumerate(children):
            is_last = (i == len(children) - 1)
            lines.extend(_render_tree_node(
                child, 
                visible_nodes, 
                tree, 
                tweets, 
                child_prefix, 
                is_last, 
                is_root_of_view=False,
                render_header=render_header,
                is_linear_continuation=False
            ))
        
    return lines


def print_conversation_threads(
    tweet_ids: List[int],
    conversation_trees: Dict[int, ConversationTree],
    tweet_dict: Dict[int, EnrichedTweet],
    depth: int = 5,
    render_header: Callable[[EnrichedTweet], str] = _render_header_default
) -> str:
    """
    Efficiently print conversation threads for a list of tweet IDs.
    
    Args:
        tweet_ids: List of tweet IDs to display threads for
        conversation_trees: Pre-computed conversation trees
        tweet_dict: Dictionary of tweet data keyed by tweet_id
        depth: Depth limit for displaying threads (ancestors or descendants)
        
    Returns:
        String representation of the threads formatted like 'tree' command
    """
    filtered_trees = filter_conversation_trees(tweet_ids, conversation_trees, tweet_dict, depth)
    return render_conversation_trees(filtered_trees, tweet_dict, render_header=render_header)


# %%