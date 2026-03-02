"""Path constants and environment loading for the pipeline."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Data lives in scratchpads/data/ — we never move it
DATA_DIR = PROJECT_ROOT / "scratchpads" / "data"
TOP_IDS_PATH = DATA_DIR / "top_quoted_tweet_ids.json"
STRANDS_DIR = DATA_DIR / "strands"
RATED_DIR = DATA_DIR / "rated_strands"
DEBUG_DIR = DATA_DIR / "debug_responses"
QUOTED_COUNTS_CACHE_PATH = DATA_DIR / "quoted_counts_cache.parquet"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "strand_summary_embeddings.json"
LABEL_CONFIG_PATH = DATA_DIR / "strand_label_config.json"
ATLAS_PARQUET_PATH = DATA_DIR / "tweet_embeddings_atlas.parquet"
TWEET_EMBEDDINGS_DIR = DATA_DIR / "all_tweet_embeddings"
VALID_ACCOUNTS_PATH = DATA_DIR / "valid_account_ids_cache.json"
ALL_SUMMARIES_PATH = DATA_DIR / "all_summaries_chronological.txt"

# Frontend export paths
FRONTEND_PUBLIC_DIR = PROJECT_ROOT / "bangers" / "public"
ATLAS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "atlas_data.json"
HISTOGRAM_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_histograms.json"
SEMANTIC_MAP_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strand_semantic_map.json"
SERIATION_ORDER_PATH = FRONTEND_PUBLIC_DIR / "strand_seriation_order.json"
STRANDS_DATA_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "strands_data.json"
BANGERS_EXPORT_PATH = FRONTEND_PUBLIC_DIR / "bangers_tweets.json"
