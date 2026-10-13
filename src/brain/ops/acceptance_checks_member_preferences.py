"""Install acceptance checks for a person's own settings: learning, reach, quiet hours, approvals.

Each is the route or the sender the setting reaches, as a reserved member signed in through the
install's own gate (`brain.ops.acceptance_people_signed_in`). **A setting is shown to take effect
where it is read**: personal learning forms nothing once it is off, a digest is held inside quiet
hours and by a channel that does not list it and is sent once they are out of the way, and an
approver who chose the console is sent no Lark card while one who chose nothing is. A check that
read a setting back and stopped there would prove a table.

**What is stood in for is the vendor and nothing else.** Slack and Lark are channels the check sets
up whose transport keeps what it is handed and sends nothing; every row is rolled back with the
check and nothing reaches a person.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check

# The memory checks' people and helper, imported rather than copied, and imported first so the
# suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks_learning import stated_memory
from brain.ops.acceptance_checks_memory import ask, memories_of, memory_app, people
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1920


# ------------------------------------------------------------- 1. learning (M40.4.1.4)
@check(
    leaves=("M40.4.1.4",),
    sentence=(
        "A person who switches personal learning off is told what it costs and has nothing more "
        "formed from what they say on Ask, while what was learnt before stays; switched on again "
        "it forms again, and a colleague's learning is unchanged throughout."
    ),
)
async def a_person_who_switches_learning_off_has_nothing_more_formed(h: Harness) -> None:
    from brain.member_preference_routes import LearningAsked, my_preferences, set_learning
    from brain.ops.member_preference_store import StoredPreferences

    placed = await people(h)
    c = await console(h)
    app = await memory_app(h)
    before = await stated_memory(h, placed.member, f"I work from {h.word()} on Fridays", 1)

    asked = await c.asked(placed.member, strong=False)
    with c.as_route():
        shown = await my_preferences(c.request(), asked)
        if shown.learning.opted_out or not shown.learning.cost.strip():
            raise CheckFailedError("a person was not told what switching learning off costs")
        off = await set_learning(c.request("POST"), LearningAsked(opted_out=True), asked)
    if (
        not off.learning.opted_out
        or not (await StoredPreferences(h.sessions).of(placed.member)).learning_opted_out
    ):
        raise CheckFailedError("switching learning off was not kept")

    held = len(await memories_of(h, placed.member))
    await ask(h, app, placed.member, f"Remember that I like {h.word()} summaries.", 2)
    if len(await memories_of(h, placed.member)) != held:
        raise CheckFailedError("a memory was formed from a person who switched learning off")
    if not any(one.memory_id == before for one in await memories_of(h, placed.member)):
        raise CheckFailedError("switching learning off removed what was learnt before")
    await stated_memory(h, placed.colleague, f"I sit by the {h.word()}", 3)

    with c.as_route():
        on = await set_learning(c.request("POST"), LearningAsked(opted_out=False), asked)
    if on.learning.opted_out:
        raise CheckFailedError("switching learning back on was not kept")
    await stated_memory(h, placed.member, f"I like {h.word()} summaries", 4)


# ------------------------------------------------------------ 2. reach (M40.5.2.1 to 3)
@check(
    leaves=("M40.5.2.1", "M40.5.2.2"),
    sentence=(
        "A person bound on Slack is shown it as a channel they can be reached on and may make it "
        "primary and choose what it tells them; a channel they are not bound on, a kind that is "
        "not a choice and an approval route that is neither the console nor a Lark card are each "
        "refused in words with nothing kept; and a colleague sees none of it."
    ),
)
async def a_person_chooses_where_they_are_reached_and_it_is_kept_whole(h: Harness) -> None:
    from brain.member.preferences import parse
    from brain.member_preference_routes import (
        ChannelNotices,
        ReachAsked,
        my_preferences,
        set_reach,
    )
    from brain.ops.acceptance_checks_learning_digest import _on_slack
    from brain.ops.member_preference_store import StoredPreferences

    placed = await people(h)
    c = await console(h)
    await _on_slack(h, {placed.member: f"UACC{h.run.upper()}P"})
    asked = await c.asked(placed.member, strong=False)
    colleague = await c.asked(placed.colleague, strong=False)

    async def reach(body: ReachAsked) -> Any:
        with c.as_route():
            return await set_reach(c.request("POST"), body, asked)

    with c.as_route():
        shown = await my_preferences(c.request(), asked)
        theirs = await my_preferences(c.request(), colleague)
    if [one.channel for one in shown.channels] != ["slack"] or theirs.channels:
        raise CheckFailedError("a person was not shown exactly the channels they are connected on")

    refusals = [
        ReachAsked(primary="lark"),
        ReachAsked(notices=[ChannelNotices(channel="lark", notify=["digest"])]),
        ReachAsked(notices=[ChannelNotices(channel="slack", notify=["approval"])]),
        ReachAsked(approval_route="slack"),
        ReachAsked(approval_route="lark"),
    ]
    for body in refusals:
        told = await reach(body)
        if getattr(told, "status_code", 200) != 422:
            raise CheckFailedError("a setting that cannot work was kept")
    if await StoredPreferences(h.sessions).of(placed.member) != parse(placed.member, {}):
        raise CheckFailedError("a refused setting was kept in part")

    kept = await reach(
        ReachAsked(
            primary="slack",
            notices=[ChannelNotices(channel="slack", notify=["automation"])],
            approval_route="console",
        )
    )
    row = kept.channels[0]
    if not (kept.primary == "slack" and row.primary and row.notify == ["automation"]):
        raise CheckFailedError("a primary channel and a notice choice were not kept")
    if kept.approval_route != "console":
        raise CheckFailedError("an approval kept on the console was not kept")
    with c.as_route():
        theirs = await my_preferences(c.request(), colleague)
    if theirs.primary is not None or theirs.approval_route is not None:
        raise CheckFailedError("one person's setting was shown to another")


# ------------------------------------------------ 3. held digests (M40.5.2.2, M40.5.2.4)
@check(
    leaves=("M40.5.2.4",),
    sentence=(
        "A person's weekly digest is held inside their quiet hours and sent once they are out of "
        "them, is held by a channel they made a statement about that leaves digests out and sent "
        "when it lists them, and is sent as before to a person who said nothing; the pass that "
        "held one is not counted finished."
    ),
)
async def a_digest_is_held_by_quiet_hours_and_by_a_channel_that_omits_it(
    h: Harness,
) -> None:
    import json
    from types import SimpleNamespace

    from brain.channels.slack import BOT_TOKEN, SIGNING_SECRET
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.learning_told import CoveredWeek, send_learning_digests, undo_page_here
    from brain.locale import time_zone
    from brain.mailbox_read import request_for
    from brain.member.preferences import PreferenceKey, clock
    from brain.memory.digest import DIGEST_PERIOD
    from brain.ops.acceptance_checks import _HeldLedger, _Secret
    from brain.ops.acceptance_checks_learning_digest import (
        THE_LEARNING_DIGEST_IS_SWITCHED_OFF,
        _on_slack,
        _sent,
    )
    from brain.ops.acceptance_escalation import _Kept
    from brain.ops.member_preference_store import StoredPreferences

    placed = await people(h)
    member_on = f"UACC{h.run.upper()}M"
    await _on_slack(h, {placed.member: member_on})
    await stated_memory(h, placed.member, f"I work from {h.word()} on Fridays", 1)

    app = await memory_app(h)
    kept = _Kept()
    app.state.channel_transport = kept
    app.state.operation_ledger = _HeldLedger()
    app.state.channel_secrets = _Secret(
        json.dumps({SIGNING_SECRET: f"acceptance-{h.run}", BOT_TOKEN: f"xoxb-acceptance-{h.run}"})
    )
    readers = StoredEntitlements(h.sessions)
    app.state.gate = SimpleNamespace(store=readers)
    at = datetime.now(UTC)
    week = CoveredWeek(covers_from=at - DIGEST_PERIOD, covers_to=at, key=f"acceptance-{h.run}")
    zone = time_zone()
    store = StoredPreferences(h.sessions)

    async def run() -> Any:
        return await send_learning_digests(
            request_for(app),
            h.sessions,
            now=at,
            zone=zone,
            page=undo_page_here(),
            readers=readers,
            week=week,
            only=(placed.member,),
        )

    inside = at.astimezone(zone)
    around = {
        "start": clock((inside - timedelta(hours=1)).time()),
        "end": clock((inside + timedelta(hours=1)).time()),
    }
    await store.set(placed.member, PreferenceKey.QUIET_HOURS, around, now=at)
    held = await run()
    if held.switched_off:
        raise CheckNotRunError(THE_LEARNING_DIGEST_IS_SWITCHED_OFF)
    if _sent(kept, 0) or held.held != 1:
        raise CheckFailedError("a digest was sent inside the person's quiet hours")

    await store.clear(placed.member, PreferenceKey.QUIET_HOURS)
    await store.set(placed.member, PreferenceKey.CHANNEL_NOTICES, {"slack": ["automation"]}, now=at)
    left_out = await run()
    if _sent(kept, 0) or left_out.held != 1:
        raise CheckFailedError("a digest was sent on a channel its person left digests out of")

    await store.set(placed.member, PreferenceKey.CHANNEL_NOTICES, {"slack": ["digest"]}, now=at)
    listed = await run()
    sent = _sent(kept, 0)
    if len(sent) != 1 or sent[0][0] != member_on or listed.held:
        raise CheckFailedError("a digest was not sent once nothing held it")

    again = await run()
    if len(_sent(kept, 0)) != 1 or again.sent:
        raise CheckFailedError("a digest held and then sent was sent twice")


# ---------------------------------------------------------- 4. approvals (M40.5.2.3)
@check(
    leaves=("M40.5.2.3",),
    sentence=(
        "An approval raised for an approver who chose the console is sent no Lark card and is on "
        "their Approvals screen; once they choose nothing the card is sent to their own chat."
    ),
)
async def an_approver_who_chose_the_console_is_sent_no_card(h: Harness) -> None:
    from brain.approval_cards import send_raised
    from brain.gate.admission import admit_card_press
    from brain.gate.context import Channel
    from brain.gate.suspension_store import StoredSuspensions
    from brain.member.preferences import PreferenceKey
    from brain.ops.acceptance_checks_cards import desk
    from brain.ops.member_preference_store import StoredPreferences

    made = await desk(h)
    store = StoredPreferences(h.sessions)
    for writing in (made.approver, made.bystander):
        await made.says(writing, "approvals")
    await store.set(made.approver, PreferenceKey.APPROVAL_ROUTE, {"channel": "console"}, now=h.now)

    card, _ = await made.promotion()
    reach = admit_card_press(await h.reach(made.approver), Channel.LARK, switched_on=True)
    raised = await StoredSuspensions(h.sessions).reading_as(reach, h.now).suspension(card)
    if raised is None:
        raise CheckFailedError("the approver could not read the promotion that was raised")
    before = len(made.lark.sent)
    await send_raised(made.chat.request(), raised)
    if len(made.lark.sent) != before:
        raise CheckFailedError("a card was sent to an approver who chose the console")

    await store.clear(made.approver, PreferenceKey.APPROVAL_ROUTE)
    await send_raised(made.chat.request(), raised)
    posted = (
        made.lark.posted()[-(len(made.lark.sent) - before) :] if made.lark.sent[before:] else []
    )
    if [where for _, where, _, _ in posted] != [made.ids[made.approver]]:
        raise CheckFailedError("a card was not sent to an approver who chose nothing")
