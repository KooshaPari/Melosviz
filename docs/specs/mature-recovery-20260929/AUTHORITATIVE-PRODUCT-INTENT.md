# Authoritative product intent — 2026-09-30

Authority: **CURRENT USER INTENT**, stated directly in the active recovery conversation. This supersedes prior recovery notes that marked the core product identity as unresolved. It does not automatically accept every historical implementation or assistant proposal.

## Melosviz

Melosviz is a **multi-scene, audio-conditioned visual generation and programming system**. A scene is a work unit inside a composition, not the product boundary.

Given an audio file plus user/programmatic configuration, analysis, tailoring and other authored controls, Melosviz should generate a unique multi-scene visual composition whose structure is meaningfully aligned with the audio: beat/rhythm where applicable, semantic/musical structure where applicable, and explicit authored intent where supplied.

The same mature system must be capable of projecting that authored/generative composition into multiple use contexts rather than being defined by one renderer or one export format:
- multi-minute graphics-driven music-video / YouTube visualization;
- short-form and other edited linear outputs;
- longer-form visualizations;
- real-time/live audience/festival-style operation where the accepted stage and renderer support it.

The product therefore owns **composition across scenes and time**: scene planning/identity, audio/time semantics, transitions, generation/programming, revision, tool/render projection, assembly/playout and evidence. Correctly rendering one isolated scene is necessary but never sufficient product closure.

The current ComfyUI/DCC/studio conductor is an implementation family within this horizon, not the product definition. Likewise the historical browser/R3F implementation may be superseded without superseding programmable/hybrid/live outcomes.

## Architectural consequences

1. Scene identity must survive same-backend multi-scene compositions; scene_type is not identity.
2. Selection/partial rerender must operate on composition scene work, not silently regenerate the whole sequence.
3. Assembly/playout is first-class: generated scene artifacts must become an ordered composition aligned to the audio.
4. Transitions and neighboring-scene effects are composition semantics, not post-hoc file concatenation only.
5. Offline linear render and real-time/live playout are projections over shared authored/audio/scene intent where feasible; they need not share every renderer.
6. Audio alignment has multiple explicit contracts: editorial timing/sections, beat/rhythm anchors, semantic/music-structure cues, and generated motion/content alignment. Do not collapse these into a single BPM claim.
7. Human GUI and programmatic/API control are complementary views over durable project intent; neither should manufacture truth from process exit or directory layout.
8. Mature architecture should maximize reuse of existing MIR, timeline, scene/DCC and rendering primitives where they faithfully preserve this product contract.

## Stage implication

The earliest useful product is still multi-scene: a narrow but real audio → planned scenes → distinct generated artifacts → ordered accepted composition journey. A one-scene demo is a primitive/integration test, not Melosviz CVP.
