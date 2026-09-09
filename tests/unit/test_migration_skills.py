"""Skills arriving from another platform: the description, the review, and what stays behind."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest

from brain.migration.skills import (
    RETIRE_AFTER_DAYS,
    BehaviourCheck,
    ForeignSkill,
    SkillMigrationError,
    arriving,
    proposed_description,
    router_descriptions,
    to_retire,
    unproven,
)
from brain.status import leaf_sentences
from brain.tools.skills import ImportedSkill, Skill, SkillSource, SkillState, SourceKind

WBS = Path("docs/wbs.json")

#: Pinned far from any wall clock. Nothing here reads the present.
NOW = datetime(2030, 6, 1, tzinfo=UTC)


#: The fixture's "leave it at something recent" marker.
#:
#: A sentinel rather than `None`, because `None` is a value this module distinguishes: a skill
#: with no recorded invocation is its own finding, and a default of `None` meaning "recent"
#: would make that case unreachable from the helper.
RECENT: Final = "recent"


def a_foreign(
    name: str = "invoicing",
    description: str = "Use the invoicing skill to raise an invoice from a project",
    last_invoked_at: datetime | str | None = RECENT,
) -> ForeignSkill:
    return ForeignSkill(
        name=name,
        description=description,
        last_invoked_at=NOW - timedelta(days=1) if last_invoked_at == RECENT else last_invoked_at,  # type: ignore[arg-type]
    )


def a_skill() -> Skill:
    return Skill(name="invoicing", description="raises an invoice from a project")


def a_source() -> SkillSource:
    return SkillSource(kind=SourceKind.UPLOAD, location="invoicing.zip", content_digest="a" * 64)


# ------------------------------------------------------- the description convention (M37.2.2.2)
def test_a_description_written_at_a_router_is_reported() -> None:
    """**M37.2.2.2. Over there the reader is a model choosing between skills; here it is a
    person looking at a card.** "Use the invoicing skill to raise an invoice" tells that person
    to use the thing they are already looking at.

    Delete this and the whole card estate arrives written as instructions to a router that
    does not exist here."""
    findings = router_descriptions((a_foreign(), a_foreign("leave", "books leave for somebody")))

    assert findings == (
        "invoicing: the description tells a router what to do rather than saying what the "
        "skill does",
    )


def test_the_preamble_is_stripped_and_what_is_left_is_a_draft() -> None:
    """The conversion is mechanical enough to detect and not mechanical enough to finish, so
    what comes back is a fragment: lowercase, unpunctuated, visibly unfinished.

    That is deliberate. A tidy sentence is one somebody ships without reading; a fragment is
    one somebody edits.

    Delete this and the obvious improvement is to capitalise and punctuate the result, which
    turns a draft into something that looks final."""
    assert proposed_description(a_foreign()) == "raise an invoice from a project"


def test_a_description_that_was_never_written_at_a_router_is_left_alone() -> None:
    """The common case for a skill somebody wrote carefully, and the case a greedy pattern
    would damage.

    Delete this and the pattern can be loosened until it rewrites descriptions that were
    already about the skill, and a wrong conversion is worse than a missed one because the
    missed one is still in `router_descriptions`."""
    careful = a_foreign("leave", "books leave for somebody and tells their manager")

    assert proposed_description(careful) == "books leave for somebody and tells their manager"
    assert router_descriptions((careful,)) == ()


def test_the_pattern_does_not_match_a_description_that_merely_starts_with_use() -> None:
    """ "Use this when a project needs invoicing" is about the skill and reads correctly on a
    card. The pattern is narrow on purpose and this is the boundary it was made narrow for.

    Delete this and the pattern can be widened to anything beginning with "use", which
    silently truncates a description that was already right."""
    fine = a_foreign("invoicing", "use this when a project needs an invoice raising")

    assert router_descriptions((fine,)) == ()
    assert proposed_description(fine) == "use this when a project needs an invoice raising"


def test_a_foreign_skill_with_no_description_is_refused() -> None:
    """There is nothing to convert and nothing to show on a card.

    Delete this and the blank branch is unreachable, and a skill arrives with an empty card."""
    with pytest.raises(SkillMigrationError, match="no description"):
        ForeignSkill(name="invoicing", description="  ")


def test_a_foreign_skill_with_no_name_is_refused() -> None:
    """Delete this and the blank branch is unreachable."""
    with pytest.raises(SkillMigrationError, match="has no name"):
        ForeignSkill(name=" ", description="raises an invoice")


# ------------------------------------------------------ nothing arrives approved (M37.2.2.3)
def test_an_imported_skill_arrives_unreviewed_and_unexecutable() -> None:
    """**M37.2.2.3. "It worked over there" is a statement about a system with a different tool
    catalogue, different data and no ceiling.**

    Delete this and a skill can arrive approved, which is the one shortcut everybody wants on
    the week of a migration."""
    imported = arriving(a_skill(), a_source())

    assert isinstance(imported, ImportedSkill)
    assert imported.state is SkillState.IMPORTED
    assert imported.reviewer == ""
    assert imported.is_executable() is False


def test_there_is_no_parameter_that_could_carry_the_old_platform_s_approval() -> None:
    """The enforcement, asserted on the signature rather than on the behaviour, in the same
    shape as `brain.migration.rebuild.authority_for`. A behavioural test says the approval did
    not come across for one input; the signature says no code path can bring it.

    Delete this and a `reviewer` parameter can be added "so the record is complete", and the
    week of a migration is exactly when somebody passes the old platform's approver into it."""
    parameters = inspect.signature(arriving).parameters

    assert set(parameters) == {"skill", "source"}


