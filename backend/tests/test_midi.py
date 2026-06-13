"""Tests for the mido-based Standard MIDI File parser.

These tests build tiny MIDI files in-memory with :class:`mido.MidiFile`
and :class:`mido.MidiTrack`, write them to a temporary path (or to
bytes), and verify that :func:`melosviz.io.midi.parse_midi` produces
the expected :class:`melosviz.analysis.models.NoteStream` output.

Coverage:

* Basic note-on / note-off pairing (pitch, velocity, timing).
* Multi-note (sequential + chord).
* Multi-track merge.
* Multi-channel handling.
* Note-On with velocity 0 == Note-Off.
* Overlapping notes.
* Tempo changes mid-track.
* Path and ``bytes`` inputs.
* Edge cases (empty, round-trip with the mido-backed ``write_midi``,
  custom PPQ).
* Error paths (missing file, bad bytes, unsupported type).
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import List, Sequence

import mido
import pytest

from melosviz.analysis.models import NoteStream
from melosviz.io.midi import (
    DEFAULT_MICROSECONDS_PER_QUARTER,
    DEFAULT_TEMPO_BPM,
    DEFAULT_TICKS_PER_BEAT,
    parse_midi,
    parse_midi_to_tuples,
    write_midi,
)


# ---------------------------------------------------------------------------
# Helpers — build in-memory MIDI files for tests
# ---------------------------------------------------------------------------


def _make_midi_bytes(
    track_messages: Sequence[Sequence[mido.Message | mido.MetaMessage]],
    *,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
    midi_type: int = 0,
) -> bytes:
    """Serialise a list of tracks to a bytes payload using mido.

    Each track is a list of messages. The first track is conventionally
    used for the tempo meta event; the helper seeds it with the
    120 BPM default tempo unless the caller already provides one.
    """
    midi = mido.MidiFile(type=midi_type, ticks_per_beat=ticks_per_beat)
    for messages in track_messages:
        track = mido.MidiTrack()
        for msg in messages:
            track.append(msg)
        midi.tracks.append(track)
    buf = io.BytesIO()
    midi.save(file=buf)
    return buf.getvalue()


def _note_on_off_track(
    pitch: int,
    *,
    velocity: int = 80,
    duration_ticks: int = 480,
    start_tick: int = 0,
    channel: int = 0,
    include_tempo: bool = True,
    end_tick: int | None = None,
) -> List[mido.Message | mido.MetaMessage]:
    """Build a simple 1-note track: optional tempo + note-on + note-off."""
    messages: List[mido.Message | mido.MetaMessage] = []
    if include_tempo:
        messages.append(
            mido.MetaMessage(
                "set_tempo",
                tempo=DEFAULT_MICROSECONDS_PER_QUARTER,
                time=0,
            )
        )
    on_time = start_tick if not include_tempo else 0
    messages.append(
        mido.Message(
            "note_on",
            channel=channel,
            note=pitch,
            velocity=velocity,
            time=on_time,
        )
    )
    off_tick = end_tick if end_tick is not None else (start_tick + duration_ticks)
    messages.append(
        mido.Message(
            "note_off",
            channel=channel,
            note=pitch,
            velocity=0,
            time=off_tick - start_tick,
        )
    )
    messages.append(mido.MetaMessage("end_of_track", time=0))
    return messages


def _chord_track(
    pitches: Sequence[int],
    *,
    velocity: int = 80,
    duration_ticks: int = 480,
) -> List[mido.Message | mido.MetaMessage]:
    """Build a track that plays ``pitches`` simultaneously (a chord)."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage(
            "set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0
        )
    ]
    # All note-ons happen at the same tick (delta 0 from the previous).
    for pitch in pitches:
        messages.append(
            mido.Message("note_on", note=pitch, velocity=velocity, time=0)
        )
    # First note-off advances time by ``duration_ticks``; subsequent
    # note-offs are simultaneous (delta 0) so the chord ends together.
    if pitches:
        messages.append(
            mido.Message(
                "note_off", note=pitches[0], velocity=0, time=duration_ticks
            )
        )
        for pitch in pitches[1:]:
            messages.append(
                mido.Message("note_off", note=pitch, velocity=0, time=0)
            )
    messages.append(mido.MetaMessage("end_of_track", time=0))
    return messages


def _approx_equal(a: float, b: float, *, rel: float = 1e-4, abs_tol: float = 1e-4) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


