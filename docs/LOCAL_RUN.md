# Melosviz Local Run Validation

Validated: 2026-06-30 on macOS Darwin 27 (Apple Silicon), Python 3.13.13.

## Hermetic local verify (start here)

One-command environment check + a fast pytest subset (no network required once
deps are installed from lockfiles):

```bash
make diagnose
cd backend && python -m pytest tests/test_golden_corpus.py -q
# equivalents: make golden   |   make test-backend  (full suite)
```

| Surface | Command | Notes |
|---------|---------|-------|
| Env self-check | `make diagnose` / `python scripts/diagnose.py` | MV-FR-50; stdlib-only |
| Golden subset | `make golden` | Offline once `backend` extras installed |
| Docs gates | `make trace` | WBS / GAP / journeys / TRACEABILITY |

**Offline / air-gap:** do not invent alternate indexes. Follow `docs/AIRGAP.md`
(bundle script, wheelhouse, `cargo vendor`, frozen locks). Policy:
`docs/SUPPLY_CHAIN.md`.

**Work claiming:** pick an open ID in `docs/WORK_DAG.md`, claim it on the
PR/issue (`claim W-2xx`), use branch `feat/w2xx-<slug>`, and reference the FR.
See the Claim protocol section in that file.

## Bridge sidecar (local dev)

The HTTP bridge listens on **`127.0.0.1:8765`** by default (`python -m
melosviz.bridge.server --port 8765`). Use the dev helper for a quick health probe
or background start (sets `MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1` for open
loopback — see `docs/ENV.md`):

```bash
pip install -e backend/
./scripts/dev_bridge.sh health    # probe /health + endpoint tips
./scripts/dev_bridge.sh start     # background sidecar on :8765
./scripts/dev_bridge.sh stop
```

Windows (PowerShell):

```powershell
pip install -e backend\
.\scripts\dev_bridge.ps1 health
.\scripts\dev_bridge.ps1 start
```

Headless bridge e2e (CI parity): `./desktop/tests/run_bridge_e2e.sh` (uses port
`18765` by default to avoid colliding with a dev sidecar on `8765`).

**Desktop app:** when running the Electrobun shell, use the system-tray menu
**Open Bridge Health** to open `http://127.0.0.1:<port>/health` in your browser
(the port is logged at startup as `[MelosViz] bridge port`). Tray strings are
localized via `desktop/locales/`.

## Local studio checklist

Short operator path for the **web studio** on loopback (the desktop shell runs
the same pipeline; tray **Open Bridge Health** is covered in the bridge section
above).

| Step | Action | Notes |
|------|--------|-------|
| 1 | **Start bridge** | `./scripts/dev_bridge.sh start` or `.\scripts\dev_bridge.ps1 start` — listens on `127.0.0.1:8765` |
| 2 | **Open web** | `cd web && npm install && npm run dev` — Vite serves `http://localhost:5173` by default |
| 3 | **Load audio** | Enter a path, browse, drag-drop, or pick from **Recent** (name + size in localStorage); **Clear recent** empties the list |
| 4 | **Analyze** | Click **Analyze** — posts to `/api/analyze` (dev proxy → bridge) |
| 5 | **Cancel / progress** | **Cancel** or **Escape** while the loading overlay is open (`useAnalysis` AbortController); overlay shows simulated **progress %** with `role="progressbar"` + live region (W-361) |
| 6 | **Locale / HC** | Header **EN/ES** toggle (persisted in localStorage); **HC** for high-contrast focus rings; **Aa** for light/dark theme — transport, errors, presets, and toasts follow locale |
| 7 | **Playback transport** | After analyze: **Space** play/pause (blocked while typing or a range slider is focused), seek bar, **elapsed / total** time readout, **±5 s** hint chips (←/→), **volume/mute** + **M** shortcut (persisted), **speed 0.5×–1.5×** slider + **0.5× / 1× / 1.5×** preset chips (persisted, scene + audio `playbackRate`), **loop** toggle + **L** shortcut (persisted, restart at end), i18n aria-labels (W-358, W-360, W-363, W-366–367, W-369–370, W-372) |
| 7b | **Scene jumps** | Right panel lists keyframe scenes — click to seek; panel label + jump aria-labels follow locale (W-374) |
| 8 | **Presets** | **Quick-apply** dropdown applies built-in presets without opening the editor dialog (W-362); full editor still available beside it |
| 9 | **Scene / fullscreen** | **Full** toggles scene fullscreen (`aria-pressed`, Escape or **f** exits); canvas has deterministic SR text mirror (`buildSceneSummary`) |
| 10 | **SpecViewer export** | Summary line shows duration · BPM · keyframe count (W-359); **Download JSON** / **Copy JSON** — copy shows aria-live toast (W-357) |
| 11 | **Errors** | Bridge-down / memory-cap hints under the alert; **Retry** re-runs analyze; **Dismiss** clears the banner (tab-order per `docs/a11y/FOCUS.md`) |

