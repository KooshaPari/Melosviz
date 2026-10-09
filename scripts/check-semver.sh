#!/usr/bin/env bash
# Verify the SemVer 2.0.0 validator that the release workflows actually run.
#
# This script deliberately does NOT keep its own copy of the pattern. It
# extracts the `grep -Eq '<pattern>'` argument out of each release workflow,
# asserts the three deployed copies are byte-identical, and runs the
# accept/reject cases against the extracted pattern. A later edit that breaks
# one workflow's copy therefore fails here instead of shipping a validator that
# silently accepts 1.2.3-foo..bar again.
#
# It also re-runs the two guards that sit in front of the pattern in the
# workflows (the CR/LF check and the length/charset check) so the pre-greps are
# covered by the same cases, and it measures the matcher's cost at the length
# limit so the cap is a measured value rather than a guess.
#
# Grammar (https://semver.org):
#   valid-num  := 0 | [1-9][0-9]*
#   pre-id     := valid-num | NONDIGIT ( [0-9A-Za-z-]* NONDIGIT )?
#   build      := NONDIGIT ( [0-9A-Za-z-]* NONDIGIT )?  joined by '.'
#   version    := MAJOR '.' MINOR '.' PATCH [ '-' pre ] [ '+' build ]
#
# Note on `+01`: build identifiers have NO leading-zero restriction under the
# official grammar, so 1.2.3+01 is valid and must be accepted. The leading-zero
# rule applies only to numeric *prerelease* ids, which is why 1.2.3-01 fails.
#
# GNU grep -E has no non-capturing groups and no \d, so the whole grammar is
# spelled out with plain capturing groups and [0-9] classes.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WF_DIR="$REPO_ROOT/.github/workflows"
WORKFLOWS=(homebrew-tap.yml scoop-bucket.yml winget-pr.yml)

fail=0
note() { printf '%s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

# The verdict words are spelled once and reused. They are the comparison key on
# both sides of every case below, so a typo in one copy would otherwise turn a
# self-check into a checker that agrees with itself for the wrong reason.
#
# Named VERDICT_* rather than ACCEPT/REJECT on purpose: ACCEPT and REJECT are
# already the case-list array names further down, and `readonly ACCEPT=accept`
# would make the later `ACCEPT=( ... )` abort with "readonly variable". Same
# word, two meanings, so they need two names.
readonly VERDICT_ACCEPT=accept
readonly VERDICT_REJECT=reject

# ------------------------------------------------------- extract the deployed pattern
note "=== 1. extract the deployed pattern from each workflow ==="
declare -A PATTERNS
for wf in "${WORKFLOWS[@]}"; do
  path="$WF_DIR/$wf"
  if [[ ! -f "$path" ]]; then
    bad "$wf is missing"
    continue
  fi
  # The pattern is the single-quoted argument of the `grep -Eq '<pattern>'` in
  # the version-validation step. Take the last such occurrence so a stray
  # grep elsewhere in the file cannot win.
  pat="$(sed -n "s/.*grep -Eq '\([^']*\)'; then.*/\1/p" "$path" | tail -n 1)"
  if [[ -z "$pat" ]]; then
    bad "could not extract a grep -Eq pattern from $wf"
    continue
  fi
  PATTERNS["$wf"]="$pat"
  printf '  %-20s %4d bytes\n' "$wf" "${#pat}"
done

note ""
note "=== 2. all three deployed copies must be byte-identical ==="
ref=""
for wf in "${WORKFLOWS[@]}"; do
  [[ -v PATTERNS["$wf"] ]] || continue
  if [[ -z "$ref" ]]; then
    ref="${PATTERNS[$wf]}"
    note "  reference: $wf"
  elif [[ "${PATTERNS[$wf]}" != "$ref" ]]; then
    bad "$wf's pattern differs from ${WORKFLOWS[0]}"
  else
    note "  ok: $wf matches"
  fi
done
if [[ -z "$ref" ]]; then
  note ""
  note "no pattern extracted; cannot run cases"
  exit 1
fi
SEMVER="$ref"

# --------------------------------------------- extract the deployed length cap
note ""
note "=== 3. extract the deployed length cap ==="
cap=""
for wf in "${WORKFLOWS[@]}"; do
  [[ -f "$WF_DIR/$wf" ]] || continue
  # \+ is not portable inside a sed bracket across BSD/GNU sed, so spell the
  # digits out twice.
  c="$(sed -n 's/.*-gt \([0-9][0-9]*\).*/\1/p' "$WF_DIR/$wf" | tail -n 1)"
  # A workflow that has lost its `-gt` guard must not be skipped silently: the
  # other workflows still supply a reference cap, so continuing here would let
  # the shared guard cases pass while this file publishes an uncapped pattern.
  if [[ -z "$c" ]]; then
    bad "$wf defines no length cap (no -gt <n> found)"
    continue
  fi
  if [[ -z "$cap" ]]; then
    cap="$c"
    note "  reference cap: $cap (from $wf)"
  elif [[ "$c" != "$cap" ]]; then
    bad "$wf caps at $c but the reference caps at $cap"
  else
    note "  ok: $wf caps at $c"
  fi
