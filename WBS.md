# WBS — MelosViz (2026-08-25)

**Repo:** [KooshaPari/Melosviz](https://github.com/KooshaPari/Melosviz)
**Branch:** `feat/comfyui-studio-pivot`
**Status:** Studio pipeline pivot in flight; see [`SPEC.md`](SPEC.md) §11
and [`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md) for the architecture
and end-to-end guide.

**Owner:** forge (agent CLI). **Driver:** `python -m melosviz.cli.main …`.

---

## Phase overview

MelosViz is now a **studio conductor** that drives industry-standard
post-production tools (ComfyUI + Cinema 4D + Unreal Engine 5 + After
Effects + DaVinci Resolve + Adobe Media Encoder + ffmpeg) to ship
**digitally created, multi-scene, 3-5 minute music videos** that work
on festival/club screens _and_ YouTube — beat-synced, visually varied,
and story-driven no matter how abstract.

| Phase | Tasks   | Theme                     | Outcome                                                      |
| ----- | ------- | ------------------------- | ------------------------------------------------------------ |
| 0     | 1–10    | Studio pivot bootstrap    | All adapters wired + director LLM in place                   |
| 1     | 11–25   | End-to-end happy path     | First 3-5 min video shipped from `viz ship`                  |
| 2     | 26–40   | Tooling hardening         | C4D/UE/AE/Resolve live-tested on real hardware               |
| 3     | 41–55   | Beat-sync + story quality | Director LLM prompt-tuning, no two scenes alike              |
| 4     | 56–70   | Render farm               | GPU k8s workers behind ComfyUI adapter                       |
| 5     | 71–85   | Ship & distribute         | YouTube upload + festival VJ delivery                        |
| 6     | 86–100  | Polish + docs             | 3-5 min video reproducible from a single WAV                 |
| 7     | 107–109 | Native-audio video        | Wan S2V + Seedance A2V workflows; audio-driven scene routing |

---

## Phase 0 — Studio pivot bootstrap (tasks 1–10)

| ID  | Title                                                                   | depends_on | ac                                                                |
| --- | ----------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------- |
| 1   | Spec the studio-pipeline pivot (ComfyUI + C4D + UE + AE + Resolve)      | —          | `SPEC.md` §11 merged                                              |
| 2   | ComfyUI adapter (`comfyui_adapter.py`) + reference workflow JSON        | 1          | unit tests green                                                  |
| 3   | Cinema 4D headless adapter (`cinema4d_adapter.py`)                      | 1          | unit tests green + offline fallback writes `c4d_render_plan.json` |
| 4   | Unreal Engine 5 Movie Render Queue adapter (`unreal_adapter.py`)        | 1          | unit tests green + offline fallback writes `ue_render_plan.json`  |
| 5   | After Effects adapter (`aerender` + `nexrender` fallback)               | 1          | unit tests green                                                  |
| 6   | DaVinci Resolve adapter (`resolve-script` + ffmpeg fallback)            | 1          | unit tests green + offline 3-deliverable master                   |
| 7   | Director LLM agent (`melosviz.llm.director.DirectorAgent`)              | 1          | template fallback unit-tested + LLM path tested                   |
| 8   | Conductor registry dispatch (`registry.py`) for all 6 backends          | 2–7        | `ADAPTER_REGISTRY` test green                                     |
| 9   | CLI subcommands: `storyboard`, `generate`, `assemble`, `master`, `ship` | 2–7        | `viz storyboard --help` exits 0                                   |
| 10  | Desktop Director's Console tab (concept / BPM / palette + shot list)    | 7,9        | `bunx tsc --noEmit` exits 0                                       |

`ac_v1`: commit on `feat/comfyui-studio-pivot` with conventional subject

- DAG id in footer.

---

## Phase 1 — End-to-end happy path (tasks 11–25)

| ID  | Title                                                                                        | depends_on | ac                                              |
| --- | -------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------- |
| 11  | Build a deterministic `viz analyze` fixture WAV (synthetic 124 BPM)                          | 9          | `pytest tests/llm/test_director.py` green       |
| 12  | Wire `viz storyboard` to emit a 5-scene storyboard JSON                                      | 7,11       | output matches `SHOT_LIST_V1` schema            |
| 13  | Run `viz generate` against a local ComfyUI server                                            | 2,12       | per-scene clip MP4s in `--out`                  |
| 14  | Run `viz generate` against Cinema 4D (mock binary)                                           | 3,12       | per-scene render plans in `--out`               |
| 15  | Run `viz generate` against UE5 (mock binary)                                                 | 4,12       | per-scene render plans in `--out`               |
| 16  | Run `viz assemble` with ffmpeg only                                                          | 9,13       | `rough.mp4` muxed at song duration              |
| 17  | Run `viz master` with DaVinci offline (ffmpeg fallback)                                      | 6,16       | 3 deliverables in `--out`                       |
| 18  | Run `viz ship` to package deliverables                                                       | 9,17       | `final.zip` contains MP4 + ProRes + audio stems |
| 19  | Storyboard fixture: prevent two adjacent scenes from being identical (camera/motion/palette) | 7          | `test_director_variation_enforced` green        |
| 20  | Beat-sync: shot boundaries snap to nearest beat (configurable tolerance)                     | 7,12       | snap test green                                 |
| 21  | Director LLM prompt template + system message documented                                     | 7          | `docs/STUDIO_PIPELINE.md` §6 updated            |
| 22  | Reproducibility: same WAV + same seed → byte-identical `storyboard.json`                     | 7,12       | `test_director_deterministic` green             |
| 23  | Story length: enforce 3-5 minute target (warn / clip outside)                                | 7,12       | `test_director_duration_window` green           |
| 24  | Offline mode smoke test: `MELOSVIZ_COMFYUI_OFFLINE=1` end-to-end                             | 9,12,17,18 | `viz ship` returns 0 with no tools              |
| 25  | Ship a real 3-5 min video to `out/samples/`                                                  | 24         | `out/samples/first_cut.mp4` plays               |

`ac_v1`: commit on `feat/comfyui-studio-pivot`.

---

## Phase 2 — Tooling hardening (tasks 26–40)

| ID  | Title                                                                          | depends_on | ac                                             |
| --- | ------------------------------------------------------------------------------ | ---------- | ---------------------------------------------- |
| 26  | ComfyUI live-test on RTX 4090 (capture timing + VRAM headroom)                 | 13         | `docs/PERF_BENCHMARK.md` updated               |
| 27  | C4D live-test (`Commandline.exe -render`) on real `.c4d` project               | 14         | render-plan → MP4 roundtrip                    |
| 28  | UE5 live-test (`UnrealEditor-Cmd -MovieRenderQueue`)                           | 15         | MRQ job → EXR/MP4 roundtrip                    |
| 29  | AE live-test (`aerender -project … -comp …`)                                   | 9          | AEPX → MP4 roundtrip                           |
| 30  | Resolve live-test (`resolve-script` + `ProjectSettings.SaveAs`)                | 17         | timeline → 3 deliverables                      |
| 31  | Flash-safety re-validation per scene (per-SceneSegment)                        | 5          | no scene flashes > 3 Hz                        |
| 32  | Color-pipeline pass: ACES 1.3 input → DaVinci Color Management → sRGB delivery | 6          | LUT test fixture                               |
| 33  | Audio mix: stems (drums/bass/vocals/other) routed to Resolve Fairlight         | 6          | stems bus diagram in `docs/STUDIO_PIPELINE.md` |
| 34  | SRT caption generation from lyrics (whisper.cpp fallback)                      | 7          | `viz ship` emits `.srt`                        |
| 35  | Director's Console live shot-list update (WebSocket progress)                  | 10         | desktop view streams per-scene progress        |
| 36  | Failure-injection tests for every adapter                                      | 2–6        | `test_studio_pipeline_adapters.py`             |
| 37  | Memory cap on per-scene render queue                                           | 9          | `viz generate --max-jobs 4` honored            |
| 38  | Resume-after-crash: `viz generate --resume <state.json>`                       | 9          | partially-rendered job completes               |
| 39  | Manifest of per-scene job-specs (for offline GPU farm)                         | 9          | `manifest.json` schema                         |
| 40  | Artifact signing: cosign attest every render                                   | 18         | `cosign verify-blob` on deliverables           |

`ac_v1`: commit on `feat/comfyui-studio-pivot`.

---

## Phase 3 — Beat-sync + story quality (tasks 41–55)

| ID  | Title                                                                                | depends_on | ac                                  |
| --- | ------------------------------------------------------------------------------------ | ---------- | ----------------------------------- |
| 41  | Camera-movement library (push / dolly / orbit / crane / handheld / static)           | 7          | 6+ distinct patterns                |
| 42  | Palette library (cyberpunk noir / bioluminescent / desert / underwater / monochrome) | 7          | 5+ palettes                         |
| 43  | Story-arc templates (rise-fall / call-response / three-act / vignette)               | 7          | 4+ templates                        |
| 44  | Director LLM prompt-tune against human-judged variety score                          | 7,42       | variety ≥ 0.85 on 20-sample eval    |
| 45  | LLM provider flexibility (OpenAI / Anthropic / local Ollama)                         | 7          | `MELOSVIZ_DIRECTOR_LLM` is base-URL |
| 46  | Cache director outputs by (WAV-fingerprint, concept, BPM)                            | 7          | second run is instant               |
| 47  | Per-scene narrative beat tag (intro / build / tension / release / resolution)        | 7          | matches MIR section type            |
| 48  | Lyrics-aligned cues (force scene change at chorus / bridge)                          | 7          | tested on 5 fixture tracks          |
| 49  | Mood-vector → palette mapping (cross-fade between adjacent palette tones)            | 7          | palette continuity test             |
| 50  | Camera-motion physics (no impossible moves — speed/distance limits)                  | 41         | feasibility check                   |
| 51  | Frame-rate tier config (24fps cinematic / 30fps YouTube / 60fps game)                | 9          | `--fps` flag honored                |
| 52  | Aspect-ratio tiers (16:9 YouTube / 21:9 cinematic / 9:16 short / 1:1 club)           | 9          | `--aspect` flag honored             |
| 53  | Loudness target (EBU R128 -14 LUFS for YouTube, -23 LUFS for festival)               | 6          | loudness test green                 |
| 54  | Director's Console: live preview frame from any per-scene clip                       | 10         | thumbnail + scrub                   |
| 55  | Director's Console: manual scene reorder + manual palette override                   | 10         | overrides saved to storyboard       |

`ac_v1`: commit on `feat/comfyui-studio-pivot`.

---

## Phase 4 — Render farm (tasks 56–70)

| ID  | Title                                                            | depends_on | ac                             |
| --- | ---------------------------------------------------------------- | ---------- | ------------------------------ |
| 56  | k8s GPU pool schema for ComfyUI workers                          | 2          | `k8s/comfyui-worker.yaml`      |
| 57  | Job queue: per-scene claim-checked off the manifest              | 39         | `viz generate --farm`          |
| 58  | S3-compatible artifact store (per-scene clip uploads)            | 39         | MinIO + GCS parity             |
| 59  | Per-worker VRAM budget (8/16/24/48 GB tiers)                     | 2          | fail-over to lower-VRAM model  |
| 60  | Cross-scene prompt dedupe (cache identical seed/prompt outputs)  | 13         | cache hit rate ≥ 30 %          |
| 61  | Spot-instance preemption handling (resume mid-scene)             | 38         | checkpoint + resume test       |
| 62  | Per-scene progress streaming (gRPC / WebSocket)                  | 35         | farm view in Console           |
| 63  | Burst-scaling under "ship by Friday" load                        | 56         | 50 concurrent scenes           |
| 64  | GPU type benchmarking (A100 / 4090 / 5090 / M3 Max)              | 26         | `docs/PERF_BENCHMARK.md` table |
| 65  | Cost-per-video estimate (kWh + spot $)                           | 26         | `docs/STUDIO_PIPELINE.md` §8   |
| 66  | Fan-out rendering of variants (different palettes × same scenes) | 7          | A/B preview                    |
| 67  | Distributed ComfyUI workflow orchestration (custom-node RPC)     | 2          | `comfyui-rpc` server           |
| 68  | Pre-flight GPU-bin packing (place scenes onto workers by VRAM)   | 59         | bin-pack greedy                |
| 69  | Quota + rate-limit guard against API-LLM providers               | 7          | backoff + retry                |
| 70  | Cost dashboard (per-track cost in Director's Console)            | 65         | `<console>/cost` route         |

`ac_v1`: commit on `feat/comfyui-studio-pivot`.

---

## Phase 5 — Ship & distribute (tasks 71–85)

| ID  | Title                                                     | depends_on | ac                     |
| --- | --------------------------------------------------------- | ---------- | ---------------------- |
| 71  | YouTube Data API v3 upload (private / unlisted / public)  | 18         | `viz ship --youtube`   |
| 72  | Thumbnail generation (mid-frame + title burn-in)          | 18         | `thumbnail.jpg` in zip |
| 73  | SRT caption upload + burn-in toggle                       | 34,71      | caption files in zip   |
| 74  | Festival VJ delivery format (ProRes 4444 + alpha matte)   | 6,18       | `viz ship --festival`  |
| 75  | Club delivery format (1080p H.264 + 4K H.265 tier)        | 18         | `viz ship --club`      |
| 76  | Beatport / Spotify Canvas pull from master (9:16, ≤ 30 s) | 51,52      | canvas variant         |
| 77  | Lyric video variant (auto-overlaid lyrics + scene)        | 34         | `viz ship --lyric`     |
| 78  | Vertical short variant (9:16, ≤ 60 s, beat-cut highlight) | 52         | `viz ship --short`     |
| 79  | Metadata embedding (artist, title, ISRC, BPM, key)        | 18         | `ffprobe` shows tags   |
| 80  | Manifest SHA256 + cosign attestation per deliverable      | 18,40      | `cosign verify-blob`   |
| 81  | Bandcamp-friendly MP3 + FLAC audio extract                | 18         | stems in zip           |
| 82  | Vinyl-friendly WAV (24-bit/96 kHz) extract                | 6          | high-res audio         |
| 83  | Email-ready preview (sub-clip + thumbnail)                | 18         | SMTP template          |
| 84  | Festival submission checklist PDF generator               | 74         | `submission.pdf`       |
| 85  | Public landing-page generator for the track               | 73,79      | `index.html`           |

`ac_v1`: commit on `feat/comfyui-studio-pivot`.

---

## Phase 6 — Polish + docs (tasks 86–100)

| ID  | Title                                                                                                                                                                                     | depends_on | ac                                                                                            |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------- |
| 86  | Reproducible run: `viz ship` from a single WAV → identical final.zip                                                                                                                      | 22,25      | byte-equality test                                                                            |
| 87  | Documentation site (mintlify / docusaurus)                                                                                                                                                | —          | `docs/` builds                                                                                |
| 88  | Tutorial: "Make your first 3-minute video"                                                                                                                                                | 25         | `docs/guides/first_video.md`                                                                  |
| 89  | Tutorial: "Re-time a video to a remix"                                                                                                                                                    | 20         | `docs/guides/remix.md`                                                                        |
| 90  | Tutorial: "Live VJ mode" (TouchDesigner integration)                                                                                                                                      | —          | `docs/guides/vj.md`                                                                           |
| 91  | Architecture diagram (ComfyUI ↔ C4D ↔ UE ↔ AE ↔ Resolve dataflow)                                                                                                                     | —          | `docs/ARCHITECTURE.md` updated                                                                |
| 92  | ADR-0004: why ComfyUI as the primary generative renderer                                                                                                                                  | —          | `docs/adr/0004-comfyui-primary.md`                                                            |
| 93  | ADR-0005: why we ship adapter fallbacks over strict deps                                                                                                                                  | —          | `docs/adr/0005-offline-fallbacks.md`                                                          |
| 94  | Local-run guide: end-to-end on a laptop                                                                                                                                                   | 24         | `docs/LOCAL_RUN.md` updated                                                                   |
| 95  | Troubleshooting matrix (every adapter, every error)                                                                                                                                       | 36         | `docs/TROUBLESHOOTING.md`                                                                     |
| 96  | Performance baseline (per-scene render time on RTX 4090)                                                                                                                                  | 26         | `docs/PERF_BENCHMARK.md` updated                                                              |
| 97  | Glossary (MIR / ComfyUI / ACES / ProRes / Fairlight / EBU R128)                                                                                                                           | —          | `docs/GLOSSARY.md`                                                                            |
| 98  | Sample-project repo (`melosviz-samples`)                                                                                                                                                  | 25         | linked from README                                                                            |
| 99  | Video-tutorial: "Watch the director make a video in 10 minutes"                                                                                                                           | 25         | `docs/guides/video_tutorial.md`                                                               |
| 100 | Public release v1.0.0 — "First Cut"                                                                                                                                                       | 86,95      | `v1.0.0` tag + GitHub Release                                                                 |
| 107 | Register `comfyui_audio_video_wan` scene type in `comfyui_adapter` + `registry` (Wan S2V with audio-conditioned latent)                                                                   | 11         | `--audio-conditioned-video`                                                                   |
| 108 | Register `comfyui_audio_video_seedance` scene type in `comfyui_adapter` + `registry` (Seedance A2V sampler)                                                                               | 11         | `seedance_a2v.json`                                                                           |
| 109 | Wire director archetype routing: `drop → wan`, `chorus → seedance` (when character present); add `audio_path`/`motion_strength`/`audio_influence` to `_SafeDict`; CLI flag + i18n + tests | 11         | `tests/render/test_native_audio_routing.py`, `tests/workflows/test_native_audio_workflows.py` |

---

## Ac conventions

- `ac_v1`: commit on `feat/comfyui-studio-pivot` with conventional subject + DAG id in footer.
- `ac_test`: `pytest -q tests/` exits 0 (Python side) **or**
  `bun test` exits 0 (desktop side).
- `ac_clippy`: `cargo clippy -- -D warnings` exits 0 (Rust side).

---

## Notes

- This WBS replaces the old `recovery/melosviz-local-20260726` recovery flow. The recovery branch is archived (task 8 of the prior WBS, marked `ac_v1`).
- Part of the **Phenotype Fleet** (cross-repo audit at `pheno-harness/_cockpit/XREPO_BACKLOG.json`).
- **Recovery branch policy:** archive, never delete (per `pheno-harness/AGENTS.md §10.5`).
- AMC / Agentora remains paused per `pheno-harness/AGENTS.md §3.2`.
- Branch taxonomy: 8-prefix (`feat/`, `fix/`, `chore/`, `docs/`, `test/`, `refactor/`, `perf/`, `build/`).
- The studio-pivot branch is `feat/comfyui-studio-pivot`; it will land as `main` once Phase 1 tasks 11–25 are green.
