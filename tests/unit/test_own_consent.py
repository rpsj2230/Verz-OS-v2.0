"""A person's own consent to a source: declared, kept in their own slot, read for them alone.

Over `brain.connectors.oauth.ConsentKind`, `brain.ops.credentials.connector_person_oauth_slot`,
`brain.ops.connector_sync_run.PersonalKeys`, `personal_access` and `personal_words`,
`WorkerConnectorKeys.lease` for a person's slot, and `brain.ops.erasure_store`'s removal of a
person's own refresh tokens, with a recorded token endpoint and vaults that answer each token by
its policy. The routes are `tests/unit/test_connector_consent_routes.py`'s, the policy files
`tests/unit/test_vault_policies.py`'s, and the whole path against PostgreSQL is the install check
in `tests/unit/test_acceptance_oauth.py`. Every refusal here has a sibling that reads.

Task ids: M11.8.6
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from brain.audit.record import credential_subject_id
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import DeclarationError
from brain.connectors.oauth import (
    NOT_CONNECTED_FOR_YOU,
    YOUR_CONSENT_WITHDRAWN,
    ConsentKind,
    ConsentNotHeldError,
    ConsentWithdrawnError,
    OAuthConsent,
)
from brain.ops.acceptance_checks_oauth import (
    AUTHORIZE_URL,
    PERSONAL_READER,
    VENDOR_EXCHANGE,
    consented_personally,
    consented_xero,
)
from brain.ops.connectable import key_reference, person_refresh_reference, refresh_reference
from brain.ops.connector_lease import (
    PERSON_LEASE_TTL,
    PERSON_POLICY,
    PERSON_TOKEN_ROLE,
    RUN_POLICY,
    RUN_TOKEN_ROLE,
)
from brain.ops.connector_sync_run import (
    PersonalKeys,
    WorkerConnectorKeys,
    is_person_slot,
    personal_access,
    personal_words,
)
from brain.ops.credentials import (
    KEY_FIELD,
    connector_oauth_slot,
    connector_person_oauth_slot,
    person_segment,
)
from brain.ops.erasure_store import (
    OWN_TOKENS_NOT_REACHED,
    _own_tokens,
    erase_own_refresh_tokens,
)
from brain.ops.leases import SealedSecret
from brain.ops.openbao import RoleToken, VaultRefusedError
from brain.ops.secrets import SecretsUnavailableError
from tests.unit.test_oauth_renewal import (
    CLIENT,
    REFRESH,
    SECRET,
    SETTINGS,
    Endpoint,
    Keys,
    Resolver,
    issued,
)

#: A clock far from any wall clock, for CLAUDE.md's reason about dates in fixtures.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
ADA: Final = "u_ada"
BEA: Final = "u_bea"


def personal(**changed: Any) -> OAuthConsent:
    given: dict[str, Any] = {
        "authorize_url": AUTHORIZE_URL,
        "token_url": VENDOR_EXCHANGE,
        "scopes": ("offline_access",),
        "kind": ConsentKind.PERSON,
        "reader": PERSONAL_READER,
    }
    given.update(changed)
    return OAuthConsent(**given)


# ------------------------------------------------------------------ the declaration
def test_a_personal_consent_names_the_reader_capability_and_a_sources_names_none() -> None:
    """A consent each person gives for themselves names the read capability a person holds to be
    read anything from the source, and a source's own consent names none. Delete this and anybody
    who can sign in may keep a refresh token for an account no read would ever use for them, or a
    source's consent carries a rule its renewal never asks."""
    assert personal().reader == PERSONAL_READER
    for refused in ("", "write:consented_account", "not a capability"):
        with pytest.raises(ConnectorContractError):
            personal(reader=refused)
    with pytest.raises(ConnectorContractError):
        personal(kind=ConsentKind.SOURCE)
    assert personal(kind=ConsentKind.SOURCE, reader="").kind is ConsentKind.SOURCE


