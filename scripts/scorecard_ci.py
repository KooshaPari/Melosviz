#!/usr/bin/env python3
"""
88-Pillar Scorecard CI Script
Audits a repository against 88 quality and security pillars.

Two properties matter for this to work as a CI gate:

1. The result must not depend on which directories happen to be present
   locally. Globs therefore skip dependency trees and build output.
2. The result must not depend on the host filesystem's case sensitivity.
   Matching is case-insensitive everywhere.
"""
import os, sys, json, argparse, fnmatch
from pathlib import Path

PILLARS = [
    {"id":1,"name":"README","check":lambda p:(p/"README.md").exists() or (p/"readme.md").exists()},
    {"id":2,"name":"LICENSE","check":lambda p:any(p.glob("LICENSE*"))},
    {"id":3,"name":"CONTRIBUTING","check":lambda p:(p/"CONTRIBUTING.md").exists()},
    {"id":4,"name":"CODE_OF_CONDUCT","check":lambda p:(p/"CODE_OF_CONDUCT.md").exists()},
    {"id":5,"name":"SECURITY","check":lambda p:(p/"SECURITY.md").exists()},
    {"id":6,"name":"CHANGELOG","check":lambda p:any(p.glob("CHANGELOG*")) or any(p.glob("CHANGES*"))},
    {"id":7,"name":"CLAUDE_MD","check":lambda p:(p/"CLAUDE.md").exists()},
    {"id":8,"name":"EDITORCONFIG","check":lambda p:(p/".editorconfig").exists()},
    {"id":9,"name":"GITIGNORE","check":lambda p:(p/".gitignore").exists()},
    {"id":10,"name":"DOCKERFILE","check":lambda p:(p/"Dockerfile").exists()},
    {"id":11,"name":"DOCKER_COMPOSE","check":lambda p:(p/"docker-compose.yml").exists() or (p/"docker-compose.yaml").exists()},
    {"id":12,"name":"MAKEFILE","check":lambda p:(p/"Makefile").exists()},
    {"id":13,"name":"JUSTFILE","check":lambda p:(p/"Justfile").exists()},
    {"id":14,"name":"PACKAGE_JSON","check":lambda p:(p/"package.json").exists()},
    {"id":15,"name":"PYPROJECT_TOML","check":lambda p:(p/"pyproject.toml").exists()},
    {"id":16,"name":"CARGO_TOML","check":lambda p:(p/"Cargo.toml").exists()},
    {"id":17,"name":"GO_MOD","check":lambda p:(p/"go.mod").exists()},
    {"id":18,"name":"ENV_EXAMPLE","check":lambda p:(p/".env.example").exists() or (p/".env.template").exists()},
    {"id":19,"name":"CI_WORKFLOW","check":lambda p:len(list((p/".github/workflows").glob("*.yml")))>0 if (p/".github/workflows").exists() else False},
    {"id":20,"name":"CODEOWNERS","check":lambda p:(p/".github/CODEOWNERS").exists() or (p/"CODEOWNERS").exists()},
    {"id":21,"name":"DEPENDABOT","check":lambda p:(p/".github/dependabot.yml").exists() or (p/".github/dependabot.yaml").exists()},
    {"id":22,"name":"ISSUE_TEMPLATE","check":lambda p:(p/".github/ISSUE_TEMPLATE").exists() and any((p/".github/ISSUE_TEMPLATE").iterdir()) if (p/".github/ISSUE_TEMPLATE").exists() else False},
    {"id":23,"name":"PR_TEMPLATE","check":lambda p:any(p.glob(".github/PULL_REQUEST_TEMPLATE*")) or any(p.glob(".github/pull_request_template*"))},
    {"id":24,"name":"FUZZ_TESTS","check":lambda p:(p/"fuzz").exists() or any(p.glob("**/fuzz_*.rs"))},
    {"id":25,"name":"BENCHMARKS","check":lambda p:(p/"benches").exists() or (p/"bench").exists()},
    {"id":26,"name":"MUTANT_TESTS","check":lambda p:(p/"mutants.out").exists() or (p/"mutants.toml").exists()},
    {"id":27,"name":"UNIT_TESTS","check":lambda p:any(p.glob("**/test_*.py")) or any(p.glob("**/*_test.rs")) or any(p.glob("**/*.test.ts")) or any(p.glob("**/*.spec.ts"))},
    {"id":28,"name":"INTEGRATION_TESTS","check":lambda p:(p/"tests"/"integration").exists() or (p/"test"/"integration").exists()},
    {"id":29,"name":"E2E_TESTS","check":lambda p:(p/"tests"/"e2e").exists() or (p/"e2e").exists()},
    {"id":30,"name":"CODE_COVERAGE","check":lambda p:(p/".coveragerc").exists() or (p/"codecov.yml").exists()},
    {"id":31,"name":"LINTING","check":lambda p:(p/".eslintrc.js").exists() or (p/"ruff.toml").exists() or (p/".clippy.toml").exists()},
    {"id":32,"name":"FORMATTING","check":lambda p:(p/".prettierrc").exists() or (p/"rustfmt.toml").exists()},
    {"id":33,"name":"SECURITY_SCANNING","check":lambda p:(p/".github/workflows"/"codeql.yml").exists() or (p/".github/workflows"/"trivy.yml").exists()},
    {"id":34,"name":"DEPENDENCY_AUDIT","check":lambda p:(p/".snyk").exists() or (p/"audit-ci.json").exists()},
    {"id":35,"name":"OPENAPI_SPEC","check":lambda p:any(p.glob("**/openapi.json")) or any(p.glob("**/swagger.json"))},
    {"id":36,"name":"DOCS_SITE","check":lambda p:(p/"docs").exists() or (p/"website").exists()},
    {"id":37,"name":"I18N","check":lambda p:(p/"locales").exists() or (p/"i18n").exists()},
    {"id":38,"name":"A11Y","check":lambda p:any(p.glob("**/*a11y*"))},
    {"id":39,"name":"LOAD_TESTING","check":lambda p:(p/"loadtests").exists() or (p/"load_tests").exists()},
    {"id":40,"name":"CONTAINER_SCANNING","check":lambda p:any(p.glob("**/trivyignore"))},
    {"id":41,"name":"FEATURE_FLAGS","check":lambda p:any(p.glob("**/*feature*flag*"))},
    {"id":42,"name":"LOGGING","check":lambda p:any(p.glob("**/logging.py")) or any(p.glob("**/*logger*"))},
    {"id":43,"name":"MONITORING","check":lambda p:(p/"monitoring").exists() or (p/"prometheus.yml").exists()},
    {"id":44,"name":"TRACING","check":lambda p:any(p.glob("**/*opentelemetry*")) or any(p.glob("**/*tracing*"))},
    {"id":45,"name":"ALERTING","check":lambda p:(p/"alerts.yml").exists() or (p/"alerting_rules.yml").exists()},
    {"id":46,"name":"RATE_LIMITING","check":lambda p:any(p.glob("**/*rate*limit*"))},
    {"id":47,"name":"CACHING","check":lambda p:any(p.glob("**/*cache*config*"))},
    {"id":48,"name":"SSL_TLS","check":lambda p:any(p.glob("**/ssl*.conf"))},
    {"id":49,"name":"WAF","check":lambda p:any(p.glob("**/*waf*"))},
    {"id":50,"name":"MFA","check":lambda p:any(p.glob("**/*mfa*"))},
    {"id":51,"name":"RBAC","check":lambda p:any(p.glob("**/*rbac*"))},
    {"id":52,"name":"AUDIT_LOGS","check":lambda p:any(p.glob("**/*audit*log*"))},
    {"id":53,"name":"DATABASE_MIGRATIONS","check":lambda p:(p/"migrations").exists() or (p/"migrate").exists()},
    {"id":54,"name":"ENV_VARS","check":lambda p:(p/".env").exists() or (p/".env.local").exists()},
    {"id":55,"name":"KUBERNETES","check":lambda p:any(p.glob("**/k8s/*.yml")) or any(p.glob("**/kubernetes/*.yml"))},
    {"id":56,"name":"HELM","check":lambda p:(p/"Chart.yaml").exists()},
    {"id":57,"name":"TERRAFORM","check":lambda p:any(p.glob("**/*.tf"))},
    {"id":58,"name":"ANSIBLE","check":lambda p:(p/"playbooks").exists() or (p/"roles").exists()},
    {"id":59,"name":"CLOUDFORMATION","check":lambda p:any(p.glob("**/*.template"))},
    {"id":60,"name":"CANARY_DEPLOY","check":lambda p:any(p.glob("**/*canary*"))},
    {"id":61,"name":"ROLLBACK","check":lambda p:any(p.glob("**/*rollback*"))},
    {"id":62,"name":"DATA_PRIVACY","check":lambda p:any(p.glob("**/*privacy*")) or any(p.glob("**/*gdpr*"))},
    {"id":63,"name":"COMPLIANCE","check":lambda p:any(p.glob("**/*compliance*"))},
    {"id":64,"name":"LICENSE_SCANNING","check":lambda p:(p/"license-checker.json").exists()},
    {"id":65,"name":"SECRET_SCANNING","check":lambda p:(p/".gitleaks.toml").exists()},
    {"id":66,"name":"IAAC","check":lambda p:any(p.glob("**/terraform/*.tf")) or any(p.glob("**/ansible/*.yml"))},
    {"id":67,"name":"CDN","check":lambda p:any(p.glob("**/*cdn*"))},
    {"id":68,"name":"FIREWALL","check":lambda p:any(p.glob("**/*firewall*"))},
    {"id":69,"name":"VPN","check":lambda p:any(p.glob("**/*vpn*"))},
    {"id":70,"name":"SSO","check":lambda p:any(p.glob("**/*sso*")) or any(p.glob("**/*oauth*"))},
    {"id":71,"name":"BACKUPS","check":lambda p:any(p.glob("**/*backup*")) or any(p.glob("**/*restore*"))},
    {"id":72,"name":"DISASTER_RECOVERY","check":lambda p:any(p.glob("**/*disaster*recovery*"))},
    {"id":73,"name":"STRESS_TESTING","check":lambda p:any(p.glob("**/*stress*test*"))},
    {"id":74,"name":"PERFORMANCE_TESTING","check":lambda p:any(p.glob("**/*perf*test*"))},
    {"id":75,"name":"SEO","check":lambda p:any(p.glob("**/*seo*")) or (p/"sitemap.xml").exists()},
    {"id":76,"name":"ANALYTICS","check":lambda p:any(p.glob("**/*analytics*")) or any(p.glob("**/*gtag*"))},
    {"id":77,"name":"FEEDBACK","check":lambda p:any(p.glob("**/*feedback*"))},
    {"id":78,"name":"SUPPORT","check":lambda p:(p/"SUPPORT.md").exists() or any(p.glob("**/*support*"))},
    {"id":79,"name":"ROADMAP","check":lambda p:(p/"ROADMAP.md").exists() or any(p.glob("**/*roadmap*"))},
    {"id":80,"name":"STATUS_PAGE","check":lambda p:any(p.glob("**/*status*page*"))},
    {"id":81,"name":"INCIDENT_RESPONSE","check":lambda p:any(p.glob("**/*incident*response*"))},
    {"id":82,"name":"DATA_SEEDING","check":lambda p:(p/"seeds").exists() or (p/"seed").exists()},
    {"id":83,"name":"DATA_CLEANUP","check":lambda p:any(p.glob("**/*cleanup*")) or any(p.glob("**/*prune*"))},
    {"id":84,"name":"THROTTLING","check":lambda p:any(p.glob("**/*throttl*"))},
    {"id":85,"name":"BUSINESS_CONTINUITY","check":lambda p:any(p.glob("**/*business*continuity*"))},
    {"id":86,"name":"SUCCESSION_PLANNING","check":lambda p:any(p.glob("**/*succession*"))},
    {"id":87,"name":"SHIPPING","check":lambda p:(p/".releaserc").exists() or (p/"release.config.js").exists()},
    {"id":88,"name":"RELEASE_NOTES","check":lambda p:any(p.glob("**/*release*note*"))},
]

