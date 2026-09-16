# M.2 — Happy Path Design: End-to-End Music Video Pipeline

**Date:** 2026-09-16
**Author:** Jcode (automated agent)
**Status:** DRAFT — ready for M.3 implementation
**Depends on:** M.1 audit (completed), SPEC.md (MV-FR-54), WBS.md (Phase 1 tasks 11-25)

---

## 1. What Is the Happy Path?

The shortest path from a WAV file to a playable MP4 video, beat-synced, multi-scene, 3-5 minutes. No manual tool setup. No missing adapters. Offline-capable (no ComfyUI/C4D/UE required for smoke test).

```
WAV in  ──> analyze ──> storyboard ──> generate ──> assemble ──> master ──> ship
                  │              │              │             │           │
                  v              v              v             v           v
            RenderSpec.json  storyboard.json  scene clips   rough.mp4   final.zip
```

---

## 2. The Six Steps

### Step 1: `viz analyze <song.wav>`

**Input:** WAV file (any sample rate, any length)
**Output:** `RenderSpec v2` JSON file

**What happens:**
- Python MIR analysis (`backend/src/melosviz/analysis/audio.py`) extracts:
  - BPM, key, mode (librosa)
  - Structural sections (intro/verse/chorus/drop/etc.)
  - Dense keyframes at 10 Hz (stems, spectrum, energy)
  - Mood vector trajectory
  - Timeline events (beats, downbeats, onsets)
- Output serialized as `RenderSpec` Pydantic model (`analysis/models.py:287`)
- Rust MIR fast-path skipped (workspace empty; Python fallback is the only path)

**CLI:**
```bash
viz analyze song.wav --out render_spec.json
```

**Verification:**
- `render_spec.json` is valid JSON
- Contains `bpm`, `key`, `sections`, `dense_keyframes`, `palette` fields
- `python -c "from melosviz.analysis.models import RenderSpec; RenderSpec.model_validate_json(open('render_spec.json').read())"` exits 0

---

### Step 2: `viz storyboard --spec render_spec.json --concept "abstract neon dreamscape"`

**Input:** RenderSpec JSON + text concept prompt
**Output:** `storyboard.json` (5-scene shot list)

**What happens:**
- Director LLM agent (`backend/src/melosviz/llm/director.py`) reads:
  - MIR summary (BPM, key, mood, sections)
  - Concept prompt
- Generates 5 scenes, each with:
  - Scene type (mapped to adapter key)
  - Duration (aligned to MIR sections)
  - Camera movement, palette, composition notes
  - Beat-synced shot boundaries (snap to nearest beat)
- Enforces variation: no two adjacent scenes share the same camera/motion/palette
- Deterministic mode: same WAV + same seed → byte-identical output

**CLI:**
```bash
viz storyboard --spec render_spec.json --concept "abstract neon dreamscape" --seed 42 --out storyboard.json
```

**Verification:**
- `storyboard.json` contains exactly 5 scenes
- No two adjacent scenes have identical `camera_movement` + `palette`
- Shot boundaries align to beats within 50ms tolerance

---

### Step 3: `viz generate --storyboard storyboard.json --out scenes/`

**Input:** Storyboard JSON
**Output:** Per-scene MP4 clips in `scenes/` directory

**What happens:**
- Conductor (`backend/src/melosviz/conductor/orchestrator.py`) reads storyboard
- For each scene, routes to the correct adapter via `ADAPTER_REGISTRY`:
  - `comfyui_image` / `comfyui_video` → `ComfyUIAdapter`
  - `generative_asset` → `ComfyUIAdapter`
  - `procedural_3d_animation` → Blender (if available)
  - `video_export` → FFmpeg fallback (always available)
- **Offline mode** (`MELOSVIZ_COMFYUI_OFFLINE=1`): generates placeholder clips via FFmpeg (colored bars + beat-synced flash)
- Each adapter produces a per-scene MP4

**CLI:**
```bash
# Online (requires ComfyUI server running)
viz generate --storyboard storyboard.json --out scenes/

# Offline (no tools required, FFmpeg placeholders)
MELOSVIZ_COMFYUI_OFFLINE=1 viz generate --storyboard storyboard.json --out scenes/
```

**Verification:**
- `scenes/` contains 5 MP4 files (one per scene)
- Each MP4 has duration matching the storyboard scene duration (±1s)
- Total scene durations sum to song duration

---

### Step 4: `viz assemble --scenes scenes/ --spec render_spec.json`

**Input:** Per-scene clips + RenderSpec
**Output:** `rough.mp4` (single timeline)

**What happens:**
- Reads scene durations from storyboard
- Concatenates clips in order using FFmpeg
- Muxes original audio track underneath
- Beat-synced transitions (crossfade or hard cut per storyboard)

**CLI:**
```bash
viz assemble --scenes scenes/ --spec render_spec.json --out rough.mp4
```

