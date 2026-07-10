#!/usr/bin/env python3
"""Emit Harbor / portage-format task trees for MelosViz agent evals (C08 L76).

Mirrors the helios_bench → portage adapter shape: each task gets
``task.toml``, ``instruction.md``, ``solution/``, and ``tests/``.

Usage::

    python eval/harbor/adapter.py --out eval/harbor/out
"""

from __future__ import annotations

import argparse
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class HarborTask:
    name: str
    category: str
    difficulty: str
    language: str
    instruction: str
    verify_snippet: str


TASKS: tuple[HarborTask, ...] = (
    HarborTask(
        name="melosviz-analyze-sine",
        category="analysis",
        difficulty="easy",
        language="python",
        instruction=textwrap.dedent(
            """\
            # Analyze a synthetic WAV into RenderSpec

            Using the MelosViz backend, write a short script that:

            1. Creates a 1.0s 440 Hz mono WAV at 44100 Hz under `/tmp` (or `$TMPDIR`).
            2. Calls `melosviz.analysis.audio.spec_from_wav`.
            3. Prints JSON with keys `duration`, `sample_rate`, `channels`
               taken from `spec.metadata`.

            Success: duration ≈ 1.0, sample_rate == 44100, channels == 1.
            """
        ),
        verify_snippet=textwrap.dedent(
            """\
            import json
            import math
            import struct
            import wave
            from pathlib import Path

            from melosviz.analysis.audio import spec_from_wav


            def _make_wav(path: Path) -> Path:
                sr, dur = 44100, 1.0
                n = int(sr * dur)
                samples = [int(32767 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(n)]
                with wave.open(str(path), "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(struct.pack(f"<{n}h", *samples))
                return path


            def test_analyze_sine_metadata(tmp_path: Path) -> None:
                wav = _make_wav(tmp_path / "sine.wav")
                spec = spec_from_wav(wav)
                meta = spec.metadata
                assert abs(float(meta["duration"]) - 1.0) < 0.05
                assert int(meta["sample_rate"]) == 44100
                assert int(meta["channels"]) == 1
            """
        ),
    ),
    HarborTask(
        name="melosviz-bridge-health",
        category="bridge",
        difficulty="easy",
        language="python",
        instruction=textwrap.dedent(
            """\
            # Bridge health probe

            Import `melosviz.bridge.server:app` and use FastAPI TestClient
            to `GET /health`. Assert status 200 and body `{"status":"ok"}`.
            """
        ),
        verify_snippet=textwrap.dedent(
            """\
            import pytest

            fastapi = pytest.importorskip("fastapi")
            from fastapi.testclient import TestClient

            from melosviz.bridge.server import app


            def test_health() -> None:
                client = TestClient(app)
                r = client.get("/health")
                assert r.status_code == 200
                assert r.json() == {"status": "ok"}
            """
        ),
    ),
    HarborTask(
        name="melosviz-golden-normalize",
        category="eval",
        difficulty="medium",
        language="python",
        instruction=textwrap.dedent(
            """\
            # Golden corpus check

            Run the committed golden corpus test:

                pytest backend/tests/test_golden_corpus.py -q

            Do not regenerate goldens unless `UPDATE_GOLDEN=1` is explicitly set.
            """
        ),
        verify_snippet=textwrap.dedent(
            """\
            import subprocess
            import sys
            from pathlib import Path

            def test_golden_suite_passes() -> None:
                root = Path(__file__).resolve().parents[4]  # repo root from emitted tree
                # Fallback: walk up looking for backend/tests
                cand = Path.cwd()
                for p in [cand, *cand.parents]:
                    t = p / "backend" / "tests" / "test_golden_corpus.py"
                    if t.is_file():
                        r = subprocess.run(
                            [sys.executable, "-m", "pytest", str(t), "-q"],
                            cwd=str(p / "backend"),
                            check=False,
                        )
                        assert r.returncode == 0
                        return
                pytest.skip("golden test not found in parents")
            """
        ),
    ),
)


def _emit_task(task: HarborTask, out_root: Path) -> Path:
    dest = out_root / task.name
    (dest / "solution").mkdir(parents=True, exist_ok=True)
    (dest / "tests").mkdir(parents=True, exist_ok=True)
    (dest / "task.toml").write_text(
        textwrap.dedent(
            f"""\
            [task]
            name = "{task.name}"
            language = "{task.language}"
            category = "{task.category}"
            difficulty = "{task.difficulty}"

            [verifier]
            timeout_sec = 60
            """
        ),
        encoding="utf-8",
    )
    (dest / "instruction.md").write_text(task.instruction, encoding="utf-8")
    (dest / "solution" / "solve.py").write_text(
        textwrap.dedent(
            f'''\
            """Stub solution for Harbor task {task.name}."""


            def solve() -> None:
                return None
            '''
        ),
        encoding="utf-8",
    )
    (dest / "tests" / "test_verify.py").write_text(
        task.verify_snippet, encoding="utf-8"
    )
    return dest


def convert(out: Path) -> list[dict[str, str]]:
    out.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, str]] = []
    for task in TASKS:
        dest = _emit_task(task, out)
        summary.append(
            {
                "name": task.name,
                "category": task.category,
                "difficulty": task.difficulty,
                "output": str(dest.relative_to(REPO_ROOT)),
            }
        )
    (out / "_summary.json").write_text(
        json.dumps({"tasks": summary, "count": len(summary)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "eval" / "harbor" / "out",
        help="Directory for emitted Harbor task trees",
    )
    args = parser.parse_args()
    summary = convert(args.out.resolve())
    print(f"emitted {len(summary)} Harbor tasks -> {args.out}")
    for row in summary:
        print(f"  - {row['name']} ({row['category']}/{row['difficulty']})")


if __name__ == "__main__":
    main()
