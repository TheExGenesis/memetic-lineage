
def create_ascii_chart(dates, width=60, height=10):
    """Create ASCII histogram showing tweet distribution over time"""
    # Check if dates is empty (works with both Series and lists)
    if dates is None or len(dates) == 0:
        return "No temporal data available"
    
    # Convert to datetime if needed
    dates = pd.to_datetime(dates)
    
    # Group by date and count
    date_counts = dates.dt.date.value_counts().sort_index()
    
    if len(date_counts) == 0:
        return "No temporal data available"
    
    # Get date range
    min_date = date_counts.index.min()
    max_date = date_counts.index.max()
    max_count = date_counts.max()
    
    # Create time buckets (up to width buckets)
    date_range = pd.date_range(min_date, max_date, periods=min(width, len(date_counts)))
    
    # Aggregate counts into buckets
    bucket_counts = []
    for i in range(len(date_range)):
        if i < len(date_range) - 1:
            start = date_range[i]
            end = date_range[i + 1]
            # Count tweets in this bucket
            mask = (dates.dt.date >= start.date()) & (dates.dt.date < end.date())
            bucket_counts.append(dates[mask].count())
        else:
            # Last bucket includes end date
            start = date_range[i]
            mask = dates.dt.date >= start.date()
            bucket_counts.append(dates[mask].count())
    
    # Normalize to fit width
    if len(bucket_counts) > width:
        # Combine buckets if we have too many
        new_bucket_counts = []
        bucket_size = len(bucket_counts) / width
        for i in range(width):
            start_idx = int(i * bucket_size)
            end_idx = int((i + 1) * bucket_size)
            new_bucket_counts.append(sum(bucket_counts[start_idx:end_idx]))
        bucket_counts = new_bucket_counts
    
    max_bucket_count = max(bucket_counts) if bucket_counts else 1
    
    # Block characters for different heights (8 levels)
    blocks = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    # Create sparkline-style histogram
    chart_lines = []
    chart_lines.append(f"\nTweet Volume Histogram ({min_date} to {max_date})")
    chart_lines.append("─" * (width + 10))
    
    # Sparkline (single row with varying heights)
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
    
    # X-axis baseline
    chart_lines.append("     └" + "─" * len(bucket_counts))
    
    # X-axis labels (showing time points evenly spaced)
    label_line = "      "
    num_labels = min(5, len(date_range))
    
    if num_labels > 0:
        for i in range(num_labels):
            date_idx = int(i * (len(date_range) - 1) / max(num_labels - 1, 1))
            # Ensure date_idx doesn't exceed bounds
            date_idx = min(date_idx, len(date_range) - 1)
            date_label = date_range[date_idx].strftime('%m/%d/%y')
            
            if i == 0:
                label_line += date_label
            else:
                # Calculate position for this label
                target_pos = 6 + int(i * len(bucket_counts) / max(num_labels - 1, 1))
                current_len = len(label_line)
                spaces_needed = max(2, target_pos - current_len)  # At least 2 spaces between labels
                label_line += " " * spaces_needed + date_label
    
    chart_lines.append(label_line)
    chart_lines.append(f"\n      Total tweets: {len(dates)} | Max per bucket: {max_bucket_count}")
    
    return "\n".join(chart_lines)