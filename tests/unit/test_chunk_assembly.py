"""
TDD specification: VoxtralTranscriber.assemble()

The assembly function merges overlapping transcript segments from adjacent
audio chunks into a single coherent transcript with:
  - No duplicate sentences at chunk boundaries
  - Monotonically increasing timestamps
  - The highest-confidence version of each duplicated segment preserved
  - Correct re-indexing of segment IDs after merge
"""

import pytest
from parler.transcription.assembler import assemble_chunks
from parler.models import TranscriptSegment, RawVoxtralChunkResponse, ChunkPlan, AudioChunk
from pathlib import Path
from unittest.mock import MagicMock


def make_segment(id, start, end, text, confidence=0.9, no_speech_prob=0.01, lang="fr"):
    return TranscriptSegment(
        id=id,
        start_s=start,
        end_s=end,
        text=text,
        language=lang,
        speaker_id=None,
        speaker_confidence=None,
        confidence=confidence,
        no_speech_prob=no_speech_prob,
        code_switch=False,
        words=None
    )


def make_chunk_response(segments, language="fr", duration=600.0):
    return RawVoxtralChunkResponse(
        text=" ".join(s.text for s in segments),
        language=language,
        duration=duration,
        segments=segments
    )


class TestBasicAssembly:

    def test_single_chunk_is_returned_unchanged(self):
        segments = [
            make_segment(0, 0.0, 4.0, "Bonjour à tous."),
            make_segment(1, 4.0, 8.0, "Commençons la réunion."),
        ]
        chunk_response = make_chunk_response(segments)
        result = assemble_chunks([chunk_response])
        assert len(result.segments) == 2
        assert result.segments[0].text == "Bonjour à tous."
        assert result.segments[1].text == "Commençons la réunion."

    def test_two_non_overlapping_chunks_concatenated(self):
        chunk1_segments = [
            make_segment(0, 0.0, 5.0, "Segment A"),
            make_segment(1, 5.0, 10.0, "Segment B"),
        ]
        chunk2_segments = [
            make_segment(0, 600.0, 605.0, "Segment C"),
            make_segment(1, 605.0, 610.0, "Segment D"),
        ]
        result = assemble_chunks([
            make_chunk_response(chunk1_segments),
            make_chunk_response(chunk2_segments),
        ])
        assert len(result.segments) == 4
        texts = [s.text for s in result.segments]
        assert "Segment A" in texts
        assert "Segment D" in texts

    def test_segment_ids_reindexed_sequentially_after_assembly(self):
        chunk1 = [make_segment(0, 0.0, 5.0, "First"), make_segment(1, 5.0, 10.0, "Second")]
        chunk2 = [make_segment(0, 600.0, 605.0, "Third"), make_segment(1, 605.0, 610.0, "Fourth")]
        result = assemble_chunks([make_chunk_response(chunk1), make_chunk_response(chunk2)])
        for i, seg in enumerate(result.segments):
            assert seg.id == i, f"Segment {i} has id {seg.id}, expected {i}"

    def test_timestamps_are_monotonically_increasing(self):
        chunk1 = [make_segment(0, 0.0, 5.0, "A"), make_segment(1, 5.0, 10.0, "B")]
        chunk2 = [make_segment(0, 600.0, 605.0, "C"), make_segment(1, 605.0, 610.0, "D")]
        result = assemble_chunks([make_chunk_response(chunk1), make_chunk_response(chunk2)])
        starts = [s.start_s for s in result.segments]
        assert starts == sorted(starts), f"Timestamps not monotonically increasing: {starts}"


