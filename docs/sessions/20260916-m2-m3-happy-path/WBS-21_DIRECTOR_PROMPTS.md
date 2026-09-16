# WBS-21: Director LLM Prompt Documentation

The Director module generates beat-synced scene plans for music-to-video pipelines.
It operates in two modes: **template-only** (default, no LLM) and **LLM-refined**
(when `MELOSVIZ_LLM_ENDPOINT` is set).

---

## 1. Template Prompt Composition

`Director._compose_prompt()` builds deterministic per-scene prompt strings
from concept + archetype. No LLM call is made in this path.

### Prompt Structure

The prompt is a comma-separated string assembled from these pieces:

```
{concept}, scene {label}, lighting: {lighting}, key of {key}, {prompt_tail}
```

Optional suffixes (appended when present):

| Suffix | When | Example |
|--------|------|---------|
| `look: {style}` | mood-board supplied | `look: cyberpunk anime` |
| `depicts: "{lyric}"` | lyric phrase aligned | `depicts: "dancing through the rain"` |
| `mood: {mood}` | lyric mood non-neutral | `mood: melancholic` |
| `subject: {token}` | continuity anchor has subject | `subject: a woman with neon tattoos` |
| `environment: {token}` | continuity anchor has env | `environment: underwater city` |
| `smooth motion, no jitter` | scene_type is comfyui_video or unreal_cinematic | (quality hint) |
| `poster-quality composition, rule of thirds` | scene_type is comfyui_image | (quality hint) |
| `bold type, geometric shapes, beat-driven timing` | scene_type is motion_graphics_beat_sync | (quality hint) |

### Lighting Bias

Lighting is derived from concept keyword matching via `_CONCEPT_KEYWORD_BIAS`:

| Concept Keyword | Lighting | Palette Suffix |
|----------------|----------|----------------|
| neon | neon noir | magenta+cyan |
| city | urban night | amber+teal |
| forest | dappled | moss+sunbeam |
| underwater | caustic | aqua+indigo |
| desert | harsh sun | ochre+sienna |
| space | rim light | violet+gold |
| dance | strobe | magenta+white |
| love | soft warm | rose+cream |
| loss | cold blue | steel+ash |
| festival | festival | fuchsia+lime |

If no keyword matches, lighting defaults to `"cinematic"`.

---

## 2. Archetype Defaults

Each segment label maps to a default scene type, camera move, and prompt tail:

| Label | Scene Type | Camera | Prompt Tail | Audio-Video |
|-------|-----------|--------|-------------|-------------|
| intro | comfyui_image | slow_dolly_in | title card, cinematic letterbox, breathing room | -- |
| verse | comfyui_video | handheld_orbit | intimate close-ups, naturalistic light, subtle motion | -- |
| chorus | comfyui_video | whip_pan_burst | wide vista, saturated palette, hero pose, dynamic camera | Seedance A2V (requires character) |
| drop | unreal_cinematic | impact_punch_in | kinetic impact frame, hyper-detailed, lens flare, pyro | Wan S2V (always) |
| bridge | motion_graphics_beat_sync | parallax_scroll | type-led transition, geometry morph, beat-synced type reveal | -- |
| breakdown | comfyui_video | slow_push_in | long take, soft focus, dreamlike, ambient texture | -- |
| outro | comfyui_image | slow_pull_back | fade to black, end credits plate, restrained motion | -- |
| unknown | comfyui_image | static_hero | balanced framing, neutral light | -- |

### Audio-Video Routing Logic

- **drop** always routes to `comfyui_audio_video_wan` (Wan S2V — any audio drives motion).
- **chorus** routes to `comfyui_audio_video_seedance` (Seedance A2V) only when:
  - The continuity anchor has a `subject_token`, OR
  - The user explicitly set `--audio-conditioned-video`.

### Anti-Repeat

Successive scenes with the same `scene_type` are automatically swapped to an
alternate type via `_alternate_scene_type()` to avoid visual monotony.

---

## 3. LLM Refinement (Optional)

When `MELOSVIZ_LLM_ENDPOINT` is set, the Director calls an OpenAI-compatible
chat endpoint to rewrite template prompts into a cohesive visual story.

### System Prompt

```
You are a music-video art director. Rewrite the following scene prompts
so they read as a single cohesive visual story. Keep timing, scene_type,
camera, and palette EXACTLY. Return valid JSON:
{"rewrites": [{"index": int, "prompt": str}]}
```

### User Message

JSON payload containing:
```json
{
  "concept": "<user concept>",
  "scenes": [
    {
      "index": 0,
      "label": "intro",
      "scene_type": "comfyui_image",
      "camera": "slow_dolly_in",
      "prompt": "<template prompt>"
    }
  ]
}
```

### Constraints

- **response_format**: `json_object` (structured output)
- **temperature**: 0.7
- **timeout**: configurable via `MELOSVIZ_LLM_TIMEOUT_S` (default 30s)
- **Model**: configurable via `MELOSVIZ_LLM_MODEL` (default from `DEFAULT_LLM_MODEL`)
- **Retries**: via `LLMAdmissionGate` (exponential backoff, respects `Retry-After`)
- **Fallback**: on any error (network, admission, malformed), original template prompts
  are returned unchanged. The Director never crashes an operator's run.

### Response Format Expected

```json
{
  "rewrites": [
    {"index": 0, "prompt": "rewritten prompt for scene 0"},
    {"index": 1, "prompt": "rewritten prompt for scene 1"}
  ]
}
```

Only scenes present in the `rewrites` array are updated; others keep their
template prompts.

---

## 4. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MELOSVIZ_LLM_ENDPOINT` | (none) | OpenAI-compatible chat completions URL |
| `MELOSVIZ_LLM_MODEL` | `DEFAULT_LLM_MODEL` | Model name for LLM calls |
| `MELOSVIZ_LLM_KEY` | (none) | API key (sent as `Authorization: Bearer`) |
| `MELOSVIZ_LLM_TIMEOUT_S` | `30` | Request timeout in seconds |

---

## 5. Pipeline Position

```
analyze (WAV → RenderSpec)
  → storyboard (RenderSpec → Storyboard via Director)
    → generate (Storyboard → scene assets)
```

The Director sits at step 2. It consumes `DirectorRequest` (built from
`RenderSpec` + CLI flags) and produces a `Storyboard` containing one
`StoryboardScene` per segment, each with:
- `prompt`: the composed/refined prompt string
- `negative`: default negative prompt for the scene type
- `scene_type`: which generator to use
- `camera`: camera movement directive
- `palette`: color palette for this scene
- `timing`: beat grid (bar onsets within the scene)
