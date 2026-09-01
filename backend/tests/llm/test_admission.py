from __future__ import annotations

import threading
import time
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
