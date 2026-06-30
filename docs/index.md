# Melosviz Docs Index

This directory contains the full specification, ADR records, traceability matrix,
and acceptance material for MelosViz.

## Architecture Decision Records

- [`adr/0003-spec-first-conductor.md`](adr/0003-spec-first-conductor.md) - ADR 0003: Spec-First Conductor over Pro Toolchain (10 principles; MV-FR-A01–A10)

## Traceability

- [`TRACEABILITY.md`](TRACEABILITY.md) - Bidirectional traceability matrix (Rev 2; 49 MV-FR-* IDs; 100% documented)
- [`COMPLETENESS.md`](COMPLETENESS.md) - Feature completeness audit (Rev 2; 88% shipped; traceability 100%)

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

## Current Scope

- Python package source lives under `backend/src/melosviz`
- The package exposes preset helpers, audio analysis helpers, and an FFmpeg
  exporter
- There is no published application shell or command-line interface yet

