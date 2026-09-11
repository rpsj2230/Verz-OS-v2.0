"""The work in the plan no commit can close: the flags, the generated list, and the gate.

Three records have to agree and they are written in three languages. `docs/wbs/acts.js` holds
the flags, `docs/wbs.json` is what the export makes of them, `docs/tracker.html` is what the
renderer makes of them, and `docs/delivery-checklist.md` is what Python makes of them. Every
test here compares two of those against each other rather than against a restatement in this
file, because a restatement is the constant compared against itself that `CLAUDE.md` warns
about, and a checklist that agrees only with the test that reads it is a checklist.

The gate is the other half. `brain.migration.decommission` refuses to report a completed
cutover while any act with a security consequence is unrecorded, and the tests for it live
here rather than beside the rest of the decommission because the list they check belongs to
`brain.migration.checklist`.

Task ids: none
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.migration.checklist import (
    CUTOVER_GATED_ACTS,
    Act,
    ActKind,
    ChecklistError,
    act_group_names,
    checklist_markdown,
    gated_acts,
    load_acts,
    main,
)
from brain.migration.decommission import (
    ActRecord,
    CompletedCutover,
    Decommission,
    DecommissionError,
    FinalBackup,
    Revocation,
    ScheduledJob,
    decommission_gaps,
    may_report_complete,
    security_acts_outstanding,
)

REPO = Path(__file__).resolve().parents[2]
WBS = REPO / "docs" / "wbs.json"
CHECKLIST = REPO / "docs" / "delivery-checklist.md"
TRACKER = REPO / "docs" / "tracker.html"

#: Pinned far from any wall clock, for the reason CLAUDE.md gives about fixtures with dates.
CUT_OVER = datetime(2030, 6, 1, tzinfo=UTC)
LATER = CUT_OVER + timedelta(days=1)
LATER_STILL = CUT_OVER + timedelta(days=2)

#: A task id anywhere in a document, leaf or group. Matches `brain.ops.sweeps.TASK_ID_RE`.
TASK_ID = re.compile(r"\bM\d+(?:\.\d+){1,4}\b")

#: A checkbox line of the generated list.
CHECKLIST_ITEM = re.compile(r"^- \[ \] `(M[\d.]+)` ", re.M)

#: A leaf checkbox in the tracker that carries an act flag.
TRACKER_ACT = re.compile(r'data-id="(M[\d.]+)"[^>]*data-act="(ACT|UNBUILDABLE)"')


def _wbs() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(WBS.read_text(encoding="utf-8"))
    return loaded


def _flags() -> dict[str, dict[str, Any]]:
    """Every act flag the exported work breakdown carries, by leaf id."""
    found: dict[str, dict[str, Any]] = {}
    for module in _wbs()["modules"]:
        found.update(module.get("leaf_acts", {}))
    return found


def _a_wbs(*, ids: list[str], texts: list[str], acts: dict[str, Any]) -> dict[str, Any]:
    """One module's worth of work breakdown, in the shape `export.js` writes."""
    return {
        "generated_by": "a test",
        "modules": [
            {
                "id": "M90",
                "name": "A module",
                "wave": 5,
                "leaf_ids": ids,
                "leaf_texts": texts,
                "leaf_waves": {},
                "leaf_acts": acts,
                "act_groups": {"M90.1": "A group"},
            }
        ],
    }


def _written(tmp_path: Path, wbs: dict[str, Any]) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / "wbs.json"
    path.write_text(json.dumps(wbs), encoding="utf-8", newline="\n")
    return path


# ------------------------------------------------------------ the flags and what reads them
def test_the_generated_checklist_holds_every_leaf_the_plan_flags_as_an_act() -> None:
    """**This is the property the whole arrangement exists for.** A delivery checklist is only
    worth having if it cannot go short, and it goes short by somebody generating it from a
    loop that skips a case: a leaf whose kind is unrecognised, a module iterated in the wrong
    order, a filter that was right when it was written. Compared against the flags in the
    exported plan rather than against a list in this file, because a list here is a second
    copy that drifts with the first and agrees with nothing.

    Delete this and a leaf can drop out of the generator silently, which is the failure the
    generator was written to prevent: the work with a security consequence is on this list and
    a shorter list still looks complete."""
    generated = checklist_markdown(WBS)
    listed = set(CHECKLIST_ITEM.findall(generated))

    assert listed == set(_flags())
    assert listed, "the plan flags no acts at all, so this test is asserting nothing"


