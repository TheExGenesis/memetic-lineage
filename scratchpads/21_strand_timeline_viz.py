#!/usr/bin/env python3
"""
Create timeline visualizations for strand exploration.
"""

import json
from datetime import datetime
from collections import defaultdict
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load data
with open('data/all_strands_context.json') as f:
    strands = json.load(f)

with open('exploration_workspace/people_mapping.json') as f:
    people_data = json.load(f)

def tweet_id_to_date(tweet_id):
    timestamp_ms = ((tweet_id >> 22) + 1288834974657)
    return datetime.fromtimestamp(timestamp_ms / 1000)

# Sort strands chronologically
strands = sorted(strands, key=lambda s: s['seed_tweet_id'])

# Add dates
for s in strands:
    s['date'] = tweet_id_to_date(s['seed_tweet_id'])

#################################################
# FIGURE 1: Strand timeline with ratings
#################################################

fig1 = go.Figure()

# Color by rating
colors = []
for s in strands:
    r = s.get('rating', {}).get('rating', 5)
    if r >= 8:
        colors.append('#2ecc71')  # green
    elif r >= 6:
        colors.append('#3498db')  # blue
    elif r >= 4:
        colors.append('#f39c12')  # orange
    else:
        colors.append('#e74c3c')  # red

fig1.add_trace(go.Scatter(
    x=[s['date'] for s in strands],
    y=[s.get('rating', {}).get('rating', 5) for s in strands],
    mode='markers+text',
    marker=dict(
        size=12,
        color=colors,
        opacity=0.7,
        line=dict(width=1, color='white')
    ),
    text=[str(i+1) for i in range(len(strands))],
    textposition='top center',
    textfont=dict(size=8),
    hovertemplate='<b>%{customdata[0]}</b><br>Date: %{x}<br>Rating: %{y}/10<extra></extra>',
    customdata=[[s['title'][:60]] for s in strands]
))

fig1.update_layout(
    title='100 Strands Timeline (colored by rating)',
    xaxis_title='Date',
    yaxis_title='Rating (0-10)',
    yaxis=dict(range=[0, 11]),
    height=500,
    showlegend=False
)

fig1.write_html('exploration_workspace/strand_timeline.html')
print("Saved: exploration_workspace/strand_timeline.html")

#################################################
# FIGURE 2: Strand count by quarter
#################################################

fig2 = go.Figure()

# Group by quarter
quarters = defaultdict(int)
for s in strands:
    q = f"{s['date'].year}-Q{(s['date'].month-1)//3+1}"
    quarters[q] += 1

# Sort quarters
sorted_quarters = sorted(quarters.items())
qs = [q for q, _ in sorted_quarters]
counts = [c for _, c in sorted_quarters]

fig2.add_trace(go.Bar(
    x=qs,
    y=counts,
    marker_color='#3498db'
))

fig2.update_layout(
    title='Strand Count by Quarter',
    xaxis_title='Quarter',
    yaxis_title='Number of Strands',
    height=400
)

fig2.write_html('exploration_workspace/strand_quarters.html')
print("Saved: exploration_workspace/strand_quarters.html")

#################################################
# FIGURE 3: Top people activity over time
#################################################

top_people = [p for p, _ in people_data['top_people'][:12]]
person_strands = people_data['person_strands']

fig3 = make_subplots(rows=4, cols=3, subplot_titles=top_people)

for idx, person in enumerate(top_people):
    row = idx // 3 + 1
    col = idx % 3 + 1

    strands_list = person_strands[person]
    by_quarter = defaultdict(int)
    for s in strands_list:
        dt = datetime.fromisoformat(s['date'])
        q = f"{dt.year}-Q{(dt.month-1)//3+1}"
        by_quarter[q] += 1

    # All quarters
    all_quarters = sorted(quarters.keys())
    counts = [by_quarter.get(q, 0) for q in all_quarters]

    fig3.add_trace(
        go.Scatter(x=all_quarters, y=counts, mode='lines+markers',
                   name=person, line=dict(width=2)),
        row=row, col=col
    )

