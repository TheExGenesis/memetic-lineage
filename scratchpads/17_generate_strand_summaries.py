# %%
"""
Generate human-friendly summaries and titles for rated strands.

Loads rated strands, sends metadata (without thread_text) to an LLM,
and produces markdown summaries with titles. Saves to rated_strands_plus/
with all original data plus the new title and summary.
"""

import json
import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from lib.retry import with_retry, is_rate_limit_error
from lib.parallel import parallel_map_to_dict

load_dotenv(Path(__file__).parent.parent / ".env")

RATED_STRANDS_DIR = Path(__file__).parent / "data" / "rated_strands"
RATED_STRANDS_PLUS_DIR = Path(__file__).parent / "data" / "rated_strands_plus"

# %%
# Pydantic model for structured output

class StrandSummary(BaseModel):
    title: str  # One-line title for the strand
    summary: str  # Human-friendly markdown summary


SUMMARIZER_PROMPT = """You extract what's ACTUALLY INTERESTING from twitter discourse threads.

Given strand metadata and tweets, write:
1. A punchy title (max 60 chars) - think newsletter subject line, not academic paper
2. A summary (1-3 paragraphs) that:
   - Opens with the juiciest insight or most quotable take
   - Names specific people and their specific claims (not "critiques on discourse norms" but "slimepriestess: 'tpot playacts at having good dispute norms'")
   - Tracks the arc: what triggered it, what peaked, what died
   - Ends with why would someone care

Write like you're telling a friend about drama you witnessed. Dense, specific, zero fluff. If something is boring, skip it. Note that not all tweets are relevant to the strand, there may be noise.

BAD: "This strand showcases cyclical self-critique with high cohesion"
GOOD: "tpot spent 2 years asking 'are we frauds?' and the answer was always 'probably, but affectionately'"

CRITICAL: Your reasoning IS the voice. The summary should read like a cleaned-up version of your reasoning, not a formalization of it.

BANNED PHRASES:
- "So why does this matter?"
- "In an era where..."
- "This isn't just X, it's Y"
- "represents a growing trend"
- "invites us to rethink"
- Any sentence that could appear in a TED talk description

STRUCTURE:
- Open with the specific thing that happened, not a quote
- Name the arc: [trigger] → [peak] → [outcome/current state]
- End with the residue: what vocabulary/practice/meme persists?

EXAMPLE OPENING:
BAD: "'Focus on what you want'—this mantra ignited a complex discussion..."
GOOD: "visakanv's 2020 throwaway tweet became tpot's unofficial attention-management doctrine, peaking when richdecibels reframed it as 'exorcism from culture-war demons'"

Output JSON:
class StrandSummary(BaseModel):
    title: str  # One-line title for the strand
    summary: str  # Human-friendly markdown summary, 1-3 paragraphs

"""



def get_client():
    return OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )


def _make_summary_call(
    client,
    strand_data: dict,
    model_name: str = "openai/gpt-4o-mini",
    temperature: float = 0.7,
) -> StrandSummary:
    """Make the LLM call to generate title and summary."""

    # Prepare data without thread_text
    data_for_llm = {
        "seed_tweet_id": strand_data["seed_tweet_id"],
        "rating": strand_data["rating"],
        # "thread_text": "[OMITTED - Full thread text contains the complete tweet content but is excluded here due to length]"
        "thread_text":strand_data['thread_text']
    }

    user_content = f"<strand_data>\n{json.dumps(data_for_llm, indent=2)}\n</strand_data>"

    schema = StrandSummary.model_json_schema()
    print(f'[DEBUG] user_content {user_content}')
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SUMMARIZER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_completion_tokens=1024,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "strand_summary",
                "schema": schema,
            },
        },
    )

    content = completion.choices[0].message.content

    if not content or not content.strip():
        raise ValueError(f"Empty response from LLM")

    # Strip markdown code blocks if present
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    parsed = json.loads(text)
    return StrandSummary.model_validate(parsed)


def generate_summary(
    strand_data: dict,
    model_name: str = "openai/gpt-4o-mini",
    max_retries: int = 3,
) -> dict:
    """Generate title and summary for a strand, with retries."""
    import time

    client = get_client()
    tweet_id = strand_data["seed_tweet_id"]

    for attempt in range(max_retries):
        try:
            summary = _make_summary_call(client, strand_data, model_name)

            # Return original data plus new fields
            return {
                **strand_data,
                "title": summary.title,
                "summary": summary.summary,
            }
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            if is_rate_limit_error(e):
                delay = 2 ** attempt
                print(f"Rate limit hit for {tweet_id}, waiting {delay}s...")
                time.sleep(delay)
            else:
                print(f"Retry {attempt + 1} for {tweet_id}: {e}")
                time.sleep(1)

    raise RuntimeError(f"Failed to generate summary for {tweet_id}")


# %%
# Load all rated strands

def load_rated_strands() -> dict[int, dict]:
    """Load all rated strand JSON files."""
    strands = {}
    for path in RATED_STRANDS_DIR.glob("*.json"):
        with open(path) as f:
            data = json.load(f)
            strands[data["seed_tweet_id"]] = data
    return strands


# %%
def process_all_strands(
    model_name: str = "openai/gpt-4o-mini",
    max_workers: int = 3,
    override_cache=False
) -> dict[int, dict]:
    """Process all rated strands and generate summaries."""

    RATED_STRANDS_PLUS_DIR.mkdir(parents=True, exist_ok=True)

    all_strands = load_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    # Check for existing results
    existing = {}
    pending_ids = []

    for tid, data in list(all_strands.items()):
        result_file = RATED_STRANDS_PLUS_DIR / f"{tid}.json"
        if result_file.exists() and not override_cache:
            with open(result_file) as f:
                existing[tid] = json.load(f)
        else:
            pending_ids.append(tid)

    if existing:
        print(f"Found {len(existing)} existing, processing {len(pending_ids)} remaining")

    if not pending_ids:
        print("All strands already processed!")
        return existing

    def process_one(tid: int) -> dict:
        data = all_strands[tid]
        result = generate_summary(data, model_name)

        # Save immediately
        with open(RATED_STRANDS_PLUS_DIR / f"{tid}.json", "w") as f:
            json.dump(result, f, indent=2)

        return result

    new_results, failed = parallel_map_to_dict(
        pending_ids, process_one,
        max_workers=max_workers,
        desc="Generating summaries"
    )

    if failed:
        print(f"[WARN] {len(failed)} strands failed: {failed}")

    return {**existing, **new_results}
# %%
if __name__ == "__main__":
    # results = process_all_strands(model_name='anthropic/claude-sonnet-4.5')
    # results = process_all_strands(model_name='anthropic/claude-haiku-4.5', override_cache=True)
    # results = process_all_strands(model_name='google/gemini-2.5-flash')
    
    # results = process_all_strands(model_name='openai/gpt-4o-mini', override_cache=True)
    # results = process_all_strands(model_name='openai/gpt-oss-120b')
    results = process_all_strands(model_name='openai/gpt-5.2')
    print(f"\nProcessed {len(results)} strands total")

    # Show a sample
    sample_id = next(iter(results))
    sample = results[sample_id]
    print(f"\n--- Sample: {sample_id} ---")
    print(f"Title: {sample['title']}")
    print(f"\nReasoning:\n{sample['rating']['reasoning_summary']}")
    print(f"\nSummary:\n{sample['summary']}")
# 

# %%