def test_every_task_id_in_the_generated_checklist_names_a_leaf_or_a_group_holding_one() -> None:
    """The other direction, and the one a reader trusts without checking. A line naming a task
    id that is not in the plan sends somebody to look for work that is not there, and a
    heading over a group id that holds no act is a section somebody reads as complete.

    Leaf ids are positional here: an id keeps resolving after a group is inserted above it, to
    different work. So this asserts every id in the document resolves to something the plan
    actually declares, rather than that it looks like an id.

    Delete this and the checklist can name a group where a leaf was meant, which is the exact
    mistake `brain.ops.sweeps` reports thirty-two of in the commit record."""
    wbs = _wbs()
    leaves = {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}
    groups = {m["id"] for m in wbs["modules"]}
    for module in wbs["modules"]:
        groups.update(module.get("act_groups", {}))
    flagged = set(_flags())

    for found in TASK_ID.findall(checklist_markdown(WBS)):
        assert found in leaves or found in groups, f"{found} names nothing in the plan"
        if found in leaves:
            assert found in flagged, f"{found} is on the checklist and is not flagged as an act"


def test_the_delivery_checklist_on_disk_is_what_the_generator_produces() -> None:
    """The file is generated and this is what makes that true rather than intended. A document
    anybody can edit is a document somebody has edited, and the edit that matters is the one
    that removes a line: a hand-trimmed checklist is indistinguishable from a complete one.

    Byte equality rather than a set comparison, because the argument for a generated document
    is that nothing about it is typed, and prose somebody added by hand is the beginning of a
    second source of truth.

    Delete this and the file drifts from the flags the first time somebody fixes a typo in it,
    and every other test here keeps passing, because they read the generator."""
    assert CHECKLIST.exists(), "run `uv run python -m brain.migration.checklist`"

    assert CHECKLIST.read_text(encoding="utf-8") == checklist_markdown(WBS)


def test_a_flag_naming_a_leaf_the_plan_does_not_have_is_refused(tmp_path: Path) -> None:
    """Leaf ids are positional. `M37.2.6.5` means the fifth key of the sixth group of the
    second task, and nothing anchors it to a sentence, so inserting a group above a flagged
    leaf repoints every flag after it at different work without changing a character. The
    generators refuse when a flag's recorded sentence stops matching; this is the case they
    cannot see, which is a `wbs.json` edited by hand or left behind by a failed export.

    Delete this and a flag can name a group id, which resolves to nothing and drops out of the
    checklist silently, taking one act with it."""
    wbs = _a_wbs(
        ids=["M90.1.1"],
        texts=["A thing somebody does"],
        acts={"M90.1": {"kind": "ACT", "gate": False, "why": ""}},
    )

    with pytest.raises(ChecklistError, match="named by no leaf"):
        load_acts(_written(tmp_path, wbs))


def test_an_act_carries_the_sentence_the_plan_gives_its_leaf(tmp_path: Path) -> None:
    """The positive case for the reader, and the reason the checklist can be read without the
    tracker open beside it. An `Act` with a flag and no sentence is a tick with an id on it.

    Delete this and `load_acts` can return the flags alone and every refusal above still
    fires, because a refusal test is satisfied by a function that refuses everything."""
    wbs = _a_wbs(
        ids=["M90.1.1", "M90.1.2"],
        texts=["A thing somebody does", "A thing somebody commits"],
        acts={"M90.1.1": {"kind": "UNBUILDABLE", "gate": True, "why": "it names a client"}},
    )

    found = load_acts(_written(tmp_path, wbs))

    assert found == (
        Act(
            leaf="M90.1.1",
            text="A thing somebody does",
            kind=ActKind.UNBUILDABLE,
            gates_cutover=True,
            why="it names a client",
        ),
    )
    assert act_group_names(_written(tmp_path, wbs))["M90.1"] == "A group"


def test_an_act_flagged_against_a_leaf_with_no_sentence_is_refused() -> None:
    """A flag whose leaf has no sentence is a checklist line that says nothing, and somebody
    reading it has an id and no idea what to do. Refused where the record is built rather than
    checked in the generator, so no other producer can make one.

    Delete this and an act with an empty sentence renders as a bare id on the checklist, which
    reads as a formatting bug rather than as a missing task."""
    with pytest.raises(ChecklistError, match="no sentence"):
        Act(leaf="M90.1.1", text="  ", kind=ActKind.ACT, gates_cutover=False, why="")


