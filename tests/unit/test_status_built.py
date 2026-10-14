"""Built is a second figure beside Done, and it is never a way of reaching Done.

Owner-approved on 2026-10-14: progress shows as soon as a task's code is merged and CI passed,
without waiting for an install to show it working, and the page says so. These tests hold the rule
in `brain.status.A_BUILT_IS_CI_CHECKED_AND_NEVER_SHOWN_WORKING`: a leaf is built when it is not
done, a person says it is READY FOR TESTING or a commit claimed it without proof, and a test in the
repository names it on a `Task ids:` line. Neither alone is enough, and a built leaf is never in
`done_task_ids`.

Task ids: M38.5.4
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain import docs_routes, status
from brain.app import Settings, create_app
from brain.ops import sweeps

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A claim made after the proof rule began and so needing proof, written out rather than derived
#: from `status.PROOF_REQUIRED_FROM`, so a moved start fails these tests instead of moving them.
AT_PROOF = "2026-09-18T00:00:00+00:00"
BEFORE_PROOF = "2026-09-17T23:59:59+00:00"

PLAN: dict[str, Any] = {
    "wave_names": {"0": "Foundation", "1": "The gate"},
    "modules": [
        {
            "id": "M0",
            "name": "Foundation",
            "wave": 0,
            "leaf_ids": ["M0.1.1", "M0.1.2", "M0.1.3", "M0.1.4"],
        },
        {"id": "M1", "name": "Identity", "wave": 1, "leaf_ids": ["M1.1.1", "M1.1.2"]},
    ],
}


def plan(**ready: str) -> dict[str, Any]:
    """The fixture plan with the named leaves hand-set READY FOR TESTING (the value is the day)."""
    modules: list[dict[str, Any]] = json.loads(json.dumps(PLAN["modules"]))
    for module in modules:
        module["leaf_progress"] = {
            leaf: {"status": "READY FOR TESTING", "why": "", "updated": day}
            for leaf, day in ready.items()
            if leaf.split(".")[0] == module["id"]
        }
    return {**PLAN, "modules": modules}


def git(cwd: Path, when: str | None, *args: str) -> None:
    import os

    env = os.environ if when is None else {**os.environ, "GIT_COMMITTER_DATE": when}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, env=dict(env))


def history(tmp_path: Path, *commits: tuple[str, str]) -> Path:
    """A repository holding each `(committed at, message)` in order, oldest first."""
    repo = tmp_path / "history"
    repo.mkdir(parents=True)
    git(repo, None, "init", "-q", "-b", "main")
    git(repo, None, "config", "user.email", "t@example.com")
    git(repo, None, "config", "user.name", "T")
    for when, message in commits:
        git(repo, when, "commit", "-q", "--allow-empty", "-m", message)
    return repo


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ the pure rule
def test_a_leaf_is_built_only_with_evidence_and_a_test() -> None:
    """The rule is a conjunction. Evidence without a test is a person's word with nothing in the
    repository behind it, and a test without evidence is code nobody has said is finished. Delete
    this and the rule can be loosened to either one, which is the version of Built the owner
    should not trust."""
    leaves = ["M1.1.1", "M1.1.2", "M1.1.3", "M1.1.4"]
    evidence = {"M1.1.1", "M1.1.2"}
    tested = {"M1.1.2", "M1.1.3"}

    assert status.built_ids(leaves, evidence, tested) == {"M1.1.2"}


def test_a_built_leaf_is_found_among_many_when_both_halves_hold() -> None:
    """The positive sibling: a rule that returned nothing would pass the test above. Delete this
    and `built_ids` can refuse everything while that test stays green."""
    leaves = ["M1.1.1", "M1.1.2", "M1.1.3"]

    assert status.built_ids(leaves, set(leaves), set(leaves)) == set(leaves)


def test_a_leaf_that_is_not_among_the_unclosed_buildable_ones_is_never_built() -> None:
    """`built_ids` answers only for the leaves it is handed, which `build_status` limits to the
    ones not done, not an act and not decided. Delete this and evidence and a test for a leaf the
    caller did not offer would put it in the figure."""
    assert status.built_ids(["M1.1.1"], {"M1.1.1", "M9.9.9"}, {"M1.1.1", "M9.9.9"}) == {"M1.1.1"}


# ------------------------------------------------------------- the tests that count
def test_a_test_names_a_leaf_only_on_a_task_ids_line(tmp_path: Path) -> None:
    """A test that says "M1.1.3 is not done yet" names the leaf and proves nothing about it, so
    only a `Task ids:` line counts, with the comment marker a TypeScript or shell test puts before
    it, in the Python suite, the console's suite and the browser harness's specs and libraries.
    Delete this and any mention in a test file makes a leaf built."""
    write(tmp_path, "tests/unit/test_a.py", '"""Why.\n\nTask ids: M1.1.1, M1.1.2\n"""\n')
    write(tmp_path, "tests/unit/test_b.py", "# M1.1.3 is not done yet\n")
    write(tmp_path, "console/tests/page.test.tsx", "/**\n * Task ids: M0.1.1\n */\n")
    write(tmp_path, "e2e/specs/flow.spec.ts", "// Task ids: M0.1.2\n")
    write(tmp_path, "e2e/lib/steps.ts", "// Task ids: M0.1.3\n")
    write(tmp_path, "e2e/pages/where.ts", "// Task ids: M0.1.4\n")

    assert status.test_named_ids(tmp_path) == {
        "M1.1.1",
        "M1.1.2",
        "M0.1.1",
        "M0.1.2",
        "M0.1.3",
    }


def test_the_places_a_test_is_read_from_are_the_ones_the_traceability_sweep_reads() -> None:
    """Two lists of where a test may live would drift, and Built would then count a leaf the sweep
    says has no test, or miss one it says has. Compared as paths below the repository root. Delete
    this and a new test directory added to one list is silently absent from the other."""
    here = {path.relative_to(REPO_ROOT) for path in status.test_sources(REPO_ROOT)}
    there = {path.relative_to(REPO_ROOT) for path in sweeps._test_sources()}

    assert here == there
    assert here, "no test sources were found at all"


# ------------------------------------------------------- claims made without proof
def test_a_claim_without_proof_is_unproved_and_closes_nothing(tmp_path: Path) -> None:
    """A claim from the start of the proof rule with no proof trailer counts for nothing as Done
    and is evidence for Built. Delete this and the evidence for Built is unread, or an unproved
    claim reaches `closed_task_ids` and the Done figure."""
    repo = history(tmp_path, (AT_PROOF, "Build it\n\nCloses: M1.1.1\n"))

    assert status.claimed_without_proof(repo) == {"M1.1.1"}
    closed, _ = status.closed_task_ids(repo)
    assert "M1.1.1" not in closed


def test_a_claim_with_proof_is_not_unproved(tmp_path: Path) -> None:
    """The sibling: a proved claim is Done, and counting it as built as well would count it
    twice. Delete this and `built` can exceed `done + built_unproven`."""
    repo = history(
        tmp_path, (AT_PROOF, "Build it\n\nCloses: M1.1.1\nProved-in-ci: the unit job runs it\n")
    )

    assert status.claimed_without_proof(repo) == set()


def test_a_claim_from_before_the_proof_rule_is_judged_as_it_was(tmp_path: Path) -> None:
    """An old claim with no trailer is already counted as Done, judged by the audit of 2026-09-17,
    so it is not also unproved. Delete this and old claims are counted on both sides."""
    repo = history(tmp_path, (BEFORE_PROOF, "Build it\n\nCloses: M1.1.1\n"))

    assert status.claimed_without_proof(repo) == set()


def test_a_later_reopens_takes_an_unproved_claim_back(tmp_path: Path) -> None:
    """The newest statement wins, as it does for Done. Delete this and a leaf the owner's audit
    reopened stays built for ever on the strength of the claim it took back."""
    repo = history(
        tmp_path,
        (AT_PROOF, "Build it\n\nCloses: M1.1.1, M1.1.2\n"),
        ("2026-09-19T00:00:00+00:00", "Take one back\n\nReopens: M1.1.1\n"),
    )

    assert status.claimed_without_proof(repo) == {"M1.1.2"}


def test_a_claim_a_later_commit_proves_leaves_the_unproved_set(tmp_path: Path) -> None:
    """A leaf claimed without proof and then claimed again with it is Done, and Done is not built.
    Delete this and a proved leaf is in both figures."""
    repo = history(
        tmp_path,
        (AT_PROOF, "Build it\n\nCloses: M1.1.1\n"),
        ("2026-09-19T00:00:00+00:00", "Show it\n\nCloses: M1.1.1\nProved-on-install: it ran\n"),
    )

    assert status.claimed_without_proof(repo) == set()


# ----------------------------------------------------------------- the figure itself
@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A repository with one done leaf (M0.1.1, proved), one claimed without proof (M0.1.2), tests
    naming M0.1.1, M0.1.2, M1.1.1 and M0.1.4, and the rest untested."""
    repo = history(
        tmp_path,
        (AT_PROOF, "Prove it\n\nCloses: M0.1.1\nProved-in-ci: the unit job runs it\n"),
        ("2026-09-19T00:00:00+00:00", "Build it\n\nCloses: M0.1.2\n"),
    )
    write(
        repo,
        "tests/unit/test_all.py",
        '"""Tests.\n\nTask ids: M0.1.1, M0.1.2, M1.1.1, M0.1.4\n"""\n',
    )
    return repo


