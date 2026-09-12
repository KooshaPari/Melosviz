# Production Delivery Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded and budget-aware Director LLM calls, deterministic per-clip visual diffs, a weekly offline GPU-smoke run, and reproducible SVG/Lottie VJ artifacts inside a real `final.zip`.

**Architecture:** Four focused standard-library modules own admission control, visual-diff construction, VJ cue generation, and deterministic packaging. Existing `Director`, `Orchestrator`, and `viz ship` code become narrow integration points. Each subsystem lands as a separately testable conventional commit on `feat/production-delivery-extensions`, followed by one end-to-end verification commit if documentation or acceptance fixtures change.

**Tech Stack:** Python 3.10+, `urllib`, `threading.Condition`, `decimal.Decimal`, `hashlib`, `subprocess`, SVG XML, Lottie JSON 5.12, `zipfile`, pytest, GitHub Actions YAML, actionlint.

---

## Scope and execution order

The approved design contains four independent subsystems but one shared delivery
contract. Keep them in one branch and one eventual PR, while preserving the
following commit boundaries:

| Order | Unit                       | Primary files                                 | Proof                      |
| ----: | -------------------------- | --------------------------------------------- | -------------------------- |
|     1 | LLM admission core         | `llm/admission.py`                            | focused unit tests         |
|     2 | Director retry integration | `llm/director.py`                             | Director behavior tests    |
|     3 | Visual-diff provenance     | `conductor/visual_diff.py`, `orchestrator.py` | unit + orchestrator tests  |
|     4 | Weekly smoke schedule      | `gpu-smoke.yml`                               | contract test + actionlint |
|     5 | VJ cue export              | `export/vj.py`                                | SVG/Lottie tests           |
|     6 | Deterministic shipping     | `export/package.py`, `cli/main.py`            | CLI + ZIP tests            |
|     7 | Docs and acceptance        | `docs/ENV.md`, `docs/STUDIO_PIPELINE.md`      | full verification          |

Do not push, open a PR, enable auto-merge, or merge as part of this plan. Those
are separate hosted-state gates after local verification. Do not admin-bypass
branch protection.

## File map

### Create

- `backend/src/melosviz/llm/admission.py` — configuration, cost estimation,
  FIFO admission, rate window, concurrency, and cost settlement.
- `backend/tests/llm/test_admission.py` — deterministic admission tests with a
  fake clock and bounded threads.
- `backend/src/melosviz/conductor/visual_diff.py` — hashes, preview extraction,
  and deterministic SVG timeline card.
- `backend/tests/conductor/test_visual_diff.py` — visual-diff unit tests.
- `backend/tests/conductor/test_orchestrator_provenance.py` — proves the live
  orchestrator writes valid provenance and visual-diff sidecars.
- `backend/tests/test_gpu_smoke_workflow.py` — text-level workflow contract.
- `backend/src/melosviz/export/__init__.py` — export package boundary.
- `backend/src/melosviz/export/vj.py` — shot discovery and SVG/Lottie cue files.
- `backend/tests/export/test_vj.py` — discovery and deterministic cue tests.
- `backend/src/melosviz/export/package.py` — media discovery, atomic manifest,
  deterministic ZIP writer.
- `backend/tests/export/test_package.py` — package and failure-atomicity tests.
- `backend/tests/cli/test_ship.py` — `viz ship` JSON/output contract.
- `docs/specs/acceptance/production_delivery_extensions.feature` — operator
  acceptance scenarios.

### Modify

- `backend/src/melosviz/llm/director.py` — use the shared gate and retry 429/5xx.
- `backend/tests/llm/test_director.py` — fail-closed and retry behavior.
- `backend/src/melosviz/conductor/provenance.py` — add `visual_diff` to the
  serialized schema.
- `backend/src/melosviz/conductor/orchestrator.py` — construct the existing
  `ClipProvenance` correctly, build visual diffs, and stop swallowing the current
  type/signature mismatch.
- `backend/src/melosviz/conductor/__init__.py` — re-export visual-diff surface.
- `.github/workflows/gpu-smoke.yml` — add schedule and event-safe defaults.
- `backend/src/melosviz/cli/main.py` — delegate `_cmd_ship` to package writer.
- `backend/tests/test_e2e_3min_pipeline.py` — require VJ artifacts in ZIP.
- `backend/tests/cli/test_gpu_smoke.py` — require final shipping topology.
- `docs/ENV.md` — document LLM guard variables.
- `docs/STUDIO_PIPELINE.md` — document visual diffs and VJ shipment layout.

## Task 1: Implement the Director admission core

**Files:**

- Create: `backend/tests/llm/test_admission.py`
- Create: `backend/src/melosviz/llm/admission.py`

- [ ] **Step 1: Write failing configuration and cost tests**

Create `backend/tests/llm/test_admission.py` with the first four tests:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from melosviz.llm.admission import (
    LLMAdmissionConfig,
    LLMAdmissionError,
    LLMAdmissionGate,
)


def _env(**overrides: str) -> dict[str, str]:
    values = {
        "MELOSVIZ_LLM_REQUESTS_PER_MINUTE": "30",
        "MELOSVIZ_LLM_MAX_CONCURRENCY": "2",
        "MELOSVIZ_LLM_MAX_QUEUE": "32",
        "MELOSVIZ_LLM_MAX_RETRIES": "3",
        "MELOSVIZ_LLM_COST_CAP_USD": "1.00",
        "MELOSVIZ_LLM_INPUT_USD_PER_MILLION": "1.00",
        "MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MELOSVIZ_LLM_MAX_OUTPUT_TOKENS": "100",
    }
    values.update(overrides)
    return values


def test_config_requires_both_prices() -> None:
    env = _env()
    env.pop("MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION")
    with pytest.raises(LLMAdmissionError, match="OUTPUT_USD_PER_MILLION"):
        LLMAdmissionConfig.from_env(env)


def test_config_rejects_non_positive_limits() -> None:
    with pytest.raises(LLMAdmissionError, match="MAX_CONCURRENCY"):
        LLMAdmissionConfig.from_env(_env(MELOSVIZ_LLM_MAX_CONCURRENCY="0"))


def test_estimate_uses_utf8_bytes_and_reserved_output() -> None:
    config = LLMAdmissionConfig.from_env(_env())
    estimate = config.estimate("abcdefgh".encode())
    assert estimate.input_tokens == 2
    assert estimate.output_tokens == 100
    assert estimate.usd == Decimal("0.000202")


def test_cost_cap_rejects_second_reservation() -> None:
    config = LLMAdmissionConfig.from_env(
        _env(
            MELOSVIZ_LLM_COST_CAP_USD="0.0003",
            MELOSVIZ_LLM_MAX_OUTPUT_TOKENS="100",
        )
    )
    gate = LLMAdmissionGate(config)
    estimate = config.estimate(b"abcdefgh")
    first = gate.reserve(estimate)
    with pytest.raises(LLMAdmissionError, match="cost cap"):
        gate.reserve(estimate)
    first.release()
```

- [ ] **Step 2: Run the tests and verify the import failure**

Run:

```bash
cd backend
uv run pytest -q tests/llm/test_admission.py
```

Expected: collection fails with `ModuleNotFoundError: No module named
'melosviz.llm.admission'`.

- [ ] **Step 3: Implement validated configuration and cost reservation**

Create `backend/src/melosviz/llm/admission.py` with these concrete public
shapes and behaviors:

```python
from __future__ import annotations

import math
import os
import time
from collections import deque
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Condition, Lock
from typing import Callable, Mapping


class LLMAdmissionError(RuntimeError):
    """A controlled rejection that preserves template Director output."""


@dataclass(frozen=True)
class LLMCostEstimate:
    input_tokens: int
    output_tokens: int
    usd: Decimal


@dataclass(frozen=True)
class LLMAdmissionConfig:
    requests_per_minute: int
    max_concurrency: int
    max_queue: int
    max_retries: int
    cost_cap_usd: Decimal
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    max_output_tokens: int

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> "LLMAdmissionConfig":
        source = os.environ if env is None else env

        def positive_int(name: str, default: str) -> int:
            raw = source.get(name, default)
            try:
                value = int(raw)
            except ValueError as exc:
                raise LLMAdmissionError(f"{name} must be an integer") from exc
            if value <= 0:
                raise LLMAdmissionError(f"{name} must be greater than zero")
            return value

        def non_negative_decimal(name: str, default: str | None = None) -> Decimal:
            raw = source.get(name, default)
            if raw is None:
                raise LLMAdmissionError(f"{name} must be configured")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise LLMAdmissionError(f"{name} must be a decimal") from exc
            if not value.is_finite() or value < 0:
                raise LLMAdmissionError(f"{name} must be finite and non-negative")
            return value

        return cls(
            requests_per_minute=positive_int(
                "MELOSVIZ_LLM_REQUESTS_PER_MINUTE", "30"
            ),
            max_concurrency=positive_int("MELOSVIZ_LLM_MAX_CONCURRENCY", "2"),
            max_queue=positive_int("MELOSVIZ_LLM_MAX_QUEUE", "32"),
            max_retries=positive_int("MELOSVIZ_LLM_MAX_RETRIES", "3"),
            cost_cap_usd=non_negative_decimal(
                "MELOSVIZ_LLM_COST_CAP_USD", "1.00"
            ),
            input_usd_per_million=non_negative_decimal(
                "MELOSVIZ_LLM_INPUT_USD_PER_MILLION"
            ),
            output_usd_per_million=non_negative_decimal(
                "MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION"
            ),
            max_output_tokens=positive_int(
                "MELOSVIZ_LLM_MAX_OUTPUT_TOKENS", "2048"
            ),
        )

    def estimate(self, payload: bytes) -> LLMCostEstimate:
        input_tokens = max(1, math.ceil(len(payload) / 4))
        million = Decimal(1_000_000)
        usd = (
            Decimal(input_tokens) * self.input_usd_per_million
            + Decimal(self.max_output_tokens) * self.output_usd_per_million
        ) / million
        return LLMCostEstimate(input_tokens, self.max_output_tokens, usd)

    def actual_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(max(0, input_tokens)) * self.input_usd_per_million
            + Decimal(max(0, output_tokens)) * self.output_usd_per_million
        ) / million


