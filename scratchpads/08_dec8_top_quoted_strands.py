# %%
import json
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict, Literal
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

from lib.strand_caches import get_quote_tweets_dict, load_caches
from lib.strand_rating_prompt import STRAND_RATER_PROMPT, StrandRating
from lib.strand_builder import get_strand_conversation_string, get_strand_seeds
from lib.conversation_explorer import filter_conversation_trees, render_conversation_trees, strand_header_print_factory
from lib.image_describer import get_image_descriptions, load_img_cache, save_img_cache, DEFAULT_CACHE_PATH, MediaDescription
# %%
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

# %%
Provider = Literal["groq", "openrouter"]

def fix_schema_for_anthropic(schema: dict) -> dict:
    """Add additionalProperties: false to all objects for Anthropic compatibility."""
    import copy
    schema = copy.deepcopy(schema)
    
    def fix_obj(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "object" and "additionalProperties" not in obj:
                obj["additionalProperties"] = False
            for v in obj.values():
                fix_obj(v)
        elif isinstance(obj, list):
            for item in obj:
                fix_obj(item)
    
    fix_obj(schema)
    return schema


def rate_strand(
    thread_text: str, 
    tweet_id: int, 
    model_name: str = "openai/gpt-oss-120b",
    provider: Provider = "groq",
    max_retries: int = 5
) -> StrandResult:
    """Send thread_text to LLM with strand rating prompt, get structured output. Retries on rate limits."""
    client = (
        Groq(api_key=os.environ.get("GROQ_API_KEY"))
        if provider == "groq"
        else OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    )
    
    user_content = f"<strand_data>\n{thread_text}\n</strand_data>"
    
    schema = StrandRating.model_json_schema()
    if "anthropic" in model_name.lower() or "claude" in model_name.lower():
        schema = fix_schema_for_anthropic(schema)
    
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=model_name,
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
                        "schema": schema,
                    },
                },
            )
            
            rating = StrandRating.model_validate(json.loads(completion.choices[0].message.content))
            
            return {
                "seed_tweet_id": tweet_id,
                "thread_text": thread_text,
                "rating": rating.model_dump(),
            }
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = any(x in error_str for x in ["rate_limit", "429", "too many requests"])
            
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"Rate limit hit for tweet {tweet_id}, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
# %%

def load_existing_results(path: Path) -> tuple[list[StrandResult], set[int]]:
    """Load existing results and return (results, processed_ids)."""
    if not path.exists():
        return [], set()
    
    with open(path) as f:
        results = json.load(f)
    
    processed_ids = {r["seed_tweet_id"] for r in results}
    return results, processed_ids


def process_strands_parallel(
    tweet_ids: list[int],
    thread_texts: list[str],
    max_workers: int = 1,
    model_name: str = "openai/gpt-oss-120b",
    provider: Provider = "groq",
    checkpoint_path: Path = OUTPUT_PATH,
    save_every: int = 1
) -> list[StrandResult]:
    """Process strands in parallel, saving incrementally. Resumes from checkpoint."""
    results, processed_ids = load_existing_results(checkpoint_path)
    print(f"Loaded {len(results)} existing results, skipping {len(processed_ids)} IDs")
    
    # Filter out already processed
    pending = [(tid, text) for tid, text in zip(tweet_ids, thread_texts) if tid not in processed_ids]
    
    if not pending:
        print("All strands already processed")
        return results
    
    pending_ids, pending_texts = zip(*pending)
    print(f"Processing {len(pending)} remaining strands...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_id = {
            executor.submit(rate_strand, text, tid, model_name, provider): tid
            for tid, text in zip(pending_ids, pending_texts)
        }
        
        completed = 0
        for future in tqdm(as_completed(future_to_id), total=len(future_to_id), desc="Rating strands"):
            tid = future_to_id[future]
            try:
                result = future.result()
                results.append(result)
                completed += 1
                
                # Save checkpoint
                if completed % save_every == 0:
                    with open(checkpoint_path, "w") as f:
                        json.dump(results, f, indent=2)
            except Exception as e:
                print(f"Failed tweet {tid} after retries: {e}")
    
    # Final save
    with open(checkpoint_path, "w") as f:
        json.dump(results, f, indent=2)
    
    return results


