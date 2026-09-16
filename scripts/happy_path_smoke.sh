#!/usr/bin/env bash
# End-to-end happy-path smoke test for MelosViz.
#
# Exercises the full pipeline in offline mode (no ComfyUI / Blender / DaVinci
# required — only Python + FFmpeg):
#
#   1. viz analyze  → RenderSpec JSON
#   2. viz storyboard → storyboard JSON
#   3. viz generate (offline) → per-scene placeholder MP4 clips
#   4. viz assemble → assembled MP4
#   5. viz master → loudness-normalized master
#   6. viz ship → final.zip deliverables
#
# Usage:
#   bash scripts/happy_path_smoke.sh
#
# Exit code 0 = all steps passed.  Non-zero = first failing step.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WAV="$REPO_ROOT/backend/tests/fixtures/test_tone.wav"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/melosviz-smoke-XXXXXX")

trap 'rm -rf "$WORK_DIR"' EXIT

echo "=== MelosViz Happy Path Smoke Test ==="
echo "Working dir: $WORK_DIR"
echo ""

# Ensure venv is activated if present
if [ -f "$REPO_ROOT/backend/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$REPO_ROOT/backend/.venv/bin/activate"
fi

# ── Step 1: Analyze ──────────────────────────────────────────────────
echo "[1/6] viz analyze ..."
python -m melosviz.cli.main analyze "$WAV" > "$WORK_DIR/render_spec.json"
python -c "
import json, sys
d = json.load(open('$WORK_DIR/render_spec.json'))
assert 'metadata' in d, 'missing metadata'
assert d['metadata'].get('duration', 0) > 0, 'zero duration'
print(f'  OK: {d[\"metadata\"][\"duration\"]:.1f}s, bpm={d[\"metadata\"].get(\"estimated_bpm\", \"?\")}')
"

# ── Step 2: Storyboard ──────────────────────────────────────────────
echo "[2/6] viz storyboard ..."
python -m melosviz.cli.main storyboard "$WAV" \
    --concept "abstract neon dreamscape" \
    --seed 42 \
    --out "$WORK_DIR/storyboard"
python -c "
import json, sys
sb = json.load(open('$WORK_DIR/storyboard/storyboard.json'))
scenes = sb.get('scenes', [])
assert len(scenes) >= 2, f'expected >=2 scenes, got {len(scenes)}'
print(f'  OK: {len(scenes)} scenes')
"

# ── Step 3: Generate (offline) ──────────────────────────────────────
echo "[3/6] viz generate (offline) ..."
MELOSVIZ_COMFYUI_OFFLINE=1 python -m melosviz.cli.main generate "$WAV" \
    --storyboard "$WORK_DIR/storyboard/storyboard.json" \
    --out "$WORK_DIR/scenes" \
    --seed 42
CLIP_COUNT=$(find "$WORK_DIR/scenes" -name "clip.mp4" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "  OK: $CLIP_COUNT placeholder clips"
if [ "$CLIP_COUNT" -lt 1 ]; then
    echo "  FAIL: no clips generated"
    exit 1
fi

# ── Step 4: Assemble ────────────────────────────────────────────────
echo "[4/6] viz assemble ..."
python -m melosviz.cli.main assemble "$WORK_DIR/scenes" 2>&1 | head -5
# The assembled file lands in the root of scenes/ as melosviz-assembled.mp4
if [ -f "$WORK_DIR/scenes/melosviz-assembled.mp4" ]; then
    DURATION=$(/opt/homebrew/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK_DIR/scenes/melosviz-assembled.mp4" 2>/dev/null || echo "?")
    echo "  OK: assembled MP4 (${DURATION}s)"
else
    echo "  FAIL: assembled MP4 not found"
    exit 1
fi

# ── Step 5: Master ──────────────────────────────────────────────────
echo "[5/6] viz master ..."
python -m melosviz.cli.main master \
    "$WORK_DIR/scenes/melosviz-assembled.mp4" \
    --out "$WORK_DIR/master" \
    --lufs-target youtube \
    --audio "$WAV" 2>&1 | head -5
if [ -d "$WORK_DIR/master" ]; then
    echo "  OK: master directory created"
else
    echo "  FAIL: master directory not found"
    exit 1
fi

# ── Step 6: Ship ────────────────────────────────────────────────────
echo "[6/6] viz ship ..."
python -m melosviz.cli.main ship "$WORK_DIR/scenes" \
    --bundle-output "$WORK_DIR/deliverables" 2>&1 | head -5
if [ -f "$WORK_DIR/deliverables/final.zip" ]; then
    SIZE=$(wc -c < "$WORK_DIR/deliverables/final.zip" | tr -d ' ')
    echo "  OK: final.zip (${SIZE} bytes)"
else
    echo "  FAIL: final.zip not found"
    exit 1
fi

echo ""
echo "=== ALL 6 STEPS PASSED ==="
echo "Working dir: $WORK_DIR"
