"""A service account's key revoked and the account retired, followed to the ledger.

`tests/unit/test_service_accounts.py` proves what the routes decide over a store in memory. This file
proves what `0148` writes. **The first half needs no server**: it reads the trigger function off the
migration and holds its words to `brain.audit.record.CredentialChange`, its subject to the one
`0054` writes for the same account, and its guard to a retirement only.

**The second half runs on real rows as the application role**: an account registered, two keys
issued, one revoked, the account retired, and a key relabelled by an operator's statement. Every
entry is read back as an `AuditEntry` and the chain verified. **It skips without a server**, which is
CI's to provide.

Task ids: M27.11.5
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import INFERRED_ACTOR, AuditRecorder, CredentialChange
from brain.identity.service_account_store import StoredServiceAccounts, slot_for
from brain.session import make_session_factory
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries
from tests.unit.test_entitlement_store import a_principal
from tests.unit.test_service_accounts import ACCOUNT, ACCOUNT_SUBJECT, OWNER, an_account
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0148_service_account_retirement_audit.py"

#: A reach digest and a trace, as a route hands them to the store.
ENT_HASH = "a" * 32
TRACE = "t-retire"


def function() -> str:
    """The trigger function as the migration executes it, whitespace collapsed."""
    return " ".join(migration_module(MIGRATION).RETIREMENT_TRIGGER_FUNCTION.split())


def recorder(actor: str) -> AuditRecorder:
    return AuditRecorder(
        AuditChain(),
        actor_id=actor,
        ent_hash=ENT_HASH,
        trace_id=TRACE,
        clock=lambda: datetime(2019, 3, 4, tzinfo=UTC),
    )


def details(actor: str, change: CredentialChange, *, inferred: bool = False) -> dict[str, str]:
    """What the recorder writes for one change, which the trigger must write too."""
    entry = recorder(actor).credential(
        slot=slot_for(ACCOUNT), change=change, actor_inferred=inferred
    )
    return dict(entry.details)


# ------------------------------------------------------------------ the trigger's shape


def test_the_trigger_writes_the_recorders_two_words_one_per_table() -> None:
    """Delete this and the trigger can write a word the recorder does not know, which the audit
    screen renders as a code nobody can filter on."""
    body = function()

    assert re.findall(r"jsonb_build_object\('change', '(\w+)'\)", body) == [
        one.value for one in CredentialChange
    ]
    assert (
        "IF TG_TABLE_NAME = 'api_key' THEN "
        "v_details := jsonb_build_object('change', 'key_revoked');"
    ) in body


def test_the_subject_is_the_one_a_registration_of_the_same_account_is_filed_under() -> None:
    """One account, one subject. Delete this and a revocation lands under a subject nobody filters
    on beside the account's registration and its keys."""
    module = migration_module(MIGRATION)
    registered = recorder(OWNER).credential(slot=slot_for(ACCOUNT))

    assert f"{module.SUBJECT_PREFIX}{ACCOUNT}" == registered.subject
    assert f"v_subject text := '{module.SUBJECT_PREFIX}' || NEW.client_id;" in function()


def test_only_a_retirement_appends_and_an_unattributed_statement_is_marked_inferred() -> None:
    """Delete this and a relabel appends an entry, or a statement nobody attributed is recorded as
    if a person had pressed it."""
    body = function()

    assert (
        "IF NOT (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) THEN RETURN NULL; END IF;"
        in body
    )
    assert "v_actor text := COALESCE(v_supplied, session_user::text);" in body
    assert f"jsonb_build_object('actor', '{INFERRED_ACTOR}')" in body
    triggers = " ".join(" ".join(migration_module(MIGRATION).TRIGGERS).split())
    assert "AFTER UPDATE ON auth.api_key" in triggers
    assert "AFTER UPDATE ON auth.service_account" in triggers


# ------------------------------------------------------------------------ the database


@contextmanager
def at_head(database: str) -> Iterator[str]:
    """A database built through every migration to head, which includes `0148`."""
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("0148 is built only on the chain CI runs, where every migration is")
        yield url


async def _registered_with_keys(accounts: StoredServiceAccounts, count: int) -> list[str]:
    await accounts.register(
        an_account(), subject=ACCOUNT_SUBJECT, label="", ent_hash="", trace_id=""
    )
    handles = []
    for _ in range(count):
        minted = await accounts.issue_key(
            ACCOUNT,
            owner=OWNER,
            not_after=datetime.now(UTC) + timedelta(days=1),
            label="",
            now=datetime.now(UTC),
            ent_hash="",
            trace_id="",
        )
        assert minted is not None
        handles.append(minted.record.handle)
    return handles


def test_a_revoked_key_and_a_retired_account_each_leave_one_entry_naming_the_owner() -> None:
    """Registered, two keys issued, one revoked, the account retired: the ledger reads the
    registration, the two keys, the revocation, the last live key revoked by the retirement, and
    the retirement, every one by the owner and under one subject, and the chain verifies. A
    relabel by an operator's statement appends nothing.

    Delete this and revoking the key an integration used is a row nobody can see who changed.
    **Skips without a server.**"""
    with at_head("brain_sa_audit") as url:
        a_principal(url, OWNER)

        async def go() -> tuple[Any, ...]:
            engine = app_engine(url)
            try:
                accounts = StoredServiceAccounts(make_session_factory(engine))
                handles = await _registered_with_keys(accounts, 2)
                revoked = await accounts.revoke_key(
                    handles[0], owner=OWNER, ent_hash=ENT_HASH, trace_id=TRACE
                )
                retired = await accounts.retire(
                    ACCOUNT, owner=OWNER, ent_hash=ENT_HASH, trace_id=TRACE
                )
                return revoked, retired, handles
            finally:
                await engine.dispose()

        revoked, retired, handles = run(go)
        sql(url, "UPDATE auth.api_key SET label = 'relabelled' WHERE handle = %s", handles[1])
        chain = entries(url)

    found: list[AuditEntry] = [one for one in chain if one.action.value == "credential"]
    subject = recorder(OWNER).credential(slot=slot_for(ACCOUNT)).subject
    assert revoked is True and retired is True
    assert all(one.subject == subject for one in found)
    assert all(one.actor_id == OWNER for one in found)
    assert [dict(one.details) for one in found] == [
        {},
        {},
        {},
        details(OWNER, CredentialChange.KEY_REVOKED),
        details(OWNER, CredentialChange.KEY_REVOKED),
        details(OWNER, CredentialChange.ACCOUNT_RETIRED),
    ]
    assert [(one.ent_hash, one.trace_id) for one in found[3:]] == [(ENT_HASH, TRACE)] * 3
    assert AuditChain(chain).verify() is None


def test_an_operators_statement_revoking_a_key_is_recorded_as_the_database_role_inferred() -> None:
    """The one way to revoke without the console is a statement, and it is recorded too.

    Delete this and a key taken away at a prompt leaves no entry. **Skips without a server.**"""
    with at_head("brain_sa_audit_statement") as url:
        a_principal(url, OWNER)

        async def go() -> str:
            engine = app_engine(url)
            try:
                accounts = StoredServiceAccounts(make_session_factory(engine))
                return (await _registered_with_keys(accounts, 1))[0]
            finally:
                await engine.dispose()

        handle = run(go)
        sql(url, "UPDATE auth.api_key SET deleted_at = now() WHERE handle = %s", handle)
        [(role,)] = sql(url, "SELECT session_user::text")
        chain = entries(url)

    last = chain[-1]
    assert last.actor_id == role
    assert dict(last.details) == details(role, CredentialChange.KEY_REVOKED, inferred=True)
    assert AuditChain(chain).verify() is None
