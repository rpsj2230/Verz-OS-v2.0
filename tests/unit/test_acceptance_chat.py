"""The Lark chat acceptance checks: the events they post, and the three checks run on PostgreSQL.

The pure half holds what the checks may say and what they post: every reason is a literal sentence,
and an event the check seals is one the install's own wire opens, and refuses under another key.
The database half runs the three checks as the worker runs them, against PostgreSQL at head,
twice: with the events route reading no chat binding, as it does until CH2, and with it reading
`auth.principal_identity`'s chat rows as CH2 wires it. Either way every table a check writes to
holds afterwards what it held before.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M10.2.2, M10.2.5, M10.2.6, M10.4.1, M10.4.2, M10.4.3, M10.4.4, M38.2.2.3, M2.3.1
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import CHECK_MODULES, NOT_RUN, PASSED, Check, registered
from brain.ops.acceptance_checks_chat import (
    BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED,
    lark_message,
    open_id,
    sealed,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "brain" / "ops" / "acceptance_checks_chat.py"

MENTIONS = "a_lark_group_message_is_answered_only_when_it_names_the_bot"
DIRECT = "a_person_bound_in_lark_is_given_their_web_answer_directly"
ROOMS = "a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone"

#: What the database half hands the run: an issuer the gate is built for, and an address of the
#: install's own for the link to Ask.
INSTALL = {
    "INSTALL_OIDC_ISSUER": "https://id.example.invalid/realms/brain",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.invalid/callback",
}

#: Every table a chat check writes to, and nothing may be left in afterwards.
WRITTEN_BY_CHAT_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "auth.principal_identity",
    "gate.capability_grant",
    "obs.audit_entry",
    "ops.channel",
    "ops.channel_delivery",
    "gate.channel_event",
    "know.classified_table",
    "know.classified_row",
)


def chat_checks() -> list[Check]:
    return [one for one in registered() if one.name in (MENTIONS, DIRECT, ROOMS)]


# ------------------------------------------------------------------------ the pure half
def test_the_three_chat_checks_are_in_the_suite_the_worker_runs() -> None:
    """Named in `CHECK_MODULES`, which is what `registered` imports and the worker runs, rather
    than registered by this test importing the module. Delete this and the module can be dropped
    from the list with the Install page simply showing three fewer rows."""
    assert "brain.ops.acceptance_checks_chat" in CHECK_MODULES
    names = [one.name for one in registered(CHECK_MODULES)]
    assert [one for one in names if one in (MENTIONS, DIRECT, ROOMS)] == [MENTIONS, DIRECT, ROOMS]


def test_every_reason_a_chat_check_raises_is_a_literal_sentence() -> None:
    """`A_RESULT_NAMES_NO_DATA`, over this module: a reason is served on a public page, so it is a
    string literal or the one named constant. Delete this and a reason can quote an answer."""
    raised = 0
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        raised += 1
        [argument] = node.args
        literal = isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        named = isinstance(argument, ast.Name) and argument.id == (
            "BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED"
        )
        assert literal or named, ast.unparse(node)
    assert raised > 20


def test_a_web_citation_read_a_minute_apart_is_the_same_source_a_chat_lists() -> None:
    """The web streams a citation as fields and a chat lists it as a sentence with its read time,
    and the two asks of one question read their source at different instants. The check reads the
    web's frames into the chat's sentence and sets the read time aside on both, and nothing else:
    another label, freshness or badge still differs. Delete this and the direct-reply check fails
    on every install once citations carry fields, or passes a chat that cites another row."""
    from brain.gate.streaming import Event, encode
    from brain.ops.acceptance_checks_chat import heard, undated

    def cited(read_at: str, *, label: str = "prices 0: band from tables", badge: str = "") -> str:
        fields = {
            "label": label,
            "freshness_text": "current",
            "kind": "record",
            "read_at": read_at,
            "badge": badge,
        }
        return encode(Event.CITATION, json.dumps(fields))

    web = heard([encode(Event.TEXT, "Band B"), cited("2999-01-01T10:00:59+00:00")])
    chat = "Band B\n\nSources:\n- prices 0: band from tables (current, read 01 Jan 2999 10:01 UTC)"
    assert web.is_what(undated(chat))
    for other in (
        heard([encode(Event.TEXT, "Band B"), cited("2999-01-01T10:00:59+00:00", label="x")]),
        heard([encode(Event.TEXT, "Band B"), cited("2999-01-01T10:00:59+00:00", badge="y")]),
    ):
        assert not other.is_what(undated(chat))
    document = "- a handbook (current, updated 01 Jan 2999)"
    assert undated(document) == "- a handbook (current)"


def test_an_event_the_check_seals_is_opened_by_the_wire_and_refused_under_another_key() -> None:
    """The check's events are sealed from Lark's algorithm, not from the wire's code, so this holds
    the two to each other: the install's `verify_event` opens one to the event it was, and an event
    sealed under another key is refused. Delete this and the checks can post events the install
    refuses, and report a working channel as broken, or accept ones Lark could never send."""
    from brain.channels.lark import (
        NONCE_HEADER,
        SIGNATURE_HEADER,
        TIMESTAMP_HEADER,
        LarkSecret,
        verify_event,
    )
    from brain.channels.webhook import WebhookRefusedError

    secret = LarkSecret(app_secret="a" * 16, encrypt_key="k" * 16, verification_token="t" * 16)
    event = lark_message(
        app_id="cli_0",
        token=secret.verification_token,
        sender=open_id(),
        text="hi",
        chat="oc_0",
        group=False,
    )

    def opened(key: str) -> bytes:
        raw, headers = sealed(event, key)
        return verify_event(
            secret=secret,
            body=raw,
            timestamp=headers[TIMESTAMP_HEADER],
            nonce=headers[NONCE_HEADER],
            signature=headers[SIGNATURE_HEADER],
            now=datetime.now(UTC),
        )

    assert json.loads(opened(secret.encrypt_key)) == event
    with pytest.raises(WebhookRefusedError):
        opened("z" * 16)


# ------------------------------------------------------------------------ a real run
class TableBindings:
    """CH2's reader as its route wires it: `auth.principal_identity`'s live chat rows by digest."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def binding_for(self, channel: Any, digest: str) -> Any:
        from sqlalchemy import select

        from brain.gate.ingress import Binding
        from brain.tables.identity import PrincipalIdentityRow

        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(PrincipalIdentityRow)
                    .where(PrincipalIdentityRow.channel == channel.value)
                    .where(PrincipalIdentityRow.identity_hash == digest)
                    .where(PrincipalIdentityRow.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return Binding(
            channel=channel,
            identity_hash=row.identity_hash,
            principal_id=row.principal_id,
            bound_at=row.bound_at,
        )


def counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_CHAT_CHECKS
    }


