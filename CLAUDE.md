# Memetic Lineage — Project Guide

## Project structure

- `pipeline/` — Python package that generates all data (strands, bangers, atlas, etc.)
- `bangers/` — Next.js frontend that displays the data
- `scratchpads/` — Numbered experiment scripts + shared `lib/` + all data in `scratchpads/data/`

Data lives in `scratchpads/data/`. Pipeline reads from there, writes frontend exports to `bangers/public/`.

## Critical: Tweet ID handling

Tweet IDs are 18-19 digit integers. Float64 cannot represent them exactly — they get rounded or displayed in scientific notation (e.g. `1.83e+18`), which silently breaks lookups.

**Rules:**
- Always read parquet files with `dtype_backend="pyarrow"` to keep IDs as proper integers/strings, never float64
- When converting IDs, go through `int(float(x))` to handle any scientific notation strings, then `str(...)` for string form
- Never trust pandas default dtype inference for ID columns — explicitly cast with `.astype(str)` or read with pyarrow backend
- The `filtered_quote_tweets` diskcache had float keys (fixed 2026-03-02 by adding `dtype_backend='pyarrow'` to `generate_filtered_quote_cache`). If quote counts look suspiciously low, regenerate this cache first

## Pipeline CLI

```bash
cd pipeline
uv run pipeline bangers                    # Phase 0: bangers_tweets.json
uv run pipeline strands                    # Phases 1-7: full strands pipeline
uv run pipeline strands --skip-build       # Skip specific phases
uv run pipeline                            # Everything (bangers first)
```

## Working style for data/debugging tasks

This project involves data science and exploratory debugging with Python, Parquet, and Pandas. This works differently from writing application code:

- **Iterate slowly and carefully.** Don't write large blocks of pipeline code before verifying each step produces correct output.
- **Debug in dialogue.** The user has strong intuitions about how the data should look. Present intermediate results, counts, and samples at each step so the user can sanity-check before proceeding.
- **Verify data at each stage:** load raw data, check counts, check ID types, inspect samples, then move to the next transformation.
- **Don't jump to code fixes** until the root cause is clearly identified and confirmed with the user.