fig3.update_layout(
    title='Top 12 People: Activity Over Time',
    height=800,
    showlegend=False
)

fig3.write_html('exploration_workspace/people_activity.html')
print("Saved: exploration_workspace/people_activity.html")

#################################################
# FIGURE 4: Rating distribution by era
#################################################

eras = {
    'Foundation (2016-2019)': (datetime(2016, 1, 1), datetime(2020, 1, 1)),
    'COVID/Golden (2020)': (datetime(2020, 1, 1), datetime(2021, 1, 1)),
    'Crystallization (2021)': (datetime(2021, 1, 1), datetime(2022, 1, 1)),
    'Framework (2022)': (datetime(2022, 1, 1), datetime(2023, 1, 1)),
    'Real-World (2023-24)': (datetime(2023, 1, 1), datetime(2025, 1, 1)),
    'Infrastructure (2025+)': (datetime(2025, 1, 1), datetime(2030, 1, 1)),
}

era_ratings = defaultdict(list)
for s in strands:
    for era_name, (start, end) in eras.items():
        if start <= s['date'] < end:
            era_ratings[era_name].append(s.get('rating', {}).get('rating', 5))
            break

fig4 = go.Figure()

era_names = list(eras.keys())
avg_ratings = [sum(era_ratings[e])/len(era_ratings[e]) if era_ratings[e] else 0 for e in era_names]
counts = [len(era_ratings[e]) for e in era_names]

fig4.add_trace(go.Bar(
    x=era_names,
    y=avg_ratings,
    text=[f'{r:.1f} ({c} strands)' for r, c in zip(avg_ratings, counts)],
    textposition='auto',
    marker_color=['#95a5a6', '#2ecc71', '#3498db', '#9b59b6', '#e67e22', '#1abc9c']
))

fig4.update_layout(
    title='Average Rating by Era',
    xaxis_title='Era',
    yaxis_title='Average Rating',
    yaxis=dict(range=[0, 10]),
    height=400
)

fig4.write_html('exploration_workspace/era_ratings.html')
print("Saved: exploration_workspace/era_ratings.html")

#################################################
# FIGURE 5: Interactive strand browser
#################################################

fig5 = go.Figure()

fig5.add_trace(go.Scatter(
    x=[s['date'] for s in strands],
    y=[s.get('rating', {}).get('rating', 5) for s in strands],
    mode='markers',
    marker=dict(
        size=[10 + s.get('rating', {}).get('rating', 5) for s in strands],
        color=[s.get('rating', {}).get('rating', 5) for s in strands],
        colorscale='Viridis',
        showscale=True,
        colorbar=dict(title='Rating'),
        opacity=0.8
    ),
    hovertemplate=(
        '<b>%{customdata[0]}</b><br><br>'
        'Date: %{x}<br>'
        'Rating: %{customdata[1]}/10<br>'
        'Evolution: %{customdata[2]}<br>'
        'Cohesion: %{customdata[3]}<br>'
        'Utility: %{customdata[4]}<br><br>'
        '<i>%{customdata[5]}</i>'
        '<extra></extra>'
    ),
    customdata=[
        [
            s['title'],
            s.get('rating', {}).get('rating', '?'),
            s.get('rating', {}).get('evolution', '?'),
            s.get('rating', {}).get('cohesion', '?'),
            s.get('rating', {}).get('utility', '?'),
            (s.get('summary', '')[:200] + '...') if len(s.get('summary', '')) > 200 else s.get('summary', '')
        ]
        for s in strands
    ]
))

fig5.update_layout(
    title='Interactive Strand Explorer',
    xaxis_title='Date',
    yaxis_title='Rating',
    height=600,
    hovermode='closest'
)

fig5.write_html('exploration_workspace/strand_explorer.html')
print("Saved: exploration_workspace/strand_explorer.html")

print("\nAll visualizations saved to exploration_workspace/")