done
if [[ -z "$cap" ]]; then
  bad "no length cap found in the release workflows"
  cap=0
fi

# ------------------------------------------------------------- the accept/reject cases
ACCEPT=(
  1.2.3
  0.0.0
  10.20.30
  1.0.0-alpha
  1.0.0-alpha.1
  1.0.0-0.3.7
  1.0.0-x.7.z.92
  1.0.0-alpha+001
  1.0.0+20130313144700
  1.0.0-beta+exp.sha.5114f85
  1.0.0-rc.1+build.1
  1.0.0--
  1.0.0-alpha.1.2+build.1848
  1.2.3+01
  1.2.3+20130313144700.5
  99999.0.1
  # Edge cases called out during review:
  #   alpha.01 -> the second identifier is numeric with a leading zero, so it
  #               must be rejected; this is the case a lax prerelease rule
  #               silently allows.
  #   '--'     -> '-' is a NONDIGIT, so this is a legal single prerelease id.
  #   '+-a'    -> '-' is a NONDIGIT, so this is a legal single build id.
  1.0.0+-a
  1.0.0-a-b
  1.0.0-a.0.b
)

REJECT=(
  01.2.3
  1.02.3
  1.2.03
  1.2.3-01
  1.2.3-0.01
  1.2.3-alpha.01
  1.2.3-foo..bar
  1.2.3-
  1.2.3+
  1.2.3+build_1
  1.2.3+build_
  1.2.3-alpha_1
  1.2.3-alpha+
  1.2.3+.
  1.2
  1.2.3.4
  v1.2.3
  "1.2.3 "
  ""
  "1.2.3-beta+"
  "1.2.3-beta..1"
  "1.2.3+build..1"
  "1.2.3-evil;echo pwned"
)

note ""
note "=== 4. pattern cases (${#ACCEPT[@]} accept, ${#REJECT[@]} reject) ==="
for v in "${ACCEPT[@]}"; do
  if printf '%s' "$v" | grep -Eq "$SEMVER"; then
    printf '  ok    accept %s\n' "$v"
  else
    bad "should accept but rejected: $v"
  fi
done
for v in "${REJECT[@]}"; do
  if printf '%s' "$v" | grep -Eq "$SEMVER"; then
    bad "should reject but accepted: $v"
  else
    printf '  ok    reject %s\n' "$v"
  fi
done

# ------------------------------------------------- the guards in front of the pattern
# The workflows reject in this order: CR/LF, then length, then charset, then
# the pattern. This mirrors that order so a case that the guards catch is
# reported as an accept, and one that only the pattern catches still lands in
# the reject list above.
note ""
note "=== 5. guard cases (CR/LF, length cap, charset) ==="

