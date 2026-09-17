# Dependency advisory triage

Durable record of Dependabot findings that need a decision rather than a bump,
so a permanently-unfixable alert does not train us to ignore the alert list.

Every entry states the evidence, not just the conclusion.

---

## GHSA-wrw7-89jp-8q8g — `glib` unsoundness in `VariantStrIter` (alert 28)

**Status:** accepted as unreachable. **The Dependabot alert is deliberately
left open** — dismissing a security alert is an operator decision, and this
environment requires explicit approval for it. The recommendation and its
evidence are recorded here; the alert stays visible until an operator acts.

To dismiss it with the recorded rationale:

```bash
gh api -X PATCH repos/KooshaPari/Melosviz/dependabot/alerts/28 \
  -f state=dismissed \
  -f dismissed_reason=tolerable_risk \
  -f dismissed_comment="Not reachable in shipped artifacts, and unfixable upstream; see docs/security/DEPENDENCY-ADVISORIES.md"
```

**Advisory.** Unsound `Iterator` / `DoubleEndedIterator` impls for
`glib::VariantStrIter`. Affected `>= 0.15.0, < 0.20.0`. Lock has `glib 0.18.5`.

**Why it cannot be bumped.** `glib 0.20.0` is unreachable from the current
tauri/wry tree. The whole gtk-rs stack is on the 0.18 line and every candidate
upstream still pins it:

```
$ cargo update -p glib --precise 0.20.0
error: failed to select a version for the requirement `glib = "^0.18"`
candidate versions found which didn't match: 0.20.0
required by package `gtk v0.18.2`
  ... which satisfies dependency `gtk = "^0.18"` (locked to 0.18.2) of package `tauri v2.11.5`
```

Checked against crates.io, not just the local lock:

| Crate | Version | gtk requirement |
| --- | --- | --- |
| `tauri` | 2.11.5 (latest stable) | `gtk ^0.18` |
| `tauri` | 3.0.0-alpha.1 (latest, pre-release) | `gtk ^0.18` |
| `wry` | 0.55.1 (locked) | `gtk ^0.18` |
| `wry` | 0.57.0 (latest) | `gtk ^0.18` |

There is no released tauri or wry that lifts `gtk` to 0.20, so no upgrade path
exists today. Moving to `tauri 3.0.0-alpha` would trade a medium-severity
unreachable advisory for a pre-release desktop framework.

**Why it is unreachable here.** `glib` arrives only through the GTK /
webkit2gtk Linux backend:

```
glib 0.18.5 <- atk <- gtk <- muda, tao, tauri, tauri-runtime-wry, wry, webkit2gtk
```

It is not in the macOS dependency graph, which is what this project ships:

```
$ cargo tree --target aarch64-apple-darwin -i glib --locked
warning: nothing to print.

$ cargo tree --target x86_64-unknown-linux-gnu -i glib --locked
glib v0.18.5
└── atk v0.18.2
    └── gtk v0.18.2
```

macOS builds use the WKWebView backend (objc2), not GTK. So the crate is never
compiled into the `.app` / `.dmg` artifacts this repo publishes, and the
unsoundness is not reachable from any shipped binary.

**When to revisit.** This becomes actionable if:

- the project starts shipping a Linux desktop build, or
- tauri/wry move to gtk-rs 0.20 — re-check with
  `cargo tree --target x86_64-unknown-linux-gnu -i glib`.

Re-check command:

```bash
gh api repos/KooshaPari/Melosviz/dependabot/alerts \
  --jq '.[] | select(.state=="open") | "\(.number) \(.dependency.package.name) \(.security_vulnerability.first_patched_version.identifier)"'
```

---

## GHSA-px8p-9vwx-vf98 — `fflate` unzip infinite loop (alert 23)

**Status:** fixed and verified closed. Dependabot alert 23 closed automatically
after the fix landed on `main`.

`three-stdlib` pins `fflate ^0.6.9`, which resolved to the vulnerable `0.6.10`.
Added a scoped override in `web/package.json`:

```json
"overrides": { "three-stdlib": { "fflate": "^0.6.11" } }
```

The override is scoped deliberately: `@types/three` requires `fflate ~0.8.2`, so
an unscoped override would break it. Resolved versions after the fix:
`node_modules/fflate` 0.8.3 (for `@types/three`),
`node_modules/three-stdlib/node_modules/fflate` 0.6.11.

---

## Reproducing the platform check

```bash
cd src-tauri
cargo tree --target aarch64-apple-darwin -i glib --locked      # expect: nothing to print
cargo tree --target x86_64-unknown-linux-gnu -i glib --locked  # expect: glib v0.18.x
```