def test_a_personal_source_asks_for_its_department_and_renews_no_scheduled_read() -> None:
    """A source each person consents to asks for the department its readers are held to, and its
    scheduled reading, if any, renews by no consent, because no read made with nobody present may
    use anybody's own token. The sibling is `consented_personally`, which is accepted. Delete this
    and a personal source can ship whose readers are held to nothing, or whose worker read renews
    with somebody's mailbox token."""
    declared = consented_personally()
    assert declared.oauth is not None and declared.console is not None
    without = tuple(one for one in declared.console.settings if one.name != "department")
    with pytest.raises(DeclarationError, match="department"):
        replace(declared, console=replace(declared.console, settings=without))
    _, renewing = consented_xero()
    with pytest.raises(DeclarationError, match="nobody present"):
        replace(declared, reading=renewing)


# ------------------------------------------------------------------ the slot
def test_a_persons_slot_is_theirs_alone_beneath_the_sources_and_the_ledger_records_it() -> None:
    """A person's slot is one segment beneath the source's own refresh token, named by a digest of
    their principal so two people never share one and a vault listing names nobody in words, and
    at the longest source name and principal it is still a slot the credential ledger records.
    Anything that is not a principal id is refused. Delete this and a principal id holding a '/'
    names somebody else's slot, or a person's consent can be kept and never recorded."""
    longest = "a" + "0" * 62
    ada, bea = connector_person_oauth_slot("xero", ADA), connector_person_oauth_slot("xero", BEA)
    assert ada.path.startswith(connector_oauth_slot("xero").path + "/")
    assert ada.path != bea.path and ADA not in ada.path
    assert is_person_slot(ada.path) and not is_person_slot(connector_oauth_slot("xero").path)
    assert credential_subject_id(connector_person_oauth_slot(longest, "u." + "x" * 126).path)
    assert person_segment(ADA) == person_segment(ADA)
    # The digest keeps an id like ".." from naming another path; the grammar refuses the rest.
    assert "/" not in person_segment("..")
    for refused in ("", "a/b", "x" * 129, "white space"):
        with pytest.raises(ValueError, match="principal"):
            person_segment(refused)


# ------------------------------------------------------------------ whose slot a read leases
def test_a_persons_keys_refuse_another_persons_slot_before_the_vault_is_asked() -> None:
    """A read made for one person leases the source's client secret and that person's own refresh
    token, and a lease of another person's slot, or of the source's own refresh token, holds its
    refusal and never reaches the keys beneath. Delete this and one person's question can lease
    another person's mailbox token."""
    keys = Keys(
        slots={
            key_reference("xero").path: SECRET,
            person_refresh_reference("xero", ADA).path: REFRESH,
            person_refresh_reference("xero", BEA).path: "BEA-REFRESH",
        }
    )
    bea = PersonalKeys(keys, connector="xero", principal_id=BEA)
    for elsewhere in (person_refresh_reference("xero", ADA), refresh_reference("xero")):
        refused = bea.lease(elsewhere, now=NOW)
        with pytest.raises(SecretsUnavailableError):
            refused.key()
    assert keys.leases == []
    assert bea.lease(person_refresh_reference("xero", BEA), now=NOW).key() == "BEA-REFRESH"
    assert bea.lease(key_reference("xero"), now=NOW).key() == SECRET


def test_a_rotation_for_one_person_is_written_to_their_slot_and_never_to_another() -> None:
    """A refresh token the vendor rotated during Bea's read is written back to Bea's slot; written
    at Ada's slot, or at the source's own, it is refused before the keys beneath are asked. Delete
    this and a rotation can overwrite somebody else's consent with a token that is not theirs."""
    keys = Keys()
    bea = PersonalKeys(keys, connector="xero", principal_id=BEA)
    for elsewhere in (person_refresh_reference("xero", ADA), refresh_reference("xero")):
        with pytest.raises(SecretsUnavailableError):
            bea.rotate(elsewhere, "NEW", now=NOW)
    assert keys.rotated == []
    bea.rotate(person_refresh_reference("xero", BEA), "NEW", now=NOW)
    assert keys.rotated == [(person_refresh_reference("xero", BEA).path, "NEW")]


