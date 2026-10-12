"""Every shipped channel proved on an install, rolled up from the checks that prove each clause.

M10.7.3 says every shipped channel is proved on an install, and lists what that means: on each chat
channel, by email, through the REST API and in the web application a bound person asks and gets a
permission-correct answer through that channel's own credential with progress streamed, a sender
bound to nobody learns nothing about the company, a message whose signature does not verify is
refused unread, a platform retry produces one answer, a waiting approval notice reaches the person
it names, the conversation continues on a second channel, and an agent not enabled on a channel
refuses there. Every clause has a check, written for the narrower leaf it was built under; none of
them names the composite, and a composite check that asked the same questions again would be the
same check twice in one run (`brain.ops.acceptance_roll_up` argues it).

**This holds the one roll-up and it asks nothing of the install**: it reads what the clause checks
came to earlier in this run, so it sits after every one of them. A channel whose check was not run
(an install with the channel's switch off, a relay not saved) leaves the roll-up not run, and one
that failed fails it, so the leaf closes only when every shipped channel has been shown.

**What each clause is shown by is a check over a channel set up with secrets the check made.** Every
one of those leaves is held by `docs/proof-sweep-holds.json` until the install connects the owner's
own account (needs-rupash 126), and so is this one: a roll-up over checks that each passed against a
stand-in is not more than they are.

Task ids: M10.7.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 1290

#: The clauses of M10.7.3, each with the leaves whose checks show it.
CLAUSES: Final = {
    "Lark answers a bound person": ("M10.2.2", "M10.3.1"),
    "Slack answers a bound person": ("M10.5.1",),
    "Teams answers a bound person": ("M10.5.2",),
    "WhatsApp answers a bound person": ("M10.5.3",),
    "Telegram answers a bound person": ("M10.5.4",),
    "email answers a bound person": ("M10.5.6",),
    "the REST API answers a keyed caller": ("M10.5.7",),
    "the web application answers at the narrower reach": ("M13.7.5",),
    "progress is streamed": ("M6.3.1",),
    "a sender bound to nobody learns nothing": ("M10.2.1", "M10.3.4"),
    "a message whose signature does not verify is refused unread": ("M10.2.1", "M10.6.2"),
    "a platform retry produces one answer": ("M10.2.1",),
    "a waiting approval notice reaches the person it names": ("M10.2.7", "M10.7.1"),
    "the conversation continues on a second channel": ("M9.1.2",),
    "an agent not enabled on a channel refuses there": ("M13.7.4",),
}


@check(
    leaves=("M10.7.3",),
    sentence=(
        "Every clause of the channels' install proof was shown in this run: each chat channel, "
        "email, the REST API and the web answering a bound person at their reach with progress "
        "streamed, a sender bound to nobody told nothing, a bad signature refused unread, a retry "
        "answered once, an approval notice delivered, a conversation continued on a second "
        "channel and an agent refusing where it is not enabled."
    ),
)
async def every_shipped_channel_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, CLAUSES, own="every_shipped_channel_is_shown_clause_by_clause_in_this_run"
    )
