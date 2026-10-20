"""Resolves conflict hunks by named choice (untracked helper). Run in the merge worktree."""

import re
import sys
from pathlib import Path

HUNK = re.compile(
    r"<<<<<<< [^\n]*\n(?P<ours>.*?)=======\n(?P<theirs>.*?)>>>>>>> [^\n]*\n", re.S
)

CHOICES: dict[str, list[str]] = {
    "docker-compose.lite.yml": ["theirs", "theirs_then_ours"],
    "ops/install/install.sh": ["ours"],
    "src/brain/ops/compose.py": ["ours"],
    "docs/install/configuration.md": ["theirs_then_ours_second_line"],
    "docs/install/install.md": ["ours"],
    "tests/unit/test_compose.py": ["ours", "ours", "ours"],
    "tests/unit/test_deployment_requirements.py": ["ours"],
    "tests/unit/test_features.py": ["ours_then_theirs", "ours_then_theirs"],
    "tests/unit/test_wiring.py": ["theirs", "theirs", "theirs"],
}


def pick(choice: str, ours: str, theirs: str) -> str:
    if choice == "ours":
        return ours
    if choice == "theirs":
        return theirs
    if choice == "theirs_then_ours":
        return theirs + ours
    if choice == "ours_then_theirs":
        return ours + theirs
    if choice == "theirs_then_ours_second_line":
        return theirs + ours.split("\n", 1)[1]
    raise SystemExit(choice)


for name, choices in CHOICES.items():
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    found = list(HUNK.finditer(text))
    if len(found) != len(choices):
        raise SystemExit(f"{name}: {len(found)} hunks, {len(choices)} choices")
    out: list[str] = []
    last = 0
    for match, choice in zip(found, choices, strict=True):
        out.append(text[last : match.start()])
        out.append(pick(choice, match.group("ours"), match.group("theirs")))
        last = match.end()
    out.append(text[last:])
    path.write_text("".join(out), encoding="utf-8", newline="\n")
    print("resolved", name)
sys.exit(0)
