# melosviz-web

React/R3F browser surface for MelosViz. Provides a file-picker panel to submit an audio path to the FastAPI bridge sidecar (`/api/analyze`), displays the returned RenderSpec summary via `SpecViewer`, and renders a live Three.js/R3F scene in the right panel — currently a placeholder animated scene that will be driven by RenderSpec keyframes in future workstreams. To run: `bun install && bun dev` (requires the Python bridge sidecar on port 8000 for analysis; the 3D scene runs standalone without it).
