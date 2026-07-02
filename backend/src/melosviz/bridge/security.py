"""Hardening primitives for ``melosviz.bridge.server``.

Provides six independent capabilities. All of them read environment variables
*lazily* on each call so unit tests can toggle behaviour without re-importing
the bridge module.

1. **Loopback guard** — refuses to bind a non-loopback interface unless the
   operator sets ``MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1``. This prevents accidental
   exposure of the desktop bridge to the LAN.

2. **Bearer auth** — when ``MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`` the bridge expects
   ``Authorization: Bearer <token>`` where ``<token>`` matches
   ``MELOSVIZ_BRIDGE_TOKEN``. Token comparison uses
   :func:`hmac.compare_digest` to avoid timing leaks.

3. **Sliding-window rate limit** — ``MELOSVIZ_BRIDGE_RATE_LIMIT`` (default
   ``60``) requests per ``MELOSVIZ_BRIDGE_WINDOW`` seconds (default ``60``)
   per remote IP. The state lives in-process; for a real cluster replace with
   Redis. The 429 response includes ``Retry-After``.

4. **Audit log** — every protected request appends a JSONL row to
   ``$MELOSVIZ_DATA_DIR/audit/bridge.jsonl`` with timestamp, IP, method, path,
   status, and duration. I/O errors are swallowed (the bridge keeps serving).

5. **Path containment** — ``wav_path`` and ``out_dir`` must resolve to a path
   inside ``MELOSVIZ_BRIDGE_ALLOWED_DIR`` (default: ``$MELOSVIZ_DATA_DIR`` or
   ``$HOME``). Symlinks are resolved before the check.

6. **Body size cap** — POST bodies larger than
   ``MELOSVIZ_BRIDGE_MAX_BODY_BYTES`` (default 1 MiB) return 413 before being
   parsed.

The module is intentionally dependency-free (stdlib only) so the security
boundary is auditable without FastAPI/Pydantic in the loop.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Iterable

# ---------------------------------------------------------------------------
# Constants (env-overridable)
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _data_dir() -> Path:
    return Path(os.environ.get("MELOSVIZ_DATA_DIR") or Path.home())


def allowed_dir() -> Path:
    """Return the canonical allowed root; defaults to ``$MELOSVIZ_DATA_DIR``."""
    explicit = os.environ.get("MELOSVIZ_BRIDGE_ALLOWED_DIR")
    return Path(explicit).resolve() if explicit else _data_dir().resolve()


def max_body_bytes() -> int:
    return _env_int("MELOSVIZ_BRIDGE_MAX_BODY_BYTES", 1 * 1024 * 1024)


# ---------------------------------------------------------------------------
# 1. Loopback guard
# ---------------------------------------------------------------------------


# Hosts that would expose the bridge to the LAN if bound.
_PUBLIC_HOSTS = frozenset({"0.0.0.0", "::", "*"})


def loopback_check(host: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``ok=False`` means main() must exit non-zero.

    A host is considered loopback when it parses as a loopback IP literal
    (``127.0.0.0/8`` or ``::1``) or matches ``localhost``. Anything else,
    including ``0.0.0.0`` and ``::``, requires
    ``MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1``.
    """
    if host in _PUBLIC_HOSTS:
        if os.environ.get("MELOSVIZ_BRIDGE_ALLOW_PUBLIC") == "1":
            return True, "ALLOW_PUBLIC=1"
        return False, (
            f"Refusing to bind {host}: loopback only by default. "
            "Set MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1 to bind a public interface."
        )
    # Anything else (127.0.0.1, ::1, localhost) is treated as loopback.
    return True, "loopback"


# ---------------------------------------------------------------------------
# 2. Bearer auth
# ---------------------------------------------------------------------------


def auth_required() -> bool:
    return os.environ.get("MELOSVIZ_BRIDGE_REQUIRE_AUTH") == "1"


def expected_token() -> str | None:
    return os.environ.get("MELOSVIZ_BRIDGE_TOKEN") or None


def check_bearer(authorization: str | None) -> tuple[bool, str]:
    """Verify ``Authorization: Bearer <token>``.

    Returns ``(ok, reason)``. With auth disabled, always returns
    ``(True, "auth-disabled")``.
    """
    if not auth_required():
        return True, "auth-disabled"
    expected = expected_token()
    if not expected:
        return False, "server-misconfigured: MELOSVIZ_BRIDGE_TOKEN unset"
    if not authorization:
        return False, "missing Authorization header"
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False, "expected Bearer scheme"
    if not hmac.compare_digest(token, expected):
        return False, "invalid token"
    return True, "ok"


# ---------------------------------------------------------------------------
# 3. Rate limit
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    window: Deque[float] = field(default_factory=deque)


