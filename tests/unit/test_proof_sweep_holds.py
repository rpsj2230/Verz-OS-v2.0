"""The held list is extended by adding a file, so two pull requests adding a hold cannot conflict.

`docs/proof-sweep-holds.json` is one JSON object, and its last entry carries no comma, so appending
a hold edited the line above it too: two pull requests appending at the end conflicted every time,
and a conflicted pull request gets no CI. `holds_at` therefore also reads every `*.json` in the
directory beside the file, and these tests hold what that promises: the files are read in name
order, a leaf held twice is refused and not silently merged, and the real list still reads as it
did.

Task ids: M38.5.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.ops.proof_sweep import HOLDS_PATH, holds_at

REPO = Path(__file__).resolve().parents[2]


def _write(path: Path, held: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"held": held}), encoding="utf-8", newline="\n")


def test_a_hold_in_the_directory_beside_the_file_is_read_with_the_file(tmp_path: Path) -> None:
    """Delete this and a hold written the way the module tells a contributor to is never read,
    so its task is closed on a pass the check made up, which is what a hold exists to stop."""
    main = tmp_path / "holds.json"
    _write(main, {"M1.1.1": "the first reason, long enough"})
    _write(tmp_path / "holds.d" / "b.json", {"M3.3.3": "from the second file, long enough"})
    _write(tmp_path / "holds.d" / "a.json", {"M2.2.2": "from the first file, long enough"})

    held = holds_at(main)

    assert held == {
        "M1.1.1": "the first reason, long enough",
        "M2.2.2": "from the first file, long enough",
        "M3.3.3": "from the second file, long enough",
    }
    assert list(held) == ["M1.1.1", "M2.2.2", "M3.3.3"]


def test_a_file_with_no_directory_beside_it_reads_as_it_always_did(tmp_path: Path) -> None:
    """The positive sibling: a reader that required the directory would refuse every install and
    every older copy of the file. Delete this and the directory becomes mandatory."""
    main = tmp_path / "holds.json"
    _write(main, {"M1.1.1": "the only reason, long enough"})

    assert holds_at(main) == {"M1.1.1": "the only reason, long enough"}


def test_a_leaf_held_in_two_places_is_refused_and_names_both(tmp_path: Path) -> None:
    """Two reasons cannot both be the reason. Delete this and the later file wins silently, so a
    reason somebody wrote is replaced by one nobody was shown it replaced."""
    main = tmp_path / "holds.json"
    _write(main, {"M1.1.1": "the first reason, long enough"})
    _write(tmp_path / "holds.d" / "again.json", {"M1.1.1": "a second reason, long enough"})

    with pytest.raises(
        ValueError, match=r"M1\.1\.1 is held in both .*holds\.json and .*again\.json"
    ):
        holds_at(main)


def test_the_real_list_still_reads_and_its_directory_is_the_one_the_module_names() -> None:
    """The file the sweep reads on a real install, through the same function. Delete this and a
    change to the reader that mangled the real path passes every test above, which use a copy."""
    held = holds_at(REPO / HOLDS_PATH)

    assert held
    assert (REPO / HOLDS_PATH).with_suffix(".d").name == "proof-sweep-holds.d"
