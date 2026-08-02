"""Python bridge to the ``melosviz-render export-frame`` Rust subcommand.

B18 — wgpu headless export → Python bridge.

This module follows the same subprocess-bridge pattern used by the rest of
the MelosViz backend: Python calls a Rust binary as a subprocess and reads
raw bytes from stdout.  There is deliberately no pyo3/maturin FFI layer so
the bridge works without a compiled Python extension and remains importable
even when the Rust binary has not been built yet (the import raises only when
you call :func:`render_frame_bytes`).

.. rubric:: Bridge pattern (matches existing backend convention)

The Rust CLI ``melosviz-render`` already documents this pattern in its
``main.rs`` doc-comment::

    result = subprocess.run(
        ["melosviz-render", "export-frame", "--spec", spec_path, "--frame", "0"],
        capture_output=True,
        check=True,
    )
    rgba_bytes = result.stdout  # width * height * 4 raw RGBA bytes

This module wraps that subprocess call with proper error reporting, binary
resolution, and optional frame-index control.

.. rubric:: GPU availability

The Rust ``WgpuRenderer`` requires a Metal (macOS) or Vulkan/DX12 (Linux/
Windows) GPU adapter.  In a headless CI environment without a GPU the binary
will exit non-zero and this module will raise :exc:`WgpuNotAvailableError`
with a clear message.  Tests that require a live GPU should check
:func:`is_wgpu_available` and skip loudly when it returns ``False``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "WgpuExportError",
    "WgpuNotAvailableError",
    "render_frame_bytes",
    "is_wgpu_available",
    "resolve_render_binary",
    "WGPU_BINARY_ENV_VAR",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Environment variable that overrides the ``melosviz-render`` binary path.
#: Useful for pointing the bridge at a debug/release build that is not on
#: ``$PATH`` (e.g. ``MELOSVIZ_RENDER_BIN=./target/debug/melosviz-render``).
WGPU_BINARY_ENV_VAR = "MELOSVIZ_RENDER_BIN"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WgpuExportError(RuntimeError):
    """Raised when the wgpu export subprocess fails."""


class WgpuNotAvailableError(WgpuExportError):
    """Raised when no GPU adapter is available or the binary cannot be found.

    Callers (e.g. tests) that want a loud skip rather than a test failure
    should check :func:`is_wgpu_available` first::

        import pytest
        from melosviz.render.wgpu_adapter import is_wgpu_available

        if not is_wgpu_available():
            pytest.skip(
                "melosviz-render binary not found or no GPU adapter available "
                "(set MELOSVIZ_RENDER_BIN or install the Rust binary to run "
                "the live wgpu export test)"
            )
    """


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------


def resolve_render_binary() -> str:
    """Return the path to a working ``melosviz-render`` binary.

    Lookup order:

    1. The ``MELOSVIZ_RENDER_BIN`` environment variable, if set and
       executable.
    2. ``shutil.which("melosviz-render")`` — standard ``$PATH`` lookup.
    3. Common Cargo output directories relative to the repo root, so the
       bridge works without installing the binary:

       - ``./target/release/melosviz-render``
       - ``./target/debug/melosviz-render``

       The search starts from the directory containing this file and walks
       upward until it finds a directory that contains a ``Cargo.toml``.

    Raises:
        WgpuNotAvailableError: When no binary could be found.
    """
    # 1. Explicit environment override.
    env_bin = os.environ.get(WGPU_BINARY_ENV_VAR)
    if env_bin:
        env_path = Path(env_bin)
        if env_path.is_file() and os.access(env_path, os.X_OK):
            logger.info("melosviz-render resolved from %s: %s", WGPU_BINARY_ENV_VAR, env_bin)
            return str(env_path)
        raise WgpuNotAvailableError(
            f"{WGPU_BINARY_ENV_VAR} is set to {env_bin!r} but the file does not "
            "exist or is not executable. Unset the variable or point it at a "
            "valid melosviz-render binary."
        )

    # 2. $PATH lookup.
    which = shutil.which("melosviz-render")
    if which:
        logger.info("melosviz-render resolved from PATH: %s", which)
        return which

    # 3. Cargo output directories relative to the repo root.
    repo_root = _find_repo_root(Path(__file__).resolve())
    if repo_root is not None:
        for sub in ("target/release/melosviz-render", "target/debug/melosviz-render"):
            candidate = repo_root / sub
            if candidate.is_file() and os.access(candidate, os.X_OK):
                logger.info("melosviz-render resolved from Cargo output: %s", candidate)
                return str(candidate)

    raise WgpuNotAvailableError(
        "Cannot find the melosviz-render binary. "
        "Build it with: cargo build -p melosviz-render-wgpu --release "
        "or set the MELOSVIZ_RENDER_BIN environment variable."
    )


def _find_repo_root(start: Path) -> Path | None:
    """Walk upward from *start* until a ``Cargo.toml`` is found."""
    current = start if start.is_dir() else start.parent
    for _ in range(10):  # guard against infinite loop on unusual filesystems
        if (current / "Cargo.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def is_wgpu_available() -> bool:
    """Return ``True`` if the wgpu render path is available end-to-end.

    Checks that:
    1. The ``melosviz-render`` binary can be resolved.
    2. The binary responds to ``--help`` without error (basic sanity check
       that it is the correct binary and not a stale build artifact).

    This intentionally does **not** verify GPU adapter availability — that
    would require actually launching a render and might fail with a misleading
    error.  GPU availability is checked implicitly when
    :func:`render_frame_bytes` is called.

    Returns:
        ``True`` if the binary exists and is runnable; ``False`` otherwise.
    """
    try:
        binary = resolve_render_binary()
    except WgpuNotAvailableError:
        return False
    try:
        probe = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            timeout=10,
        )
        return probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# Core bridge function
# ---------------------------------------------------------------------------


def render_frame_bytes(
    spec: RenderSpec | dict[str, Any],
    frame_index: int = 0,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    """Render one frame via the ``melosviz-render export-frame`` subcommand.

    Serialises *spec* to a temporary JSON file, invokes
    ``melosviz-render export-frame`` as a subprocess, and returns the raw
    RGBA bytes written to stdout by the Rust binary.

    Args:
        spec: A ``RenderSpec`` (pydantic model) or a plain ``dict`` shaped
            like one.  ``spec.metadata.width`` / ``height`` are used as the
            default output dimensions when *width* / *height* are not given.
        frame_index: Zero-based index of the frame to render (default: 0).
        width: Override output width in pixels.  Must be ≥ 1 if given.
        height: Override output height in pixels.  Must be ≥ 1 if given.

    Returns:
        Raw RGBA bytes: ``width × height × 4`` bytes in row-major order.

    Raises:
        WgpuNotAvailableError: If the ``melosviz-render`` binary cannot be
            found or the GPU adapter is unavailable.
        WgpuExportError: If the subprocess exits non-zero or stdout is empty.
        ValueError: If *frame_index* < 0, or if *width* / *height* < 1.
    """
    if frame_index < 0:
        raise ValueError(f"frame_index must be ≥ 0, got {frame_index}")
    if width is not None and width < 1:
        raise ValueError(f"width must be ≥ 1, got {width}")
    if height is not None and height < 1:
        raise ValueError(f"height must be ≥ 1, got {height}")

    binary = resolve_render_binary()

    # Serialise spec to a temporary file so the Rust binary can read it.
    spec_json = _spec_to_json(spec)
    with tempfile.NamedTemporaryFile(
        suffix=".json",
        delete=False,
        mode="w",
        encoding="utf-8",
        prefix="melosviz_spec_",
    ) as tmp:
        tmp.write(spec_json)
        spec_path = tmp.name

    try:
        cmd: list[str] = [
            binary,
            "export-frame",
            "--spec",
            spec_path,
            "--frame",
            str(frame_index),
        ]
        if width is not None:
            cmd += ["--width", str(width)]
        if height is not None:
            cmd += ["--height", str(height)]

        logger.debug("wgpu_adapter: running %s", cmd)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise WgpuNotAvailableError(
                f"melosviz-render binary not found at {binary!r}: {exc}. "
                "Build with: cargo build -p melosviz-render-wgpu --release"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise WgpuExportError(
                f"melosviz-render export-frame timed out after 120 s for frame {frame_index}."
            ) from exc

        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace")
            # GPU adapter missing produces a recognisable error message from the
            # Rust side ("No GPU adapter found").  Surface it as the specific
            # WgpuNotAvailableError so callers can distinguish it from other
            # failures.
            if "No GPU adapter" in stderr_text or "gpu adapter" in stderr_text.lower():
                raise WgpuNotAvailableError(
                    f"melosviz-render exit code {result.returncode}: no GPU adapter "
                    "available in this environment. Run on a host with Metal/Vulkan "
                    "or set MELOSVIZ_RENDER_BIN to a build with software rasterizer "
                    "support.\nstderr:\n"
                    + "\n".join(stderr_text.splitlines()[-10:])
                )
            raise WgpuExportError(
                f"melosviz-render export-frame failed (exit code {result.returncode}) "
                f"for frame {frame_index}.\nstderr:\n"
                + "\n".join(stderr_text.splitlines()[-10:])
            )

        rgba_bytes = result.stdout
        if not rgba_bytes:
            raise WgpuExportError(
                f"melosviz-render export-frame exited 0 but produced no output "
                f"for frame {frame_index}. This is a Rust-side bug."
            )

        logger.info(
            "wgpu_adapter: frame %d → %d RGBA bytes",
            frame_index,
            len(rgba_bytes),
        )
        return rgba_bytes
    finally:
        # Always clean up the temporary spec file.
        with contextlib.suppress(OSError):
            Path(spec_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _spec_to_json(spec: RenderSpec | dict[str, Any]) -> str:
    """Serialise a RenderSpec (pydantic model or dict) to a JSON string."""
    if isinstance(spec, dict):
        return json.dumps(spec)
    # Pydantic v2 models expose model_dump_json(); v1 models use .json().
    if hasattr(spec, "model_dump_json"):
        return spec.model_dump_json()  # type: ignore[union-attr]
    if hasattr(spec, "json"):
        return spec.json()  # type: ignore[union-attr]
    # Fallback: convert to dict then JSON-encode.
    return json.dumps(spec.__dict__)
