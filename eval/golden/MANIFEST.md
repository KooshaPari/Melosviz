# Golden RenderSpec corpus

Synthetic WAVs (deterministic tones) and expected normalized RenderSpec JSON.

| Case | WAV | Expected |
|------|-----|----------|
| `sine_440hz_1s` | `wav/sine_440hz_1s.wav` | `expected/sine_440hz_1s.json` |
| `sine_220hz_2s` | `wav/sine_220hz_2s.wav` | `expected/sine_220hz_2s.json` |
| `silence_1s` | `wav/silence_1s.wav` | `expected/silence_1s.json` |

Regenerate:

```bash
cd backend && UPDATE_GOLDEN=1 python -m pytest tests/test_golden_corpus.py -q
```

Normalization strips `metadata.source_audio` and rounds floats to 6 decimals.
