# Hexagonal Design Guide

## Principles

1. **Domain is pure** — no IO, no framework imports.
2. **Ports are traits** — define contracts, not implementations.
3. **Adapters implement ports** — one port can have many adapters.
4. **App wires everything** — dependency injection at the composition root.

## Example: Adding a new audio source

1. Define `AudioSource` port in `sdk/*/src/ports/`.
2. Implement `MicrophoneAdapter` in `sdk/*/src/adapters/`.
3. Register in `App::new()` composition root.
4. Swap `MicrophoneAdapter` for `FileAdapter` without changing domain.
