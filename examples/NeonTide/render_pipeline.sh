#!/usr/bin/env bash
# render_pipeline.sh — end-to-end MelosViz pipeline for the NeonTide example
# Run from inside examples/NeonTide/ or pass --from <dir>.

set -euo pipefail

# --- input discovery ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LRC="$SCRIPT_DIR/song.lrc"
MOOD_BOARD="$SCRIPT_DIR/moodboard.json"
OUTPUT="$SCRIPT_DIR/output"

WAV="${TRACK:-}"
CONCEPT="${CONCEPT:-neon noir underwater city, bioluminescent, 35mm grain}"
PALETTE="${PALETTE:-#0d0d10 #ff2bd6 #22d3ee #c084fc #f0f0f8}"
BPM="${BPM:-124}"
ASPECT_RATIO="${ASPECT_RATIO:-club_9x16}"
LUFS_TARGET="${LUFS_TARGET:-club_pa}"
EXPORT_STEMS="${EXPORT_STEMS:-1}"
OFFLINE="${MELOSVIZ_COMFYUI_OFFLINE:-1}"

if [[ -z "$WAV" ]]; then
  for candidate in ../input/track.wav ../input/NeonTide.wav ./track.wav ../track.wav; do
    if [[ -f "$candidate" ]]; then
      WAV="$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")"
      break
    fi
  done
fi

if [[ -z "$WAV" || ! -f "$WAV" ]]; then
  echo "No input wav found — set TRACK=/path/to/track.wav" >&2
  exit 1
fi

mkdir -p "$OUTPUT"

VIZ() { (cd "$SCRIPT_DIR/../../backend" && PYTHONPATH=src python3 -m melosviz.cli.main "$@"); }

echo "=== 1/6  viz analyze ==="
VIZ analyze "$WAV" --out "$OUTPUT/spec.json"

echo "=== 2/6  viz storyboard ==="
VIZ storyboard "$WAV" \
  --concept "$CONCEPT" \
  --bpm "$BPM" \
  --palette "$PALETTE" \
  --lyrics "$LRC" \
  --mood-board "$MOOD_BOARD" \
  --aspect-ratio "$ASPECT_RATIO" \
  --continuity-character "young woman with short silver hair, neon trenchcoat, hand-mirror tattoo on left forearm" \
  --continuity-environment "bioluminescent underwater city of glass and coral, neon sign reflections on water, ambient particulate matter" \
  --out "$OUTPUT"

echo "=== 3/6  viz generate ==="
if [[ "$OFFLINE" == "1" ]]; then
  MELOSVIZ_COMFYUI_OFFLINE=1 VIZ generate "$WAV" \
    --storyboard "$OUTPUT/storyboard.json" \
    --out "$OUTPUT/generate"
else
  VIZ generate "$WAV" \
    --storyboard "$OUTPUT/storyboard.json" \
    --out "$OUTPUT/generate"
fi

echo "=== 4/6  viz assemble ==="
VIZ assemble "$OUTPUT/generate" --out "$OUTPUT/rough.mp4"

echo "=== 5/6  viz master ==="
MASTER_ARGS=( --out "$OUTPUT/master" --lufs-target "$LUFS_TARGET" --audio "$WAV" )
[[ "$EXPORT_STEMS" == "1" ]] && MASTER_ARGS+=( --export-stems )
VIZ master "$OUTPUT/rough.mp4" "${MASTER_ARGS[@]}"

echo "=== 6/6  viz ship ==="
VIZ ship "$OUTPUT/master" --out "$OUTPUT/final.zip"

echo
echo "DONE. Deliverable: $OUTPUT/final.zip"