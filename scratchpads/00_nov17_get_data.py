# %%
import json
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.distance import cdist
# %%
import pandas as pd
# Read all parquet files in a directory
import glob
all_files = glob.glob('../CA_embeddings/embedding-queue/*.pending.parquet')
# Sort files by date extracted from filename (format: queue-YYYY-MM-DDTHH-MM-SS-...)
# Extract timestamp from filename and sort in descending order (most recent first)
import re
from datetime import datetime

def extract_timestamp(filepath):
    """Extract timestamp from filename like 'queue-2025-10-30T20-25-17-979Z-...'"""
    match = re.search(r'queue-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)', filepath)
    if match:
        timestamp_str = match.group(1)
        # Convert to datetime object (replace hyphens in time part with colons)
        timestamp_str = timestamp_str.replace('T', 'T').replace('-', ':', 3).replace('-', ':', 1)
        # Format: 2025-10-30T20:25:17:979Z -> need to handle milliseconds
        timestamp_str = timestamp_str.replace(':', '-', 2)  # Restore date part
        timestamp_str = timestamp_str[:19]  # Remove milliseconds and Z
        return datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
    return datetime.min  # Return minimum date if parsing fails

# Sort files by timestamp (most recent first) and take the 1000 most recent
all_files_sorted = sorted(all_files, key=extract_timestamp, reverse=True)
all_files = all_files_sorted[:300]

print(f"Processing {len(all_files)} most recent files")
if all_files:
    print(f"Most recent file: {all_files[0]}")
    print(f"Oldest file in selection: {all_files[-1]}")


df_all = pd.concat([pd.read_parquet(f) for f in all_files], ignore_index=True)

# %% Apply PCA to the data, taking the column named v0 to v1023
embedding_cols = [f'v{i}' for i in range(1018)]
X_all = df_all[embedding_cols]


# %% 
import umap
import pickle
import os

umap_dim = 5  # target dimension for visualization
cache_dir = 'cache'
os.makedirs(cache_dir, exist_ok=True)

# Create cache filename based on number of rows and umap dimensions
cache_key = f"n{len(df_all)}_dim{umap_dim}"
umap_cache_file = os.path.join(cache_dir, f'umap_{cache_key}.pkl')

# Try to load cached UMAP results
if os.path.exists(umap_cache_file):
    print(f"Loading cached UMAP results from {umap_cache_file}...")
    with open(umap_cache_file, 'rb') as f:
        cache_data = pickle.load(f)
        df_all_umap = cache_data['df_all_umap']
        umap_model = cache_data['umap_model']
    print(f"Loaded UMAP results with shape {df_all_umap.shape}")
else:
    print("Computing UMAP dimensionality reduction...")
    umap_model = umap.UMAP(n_components=umap_dim, n_jobs=8, verbose=True)
    df_all_umap_array = umap_model.fit_transform(X_all)

# As a DataFrame (optional)
    df_all_umap = pd.DataFrame(df_all_umap_array, columns=[f'umap_{i}' for i in range(umap_dim)])
    
    # Save to cache
    print(f"Saving UMAP results to {umap_cache_file}...")
    with open(umap_cache_file, 'wb') as f:
        pickle.dump({
            'df_all_umap': df_all_umap,
            'umap_model': umap_model
        }, f)
    print("UMAP results cached successfully")

# %%
from sklearn.cluster import KMeans

X = df_all_umap.copy()

# Perform KMeans clustering on the UMAP vectors
n_clusters = 550  # You can change this value as needed

# Create cache filename based on data size and number of clusters
kmeans_cache_key = f"n{len(X)}_k{n_clusters}"
kmeans_cache_file = os.path.join(cache_dir, f'kmeans_{kmeans_cache_key}.pkl')

# Try to load cached K-Means results
if os.path.exists(kmeans_cache_file):
    print(f"Loading cached K-Means results from {kmeans_cache_file}...")
    with open(kmeans_cache_file, 'rb') as f:
        cache_data = pickle.load(f)
        kmeans = cache_data['kmeans']
        X['cluster'] = cache_data['labels']
    print(f"Loaded K-Means clustering with {n_clusters} clusters")
else:
    print(f"Computing K-Means clustering with {n_clusters} clusters...")
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    kmeans.fit(X)

    # Assign cluster labels to each row
    X['cluster'] = kmeans.labels_
    
    # Save to cache
    print(f"Saving K-Means results to {kmeans_cache_file}...")
    with open(kmeans_cache_file, 'wb') as f:
        pickle.dump({
            'kmeans': kmeans,
            'labels': kmeans.labels_
        }, f)
    print("K-Means results cached successfully")

# Optionally, print the number of items in each cluster
print(X['cluster'].value_counts())

# %%

# Print the metadata of the original df from 5 clusters

# We'll print the metadata (let's use df.head(), columns, dtypes) for original df rows from 5 clusters.

# First, join the clusters back to the original df_all DataFrame
df_all_with_clusters = df_all.copy()
df_all_with_clusters = df_all_with_clusters.reset_index(drop=True)
df_all_with_clusters['cluster'] = X['cluster'].values