**Offline / air-gap:** bundle deps per `docs/AIRGAP.md` (wheelhouse, frozen locks) —
do not invent alternate package indexes. **SDK consumers** pulling `@melosviz/*`
from GitHub Packages: `docs/sdk/README.md`. Keyboard/focus contract (skip link →
`#main`): `docs/a11y/FOCUS.md`.

## Recovery / publish (Shell blocked)

When Cursor Shell or AMDRMPATH blocks `git push` / `gh pr create`, publish
on-disk lanes via the API recovery scripts (no git/gh shell required):

| Wave | Command | Publisher script |
|------|---------|------------------|
| **all (p1p → p1q)** | `RUN_ALL_RECOVERY.cmd` (repo root) | runs p1p then p1q sequentially |
| p1p (7 lanes) | `RUN_P1P_RECOVERY.cmd` | `scripts/_recover_p1p_api_all.py` |
| p1q (studio polish) | `RUN_P1Q_RECOVERY.cmd` | `scripts/_recover_p1q_api_all.py` |

`RUN_ALL_RECOVERY.cmd` logs each sub-runner exit code. Pending-merge evidence
and lane inventory: `../phenotype-org-audits-v38/audit-v38/output/MelosViz/WAVE_P1PQ_PENDING.md`.
Last API report: `scripts/_recover_p1p_report.json` / `scripts/_recover_p1q_report.json`.

---

## Completion Stages

