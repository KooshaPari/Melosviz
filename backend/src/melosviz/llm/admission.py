from __future__ import annotations

import math
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Condition, Lock
from types import TracebackType


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
    ) -> LLMAdmissionConfig:
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
        self, gate: LLMAdmissionGate, estimate: LLMCostEstimate
    ) -> None:
        self._gate = gate
        self.estimate = estimate
        self._condition = Condition()
        self._attempts = 0
        self._closed = False

    def attempt(self) -> LLMAttempt:
        return LLMAttempt(self._gate, self)

    def _begin_attempt(self) -> None:
        with self._condition:
            if self._closed:
                raise LLMAdmissionError("reservation is already closed")
            self._attempts += 1

    def _finish_attempt(self) -> None:
        with self._condition:
            self._attempts -= 1
            self._condition.notify_all()

    def settle(self, actual_usd: Decimal | None = None) -> None:
        with self._condition:
            while self._attempts:
                self._condition.wait()
            if not self._closed:
                self._gate._finish_reservation(
                    self.estimate.usd,
                    self.estimate.usd if actual_usd is None else actual_usd,
                )
                self._closed = True

    def release(self) -> None:
        with self._condition:
            while self._attempts:
                self._condition.wait()
            if not self._closed:
                self._gate._finish_reservation(self.estimate.usd, Decimal(0))
                self._closed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.settle()


class LLMAttempt(AbstractContextManager["LLMAttempt"]):
    def __init__(
        self, gate: LLMAdmissionGate, reservation: LLMReservation
    ) -> None:
        self._gate = gate
        self._reservation = reservation
        self._entered = False
        self._finished = False

    def __enter__(self) -> LLMAttempt:
        if self._entered or self._finished:
            raise LLMAdmissionError("attempt context cannot be reused")
        try:
            self._reservation._begin_attempt()
        except BaseException:
            self._finished = True
            raise
        try:
            self._gate._enter_attempt()
        except BaseException:
            self._finished = True
            self._reservation._finish_attempt()
            raise
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._entered:
            try:
                self._gate._leave_attempt()
            finally:
                self._entered = False
                self._finished = True
                self._reservation._finish_attempt()


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

        try:
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
        except BaseException:
            with self._condition:
                with suppress(ValueError):
                    self._tickets.remove(ticket)
                self._condition.notify_all()
            raise

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
