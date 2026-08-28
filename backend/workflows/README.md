# ComfyUI Workflows (shipped)

Default workflow templates that the ComfyUI adapter (`melosviz.render.comfyui_adapter`)
loads via `str.format_map` substitution. Each `{placeholder}` in the JSON is filled
from the per-scene fields in your `RenderSpec` (see `melosviz.analysis.models.RenderSpec`).

| File | Purpose | Required ComfyUI nodes |
|------|---------|------------------------|
| `sdxl_image.json` | txt2img stills (album art, intro cards) | KSampler + CheckpointLoaderSimple + CLIPTextEncode + EmptyLatentImage + VAEDecode + SaveImage |
| `wan_video.json` | text-to-video short clips (Wan 2.1 5B / 14B) | WanVideoSampler + WanVideoModelLoader + WanVideoTextEncode + WanVideoEmptyLatent + WanVideoDecode + VHS_VideoCombine |

## Placeholders

| Placeholder | Default | Notes |
|-------------|---------|-------|
| `{prompt}` | "" | CLIP / Wan text encoder input |
| `{negative}` | "lowres, blurry, watermark" | negative prompt |
| `{seed}` | 0 | sampler seed (per-scene beat-indexed) |
| `{steps}` | 28 (image) / 20 (video) | sampler steps |
| `{cfg}` | 5.5 / 6.0 | classifier-free guidance |
| `{sampler}` | euler_ancestral / euler | KSampler name |
| `{scheduler}` | normal | scheduler |
| `{width}` | 1280 | output width |
| `{height}` | 720 | output height |
| `{frames}` | 48 | video frames per clip (2 s @ 24fps) |
| `{fps}` | 24 | output frame rate |

## Custom workflows

Drop your own `*.json` files here and reference them via:

```bash
MELOSVIZ_COMFYUI_WORKFLOWS_DIR=/path/to/my/workflows viz render track.wav --real
```

The adapter looks up `workflows/<scene_type>.json` by default. To use a custom
template per-scene, set the `scene.workflow` field on the scene dict and the
adapter will fall back to that name.

## Reset to defaults

```bash
rm -rf backend/workflows/*
viz comfyui init --target backend/workflows
```
