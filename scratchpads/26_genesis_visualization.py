# %%
"""
Relationship Genesis Visualization

Loads all pair_genesis_analysis JSONs, combines into flat dataset,
and visualizes:
- Tag temporal statistics
- Distribution plots
- Bird's eye view embedding visualization of narratives
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from typing import Optional

import matplotlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Handle notebook vs script context
try:
    SCRATCHPADS_DIR = Path(__file__).parent
except NameError:
    SCRATCHPADS_DIR = Path.cwd()
    if SCRATCHPADS_DIR.name != 'scratchpads':
        SCRATCHPADS_DIR = SCRATCHPADS_DIR / 'scratchpads'

# %%
# === Configuration ===

ANALYSIS_DIR = SCRATCHPADS_DIR / "data" / "pair_genesis_analysis"
OUTPUT_DIR = SCRATCHPADS_DIR / "data" / "genesis_viz"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# All possible tags from the schema
ALL_TAGS = [
    "in_person_event",
    "matchmaker", 
    "random_reply",
    "quote_tweet_boost",
    "asymmetric_pursuit",
    "long_lurk_first_reply",
    "playful_banter",
    "intellectual_riff",
    "mentorship_vibe",
    "supportive_hype",
    "geographic_hint",
    "fertile",
    "slow_burn",
    "instant_click",
]


# %%
# === Data Loading ===

def load_all_analyses() -> list[dict]:
    """Load all pair genesis analysis JSONs and flatten into list of dicts."""
    files = sorted(ANALYSIS_DIR.glob("*.json"))
    print(f"Found {len(files)} analysis files")
    
    records = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            
            # Flatten the nested structure
            flat = {
                "pair_id": data["pair_id"],
                "person_a": data["person_a"],
                "person_b": data["person_b"],
                "first_interaction_date": data["first_interaction_date"],
                "total_interactions": data["total_interactions"],
                # Flatten analysis fields
                "genesis_narrative": data["analysis"]["genesis_narrative"],
                "neutral_genesis_narrative": data["analysis"].get("neutral_genesis_narrative", ""),
                "missing_data_score": data["analysis"].get("missing_data_score", 3),
                "initiator": data["analysis"]["initiator"],
                "symmetry_score": data["analysis"]["symmetry_score"],
                "interaction_energy": data["analysis"]["interaction_energy"],
                "tags": data["analysis"]["tags"],
                "confidence": data["analysis"]["confidence"],
            }
            
            # Add boolean columns for each tag
            for tag in ALL_TAGS:
                flat[f"tag_{tag}"] = tag in data["analysis"]["tags"]
            
            records.append(flat)
        except Exception as e:
            print(f"Error loading {f.name}: {e}")
    
    print(f"Loaded {len(records)} records")
    return records


def to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Convert records to pandas DataFrame with proper types."""
    df = pd.DataFrame(records)
    
    # Parse dates
    df["first_interaction_date"] = pd.to_datetime(df["first_interaction_date"], errors="coerce")
    
    # Extract year-month for temporal grouping
    df["first_interaction_ym"] = df["first_interaction_date"].dt.to_period("M")
    df["first_interaction_year"] = df["first_interaction_date"].dt.year
    
    return df


# %%
# === Load Data ===

records = load_all_analyses()
df = to_dataframe(records)

print(f"\nDataFrame shape: {df.shape}")
print(f"Date range: {df['first_interaction_date'].min()} to {df['first_interaction_date'].max()}")
print(f"Interaction range: {df['total_interactions'].min()} to {df['total_interactions'].max()}")


# %%
# === Tag Statistics ===

def plot_tag_frequencies(df: pd.DataFrame):
    """Plot overall tag frequencies."""
    tag_cols = [c for c in df.columns if c.startswith("tag_")]
    tag_counts = df[tag_cols].sum().sort_values(ascending=True)
    tag_counts.index = [c.replace("tag_", "") for c in tag_counts.index]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    tag_counts.plot(kind="barh", ax=ax, color="steelblue")
    ax.set_xlabel("Number of Pairs")
    ax.set_title(f"Tag Frequencies (n={len(df):,} pairs)")
    ax.grid(True, alpha=0.3, axis="x")
    
    # Add percentage labels
    for i, (tag, count) in enumerate(tag_counts.items()):
        pct = count / len(df) * 100
        ax.text(count + 5, i, f"{pct:.1f}%", va="center", fontsize=9)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "tag_frequencies.png", dpi=150)
    return plt.show()
    print(f"Saved tag_frequencies.png")


plot_tag_frequencies(df)


# %%
# === Temporal Tag Statistics ===

