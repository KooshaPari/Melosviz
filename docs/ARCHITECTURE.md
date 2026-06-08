# Melosviz Architecture

## Hexagonal Design (per component)

Each component (`backend`, `desktop`, `sdk`, `web`) follows ports-and-adapters:

### backend/
```
backend/src/
  domain/      — Audio analysis models, render spec domain logic
  ports/       — Repository, notifier, storage traits
  adapters/    — FastAPI adapter, numpy adapter, file storage
  app/         — FastAPI composition root
```

### desktop/
```
desktop/src/
  domain/      — Window state, player logic
  ports/       — Renderer, audio input, event bus traits
  adapters/    — Tauri adapter, electrobun adapter
  app/         — Desktop shell composition root
```

### sdk/python/
```
sdk/python/src/
  domain/      — Analysis algorithms, render pipeline
  ports/       — AudioSource, Renderer traits
  adapters/    — pydub adapter, PIL adapter
  app/         — SDK composition root
```

### sdk/rust/
```
sdk/rust/src/
  domain/      — Low-level DSP, render pipeline
  ports/       — AudioSource, Renderer traits
  adapters/    — rodio adapter, image adapter
  app/         — SDK composition root
```

### web/
```
web/src/
  domain/      — UI state, playback logic
  ports/       — AudioPlayer, Visualizer traits
  adapters/    — Web Audio API adapter, Canvas adapter
  app/         — Vite/React composition root
```

## Shared Contracts

All components communicate via these shared interfaces:
- `AudioSource`: stream of frequency/amplitude data
- `Renderer`: consumes audio data, produces visual frames
- `RenderSpec`: JSON-serializable visual configuration

## Cross-Component Data Flow

```
Input Audio
  -> backend: analysis (FFT, beat detection)
  -> backend: emit RenderSpec
  -> web/desktop: consume RenderSpec
  -> web/desktop: render frames via Renderer port
```
