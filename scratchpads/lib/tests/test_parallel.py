"""Tests for parallel.py utilities."""
import pytest

from lib.parallel import batch_keys, parallel_map_to_dict


class TestBatchKeys:
    def test_exact_batches(self):
        keys = [1, 2, 3, 4, 5, 6]
        result = batch_keys(keys, 2)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_partial_last_batch(self):
        keys = [1, 2, 3, 4, 5]
        result = batch_keys(keys, 2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_empty_input(self):
        assert batch_keys([], 5) == []

    def test_smaller_than_batch_size(self):
        keys = [1, 2]
        result = batch_keys(keys, 10)
        assert result == [[1, 2]]

    def test_batch_size_one(self):
        keys = [1, 2, 3]
        result = batch_keys(keys, 1)
        assert result == [[1], [2], [3]]


class TestParallelMapToDict:
    def test_success_case(self):
        keys = [1, 2, 3]
        results, failed = parallel_map_to_dict(keys, lambda x: x * 2, max_workers=2)
        assert results == {1: 2, 2: 4, 3: 6}
        assert failed == []

    def test_empty_input(self):
        results, failed = parallel_map_to_dict([], lambda x: x, max_workers=2)
        assert results == {}
        assert failed == []

    def test_partial_failures(self):
        def fn(x):
            if x == 2:
                raise ValueError("fail on 2")
            return x * 10

        results, failed = parallel_map_to_dict([1, 2, 3], fn, max_workers=2)
        assert results == {1: 10, 3: 30}
        assert failed == [2]

    def test_all_failures(self):
        def fn(x):
            raise RuntimeError("always fails")

        results, failed = parallel_map_to_dict([1, 2], fn, max_workers=2)
        assert results == {}
        assert set(failed) == {1, 2}

    def test_preserves_key_types(self):
        keys = ["a", "b", "c"]
        results, _ = parallel_map_to_dict(keys, lambda x: x.upper(), max_workers=2)
        assert results == {"a": "A", "b": "B", "c": "C"}

