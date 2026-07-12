#!/usr/bin/env python3
"""Reserved-name / dependency-confusion scanner (C06 L55 / WBS-P1.4).

Policy source: docs/SUPPLY_CHAIN.md — MelosViz publishes no private package
index; installs resolve from public registries via locked manifests only.

Checks:
  * allowlisted MelosViz package / crate / npm names (and melosviz-* family)
  * typo-adjacent confuse names in declared deps (e.g. melosvis, melos-viz)
  * unexpected private-registry / alternate-index URLs in manifests
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Legitimate owned / workspace names (docs/SUPPLY_CHAIN.md + Cargo/pyproject/npm).
ALLOWED_EXACT = frozenset(
    {
        "melosviz",
        "melosviz-mir",
        "melosviz-render-wgpu",
        "melosviz-render",
        "melosviz-web",
        "melosviz-desktop",
        "melosviz_mir",
        "melosviz_render_wgpu",
    }
)

# Simple typo / confuse blocklist adjacent to reserved MelosViz identifiers.
TYPO_BLOCKLIST = frozenset(
    {
        "melosvis",
        "melos-viz",
        "melosvizs",
        "mellosviz",
        "melosvizz",
        "melosvizx",
        "meloviz",
        "melos-vizs",
        "melosviz-hq",
        "melosvizhq",
        "melosvizjs",
        "melosviz-js",
        "melosvizpy",
        "melosviz-py",
        "melozviz",
        "melosivz",
    }
)

ALLOWED_REGISTRY_HOSTS = frozenset(
    {
        "pypi.org",
        "pypi.python.org",
        "files.pythonhosted.org",
        "registry.npmjs.org",
        "registry.npmjs.com",
        "crates.io",
        "index.crates.io",
        "static.crates.io",
        "github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
    }
)

PRIVATE_INDEX_RE = re.compile(
    r"(--extra-index-url|--index-url|\bextra-index-url\b|\bindex-url\b|"
    r"\[\[tool\.uv\.index\]\])",
    re.I,
)
URL_RE = re.compile(r"https?://([^\s\"'`>\]]+)", re.I)
REGISTRYISH_RE = re.compile(
    r"(pypi|npmjs|crates\.io|registry|/simple|artifactory|nexus|"
    r"gemfury|packagecloud|codeartifact|pkgs\.dev)",
    re.I,
)
TOML_NAME_RE = re.compile(r'(?m)^\s*name\s*=\s*"([^"]+)"')
# PEP 508 requirement name (optional extras stripped later).
PEP508_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)")

SCAN_TARGETS = (
    REPO / "backend" / "pyproject.toml",
    REPO / "Cargo.toml",
    REPO / "crates" / "melosviz-mir" / "Cargo.toml",
    REPO / "crates" / "melosviz-render-wgpu" / "Cargo.toml",
    REPO / "web" / "package.json",
    REPO / "desktop" / "package.json",
)


def _norm(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _bare_npm(name: str) -> str:
    n = _norm(name)
    if n.startswith("@") and "/" in n:
        return n.split("/", 1)[1]
    return n


def _is_allowed_owned(name: str) -> bool:
    n = _bare_npm(name)
    if n in {_norm(x) for x in ALLOWED_EXACT} or n in ALLOWED_EXACT:
        return True
    if n == "melosviz" or n.startswith("melosviz-"):
        return n not in TYPO_BLOCKLIST and not any(
            n == t or n.startswith(t + "-") for t in TYPO_BLOCKLIST
        )
    return False


def _is_typo_confuse(name: str) -> bool:
    n = _bare_npm(name)
    if _is_allowed_owned(n):
        return False
    if n in TYPO_BLOCKLIST:
        return True
    # Compact form catches melosvizs / mellosviz style, but must not treat the
    # legitimate stem "melosviz" as a hit of blocklisted "melos-viz".
    compact = n.replace("-", "")
    typo_compacts = {t.replace("-", "") for t in TYPO_BLOCKLIST} - {"melosviz"}
    return compact in typo_compacts

def _host_allowed(url_without_scheme: str) -> bool:
    host = url_without_scheme.split("/")[0].split("@")[-1].lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host in ALLOWED_REGISTRY_HOSTS


def _scan_urls(path: Path, text: str, errors: list[str]) -> None:
    rel = path.relative_to(REPO)
    if PRIVATE_INDEX_RE.search(text):
        errors.append(f"{rel}: forbidden index override / private uv index")
    for m in URL_RE.finditer(text):
        url = m.group(1).rstrip(").,;'\"")
        if not REGISTRYISH_RE.search(url):
            continue
        if not _host_allowed(url):
            errors.append(f"{rel}: unexpected private/alternate registry URL https://{url}")


def _project_name_toml(text: str) -> str | None:
    m = TOML_NAME_RE.search(text)
    return m.group(1) if m else None


def _py_deps(text: str) -> set[str]:
    """Extract dependency names from [project] dependencies / optional-deps lists."""
    names: set[str] = set()
    # Capture quoted requirement strings that look like PEP 508.
    for m in re.finditer(r'["\']([^"\']+)["\']', text):
        raw = m.group(1).strip()
        if any(x in raw for x in (" ", "://", "/", "\\", "=")) and not re.match(
            r"^[A-Za-z0-9_.-]+(\[[^\]]+\])?", raw.split(";")[0].strip()
        ):
            # Still allow "pkg>=1" / "pkg[extra]>=1"
            pass
        req = raw.split(";")[0].strip()
        # Skip paths / URLs / markers-only
        if "://" in req or req.startswith(".") or "/" in req.split("[")[0]:
            # Self-ref like melosviz[analysis,stems] is OK — no slash.
            if not re.match(r"^[A-Za-z0-9_.-]+(\[[^\]]+\])?", req):
                continue
        mname = PEP508_NAME_RE.match(req)
        if not mname:
            continue
        cand = mname.group(1)
        # Ignore non-dep TOML string noise (description words, paths, scripts).
        if "." in cand and not cand.startswith("melosviz"):
            continue
        if cand.endswith(".md") or cand in {"setuptools", "wheel"}:
            # setuptools/wheel are build-system requires — still fine to track,
            # but not reserved-name relevant. Keep them out of confuse checks
            # by only returning them when melos-adjacent OR always return all
            # real deps: prefer returning all package-like tokens from dep arrays.
            continue
        # Heuristic: only keep tokens that appear inside a dependencies-like array
        # by requiring version/extras punctuation OR known list context.
        if re.search(
            rf'["\']{re.escape(raw)}["\']',
            text,
        ) and (
            any(op in req for op in (">=", "<=", "==", "~=", "!=", "[") )
            or cand.startswith("melosviz")
            or cand in {"pydantic", "pytest", "httpx", "fastapi", "uvicorn", "ruff", "mypy",
                        "hypothesis", "pytest-bdd", "librosa", "numpy", "scipy", "demucs",
                        "torch", "opentelemetry-api", "opentelemetry-sdk",
                        "opentelemetry-exporter-otlp-proto-http"}
            or re.search(
                rf"(?ms)dependencies\s*=\s*\[[^\]]*['\"]{re.escape(cand)}",
                text,
            )
        ):
            names.add(cand)
    return names


def _cargo_dep_names(text: str) -> set[str]:
    names: set[str] = set()
    # [dependencies] / [dev-dependencies] / [build-dependencies] tables
    for block in re.finditer(
        r"(?ms)^\[((?:.*\.)?dependencies)\]\n(.*?)(?=^\[|\Z)",
        text,
    ):
        body = block.group(2)
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z0-9_-]+)\s*=', line)
            if m:
                names.add(m.group(1))
            m = re.match(r'^"([A-Za-z0-9_-]+)"\s*=', line)
            if m:
                names.add(m.group(1))
    return names


def _npm_names(data: dict) -> tuple[str | None, set[str]]:
    pkg = data.get("name") if isinstance(data.get("name"), str) else None
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            deps.update(str(k) for k in block)
    return pkg, deps


def main() -> int:
    errors: list[str] = []
    owned_declared: list[str] = []
    dep_names: set[str] = set()

    for path in SCAN_TARGETS:
        rel = path.relative_to(REPO)
        if not path.is_file():
            errors.append(f"missing scan target: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        _scan_urls(path, text, errors)

        if path.name == "pyproject.toml":
            pname = _project_name_toml(text)
            if pname:
                owned_declared.append(pname)
            dep_names.update(_py_deps(text))
            # Self-ref optional extras: melosviz[analysis,stems]
            if re.search(r'["\']melosviz\[', text):
                dep_names.add("melosviz")

        elif path.name == "Cargo.toml":
            pname = _project_name_toml(text)
            if pname:
                owned_declared.append(pname)
            # Workspace members
            for m in re.finditer(r'"(?:crates/)?(melosviz[^"]+)"', text):
                owned_declared.append(Path(m.group(1)).name)
            dep_names.update(_cargo_dep_names(text))

        elif path.name == "package.json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}: invalid JSON ({exc})")
                continue
            if not isinstance(data, dict):
                errors.append(f"{rel}: package.json root must be an object")
                continue
            pkg, deps = _npm_names(data)
            if pkg:
                owned_declared.append(pkg)
            dep_names.update(deps)
            pub = data.get("publishConfig")
            if isinstance(pub, dict):
                reg = pub.get("registry")
                if isinstance(reg, str) and reg.startswith("http"):
                    hostpart = reg.split("://", 1)[1]
                    if not _host_allowed(hostpart):
                        errors.append(f"{rel}: unexpected publishConfig.registry {reg}")

    for name in owned_declared:
        if not _is_allowed_owned(name):
            n = _bare_npm(name)
            if "melos" in n or n.endswith("viz") or "viz" in n:
                errors.append(
                    f"package name {name!r} not in reserved allowlist "
                    f"(see docs/SUPPLY_CHAIN.md)"
                )

    for name in sorted(dep_names):
        if _is_typo_confuse(name):
            errors.append(f"typo-adjacent reserved-name confuse dependency {name!r}")

    if errors:
        print("FAIL: reserved-name / dependency-confusion scanner:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    owned = ", ".join(sorted({_norm(n) for n in owned_declared}))
    print(f"PASS: reserved-name scanner — {len(SCAN_TARGETS)} manifests, owned: {owned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