def save_results(results: list[StrandResult], path: Path = OUTPUT_PATH) -> None:
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} strand results to {path}")


# %%

print("Loading top quoted tweet IDs...")
high_half_life_qt_tweet_ids = load_top_tweet_ids()[:100]
print(f"Found {len(high_half_life_qt_tweet_ids)} tweet IDs")
# %%
ultimape_tweet_id = 731740482137559040
# %%
quote_dict = get_quote_tweets_dict()
tweet_dict, conversation_trees = load_caches()
# %%
tid=712913395645685760
tweet = tweet_dict[tid]
k = 100
threshold = 0.5
exclude_tweet_id = str(tid)
filter_obj = {"must_not": [{"key": "text", "match": {"text": kw}} for kw in []]} if [] else None
# %%
seeds = get_strand_seeds(tweet_id=tid, tweet_dict=tweet_dict, quote_tweets_dict=quote_dict, exclude_keywords=[], semantic_limit=20, debug=True)


# %%

# seeds id with commas
seeds_ids = [i.tweet_id for i in seeds]
seeds_ids_str = ','.join(map(str, seeds_ids))
print(seeds_ids_str)

# %%
filtered_trees = filter_conversation_trees([i.tweet_id for i in seeds], conversation_trees, tweet_dict, depth=10, depth_up=10, depth_from_root=100)


# %%
# Let's gather ALL the tweet IDs, and make paralle calls to get_image_descriptions so the cache is filled

# Load cache once before parallel calls

# %%
# let's get all the tweet ids from gathering all keys and vales of the parents in one big set

tweet_ids_set = set()
for tree in filtered_trees.values():
    for tid in tree["parents"].keys():
        tweet_ids_set.add(tid)
    for tid in tree["parents"].values():
        tweet_ids_set.add(tid)
    for tid in tree["children"].keys():
        tweet_ids_set.add(tid)

tweet_ids = list(tweet_ids_set)

# %%
print(f"Found {len(tweet_ids)} tweet IDs")

# %%

image_cache = load_img_cache(DEFAULT_CACHE_PATH)
tweet_id_to_describe = [tid for tid in tweet_ids if tid not in image_cache]
print(f"Found {len(tweet_id_to_describe)} tweet IDs to describe")
# %%
# Process all the tweet id to describe in parallel. We add the result to the image_cache dict.


def get_multiple_image_descriptions(image_cache: dict[int, list[MediaDescription]], tweet_ids: list[int], verbose: bool = False) -> dict[int, list[MediaDescription]]:
    tweet_id_to_describe = [tid for tid in tweet_ids if tid not in image_cache]
    print(f"Found {len(tweet_id_to_describe)} tweet IDs to describe")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(get_image_descriptions, tweet_id, verbose=False): tweet_id for tweet_id in tweet_id_to_describe}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Describing images"):
            tid = futures[future]
            descriptions = future.result()
            if descriptions:
                image_cache[str(tid)] = descriptions
    return image_cache



# %%

get_image_descriptions(1668633368479805447, verbose=True)
# %%
# Save cache in bulk after all parallel calls complete
save_img_cache(image_cache, DEFAULT_CACHE_PATH)

# Convert cache to the format expected by render_strand_header
image_descriptions = {tid: image_cache.get(str(tid), []) for tid in tweet_ids}

# %%
# make seed into a dict
seed_info = {i.tweet_id: i.source_type for i in seeds}
render_strand_header = strand_header_print_factory(seed_info)
strand_str = render_conversation_trees(filtered_trees, tweet_dict, render_header=render_strand_header, image_descriptions=image_descriptions)
print(strand_str)


# %%
# Here to start gathering the seeds for all root tweet ids
# Then we get a (set of filtered trees, where each filtered tree correspond to a seed) for each one of the 100 root tweet ids
# We describe all the images in the trees
# We render the trees with the images descriptions
# We return the thread texts