# Dependency trees, build output and caches. Their contents are not part of
# the repository. Leaving them in made the score depend on whether the
# machine had run an install: web/node_modules/hls.js/src/utils/logger.ts
# satisfied LOGGING, utility-types/SUPPORT.md satisfied SUPPORT, and so on.
EXCLUDED_DIRS = {
    ".git", "node_modules", "target", ".venv", "venv", "env",
    "dist", "build", "coverage", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".turbo", ".next", ".cache",
    ".idea", ".vscode-test",
}


class RepoView:
    """Path-like view of a repository.

    Exposes the subset of the pathlib API the pillar checks use -- `/`,
    `exists()`, `iterdir()`, `glob()` -- with two deliberate differences
    from `Path`:

    * globs/walks skip EXCLUDED_DIRS, so build and dependency trees cannot
      satisfy a pillar;
    * matching is case-insensitive on every platform. pathlib is
      case-insensitive on Windows and case-sensitive on Linux, which made
      `**/*privacy*` match the tracked `docs/PRIVACY.md` locally but not
      in CI.
    """

    def __init__(self, root, files, dirs, parts=()):
        self._root = root
        self._files = files
        self._dirs = dirs
        self._parts = parts

    @classmethod
    def index(cls, root):
        files, dirs = [], []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            reldir = os.path.relpath(dirpath, root)
            reldir = "" if reldir == "." else reldir.replace(os.sep, "/")
            for d in dirnames:
                dirs.append((reldir + "/" + d) if reldir else d)
            for fn in filenames:
                files.append((reldir + "/" + fn) if reldir else fn)
        return cls(Path(root), files, dirs)

    def _child(self, parts):
        return RepoView(self._root, self._files, self._dirs, parts)

    def __truediv__(self, other):
        return self._child(self._parts + (str(other),))

    def _rel(self):
        return "/".join(self._parts).lower()

    def exists(self):
        r = self._rel()
        return r in self._flc() or r in self._dlc()

    def _flc(self):
        return self._files_lower_cache

    def _dlc(self):
        return self._dirs_lower_cache

    def iterdir(self):
        base = self._rel()
        prefix = base + "/" if base else ""
        out = []
        for c in list(self._files) + list(self._dirs):
            if not c.lower().startswith(prefix):
                continue
            rest = c[len(prefix):]
            if rest and "/" not in rest:
                out.append(self._root / c)
        return out

    def glob(self, pattern):
        base = self._rel()
        pat = pattern.lower()
        out = []
        for cand in list(self._files) + list(self._dirs):
            lc = cand.lower()
            if base:
                if not lc.startswith(base + "/"):
                    continue
                sub = lc[len(base) + 1:]
            else:
                sub = lc
            if fnmatch.fnmatchcase(sub, pat):
                out.append(self._root / cand)
            elif pat.startswith("**/") and fnmatch.fnmatchcase(sub, pat[3:]):
                out.append(self._root / cand)
        return out


