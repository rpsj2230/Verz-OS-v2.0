"""The install acceptance check for Slack as a source: a person's own channels, read for them.

M11.7.5 asks that a question on Ask can find what was said in Slack, and the owner's guards
decide how: membership is asked of Slack for every question, an asker is matched to their Slack
account by the digest of their verified work email and never by a name, and an asker with no
account, or not in the channel, is told what an asker is told when Slack holds nothing on the
subject. The check proves that on the install's own database and code.

A workspace made up for the run is connected through the store the Connectors screen's routes
call and read by the worker's own `brain.ops.connector_sync_run.attempt`, so its channels and its
members' digests are in the index. People are bound to email addresses the way an email binding
is kept, as the digest `brain.gate.ingress.identity_hash` makes. Each then asks through
`brain.ops.slack_messages_live.SlackPassages`, the passage search the answer lane's model step reads
through behind `Alongside`.

**No socket is opened.** Every Slack call is answered by `_RecordedSlack`, in Slack's documented
envelope, and each call is recorded so the check can say which channel was never read for whom
(`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`). Nothing the check
writes outlives its transaction.

What it does not prove: that the model writes an answer from a passage, which is the model lane's
own check, and that the owner's Slack answers this install, which needs an app installed in his
workspace and connected on the Connectors screen.

**The check steps aside where the install has Slack connected already**, for
`brain.ops.acceptance_checks_sources.A_SOURCE_IS_CONNECTED_HERE_ALREADY`'s reason.

Task ids: M11.7.5
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _Keys, _Resolver, _search
from brain.ops.acceptance_checks_sources import _connect_and_read, _connection

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.core.envelope import TypedResult
    from brain.knowledge.document_tools import KnowledgePassage
    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 360

A, _ = RESERVED_DEPARTMENTS

#: What the check says where the install has Slack connected already.
SLACK_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Slack connected already, so the check does not connect it again and does "
    "not read it"
)

#: The capability Slack's passages are told under, restated from `brain.ops.slack_messages_live`.
READ_MESSAGE: Final = "read:slack_message"


def _slack_id(kind: str) -> str:
    return f"{kind}{secrets.token_hex(5).upper()}"


def _body(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


@dataclass
class _RecordedSlack:
    """`SourceCaller` answering one workspace's lists, memberships and histories. No socket.

    `members` maps a member id to their address and the channels they are in; `histories` maps a
    channel to its messages. A call without the bearer key is answered as Slack answers it, with
    ok false, so a reader that sent no key reads nothing.
    """

    channels: Mapping[str, tuple[str, bool]]
    members: Mapping[str, tuple[str, tuple[str, ...]]]
    histories: Mapping[str, tuple[tuple[str, str], ...]]
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)
        if not headers.get("Authorization", "").startswith("Bearer "):
            return SourceAnswer(status=200, headers={}, body=_body({"ok": False}))
        split = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(split.query).items()}
        method = split.path.rsplit("/", 1)[-1]
        end = {"next_cursor": ""}
        if method == "conversations.list":
            listed = [
                {"id": one, "name": name, "is_private": private, "is_member": True}
                for one, (name, private) in self.channels.items()
            ]
            found: dict[str, Any] = {"channels": listed}
        elif method == "users.list":
            found = {
                "members": [
                    {
                        "id": one,
                        "deleted": False,
                        "is_bot": False,
                        "is_email_confirmed": True,
                        "profile": {"email": email},
                    }
                    for one, (email, _) in self.members.items()
                ]
            }
        elif method == "users.conversations" and query.get("user") in self.members:
            _, theirs = self.members[query["user"]]
            found = {"channels": [{"id": one} for one in theirs]}
        elif method == "conversations.history" and query.get("channel") in self.histories:
            found = {
                "messages": [
                    {"type": "message", "ts": ts, "text": text}
                    for ts, text in self.histories[query["channel"]]
                ]
            }
        else:
            return SourceAnswer(status=200, headers={}, body=_body({"ok": False}))
        reply = {"ok": True, **found, "response_metadata": end}
        return SourceAnswer(status=200, headers={}, body=_body(reply))

    def read_history_of(self, channel: str, since: int = 0) -> bool:
        return any(
            "conversations.history" in one and f"channel={channel}" in one
            for one in self.asked[since:]
        )


@check(
    leaves=("M11.7.5",),
    sentence=(
        "A Slack workspace made up for the check is connected and read by the worker into an "
        "index of channel names and email digests, and asked on Ask: a person is read the "
        "channels Slack says they are in, a private channel they are not in is never read however "
        "well it matches, a person with no Slack account or no grant is told what an absent "
        "subject is told, and no message or address is in a table."
    ),
)
async def a_slack_message_is_read_only_for_a_member_of_its_channel(h: Harness) -> None:
    from brain.connectors import slack_messages as slack
    from brain.connectors.minimal_index import fresh_canary
    from brain.gate.context import Channel
    from brain.gate.ingress import identity_hash
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connector_store import live
    from brain.ops.slack_messages_live import SlackPassages
    from brain.tables.identity import PrincipalIdentityRow

    if (await h.execute(live(slack.CONNECTOR_NAME))).scalar_one_or_none() is not None:
        raise CheckNotRunError(SLACK_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    word = h.word()
    public, private = _slack_id("C"), _slack_id("G")
    inside_id, outside_id, granted_only_id = _slack_id("U"), _slack_id("U"), _slack_id("U")
    address = {one: f"{h.word().lower()}@acceptance.invalid" for one in ("in", "out", "no", "ng")}
    open_text, closed_text = fresh_canary("ACCEPTANCE"), fresh_canary("ACCEPTANCE")
    workspace = _RecordedSlack(
        channels={public: ("general", False), private: ("leadership", True)},
        members={
            inside_id: (address["in"], (public, private)),
            outside_id: (address["out"], (public,)),
            granted_only_id: (address["ng"], (public, private)),
        },
        histories={
            public: (("1600000000.000100", f"{open_text} {word}"),),
            # Every word of the question, so it is the best match wherever it is read.
            private: (("1600000200.000100", f"{closed_text} {word} renewal price"),),
        },
    )
    connection = _connection(
        h, slack.CONNECTOR_NAME, {"workspace": _slack_id("T"), "department": A}
    )
    await _connect_and_read(h, connection, workspace, at=h.now)

    # The index holds the members as the digests an email binding keeps, and no address.
    if await _search(h, address["in"]):
        raise CheckFailedError("a Slack member's address was kept in a table")

    inside, outside, stranger, ungranted = (
        h.principal(A, "inside"),
        h.principal(A, "outside"),
        h.principal(A, "stranger"),
        h.principal(A, "ungranted"),
    )
    granted = ((READ_MESSAGE, Scope.department(A)),)
    for person, email, grants in (
        (inside, address["in"], granted),
        (outside, address["out"], granted),
        (stranger, address["no"], granted),
        (ungranted, address["ng"], ()),
    ):
        await h.person(person, department=A, grants=grants)
        await h.execute(
            *h.attributed(),
            insert(PrincipalIdentityRow).values(
                channel=Channel.EMAIL.value,
                identity_hash=identity_hash(Channel.EMAIL, email),
                principal_id=person,
                bound_at=h.now,
            ),
        )

    async def connected() -> Any:
        return connection

    search = SlackPassages(
        connected,
        sessions=h.sessions,
        keys=_Keys(),
        caller=workspace,
        resolver=_Resolver(),
        clock=lambda: h.now,
    )
    question = f"What was said about the {word} renewal price?"

    async def ask(principal_id: str, asked: str = question) -> TypedResult[KnowledgePassage]:
        reach = await _console(h, principal_id, second_factor=False)
        return await search.passages(asked, entitlement=reach, now=h.now)

    # A member of both channels is read both, the private message first as the best match, and
    # each passage is theirs alone.
    told = await ask(inside)
    texts = [one.document for one in told.records]
    if len(texts) != 2 or closed_text not in texts[0] or open_text not in texts[1]:
        raise CheckFailedError("a member was not read the channels Slack says they are in")
    if any(one.owner_id != inside or one.visibility != "personal" for one in told.records):
        raise CheckFailedError("a Slack passage was not personal to the person it was read for")

    # A member of the public channel only: the private one is never read for them.
    since = len(workspace.asked)
    theirs = " ".join(one.document for one in (await ask(outside)).records)
    if closed_text in theirs or workspace.read_history_of(private, since):
        raise CheckFailedError("a private channel's message was read for somebody not in it")
    if open_text not in theirs:
        raise CheckFailedError("a channel a person is in was not read for them")

    # No Slack account, and no grant: nothing is read, no call is made, and what they are told
    # is what a question Slack holds nothing on tells a member.
    nothing = await ask(inside, f"What was said about {h.word()}?")
    for person in (stranger, ungranted):
        since = len(workspace.asked)
        answered = await ask(person)
        if answered.records != nothing.records or answered.records:
            raise CheckFailedError("Slack was read for a person with no account in it or no grant")
        if len(workspace.asked) != since:
            raise CheckFailedError("Slack was asked about a person it could tell nothing to")

    for canary in (open_text, closed_text):
        if await _search(h, canary):
            raise CheckFailedError("a Slack message read live was found in a table")