class LLMReservation(AbstractContextManager["LLMReservation"]):
    def __init__(
        self, gate: "LLMAdmissionGate", estimate: LLMCostEstimate
    ) -> None:
        self._gate = gate
        self.estimate = estimate
        self._closed = False

    def attempt(self) -> "LLMAttempt":
        if self._closed:
            raise LLMAdmissionError("reservation is already closed")
        return LLMAttempt(self._gate)

    def settle(self, actual_usd: Decimal | None = None) -> None:
        if not self._closed:
            self._gate._finish_reservation(
                self.estimate.usd,
                self.estimate.usd if actual_usd is None else actual_usd,
            )
            self._closed = True

    def release(self) -> None:
        if not self._closed:
            self._gate._finish_reservation(self.estimate.usd, Decimal(0))
            self._closed = True

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._closed:
            self.settle()


class LLMAttempt(AbstractContextManager["LLMAttempt"]):
    def __init__(self, gate: "LLMAdmissionGate") -> None:
        self._gate = gate
        self._entered = False

    def __enter__(self) -> "LLMAttempt":
        self._gate._enter_attempt()
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._entered:
            self._gate._leave_attempt()


class LLMAdmissionGate:
    def __init__(
        self,
        config: LLMAdmissionConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._clock = clock
        self._sleep = sleeper
        self._condition = Condition()
        self._budget_lock = Lock()
        self._tickets: deque[int] = deque()
        self._starts: deque[float] = deque()
        self._next_ticket = 0
        self._active = 0
        self._reserved = Decimal(0)
        self._spent = Decimal(0)

    @property
    def spent_usd(self) -> Decimal:
        with self._budget_lock:
            return self._spent

    @property
    def waiting_count(self) -> int:
        with self._condition:
            return len(self._tickets)

    def reserve(self, estimate: LLMCostEstimate) -> LLMReservation:
        with self._budget_lock:
            projected = self._spent + self._reserved + estimate.usd
            if projected > self.config.cost_cap_usd:
                raise LLMAdmissionError(
                    f"Director LLM cost cap exceeded: {projected} > "
                    f"{self.config.cost_cap_usd}"
                )
            self._reserved += estimate.usd
        return LLMReservation(self, estimate)

    def _finish_reservation(self, reserved: Decimal, actual: Decimal) -> None:
        with self._budget_lock:
            self._reserved -= reserved
            self._spent += max(Decimal(0), actual)

    def _enter_attempt(self) -> None:
        with self._condition:
            waiting = len(self._tickets)
            if waiting >= self.config.max_queue:
                raise LLMAdmissionError("Director LLM queue is full")
            ticket = self._next_ticket
            self._next_ticket += 1
            self._tickets.append(ticket)

        while True:
            delay = 0.0
            with self._condition:
                now = self._clock()
                while self._starts and now - self._starts[0] >= 60.0:
                    self._starts.popleft()
                is_head = bool(self._tickets) and self._tickets[0] == ticket
                has_worker = self._active < self.config.max_concurrency
                has_rate = len(self._starts) < self.config.requests_per_minute
                if is_head and has_worker and has_rate:
                    self._tickets.popleft()
                    self._active += 1
                    self._starts.append(now)
                    self._condition.notify_all()
                    return
                if is_head and has_worker and self._starts:
                    delay = max(0.0, 60.0 - (now - self._starts[0]))
                else:
                    self._condition.wait(timeout=0.05)
            if delay > 0:
                self._sleep(delay)

    def _leave_attempt(self) -> None:
        with self._condition:
            self._active -= 1
            self._condition.notify_all()


_SHARED_LOCK = Lock()
_SHARED_GATES: dict[LLMAdmissionConfig, LLMAdmissionGate] = {}


def get_shared_gate(config: LLMAdmissionConfig) -> LLMAdmissionGate:
    with _SHARED_LOCK:
        gate = _SHARED_GATES.get(config)
        if gate is None:
            gate = LLMAdmissionGate(config)
            _SHARED_GATES[config] = gate
        return gate
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
cd backend
uv run pytest -q tests/llm/test_admission.py
```

Expected: `4 passed`.

- [ ] **Step 5: Add rate-window, FIFO, and queue-bound tests**

Append tests that use this fake clock and bounded thread coordination:

```python
import threading
import time


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_window_delays_second_attempt() -> None:
    clock = FakeClock()
    config = LLMAdmissionConfig.from_env(
        _env(MELOSVIZ_LLM_REQUESTS_PER_MINUTE="1")
    )
    gate = LLMAdmissionGate(config, clock=clock, sleeper=clock.sleep)
    reservation = gate.reserve(config.estimate(b"x"))
    with reservation.attempt():
        pass
    with reservation.attempt():
        pass
    reservation.release()
    assert clock.sleeps == [60.0]


def test_attempts_enter_in_fifo_order() -> None:
    config = LLMAdmissionConfig.from_env(
        _env(MELOSVIZ_LLM_MAX_CONCURRENCY="1")
    )
    gate = LLMAdmissionGate(config)
    order: list[int] = []
    first_entered = threading.Event()
    release_first = threading.Event()

    def worker(index: int) -> None:
        reservation = gate.reserve(config.estimate(str(index).encode()))
        with reservation.attempt():
            order.append(index)
            if index == 0:
                first_entered.set()
                assert release_first.wait(timeout=2)
        reservation.release()

    first = threading.Thread(target=worker, args=(0,))
    second = threading.Thread(target=worker, args=(1,))
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive() and not second.is_alive()
    assert order == [0, 1]


def test_queue_full_rejects_an_additional_waiter() -> None:
    config = LLMAdmissionConfig.from_env(
        _env(MELOSVIZ_LLM_MAX_CONCURRENCY="1", MELOSVIZ_LLM_MAX_QUEUE="1")
    )
    gate = LLMAdmissionGate(config)
    holder = gate.reserve(config.estimate(b"holder"))
    holder_attempt = holder.attempt()
    holder_attempt.__enter__()
    waiter_started = threading.Event()
    waiter_done = threading.Event()

    def wait_once() -> None:
        reservation = gate.reserve(config.estimate(b"waiter"))
        waiter_started.set()
        with reservation.attempt():
            pass
        reservation.release()
        waiter_done.set()

    waiter = threading.Thread(target=wait_once)
    waiter.start()
    assert waiter_started.wait(timeout=2)
    deadline = time.monotonic() + 2
    while gate.waiting_count != 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert gate.waiting_count == 1
    rejected = gate.reserve(config.estimate(b"rejected"))
    with pytest.raises(LLMAdmissionError, match="queue is full"):
        rejected.attempt().__enter__()
    rejected.release()
    holder_attempt.__exit__(None, None, None)
    holder.release()
    assert waiter_done.wait(timeout=2)
    waiter.join(timeout=2)
```

- [ ] **Step 6: Run admission tests and lint the new module**

Run:

```bash
cd backend
uv run pytest -q tests/llm/test_admission.py
uv run ruff check src/melosviz/llm/admission.py tests/llm/test_admission.py
```

Expected: all seven tests pass and ruff exits 0. If the queue-bound test exposes
a race, fix the queue-size calculation rather than adding sleeps to the test.

- [ ] **Step 7: Commit the admission core**

```bash
git add backend/src/melosviz/llm/admission.py backend/tests/llm/test_admission.py
git commit -m "feat(llm): add bounded Director admission gate" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 2: Integrate retries and cost settlement into Director

**Files:**

- Modify: `backend/src/melosviz/llm/director.py:55-70,412-418,611-675`
- Modify: `backend/tests/llm/test_director.py`

- [ ] **Step 1: Write failing Director integration tests**

Add imports and helpers to `backend/tests/llm/test_director.py`:

```python
import io
import urllib.error

from melosviz.llm.admission import LLMAdmissionConfig, LLMAdmissionGate


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _llm_env(monkeypatch) -> None:
    values = {
        "MELOSVIZ_LLM_ENDPOINT": "https://llm.invalid/v1/chat/completions",
        "MELOSVIZ_LLM_MODEL": "fixed-model",
        "MELOSVIZ_LLM_INPUT_USD_PER_MILLION": "1.00",
        "MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION": "2.00",
        "MELOSVIZ_LLM_MAX_OUTPUT_TOKENS": "100",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _single_scene_request() -> DirectorRequest:
    return DirectorRequest(
        concept="neon city",
        duration_s=8.0,
        bpm=120.0,
        segments=[{"label": "verse", "start": 0.0, "end": 8.0}],
    )
```

Then add these behavior tests:

```python
def test_llm_missing_prices_falls_back_without_network(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MELOSVIZ_LLM_ENDPOINT", "https://llm.invalid")
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise AssertionError("network must not be called")

    board = Director(seed=1, llm_opener=opener).storyboard(_single_scene_request())
    assert calls == 0
    assert "scene verse" in board.scenes[0].prompt
    assert "must be configured" in caplog.text


def test_llm_429_honors_retry_after_and_keeps_model(monkeypatch) -> None:
    _llm_env(monkeypatch)
    requests: list[dict] = []
    sleeps: list[float] = []
    responses = [
        urllib.error.HTTPError(
            "https://llm.invalid", 429, "rate limited", {"Retry-After": "2"}, io.BytesIO()
        ),
        FakeResponse({
            "choices": [{"message": {"content": json.dumps({
                "rewrites": [{"index": 0, "prompt": "refined prompt"}]
            })}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }),
    ]

    def opener(request, timeout):
        requests.append(json.loads(request.data.decode()))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    board = Director(
        seed=1, llm_opener=opener, llm_sleeper=sleeps.append
    ).storyboard(_single_scene_request())
    assert board.scenes[0].prompt == "refined prompt"
    assert sleeps == [2.0]
    assert [request["model"] for request in requests] == ["fixed-model", "fixed-model"]


def test_llm_non_retryable_400_attempts_once(monkeypatch) -> None:
    _llm_env(monkeypatch)
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            request.full_url, 400, "bad request", {}, io.BytesIO()
        )

    board = Director(seed=1, llm_opener=opener).storyboard(_single_scene_request())
    assert calls == 1
    assert "scene verse" in board.scenes[0].prompt
```

- [ ] **Step 2: Run the three tests and verify the constructor failure**

Run:

```bash
cd backend
uv run pytest -q tests/llm/test_director.py \
  -k 'missing_prices or honors_retry_after or non_retryable'
```

Expected: tests fail because `Director.__init__` does not accept `llm_opener` or
`llm_sleeper`.

- [ ] **Step 3: Add injectable HTTP dependencies and the retry loop**

Modify `Director.__init__` to store optional dependencies without changing
existing callers:

```python
def __init__(
    self,
    *,
    seed: int | None = None,
    llm_gate: "LLMAdmissionGate | None" = None,
    llm_opener: Any | None = None,
    llm_sleeper: Any | None = None,
) -> None:
    self._seed = seed if seed is not None else int(time.time()) & 0xFFFFFFFF
    self._llm_gate = llm_gate
    self._llm_opener = llm_opener or urllib.request.urlopen
    self._llm_sleeper = llm_sleeper or time.sleep
```

Import these names near the existing imports:

```python
from .admission import (
    LLMAdmissionConfig,
    LLMAdmissionError,
    LLMAdmissionGate,
    get_shared_gate,
)
```

Add helpers immediately before `_maybe_refine_with_llm`:

```python
@staticmethod
def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after is not None:
        try:
            return max(0.0, min(30.0, float(retry_after)))
        except ValueError:
            pass
    return float(min(30, 2 ** attempt))

@staticmethod
def _is_retryable_http(exc: urllib.error.HTTPError) -> bool:
    return exc.code == 429 or exc.code in {500, 502, 503, 504}
```

Replace the single `urlopen` section in `_maybe_refine_with_llm` with:

```python
encoded_body = json.dumps(body).encode("utf-8")
try:
    config = LLMAdmissionConfig.from_env()
    gate = self._llm_gate or get_shared_gate(config)
    estimate = config.estimate(encoded_body)
    with gate.reserve(estimate) as reservation:
        payload: dict[str, Any] | None = None
        for attempt in range(config.max_retries + 1):
            req_obj = urllib.request.Request(
                endpoint,
                method="POST",
                data=encoded_body,
                headers={
                    "Content-Type": "application/json",
                    **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
                },
            )
            try:
                with reservation.attempt():
                    with self._llm_opener(req_obj, timeout=timeout) as resp:
                        payload = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if not self._is_retryable_http(exc) or attempt >= config.max_retries:
                    raise
                self._llm_sleeper(self._retry_delay(exc, attempt))

        if payload is None:
            raise ValueError("Director LLM returned no payload")
        usage = payload.get("usage") or {}
        if "prompt_tokens" in usage and "completion_tokens" in usage:
            reservation.settle(config.actual_cost(
                int(usage["prompt_tokens"]),
                int(usage["completion_tokens"]),
            ))
        text = payload["choices"][0]["message"]["content"]
        rewrites = json.loads(text).get("rewrites") or []
        by_index = {int(item["index"]): str(item["prompt"]) for item in rewrites}
        for scene in scenes:
            if scene.index in by_index and by_index[scene.index]:
                scene.prompt = by_index[scene.index]
        logger.info(
            "Director: LLM rewrote %d/%d scene prompts", len(by_index), len(scenes)
        )
except (
    LLMAdmissionError,
    urllib.error.URLError,
    TimeoutError,
    OSError,
    KeyError,
    TypeError,
    ValueError,
) as exc:
    logger.warning(
        "Director: LLM refinement skipped (%s) — using template prompts.", exc
    )
return scenes
```

- [ ] **Step 4: Run Director and admission tests**

Run:

```bash
cd backend
uv run pytest -q tests/llm/test_admission.py tests/llm/test_director.py
uv run ruff check src/melosviz/llm/admission.py src/melosviz/llm/director.py \
  tests/llm/test_admission.py tests/llm/test_director.py
```

Expected: all tests pass and ruff exits 0. Confirm the 429 test records exactly
two requests with the same model.

- [ ] **Step 5: Commit Director integration**

```bash
git add backend/src/melosviz/llm/director.py backend/tests/llm/test_director.py
git commit -m "feat(llm): guard and retry Director refinement" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 3: Build deterministic per-clip visual diffs

**Files:**

- Create: `backend/tests/conductor/test_visual_diff.py`
- Create: `backend/src/melosviz/conductor/visual_diff.py`
- Modify: `backend/src/melosviz/conductor/provenance.py`
- Modify: `backend/tests/conductor/test_provenance.py`
- Modify: `backend/src/melosviz/conductor/__init__.py`

- [ ] **Step 1: Write failing hash, fallback, and escaping tests**

Create `backend/tests/conductor/test_visual_diff.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from melosviz.conductor.visual_diff import build_visual_diff


def test_visual_diff_hashes_artifact_and_prompt(tmp_path: Path) -> None:
    artifact = tmp_path / "scene.mp4"
    artifact.write_bytes(b"rendered-bytes")
    payload = build_visual_diff(
        artifact_path=artifact,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="intro",
        prompt="neon & rain",
        start_seconds=1.0,
        end_seconds=5.0,
        beat_seconds=[1.0, 3.0, 5.0],
        palette=["#112233"],
        frame_extractor=lambda source, target: False,
    )
    assert payload["rendered"]["sha256"] == hashlib.sha256(
        b"rendered-bytes"
    ).hexdigest()
    assert payload["prompt"]["sha256"] == hashlib.sha256(
        b"neon & rain"
    ).hexdigest()


def test_visual_diff_fallback_svg_is_deterministic_and_escaped(tmp_path: Path) -> None:
    kwargs = dict(
        artifact_path=tmp_path / "missing.mp4",
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name='<intro & "drop">',
        prompt="neon < rain & thunder",
        start_seconds=0.0,
        end_seconds=8.0,
        beat_seconds=[0.0, 4.0, 8.0],
        palette=["#ff00aa"],
        frame_extractor=lambda source, target: False,
    )
    first = build_visual_diff(**kwargs)
    first_bytes = (tmp_path / "visual-diff.svg").read_bytes()
    second = build_visual_diff(**kwargs)
    assert (tmp_path / "visual-diff.svg").read_bytes() == first_bytes
    assert first == second
    svg = first_bytes.decode()
    assert "&lt;intro &amp; &quot;drop&quot;&gt;" in svg
    assert "neon &lt; rain &amp; thunder" in svg
    assert '<script' not in svg
    assert 'href="http://' not in svg and 'href="https://' not in svg


def test_visual_diff_records_extracted_preview(tmp_path: Path) -> None:
    artifact = tmp_path / "scene.mov"
    artifact.write_bytes(b"movie")

    def extractor(source: Path, target: Path) -> bool:
        assert source == artifact
        target.write_bytes(b"png")
        return True

    payload = build_visual_diff(
        artifact_path=artifact,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="chorus",
        prompt="wide hero",
        start_seconds=2.0,
        end_seconds=6.0,
        beat_seconds=[2.0, 4.0],
        palette=[],
        frame_extractor=extractor,
    )
    assert payload["rendered"]["preview_path"] == "visual-diff-frame.png"
    assert payload["rendered"]["preview_sha256"] == hashlib.sha256(
        b"png"
    ).hexdigest()
```

- [ ] **Step 2: Run and verify the missing-module failure**

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_visual_diff.py
```

Expected: collection fails because `melosviz.conductor.visual_diff` is absent.

- [ ] **Step 3: Implement the visual-diff builder**

Create `backend/src/melosviz/conductor/visual_diff.py` with these functions:

```python
from __future__ import annotations

import hashlib
import html
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence


FrameExtractor = Callable[[Path, Path], bool]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def extract_preview_frame(source: Path, target: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or not source.is_file():
        return False
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-frames:v",
            "1",
            str(target),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    return completed.returncode == 0 and target.is_file() and target.stat().st_size > 0


def _timeline_svg(
    *,
    scene_name: str,
    prompt: str,
    start_seconds: float,
    end_seconds: float,
    beat_seconds: Sequence[float],
    palette: Sequence[str],
    has_preview: bool,
) -> str:
    duration = max(0.001, end_seconds - start_seconds)
    ticks = []
    for beat in beat_seconds:
        position = min(1.0, max(0.0, (float(beat) - start_seconds) / duration))
        x = 48 + round(position * 864, 3)
        ticks.append(
            f'<line x1="{x}" y1="470" x2="{x}" y2="504" stroke="#ffffff" />'
        )
    color = palette[0] if palette and str(palette[0]).startswith("#") else "#202033"
    preview = (
        '<image href="visual-diff-frame.png" x="48" y="72" width="864" '
        'height="330" preserveAspectRatio="xMidYMid slice" />'
        if has_preview
        else f'<rect x="48" y="72" width="864" height="330" fill="{html.escape(color)}" />'
    )
    safe_name = html.escape(scene_name[:80], quote=True)
    safe_prompt = html.escape(" ".join(prompt.split())[:180], quote=True)
    tick_markup = "".join(ticks)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" '
        'viewBox="0 0 960 540">\n'
        '<rect width="960" height="540" fill="#0d0d10" />\n'
        f'{preview}\n'
        f'<text x="48" y="40" fill="#ffffff" font-size="24">{safe_name}</text>\n'
        f'<text x="48" y="438" fill="#ffffff" font-size="18">{safe_prompt}</text>\n'
        '<line x1="48" y1="487" x2="912" y2="487" stroke="#888899" />\n'
        f'{tick_markup}\n'
        f'<text x="48" y="526" fill="#ccccd8" font-size="16">'
        f'{start_seconds:.3f}s - {end_seconds:.3f}s</text>\n'
        '</svg>\n'
    )


def build_visual_diff(
    *,
    artifact_path: Path,
    scene_dir: Path,
    job_dir: Path,
    scene_name: str,
    prompt: str,
    start_seconds: float,
    end_seconds: float,
    beat_seconds: Sequence[float],
    palette: Sequence[str],
    frame_extractor: FrameExtractor = extract_preview_frame,
) -> dict:
    scene_dir.mkdir(parents=True, exist_ok=True)
    preview = scene_dir / "visual-diff-frame.png"
    extracted = frame_extractor(artifact_path, preview)
    if not extracted and preview.exists():
        preview.unlink()
    svg_path = scene_dir / "visual-diff.svg"
    svg_path.write_text(
        _timeline_svg(
            scene_name=scene_name,
            prompt=prompt,
            start_seconds=float(start_seconds),
            end_seconds=float(end_seconds),
            beat_seconds=beat_seconds,
            palette=palette,
            has_preview=extracted,
        ),
        encoding="utf-8",
    )
    normalized_prompt = " ".join(prompt.split())
    return {
        "schema_version": "1.0",
        "rendered": {
            "path": _relative(artifact_path, job_dir),
            "sha256": _sha256(artifact_path),
            "preview_path": _relative(preview, job_dir) if extracted else None,
            "preview_sha256": _sha256(preview) if extracted else None,
        },
        "prompt": {
            "text": normalized_prompt,
            "sha256": hashlib.sha256(normalized_prompt.encode()).hexdigest(),
        },
        "timeline_thumbnail": {
            "path": _relative(svg_path, job_dir),
            "sha256": _sha256(svg_path),
            "start_seconds": float(start_seconds),
            "end_seconds": float(end_seconds),
            "beat_seconds": [float(value) for value in beat_seconds],
        },
    }
```

- [ ] **Step 4: Run visual-diff tests and verify green**

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_visual_diff.py
uv run ruff check src/melosviz/conductor/visual_diff.py \
  tests/conductor/test_visual_diff.py
```

Expected: `3 passed`; ruff exits 0.

- [ ] **Step 5: Add visual_diff to the provenance schema test-first**

Append to `backend/tests/conductor/test_provenance.py`:

```python
def test_clip_provenance_serializes_visual_diff() -> None:
    visual_diff = {
        "schema_version": "1.0",
        "rendered": {"path": "scene.mp4", "sha256": "abc"},
    }
    payload = _make_prov(visual_diff=visual_diff).to_dict()
    assert payload["visual_diff"] == visual_diff
```

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_provenance.py \
  -k serializes_visual_diff
```

Expected: fail with `TypeError` because `ClipProvenance` has no `visual_diff`
field.

- [ ] **Step 6: Extend provenance and public exports**

Add this field to `ClipProvenance` after `extra`:

```python
visual_diff: dict | None = None
```

Add this key to the dictionary returned by `to_dict`:

```python
"visual_diff": self.visual_diff,
```

In `backend/src/melosviz/conductor/__init__.py`, import and export
`build_visual_diff` and `extract_preview_frame`:

```python
from .visual_diff import build_visual_diff, extract_preview_frame
```

Add both names to `__all__` in alphabetical position.

- [ ] **Step 7: Run provenance and visual-diff tests**

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_provenance.py \
  tests/conductor/test_visual_diff.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit the visual-diff unit**

```bash
git add backend/src/melosviz/conductor/visual_diff.py \
  backend/src/melosviz/conductor/provenance.py \
  backend/src/melosviz/conductor/__init__.py \
  backend/tests/conductor/test_visual_diff.py \
  backend/tests/conductor/test_provenance.py
git commit -m "feat(conductor): add deterministic clip visual diffs" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 4: Wire valid provenance through the orchestrator

**Files:**

- Create: `backend/tests/conductor/test_orchestrator_provenance.py`
- Modify: `backend/src/melosviz/conductor/orchestrator.py:560-724`

The current best-effort block constructs `ClipProvenance` with nonexistent
`duration_ms`, `license`, and `content_origin` arguments and calls
`write_provenance` with reversed/incompatible arguments. The broad exception
then hides the failure. Correcting this is required for visual diffs to exist.

- [ ] **Step 1: Write a failing live-orchestrator provenance test**

Create `backend/tests/conductor/test_orchestrator_provenance.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from melosviz.conductor import registry as registry_module
from melosviz.conductor.orchestrator import Orchestrator


class Result:
    def __init__(self, artifact: Path) -> None:
        self.files = [artifact]


def test_orchestrator_writes_visual_diff_provenance(tmp_path, monkeypatch) -> None:
    class Adapter:
        def render(self, render_spec, **kwargs):
            artifact = Path(kwargs["output_path"]) / "scene.mp4"
            artifact.write_bytes(b"rendered")
            return Result(artifact)

    monkeypatch.setitem(registry_module.ADAPTER_REGISTRY, "video_export", Adapter)
    spec = {
        "version": 2,
        "width": 1920,
        "height": 1080,
        "fps": 24,
        "scene_segments": [{
            "name": "intro",
            "scene_type": "video_export",
            "start": 1.0,
            "end": 5.0,
            "beats": [1.0, 3.0, 5.0],
            "prompt": "neon rain",
            "palette": ["#112233"],
            "seed": 7,
        }],
    }
    orchestrator = Orchestrator(
        output_dir=tmp_path,
        skip_assembly=True,
        auto_offline=False,
    )
    orchestrator.render(spec, scene_types=["video_export"])
    sidecars = list(tmp_path.rglob("*.provenance.json"))
    assert len(sidecars) == 1
    payload = json.loads(sidecars[0].read_text())
    assert payload["scene_name"] == "intro"
    assert payload["visual_diff"]["prompt"]["text"] == "neon rain"
    assert (tmp_path / payload["visual_diff"]["timeline_thumbnail"]["path"]).is_file()
```

- [ ] **Step 2: Run and verify that no sidecar is produced**

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_orchestrator_provenance.py
```

Expected: fail at `assert len(sidecars) == 1` because the existing broad
exception hides the invalid dataclass construction.

- [ ] **Step 3: Correct the per-scene integration block**

Import `ClipProvenance`, `write_provenance`, and `build_visual_diff` once near
the beginning of `render`. Record both monotonic and wall-clock start times:

```python
t0 = time.monotonic()
render_started_at = time.time()
```

Replace the current provenance block with:

```python
try:
    render_finished_at = time.time()
    prompt = str(_seg_for_render.get("prompt") or scene_name)
    palette_value = _seg_for_render.get("palette") or []
    palette = (
        [part for part in str(palette_value).split() if part]
        if isinstance(palette_value, str)
        else [str(part) for part in palette_value]
    )
    start_seconds = float(_seg_for_render.get("start", 0.0) or 0.0)
    end_seconds = float(
        _seg_for_render.get("end", start_seconds) or start_seconds
    )
    beat_values = _seg_for_render.get("beats") or _seg_for_render.get(
        "beats_in_segment"
    ) or []
    artifact_path = Path(artifact) if artifact else scene_out_dir / "offline-plan.json"
    visual_diff = build_visual_diff(
        artifact_path=artifact_path,
        scene_dir=scene_out_dir,
        job_dir=self._output_dir,
        scene_name=scene_name,
        prompt=prompt,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        beat_seconds=[float(value) for value in beat_values],
        palette=palette,
    )
    provenance = ClipProvenance(
        artifact_path=str(artifact_path),
        scene_index=scene_idx,
        scene_name=scene_name,
        scene_type=scene_type,
        backend=backend_key,
        render_started_at=render_started_at,
        render_finished_at=render_finished_at,
        storyboard_id=job_id,
        seed=int(_seg_for_render.get("seed", scene_idx) or scene_idx),
        prompt=prompt,
        width=int(_seg_for_render.get("width", getattr(render_spec, "width", 1920)) or 1920),
        height=int(_seg_for_render.get("height", getattr(render_spec, "height", 1080)) or 1080),
        fps=int(_seg_for_render.get("fps", getattr(render_spec, "fps", 24)) or 24),
        palette=palette,
        continuity=dict(_seg_for_render.get("continuity") or {}),
        lyric=_seg_for_render.get("lyric"),
        extra={
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "beat_seconds": [float(value) for value in beat_values],
            "license": "CC-BY-NC-4.0",
            "content_origin": "melosviz-generated",
        },
        visual_diff=visual_diff,
    )
    self._provenance_records.append(provenance)
    write_provenance(provenance)
except Exception as exc:
    logger.warning("provenance write failed for scene[%d]: %s", scene_idx, exc)
```

In the adjacent cache block, replace every use of the stale loop variable `seg`
with `_seg_for_render`. Do not redesign the cache in this task.

- [ ] **Step 4: Run orchestrator, provenance, cache, and event tests**

Run:

```bash
cd backend
uv run pytest -q tests/conductor/test_orchestrator_provenance.py \
  tests/conductor/test_provenance.py tests/conductor/test_visual_diff.py \
  tests/conductor/test_render_cache.py tests/conductor/test_events.py
```

Expected: all tests pass, including one valid sidecar from the new integration
test.

- [ ] **Step 5: Commit orchestrator wiring**

```bash
git add backend/src/melosviz/conductor/orchestrator.py \
  backend/tests/conductor/test_orchestrator_provenance.py
git commit -m "fix(conductor): persist clip provenance and visual diffs" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 5: Schedule the offline GPU smoke weekly

**Files:**

- Create: `backend/tests/test_gpu_smoke_workflow.py`
- Modify: `.github/workflows/gpu-smoke.yml`

- [ ] **Step 1: Write a failing text-level workflow contract**

Create `backend/tests/test_gpu_smoke_workflow.py`:

```python
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "gpu-smoke.yml"


def test_gpu_smoke_supports_manual_and_weekly_runs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "17 8 * * 1" in text


def test_scheduled_run_has_explicit_defaults() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "PYTHON_VERSION:" in text
    assert "INSTALL_FFMPEG:" in text
    assert "MELOSVIZ_COMFYUI_OFFLINE: '1'" in text
    assert "tests/cli/test_gpu_smoke.py" in text
```

- [ ] **Step 2: Run and verify schedule/default failures**

Run:

```bash
cd backend
uv run pytest -q tests/test_gpu_smoke_workflow.py
```

Expected: both tests fail because `schedule`, `PYTHON_VERSION`, and
`INSTALL_FFMPEG` are absent.

- [ ] **Step 3: Update the workflow with event-safe values**

Change the title and trigger block to:

```yaml
name: gpu-smoke

on:
  schedule:
    - cron: "17 8 * * 1"
  workflow_dispatch:
    inputs:
      python-version:
        description: "Python version"
        default: "3.12"
        required: false
        type: choice
        options:
          - 3.10
          - 3.11
          - 3.12
          - 3.13
      ffmpeg:
        description: "Install ffmpeg?"
        default: true
        type: boolean
```

Replace the job environment with:

```yaml
env:
  MELOSVIZ_COMFYUI_OFFLINE: "1"
  PYTHON_VERSION: ${{ github.event_name == 'workflow_dispatch' && inputs.python-version || '3.12' }}
  INSTALL_FFMPEG: ${{ github.event_name == 'schedule' || inputs.ffmpeg }}
```

Change the ffmpeg condition and Python references to:

```yaml
- name: Install ffmpeg
  if: ${{ env.INSTALL_FFMPEG == 'true' }}
  run: sudo apt-get update && sudo apt-get install -y ffmpeg

- name: Set up Python ${{ env.PYTHON_VERSION }}
  run: uv python install ${{ env.PYTHON_VERSION }}
```

Keep the existing offline smoke command and summary unchanged.

- [ ] **Step 4: Run contract tests and actionlint**

Run:

```bash
cd backend
uv run pytest -q tests/test_gpu_smoke_workflow.py
cd ..
actionlint .github/workflows/gpu-smoke.yml
```

Expected: two tests pass and actionlint exits 0.

- [ ] **Step 5: Commit the schedule**

```bash
git add .github/workflows/gpu-smoke.yml backend/tests/test_gpu_smoke_workflow.py
git commit -m "ci: schedule weekly offline GPU smoke" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 6: Generate deterministic SVG and Lottie VJ cues

**Files:**

- Create: `backend/src/melosviz/export/__init__.py`
- Create: `backend/src/melosviz/export/vj.py`
- Create: `backend/tests/export/test_vj.py`

- [ ] **Step 1: Write failing shot-discovery and cue tests**

Create `backend/tests/export/test_vj.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from melosviz.export.vj import discover_shots, export_vj_cues


def test_discover_shots_prefers_multi_shot_plan(tmp_path: Path) -> None:
    (tmp_path / "plan.json").write_text(json.dumps({
        "shots": [{
            "scene_index": 2,
            "shot_index": 1,
            "duration_s": 4.0,
            "prompt": "hero <wide>",
            "camera_motion": "orbit",
        }]
    }))
    (tmp_path / "storyboard.json").write_text(json.dumps({
        "scenes": [{"index": 9, "duration": 8.0, "prompt": "fallback"}]
    }))
    shots = discover_shots(tmp_path, [])
    assert [(shot["scene_index"], shot["shot_index"]) for shot in shots] == [(2, 1)]


def test_export_vj_cues_writes_deterministic_svg_and_lottie(tmp_path: Path) -> None:
    shots = [{
        "scene_index": 1,
        "shot_index": 2,
        "start": 10.0,
        "duration_s": 4.0,
        "label": "chorus & drop",
        "prompt": "hero <wide>",
        "camera_motion": "orbit",
        "palette": ["#ff00aa", "#00ffee"],
        "beats": [10.0, 12.0, 14.0],
        "width": 1920,
        "height": 1080,
        "fps": 24,
    }]
    first = export_vj_cues(shots, tmp_path / "vj")
    svg_path = tmp_path / "vj" / "shot-0001-02.svg"
    lottie_path = tmp_path / "vj" / "shot-0001-02.lottie.json"
    first_svg = svg_path.read_bytes()
    first_lottie = lottie_path.read_bytes()
    second = export_vj_cues(shots, tmp_path / "vj")
    assert first == second
    assert svg_path.read_bytes() == first_svg
    assert lottie_path.read_bytes() == first_lottie
    assert "chorus &amp; drop" in first_svg.decode()
    lottie = json.loads(first_lottie)
    assert lottie["v"] == "5.12.0"
    assert lottie["op"] == 96
    assert {layer["ty"] for layer in lottie["layers"]} == {4, 5}
    assert any(
        layer.get("t", {}).get("d", {}).get("k", [{}])[0].get("s", {}).get("t")
        == "chorus & drop"
        for layer in lottie["layers"]
        if layer["ty"] == 5
    )
    assert any(
        layer.get("t", {}).get("d", {}).get("k", [{}])[0].get("s", {}).get("t")
        == "hero <wide>"
        for layer in lottie["layers"]
        if layer["ty"] == 5
    )
    assert [marker["cm"] for marker in lottie["markers"]] == [
        "shot-start", "beat-000", "beat-001", "beat-002", "shot-end"
    ]
```

- [ ] **Step 2: Run and verify missing export package**

Run:

```bash
cd backend
uv run pytest -q tests/export/test_vj.py
```

Expected: collection fails because `melosviz.export` is absent.

- [ ] **Step 3: Implement normalized shot discovery and cue writers**

Create `backend/src/melosviz/export/__init__.py`:

```python
"""Portable delivery exporters for MelosViz."""

from .vj import discover_shots, export_vj_cues

__all__ = ["discover_shots", "export_vj_cues"]
```

Create `backend/src/melosviz/export/vj.py` with:

```python
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Iterable, Sequence


def _json_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.json")
        if "deliverables" not in path.parts and "vj" not in path.parts
    )


def _load_objects(root: Path) -> list[dict]:
    objects = []
    for path in _json_files(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def _normalize_shot(raw: dict, fallback_index: int) -> dict:
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    scene_index = int(raw.get("scene_index", raw.get("index", fallback_index)))
    shot_index = int(raw.get("shot_index", 0))
    start = float(raw.get(
        "start", raw.get("start_seconds", extra.get("start_seconds", 0.0))
    ) or 0.0)
    duration = float(raw.get("duration_s", raw.get("duration", 0.0)) or 0.0)
    if duration <= 0 and raw.get("end") is not None:
        duration = max(0.0, float(raw["end"]) - start)
    if duration <= 0 and extra.get("end_seconds") is not None:
        duration = max(0.0, float(extra["end_seconds"]) - start)
    beats = raw.get("beats") or raw.get("beats_in_segment") or raw.get(
        "beat_seconds"
    ) or extra.get("beat_seconds") or []
    palette = raw.get("palette") or raw.get("palette_override") or ["#7c6af7"]
    return {
        "scene_index": scene_index,
        "shot_index": shot_index,
        "start": start,
        "duration_s": max(1 / 24, duration),
        "label": str(raw.get("label", raw.get("scene_name", f"scene-{scene_index}"))),
        "prompt": str(raw.get("prompt", "")),
        "camera_motion": str(raw.get("camera_motion", raw.get("camera", "static"))),
        "palette": [str(value) for value in palette],
        "beats": [float(value) for value in beats],
        "width": int(raw.get("width", 1920) or 1920),
        "height": int(raw.get("height", 1080) or 1080),
        "fps": int(raw.get("fps", 24) or 24),
    }


def discover_shots(job_dir: Path, media_paths: Sequence[Path]) -> list[dict]:
    objects = _load_objects(job_dir)
    for key in ("shots", "scenes"):
        for payload in objects:
            values = payload.get(key)
            if isinstance(values, list) and values:
                shots = [
                    _normalize_shot(value, index)
                    for index, value in enumerate(values)
                    if isinstance(value, dict)
                ]
                return sorted(shots, key=lambda item: (
                    item["scene_index"], item["shot_index"]
                ))
    provenance = [
        payload for payload in objects
        if "artifact_path" in payload and "scene_index" in payload
    ]
    if provenance:
        return sorted(
            [_normalize_shot(value, index) for index, value in enumerate(provenance)],
            key=lambda item: (item["scene_index"], item["shot_index"]),
        )
    return [
        _normalize_shot({"index": index, "label": path.stem}, index)
        for index, path in enumerate(sorted(media_paths, key=lambda value: value.as_posix()))
    ]


def _svg(shot: dict) -> str:
    label = html.escape(shot["label"][:80], quote=True)
    prompt = html.escape(" ".join(shot["prompt"].split())[:180], quote=True)
    camera = html.escape(shot["camera_motion"][:80], quote=True)
    colors = shot["palette"] or ["#7c6af7"]
    duration = shot["duration_s"]
    beat_lines = []
    for beat in shot["beats"]:
        relative = (beat - shot["start"]) / duration
        x = 64 + round(max(0.0, min(1.0, relative)) * 832, 3)
        beat_lines.append(
            f'<line x1="{x}" y1="455" x2="{x}" y2="500" stroke="#ffffff" />'
        )
    swatches = "".join(
        f'<rect x="{64 + index * 96}" y="300" width="80" height="80" '
        f'fill="{html.escape(color, quote=True)}" />'
        for index, color in enumerate(colors[:8])
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" '
        'viewBox="0 0 960 540">\n'
        '<rect width="960" height="540" fill="#0d0d10" />\n'
        f'<text x="64" y="72" fill="#ffffff" font-size="30">{label}</text>\n'
        f'<text x="64" y="120" fill="#ccccd8" font-size="18">{camera}</text>\n'
        f'<text x="64" y="176" fill="#ffffff" font-size="20">{prompt}</text>\n'
        f'{swatches}\n'
        '<line x1="64" y1="480" x2="896" y2="480" stroke="#888899" />\n'
        f'{"".join(beat_lines)}\n'
        f'<text x="64" y="525" fill="#ccccd8" font-size="16">'
        f'{shot["start"]:.3f}s + {duration:.3f}s</text>\n'
        '</svg>\n'
    )


def _lottie(shot: dict) -> dict:
    fps = shot["fps"]
    frames = max(1, round(shot["duration_s"] * fps))
    markers = [{"tm": 0, "cm": "shot-start", "dr": 0}]
    for index, beat in enumerate(shot["beats"]):
        frame = round(max(0.0, beat - shot["start"]) * fps)
        markers.append({"tm": min(frames, frame), "cm": f"beat-{index:03d}", "dr": 0})
    markers.append({"tm": frames, "cm": "shot-end", "dr": 0})
    color = shot["palette"][0] if shot["palette"] else "#7c6af7"
    rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)] \
        if len(color) == 7 and color.startswith("#") else [0.486, 0.416, 0.969]
    return {
        "v": "5.12.0",
        "fr": fps,
        "ip": 0,
        "op": frames,
        "w": shot["width"],
        "h": shot["height"],
        "nm": f'shot-{shot["scene_index"]:04d}-{shot["shot_index"]:02d}',
        "ddd": 0,
        "assets": [],
        "layers": [{
            "ddd": 0,
            "ind": 1,
            "ty": 4,
            "nm": "palette-field",
            "sr": 1,
            "ks": {
                "o": {"a": 0, "k": 100},
                "r": {"a": 0, "k": 0},
                "p": {"a": 0, "k": [shot["width"] / 2, shot["height"] / 2, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 0, "k": [100, 100, 100]},
            },
            "shapes": [{
                "ty": "fl",
                "c": {"a": 0, "k": [*rgb, 1]},
                "o": {"a": 0, "k": 100},
                "r": 1,
                "nm": "palette-fill",
            }],
            "ip": 0,
            "op": frames,
            "st": 0,
            "bm": 0,
        }, {
            "ddd": 0,
            "ind": 2,
            "ty": 5,
            "nm": "shot-label",
            "sr": 1,
            "ks": {
                "o": {"a": 0, "k": 100},
                "r": {"a": 0, "k": 0},
                "p": {"a": 0, "k": [64, 96, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 0, "k": [100, 100, 100]},
            },
            "t": {
                "d": {"k": [{
                    "s": {
                        "sz": [shot["width"] - 128, 180],
                        "ps": [0, 0],
                        "s": 48,
                        "f": "Arial",
                        "t": shot["label"][:80],
                        "j": 0,
                        "tr": 0,
                        "lh": 58,
                        "ls": 0,
                        "fc": [1, 1, 1],
                    },
                    "t": 0,
                }]},
                "p": {},
                "m": {"g": 1, "a": {"a": 0, "k": [0, 0]}},
            },
            "ip": 0,
            "op": frames,
            "st": 0,
            "bm": 0,
        }, {
            "ddd": 0,
            "ind": 3,
            "ty": 5,
            "nm": "prompt-summary",
            "sr": 1,
            "ks": {
                "o": {"a": 0, "k": 100},
                "r": {"a": 0, "k": 0},
                "p": {"a": 0, "k": [64, 180, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 0, "k": [100, 100, 100]},
            },
            "t": {
                "d": {"k": [{
                    "s": {
                        "sz": [shot["width"] - 128, 280],
                        "ps": [0, 0],
                        "s": 28,
                        "f": "Arial",
                        "t": " ".join(shot["prompt"].split())[:180],
                        "j": 0,
                        "tr": 0,
                        "lh": 36,
                        "ls": 0,
                        "fc": [1, 1, 1],
                    },
                    "t": 0,
                }]},
                "p": {},
                "m": {"g": 1, "a": {"a": 0, "k": [0, 0]}},
            },
            "ip": 0,
            "op": frames,
            "st": 0,
            "bm": 0,
        }],
        "markers": markers,
        "meta": {
            "scene_index": shot["scene_index"],
            "shot_index": shot["shot_index"],
            "label": shot["label"],
            "prompt": " ".join(shot["prompt"].split())[:180],
            "camera_motion": shot["camera_motion"],
        },
    }


def export_vj_cues(shots: Iterable[dict], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for raw in shots:
        shot = _normalize_shot(raw, len(written))
        stem = f'shot-{shot["scene_index"]:04d}-{shot["shot_index"]:02d}'
        svg_path = output_dir / f"{stem}.svg"
        lottie_path = output_dir / f"{stem}.lottie.json"
        svg_path.write_text(_svg(shot), encoding="utf-8")
        lottie_path.write_text(
            json.dumps(_lottie(shot), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        written.extend([svg_path, lottie_path])
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0",
        "cue_count": len(written) // 2,
        "files": [path.name for path in written],
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    written.append(manifest)
    return written
```

- [ ] **Step 4: Run VJ tests and lint**

Run:

```bash
cd backend
uv run pytest -q tests/export/test_vj.py
uv run ruff check src/melosviz/export tests/export/test_vj.py
```

Expected: two tests pass and ruff exits 0.

- [ ] **Step 5: Add provenance and media fallback tests**

Append these exact tests to `backend/tests/export/test_vj.py`:

```python
def test_discover_shots_reads_provenance_timing(tmp_path: Path) -> None:
    sidecar = tmp_path / "clip.mp4.provenance.json"
    sidecar.write_text(json.dumps({
        "artifact_path": str(tmp_path / "clip.mp4"),
        "scene_index": 3,
        "scene_name": "bridge",
        "prompt": "type morph",
        "extra": {
            "start_seconds": 12.0,
            "end_seconds": 16.0,
            "beat_seconds": [12.0, 14.0, 16.0],
        },
    }))
    shots = discover_shots(tmp_path, [])
    assert len(shots) == 1
    assert shots[0]["scene_index"] == 3
    assert shots[0]["start"] == 12.0
    assert shots[0]["duration_s"] == 4.0
    assert shots[0]["beats"] == [12.0, 14.0, 16.0]


def test_discover_shots_orders_media_by_relative_path(tmp_path: Path) -> None:
    first = tmp_path / "a" / "z.mp4"
    second = tmp_path / "b" / "a.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    shots = discover_shots(tmp_path, [second, first])
    assert [shot["label"] for shot in shots] == ["z", "a"]
    assert [shot["scene_index"] for shot in shots] == [0, 1]
```

Run:

```bash
cd backend
uv run pytest -q tests/export/test_vj.py
```

Expected: four tests pass.

- [ ] **Step 6: Commit VJ export**

```bash
git add backend/src/melosviz/export/__init__.py \
  backend/src/melosviz/export/vj.py backend/tests/export/test_vj.py
git commit -m "feat(export): add SVG and Lottie VJ cues" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 7: Create a real deterministic final.zip

**Files:**

- Create: `backend/src/melosviz/export/package.py`
- Create: `backend/tests/export/test_package.py`
- Create: `backend/tests/cli/test_ship.py`
- Modify: `backend/src/melosviz/export/__init__.py`
- Modify: `backend/src/melosviz/cli/main.py:1050-1102`
- Modify: `backend/tests/test_e2e_3min_pipeline.py:198-214`

- [ ] **Step 1: Write failing package tests**

Create `backend/tests/export/test_package.py`:

```python
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from melosviz.export.package import build_delivery_package


def test_online_package_contains_media_manifest_and_vj(tmp_path: Path) -> None:
    media = tmp_path / "festival_master.mov"
    media.write_bytes(b"movie")
    (tmp_path / "storyboard.json").write_text(json.dumps({
        "scenes": [{
            "index": 0,
            "label": "intro",
            "start": 0.0,
            "duration": 4.0,
            "prompt": "neon intro",
            "beats_in_segment": [0.0, 2.0, 4.0],
        }]
    }))
    result = build_delivery_package(tmp_path)
    assert result["mode"] == "online"
    assert Path(result["final_zip"]).is_file()
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
    assert "deliverables/festival_master.mov" in names
    assert "manifest.json" in names
    assert "vj/shot-0000-00.svg" in names
    assert "vj/shot-0000-00.lottie.json" in names


def test_package_is_byte_deterministic(tmp_path: Path) -> None:
    (tmp_path / "club.mp4").write_bytes(b"video")
    first = build_delivery_package(tmp_path)
    first_bytes = Path(first["final_zip"]).read_bytes()
    second = build_delivery_package(tmp_path)
    assert Path(second["final_zip"]).read_bytes() == first_bytes


def test_package_failure_preserves_previous_zip(tmp_path: Path, monkeypatch) -> None:
    final_zip = tmp_path / "final.zip"
    final_zip.write_bytes(b"previous-valid-zip")
    (tmp_path / "club.mp4").write_bytes(b"video")

    real_replace = __import__("os").replace

    def fail_replace(source, target):
        if Path(target).name == "final.zip":
            raise OSError("replace failed")
        real_replace(source, target)

    monkeypatch.setattr("melosviz.export.package.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        build_delivery_package(tmp_path)
    assert final_zip.read_bytes() == b"previous-valid-zip"
    assert not (tmp_path / ".final.zip.tmp").exists()


def test_offline_package_retains_readme_and_empty_vj_manifest(tmp_path: Path) -> None:
    result = build_delivery_package(tmp_path)
    assert result["mode"] == "offline"
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
    assert "README.txt" in names
    assert "manifest.json" in names
    assert "vj/manifest.json" in names


def test_duplicate_media_basenames_keep_distinct_archive_paths(tmp_path: Path) -> None:
    first = tmp_path / "festival" / "master.mp4"
    second = tmp_path / "club" / "master.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"festival")
    second.write_bytes(b"club")
    result = build_delivery_package(tmp_path)
    with zipfile.ZipFile(result["final_zip"]) as archive:
        names = archive.namelist()
        assert archive.read("deliverables/festival/master.mp4") == b"festival"
        assert archive.read("deliverables/club/master.mp4") == b"club"
    assert names.count("deliverables/festival/master.mp4") == 1
    assert names.count("deliverables/club/master.mp4") == 1
```

- [ ] **Step 2: Run and verify the missing package module**

Run:

```bash
cd backend
uv run pytest -q tests/export/test_package.py
```

Expected: collection fails because `melosviz.export.package` is absent.

- [ ] **Step 3: Implement deterministic media discovery and atomic ZIP writing**

Create `backend/src/melosviz/export/package.py`:

```python
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

from .vj import discover_shots, export_vj_cues


MEDIA_PATTERNS = ("*.mp4", "*.mov", "*.wav", "*.aif", "*.srt", "*.vtt", "*.edl")
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def _discover_media(job_dir: Path) -> list[Path]:
    excluded = {job_dir / "final.zip", job_dir / ".final.zip.tmp"}
    found: set[Path] = set()
    for pattern in MEDIA_PATTERNS:
        for path in job_dir.rglob(pattern):
            if path.is_file() and path not in excluded and "deliverables" not in path.parts:
                found.add(path)
    return sorted(found, key=lambda path: path.relative_to(job_dir).as_posix())


def _safe_archive_name(relative: Path) -> str:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe archive path: {relative}")
    return relative.as_posix()


def _write_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(_safe_archive_name(Path(name)), FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def build_delivery_package(job_dir: Path) -> dict:
    root = job_dir.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    media = _discover_media(root)
    deliverables = root / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in media:
        relative = source.relative_to(root)
        target = deliverables / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)

    shots = discover_shots(root, media)
    vj_files = export_vj_cues(shots, deliverables / "vj")
    mode = "online" if media else "offline"
    manifest = {
        "schema_version": "1.0",
        "job_dir": str(root),
        "mode": mode,
        "count": len(copied),
        "deliverables": [
            path.relative_to(deliverables).as_posix() for path in copied
        ],
        "vj": [path.relative_to(deliverables).as_posix() for path in vj_files],
    }
    if mode == "offline":
        manifest["note"] = (
            "No rendered media files found. Re-run viz master and viz ship "
            "after rendering real clips."
        )
    manifest_path = deliverables / "manifest.json"
    _atomic_json(manifest_path, manifest)

    final_zip = root / "final.zip"
    temporary_zip = root / ".final.zip.tmp"
    try:
        with zipfile.ZipFile(temporary_zip, "w") as archive:
            if mode == "offline":
                _write_entry(
                    archive,
                    "README.txt",
                    b"MelosViz offline render - no clips produced yet.\n",
                )
            _write_entry(archive, "manifest.json", manifest_path.read_bytes())
            for path in sorted(copied, key=lambda value: value.as_posix()):
                name = "deliverables/" + path.relative_to(deliverables).as_posix()
                if path.is_file():
                    _write_entry(archive, name, path.read_bytes())
            for path in sorted(vj_files, key=lambda value: value.as_posix()):
                name = path.relative_to(deliverables).as_posix()
                if path.is_file():
                    _write_entry(archive, name, path.read_bytes())
        os.replace(temporary_zip, final_zip)
    except BaseException:
        if temporary_zip.exists():
            temporary_zip.unlink()
        raise
    return {
        **manifest,
        "manifest": str(manifest_path),
        "final_zip": str(final_zip),
        "final_zip_bytes": final_zip.stat().st_size,
    }
```

Update `backend/src/melosviz/export/__init__.py`:

```python
from .package import build_delivery_package
from .vj import discover_shots, export_vj_cues

__all__ = ["build_delivery_package", "discover_shots", "export_vj_cues"]
```

- [ ] **Step 4: Run package tests and fix deterministic entry order**

Run:

```bash
cd backend
uv run pytest -q tests/export/test_package.py
uv run ruff check src/melosviz/export tests/export
```

Expected: five tests pass and ruff exits 0. If byte determinism fails, inspect
archive entry order and generated JSON; do not weaken the byte assertion.

- [ ] **Step 5: Write failing CLI tests**

Create `backend/tests/cli/test_ship.py`:

```python
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from melosviz.cli.main import main


def test_ship_online_prints_zip_metadata(tmp_path: Path, capsys) -> None:
    (tmp_path / "master.mp4").write_bytes(b"video")
    with pytest.raises(SystemExit) as exit_info:
        main(["ship", str(tmp_path)])
    assert exit_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "online"
    assert payload["final_zip"].endswith("final.zip")
    assert payload["final_zip_bytes"] > 0
    with zipfile.ZipFile(payload["final_zip"]) as archive:
        assert "deliverables/master.mp4" in archive.namelist()


def test_ship_missing_directory_exits_nonzero(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        main(["ship", str(missing)])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("main must exit nonzero for a missing job directory")
```

- [ ] **Step 6: Run and verify online CLI metadata failure**

Run:

```bash
cd backend
uv run pytest -q tests/cli/test_ship.py
```

Expected: the online test fails because current `_cmd_ship` does not create or
print `final_zip` metadata.

- [ ] **Step 7: Replace `_cmd_ship` with the package boundary**

Replace the body of `_cmd_ship` in `backend/src/melosviz/cli/main.py` with:

```python
def _cmd_ship(args: argparse.Namespace) -> int:
    """Package final deliverables and portable festival-VJ cues."""
    from melosviz.export.package import build_delivery_package
    from melosviz.i18n import t

    job_dir = Path(args.job_dir)
    if not job_dir.is_dir():
        print(t("cli.error.dir_not_found", path=job_dir), file=sys.stderr)
        return 1
    try:
        payload = build_delivery_package(job_dir)
    except (OSError, ValueError) as exc:
        print(f"viz ship failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0
```

- [ ] **Step 8: Run CLI and package tests**

Run:

```bash
cd backend
uv run pytest -q tests/export/test_package.py tests/export/test_vj.py \
  tests/cli/test_ship.py tests/test_bridge_studio_pipeline.py
```

Expected: all tests pass. The bridge tests must continue to parse the same
`final_zip`, byte-size, and manifest fields.

- [ ] **Step 9: Strengthen the three-minute acceptance assertion**

In `backend/tests/test_e2e_3min_pipeline.py`, replace the final JSON-only ZIP
assertion with an offline-aware topology check:

```python
with zipfile.ZipFile(zips[0], "r") as archive:
    names = archive.namelist()
    manifest = json.loads(archive.read("manifest.json"))
assert "manifest.json" in names
assert "vj/manifest.json" in names
if manifest["mode"] == "online":
    assert any(name.startswith("vj/") and name.endswith(".svg") for name in names)
    assert any(
        name.startswith("vj/") and name.endswith(".lottie.json") for name in names
    )
```

Run:

```bash
cd backend
MELOSVIZ_COMFYUI_OFFLINE=1 uv run pytest -q -m slow \
  tests/test_e2e_3min_pipeline.py
```

Expected: the full five-step pipeline passes. Its current offline master path
contains `vj/manifest.json`; the online package unit test proves both cue
formats for rendered media. If ffmpeg is unavailable, the test may report a
documented skip; do not call a skip a passing render.

- [ ] **Step 10: Commit deterministic shipping**

```bash
git add backend/src/melosviz/export backend/src/melosviz/cli/main.py \
  backend/tests/export backend/tests/cli/test_ship.py \
  backend/tests/test_e2e_3min_pipeline.py
git commit -m "feat(ship): package deterministic VJ delivery archive" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 8: Extend offline smoke acceptance and operator documentation

**Files:**

- Modify: `backend/tests/cli/test_gpu_smoke.py`
- Create: `docs/specs/acceptance/production_delivery_extensions.feature`
- Modify: `docs/ENV.md`
- Modify: `docs/STUDIO_PIPELINE.md`

- [ ] **Step 1: Extend the offline smoke through ship**

After the existing generated-workflow assertions in
`backend/tests/cli/test_gpu_smoke.py`, add an offline `ship` call against the
generated directory and assert:

```python
_run_cli(["ship", str(gen_path)], WORKDIR, env)
final_zip = gen_path / "final.zip"
assert final_zip.is_file() and final_zip.stat().st_size > 0
```

Add `import zipfile` with the standard imports and then assert archive topology:

```python
with zipfile.ZipFile(final_zip) as archive:
    names = archive.namelist()
assert "manifest.json" in names
assert "vj/manifest.json" in names
```

- [ ] **Step 2: Write operator acceptance scenarios**

Create `docs/specs/acceptance/production_delivery_extensions.feature`:

```gherkin
Feature: Production delivery extensions
  Scenario: Director refinement is rate limited without changing models
    Given an OpenAI-compatible Director endpoint returns HTTP 429
    When the endpoint supplies a Retry-After delay
    Then MelosViz retries after that delay with the configured model
    And deterministic template prompts remain available if retries fail

  Scenario: Every completed clip has review evidence
    Given a scene render completes
    When MelosViz writes clip provenance
    Then the record contains artifact and prompt hashes
    And a deterministic SVG timeline thumbnail exists

  Scenario: Festival delivery includes portable cues
    Given a rendered master and storyboard metadata
    When the operator runs viz ship
    Then final.zip contains the media manifest
    And final.zip contains one SVG and one Lottie cue per discovered shot

  Scenario: Offline GPU smoke remains honest
    Given no physical GPU backend is connected
    When the weekly GPU smoke workflow runs in offline mode
    Then it verifies deterministic artifact topology
    And it does not claim physical GPU rendering succeeded
```

- [ ] **Step 3: Document exact environment variables**

Add these rows to the Director section in `docs/ENV.md`:

```markdown
| `MELOSVIZ_LLM_REQUESTS_PER_MINUTE` | `30` | Director | Starts per rolling 60-second window |
| `MELOSVIZ_LLM_MAX_CONCURRENCY` | `2` | Director | Simultaneous LLM HTTP attempts |
| `MELOSVIZ_LLM_MAX_QUEUE` | `32` | Director | Waiting attempts before template fallback |
| `MELOSVIZ_LLM_MAX_RETRIES` | `3` | Director | 429/5xx retry count |
| `MELOSVIZ_LLM_COST_CAP_USD` | `1.00` | Director | Process-local estimated/actual spend ceiling |
| `MELOSVIZ_LLM_INPUT_USD_PER_MILLION` | required for LLM | Director | Operator-supplied input-token price |
| `MELOSVIZ_LLM_OUTPUT_USD_PER_MILLION` | required for LLM | Director | Operator-supplied output-token price |
| `MELOSVIZ_LLM_MAX_OUTPUT_TOKENS` | `2048` | Director | Preflight output reservation |
```

- [ ] **Step 4: Document visual diff and ZIP layouts**

In `docs/STUDIO_PIPELINE.md`, add the generated scene review artifacts:

```text
scene_002/
|- clip.mp4.provenance.json
|- visual-diff-frame.png
`- visual-diff.svg
```

Extend the `final.zip` list with:

```text
vj/
|- manifest.json
|- shot-0002-01.svg
`- shot-0002-01.lottie.json
```

State explicitly that SVG/Lottie files are cue and timing metadata, not
vectorized copies of rendered footage, and that the scheduled GPU smoke is an
offline topology check.

- [ ] **Step 5: Run smoke, docs, and focused suites**

Run:

```bash
cd backend
MELOSVIZ_COMFYUI_OFFLINE=1 uv run pytest -q -m slow \
  tests/cli/test_gpu_smoke.py
uv run pytest -q tests/llm/test_admission.py tests/llm/test_director.py \
  tests/conductor/test_visual_diff.py tests/conductor/test_provenance.py \
  tests/conductor/test_orchestrator_provenance.py \
  tests/export/test_vj.py tests/export/test_package.py \
  tests/cli/test_ship.py tests/test_gpu_smoke_workflow.py
cd ..
python scripts/check_wbs.py
python scripts/check_fr_status.py
actionlint .github/workflows/gpu-smoke.yml
```

Expected: all focused tests pass, smoke passes or reports only an explicit
ffmpeg skip, both documentation checks exit 0, and actionlint exits 0.

- [ ] **Step 6: Commit docs and acceptance coverage**

```bash
git add backend/tests/cli/test_gpu_smoke.py \
  docs/specs/acceptance/production_delivery_extensions.feature \
  docs/ENV.md docs/STUDIO_PIPELINE.md
git commit -m "docs: document production delivery extensions" \
  -m "DAG-Id: melosviz-production-delivery-extensions"
```

## Task 9: Full local verification and handoff

**Files:**

- Verify only; modify files only for failures directly caused by this branch.

- [ ] **Step 1: Verify worktree and requirement coverage**

Run:

```bash
git status --short --branch
git diff main...HEAD --stat
git log --oneline main..HEAD
```

Expected: only planned files differ, the branch contains the design/plan plus
the focused implementation commits, and the tree is clean before full tests.

- [ ] **Step 2: Run the complete backend suite**

Run:

```bash
cd backend
uv run pytest -q tests/
```

Expected: exit 0 with zero failures. Record the exact pass/skip counts from the
fresh output. Do not infer hosted CI from this local run.

- [ ] **Step 3: Run lint and type checks**

Run:

```bash
cd backend
uv run ruff check src tests
uv run mypy src/melosviz/llm/admission.py \
  src/melosviz/conductor/visual_diff.py \
  src/melosviz/export/vj.py src/melosviz/export/package.py
cd ..
actionlint .github/workflows/gpu-smoke.yml
git diff --check main...HEAD
```

Expected: every command exits 0.

- [ ] **Step 4: Run the two slow acceptance paths explicitly**

Run:

```bash
cd backend
MELOSVIZ_COMFYUI_OFFLINE=1 uv run pytest -q -m slow \
  tests/cli/test_gpu_smoke.py tests/test_e2e_3min_pipeline.py
```

Expected: both tests pass when ffmpeg is installed. If either skips, report the
exact missing prerequisite and keep that acceptance gate open.

- [ ] **Step 5: Verify the final archive manually from a test fixture**

Run:

```bash
cd backend
uv run pytest -q tests/cli/test_ship.py::test_ship_online_prints_zip_metadata -s
```

Expected: one test passes. The automated assertion opens the ZIP and verifies
media, manifest, SVG, and Lottie entries; no production deliverable is created.

- [ ] **Step 6: Reconcile hosted state without mutating it**

Run:

```bash
gh run list --branch main --limit 10 \
  --json databaseId,name,status,conclusion,headSha,createdAt,url
gh pr list --head feat/production-delivery-extensions --json number,state,url
```

Expected: report current hosted failures/successes separately. An empty PR list
is expected because this plan does not authorize push or PR creation.

- [ ] **Step 7: Present the local handoff gate**

Report:

- branch and exact HEAD SHA;
- clean/dirty state;
- commit list;
- exact full-suite, focused-suite, lint, type-check, actionlint, and slow-test
  results;
- any skipped physical-tool validation;
- current hosted `main` failures as pre-existing or newly observed evidence;
- the explicit next gate: approval to push and open one PR.

Do not call the feature shipped, merged, or released until the PR is reviewed,
required hosted checks pass, and the protected merge completes.