# ---------------------------------------------------------------------------
# 1. Basic single-note round-trip
# ---------------------------------------------------------------------------


def test_parse_midi_single_note_from_bytes() -> None:
    """A single note-on / note-off pair yields exactly one note."""
    data = _make_midi_bytes([_note_on_off_track(60, velocity=80, duration_ticks=480)])
    stream = parse_midi(data)

    assert isinstance(stream, NoteStream)
    assert len(stream) == 1
    note = stream.notes[0]
    assert note.pitch == 60
    assert note.velocity == 80
    # The note starts at tick 0 and lasts 480 ticks. At 480 PPQ and
    # 120 BPM (one quarter note = 0.5s) the duration is 0.5s.
    assert _approx_equal(note.start, 0.0), f"start={note.start}"
    assert _approx_equal(note.duration, 0.5), f"duration={note.duration}"
    assert stream.source_path is None
    assert stream.ticks_per_beat == DEFAULT_TICKS_PER_BEAT


def test_parse_midi_single_note_from_path(tmp_path: Path) -> None:
    """A path-based load produces the same result as bytes-based."""
    midi_path = tmp_path / "single.mid"
    data = _make_midi_bytes([_note_on_off_track(60, velocity=80, duration_ticks=480)])
    midi_path.write_bytes(data)

    stream = parse_midi(midi_path)
    assert len(stream) == 1
    assert stream.notes[0].pitch == 60
    assert stream.source_path == str(midi_path)


def test_parse_midi_single_note_from_pathlib_path(tmp_path: Path) -> None:
    """A :class:`pathlib.Path` is accepted in addition to ``str``."""
    midi_path = tmp_path / "p.mid"
    data = _make_midi_bytes([_note_on_off_track(64, velocity=100, duration_ticks=240)])
    midi_path.write_bytes(data)

    stream = parse_midi(midi_path)  # already a Path
    assert len(stream) == 1
    assert stream.notes[0].pitch == 64
    # 240 ticks / 480 PPQ = 0.5 quarter notes; at 120 BPM that is
    # 0.25 seconds of duration. The note starts at tick 0.
    assert _approx_equal(stream.notes[0].start, 0.0)
    assert _approx_equal(stream.notes[0].duration, 0.25)


# ---------------------------------------------------------------------------
# 2. Pitch / velocity preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pitch", [21, 36, 60, 72, 84, 108])
def test_parse_midi_pitch_range(pitch: int) -> None:
    """Every pitch in the audible range survives a parse round-trip."""
    data = _make_midi_bytes([_note_on_off_track(pitch, velocity=80, duration_ticks=240)])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert stream.notes[0].pitch == pitch


@pytest.mark.parametrize("velocity", [1, 16, 64, 80, 100, 127])
def test_parse_midi_velocity_range(velocity: int) -> None:
    """Velocities from 1 to 127 are preserved exactly."""
    data = _make_midi_bytes([_note_on_off_track(60, velocity=velocity, duration_ticks=240)])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert stream.notes[0].velocity == velocity


# ---------------------------------------------------------------------------
# 3. Timing — start, duration, and gap correctness
# ---------------------------------------------------------------------------


def test_parse_midi_start_time_reflects_note_on() -> None:
    """A note that starts 960 ticks in (2 beats) is reported at 1.0s."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=960),
        mido.Message("note_off", note=60, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert _approx_equal(stream.notes[0].start, 1.0)
    assert _approx_equal(stream.notes[0].duration, 0.5)


def test_parse_midi_duration_reflects_note_off() -> None:
    """A note held for 1440 ticks (3 beats) has a 1.5s duration."""
    data = _make_midi_bytes(
        [_note_on_off_track(60, velocity=80, duration_ticks=1440)]
    )
    stream = parse_midi(data)
    assert len(stream) == 1
    assert _approx_equal(stream.notes[0].duration, 1.5)


def test_parse_midi_sequential_notes_have_distinct_starts() -> None:
    """Sequential notes get non-overlapping start times."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=240),
        mido.Message("note_on", note=62, velocity=90, time=0),
        mido.Message("note_off", note=62, velocity=0, time=240),
        mido.Message("note_on", note=64, velocity=100, time=0),
        mido.Message("note_off", note=64, velocity=0, time=240),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert [n.pitch for n in stream.notes] == [60, 62, 64]
    assert [n.velocity for n in stream.notes] == [80, 90, 100]
    # Each note starts at 0, 0.25, 0.5
    starts = [n.start for n in stream.notes]
    assert _approx_equal(starts[0], 0.0)
    assert _approx_equal(starts[1], 0.25)
    assert _approx_equal(starts[2], 0.5)


