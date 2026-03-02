"""Phase 4.5 + 4.6: Generate tweet embeddings and atlas parquet (UMAP)."""

import json
import re

from pipeline.config import TWEET_EMBEDDINGS_DIR, ATLAS_PARQUET_PATH
from pipeline.helpers import load_all_rated_strands
from pipeline.lib.parallel import parallel_map_to_dict


def _extract_tweet_ids_from_thread(thread_text: str) -> list[int]:
    """Extract all tweet IDs from thread_text."""
    tweet_ids = []
    pattern = re.compile(r'^[│├└─\s]*(\d{15,})\s+\[')
    for line in thread_text.split('\n'):
        match = pattern.match(line)
        if match:
            tweet_ids.append(int(match.group(1)))
    return tweet_ids


def _parse_tweet_from_thread(thread_text: str, tweet_id: int) -> dict | None:
    """Extract tweet text, date, likes, retweets from thread_text by tweet_id."""
    tweet_id_str = str(tweet_id)
    lines = thread_text.split('\n')

    header_pattern = re.compile(rf'^[│├└─\s]*{tweet_id_str}\s+\[')
    start_idx = None
    for i, line in enumerate(lines):
        if header_pattern.match(line):
            start_idx = i
            break

    if start_idx is None:
        return None

    header_line = lines[start_idx]

    date_match = re.search(rf'{tweet_id_str}\s+\[([0-9-]+)\]', header_line)
    date = date_match.group(1) if date_match else None

    stats_match = re.search(r'💜\s+(\d+)\s+🔁\s+(\d+)', header_line)
    likes = int(stats_match.group(1)) if stats_match else None
    retweets = int(stats_match.group(2)) if stats_match else None

    prefix_match = re.match(rf'^([│├└─\s]*){tweet_id_str}', header_line)
    tree_prefix = prefix_match.group(1) if prefix_match else ""

    content_lines = []
    next_tweet_pattern = re.compile(r'^[│├└─\s]*\d{15,}\s+\[')
    separators = {'===', '↓'}

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped_line = line[len(tree_prefix):] if tree_prefix and line.startswith(tree_prefix) else line
        stripped = stripped_line.strip()

        if stripped in separators:
            break
        if next_tweet_pattern.match(line):
            break
        if re.match(r'^[│\s]*[├└]──\s*\d{15,}\s+\[', line):
            break

        content_lines.append(stripped)

    text = '\n'.join(content_lines).strip()
    text = re.sub(r'\n{3,}', '\n\n', text)

    return {
        'text': text.strip(),
        'date': date,
        'likes': likes,
        'retweets': retweets,
    }


def _clean_tweet_text(text: str) -> str:
    """Clean tweet text for embedding."""
    text = re.sub(r'^[│├└─\s]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^(@\w+\s*)+', '', text.strip())
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'↓', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _build_embedding_text(tweet_text: str, annotation: str = None) -> str | None:
    """Combine tweet text and annotation for embedding."""
    cleaned = _clean_tweet_text(tweet_text)
    if len(cleaned) < 10:
        return None

    if annotation:
        return f"Tweet:\n{cleaned}\n\nAnnotation:\n{annotation}"
    return f"Tweet:\n{cleaned}"


