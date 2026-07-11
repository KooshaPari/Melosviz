# Melosviz Docs Index

This directory contains the full specification, ADR records, traceability matrix,
and acceptance material for MelosViz.

## Architecture Decision Records

- [`adr/0003-spec-first-conductor.md`](adr/0003-spec-first-conductor.md) - ADR 0003: Spec-First Conductor over Pro Toolchain (10 principles; MV-FR-A01–A10)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - surface / role map
- [`VISUAL_SPEC.md`](VISUAL_SPEC.md) - brand / motion / theme contract
- [`visual/IDENTITY.md`](visual/IDENTITY.md) · [`visual/PROVENANCE.md`](visual/PROVENANCE.md)
- [`PACKAGING.md`](PACKAGING.md) · [`AIRGAP.md`](AIRGAP.md) · [`DISTRIBUTION_POLICY.md`](DISTRIBUTION_POLICY.md)
- [`a11y/FOCUS.md`](a11y/FOCUS.md) · [`a11y/CONTRAST.md`](a11y/CONTRAST.md)
- [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md) - lockfiles + dependency-confusion policy

## Traceability

- [`TRACEABILITY.md`](TRACEABILITY.md) - Bidirectional traceability matrix (Rev 2; 49 MV-FR-* IDs; 100% documented)
- [`COMPLETENESS.md`](COMPLETENESS.md) - Feature completeness audit (Rev 2; 88% shipped; traceability 100%)
- [`functional_requirements.md`](functional_requirements.md) - FR catalog
- [`WORK_DAG.md`](WORK_DAG.md) - claimable task DAG
- [`EVAL.md`](EVAL.md) - eval / golden / Harbor / load index
- [`USER_JOURNEYS.md`](USER_JOURNEYS.md) - outside-in journey / friction map
- [`ENV.md`](ENV.md) - 12-factor env catalog
- [`UNINSTALL.md`](UNINSTALL.md) - uninstall / cleanup matrix
- [`SLO.md`](SLO.md) - bridge SLO / error-budget sketches

## Functional Specifications

- [`specs/SPEC.md`](specs/SPEC.md) - functional requirements and traceability (FR-1–FR-6; preset + video exporter)
- [`specs/acceptance/presets.feature`](specs/acceptance/presets.feature) -
  acceptance scenarios for presets
- [`specs/acceptance/video_exporter.feature`](specs/acceptance/video_exporter.feature) -
  acceptance scenarios for the video exporter
- [`specs/acceptance/test_presets_acceptance.py`](specs/acceptance/test_presets_acceptance.py) -
  step definitions / harness for preset scenarios
- [`specs/acceptance/test_video_exporter_acceptance.py`](specs/acceptance/test_video_exporter_acceptance.py) -
  step definitions / harness for video exporter scenarios

## Ops

- [`OBSERVABILITY.md`](OBSERVABILITY.md) · [`PACKAGING.md`](PACKAGING.md) · [`LOCAL_RUN.md`](LOCAL_RUN.md)

## Current Scope

- Python package source lives under `backend/src/melosviz`
- Electrobun desktop + FastAPI bridge + R3F web + Rust MIR/wgpu
- Top-level product spec: [`../SPEC.md`](../SPEC.md)
