# Golden RenderSpec corpus

Synthetic WAVs (deterministic tones + multi-genre character synthetics) and
expected normalized RenderSpec JSON. Copyright-free stand-ins for real-track
diversity (kick pulse / chord stack / noise burst).

| Case | Character | Expected |
|------|-----------|----------|
| `sine_440hz_1s` | pure tone A4 | `expected/sine_440hz_1s.json` |
| `sine_220hz_2s` | pure tone A3 | `expected/sine_220hz_2s.json` |
| `silence_1s` | silence | `expected/silence_1s.json` |
| `kick_pattern_2s` | electronic / EDM-like pulses | `expected/kick_pattern_2s.json` |
| `chord_cmaj_1s` | harmonic / pop triad | `expected/chord_cmaj_1s.json` |
| `noise_burst_1s` | ambient / texture noise | `expected/noise_burst_1s.json` |

Regenerate:

```bash
cd backend && UPDATE_GOLDEN=1 python -m pytest tests/test_golden_corpus.py -q
```

Normalization strips `metadata.source_audio` and rounds floats to 6 decimals.
