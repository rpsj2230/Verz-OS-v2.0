"""The owner's requirements register, and the rules that turn the build red when a row is uncovered.

The first half reads the real `docs/requirements/register.json` against the real `docs/wbs.json`
and `docs/needs-rupash.md`, one test per rule, so a failure names the rule a new row broke and
lists every row that broke it. The second half holds each rule to a fixture with a sibling that
proves a good row still passes, because a check tested only by its refusals is satisfied by one
that refuses everything, and a register that is always red gets its test deleted.

Task ids: none
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain import docs_routes
from brain.app import Settings, create_app
from brain.requirements import (
    A_DECIDED_LEAF_IS_A_NARROWING_AND_A_NARROWING_IS_ASKED,
    A_DECISION_NAMES_THE_QUESTION_THAT_DECIDED_IT,
    A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED,
    A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD,
    AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING,
    ONE_ID_IS_ONE_REQUIREMENT,
    Assessment,
    Register,
    assess,
    load_register,
    main,
    needs_items,
)
from brain.status import load_wbs

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"


def real() -> Assessment:
    """The real register, judged without commits: none of the coverage rules reads one."""
    return assess(
        load_register(DOCS / "requirements" / "register.json"),
        load_wbs(DOCS / "wbs.json"),
        (),
        needs_items(DOCS / "needs-rupash.md"),
    )


def broken(assessment: Assessment, rule: str) -> list[str]:
    return [str(f) for f in assessment.findings if f.rule == rule]


# ----------------------------------------------------------------- the real register
def test_the_register_holds_requirements() -> None:
    """Every rule below is a claim about each row, and an empty register satisfies all of them.
    Delete this and the file can be emptied, or fail to load as a list, with every other test in
    the first half still green."""
    assert len(real().standings) >= 10


def test_every_requirement_in_the_register_names_a_task() -> None:
    """The reason the register exists: capabilities the owner asked for never became tasks, and
    nothing noticed. Delete this and a row with no leaf is a requirement nobody will build that
    the build accepts."""
    assert broken(real(), A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD) == []


def test_every_id_the_register_names_is_a_leaf_of_the_work_breakdown() -> None:
    """A mistyped id or a group looks exactly like coverage in the file. Delete this and a row
    can point at `M17.4` or at an id that was renumbered away, and read as covered for ever."""
    assert broken(real(), AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING) == []


def test_every_requirement_in_the_register_names_a_proof_task() -> None:
    """The tracker has already shown work as done that the owner's install did not. Delete this
    and a requirement can be counted delivered because its parts were ticked, with nothing
    proving it works on an install."""
    assert broken(real(), A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED) == []


def test_no_requirement_rests_on_a_decided_leaf_without_naming_its_decision() -> None:
    """The other half of how requirements went missing: a narrowing decided in a docstring and
    never asked. Delete this and a row can rest on a leaf decided against with no trace of who
    decided it."""
    assert broken(real(), A_DECIDED_LEAF_IS_A_NARROWING_AND_A_NARROWING_IS_ASKED) == []


def test_every_decision_in_the_register_names_an_item_the_owner_was_asked() -> None:
    """A decision that names no item of `docs/needs-rupash.md` is a docstring by another name.
    Delete this and `decision` can hold any sentence, which satisfies the rule above while
    recording nothing anybody can find."""
    assert broken(real(), A_DECISION_NAMES_THE_QUESTION_THAT_DECIDED_IT) == []


def test_no_two_requirements_in_the_register_share_an_id() -> None:
    """The register is filled from several tracings at once, and each numbers its own rows.
    Delete this and two requirements can share an id, so a finding or a delivery names one and
    means either."""
    assert broken(real(), ONE_ID_IS_ONE_REQUIREMENT) == []


def test_the_register_is_clean_by_the_command_a_person_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Whoever fills the register runs `python -m brain.requirements`, which reads the commits
    as well, from wherever the module finds itself. Delete this and the command can disagree
    with the tests above, or fail on the real history, and the person filling the register is
    told the opposite of what CI says."""
    assert main() == 0
    assert "covered by a task and a proof" in capsys.readouterr().out


# ----------------------------------------------------------------- the rules, on fixtures
WBS: dict[str, Any] = {
    "modules": [
        {
            "id": "M1",
            "name": "One",
            "wave": 0,
            "leaf_ids": ["M1.1.1", "M1.1.2", "M1.2.1", "M1.2.2"],
            "leaf_decided": {"M1.2.1": {"kind": "DECIDED", "why": "item 58"}},
        }
    ]
}