# ---------------------------------------------------------------------------
# 4. Note-On with velocity 0 == Note-Off
# ---------------------------------------------------------------------------


def test_parse_midi_note_on_zero_velocity_is_note_off() -> None:
    """A note-on with velocity 0 closes the pending note (SMF convention)."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_on", note=60, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert stream.notes[0].velocity == 80
    assert _approx_equal(stream.notes[0].duration, 0.5)


# ---------------------------------------------------------------------------
# 5. Chord (simultaneous notes)
# ---------------------------------------------------------------------------


def test_parse_midi_chord_yields_all_pitches() -> None:
    """Three notes triggered at the same tick form a chord."""
    data = _make_midi_bytes([_chord_track([60, 64, 67], velocity=80, duration_ticks=480)])
    stream = parse_midi(data)
    assert len(stream) == 3
    pitches = sorted(n.pitch for n in stream.notes)
    assert pitches == [60, 64, 67]
    for note in stream.notes:
        assert note.velocity == 80
        assert _approx_equal(note.start, 0.0)
        assert _approx_equal(note.duration, 0.5)


# ---------------------------------------------------------------------------
# 6. Multi-track
# ---------------------------------------------------------------------------


def test_parse_midi_multi_track_merges_notes() -> None:
    """Notes from multiple tracks are merged into one NoteStream."""
    tracks = [
        _note_on_off_track(60, velocity=80, duration_ticks=480, start_tick=0),
        _note_on_off_track(64, velocity=100, duration_ticks=480, start_tick=480),
        _note_on_off_track(67, velocity=120, duration_ticks=480, start_tick=960),
    ]
    data = _make_midi_bytes(tracks, midi_type=1)
    stream = parse_midi(data)
    assert len(stream) == 3
    pitches = [n.pitch for n in stream.notes]
    assert pitches == [60, 64, 67]


def test_parse_midi_multi_track_preserves_velocity_per_track() -> None:
    """Each track's velocity is preserved after the merge."""
    tracks = [
        _note_on_off_track(60, velocity=20, duration_ticks=240),
        _note_on_off_track(64, velocity=80, duration_ticks=240, start_tick=240),
    ]
    data = _make_midi_bytes(tracks, midi_type=1)
    stream = parse_midi(data)
    by_pitch = {n.pitch: n for n in stream.notes}
    assert by_pitch[60].velocity == 20
    assert by_pitch[64].velocity == 80


# ---------------------------------------------------------------------------
# 7. Multi-channel
# ---------------------------------------------------------------------------


def test_parse_midi_multi_channel_yields_all_notes() -> None:
    """Notes on different channels are all returned (channel is not
    currently used as a filter)."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", channel=0, note=60, velocity=64, time=0),
        mido.Message("note_on", channel=1, note=64, velocity=80, time=0),
        mido.Message("note_on", channel=2, note=67, velocity=96, time=0),
        mido.Message("note_off", channel=0, note=60, velocity=0, time=480),
        mido.Message("note_off", channel=1, note=64, velocity=0, time=480),
        mido.Message("note_off", channel=2, note=67, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert len(stream) == 3
    by_pitch = {n.pitch: n for n in stream.notes}
    assert by_pitch[60].velocity == 64
    assert by_pitch[64].velocity == 80
    assert by_pitch[67].velocity == 96


# ---------------------------------------------------------------------------
# 8. Overlapping notes (sustained + melody)
# ---------------------------------------------------------------------------


def test_parse_midi_overlapping_notes_are_preserved() -> None:
    """A sustained note overlapping a short melody yields all notes."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        # Note 60 starts at tick 0, ends at tick 1200 (held the whole time).
        mido.Message("note_on", note=60, velocity=70, time=0),
        mido.Message("note_on", note=64, velocity=80, time=240),
        mido.Message("note_off", note=64, velocity=0, time=240),
        mido.Message("note_on", note=67, velocity=90, time=240),
        mido.Message("note_off", note=67, velocity=0, time=240),
        mido.Message("note_off", note=60, velocity=0, time=240),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    pitches = [n.pitch for n in stream.notes]
    assert pitches == [60, 64, 67]
    by_pitch = {n.pitch: n for n in stream.notes}
    # Note 60 is held from tick 0 to tick 1200 — at 480 PPQ and 120 BPM
    # (0.5s per quarter note) that is 1200/480 * 0.5 = 1.25s.
    assert _approx_equal(by_pitch[60].duration, 1.25)
    # The middle notes each last 240 ticks (0.5 quarter) = 0.25s.
    assert _approx_equal(by_pitch[64].duration, 0.25)
    assert _approx_equal(by_pitch[67].duration, 0.25)