# Now, select 5 random clusters (or top 5 cluster labels if preferred)
clusters_to_show = df_all_with_clusters['cluster'].unique()[:5]

for cluster_label in clusters_to_show:
    print(f"\n=== Metadata for cluster {cluster_label} ===")
    cluster_df = df_all_with_clusters[df_all_with_clusters['cluster'] == cluster_label]
    # Find the 50 points in this cluster that are closest to the centroid
    
    # Get the numerical features DataFrame that was used for clustering
    cluster_idx = cluster_label
    
    # Find the indices of the points in X that belong to this cluster
    cluster_indices = X.index[X['cluster'] == cluster_idx].tolist()
    
    # Get the centroid for this cluster
    centroid = kmeans.cluster_centers_[cluster_idx]
    
    # Get only the feature columns used for KMeans (exclude 'cluster')
    feature_columns = [col for col in X.columns if col != 'cluster']
    X_cluster = X.loc[cluster_indices, feature_columns]
    
    # Compute the distances to the centroid
    distances = cdist(X_cluster.values, centroid.reshape(1, -1), metric='euclidean').flatten()
    
    # Get the indices of the 50 closest points
    closest_point_indices = np.argsort(distances)[:50]
    closest_indices_in_X = X_cluster.index[closest_point_indices]

    # Select these points from cluster_df (which is aligned with df_all_with_clusters)
    cluster_df = cluster_df.loc[closest_indices_in_X]

    for idx, row in cluster_df[:50].iterrows():
        try:
            metadata = json.loads(row['metadata'])
            print(metadata.get("original_text", "No original_text found"))
            print("--------------------------------")
        except Exception as e:
            print(f"Error reading metadata for index {idx}: {e}")


# %%

# Reduce dimension to 2 using PCA for visualization
import umap
import numpy as np
import matplotlib.pyplot as plt

# Get the feature columns used for KMeans (exclude 'cluster')
feature_columns = [col for col in X.columns if col != 'cluster']
X_features = X[feature_columns][:50000]

# Reduce the data to 2 dimensions for visualization using UMAP
umap_2d = umap.UMAP(n_components=2, n_jobs=8, verbose=True)
df_2d = umap_2d.fit_transform(X_features)

# Transform the original centroids to 2D using the fitted UMAP
centroids_high_dim = kmeans.cluster_centers_
centroids_2d = umap_2d.transform(centroids_high_dim)
# %%

n_points = df_2d.shape[0]
sample_size = max(1, int(n_points))
sample_indices = np.random.choice(n_points, size=sample_size, replace=False)
sample_points = df_2d[sample_indices]
sample_labels = kmeans.labels_[sample_indices]
# %%
from bokeh.plotting import figure, show, output_notebook
from bokeh.models import HoverTool, ColumnDataSource, WheelZoomTool
from bokeh.palettes import Category20_20
import pandas as pd

# Prepare the data for Bokeh
# Extract original_text from metadata for the sampled points
metadata_list = []
for idx in sample_indices:
    try:
        metadata = json.loads(df_all_with_clusters.iloc[idx]['metadata'])
        metadata_list.append(metadata.get("original_text", "No text available"))
    except:
        metadata_list.append("Error loading text")

