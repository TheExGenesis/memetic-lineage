# %%
"""
Bird's Eye View visualization of relationship genesis narratives.

Uses birds_eye_view to embed and visualize the genesis narratives.
"""

import json
from pathlib import Path
import numpy as np
# %%
# === Configuration ===

SCRATCHPADS_DIR = Path(__file__).parent if "__file__" in dir() else Path.cwd()
ANALYSIS_DIR = SCRATCHPADS_DIR / "data" / "pair_genesis_analysis"

# All possible tags
ALL_TAGS = [
    "in_person_event", "matchmaker", "random_reply", "quote_tweet_boost",
    "asymmetric_pursuit", "long_lurk_first_reply", "playful_banter", 
    "intellectual_riff", "mentorship_vibe", "supportive_hype",
    "geographic_hint", "fertile", "slow_burn", "instant_click",
]



# %%
# === Load Data ===

def load_genesis_data() -> list[dict]:
    """Load all genesis analysis files as flat dicts."""
    files = sorted(ANALYSIS_DIR.glob("*.json"))
    print(f"Found {len(files)} analysis files")
    
    chunks = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            
            # Flatten into a single dict for bird's eye view
            chunk = {
                # Text field for embedding
                "text": data["analysis"]["neutral_genesis_narrative"],
                "genesis_narrative": data["analysis"]["genesis_narrative"],
                
                # Metadata fields
                "pair_id": data["pair_id"],
                "person_a": data["person_a"],
                "person_b": data["person_b"],
                "first_interaction_date": data["first_interaction_date"],
                "total_interactions": data["total_interactions"],
                "log_total_interactions": np.log(data["total_interactions"]),
                
                # Analysis fields
                "neutral_narrative": data["analysis"].get("neutral_genesis_narrative", ""),
                "initiator": data["analysis"]["initiator"],
                "symmetry_score": data["analysis"]["symmetry_score"],
                "interaction_energy": data["analysis"]["interaction_energy"],
                "confidence": data["analysis"]["confidence"],
                "missing_data_score": data["analysis"].get("missing_data_score", 3),
                
                # Tags as comma-separated string
                "tag_count": len(data["analysis"]["tags"]),
                
                # Individual tag booleans (for coloring)
                "is_fertile": int("fertile" in data["analysis"]["tags"]),
                "is_slow_burn": int("slow_burn" in data["analysis"]["tags"]),
                "is_instant_click": int("instant_click" in data["analysis"]["tags"]),
                "is_intellectual": int("intellectual_riff" in data["analysis"]["tags"]),
                "is_playful": int("playful_banter" in data["analysis"]["tags"]),
                "is_geographic": int("geographic_hint" in data["analysis"]["tags"]),
                "is_in_person": int("in_person_event" in data["analysis"]["tags"]),
                "is_matchmaker": int("matchmaker" in data["analysis"]["tags"]),
                "is_random_reply": int("random_reply" in data["analysis"]["tags"]),
                "is_quote_tweet_boost": int("quote_tweet_boost" in data["analysis"]["tags"]),
                "is_asymmetric_pursuit": int("asymmetric_pursuit" in data["analysis"]["tags"]),
                "is_long_lurk_first_reply": int("long_lurk_first_reply" in data["analysis"]["tags"]),
                "is_playful_banter": int("playful_banter" in data["analysis"]["tags"]),
                "is_intellectual_riff": int("intellectual_riff" in data["analysis"]["tags"]),
                "is_mentorship_vibe": int("mentorship_vibe" in data["analysis"]["tags"]),
            }
            chunks.append(chunk)
        except Exception as e:
            print(f"Error loading {f.name}: {e}")
    
    print(f"Loaded {len(chunks)} records")
    return chunks


# %%
# Load the data
chunks = load_genesis_data()

# Show sample
print("\nSample chunk:")
for k, v in list(chunks[0].items())[:10]:
    print(f"  {k}: {v}")

import json


with open("genesis_birds_eye_data.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)
print('Exported first fields to genesis_birds_eye_data.json')



# %%

vibecamp_relations = 0

keywords = ["vibecamp", "VibeCamp", "Vibe Camp", "vibe camp", "Vibecamp"]
for c in chunks:
    for keyword in keywords:
        if keyword in c["genesis_narrative"]:
            vibecamp_relations += 1
            break
print(f"Found {vibecamp_relations} vibecamp relations out of {len(chunks)} total relations")


# %%
# === Bird's Eye View ===

from birds_eye_view.core import ChunkCollection
from birds_eye_view.plotting import visualize_chunks
import birds_eye_view.plotting
from birds_eye_view.core import (
    ChunkCollection,
    Pipeline,
    OpenAIEmbeddor,
    UMAPReductor,
    DotProductLabelor,
    HierachicalLabelMapper,
    EmbeddingSearch,
)
from birds_eye_view.plotting import visualize_chunks
from birds_eye_view.file_loading import load_files

cache_file = "cache/"
embedding_model = "text-embedding-3-large"
pipeline = Pipeline(
    [
        OpenAIEmbeddor(
            model=embedding_model,
            cache_dir=cache_file,
            batch_size=2000,
        ),
        DotProductLabelor(
            nb_labels=3,
            embedding_model=embedding_model,
            key_name="emoji",
            cache_dir="../cache/emoji"
        ),
        UMAPReductor(
            verbose=True,
            n_neighbors=20,
            min_dist=0.05,
            random_state=None,
            n_jobs=8,
        ),
        HierachicalLabelMapper(
            max_number_levels=10,
            key_name="emoji",
            max_zoom=1.5,
        ),
    ],
    verbose=True,
)

# %%

# filter chunks that have >=4 data missing scores

chunks = [chunk for chunk in chunks if chunk["missing_data_score"] <= 3]
print(f"Filtered to {len(chunks)} chunks with <4 missing data scores")

# %%
# Create collection from our data
collection = ChunkCollection.load_from_list(l=chunks, pipeline=pipeline)

# %%
collection.process_chunks()

# %%

# %%

for i,chunk in enumerate(collection.chunks):
    chunk.display_text = chunk.display_text + "\n\n" \
            + "Pair ID: " + chunks[i]["pair_id"] + "\n" \
            + "Person A: " + chunks[i]["person_a"] + "\n" \
            + "Person B: " + chunks[i]["person_b"] + "\n" \
            + "First interaction date: " + chunks[i]["first_interaction_date"] + "\n" \
            + "Total interactions: " + str(chunks[i]["total_interactions"]) + "\n" \
            + "Missing data score: " + str(chunks[i]["missing_data_score"]) + "\n" \
            + "Genesis narrative: " + chunks[i]["genesis_narrative"] + "\n" 
    print(chunks[i]["genesis_narrative"])
    print("========")

# %%

visualize_chunks(collection, n_connections=0, )

# %%

for c in collection
