"""Phase 6: Generate seriation order (topic sorting by semantic similarity)."""

import json

import numpy as np

from pipeline.config import EMBEDDINGS_CACHE_PATH, FRONTEND_PUBLIC_DIR, SERIATION_ORDER_PATH
from pipeline.helpers import load_all_rated_strands


def run() -> bool:
    """Generate seriation order - strands sorted by semantic similarity (greedy nearest neighbor)."""
    print("\n" + "=" * 60)
    print("PHASE 6: Generate Seriation Order")
    print("=" * 60)

    if not EMBEDDINGS_CACHE_PATH.exists():
        print(f"[ERROR] Embeddings cache not found at {EMBEDDINGS_CACHE_PATH}")
        return False

    with open(EMBEDDINGS_CACHE_PATH) as f:
        cache_data = json.load(f)

    embeddings_list = cache_data.get('embeddings', [])
    print(f"Loaded {len(embeddings_list)} strand embeddings")

    if len(embeddings_list) < 2:
        print("[ERROR] Need at least 2 strands for seriation")
        return False

    all_strands = load_all_rated_strands()

    # Build lookup: seed_tweet_id -> (embedding, rating)
    strand_data = {}
    for entry in embeddings_list:
        seed_id = str(entry['seed_tweet_id'])
        embedding = np.array(entry['embedding'])
        strand = all_strands.get(int(seed_id), {})
        rating_obj = strand.get('rating', {})
        rating = rating_obj.get('rating', 5) if isinstance(rating_obj, dict) else 5
        strand_data[seed_id] = {
            'embedding': embedding,
            'rating': rating,
        }

    # Normalize embeddings for cosine similarity
    for data in strand_data.values():
        norm = np.linalg.norm(data['embedding'])
        if norm > 0:
            data['embedding'] = data['embedding'] / norm

    # Start with a high-scoring strand
    start_id = max(strand_data.keys(), key=lambda x: strand_data[x]['rating'])
    print(f"Starting seriation from strand {start_id} (rating: {strand_data[start_id]['rating']})")

    # Greedy nearest neighbor seriation
    remaining = set(strand_data.keys())
    order = []
    current_id = start_id
    remaining.remove(current_id)
    order.append({'id': current_id, 'distance': 0.0})

    while remaining:
        current_emb = strand_data[current_id]['embedding']

        best_id = None
        best_dist = float('inf')

        for candidate_id in remaining:
            candidate_emb = strand_data[candidate_id]['embedding']
            similarity = np.dot(current_emb, candidate_emb)
            distance = 1 - similarity
            if distance < best_dist:
                best_dist = distance
                best_id = candidate_id

        if best_id is None:
            break

        order.append({'id': best_id, 'distance': round(float(best_dist), 6)})
        remaining.remove(best_id)
        current_id = best_id

    print(f"Generated seriation order for {len(order)} strands")

    distances = [o['distance'] for o in order[1:]]
    if distances:
        print(f"  Distance stats: min={min(distances):.4f}, max={max(distances):.4f}, mean={np.mean(distances):.4f}")

    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        'order': order,
        'start_id': start_id,
        'count': len(order),
    }
    with open(SERIATION_ORDER_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Exported seriation order to {SERIATION_ORDER_PATH}")
    return True
