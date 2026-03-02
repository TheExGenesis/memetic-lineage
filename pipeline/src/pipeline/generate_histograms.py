"""Phase 4: Generate tweet distribution histograms."""

from pipeline.helpers import load_all_rated_strands, save_rated_strand
from pipeline.lib.histogram import generate_histogram


def run(force_regenerate: bool = False) -> int:
    """Generate histograms for strands. Updates rated_strands in-place."""
    print("\n" + "=" * 60)
    print("PHASE 4: Generate Histograms")
    print("=" * 60)

    all_strands = load_all_rated_strands()
    print(f"Loaded {len(all_strands)} rated strands")

    updated_count = 0

    for strand_id, data in all_strands.items():
        if not force_regenerate and data.get("histogram"):
            continue

        thread_text = data.get("thread_text", "")
        if not thread_text:
            print(f"[WARN] Strand {strand_id} has no thread_text")
            continue

        histogram = generate_histogram(thread_text)
        data["histogram"] = histogram

        save_rated_strand(strand_id, data)
        updated_count += 1

    print(f"Generated histograms for {updated_count} strands")
    return updated_count
