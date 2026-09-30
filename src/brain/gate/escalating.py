"""Which skill hands an unanswered question to a person, and what the person and the asker read.

`brain.gate.abstain` holds the escalation itself: its triggers, its route, its handoff and its
expiry. This is the part the answer path needs and that module had nowhere to put: from the skills
an agent runs with, which one declares an escalation, the handoff built from what the asker gave and
nothing else, and the two sentences, one for the named person and one for the asker.

**A skill declares it and an abstention fires it (M8.3.1).** `declared_by` picks, from the skills a
run offers (pinned, approved, unmoved and within the run's reach, which is
`brain.gate.model_lane.skills_offered`), the first by name that names a queue. The trigger is always
`EscalationTrigger.ABSTENTION`. There is no path by which a model's reply raises one, for
`brain.gate.abstain.MODEL_JUDGEMENT_IS_NOT_A_TRIGGER`'s reason. First by name, because two skills
on one agent both declaring a queue is a configuration somebody should see and fix, and a choice
that depended on the order they were pinned in would change without anybody changing anything.

**A handoff carries what the asker could see and nothing more (M8.3.2).** Who asked, their
question in their own words, what was tried as step names, what the skill's author said is needed,
and the trace to quote. Never a passage, a record, a field, a title, or the abstention's reason:
the person it is routed to may hold less than the asker, and an abstention the asker was refused
reads to the asker exactly as one with nothing behind it, so it reads the same to the person too.
`tried` is `TRIED` and the skill's own name for the same reason, a constant rather than the steps
the answer happened to reach: a refusal and an absence stop at different steps, and a list of steps
that differed between them would say which one it was. See
`A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`.

**Every escalation expires (M8.3.4).** The skill's `escalate_within` hours, or
`brain.gate.abstain.DEFAULT_ESCALATION_TTL`, and `raise_escalation` refuses to make one without.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M8.3.1, M8.3.2, M8.3.4
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from brain.gate.abstain import (
    DEFAULT_ESCALATION_TTL,
    ESCALATION_EXPIRED_TEXT,
    ESCALATION_TEXT,
    Escalation,
    EscalationRoute,
    EscalationTrigger,
    Handoff,
    raise_escalation,
)
from brain.tools.skills import ImportedSkill, Skill

# ------------------------------------------------------------------ written-down reasons
#: Why a handoff holds the asker's words, step names and the author's sentence, and nothing else.
A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE: Final = (
    "The person a question is handed to may hold less than the asker, and to the asker a refusal "
    "reads exactly as an absence. So the handoff carries the question in the asker's words, what "
    "was tried as fixed step names, and the sentence the skill's author wrote, and never a "
    "passage, a record, a title or why the answer abstained: anything more would tell the person "
    "something the asker could not see, or tell anybody which of the two it was."
)

#: What was tried before any escalation: the question searched at the asker's own reach. The
#: same for every escalation, for `A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`'s reason.
TRIED: Final[tuple[str, ...]] = ("answer.searched_at_the_askers_reach",)

#: What the named person is sent. Every field is one the handoff already holds.
HANDOFF_TEXT: Final = (
    "A question for {queue}, handed on because nothing answered it.\n"
    "Asked by: {asker}\n"
    "Question: {question}\n"
    "Tried: {tried}\n"
    "Needed: {needed}\n"
    "Please pick it up by {expires}."
)


def declared_by(skills: Iterable[ImportedSkill]) -> Skill | None:
    """The skill whose declared escalation applies: the first by name that names a queue.

    Among the executable ones only, so a declaration in a skill nobody approved, or one edited
    since it was, sends nothing anywhere.
    """
    declaring = sorted(
        (one.skill for one in skills if one.is_executable() and one.skill.escalate_to),
        key=lambda skill: skill.name,
    )
    return declaring[0] if declaring else None


def tried_by(skill: Skill) -> tuple[str, ...]:
    """What the handoff says was tried: `TRIED`, and the skill's own name as a step."""
    return (*TRIED, f"skill.{skill.name.replace('-', '_')}")


def ttl_of(skill: Skill) -> timedelta:
    """How long a person has to pick this skill's escalation up."""
    if skill.escalate_within is None:
        return DEFAULT_ESCALATION_TTL
    return timedelta(hours=skill.escalate_within)


def escalation_for(
    skill: Skill,
    *,
    route: EscalationRoute,
    asker_id: str,
    question: str,
    trace_ref: str,
    now: datetime,
) -> Escalation:
    """The escalation this skill's declaration raises for this abstention.

    Raises `ValueError` for a skill that declares none, which a caller reaching here has not
    checked, and for anything `Handoff` refuses.
    """
    if not skill.escalate_to or skill.escalate_to != route.queue:
        msg = f"skill {skill.name!r} does not escalate to {route.queue!r}"
        raise ValueError(msg)
    return raise_escalation(
        trigger=EscalationTrigger.ABSTENTION,
        route=route,
        handoff=Handoff(
            asker_id=asker_id,
            question=question,
            tried=tried_by(skill),
            needed=skill.escalation_needs,
            trace_ref=trace_ref,
        ),
        now=now,
        ttl=ttl_of(skill),
    )


def handoff_text(
    *,
    queue: str,
    asker: str,
    question: str,
    tried: Sequence[str],
    needed: str,
    expires_at: datetime,
) -> str:
    """What the named person is sent: `HANDOFF_TEXT` over the handoff's own fields."""
    return HANDOFF_TEXT.format(
        queue=queue,
        asker=asker,
        question=question,
        tried=", ".join(tried),
        needed=needed,
        expires=expires_at.astimezone(UTC).strftime("%d %b %Y %H:%M UTC"),
    )


def said_to_asker(queue: str, *, expired: bool) -> str:
    """The one sentence the asker is told about an escalation, before or after it expired."""
    return (ESCALATION_EXPIRED_TEXT if expired else ESCALATION_TEXT).format(queue=queue)