# Create a color palette
colors = Category20_20 if n_clusters <= 20 else Category20_20 * (n_clusters // 20 + 1)
color_map = {i: colors[i % len(colors)] for i in range(n_clusters)}
point_colors = [color_map[label] for label in sample_labels]

# Create ColumnDataSource for scatter points
source = ColumnDataSource(data=dict(
    x=sample_points[:, 0],
    y=sample_points[:, 1],
    cluster=sample_labels,
    text=metadata_list,
    color=point_colors
))

# Create ColumnDataSource for centroids
centroid_source = ColumnDataSource(data=dict(
    x=centroids_2d[:, 0],
    y=centroids_2d[:, 1],
    cluster=list(range(n_clusters))
))

# Create the figure
p = figure(
    width=900,
    height=700,
    title='KMeans clusters (centroids and 5% sample, UMAP)',
    tools='pan,wheel_zoom,box_zoom,reset,save',
    x_axis_label='UMAP Dimension 1',
    y_axis_label='UMAP Dimension 2'
)

# Set wheel zoom as the active scroll tool
p.toolbar.active_scroll = p.select_one(WheelZoomTool)

# Add scatter plot for sampled points
scatter = p.circle(
    'x', 'y',
    source=source,
    size=8,
    color='color',
    alpha=0.6,
    legend_field='cluster'
)

# Add hover tool for scatter points
hover = HoverTool(
    renderers=[scatter],
    tooltips=[
        ("Cluster", "@cluster"),
        ("Original Text", "@text{safe}")
    ]
)
p.add_tools(hover)

# Add centroids as X markers
p.x(
    'x', 'y',
    source=centroid_source,
    size=20,
    color='black',
    line_width=2,
    legend_label='Centroids'
)

p.legend.title = 'Cluster'
p.legend.click_policy = "hide"

output_notebook()
show(p)

# %%

enriched_tweets = pd.read_parquet('enriched_tweets.parquet')
enriched_tweets.head()

# %%
print("Extracting tweet IDs from df_all metadata...")
# %%
# More efficient: use apply() instead of iterrows()
def extract_tweet_id(metadata_str):
    try:
        metadata = json.loads(metadata_str)
        return metadata.get('original_text')
    except:
        return None

# apply the function to the metadata column
og_text = df_all.metadata.apply(extract_tweet_id)

# %%
# Filter enriched_tweets to only include rows where full_text matches og_text
# Remove duplicates based on full_text
filtered_enriched_tweets = enriched_tweets[enriched_tweets['full_text'].isin(og_text)].drop_duplicates(subset='full_text')

print(f"Original enriched_tweets shape: {enriched_tweets.shape}")
print(f"Filtered enriched_tweets shape: {filtered_enriched_tweets.shape}")
print(f"Number of unique og_text values: {og_text.nunique()}")

# %%

# %%

# %%
# Check if created_at column exists
if 'created_at' in filtered_enriched_tweets.columns:
    # Convert created_at to datetime if it's not already
    filtered_enriched_tweets['created_at'] = pd.to_datetime(filtered_enriched_tweets['created_at'])
    
    # Plot histogram of created_at dates
    plt.figure(figsize=(14, 12))
    
    # Plot 1: Histogram by date
    plt.subplot(2, 1, 1)
    date_counts = filtered_enriched_tweets['created_at'].dt.date.value_counts().sort_index()
    date_counts.plot(kind='bar')
    plt.title('Tweet Distribution by Date')
    plt.xlabel('Year')
    plt.ylabel('Number of Tweets')
    # Get unique years from the dates
    dates = date_counts.index
    years = sorted(set(pd.to_datetime(dates).year))
    # Set x-axis to show only years
    ax = plt.gca()
    tick_positions = []
    tick_labels = []
    for year in years:
        year_dates = [d for d in dates if pd.to_datetime(d).year == year]
        if year_dates:
            tick_positions.append(list(dates).index(year_dates[0]))
            tick_labels.append(str(year))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=0)
    plt.tight_layout()
    
    # Plot 2: Histogram by hour of day
    plt.subplot(2, 1, 2)
    filtered_enriched_tweets['created_at'].dt.hour.value_counts().sort_index().plot(kind='bar')
    plt.title('Tweet Distribution by Hour of Day')
    plt.xlabel('Hour (UTC)')
    plt.ylabel('Number of Tweets')
    plt.tight_layout()
    
    plt.show()
    
    # Print some statistics
    print("\n=== Tweet Timeline Statistics ===")
    print(f"Earliest tweet: {filtered_enriched_tweets['created_at'].min()}")
    print(f"Latest tweet: {filtered_enriched_tweets['created_at'].max()}")
    print(f"Date range: {(filtered_enriched_tweets['created_at'].max() - filtered_enriched_tweets['created_at'].min()).days} days")
    print(f"\nTop 5 most active dates:")
    print(filtered_enriched_tweets['created_at'].dt.date.value_counts().head())
else:
    print(f"Warning: 'created_at' column not found in enriched_tweets")
    print(f"Available columns: {filtered_enriched_tweets.columns.tolist()}")

# Store filtered tweets for later use
df_all_enriched = filtered_enriched_tweets


# %%

# Find 10 clusters and name them using LLM
from groq import Groq
from pydantic import BaseModel
import os

# Set your GROQ API key
#os.environ['GROQ_API_KEY'] = ""

# Initialize Groq client
client = Groq()

n_clusters_for_naming = 550

# Define the structured output model
class ClusterAnalysis(BaseModel):
    reasoning: str
    discourse_coherence_score: int
    generative_density_score: int
    temporal_coherence_score: int
    cluster_name: str  # Short, descriptive name (2-5 words)

