"""Bridge concurrency / race stress (C00 L7 · G-C00-03).

Hammers :class:`RateLimiter` and :class:`RenderQuota` under
``ThreadPoolExecutor`` with deliberately low ceilings. Asserts no over-admit
and no crashes. Patterns follow ``test_bridge_security`` / ``test_load_bridge``.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from melosviz.bridge.security import QuotaExceeded, RateLimiter, RenderQuota


def test_rate_limiter_no_over_admit_under_race() -> None:
    """Concurrent check() must never admit more than max_requests in-window."""
    ceiling = 8
    lim = RateLimiter(max_requests=ceiling, window_seconds=60)
    allowed = 0
    denied = 0
    lock = threading.Lock()
    n = 200
    workers = 32

    def one(_: int) -> bool:
        ok, _retry = lim.check("race-client")
        return ok

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, i) for i in range(n)]
        for f in as_completed(futures):
            ok = f.result()
            with lock:
                if ok:
                    allowed += 1
                else:
                    denied += 1

    assert allowed == ceiling, f"over-admit: allowed={allowed} ceiling={ceiling}"
    assert denied == n - ceiling
    assert allowed + denied == n


def test_render_quota_no_over_admit_under_race() -> None:
    """Concurrent try_acquire must never push inflight above max_concurrent."""
    ceiling = 3
    q = RenderQuota(max_concurrent=ceiling, max_rss_mb=0)
    peak = 0
    peak_lock = threading.Lock()
    acquired = 0
    rejected = 0
    count_lock = threading.Lock()
    hold = threading.Event()
    n = 80
    workers = 24

    def one(_: int) -> bool:
        nonlocal peak, acquired, rejected
        ok = q.try_acquire()
        if not ok:
            with count_lock:
                rejected += 1
            return False
        with count_lock:
            acquired += 1
        with peak_lock:
            cur = q.inflight
            if cur > peak:
                peak = cur
        # Hold the slot so other threads contend against a saturated quota.
        hold.wait(timeout=2.0)
        q.release()
        return True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, i) for i in range(n)]
        # Let contention build, then release holders.
        time.sleep(0.05)
        hold.set()
        results = [f.result() for f in as_completed(futures)]

    assert peak <= ceiling, f"over-admit: peak inflight={peak} ceiling={ceiling}"
    assert acquired == results.count(True)
    assert rejected == results.count(False)
    assert acquired + rejected == n
    assert acquired >= ceiling  # at least one full wave of admits
    assert rejected > 0
    assert q.inflight == 0


def test_render_quota_slot_context_race_safe() -> None:
    """slot() under threads: only ceiling succeed concurrently; no crash."""
    ceiling = 2
    q = RenderQuota(max_concurrent=ceiling, max_rss_mb=0)
    successes = 0
    quota_hits = 0
    lock = threading.Lock()
    barrier = threading.Barrier(16)
    n = 16

    def one(_: int) -> None:
        nonlocal successes, quota_hits
        barrier.wait(timeout=5.0)
        try:
            with q.slot():
                with lock:
                    successes += 1
                    assert q.inflight <= ceiling
                time.sleep(0.02)
        except QuotaExceeded:
            with lock:
                quota_hits += 1

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(one, range(n)))

    assert successes + quota_hits == n
    assert successes >= ceiling
    assert quota_hits > 0
    assert q.inflight == 0


def test_rate_limiter_and_quota_combined_stress() -> None:
    """Mixed limiter + quota traffic must stay within both ceilings."""
    lim = RateLimiter(max_requests=10, window_seconds=60)
    q = RenderQuota(max_concurrent=2, max_rss_mb=0)
    admit_lim = 0
    admit_q = 0
    peak_q = 0
    lock = threading.Lock()
    n = 100

    def one(i: int) -> None:
        nonlocal admit_lim, admit_q, peak_q
        ok, _ = lim.check(f"k{i % 4}")  # a few keys share windows
        if ok:
            with lock:
                admit_lim += 1
        if q.try_acquire():
            with lock:
                admit_q += 1
                peak_q = max(peak_q, q.inflight)
            time.sleep(0.001)
            q.release()

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(one, range(n)))

    # Per-key ceiling is 10; four keys → at most 40 admits, never >10 per key
    # globally we only assert no crash + quota peak.
    assert admit_lim <= 40
    assert peak_q <= 2
    assert q.inflight == 0
    # Sanity: some admits happened.
    assert admit_lim > 0
    assert admit_q > 0


@pytest.mark.parametrize("ceiling", [1, 2, 5])
def test_rate_limiter_exact_ceiling_parametrized(ceiling: int) -> None:
    lim = RateLimiter(max_requests=ceiling, window_seconds=30)
    n = ceiling * 10
    with ThreadPoolExecutor(max_workers=min(32, n)) as pool:
        oks = list(pool.map(lambda _: lim.check("solo")[0], range(n)))
    assert sum(1 for ok in oks if ok) == ceiling
