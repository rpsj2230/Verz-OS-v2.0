"""Re-fill the prose paragraphs of docstrings and comments that run past 100 columns.

A private helper for this package of work (never committed): it only touches a paragraph that has
a line over the limit, leaves code and one-line docstrings alone, and prints what it could not fix.
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

WIDTH = 100
LIST = re.compile(r"^\s*(?:[-*]|\d+[.)])\s")


def rewrap(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    remaining: list[str] = []
    in_doc = False
    index = 0
    while index < len(lines):
        line = lines[index]
        quotes = line.count('"""')
        starts_doc = quotes % 2 == 1 and not in_doc
        was_doc = in_doc
        if starts_doc:
            in_doc = True
        elif quotes % 2 == 1 and in_doc:
            in_doc = False
        prose = (was_doc or starts_doc) and quotes == 0 or (starts_doc and quotes == 1)
        is_comment = line.lstrip().startswith("#")
        if len(line) > WIDTH and (prose or is_comment) and not LIST.match(line):
            indent = re.match(r"\s*", line).group(0)  # type: ignore[union-attr]
            marker = ""
            body = line.strip()
            if is_comment:
                marker = "#: " if body.startswith("#:") else "# "
                body = body[len(marker) :] if body.startswith(marker) else body.lstrip("#: ")
            first_quote = ""
            if starts_doc and not was_doc:
                first_quote = '"""'
                body = body[3:]
            # gather the following lines of the same paragraph
            paragraph = [body]
            end = index + 1
            while end < len(lines):
                nxt = lines[end]
                stripped = nxt.strip()
                if not stripped or '"""' in nxt or LIST.match(nxt):
                    break
                if is_comment != stripped.startswith("#"):
                    break
                if is_comment:
                    stripped = stripped[len(marker) :] if stripped.startswith(marker) else stripped
                paragraph.append(stripped)
                end += 1
            text = " ".join(paragraph)
            prefix = indent + marker + first_quote
            subsequent = indent + marker
            wrapped = textwrap.wrap(
                text,
                width=WIDTH,
                initial_indent=prefix,
                subsequent_indent=subsequent,
                break_long_words=False,
                break_on_hyphens=False,
            )
            out.extend(wrapped)
            index = end
            continue
        if len(line) > WIDTH:
            remaining.append(f"{path}:{index + 1}: {len(line)}")
        out.append(line)
        index += 1
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    return remaining


if __name__ == "__main__":
    for name in sys.argv[1:]:
        for left in rewrap(Path(name)):
            print(left)
