"""Phase 7: Generate chronological summary text file."""

from pipeline.config import ALL_SUMMARIES_PATH
from pipeline.helpers import load_all_rated_strands


def run() -> bool:
    """Generate a single text file with all strand summaries in chronological order."""
    print("\n" + "=" * 60)
    print("PHASE 7: Generate Chronological Summary")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    if not all_strands:
        print("[ERROR] No rated strands found")
        return False

    # Sort by tweet ID numerically (tweet IDs are chronologically ordered)
    sorted_ids = sorted(all_strands.keys(), key=lambda x: int(x))

    lines = []
    total = len(sorted_ids)

    for idx, strand_id in enumerate(sorted_ids, 1):
        data = all_strands[strand_id]

        title = data.get("title", "Untitled")
        summary = data.get("summary", "")
        rating_obj = data.get("rating", {})
        histogram = data.get("histogram", {})

        if isinstance(rating_obj, dict):
            rating_num = rating_obj.get("rating", "?")
            evolution = rating_obj.get("evolution", "?")
            cohesion = rating_obj.get("cohesion", "?")
            utility = rating_obj.get("utility", "?")
            reasoning = rating_obj.get("reasoning_summary", "")
            essential_tweets = rating_obj.get("essential_tweets", [])
        else:
            rating_num = "?"
            evolution = cohesion = utility = "?"
            reasoning = ""
            essential_tweets = []

        total_tweets = histogram.get("total_tweets", 0)

        lines.append(f"═══ [{idx}/{total}] ═══")
        lines.append(f"ID: {strand_id}")
        lines.append(f"TITLE: {title}")
        lines.append(f"RATING: {rating_num}/10 | Evolution: {evolution} | Cohesion: {cohesion} | Utility: {utility} | TWEETS: {total_tweets}")
        lines.append("")
        lines.append(f"SUMMARY: {summary}")
        lines.append("")

        if reasoning:
            lines.append(f"REASONING: {reasoning}")
            lines.append("")

        if essential_tweets:
            lines.append(f"ESSENTIAL TWEETS ({len(essential_tweets)}):")
            for et in essential_tweets:
                tweet_id = et.get("tweet_id", "?")
                annotation = et.get("annotation", "")
                lines.append(f"  • {tweet_id}: {annotation}")
            lines.append("")

        lines.append("─" * 80)
        lines.append("")

    with open(ALL_SUMMARIES_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"Exported {total} strand summaries to {ALL_SUMMARIES_PATH}")
    return True
