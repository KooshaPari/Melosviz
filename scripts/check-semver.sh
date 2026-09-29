#!/usr/bin/env bash
# Design + verify a strict SemVer 2.0.0 validator usable from a single
# grep -Eq, so the release workflows can reject malformed version strings.
#
# Grammar (https://semver.org):
#   valid-num  := 0 | [1-9][0-9]*
#   pre-id     := valid-num | NONDIGIT ( [0-9A-Za-z-]* NONDIGIT )?
#   build      := NONDIGIT ( [0-9A-Za-z-]* NONDIGIT )?  joined by '.'
#   version    := MAJOR '.' MINOR '.' PATCH [ '-' pre ] [ '+' build ]
#
# Must reject: 01.2.3, 1.2.3-01, 1.2.3-0.01, 1.2.3-foo..bar, 1.2.3-,
#              1.2.3+, 1.2.3+build_1, 1.2.3-alpha_1, 1.2.3-alpha+,
#              1.2.3+., 1.2, 1.2.3.4, v1.2.3, " 1.2.3", "1.2.3 ", 1.2.3-beta+
# Must accept: 1.2.3, 0.0.0, 1.0.0-alpha, 1.0.0-alpha.1, 1.0.0-0.3.7,
#              1.0.0-x.7.z.92, 1.0.0-alpha+001, 1.0.0+20130313144700,
#              1.0.0-beta+exp.sha.5114f85, 1.0.0-rc.1+build.1, 10.20.30
#              1.0.0-- (legal: '-' is a NONDIGIT leading prerelease id)
#
# Note on `+01`: build identifiers have NO leading-zero restriction under the
# official grammar, so 1.2.3+01 is valid and must be accepted. The leading-zero
# rule applies only to numeric *prerelease* ids, which is why 1.2.3-01 fails.
#
# NOTE: GNU grep -E has no non-capturing groups and no \d, so the whole
# grammar is spelled out with plain capturing groups and [0-9] classes.
SEMVER='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-((0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?(\+([0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*))?$'

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
)

REJECT=(
  01.2.3
  1.02.3
  1.2.03
  1.2.3-01
  1.2.3-0.01
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
  " 1.2.3"
  "1.2.3 "
  ""
  "1.2.3-beta+"
  "1.2.3-beta..1"
  "1.2.3+build..1"
)

fail=0
for v in "${ACCEPT[@]}"; do
  if printf '%s' "$v" | grep -Eq "$SEMVER"; then
    printf 'ok    accept %s\n' "$v"
  else
    printf 'FAIL  should accept but rejected: %s\n' "$v"
    fail=1
  fi
done

for v in "${REJECT[@]}"; do
  if printf '%s' "$v" | grep -Eq "$SEMVER"; then
    printf 'FAIL  should reject but accepted: %s\n' "$v"
    fail=1
  else
    printf 'ok    reject %s\n' "$v"
  fi
done

printf '\n'
if [[ $fail -eq 0 ]]; then
  echo "ALL SEMVER CASES PASS"
else
  echo "SEMVER PATTERN HAS FAILURES"
fi
exit "$fail"
