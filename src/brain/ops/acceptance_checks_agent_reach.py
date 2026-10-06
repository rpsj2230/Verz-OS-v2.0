"""The install acceptance check for asking through an agent: the narrower reach, on every channel.

`E_run(caller, agent) = E(caller) ∩ agent_ceiling` is the rule the whole product serves, and
`brain.gate.roster.run_entitlement` is where an answer takes it. M13.7.5 asks for it as a person
meets it: a question that reaches an agent, through the web or through a chat, is answered at the
narrower of the asker's reach and the agent's ceiling, never at the wider. M13.1.3 asks for the
audience to be separate from the authority: who may use an agent is one fact and what it reaches
is another.

**Both directions of "narrower", because each has its own way to be wrong.** A table uploaded
into acceptance_a has an open column and a held one. One agent's ceiling holds the open column
only; the other's holds both. A person holding both asks the first agent for the held value and
must not be told it, though asking with no agent they are: the agent narrows a wider person. A
person holding the open column only asks the second agent and must not be told it either: a
wider agent does not lend a narrower person its reach. Each is answered exactly as a row that
does not exist is answered, because a withheld value and an absent one are one answer.

**The web and Lark are asked the same questions.** The web is `/answer`'s own function with the
agent picked beside the question; Lark is the install's events address with a signed direct
message opening `@agent`, which `brain.gate.addressing.from_mention` reads. Rejected: asking
`run_entitlement` directly, which proves the function and not that each channel goes through it.

**Audience is not authority.** A member of acceptance_b holding the same reads in acceptance_a as
the wider person is outside both agents' audience. Naming the narrower agent does nothing for
them: they are answered exactly as when they name an agent that does not exist, which is at
their own reach, while the wider person, inside the audience with the same authority, is
narrowed by it.

Task ids: M13.7.5, M13.1.3
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_chat import (
    bound,
    chat_id,
    heard,
    lark_app,
    open_id,
    undated,
    uploaded,
)
from brain.ops.acceptance_routing import roster_over
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.acceptance_checks_chat import _Heard, _LarkApp, _Table

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 404

NOT_ANSWERED_PLAINLY: Final = "a person holding a column was not told it with no agent picked"
WIDER_THAN_THE_AGENT: Final = "an answer through an agent went past the agent's ceiling"
WIDER_THAN_THE_ASKER: Final = "an agent lent a person a reach the person does not hold"
TOLD_IT_EXISTS: Final = "a value withheld through an agent was answered unlike a missing row"
OPEN_NOT_ANSWERED: Final = "an agent did not answer what both it and its asker may read"
CHAT_DIFFERS: Final = "a question through an agent in Lark was not answered as on the web"
AUDIENCE_IS_AUTHORITY: Final = "a person outside an agent's audience was answered through it"


async def _agent(h: Harness, owner: str, name: str, capabilities: Sequence[str]) -> str:
    """An agent of acceptance_a, enabled, whose ceiling holds exactly `capabilities` there.

    The three rows `brain.agents.install_store.finish` writes, as the skills check writes them,
    with a template signed by a key made for the check.
    """
    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        TemplateManifest,
        install,
        materialise,
        publish,
    )
    from brain.core.entitlement import Capability
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    agent_id, key = f"acceptance_{h.run}_{name}", secrets.token_hex(32)
    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id=agent_id,
                version=1,
                published_by=owner,
                display_name=f"Acceptance {name} agent",
            ),
            persona="Answers an install acceptance check and nobody else.",
            authority=ManifestAuthority(
                scope=Scope.department(A),
                capabilities=tuple(Capability(value=one) for one in capabilities),
            ),
        ),
        key=key,
        signed_by=owner,
        at=h.now,
    )
    instance = install(signed, key=key, instance_id=agent_id, created_by=owner, at=h.now)
    effective = materialise(
        signed,
        instance,
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department=A),
    )
    await h.execute(
        *h.attributed(owner),
        insert(TemplateVersionRow).values(**version_values(signed)),
        insert(TemplateInstanceRow).values(
            id=agent_id,
            template_id=instance.template_id,
            template_version=instance.template_version,
            content_digest=instance.content_digest,
            overlay=dict(instance.overlay),
            field_owners={},
            effective_document=dict(effective.document),
            effective_hash=effective.config_hash,
            created_by=owner,
        ),
        insert(AgentRow).values(**agent_values(effective.record)),
    )
    return agent_id


async def _on_the_web(
    chat: _LarkApp, principal_id: str, question: str, agent: str | None
) -> _Heard:
    """What the web's Ask streams this person, with `agent` picked beside the question."""
    from brain.api_routes import Answering, Question, answered_for
    from brain.gate.admission import Assurance, admit
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.identity.principal_store import StoredPrincipals

    h = chat.h
    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    now = datetime.now(UTC)
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    outcome = await answered_for(
        chat.request(),
        open_trace(f"{h.trace_id}-{secrets.token_hex(4)}", now, Channel.CONSOLE),
        Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=now),
        Question(question=question, agent=agent),
    )
    if not isinstance(outcome, Answered):
        raise CheckFailedError("the web's answer was refused by a window the check never uses")
    return heard(outcome.frames)


