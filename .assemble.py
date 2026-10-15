"""Builds the stacked commits from the WIP trees, with the fixes the full suite found applied to each.

Run from wk-model. It touches no working tree but its own scratch worktree and prints the commit
ids. Not part of the repository (untracked, deleted afterwards).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(".").resolve()
ASM = REPO.parent / "wk-model-asm"

HEAD = "HEAD"
WIP_A = "80135bb4"  # the document parts
WIP_C = "66c35f27"  # the embedding part and the worker (after its tests)
WIP_D = "9582cd23"  # how a passage was read
WIP_E = "db83aca6"  # the entity part
PR1_BASE = "d9f22be1"

#: Files whose HEAD version is the fix and which no later piece edits after it.
FIXED_BY_HEAD = [
    "src/brain/ops/guards.py",
    "tests/unit/test_guards.py",
    "migrations/versions/0250_model_server.py",
    "src/brain/knowledge/search.py",
]

#: Files the rename of `call` to `ask` reaches, where they exist in a tree.
RENAMED = [
    "src/brain/knowledge/model_server_parsers.py",
    "src/brain/knowledge/document_services.py",
    "src/brain/ops/model_server_client.py",
    "src/brain/ops/acceptance_checks_modelserver.py",
    "tests/unit/test_model_server_client.py",
    "tests/unit/test_model_server_parsers.py",
    "tests/unit/test_how_a_passage_was_read.py",
    "tests/unit/test_how_a_passage_was_read_db.py",
    "tests/unit/test_model_server_end_to_end.py",
    "tests/unit/test_document_services.py",
    "tests/unit/test_ingest_queue.py",
    "tests/unit/test_acceptance_modelserver_documents.py",
]


def git(*args: str, cwd: Path = REPO, input_: str | None = None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, input=input_, text=True, capture_output=True, check=False
    )
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr}")
    return done.stdout.strip()


def show(rev: str, path: str) -> str | None:
    done = subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=REPO, text=True, capture_output=True, check=False
    )
    return done.stdout if done.returncode == 0 else None


def rename(text: str) -> str:
    text = re.sub(r"def call\(self, part: (Part|object), request: object\)", r"def ask(self, part: \1, request: object)", text)
    text = text.replace(".server.call(", ".server.ask(")
    text = text.replace(").call(Part.", ").ask(Part.")
    text = text.replace("client.call(Part.", "client.ask(Part.")
    text = text.replace("Caller.call", "Caller.ask")
    return text


def build(tree_of: str, replace: dict[str, str | None], message: str, parent: str) -> str:
    """A commit whose tree is `tree_of`'s with `replace` applied, and the rename."""
    if ASM.exists():
        git("worktree", "remove", "--force", str(ASM))
    git("worktree", "add", "--detach", str(ASM), tree_of)
    for path in RENAMED:
        target = ASM / path
        if target.exists():
            target.write_text(rename(target.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    for path, content in replace.items():
        target = ASM / path
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
    # The roadmap is derived from the notes and is regenerated rather than merged.
    env = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ["PATH"]}
    subprocess.run(["node", "docs/wbs/export.js"], cwd=ASM, env=env, check=True, capture_output=True)
    subprocess.run(["node", "docs/wbs/render.js"], cwd=ASM, env=env, check=True, capture_output=True)
    git("add", "-A", cwd=ASM)
    tree = git("write-tree", cwd=ASM)
    commit = git("commit-tree", tree, "-p", parent, "-F", "-", input_=message)
    return commit


def message_of(path: str, table: str = "") -> str:
    body = Path(path).read_text(encoding="utf-8")
    first, _, rest = body.partition("\n")
    # The table sits before the trailer line, so the trailer stays the last line.
    marker = "\nCo-Authored-By:"
    head, trailer = rest.rsplit(marker, 1)
    return f"{first}\n{head.rstrip()}\n\n{table.rstrip()}\n\nCo-Authored-By:{trailer}"


def entity_section_removed(text: str) -> str:
    """The acceptance module as it stood before the entity part's check was added to it."""
    start = text.index("# ------------------------------------------------------------------------ the entity part")
    end = text.index("# ------------------------------------------------------------------------ how a passage was read")
    return text[:start] + text[end:]


def notes_without_entity(head_notes: str, then_notes: str) -> str:
    """HEAD's roadmap notes with the entity leaf's entry as `then_notes` had it."""
    def block(text: str) -> tuple[int, int]:
        begin = text.index('  "M32.2.1.2": {')
        return begin, text.index("  },", begin) + len("  },")

    a, b = block(head_notes)
    c, d = block(then_notes)
    return head_notes[:a] + then_notes[c:d] + head_notes[b:]


def main() -> None:
    parent = sys.argv[1]
    fixes = {path: show(HEAD, path) for path in FIXED_BY_HEAD}
    effects = show(HEAD, "src/brain/ops/effects.py")
    fixes_later = {**fixes, "src/brain/ops/effects.py": effects}

    # PR1: the frame's own fixes, on the merge of main.
    one = dict(fixes)
    one["tests/unit/test_parse_layout.py"] = show(WIP_A, "tests/unit/test_parse_layout.py")
    pr1 = build(PR1_BASE, one, Path(".msg_fix1.txt").read_text(encoding="utf-8"), parent)
    print("pr1", pr1)

    pr2 = build(WIP_A, fixes_later, message_of(".body2.txt", table_text("pr2")), pr1)
    print("pr2", pr2)
    pr3 = build(WIP_C, fixes_later, message_of(".body3.txt", table_text("pr3")), pr2)
    print("pr3", pr3)

    four = dict(fixes_later)
    for path in (
        "tests/unit/test_how_a_passage_was_read.py",
        "tests/unit/test_how_a_passage_was_read_db.py",
        "tests/unit/test_inference_server_documents.py",
        "docs/proof-sweep-holds.d/model-server-provenance.json",
    ):
        four[path] = show(HEAD, path)
    head_checks = show(HEAD, "src/brain/ops/acceptance_checks_modelserver.py")
    assert head_checks is not None
    four["src/brain/ops/acceptance_checks_modelserver.py"] = entity_section_removed(head_checks)
    head_notes = show(HEAD, "docs/wbs/progress.js")
    then_notes = show(WIP_D, "docs/wbs/progress.js")
    assert head_notes is not None and then_notes is not None
    four["docs/wbs/progress.js"] = notes_without_entity(head_notes, then_notes)
    pr4 = build(WIP_D, four, message_of(".body4.txt", table_text("pr4")), pr3)
    print("pr4", pr4)

    five = dict(fixes_later)
    pr5 = build(HEAD, five, message_of(".body5.txt", table_text("pr5")), pr4)
    print("pr5", pr5)


def table_text(which: str) -> str:
    return Path(f".table_{which}.txt").read_text(encoding="utf-8")


if __name__ == "__main__":
    main()