**Verification:**
- `rough.mp4` duration ≈ song duration (±2s)
- Audio track is present and matches original WAV
- All 5 scenes appear in correct order

---

### Step 5: `viz master --input rough.mp4 --spec render_spec.json`

**Input:** Rough cut + RenderSpec
**Output:** Mastered MP4 (EBU R128 loudness, color-corrected)

**What happens:**
- Loudness normalization to -14 LUFS (YouTube target)
- FFmpeg-based color pipeline (ACES-to-sRGB approximation)
- Audio stem mix: drums/bass/vocals/other balanced
- Output at target resolution (1080p default)

**CLI:**
```bash
viz master --input rough.mp4 --spec render_spec.json --out master.mp4
```

**Verification:**
- `master.mp4` exists and is playable
- FFmpeg loudness probe shows -14 LUFS ±1 LU

---

### Step 6: `viz ship --master master.mp4 --out deliverables/`

**Input:** Mastered MP4
**Output:** Packaged deliverables in `deliverables/`

**What happens:**
- Copies master MP4
- Extracts audio stems (if available)
- Generates thumbnail (mid-frame extraction)
- Creates `final.zip` containing:
  - `master.mp4`
  - `audio_stems.zip` (drums/bass/vocals/other)
  - `thumbnail.jpg`
  - `storyboard.json` (provenance)
  - `render_spec.json` (provenance)

**CLI:**
```bash
viz ship --master master.mp4 --out deliverables/
```

**Verification:**
- `deliverables/final.zip` exists
- ZIP contains at least: master.mp4, thumbnail.jpg, storyboard.json

---

## 3. Full Happy Path Command Sequence

```bash
# 1. Analyze
viz analyze song.wav --out render_spec.json

# 2. Storyboard
viz storyboard --spec render_spec.json --concept "abstract neon dreamscape" --seed 42 --out storyboard.json

# 3. Generate (offline for smoke test)
MELOSVIZ_COMFYUI_OFFLINE=1 viz generate --storyboard storyboard.json --out scenes/

# 4. Assemble
viz assemble --scenes scenes/ --spec render_spec.json --out rough.mp4

# 5. Master
viz master --input rough.mp4 --spec render_spec.json --out master.mp4

# 6. Ship
viz ship --master master.mp4 --out deliverables/

# Verify
ls -la deliverables/final.zip
ffprobe -v error -show_entries format=duration -of csv=p=0 master.mp4
```

---

## 4. Dependency Map (WBS Alignment)

| Happy Path Step | WBS Task(s) | Status | Notes |
|-----------------|-------------|--------|-------|
| `viz analyze` | 11 (fixture WAV) | DONE | CLI functional, Python MIR working |
| `viz storyboard` | 12 (storyboard JSON) | PARTIAL | CLI exists, Director LLM wired, needs fixture test |
| `viz generate` | 13-15 (per-adapter generate) | PARTIAL | ComfyUI adapter exists, offline mode needs wiring |
| `viz assemble` | 16 (ffmpeg mux) | PARTIAL | CLI exists, needs end-to-end verification |
| `viz master` | 17 (DaVinci/ffmpeg master) | PARTIAL | FFmpeg fallback exists, needs loudness normalization |
| `viz ship` | 18 (package deliverables) | PARTIAL | CLI exists, needs ZIP packaging |

---

## 5. What M.3 Needs to Implement

Based on gaps found during M.2 design:

1. **Fixture WAV** (WBS-11): Create a synthetic 124 BPM WAV for deterministic testing
2. **Offline generate mode** (WBS-24): Wire `MELOSVIZ_COMFYUI_OFFLINE=1` env var to produce FFmpeg placeholder clips
3. **Assemble verification**: End-to-end test that `viz assemble` produces a valid MP4 with audio
4. **Master loudness**: Verify FFmpeg loudness normalization hits -14 LUFS
5. **Ship ZIP packaging**: Verify `viz ship` produces a ZIP with all expected artifacts
6. **End-to-end smoke test**: Single script that runs all 6 steps and validates outputs

---

## 6. Acceptance Criteria (maps to WBS Phase 1)

| Criterion | WBS Task | Verification |
|-----------|----------|-------------|
| `viz analyze` produces valid RenderSpec JSON | 11 | Pydantic model_validate_json passes |
| `viz storyboard` produces 5-scene JSON with variation | 12, 19 | No adjacent duplicate scenes |
| `viz generate` produces per-scene MP4s (offline) | 24 | 5 MP4 files in scenes/ |
| `viz assemble` produces rough.mp4 with audio | 16 | Duration ≈ song duration |
| `viz master` produces loudness-normalized MP4 | 17 | ffprobe shows -14 LUFS |
| `viz ship` produces final.zip with all artifacts | 18 | ZIP contains MP4 + thumbnail + JSON |
| Full pipeline runs from single WAV | 25 | One script, zero manual steps |
