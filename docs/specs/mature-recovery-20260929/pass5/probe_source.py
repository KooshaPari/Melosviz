#!/usr/bin/env python3
"""Execute frozen helper counterexamples, not a product/E2E acceptance suite.
Default mode uses explicit extracted bodies. --repo reads and hashes the full
frozen source, verifies executable AST equality, then uses those actual nodes.
An observation of a defect is NOT a passing product criterion.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, logging, platform, shutil, subprocess, sys, tempfile, wave
from pathlib import Path

PIN = "1aec20a2ba41a01ed557d1c7f63f9a0089f842cf"
BLOB = "549e70a5741f43546af3d068b5444d54d47affc2"
SOURCE = "backend/src/melosviz/conductor/orchestrator.py"
SYMBOLS = ("_is_zero_duration", "_artifact_rejection", "_materialise_cached_artifact")

class NoDoc(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        return node

def functions(text):
    root = NoDoc().visit(ast.parse(text))
    nodes = [n for n in root.body if isinstance(n, ast.FunctionDef) and n.name in SYMBOLS]
    if {n.name for n in nodes} != set(SYMBOLS):
        raise ValueError("missing expected source function")
    return nodes

def gitblob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def run(args):
    return subprocess.run(args, capture_output=True, check=False, timeout=20)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    extraction = Path(__file__).with_name("sources") / "orchestrator_helpers.py"
    nodes = functions(extraction.read_text())
    mode = "EXTRACTED_FUNCTION_EXECUTION"
    full_blob_verified = False
    if a.repo:
        raw = (a.repo / SOURCE).read_bytes()
        if gitblob(raw) != BLOB:
            raise ValueError("wrong source blob: refuses to claim reproduction on another candidate")
        original = functions(raw.decode())
        if [ast.dump(n) for n in nodes] != [ast.dump(n) for n in original]:
            raise ValueError("extracted executable AST differs from frozen source")
        nodes, mode, full_blob_verified = original, "FROZEN_FULL_SOURCE_AST_EXECUTION", True
    env = dict(Path=Path, json=json, shutil=shutil, logger=logging.getLogger("probe"))
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(extraction), "exec"), env)
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("BLOCKED: ffprobe absent; cannot independently check media")
    checks = []
    with tempfile.TemporaryDirectory(prefix="melosviz-counterexamples-") as td:
        root = Path(td)
        for name, data, expected_rejected in [
            ("garbage.mp4", bytes(64), False),
            ("malformed.wav", b"not a WAV file", False),
            ("empty.mp4", b"", True),
        ]:
            f = root / name; f.write_bytes(data)
            candidate = env["_artifact_rejection"](str(f))
            independent = run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(f)])
            checks.append(dict(case=name, candidate_rejection=candidate,
                independent_probe_exit=independent.returncode,
                false_green=candidate is None and independent.returncode != 0,
                expected_counterexample_observed=(candidate is not None) == expected_rejected and independent.returncode != 0,
                subject_sha256=sha(data), stderr=independent.stderr.decode(errors="replace")[-1000:]))
        f = root / "zero.wav"
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
        rejected = env["_artifact_rejection"](str(f))
        checks.append(dict(case="zero_frame_wav_control", candidate_rejection=rejected,
                           expected_counterexample_observed=bool(rejected and "zero-duration" in rejected), false_green=False))
        out = root / "out"; scene = out / "scene"; scene.mkdir(parents=True)
        blob = root / "cached.bin"; blob.write_bytes(b"NEW!")
        blob.with_suffix(".json").write_text(json.dumps({"artifact_relpath":"scene/clip.mp4"}))
        target = scene / "clip.mp4"; target.write_bytes(b"OLD!")
        got = env["_materialise_cached_artifact"](blob, out, scene)
        checks.append(dict(case="equal_size_wrong_bytes", returned_target=str(got.relative_to(root)),
            actual_bytes=target.read_text(), expected_bytes=blob.read_text(),
            actual_sha256=sha(target.read_bytes()), expected_sha256=sha(blob.read_bytes()),
            false_green=got is not None and target.read_bytes() != blob.read_bytes(),
            expected_counterexample_observed=target.read_bytes() == b"OLD!"))
        target.write_bytes(b"shorter")
        env["_materialise_cached_artifact"](blob, out, scene)
        checks.append(dict(case="different_size_copy_control", false_green=False,
                           expected_counterexample_observed=target.read_bytes() == b"NEW!"))
    payload = dict(schema_version=1, source_commit=PIN, source_path=SOURCE,
        claimed_source_blob=BLOB, full_blob_verified=full_blob_verified,
        execution_mode=mode, extraction_sha256=sha(extraction.read_bytes()),
        executable_ast_sha256={n.name:sha(ast.dump(n).encode()) for n in nodes},
        python=sys.version, platform=platform.platform(),
        ffprobe_version=run([ffprobe,"-version"]).stdout.decode().splitlines()[0],
        scope="Isolated real function bodies; NOT CLI/GUI/native/GPU E2E",
        product_verdict="FAIL_FOR_PROBED_CRITERIA", cases=checks,
        all_expected_observations=all(x["expected_counterexample_observed"] for x in checks))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(payload, indent=2)+"\n")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_expected_observations"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