| Stage | Description | Result | Notes |
|-------|-------------|--------|-------|
| 0 | CLI install (`pip install -e .`) | PASS | `viz --help` works |
| 1a | `viz analyze <wav>` dep-light (no audioop) | PARTIAL | Produces valid JSON but flat amplitude_envelope (all 0.5); Python 3.13 removed `audioop` |
| 1b | `viz analyze <wav>` with audioop-lts | FAIL | `audioop.error: not a whole number of frames` — segment alignment bug (#audioop-alignment) |
| 1c | `spec_from_wav_rich` dep-light (no librosa) | PASS | 4 scene_segments, 75 dense_keyframes, proper structure |
| 2a | `viz build <wav>` (mock adapters) | FAIL | CLI bug: calls `spec_from_wav` (v1) which produces no scene_segments; `assemble_render_plan` rejects empty scene_segments |
| 2b | `assemble_render_plan` via Python API | PASS | 4-segment mock plan produced with scene types, transitions, beat alignment |
| 3 | `pip install librosa numpy` | PASS | Installs cleanly (~30s); scipy, numba pulled in |
| 3a | `spec_from_wav_rich` with librosa | PASS | Rich output: BPM, key, mode, danceability, spectral centroid, dense keyframes |
| 3b | Test suite with librosa | PASS | 315/315 pass, 2 skipped |
| 3c | Test suite without librosa | PARTIAL | 314/315 pass; 1 failure: `test_segment_energy_varies_across_segments` (flat 0.5 envelope) |
| 4 | FFmpeg video export | PASS | ffmpeg 8.1.2 working; 64x64 MP4 smoke clip produced (1662 bytes) |
| 4a | Blender headless | PASS | Blender 4.4.3 installed via DMG; headless bpy smoke render OK (2643-byte PNG) |
| 4b | Demucs stem separation | PASS | demucs 4.0.1 via pipx; CLI + Python import verified; CPU-only (no GPU required) |
| 4c | librosa MIR | PASS | librosa 0.11.0 in backend uv venv; import verified |
| 4d | TouchDesigner / AfterEffects / Firefly | OPERATOR-INSTALL | GUI/licensed; see Stage 4 install table |

## Commands (Exact)

### Stage 0 — Install

```bash
cd /path/to/melosviz/.claude/worktrees/local-run-demo-2026-06-30/backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
viz --help
```

Output: `usage: viz [-h] {analyze,build,render,diff,apply} ...`

### Stage 1 — Analyze (dep-light, no librosa)

Generate a synthetic WAV with stdlib:

```python
import wave, struct, math

SAMPLE_RATE = 44100
DURATION_SEC = 5
FREQ_HZ = 440.0
AMPLITUDE = 16000

samples = []
for i in range(int(SAMPLE_RATE * DURATION_SEC)):
    t = i / SAMPLE_RATE
    beat_env = 0.5 + 0.5 * math.sin(2 * math.pi * 2.0 * t)
    v = int(beat_env * AMPLITUDE * math.sin(2 * math.pi * FREQ_HZ * t))
    samples.append(v)

with wave.open("/tmp/test_tone.wav", "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(SAMPLE_RATE)
    f.writeframes(struct.pack(f"<{len(samples)}h", *samples))
```

Via Python API (robust dep-light path):

```python
from melosviz.analysis.audio import spec_from_wav_rich
spec = spec_from_wav_rich('/tmp/test_tone.wav')
# Returns: 4 scene_segments, 75 dense_keyframes, timeline_events with section markers
```

`viz analyze /tmp/test_tone.wav` on Python 3.13 without audioop: succeeds but produces flat
`amplitude_envelope` (all 0.5) because the stdlib fallback skips RMS computation.

### Stage 2 — Build/Render Plan

CLI `viz build` is blocked by a bug (see Known Bugs below). Use the Python API directly:

```python
from melosviz.analysis.audio import spec_from_wav_rich
from melosviz.compose.assemble import assemble_render_plan

spec = spec_from_wav_rich('/tmp/test_tone.wav')
plan = assemble_render_plan(spec, mock_adapters=True)
# Returns plan dict with 4 segments, transitions, beat-aligned starts, flash_safe=True
```

Sample plan output (truncated):

```json
{
  "version": "2.0",
  "total_duration": 5.0,
  "fps": 30,
  "segment_count": 4,
  "flash_safe": true,
  "segments": [
    {"index": 0, "label": "intro", "scene_type": "live_stage",
     "material": "organic_distort", "intensity": 0.5,
     "adapter_result": {"mock": true, "output_path": "/tmp/melosviz/seg_000.mov"}},
    ...
  ],
  "transitions": [1.2162, 2.5, 3.7162]
}
```

### Stage 3 — Rich MIR (with librosa)

```bash
pip install "librosa>=0.10" "numpy>=1.26"
```

Re-run rich analysis:

```python
from melosviz.analysis.audio import spec_from_wav_rich
spec = spec_from_wav_rich('/tmp/test_tone.wav')
d = spec.model_dump()
# d['mir']['tempo_bpm'] -> float
# d['mir']['key'] -> e.g. "A"
# d['mir']['mode'] -> "major" or "minor"
# d['mir']['danceability'] -> float 0-1
# d['dense_keyframes'] -> 75 frames with energy, brightness, spectral_centroid, beat_strength
# d['stem_channels'] -> spectral-fallback stems (drums/bass/vocals/other)
```

Test suite result: `315 passed, 2 skipped`.

### Stage 4 — Real Renderers (hardware/install gates)

Updated: 2026-06-30. Bug 3 (ffmpeg dyld symbol error) has been resolved; ffmpeg 8.1.2
re-installed from Homebrew now works. Blender 4.4.3 installed and verified headless.
Demucs 4.0.1 installed via pipx and importable. Librosa 0.11.0 installed in backend venv.

| Adapter | Gate | Status | Notes |
|---------|------|--------|-------|
| `video_exporter` (FFmpeg) | `ffmpeg` on PATH | PASS | ffmpeg 8.1.2; encode to MP4/WebM verified (1662-byte smoke clip at 64x64) |
| `blender_exporter` | Blender 4.x headless | PASS | Blender 4.4.3 installed; headless bpy smoke render produces PNG frame (2643 bytes at 64x64) |
| Demucs stems | `pipx install demucs` | PASS | demucs 4.0.1 installed; CLI available; Python import works (CPU-only; no torch GPU required for HTDemucs htdemucs model on CPU) |
| librosa (MIR) | `pip/uv install librosa` | PASS | librosa 0.11.0 in backend venv; `import librosa` succeeds |
| `touchdesigner` runtime | TouchDesigner install | OPERATOR-INSTALL | GUI app; no headless CLI available — see install instructions below |
| `aftereffects_adapter` | After Effects + scripting | OPERATOR-INSTALL | GUI + Adobe license required |
| `firefly_adapter` | Adobe Firefly API key | OPERATOR-INSTALL | Requires `ADOBE_FIREFLY_API_KEY` env var |
| `mediaencoder_adapter` | Adobe Media Encoder | OPERATOR-INSTALL | GUI + Adobe license required |

#### Stage 4 — FFmpeg smoke verify

```bash
ffmpeg -version 2>&1 | head -1
# ffmpeg version 8.1.2

ffmpeg -f lavfi -i color=black:s=64x64:d=0.1 -vframes 3 /tmp/melosviz_smoke.mp4 -y
ls -la /tmp/melosviz_smoke.mp4
# -rw-r--r-- 1662 Jun 30 ... /tmp/melosviz_smoke.mp4
```

#### Stage 4 — Blender install (headless, via DMG)

The `brew install --cask blender` download may fail with a connection reset. Direct DMG
install is reliable:

```bash
# Download Blender 4.4.3 ARM64 DMG (289 MB)
curl -C - -L --retry 5 -o /tmp/blender-macos-arm64.dmg \
  "https://download.blender.org/release/Blender4.4/blender-4.4.3-macos-arm64.dmg"

# Mount and copy
hdiutil attach /tmp/blender-macos-arm64.dmg -nobrowse
cp -R /Volumes/Blender/Blender.app /Applications/
hdiutil detach /Volumes/Blender

# Verify headless mode
/Applications/Blender.app/Contents/MacOS/Blender --version
# Blender 4.4.3

/Applications/Blender.app/Contents/MacOS/Blender --background \
  --python-expr "print('bpy ok')"
# Output: bpy ok
```

The blender_exporter resolves the binary automatically from:
1. `MELOSVIZ_BLENDER_BIN` env var
2. `shutil.which("blender")` (PATH lookup)
3. `/Applications/Blender.app/Contents/MacOS/Blender` (macOS bundle fallback)

Since Blender.app is in `/Applications`, the fallback path works without PATH changes.

#### Stage 4 — Blender headless render smoke

A minimal scene (64x64, 1 frame, empty scene + camera) renders in ~2 seconds:

```python
# run: /Applications/Blender.app/Contents/MacOS/Blender --background --python-expr "..."
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x = 64
sc.render.resolution_y = 64
sc.frame_start = 1
sc.frame_end = 1
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = '/tmp/melosviz-blender-smoke/smoke_'
bpy.ops.object.camera_add()
sc.camera = bpy.context.active_object
bpy.ops.render.render(write_still=True)
print('SMOKE_RENDER_OK')
```

Result: `SMOKE_RENDER_OK`, `/tmp/melosviz-blender-smoke/smoke_.png` (2643 bytes).

#### Stage 4 — Demucs stems install

```bash
pipx install demucs
# installed package demucs 4.0.1, using Python 3.14.5

demucs --help   # verify CLI works

# Python import verify:
python3 -c "import demucs; print('demucs ok')"
# demucs ok
```

Note: Demucs bundles its own torch dependency. The `htdemucs` model runs on CPU (slower
than GPU but functional). First separation call downloads model weights (~83 MB) to
`~/.cache/torch/hub/`. Set `DEMUCS_CACHE` to override.

The melosviz audio module imports demucs at call time (not import time), so the package
is always importable regardless of demucs presence.

#### Stage 4 — librosa install in backend venv

```bash
cd backend
uv venv --clear .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[test,lint]"
uv pip install --python .venv/bin/python librosa

.venv/bin/python -c "import librosa; print('librosa', librosa.__version__)"
# librosa 0.11.0
```

#### Stage 4 — Operator-install GUI/licensed tools

These require GUI installation or a paid license; no headless CLI install is available:

| Tool | Install command | Needed for |
|------|----------------|------------|
| TouchDesigner | Download from https://derivative.ca/download | `runtime/touchdesigner/` live render adapter |
| Adobe After Effects | Adobe Creative Cloud app | `render/aftereffects_adapter.py` |
| Adobe Media Encoder | Adobe Creative Cloud app | `render/mediaencoder_adapter.py` |
| Adobe Firefly | N/A (API key only) — `export ADOBE_FIREFLY_API_KEY=...` | `render/firefly_adapter.py` |

## Known Bugs Found During Validation

### Bug 1: `audioop` segment alignment (critical)

**File:** `backend/src/melosviz/analysis/audio.py:122`

**Trigger:** Python 3.13 + `audioop-lts` installed (or Python ≤3.12 with standard `audioop`).

**Root cause:** `segment_size = max(1, len(mono) // max(1, bucket_count))` does not guarantee
alignment to `sample_width`. For a 441000-byte mono stream with `bucket_count=120`, this yields
`segment_size=3675` (odd), which fails `audioop.rms(segment, sample_width=2)` with
`audioop.error: not a whole number of frames`.

**Workaround:** Without `audioop-lts`, Python 3.13 silently skips audioop and falls back to flat
0.5 values. Envelope is meaningless but no crash.

**Fix needed:**
```python
# In analyze_wav, replace:
segment_size = max(1, len(mono) // max(1, bucket_count))
# With:
segment_size = max(sample_width, (len(mono) // max(1, bucket_count) // sample_width) * sample_width)
```

### Bug 2: `viz build` / `viz analyze` use v1 analysis path (no scene_segments)

**File:** `backend/src/melosviz/cli/main.py:54`

**Trigger:** `viz build <wav>` and `viz analyze <wav>` call `spec_from_wav` (v1) which produces
no `scene_segments`, `dense_keyframes`, or `timeline_events`. Then `assemble_render_plan`
raises `AssemblyError: render_spec.scene_segments is empty`.

**Fix needed:** CLI commands should call `spec_from_wav_rich` (the v2 path). The v1 path can
be retained for compatibility but should not be the default for CLI invocations.

### Bug 3: FFmpeg binary broken on this machine (environment-specific) — RESOLVED

**Was:** Local Homebrew ffmpeg 8.1 had dyld symbol error for `_x265_api_get_215`.

**Resolution (2026-06-30):** ffmpeg 8.1.2 re-installed from Homebrew. `ffmpeg -version`
and a 64x64 MP4 encode both succeed. `is_ffmpeg_available()` now returns True.

## What Each Optional Dep Unlocks

| Dependency | Unlocks | Without it |
|-----------|---------|------------|
| `audioop` / `audioop-lts` | Real RMS envelope in `analyze_wav` | Flat 0.5 envelope (silent degradation) |
| `librosa` + `numpy` | Beat tracking, onset detection, spectral centroid, key/mode, danceability, MFCC valence/arousal, scene boundary detection | Uniform fallback values; tests mostly pass but `test_segment_energy_varies` fails |
| `scipy` | Spectral novelty scene boundary detection (used by librosa path) | Falls back to equal-duration segments |
| `ffmpeg` on PATH | `export_video()` producing real MP4/WebM | `FFMpegNotFoundError` | INSTALLED 8.1.2 |
| `demucs` + `torch` | Real HTDemucs stem separation (drums/bass/vocals/other) | Spectral-fallback stems (if librosa present) or zero stems | INSTALLED demucs 4.0.1 (CPU) |
| Blender 4.x | `blender_exporter` 3D scene rendering | Adapter raises `BlenderNotFoundError` | INSTALLED 4.4.3 (/Applications/Blender.app) |
| TouchDesigner | `touchdesigner/` runtime adapter | Not invokable |
| Adobe AE / ME | `aftereffects_adapter`, `mediaencoder_adapter` | Not invokable |
| Adobe Firefly | `firefly_adapter` image generation | Not invokable |

## Fixture File

`tests/fixtures/test_tone.wav` — a 5-second, 44100Hz, mono, 16-bit PCM WAV generated
with stdlib `wave` + `struct`. Created during this validation run and committed as a
test fixture for future local runs.
