# %%
import pandas as pd
import numpy as np
from collections import defaultdict

class ConversationExplorer:
    def __init__(self, tweets_df: pd.DataFrame):
        # 1. Pre-index the dataframe for O(1) lookups (Critical for performance)
        print("Indexing tweets...")
        self.df = tweets_df.set_index('tweet_id')
        
        # 2. Pre-build adjacency list for O(1) child lookup
        # This avoids filtering the whole DF to find replies
        print("Building conversation graph...")
        self.children_map = defaultdict(list)
        
        # Vectorized approach is faster than iterating rows
        if 'reply_to_tweet_id' in tweets_df.columns:
             # Filter for rows that are replies and not NA
             # We specifically select columns to avoid overhead
             replies = tweets_df[tweets_df['reply_to_tweet_id'].notna()][['tweet_id', 'reply_to_tweet_id']]
             
             # Iterate over the filtered DataFrame (much smaller than 300k if not all are replies)
             for tid, parent_id in zip(replies['tweet_id'], replies['reply_to_tweet_id']):
                 self.children_map[int(parent_id)].append(tid)

    def print_tree(self, 
                   tweet_ids, 
                   depth_up: int | None = None, 
                   depth_down: int | None = None, 
                   debug: bool = False,
                   _visited_annexes: set | None = None,
                   _printed_ids: set | None = None) -> str:
        
        if _visited_annexes is None: _visited_annexes = set()
        if _printed_ids is None: _printed_ids = set()
        
        # Normalize input
        if isinstance(tweet_ids, (int, float, str, np.integer)):
            tweet_ids = [int(tweet_ids)]
        else:
            tweet_ids = [int(tid) for tid in tweet_ids]
            
        valid_seeds = [tid for tid in tweet_ids if tid in self.df.index]
        if not valid_seeds: return "No valid tweet IDs found."

        # Group seeds by conversation ID
        seeds_by_conv = defaultdict(list)
        for tid in valid_seeds:
            conv_id = self.df.loc[tid].get('conversation_id')
            if pd.notna(conv_id):
                seeds_by_conv[int(conv_id)].append(tid)
            else:
                seeds_by_conv[tid].append(tid)

        lines = []
        annex_ids_to_process = []

        for conv_id, conv_seeds in sorted(seeds_by_conv.items()):
            # Determine visible set using graph traversal (BFS/DFS) with pre-computed maps
            visible_ids = set()
            
            def traverse_up(curr_id, steps_left):
                if curr_id not in self.df.index: return
                visible_ids.add(curr_id)
                if steps_left is not None and steps_left <= 0: return
                
                parent_id = self.df.loc[curr_id].get('reply_to_tweet_id')
                if pd.notna(parent_id):
                    traverse_up(int(parent_id), None if steps_left is None else steps_left - 1)

            def traverse_down(curr_id, steps_left):
                visible_ids.add(curr_id)
                if steps_left is not None and steps_left <= 0: return
                
                # O(1) lookup instead of filtering
                children = self.children_map.get(curr_id, [])
                for child_id in children:
                    if child_id in self.df.index: # Ensure child exists in data
                         traverse_down(child_id, None if steps_left is None else steps_left - 1)

            for seed in conv_seeds:
                traverse_up(seed, depth_up)
                traverse_down(seed, depth_down)

            _printed_ids.update(visible_ids)

            # Identify roots of the *visible* forest
            print_roots = []
            for vid in visible_ids:
                parent = self.df.loc[vid].get('reply_to_tweet_id')
                # If parent is missing or parent is not in the visible set, this is a root
                if pd.isna(parent) or int(parent) not in visible_ids:
                    print_roots.append(vid)
            print_roots.sort()

            def print_quote(q_id, indent):
                if q_id not in self.df.index:
                    lines.append(f"{indent}[Quoted tweet {q_id} not found]")
                    return
                    
                row = self.df.loc[q_id]
                username = row.get('username') or "unknown"
                text = row.get('full_text') or ""
                created_at = row.get('created_at')
                date = pd.Timestamp(created_at).strftime('%Y-%m-%d') if pd.notna(created_at) else "?"
                
                lines.append(f"{indent}@{username} ({date}) [Quoted id:{q_id}]:")
                for line in text.split('\n'):
                    lines.append(f"{indent}  {line}")
                
                need_annex = True
                if depth_up == 0 and depth_down == 0:
                    need_annex = False
                
                if q_id in _printed_ids:
                    need_annex = False
                    
                if need_annex:
                    lines.append(f"{indent}(See Annex below for full context)")
                    if q_id not in _visited_annexes:
                         annex_ids_to_process.append(q_id)
                         _visited_annexes.add(q_id)
                
                next_q = row.get('quoted_tweet_id')
                if pd.notna(next_q):
                    print_quote(int(next_q), indent + "    ┃ ")

            def format_node(tid, depth, prefix, is_last_child):
                row = self.df.loc[tid]
                created_at = row.get('created_at')
                pretty_date = pd.Timestamp(created_at).strftime('%Y-%m-%d %H:%M') if pd.notna(created_at) else "unknown"
                username = row.get('username') or "unknown"
                full_text = row.get('full_text') or ""
                
                metrics = f"❤️ {row.get('favorite_count', 0)} 🔁 {row.get('retweet_count', 0)}"
                quoted_cnt = row.get('quoted_count', 0)
                if pd.notna(quoted_cnt) and quoted_cnt > 0:
                     metrics += f" 💬 {int(quoted_cnt)}"
                     
                if depth == 0:
                    curr_prefix = ""
                    child_prefix = "" 
                else:
                    curr_prefix = prefix + ("└── " if is_last_child else "├── ")
                    child_prefix = prefix + ("    " if is_last_child else "│   ")
                    
                lines.append(f"{curr_prefix}@{username} ({pretty_date}) {metrics} [id:{tid}]")
                
                text_indent = child_prefix + ("    " if depth == 0 else "") 
                if depth == 0: text_indent = "    "
                
                for line in full_text.split('\n'):
                    lines.append(f"{text_indent}{line}")
                    
                quoted_id = row.get('quoted_tweet_id')
                if pd.notna(quoted_id):
                    quoted_id = int(quoted_id)
                    print_quote(quoted_id, text_indent + "    ┃ ")
                    
                # Use pre-built children map
                children = [c for c in self.children_map.get(tid, []) if c in visible_ids]
                children.sort()
                
                for i, child in enumerate(children):
                    is_last = (i == len(children) - 1)
                    next_prefix = prefix + ("    " if is_last_child else "│   ")
                    if depth == 0: next_prefix = "" 
                    format_node(child, depth + 1, next_prefix, is_last)

            if not print_roots:
                lines.append("No visible tweets found.")

            for root in print_roots:
                format_node(root, 0, "", True)
                lines.append("") 

        # Process Annexes (Recursive call to method)
        for annex_id in annex_ids_to_process:
            lines.append(f"\n>>> Annex: Context for Quoted Tweet {annex_id} <<<")
            # Call the method on self
            annex_text = self.print_tree(
                [annex_id], 
                depth_up=depth_up, 
                depth_down=depth_down, 
                debug=debug,
                _visited_annexes=_visited_annexes,
                _printed_ids=_printed_ids
            )
            lines.append(annex_text)

        return "\n".join(lines)