ITEMS = frozenset({58, 61})


def row(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "OWN-1.1",
        "source": "a source",
        "area": "Agents",
        "requirement": "a requirement",
        "leaves": ["M1.1.1"],
        "proof": ["M1.1.2"],
        "decision": None,
    }
    fields.update(changes)
    return fields


def judge(*rows: dict[str, Any], closed: tuple[str, ...] = ()) -> Assessment:
    return assess(Register.model_validate({"requirements": rows}), WBS, closed, ITEMS)


def rules(assessment: Assessment) -> list[str]:
    return [f.rule for f in assessment.findings]


def test_a_row_with_a_leaf_and_a_proof_and_no_decided_leaf_has_no_finding() -> None:
    """The sibling of every refusal below. Delete this and a check that reports every row, or
    that reads a proof leaf as unknown, passes every other test in this half."""
    assessment = judge(row(), row(id="OWN-1.2", leaves=["M1.1.1", "M1.2.2"]))
    assert assessment.findings == ()
    assert [s.covered for s in assessment.standings] == [True, True]


def test_a_requirement_naming_no_task_is_reported() -> None:
    """The failure the register was built for. Delete this and an empty `leaves` passes."""
    assessment = judge(row(leaves=[]))
    assert rules(assessment) == [A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD]
    assert [str(f) for f in assessment.findings] == [
        f"OWN-1.1 {A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD}"
    ]


def test_a_requirement_naming_no_proof_task_is_reported() -> None:
    """Delete this and an empty `proof` passes, and nothing then stops a requirement being
    counted done on its parts alone."""
    assessment = judge(row(proof=[]))
    assert rules(assessment) == [A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED]


def test_an_id_that_is_no_leaf_is_reported_by_name_wherever_it_is_named() -> None:
    """In `leaves` and in `proof` alike, and named, so whoever fixes the row knows which id.
    Delete this and a check reading only `leaves` passes, which leaves every proof unchecked."""
    assessment = judge(row(leaves=["M1.1.1", "M9.9.9"], proof=["M1.1.3"]))
    (finding,) = assessment.findings
    assert finding.rule == AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING
    assert finding.ids == ("M9.9.9", "M1.1.3")
    assert str(finding) == f"OWN-1.1 {AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING} (M9.9.9, M1.1.3)"


def test_a_group_id_covers_nothing() -> None:
    """`M1.1` is real and is not a leaf, and an ancestor closes none of its children. Delete this
    and a check that accepts any id with a real prefix passes."""
    assessment = judge(row(proof=["M1.1"]))
    assert rules(assessment) == [AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING]


def test_a_decided_leaf_with_no_decision_is_reported_in_leaves_and_in_proof() -> None:
    """A narrowing is a question to the owner. Delete this and a row can rest on a leaf decided
    against, as a building leaf or as its proof, with nobody asked."""
    assessment = judge(
        row(leaves=["M1.2.1"]),
        row(id="OWN-1.2", proof=["M1.2.1"]),
    )
    assert rules(assessment) == [A_DECIDED_LEAF_IS_A_NARROWING_AND_A_NARROWING_IS_ASKED] * 2
    assert [f.ids for f in assessment.findings] == [("M1.2.1",), ("M1.2.1",)]


def test_a_decided_leaf_with_a_decision_naming_an_item_is_covered() -> None:
    """The sibling: the rule asks for the decision, not for the leaf to be removed. Delete this
    and a check refusing every decided leaf passes, which leaves the owner's recorded answers
    with nowhere to go."""
    assessment = judge(row(leaves=["M1.2.1"], decision="needs-rupash 58: not needed yet"))
    assert assessment.findings == ()


@pytest.mark.parametrize(
    "decision",
    [
        "decided in the architecture",
        "needs-rupash 999",
        "needs-rupash 58, and needs-rupash 999",
    ],
)
def test_a_decision_that_names_no_item_the_owner_was_asked_is_reported(decision: str) -> None:
    """No item at all, an item that does not exist, and one real item beside one that does not.
    Delete this and any of the three satisfies the decided-leaf rule while naming nothing a
    person can open."""
    assessment = judge(row(decision=decision))
    assert rules(assessment) == [A_DECISION_NAMES_THE_QUESTION_THAT_DECIDED_IT]


