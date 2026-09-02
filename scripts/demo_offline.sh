#!/usr/bin/env bash
# scripts/demo_offline.sh — full offline demo of Melosviz.
#
# Runs the entire pipeline (storyboard -> generate -> ship -> VJ export)
# with no GPU, no ComfyUI, no network. Produces real artifacts you can
# inspect under $OUT_DIR (default: /tmp/melosviz-demo).
#
# Usage:
#   ./scripts/demo_offline.sh                # full demo
#   OUT_DIR=./my-demo ./scripts/demo_offline.sh
#
# Prerequisites: `viz` CLI installed in the active venv
# (run `make viz-install` first).
set -euo pipefail

OUT_DIR="${OUT_DIR:-/tmp/melosviz-demo}"
TRACK="$OUT_DIR/track.wav"
STORYBOARD="$OUT_DIR/storyboard.json"
GEN="$OUT_DIR/generate"

# Step 0 — clean slate
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# Step 1 — synthesize a 6-second silent mono WAV (no audio tools needed)
python3 - <<'PY'
import os, sys, wave
out_dir = os.environ.get("OUT_DIR", "/tmp/melosviz-demo")
os.makedirs(out_dir, exist_ok=True)
with wave.open(os.path.join(out_dir, "track.wav"), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    w.writeframes(b"\x00\x00" * 22050 * 6)
print(f"  wrote {os.path.join(out_dir, 'track.wav')}")
PY

# Step 2 — storyboard: concept -> per-scene JSON plan
echo "[1/3] viz storyboard"
MELOSVIZ_COMFYUI_OFFLINE=1 \
  viz storyboard "$TRACK" \
    --concept "neon city after rain, cinematic dolly shots" \
    --bpm 110 \
    --out "$STORYBOARD"

# Step 3 — generate: per-scene render plans + provenance sidecars
# (offline mode writes workflow.json / c4d_render_plan.json per scene
# instead of actually calling ComfyUI / C4D)
echo "[2/3] viz generate"
MELOSVIZ_COMFYUI_OFFLINE=1 \
  viz generate "$TRACK" \
    --storyboard "$STORYBOARD" \
    --out "$GEN"

# Step 4 — ship: deterministic ZIP bundle with manifest, SHA-256SUMS,
# MERMAID.md, and VJ export (SVG timeline + Lottie cues per scene)
echo "[3/3] viz ship"
MELOSVIZ_COMFYUI_OFFLINE=1 \
  viz ship "$GEN" \
    --bundle-name final.zip

# Step 5 — print summary of artifacts produced
echo
echo "=== demo complete ==="
echo "out dir: $OUT_DIR"
echo
echo "Top-level files:"
ls -1 "$OUT_DIR"
echo
echo "Generate output:"
find "$GEN" -maxdepth 2 -type d | sort | head -20
echo
echo "Bundle contents (first 25 lines):"
unzip -l "$GEN/final.zip" | head -25