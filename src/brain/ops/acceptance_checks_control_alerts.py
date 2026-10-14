"""The install acceptance check for the alert that a safety mechanism has not run: whoever holds the
operations alert is told once in their own chat, and when nobody who holds it has a chat, the
install's alert address is sent the same sentence.

The check runs `brain.control_not_run_told.tell_overdue_controls`, the function the web process's
loop runs, over the check's own people and one control of the product's own registry that the check
says last succeeded long ago, through `brain.tell_later.tell` on a Slack channel the check sets up
whose transport keeps each request and sends nothing, and through the mail door onto a relay the
check names, which keeps each message and sends nothing. The operation ledger is in memory and
every write is in the check's rolled-back transaction, so **nothing reaches a real person and
nothing here depends on what the install's worker has or has not run**. See
`THE_ALERT_REACHES_A_CHANNEL_AND_A_RELAY_THE_CHECK_HOLDS`.

**What the check proves.** A person of the check's own who holds the operations alert and may open
Incidents is sent one message in their own Slack conversation naming the mechanism and how long,
and not what it guards; one who holds the alert and cannot open Incidents, and one who holds
nothing, are sent nothing; a second run sends nothing more and the install's address is not written
to. When none of the people has a chat, the address the check names is sent the same sentence once
through the relay, and a second run sends no second.

**What it does not prove**, stated: that the loop the application starts runs on the install, which
is logged on every pass; that Slack and the install's real relay accept the message, which the
Connect Slack test and the Notifications test message prove; and the seven-day recency, which a
unit test holds because the check cannot age a binding's last use inside its transaction. Not run
when an administrator has not switched `control_not_run_alerts` on, which is every install until
somebody does: the check says so in those words and does not turn it on.

Task ids: M17.7.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_learning_digest import _on_slack, _sent
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 283

#: Why the alert is sent to a channel and a relay the check holds.
THE_ALERT_REACHES_A_CHANNEL_AND_A_RELAY_THE_CHECK_HOLDS: Final = (
    "The alert is sent through the product's own senders on a Slack channel the check sets up and "
    "a relay it names, each of which keeps what it was asked to send and sends nothing, with the "
    "operation ledger held in memory, so the check reads exactly what each person and the address "
    "would have been sent and nobody is sent anything."
)

#: The reserved top-level domain, which no mail system delivers to.
_DOMAIN: Final = "acceptance.invalid"

# ------------------------------------------------------------------------ the verdicts
THE_ALERTS_ARE_SWITCHED_OFF: Final = (
    "the control_not_run_alerts feature, or the notice that a mechanism has not run, is switched "
    "off on this install, so nobody is told of a mechanism that has not run and that telling was "
    "not checked"
)
NO_CONTROL_TO_ASK_ABOUT: Final = "the registry holds no control a scheduler starts to ask about"
NOT_SENT_ONCE: Final = (
    "the person who holds the operations alert and opens Incidents was not sent one message in "
    "their own chat"
)
NAMED_NOTHING: Final = "the alert did not name the mechanism that had not run"
NAMED_WHAT_IT_GUARDS: Final = "the alert said what the mechanism guards, which is for Incidents"
TOLD_SOMEBODY_WHO_COULD_NOT_ACT: Final = (
    "somebody who holds the alert and cannot open Incidents, or who holds neither, was sent it"
)
EMAILED_WHILE_SOMEBODY_WAS_IN_CHAT: Final = (
    "the install's address was sent the alert although a holder was told in their own chat"
)
SENT_TWICE: Final = "a second run over the same silence sent the alert again"
NOT_EMAILED_WITH_NOBODY_IN_CHAT: Final = (
    "with nobody holding the alert in a chat, the install's address was not sent it once"
)
THE_EMAIL_SAID_SOMETHING_ELSE: Final = (
    "the email did not say what the chat says, or named the mechanism in its subject"
)


@check(
    leaves=("M17.7.2",),
    sentence=(
        "A mechanism that has not run in its window is told once, in their own Slack chat, to a "
        "person who holds the operations alert and may open Incidents, naming it and how long and "
        "not what it guards, and to nobody else; with nobody in a chat, the install's alert "
        "address is sent the same sentence once."
    ),
)
async def a_mechanism_that_has_not_run_is_told_to_whoever_holds_the_alert(h: Harness) -> None:
    import json
    from types import SimpleNamespace

    from brain.channels.slack import BOT_TOKEN, SIGNING_SECRET
    from brain.console.screens import screen
    from brain.control_not_run_told import INCIDENTS_SCREEN, tell_overdue_controls
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.mailbox_read import request_for
    from brain.ops.acceptance_checks import _HeldLedger, _Secret
    from brain.ops.acceptance_checks_memory import memory_app
    from brain.ops.acceptance_escalation import _Kept
    from brain.ops.acceptance_workspace import _everywhere, _planes
    from brain.ops.alerting import OPERATIONS_ALERT
    from brain.ops.controls import Invocation
    from brain.ops.idempotency import CallOutcome
    from brain.ops.mail import MailAnswer, MailSettings, Message, Security
    from brain.ops.schedule import schedulable

    chosen = next((one for one in schedulable() if one.invoked_by is not Invocation.NOTHING), None)
    if chosen is None:
        raise CheckNotRunError(NO_CONTROL_TO_ASK_ABOUT)
    last_success = {chosen.name: h.now - chosen.alert_after * 3}

    await h.found_departments()
    opens = (screen(INCIDENTS_SCREEN).read.requires.value, *_planes())
    holder, blind, nobody = (h.principal(A, one) for one in ("holder", "blind", "nobody"))
    await h.person(holder, department=A, grants=_everywhere(OPERATIONS_ALERT.value, *opens))
    await h.person(blind, department=A, grants=_everywhere(OPERATIONS_ALERT.value))
    await h.person(nobody, department=B)
    on = {
        holder: f"UACC{h.run.upper()}H",
        blind: f"UACC{h.run.upper()}B",
        nobody: f"UACC{h.run.upper()}N",
    }
    await _on_slack(h, on)

    class Relay:
        def __init__(self) -> None:
            self.sent: list[Message] = []

        def send(self, message: Message) -> MailAnswer:
            self.sent.append(message)
            return MailAnswer(CallOutcome.OK)

    app = await memory_app(h)
    kept, relay = _Kept(), Relay()
    app.state.channel_transport = kept
    app.state.operation_ledger = _HeldLedger()
    app.state.channel_secrets = _Secret(
        json.dumps({SIGNING_SECRET: f"acceptance-{h.run}", BOT_TOKEN: f"xoxb-acceptance-{h.run}"})
    )
    app.state.gate = SimpleNamespace(store=StoredEntitlements(h.sessions))
    app.state.mail_settings = MailSettings(
        host=f"relay.{_DOMAIN}",
        port=587,
        security=Security.STARTTLS,
        sender=f"acceptance-{h.run}@{_DOMAIN}",
        username="",
    )
    app.state.mail_transport = lambda settings, password: relay
    address = f"acceptance-{h.run}-alerts@{_DOMAIN}"

    async def run(*people: str) -> Any:
        return await tell_overdue_controls(
            request_for(app),
            h.sessions,
            now=h.now,
            since=h.now - timedelta(days=400),
            last_success=last_success,
            people=people,
            email=address,
            controls=[chosen],
        )

    told = await run(holder, blind, nobody)
    if told.switched_off:
        raise CheckNotRunError(THE_ALERTS_ARE_SWITCHED_OFF)
    first = _sent(kept, 0)
    if any(channel in {on[blind], on[nobody]} for channel, _ in first):
        raise CheckFailedError(TOLD_SOMEBODY_WHO_COULD_NOT_ACT)
    mine = [said for channel, said in first if channel == on[holder]]
    if len(mine) != 1 or len(first) != 1:
        raise CheckFailedError(NOT_SENT_ONCE)
    [said] = mine
    if chosen.name not in said:
        raise CheckFailedError(NAMED_NOTHING)
    if chosen.guards in said or chosen.lost_silently in said:
        raise CheckFailedError(NAMED_WHAT_IT_GUARDS)
    if relay.sent:
        raise CheckFailedError(EMAILED_WHILE_SOMEBODY_WAS_IN_CHAT)

    await run(holder, blind, nobody)
    if _sent(kept, len(first)) or relay.sent:
        raise CheckFailedError(SENT_TWICE)

    # Nobody with a chat: the install's address is sent the same sentence, once.
    await run()
    if len(relay.sent) != 1 or relay.sent[0].to != address:
        raise CheckFailedError(NOT_EMAILED_WITH_NOBODY_IN_CHAT)
    if relay.sent[0].body != said or chosen.name in relay.sent[0].subject:
        raise CheckFailedError(THE_EMAIL_SAID_SOMETHING_ELSE)
    await run()
    if len(relay.sent) != 1:
        raise CheckFailedError(SENT_TWICE)