def test_the_generator_refuses_a_repository_with_no_work_breakdown(tmp_path: Path) -> None:
    """`main` takes the repository as a parameter so this branch can be reached at all, which
    is the argument `brain.status.main` makes for the same shape. A generator that can only be
    pointed at this repository has a missing-file branch nothing runs, and CI is where it
    would first execute.

    Delete this and the branch goes untested, and a missing work breakdown writes an empty
    checklist over the real one rather than failing."""
    assert main(repo=tmp_path) == 1


def test_generating_the_checklist_writes_the_file_and_reports_what_it_holds(
    tmp_path: Path,
) -> None:
    """The positive case for `main`, and the one the pre-commit habit depends on.

    Delete this and the refusal above is satisfied by a `main` that returns 1 for every
    repository, so nobody would notice the generator no longer writing anything."""
    _written(
        tmp_path,
        _a_wbs(
            ids=["M90.1.1"],
            texts=["A thing somebody does"],
            acts={"M90.1.1": {"kind": "ACT", "gate": False, "why": ""}},
        ),
    )

    assert main(repo=tmp_path) == 0
    written = (tmp_path / "docs" / "delivery-checklist.md").read_text(encoding="utf-8")
    assert "`M90.1.1` A thing somebody does" in written
    assert "1 items, 0 of which gate the cutover." in written


# ---------------------------------------------------------- the two records of the same flags
def test_the_tracker_and_the_work_breakdown_flag_the_same_leaves() -> None:
    """Two programs in two languages read one source and both are shown to a client. `render.js`
    writes the tracker, `export.js` writes the JSON, and they number the tree separately: this
    repository has already shipped a page where the two disagreed about which wave a leaf was
    in, and the owner found it rather than a test.

    The same failure applies to a flag with more consequence, because an act the tracker does
    not mark is an act somebody reads as ordinary buildable work and waits for.

    Delete this and one of the two generators can be run without the other, which is exactly
    what happens when somebody edits the flags and re-exports without re-rendering."""
    marked = dict(TRACKER_ACT.findall(TRACKER.read_text("utf-8")))
    flags = _flags()

    assert marked == {leaf: flag["kind"] for leaf, flag in flags.items()}


def test_the_tracker_counts_the_buildable_leaves_as_the_total_less_the_acts() -> None:
    """The decision this was built for: the percentage was mixing work that closes when it is
    written with work that closes when a person does something on a day with a client, so it
    stops rising at around 86 percent for a reason that is not the build stalling. The tracker
    reports both numbers, and this is what stops the buildable one being typed.

    Delete this and the figure on the page can disagree with the flags underneath it, which is
    a number a client reads and nobody re-derives."""
    html = TRACKER.read_text("utf-8")
    total = sum(len(m["leaf_ids"]) for m in _wbs()["modules"])
    acts = len(_flags())

    buildable = re.search(r'id="cBuild">0</b> of (\d+)', html)
    stated_acts = re.search(r'id="cActs">(\d+)', html)
    assert buildable is not None and stated_acts is not None
    assert int(buildable.group(1)) == total - acts
    assert int(stated_acts.group(1)) == acts


def test_the_four_leaves_that_name_one_companys_things_are_recorded_as_unbuildable() -> None:
    """The first rule of this repository is that no company's details go into it, and four
    leaves of the plan ask for exactly that: how many house skills there are, four of them by
    name, which chat groups each agent sits in, and what the outgoing vendor produced. They
    cannot be code here whoever writes them, and undone and unbuildable look identical on a
    tracker while meaning opposite things.

    The ids are pinned because the classification is a judgement rather than a derivation, and
    a judgement nobody wrote down is one the next reader has to make again.

    Delete this and the four can be quietly reclassified as ordinary acts, and somebody spends
    a day trying to make one fit."""
    unbuildable = {
        leaf for leaf, flag in _flags().items() if flag["kind"] == ActKind.UNBUILDABLE.value
    }

    assert unbuildable == {"M37.2.1.1", "M37.2.1.5", "M37.2.1.6", "M37.2.2.1"}
    assert all(flag["why"] for leaf, flag in _flags().items() if leaf in unbuildable)


