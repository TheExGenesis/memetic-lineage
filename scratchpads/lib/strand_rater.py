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


class StrandData(TypedDict):
    thread_text: str
    seed_ids: list[int]


class RatedStrandResult(TypedDict):
    seed_tweet_id: int
    thread_text: str
    seed_ids: list[int]
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


class JSONParseError(Exception):
    """Raised when LLM response can't be parsed as JSON."""
    def __init__(self, message: str, raw_content: str, tweet_id: Optional[int] = None):
        super().__init__(message)
        self.raw_content = raw_content
        self.tweet_id = tweet_id


def _make_rate_strand_call(
    client,
    model_name: str,
    thread_text: str,
    temperature: float,
    tweet_id: Optional[int] = None
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
    finish_reason = completion.choices[0].finish_reason
    
    if not content or not content.strip():
        raise EmptyResponseError(f"LLM returned empty response (finish_reason: {finish_reason})")
    
    # Strip markdown code blocks if present
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise JSONParseError(
            f"JSON parse failed: {e}. finish_reason={finish_reason}, len={len(content)}, first100={repr(content[:100])}",
            raw_content=content,
            tweet_id=tweet_id
        ) from e
    
    try:
        return StrandRating.model_validate(parsed)
    except Exception as e:
        raise JSONParseError(
            f"Pydantic validation failed: {e}",
            raw_content=content,
            tweet_id=tweet_id
        ) from e


def rate_strand(
    thread_text: str,
    tweet_id: int,
    seed_ids: list[int] = [],
    model_name: str = "openai/gpt-4o-mini",
    provider: Provider = "openrouter",
    max_retries: int = 2,
    base_temperature: float = 0.7,
    debug_dir: Optional[Path] = None
) -> RatedStrandResult:
    """
    Rate a strand using LLM with structured output.
    
    Retries on rate limits with exponential backoff.
    On empty responses or structured output failures, retries with higher temperature.
    If debug_dir is set, saves failed raw responses for inspection.
    """
    import time
    
    client = _get_client(provider)
    temperature = base_temperature
    last_error: Optional[Exception] = None
    
    for attempt in range(max_retries):
        try:
            rating = _make_rate_strand_call(client, model_name, thread_text, temperature, tweet_id)
            return {
                "seed_tweet_id": tweet_id,
                "thread_text": thread_text,
                "seed_ids": seed_ids,
                "rating": rating.model_dump(),
            }
        except Exception as e:
            last_error = e
            
            # Save failed response if it's a JSONParseError
            if debug_dir and isinstance(e, JSONParseError):
                debug_dir = Path(debug_dir)
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_file = debug_dir / f"{tweet_id}_attempt{attempt}.txt"
                debug_file.write_text(e.raw_content)
                print(f"[DEBUG] Saved raw response to {debug_file}")
            
            if attempt == max_retries - 1:
                raise
            
            if is_rate_limit_error(e):
                delay = 2 ** attempt
                print(f"Rate limit hit for tweet {tweet_id}, waiting {delay}s...")
                time.sleep(delay)
            elif isinstance(e, EmptyResponseError):
                delay = 2 ** attempt
                print(f"Empty response for tweet {tweet_id}, waiting {delay}s and retrying...")
                time.sleep(delay)
            else:
                temperature = min(1.0, temperature + 0.1)
                print(f"Retry {attempt + 1} for tweet {tweet_id} with temp={temperature:.1f}: {e}")
                time.sleep(1)
    
    raise RuntimeError(f"Failed to rate tweet {tweet_id} after {max_retries} attempts") from last_error


def rate_strands_batch(
    strands_data: Dict[int, StrandData],
    model_name: str = "openai/gpt-4o-mini",
    provider: Provider = "openrouter",
    max_workers: int = 2,
    output_dir: Optional[Path] = None,
    max_retries: int = 2,
    base_temperature: float = 0.7,
    debug_dir: Optional[Path] = None,
) -> Dict[int, RatedStrandResult]:
    """
    Rate multiple strands in parallel with phase-level parallelism.
    
    Args:
        strands_data: Dict of tweet_id -> StrandData (thread_text + seed_ids)
        model_name: LLM model to use
        provider: "groq" or "openrouter"
        max_workers: Parallel workers (keep low for rate limits)
        output_dir: If provided, save each result as {tweet_id}.json
        debug_dir: If provided, save failed raw LLM responses for debugging
        
    Returns:
        Dict of tweet_id -> RatedStrandResult
    """
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for existing results
    existing: Dict[int, RatedStrandResult] = {}
    pending_ids: List[int] = []
    
    for tid in strands_data.keys():
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
        data = strands_data[tid]
        result = rate_strand(
            data["thread_text"], tid,
            seed_ids=data.get("seed_ids", []),
            model_name=model_name, provider=provider,
            max_retries=max_retries, base_temperature=base_temperature,
            debug_dir=debug_dir
        )
        if output_dir:
            with open(output_dir / f"{tid}.json", "w") as f:
                json.dump(result, f, indent=2)
        return result
    
    new_results, failed = parallel_map_to_dict(
        pending_ids, rate_one,
        max_workers=max_workers,
        desc="Rating strands"
    )
    
    if failed:
        print(f"[WARN] {len(failed)} strands failed to rate: {failed}")
    
    return {**existing, **new_results}

