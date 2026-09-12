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
    """Monetary pre-estimate for an LLM call (input + capped output tokens)."""

    input_tokens: int
    output_tokens: int
    usd: Decimal


@dataclass(frozen=True)
class LLMAdmissionConfig:
    """Immutable configuration for :class:`LLMAdmissionGate`.

    Drives the rate / concurrency / cost-cap policy enforced for every
    Director LLM call.
    """

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
        """Build a config from ``MELOSVIZ_LLM_*`` environment variables.

        Falls back to ``(30, 2, 32, 3, 1.00)`` for the numeric fields. Pricing
        fields have no default — the operator must opt in to LLM spend.
        """
        source = os.environ if env is None else env

        def positive_int(name: str, default: str) -> int:
            """Parse a strictly positive integer env-var with a default."""
            raw = source.get(name, default)
            try:
                value = int(raw)
            except ValueError as exc:
                raise LLMAdmissionError(f"{name} must be an integer") from exc
            if value <= 0:
                raise LLMAdmissionError(f"{name} must be greater than zero")
            return value

        def non_negative_decimal(name: str, default: str | None = None) -> Decimal:
            """Parse a finite, non-negative Decimal env-var, defaulting to raising."""
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
        """Estimate cost for ``payload`` assuming a worst-case output."""
        input_tokens = max(1, math.ceil(len(payload) / 4))
        million = Decimal(1_000_000)
        usd = (
            Decimal(input_tokens) * self.input_usd_per_million
            + Decimal(self.max_output_tokens) * self.output_usd_per_million
        ) / million
        return LLMCostEstimate(input_tokens, self.max_output_tokens, usd)

    def actual_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Compute the actual spend for a reported token usage pair."""
        million = Decimal(1_000_000)
        return (
            Decimal(max(0, input_tokens)) * self.input_usd_per_million
            + Decimal(max(0, output_tokens)) * self.output_usd_per_million
        ) / million


class LLMReservation(AbstractContextManager["LLMReservation"]):
    """A reserved budget slot for one logical LLM call (potentially retried)."""

    def __init__(
        self, gate: LLMAdmissionGate, estimate: LLMCostEstimate
    ) -> None:
        """Record the reservation against the gate's budget ledger."""
        self._gate = gate
        self.estimate = estimate
        self._condition = Condition()
        self._attempts = 0
        self._closed = False
        #: ``True`` once at least one :class:`LLMAttempt` has *entered*
        #: the queue (i.e. was admitted into the rate / concurrency slots).
        #: Rejected attempts (queue full, cost-cap exceeded, lock failure)
        #: do not flip this — the reservation never executed the LLM call
        #: so the actual spend is 0. ``settle()`` falls back to
        #: release-semantics when this is False.
        self._any_attempt_entered = False

    def attempt(self) -> LLMAttempt:
        """Create a new attempt context manager (one HTTP request)."""
        return LLMAttempt(self._gate, self)

    def _begin_attempt(self) -> None:
        """Increment the in-flight counter for this reservation."""
        with self._condition:
            if self._closed:
                raise LLMAdmissionError("reservation is already closed")
            self._attempts += 1

    def _finish_attempt(self) -> None:
        """Decrement the in-flight counter and wake any waiters."""
        with self._condition:
            self._attempts -= 1
            self._condition.notify_all()

    def _record_attempt_entered(self) -> None:
        """Mark that at least one attempt was admitted into the queue."""
        with self._condition:
            self._any_attempt_entered = True

    def settle(self, actual_usd: Decimal | None = None) -> None:
        """Close the reservation with the true spend so the ledger balances.

        Records ``0`` if no attempt ever entered the queue (rejection
        semantics), the estimate if ``actual_usd`` is ``None`` and at least
        one attempt ran, otherwise the explicit ``actual_usd``.
        """
        with self._condition:
            while self._attempts:
                self._condition.wait()
            if not self._closed:
                if not self._any_attempt_entered:
                    # No attempt ever entered the queue (every attempt was
                    # rejected — queue full, cost cap, sleeper failure…).
                    # No LLM call ran, so the actual spend is 0; behave
                    # like :meth:`release`.
                    actual = Decimal(0)
                elif actual_usd is None:
                    actual = self.estimate.usd
                else:
                    actual = actual_usd
                self._gate._finish_reservation(self.estimate.usd, actual)
                self._closed = True

    def release(self) -> None:
        """Close the reservation without spending (used on early aborts)."""
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
        """Delegate to :meth:`settle` so ``with reservation: ...`` works."""
        self.settle()


class LLMAttempt(AbstractContextManager["LLMAttempt"]):
    """A single attempt to enter the queue and call the LLM once."""

    def __init__(
        self, gate: LLMAdmissionGate, reservation: LLMReservation
    ) -> None:
        """Bind the attempt to its gate and reservation."""
        self._gate = gate
        self._reservation = reservation
        self._entered = False
        self._finished = False

    def __enter__(self) -> LLMAttempt:
        """Reserve a queue ticket and wait for a worker / rate slot."""
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
        # Only flip after ``_enter_attempt`` returns — i.e. the attempt
        # was admitted into the rate / concurrency slots. Rejections are
        # invisible to the reservation ledger.
        self._reservation._record_attempt_entered()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the worker slot and reservation in-flight counter."""
        if self._entered:
            try:
                self._gate._leave_attempt()
            finally:
                self._entered = False
                self._finished = True
                self._reservation._finish_attempt()


class LLMAdmissionGate:
    """Thread-safe rate / concurrency / cost gate for LLM calls."""

    def __init__(
        self,
        config: LLMAdmissionConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialise the gate with optional injectable clock / sleeper."""
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
        """Lifetime actual spend tracked by the gate (USD)."""
        with self._budget_lock:
            return self._spent

    @property
    def waiting_count(self) -> int:
        """Number of attempts currently parked in the rate queue."""
        with self._condition:
            return len(self._tickets)

    def reserve(self, estimate: LLMCostEstimate) -> LLMReservation:
        """Reserve budget for a logical LLM call, rejecting if cap exceeded."""
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
        """Reconcile reserved vs actual spend on reservation close."""
        with self._budget_lock:
            self._reserved -= reserved
            self._spent += max(Decimal(0), actual)

    def _enter_attempt(self) -> None:
        """Block until the attempt gets a rate + worker slot, or reject."""
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
        """Release a worker slot and wake any waiting attempt."""
        with self._condition:
            self._active -= 1
            self._condition.notify_all()


_SHARED_LOCK = Lock()
_SHARED_GATES: dict[LLMAdmissionConfig, LLMAdmissionGate] = {}


def get_shared_gate(config: LLMAdmissionConfig) -> LLMAdmissionGate:
    """Return the process-wide :class:`LLMAdmissionGate` for ``config``.

    Gates are keyed by the (frozen) config dataclass, so two Directors
    constructed from identical env-vars share one gate and one ledger.
    """
    with _SHARED_LOCK:
        gate = _SHARED_GATES.get(config)
        if gate is None:
            gate = LLMAdmissionGate(config)
            _SHARED_GATES[config] = gate
        return gate
