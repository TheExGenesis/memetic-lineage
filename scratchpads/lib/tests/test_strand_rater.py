"""Tests for strand_rater.py pure functions."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from lib.strand_rater import (
    _fix_schema_for_anthropic,
    rate_strand,
    rate_strands_batch,
    EmptyResponseError,
    JSONParseError,
)


class TestFixSchemaForAnthropic:
    def test_adds_additional_properties_to_object(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["name"]["type"] == "string"

    def test_preserves_existing_additional_properties(self):
        schema = {"type": "object", "additionalProperties": True}
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is True

    def test_nested_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["nested"]["additionalProperties"] is False

    def test_array_of_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "integer"}}},
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["items"]["items"]["additionalProperties"] is False

    def test_non_object_types_unchanged(self):
        schema = {"type": "string"}
        result = _fix_schema_for_anthropic(schema)
        assert result == {"type": "string"}

    def test_does_not_mutate_original(self):
        original = {"type": "object", "properties": {"x": {"type": "number"}}}
        _ = _fix_schema_for_anthropic(original)
        assert "additionalProperties" not in original

    def test_deeply_nested_structure(self):
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {"level3": {"type": "string"}},
                        }
                    },
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["level1"]["additionalProperties"] is False
        assert result["properties"]["level1"]["properties"]["level2"]["additionalProperties"] is False

    def test_empty_schema(self):
        result = _fix_schema_for_anthropic({})
        assert result == {}

    def test_mixed_types_in_array(self):
        schema = {
            "type": "object",
            "properties": {
                "mixed": {
                    "type": "array",
                    "items": [
                        {"type": "object", "properties": {"a": {"type": "string"}}},
                        {"type": "string"},
                    ],
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["mixed"]["items"][0]["additionalProperties"] is False


class TestEmptyResponseError:
    """Tests for EmptyResponseError exception."""

    def test_is_exception(self):
        err = EmptyResponseError("Empty response")
        assert isinstance(err, Exception)

    def test_message(self):
        err = EmptyResponseError("LLM returned nothing")
        assert "LLM returned nothing" in str(err)


class TestJSONParseError:
    """Tests for JSONParseError exception."""

    def test_stores_raw_content(self):
        err = JSONParseError("Parse failed", raw_content="not json {{{", tweet_id=123)
        assert err.raw_content == "not json {{{"
        assert err.tweet_id == 123

    def test_message(self):
        err = JSONParseError("Invalid JSON", raw_content="bad", tweet_id=456)
        assert "Invalid JSON" in str(err)


class TestRateStrand:
    """Tests for rate_strand control flow."""

    @pytest.fixture
    def mock_valid_response(self):
        """Create a mock completion with valid JSON response."""
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps({
            "reasoning_summary": "Test summary of the strand",
            "rating": 7,
            "evolution": "medium",
            "cohesion": "high",
            "utility": "medium",
            "essential_tweets": [{"tweet_id": 123, "annotation": "Key insight"}],
        })
        mock_completion.choices[0].finish_reason = "stop"
        return mock_completion

    @pytest.fixture
    def mock_empty_response(self):
        """Create a mock completion with empty response."""
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = ""
        mock_completion.choices[0].finish_reason = "stop"
        return mock_completion

    @pytest.fixture
    def mock_invalid_json_response(self):
        """Create a mock completion with invalid JSON."""
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "not valid json {{{"
        mock_completion.choices[0].finish_reason = "stop"
        return mock_completion

    def test_success_returns_rated_result(self, mock_valid_response):
        """Successful rating should return RatedStrandResult."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_valid_response

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            result = rate_strand(
                thread_text="Test thread",
                tweet_id=123,
                seeds=[{"tweet_id": 123, "source_type": "root"}],
            )

        assert result["seed_tweet_id"] == 123
        assert result["thread_text"] == "Test thread"
        assert "rating" in result
        assert result["rating"]["rating"] == 7

    def test_empty_response_triggers_retry(self, mock_empty_response, mock_valid_response):
        """Empty response should trigger retry."""
        mock_client = MagicMock()
        # First call returns empty, second returns valid
        mock_client.chat.completions.create.side_effect = [
            mock_empty_response,
            mock_valid_response,
        ]

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            with patch('time.sleep'):  # Don't actually sleep
                result = rate_strand(
                    thread_text="Test thread",
                    tweet_id=123,
                    max_retries=3,
                )

        # Should have called twice (first failed, second succeeded)
        assert mock_client.chat.completions.create.call_count == 2
        assert result["rating"]["rating"] == 7

    def test_json_parse_error_increases_temperature(self, mock_invalid_json_response, mock_valid_response):
        """JSON parse error should retry with higher temperature."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            mock_invalid_json_response,
            mock_valid_response,
        ]

        temperatures_used = []

        def capture_temperature(*args, **kwargs):
            temperatures_used.append(kwargs.get('temperature', 0.7))
            if len(temperatures_used) == 1:
                return mock_invalid_json_response
            return mock_valid_response

        mock_client.chat.completions.create.side_effect = capture_temperature

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            with patch('time.sleep'):
                result = rate_strand(
                    thread_text="Test thread",
                    tweet_id=123,
                    base_temperature=0.7,
                    max_retries=3,
                )

        # Second call should have higher temperature
        assert len(temperatures_used) == 2
        assert temperatures_used[1] > temperatures_used[0]

    def test_rate_limit_error_triggers_exponential_backoff(self, mock_valid_response):
        """Rate limit errors should trigger exponential backoff."""
        mock_client = MagicMock()

        call_count = [0]
        def rate_limit_then_success(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("HTTP 429 Too Many Requests")
            return mock_valid_response

        mock_client.chat.completions.create.side_effect = rate_limit_then_success

        sleep_times = []
        def capture_sleep(seconds):
            sleep_times.append(seconds)

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            with patch('time.sleep', side_effect=capture_sleep):
                result = rate_strand(
                    thread_text="Test thread",
                    tweet_id=123,
                    max_retries=3,
                )

        assert len(sleep_times) >= 1
        # First retry should sleep for 2^0 = 1 second
        assert sleep_times[0] == 1

    def test_json_parse_error_saves_debug_file(self, tmp_path):
        """JSONParseError should save raw response to debug_dir."""
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "invalid json content here"
        mock_completion.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            with patch('time.sleep'):
                with pytest.raises(JSONParseError):
                    rate_strand(
                        thread_text="Test thread",
                        tweet_id=999,
                        max_retries=2,
                        debug_dir=tmp_path,
                    )

        # Check debug file was created
        debug_files = list(tmp_path.glob("999_*.txt"))
        assert len(debug_files) >= 1
        assert "invalid json content here" in debug_files[0].read_text()

    def test_all_retries_exhausted_raises(self, mock_invalid_json_response):
        """Should raise after exhausting all retries."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_invalid_json_response

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            with patch('time.sleep'):
                with pytest.raises(JSONParseError):
                    rate_strand(
                        thread_text="Test thread",
                        tweet_id=123,
                        max_retries=2,
                    )

        # Should have tried max_retries times
        assert mock_client.chat.completions.create.call_count == 2

    def test_strips_markdown_code_blocks(self):
        """Should strip markdown code blocks from response."""
        mock_client = MagicMock()
        mock_completion = MagicMock()
        # Response wrapped in markdown code block
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = """```json
{"reasoning_summary": "Test", "rating": 8, "evolution": "high", "cohesion": "high", "utility": "high", "essential_tweets": []}
```"""
        mock_completion.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create.return_value = mock_completion

        with patch('lib.strand_rater._get_client', return_value=mock_client):
            result = rate_strand(
                thread_text="Test thread",
                tweet_id=123,
            )

        assert result["rating"]["rating"] == 8