def test_built_counts_what_is_done_plus_what_is_built_and_not_yet_proven(tree: Path) -> None:
    """M0.1.1 is done, M0.1.2 is claimed without proof and tested, M1.1.1 is READY and tested, and
    M0.1.4 is tested with no evidence. So done is one, built is three and the unproven two. Delete
    this and the sum, or either half of the evidence, can drift without a test noticing."""
    s = status.build_status(tree, plan(**{"M1.1.1": "2026-10-14"}))

    assert s.done == 1
    assert s.built_unproven == 2
    assert s.built == 3
    assert s.built_task_ids == ["M0.1.2", "M1.1.1"]
    assert s.total == 6
    assert (s.percent, s.built_percent) == (16.7, 50.0)


def test_a_built_leaf_is_never_in_the_done_list_or_the_done_percentage(tree: Path) -> None:
    """The guard the owner asked for: never call built work done. Built leaves are absent from
    `done_task_ids`, the Done percentage is what commits with proof close and nothing more, and a
    built leaf is still listed by its hand-set status. Delete this and a built leaf can slip into
    Done, which is the 1046-task mistake of 2026-09-17 over again."""
    s = status.build_status(tree, plan(**{"M1.1.1": "2026-10-14"}))

    assert s.done_task_ids == ["M0.1.1"]
    assert set(s.built_task_ids).isdisjoint(s.done_task_ids)
    assert s.leaf_status["M1.1.1"].status == "READY FOR TESTING"


