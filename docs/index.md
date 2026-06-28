# Melosviz Docs Index

This directory currently contains the functional specification and acceptance
material for the Python package.

## Documents

- [`specs/SPEC.md`](specs/SPEC.md) - functional requirements and traceability
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