def test_an_imported_skill_still_goes_through_the_ordinary_review() -> None:
    """The positive case, and it proves the refusal above is not a dead end: the path exists
    and it is the same one every other skill takes.

    Delete this and `arriving` could return something the review path cannot accept, and
    nothing here would notice until a migration."""
    imported = arriving(a_skill(), a_source())

    approved = imported.approved_by("u_priya", NOW)

    assert approved.is_executable() is True
    assert approved.reviewer == "u_priya"


# --------------------------------------------------------- parsing is not behaviour (M37.2.2.4)
def test_a_skill_nobody_has_run_a_real_task_through_is_unproven() -> None:
    """**M37.2.2.4. Parsing is the check that gets done because it is free.** A skill whose
    file loads and whose card renders can still answer differently here, because the tools it
    names are not the tools it had.

    Delete this and "it parses" becomes the acceptance test for authored work."""
    findings = unproven((a_foreign(), a_foreign("leave", "books leave")), ())

    assert findings == (
        "invoicing: imported and no real task has been run through it",
        "leave: imported and no real task has been run through it",
    )


def test_a_skill_that_answered_differently_is_a_separate_finding() -> None:
    """Different work from the one above: nobody looked is a task to do, and the answer changed
    is a skill to fix. It is not a failure of the migration either, it is the migration finding
    what it was run to find.

    Delete this and a list of only the unchecked ones reads as a clean import once somebody
    works through it."""
    checks = (
        BehaviourCheck(
            skill_name="invoicing",
            task="raise the March invoice for the Acme rebuild",
            same_answer=False,
            checked_by="u_priya",
        ),
    )

    assert unproven((a_foreign(),), checks) == (
        "invoicing: answered 'raise the March invoice for the Acme rebuild' differently after "
        "import",
    )


def test_a_skill_checked_on_a_real_task_with_the_same_answer_is_not_reported() -> None:
    """The positive case.

    Delete this and `unproven` can be written to report every skill, which makes the list
    unreadable and gets it ignored."""
    checks = (
        BehaviourCheck(
            skill_name="invoicing",
            task="raise the March invoice for the Acme rebuild",
            same_answer=True,
            checked_by="u_priya",
        ),
    )

    assert unproven((a_foreign(),), checks) == ()


def test_a_check_that_names_no_task_is_refused() -> None:
    """**A comparison that does not say what was compared is a tick.** The task is what makes
    the check re-runnable by somebody who doubts it.

    Delete this and the record fills up with checks nobody can repeat."""
    with pytest.raises(SkillMigrationError, match="names no task"):
        BehaviourCheck(skill_name="invoicing", task=" ", same_answer=True, checked_by="u_priya")


