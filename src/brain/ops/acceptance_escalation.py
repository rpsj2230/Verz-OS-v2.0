"""The install acceptance checks for escalation and sensitive topics (M8.4.1).

M8.4.1 asks two things of an install. An escalated question reaches the named person in their own
channel with who asked, what, what was tried and what is needed, and times out as configured. And a
question about HR, harassment, whistleblowing, salary, medical or legal matters is intercepted and
routed before any agent answers, without its content being recorded. One check each, because they
are two flows and a red row should say which one broke.

**Each check is the routes' own functions in the routes' order.** The skill is added, approved and
assigned through the Skills screen's sequence (`brain.ops.acceptance_checks_skills`), the queue's
person is named through `brain.ops.escalation_store`, the question is asked through `/answer`'s own
`answered_for` with the stand-in model (`brain.ops.acceptance_answers.asking_with_a_stand_in`), and
the handoff is sent by the product's own `brain.channels.outbound.deliver` on a webhook channel set
up in the check, whose transport keeps each request and sends nothing, as
`brain.ops.acceptance_checks.a_webhook_channel_receives_once_and_stops_both_ways` does. Nothing
reaches a real person. See `THE_HANDOFF_REACHES_A_CHANNEL_THE_CHECK_HOLDS`.

**A restricted document is in play, and the named person learns nothing of it.** A document in
acceptance_b pairs a word with a value. A member of acceptance_a asks about the word through an
agent whose skill escalates: the answer abstains, and what the member reads is word for word what
a question about a word nothing holds reads; the handoff sent carries the member's question and
never the document's value or title. See `A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`.

**The timeout is the skill's own, and the worker's control expires it.** The skill says one hour.
The check reads the row's deadline, then runs `brain.ops.escalation_store.expire_overdue` as the
worker's login at a moment past it, in a savepoint of its transaction, as the knowledge review
check runs its sweep, and on a login that cannot read past a policy it says it was not run.

Task ids: M38.5.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Why the check's handoff reaches a transport the check holds.
THE_HANDOFF_REACHES_A_CHANNEL_THE_CHECK_HOLDS: Final = (
    "The named person is reached through the product's own sender on a webhook channel the check "
    "sets up, whose transport keeps what it was asked to send and sends nothing, so the check "
    "reads exactly what a person would have been sent and no person is sent anything."
)

#: The queue the check's skill escalates to. A name no install gives a queue of its own; the
#: person named for it is named inside the check's transaction and rolled back with it.
QUEUE: Final = "acceptance_escalations"

#: What the check's skill says is needed, as its author would write it.
NEEDED: Final = "Somebody who can answer this from a document the asker may read"

#: The hours the check's skill gives a person, the shortest a skill may give.
WITHIN_HOURS: Final = 1

#: Why the expiry was not run on this install.
THE_EXPIRY_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN: Final = (
    "this login cannot mark a handoff expired, which the worker's escalation_expiry control does "
    "as its own login, so the timeout was not checked here; the worker's own run does it"
)

#: Why the send was not checked on this install.
THE_NOTICE_IS_SWITCHED_OFF: Final = (
    "an administrator has switched the notice of a question handed to a person off on this "
    "install, so the handoff is listed and not sent, and its sending was not checked"
)


@dataclass
class _Kept:
    """`brain.channels.adapter.ChannelTransport` that keeps each request and sends nothing."""

    sent: list[Any] = field(default_factory=list)

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=200)

    def read(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        del request
        return VendorAnswer(connection_failed=True)


def _sent_text(kept: _Kept) -> str:
    """Every message the transport was asked to send, as one text: the webhook body's `text`."""
    import json

    found = []
    for one in kept.sent:
        body = json.loads(bytes(getattr(one, "body", b"{}")).decode("utf-8"))
        found.append(str(body.get("text", "")) if isinstance(body, dict) else "")
    return "\n".join(found)