def test_a_leaf_both_done_and_hand_set_ready_is_counted_once_as_done(tree: Path) -> None:
    """A stale READY FOR TESTING entry on a leaf a commit has since closed, with a test naming it,
    meets every condition for built except that it is done. It stays done and is not counted a
    second time. Delete this and the two figures overlap, so built is more than done plus the
    unproven and a proven leaf is called built as well."""
    s = status.build_status(tree, plan(**{"M0.1.1": "2026-09-01", "M1.1.1": "2026-10-14"}))

    assert s.done_task_ids == ["M0.1.1"]
    assert "M0.1.1" not in s.built_task_ids
    assert (s.done, s.built_unproven, s.built) == (1, 2, 3)
    assert s.built == s.done + len(s.built_task_ids)


def test_evidence_with_no_test_is_not_built(tree: Path) -> None:
    """M0.1.3 is READY FOR TESTING and no test names it, so it is not built, and M0.1.4 has a test
    and no evidence, so it is not either. Delete this and either half can be dropped from the
    rule with the sum test above still green."""
    s = status.build_status(tree, plan(**{"M0.1.3": "2026-10-14"}))

    assert "M0.1.3" not in s.built_task_ids
    assert "M0.1.4" not in s.built_task_ids
    assert s.built_task_ids == ["M0.1.2"]


