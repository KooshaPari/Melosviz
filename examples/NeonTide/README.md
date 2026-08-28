# NeonTide — example 3-minute music-video pipeline run

A complete, CC-licensed reference example for the MelosViz studio pipeline.

## Files

- `song.lrc` — lyrics in LRC format with phrase-level timing.
- `moodboard.json` — concept + subject + environment + palette seeds + reference-image list (5 free/libre refs).
- `references/` — reference images (paths only — point at your own CDN / generation output; the orchestrator only cares about the path list).
- `render_pipeline.sh` — one-command shell driver that runs the full studio pipeline against the references + lyrics and produces `output/storyboard.json`, `output/master/`, and `output/final.zip`.

## What it produces

A festival / club / YouTube-grade deliverable for "Neon Tide":

| Format              | Target                    | Why                                      |
| ------------------- | ------------------------- | ---------------------------------------- |
| ProRes 422 HQ MP4   | Festival screens          | 10-bit 4:2:2, colorist-friendly          |
| H.264 1080p MP4     | YouTube + Vimeo + IG feed | max-compat                               |
| H.264 1080×1920 MP4 | Club PA screens (9:16)    | vertical, fits VJ walls                  |
| Master WAV          | Festival sound mix        | stems already split by `audio_finishing` |
| SRT captions        | YouTube + accessibility   | driven by `song.lrc`                     |
| Storyboard.json     | Re-render / art-director  | keeps every edit + provenance            |
| Per-clip JSON       | Provenance / license      | clip-by-clip provenance JSONs            |

## How to run

### Online (ComfyUI + optional C4D + UE + AE + DaVinci)

```bash
# 1. bring up the dev stack
make dev-up

# 2. with a real track.wav in ../input/, run:
make dev-pipeline TRACK=../input/track.wav \
                CONCEPT="$(cat concept.txt)" \
                PALETTE="#0d0d10 #ff2bd6 #22d3ee #c084fc #f0f0f8"
```

### Offline (workflow JSONs only — no GPU)

```bash
MELOSVIZ_COMFYUI_OFFLINE=1 \
LYRICS=$(pwd)/song.lrc \
MOOD_BOARD=$(pwd)/moodboard.json \
CONCEPT="neon noir underwater city" \
BPM=124 \
PALETTE="#0d0d10 #ff2bd6 #22d3ee #c084fc #f0f0f8" \
bash render_pipeline.sh
```

## License

- **Lyrics** (`song.lrc`): CC-BY 4.0 (Koosha Pari)
- **Mood board** (`moodboard.json`): CC-BY 4.0 (Koosha Pari)
- **Reference images** (`./refs/*`): bring-your-own (placeholder paths)

The deliverable metadata (`output/manifest.json`) carries the license stack
forward so any festival / club / YouTube recipient can attribute correctly.