# For each cluster, get 50 sample tweets
def get_cluster_name(cluster_id, texts):
    """Send 50 tweets from a cluster to LLM and ask it to name the cluster."""
    # Prepare the prompt with sample tweets
    sample_text = "\n".join([f"- {text}" for text in texts[:50]])
    
    prompt = f"""You are analyzing a cluster of tweets. Below are sample tweets from this cluster.

# Instructions:

All right, so we have rough clusters of tweets. And what we want is to find high quality strands of discourse or narrative within those clusters. So the hypothesis is that a cluster of embeddings of tweets will correspond closely enough to such a strand of discourse. For example, we could be discussing some specific topic in AI safety like EU regulation or the rise of Janas, the meditative state, over time from being discovered within a specific community to turning mainstream. Or we could be interested in some specific flare up of dating discourse, maybe about age gap relationships or some specific birthday or G. These are just examples, but the point is that we're trying to identify coherent high quality strands of discourse in clusters. And what we want you to do is you're going to look at each of these clusters one at a time and you will score the clusters based on how coherent and interesting they are. Things that are not interesting include flat groupings of the same superficial semantic meaning. So a cluster that's just about animals in general or a cluster that's just about food in general or interactions between people where the interactions have the same sentiments but aren't necessarily connected thematically. Examples of clusters that would be interesting include clusters where a lot of the posts seem to be replying to each other or at least referencing one another and referring to the same events and concepts. Importantly, we are not interested in thematic grouping. We are not interested in fighting tweets that are only about the same theme, about the same topic. We are interested in candidates for new cultural production. Does it feel like this cluster is introducing something? It's like making something new. The people are piecing puzzles together to create new discourse out of all cultural meme. That's a thing we're interested in. So it's like a special case of thematic tightness. It should be about the same theme but not all thematic clusters link to new cultural production. That's right. The cluster doesn't necessarily have to be fully coherent as long as we can identify an interesting strand within the cluster.

!important: don't use quotes in the output, follow the json schema.

# Rubric scores:

**discourse coherence (0-10)**: not just thematic similarity but actual conversational threading - are people responding to/building on each other's ideas? referencing the same specific events, papers, people? you want to distinguish "everyone talking about AI" from "everyone discussing that specific yudkowsky post from tuesday"

**generative density (0-10)**: this is your "new cultural production" metric. are people synthesizing? coining terms? creating frameworks? you can spot this through novel metaphors, emergent terminology, conceptual bridges between previously unconnected ideas. a cluster about "animals" scores low, but "applying predator-prey dynamics to social media algorithms" might score high

**temporal coherence (0-10)**: does the cluster represent an actual unfolding discourse with a beginning, middle, development? or is it just random samples of similar content across time? look for cascading responses, evolution of arguments, people changing positions

# Output format

1. Provide your reasoning about what these tweets have in common and what theme or topic they represent.
2. Give the scores from the rubric from 1 to 10
3. Provide a short, descriptive name (2-5 words) for this cluster that captures the main theme or topic.

# Tweets:
{sample_text}

"""
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "cluster_analysis",
                    "schema": ClusterAnalysis.model_json_schema()
                }
            }
        )
        # Parse the structured response using Pydantic validation
        analysis = ClusterAnalysis.model_validate(json.loads(response.choices[0].message.content))
        return analysis
    except Exception as e:
        print(f"Error naming cluster {cluster_id}: {e}")
        # Return a default structured response on error
        return ClusterAnalysis(
            reasoning=f"Error occurred: {str(e)}",
            discourse_coherence_score=0,
            generative_density_score=0,
            temporal_coherence_score=0,
            cluster_name=f"Cluster {cluster_id}"
        )


# %%
# Collect tweets for each cluster
# Get the top n_clusters_for_naming clusters by size
cluster_counts = X['cluster'].value_counts()
top_clusters = cluster_counts.head(n_clusters_for_naming).index.tolist()

cluster_tweets = {}
for cluster_label in top_clusters:
    print(f"\n=== Extracting texts from cluster {cluster_label} ===")
    
    # Find the indices of the points in X that belong to this cluster
    cluster_indices = X.index[X['cluster'] == cluster_label].tolist()
    
    # Extract original_text from metadata and match with enriched tweets
    cluster_data = []
    for idx in cluster_indices:
        try:
            metadata = json.loads(df_all_with_clusters.iloc[idx]['metadata'])
            original_text = metadata.get("original_text", "")
            if original_text:
                cluster_data.append({
                    'idx': idx,
                    'text': original_text
                })
        except Exception as e:
            continue
    
    # Create DataFrame and match with enriched tweets
    cluster_df = pd.DataFrame(cluster_data)
    
    # Match with filtered_enriched_tweets based on text
    cluster_enriched = filtered_enriched_tweets[
        filtered_enriched_tweets['full_text'].isin(cluster_df['text'])
    ].copy()
    
    if len(cluster_enriched) == 0:
        print(f"Warning: No matching tweets found in enriched_tweets for cluster {cluster_label}")
        cluster_tweets[cluster_label] = []
        continue
    
    # Sort by created_at date
    cluster_enriched = cluster_enriched.sort_values('created_at')
    
    # Get date range
    min_date = cluster_enriched['created_at'].min()
    max_date = cluster_enriched['created_at'].max()
    date_range = (max_date - min_date).total_seconds()
    
    print(f"  Date range: {min_date.date()} to {max_date.date()}")
    print(f"  Total tweets in cluster: {len(cluster_enriched)}")
    
    # Sample 5 chunks of 10 consecutive tweets spanning the duration
    texts = []
    chunk_size = 4
    num_chunks = 4
    
    if len(cluster_enriched) < 50:
        # If we have fewer than 50 tweets, just take all of them
        for _, row in cluster_enriched.iterrows():
            username = row.get('user_screen_name', row.get('screen_name', row.get('username', 'Unknown')))
            date_str = row['created_at'].strftime('%Y-%m-%d %H:%M')
            text = f"[{date_str}] @{username}: {row['full_text']}"
            texts.append(text)
    else:
        # Divide the time range into 5 periods
        period_duration = date_range / num_chunks
        
        for chunk_idx in range(num_chunks):
            # Calculate time window for this chunk
            chunk_start = min_date + pd.Timedelta(seconds=chunk_idx * period_duration)
            chunk_end = min_date + pd.Timedelta(seconds=(chunk_idx + 1) * period_duration)
            
            # Get tweets in this time window
            chunk_tweets = cluster_enriched[
                (cluster_enriched['created_at'] >= chunk_start) & 
                (cluster_enriched['created_at'] < chunk_end)
            ]
            
            # Take 10 consecutive tweets from this chunk (or all if fewer)
            chunk_sample = chunk_tweets.head(chunk_size)
            
            for _, row in chunk_sample.iterrows():
                # Extract username (handle different possible column names)
                username = row.get('user_screen_name', row.get('screen_name', row.get('username', 'Unknown')))
                date_str = row['created_at'].strftime('%Y-%m-%d %H:%M')
                text = f"[{date_str}] @{username}: {row['full_text']}"
                texts.append(text)
    
    cluster_tweets[cluster_label] = texts
    print(f"  Sampled {len(texts)} texts spanning the cluster duration")