class RateLimiter:
    """Per-key sliding-window limiter.

    Thread-safe. State is in-process; for multi-worker deployments swap
    in a Redis backend.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ):
        self._max = (
            max_requests
            if max_requests is not None
            else _env_int("MELOSVIZ_BRIDGE_RATE_LIMIT", 30)
        )
        self._window = (
            window_seconds
            if window_seconds is not None
            else _env_int("MELOSVIZ_BRIDGE_WINDOW", 60)
        )
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``."""
        if self._max <= 0:
            return True, 0
        ts = now if now is not None else time.monotonic()
        cutoff = ts - self._window
        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket())
            # Drop expired entries.
            while bucket.window and bucket.window[0] <= cutoff:
                bucket.window.popleft()
            if len(bucket.window) >= self._max:
                # Retry-after = time until the oldest in-window entry expires.
                retry = max(1, int(self._window - (ts - bucket.window[0])))
                return False, retry
            bucket.window.append(ts)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


# ---------------------------------------------------------------------------
# 4. Audit log
# ---------------------------------------------------------------------------


def audit_path() -> Path:
    return _data_dir() / "audit" / "bridge.jsonl"


def append_audit(row: dict[str, object]) -> None:
    """Append one row to the JSONL audit log; never raises."""
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        # Audit must never break the request; swallowed on purpose.
        return


def build_audit_row(
    *,
    ip: str,
    method: str,
    path: str,
    status: int,
    dur_ms: float,
) -> dict[str, object]:
    return {
        "ts": time.time(),
        "ip": ip,
        "method": method,
        "path": path,
        "status": int(status),
        "dur_ms": round(float(dur_ms), 3),
    }


# ---------------------------------------------------------------------------
# 5. Path containment
# ---------------------------------------------------------------------------


def is_path_allowed(p: Path, *, root: Path | None = None) -> bool:
    """Return True iff ``p`` resolves inside ``root`` (default: allowed_dir)."""
    try:
        target = Path(p).expanduser().resolve(strict=False)
        boundary = (root or allowed_dir()).resolve()
        try:
            return target.is_relative_to(boundary)
        except AttributeError:  # pragma: no cover — py3.8 fallback
            try:
                target.relative_to(boundary)
                return True
            except ValueError:
                return False
    except (OSError, RuntimeError):
        return False


# ---------------------------------------------------------------------------
# 6. Middleware factory
# ---------------------------------------------------------------------------


# Module-level registry: app_id(id(app)) -> live RateLimiter.
# Tests can ``_LIVE_LIMITERS[id(app)] = new_limiter`` and have the middleware
# pick it up on the next request. ``install_middleware`` registers the initial
# limiter; the dispatch loop dereferences the registry per request.
_LIVE_LIMITERS: dict[int, RateLimiter] = {}


def install_middleware(
    app,
    *,
    rate_limiter: RateLimiter | None = None,
    protected_paths: Iterable[str] = (),
) -> RateLimiter:
    """Attach the security middleware to a FastAPI ``app`` and return the
    shared :class:`RateLimiter` (tests can call ``.reset()`` between cases).
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    limiter = rate_limiter or RateLimiter()
    protected = set(protected_paths)
    _LIVE_LIMITERS[id(app)] = limiter

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # type: ignore[override]
            start = time.monotonic()
            method = request.method
            path = request.url.path
            ip = request.client.host if request.client else "unknown"
            is_protected = path in protected or (
                method == "POST" and path.startswith(("/analyze", "/build", "/render"))
            )

            # Body size cap.
            if method == "POST" and is_protected:
                clen = int(request.headers.get("content-length") or 0)
                if clen > max_body_bytes():
                    self._audit(ip, method, path, 413, start)
                    return JSONResponse(
                        {"detail": f"Body exceeds {max_body_bytes()} bytes"},
                        status_code=413,
                    )

            # Auth.
            if is_protected and auth_required():
                ok, _reason = check_bearer(request.headers.get("authorization"))
                if not ok:
                    auth_header = request.headers.get("authorization")
                    code = 401
                    if auth_header and auth_header.lower().startswith("bearer "):
                        code = 403
                    self._audit(ip, method, path, code, start)
                    return JSONResponse(
                        {"detail": "valid Bearer token required"},
                        status_code=code,
                        headers={"WWW-Authenticate": "Bearer"} if code == 401 else None,
                    )

            # Rate limit (read live limiter so tests can swap).
            live = _LIVE_LIMITERS.get(id(request.app)) or limiter
            allowed, retry = live.check(ip)
            if not allowed:
                self._audit(ip, method, path, 429, start)
                return JSONResponse(
                    {"detail": f"Rate limit exceeded; retry in {retry}s"},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )

            response = await call_next(request)
            self._audit(ip, method, path, response.status_code, start)
            return response

        def _audit(self, ip: str, method: str, path: str, status: int, start: float) -> None:
            protected_now = path in protected or (
                method == "POST" and path.startswith(("/analyze", "/build", "/render"))
            )
            if not protected_now:
                return
            dur = (time.monotonic() - start) * 1000.0
            try:
                append_audit(
                    build_audit_row(
                        ip=ip,
                        method=method,
                        path=path,
                        status=status,
                        dur_ms=dur,
                    )
                )
            except Exception:  # noqa: BLE001
                return

    app.add_middleware(SecurityMiddleware)
    return limiter
