"""What an agent's Profile says about its skills and about computer use, held to what decides them.

Two sentences the page used to type for itself, now said from the code that decides each: whether
anything about the agent stops every run from using an assigned skill, and whether the product has
an isolated desktop runner to offer. Each skill case is asked of `brain.gate.model_lane.
skills_offered`, the run path itself, as well as of `skill_standing`, so the Profile cannot say a
skill does not change a run while a run offers it, nor the reverse.

Task ids: M27.11.12, M27.15.32
"""

from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from brain.agents.template import SkillRef
from brain.console import agent_behaviour
from brain.console.agent_behaviour import (
    CHANGED_AFTER_APPROVAL,
    COMPUTER_USE_NOT_OFFERED,
    COMPUTER_USE_RUNNER_PRESENT,
    DESKTOP_RUNNER_MODULE,
    NAMES_A_TOOL_THE_AGENT_MAY_NOT_CALL,
    NOT_IN_THE_LIBRARY,
    REJECTED_IN_REVIEW,
    WAITING_FOR_REVIEW,
    computer_use,
    isolated_desktop_runner_exists,
    skill_standing,
    usable_tools,
)
from brain.console.agent_tabs import Review, chip_for
from brain.console.skill_library import LibrarySkill, decided
from brain.gate.model_lane import AgentRun, skills_offered
from brain.tools.skills import SkillPin
from tests.unit.test_skill_library import (
    AGENT,
    NOW,
    REVIEWER,
    a_library_skill,
    a_registry,
    an_approved_skill,
    an_install,
    reach,
    text_with,
)

ONE_TOOL = text_with(tools="[crm.read_client]")
A_TOOL_THE_AGENT_MAY_NOT_CALL = text_with(tools="[crm.read_client, desk.read_ticket]")
EVERYTHING = reach("read:client.name", "read:ticket.status")


def standing_of(
    library: tuple[LibrarySkill, ...], pinned: LibrarySkill
) -> agent_behaviour.SkillStanding:
    """What the Profile says of one pinned skill, as the route builds it from the same inputs."""
    _, _, record = an_install()
    row = next((one for one in library if one.digest == pinned.digest), None)
    return skill_standing(
        review=None if row is None else chip_for(row.imported).review,
        tools=() if row is None else row.imported.skill.tools,
        usable=usable_tools(record.authority, a_registry().definitions()),
    )


def offered_by_a_run(library: tuple[LibrarySkill, ...], pinned: LibrarySkill) -> bool:
    """Whether the run path offers this pinned skill to somebody who holds every capability."""
    _, _, record = an_install()
    pin = SkillPin(agent_id=AGENT, skill_name=pinned.name, digest=pinned.digest)
    run = AgentRun(record=record, pins=(pin,), library=library, registry=a_registry())
    return bool(skills_offered(run, caller=EVERYTHING, now=NOW))


def changed_after_approval() -> LibrarySkill:
    """An approved skill whose text has moved since: the row still reads approved."""
    approved = an_approved_skill(ONE_TOOL)
    moved = a_library_skill(text_with(tools="[crm.read_client]", version="1.0.1")).imported.skill
    return replace(approved, imported=approved.imported.model_copy(update={"skill": moved}))


# ------------------------------------------------------------------------------ skills
def test_a_skill_nothing_stops_is_said_to_be_stopped_by_nothing_and_a_run_offers_it() -> None:
    """The positive case, asked of both sides: an approved skill whose tools the agent may call is
    not described as stopped, and the run path does offer it.

    Delete this and every refusal below is satisfied by a standing that stops every skill."""
    one = an_approved_skill(ONE_TOOL)
    assert standing_of((one,), one).because is None
    assert offered_by_a_run((one,), one) is True