# %%
# Name clusters using a queue system with retry logic
from collections import deque
import time
import random

# Initialize the request queue
print("Initializing request queue...")
request_queue = deque()
for cluster_id, texts in cluster_tweets.items():
    request_queue.append({
        'cluster_id': cluster_id,
        'texts': texts,
        'attempts': 0,
        'max_attempts': 3
    })

cluster_analyses = {}
total_clusters = len(request_queue)
completed_count = 0
failed_permanently = 0

print(f"Starting to process {total_clusters} clusters...")
print(f"Settings: 20s wait between requests, max 3 attempts per cluster\n")

# Process queue until empty
while request_queue:
    # Get next request from queue
    request = request_queue.popleft()
    cluster_id = request['cluster_id']
    texts = request['texts']
    attempts = request['attempts'] + 1
    
    print(f"\n[Queue: {len(request_queue)} remaining | Completed: {completed_count}/{total_clusters}]")
    print(f"Processing Cluster {cluster_id} (attempt {attempts}/{request['max_attempts']})...")
    
    try:
        # Make the API call
        analysis = get_cluster_name(cluster_id, texts)
        
        # Success! Add to results
        cluster_analyses[cluster_id] = analysis
        completed_count += 1
        
        print(f"✓ SUCCESS - Cluster {cluster_id}: {analysis.cluster_name}")
        print(f"  Discourse: {analysis.discourse_coherence_score}/10 | Generative: {analysis.generative_density_score}/10 | Temporal: {analysis.temporal_coherence_score}/10")
        print(f"  Reasoning: {analysis.reasoning[:150]}...")
        
    except Exception as e:
        print(f"✗ ERROR - Cluster {cluster_id}: {str(e)}")
        
        # Check if we should retry
        if attempts < request['max_attempts']:
            # Add back to queue for retry
            request['attempts'] = attempts
            request_queue.append(request)
            print(f"  → Added back to queue for retry (attempt {attempts}/{request['max_attempts']})")
        else:
            # Max attempts reached, mark as failed
            failed_permanently += 1
            cluster_analyses[cluster_id] = ClusterAnalysis(
                reasoning=f"Failed after {request['max_attempts']} attempts: {str(e)}",
                discourse_coherence_score=0,
                generative_density_score=0,
                temporal_coherence_score=0,
                cluster_name=f"Cluster {cluster_id} (Failed)"
            )
            print(f"  → Max attempts reached, marked as failed")
    
    # Wait before next request (unless queue is empty)
    if request_queue:
        wait_time = 0
        print(f"  ⏳ Waiting {wait_time} seconds before next request...")
        time.sleep(wait_time)

# Print final summary
print("\n" + "="*60)
print("PROCESSING COMPLETE")
print("="*60)
print(f"Total clusters: {total_clusters}")
print(f"Successfully processed: {completed_count}")
print(f"Failed permanently: {failed_permanently}")
print(f"Success rate: {(completed_count/total_clusters)*100:.1f}%")


# %% save the cluster analyses and tweets to a pickle file
import pickle
with open('cluster_analyses.pkl', 'wb') as f:
    pickle.dump(cluster_analyses, f)
with open('cluster_tweets.pkl', 'wb') as f:
    pickle.dump(cluster_tweets, f)


# %% load the cluster analyses and tweets from pickle files
import pickle
with open('cluster_analyses.pkl', 'rb') as f:
    cluster_analyses = pickle.load(f)
with open('cluster_tweets.pkl', 'rb') as f:
    cluster_tweets = pickle.load(f)


# %%