async def _escalating_agent(h: Harness) -> tuple[str, str]:
    """An agent of acceptance_a reading knowledge, with a skill that escalates to `QUEUE` within
    `WITHIN_HOURS`, added, approved and assigned through the Skills screen's sequence. Returns the
    agent and the skills administrator."""
    from brain.console.skill_library import added, decided, read_package
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
        _named,
        _skill_md,
        _store,
    )
    from brain.ops.skill_store import StoredSkills

    admin = await _administrator(h, "escalations")
    reach = await h.reach(admin)
    made = added(
        read_package(
            "SKILL.md",
            _skill_md(
                _named(h, "escalates"),
                description="Use when a question in an acceptance check finds nothing to answer it",
                extra=(
                    f"escalate_to: {QUEUE}",
                    f"escalation_needs: {NEEDED}",
                    f"escalate_within: {WITHIN_HOURS}",
                ),
            ),
        ),
        by=admin,
        at=h.now,
    )
    if made.imported.skill.escalate_to != QUEUE:
        raise CheckFailedError("a skill declaring a queue was read without it")
    await _store(h, made, reach)
    approval = decided(made, reviewer=admin, approve=True, at=h.now)
    if not await StoredSkills(h.sessions).decide(
        approval, ent_hash=reach.ent_hash(), trace_id=h.trace_id
    ):
        raise CheckFailedError("an administrator could not approve the skill they added")
    agent = await _an_agent(h, admin, capabilities=KNOWLEDGE_READS)
    await _assign(h, made.digest, agent, reach)
    return agent, admin


