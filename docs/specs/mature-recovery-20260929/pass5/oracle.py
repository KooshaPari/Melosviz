#!/usr/bin/env python3
"""Independent, fail-closed oracle for a SMALL LOSSLESS 3-scene test profile.
Not a general video quality/safety judge. Policy must be supplied by the reviewer,
not obtained from the candidate. Exit 0=all expected criteria pass, 1=fail,
2=collector/input failure. Selftests validate this oracle, NOT Melosviz.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from fractions import Fraction
from pathlib import Path

VERSION = "mv-oracle-0.2-experimental"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FRAMES = 96

class Blocked(RuntimeError): pass

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def execute(args: list[str]) -> bytes:
    try:
        r = subprocess.run(args, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked(str(exc)) from exc
    if r.returncode or r.stderr.strip():
        raise ValueError(f"media collector rejected input: {r.stderr.decode(errors='replace')[-500:]}")
    return r.stdout

def inside(root: Path, raw: str) -> Path:
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("artifact path is not a confined relative path")
    p = (root / rel).resolve(strict=True)
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError("artifact escapes root or is not a file")
    if not 0 < p.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("artifact size outside fixture limits")
    return p

def inspect_media(path: Path, expected: dict, ffmpeg: str, ffprobe: str) -> dict:
    before = sha(path.read_bytes())
    common = ["-v", "error", "-protocol_whitelist", "file,pipe", "-format_whitelist", "matroska,webm,mov"]
    info = json.loads(execute([ffprobe, *common, "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)]))
    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(video) != 1 or len(audio) != 1 or len(info.get("streams", [])) != 2:
        raise ValueError("fixture requires exactly one video and one audio stream")
    v, a = video[0], audio[0]
    if v.get("codec_name") != "ffv1" or a.get("codec_name") != "pcm_s16le":
        raise ValueError("unqualified codec for lossless fixture profile")
    if (v.get("width"), v.get("height")) != (expected["width"], expected["height"]):
        raise ValueError("wrong geometry")
    if Fraction(v["r_frame_rate"]) != Fraction(expected["fps"]):
        raise ValueError("wrong frame rate")
    if int(v.get("nb_read_frames", -1)) != expected["frames"]:
        raise ValueError("wrong decoded frame count")
    timestamps = json.loads(execute([ffprobe, *common, "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path)]))
    observed_times = timestamps.get("frames", [])
    if len(observed_times) != expected["frames"]:
        raise ValueError("timestamp count mismatch")
    tolerance = Fraction(expected["pts_tolerance_s"])
    if tolerance < 0 or tolerance > Fraction(1, 500):
        raise ValueError("unqualified timing tolerance")
    for i, frame in enumerate(observed_times):
        if abs(Fraction(frame["best_effort_timestamp_time"]) - Fraction(i, 1) / Fraction(expected["fps"])) > tolerance:
            raise ValueError("presentation timeline differs from fixture clock")
    if int(a["sample_rate"]) != expected["sample_rate"] or a["channels"] != 1:
        raise ValueError("wrong audio configuration")
    audio_times = json.loads(execute([ffprobe, *common, "-select_streams", "a:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time,nb_samples", "-of", "json", str(path)]))
    sample_cursor = 0
    for frame in audio_times.get("frames", []):
        if abs(Fraction(frame["best_effort_timestamp_time"]) - Fraction(sample_cursor, expected["sample_rate"])) > tolerance:
            raise ValueError("audio presentation timeline differs from fixture clock")
        sample_cursor += int(frame["nb_samples"])
    if sample_cursor != expected["samples"]:
        raise ValueError("decoded audio sample count mismatch")
    if expected["frames"] > MAX_FRAMES or expected["width"] > 64 or expected["height"] > 64:
        raise ValueError("policy exceeds fixture resource ceiling")
    rgb = execute([ffmpeg, *common, "-xerror", "-err_detect", "explode", "-i", str(path),
        "-map", "0:v:0", "-frames:v", str(MAX_FRAMES+1), "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    pcm = execute([ffmpeg, *common, "-xerror", "-err_detect", "explode", "-i", str(path),
        "-map", "0:a:0", "-t", "9", "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1"])
    if len(rgb) != expected["frames"] * expected["width"] * expected["height"] * 3:
        raise ValueError("decoded video length mismatch")
    if sha(rgb) != expected["rgb_sha256"] or sha(pcm) != expected["pcm_sha256"]:
        raise ValueError("decoded content/order/audio differs from accepted fixture")
    after = sha(path.read_bytes())
    if before != after:
        raise ValueError("artifact changed while being evaluated")
    return {"artifact_sha256": before, "decoded_rgb_sha256": sha(rgb), "decoded_pcm_sha256": sha(pcm)}

def evaluate(policy: dict, receipt: dict, root: Path, *, ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    errors, observations = [], []
    if not isinstance(policy, dict) or not isinstance(receipt, dict):
        return {"verdict":"FAIL", "verifier":VERSION, "errors":["policy and receipt must be objects"], "observations":[]}
    try:
        fm, fp = ffmpeg or shutil.which("ffmpeg"), ffprobe or shutil.which("ffprobe")
        if not fm or not fp:
            raise Blocked("required media collector unavailable")
        expected = policy.get("scenes")
        if not isinstance(expected, list) or not expected or len(expected) > 8:
            raise ValueError("empty/oversized trusted scene denominator")
        ids = [s["id"] for s in expected]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate trusted scene IDs")
        for key in ("product", "project_revision", "contract", "candidate", "configuration"):
            if not policy.get(key) or receipt.get(key) != policy[key]:
                errors.append(f"identity mismatch: {key}")
        if receipt.get("run_id") != policy.get("expected_run_id") or not policy.get("expected_run_id"):
            errors.append("stale/wrong evaluation run")
        if receipt.get("collector_status") != "complete":
            errors.append("missing/failed/skipped collection")
        actual = receipt.get("scenes", [])
        if not isinstance(actual, list) or not all(isinstance(s, dict) for s in actual) or [s.get("id") for s in actual] != ids:
            errors.append("missing/duplicate/reordered scene receipts")
        else:
            for want, got in zip(expected, actual, strict=True):
                if got.get("revision") != want["revision"] or got.get("mode") != "real-media":
                    errors.append(f"scene identity/mode mismatch: {want['id']}"); continue
                try:
                    obs = inspect_media(inside(root, got["path"]), want, fm, fp)
                    if got.get("artifact_sha256") != obs["artifact_sha256"]:
                        errors.append(f"artifact digest mismatch: {want['id']}")
                    observations.append({"scene": want["id"], **obs})
                except ValueError as exc:
                    errors.append(f"scene {want['id']}: {exc}")
        final = receipt.get("assembly", {})
        if not isinstance(final, dict) or final.get("state") != "assembled_unverified":
            errors.append("no independently verifiable assembled output")
        else:
            try:
                obs = inspect_media(inside(root, final["path"]), policy["assembly"], fm, fp)
                if final.get("artifact_sha256") != obs["artifact_sha256"]:
                    errors.append("assembly digest mismatch")
                observations.append({"assembly": True, **obs})
            except ValueError as exc:
                errors.append(f"assembly: {exc}")
    except Blocked as exc:
        return {"verdict":"BLOCKED", "verifier":VERSION, "verifier_sha256":sha(Path(__file__).read_bytes()), "errors":[str(exc)], "observations":observations}
    except (KeyError, TypeError, ValueError, OSError, AttributeError) as exc:
        errors.append(f"invalid or missing evidence: {exc}")
    return {"verdict":"FAIL" if errors else "PASS", "verifier":VERSION, "verifier_sha256":sha(Path(__file__).read_bytes()),
            "identity_authentication":"requires trusted external execution receipt; claims alone are not authenticated",
            "policy_sha256":sha(json.dumps(policy, sort_keys=True).encode()), "errors":errors, "observations":observations}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy",required=True,type=Path); p.add_argument("--receipt",required=True,type=Path)
    p.add_argument("--root",required=True,type=Path); p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    try: result=evaluate(json.loads(a.policy.read_text()),json.loads(a.receipt.read_text()),a.root)
    except (OSError,ValueError) as exc: result={"verdict":"BLOCKED","errors":[str(exc)]}
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    return {"PASS":0,"FAIL":1,"BLOCKED":2}[result["verdict"]]

if __name__=="__main__": raise SystemExit(main())