# Print summary
print("\n=== Cluster Analysis Summary ===")
for cluster_id in sorted(cluster_analyses.keys()):
    count = len(cluster_tweets[cluster_id])
    analysis = cluster_analyses[cluster_id]
    print(f"\nCluster {cluster_id} ({count} tweets):")
    print(f"  Name: {analysis.cluster_name}")
    print(f"  Discourse Coherence Score: {analysis.discourse_coherence_score}/10")
    print(f"  Generative Density Score: {analysis.generative_density_score}/10")
    print(f"  Temporal Coherence Score: {analysis.temporal_coherence_score}/10")
    print(f"  Reasoning: {analysis.reasoning}")
    print(f"\n  Sample Tweets:")
    for i, tweet in enumerate(cluster_tweets[cluster_id], 1):
        # Truncate long tweets for better readability
        tweet_preview = tweet[:150] + "..." if len(tweet) > 150 else tweet
        print(f"    {i}. {tweet_preview}")
    print()  # Add extra line for spacing between clusters

# %%


import pandas as pd

# Create a dataframe with cluster information
cluster_data = []
for cluster_id in sorted(cluster_analyses.keys()):
    analysis = cluster_analyses[cluster_id]
    tweets = cluster_tweets[cluster_id]
    
    # Calculate average score
    avg_score = (analysis.discourse_coherence_score + 
                 analysis.generative_density_score + 
                 analysis.temporal_coherence_score) / 3
    
    cluster_data.append({
        'cluster_id': cluster_id,
        'name': analysis.cluster_name,
        'discourse_score': analysis.discourse_coherence_score,
        'generative_score': analysis.generative_density_score,
        'temporal_score': analysis.temporal_coherence_score,
        'avg_score': avg_score,
        'tweet_count': len(tweets),
        'tweets': tweets  # Store all tweets instead of just sample
    })

df_clusters = pd.DataFrame(cluster_data)

# Sort by average score descending
df_clusters = df_clusters.sort_values('avg_score', ascending=False)

# Print top 20 clusters in a readable way
print("\n" + "="*80)
print("TOP 20 CLUSTERS BY AVERAGE SCORE")
print("="*80)

for idx, row in df_clusters.head(20).iterrows():
    print(f"\n{'─'*80}")
    print(f"Rank: #{list(df_clusters.index).index(idx) + 1} | Cluster ID: {row['cluster_id']} | Tweets: {row['tweet_count']}")
    print(f"Name: {row['name']}")
    print(f"Scores: Discourse={row['discourse_score']}/10, Generative={row['generative_score']}/10, "
          f"Temporal={row['temporal_score']}/10 → Avg={row['avg_score']:.2f}/10")
    print(f"\nSample Tweets:")
    for i, tweet in enumerate(row['tweets'], 1):
        print(f"  {i}. {tweet}")

print(f"\n{'='*80}\n")

# Display dataframe summary
print("\nDataFrame Summary:")
print(df_clusters[['cluster_id', 'name', 'discourse_score', 'generative_score', 
                   'temporal_score', 'avg_score', 'tweet_count']].head(20))


# %%

# Create detailed cluster report files
import os
import re
from datetime import datetime

# Create clusters directory
clusters_dir = 'cluster_reports'
os.makedirs(clusters_dir, exist_ok=True)

