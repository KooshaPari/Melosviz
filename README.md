# Melosviz

Melosviz is a small Python package for music-visualization experiments. The
current codebase is focused on two concrete pieces:

- `melosviz.presets`, which provides mutation-style presets for
  `RenderSpec`
- `melosviz.render.video_exporter`, which turns a `RenderSpec` into a short
  MP4 or WebM clip with FFmpeg

There is no CLI or web app in this repository yet. The supported workflow is
library usage from Python.

## Repository Layout

- `backend/` - installable Python package source, tests, and packaging config
- `docs/` - design/specification notes
- `assets/brand/` - SVG brand assets

## Requirements

- Python 3.10 or newer
- FFmpeg on `PATH`, or set `MELOSVIZ_FFMPEG_BIN` to the binary you want to use

`ffmpeg` is required only for video export. Preset loading and `RenderSpec`
manipulation work without it.

## Install

The package metadata lives in `backend/pyproject.toml`, so install from that
directory:

```bash
cd backend
pip install -e ".[test,lint]"
```

If you only need the runtime package, install the base project instead:

```bash
cd backend
pip install -e .
```

## Usage

### Load and apply a preset

```python
from melosviz.analysis.models import RenderSpec
from melosviz.presets.cinematic import apply

spec = apply(RenderSpec())
print(spec.metadata["preset"])  # cinematic
print(spec.palette)
```

### List built-in presets

```python
from melosviz.presets import list_presets

print(list_presets())
```

### Export a video

```python
from pathlib import Path

from melosviz.analysis.models import RenderSpec
from melosviz.render.video_exporter import export_video

spec = RenderSpec(
    metadata={
        "width": 1280,
        "height": 720,
        "fps": 30,
        "duration": 1.0,
    }
)

output = export_video(spec, format="mp4", output_dir=Path("exports"))
print(output)
```

`export_video` accepts `format="mp4"` or `format="webm"` and returns the
absolute path to the produced file.

### Convert a WAV file into a render spec and export it

```python
from pathlib import Path

from melosviz.analysis.audio import spec_from_wav
from melosviz.presets.cinematic import apply
from melosviz.render.video_exporter import export_video

spec = apply(spec_from_wav(Path("input.wav")))
output = export_video(spec, output_dir=Path("exports"))
print(output)
```

## What Ships Today

- `melosviz.analysis.models.RenderSpec` and `ThemePreset`
- `melosviz.analysis.audio.analyze_wav()` and `spec_from_wav()`
- `melosviz.presets.list_presets()` and `load_preset()`
- `melosviz.presets.cinematic.apply()`
- `melosviz.render.video_exporter.export_video()`
- `melosviz.render.video_exporter.render_audio_video()`

## Notes

- The exporter writes a temporary PNG frame sequence and muxes it with FFmpeg.
- `MELOSVIZ_FFMPEG_BIN` overrides FFmpeg resolution when `ffmpeg` is not on
  `PATH`.
- The package uses only the Python standard library plus `pydantic` at runtime.