@dataclass
class Minting:
    """`RunTokenVault` noting each role minted against, answering with that role's own policy
    unless `policy` says otherwise, and reading whatever `slots` holds."""

    slots: dict[str, str]
    policy: str | None = None
    roles: list[str] = field(default_factory=list)

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Any) -> RoleToken:
        self.roles.append(role)
        given = {PERSON_TOKEN_ROLE: PERSON_POLICY, RUN_TOKEN_ROLE: RUN_POLICY}[role]
        return RoleToken(
            token=SealedSecret("t"),
            accessor="a",
            lease_seconds=int(ttl.total_seconds()),
            renewable=False,
            policies=(self.policy or given,),
        )

    def holding(self, token: RoleToken) -> Any:
        vault = self

        class Reader:
            def read_static_kv(self, path: str) -> dict[str, Any]:
                if path not in vault.slots:
                    raise VaultRefusedError("absent", status=404)
                return {KEY_FIELD: vault.slots[path]}

            def revoke_self(self) -> None:
                return None

        del token
        return Reader()


def test_a_persons_token_is_read_under_the_role_only_the_application_may_mint() -> None:
    """A person's slot is leased with a token minted against the person role and judged against
    the person policy alone, for no longer than a question's read; a source's key is still leased
    under the run role. A token the vault minted with the run policy for a person's slot is given
    back unused. Delete this and a person's mailbox token is read under the role the worker mints
    for every scheduled read."""
    ada = person_refresh_reference("xero", ADA)
    vault = Minting(slots={ada.path: REFRESH, key_reference("xero").path: SECRET})
    keys = WorkerConnectorKeys(vault)
    assert keys.lease(ada, now=NOW).key() == REFRESH
    assert keys.lease(key_reference("xero"), now=NOW).key() == SECRET
    assert vault.roles == [PERSON_TOKEN_ROLE, RUN_TOKEN_ROLE]
    assert timedelta(minutes=5) >= PERSON_LEASE_TTL
    widened = WorkerConnectorKeys(Minting(slots={ada.path: REFRESH}, policy=RUN_POLICY))
    with pytest.raises(VaultRefusedError):
        widened.lease(ada, now=NOW).key()


# ------------------------------------------------------------------ the read
def access_for(principal_id: str, keys: Keys, endpoint: Endpoint) -> Any:
    return personal_access(
        personal(),
        connector="xero",
        principal_id=principal_id,
        settings=SETTINGS,
        keys=keys,
        poster=endpoint,
        resolver=Resolver(),
        now=NOW,
    )


def test_a_persons_read_renews_their_own_consent_and_keeps_a_rotation_in_their_slot() -> None:
    """Ada's read posts Ada's refresh token with the source's client secret and client id, is given
    the access the vendor issued, and the token the vendor rotated is written to Ada's slot. Delete
    this and a person's read renews with somebody else's consent, or loses their own on its first
    rotation."""
    ada = person_refresh_reference("xero", ADA)
    keys = Keys(slots={key_reference("xero").path: SECRET, ada.path: REFRESH})
    endpoint = Endpoint(issued(refresh="ROTATED-ADA"))
    token = access_for(ADA, keys, endpoint)
    assert token.value == "ACCESS-1"
    (form,) = endpoint.forms
    assert (form["refresh_token"], form["client_secret"], form["client_id"]) == (
        REFRESH,
        SECRET,
        CLIENT,
    )
    assert keys.rotated == [(ada.path, "ROTATED-ADA")]


def test_a_person_who_has_not_consented_is_told_so_and_nobody_elses_token_is_posted() -> None:
    """Bea has not consented, Ada has: Bea's read is refused as no consent held, said to her in
    words, and nothing is posted to the vendor. Delete this and a read for a person with no
    consent of their own falls through to whatever consent the source holds."""
    keys = Keys(
        slots={
            key_reference("xero").path: SECRET,
            person_refresh_reference("xero", ADA).path: REFRESH,
        }
    )
    endpoint = Endpoint(issued())
    with pytest.raises(ConsentNotHeldError) as refused:
        access_for(BEA, keys, endpoint)
    assert personal_words(refused.value) == NOT_CONNECTED_FOR_YOU
    assert endpoint.forms == []


