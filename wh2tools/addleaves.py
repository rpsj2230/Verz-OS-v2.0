"""Append leaves to the last one-line task group of one module, and rows to the register.

usage: addleaves.py <repo> <wbsfile> <module id e.g. M10> <json file with {"leaves":[...],"rows":[...]}>
"""
import json
import sys

repo, wbsfile, module, spec = sys.argv[1:5]
spec = json.load(open(spec))
path = f"{repo}/docs/wbs/{wbsfile}"
text = open(path, encoding="utf-8").read()
lines = text.split("\n")
start = next(i for i, ln in enumerate(lines) if ln.startswith('{id:"%s",' % module))
end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("]}"))
group = end - 1
line = lines[group].rstrip()
tail = "]}," if line.endswith("]},") else "]}"
assert line.endswith(tail), line[-40:]
body = line[: -len(tail)]
adds = "".join("," + json.dumps(t, ensure_ascii=False) for t in spec["leaves"])
lines[group] = body + adds + tail
open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

if spec.get("rows"):
    rpath = f"{repo}/docs/requirements/register.json"
    data = json.loads(open(rpath, encoding="utf-8").read())
    data["requirements"].extend(spec["rows"])
    out = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    open(rpath, "w", encoding="utf-8", newline="\n").write(out)
print("ok", len(spec["leaves"]), "leaves", len(spec.get("rows", [])), "rows")
