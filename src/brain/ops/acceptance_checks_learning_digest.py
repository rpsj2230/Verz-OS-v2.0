"""The install acceptance check for the weekly learning digest: a person is told their own week
once, in their own chat, with where to undo each thing, and told nothing they may not recall.

The check forms memories on Ask through `brain.api_routes.answered_for`, as
`brain.ops.acceptance_checks_learning` does, so the learning records are the install's own. It
then runs `brain.learning_told.send_learning_digests`, the function the web process's loop runs,
over the check's own people and a week ending now, through `brain.tell_later.tell` on a Slack
channel the check sets up, whose transport keeps each request and sends nothing, with the operation
ledger in memory. Every write is in the check's rolled-back transaction, and nothing reaches a real
person. See `THE_WEEK_REACHES_A_CHANNEL_THE_CHECK_HOLDS`.

**What the check proves.** A member of acceptance_a who formed a memory that week is sent one
message, in their own Slack conversation, naming that memory with where its undo is, and the
undo it links marks it when pressed as them, though they hold no member grant. A memory they
formed under a grant since removed, and a colleague's memory, are named nowhere in it. A member of
acceptance_b who formed nothing is sent nothing. A second run over the same week sends nothing
more.

**What it does not prove**, stated: that the loop the application starts runs on the install, which
is a property of the process and is logged on every pass, and that Slack accepts the message with
the install's own app, which the Connect Slack test proves.

Task ids: M16.5.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check

# The memory checks' people and the stated memory helper, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks_learning import stated_memory
from brain.ops.acceptance_checks_memory import memory_app, people
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 282

#: Why the week is sent to a channel the check holds.
THE_WEEK_REACHES_A_CHANNEL_THE_CHECK_HOLDS: Final = (
    "The week is told through the product's own sender on a Slack channel the check sets up, whose "
    "transport keeps what it was asked to send and sends nothing, with the operation ledger held "
    "in memory, so the check reads exactly what each person would have been sent and nobody is "
    "sent anything."
)

#: The grant the check removes before forming the memory its person may then not recall.
REMOVED: Final = "read:knowledge.title"

# ------------------------------------------------------------------------ the verdicts
THE_LEARNING_DIGEST_IS_SWITCHED_OFF: Final = (
    "an administrator has switched the weekly learning digest off on this install, so nobody is "
    "told their week, and that telling was not checked"
)
NOT_SENT_ONCE: Final = (
    "a person who formed a memory that week was not sent one message in their own chat"
)
NOT_NAMED_WITH_UNDO: Final = (
    "the week's message did not name the memory learnt with where its undo is"
)
NAMED_OUTSIDE_REACH: Final = (
    "the week's message named a memory its person may not recall or somebody else's"
)
SENT_WITH_NOTHING_LEARNT: Final = "a person who formed nothing that week was sent a message"
SENT_TWICE: Final = "a second run over the same week sent the week's message again"
UNDO_DID_NOTHING: Final = "the undo the week's message linked did not mark the memory"
MEMBER_GRANT_HELD: Final = (
    "the check's person held the member grant, so it could not show the undo works without it"
)


def _sent(kept: Any, before: int) -> list[tuple[str, str]]:
    """Each message the transport was handed since `before`, as Slack's channel and text."""
    import json

    found = []
    for one in kept.sent[before:]:
        body = json.loads(bytes(one.body).decode("utf-8"))
        found.append((str(body.get("channel", "")), str(body.get("text", ""))))
    return found


