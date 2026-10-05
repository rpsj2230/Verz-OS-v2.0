"""A skill's declared escalation: read from its file, digested, chosen, and turned into a handoff.

`brain.tools.skills` reads the three frontmatter keys and holds them together;
`brain.gate.escalating` picks the declaring skill among those a run offers and builds the handoff
and the two sentences. Every refusal has a sibling proving the thing it refuses still works.

Task ids: M8.3.1, M8.3.2, M8.3.4
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from brain.gate.abstain import (
    DEFAULT_ESCALATION_TTL,
    ESCALATION_EXPIRED_TEXT,
    ESCALATION_TEXT,
    MODEL_JUDGEMENT_IS_NOT_A_TRIGGER,
    EscalationRoute,
    EscalationTrigger,
)
from brain.gate.context import Channel
from brain.gate.escalating import (
    TRIED,
    declared_by,
    escalation_for,
    handoff_text,
    said_to_asker,
    tried_by,
    ttl_of,
)
from brain.tools.skills import (
    DIGEST_SCHEMA,
    FRONTMATTER_KEYS,
    ImportedSkill,
    Skill,
    SkillError,
    SkillSource,
    SkillState,
    SourceKind,
    markdown_of,
    skill_from_markdown,
)

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

NEEDS: Final = "Somebody who can quote outside the price list"


def skill_md(*extra: str, name: str = "quote-desk") -> str:
    return "\n".join(
        [
            "---",
            f"name: {name}",
            "description: Use when a client asks for a price the list does not hold",
            "version: 1.0.0",
            *extra,
            "---",
            "Look the price up. If nothing answers, hand it on.",
            "",
        ]
    )


def escalating(name: str = "quote-desk", within: int | None = 2) -> Skill:
    extra = ["escalate_to: pricing", f"escalation_needs: {NEEDS}"]
    if within is not None:
        extra.append(f"escalate_within: {within}")
    return skill_from_markdown(skill_md(*extra, name=name))


def approved(skill: Skill) -> ImportedSkill:
    source = SkillSource(kind=SourceKind.UPLOAD, location="skill.zip", content_digest="a" * 64)
    return ImportedSkill(
        skill=skill,
        source=source,
        state=SkillState.APPROVED,
        reviewer="u_reviewer",
        reviewed_at=LONG_AGO,
        approved_digest=skill.digest(),
    )


# --------------------------------------------------------------------------- the file
def test_a_skill_file_declares_a_queue_what_it_needs_and_the_hours_a_person_has() -> None:
    """The positive case. Delete this and the three keys can be refused or dropped by the parser,
    so no skill ever escalates."""
    skill = escalating()
    assert (skill.escalate_to, skill.escalation_needs, skill.escalate_within) == (
        "pricing",
        NEEDS,
        2,
    )
    assert {"escalate_to", "escalation_needs", "escalate_within"} <= FRONTMATTER_KEYS


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        (("escalation_needs: somebody",), "need escalate_to"),
        (("escalate_within: 3",), "need escalate_to"),
        (("escalate_to: pricing",), "a queue with no sentence"),
        (("escalate_to: Pricing Desk", "escalation_needs: somebody"), "not a queue name"),
        (("escalate_to: pricing", "escalation_needs: somebody", "escalate_within: 0"), "between 1"),
        (
            ("escalate_to: pricing", "escalation_needs: somebody", "escalate_within: 73"),
            "between 1",
        ),
        (("escalate_to: pricing", "escalation_needs: somebody", "escalate_within: soon"), "hours"),
    ],
)
def test_a_half_declared_or_malformed_escalation_is_refused(
    extra: tuple[str, ...], said: str
) -> None:
    """Delete this and a queue with no sentence reaches a person who cannot judge it, a sentence
    with no queue goes nowhere, and a deadline of no hours is an escalation born expired."""
    with pytest.raises(SkillError, match=said):
        skill_from_markdown(skill_md(*extra))


def test_a_skill_that_declares_no_escalation_digests_as_it_did_before_escalation_existed() -> None:
    """The digest of a skill with no escalation is the digest the version before this one computed,
    written out here rather than called, so every approval already granted still holds. Delete this
    and adding the keys voids every approval on every install."""
    skill = skill_from_markdown(skill_md())
    parts = [DIGEST_SCHEMA, skill.name, skill.version, skill.description, skill.body]
    before = hashlib.sha256("".join(f"{len(p)}:{p}" for p in parts).encode("utf-8")).hexdigest()
    assert skill.digest() == before


def test_an_escalation_is_part_of_what_a_reviewer_approved() -> None:
    """Changing the queue, the sentence or the hours changes the digest. Delete this and a skill
    approved to escalate to one queue can be edited to send its questions to another with the
    approval standing."""
    base = escalating()
    moved = {
        escalating(within=3).digest(),
        skill_from_markdown(
            skill_md("escalate_to: finance", f"escalation_needs: {NEEDS}", "escalate_within: 2")
        ).digest(),
        skill_from_markdown(
            skill_md("escalate_to: pricing", "escalation_needs: Other", "escalate_within: 2")
        ).digest(),
    }
    assert base.digest() not in moved
    assert skill_from_markdown(skill_md()).digest() != base.digest()


def test_a_declared_escalation_is_written_back_as_the_file_it_was_read_from() -> None:
    """Delete this and opening an escalating skill to edit it raises, or offers a file that drops
    the declaration a reviewer approved."""
    for skill in (escalating(), escalating(within=None)):
        assert skill_from_markdown(markdown_of(skill)) == skill


# ------------------------------------------------------------------------ the choice
def test_the_declaring_skill_is_the_first_approved_one_by_name() -> None:
    """Delete this and the choice between two declaring skills follows the order they were pinned
    in, so the queue a question goes to changes with nothing changed."""
    later, earlier = approved(escalating("zeta-desk")), approved(escalating("alpha-desk"))
    quiet = approved(skill_from_markdown(skill_md(name="alpha-quiet")))
    chosen = declared_by([later, quiet, earlier])
    assert chosen is not None and chosen.name == "alpha-desk"


def test_a_declaration_in_a_skill_nobody_approved_sends_nothing() -> None:
    """Delete this and an imported file nobody reviewed routes questions to a queue of its
    choosing."""
    unreviewed = ImportedSkill(
        skill=escalating(),
        source=SkillSource(kind=SourceKind.UPLOAD, location="x.zip", content_digest="b" * 64),
    )
    assert declared_by([unreviewed]) is None
    assert declared_by([approved(escalating())]) is not None


# ---------------------------------------------------------------------- the handoff
def test_a_handoff_is_the_asker_s_words_fixed_step_names_and_the_author_s_sentence() -> None:
    """`A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`: what was tried is the same for every
    escalation of a skill, whatever the answer reached. Delete this and `tried` can start listing
    the steps an answer took, which differ between a refusal and an absence."""
    skill = escalating()
    made = escalation_for(
        skill,
        route=EscalationRoute(queue="pricing", channel=Channel.CONSOLE),
        asker_id="u_asker",
        question="What does the premium plan cost for a charity?",
        trace_ref="t-1",
        now=LONG_AGO,
    )
    assert made.trigger is EscalationTrigger.ABSTENTION
    assert made.handoff.tried == (*TRIED, "skill.quote_desk") == tried_by(skill)
    assert made.handoff.needed == NEEDS
    assert made.expires_at - made.raised_at == timedelta(hours=2)


def test_the_only_trigger_a_declaration_raises_is_an_abstention() -> None:
    """Delete this and a model's reply could be made a trigger by a later edit, which is the one
    thing `MODEL_JUDGEMENT_IS_NOT_A_TRIGGER` exists to prevent."""
    assert "model" in MODEL_JUDGEMENT_IS_NOT_A_TRIGGER.lower()
    assert {one.value for one in EscalationTrigger} == {
        "authored step",
        "abstention",
        "approval required",
    }


def test_an_escalation_for_another_queue_is_refused() -> None:
    """Delete this and a route read for one queue can carry a skill's question to another."""
    with pytest.raises(ValueError, match="does not escalate to"):
        escalation_for(
            escalating(),
            route=EscalationRoute(queue="finance", channel=Channel.CONSOLE),
            asker_id="u_asker",
            question="How much?",
            trace_ref="t-1",
            now=LONG_AGO,
        )


def test_every_escalation_has_a_deadline_and_the_default_is_the_product_s() -> None:
    """Delete this and a skill that states no hours escalates with no deadline at all."""
    assert ttl_of(escalating(within=None)) == DEFAULT_ESCALATION_TTL
    assert ttl_of(escalating(within=5)) == timedelta(hours=5)


def test_the_person_is_sent_the_handoff_s_own_fields_and_the_asker_one_sentence() -> None:
    """Delete this and the message to the named person can drop what is needed, or the asker can
    be told about the person rather than the queue."""
    text = handoff_text(
        queue="pricing",
        asker="Asha Asker",
        question="What does it cost?",
        tried=("answer.searched_at_the_askers_reach", "skill.quote_desk"),
        needed=NEEDS,
        expires_at=LONG_AGO,
    )
    for part in ("pricing", "Asha Asker", "What does it cost?", "skill.quote_desk", NEEDS):
        assert part in text
    assert "04 Mar 2019 09:00 UTC" in text
    assert said_to_asker("pricing", expired=False) == ESCALATION_TEXT.format(queue="pricing")
    assert said_to_asker("pricing", expired=True) == ESCALATION_EXPIRED_TEXT.format(queue="pricing")
