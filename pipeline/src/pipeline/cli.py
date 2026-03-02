"""CLI entry point for the pipeline."""

import argparse
import sys
import traceback
from datetime import datetime

from pipeline.lib.strand_caches import load_caches, get_quote_tweets_dict


def main():
    parser = argparse.ArgumentParser(
        description="Memetic lineage strand processing pipeline",
        prog="pipeline",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- `pipeline bangers` ---
    bangers_parser = subparsers.add_parser("bangers", help="Generate bangers_tweets.json")
    bangers_parser.add_argument("--parquet", type=str, default=None, help="Path to tweets parquet file")

    # --- `pipeline strands` ---
    strands_parser = subparsers.add_parser("strands", help="Run strands pipeline (phases 1-7)")
    strands_parser.add_argument("--skip-build", action="store_true", help="Skip building strands")
    strands_parser.add_argument("--skip-rate", action="store_true", help="Skip rating strands")
    strands_parser.add_argument("--skip-summary", action="store_true", help="Skip generating summaries")
    strands_parser.add_argument("--skip-histogram", action="store_true", help="Skip generating histograms")
    strands_parser.add_argument("--skip-umap", action="store_true", help="Skip UMAP export")
    strands_parser.add_argument("--skip-atlas", action="store_true", help="Skip atlas export")
    strands_parser.add_argument("--skip-tweet-embeddings", action="store_true", help="Skip tweet embeddings generation")
    strands_parser.add_argument("--skip-atlas-parquet", action="store_true", help="Skip atlas parquet (UMAP on tweets)")
    strands_parser.add_argument("--enrich-only", action="store_true", help="Only add summaries/histograms")
    strands_parser.add_argument("--export-only", action="store_true", help="Only export to frontend")
    strands_parser.add_argument("--force", action="store_true", help="Force regenerate all")
    strands_parser.add_argument("--parquet", type=str, default=None, help="Path to tweets parquet file")
    strands_parser.add_argument("--rating-model", default="anthropic/claude-sonnet-4.5", help="Model for rating")
    strands_parser.add_argument("--summary-model", default="openai/gpt-5.2", help="Model for summaries")

    args = parser.parse_args()

    print("=" * 60)
    print("STRAND PROCESSING PIPELINE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    errors = []

    if args.command is None:
        # No subcommand: run everything (bangers first, then strands)
        _run_bangers(args, errors, parquet_path=None)
        _run_strands(args, errors, all_defaults=True)
    elif args.command == "bangers":
        _run_bangers(args, errors, parquet_path=args.parquet)
    elif args.command == "strands":
        _run_strands(args, errors)
    else:
        parser.print_help()
        sys.exit(1)

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"Finished: {datetime.now().isoformat()}")
    print("=" * 60)

    if errors:
        print(f"\n[ERRORS] {len(errors)} phase(s) had errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\nAll phases completed successfully!")
        sys.exit(0)


def _run_bangers(args, errors: list, parquet_path: str = None):
    """Run bangers data generation (Phase 0)."""
    from pipeline.bangers import run as run_bangers
    try:
        run_bangers(parquet_path=parquet_path)
    except Exception as e:
        errors.append(f"Bangers: {e}")
        print(f"[ERROR] Bangers failed: {e}")
        traceback.print_exc()


def _run_strands(args, errors: list, all_defaults: bool = False):
    """Run the strands pipeline (Phases 1-7)."""
    from pipeline.build_strands import run as run_build
    from pipeline.rate_strands import run as run_rate
    from pipeline.generate_summaries import run as run_summaries
    from pipeline.generate_histograms import run as run_histograms
    from pipeline.generate_embeddings import run_tweet_embeddings, run_atlas_parquet
    from pipeline.export_strands import run_strands_data, run_histograms as run_export_histograms, run_semantic_map, run_atlas
    from pipeline.generate_seriation import run as run_seriation
    from pipeline.generate_summary_text import run as run_summary_text

    # Resolve skip flags
    if all_defaults:
        skip_build = skip_rate = skip_summary = skip_histogram = False
        skip_tweet_embeddings = skip_atlas_parquet = False
        skip_umap = skip_atlas = False
        force = False
        rating_model = "anthropic/claude-sonnet-4.5"
        summary_model = "openai/gpt-5.2"
    else:
        # Shortcut modes
        if getattr(args, 'export_only', False):
            args.skip_build = args.skip_rate = args.skip_summary = args.skip_histogram = True
            args.skip_tweet_embeddings = args.skip_atlas_parquet = True
        if getattr(args, 'enrich_only', False):
            args.skip_build = args.skip_rate = True

        skip_build = getattr(args, 'skip_build', False)
        skip_rate = getattr(args, 'skip_rate', False)
        skip_summary = getattr(args, 'skip_summary', False)
        skip_histogram = getattr(args, 'skip_histogram', False)
        skip_tweet_embeddings = getattr(args, 'skip_tweet_embeddings', False)
        skip_atlas_parquet = getattr(args, 'skip_atlas_parquet', False)
        skip_umap = getattr(args, 'skip_umap', False)
        skip_atlas = getattr(args, 'skip_atlas', False)
        force = getattr(args, 'force', False)
        rating_model = getattr(args, 'rating_model', "anthropic/claude-sonnet-4.5")
        summary_model = getattr(args, 'summary_model', "openai/gpt-5.2")

    # Phase 1: Build
    if not skip_build:
        try:
            tweet_dict, conversation_trees = load_caches()
            quote_dict = get_quote_tweets_dict()
            run_build(tweet_dict, quote_dict, conversation_trees, force_rebuild=force)
        except Exception as e:
            errors.append(f"Phase 1 (Build): {e}")
            print(f"[ERROR] Phase 1 failed: {e}")

    # Phase 2: Rate
    if not skip_rate:
        try:
            run_rate(model_name=rating_model)
        except Exception as e:
            errors.append(f"Phase 2 (Rate): {e}")
            print(f"[ERROR] Phase 2 failed: {e}")

    # Phase 3: Summaries
    if not skip_summary:
        try:
            run_summaries(model_name=summary_model, force_regenerate=force)
        except Exception as e:
            errors.append(f"Phase 3 (Summary): {e}")
            print(f"[ERROR] Phase 3 failed: {e}")

    # Phase 4: Histograms
    if not skip_histogram:
        try:
            run_histograms(force_regenerate=force)
        except Exception as e:
            errors.append(f"Phase 4 (Histogram): {e}")
            print(f"[ERROR] Phase 4 failed: {e}")

    # Phase 4.5: Tweet Embeddings
    if not skip_tweet_embeddings:
        try:
            run_tweet_embeddings(force_regenerate=force)
        except Exception as e:
            errors.append(f"Phase 4.5 (Tweet Embeddings): {e}")
            print(f"[ERROR] Phase 4.5 failed: {e}")

    # Phase 4.6: Atlas Parquet
    if not skip_atlas_parquet:
        try:
            run_atlas_parquet(force_regenerate=force)
        except Exception as e:
            errors.append(f"Phase 4.6 (Atlas Parquet): {e}")
            print(f"[ERROR] Phase 4.6 failed: {e}")

    # Phase 5: Export strands data
    try:
        if not run_strands_data():
            errors.append("Phase 5 (Export Strands Data): Failed")
    except Exception as e:
        errors.append(f"Phase 5 (Export Strands Data): {e}")
        print(f"[ERROR] Phase 5 failed: {e}")

    # Phase 5a: Export histograms
    try:
        if not run_export_histograms():
            errors.append("Phase 5a (Export Histograms): Missing histogram data")
    except Exception as e:
        errors.append(f"Phase 5a (Export Histograms): {e}")
        print(f"[ERROR] Phase 5a failed: {e}")

    # Phase 5b: Export UMAP
    if not skip_umap:
        try:
            if not run_semantic_map():
                errors.append("Phase 5b (Export UMAP): Missing summary data")
        except Exception as e:
            errors.append(f"Phase 5b (Export UMAP): {e}")
            print(f"[ERROR] Phase 5b failed: {e}")

    # Phase 5c: Export Atlas
    if not skip_atlas:
        try:
            if not run_atlas():
                print("[WARN] Phase 5c: Atlas parquet not available, skipping")
        except Exception as e:
            errors.append(f"Phase 5c (Export Atlas): {e}")
            print(f"[ERROR] Phase 5c failed: {e}")

    # Phase 6: Generate Seriation Order
    try:
        if not run_seriation():
            print("[WARN] Phase 6: Could not generate seriation order")
    except Exception as e:
        errors.append(f"Phase 6 (Seriation): {e}")
        print(f"[ERROR] Phase 6 failed: {e}")

    # Phase 7: Generate Chronological Summary
    try:
        if not run_summary_text():
            print("[WARN] Phase 7: Could not generate chronological summary")
    except Exception as e:
        errors.append(f"Phase 7 (Chronological Summary): {e}")
        print(f"[ERROR] Phase 7 failed: {e}")
