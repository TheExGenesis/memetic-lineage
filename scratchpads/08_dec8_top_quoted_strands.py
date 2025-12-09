# %%
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict
from groq import Groq
from dotenv import load_dotenv
from tqdm import tqdm

from lib.strand_tools import get_thread_texts
from lib.strand_rating_prompt import STRAND_RATER_PROMPT, StrandRating

load_dotenv(Path(__file__).parent.parent / ".env")

DATA_DIR = Path(__file__).parent / "data"
TOP_IDS_PATH = DATA_DIR / "top_quoted_tweet_ids.json"
OUTPUT_PATH = DATA_DIR / "top_quoted_strands.json"


class StrandResult(TypedDict):
    seed_tweet_id: int
    thread_text: str
    rating: dict  # StrandRating as dict


def load_top_tweet_ids() -> list[int]:
    with open(TOP_IDS_PATH) as f:
        return json.load(f)


def rate_strand(thread_text: str, tweet_id: int) -> StrandResult:
    """Send thread_text to Groq with strand rating prompt, get structured output."""
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    user_content = f"<strand_data>\n{thread_text}\n</strand_data>"
    
    completion = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": STRAND_RATER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
        max_completion_tokens=2048,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "strand_rating",
                "schema": StrandRating.model_json_schema(),
            },
        },
    )
    
    rating = StrandRating.model_validate(json.loads(completion.choices[0].message.content))
    
    return {
        "seed_tweet_id": tweet_id,
        "thread_text": thread_text,
        "rating": rating.model_dump(),
    }


def process_strands_parallel(
    tweet_ids: list[int],
    thread_texts: list[str],
    max_workers: int = 5,
) -> list[StrandResult]:
    """Process strands in parallel using ThreadPoolExecutor."""
    results: list[StrandResult] = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_id = {
            executor.submit(rate_strand, text, tid): tid
            for tid, text in zip(tweet_ids, thread_texts)
        }
        
        for future in tqdm(as_completed(future_to_id), total=len(future_to_id), desc="Rating strands"):
            tid = future_to_id[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Error processing tweet {tid}: {e}")
    
    return results


def save_results(results: list[StrandResult], path: Path = OUTPUT_PATH) -> None:
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} strand results to {path}")


# %%
if __name__ == "__main__":
    print("Loading top quoted tweet IDs...")
    tweet_ids = load_top_tweet_ids()[:5]
    print(f"Found {len(tweet_ids)} tweet IDs")
    
    print("Generating thread texts...")
    thread_texts = get_thread_texts(tweet_ids)
    print(f"Generated {len(thread_texts)} thread texts")
    
    # Filter out empty threads
    valid_pairs = [(tid, text) for tid, text in zip(tweet_ids, thread_texts) if text.strip()]
    print(f"Found {len(valid_pairs)} non-empty threads")
    
    if not valid_pairs:
        print("No valid threads to process")
    else:
        valid_ids, valid_texts = zip(*valid_pairs)
        print("Sending to Groq for rating...")
        results = process_strands_parallel(list(valid_ids), list(valid_texts))
        save_results(results)
        
        # Preview first result
        if results:
            r = results[0]
            print("\n--- Preview of first result ---")
            print(f"Seed Tweet ID: {r['seed_tweet_id']}")
            print(f"Rating: {r['rating']['rating']}/10")
            print(f"Evolution: {r['rating']['evolution']} | Cohesion: {r['rating']['cohesion']} | Utility: {r['rating']['utility']}")
            print(f"Summary: {r['rating']['reasoning_summary'][:200]}...")
            print(f"Essential tweets: {len(r['rating']['essential_tweets'])} selected")


# %%
valid_ids, valid_texts = zip(*valid_pairs)
print("Sending to Groq for rating...")
results = process_strands_parallel(list(valid_ids), list(valid_texts))
save_results(results)
# %%
# Preview first result
for r in results:
    print("\n--- Preview of result ---")
    print(f"Seed Tweet ID: {r['seed_tweet_id']}")
    print(f"Rating: {r['rating']['rating']}/10")
    print(f"Evolution: {r['rating']['evolution']} | Cohesion: {r['rating']['cohesion']} | Utility: {r['rating']['utility']}")
    print(f"Summary: {r['rating']['reasoning_summary']}")
    print(f"Essential tweets: {len(r['rating']['essential_tweets'])} selected")
    print("-" * 100)

# %%
get_thread_texts([712913395645685760])
# %%
