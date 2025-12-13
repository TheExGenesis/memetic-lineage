# %%
"""Strand rating using LLMs with structured output."""
import json
import os
from pathlib import Path
from typing import TypedDict, Literal, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI

from .retry import with_retry, is_rate_limit_error
from .parallel import parallel_map_to_dict
from .strand_rating_prompt import STRAND_RATER_PROMPT, StrandRating

load_dotenv(Path(__file__).parent.parent.parent / ".env")

Provider = Literal["groq", "openrouter"]


class RatedStrandResult(TypedDict):
    seed_tweet_id: int
    thread_text: str
    rating: dict


def _fix_schema_for_anthropic(schema: dict) -> dict:
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


def _get_client(provider: Provider):
    if provider == "groq":
        return Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )


class EmptyResponseError(Exception):
    """Raised when LLM returns empty content."""
    pass


def _make_rate_strand_call(
    client,
    model_name: str,
    thread_text: str,
    temperature: float
) -> StrandRating:
    """Make the actual LLM call for rating."""
    user_content = f"<strand_data>\n{thread_text}\n</strand_data>"
    
    schema = StrandRating.model_json_schema()
    if "anthropic" in model_name.lower() or "claude" in model_name.lower():
        schema = _fix_schema_for_anthropic(schema)
    
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": STRAND_RATER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_completion_tokens=2048,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "strand_rating",
                "schema": schema,
            },
        },
    )
    
    content = completion.choices[0].message.content
    if not content or not content.strip():
        raise EmptyResponseError(f"LLM returned empty response (finish_reason: {completion.choices[0].finish_reason})")
    
    return StrandRating.model_validate(json.loads(content))


def rate_strand(
    thread_text: str,
    tweet_id: int,
    model_name: str = "openai/gpt-4o-mini",
    provider: Provider = "openrouter",
    max_retries: int = 2,
    base_temperature: float = 0.7
) -> RatedStrandResult:
    """
    Rate a strand using LLM with structured output.
    
    Retries on rate limits with exponential backoff.
    On empty responses or structured output failures, retries with higher temperature.
    """
    import time
    
    client = _get_client(provider)
    temperature = base_temperature
    
    for attempt in range(max_retries):
        try:
            rating = _make_rate_strand_call(client, model_name, thread_text, temperature)
            return {
                "seed_tweet_id": tweet_id,
                "thread_text": thread_text,
                "rating": rating.model_dump(),
            }
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            if is_rate_limit_error(e):
                delay = 2 ** attempt
                print(f"Rate limit hit for tweet {tweet_id}, waiting {delay}s...")
                time.sleep(delay)
            elif isinstance(e, EmptyResponseError):
                # Empty response - wait a bit and retry with same temp
                delay = 2 ** attempt
                print(f"Empty response for tweet {tweet_id}, waiting {delay}s and retrying...")
                time.sleep(delay)
            else:
                # Structured output failure (JSON parse, validation) - bump temperature
                temperature = min(1.0, temperature + 0.1)
                print(f"Retry {attempt + 1} for tweet {tweet_id} with temp={temperature:.1f}: {e}")
                time.sleep(1)  # Small delay before retry
    
    raise RuntimeError(f"Failed to rate tweet {tweet_id} after {max_retries} attempts")


def rate_strands_batch(
    strand_texts: Dict[int, str],
    model_name: str = "openai/gpt-4o-mini",
    provider: Provider = "openrouter",
    max_workers: int = 2,
    output_dir: Optional[Path] = None,
    max_retries: int = 2,
    base_temperature: float = 0.7,
) -> Dict[int, RatedStrandResult]:
    """
    Rate multiple strands in parallel with phase-level parallelism.
    
    Args:
        strand_texts: Dict of tweet_id -> thread_text
        model_name: LLM model to use
        provider: "groq" or "openrouter"
        max_workers: Parallel workers (keep low for rate limits)
        output_dir: If provided, save each result as {tweet_id}.json
        
    Returns:
        Dict of tweet_id -> RatedStrandResult
    """
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for existing results
    existing: Dict[int, RatedStrandResult] = {}
    pending_ids: List[int] = []
    
    for tid in strand_texts.keys():
        if output_dir:
            result_file = output_dir / f"{tid}.json"
            if result_file.exists():
                with open(result_file) as f:
                    existing[tid] = json.load(f)
                continue
        pending_ids.append(tid)
    
    if existing:
        print(f"Loaded {len(existing)} existing results, processing {len(pending_ids)} remaining")
    
    if not pending_ids:
        return existing
    
    def rate_one(tid: int) -> RatedStrandResult:
        result = rate_strand(
            strand_texts[tid], tid,
            model_name=model_name, provider=provider
        )
        if output_dir:
            with open(output_dir / f"{tid}.json", "w") as f:
                json.dump({result}, f, indent=2)
        return result
    
    new_results, failed = parallel_map_to_dict(
        pending_ids, rate_one,
        max_workers=max_workers,
        desc="Rating strands"
    )
    
    if failed:
        print(f"[WARN] {len(failed)} strands failed to rate: {failed}")
    
    return {**existing, **new_results}

