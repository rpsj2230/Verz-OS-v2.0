"""Progress computed from git history, and the pages that serve it.

Task ids: M38.3.1.1, M38.3.1.3, M38.3.1.4,
M38.3.2.1, M38.3.2.2, M38.3.2.3, M38.3.2.4, M38.3.2.5

M38.3.1.2 is tested at the end: the status file is committed to the `status` branch rather than
to main, because a commit to main would store a derived value in the tree it is derived from and
start CI and Deploy again for every merge. M38.2.1.6 and M38.2.1.1 are tested through
/build/waves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import docs_routes, status
from brain.app import Settings, create_app

WBS = {
    "wave_names": {"0": "Foundation", "1": "The gate"},
    "modules": [
        {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.1.2", "M0.2.1"]},
        {"id": "M1", "name": "Identity", "wave": 1, "leaf_ids": ["M1.1.1", "M1.1.2"]},
    ],
}


def git(cwd: Path, *args: str) -> None:
    """The status generator's only input is git history, so the tests build real repos."""
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


#: The proof trailer a fixture commit carries when the test is about something other than proof.
#:
#: **Without it every fixture here is a clock.** These commits are made at the moment the test
#: runs, and from `status.PROOF_REQUIRED_FROM` a claim without proof counts for nothing, so on
#: that date every test built on a claim would go red with nothing about the code having changed.
#: The tests about the proof rule itself pin their commit dates instead, either side of it.
PROVED = "Proved-in-ci: unit"

#: Either side of `status.PROOF_REQUIRED_FROM`, written out rather than derived from it, so a
#: moved start fails the tests about the start instead of moving them with it.
BEFORE_PROOF = "2026-09-17T23:59:59+00:00"
AT_PROOF = "2026-09-18T00:00:00+00:00"


def git_at(cwd: Path, when: str, *args: str) -> None:
    """`git` with both of a commit's dates pinned, for a test about when a claim was made.

    Both, because `%ct` is the committer date and `--date` sets only the author's.
    """
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
        env={**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f.txt").write_text("1")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", f"M0.1.1: first thing\n\n{PROVED}\n")
    (tmp_path / "f.txt").write_text("2")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", f"second thing\n\nCloses: M0.1.2 M1.1.1\n{PROVED}\n")
    return tmp_path


# ------------------------------------------------------------- extraction
def test_ids_are_read_from_subject_and_body(repo: Path) -> None:
    """A commit closing eight leaves lists them on a Closes: trailer rather than cramming
    them into a 72-character subject, so both places are read."""
    found, _ = status.closed_task_ids(repo)
    assert found == {"M0.1.1", "M0.1.2", "M1.1.1"}


def test_recent_commits_are_recorded_newest_first(repo: Path) -> None:
    _, recent = status.closed_task_ids(repo)
    assert recent[0]["subject"] == "second thing"
    assert "M1.1.1" in recent[0]["closed"]


def test_a_commit_naming_no_task_is_not_listed(repo: Path) -> None:
    git(repo, "commit", "--allow-empty", "-m", "tidy up")
    _, recent = status.closed_task_ids(repo)
    assert all(r["subject"] != "tidy up" for r in recent)


def test_a_directory_that_is_not_a_repo_yields_nothing(tmp_path: Path) -> None:
    """No history must mean zero progress, never a crash and never a wrong number."""
    found, recent = status.closed_task_ids(tmp_path)
    assert found == set()
    assert recent == []


# ---------------------------------------------------------------- rollup
def test_progress_counts_only_what_commits_closed(repo: Path) -> None:
    s = status.build_status(repo, WBS)
    assert s.total == 5
    assert s.done == 3
    assert s.percent == 60.0