def test_a_check_that_names_nobody_is_refused() -> None:
    """Somebody ran it, and who is the question asked when the answer is disputed.

    Delete this and behaviour checks arrive from a spreadsheet with an empty column."""
    with pytest.raises(SkillMigrationError, match="names nobody who ran it"):
        BehaviourCheck(
            skill_name="invoicing", task="raise an invoice", same_answer=True, checked_by=""
        )


def test_a_check_that_names_no_skill_is_refused() -> None:
    """Delete this and the blank branch is unreachable, and a check counts towards a skill
    called nothing."""
    with pytest.raises(SkillMigrationError, match="names no skill"):
        BehaviourCheck(skill_name="", task="raise an invoice", same_answer=True, checked_by="u_x")


# ----------------------------------------------------------- what stays behind (M37.2.2.5)
def test_the_retirement_window_is_the_one_the_leaf_states() -> None:
    """**M37.2.2.5 says ninety days, and the leaf sentence is the only anchor there is.**

    The figure is a judgement rather than an arithmetic consequence of anything else, so a
    number written in this test file would be the same number written twice by the same person
    and would agree with the module for every value either could hold. Read from the leaf, it
    disagrees the day somebody changes one without the other.

    Delete this and the window can drift to thirty or to a year with nothing going red."""
    tens = ("", "ten", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    assert RETIRE_AFTER_DAYS % 10 == 0, "the spelling table below only covers whole tens"
    spelled = tens[RETIRE_AFTER_DAYS // 10]

    assert f"{spelled} days" in leaf_sentences(WBS)["M37.2.2.5"].casefold()


def test_a_skill_nobody_has_invoked_inside_the_window_is_retired() -> None:
    """Retiring is declining to spend a review on a skill nobody has asked for. The export
    still holds it.

    Delete this and every skill on the old platform is carried, reviewed and maintained,
    including the ones written for a client who left."""
    stale = a_foreign("old", "does something", NOW - timedelta(days=RETIRE_AFTER_DAYS + 1))

    assert to_retire((a_foreign(), stale), now=NOW) == (
        f"old: last invoked {stale.last_invoked_at}, more than {RETIRE_AFTER_DAYS} days ago",
    )


def test_a_skill_with_no_recorded_invocation_gets_its_own_sentence() -> None:
    """**Never used and used before anything recorded it are different evidence**, and the
    difference is between a decision and a guess. Folded into the sentence above it would
    claim a last-invoked date that does not exist.

    Delete this and a platform that started recording invocations last month retires every
    skill written before then, with a sentence saying they were last used at None."""
    findings = to_retire((a_foreign("old", "does something", last_invoked_at=None),), now=NOW)

    assert findings == ("old: never invoked, or invoked before anything recorded it",)


def test_a_skill_invoked_inside_the_window_is_carried() -> None:
    """The positive case, and the boundary: a skill invoked exactly at the cutoff is inside it.

    Delete this and the comparison can be written the other way round, which retires a skill
    somebody used ninety days ago to the minute, and the argument for the window is that
    ninety days of silence is evidence rather than that ninety days is a deadline."""
    edge = a_foreign("edge", "does something", NOW - timedelta(days=RETIRE_AFTER_DAYS))

    assert to_retire((a_foreign(), edge), now=NOW) == ()


def test_the_window_is_a_parameter_so_a_client_can_argue_about_it() -> None:
    """The default is the leaf's figure and the argument is a client's to have. A window that
    could not be changed would be changed by editing the constant, which moves it for everybody.

    Delete this and the parameter can be dropped, and the next client's different answer
    becomes a code change."""
    used_last_week = a_foreign("recent", "does something", NOW - timedelta(days=7))

    assert to_retire((used_last_week,), now=NOW, after_days=3) == (
        f"recent: last invoked {used_last_week.last_invoked_at}, more than 3 days ago",
    )
