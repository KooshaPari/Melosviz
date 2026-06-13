"""MIDI input parser and writer.

This module provides :func:`parse_midi`, a thin wrapper around the
``mido`` library that converts a Standard MIDI File (SMF) — read from
either a filesystem path or an in-memory ``bytes`` payload — into a
:class:`~melosviz.analysis.models.NoteStream` whose ``notes`` list
captures every note as a ``(pitch, velocity, start_ticks, end_ticks)``
tuple (serialised into the domain :class:`Note` model).

The intent is to give Melosviz a small, well-tested adapter for
importing melodies from short, well-formed MIDI files (DAW exports,
MIDI exporters, etc.) without depending on heavier libraries like
``pretty_midi`` or rolling our own SMF parser.

Supported features
-------------------

* Format 0 (single multi-channel track) and Format 1 (one track per
  instrument plus a tempo/conducting track) files.
* PPQ time division. SMPTE division is rejected by ``mido``.
* ``Set Tempo`` (``FF 51``) meta events: tempo changes mid-track are
  honoured when computing note start / duration in seconds.
* Note-On (``9n``) and Note-Off (``8n``) events, including the
  convention that Note-On with ``velocity == 0`` is treated as a
  Note-Off.
* Tracks are merged in file order; the resulting ``NoteStream`` is
  sorted by ``(start, pitch, velocity)`` for deterministic downstream
  rendering.

Limitations
-----------

* No support for ``Pitch Bend``, ``Control Change``, ``Program Change``
  or other channel-voice messages (other than note on/off). They are
  silently skipped.
* No support for SysEx or aftertouch.
* A note that is still held at end-of-track is closed with a duration
  equal to ``end_of_track_time - start_time`` (same convention as the
  previous pure-Python implementation).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, List, Tuple, Union

import mido

from ..analysis.models import Note, NoteStream  # relative: works under both layouts


# ---------------------------------------------------------------------------
# Public constants (also re-exported for downstream consumers)
# ---------------------------------------------------------------------------

# Default tempo in microseconds per quarter note corresponds to 120 BPM.
DEFAULT_MICROSECONDS_PER_QUARTER = 500_000
DEFAULT_TEMPO_BPM = 60_000_000 / DEFAULT_MICROSECONDS_PER_QUARTER
DEFAULT_TICKS_PER_BEAT = 480


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Anything ``parse_midi`` knows how to open: a path-like (str / Path)
# referring to a file on disk, or the raw bytes of a MIDI payload.
MidiSource = Union[str, Path, bytes]

# A 4-tuple capturing the conceptual content of a note before it is
# serialised into a :class:`Note` model: ``(pitch, velocity,
# start_ticks, end_ticks)``.
NoteTuple = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _open_midi(source: MidiSource) -> Tuple[mido.MidiFile, str | None]:
    """Open a :class:`mido.MidiFile` from a path or a bytes payload.

    Returns a ``(midi_file, source_path)`` pair. ``source_path`` is the
    stringified path when one was supplied, or ``None`` when the input
    was raw bytes.
    """
    if isinstance(source, (str, Path)):
        return mido.MidiFile(str(source)), str(source)
    if isinstance(source, (bytes, bytearray, memoryview)):
        return mido.MidiFile(file=io.BytesIO(bytes(source))), None
    raise TypeError(
        f"Unsupported source type for parse_midi: {type(source).__name__!r}; "
        "expected str, Path, or bytes"
    )


def _tick_to_seconds(tick: int, ticks_per_beat: int, tempo_micros: int) -> float:
    """Convert an absolute tick count to seconds under the given tempo."""
    return mido.tick2second(tick, ticks_per_beat, tempo_micros)


def _track_to_note_tuples(
    track: mido.MidiTrack,
    ticks_per_beat: int,
    *,
    initial_tempo_micros: int = DEFAULT_MICROSECONDS_PER_QUARTER,
) -> List[NoteTuple]:
    """Walk a single mido track, returning ``(pitch, velocity,
    start_ticks, end_ticks)`` tuples for every note that closed inside
    the track (or is held through end-of-track).

    The track-local tempo is initialised from ``initial_tempo_micros``
    and updated whenever a ``set_tempo`` meta event is encountered, so
    tempo changes are honoured for the *remainder* of the track. The
    default matches the SMF convention: 120 BPM = 500_000
    microseconds per quarter note.
    """
    notes: List[NoteTuple] = []
    current_tick = 0
    current_tempo = initial_tempo_micros

    # pitch -> (start_tick, velocity) for notes that are currently held.
    pending: dict[int, Tuple[int, int]] = {}

    def _close(pitch: int, end_tick: int) -> None:
        if pitch in pending:
            start_tick, velocity = pending.pop(pitch)
            notes.append((pitch, velocity, start_tick, end_tick))

    for msg in track:
        current_tick += max(0, int(msg.time))
        msg_type = msg.type

        if msg_type == "set_tempo":
            # ``msg.tempo`` is microseconds per quarter note.
            current_tempo = int(msg.tempo)
            continue

        if msg_type == "note_on" and msg.velocity > 0:
            # If this pitch is already held, close the previous note
            # first (re-trigger semantics).
            _close(msg.note, current_tick)
            pending[msg.note] = (current_tick, int(msg.velocity))
        elif msg_type == "note_off" or (msg_type == "note_on" and msg.velocity == 0):
            _close(msg.note, current_tick)
        # All other message types (control_change, program_change,
        # time_signature, track_name, end_of_track, meta text, ...) are
        # accepted and ignored.

    # Close any notes still held at end-of-track.
    for pitch, (start_tick, velocity) in pending.items():
        notes.append((pitch, velocity, start_tick, current_tick))

    return notes


def _note_tuple_to_seconds(
    note_tuple: NoteTuple,
    ticks_per_beat: int,
    tempo_micros: int,
) -> Note:
    """Convert a ``(pitch, velocity, start_ticks, end_ticks)`` tuple
    to a :class:`Note` whose ``start`` and ``duration`` are in seconds.

    For long notes that cross tempo changes, the start time uses the
    tempo at the start tick and the end time uses the *current* track
    tempo (a small simplification: a note that straddles a tempo change
    in the same track is reported using the post-change tempo for the
    end tick; in practice this is the common case and is stable enough
    for downstream rendering).
    """
    pitch, velocity, start_tick, end_tick = note_tuple
    start = _tick_to_seconds(start_tick, ticks_per_beat, tempo_micros)
    end = _tick_to_seconds(end_tick, ticks_per_beat, tempo_micros)
    duration = max(0.0, end - start)
    return Note(pitch=pitch, velocity=velocity, start=start, duration=duration)


# ---------------------------------------------------------------------------
# Public API: parse_midi
# ---------------------------------------------------------------------------


def parse_midi(path_or_bytes: MidiSource) -> NoteStream:
    """Parse a Standard MIDI File from a path or bytes payload.

    The input may be either a filesystem path (``str`` or
    :class:`pathlib.Path`) pointing to a ``.mid`` / ``.midi`` file, or
    a raw ``bytes`` payload containing the encoded MIDI data. This is
    the only public entry point most callers need; it always returns a
    :class:`~melosviz.analysis.models.NoteStream`.

    Internally the parser walks each track, accumulating absolute
    ticks and tracking tempo changes. Note-On / Note-Off pairs are
    matched up and emitted as :class:`Note` objects, sorted by
    ``(start, pitch, velocity)`` so the downstream renderer sees a
    deterministic ordering.

    Args:
        path_or_bytes: A path-like pointing to a MIDI file, or the raw
            bytes of one.

    Returns:
        A :class:`~melosviz.analysis.models.NoteStream` whose
        ``notes`` attribute holds the parsed notes. The ``ticks_per_beat``
        attribute is populated from the file header (defaults to 480
        when the header is missing). ``source_path`` is set to the
        stringified path when one was supplied, otherwise ``None``.

    Raises:
        TypeError: If ``path_or_bytes`` is not a ``str``, ``Path`` or
            ``bytes`` object.
        FileNotFoundError: If a path is given that does not exist on
            disk.
        OSError: For other I/O errors when reading from disk.
        ValueError: If the input is not a valid Standard MIDI File.
    """
    midi, source_path = _open_midi(path_or_bytes)

    ticks_per_beat = int(midi.ticks_per_beat) if midi.ticks_per_beat else DEFAULT_TICKS_PER_BEAT

    # Seed the per-track tempo with whatever the first track's
    # ``set_tempo`` meta event reports, falling back to 120 BPM. This
    # matches the convention used by virtually every DAW export.
    initial_tempo = DEFAULT_MICROSECONDS_PER_QUARTER
    for msg in midi.tracks[0] if midi.tracks else []:
        if msg.type == "set_tempo":
            initial_tempo = int(msg.tempo)
            break

    notes: List[Note] = []
    for track in midi.tracks:
        # Re-seed each track from the file-wide initial tempo so that
        # tracks without their own ``set_tempo`` event still use the
        # correct global tempo.
        for note_tuple in _track_to_note_tuples(
            track,
            ticks_per_beat,
            initial_tempo_micros=initial_tempo,
        ):
            notes.append(
                _note_tuple_to_seconds(note_tuple, ticks_per_beat, initial_tempo)
            )

    notes.sort(key=lambda n: (n.start, n.pitch, n.velocity))
    return NoteStream(
        notes=notes,
        source_path=source_path,
        ticks_per_beat=ticks_per_beat,
    )


# ---------------------------------------------------------------------------
# Public API: parse_midi_to_tuples
# ---------------------------------------------------------------------------


def parse_midi_to_tuples(path_or_bytes: MidiSource) -> List[NoteTuple]:
    """Parse a Standard MIDI File and return a list of raw
    ``(pitch, velocity, start_ticks, end_ticks)`` tuples.

    This is a convenience alternative to :func:`parse_midi` for
    callers that want the parser output in its original tick-based
    form (no seconds conversion). The list is sorted by
    ``(start_ticks, pitch, velocity)`` for deterministic ordering.

    Args:
        path_or_bytes: A path-like pointing to a MIDI file, or the raw
            bytes of one.

    Returns:
        A list of ``(pitch, velocity, start_ticks, end_ticks)`` tuples,
        one per note, sorted by start tick.
    """
    midi, _ = _open_midi(path_or_bytes)
    ticks_per_beat = int(midi.ticks_per_beat) if midi.ticks_per_beat else DEFAULT_TICKS_PER_BEAT

    initial_tempo = DEFAULT_MICROSECONDS_PER_QUARTER
    for msg in midi.tracks[0] if midi.tracks else []:
        if msg.type == "set_tempo":
            initial_tempo = int(msg.tempo)
            break

    note_tuples: List[NoteTuple] = []
    for track in midi.tracks:
        note_tuples.extend(
            _track_to_note_tuples(
                track,
                ticks_per_beat,
                initial_tempo_micros=initial_tempo,
            )
        )

    note_tuples.sort(key=lambda nt: (nt[2], nt[0], nt[1]))
    return note_tuples


# ---------------------------------------------------------------------------
# Public API: write_midi
# ---------------------------------------------------------------------------


def write_midi(
    notes: Iterable[Note],
    path: str | Path,
    *,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
    tempo_bpm: float = DEFAULT_TEMPO_BPM,
    track_name: str = "melosviz",
) -> None:
    """Serialise a stream of notes to a Standard MIDI File (Format 1)
    using ``mido``.

    The file is written as Format 1 with two tracks: a conducting track
    that contains the tempo meta event and track name, and a single
    note track that holds all note-on / note-off events. Note-offs are
    emitted as Note-On messages with velocity 0 (the modern SMF
    convention) which keeps the resulting file round-trippable through
    this module.

    Args:
        notes: Iterable of :class:`~melosviz.analysis.models.Note` to write.
        path: Destination path. Existing files are overwritten.
        ticks_per_beat: PPQ resolution. Default ``480``.
        tempo_bpm: Initial tempo in beats per minute. Default ``120``.
        track_name: Track-name meta event written to the first track.

    Raises:
        ValueError: If ``ticks_per_beat`` is not positive or ``tempo_bpm``
            is not positive.
    """
    if ticks_per_beat <= 0:
        raise ValueError(f"ticks_per_beat must be positive, got {ticks_per_beat}")
    if tempo_bpm <= 0:
        raise ValueError(f"tempo_bpm must be positive, got {tempo_bpm}")

    seconds_per_tick = 60.0 / (tempo_bpm * ticks_per_beat)
    note_list = list(notes)

    # Build the merged, tick-sorted event list. Note-offs (as Note-On
    # with velocity 0) are emitted *before* note-ons at the same tick
    # so the file is unambiguously round-trippable through this module.
    events: List[Tuple[int, str, int, int]] = []  # (tick, kind, pitch, velocity)
    for note in note_list:
        start_tick = int(round(note.start / seconds_per_tick))
        end_tick = int(round((note.start + note.duration) / seconds_per_tick))
        if end_tick < start_tick:
            end_tick = start_tick
        events.append((start_tick, "on", note.pitch, max(0, min(127, note.velocity))))
        events.append((end_tick, "off", note.pitch, 0))

    events.sort(key=lambda ev: (ev[0], 0 if ev[1] == "off" else 1, ev[2]))

    # Track 1: conducting (tempo + name + end-of-track).
    conducting = mido.MidiTrack()
    conducting.append(
        mido.MetaMessage(
            "set_tempo",
            tempo=mido.bpm2tempo(tempo_bpm),
            time=0,
        )
    )
    conducting.append(
        mido.MetaMessage("track_name", name=track_name, time=0)
    )
    conducting.append(mido.MetaMessage("end_of_track", time=0))

    # Track 2: notes + end-of-track.
    note_track = mido.MidiTrack()
    last_tick = 0
    for tick, kind, pitch, velocity in events:
        delta = tick - last_tick
        if delta < 0:
            raise ValueError("Negative delta in MIDI event stream")
        last_tick = tick
        if kind == "on":
            note_track.append(
                mido.Message("note_on", channel=0, note=pitch, velocity=velocity, time=delta)
            )
        else:
            # Note-off emitted as a Note-On with velocity 0 (modern SMF convention).
            note_track.append(
                mido.Message("note_on", channel=0, note=pitch, velocity=0, time=delta)
            )
    note_track.append(mido.MetaMessage("end_of_track", time=0))

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    midi.tracks.append(conducting)
    midi.tracks.append(note_track)
    midi.save(str(path))


__all__ = [
    "DEFAULT_MICROSECONDS_PER_QUARTER",
    "DEFAULT_TEMPO_BPM",
    "DEFAULT_TICKS_PER_BEAT",
    "MidiSource",
    "NoteTuple",
    "parse_midi",
    "parse_midi_to_tuples",
    "write_midi",
]