thread_texts = []
image_cache = load_img_cache(DEFAULT_CACHE_PATH)
depth = 10
for tid in high_half_life_qt_tweet_ids[:1]:
    seeds = get_strand_seeds(tid, tweet_dict, quote_dict, conversation_trees)
    print(f"Found {len(seeds)} seeds for tweet {tid}")
    seed_ids = [s.tweet_id for s in seeds]
    print(f"Found {len(seed_ids)} seed IDs for tweet {tid}")
    filtered_trees = filter_conversation_trees(seed_ids, conversation_trees, tweet_dict, depth=depth, depth_up=depth, depth_from_root=depth)

    tree_tweet_ids = set()
    for tree in filtered_trees.values():
        for tid in tree["parents"].keys():
            tree_tweet_ids.add(tid)
        for tid in tree["parents"].values():
            tree_tweet_ids.add(tid)
        for tid in tree["children"].keys():
            tree_tweet_ids.add(tid)
    tree_tweet_ids = list(tree_tweet_ids)
    print(f"Found {len(tree_tweet_ids)} tweet IDs in the trees for tweet {tid}")

    image_cache = get_multiple_image_descriptions(image_cache, tree_tweet_ids)
    print(f"Found {len(image_cache)} image descriptions for tweet {tid}")
    thread_text = render_conversation_trees(filtered_trees, tweet_dict, render_header=render_strand_header, image_descriptions=image_cache)
    print(f"Generated thread text for tweet {tid}")
    thread_texts.append(thread_text)

# %%
print("Generating thread texts...")

thread_texts = []
def generate_strand_thread_text(tid: int, depth=10) -> str:
    seeds = get_strand_seeds(tid, tweet_dict, quote_dict, conversation_trees)
    tweet_ids = [s.tweet_id for s in seeds]
    filtered_trees = filter_conversation_trees(tweet_ids, conversation_trees, tweet_dict, depth)
    return render_conversation_trees(filtered_trees, tweet_dict, render_header=render_strand_header, image_descriptions=image_descriptions)

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(generate_strand_thread_text, tid): tid for tid in tweet_ids}
    for future in tqdm(as_completed(futures), total=len(futures), desc="Generating thread texts"):
        thread_text = future.result()
        thread_texts.append(thread_text)
# Save thread texts for inspection
thread_texts_path = Path("scratchpads/thread_texts.json")
with open(thread_texts_path, "w") as f:
    json.dump(
        [{"tweet_id": tid, "thread_text": text} for tid, text in zip(tweet_ids, thread_texts)],
        f,
        indent=2
    )
print(f"Saved thread texts to {thread_texts_path}")


print(f"Generated {len(thread_texts)} thread texts")
# %%
# read thread texts from data/top_quoted_strands.json and get "thread_text" from each entry

thread_texts = [entry["thread_text"] for entry in json.load(open(OUTPUT_PATH))]
print(f"Read {len(thread_texts)} thread texts")


# %%
# Filter out empty threads
valid_pairs = [(tid, text) for tid, text in zip(tweet_ids, thread_texts) if text.strip()]
print(f"Found {len(valid_pairs)} non-empty threads")

if not valid_pairs:
    print("No valid threads to process")
else:
    valid_ids, valid_texts = zip(*valid_pairs)
    print("Sending to Groq for rating...")
    results = process_strands_parallel(list(valid_ids[:1]), list(valid_texts), provider="openrouter", model_name="anthropic/claude-sonnet-4.5")
    save_results(results)


# %%
# valid_ids, valid_texts = zip(*valid_pairs)
# print("Sending to Groq for rating...")
# results = process_strands_parallel(list(valid_ids), list(valid_texts))
# save_results(results)
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

# * Inspect the thread text to be sure they work - ddone 
# * Cache the qutoe dict - ddone 
# * Switch for ~~sonnet 4.5 ~~ oAI OSS 120B
# * add a name to the strands - LATER 
