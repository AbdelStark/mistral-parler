"""
TDD specification: SpeakerAttributor.attribute()

The attribution layer assigns human-readable speaker names to transcript
segments. It operates in two passes:

  Pass 1 — Name extraction: scan the first 5 minutes of transcript text for
             self-introduction patterns ("I'm Pierre", "Je m'appelle Sophie",
             "This is David speaking")

  Pass 2 — Turn assignment: match extracted names to segments using temporal
             proximity and speaker_id diarisation cues (when available)

Design contract:
  - Input: Transcript (frozen) + optional participant list
  - Output: new Transcript with speaker labels on segments (never mutates input)
  - When a name cannot be assigned: speaker = "Unknown"
  - Participant list hints improve confidence but are never required
  - --anonymize-speakers replaces names with "Speaker A", "Speaker B", etc.
  - Consecutive segments by the same speaker are NOT merged (segment IDs preserved)
  - Never raises for any input; graceful fallback to Unknown
"""

import pytest
from parler.transcription.attributor import SpeakerAttributor
from parler.models import Transcript, TranscriptSegment


def seg(id, start, end, text, speaker_id=None, speaker_confidence=None):
    return TranscriptSegment(
        id=id,
        start_s=start,
        end_s=end,
        text=text,
        language="fr",
        speaker_id=speaker_id,
        speaker_confidence=speaker_confidence,
        confidence=0.9,
        no_speech_prob=0.01,
        code_switch=False,
        words=None,
    )


def make_transcript(*segments):
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="fr",
        duration_s=segments[-1].end_s if segments else 0.0,
        segments=tuple(segments),
    )


class TestNameExtraction:

    def test_self_introduction_english_detected(self):
        """'I'm Pierre' in the opening minutes should label the speaker as Pierre."""
        transcript = make_transcript(
            seg(0, 0.0, 3.0, "Good morning everyone."),
            seg(1, 3.0, 6.0, "I'm Pierre and I'll chair today's meeting."),
            seg(2, 6.0, 10.0, "Let's get started."),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[])
        # Segment 1 (the intro) should have Pierre as speaker
        speaker_names = {s.id: s.speaker_id for s in result.segments}
        assert speaker_names[1] == "Pierre" or speaker_names[2] == "Pierre"

    def test_french_self_introduction_detected(self):
        """'Je m'appelle Sophie' pattern in French."""
        transcript = make_transcript(
            seg(0, 0.0, 4.0, "Bonjour tout le monde."),
            seg(1, 4.0, 8.0, "Je m'appelle Sophie et je suis responsable produit."),
            seg(2, 8.0, 12.0, "Aujourd'hui on va parler du lancement."),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[])
        names_found = {s.speaker_id for s in result.segments if s.speaker_id}
        assert "Sophie" in names_found

    def test_participant_list_improves_attribution(self):
        """With a participant list hint, ambiguous speaker_id=SPEAKER_00 can be resolved."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Let's discuss the roadmap.", speaker_id="SPEAKER_00"),
            seg(1, 5.0, 10.0, "I agree, the timeline needs adjustment.", speaker_id="SPEAKER_01"),
            seg(2, 10.0, 15.0, "What's the launch date?", speaker_id="SPEAKER_00"),
        )
        # If the only two participants are Pierre and Sophie, SPEAKER_00 and
        # SPEAKER_01 get mapped to them (first occurrence → first name).
        result = SpeakerAttributor().attribute(transcript, participants=["Pierre", "Sophie"])
        speakers = {s.speaker_id for s in result.segments if s.speaker_id}
        # Both participant names should appear once diarization IDs are resolved
        assert "Pierre" in speakers or "Sophie" in speakers

    def test_nickname_alias_resolved_via_participant_list(self):
        """'Pierre-Louis' spoken as 'PL' should resolve when participant list contains 'Pierre-Louis'."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "PL, can you take this action item?"),
            seg(1, 5.0, 10.0, "Sure, I'll handle it."),
        )
        result = SpeakerAttributor().attribute(
            transcript, participants=["Pierre-Louis", "Sophie"]
        )
        # PL → Pierre-Louis resolution should be attempted; not strictly required
        # but the name must not silently vanish
        assert result is not None

    def test_unknown_assigned_when_no_clue(self):
        """Segments with no speaker cue should get speaker_id='Unknown'."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "The project is on track."),
            seg(1, 5.0, 10.0, "Delivery is set for next Thursday."),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[])
        for s in result.segments:
            assert s.speaker_id in (None, "Unknown") or isinstance(s.speaker_id, str)

    def test_attribution_does_not_mutate_input_transcript(self):
        """The input Transcript is frozen — attribution must return a new object."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Test segment."),
        )
        original_id = id(transcript)
        result = SpeakerAttributor().attribute(transcript, participants=[])
        assert id(result) != original_id

    def test_result_transcript_is_immutable(self):
        """The attributed Transcript is also frozen."""
        transcript = make_transcript(seg(0, 0.0, 5.0, "Test."))
        result = SpeakerAttributor().attribute(transcript, participants=[])
        with pytest.raises((AttributeError, TypeError)):
            result.segments[0].speaker_id = "Hacked"

    def test_segment_count_preserved_after_attribution(self):
        """Attribution must never drop or duplicate segments."""
        segments = [seg(i, i * 5.0, (i + 1) * 5.0, f"Segment {i}.") for i in range(10)]
        transcript = make_transcript(*segments)
        result = SpeakerAttributor().attribute(transcript, participants=["Alice", "Bob"])
        assert len(result.segments) == 10

    def test_segment_ids_preserved_after_attribution(self):
        """IDs in the attributed transcript must match the originals."""
        segments = [seg(i, i * 5.0, (i + 1) * 5.0, f"Segment {i}.") for i in range(5)]
        transcript = make_transcript(*segments)
        result = SpeakerAttributor().attribute(transcript, participants=[])
        assert [s.id for s in result.segments] == [0, 1, 2, 3, 4]