def test_a_withdrawn_personal_consent_is_said_to_that_person_and_another_still_reads() -> None:
    """The vendor refusing Ada's renewal is Ada's consent withdrawn, said to her in her own
    sentence, while Bea's read with her own consent is renewed. Delete this and one person's
    revoked consent reads as the source down for everybody, or is not said at all."""
    keys = Keys(
        slots={
            key_reference("xero").path: SECRET,
            person_refresh_reference("xero", ADA).path: REFRESH,
            person_refresh_reference("xero", BEA).path: "BEA-REFRESH",
        }
    )
    from brain.ops.connector_sync_run import SourceAnswer

    refusing = Endpoint(SourceAnswer(status=400, headers={}, body=b'{"error":"invalid_grant"}'))
    with pytest.raises(ConsentWithdrawnError) as refused:
        access_for(ADA, keys, refusing)
    assert personal_words(refused.value) == YOUR_CONSENT_WITHDRAWN
    assert access_for(BEA, keys, Endpoint(issued())).value == "ACCESS-1"


# ------------------------------------------------------------------ erasure
@dataclass
class Removing:
    """`RemovesSlots` noting each path it removed, or refusing every one."""

    removed: list[str] = field(default_factory=list)
    refuse: bool = False

    def remove_static_kv(self, path: str) -> None:
        if self.refuse:
            raise VaultRefusedError("refused", status=403)
        self.removed.append(path)


def test_erasing_a_person_removes_their_own_slot_for_every_personal_source() -> None:
    """Erasing Ada removes Ada's slot for each source each person consents to, and nobody else's,
    and says so on the report line; a vault that refuses raises, so the request stays open. Delete
    this and a person's mailbox token outlives their erasure."""
    vault = Removing()
    said = _own_tokens(vault, ADA, ("google_workspace", "xero"))
    assert vault.removed == [
        connector_person_oauth_slot("google_workspace", ADA).path,
        connector_person_oauth_slot("xero", ADA).path,
    ]
    assert "2 source(s)" in said
    with pytest.raises(SecretsUnavailableError):
        erase_own_refresh_tokens(Removing(refuse=True), ADA, ("xero",))


def test_an_erasure_with_no_vault_says_the_tokens_were_not_reached() -> None:
    """A worker with no vault says on the report line that the person's own tokens were not
    reached, rather than finishing as though they were; an install with no source each person
    consents to says nothing about them. Delete this and an erasure reads as complete with a
    token still standing."""
    assert _own_tokens(None, ADA, ("xero",)) == f"; {OWN_TOKENS_NOT_REACHED}"
    assert _own_tokens(None, ADA, ()) == ""
    assert _own_tokens(Removing(), ADA, ()) == ""


@pytest.mark.needs_db
def test_the_drain_removes_a_persons_own_tokens_and_a_refusing_vault_leaves_the_request_open() -> (
    None
):
    """The erasure queue removes the person's own refresh token slots inside the request's
    transaction and says so on its line; a vault that refuses raises, the request's transaction
    rolls back and it stays open for the next run, rather than finishing with a token standing.
    Delete this and the drain can finish a request without ever asking the vault."""
    import psycopg

    from brain.ops.erasure_store import drain_erasure_queue
    from tests.unit.test_erasure_store import NOW as DUE
    from tests.unit.test_erasure_store import a_person, estate, file, one

    with estate("brain_erasure_own_tokens") as url:
        a_person(url, "p_ada")
        file(url, "p_ada")
        refusing = Removing(refuse=True)
        with psycopg.connect(url) as conn, pytest.raises(SecretsUnavailableError):
            drain_erasure_queue(conn, now=DUE, own_tokens=refusing, consented=("xero",))
        assert one(url, "SELECT count(*) FROM ops.erasure_request WHERE finished_at IS NULL") == 1

        vault = Removing()
        with psycopg.connect(url) as conn:
            said = drain_erasure_queue(conn, now=DUE, own_tokens=vault, consented=("xero",))
            conn.commit()
        assert vault.removed == [connector_person_oauth_slot("xero", "p_ada").path]
        assert said.endswith("their own refresh token removed from 1 source(s)")
        assert one(url, "SELECT count(*) FROM ops.erasure_request WHERE finished_at IS NULL") == 0