#: The fixture plan with one leaf of M1 flagged as an act, as `docs/wbs/acts.js` would.
WBS_WITH_AN_ACT = {
    "wave_names": {"0": "Foundation", "1": "The gate"},
    "modules": [
        {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.1.2", "M0.2.1"]},
        {
            "id": "M1",
            "name": "Identity",
            "wave": 1,
            "leaf_ids": ["M1.1.1", "M1.1.2"],
            "leaf_acts": {"M1.1.2": {"kind": "ACT", "gate": False}},
        },
    ],
}


def test_an_act_is_left_out_of_the_percentage_and_counted_beside_it(repo: Path) -> None:
    """An act is work a person does on the week of a migration, and no commit can close it.
    In the denominator it holds the figure short of 100 for ever, which the owner read as a
    stalled build. Delete this and the act can slide back into `total`, and the headline on
    /build and /build/tracker drops back below what was actually built."""
    s = status.build_status(repo, WBS_WITH_AN_ACT)

    assert s.total == 4
    assert s.done == 3
    assert s.percent == 75.0
    assert s.acts == 1
    wave_one = next(w for w in s.waves if w.wave == 1)
    assert (wave_one.done, wave_one.total, wave_one.acts) == (1, 1, 1)
    module_one = next(m for m in s.modules if m.module == "M1")
    assert (module_one.done, module_one.total, module_one.acts) == (1, 1, 1)


def test_a_buildable_leaf_still_counts_when_its_module_carries_an_act(repo: Path) -> None:
    """The positive sibling. A flag that removed its whole module from the count, or every
    leaf of its wave, would pass the test above and understate real work. Delete this and
    that version is indistinguishable from the right one."""
    s = status.build_status(repo, WBS_WITH_AN_ACT)

    assert "M1.1.1" in s.done_task_ids
    module_one = next(m for m in s.modules if m.module == "M1")
    assert module_one.done == 1
    wave_zero = next(w for w in s.waves if w.wave == 0)
    assert (wave_zero.done, wave_zero.total, wave_zero.acts) == (2, 3, 0)


#: The fixture plan with two acts and one leaf decided against, all in M1, as `export.js`
#: writes. Two acts and one decision rather than one of each, so a wave or a module that
#: reported one count under the other's name reads a different number and is caught.
WBS_WITH_A_DECIDED_LEAF: dict[str, Any] = {
    "wave_names": {"0": "Foundation", "1": "The gate"},
    "modules": [
        {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.1.2", "M0.2.1"]},
        {
            "id": "M1",
            "name": "Identity",
            "wave": 1,
            "leaf_ids": ["M1.1.1", "M1.1.2", "M1.1.3", "M1.1.4"],
            "leaf_acts": {
                "M1.1.2": {"kind": "ACT", "gate": False},
                "M1.1.4": {"kind": "ACT", "gate": False},
            },
            "leaf_decided": {"M1.1.3": {"kind": "DECIDED", "why": "item 58"}},
        },
    ],
}


def test_a_decided_leaf_is_left_out_of_the_percentage_per_wave_and_per_module(repo: Path) -> None:
    """Item 58 recorded nine plugin interfaces as decided, not needed as written. Counted in the
    denominator they hold the figure down with work nobody will do. Delete this and a decided
    leaf can slide back into `total`, overall or in its wave or its module, and the headline
    understates what was built by exactly the work that was decided against."""
    s = status.build_status(repo, WBS_WITH_A_DECIDED_LEAF)

    assert (s.done, s.total, s.percent) == (3, 4, 75.0)
    assert s.decided == 1
    wave_one = next(w for w in s.waves if w.wave == 1)
    assert (wave_one.done, wave_one.total, wave_one.decided) == (1, 1, 1)
    module_one = next(m for m in s.modules if m.module == "M1")
    assert (module_one.done, module_one.total, module_one.decided) == (1, 1, 1)


def test_a_decided_leaf_is_not_counted_as_a_client_task(repo: Path) -> None:
    """A decided leaf is nobody's work on any week, and the act count is read as client tasks
    on the week of a migration. Delete this and the reader can fold decided leaves into `acts`,
    which keeps the percentage right and tells the owner there are forty-eight things to do
    with a client when there are thirty-nine."""
    s = status.build_status(repo, WBS_WITH_A_DECIDED_LEAF)

    assert (s.acts, s.decided) == (2, 1)
    wave_one = next(w for w in s.waves if w.wave == 1)
    assert (wave_one.acts, wave_one.decided) == (2, 1)
    module_one = next(m for m in s.modules if m.module == "M1")
    assert (module_one.acts, module_one.decided) == (2, 1)


def test_a_buildable_leaf_still_counts_beside_a_decided_one(repo: Path) -> None:
    """The positive sibling. A decision that took its whole module, or its wave, out of the
    count would pass both tests above. Delete this and that version is indistinguishable from
    the right one."""
    s = status.build_status(repo, WBS_WITH_A_DECIDED_LEAF)

    assert "M1.1.1" in s.done_task_ids
    wave_zero = next(w for w in s.waves if w.wave == 0)
    assert (wave_zero.done, wave_zero.total, wave_zero.acts, wave_zero.decided) == (2, 3, 0, 0)
    assert s.total + s.acts + s.decided == sum(
        len(m["leaf_ids"]) for m in WBS_WITH_A_DECIDED_LEAF["modules"]
    )


def test_a_decided_leaf_is_never_named_as_the_next_thing_to_build(repo: Path) -> None:
    """Next up answers what a commit should close next, and nobody should close a leaf that was
    decided against. Built so the decided leaf is reachable: wave 0 is all closed, so wave 1 is
    current, and the decided leaf sits before an open buildable one. Delete this and a decided
    plugin interface can sit at the top of that list for ever."""
    plan = {
        "wave_names": WBS["wave_names"],
        "modules": [
            {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.1.2"]},
            {
                "id": "M1",
                "name": "Identity",
                "wave": 1,
                "leaf_ids": ["M1.1.1", "M1.1.2", "M1.1.3"],
                "leaf_decided": {"M1.1.2": {"kind": "DECIDED", "why": "item 58"}},
            },
        ],
    }

    s = status.build_status(repo, plan)

    assert s.current_wave == 1
    assert s.next_up == ["M1.1.3"]


def test_a_leaf_flagged_both_as_an_act_and_as_decided_is_refused() -> None:
    """The checklist reads the acts and this page reads both, so a leaf in both is a person
    sent to do work the page says was decided against. `export.js` writes each flag to one
    field; this is the hand-edited or stale `wbs.json` it cannot see. Delete this and such a
    leaf is silently counted as decided while the checklist lists it."""
    module = {
        "id": "M1",
        "leaf_acts": {"M1.1.2": {"kind": "ACT", "gate": False}},
        "leaf_decided": {"M1.1.2": {"kind": "DECIDED", "why": "item 58"}},
    }

    with pytest.raises(ValueError, match="both as an act and as decided"):
        status.decided_of(module)


def test_a_module_whose_act_and_decision_name_different_leaves_is_read(repo: Path) -> None:
    """The positive sibling of the refusal above. Delete this and `decided_of` can refuse every
    module that carries both fields, which the refusal test cannot tell apart from the rule."""
    module = WBS_WITH_A_DECIDED_LEAF["modules"][1]

    assert set(status.decided_of(module)) == {"M1.1.3"}


def test_the_decided_leaves_are_the_register_points_that_are_not_plugins() -> None:
    """Item 58 Option B records the extension-point register's answer as the decision: every
    M29.1 point the register does not answer PLUGIN is decided, not needed as written. Compared
    against `brain.plugins.points` rather than against a list here, so a point the register
    later answers PLUGIN reopens its leaf as buildable, and a flag with no register answer
    behind it is red. Delete this and the two drift, and the tracker reports a decision the
    register no longer makes."""
    from brain.plugins.points import POINTS, Answer

    repo = Path(__file__).resolve().parents[2]
    wbs = status.load_wbs(repo / "docs" / "wbs.json")
    decided = {leaf: flag for m in wbs["modules"] for leaf, flag in status.decided_of(m).items()}

    register = {leaf: flag for leaf, flag in decided.items() if "item 58" in flag["why"]}
    assert set(register) == {one.leaf for one in POINTS if one.answer is not Answer.PLUGIN}
    assert all(flag["kind"] == "DECIDED" for flag in decided.values())

    # The only other decision is a duplicate merged on the owner's approval of 2026-09-17, and
    # it names the leaf that carries the work, which must exist and must not be retired too.
    leaves = {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}
    for leaf, flag in decided.items():
        if leaf in register:
            continue
        # Or the owner decided it on the Needs you page, and the item it names is there.
        owner = re.match(r"owner \d{4}-\d{2}-\d{2}, item (\d+):", flag["why"])
        if owner:
            needs = (repo / "docs" / "needs-rupash.md").read_text(encoding="utf-8")
            assert f"\n## {owner.group(1)}. " in needs, (leaf, flag["why"])
            continue
        merged = re.match(r"Merged into (M\d+(?:\.\d+)+),", flag["why"])
        assert merged, f"{leaf} is decided for a reason that is not item 58, a merge or the owner"
        assert merged.group(1) in leaves and merged.group(1) not in decided, (leaf, flag["why"])


def test_an_act_is_never_named_as_the_next_thing_to_build(repo: Path) -> None:
    """Next up answers what a commit should close next, and a commit cannot close an act.
    Delete this and an act can sit at the top of that list for ever, the same stall the
    percentage had, in a different place.

    The plan is built so the act is reachable: wave 0 holds only closed leaves, so wave 1 is
    current, and the act sits before an open buildable leaf in plan order. The first version
    used the shared fixture, whose current wave was 0, so an act in wave 1 was never a
    candidate and the test passed with the rule deleted; a mutation found that."""
    plan = {
        "wave_names": WBS["wave_names"],
        "modules": [
            {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.1.2"]},
            {
                "id": "M1",
                "name": "Identity",
                "wave": 1,
                "leaf_ids": ["M1.1.1", "M1.1.2", "M1.1.3"],
                "leaf_acts": {"M1.1.2": {"kind": "ACT", "gate": False}},
            },
        ],
    }

    s = status.build_status(repo, plan)

    assert s.current_wave == 1
    assert s.next_up == ["M1.1.3"]
    assert s.acts == 1


def test_an_act_a_commit_names_is_ticked_and_still_left_out_of_the_percentage(
    repo: Path,
) -> None:
    """A commit can name an act, and the tracker ticks every leaf in `done_task_ids`. Leaving
    an act out of that list would show a leaf somebody recorded as closed as still open, and
    counting it in `done` would put a leaf back in the figure that the denominator left out,
    so the percentage could pass 100. Delete this and either half can break unseen, because
    no commit in this repository has closed an act yet."""
    git(repo, "commit", "--allow-empty", "-m", f"announced\n\nCloses: M1.1.2\n{PROVED}")

    s = status.build_status(repo, WBS_WITH_AN_ACT)

    assert "M1.1.2" in s.done_task_ids
    assert (s.done, s.total) == (3, 4)
    assert s.percent <= 100.0


def test_a_parent_id_closes_nothing(repo: Path) -> None:
    """Changed 2026-09-04 after finding the number inflated.

    An ancestor id used to close every leaf beneath it, which is what an honest commit
    for a large piece of work looks like - and exactly why it was dangerous. A commit
    saying M0.6 closed connector cassettes that were never written. Nothing warned.
    """
    git(repo, "commit", "--allow-empty", "-m", f"M0.2: the whole subtree\n\n{PROVED}")
    s = status.build_status(repo, WBS)
    assert "M0.2.1" not in s.done_task_ids


def test_a_leaf_id_does_not_close_a_sibling(repo: Path) -> None:
    s = status.build_status(repo, WBS)
    assert "M1.1.2" not in s.done_task_ids


def test_waves_roll_up_separately(repo: Path) -> None:
    s = status.build_status(repo, WBS)
    by_wave = {w.wave: w for w in s.waves}
    assert (by_wave[0].done, by_wave[0].total) == (2, 3)
    assert (by_wave[1].done, by_wave[1].total) == (1, 2)


def test_closed_today_counts_the_days_work(repo: Path) -> None:
    """M38.3.1.4. Both commits in the fixture are made now, so all three of their leaves
    are today's. Deleting this leaves the number free to be anything: it is displayed
    prominently and checked by nobody, which is the worst combination for a figure a person
    reads to decide whether to ask what happened."""
    assert status.build_status(repo, WBS).closed_today == 3


def test_a_commit_from_before_today_is_not_counted(repo: Path) -> None:
    """The boundary, and it has to be real rather than assumed. Without this the count is
    "every leaf ever closed" on a repository whose history is short, which is exactly the
    situation now and exactly when nobody would notice."""
    # Dated at commit time rather than amended afterwards. `--since` reads the *committer*
    # date, and `--date` sets only the author date, so an amend that looks like it moved the
    # commit leaves the filter reading the original moment.
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "old work\n\nCloses: M0.2.1"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_COMMITTER_DATE": "2026-09-01T09:00:00+00:00",
            "GIT_AUTHOR_DATE": "2026-09-01T09:00:00+00:00",
        },
    )
    s = status.build_status(repo, WBS)
    # Counted as done, because it is. Not counted as today's, because it is not.
    assert "M0.2.1" in s.done_task_ids
    assert s.closed_today == 3


def test_next_up_names_unclosed_leaves_in_the_current_wave(repo: Path) -> None:
    """M38.3.1.4. In plan order, not id order: the WBS lists leaves in the sequence they
    are meant to be done, and re-sorting answers a different question."""
    s = status.build_status(repo, WBS)
    assert s.next_up
    assert all(leaf not in s.done_task_ids for leaf in s.next_up)


def test_next_up_is_empty_when_the_current_wave_is_finished(repo: Path) -> None:
    """Otherwise the page suggests work in a wave that has none left, which reads as the
    plan being wrong rather than the page being wrong."""
    git(repo, "commit", "--allow-empty", "-m", f"rest of wave 0\n\nCloses: M0.2.1\n{PROVED}")
    s = status.build_status(repo, WBS)
    assert s.current_wave == 1
    assert all(leaf.startswith("M1") for leaf in s.next_up), s.next_up


def test_current_wave_is_the_first_unfinished_one(repo: Path) -> None:
    assert status.build_status(repo, WBS).current_wave == 0


def test_current_wave_is_none_when_everything_is_done(repo: Path) -> None:
    """None means finished. Reporting a current wave forever would be a quiet lie.

    Note the ids: a bare `M0` is a module, not a task, and deliberately closes nothing.
    """
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        f"M0.1.1 M0.1.2 M0.2.1 M1.1.1 M1.1.2 everything\n\n{PROVED}",
    )
    s = status.build_status(repo, WBS)
    assert s.done == s.total
    assert s.current_wave is None


def test_leaf_ids_are_derived_the_way_the_renderer_numbers_them(tmp_path: Path) -> None:
    """If these drifted, a commit closing M0.2.4 would tick a different box in the
    tracker than the one the status page counts."""
    wbs = {
        "modules": [
            {
                "id": "M0",
                "name": "x",
                "wave": 0,
                "tasks": [{"n": "group", "s": [{"n": "sub", "k": ["a", "b"]}, "leaf"]}],
            }
        ]
    }
    p = tmp_path / "wbs.json"
    p.write_text(json.dumps(wbs), encoding="utf-8")
    assert status.load_wbs(p)["modules"][0]["leaf_ids"] == ["M0.1.1.1", "M0.1.1.2", "M0.1.2"]


# ------------------------------------------------------------- regression
def test_a_one_line_commit_message_is_counted(repo: Path) -> None:
    r"""Regression, found by test_ids_are_read_from_subject_and_body on 2026-09-04.

    Python counts \x1c through \x1f as whitespace, so `entry.strip()` ate the trailing
    unit separator. A commit with an empty body - every one-line message, and so most
    commits - then split into three fields instead of four and was dropped with no error
    anywhere. Progress simply read low.

    Dated before `status.PROOF_REQUIRED_FROM`, and fixed there. A one-line message has no body,
    so it can carry no proof, and from that instant its claim would count for nothing whether
    or not the parse were right. Made at the moment the test runs, this would stop testing the
    parse the day the rule started.
    """
    git_at(repo, BEFORE_PROOF, "commit", "--allow-empty", "-m", "M1.1.2: one line, no body")
    found, recent = status.closed_task_ids(repo)
    assert "M1.1.2" in found
    assert recent[0]["subject"] == "M1.1.2: one line, no body"


def test_a_body_containing_the_separator_does_not_split_the_record(repo: Path) -> None:
    """maxsplit=3 keeps the body whole, so pasted output cannot corrupt the parse."""
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        f"M0.2.1: x\n\nlog said a\x1fb\n\nCloses: M1.1.2\n{PROVED}\n",
    )
    found, _ = status.closed_task_ids(repo)
    assert {"M0.2.1", "M1.1.2"} <= found


