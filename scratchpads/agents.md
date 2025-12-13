# Scratchpads Agent Guidelines

## Architecture Principles

### Functional Pipeline
- Data flows through phases, always returns to top layer
- Functions return `Dict[int, T]` keyed by tweet_id
- No hidden state mutations - explicit cache passing and merging

### Phase-Level Parallelism
Parallelize each phase separately, not end-to-end. Benefits:
- Dedupe work before dispatching (images especially)
- Per-phase concurrency tuning based on resource type
- Shared cache between phases
- Clear progress tracking

**Concurrency targets:**
| Phase | Type | Workers | Reason |
|-------|------|---------|--------|
| Seeds (semantic search) | IO | 4 | Moderate API limits |
| Filter trees | CPU | 8 | Pure dict operations |
| Image descriptions | IO | 2 | Groq rate limits |
| Render | CPU | 1 | Fast, string ops |

### Caching
- Use diskcache for large persistent caches (tweet_dict, reply_trees, quote_tweets)
- Image cache uses CSV for simplicity and human-readability
- Always check cache before dispatching parallel work

### Error Handling
- Exponential backoff on external API calls (Groq, Supabase)
- For structured output failures (LLM), retry with higher temperature
- `parallel_map_to_dict` logs errors but continues processing

## Key Files

| File | Purpose |
|------|---------|
| `lib/strand_caches.py` | Diskcache loading for tweet_dict, reply_trees, quote_tweets |
| `lib/strand_builder.py` | Strand pipeline: seeds → trees → images → render |
| `lib/strand_rater.py` | LLM-based strand rating |
| `lib/image_describer.py` | Groq image descriptions with retry |
| `lib/parallel.py` | `parallel_map_to_dict` utility |
| `lib/retry.py` | `@with_retry` decorator |

## Conventions

- Type hints on all functions (signatures or short comments)
- No inline explanation comments unless asked
- Prefer `toolz` patterns where applicable
- Tests are integration-style, not exhaustive unit tests

## TODOs

- [ ] Add async variants of parallel utilities for true async IO
- [ ] Consolidate image cache to diskcache format
- [ ] Add structured logging instead of print statements

