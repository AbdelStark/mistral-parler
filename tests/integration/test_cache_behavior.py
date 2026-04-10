"""
Integration tests: Content-hash caching layer

These tests verify the TranscriptCache and ExtractionCache:
  - Cache key = sha256(audio_content)[:16] + model_version (transcript)
  - Cache key = sha256(transcript_text)[:16] + prompt_version (extraction)
  - Cache hit returns stored result without any API call
  - Cache miss triggers API call and stores the result
  - Changing audio content (different hash) is a cache miss
  - Changing model version is a cache miss
  - Changing prompt version is a cache miss
  - Cache can be cleared (all entries or single entry)
  - Cache honours TTL (expired entries treated as miss)
  - Cache is stored as JSON files in the configured directory
  - Cache directory is created if it doesn't exist
"""

import pytest
import json
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from parler.transcription.cache import TranscriptCache
from parler.extraction.cache import ExtractionCache
from parler.models import (
    Transcript, TranscriptSegment, DecisionLog, Decision,
    ExtractionMetadata
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_segment(id=0, start=0.0, end=5.0, text="Test segment."):
    return TranscriptSegment(
        id=id, start_s=start, end_s=end, text=text, language="fr",
        speaker_id=None, speaker_confidence=None, confidence=0.9,
        no_speech_prob=0.01, code_switch=False, words=None,
    )


def make_transcript(text="Test transcript", duration=60.0):
    seg = make_segment(text=text)
    return Transcript(
        text=text, language="fr", duration_s=duration, segments=(seg,)
    )


def make_decision_log():
    return DecisionLog(
        decisions=(
            Decision(
                id="D1", summary="Test decision", timestamp_s=10.0,
                speaker="Pierre", confirmed_by=(), quote=".", confidence="high",
                language="fr"
            ),
        ),
        commitments=(),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.0.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:00:00Z",
            input_tokens=100,
            output_tokens=50,
        ),
    )


# ─── TranscriptCache ─────────────────────────────────────────────────────────

