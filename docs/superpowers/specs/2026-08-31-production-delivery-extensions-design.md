# Production Delivery Extensions Design

**Status:** Approved for implementation planning

**Date:** 2026-08-31

**Scope:** Director LLM admission control, per-clip visual-diff metadata,
scheduled GPU smoke coverage, and festival-VJ exports in `final.zip`.

## Context

MelosViz already generates deterministic storyboards, routes scenes through
studio adapters, records per-clip provenance, and exposes a `viz ship` command.
Four production-delivery gaps remain:

1. The Director makes an unguarded synchronous LLM request. It has no shared
   backpressure, 429 retry policy, queue bound, or cost ceiling.
2. Clip provenance does not give reviewers a compact comparison between the
   rendered artifact, source prompt, and its position on the timeline.
3. `.github/workflows/gpu-smoke.yml` can only be started manually.
4. The online `viz ship` path writes `manifest.json` but does not create
   `final.zip`, and it does not provide portable cue artifacts for festival VJs.

The implementation must preserve the deterministic template fallback and must
not add a required external service or Python dependency.

## Goals

- Bound concurrent Director LLM work with a process-local FIFO queue.
- Enforce configurable request-rate and estimated-cost ceilings before an LLM
  call begins.
- Retry rate-limited requests without changing models.
- Add deterministic visual-diff metadata and review thumbnails to clip
  provenance.
- Run the existing GPU smoke workflow weekly while retaining manual dispatch.
- Produce a real `final.zip` for rendered jobs.
- Include one SVG cue card and one Lottie JSON timing composition per shot in a
  `vj/` directory in the ZIP.
- Cover every new behavior with test-first unit or acceptance tests.

## Non-goals

- Distributed queueing across hosts or processes.
- Exact reconciliation with a provider invoice.
- Automatic model switching.
- Raster-to-vector tracing of rendered frames.
- A new web UI for reviewing visual diffs.
- YouTube or Vimeo publishing.

## Architecture

The work is divided into four independently testable units and one narrow CLI
integration point:

```text
Director
  -> DirectorLLMGate
     -> FIFO admission + rate window + cost reservation
     -> existing OpenAI-compatible HTTP request

Rendered clip
  -> ClipProvenance
     -> VisualDiffBuilder
        -> representative frame when ffmpeg can decode the artifact
        -> deterministic SVG review card

viz ship <job_dir>
  -> VJExporter
     -> per-shot SVG + Lottie JSON
  -> PackageWriter
     -> manifest.json + media + vj/* -> final.zip

GitHub scheduler
  -> existing offline GPU smoke test
```

All helpers use the Python standard library. Subprocess use is limited to the
already-supported `ffmpeg` executable, and every ffmpeg-dependent path has a
deterministic SVG fallback.

## 1. Director LLM admission and budget guard

### Component boundary

Create `backend/src/melosviz/llm/admission.py`. It owns queueing, rate-window
accounting, retry delays, and cost reservations. `director.py` remains
responsible for request construction and response parsing.

The public types are:

- `LLMAdmissionConfig`: validated values loaded from the environment.
- `LLMCostEstimate`: estimated input tokens, reserved output tokens, and USD.
- `LLMAdmissionGate`: a process-local FIFO gate shared by Director instances.
- `LLMAdmissionError`: a controlled rejection that causes template fallback.

The gate accepts injected monotonic-clock and sleeper functions so rate-window
and retry tests do not wait in real time.

### Configuration contract

| Environment variable                  | Default | Meaning                                                 |
| ------------------------------------- | ------: | ------------------------------------------------------- |
| `MELOSVIZ_LLM_REQUESTS_PER_MINUTE`    |    `30` | Starts allowed in a rolling 60-second window            |
| `MELOSVIZ_LLM_MAX_CONCURRENCY`        |     `2` | Requests simultaneously inside the HTTP section         |
| `MELOSVIZ_LLM_MAX_QUEUE`              |    `32` | Waiting callers before fail-closed fallback             |
| `MELOSVIZ_LLM_MAX_RETRIES`            |     `3` | Additional attempts for 429 and retryable 5xx responses |
| `MELOSVIZ_LLM_COST_CAP_USD`           |  `1.00` | Process-local reserved plus actual cost ceiling         |
| `MELOSVIZ_LLM_INPUT_USD_PER_MILLION`  |   unset | Provider price supplied by the operator                 |
| `MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION` |   unset | Provider price supplied by the operator                 |
| `MELOSVIZ_LLM_MAX_OUTPUT_TOKENS`      |  `2048` | Output reservation used for the preflight estimate      |