def plot_tag_temporal_trends(df: pd.DataFrame):
    """Plot how tag frequencies change over time."""
    # Filter to valid dates and reasonable time range
    df_valid = df[df["first_interaction_date"].notna()].copy()
    df_valid = df_valid[df_valid["first_interaction_year"] >= 2018]
    
    # Group by year
    tag_cols = [c for c in df.columns if c.startswith("tag_")]
    yearly = df_valid.groupby("first_interaction_year")[tag_cols].mean()
    yearly.columns = [c.replace("tag_", "") for c in yearly.columns]
    
    # Select most common tags for readability
    top_tags = df_valid[tag_cols].sum().nlargest(8).index
    top_tags = [c.replace("tag_", "") for c in top_tags]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    yearly[top_tags].plot(ax=ax, marker="o", linewidth=2)
    ax.set_xlabel("Year of First Interaction")
    ax.set_ylabel("Proportion of Pairs with Tag")
    ax.set_title("Tag Frequency Over Time (Top 8 Tags)")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, None)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "tag_temporal_trends.png", dpi=150)
    plt.show()
    print(f"Saved tag_temporal_trends.png")


plot_tag_temporal_trends(df)


# %%
# === Tag Co-occurrence ===

def plot_tag_cooccurrence(df: pd.DataFrame):
    """Plot tag co-occurrence matrix."""
    tag_cols = [c for c in df.columns if c.startswith("tag_")]
    tag_matrix = df[tag_cols].astype(int)
    tag_matrix.columns = [c.replace("tag_", "") for c in tag_matrix.columns]
    
    # Compute co-occurrence
    cooccur = tag_matrix.T @ tag_matrix
    
    # Normalize by diagonal (Jaccard-ish)
    diag = np.diag(cooccur)
    with np.errstate(divide='ignore', invalid='ignore'):
        jaccard = cooccur / (diag[:, None] + diag[None, :] - cooccur)
        jaccard = np.nan_to_num(jaccard, 0)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(jaccard, cmap="YlOrRd", vmin=0, vmax=1.0)
    ax.set_xticks(range(len(tag_matrix.columns)))
    ax.set_yticks(range(len(tag_matrix.columns)))
    ax.set_xticklabels(tag_matrix.columns, rotation=45, ha="right")
    ax.set_yticklabels(tag_matrix.columns)
    ax.set_title("Tag Co-occurrence (Jaccard Similarity)")
    plt.colorbar(im, ax=ax, shrink=0.8)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "tag_cooccurrence.png", dpi=150)
    plt.show()
    print(f"Saved tag_cooccurrence.png")


plot_tag_cooccurrence(df)


# %%
# === Interaction Energy Distribution ===

def plot_energy_distribution(df: pd.DataFrame):
    """Plot distribution of interaction energy types."""
    energy_counts = df["interaction_energy"].value_counts()
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Pie chart
    axes[0].pie(energy_counts.values, labels=energy_counts.index, autopct="%1.1f%%",
                colors=plt.cm.Set2.colors)
    axes[0].set_title("Interaction Energy Distribution")
    
    # Bar chart by symmetry score
    energy_by_symmetry = df.groupby(["symmetry_score", "interaction_energy"]).size().unstack(fill_value=0)
    energy_by_symmetry.plot(kind="bar", ax=axes[1], stacked=True, colormap="Set2")
    axes[1].set_xlabel("Symmetry Score")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Energy Type by Symmetry Score")
    axes[1].legend(title="Energy", bbox_to_anchor=(1.02, 1))
    axes[1].tick_params(axis='x', rotation=0)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "energy_distribution.png", dpi=150)
    plt.show()
    print(f"Saved energy_distribution.png")


plot_energy_distribution(df)


# %%
# === Confidence vs Data Quality ===

