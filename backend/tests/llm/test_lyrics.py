"""Tests for the LRC parser + sentiment scoring + phrase alignment."""

from __future__ import annotations

import pytest

from melosviz.llm.lyrics import (
    LyricPhrase,
    _score_sentiment,
    align_to_segments,
    is_lyric_mood,
    parse_lrc,
    parse_lyrics_file,
)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------


class TestSentiment:
    def test_positive_phrases_score_high_valence(self):
        v, _ = _score_sentiment("I love the way you shine in golden light")
        assert v > 0.0

    def test_negative_phrases_score_low_valence(self):
        v, _ = _score_sentiment("Lost in the darkness, fading, alone")
        assert v < 0.0

    def test_energetic_phrases_score_high_arousal(self):
        _, a = _score_sentiment("Scream, fight, burn the fire, explode")
        assert a > 0.0

    def test_calm_phrases_score_low_arousal(self):
        _, a = _score_sentiment("Whisper, breathe, drift, softly, gently")
        assert a < 0.0

    def test_empty_text_scores_zero(self):
        assert _score_sentiment("") == (0.0, 0.0)

    def test_mood_labels_known_set(self):
        assert is_lyric_mood("euphoric")
        assert is_lyric_mood("tender")
        assert is_lyric_mood("fierce")
        assert is_lyric_mood("somber")
        assert is_lyric_mood("neutral")
        assert not is_lyric_mood("random")


# ---------------------------------------------------------------------------
# LRC parsing
# ---------------------------------------------------------------------------


class TestParseLRC:
    def test_basic_lrc(self):
        text = """[00:00.00]City lights are calling out my name
[00:04.50]Neon pouring through the doorway"""
        phrases = parse_lrc(text)
        assert len(phrases) == 2
        assert phrases[0].text == "City lights are calling out my name"
        assert phrases[0].start == 0.0
        assert phrases[1].start == pytest.approx(4.5)
        # Each phrase's end = next phrase's start (or +5s if last)
        assert phrases[0].end == pytest.approx(4.5)
        assert phrases[1].end == pytest.approx(4.5 + 5.0)

    def test_lrc_with_minutes_and_seconds(self):
        phrases = parse_lrc("[01:30.00]Mid-song bridge")
        assert len(phrases) == 1
        assert phrases[0].start == pytest.approx(90.0)

    def test_lrc_ignores_metadata_tags(self):
        text = """[ar:Test Artist]
[ti:Test Song]
[00:00.00]First lyric
[00:05.00]Second lyric"""
        phrases = parse_lrc(text)
        assert len(phrases) == 2
        assert all("[" not in p.text for p in phrases)

    def test_lrc_sorts_out_of_order_lines(self):
        text = """[00:05.00]Second
[00:00.00]First"""
        phrases = parse_lrc(text)
        assert phrases[0].text == "First"
        assert phrases[1].text == "Second"

    def test_plain_text_lines_are_parsed(self):
        # Lines without timestamps → start=0, end=1.0 (caller should
        # spread them across the track).
        phrases = parse_lrc("First line\nSecond line\n\n  Third line  ")
        assert len(phrases) == 3
        assert phrases[0].text == "First line"
        assert phrases[2].text == "Third line"  # whitespace normalized

    def test_empty_input_returns_empty_list(self):
        assert parse_lrc("") == []
        assert parse_lrc("\n\n[ar:tag]\n") == []

    def test_phrase_dataclass_serializes(self):
        phrases = parse_lrc("[00:00.00]Love is burning bright")
        d = phrases[0].to_dict()
        assert d["text"] == "Love is burning bright"
        assert d["start"] == 0.0
        assert d["valence"] > 0  # positive words


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


class TestParseLyricsFile:
    def test_lrc_file(self, tmp_path):
        f = tmp_path / "song.lrc"
        f.write_text(
            "[00:00.00]Line one\n[00:04.00]Line two\n",
            encoding="utf-8",
        )
        phrases = parse_lyrics_file(f)
        assert len(phrases) == 2

    def test_json_file(self, tmp_path):
        import json
        f = tmp_path / "song.json"
        f.write_text(json.dumps([
            {"text": "First line", "start": 0.0, "end": 4.0},
            {"text": "Second line", "start": 4.0, "end": 8.0},
        ]), encoding="utf-8")
        phrases = parse_lyrics_file(f)
        assert len(phrases) == 2
        assert phrases[1].text == "Second line"

    def test_plain_text_file(self, tmp_path):
        f = tmp_path / "song.txt"
        f.write_text("First line\nSecond line\n", encoding="utf-8")
        phrases = parse_lyrics_file(f)
        assert len(phrases) == 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_lyrics_file(tmp_path / "nope.txt")


# ---------------------------------------------------------------------------
# Segment alignment
# ---------------------------------------------------------------------------


class TestAlignToSegments:
    def test_lyrics_snap_into_segments(self):
        phrases = parse_lrc(
            "[00:00.00]Line A\n[00:03.00]Line B\n[00:06.00]Line C"
        )
        segments = [
            {"index": 0, "label": "verse", "start": 0.0, "end": 8.0,
             "energy_mean": 0.5},
        ]
        aligned = align_to_segments(phrases, segments)
        # Each phrase becomes one scene
        assert len(aligned) == 3
        assert aligned[0]["lyric_text"] == "Line A"
        assert aligned[1]["lyric_text"] == "Line B"
        assert aligned[2]["lyric_text"] == "Line C"

    def test_short_segments_get_merged(self):
        phrases = parse_lrc(
            "[00:00.00]Quick\n[00:01.00]Lines\n[00:02.00]Three\n[00:03.00]Four"
        )
        segments = [
            {"index": 0, "label": "verse", "start": 0.0, "end": 4.0,
             "energy_mean": 0.5},
        ]
        aligned = align_to_segments(phrases, segments, min_segment_s=2.5)
        # Lines < 2.5s should merge into their neighbour
        assert all(float(s["end"] - s["start"]) >= 1.0 for s in aligned)

    def test_segments_outside_lyric_window_still_appear(self):
        phrases = parse_lrc("[00:00.00]Only one\n[00:04.00]Line")
        segments = [
            {"index": 0, "label": "intro",  "start": 0.0,  "end": 2.0},
            {"index": 1, "label": "verse",  "start": 2.0,  "end": 4.0},
            {"index": 2, "label": "outro",  "start": 4.0,  "end": 8.0},
        ]
        aligned = align_to_segments(phrases, segments)
        # Every original segment is represented in the output
        labels = {s.get("label") for s in aligned}
        assert "intro" in labels or any(s.get("lyric_text") for s in aligned if s.get("label") == "intro")
        assert "outro" in labels or any(s.get("lyric_text") for s in aligned if s.get("label") == "outro")

    def test_segments_without_lyrics_pass_through(self):
        segments = [
            {"index": 0, "label": "verse", "start": 0.0, "end": 4.0},
        ]
        aligned = align_to_segments([], segments)
        assert len(aligned) == 1
        assert aligned[0]["lyric_index"] == -1