# %%
def count_quotes(tweets_df):
    """
    Count how many times each tweet is quoted by others (excluding self-quotes).
    
    Args:
        tweets_df: DataFrame with columns 'quoted_tweet_id', 'tweet_id', 'account_id'
    
    Returns:
        DataFrame with columns 'quoted_tweet_id' and 'quoted_count', sorted by count descending
    """
    # Filter out self-quotes: only count quotes where the quoting user differs from the quoted tweet's author
    # First, get the account_id for each quoted tweet
    quoted_tweet_authors = tweets_df[['tweet_id', 'account_id']].rename(
        columns={'tweet_id': 'quoted_tweet_id', 'account_id': 'quoted_author_id'}
    )
    
    # Merge to get both the quoting user and the quoted tweet's author
    tweets_with_authors = tweets_df.merge(
        quoted_tweet_authors, 
        on='quoted_tweet_id', 
        how='left'
    )
    
    # Filter to only quotes where account_id != quoted_author_id (exclude self-quotes)
    non_self_quotes = tweets_with_authors[
        tweets_with_authors['account_id'] != tweets_with_authors['quoted_author_id']
    ]
    
    # Count number of times tweets are quoted (by others)
    quoted_counts = non_self_quotes.groupby('quoted_tweet_id').size().reset_index(
        name='quoted_count'
    ).sort_values(by='quoted_count', ascending=False)
    
    return quoted_counts
