import subprocess, re, json

actions = [
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    "dtolnay/rust-toolchain@2c7215f132e9ebf062739d9130488b56d53c060c",
    "oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "sigstore/cosign-installer@3454372f43399081ed03b604cb2d021dabca52bb",
    "actions/attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373",
    "softprops/action-gh-release@c95fe60539f7a31b3f6c3a0c2c0515c3ba6d0a7c",
]

for action in actions:
    name, sha = action.split("@")
    # Try resolving the full SHA
    r = subprocess.run(["c:/Program Files/GitHub CLI/gh.exe", "api", f"repos/{name}/commits/{sha}"], capture_output=True, text=True)
    d = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", r.stdout)
    if r.returncode == 0 and '"sha"' in d:
        try:
            data = json.loads(d)
            real = data.get("sha", "?")[:12]
            msg = data.get("commit", {}).get("message", "")[:60]
            print(f"  OK  {name}@{sha[:10]}... = {real}  '{msg}'")
        except:
            print(f"  ??  {name}@{sha[:10]}... parse-err")
    else:
        print(f"  BAD {name}@{sha[:10]}... NOT FOUND (rc={r.returncode})")
