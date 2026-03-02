"""
Histogram generation for strand tweet distribution over time.

Parses dates from thread_text and generates monthly tweet counts.
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import TypedDict


class HistogramData(TypedDict):
    counts: list[int]  # Per-month tweet counts
    total_tweets: int
    date_range: dict  # {"start": "2015-01", "end": "2025-12"}


# Fixed date range to match frontend expectations
START_YEAR = 2015
START_MONTH = 1
END_YEAR = 2025
END_MONTH = 12

# Pre-compute all months in range
ALL_MONTHS = []
for year in range(START_YEAR, END_YEAR + 1):
    for month in range(1, 13):
        ALL_MONTHS.append((year, month))


def _month_to_index(year: int, month: int) -> int:
    """Convert year/month to index in ALL_MONTHS list."""
    return (year - START_YEAR) * 12 + (month - 1)


def generate_histogram(thread_text: str) -> HistogramData:
    """
    Generate histogram data from strand thread_text.

    Parses dates in format [YYYY-MM-DD] from thread_text and counts
    tweets per month over the fixed range 2015-01 to 2025-12.

    Args:
        thread_text: The strand's thread text containing tweet dates

    Returns:
        HistogramData with counts array, total_tweets, and date_range
    """
    # Pattern matches [YYYY-MM-DD] date format in thread_text
    date_pattern = re.compile(r'\[(\d{4})-(\d{2})-\d{2}\]')

    # Count tweets per month
    month_counts = defaultdict(int)

    for match in date_pattern.finditer(thread_text):
        year = int(match.group(1))
        month = int(match.group(2))

        # Only count if within our range
        if START_YEAR <= year <= END_YEAR:
            month_counts[(year, month)] += 1

    # Build counts array for all months
    counts = []
    for year, month in ALL_MONTHS:
        counts.append(month_counts.get((year, month), 0))

    total_tweets = sum(counts)

    return {
        "counts": counts,
        "total_tweets": total_tweets,
        "date_range": {
            "start": f"{START_YEAR:04d}-{START_MONTH:02d}",
            "end": f"{END_YEAR:04d}-{END_MONTH:02d}"
        }
    }


def generate_histogram_export(strands: dict[str, dict]) -> dict:
    """
    Generate histogram export data for frontend.

    Args:
        strands: Dict of strand_id -> strand_data (must have 'histogram' field)

    Returns:
        Export data matching strand_histograms.json format
    """
    # Build months array
    months = []
    for year, month in ALL_MONTHS:
        months.append({
            "year": year,
            "month": month,
            "date": f"{year:04d}-{month:02d}"
        })

    # Build strands data
    strands_export = {}
    for strand_id, strand_data in strands.items():
        histogram = strand_data.get("histogram", {})
        counts = histogram.get("counts", [0] * len(ALL_MONTHS))

        strands_export[str(strand_id)] = {
            "strand_id": str(strand_id),
            "total_tweets": histogram.get("total_tweets", sum(counts)),
            "date_range": histogram.get("date_range", {
                "start": f"{START_YEAR:04d}-{START_MONTH:02d}",
                "end": f"{END_YEAR:04d}-{END_MONTH:02d}"
            }),
            "histogram": counts
        }

    return {
        "generated_at": datetime.now().isoformat(),
        "months": months,
        "strands": strands_export
    }