def audit_repo(repo_path):
    path = Path(repo_path)
    if not path.is_dir():
        raise ValueError(f"Path {repo_path} is not a directory")
    view = RepoView.index(repo_path)
    # cache lowercase lookup sets once; RepoView instances share the lists
    view._files_lower_cache = {f.lower() for f in view._files}
    view._dirs_lower_cache = {d.lower() for d in view._dirs}
    RepoView._files_lower_cache = view._files_lower_cache
    RepoView._dirs_lower_cache = view._dirs_lower_cache

    results, score = [], 0
    for pillar in PILLARS:
        try:
            passed = pillar["check"](view)
            if isinstance(passed, list): passed = len(passed) > 0
            results.append({"id":pillar["id"],"name":pillar["name"],"passed":bool(passed)})
            if passed: score += 1
        except Exception as e:
            results.append({"id":pillar["id"],"name":pillar["name"],"passed":False,"error":str(e)})
    return {"score":score,"total":len(PILLARS),"percentage":(score/len(PILLARS))*100,"results":results}


# The baseline is project configuration that lives at a known path next to
# this script. It is deliberately not a command line option: a free-form
# path would add attack surface for no benefit, and every caller wants the
# one canonical file.
REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / ".github" / "scorecard-baseline.json"


def _load_baseline():
    """Read the tracked baseline score, or None if none has been recorded."""
    if not BASELINE_PATH.is_file():
        return None
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("score")