The cost estimator conservatively approximates input tokens as
`ceil(UTF-8 byte length / 4)`. It reserves the configured maximum output tokens
before admission. After a response, provider `usage.prompt_tokens` and
`usage.completion_tokens` replace the estimate when present; otherwise the
reservation remains the recorded charge.

If either price is missing, malformed, or negative, LLM refinement is rejected
before network access. This fail-closed rule guarantees that enabling a novel
model cannot silently bypass the dollar ceiling. Operators who want LLM
refinement must explicitly provide both prices.

### Queue and rate behavior

Each caller receives an increasing ticket. A caller may enter only when:

- its ticket is first in the FIFO queue;
- fewer than `MAX_CONCURRENCY` callers are active;
- the rolling request window has capacity; and
- reserving its estimated cost stays at or below the cap.

When the queue is full or the cost reservation would exceed the cap, the gate
raises `LLMAdmissionError`. `Director._maybe_refine_with_llm` logs one warning
and returns the unchanged deterministic scene prompts.

HTTP 429 responses honor a numeric `Retry-After` header. If the header is absent
or invalid, delays are `1`, `2`, and `4` seconds, capped at 30 seconds. HTTP
500, 502, 503, and 504 use the same fallback delays. Other 4xx responses and
response-schema failures do not retry. Retrying never changes the configured
model.

## 2. Per-clip visual diffs

### Component boundary

Create `backend/src/melosviz/conductor/visual_diff.py`. It accepts a completed
clip provenance record and its scene output directory and returns a
JSON-serializable `visual_diff` object. Provenance serialization remains owned
by `conductor/provenance.py`; the orchestrator calls the builder after the
artifact is known.

### Manifest schema

Each completed clip adds:

```json
{
  "visual_diff": {
    "schema_version": "1.0",
    "rendered": {
      "path": "scene_002/clip.mp4",
      "sha256": "...",
      "preview_path": "scene_002/visual-diff-frame.png",
      "preview_sha256": "..."
    },
    "prompt": {
      "text": "...",
      "sha256": "..."
    },
    "timeline_thumbnail": {
      "path": "scene_002/visual-diff.svg",
      "sha256": "...",
      "start_seconds": 20.0,
      "end_seconds": 36.0,
      "beat_seconds": [20.0, 20.48]
    }
  }
}
```

Paths stored in manifests are relative to the job directory when possible.
Hashes are SHA-256 over file bytes and normalized UTF-8 prompt text.

For decodable video or image artifacts, ffmpeg writes a single representative
PNG frame. The SVG review card references that PNG and overlays the scene name,
prompt excerpt, time range, and beat ticks. If the artifact is absent, is an
offline plan, or ffmpeg cannot decode it, the SVG uses a palette-derived color
field instead. Missing previews never fail the render.

The SVG is generated without scripting or external URLs. XML text is escaped,
prompt excerpts are bounded, numeric values are normalized, and the same inputs
produce byte-identical SVG output.

## 3. Weekly GPU smoke workflow

Update `.github/workflows/gpu-smoke.yml` to support both:

- existing `workflow_dispatch` inputs; and
- `schedule` with cron `17 8 * * 1` (Mondays at 08:17 UTC).

Scheduled runs use Python 3.12 and install ffmpeg. Manual runs retain their
selected Python version and ffmpeg choice. Event-specific values are normalized
into job-level environment variables so a scheduled event never evaluates a
missing dispatch input as an empty version or false installation choice.

The workflow remains offline (`MELOSVIZ_COMFYUI_OFFLINE=1`) and continues to run
only `tests/cli/test_gpu_smoke.py` with the `slow` marker. This scheduled check
is CI evidence for artifact topology, not proof that a physical GPU backend was
exercised.

## 4. Festival-VJ cue export

### Component boundary

Create `backend/src/melosviz/export/vj.py`. It converts shot records into
portable cue artifacts without claiming to vectorize rendered video.

Shot metadata is discovered in this order:

1. a multi-shot plan containing a top-level `shots` array;
2. `storyboard.json`, with each scene treated as one shot; or
3. completed clip provenance, with each clip treated as one shot.

If none is present, media deliverables are converted into minimal cues ordered
by normalized relative path. Thus an online shipment always receives a `vj/`
package even when upstream shot planning metadata was not retained.

### SVG cue card

Each `vj/shot-SSSS-HH.svg` contains:

- scene and shot indices;
- start time and duration;
- scene label and camera motion;
- a bounded prompt summary;
- palette swatches;
- beat ticks across a normalized timeline; and
- an optional relative reference to the visual-diff preview frame.