def test_a_decision_naming_several_real_items_is_accepted() -> None:
    """The sibling of the mixed case above. Delete this and a check that accepts only one item,
    or reads only the first, passes."""
    assert judge(row(decision="needs-rupash 58 and needs-rupash 61")).findings == ()


def test_two_rows_with_one_id_are_both_reported() -> None:
    """Both, because neither is the right one to keep. Delete this and two requirements can share
    an id; the clean fixture above is the sibling proving distinct ids pass."""
    assessment = judge(row(), row(requirement="another"))
    assert rules(assessment) == [ONE_ID_IS_ONE_REQUIREMENT] * 2


def test_a_row_carrying_a_field_the_register_does_not_define_is_refused() -> None:
    """The tracing writes `conflict` beside each row, and a narrowing kept there is read by no
    rule. Delete this and it loads in silence."""
    with pytest.raises(ValidationError):
        Register.model_validate({"requirements": [row(conflict="decided against the owner")]})


def test_a_register_carrying_anything_beside_its_rows_is_refused() -> None:
    """A tracing can also write a list of gaps, and a gap is a requirement with no task. Delete
    this and a `gaps` list beside `requirements` loads with every gap unread, which is the
    failure the register exists for, arriving in the register itself."""
    with pytest.raises(ValidationError):
        Register.model_validate({"requirements": [row()], "gaps": [row(id="OWN-9.1")]})


def test_a_row_without_a_decision_field_is_refused() -> None:
    """`decision` is written out as null rather than left out, so a row says it was checked for
    a narrowing. Delete this and a default can make an absent field read as no narrowing."""
    fields = row()
    del fields["decision"]
    with pytest.raises(ValidationError):
        Register.model_validate({"requirements": [fields]})


# ----------------------------------------------------------------- delivered
def test_a_clean_row_with_every_leaf_and_proof_closed_is_delivered() -> None:
    """The sibling of every refusal below. Delete this and a count of delivered that is always
    zero passes them all."""
    (standing,) = judge(row(), closed=("M1.1.1", "M1.1.2")).standings
    assert standing.delivered


def test_a_row_with_a_building_leaf_open_is_not_delivered() -> None:
    """Delete this and a proof closed ahead of the work it proves delivers the requirement."""
    (standing,) = judge(row(leaves=["M1.1.1", "M1.2.2"]), closed=("M1.1.1", "M1.1.2")).standings
    assert not standing.delivered


def test_a_row_with_its_proof_open_is_not_delivered() -> None:
    """The rule the constant states: ticked parts are not a delivery. Delete this and a row is
    delivered the moment its building leaves close."""
    (standing,) = judge(row(), closed=("M1.1.1",)).standings
    assert not standing.delivered


def test_a_row_with_no_proof_is_not_delivered_however_many_leaves_are_closed() -> None:
    """Every id it names is closed, because it names no proof. Delete this and `all` over an
    empty proof delivers it."""
    (standing,) = judge(row(proof=[]), closed=("M1.1.1",)).standings
    assert not standing.delivered


def test_a_group_named_in_a_commit_subject_does_not_deliver_a_row() -> None:
    """`closed_task_ids` reports whatever a subject named, groups included. Delete this and a row
    whose proof is `M1.1` is delivered by a commit titled `M1.1: ...`."""
    (standing,) = judge(row(proof=["M1.1"]), closed=("M1.1.1", "M1.1")).standings
    assert not standing.delivered


def test_the_summary_counts_total_covered_and_delivered_apart() -> None:
    """Three rows, one of each standing. Delete this and the page's three figures can be one
    figure printed three times."""
    assessment = judge(
        row(),
        row(id="OWN-1.2", leaves=["M1.2.2"]),
        row(id="OWN-1.3", proof=[]),
        closed=("M1.1.1", "M1.1.2"),
    )
    assert assessment.summary() == {"total": 3, "covered": 2, "delivered": 1}


# ----------------------------------------------------------------- reading needs-rupash
def test_the_items_a_decision_may_name_are_the_numbered_headings_of_needs_rupash(
    tmp_path: Path,
) -> None:
    """Open and answered alike, second-level headings only. Delete this and a sub-heading
    numbered like an item, or only the first item in the file, is what a decision is checked
    against."""
    needs = tmp_path / "needs-rupash.md"
    needs.write_text(
        "# Needs Rupash\n\n# Open\n\n## 63. Open one\n\n### 4. A step\n\n"
        "# Answered\n\n## 58. Answered one\n\nprose ## 7. not a heading\n",
        encoding="utf-8",
    )
    assert needs_items(needs) == {63, 58}