async def _expired(h: Harness, at: Any) -> int:
    """The worker's `escalation_expiry` at `at`, as its login, in a savepoint of the check."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.ops.escalation_store import expire_overdue
    from brain.session import LOGIN_BYPASSES_ROW_SECURITY

    if not (await h.execute(LOGIN_BYPASSES_ROW_SECURITY)).scalar_one():
        raise CheckNotRunError(THE_EXPIRY_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN)
    async with (
        AsyncSession(
            bind=h.connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        ) as session,
        session.begin(),
    ):
        await session.execute(text("RESET ROLE"))
        return await expire_overdue(session, now=at)


@check(
    leaves=("M8.3.1", "M8.3.2", "M8.3.4", "M8.4.1"),
    sentence=(
        "A member of acceptance_a asks an agent whose approved skill escalates about a word only "
        "a document in acceptance_b holds: they read what a word nothing holds reads, plus one "
        "sentence naming the queue; the named person's channel is sent who asked, the question, "
        "what was tried and what is needed, and nothing of the document; it expires on time."
    ),
)
async def an_escalated_question_reaches_its_person_and_times_out(h: Harness) -> None:
    from brain.channels.webhook import REPLY_URL
    from brain.chat_answer import chat_text
    from brain.gate.abstain import ESCALATION_TEXT
    from brain.gate.context import Channel
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_answers import asking_with_a_stand_in
    from brain.ops.acceptance_checks import _HeldLedger, _Secret
    from brain.ops.acceptance_models import Paired, asked, paired_in
    from brain.ops.acceptance_routing import roster_over
    from brain.ops.channel_store import StoredChannels
    from brain.ops.escalation_store import StoredEscalations
    from brain.tables.escalation import EscalationDelivery

    s = await asking_with_a_stand_in(h)
    agent, admin = await _escalating_agent(h)
    person, keeper = h.principal(B, "escalations"), h.principal(B, "library")
    await h.person(person, department=B, grants=_in(B, *KNOWLEDGE_READS))
    await h.person(keeper, department=B, grants=_in(B, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    restricted = await paired_in(h, B, keeper)

    # The person is named for the queue, reached on a webhook channel the check holds.
    await StoredChannels(h.sessions).save(
        Channel.WEBHOOK,
        enabled=True,
        tenant={REPLY_URL: f"https://acceptance.invalid/{h.run}"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    store = StoredEscalations(h.sessions)
    admin_reach = await h.reach(admin)
    await store.name_route(
        QUEUE,
        person,
        Channel.WEBHOOK,
        f"acceptance-{h.run}",
        by=admin,
        ent_hash=admin_reach.ent_hash(),
        trace_id=h.trace_id,
    )
    kept = _Kept()
    s.app.state.agent_roster = roster_over(h)
    s.app.state.channel_transport = kept
    s.app.state.channel_secrets = _Secret("acceptance-webhook-secret")
    s.app.state.operation_ledger = _HeldLedger()

    # Asked about the restricted document's word, and about a word nothing holds.
    before = s.ask_sent()
    withheld = await asked(h, s.app, s.reader, restricted.question, 1, agent=agent)
    nothing = await asked(h, s.app, s.reader, Paired(h.word(), "").question, 2, agent=agent)
    if s.ask_sent() != before:
        raise CheckFailedError("a model was asked about a question nothing the member may see")
    if withheld.abstention is None or nothing.abstention is None:
        raise CheckFailedError("a question nothing the member may see answers was answered")
    told = ESCALATION_TEXT.format(queue=QUEUE)
    if chat_text(withheld) != chat_text(nothing) or told not in chat_text(withheld):
        raise CheckFailedError(
            "a question about a document the member may not see read differently from one "
            "about nothing, or did not say it was handed to a person"
        )

    # The named person's channel was sent each handoff, and nothing of the document.
    handoffs = [one for one in await store.mine(person) if one.asker_id == s.reader]
    if len(handoffs) != 2 or {one.routed_to for one in handoffs} != {person}:
        raise CheckFailedError("the two handoffs were not routed to the person named for the queue")
    if any(one.delivery is EscalationDelivery.NOT_SENT for one in handoffs):
        raise CheckNotRunError(THE_NOTICE_IS_SWITCHED_OFF)
    if any(one.delivery is not EscalationDelivery.SENT for one in handoffs) or len(kept.sent) != 2:
        raise CheckFailedError("a handoff was not sent to the named person's own channel")
    sent = _sent_text(kept)
    if restricted.question not in sent or NEEDED not in sent or "Tried:" not in sent:
        raise CheckFailedError("the handoff sent did not say what was asked, tried and needed")
    if restricted.value in sent or any(word in sent for word in ("not_entitled", "withheld")):
        raise CheckFailedError("the handoff sent carried something the member could not see")

    # The timeout the skill set, and the worker's control expiring it at that moment and not before.
    # Only the check's own rows are judged: the control expires every handoff on the install that
    # is due, and a real one due before the check's is none of its business.
    first = handoffs[0]
    if any(one.expires_at - one.raised_at != timedelta(hours=WITHIN_HOURS) for one in handoffs):
        raise CheckFailedError("the handoff's deadline was not the one its skill set")

    async def still_open() -> int:
        mine = [one for one in await store.mine(s.reader) if one.asker_id == s.reader]
        return sum(one.expired_at is None for one in mine)

    await _expired(h, first.expires_at - timedelta(seconds=1))
    if await still_open() != len(handoffs):
        raise CheckFailedError("a handoff was marked expired before its deadline")
    await _expired(h, max(one.expires_at for one in handoffs))
    if await still_open() != 0:
        raise CheckFailedError("the member's own list did not say nobody picked their question up")


@check(
    leaves=("M8.4.1",),
    sentence=(
        "A member of acceptance_a asks a question about harassment carrying a word nothing else "
        "holds: it is routed to the person named for the topic and answered with the referral "
        "sentence before any model is asked, and afterwards the word is in no table."
    ),
)
async def a_sensitive_question_is_routed_before_any_agent_answers(h: Harness) -> None:
    from brain.audit.compliance import SensitiveTopic, intercept
    from brain.chat_answer import chat_text
    from brain.ops.acceptance_answers import asking_with_a_stand_in
    from brain.ops.acceptance_checks_connectors import _search
    from brain.ops.acceptance_models import asked
    from brain.ops.sensitive_referral_store import StoredSensitiveReferrals

    s = await asking_with_a_stand_in(h)
    named = h.principal(B, "referrals")
    await h.person(named, department=B, grants=_in(B, *KNOWLEDGE_READS))
    referrals = StoredSensitiveReferrals(h.sessions)
    await referrals.name(
        SensitiveTopic.HARASSMENT, named, by=h.actor, ent_hash="0" * 32, trace_id=h.trace_id
    )
    canary = h.word()
    question = f"I want to report harassment by {canary} in my team"
    decision = intercept(question, trace_id=h.trace_id)
    if decision.topic is not SensitiveTopic.HARASSMENT:
        raise CheckFailedError("a question about harassment was not recognised as one")

    before = s.ask_sent()
    answered = await asked(h, s.app, s.reader, question, 1)
    if s.ask_sent() != before or not answered.referred:
        raise CheckFailedError("a sensitive question reached a model before it was routed")
    reply = decision.reply()
    if reply is None or reply not in chat_text(answered) or canary in chat_text(answered):
        raise CheckFailedError("the asker was not told the one referral sentence")
    routed = [one for one in await referrals.mine(named) if one.asked_by == s.reader]
    if [(one.topic, one.routed_to) for one in routed] != [(SensitiveTopic.HARASSMENT, named)]:
        raise CheckFailedError("the question was not routed to the person named for its topic")
    if await _search(h, canary):
        raise CheckFailedError("a word from a sensitive question was recorded in a table")