def plot_confidence_analysis(df: pd.DataFrame):
    """Plot confidence levels and their relationship to data quality."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    
    # Confidence distribution
    conf_counts = df["confidence"].value_counts()
    conf_order = ["high", "medium", "low"]
    conf_counts = conf_counts.reindex([c for c in conf_order if c in conf_counts.index])
    axes[0].bar(conf_counts.index, conf_counts.values, color=["green", "orange", "red"])
    axes[0].set_title("Confidence Level Distribution")
    axes[0].set_ylabel("Count")
    
    # Confidence vs interactions
    for conf in conf_order:
        subset = df[df["confidence"] == conf]["total_interactions"]
        if len(subset) > 0:
            axes[1].hist(subset, bins=30, alpha=0.5, label=conf, 
                        range=(0, df["total_interactions"].quantile(0.95)))
    axes[1].set_xlabel("Total Interactions")
    axes[1].set_ylabel("Count")
    axes[1].set_title("Interactions by Confidence Level")
    axes[1].legend()
    
    # Missing data score distribution
    if "missing_data_score" in df.columns:
        missing_counts = df["missing_data_score"].value_counts().sort_index()
        axes[2].bar(missing_counts.index.astype(str), missing_counts.values, color="steelblue")
        axes[2].set_xlabel("Missing Data Score (1=complete, 5=likely missing)")
        axes[2].set_ylabel("Count")
        axes[2].set_title("Missing Data Score Distribution")
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "confidence_analysis.png", dpi=150)
    plt.show()
    print(f"Saved confidence_analysis.png")


plot_confidence_analysis(df)


# %%
# === Initiator Analysis ===

def plot_initiator_analysis(df: pd.DataFrame):
    """Analyze who typically initiates relationships."""
    init_counts = df["initiator"].value_counts()
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Overall distribution
    colors = {"person_a": "steelblue", "person_b": "coral", "mutual": "green", "unclear": "gray"}
    bar_colors = [colors.get(x, "gray") for x in init_counts.index]
    axes[0].bar(init_counts.index, init_counts.values, color=bar_colors)
    axes[0].set_title("Who Initiates the Relationship?")
    axes[0].set_ylabel("Count")
    
    # Initiator vs symmetry
    init_symmetry = df.groupby("initiator")["symmetry_score"].mean().sort_values()
    axes[1].barh(init_symmetry.index, init_symmetry.values, 
                 color=[colors.get(x, "gray") for x in init_symmetry.index])
    axes[1].set_xlabel("Average Symmetry Score")
    axes[1].set_title("Initiator Type vs Relationship Symmetry")
    axes[1].set_xlim(1, 5)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "initiator_analysis.png", dpi=150)
    plt.show()
    print(f"Saved initiator_analysis.png")


plot_initiator_analysis(df)


# %%
# === Interaction Distribution (Log-Log) ===

def plot_interaction_distribution(df: pd.DataFrame):
    """Plot log-log distribution of interactions."""
    counts = df["total_interactions"].values
    counts = counts[counts > 0]
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Histogram with log bins
    bins = np.logspace(0, np.log10(max(counts) + 1), 40)
    axes[0].hist(counts, bins=bins, edgecolor="black", alpha=0.7)
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Number of Interactions")
    axes[0].set_ylabel("Number of Pairs")
    axes[0].set_title(f"Interaction Distribution (n={len(counts):,})")
    axes[0].grid(True, alpha=0.3)
    
    # Add stats
    median = np.median(counts)
    mean = np.mean(counts)
    axes[0].axvline(median, color="red", linestyle="--", label=f"Median: {median:.0f}")
    axes[0].axvline(mean, color="orange", linestyle="--", label=f"Mean: {mean:.1f}")
    axes[0].legend()
    
    # Rank plot (Zipf-like)
    sorted_counts = np.sort(counts)[::-1]
    ranks = np.arange(1, len(sorted_counts) + 1)
    axes[1].loglog(ranks, sorted_counts, ".", alpha=0.5, markersize=3)
    axes[1].set_xlabel("Rank")
    axes[1].set_ylabel("Number of Interactions")
    axes[1].set_title("Rank-Frequency Plot")
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "interaction_distribution.png", dpi=150)
    plt.show()
    print(f"Saved interaction_distribution.png")
    
    # Print summary
    print(f"Total pairs: {len(counts):,}")
    print(f"Interaction range: {min(counts)} - {max(counts)}")
    print(f"Median: {median:.0f}, Mean: {mean:.1f}")
    print(f"Pairs with 10+: {sum(counts >= 10):,}")
    print(f"Pairs with 50+: {sum(counts >= 50):,}")
    print(f"Pairs with 100+: {sum(counts >= 100):,}")


plot_interaction_distribution(df)


# %%
# === Fertile Relationships Analysis ===

def analyze_fertile_relationships(df: pd.DataFrame):
    """Deep dive into 'fertile' tagged relationships."""
    fertile = df[df["tag_fertile"]]
    non_fertile = df[~df["tag_fertile"]]
    
    print(f"Fertile relationships: {len(fertile):,} ({len(fertile)/len(df)*100:.1f}%)")
    print(f"Non-fertile: {len(non_fertile):,}")
    
    # Compare characteristics
    print("\n--- Comparison ---")
    print(f"Avg interactions - Fertile: {fertile['total_interactions'].mean():.1f}, Non-fertile: {non_fertile['total_interactions'].mean():.1f}")
    print(f"Avg symmetry - Fertile: {fertile['symmetry_score'].mean():.2f}, Non-fertile: {non_fertile['symmetry_score'].mean():.2f}")
    
    # Tag co-occurrence with fertile
    tag_cols = [c for c in df.columns if c.startswith("tag_") and c != "tag_fertile"]
    fertile_cooccur = fertile[tag_cols].mean().sort_values(ascending=False)
    fertile_cooccur.index = [c.replace("tag_", "") for c in fertile_cooccur.index]
    
    print("\nTop tags co-occurring with 'fertile':")
    for tag, pct in fertile_cooccur.head(5).items():
        print(f"  {tag}: {pct*100:.1f}%")


analyze_fertile_relationships(df)