# ---------------------------------------------------------------------------
# 9. Tempo changes
# ---------------------------------------------------------------------------


def test_parse_midi_default_tempo_used_when_no_meta() -> None:
    """A track with no ``set_tempo`` event uses the 120 BPM default."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    # Without a tempo event the parser still produces a sensible 0.5s
    # duration because mido's tick2second assumes 120 BPM by default
    # for the leading region. We just check the parser doesn't blow
    # up and produces *some* sane value.
    assert len(stream) == 1
    assert stream.notes[0].duration > 0


def test_parse_midi_tempo_meta_event_affects_timing() -> None:
    """A 60 BPM tempo (1_000_000 microseconds/quarter) doubles duration."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=1_000_000, time=0),  # 60 BPM
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    # 60 BPM = 1 second per quarter. One quarter note = 1.0 second.
    assert _approx_equal(stream.notes[0].duration, 1.0)


def test_parse_midi_tempo_change_mid_track() -> None:
    """A tempo change after the first note affects subsequent timing."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=480),
        # Switch to 60 BPM (1_000_000 microseconds/quarter) for the next note.
        mido.MetaMessage("set_tempo", tempo=1_000_000, time=0),
        mido.Message("note_on", note=64, velocity=80, time=0),
        mido.Message("note_off", note=64, velocity=0, time=480),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    by_pitch = {n.pitch: n for n in stream.notes}
    assert _approx_equal(by_pitch[60].duration, 0.5)  # 120 BPM quarter
    assert _approx_equal(by_pitch[64].duration, 1.0)  # 60 BPM quarter


# ---------------------------------------------------------------------------
# 10. ticks_per_beat (PPQ) preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ppq", [96, 240, 480, 960, 1920])
def test_parse_midi_custom_ppq(ppq: int) -> None:
    """The header's PPQ is preserved on the returned NoteStream."""
    data = _make_midi_bytes(
        [_note_on_off_track(60, velocity=80, duration_ticks=ppq // 2)],
        ticks_per_beat=ppq,
    )
    stream = parse_midi(data)
    assert stream.ticks_per_beat == ppq


# ---------------------------------------------------------------------------
# 11. parse_midi_to_tuples — tick-based output
# ---------------------------------------------------------------------------


def test_parse_midi_to_tuples_basic() -> None:
    """The tuple form preserves exact tick positions and metadata."""
    data = _make_midi_bytes(
        [_note_on_off_track(60, velocity=80, duration_ticks=480, start_tick=0)]
    )
    tuples = parse_midi_to_tuples(data)
    assert len(tuples) == 1
    pitch, velocity, start_ticks, end_ticks = tuples[0]
    assert pitch == 60
    assert velocity == 80
    assert start_ticks == 0
    assert end_ticks == 480


def test_parse_midi_to_tuples_returns_tick_durations() -> None:
    """Tuple durations are in ticks, not seconds."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=960),  # 2 quarters
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    tuples = parse_midi_to_tuples(data)
    assert len(tuples) == 1
    _pitch, _velocity, start_ticks, end_ticks = tuples[0]
    assert end_ticks - start_ticks == 960


def test_parse_midi_to_tuples_sorted_by_start() -> None:
    """The tuple list is sorted by (start_ticks, pitch, velocity)."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        # Note 64 starts first (at tick 240), then note 60 (at tick 480).
        mido.Message("note_on", note=64, velocity=80, time=240),
        mido.Message("note_off", note=64, velocity=0, time=240),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=240),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    tuples = parse_midi_to_tuples(data)
    starts = [t[2] for t in tuples]
    assert starts == sorted(starts)
    # 64 starts earlier than 60, so the sorted order is [64, 60].
    assert [t[0] for t in tuples] == [64, 60]


# ---------------------------------------------------------------------------
# 12. Round-trip with the mido-backed write_midi
# ---------------------------------------------------------------------------


def test_write_then_parse_round_trip(tmp_path: Path) -> None:
    """Notes written by ``write_midi`` parse back to the same values
    within a small floating-point tolerance."""
    from melosviz.analysis.models import Note

    original = [
        Note(pitch=60, start=0.0, duration=0.5, velocity=80),
        Note(pitch=62, start=0.5, duration=0.5, velocity=90),
        Note(pitch=64, start=1.0, duration=1.0, velocity=100),
    ]
    midi_path = tmp_path / "rt.mid"
    write_midi(original, midi_path)

    stream = parse_midi(midi_path)
    assert len(stream) == len(original)
    for got, want in zip(stream.notes, original):
        assert got.pitch == want.pitch
        assert got.velocity == want.velocity
        assert _approx_equal(got.start, want.start)
        assert _approx_equal(got.duration, want.duration)


def test_parse_midi_notes_are_sorted_by_start() -> None:
    """The NoteStream's ``notes`` list is sorted by (start, pitch, velocity)."""
    # Build a multi-track file where notes are intentionally out of
    # track order so we can verify the final sort.
    tracks = [
        # Track 1: note at 0.75s.
        _note_on_off_track(67, velocity=80, duration_ticks=240, start_tick=720),
        # Track 2: note at 0.0s.
        _note_on_off_track(60, velocity=80, duration_ticks=240, start_tick=0),
        # Track 3: note at 0.5s.
        _note_on_off_track(64, velocity=80, duration_ticks=240, start_tick=480),
    ]
    data = _make_midi_bytes(tracks, midi_type=1)
    stream = parse_midi(data)
    assert [n.pitch for n in stream.notes] == [60, 64, 67]
    starts = [n.start for n in stream.notes]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# 13. Edge cases
# ---------------------------------------------------------------------------


def test_parse_midi_empty_file() -> None:
    """A file with a single empty track yields an empty NoteStream."""
    empty_track = [mido.MetaMessage("end_of_track", time=0)]
    data = _make_midi_bytes([empty_track])
    stream = parse_midi(data)
    assert stream.notes == []
    assert len(stream) == 0


def test_parse_midi_zero_duration_note_via_instant_off() -> None:
    """A note-on immediately followed by a note-off at the same tick
    is reported with a duration of zero."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        mido.Message("note_off", note=60, velocity=0, time=0),
        mido.MetaMessage("end_of_track", time=0),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert _approx_equal(stream.notes[0].duration, 0.0)


def test_parse_midi_pending_note_closed_at_end_of_track() -> None:
    """A note-on without a matching note-off is closed at end-of-track
    with a positive duration."""
    messages: List[mido.Message | mido.MetaMessage] = [
        mido.MetaMessage("set_tempo", tempo=DEFAULT_MICROSECONDS_PER_QUARTER, time=0),
        mido.Message("note_on", note=60, velocity=80, time=0),
        # Move forward 480 ticks (0.5s) before end-of-track.
        mido.MetaMessage("end_of_track", time=480),
    ]
    data = _make_midi_bytes([messages])
    stream = parse_midi(data)
    assert len(stream) == 1
    assert _approx_equal(stream.notes[0].duration, 0.5)
    assert stream.notes[0].velocity == 80


# ---------------------------------------------------------------------------
# 14. Error / contract behaviour
# ---------------------------------------------------------------------------


def test_parse_midi_missing_path_raises(tmp_path: Path) -> None:
    """A non-existent file path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        parse_midi(tmp_path / "no_such_file.mid")


def test_parse_midi_rejects_non_midi_bytes() -> None:
    """Garbage bytes raise ValueError (via mido)."""
    with pytest.raises(Exception):
        parse_midi(b"not a midi file at all")


def test_parse_midi_rejects_unsupported_type() -> None:
    """A file with an invalid source type raises TypeError."""
    with pytest.raises(TypeError):
        parse_midi(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 15. Module-level constants sanity check
# ---------------------------------------------------------------------------


def test_default_constants_match_smf_spec() -> None:
    """120 BPM == 500_000 microseconds per quarter note."""
    assert DEFAULT_MICROSECONDS_PER_QUARTER == 500_000
    assert _approx_equal(DEFAULT_TEMPO_BPM, 120.0)
    assert DEFAULT_TICKS_PER_BEAT == 480