async def _in_lark(chat: _LarkApp, identity: str, question: str, agent: str) -> str:
    """The reply to a direct message opening `@agent`, without each source's read instant."""
    direct = chat_id()
    before = len(chat.lark.sent)
    await chat.post(identity, f"@{agent} {question}", chat=direct, group=False, to_bot=False)
    sent = chat.lark.messages()[before:]
    if len(sent) != 1:
        raise CheckFailedError("a direct message naming an agent was not answered in its chat")
    return undated(sent[0][2])


def _says(answer: _Heard, value: str) -> bool:
    return value in answer.prose


@check(
    leaves=("M13.7.5", "M13.1.3"),
    sentence=(
        "Asked on the web and in Lark about a row of a table in acceptance_a, an agent whose "
        "ceiling lacks a column does not tell a person who holds it, and an agent holding it does "
        "not tell a person who lacks it, each answered as for a missing row; a member of "
        "acceptance_b with the same reads naming the first agent is answered as for no agent."
    ),
)
async def asking_through_an_agent_is_answered_at_the_narrower_reach(h: Harness) -> None:
    await h.found_departments()
    chat = await lark_app(h)
    # The stored agents, read on each question as the application's roster reads them.
    chat.app.state.agent_roster = roster_over(h)
    table: _Table = await uploaded(h)
    held_reads = table.reads(A, held=True)
    open_reads = table.reads(A, held=False)

    owner = h.principal(A, "owner")
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    outsider = h.principal(B, "outsider")
    await h.person(owner, department=A, grants=held_reads)
    await h.person(wide, department=A, grants=held_reads)
    await h.person(narrow, department=A, grants=open_reads)
    await h.person(outsider, department=B, grants=held_reads)
    open_only = await _agent(h, owner, "open", [one for one, _ in open_reads])
    everything = await _agent(h, owner, "held", [one for one, _ in held_reads])
    ids = {wide: open_id(), narrow: open_id(), outsider: open_id()}
    await bound(chat, ids)

    held_question = table.asking(table.held_column)
    open_question = table.asking(table.open_column)
    missing = table.asking(table.held_column, h.word())

    if not _says(await _on_the_web(chat, wide, held_question, None), table.held):
        raise CheckFailedError(NOT_ANSWERED_PLAINLY)
    narrowed = await _on_the_web(chat, wide, held_question, open_only)
    if _says(narrowed, table.held):
        raise CheckFailedError(WIDER_THAN_THE_AGENT)
    if narrowed != await _on_the_web(chat, wide, missing, open_only):
        raise CheckFailedError(TOLD_IT_EXISTS)
    lent = await _on_the_web(chat, narrow, held_question, everything)
    if _says(lent, table.held):
        raise CheckFailedError(WIDER_THAN_THE_ASKER)
    if lent != await _on_the_web(chat, narrow, missing, everything):
        raise CheckFailedError(TOLD_IT_EXISTS)
    shared = await _on_the_web(chat, narrow, open_question, everything)
    if not _says(shared, table.seen):
        raise CheckFailedError(OPEN_NOT_ANSWERED)

    for asker, question, agent, web in (
        (wide, held_question, open_only, narrowed),
        (narrow, held_question, everything, lent),
        (narrow, open_question, everything, shared),
    ):
        if not web.is_what(await _in_lark(chat, ids[asker], question, agent)):
            raise CheckFailedError(CHAT_DIFFERS)

    nobody = f"acceptance_{h.run}_nobody"
    named = await _on_the_web(chat, outsider, held_question, open_only)
    if named != await _on_the_web(chat, outsider, held_question, nobody):
        raise CheckFailedError(AUDIENCE_IS_AUTHORITY)
