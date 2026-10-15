"""Merge another branch's needs items into the train's needs page, renumbered.

usage: renumber_needs.py <their_ref> <first_old> <last_old> <new_first>
Their items old..last map to new_first.. in order; blocks are copied whole, with their own numbers
rewritten (heading, the reply prompts), the header rebuilt on top of the train's, counts left to the caller.
"""
import re, subprocess, sys
from pathlib import Path
their_ref, first_old, last_old, new_first = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
mapping = {old: new_first + (old - first_old) for old in range(first_old, last_old + 1)}
def show(spec):
    return subprocess.run(["git", "show", spec], capture_output=True, text=True, check=True).stdout
theirs = show(f"{their_ref}:docs/needs-rupash.md")
ours = show(":2:docs/needs-rupash.md")
def renumber(text):
    # heading, quoted replies ("180: B"), and "item 180" style mentions, only for numbers in the mapping
    def sub_heading(m): return f"## {mapping[int(m.group(1))]}."
    text = re.sub(r"^## (\d+)\.", lambda m: sub_heading(m) if int(m.group(1)) in mapping else m.group(0), text, flags=re.M)
    text = re.sub(r'"(\d+): ([A-Z][^"]*)"', lambda m: f'"{mapping[int(m.group(1))]}: {m.group(2)}"' if int(m.group(1)) in mapping else m.group(0), text)
    return text
# the blocks: from the first of their new headings down to just before the item below their range
hi = last_old; lo = first_old
start = theirs.index(f"## {hi}. ")
end = theirs.index(f"## {lo - 1}. ")
blocks = renumber(theirs[start:end])
# the header's items
their_header = theirs.splitlines()[4]
our_header = ours.splitlines()[4]
cut = their_header.index(f"**{lo - 1},**")
new_part = renumber_h = re.sub(r"\*\*(\d+),\*\*", lambda m: f"**{mapping.get(int(m.group(1)), int(m.group(1)))},**" if int(m.group(1)) in mapping else m.group(0), their_header[: cut])
# strip their leading "**N items are open: "
new_part = re.sub(r"^\*\*\d+ items are open: ", "", new_part)
count_now = int(re.match(r"\*\*(\d+) items are open", our_header).group(1)); added = last_old - first_old + 1
our_rest = re.sub(r"^\*\*\d+ items are open: ", "", our_header)
header = f"**{count_now + added} items are open: " + new_part + our_rest
lines = ours.splitlines(keepends=True)
lines[4] = header + "\n"
text = "".join(lines)
top = max(int(x) for x in re.findall(r'^## (\d+)\.', text, flags=re.M))
anchor = text.index(f"## {top}. ")
text = text[:anchor] + blocks + text[anchor:]
Path("docs/needs-rupash.md").write_text(text)
print("items added:", added, "count now", count_now + added, "| mapping", mapping)