def test_each_wave_and_module_reports_what_it_has_built(tree: Path) -> None:
    """Per wave and per module, so the table on /build and the tracker's wave row can show it.
    Wave 0 holds M0.1.1 (done) and M0.1.2 (built); wave 1 holds M1.1.1 (built). Delete this and
    the per-wave figure can be left at zero while the headline moves."""
    s = status.build_status(tree, plan(**{"M1.1.1": "2026-10-14"}))

    waves = {w.wave: w for w in s.waves}
    assert (waves[0].done, waves[0].built, waves[0].total, waves[0].built_percent) == (
        1,
        2,
        4,
        50.0,
    )
    assert (waves[1].done, waves[1].built, waves[1].total, waves[1].built_percent) == (
        0,
        1,
        2,
        50.0,
    )
    modules = {m.module: m for m in s.modules}
    assert (modules["M0"].done, modules["M0"].built) == (1, 2)
    assert (modules["M1"].done, modules["M1"].built) == (0, 1)


def test_an_act_and_a_decided_leaf_are_never_built(tree: Path) -> None:
    """An act is a person's work and a decided leaf is nobody's, so neither is in the total and
    neither can be in the built figure however well tested. Delete this and a leaf counted
    nowhere else is counted as built."""
    modules: list[dict[str, Any]] = json.loads(
        json.dumps(plan(**{"M1.1.1": "2026-10-14"})["modules"])
    )
    modules[0]["leaf_acts"] = {"M0.1.2": {"kind": "ACT", "gate": False}}
    modules[1]["leaf_decided"] = {"M1.1.1": {"kind": "DECIDED", "why": "not needed"}}

    s = status.build_status(tree, {**PLAN, "modules": modules})

    assert s.built_task_ids == []
    assert s.built == s.done


def test_a_repository_with_no_tests_reports_nothing_built_rather_than_raising(
    tmp_path: Path,
) -> None:
    """A checkout with no `tests` directory, as the other fixtures here are, has nothing that can
    prove a leaf. Delete this and the first status built from such a tree fails to read it."""
    repo = history(tmp_path, (AT_PROOF, "Build it\n\nCloses: M0.1.1\n"))

    s = status.build_status(repo, plan(**{"M0.1.1": "2026-10-14"}))

    assert (s.built, s.built_unproven, s.built_task_ids) == (0, 0, [])


# ------------------------------------------------------ the real repository's figure
def test_the_real_figure_is_made_of_real_leaves_and_never_overlaps_done() -> None:
    """Read from the committed work breakdown and this repository's history and tests. Every built
    leaf is a buildable leaf, none is done, and built is exactly done plus the unproven. Delete
    this and a mistaken figure reaches the owner's page with only a hand-built fixture checked."""
    wbs = status.load_wbs(REPO_ROOT / "docs" / "wbs.json")

    s = status.build_status(REPO_ROOT, wbs)

    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert set(s.built_task_ids) <= leaves
    assert set(s.built_task_ids).isdisjoint(s.done_task_ids)
    assert s.built == s.done + s.built_unproven == s.done + len(s.built_task_ids)
    assert s.built >= s.done
    assert sum(w.built for w in s.waves) == s.built
    assert all(w.built >= w.done for w in s.waves)


# -------------------------------------------------------------------- what the page says
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> str:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    with TestClient(create_app(Settings(env="production"))) as client:
        return client.get("/build").text


FIGURES: dict[str, Any] = {
    "commit": "abc1234",
    "total": 200,
    "done": 80,
    "percent": 40.0,
    "built": 130,
    "built_percent": 65.0,
    "built_unproven": 50,
    "current_wave": 0,
    "waves": [
        {
            "wave": 0,
            "name": "Foundation",
            "total": 200,
            "done": 80,
            "percent": 40.0,
            "built": 130,
            "built_percent": 65.0,
        }
    ],
}


