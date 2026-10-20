"""Resolve conflict hunks in the named files by an explicit per-file policy.

usage: resolve_hunks.py POLICY FILE [FILE...]
POLICY: ours | theirs | theirs_ours | ours_theirs | union
`union` keeps ours then theirs and drops a theirs line already present in ours.
Refuses to finish if any marker remains.
"""

import sys
from pathlib import Path

policy = sys.argv[1]
for name in sys.argv[2:]:
    p = Path(name)
    out: list[str] = []
    ours: list[str] = []
    theirs: list[str] = []
    state = "n"
    for line in p.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("<<<<<<< "):
            state = "o"
            ours, theirs = [], []
        elif line.startswith("=======") and state == "o":
            state = "t"
        elif line.startswith(">>>>>>> ") and state == "t":
            if policy == "ours":
                out += ours
            elif policy == "theirs":
                out += theirs
            elif policy == "theirs_ours":
                out += theirs + ours
            elif policy == "ours_theirs":
                out += ours + theirs
            elif policy == "union":
                out += ours + [t for t in theirs if t not in ours]
            state = "n"
        elif state == "o":
            ours.append(line)
        elif state == "t":
            theirs.append(line)
        else:
            out.append(line)
    assert state == "n", name
    p.write_text("".join(out), encoding="utf-8", newline="\n")
    text = p.read_text(encoding="utf-8")
    assert "<<<<<<<" not in text and ">>>>>>>" not in text, name
    print("resolved", name)
