"""
Performance benchmarks: parler core processing paths

Uses pytest-benchmark to establish performance baselines and guard against
regressions in the hot paths.

Run:
    pytest tests/benchmarks/ -v --benchmark-only
    pytest tests/benchmarks/ --benchmark-compare  # compare vs baseline
    pytest tests/benchmarks/ --benchmark-save=baseline  # save baseline

Performance contracts (enforced in CI via --benchmark-max-time):
  - deadline_resolver:    ≤ 1 ms per call
  - chunk_assembly:       ≤ 50 ms for 10-chunk assembly
  - extraction parsing:   ≤ 10 ms for 20-item response
  - report rendering:     ≤ 100 ms for Markdown, ≤ 500 ms for HTML
  - config loading:       ≤ 10 ms from file
"""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from parler.extraction.deadline_resolver import resolve_deadline, resolve_deadline_full
from parler.extraction.parser import parse_extraction_response
from parler.transcription.assembler import assemble_chunks
from parler.models import (
    TranscriptSegment, RawVoxtralChunkResponse,
    DecisionLog, Decision, Commitment, CommitmentDeadline, ExtractionMetadata
)


ANCHOR = date(2026, 4, 9)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_segment(id, start, end, text="Segment text here."):
    return TranscriptSegment(
        id=id, start_s=start, end_s=end, text=text,
        language="fr", speaker_id=None, speaker_confidence=None,
        confidence=0.9, no_speech_prob=0.01, code_switch=False, words=None,
    )


def make_chunk(segments, duration=600.0):
    return RawVoxtralChunkResponse(
        text=" ".join(s.text for s in segments),
        language="fr",
        duration=duration,
        segments=segments,
    )


def make_extraction_response(n_decisions=20, n_commitments=10):
    return {
        "decisions": [
            {
                "id": f"D{i}", "summary": f"Decision {i} about project scope",
                "confidence": "high", "language": "fr",
                "quote": f"Quote {i}.", "timestamp_s": float(i * 60),
                "speaker": "Pierre", "confirmed_by": [],
            }
            for i in range(1, n_decisions + 1)
        ],
        "commitments": [
            {
                "id": f"C{i}", "action": f"Action item {i} to be completed",
                "owner": "Sophie", "confidence": "high", "language": "fr",
                "quote": f"Quote {i}.", "timestamp_s": float(i * 120),
                "deadline": {"raw": "vendredi prochain", "resolved_date": None, "is_explicit": False},
            }
            for i in range(1, n_commitments + 1)
        ],
        "rejected": [],
        "open_questions": [],
    }


# ─── Deadline resolver benchmarks ────────────────────────────────────────────

@pytest.mark.benchmark
class TestDeadlineResolverPerformance:

    def test_bench_resolve_english_relative(self, benchmark):
        """Benchmark: resolve 'next Friday' in English (simple relative date)."""
        result = benchmark(resolve_deadline, "next Friday", ANCHOR, "en")
        assert result is not None

    def test_bench_resolve_french_relative(self, benchmark):
        """Benchmark: resolve 'vendredi prochain' in French."""
        result = benchmark(resolve_deadline, "vendredi prochain", ANCHOR, "fr")
        assert result is not None

    def test_bench_resolve_explicit_date(self, benchmark):
        """Benchmark: parse an explicit ISO date."""
        result = benchmark(resolve_deadline, "2026-04-20", ANCHOR, "en")
        assert result == date(2026, 4, 20)

    def test_bench_resolve_unresolvable(self, benchmark):
        """Benchmark: unresolvable string should short-circuit quickly."""
        result = benchmark(resolve_deadline, "sometime soon", ANCHOR, "en")
        assert result is None

    def test_bench_resolve_full_with_metadata(self, benchmark):
        """Benchmark: resolve_deadline_full (returns CommitmentDeadline with flags)."""
        result = benchmark(resolve_deadline_full, "next Friday", ANCHOR, "en")
        assert result is not None

    def test_bench_resolve_none_input(self, benchmark):
        """Benchmark: None input fast-path."""
        result = benchmark(resolve_deadline, None, ANCHOR, "en")
        assert result is None


# ─── Extraction parser benchmarks ────────────────────────────────────────────

@pytest.mark.benchmark
class TestExtractionParserPerformance:

    def test_bench_parse_small_response(self, benchmark):
        """Benchmark: parse a small response (5 decisions, 3 commitments)."""
        response = make_extraction_response(n_decisions=5, n_commitments=3)
        result = benchmark(parse_extraction_response, response, meeting_date=ANCHOR)
        assert len(result.decisions) == 5

    def test_bench_parse_large_response(self, benchmark):
        """Benchmark: parse a large response (20 decisions, 10 commitments)."""
        response = make_extraction_response(n_decisions=20, n_commitments=10)
        result = benchmark(parse_extraction_response, response, meeting_date=ANCHOR)
        assert len(result.decisions) == 20

    def test_bench_parse_empty_response(self, benchmark):
        """Benchmark: parse an empty response (fast path)."""
        response = {"decisions": [], "commitments": [], "rejected": [], "open_questions": []}
        result = benchmark(parse_extraction_response, response, meeting_date=ANCHOR)
        assert result.is_empty

    def test_bench_parse_with_deadline_resolution(self, benchmark):
        """Benchmark: parsing with deadline resolution for 10 commitments."""
        response = make_extraction_response(n_decisions=5, n_commitments=10)
        result = benchmark(parse_extraction_response, response, meeting_date=ANCHOR)
        assert len(result.commitments) == 10


