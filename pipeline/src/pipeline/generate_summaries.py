"""Phase 3: Generate titles + summaries for rated strands."""

import json
import os

from openai import OpenAI

from pipeline.helpers import load_all_rated_strands, save_rated_strand
from pipeline.lib.parallel import parallel_map_to_dict


def _generate_summary_for_strand(strand_data: dict, model_name: str) -> dict:
    """Generate title and summary for a single strand."""
    from pydantic import BaseModel

    class StrandSummary(BaseModel):
        title: str
        summary: str

    SUMMARIZER_PROMPT = """You extract what's ACTUALLY INTERESTING from twitter discourse threads.

Given strand metadata and tweets, write:
1. A punchy title (max 60 chars) - think newsletter subject line, not academic paper
2. A summary (1-3 paragraphs) that:
   - Opens with the juiciest insight or most quotable take
   - Names specific people and their specific claims
   - Tracks the arc: what triggered it, what peaked, what died
   - Ends with why would someone care

Write like you're telling a friend about drama you witnessed. Dense, specific, zero fluff.

Output JSON with fields: title, summary"""

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

    data_for_llm = {
        "seed_tweet_id": strand_data["seed_tweet_id"],
        "rating": strand_data.get("rating", {}),
        "thread_text": strand_data.get("thread_text", "")
    }

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SUMMARIZER_PROMPT},
            {"role": "user", "content": f"<strand_data>\n{json.dumps(data_for_llm, indent=2)}\n</strand_data>"},
        ],
        temperature=0.7,
        max_completion_tokens=1024,
        response_format={"type": "json_object"},
    )

    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Empty response from LLM")

    parsed = json.loads(content.strip())
    return {
        "title": parsed.get("title", "Untitled"),
        "summary": parsed.get("summary", "")
    }


def run(
    model_name: str = "openai/gpt-4o-mini",
    max_workers: int = 32,
    force_regenerate: bool = False,
) -> int:
    """Generate summaries for strands missing title/summary. Updates rated_strands in-place."""
    print("\n" + "=" * 60)
    print("PHASE 3: Generate Summaries")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    # Find strands missing summaries
    pending = []
    for strand_id, data in all_strands.items():
        if force_regenerate or not data.get("title") or not data.get("summary"):
            pending.append(strand_id)

    print(f"Found {len(pending)} strands needing summaries")

    if not pending:
        print("All strands have summaries!")
        return 0

    def process_one(strand_id: int) -> dict:
        data = all_strands[strand_id]
        result = _generate_summary_for_strand(data, model_name)
        data["title"] = result["title"]
        data["summary"] = result["summary"]
        save_rated_strand(strand_id, data)
        return result

    results, failed = parallel_map_to_dict(
        pending, process_one,
        max_workers=max_workers,
        desc="Generating summaries"
    )

    if failed:
        print(f"[WARN] {len(failed)} strands failed: {list(failed.keys())[:5]}...")

    print(f"Generated summaries for {len(results)} strands")
    return len(results)
