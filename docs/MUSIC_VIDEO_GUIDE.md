# MelosViz — Music Video Production Guide

> **Goal:** ship a digitally created, multi-scene, **3-5 minute music
> video** that holds up on a festival/club screen _and_ on YouTube.
> Beat-synced, visually varied, and telling a story no matter how
> abstract.

This is the **top-level, discoverable entry point** for the
end-to-end music-video workflow.

---

## 0. The one-line summary

> **ComfyUI + Cinema 4D + Unreal Engine 5 + After Effects + DaVinci
> Resolve + ffmpeg, glued by a Python orchestrator, driven by a
> Director LLM, operated from a Director's Console.**

That's MelosViz. The browser/React/R3F approach is deprecated. The
desktop app is a **Director's Console** (timeline + shot list + render
queue), not a 3D editor. All real rendering is delegated to
industry-standard tools.

---

## 1. The full guide lives here

**The canonical end-to-end guide is
[`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md).** It walks you
from "I have a WAV file" to "I have a master MP4 + festival ProRes +
audio stems" with:

- A tools-and-prerequisites table (ComfyUI, C4D, UE5, AE, Resolve, ffmpeg).
- A one-picture pipeline overview (`viz analyze` → `storyboard` →
  `generate` → `assemble` → `master` → `ship`).
- Per-step instructions for every stage.
- A worked example for a 3-minute, 124 BPM track.
- Troubleshooting tips per adapter.
- Art-direction suggestions (palettes, cameras, motion language).

---

## 2. The 60-second tour (one command per stage)

```bash
# 0. You have a WAV file.
ls track.wav

# 1. Analyze it (BPM, beats, segments, palette hints).
python -m melosviz.cli.main analyze track.wav --out spec.json

# 2. Storyboard it (LLM or template — varied, beat-synced, story-driven).
python -m melosviz.cli.main storyboard track.wav \
    --concept "abstract underwater city, bioluminescent, 35mm grain" \
    --bpm 124 \
    --palette "#0d0d10 #ff2bd6 #22d3ee" \
    --out storyboard.json

# 3. Generate per-scene clips (ComfyUI / C4D / UE / AE — offline fallback if missing).
python -m melosviz.cli.main generate track.wav \
    --storyboard storyboard.json \
    --out ./out

# 4. Assemble the rough cut (AME or ffmpeg).
python -m melosviz.cli.main assemble ./out --out ./rough.mp4

# 5. Master (color + audio mix + 3 deliverables).
python -m melosviz.cli.main master ./rough.mp4 --out ./master

# 6. Ship (MP4 + ProRes + audio stems + SRT captions).
python -m melosviz.cli.main ship ./master --out ./final.zip
```

---

## 3. What you get out the other end

`final.zip` contains:

| Deliverable             | Format                   | Audience                      |
| ----------------------- | ------------------------ | ----------------------------- |
| `final_1080p.mp4`       | H.264 / AAC              | YouTube (≤ 1080p), social     |
| `final_4k.mp4`          | H.265 / AAC              | YouTube (4K), Vimeo           |
| `final_prores_4444.mov` | ProRes 4444 (with alpha) | Festival VJ rigs              |
| `stems/`                | 24-bit/96 kHz WAVs       | Bandcamp, vinyl, live shows   |
| `captions.srt`          | SRT                      | YouTube auto-sync, festivals  |
| `storyboard.json`       | JSON                     | Re-render, audit, handoff     |
| `manifest.json`         | JSON + SHA256            | Provenance, cosign-verifiable |

---

## 4. The toolchain at a glance

| Stage               | Tool                                          | Adapter                                          | Fallback                            |
| ------------------- | --------------------------------------------- | ------------------------------------------------ | ----------------------------------- |
| Analyze             | Rust MIR / Python librosa                     | `crates/melosviz-mir`, `melosviz.analysis.audio` | always                              |
| Storyboard          | LLM (OpenAI-compatible) or template           | `melosviz.llm.director.DirectorAgent`            | template always                     |
| Generate images     | **ComfyUI** (SDXL / Flux / Wan 2.1)           | `render/comfyui_adapter.py`                      | offline → `workflow.json` per scene |
| Generate 3D         | **Cinema 4D** (`Commandline.exe` / `c4dpy`)   | `render/cinema4d_adapter.py`                     | offline → `c4d_render_plan.json`    |
| Real-time cinematic | **Unreal Engine 5** (`UnrealEditor-Cmd`)      | `render/unreal_adapter.py`                       | offline → `ue_render_plan.json`     |
| Motion graphics     | **After Effects** (`aerender`)                | `render/aftereffects_adapter.py`                 | `nexrender` server fallback         |
| Assemble            | **Adobe Media Encoder** (`ame`) or **ffmpeg** | `render/mediaencoder_adapter.py`                 | ffmpeg always                       |
| Master              | **DaVinci Resolve** (`resolve-script`)        | `render/davinci_adapter.py`                      | ffmpeg → 3 deliverables             |
| Ship                | ffmpeg + sha256 + cosign                      | `viz ship`                                       | always                              |

---

## 5. The goal in one paragraph

A 3-5 minute, multi-scene music video where:

- **Beats drive cuts.** Every scene boundary snaps to a beat (within
  ±120 ms tolerance, configurable per BPM).
- **Two adjacent scenes are never identical** (camera motion + palette
  - scene type all vary).
- **The story is told** — even abstract pieces have an intro / build /
  tension / release / resolution arc driven by MIR section detection
  and the director's narrative beat tagging.
- **The visual language is coherent** — palette cross-fades between
  adjacent scenes instead of hard-cutting.
- **It renders locally.** All required tools are free or low-cost.
  ComfyUI + ffmpeg alone can produce the entire deliverable set.
- **It renders reproducibly.** Same WAV + same seed → byte-identical
  `storyboard.json`. Same storyboard → byte-identical `final.zip`
  (modulo non-deterministic GPU floating-point order; we surface this).

---

## 6. Where to look first

| If you want to…                | Read this                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Understand the architecture    | [`SPEC.md`](SPEC.md) §11                                                       |
| Make your first 3-minute video | [`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md)                           |
| See the full roadmap           | [`WBS.md`](WBS.md)                                                             |
| Add a new adapter              | `SPEC.md §3.2`                                                                 |
| Add a new CLI subcommand       | [`backend/src/melosviz/cli/main.py`](backend/src/melosviz/cli/main.py)         |
| Tune the Director LLM          | [`backend/src/melosviz/llm/director.py`](backend/src/melosviz/llm/director.py) |
| Operate the Director's Console | [`desktop/views/main/index.html`](desktop/views/main/index.html)               |

---

## 7. The promise

> _A single WAV file should be enough to ship a 3-5 minute music
> video — beat-synced, story-driven, festival-ready._

That's the bar. Every commit on `feat/comfyui-studio-pivot` is moving
toward it.
