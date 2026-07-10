# Harbor / portage adapter for MelosViz

Emits agent-eval task trees compatible with phenotype **portage** / Harbor
runners (same shape as `helios_bench` → portage).

```bash
python eval/harbor/adapter.py --out eval/harbor/out
```

Tasks cover analyze-sine, bridge health, and golden corpus verification.
See `docs/EVAL.md`.