guard_check() {
  # $1 = version, $2 = expect(accept|reject)
  # $2 is validated before anything else: an expectation outside the two
  # verdicts would make the comparison below vacuously true for every input,
  # turning this case into a no-op that always reports ok.
  local v="$1" expect="$2" verdict=$VERDICT_ACCEPT
  case "$expect" in
    "$VERDICT_ACCEPT"|"$VERDICT_REJECT") ;;
    *)
      bad "internal error: guard_check expectation must be '$VERDICT_ACCEPT' or '$VERDICT_REJECT', got: $expect"
      return 0
      ;;
  esac
  case "$v" in
    *$'\n'*|*$'\r'*) verdict=$VERDICT_REJECT ;;
  esac
  if [[ "$verdict" == "$VERDICT_ACCEPT" && ${#v} -gt "$cap" ]]; then
    verdict=$VERDICT_REJECT
  fi
  if [[ "$verdict" == "$VERDICT_ACCEPT" ]]; then
    case "$v" in
      ''|*[!0-9A-Za-z.+-]*) verdict=$VERDICT_REJECT ;;
    esac
  fi
  if [[ "$verdict" == "$VERDICT_REJECT" ]]; then
    :
  elif printf '%s' "$v" | grep -Eq "$SEMVER"; then
    verdict=$VERDICT_ACCEPT
  else
    verdict=$VERDICT_REJECT
  fi
  if [[ "$verdict" == "$expect" ]]; then
    printf '  ok    %s %s\n' "$expect" "$(printf '%q' "$v")"
  else
    bad "expected $expect, got $verdict for: $(printf '%q' "$v")"
  fi
}

# Newline injection: must be caught by the CR/LF guard, before grep ever runs.
guard_check "$(printf '1.0.0\nEVIL=1')" $VERDICT_REJECT
guard_check "$(printf '1.0.0\rcarriage')" $VERDICT_REJECT
# Over the cap: rejected by the length guard.
long_ok="$(printf '1.0.0-alpha.%0.s' $(seq 1 40))${cap}"
guard_check "$long_ok" $VERDICT_REJECT
# Under the cap, built only from characters the charset guard allows, so it
# survives all three guards and is judged by the pattern alone. This is the
# case the nested-quantifier pattern is most likely to get wrong, and it is
# the one the cost measurement below depends on being reachable.
#
# The suffix is sized from the remaining budget, so the whole input is exactly
# $cap characters: one over would be turned away by the length guard and the
# pattern would never run, which is the defect this case exists to catch.
# The prerelease identifier is NUMERIC and carries a leading zero, which
# SemVer forbids, so the pattern has to reject it on that alone.
#
# Letters would not work: an alphanumeric prerelease such as 1.0.0-aaaa is
# valid SemVer, so a letter-padded input is accepted and tests nothing.
guard_check "1.0.0-0$(printf '0%.0s' $(seq 1 $((cap - 7))))" $VERDICT_REJECT
# Underscore, space and shell metacharacters are outside the allowed charset.
guard_check "1.2.3-alpha_1" $VERDICT_REJECT
# Both ends of the charset guard: a leading space or tab is exactly the
# input `*[!0-9A-Za-z.+-]*` exists to reject, and it is the variant that
# would slip through if the pattern were ever widened to allow leading
# whitespace, so it is tested here rather than only in REJECT.
guard_check "1.2.3 " $VERDICT_REJECT
guard_check " 1.2.3" $VERDICT_REJECT
guard_check "$(printf '\t1.2.3')" $VERDICT_REJECT
guard_check '1.2.3-$(id)' $VERDICT_REJECT
guard_check '1.2.3-`id`' $VERDICT_REJECT
guard_check "1.2.3-rc.1+build.1" $VERDICT_ACCEPT
guard_check "1.0.0-alpha" $VERDICT_ACCEPT

# ------------------------------------------------- the cap must actually bound the cost
# The pattern is a star inside a star over an overlapping class, so a
# backtracking matcher is quadratic in the input length. This is the reason the
# workflows cap the length, and the cap is only a real control if the cost at
# the cap is actually small.
#
# Measure it with ONE grep process and N lines, then divide: a separate
# process per input would measure process startup, not the matcher. GNU grep
# is a DFA and so stays fast at every length here, which is precisely why the
# cap is not redundant: the same pattern evaluated by a backtracking engine
# (PCRE, or re-deriving the check in another language) does O(n^2) work on the
# same inputs, and 4096 characters already takes 1.1 s there. The cap keeps
# every consumer of this pattern cheap regardless of which engine runs it.
note ""
note "=== 6. matcher cost vs input length (the reason the cap exists) ==="
if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  py="$(command -v python3 || command -v python)"
  # Worst case for a backtracker: a long run of valid identifier characters
  # followed by one character that cannot match, forcing full backtracking.
  # `set -e` is on, so a bare call that exits non-zero would kill the script
  # before `bad` ran and before the summary printed. Putting it in a
  # condition routes the failure through the normal accounting instead.
  if ! "$py" - "$SEMVER" "$cap" <<'PY'
import re
import sys
import time

pat, cap = re.compile(sys.argv[1]), int(sys.argv[2])
PREFIX, SUFFIX = "1.0.0-", "!"
OVERHEAD = len(PREFIX) + len(SUFFIX)
worst = 0.0
# n is the TOTAL input length, not the length of the a-run, so the
# "<= cap" row really is an input the length guard admits. Offsetting by
# OVERHEAD is what keeps the reported worst case inside the bound the
# workflows actually enforce.
for n in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
    s = PREFIX + "a" * (n - OVERHEAD) + SUFFIX
    assert len(s) == n, (len(s), n)
    reps = 200 if n <= 512 else 20
    t0 = time.perf_counter()
    for _ in range(reps):
        pat.search(s)
    per = (time.perf_counter() - t0) / reps
    if n <= cap:
        worst = per
    note = "<= cap" if n <= cap else "(rejected before the pattern runs)"
    print("  len=%-6d %8.3f ms  %s" % (n, per * 1000, note))
print("  ok: worst case at the cap (%d chars) is %.3f ms" % (cap, worst * 1000)
      if worst < 0.05 else
      "  FAIL: a %d-char input costs %.3f ms; the cap is too high" % (cap, worst * 1000))
sys.exit(0 if worst < 0.05 else 1)
PY
  then
    bad "the backtracking cost at the ${cap}-char cap is above the 50ms budget"
  fi
else
  note "  skipped: no python available to measure the backtracking cost"
fi

note ""
if [[ $fail -eq 0 ]]; then
  note "ALL SEMVER CASES PASS (pattern + guards + cost bound)"
else
  note "SEMVER VALIDATION HAS FAILURES"
fi
exit "$fail"
