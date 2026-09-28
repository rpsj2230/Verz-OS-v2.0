"""The Credentials screen's reads of the database and of the vault's own view of its policy.

The first half needs no server: the vault client's parse of `sys/capabilities-self` in the three
shapes OpenBao answers with (the path's own key, `capabilities` for a single path, and the newer
`data` wrapping, from the vault's API documentation for that endpoint), and its refusal of anything
else. The second half builds a database to the head and proves `StoredCredentialHistory` reads a
slot's ledger entries through the trigger a real write fires, and each kind's last use from the
table that records it, as the application role. **It skips when there is no server.**

Task ids: M27.11.10, M27.15.50
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from brain.ops.credential_catalogue import LIVE_READ_MINT_PATH, LiveReads, live_reads_of
from brain.ops.credential_write_store import StoredCredentialHistory, StoredCredentialWrites
from brain.ops.openbao import OpenBaoVault
from brain.ops.secrets import SecretsUnavailableError
from brain.session import make_session_factory
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine

#: Far from any plausible wall clock, for CLAUDE.md's reason.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


class Answering(OpenBaoVault):
    """The real client with its network call replaced by one recorded answer."""

    def __init__(self, answer: dict[str, Any]) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.answer = answer
        self.asked: list[tuple[str, str, dict[str, Any] | None]] = []

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.asked.append((method, path, body))
        return self.answer


@pytest.mark.parametrize(
    "answer",
    [
        {LIVE_READ_MINT_PATH: ["create", "update"]},
        {"capabilities": ["create", "update"]},
        {"data": {LIVE_READ_MINT_PATH: ["create", "update"]}},
    ],
)
def test_the_loaded_policy_is_read_in_every_shape_the_vault_answers_with(
    answer: dict[str, Any],
) -> None:
    """Delete this and a vault that wraps its answer reads as one refusing the mint, and the screen
    tells the owner to reload a policy that is already loaded."""
    vault = Answering(answer)

    assert vault.capabilities_self(LIVE_READ_MINT_PATH) == ("create", "update")
    assert vault.asked == [("POST", "sys/capabilities-self", {"paths": [LIVE_READ_MINT_PATH]})]
    assert live_reads_of(vault) is LiveReads.READY


def test_a_denied_mint_is_waiting_and_an_unreadable_answer_is_not_known() -> None:
    """The refusal, and the difference between a policy that says no and a vault that said
    nothing readable. Delete this and a garbled answer tells the owner to load the policies."""
    assert live_reads_of(Answering({LIVE_READ_MINT_PATH: ["deny"]})) is LiveReads.WAITING
    with pytest.raises(SecretsUnavailableError):
        Answering({"capabilities": "deny"}).capabilities_self(LIVE_READ_MINT_PATH)
    assert live_reads_of(Answering({})) is LiveReads.UNKNOWN
    assert live_reads_of(object()) is LiveReads.UNKNOWN


def test_a_slot_s_history_and_each_kind_s_last_use_are_read_as_the_application() -> None:
    """Through a real write, so the trigger appends the entry the history reads; and one row in each
    table that records a use, beside a row that must not count. Delete this and the page's history
    or its last use can read nothing on an install while every stubbed test stays green.
    **Skips without a server.**"""
    with retirable("brain_credential_history") as url:
        if not has_pgvector(url):
            pytest.skip("the tables the last use is read from need the full chain of migrations")
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
            " VALUES ('u_keeper', 'human', 'staff', 'Kim Keeper', 'web')",
        )
        sql(
            url,
            "INSERT INTO ops.provider_health (deployment_id, provider, last_live_at)"
            " VALUES ('d1', 'anthropic', %s), ('d2', 'anthropic', %s)",
            LONG_AGO,
            LONG_AGO - timedelta(days=1),
        )
        for lease, started in (("revoked", LONG_AGO), ("none", LONG_AGO + timedelta(days=1))):
            sql(
                url,
                "INSERT INTO ops.connector_sync (connection_id, connector, started_at, finished_at,"
                " outcome, health, next_attempt_at, detail, lease) VALUES"
                " (%s, 'xero', %s, %s, 'synced', 'ok', %s, 'Read to the end.', %s)",
                uuid.uuid4(),
                started,
                started,
                started,
                lease,
            )
        sql(
            url,
            "INSERT INTO ops.channel_delivery (channel, direction, outcome, reason, recorded_at)"
            " VALUES ('lark', 'outbound', 'sent', NULL, %s),"
            " ('lark', 'inbound', 'refused', 'bad_signature', %s)",
            LONG_AGO,
            LONG_AGO + timedelta(days=1),
        )

        async def read() -> dict[str, Any]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                await StoredCredentialWrites(sessions).record(
                    slot="providers/anthropic", written_by="u_keeper", trace_id="t1", ent_hash=""
                )
                await StoredCredentialWrites(sessions).record(
                    slot="providers/openai", written_by="u_keeper", trace_id="t2", ent_hash=""
                )
                history = StoredCredentialHistory(sessions)
                return {
                    "changes": await history.changes("credential:providers.anthropic"),
                    "provider": await history.last_used("provider", "anthropic"),
                    "connector": await history.last_used("connector", "xero"),
                    "channel": await history.last_used("channel", "lark"),
                    "relay": await history.last_used("relay", "mail_relay"),
                    "nobody": await history.last_used("provider", "openai"),
                }
            finally:
                await engine.dispose()

        found = run(read)

    [change] = found["changes"]
    assert (change.actor_id, change.actor_name) == ("u_keeper", "Kim Keeper")
    assert (found["provider"], found["connector"], found["channel"]) == (
        LONG_AGO,
        LONG_AGO,
        LONG_AGO,
    )
    assert (found["relay"], found["nobody"]) == (None, None)