def test_the_page_shows_done_and_built_side_by_side_with_their_own_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The headline is two figures and each says what it is: Done keeps its name and meaning, and
    Built says it is CI-checked and not yet shown working on the install. Delete this and the page
    can show one figure under the other's name, which is how built work gets called done."""
    page = served(tmp_path, monkeypatch, FIGURES)

    assert docs_routes.DONE_LABEL in page
    assert docs_routes.BUILT_LABEL in page
    # Against words outside the constants, which a test that imported them would only compare
    # with themselves: Done keeps its name, and Built says what it is not yet.
    assert docs_routes.DONE_LABEL.startswith("Done")
    assert docs_routes.BUILT_LABEL.startswith("Built")
    assert "CI-checked, not yet shown working on the install" in docs_routes.BUILT_LABEL
    assert re.search(r'<div class="fig">.*?40\.0%.*?80 of 200 buildable tasks', page, re.S)
    assert re.search(r'<div class="fig built">.*?65\.0%.*?130 of 200 buildable tasks', page, re.S)
    assert "80 done plus 50 built and not yet shown working" in page


def test_the_page_explains_the_difference_in_plain_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The note says what Done and Built mean, that built is never counted as done and that a
    tester will later promote built tasks. Delete this and the second figure arrives with no
    explanation, which reads as a softer version of the first."""
    page = served(tmp_path, monkeypatch, FIGURES)

    assert docs_routes.DONE_VERSUS_BUILT in page
    assert "never counted as done" in docs_routes.DONE_VERSUS_BUILT
    assert "A tester will later" in docs_routes.DONE_VERSUS_BUILT
    assert "promote built tasks to Done" in docs_routes.DONE_VERSUS_BUILT


def test_the_wave_table_has_a_built_column_beside_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each wave row says how many of its tasks are built, after the percentage done. Delete this
    and the table can lose the column while the headline keeps it."""
    page = served(tmp_path, monkeypatch, FIGURES)

    header = re.search(r"<thead>.*?</thead>", page, re.S)
    assert header is not None
    assert re.search(r"Done</th><th></th>.*?%</th>.*?Built</th>", header.group(0), re.S)
    row = re.search(r"<tr><td>Wave 0</td>.*?</tr>", page)
    assert row is not None
    cells = re.findall(r'<td class="n">([^<]*)</td>', row.group(0))
    assert cells[:3] == ["80/200", "40.0%", "130/200"]


def test_a_status_file_with_no_built_figure_says_so_rather_than_showing_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file baked before the figure existed carries no `built`. A zero would read as nothing
    being built, so the page says this build did not report one. Delete this and an old status
    file shows Built as 0%."""
    body = {k: v for k, v in FIGURES.items() if k not in ("built", "built_percent")}
    body["waves"] = [{k: v for k, v in FIGURES["waves"][0].items() if not k.startswith("built")}]

    page = served(tmp_path, monkeypatch, body)

    assert "this build did not report a built figure" in page
    assert re.search(r'<div class="fig built">.*?n/a', page, re.S)


# ----------------------------------------------------------------- what the tracker does
def tracker_html() -> str:
    return (REPO_ROOT / "docs" / "tracker.html").read_text(encoding="utf-8")


def test_the_tracker_shows_done_and_built_with_the_same_labels() -> None:
    """The committed tracker carries both labels and the note, so it says the same as /build. The
    tracker is generated by `docs/wbs/render.js`, so this reads the output. Delete this and the
    tracker can drop Built or rename Done while /build keeps both."""
    html = tracker_html()

    assert "done (shown working)" in html
    assert "built (CI-checked, not yet shown working on the install)" in html
    assert "A tester will later promote built tasks to Done." in html
    assert 'id="pctBuilt"' in html
    assert "data-wavebuilt=" in html


def test_the_tracker_never_ticks_a_built_leaf_as_done() -> None:
    """A built leaf is read into a set of its own and never into `state`, which is what ticks a
    leaf and counts it done. Asserted on the two assignments: `state` is filled from
    `done_task_ids` and only that. Delete this and a later edit can fill `state` from the built
    list, which would tick built work as done on the page the owner opens."""
    html = tracker_html()

    assert "(st.done_task_ids||[]).forEach(function(id){state[id]=1});" in html
    assert "(st.built_task_ids||[]).forEach(function(id){builtOnly[id]=1});" in html
    assert not re.search(r"built_task_ids[^;]*state\[", html)
    assert 'li.leaf.built .lbl::after{content:"BUILT"' in html