@pytest.mark.parametrize(
    ("label", "build", "sentence"),
    [
        ("unreviewed", lambda: a_library_skill(ONE_TOOL), WAITING_FOR_REVIEW),
        (
            "rejected",
            lambda: decided(a_library_skill(ONE_TOOL), reviewer=REVIEWER, approve=False, at=NOW),
            REJECTED_IN_REVIEW,
        ),
        ("changed", changed_after_approval, CHANGED_AFTER_APPROVAL),
        (
            "names a tool the ceiling does not allow",
            lambda: an_approved_skill(A_TOOL_THE_AGENT_MAY_NOT_CALL),
            NAMES_A_TOOL_THE_AGENT_MAY_NOT_CALL,
        ),
    ],
)
def test_a_skill_is_said_not_to_change_a_run_exactly_where_the_run_path_does_not_offer_it(
    label: str, build: object, sentence: str
) -> None:
    """Four ways an assigned skill cannot reach a run, each said in its own sentence, and each
    checked against `skills_offered` itself rather than against a restatement of its rule.

    Delete this and the Profile can say a skill is waiting for review while the run offers it, or
    say nothing while the run never will, which is the sentence it used to type for itself."""
    one = build()  # type: ignore[operator]
    assert isinstance(one, LibrarySkill), label
    assert standing_of((one,), one).because == sentence
    assert offered_by_a_run((one,), one) is False


def test_a_pinned_skill_the_library_has_no_row_for_is_said_not_to_be_used() -> None:
    """A skill the agent's template shipped, or whose library row was removed, is never offered:
    the run path walks the library's rows. Delete this and a pin with no row reads as a skill a
    run uses."""
    one = an_approved_skill(ONE_TOOL)
    assert standing_of((), one).because == NOT_IN_THE_LIBRARY
    assert offered_by_a_run((), one) is False


def test_a_skill_naming_no_tool_is_stopped_by_no_tool() -> None:
    """The subset test over an empty list holds. Delete this and the tool check is turned into
    an equality, which would call a skill with no tools stopped for naming nothing."""
    assert skill_standing(review=Review.APPROVED, tools=(), usable=()).because is None


def test_the_tools_a_run_could_call_are_the_ceilings_own_comparison() -> None:
    """The set the standing is checked against is the Profile's tool rows within the ceiling and
    nothing else, so a tool the registry holds and the ceiling does not name is absent.

    Delete this and a skill naming a registered tool the agent may not call reads as usable."""
    _, _, record = an_install()
    usable = usable_tools(record.authority, a_registry().definitions())
    assert usable == frozenset({"crm.read_client"})
    assert usable_tools(record.authority, ()) == frozenset()


# ------------------------------------------------------------------------- computer use
def test_computer_use_is_not_offered_because_the_product_has_no_desktop_runner() -> None:
    """On this tree there is no isolated desktop runner, so the Profile offers nothing and says
    in one sentence that it is not offered. Delete this and the day somebody adds the runner
    module the Profile goes on saying it does not exist, or the reverse."""
    assert isolated_desktop_runner_exists() is False
    said = computer_use()
    assert (said.offered, said.sentence) == (False, COMPUTER_USE_NOT_OFFERED)


def test_the_desktop_runner_is_found_by_asking_the_import_machinery_for_its_module() -> None:
    """The positive sibling: a module that is part of the product is found, a missing one and one
    under a package that is missing are not, and none raises.

    Delete this and the existence check is satisfied by a function that always answers no."""
    assert isolated_desktop_runner_exists("json") is True
    assert isolated_desktop_runner_exists("brain.browsing.not_a_module") is False
    assert isolated_desktop_runner_exists("not_a_package.runner") is False
    assert isolated_desktop_runner_exists("") is False


def test_the_runner_the_check_looks_for_is_not_a_module_the_product_has() -> None:
    """The constant names a module that does not exist. If it did, the answer above would be
    asserted by luck. Delete this and the two tests above can pass on a renamed constant."""
    with pytest.raises(ImportError):
        importlib.import_module(DESKTOP_RUNNER_MODULE)


def test_a_present_runner_is_still_not_offered_until_an_agent_can_be_switched_to_it() -> None:
    """With a runner present the sentence changes and `offered` stays false: there is no per-agent
    switch to write to, so a page must not draw one.

    Delete this and the day a runner lands the Profile draws a switch with nowhere to write."""
    said = computer_use(runner_exists=True)
    assert (said.offered, said.sentence) == (False, COMPUTER_USE_RUNNER_PRESENT)
    assert said.sentence != computer_use(runner_exists=False).sentence


def test_a_skill_pin_type_is_the_one_the_template_names() -> None:
    """The pin a template ships is `SkillRef`, which has a name and a digest and no review. Delete
    this and a pin is assumed to carry a review the page then reads from nothing."""
    assert set(SkillRef.model_fields) == {"name", "digest"}