def main():
    parser = argparse.ArgumentParser(description="88-Pillar Scorecard Audit")
    parser.add_argument("path", help="Path to repository")
    parser.add_argument("--threshold", type=int, default=None,
                        help="Absolute minimum score. Fails if the score is lower.")
    parser.add_argument("--fail-on-drop", action="store_true",
                        help="Exit non-zero when the score is below the tracked baseline.")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Record the current score as the tracked baseline and exit 0.")
    parser.add_argument("--output", choices=["text","json","markdown"], default="text")
    args = parser.parse_args()

    try:
        report = audit_repo(args.path)
        baseline = _load_baseline()

        if args.update_baseline:
            payload = {"score": report["score"], "total": report["total"],
                       "percentage": round(report["percentage"], 1)}
            with open(BASELINE_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.write("\n")
            print("Baseline written to %s: %d/%d"
                  % (BASELINE_PATH, report["score"], report["total"]))
            return

        if args.output == "json":
            out = dict(report)
            out["threshold"] = args.threshold
            out["baseline"] = baseline
            print(json.dumps(out, indent=2))
        elif args.output == "markdown":
            print("# 88-Pillar Scorecard Report\n")
            print(f"**Score:** {report['score']}/{report['total']} ({report['percentage']:.1f}%)\n")
            if baseline is not None:
                print(f"**Baseline:** {baseline}\n")
            if args.threshold is not None:
                print(f"**Threshold:** {args.threshold}\n")
            print("## Results\n| ID | Pillar | Status |\n|---|--------|--------|")
            for r in report["results"]:
                print(f"| {r['id']} | {r['name']} | {'PASS' if r['passed'] else 'FAIL'} |")
        else:
            print(f"Scorecard: {report['score']}/{report['total']} ({report['percentage']:.1f}%)")
            if baseline is not None:
                print(f"Baseline: {baseline}")
            if args.threshold is not None:
                print(f"Threshold: {args.threshold}")
            failed = [r["name"] for r in report["results"] if not r["passed"]]
            print("Failed: " + ", ".join(failed))

        problems = []
        if args.threshold is not None and report["score"] < args.threshold:
            problems.append("score %d is below threshold %d"
                            % (report["score"], args.threshold))
        if args.fail_on_drop and baseline is not None and report["score"] < baseline:
            problems.append("score %d dropped below baseline %d"
                            % (report["score"], baseline))
        if problems:
            for p in problems:
                # stderr, so stdout stays valid JSON for --output json
                print("::error::" + p, file=sys.stderr)
            sys.exit(1)

        if baseline is not None and report["score"] > baseline:
            print("Score improved from %d to %d; bump the baseline with "
                  "--update-baseline." % (baseline, report["score"]))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