class TestOverlapDeduplication:

    def test_duplicate_segment_at_overlap_removed(self):
        """
        Chunk 1 ends with "La réunion se passe bien." (high confidence)
        Chunk 2 starts with "La réunion se passe bien." (same text, lower confidence)
        Expected: only one copy retained
        """
        overlap_text = "La réunion se passe bien."
        chunk1 = [
            make_segment(0, 0.0, 5.0, "Bonjour."),
            make_segment(1, 570.0, 575.0, overlap_text, confidence=0.92),  # at chunk 1 end
        ]
        chunk2 = [
            make_segment(0, 570.0, 575.0, overlap_text, confidence=0.78),  # same text, lower conf
            make_segment(1, 600.0, 605.0, "Continuons."),
        ]
        result = assemble_chunks([
            make_chunk_response(chunk1),
            make_chunk_response(chunk2),
        ])
        matching = [s for s in result.segments if overlap_text in s.text]
        assert len(matching) == 1, f"Expected 1 copy, got {len(matching)}"

    def test_higher_confidence_version_preserved_in_overlap(self):
        """When two versions of a segment exist, keep the higher-confidence one."""
        text = "La réunion se passe bien."
        chunk1 = [make_segment(0, 570.0, 575.0, text, confidence=0.92)]
        chunk2 = [make_segment(0, 570.0, 575.0, text, confidence=0.78)]
        result = assemble_chunks([make_chunk_response(chunk1), make_chunk_response(chunk2)])
        matching = [s for s in result.segments if text in s.text]
        assert len(matching) == 1
        assert matching[0].confidence == pytest.approx(0.92)

    def test_slightly_different_text_in_overlap_both_retained(self):
        """
        Same region, different text (Voxtral transcribed differently in each chunk).
        Both are retained; deduplication only removes near-identical segments.
        """
        chunk1 = [make_segment(0, 570.0, 575.0, "On va commencer.")]
        chunk2 = [make_segment(0, 571.0, 576.0, "On va commencer maintenant.")]  # extra word
        result = assemble_chunks([make_chunk_response(chunk1), make_chunk_response(chunk2)])
        # Both retained because texts differ meaningfully
        assert len([s for s in result.segments if "commencer" in s.text]) == 2

    def test_no_speech_segments_not_duplicated(self):
        """Silence/no-speech segments at boundaries should not be duplicated."""
        silence = make_segment(0, 590.0, 600.0, "", no_speech_prob=0.95)
        chunk1 = [make_segment(0, 580.0, 590.0, "Last sentence."), silence]
        chunk2 = [silence, make_segment(1, 600.0, 610.0, "First sentence.")]
        result = assemble_chunks([make_chunk_response(chunk1), make_chunk_response(chunk2)])
        silence_segs = [s for s in result.segments if s.no_speech_prob > 0.9]
        assert len(silence_segs) <= 1, "Silence segment duplicated at chunk boundary"


class TestAssemblyInvariants:

    def test_total_duration_within_2_percent_of_input(self):
        """The assembled transcript's time span should match the audio duration."""
        audio_duration = 2700.0  # 45 minutes
        chunk1 = [make_segment(0, 0.0, 5.0, "A")]
        chunk_last = [make_segment(0, 2695.0, 2700.0, "Z")]
        result = assemble_chunks([
            make_chunk_response(chunk1, duration=600.0),
            make_chunk_response(chunk_last, duration=600.0),
        ])
        actual_duration = result.segments[-1].end_s - result.segments[0].start_s
        assert abs(actual_duration - audio_duration) / audio_duration < 0.02

    def test_assembly_result_is_immutable(self):
        """Transcript is a frozen dataclass; modifying should raise."""
        chunk = [make_segment(0, 0.0, 5.0, "Test")]
        result = assemble_chunks([make_chunk_response(chunk)])
        with pytest.raises((AttributeError, TypeError)):
            result.segments[0].text = "Modified"  # should raise on frozen dataclass

    def test_empty_chunk_list_raises_value_error(self):
        with pytest.raises(ValueError, match="at least one chunk"):
            assemble_chunks([])

    def test_five_chunks_assembled_correctly(self):
        """Stress test: 5 chunks covering 50 minutes."""
        chunks = []
        for i in range(5):
            start = i * 600.0
            segs = [make_segment(0, start, start + 5.0, f"Segment {i*2}"),
                    make_segment(1, start + 5.0, start + 10.0, f"Segment {i*2+1}")]
            chunks.append(make_chunk_response(segs, duration=600.0))

        result = assemble_chunks(chunks)
        # 5 chunks × 2 segments = 10 segments (no overlap in this test)
        assert len(result.segments) == 10
        starts = [s.start_s for s in result.segments]
        assert starts == sorted(starts)
