# %%
"""
Relation Genesis - Export pair interaction samples

This script exports first interactions for random user pairs to individual files.
Each file contains conversation trees and A->B->A patterns.
"""

import sys
from pathlib import Path

# Handle notebook vs script context
try:
    SCRATCHPADS_DIR = Path(__file__).parent
except NameError:
    SCRATCHPADS_DIR = Path.cwd()
    if SCRATCHPADS_DIR.name != 'scratchpads':
        SCRATCHPADS_DIR = SCRATCHPADS_DIR / 'scratchpads'

# Ensure lib is importable
if str(SCRATCHPADS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRATCHPADS_DIR))

from lib.strand_caches import load_caches
from lib.serendipity import (
    get_or_build_interaction_history,
    export_pair_files,
)

# %%
# Load data
print("Loading caches...")
tweet_dict, conversation_trees = load_caches(auto_generate=False)
print(f"Loaded {len(tweet_dict)} tweets and {len(conversation_trees)} conversation trees")

# %%
# Get or build interaction history
pair_history = get_or_build_interaction_history(tweet_dict)

# %%
# Run the export
selected_pairs = export_pair_files(
    pair_history, 
    tweet_dict, 
    conversation_trees,
    num_pairs=20,  # Set to None for all valid pairs
    seed=42
)

# %%
print(f"\nExported {len(selected_pairs)} pairs:")
for user_a, user_b in selected_pairs[:20]:  # Show first 20
    print(f"  @{user_a} <-> @{user_b}")

# %%
