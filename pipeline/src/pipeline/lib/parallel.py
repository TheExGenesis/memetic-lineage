"""Parallel execution utilities for phase-level parallelism."""
from typing import TypeVar, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

K = TypeVar('K')
V = TypeVar('V')


def parallel_map_to_dict(
    keys: List[K],
    fn: Callable[[K], V],
    max_workers: int = 4,
    desc: str = "Processing"
) -> Tuple[Dict[K, V], List[K]]:
    """
    Map fn over keys in parallel, return (results_dict, failed_keys).
    
    Args:
        keys: List of keys to process
        fn: Function that takes a key and returns a value
        max_workers: Number of parallel workers
        desc: Progress bar description
        
    Returns:
        Tuple of (results dict, list of failed keys)
    """
    results: Dict[K, V] = {}
    failed: List[K] = []
    
    if not keys:
        return results, failed
    
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fn, k): k for k in keys}
        for fut in tqdm(as_completed(futures), total=len(futures), desc=desc):
            k = futures[fut]
            try:
                results[k] = fut.result()
            except Exception as e:
                print(f"[ERROR] {k}: {type(e).__name__}: {e}")
                failed.append(k)
    
    return results, failed


def parallel_map_to_dict_with_context(
    keys: List[K],
    fn: Callable[[K, Dict], V],
    context: Dict,
    max_workers: int = 4,
    desc: str = "Processing"
) -> Tuple[Dict[K, V], List[K]]:
    """
    Like parallel_map_to_dict but passes shared context to each call.
    Context is read-only (no mutations visible across threads).
    """
    return parallel_map_to_dict(
        keys,
        lambda k: fn(k, context),
        max_workers=max_workers,
        desc=desc
    )


def batch_keys(keys: List[K], batch_size: int) -> List[List[K]]:
    """Split keys into batches of batch_size."""
    return [keys[i:i + batch_size] for i in range(0, len(keys), batch_size)]

