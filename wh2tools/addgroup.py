"""Append a new one-line task group to the end of a module, and rows to the register.

usage: addgroup.py <repo> <wbsfile> <module id> <json {"group": name, "leaves": [...], "rows": [...]}>
If the group already exists by name (a second run), the leaves are appended to it.
"""
import json
import sys

repo, wbsfile, module, spec = sys.argv[1:5]
spec = json.load(open(spec))
path = f"{repo}/docs/wbs/{wbsfile}"
lines = open(path, encoding="utf-8").read().split("\n")
start = next(i for i, ln in enumerate(lines) if ln.startswith('{id:"%s",' % module))
end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("]}"))
name = json.dumps(spec["group"], ensure_ascii=False)
leaves = ",".join(json.dumps(t, ensure_ascii=False) for t in spec["leaves"])
existing = next((i for i in range(start, end) if lines[i].lstrip().startswith("{n:" + name)), None)
if existing is not None:
    line = lines[existing].rstrip()
    tail = "]}," if line.endswith("]},") else "]}"
    lines[existing] = line[: -len(tail)] + "," + leaves + tail
else:
    last = lines[end - 1].rstrip()
    if not last.endswith(","):
        lines[end - 1] = last + ","
    lines.insert(end, " {n:%s,s:[%s]}" % (name, leaves))
open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
if spec.get("rows"):
    rpath = f"{repo}/docs/requirements/register.json"
    data = json.loads(open(rpath, encoding="utf-8").read())
    data["requirements"].extend(spec["rows"])
    open(rpath, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    )
print("ok")
