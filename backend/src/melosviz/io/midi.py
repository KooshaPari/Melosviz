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


def _build_tempo_map(
    track: mido.MidiTrack,
    *,
    initial_tempo_micros: int = DEFAULT_MICROSECONDS_PER_QUARTER,
) -> List[Tuple[int, int]]:
    """Walk a track and return a sorted ``(absolute_tick, tempo_micros)`` map.

    The first entry is always ``(0, initial_tempo_micros)``; subsequent
    entries record every ``set_tempo`` meta event in tick order. The
    list is used by :func:`_tick_to_seconds` to convert absolute tick
    positions to seconds, honouring mid-track tempo changes.
    """
    tempo_map: List[Tuple[int, int]] = [(0, int(initial_tempo_micros))]
    current_tick = 0
    current_tempo = int(initial_tempo_micros)
    for msg in track:
        current_tick += max(0, int(msg.time))
        if msg.type == "set_tempo":
            new_tempo = int(msg.tempo)
            if new_tempo > 0 and new_tempo != current_tempo:
                tempo_map.append((current_tick, new_tempo))
                current_tempo = new_tempo
    return tempo_map


def _absolute_time_at_tick(
    tick: int, ticks_per_beat: int, tempo_map: List[Tuple[int, int]]
) -> float:
    """Compute the cumulative time in seconds at ``tick``.

    Tempo changes are recorded with their *change* tick; the change
    applies to ticks *strictly greater* than that tick. So an event at
    exactly the change tick still uses the previous tempo, and the
    cumulative time at the change tick is the time using the previous
    tempo only.
    """
    seconds = 0.0
    prev_tick = 0
    prev_tempo = tempo_map[0][1]
    # Skip the (0, initial) entry — its tick is 0 and the region
    # before it is empty.
    for t, tempo in tempo_map[1:]:
        if t > tick:
            break
        seconds += (t - prev_tick) * prev_tempo / 1_000_000.0 / ticks_per_beat
        prev_tick = t
        prev_tempo = tempo
    seconds += (tick - prev_tick) * prev_tempo / 1_000_000.0 / ticks_per_beat
    return seconds


def _tempo_at_tick(tick: int, tempo_map: List[Tuple[int, int]]) -> int:
    """Return the tempo (microseconds per quarter) in effect at ``tick``.

    A change recorded at tick ``T`` is taken to be in effect at
    ``T`` itself: events that co-occur with a ``set_tempo`` message in
    the file see the new tempo. This matches the on-the-wire
    behaviour of every DAW that emits a ``set_tempo`` immediately
    before a note on the same delta.
    """
    current_tempo = tempo_map[0][1]
    for t, tempo in tempo_map:
        if t <= tick:
            current_tempo = tempo
        else:
            break
    return current_tempo


def _track_to_note_tuples(
    track: mido.MidiTrack,
    ticks_per_beat: int,
    *,
    initial_tempo_micros: int = DEFAULT_MICROSECONDS_PER_QUARTER,
) -> List[NoteTuple]:
    """Walk a single mido track, returning ``(pitch, velocity,
    start_ticks, end_ticks)`` tuples for every note that closed inside
    the track (or is held through end-of-track).

    The tick positions are stored in the file's native tick units; the
    caller is responsible for converting them to seconds with a tempo
    map (see :func:`_tick_to_seconds_with_map`).
    """
    notes: List[NoteTuple] = []
    current_tick = 0

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
            # Tempo changes are recorded in the tempo map (built once
            # by the caller) and have no effect on tick accumulation.
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
    tempo_map: List[Tuple[int, int]],
) -> Note:
    """Convert a ``(pitch, velocity, start_ticks, end_ticks)`` tuple
    to a :class:`Note` whose ``start`` and ``duration`` are in seconds.

    ``start`` is the cumulative time at ``start_tick`` (accounting for
    tempo changes earlier on the timeline). ``duration`` is computed
    using the tempo in effect at the *start* of the note, so a tempo
    change during a held note does not retroactively shrink it.
    """
    pitch, velocity, start_tick, end_tick = note_tuple
    start = _absolute_time_at_tick(start_tick, ticks_per_beat, tempo_map)
    tempo_at_start = _tempo_at_tick(start_tick, tempo_map)
    duration = max(
        0.0,
        (end_tick - start_tick) * tempo_at_start / 1_000_000.0 / ticks_per_beat,
    )
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
        # Build a per-track tempo map so that tempo changes mid-track
        # (and any global ``set_tempo`` in the first track) are
        # honoured when converting note tuples to seconds.
        tempo_map = _build_tempo_map(
            track, initial_tempo_micros=initial_tempo
        )
        for note_tuple in _track_to_note_tuples(
            track,
            ticks_per_beat,
            initial_tempo_micros=initial_tempo,
        ):
            notes.append(
                _note_tuple_to_seconds(note_tuple, ticks_per_beat, tempo_map)
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
