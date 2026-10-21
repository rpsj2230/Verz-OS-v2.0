"""Trying an approved skill: one question carries a pin that is never stored (M40.7.2).

Pure: `with_tried_skill` over real library rows, and the question model. The route is exercised by
the Ask page tests; the metering is the ordinary run's.

Task ids: M40.7.2
"""

from __future__ import annotations

from brain.api_routes import Question, with_tried_skill
from brain.console.skill_library import added, read_package
from brain.gate.model_lane import AgentRun, skills_offered
from brain.tools.skills import SkillPin
from tests.unit.test_member_starters import skill_text
from tests.unit.test_skill_library import (
    AGENT,
    NOW,
    a_registry,
    an_approved_skill,
    an_install,
    reach,
)


def test_an_approved_unchanged_skill_is_pinned_for_the_question() -> None:
    """The positive case. Delete this and a function that never pinned passes every refusal."""
    one = an_approved_skill(skill_text())
    pins = with_tried_skill((), [one], one.digest, agent_id=AGENT)
    assert pins == (SkillPin(agent_id=AGENT, skill_name=one.name, digest=one.digest),)


def test_a_skill_nobody_approved_is_not_pinned_and_nothing_says_so() -> None:
    """An undecided skill is never tried. Delete this and a person can run a procedure no named
    person read."""
    undecided = added(read_package("SKILL.md", skill_text().encode()), by="u_importer", at=NOW)
    assert with_tried_skill((), [undecided], undecided.digest, agent_id=AGENT) == ()


def test_a_digest_the_library_does_not_hold_pins_nothing() -> None:
    """The answer is the one for a skill that does not exist. Delete this and a made-up digest
    errors, which tells a person which digests are real."""
    one = an_approved_skill(skill_text())
    assert with_tried_skill((), [one], "f" * 64, agent_id=AGENT) == ()


def test_a_skill_already_on_the_agent_is_not_pinned_twice() -> None:
    """Delete this and the same card is offered to the model twice."""
    one = an_approved_skill(skill_text())
    held = (SkillPin(agent_id=AGENT, skill_name=one.name, digest=one.digest),)
    assert with_tried_skill(held, [one], one.digest, agent_id=AGENT) == held


def test_a_tried_skill_is_offered_only_when_its_tools_are_within_the_runs_reach() -> None:
    """Pinning does not widen anything: the run still asks every tool of the reach. Delete this and
    trying a skill could lend a person a tool they do not hold."""
    one = an_approved_skill(skill_text())
    _, _, record = an_install()
    pins = with_tried_skill((), [one], one.digest, agent_id=AGENT)
    run = AgentRun(record=record, pins=pins, library=(one,), registry=a_registry())
    assert [
        s.skill.name for s in skills_offered(run, caller=reach("read:client.name"), now=NOW)
    ] == [one.name]
    assert skills_offered(run, caller=reach(), now=NOW) == ()


def test_the_question_carries_a_skill_to_try_as_a_digest_and_nothing_looser() -> None:
    """A 64-character lower-case hex digest or nothing. Delete this and a name or a path could
    travel in the field."""
    assert Question(question="x", try_skill="a" * 64).try_skill == "a" * 64
    assert Question(question="x").try_skill is None
    for bad in ("hosting-expiry", "A" * 64, "a" * 63, "../etc"):
        try:
            Question(question="x", try_skill=bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} was accepted as a skill digest")


def test_a_skill_whose_stored_text_moved_since_approval_is_not_pinned() -> None:
    """A row that no longer digests to its key is skipped, as a run skips it. Delete this and a
    skill edited in place after it was approved can be tried."""
    from dataclasses import replace

    one = an_approved_skill(skill_text())
    moved = replace(one, digest="b" * 64)
    assert moved.moved
    assert with_tried_skill((), [moved], moved.digest, agent_id=AGENT) == ()


def test_a_retired_version_is_not_pinned_for_a_try() -> None:
    """Retiring refuses a version to new use, and a try is a new use. Delete this and a retired
    version can still be run."""
    one = an_approved_skill(skill_text())
    assert (
        with_tried_skill((), [one], one.digest, agent_id=AGENT, retired=frozenset({one.digest}))
        == ()
    )
    assert len(with_tried_skill((), [one], one.digest, agent_id=AGENT, retired=frozenset())) == 1


def test_a_question_carrying_a_skill_to_try_is_neither_looked_up_nor_kept_by_the_cache() -> None:
    """The cache's key has no skill, so an answer made with one must not be served to a question
    without it, nor the reverse. Delete this and a tried answer reaches everybody who asks."""
    from brain.api_routes import answer_is_not_cacheable

    plain = Question(question="x")
    assert answer_is_not_cacheable(plain, referral=None, follow_up=None) is False
    assert answer_is_not_cacheable(
        Question(question="x", try_skill="a" * 64), referral=None, follow_up=None
    )
    assert answer_is_not_cacheable(plain, referral=object(), follow_up=None)
    assert answer_is_not_cacheable(plain, referral=None, follow_up=object())