def test_with_no_needs_rupash_every_decision_is_a_finding(tmp_path: Path) -> None:
    """Delete this and a missing file can raise, or pass every decision."""
    assert needs_items(tmp_path / "absent.md") == frozenset()


# ----------------------------------------------------------------- the command
def write_docs(docs: Path, *rows: dict[str, Any], wbs: bool = True) -> None:
    (docs / "requirements").mkdir(parents=True)
    (docs / "requirements" / "register.json").write_text(
        json.dumps({"requirements": list(rows)}), encoding="utf-8"
    )
    if wbs:
        (docs / "wbs.json").write_text(json.dumps(WBS), encoding="utf-8")
    (docs / "needs-rupash.md").write_text("# Answered\n\n## 58. One\n", encoding="utf-8")


def test_the_command_fails_while_a_row_has_a_finding_and_passes_when_none_has(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the command can print findings and exit zero, which is the promise the
    owner asked not to be given."""
    bad, good = tmp_path / "bad", tmp_path / "good"
    write_docs(bad / "docs", row(proof=[]))
    write_docs(good / "docs", row())

    assert main(bad) == 1
    assert A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED in capsys.readouterr().out
    assert main(good) == 0


def test_the_command_counts_a_requirement_delivered_from_the_commits_that_closed_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command reads git through `closed_task_ids`, by subject and by `Closes:` trailer.
    Delete this and the command can report nothing delivered for ever, because every other test
    of it runs where there is no history."""
    write_docs(tmp_path / "docs", row(), row(id="OWN-1.2", leaves=["M1.2.2"]))

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    git("add", "-A")
    git("commit", "-m", "M1.1.1: the building leaf\n\nCloses: M1.1.2\nProved-in-ci: unit\n")

    assert main(tmp_path) == 0
    assert "2 requirements, 2 covered by a task and a proof, 1 delivered" in capsys.readouterr().out


def test_the_command_fails_where_there_is_no_register(tmp_path: Path) -> None:
    """A missing register is not a clean one. Delete this and deleting the file turns the check
    green."""
    assert main(tmp_path) == 1


# ----------------------------------------------------------------- the build pages
@pytest.fixture
def pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "status.json").write_text(
        json.dumps({"commit": "abc1234", "done_task_ids": ["M1.1.1", "M1.1.2"], "waves": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(docs_routes, "DOCS", docs)
    yield docs


def test_the_build_page_and_the_status_feed_state_the_three_requirement_figures(
    pages: Path,
) -> None:
    """Delivered is read from the baked status file, because the image has no git history.
    Delete this and the figures can vanish from the page, or be computed against nothing
    closed, with every rule above still green."""
    write_docs(pages, row(), row(id="OWN-1.2", leaves=["M1.2.2"]), row(id="OWN-1.3", proof=[]))
    with TestClient(create_app(Settings(env="production"))) as client:
        page = client.get("/build").text
        feed = client.get("/api/status.json").json()

    assert "3 requirements, 2 covered by a task and a proof, 1 delivered" in page
    assert feed["requirements"] == {"total": 3, "covered": 2, "delivered": 1}


def test_a_register_with_no_work_breakdown_beside_it_covers_nothing(pages: Path) -> None:
    """Every id then names no leaf. Delete this and a missing `wbs.json` can take the build page
    down instead of reporting nothing covered."""
    write_docs(pages, row(), wbs=False)
    with TestClient(create_app(Settings(env="production"))) as client:
        assert client.get("/api/status.json").json()["requirements"] == {
            "total": 1,
            "covered": 0,
            "delivered": 0,
        }


def test_a_build_with_no_register_says_so_rather_than_counting_zero(pages: Path) -> None:
    """A count of zero says nothing was asked for. Delete this and an image missing its register
    reads as a project with no requirements."""
    with TestClient(create_app(Settings(env="production"))) as client:
        page = client.get("/build").text
        feed = client.get("/api/status.json").json()

    assert "no requirements register published" in page
    assert "0 requirements" not in page
    assert feed["requirements"] is None