# ------------------------------------------------------------------ the consent rows
def test_a_table_removed_on_erasure_must_name_whose_rows_it_holds() -> None:
    """`REMOVED` is held to the subject declarations: the consent table names `principal_id` and
    is no finding, and a table declared removed that names nobody is one. Delete this and a table
    can be declared removed with no column saying whose rows the erasure deletes, so it would
    delete by a condition nobody wrote."""
    from brain.ops.erasure_store import REMOVED, SUBJECT_COLUMNS, declaration_gaps

    assert SUBJECT_COLUMNS["ops.oauth_consent"] == "principal_id"
    assert "ops.oauth_consent" in REMOVED
    assert not [one for one in declaration_gaps(("ops.oauth_consent",)) if "removed" in one]
    found = declaration_gaps(
        ("ops.nobodys",),
        subjects={},
        through={},
        about_nobody=frozenset({"ops.nobodys"}),
        retained={},
        removed={"ops.nobodys": "a reason"},
    )
    assert any("ops.nobodys is removed on erasure and names nobody" in one for one in found)


@pytest.mark.needs_db
def test_erasing_a_person_removes_their_consent_rows_and_the_application_never_can() -> None:
    """At head: the erasure queue removes Ada's consent rows and leaves Bea's, and records them
    removed; the application role, as Ada herself, is refused a DELETE of her own row while it
    may still start and take her consents. Delete this and an erased person's consents stay, or
    a debugging session grants the application DELETE and a person can erase the record that they
    asked a vendor for access."""
    import uuid

    import psycopg

    from brain.connectors.oauth import ConsentKind, new_consent, state_digest
    from brain.ops.connector_consent import StoredConsents
    from brain.ops.erasure_store import drain_erasure_queue
    from brain.session import make_app_engine, make_application_sessions
    from brain.tables.audit import attributed_to
    from brain.tables.oauth_consent import OAuthConsentRow
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_acceptance import at_head

    back = "https://console.example/connector-consent"
    with at_head("brain_oauth_consent_erased") as url:

        async def started() -> None:
            engine = make_app_engine(url)
            try:
                for who, _ in ((ADA, 1), (ADA, 2), (BEA, 1), (BEA, 2)):
                    await StoredConsents(make_application_sessions(engine)).issue(
                        connector="xero",
                        principal_id=who,
                        start=new_consent(),
                        return_address=back,
                        now=NOW,
                        kind=ConsentKind.PERSON,
                    )
            finally:
                await engine.dispose()

        run(started)

        async def deleted_as_ada() -> None:
            from sqlalchemy import delete

            engine = make_app_engine(url)
            try:
                sessions = make_application_sessions(engine)
                async with sessions() as session, session.begin():
                    for one in attributed_to(actor_id=ADA, ent_hash="", trace_id=""):
                        await session.execute(one)
                    await session.execute(
                        delete(OAuthConsentRow).where(OAuthConsentRow.principal_id == ADA)
                    )
            finally:
                await engine.dispose()

        with pytest.raises(Exception, match="permission denied"):
            run(deleted_as_ada)
        assert sql(url, "SELECT count(*) FROM ops.oauth_consent WHERE principal_id = %s", ADA) == [
            (2,)
        ]
        # The sibling: the application still starts and takes a consent of hers.
        later = new_consent()

        async def issue_and_take() -> object:
            engine = make_app_engine(url)
            try:
                store = StoredConsents(make_application_sessions(engine))
                await store.issue(
                    connector="xero",
                    principal_id=ADA,
                    start=later,
                    return_address=back,
                    now=NOW,
                    kind=ConsentKind.PERSON,
                )
                return await store.take(state=later.state, principal_id=ADA, now=NOW)
            finally:
                await engine.dispose()

        assert run(issue_and_take) is not None
        assert state_digest(later.state)

        request = uuid.uuid4()
        sql(
            url,
            "INSERT INTO ops.erasure_request "
            "(request_id, subject_id, reason_reference, requested_by, requested_at) "
            "VALUES (%s, %s, 'DSAR-1', 'u_admin', %s)",
            request,
            ADA,
            NOW,
        )
        with psycopg.connect(url) as conn:
            drain_erasure_queue(conn, now=NOW, consented=())
            conn.commit()
        assert sql(url, "SELECT principal_id, count(*) FROM ops.oauth_consent GROUP BY 1") == [
            (BEA, 2)
        ]
        [(stores,)] = sql(
            url, "SELECT stores FROM ops.erasure_request WHERE request_id = %s", request
        )
        operations = next(one for one in stores if one["store"] == "operations")
        assert operations["removed"] >= 3 and operations["reached"] is True