def run_tweet_embeddings(
    max_workers: int = 32,
    force_regenerate: bool = False,
) -> int:
    """Generate per-tweet embeddings for atlas visualization using parallel processing."""
    import os
    from openai import OpenAI

    print("\n" + "=" * 60)
    print("PHASE 4.5: Generate Tweet Embeddings")
    print("=" * 60)

    TWEET_EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    all_strands = load_all_rated_strands()
    existing = {int(p.stem) for p in TWEET_EMBEDDINGS_DIR.glob("*.json") if p.stem.isdigit()}

    if force_regenerate:
        pending = list(all_strands.keys())
    else:
        pending = [sid for sid in all_strands.keys() if sid not in existing]

    print(f"Found {len(all_strands)} rated strands, {len(existing)} already have tweet embeddings")
    print(f"Processing {len(pending)} strands with {max_workers} parallel workers")

    if not pending:
        print("All strands already have tweet embeddings!")
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[ERROR] OPENROUTER_API_KEY not found")
        return 0

    EMBEDDING_MODEL = "openai/text-embedding-3-large"

    def process_single_strand(strand_id: int) -> bool:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                all_embeddings.extend([d.embedding for d in response.data])
            return all_embeddings

        strand = all_strands[strand_id]
        thread_text = strand.get("thread_text", "")
        if not thread_text:
            return False

        essential_lookup = {}
        if "rating" in strand and "essential_tweets" in strand["rating"]:
            for et in strand["rating"]["essential_tweets"]:
                tid = str(et.get("tweet_id", ""))
                essential_lookup[tid] = et.get("annotation", "")

        tweet_ids = _extract_tweet_ids_from_thread(thread_text)
        tweets_to_embed = []

        for tid in tweet_ids:
            parsed = _parse_tweet_from_thread(thread_text, tid)
            if not parsed or not parsed["text"]:
                continue

            tid_str = str(tid)
            is_essential = tid_str in essential_lookup
            is_root = tid_str == str(strand_id)
            annotation = essential_lookup.get(tid_str)

            text_to_embed = _build_embedding_text(parsed["text"], annotation)
            if text_to_embed is None:
                continue

            tweet_type = "regular"
            if is_root and is_essential:
                tweet_type = "root_essential"
            elif is_root:
                tweet_type = "root_regular"
            elif is_essential:
                tweet_type = "essential"

            tweets_to_embed.append({
                "tweet_id": tid_str,
                "annotation": annotation,
                "tweet_text": _clean_tweet_text(parsed["text"]),
                "text_to_embed": text_to_embed,
                "tweet_type": tweet_type,
                "date": parsed["date"],
                "likes": parsed["likes"],
                "retweets": parsed["retweets"],
            })

        if not tweets_to_embed:
            return False

        texts = [t["text_to_embed"] for t in tweets_to_embed]
        embeddings = get_embeddings_batch(texts)

        results = []
        for i, tweet in enumerate(tweets_to_embed):
            results.append({
                "tweet_id": tweet["tweet_id"],
                "annotation": tweet["annotation"],
                "tweet_text": tweet["tweet_text"],
                "text_embedded": tweet["text_to_embed"],
                "tweet_type": tweet["tweet_type"],
                "date": tweet["date"],
                "likes": tweet["likes"],
                "retweets": tweet["retweets"],
                "embedding": embeddings[i],
            })

        output = {
            "seed_tweet_id": str(strand_id),
            "model": EMBEDDING_MODEL,
            "all_tweet_embeddings": results,
        }
        with open(TWEET_EMBEDDINGS_DIR / f"{strand_id}.json", "w") as f:
            json.dump(output, f)

        return True

    results, failed = parallel_map_to_dict(
        pending,
        process_single_strand,
        max_workers=max_workers,
        desc="Generating tweet embeddings"
    )

    processed = sum(1 for v in results.values() if v)
    if failed:
        print(f"[WARN] {len(failed)} strands failed to process")
    print(f"Generated tweet embeddings for {processed} strands")
    return processed


def run_atlas_parquet(force_regenerate: bool = False) -> bool:
    """Run UMAP on tweet embeddings and save to parquet for atlas."""
    import numpy as np
    import pandas as pd
    import umap

    print("\n" + "=" * 60)
    print("PHASE 4.6: Generate Atlas Parquet")
    print("=" * 60)

    if not force_regenerate and ATLAS_PARQUET_PATH.exists():
        embedding_files = list(TWEET_EMBEDDINGS_DIR.glob("*.json"))
        if embedding_files:
            newest_embedding = max(f.stat().st_mtime for f in embedding_files)
            parquet_mtime = ATLAS_PARQUET_PATH.stat().st_mtime
            if parquet_mtime > newest_embedding:
                print("Atlas parquet is up to date, skipping")
                return True

    embedding_files = sorted(TWEET_EMBEDDINGS_DIR.glob("*.json"))
    if not embedding_files:
        print("[ERROR] No tweet embedding files found")
        return False

    print(f"Loading embeddings from {len(embedding_files)} files...")

    all_embeddings = []
    all_metadata = []

    from tqdm import tqdm
    for filepath in tqdm(embedding_files, desc="Loading embeddings"):
        with open(filepath) as f:
            data = json.load(f)

        strand_id = data["seed_tweet_id"]
        embeddings_data = data.get("all_tweet_embeddings", [])

        for item in embeddings_data:
            all_embeddings.append(item["embedding"])
            all_metadata.append({
                "tweet_id": item["tweet_id"],
                "strand_id": strand_id,
                "annotation": item.get("annotation", "") or "",
                "tweet_type": item.get("tweet_type", "unknown"),
                "text": item.get("text_embedded", item.get("tweet_text", "")),
                "date": item.get("date"),
                "likes": item.get("likes"),
                "retweets": item.get("retweets"),
            })

    print(f"Loaded {len(all_embeddings)} tweet embeddings from {len(embedding_files)} strands")

    if len(all_embeddings) < 2:
        print("[ERROR] Need at least 2 embeddings for UMAP")
        return False

    print("Running UMAP projection...")
    X = np.array(all_embeddings)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=10,
        min_dist=0.1,
        random_state=42,
        verbose=True,
    )
    embedding_2d = reducer.fit_transform(X)

    df = pd.DataFrame(all_metadata)
    df["projection_x"] = embedding_2d[:, 0]
    df["projection_y"] = embedding_2d[:, 1]
    df["is_essential"] = df["tweet_type"].isin(["essential", "root_essential"])
    df["is_root"] = df["tweet_type"].isin(["root_essential", "root_regular"])

    df.to_parquet(ATLAS_PARQUET_PATH, index=False)
    print(f"Saved atlas parquet: {ATLAS_PARQUET_PATH}")
    print(f"  {len(df)} tweets from {df['strand_id'].nunique()} strands")

    return True
