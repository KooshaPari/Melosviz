from __future__ import annotations

import threading
import time
from collections.abc import Callable
from decimal import Decimal
from typing import NoReturn

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
    estimate = config.estimate(b"abcdefgh")
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


def test_concurrent_reservation_cleanup_finalizes_ledger_once() -> None:
    config = LLMAdmissionConfig.from_env(_env())
    gate = LLMAdmissionGate(config)
    reservation = gate.reserve(config.estimate(b"reservation"))
    finish_started = threading.Event()
    allow_finish = threading.Event()
    release_started = threading.Event()
    finish_calls: list[tuple[Decimal, Decimal]] = []
    worker_errors: list[BaseException] = []
    original_finish = gate._finish_reservation

    def controlled_finish(reserved: Decimal, actual: Decimal) -> None:
        finish_calls.append((reserved, actual))
        finish_started.set()
        assert allow_finish.wait(timeout=2)
        original_finish(reserved, actual)

    gate._finish_reservation = controlled_finish  # type: ignore[method-assign]

    def settle() -> None:
        try:
            reservation.settle(Decimal("0.0001"))
        except BaseException as exc:
            worker_errors.append(exc)

    def release() -> None:
        try:
            release_started.set()
            reservation.release()
        except BaseException as exc:
            worker_errors.append(exc)

    settle_thread = threading.Thread(target=settle)
    release_thread = threading.Thread(target=release)
    settle_thread.start()
    release_thread_was_started = False
    try:
        assert finish_started.wait(timeout=2)
        release_thread.start()
        release_thread_was_started = True
        assert release_started.wait(timeout=2)
        deadline = time.monotonic() + 0.25
        while len(finish_calls) == 1 and time.monotonic() < deadline:
            time.sleep(0.005)
    finally:
        allow_finish.set()
        settle_thread.join(timeout=2)
        if release_thread_was_started:
            release_thread.join(timeout=2)

    assert not settle_thread.is_alive()
    assert not release_thread_was_started or not release_thread.is_alive()
    assert worker_errors == []
    assert len(finish_calls) == 1
    assert gate.spent_usd == Decimal("0.0001")


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


@pytest.mark.parametrize("failure_source", ["clock", "wait", "sleeper"])
def test_failed_attempt_removes_queued_ticket(
    failure_source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    config = LLMAdmissionConfig.from_env(
        _env(
            MELOSVIZ_LLM_REQUESTS_PER_MINUTE="1",
            MELOSVIZ_LLM_MAX_CONCURRENCY="1",
        )
    )

    def fail(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError(f"{failure_source} failed")

    sleeper: Callable[[float], None] = clock.sleep
    if failure_source == "sleeper":
        sleeper = fail
    gate = LLMAdmissionGate(config, clock=clock, sleeper=sleeper)

    if failure_source == "sleeper":
        first = gate.reserve(config.estimate(b"first"))
        with first.attempt():
            pass
        first.release()
    elif failure_source == "clock":
        monkeypatch.setattr(gate, "_clock", fail)
    else:
        holder = gate.reserve(config.estimate(b"holder"))
        holder_attempt = holder.attempt()
        holder_attempt.__enter__()
        monkeypatch.setattr(gate._condition, "wait", fail)

    reservation = gate.reserve(config.estimate(b"failed"))
    try:
        with pytest.raises(RuntimeError, match=f"{failure_source} failed"):
            reservation.attempt().__enter__()
    finally:
        reservation.release()
        if failure_source == "wait":
            holder_attempt.__exit__(None, None, None)
            holder.release()

    assert gate.waiting_count == 0


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
    worker_errors: list[BaseException] = []

    def wait_once() -> None:
        reservation = None
        try:
            reservation = gate.reserve(config.estimate(b"waiter"))
            waiter_started.set()
            with reservation.attempt():
                pass
        except BaseException as exc:
            worker_errors.append(exc)
        finally:
            try:
                if reservation is not None:
                    reservation.release()
            except BaseException as exc:
                worker_errors.append(exc)
            finally:
                waiter_done.set()

    waiter = threading.Thread(target=wait_once)
    waiter.start()
    try:
        assert waiter_started.wait(timeout=2)
        deadline = time.monotonic() + 2
        while gate.waiting_count != 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert gate.waiting_count == 1
        rejected = gate.reserve(config.estimate(b"rejected"))
        try:
            with pytest.raises(LLMAdmissionError, match="queue is full"):
                rejected.attempt().__enter__()
        finally:
            rejected.release()
    finally:
        try:
            holder_attempt.__exit__(None, None, None)
            holder.release()
        finally:
            waiter.join(timeout=2)

    assert waiter_done.is_set()
    assert not waiter.is_alive()
    assert worker_errors == []