class TestRateStrandsBatch:
    """Tests for rate_strands_batch."""

    def test_skips_existing_results(self, tmp_path):
        """Should skip strands that already have result files."""
        # Create existing result file
        existing_result = {
            "seed_tweet_id": 1001,
            "thread_text": "Existing",
            "seeds": [],
            "rating": {"rating": 7, "essential_tweets": [], "reasoning": "Cached"}
        }
        (tmp_path / "1001.json").write_text(json.dumps(existing_result))

        strands_data = {
            1001: {"thread_text": "Existing thread", "seeds": []},
            1002: {"thread_text": "New thread", "seeds": []},
        }

        # Mock rate_strand to track which strands get rated
        rated_ids = []

        def mock_rate_strand(thread_text, tweet_id, **kwargs):
            rated_ids.append(tweet_id)
            return {
                "seed_tweet_id": tweet_id,
                "thread_text": thread_text,
                "seeds": [],
                "rating": {"rating": 5, "essential_tweets": [], "reasoning": "New"}
            }

        with patch('lib.strand_rater.rate_strand', side_effect=mock_rate_strand):
            results = rate_strands_batch(
                strands_data,
                output_dir=tmp_path,
                max_workers=1,
            )

        # Only 1002 should have been rated (1001 was cached)
        assert 1001 not in rated_ids
        assert 1002 in rated_ids

        # Both should be in results
        assert 1001 in results
        assert 1002 in results
        assert results[1001]["rating"]["reasoning"] == "Cached"
        assert results[1002]["rating"]["reasoning"] == "New"

    def test_saves_results_to_output_dir(self, tmp_path):
        """Should save each result to output_dir."""
        strands_data = {
            2001: {"thread_text": "Thread 1", "seeds": []},
        }

        def mock_rate_strand(thread_text, tweet_id, **kwargs):
            return {
                "seed_tweet_id": tweet_id,
                "thread_text": thread_text,
                "seeds": [],
                "rating": {"rating": 6, "essential_tweets": [], "reasoning": "Test"}
            }

        with patch('lib.strand_rater.rate_strand', side_effect=mock_rate_strand):
            rate_strands_batch(
                strands_data,
                output_dir=tmp_path,
                max_workers=1,
            )

        # Result file should exist
        result_file = tmp_path / "2001.json"
        assert result_file.exists()

        saved_data = json.loads(result_file.read_text())
        assert saved_data["seed_tweet_id"] == 2001
        assert saved_data["rating"]["rating"] == 6

    def test_returns_empty_when_all_cached(self, tmp_path):
        """Should return cached results when all strands already processed."""
        # Create existing results
        for tid in [3001, 3002]:
            result = {
                "seed_tweet_id": tid,
                "thread_text": f"Thread {tid}",
                "seeds": [],
                "rating": {"rating": 7, "essential_tweets": [], "reasoning": "Cached"}
            }
            (tmp_path / f"{tid}.json").write_text(json.dumps(result))

        strands_data = {
            3001: {"thread_text": "Thread 3001", "seeds": []},
            3002: {"thread_text": "Thread 3002", "seeds": []},
        }

        with patch('lib.strand_rater.rate_strand') as mock_rate:
            results = rate_strands_batch(
                strands_data,
                output_dir=tmp_path,
                max_workers=1,
            )

        # rate_strand should not have been called
        mock_rate.assert_not_called()

        # All results should be returned
        assert len(results) == 2
        assert 3001 in results
        assert 3002 in results

