# Task Context - January 12, 2026

## Session Summary

### Completed Work

1. **Added tests** to `test_strand_builder.py`, `test_strand_rater.py`, `test_strand_pipeline.py` - all 128 tests passing

2. **Fixed atlas data pipeline**:
   - Root cause: 252 rated strands existed, but only 120 had tweet-level embeddings
   - Added `phase_generate_tweet_embeddings()` to `strands.py` (parallel embedding generation)
   - Added `phase_generate_atlas_parquet()` to `strands.py` (UMAP projection)
   - Fixed 4 corrupted JSON files from parallel writes
   - **Result**: Atlas parquet now has 37,073 tweets from 252 strands (was 22,582 from 120)
   - Exported to: `top-qt-website/bangers/public/atlas_data.json` (14.4 MB)

3. **Minor remaining issue**: Strand `1332437788503859200` missing summary (causes Phase 5b error but doesn't affect atlas)

---

## Pending Tasks

### 1. Mini Atlas Not Updating in Best-Strands View
- **Issue**: The mini atlas component in the best-strands view didn't update with new data
- **Likely cause**: Frontend may be caching old data or not loading from updated `atlas_data.json`
- **Files to check**:
  - `top-qt-website/bangers/` - React components for mini atlas
  - Check if there's a separate data file for best-strands minimap vs main atlas

### 2. Edge Colors Wrong Between Essential Tweets
- **Issue**: Edges between essential tweets of the same strand are all blue
- **Expected**: Edges should have the strand's color
- **Files to check**:
  - Look for edge rendering code in atlas components
  - Find where strand colors are defined and how they're applied to edges
  - Check if there's a distinction between intra-strand edges vs inter-strand edges

### 3. Envelope Tightness Not Working
- **Issue**: Envelopes around strands extend way further than expected
- **Expected**: Envelopes should be tight around the strand's tweets based on 2D display distance
- **Root cause hypothesis**: Distances might be calculated in embedding space (high-dim) instead of 2D projection space
- **Files to check**:
  - Find envelope/hull calculation code
  - Verify distances use `projection_x`, `projection_y` columns (2D) not raw embeddings
  - Check envelope algorithm parameters (alpha shape, convex hull, padding)

---

## Key Files Reference

### Data Pipeline
- `scratchpads/strands.py` - Main pipeline with all phases
- `scratchpads/data/tweet_embeddings_atlas.parquet` - UMAP projections for 37,073 tweets
- `scratchpads/data/all_tweet_embeddings/*.json` - 252 files with per-tweet embeddings
- `scratchpads/data/rated_strands/*.json` - 252 rated strand files

### Frontend
- `top-qt-website/bangers/public/atlas_data.json` - Exported atlas data (14.4 MB)
- `top-qt-website/bangers/public/strand_histograms.json` - Histogram data
- `top-qt-website/bangers/` - React app root

### Verification Commands
```bash
# Check atlas parquet has all strands
cd /Users/frsc/Documents/Projects/memetic-lineage/scratchpads
python3 -c "import pandas as pd; df = pd.read_parquet('data/tweet_embeddings_atlas.parquet'); print(f'{len(df)} tweets, {df.strand_id.nunique()} strands')"
# Expected: 37073 tweets, 252 strands

# Check exported JSON has all data
cd /Users/frsc/Documents/Projects/memetic-lineage/top-qt-website/bangers
python3 -c "import json; d = json.load(open('public/atlas_data.json')); print(f\"{len(d['tweets'])} tweets\")"
# Expected: 37073 tweets

# Fix missing summary (optional)
cd /Users/frsc/Documents/Projects/memetic-lineage/scratchpads
python3 strands.py --skip-build --skip-rate --skip-histogram --skip-tweet-embeddings --skip-atlas-parquet --skip-atlas
```

---

## Next Steps

1. Investigate mini atlas data loading in best-strands component
2. Find and fix edge coloring logic for intra-strand edges
3. Fix envelope calculation to use 2D projection distances
4. Optionally regenerate missing summary for strand 1332437788503859200
