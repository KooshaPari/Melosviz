# Melosviz mature contract ontology and journeys — authority-anchored 2026-09-30

Authority: current explicit user clarification in `AUTHORITATIVE-INTENT-20260930.md`. This replaces the earlier candidate framing that treated multi-scene/hybrid scope as potentially historical-only. Implementation details remain subject to SOTA/design gates.

## Product identity

Melosviz is an **audio-conditioned programmable multi-scene visual composition and production/runtime system**. Its product unit is not an isolated generated scene. It is a temporally coherent audiovisual composition/session whose scenes may use different representations, renderers and generation methods while remaining aligned to one audio work and one accepted creative/programmatic intent.

Representative mature use projections:
- multi-minute music-video / YouTube visualization;
- short-form derived output;
- other offline long-form audiovisual work;
- real-time/live-audience visual performance where qualified.

A three-minute graphics-driven music video is a representative product-scale workload, not a requirement that every work be exactly that duration.

## Core ontology

```
Composition / Project
  ├─ accepted creative + programmable intent
  ├─ source audio + immutable asset identity
  ├─ analysis
  │    ├─ sample/timebase
  │    ├─ beat/rhythm/onset structure + uncertainty
  │    ├─ musical/section structure
  │    └─ semantic/lyric/mood/context signals where applicable
  ├─ timeline / sequence
  │    ├─ SceneInstance[0..N]
  │    │    ├─ revision
  │    │    ├─ start/end/transition relationship
  │    │    ├─ scene program/spec
  │    │    ├─ representation/render backend selection
  │    │    ├─ assets/references
  │    │    └─ execution attempts → artifacts → evidence
  │    └─ cross-scene continuity/coherence constraints
  ├─ offline projection
  │    └─ ordered accepted artifacts → transition/assembly/master → deliverable
  └─ live projection
       └─ same accepted composition/time/scene intent → bounded-latency runtime/adapters
```

Scene type/backend is **not identity**. For the current studio pipeline, existing `scene_index` is the minimum viable work identity; a more durable cross-revision scene ID is introduced only if requirements prove index stability insufficient.

Beat alignment, editorial timing alignment, semantic alignment and generative motion alignment are different claims with different evaluators. Storing BPM does not prove them all.

## Product projections

| Projection | Principal obligation |
|---|---|
| Creative/programmatic intent | Human/agent can specify constraints, structure, scene behavior and accepted overrides without losing authority/provenance |
| Audio intelligence | Produce evidence-bound timing/structural/semantic signals with uncertainty and stable source identity |
| Multi-scene planning | Generate/revise an ordered scene sequence appropriate to the audio and requested output/use |
| Scene execution | Execute heterogeneous scene programs without losing scene identity or duplicating work |
| Cross-scene composition | Maintain transitions, ordering, timing, continuity and composition-level coherence |
| Review/revision | Human/agent can inspect and modify one or more scenes and understand the exact delta |
| Offline delivery | Assemble/master independently verified scene artifacts into intended short/long-form media |
| Live runtime | Project accepted scene/timeline intent into a real-time execution model with explicit latency/failure semantics |
| Evidence/recovery | Distinguish plan, execution, artifact validation, creative acceptance, cache reuse and final acceptance across restarts/workers |

## Normative mature journeys

**M-J-COMPOSE-LONGFORM:** import an audio work; derive/review timing + semantic structure; create a multi-scene composition; generate heterogeneous scenes; independently verify them; assemble in intended order with intended audio; review and export a multi-minute deliverable.

**M-J-REVISE-SCENE:** open a durable composition; change one scene or transition; preserve the revision delta; recompute only the work required by accepted dependency policy; reassemble and prove the new composition contains the new scene while unaffected evidence remains valid only when identity matches.

**M-J-SHORTFORM:** derive/reframe a selected temporal/semantic region or alternate scene projection for a short-form target while retaining provenance to the source composition/audio and explicitly handling aspect/timing changes.

**M-J-LIVE:** load an accepted composition/program and audio/live timing source; schedule/generate/project scene state in real time; tolerate/declare latency/degradation and transition behavior; retain enough runtime evidence for operator diagnosis. Exact live latency and renderer guarantees remain to be researched/accepted.

**M-J-HYBRID:** use accepted heterogeneous representations/renderers in one composition and preserve semantic/timeline identity across them. Historical scanner/photo/mesh/splat details remain candidates to reconcile, not automatically mandatory implementations.

**M-J-RECOVER:** replace a renderer/worker/application after failure and resume from durable project/job/evidence truth without treating stale cache, a plan, or an old revision as accepted current output.

## Stage projections

**CVP:** a small but real **multi-scene** composition on one qualified audio fixture and narrow renderer set, using the mature scene/time/evidence spine. Single-scene output alone is not a Melosviz CVP.

**MVP:** closes composition + revision + offline delivery with at least one heterogeneous or meaningfully distinct scene workflow and independently verified assembly.

**Beta:** widens renderer/scene-program adapters, quality/creative review, recovery, output formats and selected live/runtime experiments.

**GA:** closes accepted offline production/support/security/accessibility/reproducibility obligations for supported configurations.

**Mature:** full recovered offline + selected live/hybrid contract. Live may have a separate support matrix; it must not be faked by calling offline frame generation “real-time.”

## Current implementation consequences

M-F13/M-F16/M-F18 are core-spine failures, not peripheral defects: iteration is duplicated, scene selection is inert, scene-type collapses results, and generated artifacts do not reach assembly. M-E02 is therefore a critical-path architecture repair experiment.

“Stub breadth; mature spine” here means: support a narrow set of scene generators initially, but make composition identity, audio timebase, scene identity/revision, ordering, execution result, artifact/evidence and assembly truthful from the beginning.


## Authoritative horizon correction — 2026-09-30

Current user intent resolves Melosviz as a multi-scene, audio-conditioned visual composition/generation system. Replace any reading of this document that treats a scene renderer as the mature product.

The canonical composition spine is:

`AudioSource + Analysis/Annotations + ProjectRevision + Ordered SceneWork + Transitions/Neighbor Semantics + Generative/Programmed Intent + Render/Playout Projections + Evidence`.

A linear music-video export and a live/festival playout are projections over this spine where applicable. They may use different renderer/runtime implementations while sharing accepted scene/audio/program intent.

**Editorial bootstrap:** OpenTimelineIO is a candidate projection/interchange layer, not the canonical product database. Its RationalTime/TimeRange, tracks, clips, transitions, markers and external media references map well to accepted rendered/editable timeline state. Melosviz-specific generative scene programs, audio-analysis uncertainty, backend/workflow/model identity, live controls and evidence remain outside ordinary OTIO semantics and should be preserved in canonical product state or explicit metadata/adapters.

The earliest usable stage must contain multiple scenes. A single-scene renderer success is an integration primitive.
