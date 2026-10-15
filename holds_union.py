import json, subprocess, sys
from pathlib import Path
def stage(n):
    return json.loads(subprocess.run(["git", "show", f":{n}:docs/proof-sweep-holds.json"], capture_output=True, text=True, check=True).stdout)
base = json.loads(subprocess.run(["git", "show", ":1:docs/proof-sweep-holds.json"], capture_output=True, text=True).stdout or "{}")
ours, theirs = stage(2), stage(3)
out = dict(ours)
for k, v in theirs.items():
    if k == "held":
        merged = dict(ours["held"])
        for leaf, why in theirs["held"].items():
            if leaf in merged and merged[leaf] != why:
                print("DIFFERENT reason kept from ours for", leaf)
            merged.setdefault(leaf, why)
        out["held"] = merged
    elif k not in out:
        out[k] = v
raw = Path("docs/proof-sweep-holds.json").read_text()
indent = 2
p = Path("docs/proof-sweep-holds.json")
p.write_text(json.dumps(out, indent=indent, ensure_ascii=False) + "\n")
print("held:", len(out["held"]), "(ours", len(ours["held"]), "theirs", len(theirs["held"]), ")")
