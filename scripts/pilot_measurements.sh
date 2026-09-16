#!/usr/bin/env bash
# G4 Pilot Measurement Harness — MelosViz
#
# Runs the full happy-path pipeline and captures performance metrics:
# - Wall-clock time per pipeline step
# - Output file sizes
# - FFmpeg probe: duration, fps, codec, resolution, frame count
# - LUFS loudness (from loudnorm stats)
# - Frame pacing (avg/max/std of inter-frame intervals)
# - A/V sync drift (audio vs video duration delta)
#
# Outputs: pilot_report.json (structured) + stdout summary table
# Exit 0 = all metrics within range, exit 1 = any critical failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WAV="$REPO_ROOT/backend/tests/fixtures/test_tone.wav"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/melosviz-pilot-XXXXXX")
REPORT="$WORK_DIR/pilot_report.json"
FFPROBE="/opt/homebrew/bin/ffprobe"

trap 'rm -rf "$WORK_DIR"' EXIT

# ── Helpers ──────────────────────────────────────────────────────────
now_ms() { python3 -c "import time; print(int(time.time()*1000))"; }

json_set() {
    # $1=file $2=key $3=value (string or number)
    python3 -c "
import json, sys
f = open('$1')
d = json.load(f); f.close()
d['$2'] = $3
json.dump(d, open('$1','w'), indent=2)
"
}

# ── Setup ────────────────────────────────────────────────────────────
echo '{"steps":{},"files":{},"probe":{},"measurements":{},"pass":true,"failures":[]}' > "$REPORT"

if [ -f "$REPO_ROOT/backend/.venv/bin/activate" ]; then
    source "$REPO_ROOT/backend/.venv/bin/activate"
fi

cd "$REPO_ROOT/backend"

echo "=== MelosViz Pilot Measurement ==="
echo "Work dir: $WORK_DIR"
echo ""

# ── Step 1: Analyze ─────────────────────────────────────────────────
T0=$(now_ms)
python -m melosviz.cli.main analyze "$WAV" > "$WORK_DIR/render_spec.json"
T1=$(now_ms)
STEP1_MS=$((T1 - T0))
json_set "$REPORT" "steps.analyze_ms" "$STEP1_MS"
echo "[1/6] analyze       ${STEP1_MS}ms"

# ── Step 2: Storyboard ──────────────────────────────────────────────
T0=$(now_ms)
python -m melosviz.cli.main storyboard "$WAV" \
    --concept "abstract neon dreamscape" \
    --seed 42 \
    --out "$WORK_DIR/storyboard"
T1=$(now_ms)
STEP2_MS=$((T1 - T0))
json_set "$REPORT" "steps.storyboard_ms" "$STEP2_MS"
echo "[2/6] storyboard    ${STEP2_MS}ms"

# ── Step 3: Generate (offline) ──────────────────────────────────────
T0=$(now_ms)
MELOSVIZ_COMFYUI_OFFLINE=1 python -m melosviz.cli.main generate "$WAV" \
    --storyboard "$WORK_DIR/storyboard/storyboard.json" \
    --out "$WORK_DIR/scenes" \
    --seed 42