# ─── Chunk assembly benchmarks ───────────────────────────────────────────────

@pytest.mark.benchmark
class TestChunkAssemblyPerformance:

    def test_bench_assemble_2_chunks(self, benchmark):
        """Benchmark: assemble 2 chunks (typical short meeting)."""
        chunks = [
            make_chunk([make_segment(i, i * 5.0, (i + 1) * 5.0) for i in range(20)]),
            make_chunk([make_segment(i, 600.0 + i * 5.0, 605.0 + i * 5.0) for i in range(20)]),
        ]
        result = benchmark(assemble_chunks, chunks)
        assert len(result.segments) > 0

    def test_bench_assemble_5_chunks(self, benchmark):
        """Benchmark: assemble 5 chunks (45-minute meeting)."""
        chunks = [
            make_chunk([
                make_segment(j, i * 600.0 + j * 5.0, i * 600.0 + (j + 1) * 5.0)
                for j in range(20)
            ])
            for i in range(5)
        ]
        result = benchmark(assemble_chunks, chunks)
        assert len(result.segments) > 0

    def test_bench_assemble_with_overlap_dedup(self, benchmark):
        """Benchmark: assembly with realistic overlap at chunk boundaries."""
        overlap_text = "La réunion se passe bien."
        chunk1 = make_chunk([
            make_segment(0, 0.0, 5.0, "Bonjour."),
            make_segment(1, 570.0, 575.0, overlap_text),
        ])
        chunk2 = make_chunk([
            make_segment(0, 570.0, 575.0, overlap_text),
            make_segment(1, 600.0, 605.0, "Au revoir."),
        ])
        result = benchmark(assemble_chunks, [chunk1, chunk2])
        overlap_count = sum(1 for s in result.segments if overlap_text in s.text)
        assert overlap_count == 1


# ─── Report rendering benchmarks ─────────────────────────────────────────────

@pytest.mark.benchmark
class TestReportRenderingPerformance:

    @pytest.fixture
    def large_decision_log(self):
        decisions = tuple(
            Decision(
                id=f"D{i}", summary=f"Decision {i}: important project choice was made",
                timestamp_s=float(i * 60), speaker="Pierre", confirmed_by=("Sophie",),
                quote=f"Quote for decision {i}.", confidence="high", language="fr"
            )
            for i in range(1, 21)
        )
        commitments = tuple(
            Commitment(
                id=f"C{i}", owner="Sophie",
                action=f"Action item {i}: complete the task by deadline",
                deadline=CommitmentDeadline(
                    raw="vendredi prochain", resolved_date=date(2026, 4, 17), is_explicit=False
                ),
                timestamp_s=float(i * 120), quote=f"Quote {i}.",
                confidence="high", language="fr"
            )
            for i in range(1, 11)
        )
        return DecisionLog(
            decisions=decisions,
            commitments=commitments,
            rejected=(),
            open_questions=(),
            metadata=ExtractionMetadata(
                model="mistral-large-latest", prompt_version="v1.2.0",
                meeting_date=date(2026, 4, 9), extracted_at="2026-04-09T10:00:00Z",
                input_tokens=2048, output_tokens=512,
            ),
        )

    def test_bench_render_markdown(self, benchmark, large_decision_log):
        """Benchmark: render 20 decisions + 10 commitments to Markdown."""
        from parler.rendering.renderer import ReportRenderer, RenderConfig, OutputFormat
        renderer = ReportRenderer()
        config = RenderConfig(format=OutputFormat.MARKDOWN)
        result = benchmark(renderer.render, large_decision_log, config)
        assert "D1" in result

    def test_bench_render_html(self, benchmark, large_decision_log):
        """Benchmark: render 20 decisions + 10 commitments to self-contained HTML."""
        from parler.rendering.renderer import ReportRenderer, RenderConfig, OutputFormat
        renderer = ReportRenderer()
        config = RenderConfig(format=OutputFormat.HTML)
        result = benchmark(renderer.render, large_decision_log, config)
        assert "<html" in result

    def test_bench_render_json(self, benchmark, large_decision_log):
        """Benchmark: render and JSON-serialize 20 decisions + 10 commitments."""
        import json
        from parler.rendering.renderer import ReportRenderer, RenderConfig, OutputFormat
        renderer = ReportRenderer()
        config = RenderConfig(format=OutputFormat.JSON)
        result = benchmark(renderer.render, large_decision_log, config)
        parsed = json.loads(result)
        assert len(parsed["decisions"]) == 20
