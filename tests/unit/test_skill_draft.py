"""A model's reply becomes a draft skill, or a refusal, and nothing in it widens anything.

Each refusal has the sibling that proves a good reply still drafts. The drafted `SKILL.md` is read
back through the one parser, so what is held here is that the reply cannot become anything a pasted
file could not.

Task ids: M12.4.14
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain.tools.skill_draft import (
    DESCRIPTION_CHARS,
    DRAFT_VERSION,
    LEFT_OUT,
    SkillDraftError,
    checked_description,
    draft_messages,
    read_reply,
    system_prompt,
)
from brain.tools.skill_examples import examples_of
from brain.tools.skills import skill_from_markdown

TOOLS = ("crm.read_client", "desk.read_ticket")
DEPARTMENTS = ("finance", "web")


def a_reply(**overrides: Any) -> str:
    """A reply as a model would write it, with some keys replaced."""
    found: dict[str, Any] = {
        "name": "renewal-check",
        "description": "Use when a client asks whether their domain is close to renewal",
        "instructions": "Look up the client.\nRead their open tickets.\nSay when it renews.",
        "tools": ["crm.read_client", "desk.read_ticket"],
        "knowledge": ["finance"],
        "examples": [
            {"task": "When does acme renew", "tools": ["crm.read_client"]},
            {"task": "Is there a renewal ticket for acme", "tools": ["desk.read_ticket"]},
        ],
    }
    found.update(overrides)
    return json.dumps(found)


def read(reply: str) -> Any:
    return read_reply(reply, tools=TOOLS, departments=DEPARTMENTS)


def test_a_good_reply_is_a_skill_the_one_parser_reads_with_its_examples_and_needs() -> None:
    """The draft keeps the name, the version of a draft, the tools and the department it was
    allowed, and the examples are lines `examples_of` reads back, each expecting only listed tools.

    Delete this and a reply that is well formed drafts nothing, or drafts a skill whose examples
    the rehearsal cannot read."""
    draft = read(a_reply())
    assert draft.skill.name == "renewal-check"
    assert draft.skill.version == DRAFT_VERSION
    assert draft.skill.tools == TOOLS
    assert draft.skill.knowledge == ("finance",)
    assert draft.findings == ()
    assert skill_from_markdown(draft.markdown) == draft.skill
    assert [(one.task, one.expects) for one in examples_of(draft.skill)] == [
        ("When does acme renew", ("crm.read_client",)),
        ("Is there a renewal ticket for acme", ("desk.read_ticket",)),
    ]


def test_a_tool_or_department_the_install_does_not_hold_is_left_out_and_said() -> None:
    """An invented tool and an unknown department are dropped with a finding each, and an example
    that named the invented tool keeps its line expecting nothing.

    Delete this and a draft can name a tool nobody registered, which would be a skill that cannot
    do what it says, approved by a reviewer who was never told a step was lost."""
    draft = read(
        a_reply(
            tools=["crm.read_client", "mail.send_everything"],
            knowledge=["finance", "payroll"],
            examples=[{"task": "Mail acme", "tools": ["mail.send_everything"]}],
        )
    )
    assert draft.skill.tools == ("crm.read_client",)
    assert draft.skill.knowledge == ("finance",)
    assert sorted(one.what for one in draft.findings) == ["mail.send_everything", "payroll"]
    assert all(LEFT_OUT in one.message for one in draft.findings)
    assert [(one.task, one.expects) for one in examples_of(draft.skill)] == [("Mail acme", ())]


def test_a_reply_that_is_not_one_object_is_refused_whole() -> None:
    """Prose, a list, prose around an object and an object with no instructions are each refused
    with a sentence saying nothing was drafted, while the same object in a code fence is read.

    Delete this and a model's chatter becomes a skill, or a fenced reply, which models send most
    of the time, is refused."""
    for bad in ("here is your skill", "[1, 2]", f"Sure! {a_reply()}", a_reply(instructions="")):
        with pytest.raises(SkillDraftError) as refused:
            read(bad)
        assert "nothing was drafted" in str(refused.value)
    assert read(f"```json\n{a_reply()}\n```").skill.name == "renewal-check"


def test_a_draft_the_parser_would_refuse_is_refused_in_words() -> None:
    """A description that does not open by saying when the skill is used and a name that is not a
    slug are the parser's refusals, carried to the person.

    Delete this and a draft is stored that no router can choose, or one the library's own table
    refuses after the press."""
    for bad in (
        a_reply(description="Checks domain renewals"),
        a_reply(name="Renewal Check"),
    ):
        with pytest.raises(SkillDraftError) as refused:
            read(bad)
        assert "nothing was drafted" in str(refused.value)


def test_a_reply_carrying_reach_has_it_ignored() -> None:
    """A `capabilities`, `scope` and `leash` key in a reply changes nothing about the skill, which
    has no field to hold one.

    Delete this and a reply that argues for reach is read into a skill that carries it, or refused
    for a key that was never going to be read."""
    plain = read(a_reply())
    reaching = read(a_reply(capabilities=["admin:everything"], scope="all", leash="autonomous"))
    assert reaching.skill == plain.skill
    assert "admin" not in reaching.markdown


def test_the_description_is_bounded_and_the_standing_prompt_takes_no_caller() -> None:
    """An empty description and one past the bound are refused, and the system message is the same
    text whoever asks, with the tools and departments sorted into the request.

    Delete this and a draft is asked of nothing, or two people asking the same thing send different
    bytes in the part meant to be shared."""
    assert checked_description("  a procedure  ") == "a procedure"
    for bad in ("", "   ", "x" * (DESCRIPTION_CHARS + 1)):
        with pytest.raises(SkillDraftError):
            checked_description(bad)
    first = draft_messages(
        "one", tools=[("b.x_y", "B"), ("a.x_y", "A")], departments=["web", "ops"]
    )
    again = draft_messages(
        "one", tools=[("a.x_y", "A"), ("b.x_y", "B")], departments=["ops", "web"]
    )
    assert first == again
    assert first[0].content == system_prompt()
    assert first[1].content.index("a.x_y") < first[1].content.index("b.x_y")