def sanitize_filename(name):
    """Remove invalid filename characters"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

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

print(f"Creating cluster report files in '{clusters_dir}/' directory...")

for idx, row in df_clusters.iterrows():
    cluster_id = row['cluster_id']
    
    # Keep reference to formatted cluster tweets for fallback
    cluster_texts = cluster_tweets.get(cluster_id, [])
    
    # Get ALL enriched tweets for this cluster directly from df_all_with_clusters
    cluster_indices = X.index[X['cluster'] == cluster_id].tolist()
    
    # Extract original texts from metadata
    original_texts = []
    for idx_val in cluster_indices:
        try:
            metadata = json.loads(df_all_with_clusters.iloc[idx_val]['metadata'])
            original_text = metadata.get("original_text", "")
            if original_text:
                original_texts.append(original_text)
        except:
            continue
    
    # Match with filtered_enriched_tweets to get full data
    cluster_full_data = filtered_enriched_tweets[
        filtered_enriched_tweets['full_text'].isin(original_texts)
    ].copy()
    
    # Convert to proper DataFrame format
    if len(cluster_full_data) > 0:
        cluster_df = cluster_full_data.sort_values('created_at').reset_index(drop=True)
    else:
        cluster_df = pd.DataFrame()
    
    # Create filename with average score prefix
    avg_score = row['avg_score']
    sanitized_name = sanitize_filename(row['name'])
    filename = f"{avg_score:05.2f}_{cluster_id:03d}_{sanitized_name}.txt"
    filepath = os.path.join(clusters_dir, filename)
    
    # Build file content
    content = []
    content.append("=" * 80)
    content.append(f"CLUSTER REPORT: {row['name']}")
    content.append("=" * 80)
    content.append(f"\nCluster ID: {cluster_id}")
    content.append(f"Total Tweets: {len(cluster_df)}")
    content.append(f"\nSCORES:")
    content.append(f"  Discourse Coherence:  {row['discourse_score']}/10")
    content.append(f"  Generative Density:   {row['generative_score']}/10")
    content.append(f"  Temporal Coherence:   {row['temporal_score']}/10")
    content.append(f"  ─────────────────────────────")
    content.append(f"  Average Score:        {avg_score:.2f}/10")
    
    # Add ASCII chart if we have temporal data
    if len(cluster_df) > 0 and 'created_at' in cluster_df.columns:
        chart = create_ascii_chart(cluster_df['created_at'])
        content.append(f"\n{chart}")
    
    content.append("\n" + "=" * 80)
    content.append("SAMPLE TWEETS (40 tweets from 4 temporal chunks)")
    content.append("=" * 80)
    
    # Get 40 sample tweets from 4 chunks (10 each)
    if len(cluster_df) > 0 and 'created_at' in cluster_df.columns:
        cluster_df_sorted = cluster_df.sort_values('created_at')
        total_tweets = len(cluster_df_sorted)
        
        chunks = []
        if total_tweets >= 40:
            # Divide into 4 equal time periods
            chunk_size = 10
            period_size = total_tweets / 4
            
            for i in range(4):
                start_idx = int(i * period_size)
                chunk = cluster_df_sorted.iloc[start_idx:start_idx + chunk_size]
                chunks.append(chunk)
        else:
            # Just take all tweets
            chunks = [cluster_df_sorted]
        
        sample_count = 0
        for chunk_idx, chunk in enumerate(chunks):
            if len(chunk) > 0:
                content.append(f"\n─── Chunk {chunk_idx + 1} ───")
                for _, tweet in chunk.iterrows():
                    sample_count += 1
                    username = tweet.get('user_screen_name', tweet.get('screen_name', tweet.get('username', 'Unknown')))
                    date_str = tweet['created_at'].strftime('%Y-%m-%d %H:%M')
                    content.append(f"\n{sample_count}. [{date_str}] @{username}")
                    content.append(f"   {tweet['full_text']}")
    else:
        # Fallback to using the formatted texts
        for i, tweet in enumerate(cluster_texts[:40], 1):
            content.append(f"\n{i}. {tweet}")
    
    content.append("\n\n" + "=" * 80)
    content.append("ALL TWEETS IN CLUSTER")
    content.append("=" * 80 + "\n")
    
    # Add all tweets
    if len(cluster_df) > 0 and 'created_at' in cluster_df.columns:
        cluster_df_sorted = cluster_df.sort_values('created_at')
        for idx, tweet in enumerate(cluster_df_sorted.itertuples(), 1):
            username = getattr(tweet, 'user_screen_name', getattr(tweet, 'screen_name', getattr(tweet, 'username', 'Unknown')))
            date_str = tweet.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content.append(f"[{date_str}] @{username}")
            content.append(tweet.full_text)
            content.append("\n" + "─" * 80 + "\n")
    else:
        # Fallback to formatted texts
        for tweet in cluster_texts:
            content.append(tweet)
            content.append("\n" + "─" * 80 + "\n")
    
    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(content))
    
    print(f"  Created: {filename}")

print(f"\n✓ Created {len(df_clusters)} cluster report files in '{clusters_dir}/'")


# %%

# Print cluster information one by one with fixed date range histogram
from datetime import datetime

def create_fixed_range_histogram(dates, width=60, start_date='2008-01-01', end_date='2026-01-01'):
    """Create ASCII histogram with fixed date range"""
    if dates is None or len(dates) == 0:
        # Return empty histogram
        sparkline = "     │" + " " * width
        return sparkline
    
    # Convert to datetime if needed
    dates = pd.to_datetime(dates)
    
    # Fixed date range - make timezone aware if dates are timezone aware
    min_date = pd.to_datetime(start_date)
    max_date = pd.to_datetime(end_date)
    
    # Match timezone of dates
    if hasattr(dates.dtype, 'tz') and dates.dtype.tz is not None:
        # dates are timezone-aware, make min_date and max_date aware too
        min_date = min_date.tz_localize('UTC')
        max_date = max_date.tz_localize('UTC')
    
    # Create time buckets
    date_range = pd.date_range(min_date, max_date, periods=width)
    
    # Aggregate counts into buckets
    bucket_counts = []
    for i in range(len(date_range)):
        if i < len(date_range) - 1:
            start = date_range[i]
            end = date_range[i + 1]
            # Count tweets in this bucket
            mask = (dates >= start) & (dates < end)
            bucket_counts.append(dates[mask].count())
        else:
            # Last bucket includes end date
            start = date_range[i]
            mask = dates >= start
            bucket_counts.append(dates[mask].count())
    
    max_bucket_count = max(bucket_counts) if bucket_counts else 1
    
    # Block characters for different heights (8 levels)
    blocks = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    # Create sparkline
    sparkline = "     │"
    for count in bucket_counts:
        # Normalize to 0-8 range
        if max_bucket_count > 0:
            level = int((count / max_bucket_count) * 8)
            level = min(8, level)  # Cap at 8
        else:
            level = 0
        sparkline += blocks[level]
    
    return sparkline

# Print all clusters
print("\n" + "=" * 80)
print("CLUSTER SUMMARIES (Fixed Timeline: Jan 2008 - Jan 2026)")
print("=" * 80 + "\n")

for idx, row in df_clusters.iterrows():
    cluster_id = row['cluster_id']
    
    # Get cluster tweets for histogram
    cluster_indices = X.index[X['cluster'] == cluster_id].tolist()
    original_texts = []
    for idx_val in cluster_indices:
        try:
            metadata = json.loads(df_all_with_clusters.iloc[idx_val]['metadata'])
            original_text = metadata.get("original_text", "")
            if original_text:
                original_texts.append(original_text)
        except:
            continue
    
    # Get dates from enriched tweets
    cluster_enriched = filtered_enriched_tweets[
        filtered_enriched_tweets['full_text'].isin(original_texts)
    ]
    
    dates = cluster_enriched['created_at'] if len(cluster_enriched) > 0 else pd.Series(dtype='datetime64[ns]')
    
    # Create fixed range histogram
    histogram = create_fixed_range_histogram(dates, width=60, start_date='2008-01-01', end_date='2026-01-01')
    
    # Print cluster info
    print(f"Cluster {cluster_id:3d} | Avg: {row['avg_score']:.2f}/10")
    print(histogram)
    print(f"     └{'─'*60}")
    print(f"      2008{' '*52}2026")
    print(f"\n     {row['name']}")
    print(f"     Discourse: {row['discourse_score']}/10 | Generative: {row['generative_score']}/10 | Temporal: {row['temporal_score']}/10")
    print(f"     Tweets: {len(cluster_enriched)}")
    print("\n" + "─" * 80 + "\n")

print("\n" + "=" * 80)


# %%
# Define line styles for each cluster
line_styles = {
    81: '-',      # solid line for Bitcoin
    500: '-',     # solid line for Tokenization
    418: ':'      # dotted line for Digital Sangha (control)
}

# Update cluster names
clusters_to_plot = {
    81: 'Bitcoin Evolution Narrative',
    500: 'Tokenization & Crypto Evolution',
    418: 'Digital Sangha Narrative (control)'
}

# Plot tweet volume evolution for specific clusters
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Define the clusters to plot
clusters_to_plot = {
    81: 'Bitcoin Evolution Narrative',
    500: 'Tokenization & Crypto Evolution',
    418: 'Digital Sangha Narrative (control)'
}

# Create figure
plt.figure(figsize=(14, 7))

# For each cluster, get tweet dates and plot
for cluster_id, cluster_name in clusters_to_plot.items():
    # Get cluster tweets
    cluster_indices = X.index[X['cluster'] == cluster_id].tolist()
    original_texts = []
    for idx_val in cluster_indices:
        try:
            metadata = json.loads(df_all_with_clusters.iloc[idx_val]['metadata'])
            original_text = metadata.get("original_text", "")
            if original_text:
                original_texts.append(original_text)
        except:
            continue
    
    # Get dates from enriched tweets
    cluster_enriched = filtered_enriched_tweets[
        filtered_enriched_tweets['full_text'].isin(original_texts)
    ]
    
    if len(cluster_enriched) > 0:
        dates = cluster_enriched['created_at'].sort_values()
        
        # Create monthly bins for smoother visualization
        dates_series = pd.Series(dates.values)
        monthly_counts = dates_series.groupby(dates_series.dt.to_period('M')).size()
        monthly_dates = monthly_counts.index.to_timestamp()
        
        # Plot the line with the appropriate line style
        plt.plot(monthly_dates, monthly_counts.values, label=f"{cluster_name}", 
                linewidth=2, alpha=0.8, linestyle=line_styles[cluster_id])

# Format the plot
plt.xlabel('Date', fontsize=12)
plt.ylabel('Tweet Volume (per month)', fontsize=12)
plt.title('Tweet Volume Evolution', fontsize=14, fontweight='bold')
plt.legend(loc='best', fontsize=10)
plt.grid(True, alpha=0.3)

# Format x-axis dates
ax = plt.gca()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
ax.xaxis.set_major_locator(mdates.YearLocator(2))
plt.xticks(rotation=45)

plt.tight_layout()
plt.savefig('cluster_volume_evolution.png', dpi=300, bbox_inches='tight')
plt.show()

print("\nPlot saved as 'cluster_volume_evolution.png'")


# %%

# Create a mapping from index to cluster_id
df_all_with_clusters_indexed = df_all_with_clusters.set_index('key')
index_to_cluster = df_all_with_clusters_indexed['cluster'].to_dict()

# Save the mapping to a JSON file
with open('index_to_cluster_mapping.json', 'w') as f:
    json.dump(index_to_cluster, f, indent=2)

print(f"Created mapping for {len(index_to_cluster)} indices to clusters")
print("Mapping saved to 'index_to_cluster_mapping.json'")