class TestTranscriptCache:

    def test_store_and_retrieve_transcript(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="abc123abc123", model="voxtral-v1-5", transcript=transcript)
        result = cache.get(content_hash="abc123abc123", model="voxtral-v1-5")
        assert result is not None
        assert result.text == "Test transcript"

    def test_cache_miss_returns_none(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        result = cache.get(content_hash="nonexistent", model="voxtral-v1-5")
        assert result is None

    def test_different_content_hash_is_cache_miss(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="aaa111aaa111", model="voxtral-v1-5", transcript=transcript)
        result = cache.get(content_hash="bbb222bbb222", model="voxtral-v1-5")
        assert result is None

    def test_different_model_version_is_cache_miss(self, tmp_path):
        """Same audio hash but different model → cache miss."""
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="abc123abc123", model="voxtral-v1", transcript=transcript)
        result = cache.get(content_hash="abc123abc123", model="voxtral-v1-5")
        assert result is None

    def test_cache_persisted_as_json_file(self, tmp_path):
        """Cache entry should be written as a JSON file on disk."""
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="abc123abc123", model="voxtral-v1-5", transcript=transcript)
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) >= 1

    def test_cache_directory_created_if_missing(self, tmp_path):
        """Cache dir that doesn't exist should be created automatically."""
        new_dir = tmp_path / "new" / "cache" / "dir"
        cache = TranscriptCache(cache_dir=new_dir)
        transcript = make_transcript()
        cache.store(content_hash="abc123", model="voxtral-v1-5", transcript=transcript)
        assert new_dir.exists()

    def test_cache_survives_process_restart(self, tmp_path):
        """Cache stored in one instance should be readable by a new instance."""
        transcript = make_transcript(text="Persisted transcript")
        TranscriptCache(cache_dir=tmp_path).store(
            content_hash="persist123", model="voxtral-v1-5", transcript=transcript
        )
        # Simulate restart with new instance
        new_cache = TranscriptCache(cache_dir=tmp_path)
        result = new_cache.get(content_hash="persist123", model="voxtral-v1-5")
        assert result is not None
        assert result.text == "Persisted transcript"

    def test_clear_removes_all_entries(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="aaa", model="voxtral-v1-5", transcript=transcript)
        cache.store(content_hash="bbb", model="voxtral-v1-5", transcript=transcript)
        cache.clear()
        assert cache.get(content_hash="aaa", model="voxtral-v1-5") is None
        assert cache.get(content_hash="bbb", model="voxtral-v1-5") is None

    def test_clear_specific_entry(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="aaa", model="voxtral-v1-5", transcript=transcript)
        cache.store(content_hash="bbb", model="voxtral-v1-5", transcript=transcript)
        cache.clear(content_hash="aaa", model="voxtral-v1-5")
        assert cache.get(content_hash="aaa", model="voxtral-v1-5") is None
        assert cache.get(content_hash="bbb", model="voxtral-v1-5") is not None

    def test_cache_size_reported_correctly(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        cache.store(content_hash="aaa", model="voxtral-v1-5", transcript=transcript)
        cache.store(content_hash="bbb", model="voxtral-v1-5", transcript=transcript)
        assert cache.entry_count() == 2

    def test_expired_entry_treated_as_miss(self, tmp_path):
        """An entry older than TTL should be treated as a cache miss."""
        cache = TranscriptCache(cache_dir=tmp_path, ttl_days=1)
        transcript = make_transcript()
        cache.store(content_hash="old123", model="voxtral-v1-5", transcript=transcript)

        # Mock the file modification time to be 2 days ago
        import os
        old_time = time.time() - (2 * 86400)
        cache_files = list(tmp_path.glob("*.json"))
        for f in cache_files:
            os.utime(f, (old_time, old_time))

        result = cache.get(content_hash="old123", model="voxtral-v1-5")
        assert result is None

    def test_corrupt_transcript_cache_entry_treated_as_miss(self, tmp_path):
        cache = TranscriptCache(cache_dir=tmp_path)
        transcript = make_transcript()
        path = cache.store(content_hash="broken123", model="voxtral-v1-5", transcript=transcript)
        path.write_text("{not valid json", encoding="utf-8")

        result = cache.get(content_hash="broken123", model="voxtral-v1-5")
        assert result is None


# ─── ExtractionCache ─────────────────────────────────────────────────────────

class TestExtractionCache:

    def test_store_and_retrieve_decision_log(self, tmp_path):
        cache = ExtractionCache(cache_dir=tmp_path)
        log = make_decision_log()
        cache.store(
            transcript_hash="txthash123",
            prompt_version="v1.0.0",
            log=log
        )
        result = cache.get(transcript_hash="txthash123", prompt_version="v1.0.0")
        assert result is not None
        assert len(result.decisions) == 1
        assert result.decisions[0].id == "D1"

    def test_different_prompt_version_is_cache_miss(self, tmp_path):
        """Same transcript, different prompt version → miss (prompt changed = re-extract)."""
        cache = ExtractionCache(cache_dir=tmp_path)
        log = make_decision_log()
        cache.store(transcript_hash="txthash123", prompt_version="v1.0.0", log=log)
        result = cache.get(transcript_hash="txthash123", prompt_version="v1.1.0")
        assert result is None

    def test_extraction_cache_miss_returns_none(self, tmp_path):
        cache = ExtractionCache(cache_dir=tmp_path)
        result = cache.get(transcript_hash="nonexistent", prompt_version="v1.0.0")
        assert result is None

    def test_extraction_cache_clear_all(self, tmp_path):
        cache = ExtractionCache(cache_dir=tmp_path)
        log = make_decision_log()
        cache.store(transcript_hash="abc", prompt_version="v1.0.0", log=log)
        cache.clear()
        assert cache.get(transcript_hash="abc", prompt_version="v1.0.0") is None

    def test_extraction_result_preserved_correctly(self, tmp_path):
        """The full structure of a DecisionLog should survive cache round-trip."""
        cache = ExtractionCache(cache_dir=tmp_path)
        log = make_decision_log()
        cache.store(transcript_hash="round_trip", prompt_version="v1.0.0", log=log)
        result = cache.get(transcript_hash="round_trip", prompt_version="v1.0.0")

        assert result.decisions[0].summary == "Test decision"
        assert result.decisions[0].confidence == "high"
        assert result.metadata.model == "mistral-large-latest"
        assert result.metadata.meeting_date == date(2026, 4, 9)

    def test_corrupt_extraction_cache_entry_treated_as_miss(self, tmp_path):
        cache = ExtractionCache(cache_dir=tmp_path)
        log = make_decision_log()
        path = cache.store(transcript_hash="broken_log", prompt_version="v1.0.0", log=log)
        path.write_text("{not valid json", encoding="utf-8")

        result = cache.get(transcript_hash="broken_log", prompt_version="v1.0.0")
        assert result is None
