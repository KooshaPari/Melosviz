#!/usr/bin/env bash
# Run the full MelosViz studio pipeline against the docker-compose.dev stack.
#
# Usage:
#   deploy/scripts/run_pipeline_dev.sh /path/to/track.wav [out_dir]
#
# Environment overrides (all optional):
#   MELOSVIZ_COMFYUI_URL   — default http://127.0.0.1:8188
#   MELOSVIZ_C4D_URL       — default http://127.0.0.1:8190
#   MELOSVIZ_BRIDGE_URL    — default http://127.0.0.1:8787
#   MELOSVIZ_CONCEPT       — concept prompt for the LLM director
#   MELOSVIZ_BPM           — BPM (auto-detected if unset)
#   MELOSVIZ_PALETTE       — space-separated hex colours (default "#0d0d10 #ff2bd6 #22d3ee")
#   MELOSVIZ_LYRICS        — path to .lrc (optional)
#   MELOSVIZ_ASPECT_RATIO  — aspect-ratio preset (default youtube_16x9_1080p)
#   MELOSVIZ_LUFS_TARGET   — mastering target (default youtube)
#   MELOSVIZ_EXPORT_STEMS  — 1 to export audio stems (default 0)

set -euo pipefail

WAV="${1:?path to a .wav file is required}"
OUT_DIR="${2:-./out_$(date +%s)}"

COMFYUI_URL="${MELOSVIZ_COMFYUI_URL:-http://127.0.0.1:8188}"
C4D_URL="${MELOSVIZ_C4D_URL:-http://127.0.0.1:8190}"
BRIDGE_URL="${MELOSVIZ_BRIDGE_URL:-http://127.0.0.1:8787}"
CONCEPT="${MELOSVIZ_CONCEPT:-neon noir: bioluminescent underwater city at dusk, dancer becoming the light}"
BPM="${MELOSVIZ_BPM:-}"
PALETTE="${MELOSVIZ_PALETTE:-#0d0d10 #ff2bd6 #22d3ee}"
LYRICS_ARG=""
if [[ -n "${MELOSVIZ_LYRICS:-}" ]]; then
  LYRICS_ARG="--lyrics ${MELOSVIZ_LYRICS}"
fi
ASPECT_RATIO="${MELOSVIZ_ASPECT_RATIO:-youtube_16x9_1080p}"
LUFS_TARGET="${MELOSVIZ_LUFS_TARGET:-youtube}"
LUFS_ARG="--lufs-target ${LUFS_TARGET}"
STEMS_ARG=""
if [[ "${MELOSVIZ_EXPORT_STEMS:-0}" == "1" ]]; then
  STEMS_ARG="--export-stems"
fi
BPM_ARG=""
if [[ -n "${BPM}" ]]; then
  BPM_ARG="--bpm ${BPM}"
fi

PYTHONPATH=backend/src

echo "==> [1/5] storyboard"
mkdir -p "${OUT_DIR}"
python3 -m melosviz.cli.main storyboard "${WAV}" \
  --concept "${CONCEPT}" \
  ${BPM_ARG} \
  --palette "${PALETTE}" \
  ${LYRICS_ARG} \
  --aspect-ratio "${ASPECT_RATIO}" \
  --out "${OUT_DIR}/storyboard.json"

echo "==> [2/5] generate (ComfyUI at ${COMFYUI_URL}, C4D stub at ${C4D_URL})"
python3 -m melosviz.cli.main generate "${WAV}" \
  --storyboard "${OUT_DIR}/storyboard.json" \
  --out "${OUT_DIR}/generate"

echo "==> [3/5] assemble"
python3 -m melosviz.cli.main assemble "${OUT_DIR}/generate"

echo "==> [4/5] master"
python3 -m melosviz.cli.main master "${OUT_DIR}/generate/assembly/assembly_plan.json" \
  --out "${OUT_DIR}/master" \
  --audio "${WAV}" \
  ${LUFS_ARG} ${STEMS_ARG}

echo "==> [5/5] ship"
python3 -m melosviz.cli.main ship "${OUT_DIR}/master"

echo
echo "Pipeline complete. Artifacts:"
echo "  storyboard  : ${OUT_DIR}/storyboard.json"
echo "  per-scene   : ${OUT_DIR}/generate/{comfyui_image,comfyui_video,c4d_3d,unreal_cinematic,aftereffects_compositing,motion_graphics_beat_sync,procedural_3d_animation,generative_asset}/scene_*/"
echo "  assembly    : ${OUT_DIR}/generate/assembly/assembly_plan.json"
echo "  master      : ${OUT_DIR}/master/{master_plan.json,audio_master.wav,stems/,deliverables/manifest.json}"
echo "  final       : ${OUT_DIR}/master/final.zip"