# ------------------------------------------------------------------------ the cutover gate
def test_the_gated_ids_are_exactly_the_ones_the_plan_flags_as_gating() -> None:
    """**The gate's list is a constant and this is what stops it being a second opinion.**
    `CUTOVER_GATED_ACTS` is written in Python rather than read out of the plan at the moment
    the gate runs, because a required list loaded from a document has a state where the
    document is missing, stale, or regenerated with a leaf unflagged, and in every one of them
    the gate finds nothing required and reports a clean cutover. That failure is silent and
    permissive, which is the direction that ships.

    The cost of that choice is two records, and this is the test that pays it: the constant is
    compared against the flags in the plan, which is a comparison against something outside
    itself rather than the constant compared against a restatement of itself.

    **The literal below is a third copy and it is deliberate.** Two records compared against
    each other both move when one edit touches both, and an agent adding a gated act edits the
    plan and the constant in the same breath. The list written out here is the one a reviewer
    reads, so widening what gates a client's cutover costs three deliberate edits rather than
    two mechanical ones. That is the whole of what it buys and it is worth the friction: this
    set is the difference between a cutover reported complete and a cutover that was.

    Two were added on 2026-09-11 and neither came from the plan. Both administrative consoles
    on the first deployment were measured answering from the open internet, so a second factor
    on the control panel and the deletion of a bootstrap administrator joined the set. The
    owner asked for them at go-live rather than now, which is right: nothing holds client data
    yet, and a hardening step taken before the thing it protects exists is one nobody
    re-checks on the day it matters. Gating the cutover is exactly how a step deferred to that
    day is not forgotten on it.

    Delete this and the two drift, and the one that drifts is whichever nobody is looking at,
    which is the gate."""
    assert set(CUTOVER_GATED_ACTS) == set(gated_acts(load_acts(WBS)))
    assert set(CUTOVER_GATED_ACTS) == {
        "M37.2.5.4",
        "M37.2.6.1",
        "M37.2.6.2",
        "M37.2.6.5",
        "M37.4.1.3",
        "M37.6.1.1",
        "M37.6.1.2",
    }


def test_every_gated_leaf_is_also_flagged_as_work_for_a_person() -> None:
    """A gated leaf that is not an act would be a commit the cutover waits for, which is a
    build gate wearing a delivery gate's clothes and would refuse a cutover until somebody
    wrote code on the day.

    Delete this and the two flags can come apart, and the gate starts refusing for a reason
    nobody on the client's site can act on."""
    flags = _flags()

    for leaf in CUTOVER_GATED_ACTS:
        assert leaf in flags, f"{leaf} gates the cutover and is not flagged as an act"


def test_a_cutover_cannot_be_reported_complete_while_a_security_act_is_unrecorded() -> None:
    """**This is the answer to the objection that a list nothing gates is a list nobody
    reads.** An OAuth grant nobody withdrew is how an outgoing vendor keeps reading a client's
    mail after everybody believes the account is closed, and it is exactly the item that gets
    ticked in a meeting rather than done. So the report refuses rather than carrying a note.

    Delete this and the five acts with a security consequence become five lines in a document,
    which is the arrangement this repository declined."""
    record = Decommission(cut_over_at=CUT_OVER)

    assert not may_report_complete(record)
    with pytest.raises(DecommissionError, match="cannot be reported complete"):
        CompletedCutover(record=record, reported_by="the delivery lead")


def test_the_refusal_names_every_outstanding_act_rather_than_the_first() -> None:
    """Five findings and not one, because they send somebody to five different consoles. A
    refusal naming the first is worked one at a time, and each round trip is a day on a week
    where the outgoing vendor still holds credentials.

    Delete this and the message can be shortened to the first finding without any test
    noticing, which is the shape a refusal collapses into when somebody tidies it."""
    record = Decommission(cut_over_at=CUT_OVER)

    outstanding = security_acts_outstanding(record)

    assert len(outstanding) == len(CUTOVER_GATED_ACTS)
    assert [one.split(":")[0] for one in outstanding] == sorted(CUTOVER_GATED_ACTS)
    with pytest.raises(DecommissionError) as raised:
        CompletedCutover(record=record, reported_by="the delivery lead")
    for leaf in CUTOVER_GATED_ACTS:
        assert leaf in str(raised.value)