The SVG is static, script-free, uses only local references, and is deterministic.

### Lottie composition

Each matching `vj/shot-SSSS-HH.lottie.json` is a Lottie 5.12 JSON composition
with:

- the shot width, height, and fps;
- in/out frames derived from shot duration;
- marker records for shot start, beats, and shot end;
- text layers for shot identity and prompt summary; and
- shape layers using the shot palette.

The Lottie file is timing and cue metadata suitable for VJ tooling. It does not
embed or trace rendered footage.

## 5. Shipping integration

Refactor the packaging portion of `backend/src/melosviz/cli/main.py` into a
small helper module, `backend/src/melosviz/export/package.py`, while retaining
the existing `viz ship <job_dir>` CLI contract.

The package writer:

1. discovers supported media and caption deliverables;
2. creates visual/VJ artifacts;
3. writes `deliverables/manifest.json` atomically;
4. creates `<job_dir>/final.zip` through a temporary sibling file; and
5. replaces the destination ZIP only after the archive closes successfully.

Archive names are normalized relative paths. Duplicate basenames do not
overwrite each other, the ZIP never includes itself or its temporary file, and
entries are sorted for reproducibility. ZIP metadata uses a fixed timestamp so
unchanged inputs produce a byte-stable archive.

Offline behavior remains valid: no-media jobs receive the existing README and
manifest plus an empty `vj/manifest.json`. Online behavior is corrected to
create the actual ZIP and report its path and byte size in CLI JSON output.

## Error handling

- LLM admission, budget, retry, or parsing failures preserve template prompts.
- A failed preview extraction records the reason in visual-diff metadata and
  emits the deterministic SVG fallback.
- A malformed optional storyboard or shot-plan file is ignored with a warning;
  provenance or media fallback remains available.
- A failure while creating `final.zip` leaves any previous valid ZIP untouched
  and removes only the explicitly named temporary sibling.
- Invalid paths and archive traversal components are rejected before packaging.
- Scheduled workflow failures are reported by GitHub Actions and are not
  described as local test failures or physical-GPU failures.

## Testing strategy

Implementation follows one red-green-refactor cycle per behavior.

### Director admission tests

- FIFO order under concurrent callers.
- queue-full rejection without network access.
- rolling-window delay using a fake clock.
- cost-cap rejection and reservation release.
- missing price configuration fails closed.
- 429 honors `Retry-After` and retains the same model.
- retryable 5xx backoff and exhausted-retry fallback.
- non-retryable 4xx performs one attempt.
- provider usage replaces the estimate.

### Visual-diff tests

- stable prompt and artifact hashes.
- representative-frame success through an injected extractor.
- deterministic SVG fallback without media or ffmpeg.
- XML escaping and bounded prompt content.
- relative paths and normalized timeline values.
- provenance manifest round-trip with `visual_diff`.

### Workflow tests

- YAML has both dispatch and schedule triggers.
- scheduled defaults resolve to Python 3.12 with ffmpeg enabled.
- the smoke command and offline environment remain unchanged.

### VJ and packaging tests

- shot-plan, storyboard, provenance, and media fallback discovery.
- deterministic SVG and valid Lottie JSON per shot.
- beat markers and frame calculations.
- online `viz ship` creates a readable `final.zip` containing media,
  manifest, SVG, and Lottie files.
- duplicate media basenames remain distinct.
- offline packaging retains README and manifest behavior.
- a packaging failure does not overwrite a prior valid ZIP.
- the three-minute pipeline acceptance test verifies ZIP contents.

Before push or pull-request creation, run the focused suites, the complete
backend test suite, workflow lint available in the repository, and the existing
CLI GPU smoke test locally in offline mode. Hosted qgate, security, review, and
scheduled-run results remain separate merge gates.

## Acceptance criteria

1. Concurrent Director calls cannot exceed configured queue, concurrency, rate,
   or cost limits.
2. A 429 response waits and retries without model substitution.
3. Guard failure leaves storyboard timing, tools, and template prompts intact.
4. Every completed clip manifest contains rendered, prompt, and timeline visual
   diff fields, with a deterministic SVG available even without ffmpeg.
5. The GPU smoke workflow supports manual and weekly scheduled execution.
6. A rendered `viz ship` invocation creates a readable `final.zip`.
7. The ZIP contains deterministic per-shot SVG and Lottie cue artifacts under
   `vj/`.
8. No new required third-party Python package is introduced.
9. Local verification and hosted GitHub status are reported independently.