def run_checks(url: str, checks: Sequence[Check]) -> tuple[dict[str, tuple[str, str]], str]:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    stream = io.StringIO()

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await acceptance_run.run_suite(engine, checks, settings=settings, stream=stream)
        finally:
            await engine.dispose()

    results = asyncio.run(run())
    return {one.name: (one.outcome, one.reason) for one in results}, stream.getvalue()


@pytest.mark.needs_db
def test_on_a_real_database_the_chat_checks_pass_where_bindings_are_read_and_wait_where_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The three checks as the worker runs them, on PostgreSQL at head.** With the route reading
    no chat binding, as it does until CH2, the mention check passes and the two needing a bound
    person are not run, with the sentence saying why; with the route reading chat bindings as CH2
    wires it, all three pass. Both halves name their route, so the test says the same before and
    after CH2 lands. After both runs every table a check wrote to holds what it held before.
    Delete this and a chat check that commits, or cannot pass on a real schema, reaches the
    owner's server first."""
    import brain.channel_routes
    from brain.channels.inbound import NoBindingsYet
    from brain.routing_routes import sessions_of

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    with at_head("brain_acceptance_chat") as url:
        before = counts(url)
        monkeypatch.setattr(brain.channel_routes, "bindings_of", lambda request: NoBindingsYet())
        waiting, waited_log = run_checks(url, chat_checks())
        monkeypatch.setattr(
            brain.channel_routes, "bindings_of", lambda request: TableBindings(sessions_of(request))
        )
        bound, bound_log = run_checks(url, chat_checks())
        after = counts(url)

    assert waiting == {
        MENTIONS: (PASSED, ""),
        DIRECT: (NOT_RUN, BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED),
        ROOMS: (NOT_RUN, BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED),
    }, waited_log
    assert bound == {MENTIONS: (PASSED, ""), DIRECT: (PASSED, ""), ROOMS: (PASSED, "")}, bound_log
    assert after == before
