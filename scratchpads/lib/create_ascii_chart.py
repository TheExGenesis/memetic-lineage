# %%
import pandas as pd


def create_ascii_chart(dates, width=100, height=10, min_date=None, max_date=None):
    """Create ASCII histogram showing tweet distribution over time
    
    Args:
        dates: Series or list of datetime objects
        width: Width of the chart in characters (default 100)
        height: Height parameter (currently unused, kept for compatibility)
        min_date: Optional minimum date to display (datetime or string)
        max_date: Optional maximum date to display (datetime or string)
    """
    # Check if dates is empty (works with both Series and lists)
    if dates is None or len(dates) == 0:
        return "No temporal data available"
    
    # Convert to datetime if needed
    dates = pd.to_datetime(dates)
    
    # Filter dates by min_date and max_date if provided
    if min_date is not None:
        min_date = pd.to_datetime(min_date)
        # Ensure timezone compatibility
        if dates.dt.tz is not None and min_date.tz is None:
            min_date = min_date.tz_localize(dates.dt.tz)
        elif dates.dt.tz is None and min_date.tz is not None:
            min_date = min_date.tz_localize(None)
        dates = dates[dates >= min_date]
    
    if max_date is not None:
        max_date = pd.to_datetime(max_date)
        # Ensure timezone compatibility
        if dates.dt.tz is not None and max_date.tz is None:
            max_date = max_date.tz_localize(dates.dt.tz)
        elif dates.dt.tz is None and max_date.tz is not None:
            max_date = max_date.tz_localize(None)
        dates = dates[dates <= max_date]
    
    if len(dates) == 0:
        return "No temporal data available in specified date range"
    
    # Group by date and count
    date_counts = dates.dt.date.value_counts().sort_index()
    
    if len(date_counts) == 0:
        return "No temporal data available"
    
    # Get date range (use provided min/max if available, otherwise use data range)
    data_min_date = date_counts.index.min()
    data_max_date = date_counts.index.max()
    
    if min_date is not None:
        display_min_date = min_date.date() if hasattr(min_date, 'date') else min_date
    else:
        display_min_date = data_min_date
    
    if max_date is not None:
        display_max_date = max_date.date() if hasattr(max_date, 'date') else max_date
    else:
        display_max_date = data_max_date
    
    max_count = date_counts.max()
    
    # Create time buckets - always use exactly 'width' buckets for consistent display
    date_range = pd.date_range(display_min_date, display_max_date, periods=width + 1)
    
    # Aggregate counts into buckets - always create exactly 'width' buckets
    bucket_counts = []
    for i in range(width):
        start = date_range[i]
        end = date_range[i + 1]
        # Count tweets in this bucket
        mask = (dates.dt.date >= start.date()) & (dates.dt.date < end.date())
        bucket_counts.append(dates[mask].count())
    
    max_bucket_count = max(bucket_counts) if bucket_counts else 1
    
    # Block characters for different heights (8 levels)
    blocks = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    # Create sparkline-style histogram
    chart_lines = []
    chart_lines.append(f"\nTweet Volume Histogram ({display_min_date} to {display_max_date})")
    chart_lines.append("─" * (width + 10))
    
    # Sparkline (single row with varying heights) - always exactly 'width' characters
    sparkline = "     │"
    for count in bucket_counts:
        # Normalize to 0-8 range
        if max_bucket_count > 0:
            level = int((count / max_bucket_count) * 8)
            level = min(8, level)  # Cap at 8
        else:
            level = 0
        sparkline += blocks[level]
    chart_lines.append(sparkline)
    
    # X-axis baseline - always exactly 'width' characters
    chart_lines.append("     └" + "─" * width)
    
    # X-axis labels (showing time points evenly spaced)
    label_line = "      "
    num_labels = 5
    
    for i in range(num_labels):
        date_idx = int(i * (len(date_range) - 1) / (num_labels - 1))
        # Ensure date_idx doesn't exceed bounds
        date_idx = min(date_idx, len(date_range) - 1)
        date_label = date_range[date_idx].strftime('%m/%d/%y')
        
        if i == 0:
            label_line += date_label
        else:
            # Calculate position for this label
            target_pos = 6 + int(i * width / (num_labels - 1))
            current_len = len(label_line)
            spaces_needed = max(2, target_pos - current_len)  # At least 2 spaces between labels
            label_line += " " * spaces_needed + date_label
    
    chart_lines.append(label_line)
    chart_lines.append(f"\n      Total tweets: {len(dates)} | Max per bucket: {max_bucket_count}")
    
    return "\n".join(chart_lines)
# %%