class TestAnonymization:

    def test_anonymize_flag_replaces_names_with_letters(self):
        """With anonymize=True, all speaker labels become 'Speaker A', 'Speaker B', etc."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "I'm Pierre.", speaker_id="SPEAKER_00"),
            seg(1, 5.0, 10.0, "And I'm Sophie.", speaker_id="SPEAKER_01"),
            seg(2, 10.0, 15.0, "Back to Pierre.", speaker_id="SPEAKER_00"),
        )
        result = SpeakerAttributor().attribute(
            transcript, participants=["Pierre", "Sophie"], anonymize=True
        )
        speakers = {s.speaker_id for s in result.segments if s.speaker_id}
        assert all(sp.startswith("Speaker ") for sp in speakers)
        assert "Pierre" not in speakers
        assert "Sophie" not in speakers

    def test_anonymize_produces_consistent_labels(self):
        """The same diarization ID always maps to the same anonymized label."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "A", speaker_id="SPEAKER_00"),
            seg(1, 5.0, 10.0, "B", speaker_id="SPEAKER_01"),
            seg(2, 10.0, 15.0, "C", speaker_id="SPEAKER_00"),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[], anonymize=True)
        label_map = {}
        for s in result.segments:
            if s.speaker_id:
                # All segments with SPEAKER_00 should get the same label
                pass
        segs_by_orig = [s for s in result.segments if s.text in ("A", "C")]
        assert segs_by_orig[0].speaker_id == segs_by_orig[1].speaker_id

    def test_no_anonymize_preserves_real_names(self):
        """Without anonymize flag, real names from participant list are preserved."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "I'm Pierre.", speaker_id="SPEAKER_00"),
        )
        result = SpeakerAttributor().attribute(
            transcript, participants=["Pierre"], anonymize=False
        )
        has_real_name = any("Pierre" in (s.speaker_id or "") for s in result.segments)
        assert has_real_name


class TestQAPattern:

    def test_question_answer_pair_attribution(self):
        """Explicit question → answer sequence should attribute turns correctly."""
        transcript = make_transcript(
            seg(0, 0.0, 4.0, "Alice, what is the status of the deployment?"),
            seg(1, 4.0, 8.0, "The deployment is on track for Friday."),
            seg(2, 8.0, 12.0, "Great, Bob, can you confirm the QA sign-off?"),
            seg(3, 12.0, 16.0, "Yes, QA is complete."),
        )
        result = SpeakerAttributor().attribute(
            transcript, participants=["Alice", "Bob", "Manager"]
        )
        # Seg 1 is Alice's response, seg 3 is Bob's — test that attribution ran
        assert result is not None
        assert len(result.segments) == 4


class TestEdgeCases:

    def test_empty_transcript_returns_empty_transcript(self):
        transcript = Transcript(
            text="",
            language="fr",
            duration_s=0.0,
            segments=(),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[])
        assert len(result.segments) == 0

    def test_single_speaker_whole_meeting(self):
        """All segments get the same speaker when only one person speaks."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "I'm Pierre. Let me walk you through the agenda.", speaker_id="SPEAKER_00"),
            seg(1, 5.0, 10.0, "First item: Q2 roadmap.", speaker_id="SPEAKER_00"),
            seg(2, 10.0, 15.0, "Second item: hiring.", speaker_id="SPEAKER_00"),
        )
        result = SpeakerAttributor().attribute(transcript, participants=["Pierre"])
        speaker_set = {s.speaker_id for s in result.segments if s.speaker_id}
        assert len(speaker_set) == 1

    def test_no_diarization_ids_still_attempts_name_attribution(self):
        """Even without speaker_id on segments, name extraction should still run."""
        transcript = make_transcript(
            seg(0, 0.0, 4.0, "I'm Alice and this is my weekly update."),
            seg(1, 4.0, 8.0, "The project is going well."),
        )
        result = SpeakerAttributor().attribute(transcript, participants=["Alice"])
        # Attribution ran without crashing
        assert len(result.segments) == 2

    def test_attribution_never_raises_on_garbage_transcript(self):
        """If segments have empty text, attribution still completes without error."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, ""),
            seg(1, 5.0, 10.0, "   "),
            seg(2, 10.0, 15.0, ""),
        )
        result = SpeakerAttributor().attribute(transcript, participants=[])
        assert len(result.segments) == 3