async def _on_slack(h: Harness, people: dict[str, str]) -> None:
    """A Slack channel the check holds, and each person bound on it with their own address kept, as
    their own message would keep it."""
    from functools import partial

    from brain.channels.adapter import BOT_ID
    from brain.channels.binding import settle
    from brain.gate.context import Channel
    from brain.gate.ingress import Binding, identity_hash
    from brain.ops.binding_store import StoredAddresses, StoredBindings
    from brain.ops.channel_store import StoredChannels

    await StoredChannels(h.sessions).save(
        Channel.SLACK,
        enabled=True,
        tenant={BOT_ID: "UACCEPT0BOT"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    for principal_id, slack_id in people.items():
        fresh = Binding(
            channel=Channel.SLACK,
            identity_hash=identity_hash(Channel.SLACK, slack_id),
            principal_id=principal_id,
            bound_at=h.now,
        )
        await StoredBindings(h.sessions).bind(
            fresh, decide=partial(settle, fresh), trace_id=h.trace_id
        )
        if not await StoredAddresses(h.sessions).remember(Channel.SLACK, slack_id):
            raise CheckFailedError("a Slack binding did not keep its person's own address")


@check(
    leaves=("M16.5.1",),
    sentence=(
        "A member of acceptance_a who formed a memory on Ask that week is sent one message in "
        "their own Slack chat naming it with where to undo it, and that undo marks it without the "
        "member grant; a memory formed under a grant since removed and a colleague's are named "
        "nowhere; a member of acceptance_b who formed nothing is sent nothing; and a second run "
        "sends nothing more."
    ),
)
async def a_persons_week_of_learning_is_told_once_with_its_undo(h: Harness) -> None:
    import json
    from types import SimpleNamespace

    from brain.channels.slack import BOT_TOKEN, SIGNING_SECRET
    from brain.console.reads import permitted
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.govern_routes import retire_grant
    from brain.learning_told import CoveredWeek, send_learning_digests, undo_link, undo_page_here
    from brain.locale import time_zone
    from brain.mailbox_read import request_for
    from brain.member.shell import member_screen
    from brain.memory.digest import DIGEST_PERIOD
    from brain.mine_routes import MEMBER_HOME, forgotten
    from brain.ops.acceptance_checks import _HeldLedger, _Secret
    from brain.ops.acceptance_escalation import _Kept
    from brain.ops.memory_store import StoredMemoryRecords

    placed = await people(h)
    member_on, other_on = f"UACC{h.run.upper()}M", f"UACC{h.run.upper()}O"
    await _on_slack(h, {placed.member: member_on, placed.other: other_on})

    hidden = await stated_memory(h, placed.member, f"I sign as {h.word()}", 1)
    await h.execute(*h.attributed(), retire_grant(placed.member, REMOVED))
    kept_memory = await stated_memory(h, placed.member, f"I work from {h.word()} on Fridays", 2)
    theirs = await stated_memory(h, placed.colleague, f"I sign as {h.word()}", 3)

    app = await memory_app(h)
    kept = _Kept()
    app.state.channel_transport = kept
    app.state.operation_ledger = _HeldLedger()
    app.state.channel_secrets = _Secret(
        json.dumps({SIGNING_SECRET: f"acceptance-{h.run}", BOT_TOKEN: f"xoxb-acceptance-{h.run}"})
    )
    readers = StoredEntitlements(h.sessions)
    # The reach a message is held to when it leaves, from the install's own grants, as a process
    # with its gate wired reads it.
    app.state.gate = SimpleNamespace(store=readers)

    at = datetime.now(UTC)
    week = CoveredWeek(covers_from=at - DIGEST_PERIOD, covers_to=at, key=f"acceptance-{h.run}")
    page = undo_page_here()

    async def run() -> Any:
        return await send_learning_digests(
            request_for(app),
            h.sessions,
            now=at,
            zone=time_zone(),
            page=page,
            readers=readers,
            week=week,
            only=(placed.member, placed.other),
        )

    told = await run()
    if told.switched_off:
        raise CheckNotRunError(THE_LEARNING_DIGEST_IS_SWITCHED_OFF)
    first = _sent(kept, 0)
    if any(channel == other_on for channel, _ in first):
        raise CheckFailedError(SENT_WITH_NOTHING_LEARNT)
    mine = [said for channel, said in first if channel == member_on]
    if len(mine) != 1 or len(first) != 1:
        raise CheckFailedError(NOT_SENT_ONCE)
    [said] = mine
    if hidden in said or theirs in said:
        raise CheckFailedError(NAMED_OUTSIDE_REACH)
    if undo_link(page, kept_memory) not in said:
        raise CheckFailedError(NOT_NAMED_WITH_UNDO)

    again = await run()
    if _sent(kept, len(first)) or again.sent:
        raise CheckFailedError(SENT_TWICE)

    # Undone as the person, who holds no member grant: the route the link's page posts asks for
    # none, and its body is this function. `tests/unit/test_mine_routes.py` holds the route itself.
    member = await h.reach(placed.member)
    if permitted(member_screen(MEMBER_HOME).read, member, at):
        raise CheckFailedError(MEMBER_GRANT_HELD)
    undone = await forgotten(
        h.sessions,
        StoredMemoryRecords(h.sessions),
        principal_id=placed.member,
        memory_id=kept_memory,
        ent_hash=member.ent_hash(),
        trace_id=h.trace_id,
        now=at,
    )
    if undone is None or not undone.took_effect:
        raise CheckFailedError(UNDO_DID_NOTHING)