# ----------------------------------------------------------------- routes
@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(
        json.dumps(
            {
                "commit": "abc1234",
                "total": 100,
                "done": 25,
                "percent": 25.0,
                "acts": 39,
                "decided": 9,
                "current_wave": 1,
                "waves": [
                    {"wave": 1, "name": "The gate", "total": 100, "done": 25, "percent": 25.0}
                ],
                "modules": [],
                "done_task_ids": ["M0.1.1"],
                "closed_today": 3,
                "next_up": ["M1.2.3", "M1.2.4"],
                "recent": [
                    {"sha": "abc1234", "subject": "M0.1.1: a thing", "closed": "M0.1.1", "at": ""}
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "tracker.html").write_text("<h1>tracker</h1>", encoding="utf-8")
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    app: FastAPI = create_app(Settings(env="production"))
    with TestClient(app) as c:
        yield c


def test_status_endpoint_serves_the_baked_file(client: TestClient) -> None:
    body = client.get("/api/status.json").json()
    assert body["percent"] == 25.0
    assert body["done_task_ids"] == ["M0.1.1"]


def test_status_is_never_cached(client: TestClient) -> None:
    """A cached status page is a page that can show yesterday's progress."""
    assert client.get("/api/status.json").headers["cache-control"] == "no-store"


def test_index_shows_the_percentage_and_the_commit(client: TestClient) -> None:
    text = client.get("/build").text
    assert "25.0%" in text
    assert "abc1234" in text
    assert "The gate" in text


def test_the_page_says_how_many_client_tasks_the_percentage_leaves_out(
    client: TestClient,
) -> None:
    """The percentage counts buildable leaves only, and a figure that silently drops 39
    leaves reads as a number somebody massaged. So the page states what it left out, next to
    the figure. Delete this and the line can disappear while the percentage stays buildable,
    which is the version of this page nobody should trust."""
    text = client.get("/build").text

    assert "25 of 100 buildable tasks" in text
    assert "39 client tasks on the week of a migration, not counted" in text


def test_the_page_reports_decided_leaves_as_their_own_count_and_not_as_client_tasks(
    client: TestClient,
) -> None:
    """Item 58 recorded nine plugin interfaces as decided, not needed as written. They are not
    client tasks on the week of a migration, so the page states them on their own line with
    their own label while the client task line keeps its own number. Delete this and the line
    can vanish, or the nine can be folded into the client tasks, and either way the page says
    something about the plan that was not decided."""
    text = client.get("/build").text

    assert "9 decided, not needed as written" in text
    assert "39 client tasks on the week of a migration, not counted" in text
    assert "48 client tasks" not in text


def test_the_page_says_how_much_closed_today(client: TestClient) -> None:
    """M38.3.2.3. The number a person actually wants when they open this: not the total,
    which barely moves, but whether anything happened since they last looked."""
    assert "3 closed today" in client.get("/build").text


def test_a_day_with_nothing_closed_says_so_rather_than_showing_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero is a real answer and is the one worth showing. A page that only ever displays
    movement cannot display a stall, and hiding the line on a quiet day means a stalled
    project looks identical to a project nobody has checked."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(
        json.dumps(
            {
                "commit": "abc1234",
                "total": 100,
                "done": 25,
                "percent": 25.0,
                "current_wave": 1,
                "waves": [
                    {"wave": 1, "name": "The gate", "total": 100, "done": 25, "percent": 25.0}
                ],
                "closed_today": 0,
                "next_up": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    with TestClient(create_app(Settings(env="production"))) as c:
        text = c.get("/build").text
    assert "nothing closed today yet" in text
    assert "this wave is finished" in text


def test_the_page_says_what_is_next(client: TestClient) -> None:
    """M38.3.2.3. "What is next" without anybody opening the tracker and reading down it.
    In plan order rather than id order, because the WBS lists leaves in the sequence they
    are meant to be done and `M12.1.10` sorts before `M12.1.2` as a string."""
    text = client.get("/build").text
    assert "Next up" in text
    assert "M1.2.3" in text
    assert text.index("M1.2.3") < text.index("M1.2.4")


def test_the_page_names_the_commit_it_was_built_from(client: TestClient) -> None:
    """M38.3.2.4, and the half that always worked. A status page that cannot say which
    version produced it is a page nobody can check against the running system."""
    assert "abc1234" in client.get("/build").text


def test_the_page_is_reachable_without_signing_in(client: TestClient) -> None:
    """M38.3.2.5. The whole point: progress needs no meeting, which means it needs no
    account either. Built with `env="production"`, where the interactive API docs are off,
    so this asserts the build pages are deliberately exempt rather than accidentally open."""
    for path in ("/build", "/build/tracker", "/api/status.json"):
        assert client.get(path).status_code == 200, path
    assert client.get("/docs").status_code == 404


def test_the_status_file_is_never_written_by_hand(client: TestClient) -> None:
    """M38.3.1.3. There is no endpoint, flag or environment variable that marks a task
    done. The only way a leaf becomes closed is a commit on main naming it, which means the
    page cannot show progress that does not exist.

    Asserted structurally over the module rather than by trying every URL: a route that
    accepted a task id would have to exist as a function, and this is the check that fails
    when somebody adds one for convenience during a demo."""
    import inspect

    source = inspect.getsource(docs_routes)
    for verb in ("@router.post", "@router.put", "@router.patch", "@router.delete"):
        assert verb not in source, f"{verb} on the build pages: progress could be set by hand"


def test_tracker_is_served(client: TestClient) -> None:
    assert client.get("/build/tracker").status_code == 200


def test_a_missing_document_is_a_404_not_a_crash(client: TestClient) -> None:
    """Architecture is not in this fixture. A missing doc must not take the app down."""
    assert client.get("/build/architecture").status_code == 404


def test_docs_pages_are_reachable_in_production(client: TestClient) -> None:
    """Unlike /docs these carry no company data and stay on in production - the whole
    point is that progress is visible without asking anyone."""
    assert client.get("/build").status_code == 200
    assert client.get("/api/status.json").status_code == 200


# ------------------------------------------------------------- regression
def test_body_prose_does_not_claim_anything(repo: Path) -> None:
    """Regression, found by reading my own status page on 2026-09-04.

    A commit body listed ten ids under "Deliberately NOT claimed" and the parser counted
    all ten. It has no concept of negation and cannot be given one: "not M0.6.5",
    "M0.6.5 is not done" and "blocked: M0.6.5" are identical to a scanner, and the
    failure is silent and in the direction that flatters.

    The rule is now positional, not semantic.
    """
    # Proved, so the only reason left for these ids not to count is that they are prose.
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        f"tidy up\n\nStill outstanding: M1.1.2 and M0.2.1.\n\n{PROVED}",
    )
    found, _ = status.closed_task_ids(repo)
    assert "M1.1.2" not in found
    assert "M0.2.1" not in found


def test_a_closes_trailer_claims(repo: Path) -> None:
    git(repo, "commit", "--allow-empty", "-m", f"some work\n\nCloses: M1.1.2, M0.2.1\n{PROVED}\n")
    found, _ = status.closed_task_ids(repo)
    assert {"M1.1.2", "M0.2.1"} <= found


def test_the_subject_still_claims(repo: Path) -> None:
    """The common case stays as it was: one id, in the subject, where it is visible in
    every log listing."""
    git(repo, "commit", "--allow-empty", "-m", f"M1.1.2: a thing\n\n{PROVED}")
    found, _ = status.closed_task_ids(repo)
    assert "M1.1.2" in found


def test_claimed_ids_reads_subject_and_trailer_only() -> None:
    ids = status.claimed_ids(
        "M0.1.1: subject",
        "Body mentions M9.9.9 in prose.\n\nCloses: M0.1.2 M0.1.3\n",
    )
    assert ids == {"M0.1.1", "M0.1.2", "M0.1.3"}


# ------------------------------------- the open count is the open count (M38.3.2.3)
def test_the_needs_count_stops_at_the_answered_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It used to count every `## ` heading in the file, so the badge on the status page was
    the number of items ever *raised*: it read twenty-two while two were actually open, and
    it could only ever go up.

    A count that never falls is a count nobody acts on, because answering something does not
    change it. Deleting this test lets the badge drift back into being a running total, which
    looks identical to a working one until you notice it has never gone down."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "needs-rupash.md").write_text(
        "# Needs Rupash\n\n# Open\n\n## 24. still open\n\n## 25. also open\n\n"
        "# Answered\n\n## 23. decided\n\n## 22. decided\n\n## 21. decided\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    assert docs_routes._needs_count() == 2


def test_a_document_with_nothing_answered_yet_counts_everything() -> None:
    """The boundary in the other direction. Before anything is decided there is no
    `# Answered` heading, and every item is open - so a reader that broke on a missing
    heading would report zero, which is the most reassuring wrong answer available."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp)
        (docs / "needs-rupash.md").write_text(
            "# Needs Rupash\n\n# Open\n\n## 1. a\n\n## 2. b\n", encoding="utf-8"
        )
        original = docs_routes.DOCS
        docs_routes.DOCS = docs
        try:
            assert docs_routes._needs_count() == 2
        finally:
            docs_routes.DOCS = original


def test_the_real_document_reports_what_its_own_first_paragraph_says() -> None:
    """The badge and the sentence at the top of the page are the same fact asked twice, and
    they are written in different places. This is what stops them disagreeing - which they
    did, for as long as the count was a running total."""
    import re

    from brain.docs_routes import DOCS, NEEDS_FILE, _needs_count

    text = (DOCS / NEEDS_FILE).read_text(encoding="utf-8")
    # Singular as well as plural. The pattern was `(\d+) items are open`, which quietly
    # required the document to be ungrammatical the day exactly one item was left, and that
    # day arrived: the sentence read "1 item is open" and the test reported that the
    # document no longer stated a count at all. A guard that fails on the correct wording
    # teaches whoever meets it to edit the prose to suit the regex.
    # And the zero case, which arrived on 2026-09-06 when the last four were answered in one
    # message. The pattern required a digit, so "Nothing is open" read to it as a document
    # that states no count at all, and the only way to satisfy it was to write "**0 items are
    # open**", which nobody would write. That is the same failure the paragraph above records
    # for the singular, arriving from the other end of the range: a guard that rejects the
    # natural wording is a guard that gets satisfied by making the prose worse.
    counted = _needs_count()
    numeric = re.search(r"\*\*(\d+) items? (?:are|is) open", text)
    none_left = re.search(r"\*\*Nothing is open", text)

    assert numeric or none_left, "the document no longer states how many items are open"
    if numeric:
        assert int(numeric.group(1)) == counted
        assert counted > 0, "the document states a count while nothing is open"
    else:
        assert counted == 0, (
            f"the document says nothing is open and {counted} item(s) are still under "
            f"the Open heading"
        )


# ------------------------------- the two pages that show progress must agree
#
# `/build` reads `docs/status.json`, written by `brain.status`. `/build/tracker` is
# `docs/tracker.html`, written by `docs/wbs/render.js`. Two programs, two languages, one
# WBS, and both shown to the client on the same site.


def _tracker_leaves_per_wave() -> dict[int, int]:
    """Every leaf checkbox in the tracker, counted by the wave the page assigns it."""
    import collections
    import re

    html = (Path(__file__).resolve().parents[2] / "docs" / "tracker.html").read_text(
        encoding="utf-8"
    )
    # Buildable leaves only: an act's checkbox carries data-act and is counted beside the
    # figure, never in it, on both pages.
    boxes = re.findall(r'<input type="checkbox" class="cb"[^>]*>', html)
    found = [
        re.search(r'data-wave="(\d+)"', box)
        for box in boxes
        if "data-act=" not in box and "data-decided=" not in box
    ]
    counted = collections.Counter(int(w.group(1)) for w in found if w is not None)
    return dict(counted)


def _wbs_leaves_per_wave() -> dict[int, int]:
    """The partition the WBS itself declares: a leaf's own wave, else its module's.

    Derived from the source rather than read from `docs/status.json`, which is generated at
    build time and not committed - the first version of this test read that file, passed on
    my machine and failed in CI with `FileNotFoundError`, which is the whole reason a test
    should compare against the source and not against another derived artefact.

    It is also the stronger comparison. `status.json` is one program's output; the WBS is
    what both programs claim to be reading.
    """
    import collections

    wbs = status.load_wbs(Path(__file__).resolve().parents[2] / "docs" / "wbs.json")
    counted: collections.Counter[int] = collections.Counter()
    for module in wbs["modules"]:
        module_wave = int(module.get("wave", 0))
        leaf_waves = module.get("leaf_waves", {})
        flags = module.get("leaf_acts", {})
        decided = module.get("leaf_decided", {})
        for leaf in module["leaf_ids"]:
            if leaf in flags or leaf in decided:
                continue
            counted[int(leaf_waves.get(leaf, module_wave))] += 1
    return dict(counted)


def test_the_tracker_and_the_status_page_put_each_leaf_in_the_same_wave() -> None:
    """The bug this exists for was visible on the live site and the owner found it, not a
    test: `/build` said wave 0 was 110/112 and `/build/tracker` said 110/129, from one WBS.

    The tracker bucketed each leaf by its *module's* wave. A leaf can sit later than its
    module - M38's delivery pipeline is wave 0, and "what is live after wave 3" cannot be
    done before wave 3 - so seventeen leaves nobody could start sat in wave 0's denominator,
    and wave 0 could never reach 100%. `render.js` already had `waveOfLeaf` for exactly this
    and used it for the schedule sizing, just not for the rollup shown to a reader.

    Compared per wave rather than on the totals, because two different partitions of 1150
    leaves sum to 1150 either way. Delete this and the two pages drift again, silently, and
    the person who notices is the client."""
    assert _tracker_leaves_per_wave() == _wbs_leaves_per_wave()


#: The record and line separators, written as code points so this file stays readable.
SEPARATOR = chr(30)
NEWLINE = chr(10)


def tmp_repo() -> Path:
    """A throwaway git repository under the system temporary directory.

    A directory of its own rather than `tmp_path`, because this file's tests are plain
    functions and adding a fixture parameter to one of them would be the only one.
    """
    import tempfile

    return Path(tempfile.mkdtemp(prefix="brain-status-"))


def _empty_repo() -> Path:
    """A git repository with no commits in it, which is what an installer leaves behind."""
    import subprocess

    repo = tmp_repo()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=30)
    return repo


def test_a_repository_with_no_commits_reports_nothing_closed_rather_than_raising() -> None:
    """**The first thing this reads is `git log`, and a fresh repository has none.**

    Not hypothetical: the installer creates the client's repository before anything is
    committed to it, and the same path answers a machine with no git, because `_git` returns
    the empty string for both.

    There is no guard for it and there was one until a mutation showed it changed nothing: an
    empty string splits into one empty entry, the field count skips it, and the loop falls out
    to the same empty pair. This asserts the property rather than the guard, which is what the
    repository does everywhere it has removed a branch that could not fire.

    Delete this and the behaviour on a fresh install is nobody's claim."""
    closed, recent = status.closed_task_ids(_empty_repo())

    assert closed == set()
    assert recent == []


def test_a_record_separator_inside_a_commit_message_does_not_break_the_reader() -> None:
    """A commit whose message contains the record separator splits into two entries, and the
    second holds no field separators at all.

    Both readers guard against it and both guards are here: `closed_task_ids` needs three
    fields and `closed_since` needs two, and neither can assume the log it parses was written
    only by git's format string. A message can hold any byte somebody types.

    Delete this and one strange commit message turns the whole log into fields that are read
    off by one, silently, and the tracker under-counts with nothing to say so.
    """
    import subprocess
    from datetime import UTC, datetime, timedelta

    repo = tmp_repo()
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.invalid"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(command, cwd=repo, check=True, timeout=30)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=30)
    (repo / "msg.txt").write_text(
        f"M0.1.1 done\n\nCloses: M0.1.1\n{PROVED}\n\nand then \x1e a separator\n", encoding="utf-8"
    )
    subprocess.run(["git", "commit", "-q", "-F", "msg.txt"], cwd=repo, check=True, timeout=30)

    closed, _ = status.closed_task_ids(repo)
    since = status.closed_since(repo, datetime.now(UTC) - timedelta(days=1))

    assert "M0.1.1" in closed
    assert "M0.1.1" in since


def test_a_message_holding_a_bare_number_between_two_separators_is_skipped() -> None:
    """**The one entry the timestamp parser cannot refuse for us.**

    A commit message containing two record separators splits the log into an extra entry with
    no field separators in it. Almost every such entry is prose, so `int()` raises and the
    reader skips it; one made of digits parses, compares against the cutoff, and the next line
    asks for a field that is not there. The difference is an `IndexError` that takes the build
    status page down against a record quietly skipped.

    The number is far in the future so it is inside any window this is asked about, which is
    what makes the guard the only thing standing in front of the index.

    Delete this and the field-count guard in `closed_since` is unreachable, and one strange
    commit message stops the status page from being generated at all.
    """
    import subprocess
    from datetime import UTC, datetime, timedelta

    repo = tmp_repo()
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.invalid"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(command, cwd=repo, check=True, timeout=30)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=30)
    hostile = (
        "M0.1.1 done"
        + NEWLINE * 2
        + "Closes: M0.1.1"
        + NEWLINE
        + PROVED
        + NEWLINE * 2
        + SEPARATOR
        + "9999999999"
        + SEPARATOR
        + NEWLINE
    )
    (repo / "msg.txt").write_text(hostile, encoding="utf-8")
    subprocess.run(["git", "commit", "-q", "-F", "msg.txt"], cwd=repo, check=True, timeout=30)

    since = status.closed_since(repo, datetime.now(UTC) - timedelta(days=1))

    assert "M0.1.1" in since


def _wbs(modules: int, leaves_per_module: int, wave: int = 0) -> dict[str, object]:
    """A work breakdown with nothing closed against it, for the next-up tests below."""
    return {
        "wave_names": {str(wave): "a wave"},
        "modules": [
            {
                "id": f"M{index}",
                "name": f"module {index}",
                "wave": wave,
                "leaf_ids": [f"M{index}.1.{leaf}" for leaf in range(1, leaves_per_module + 1)],
            }
            for index in range(modules)
        ],
    }


def test_the_next_up_list_stops_at_five_however_much_is_open() -> None:
    """**Two breaks, one inside the leaf loop and one outside it, and both are load-bearing.**

    Without the inner one the module being scanned contributes every open leaf it has. Without
    the outer one the inner break fires at five and the next module starts appending, so the
    count runs past five and never comes back to it: the test is `== 5` and the list is already
    there.

    A page showing forty next-up tasks is a page nobody reads, which is the failure this
    silently produces.

    Delete this and the cap is decoration.
    """
    built = status.build_status(_empty_repo(), _wbs(modules=3, leaves_per_module=9))

    assert len(built.next_up) == 5


def test_next_up_names_only_the_wave_being_worked() -> None:
    """The list answers "what is next", and next means next in the wave somebody is in. A leaf
    from a later wave in that list sends whoever reads it to work that cannot start.

    Delete this and the page proposes work from a wave whose dependencies do not exist yet.
    """
    wbs = _wbs(modules=2, leaves_per_module=2)
    modules = wbs["modules"]
    assert isinstance(modules, list)
    modules[1]["wave"] = 4

    built = status.build_status(_empty_repo(), wbs)

    assert built.next_up
    assert all(leaf.startswith("M0.") for leaf in built.next_up), built.next_up


def test_the_entry_point_refuses_a_repository_with_no_work_breakdown() -> None:
    """CI runs `main` before the image is built, so the missing-file branch is the one that
    decides what happens when the work breakdown is not where it should be.

    `main` takes the repository as a parameter with the derived path as its default, and that
    parameter exists for this: a function that can only be pointed at this repository has a
    branch nothing can reach, and CI is where it would first run.

    Delete this and the branch goes back to being unreachable, and a missing WBS in CI is a
    traceback rather than a sentence naming the path.
    """
    assert status.main(_empty_repo()) == 1


def test_a_commit_message_outside_the_machines_codepage_does_not_take_the_page_down() -> None:
    """**A commit body quoting a Chinese phrase made `build_status` raise on 2026-09-09.**

    Git writes commit messages as UTF-8. `subprocess.run(text=True)` decodes with the
    platform's ANSI codepage, which on this machine is cp1252, so the first message holding a
    character cp1252 does not have took the whole build status page with it. The traceback
    named the line in `status.py` rather than the commit, which is why it took a while to
    read. A curly quote pasted out of a word processor does the same thing.

    Run against a real repository built here rather than by patching `subprocess`, because
    what is being tested is the decoding of git's actual bytes and a patched `run` would
    return whatever the test handed it.

    Delete this and the reader goes back to the platform default, and the page breaks again
    the first time somebody writes a commit message in their own language, which for this
    product is a first-class case rather than an edge one.
    """
    import subprocess

    repo = tmp_repo()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=30)
    subprocess.run(
        ["git", "config", "user.email", "t@example.invalid"], cwd=repo, check=True, timeout=30
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, timeout=30)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=30)
    # The phrase is the one that broke it, plus a curly quote, which is the likelier source.
    message = f"SLA \u6761\u6b3e and a \u201ccurly\u201d quote\n\nCloses: M0.1.1\n{PROVED}\n"
    (repo / "msg.txt").write_text(message, encoding="utf-8")
    subprocess.run(["git", "commit", "-q", "-F", "msg.txt"], cwd=repo, check=True, timeout=30)

    closed, recent = status.closed_task_ids(repo)

    assert "M0.1.1" in closed
    assert recent, "the commit was read"


def test_the_generated_status_agrees_with_the_wbs_about_the_waves() -> None:
    """The other half of the same property, and the half that decides what `/build` shows.

    `build_status` is run rather than its output read, because `docs/status.json` is written
    at build time and is not in the repository. Running it needs only the WBS and git, both
    of which are here."""
    repo = Path(__file__).resolve().parents[2]
    wbs = status.load_wbs(repo / "docs" / "wbs.json")

    built = status.build_status(repo, wbs)

    assert {w.wave: w.total for w in built.waves} == _wbs_leaves_per_wave()


def test_every_leaf_appears_exactly_once_on_the_tracker() -> None:
    """The buildable leaves, the acts and the decided leaves together have to be the whole
    plan. A partition that dropped a leaf would still let the test above pass if both sides
    dropped it, so this checks against the WBS itself rather than against the other page, and
    it counts the acts and the decided leaves too, so excluding them from the percentage can
    never quietly lose one, or count one twice."""
    repo = Path(__file__).resolve().parents[2]
    wbs = status.load_wbs(repo / "docs" / "wbs.json")
    expected = sum(len(m["leaf_ids"]) for m in wbs["modules"])
    acts = sum(len(status.acts_of(m)) for m in wbs["modules"])
    decided = sum(len(status.decided_of(m)) for m in wbs["modules"])

    built = status.build_status(repo, wbs)

    assert acts > 0, "the work breakdown flags no acts, so this test is watching nothing"
    assert decided > 0, "the work breakdown records no decided leaf, so half of this is idle"
    assert sum(_tracker_leaves_per_wave().values()) + acts + decided == expected
    assert built.total + built.acts + built.decided == expected
    assert (built.acts, built.decided) == (acts, decided)


# ------------------------------------------------- taking back a claim that was not true
#
# A leaf can be closed by mistake, because an id mentioned in a subject line closes it and a
# subject line is a sentence about something else. `M0.4.2` is the case: a commit whose
# subject read "M0.4.2: mount the Postgres volume at the path 18 expects" closed the leaf for
# `docker-compose.full.yml`, a file that deliberately does not exist.


def _message(subject: str, trailer: str) -> str:
    """A commit message with a real blank line between subject and trailer.

    Built with an explicit newline rather than written as a literal, because these
    messages reach the file through a shell heredoc and a backslash-n has been eaten
    three separate times in this repository. The trap is in the tooling, not the test."""
    return subject + chr(10) + chr(10) + trailer


def test_a_reopens_trailer_takes_an_id_back() -> None:
    """Without this there is no way to correct a false claim except rewriting history, and
    the plan shows work as delivered that nobody did."""
    assert status.reopened_ids("Reopens: M0.4.2") == {"M0.4.2"}


def test_a_subject_line_cannot_reopen_anything() -> None:
    """Trailer only, and deliberately asymmetric with closing. A subject mention is what
    causes the mistake this exists to correct, so letting a subject reopen would hand the
    same loose mechanism the power to un-deliver work as well.

    Delete this and "Reopens: ..." in a subject silently starts removing leaves."""
    assert status.reopened_ids("") == set()
    assert status.claimed_ids("Reopens: M0.4.2", "") == {"M0.4.2"}


def test_the_newest_statement_about_an_id_is_the_one_that_counts(tmp_path: Path) -> None:
    """`git log` walks newest first, so the first commit to mention an id settles it.

    Without that, an older `Closes:` puts back what a newer `Reopens:` took away, and the
    correction works on the day it is written and silently stops working the moment anybody
    looks further back. That is the failure mode worth testing, because it is invisible: the
    count is simply wrong again, with nothing saying so.

    A real repository rather than a fake, because the ordering being tested is git's."""
    import subprocess

    repo = tmp_path / "r"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    (repo / "a").write_text("1", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", _message("M1.1.1: the original claim", PROVED))
    (repo / "a").write_text("2", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", _message("Take it back", "Reopens: M1.1.1"))

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" not in closed, "a newer Reopens was overridden by an older claim"


def test_a_claim_after_a_reopen_closes_it_again(tmp_path: Path) -> None:
    """The other direction, so reopening cannot become permanent. Work that was wrongly
    marked done and is then genuinely done has to be closeable, or the correction becomes a
    worse error than the one it fixed."""
    import subprocess

    repo = tmp_path / "r2"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    (repo / "a").write_text("1", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", _message("M1.1.1: the original claim", PROVED))
    (repo / "a").write_text("2", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", _message("Take it back", "Reopens: M1.1.1"))
    (repo / "a").write_text("3", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", _message("Actually build it", "Closes: M1.1.1" + chr(10) + PROVED))

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" in closed


# ------------------------------------------------- a claim counts only with its proof
#
# On 2026-09-17 an audit reopened 1046 of the 1213 tasks this page counted as done, because the
# owner's install did not show them working. From `status.PROOF_REQUIRED_FROM` a claim counts
# only when its own commit carries a `Proved-on-install:` or `Proved-in-ci:` line. Every commit
# below has its dates pinned either side of that instant, so none of these is a clock.


def _history(tmp_path: Path, *commits: tuple[str, str]) -> Path:
    """A repository holding each `(committed at, message)` in order, oldest first."""
    repo = tmp_path / "history"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    for when, message in commits:
        git_at(repo, when, "commit", "-q", "--allow-empty", "-m", message)
    return repo


@pytest.mark.parametrize(
    "message",
    ["Build it\n\nCloses: M1.1.1\n", "M1.1.1: build it\n", "M1.1.1: build it\n\nSeen working.\n"],
    ids=["on a Closes line", "in the subject", "in the subject with a body"],
)
def test_a_claim_from_the_start_of_the_proof_rule_without_proof_is_not_counted(
    tmp_path: Path, message: str
) -> None:
    """**The rule, and the half that holds when the commit hook is skipped.** `git commit
    --no-verify` walks past `brain.ops.conventions`, so this page has to refuse the claim on its
    own, and at the first instant of the rule rather than a second later.

    Delete this and an unproved claim counts again on the page the owner reads, which is how
    1046 tasks came to show as done."""
    repo = _history(tmp_path, (AT_PROOF, message))

    closed, recent = status.closed_task_ids(repo)

    assert "M1.1.1" not in closed
    assert recent == [], "a claim that does not count was listed as a closure"


@pytest.mark.parametrize(
    "proof",
    [
        "Proved-on-install: signed in as a staff member and the answer named the invoice",
        "Proved-in-ci: the unit job runs tests/unit/test_status.py",
        "proved-in-ci: the unit job",
    ],
    ids=["on an install", "in CI", "lower case"],
)
def test_a_claim_from_the_start_of_the_proof_rule_with_proof_is_counted(
    tmp_path: Path, proof: str
) -> None:
    """The positive sibling. Without it the rule above is satisfied by a page that counts
    nothing after the start, which would read as a build that stopped the day the rule began.

    Lower case counts because every other trailer this page reads is case-insensitive, and the
    commit hook reads proof through the same function. Delete this and a proved claim can
    silently stop counting."""
    repo = _history(tmp_path, (AT_PROOF, f"Build it\n\nCloses: M1.1.1\n{proof}\n"))

    closed, recent = status.closed_task_ids(repo)

    assert "M1.1.1" in closed
    assert recent[0]["closed"] == "M1.1.1"


def test_a_claim_made_before_the_proof_rule_is_counted_as_it_always_was(tmp_path: Path) -> None:
    """**Earlier commits are judged as they were.** The audit already read every claim made
    before the rule and reopened what the install did not bear out, so a claim from the second
    before still counts without a trailer that did not exist when it was written.

    Delete this and the start can be moved back over the history, and the 167 tasks the audit
    left standing drop off the page for want of a trailer."""
    repo = _history(tmp_path, (BEFORE_PROOF, "M1.1.1: build it\n"))

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" in closed


@pytest.mark.parametrize(
    "trailer",
    ["Proved-on-install:", "Proved-in-ci:   ", "Proved-on-install:\t"],
    ids=["nothing after the colon", "spaces", "a tab"],
)
def test_an_empty_proof_trailer_does_not_count(tmp_path: Path, trailer: str) -> None:
    """A colon with nothing after it is the cheapest way to satisfy the letter of the rule, and
    it proves nothing.

    Delete this and the trailer becomes a word to type rather than a sentence saying what was
    seen, which is the unit test over fakes again, one line shorter."""
    repo = _history(tmp_path, (AT_PROOF, f"Build it\n\nCloses: M1.1.1\n{trailer}\nMore prose.\n"))

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" not in closed


def test_a_proof_written_as_the_subject_proves_nothing(tmp_path: Path) -> None:
    """Proof is read from the body, where a trailer is. A subject that reads like a trailer is a
    sentence, and git's `%s` would carry it with the claim beside it.

    Delete this and proof can be read from the subject line, where the commit hook does not
    look for it, so the two halves of the rule disagree about the same message."""
    repo = _history(tmp_path, (AT_PROOF, "Proved-in-ci: the unit job, M1.1.1\n"))

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" not in closed


def test_an_unproved_claim_neither_closes_a_task_nor_settles_one(tmp_path: Path) -> None:
    """An unproved claim is as though it were not there. It does not undo an older reopen, and
    it does not stand in front of an older claim either, because the newest statement about an
    id is the one that counts and an unproved claim is not a statement.

    Delete this and an unproved claim can be made to settle an id, which either closes a task
    nobody proved or hides a proved claim behind one nobody did."""
    reopened = _history(
        tmp_path / "a",
        ("2026-09-10T09:00:00+00:00", "M1.1.1: build it\n"),
        ("2026-09-11T09:00:00+00:00", "Take it back\n\nReopens: M1.1.1\n"),
        (AT_PROOF, "Build it again\n\nCloses: M1.1.1\n"),
    )
    claimed = _history(
        tmp_path / "b",
        ("2026-09-10T09:00:00+00:00", "M1.1.1: build it\n"),
        (AT_PROOF, "Build it again\n\nCloses: M1.1.1\n"),
    )

    assert "M1.1.1" not in status.closed_task_ids(reopened)[0]
    assert "M1.1.1" in status.closed_task_ids(claimed)[0]


def test_a_reopen_from_the_start_of_the_proof_rule_needs_no_proof(tmp_path: Path) -> None:
    """Taking a claim back only lowers the count, which is never the direction a mistake
    flatters, so a `Reopens:` line counts with no proof beside it.

    Delete this and the page can be written to skip a whole unproved commit, reopens and all,
    and a correction after the start would silently stop correcting anything."""
    repo = _history(
        tmp_path,
        (BEFORE_PROOF, "M1.1.1: build it\n"),
        (AT_PROOF, "Take it back\n\nReopens: M1.1.1\n"),
    )

    closed, _ = status.closed_task_ids(repo)

    assert "M1.1.1" not in closed


def test_closed_today_applies_the_same_proof_rule(tmp_path: Path) -> None:
    """`closed_since` walks the history a second time for the day's count, so it has to judge a
    claim the way `closed_task_ids` does or it can name as closed today a leaf the page does not
    count at all.

    Delete this and the second reader can drift back to the bare claim with every other test
    here green, because `build_status` intersects the two and hides the difference."""
    repo = _history(
        tmp_path,
        (AT_PROOF, "Build one\n\nCloses: M1.1.1\n"),
        (AT_PROOF, f"Build two\n\nCloses: M1.1.2\n{PROVED}\n"),
    )

    since = status.closed_since(repo, datetime(2026, 9, 18, tzinfo=UTC))

    assert since == {"M1.1.2"}


def test_a_record_typed_into_a_commit_message_is_skipped_rather_than_read(tmp_path: Path) -> None:
    """**A commit message holding the separators can hold a whole record.** One whose timestamp
    is not a number came to this reader as a commit, and once the proof rule reads the timestamp
    of every record it would raise and take the page down. Before the rule it raised only when
    the record claimed something, which is the case written here.

    Delete this and the skip can go, and one strange commit message stops the status page being
    generated at all."""
    forged = (
        "Real work"
        + NEWLINE * 2
        + "Pasted log:"
        + SEPARATOR
        + "not-a-hash"
        + chr(31)
        + "not-a-time"
        + chr(31)
        + "M1.1.2 forged"
        + chr(31)
        + "Proved-in-ci: nothing"
        + NEWLINE
    )
    repo = _history(tmp_path, (BEFORE_PROOF, forged))

    closed, recent = status.closed_task_ids(repo)
    # The day's reader takes the same record with one field fewer, so its first field is text.
    since = status.closed_since(repo, datetime(2019, 1, 1, tzinfo=UTC))

    assert "M1.1.2" not in closed
    assert recent == []
    assert "M1.1.2" not in since


# --- the sentence that specifies a leaf (M38.3.1.4) -------------------------------------------


REAL_WBS = Path(__file__).resolve().parents[2] / "docs" / "wbs.json"


def a_wbs(path: Path, ids: list[str], texts: list[str] | None) -> Path:
    """One module, written to disk, with the sentences under the caller's control.

    A file rather than a dictionary because `leaf_sentences` takes a path, and it takes a path
    because the thing it reads is a build artefact that can be stale. A helper that let the
    test hand it a parsed object would test a function nobody calls."""
    module: dict[str, object] = {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ids}
    if texts is not None:
        module["leaf_texts"] = texts
    path.write_text(json.dumps({"modules": [module]}), encoding="utf-8", newline="\n")
    return path


def test_every_leaf_of_the_work_breakdown_arrives_with_the_sentence_that_specifies_it() -> None:
    """The positive case, against the real export rather than a fixture, because the reader
    exists so that a test can anchor a constant to the leaf it claims to implement and a
    reader that works only on a two-leaf fixture would not carry that.

    Counted and checked for emptiness, not spot-checked on one id: a lookup that returned the
    same sentence for every leaf would satisfy any single-id assertion, and so would one that
    returned the module's first sentence for all of its leaves.

    Delete this and `leaf_sentences` can come back empty, every test anchored to a leaf skips
    its comparison silently, and the anchoring stops meaning anything."""
    found = status.leaf_sentences(REAL_WBS)
    ids = {leaf for module in status.load_wbs(REAL_WBS)["modules"] for leaf in module["leaf_ids"]}

    assert set(found) == ids
    assert all(one.strip() for one in found.values())
    assert len(set(found.values())) > len(found) * 0.9, "the sentences are barely distinct"


def test_a_module_carrying_fewer_sentences_than_leaves_is_refused_rather_than_zipped(
    tmp_path: Path,
) -> None:
    """**The arrays are positional, so a missing sentence does not lose one leaf, it renames
    every leaf after it.** `M0.1.2` would come back holding `M0.1.3`'s sentence, and a test
    anchored to it would be comparing a constant against its neighbour's specification, which
    is worse than having no sentence at all because it looks like an answer.

    `zip` without `strict` is the default that does this quietly, so the length is checked
    before the zip and the reason is named.

    Delete this and the guard has nothing to fire on, and dropping the check restores the
    silent shift with every other test in this file still green."""
    short = a_wbs(tmp_path / "short.json", ["M0.1.1", "M0.1.2", "M0.1.3"], ["one", "two"])

    with pytest.raises(ValueError, match="positional"):
        status.leaf_sentences(short)

    # And the same file with the sentence restored is read, so the refusal above is a
    # property of the mismatch and not of the fixture being unreadable.
    whole = a_wbs(tmp_path / "whole.json", ["M0.1.1", "M0.1.2", "M0.1.3"], ["one", "two", "three"])

    assert status.leaf_sentences(whole) == {"M0.1.1": "one", "M0.1.2": "two", "M0.1.3": "three"}


def test_an_export_written_before_sentences_existed_reads_as_absent_rather_than_failing(
    tmp_path: Path,
) -> None:
    """A checkout from before `docs/wbs/export.js` learned to write them is a `wbs.json` with
    ids and no sentences, and the reader has to survive it: `load_wbs` already tolerates a WBS
    with no `leaf_ids` at all, and a reader that refused an older export would be the one
    function in this module that cannot run against last week.

    Absence and a mismatch are different answers on purpose. Nothing is missing from an old
    export; something is wrong with a short one.

    Delete this and the tolerance can be replaced by a raise, and `brain.status` stops
    importing on any tree whose `wbs.json` has not been regenerated."""
    old = a_wbs(tmp_path / "old.json", ["M0.1.1", "M0.1.2"], None)

    assert status.leaf_sentences(old) == {}


# --- the page renders its markup rather than reading it out (M38.3.2.1) -----------------------


def test_every_heading_level_the_document_uses_is_rendered_as_a_heading() -> None:
    """**Five third-level headings rendered on the live page as the literal text
    `### 1. Four containers read a settings file that will not be there`.** The line loop
    tested `## ` and `# ` and had nothing for `### `, so those lines fell through to the
    paragraph branch, and the page read out its own markup in the middle of an item. Nothing
    looked broken, which is why it survived: an unstyled paragraph beginning with three hashes
    is a page reading correctly to a machine and wrongly to a person.

    Asserted over the levels the real document actually uses, read from the document, rather
    than over a fixed list. A fourth level added to `needs-rupash.md` next month is covered on
    the day it is written, and a level that stops being used stops being asserted.

    Both directions. Every level is rendered as its tag, and no rendered line still begins with
    a hash, because emitting `<h3>### text</h3>` would satisfy the first half.

    Delete this and the next heading level added to the document is published as prose."""
    import re

    from brain import docs_routes

    text = (docs_routes.DOCS / "needs-rupash.md").read_text(encoding="utf-8")
    levels = {len(found) for found in re.findall(r"^(#{1,6}) \S", text, flags=re.MULTILINE)}

    assert levels >= {1, 2, 3}, f"the document no longer uses three levels: {levels}"

    page = bytes(docs_routes.needs_rupash().body).decode("utf-8")

    for level in levels:
        assert f"<h{level}>" in page, f"level {level} is used in the document and rendered as prose"

    # And nothing rendered still carries the markup that produced it. Searched over the whole
    # page rather than over headings alone, because the failure was a paragraph and not a
    # heading: the hashes were in a `<p>`.
    for stray in re.findall(r">\s*(#{1,6} [^<]{0,60})", page):
        raise AssertionError(f"markup published as content: {stray!r}")


def test_the_tracker_offers_the_filter_that_shows_only_what_is_left() -> None:
    """The owner reads this page to see what is not done, and until 2026-09-16 that meant
    scrolling twelve hundred rows past the ones that are. The filter hides the done leaves and,
    with them, every group and module heading left with nothing under it, so the page reads as
    the remaining work rather than as a list of empty headings.

    Asserted on the rendered page rather than on the renderer, because the page is what is
    served: `docs/tracker.html` is committed and `docs/wbs/render.js` is run by hand, so a
    change to the renderer that nobody regenerates is a change nobody sees.

    Delete this and the button can go, or the three rules under it can be trimmed to the first,
    which leaves headings standing over nothing and reads as work that does not exist."""
    root = Path(__file__).resolve().parents[2]
    page = (root / "docs" / "tracker.html").read_text(encoding="utf-8")

    assert 'id="bLeft"' in page
    assert "body.leftonly li.leaf.done{display:none}" in page
    assert "body.leftonly li.n:not(.leaf):not(:has(li.leaf:not(.done))){display:none}" in page
    assert "body.leftonly section[data-mod]:not(:has(li.leaf:not(.done))){display:none}" in page


# --- statuses other than DONE, set by hand in docs/wbs/progress.js ----------------------------
#
#: The repository this file sits in.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The owner asked on 2026-09-17 for every task to show OPEN, IN PROGRESS, READY FOR TESTING,
# BLOCKED with its reason, or DONE. DONE stays computed from commits; the rest are typed.


def _with_progress(entries: dict[str, dict[str, str]]) -> dict[str, Any]:
    """The fixture plan with hand-set statuses on M0 and M1, as `export.js` writes them."""
    by_module: dict[str, dict[str, dict[str, str]]] = {}
    for leaf, entry in entries.items():
        by_module.setdefault(leaf.split(".")[0], {})[leaf] = entry
    modules: list[dict[str, Any]] = json.loads(json.dumps(WBS["modules"]))
    for module in modules:
        module["leaf_progress"] = by_module.get(str(module["id"]), {})
    return {**WBS, "modules": modules}


@pytest.mark.parametrize(
    ("leaf", "entry", "reason"),
    [
        ("M9.1.1", {"status": "OPEN", "updated": "2026-09-17"}, "is not a leaf"),
        ("M0.2.1", {"status": "STARTED", "updated": "2026-09-17"}, "none of"),
        ("M0.2.1", {"status": "DONE", "updated": "2026-09-17"}, "none of"),
        ("M0.2.1", {"status": "BLOCKED", "why": "  ", "updated": "2026-09-17"}, "no reason"),
        ("M0.2.1", {"status": "IN PROGRESS", "updated": "17/09/2026"}, "no updated day"),
    ],
)
def test_a_progress_entry_the_file_would_refuse_is_refused_in_the_export_too(
    leaf: str, entry: dict[str, str], reason: str
) -> None:
    """`progress.js` throws on each of these, and `wbs.json` can still hold one: edited by hand
    or left behind by a failed export. DONE is here because a file that could say DONE would mark
    a task done by hand, which M38.3.1.3 forbids. Delete this and an unknown id or status is
    shown to the owner as though it meant something."""
    module = {"id": "M0", "name": "Foundation", "wave": 0, "leaf_ids": ["M0.1.1", "M0.2.1"]}

    with pytest.raises(ValueError, match=reason):
        status.progress_of({**module, "leaf_progress": {leaf: entry}})


def test_a_well_formed_progress_entry_is_read_with_its_reason() -> None:
    """The positive sibling: a validator refusing everything passes every test above."""
    module = {
        "id": "M0",
        "leaf_ids": ["M0.1.1", "M0.2.1"],
        "leaf_progress": {
            "M0.2.1": {"status": "BLOCKED", "why": "needs a token", "updated": "2026-09-17"},
            "M0.1.1": {"status": "READY FOR TESTING", "updated": "2026-09-17"},
        },
    }

    found = status.progress_of(module)

    assert found["M0.2.1"] == status.LeafProgress(
        status="BLOCKED", why="needs a token", updated="2026-09-17"
    )
    assert found["M0.1.1"].status == "READY FOR TESTING"


def test_a_closed_leaf_is_done_whatever_the_progress_file_says(repo: Path) -> None:
    """**The rule the owner stated: DONE comes from commits, and nothing typed overrides it.**
    M0.1.1 is closed by a commit in the fixture and marked IN PROGRESS by hand. Delete this and a
    stale entry can hold delivered work at IN PROGRESS on both pages."""
    wbs = _with_progress({"M0.1.1": {"status": "IN PROGRESS", "updated": "2026-09-17"}})

    s = status.build_status(repo, wbs)

    assert "M0.1.1" in s.done_task_ids
    assert "M0.1.1" not in s.leaf_status
    wave_zero = next(w for w in s.waves if w.wave == 0)
    assert (wave_zero.done, wave_zero.in_progress) == (2, 0)


def test_each_wave_counts_its_unclosed_leaves_by_status_and_the_counts_sum_to_the_total(
    repo: Path,
) -> None:
    """Per wave, because the owner asked for a count per status per wave. The sum is the property
    that makes the columns trustworthy: a leaf counted under two statuses, or under none, makes
    the row add up to something other than the wave. Delete this and the columns on /build can
    disagree with the percentage beside them."""
    wbs = _with_progress(
        {
            "M0.2.1": {"status": "BLOCKED", "why": "waits on a token", "updated": "2026-09-17"},
            "M1.1.2": {"status": "READY FOR TESTING", "why": "", "updated": "2026-09-17"},
        }
    )

    s = status.build_status(repo, wbs)

    by_wave = {w.wave: w for w in s.waves}
    assert (by_wave[0].blocked, by_wave[0].open, by_wave[0].done) == (1, 0, 2)
    assert (by_wave[1].ready_for_testing, by_wave[1].open, by_wave[1].done) == (1, 0, 1)
    for w in s.waves:
        assert w.done + w.in_progress + w.ready_for_testing + w.blocked + w.open == w.total
    assert s.leaf_status["M0.2.1"].why == "waits on a token"


def test_every_hand_set_status_in_the_repository_is_a_known_status_on_a_real_leaf() -> None:
    """The committed export, read the way the status page reads it. `export.js` refuses these
    first; this is the refusal a Python run sees when `wbs.json` was edited instead. Delete this
    and an unknown id or status in the file the image ships reaches the owner's page."""
    wbs = status.load_wbs(REAL_WBS)
    entries = {
        leaf: entry
        for module in wbs["modules"]
        for leaf, entry in status.progress_of(module).items()
    }

    assert all(entry.status in status.HAND_SET_STATUSES for entry in entries.values())
    assert status.wave_records_of(wbs) is not None


def test_the_tracker_shows_each_leaf_the_status_the_work_breakdown_gives_it() -> None:
    """Every leaf checkbox carries one status, OPEN unless `progress.js` says otherwise, so the
    tracker and /build read one file. Delete this and `render.js` can badge a different leaf, or
    none, with the status page still right."""
    html = (REPO_ROOT / "docs" / "tracker.html").read_text(encoding="utf-8")
    wbs = status.load_wbs(REAL_WBS)
    expected = {
        leaf: status.progress_of(module)[leaf].status
        if leaf in status.progress_of(module)
        else status.OPEN
        for module in wbs["modules"]
        for leaf in module["leaf_ids"]
    }

    boxes = re.findall(r'<input type="checkbox" class="cb"[^>]*>', html)
    shown: dict[str, str] = {}
    for box in boxes:
        leaf, state = re.search(r'data-id="([^"]+)"', box), re.search(r'data-status="([^"]+)"', box)
        assert leaf is not None, box
        shown[leaf.group(1)] = state.group(1) if state is not None else "no status"

    assert shown == expected
    # A closed leaf gets li.done from the live status, and its status chip is hidden under it.
    assert "li.leaf.done .pst,li.leaf.done .pwhy{display:none}" in html


def test_the_status_page_shows_each_waves_count_per_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/build is the other page the owner named. Delete this and the columns can vanish from it
    while the tracker keeps them."""
    docs = tmp_path / "docs"
    docs.mkdir()
    wave = {"wave": 0, "name": "Foundation", "total": 10, "done": 4, "percent": 40.0}
    counts = {"in_progress": 3, "ready_for_testing": 2, "blocked": 1, "open": 0}
    body = {"commit": "abc1234", "waves": [{**wave, **counts}], "done_task_ids": []}
    (docs / "status.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(docs_routes, "DOCS", docs)

    with TestClient(create_app(Settings(env="production"))) as client:
        page = client.get("/build").text

    row = re.search(r"<tr><td>Wave 0</td>.*?</tr>", page)
    assert row is not None
    cells = re.findall(r'<td class="n">([^<]*)</td>', row.group(0))
    assert cells == ["4/10", "40.0%", "3", "2", "1", "0"]
    assert '<th style="text-align:right">Blocked</th>' in page


# --- the wave reports page (M38.2.1.6) and the end-of-wave record (M38.2.1.1) ---------------


def _waves_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, records: dict[str, Any] | None = None
) -> TestClient:
    docs = tmp_path / "docs"
    docs.mkdir()
    wbs = {
        "wave_names": {"0": "Foundation", "1": "The gate"},
        "wave_records": records or {},
        "modules": [
            {
                "id": "M0",
                "name": "Foundation",
                "wave": 0,
                "leaf_ids": ["M0.1.1", "M0.1.2", "M0.1.3"],
                "leaf_texts": ["first", "second", "third <b>"],
                "leaf_progress": {
                    "M0.1.2": {
                        "status": "BLOCKED",
                        "why": "waits on <token>",
                        "updated": "2026-09-17",
                    },
                    "M0.1.1": {"status": "IN PROGRESS", "why": "", "updated": "2026-09-17"},
                },
            },
            {
                "id": "M1",
                "name": "Identity",
                "wave": 1,
                "leaf_ids": ["M1.1.1"],
                "leaf_texts": ["x"],
            },
        ],
    }
    (docs / "wbs.json").write_text(json.dumps(wbs), encoding="utf-8")
    (docs / "status.json").write_text(
        json.dumps({"commit": "abc1234", "done_task_ids": ["M0.1.1"], "recent": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    return TestClient(create_app(Settings(env="production")))


def test_the_wave_reports_page_counts_each_status_and_names_every_block_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M38.2.1.6, as the owner reads it at /build/waves. M0.1.1 is closed and marked IN PROGRESS,
    so it counts closed; M0.1.2 is blocked, and its reason is shown escaped, because the progress
    file is typed by a person and lands in markup. Delete this and the page can lose the reasons,
    which is the half of a block somebody acts on."""
    with _waves_client(tmp_path, monkeypatch) as client:
        response = client.get("/build/waves")

    assert response.status_code == 200
    page = response.text
    wave_zero = page[page.index('id="wave-0"') : page.index('id="wave-1"')]
    assert "1 closed" in wave_zero
    assert "0 in progress" in wave_zero
    assert "1 blocked" in wave_zero
    assert "1 open" in wave_zero
    assert "waits on &lt;token&gt;" in wave_zero
    assert "<token>" not in page
    assert "No end-of-wave commit recorded yet" in wave_zero


def test_the_wave_reports_page_shows_the_commit_a_wave_was_recorded_as_closing_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M38.2.1.1: the record is shown where the wave is. Delete this and a recorded commit can be
    in the file and on no page."""
    records = {"0": {"commit": "fa53822", "recorded": "2026-09-20", "note": "accepted"}}
    with _waves_client(tmp_path, monkeypatch, records=records) as client:
        page = client.get("/build/waves").text

    wave_zero = page[page.index('id="wave-0"') : page.index('id="wave-1"')]
    assert "<code>fa53822</code> on 2026-09-20: accepted" in wave_zero
    assert "No end-of-wave commit recorded yet" in page[page.index('id="wave-1"') :]


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ({"9": {"commit": "fa53822", "recorded": "2026-09-20"}}, "not a wave"),
        ({"0": {"commit": "main", "recorded": "2026-09-20"}}, "not a commit"),
        ({"0": {"commit": "fa53822", "recorded": "soon"}}, "no recorded day"),
    ],
)
def test_a_wave_record_naming_no_wave_no_commit_or_no_day_is_refused(
    records: dict[str, Any], reason: str
) -> None:
    """A record is what says which commit a wave ended at, now that tags are cut only for client
    installs, so one naming a branch or a wave that does not exist is refused. Delete this and
    `main` can be recorded as a wave's commit, which moves every day."""
    with pytest.raises(ValueError, match=reason):
        status.wave_records_of({"wave_names": {"0": "Foundation"}, "wave_records": records})


def test_every_recorded_wave_commit_is_in_this_repositorys_history() -> None:
    """A record that names a commit nobody can find is a record of nothing. Checked only where
    the history is complete, since a shallow clone cannot tell a missing commit from an unfetched
    one; CI's unit jobs fetch the whole history."""
    records = status.wave_records_of(status.load_wbs(REAL_WBS))
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if shallow != "false":
        pytest.skip("not a complete clone, so an absent commit may simply be unfetched")
    for wave, record in records.items():
        found = subprocess.run(
            ["git", "cat-file", "-e", f"{record.commit}^{{commit}}"], cwd=REPO_ROOT, check=False
        )
        assert found.returncode == 0, f"wave {wave} records {record.commit}, which is not here"


# --- the status file written to the repository (M38.3.1.2) ------------------------------------


def _status_file_workflow() -> dict[Any, Any]:
    import yaml

    parsed: dict[Any, Any] = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "status-file.yml").read_text(encoding="utf-8")
    )
    return parsed


def test_the_status_file_is_committed_after_each_green_ci_on_main_and_never_to_main() -> None:
    """M38.3.1.2. After a green CI on main, because a task is done only when CI is green; to the
    `status` branch, because a commit to main would start CI and Deploy again for every merge.
    Delete this and the push can be pointed at main, or the trigger at every CI run whatever its
    result, with the file still looking right."""
    workflow = _status_file_workflow()
    # PyYAML reads the bare key `on` as True.
    trigger = workflow[True]["workflow_run"]
    job = workflow["jobs"]["write"]
    steps = job["steps"]
    runs = "\n".join(str(step.get("run", "")) for step in steps)

    assert trigger == {"workflows": ["CI"], "branches": ["main"], "types": ["completed"]}
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert workflow["permissions"] == {"contents": "write"}
    assert "uv run python -m brain.status" in runs
    assert "git push --quiet origin HEAD:refs/heads/status" in runs
    assert not re.search(r"push[^\n]*\bmain\b", runs)
    checkout = next(s for s in steps if "actions/checkout" in str(s.get("uses", "")))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha || github.sha }}"