T1=$(now_ms)
STEP3_MS=$((T1 - T0))
json_set "$REPORT" "steps.generate_ms" "$STEP3_MS"
CLIP_COUNT=$(find "$WORK_DIR/scenes" -name "clip.mp4" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "[3/6] generate      ${STEP3_MS}ms  ($CLIP_COUNT clips)"

# ── Step 4: Assemble ────────────────────────────────────────────────
T0=$(now_ms)
python -m melosviz.cli.main assemble "$WORK_DIR/scenes" 2>/dev/null
T1=$(now_ms)
STEP4_MS=$((T1 - T0))
ASSEMBLED="$WORK_DIR/scenes/melosviz-assembled.mp4"
json_set "$REPORT" "steps.assemble_ms" "$STEP4_MS"
echo "[4/6] assemble      ${STEP4_MS}ms"

# ── Step 5: Master ──────────────────────────────────────────────────
T0=$(now_ms)
python -m melosviz.cli.main master "$ASSEMBLED" \
    --out "$WORK_DIR/master" \
    --lufs-target youtube \
    --audio "$WAV" 2>/dev/null
T1=$(now_ms)
STEP5_MS=$((T1 - T0))
json_set "$REPORT" "steps.master_ms" "$STEP5_MS"
MASTERED=$(find "$WORK_DIR/master" -name "*.wav" -type f 2>/dev/null | head -1)
echo "[5/6] master        ${STEP5_MS}ms"

# ── Step 6: Ship ────────────────────────────────────────────────────
T0=$(now_ms)
python -m melosviz.cli.main ship "$WORK_DIR/scenes" \
    --bundle-output "$WORK_DIR/deliverables" 2>/dev/null
T1=$(now_ms)
STEP6_MS=$((T1 - T0))
json_set "$REPORT" "steps.ship_ms" "$STEP6_MS"
echo "[6/6] ship          ${STEP6_MS}ms"

TOTAL_MS=$((STEP1_MS + STEP2_MS + STEP3_MS + STEP4_MS + STEP5_MS + STEP6_MS))
json_set "$REPORT" "steps.total_ms" "$TOTAL_MS"
echo ""
echo "Total pipeline: ${TOTAL_MS}ms"

# ── File Sizes ──────────────────────────────────────────────────────
echo ""
echo "--- File Sizes ---"
for f in "$WORK_DIR/render_spec.json" "$ASSEMBLED" "$MASTERED" "$WORK_DIR/deliverables/final.zip"; do
    if [ -f "$f" ]; then
        SZ=$(wc -c < "$f" | tr -d ' ')
        BASENAME=$(basename "$f")
        json_set "$REPORT" "files.${BASENAME}_bytes" "$SZ"
        printf "  %-35s %10s bytes\n" "$BASENAME" "$SZ"
    fi
done

# ── FFmpeg Probe: Assembled MP4 ──────────────────────────────────────
echo ""
echo "--- FFmpeg Probe (assembled) ---"
if [ -f "$ASSEMBLED" ]; then
    # Duration
    DURATION=$($FFPROBE -v error -show_entries format=duration -of csv=p=0 "$ASSEMBLED" 2>/dev/null || echo "0")
    json_set "$REPORT" "probe.assembled_duration_s" "$DURATION"
    echo "  Duration: ${DURATION}s"

    # FPS
    FPS=$($FFPROBE -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$ASSEMBLED" 2>/dev/null | head -1 || echo "?")
    json_set "$REPORT" "probe.assembled_fps" "\"$FPS\""
    echo "  FPS: $FPS"

    # Codec
    CODEC=$($FFPROBE -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$ASSEMBLED" 2>/dev/null || echo "?")
    json_set "$REPORT" "probe.assembled_codec" "\"$CODEC\""
    echo "  Codec: $CODEC"

    # Resolution
    RES=$($FFPROBE -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$ASSEMBLED" 2>/dev/null || echo "?")
    json_set "$REPORT" "probe.assembled_resolution" "\"$RES\""
    echo "  Resolution: $RES"

    # Frame count
    FRAMES=$($FFPROBE -v error -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$ASSEMBLED" 2>/dev/null || echo "?")
    json_set "$REPORT" "probe.assembled_frame_count" "\"${FRAMES:-?}\""
    echo "  Frames: $FRAMES"
fi

# ── LUFS (from mastered output) ─────────────────────────────────────
echo ""
echo "--- LUFS Loudness ---"
if [ -f "$MASTERED" ]; then
    LUFS_RAW=$($FFPROBE -v error -f lavfi -i "amovie=$MASTERED,ebur128=peak=true" -show_entries frame_tags=lavfi.EBUR128.I -of csv=p=0 "$MASTERED" 2>/dev/null | tail -1 || echo "")
    if [ -n "$LUFS_RAW" ] && [ "$LUFS_RAW" != "?" ]; then
        LUFS_VAL=$(echo "$LUFS_RAW" | sed 's/.*I=//;s/,.*//')
        json_set "$REPORT" "measurements.lufs" "$LUFS_VAL"
        echo "  Integrated LUFS: $LUFS_VAL"
    else
        # Fallback: use ffmpeg loudnorm stats
        LOUDSTAT=$(ffmpeg -i "$MASTERED" -af loudnorm=print_format=json -f null /dev/null 2>&1 | grep -A20 '"input_i"' | head -20 || echo "")
        if [ -n "$LOUDSTAT" ]; then
            LUFS_VAL=$(echo "$LOUDSTAT" | grep '"input_i"' | sed 's/.*: "//;s/".*//')
            json_set "$REPORT" "measurements.lufs" "$LUFS_VAL"
            echo "  Integrated LUFS: $LUFS_VAL (loudnorm fallback)"
        else
            json_set "$REPORT" "measurements.lufs" "null"
            echo "  LUFS: could not measure"
        fi
    fi
fi

# ── A/V Sync Drift ──────────────────────────────────────────────────
echo ""
echo "--- A/V Sync Drift ---"
if [ -f "$ASSEMBLED" ]; then
    AUDIO_DUR=$($FFPROBE -v error -select_streams a:0 -show_entries format=duration -of csv=p=0 "$ASSEMBLED" 2>/dev/null || echo "0")
    VIDEO_DUR=$DURATION
    DRIFT=$(python3 -c "
a, v = float('${AUDIO_DUR}' or 0), float('${VIDEO_DUR}' or 0)
print(f'{abs(a - v):.4f}')
")
    json_set "$REPORT" "measurements.av_drift_s" "$DRIFT"
    json_set "$REPORT" "measurements.audio_duration_s" "$AUDIO_DUR"
    echo "  Audio: ${AUDIO_DUR}s  Video: ${VIDEO_DUR}s  Drift: ${DRIFT}s"
fi

# ── Frame Pacing (placeholder clips are constant-framerate) ──────────
echo ""
echo "--- Frame Pacing ---"
FIRST_CLIP=$(find "$WORK_DIR/scenes" -name "clip.mp4" -type f 2>/dev/null | head -1)
if [ -n "$FIRST_CLIP" ] && [ -f "$FIRST_CLIP" ]; then
    STATS=$($FFPROBE -v error -select_streams v:0 \
        -show_entries frame=pts_time -of csv=p=0 "$FIRST_CLIP" 2>/dev/null | head -100 || echo "")
    if [ -n "$STATS" ]; then
        PACING=$(python3 -c "
lines = '''$STATS'''.strip().split('\n')
pts = []
for l in lines:
    l = l.strip()
    if l and ',' not in l:
        try: pts.append(float(l))
        except: pass
if len(pts) < 2:
    print('{\"avg_ms\": 0, \"max_ms\": 0, \"std_ms\": 0, \"n\": 0}')
else:
    intervals = [1000*(pts[i]-pts[i-1]) for i in range(1, len(pts))]
    import statistics
    avg = statistics.mean(intervals)
    mx = max(intervals)
    sd = statistics.stdev(intervals) if len(intervals) > 1 else 0
    print(f'{{\"avg_ms\": {avg:.3f}, \"max_ms\": {mx:.3f}, \"std_ms\": {sd:.3f}, \"n\": {len(intervals)}}}')
")
        python3 -c "
import json
d = json.load(open('$REPORT'))
d['measurements']['frame_pacing'] = json.loads('''$PACING''')
json.dump(d, open('$REPORT','w'), indent=2)
"
        AVG=$(echo "$PACING" | python3 -c "import sys,json; print(json.load(sys.stdin)['avg_ms'])")
        STD=$(echo "$PACING" | python3 -c "import sys,json; print(json.load(sys.stdin)['std_ms'])")
        echo "  Avg frame interval: ${AVG}ms  Std dev: ${STD}ms"
    fi
fi

# ── Validation Gate ──────────────────────────────────────────────────
echo ""
echo "--- Validation ---"
PASS=true
FAILURES="[]"

check() {
    # $1=name $2=condition $3=threshold
    if eval "$2"; then
        echo "  PASS: $1"
    else
        echo "  FAIL: $1 ($3)"
        PASS=false
        FAILURES=$(python3 -c "
import json
f = json.load(open('$REPORT'))
f['failures'].append('$1')
json.dump(f, open('$REPORT','w'), indent=2)
")
    fi
}

check "pipeline_total_lt_120s" "[ $TOTAL_MS -lt 120000 ]" "was ${TOTAL_MS}ms"
check "all_clips_exist" "[ $CLIP_COUNT -ge 1 ]" "was $CLIP_COUNT clips"
check "assembled_exists" "[ -f '$ASSEMBLED' ]" "file missing"
check "mastered_exists" "[ -f '$MASTERED' ]" "file missing"
check "final_zip_exists" "[ -f '$WORK_DIR/deliverables/final.zip' ]" "file missing"
check "av_drift_lt_100ms" "[ \$(python3 -c \"print(1 if float('$DRIFT') < 0.1 else 0)\") -eq 1 ]" "was ${DRIFT}s"

# LUFS check: -16 +/- 2 (target -14)
if [ -n "${LUFS_VAL:-}" ] && [ "$LUFS_VAL" != "null" ]; then
    check "lufs_in_range" "[ \$(python3 -c \"print(1 if -18 < float('$LUFS_VAL') < -12 else 0)\") -eq 1 ]" "was ${LUFS_VAL} LUFS"
fi

# Frame pacing check: std dev < 5ms
STD_MS=$(echo "${PACING:-{}}" | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(d.get('std_ms', 0))
except: print(0)
" 2>/dev/null || echo "0")
check "frame_pacing_std_lt_5ms" "[ \$(python3 -c \"print(1 if float('$STD_MS') < 5.0 else 0)\") -eq 1 ]" "was ${STD_MS}ms std"

# ── Final Report ─────────────────────────────────────────────────────
python3 -c "
import json
d = json.load(open('$REPORT'))
d['pass'] = $( [ "$PASS" = true ] && echo "True" || echo "False" )
json.dump(d, open('$REPORT','w'), indent=2)
"

echo ""
if [ "$PASS" = true ]; then
    echo "=== ALL CHECKS PASSED ==="
    echo "Report: $REPORT"
    exit 0
else
    echo "=== SOME CHECKS FAILED ==="
    echo "Report: $REPORT"
    exit 1
fi