def test_recording_an_act_that_does_not_gate_leaves_the_cutover_refused() -> None:
    """The gate counts the acts it named, not acts. A record of the training session and the
    rollout order is a full afternoon's work and withdraws no credential, and a gate satisfied
    by any five ticks is a gate satisfied by the easy five.

    Delete this and the check can be loosened to a count, which is the change somebody makes
    when the refusal fires on a day nobody has time for it."""
    record = Decommission(
        cut_over_at=CUT_OVER,
        acts=tuple(
            ActRecord(leaf=leaf, performed_at=LATER, recorded_by="the delivery lead")
            for leaf in ("M37.3.1.2", "M37.3.2.1", "M37.3.3.1", "M37.3.3.2", "M37.3.3.3")
        ),
    )

    assert not may_report_complete(record)
    assert len(security_acts_outstanding(record)) == len(CUTOVER_GATED_ACTS)


def test_a_cutover_with_every_security_act_recorded_is_reported_complete() -> None:
    """The positive case, and every refusal above needs it: a guard tested only by what it
    refuses is satisfied by a guard that refuses everything, and a cutover that can never be
    reported complete is a gate somebody removes on the day rather than argues with.

    Delete this and the gate can be tightened until no migration ever finishes, and the tests
    stay green all the way."""
    record = Decommission(
        cut_over_at=CUT_OVER,
        read_only_at=LATER,
        archived_at=LATER_STILL,
        acts=tuple(
            ActRecord(leaf=leaf, performed_at=LATER, recorded_by="the delivery lead")
            for leaf in CUTOVER_GATED_ACTS
        ),
    )

    assert may_report_complete(record)
    assert security_acts_outstanding(record) == ()
    reported = CompletedCutover(record=record, reported_by="the delivery lead")
    assert reported.record is record


def test_an_act_recorded_by_nobody_is_refused() -> None:
    """Nothing here can reach the outgoing system, so the whole content of an act record is
    somebody's word that they did it. A word with nobody's name on it is a tick, and it is the
    same distinction the module already draws between a job that was disabled and a job
    somebody watched afterwards.

    Delete this and the gate is satisfied by five records nobody signed, which is a checklist
    filled in from the plan rather than from the week."""
    with pytest.raises(DecommissionError, match="says who did it nowhere"):
        ActRecord(leaf="M37.2.6.1", performed_at=LATER, recorded_by="   ")

    with pytest.raises(DecommissionError, match="names no task"):
        ActRecord(leaf=" ", performed_at=LATER, recorded_by="the delivery lead")


def test_a_completed_cutover_reported_by_nobody_is_refused() -> None:
    """The report is a claim somebody makes, and an unattributed one is what a screen writes
    by default.

    Delete this and a report can be produced with no author, which is the state a generated
    handover pack is in unless somebody refuses it."""
    record = Decommission(
        cut_over_at=CUT_OVER,
        acts=tuple(
            ActRecord(leaf=leaf, performed_at=LATER, recorded_by="the delivery lead")
            for leaf in CUTOVER_GATED_ACTS
        ),
    )

    with pytest.raises(DecommissionError, match="reported by nobody"):
        CompletedCutover(record=record, reported_by="")


def test_the_acts_gate_the_cutover_and_not_the_decommission_findings() -> None:
    """The two questions are separate on purpose. `decommission_gaps` reports what is still
    true of the old system; two of the gated acts are about the client's own tenant and the
    client's own backup and are not facts about the old system at all. Folding them in would
    also make an empty tuple of acts read as "none were required", which is the permissive
    reading of an absence.

    Delete this and somebody folds the two together for tidiness, and every existing caller of
    `decommission_gaps` starts reporting five findings it was never asked about."""
    finished = Decommission(
        cut_over_at=CUT_OVER,
        read_only_at=LATER,
        archived_at=LATER_STILL,
        revocations=(Revocation(connector="drive", requested_at=LATER, verified_at=LATER_STILL),),
        jobs=(ScheduledJob(name="nightly sync", disabled_at=LATER, watched_until=LATER_STILL),),
        final_backup=FinalBackup(backup_id="b1", taken_at=LATER, verified=True),
    )

    assert decommission_gaps(finished) == ()
    assert not may_report_complete(finished)
