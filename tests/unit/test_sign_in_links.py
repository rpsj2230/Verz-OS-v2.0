"""Sign-in links: who may see them, which one is the last administrator's, and unlinking one.

The first half needs no server: `sign_in_binding.decide_unlink`, which is the rule, and
`console.sign_in_links`, which is who may be shown the links and how a row is marked. The second
builds the database through `0047` and `0050` and drives `SignInBindings.unlink` as the
application role, proving the three things an unlink has to reach: the link retired, the `sign_in`
entry naming who retired it, and the account refused on its next request by the real directory.
It skips when there is no server.

Task ids: M27.7.11
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.console.sign_in_links import (
    LINK_AUTHORITY,
    LinkRow,
    link_rows,
    may_see_links,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.first_administrator import SIGN_IN_AUTHORITY
from brain.identity.keycloak_tokens import keycloak_authority
from brain.identity.oidc import TokenRefusal, TokenRefusedError
from brain.identity.principal_directory import StoredDirectory
from brain.identity.sign_in_binding import (
    SignInBindings,
    SignInLink,
    Unlinked,
    decide_unlink,
    sign_in_bindings,
)
from brain.ops.jobs import hidden_count_fields
from brain.session import make_session_factory
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_grant, a_principal
from tests.unit.test_keycloak_tokens import ISSUER, NOW, SUBJECT, Clock, Idp, token

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect


def reach(*grants: Grant) -> EntitlementSet:
    return EntitlementSet(principal_id="u_reader", grants=grants)


def a_link(principal_id: str) -> SignInLink:
    return SignInLink(
        principal_id=principal_id,
        display_name=f"Person {principal_id}",
        department="web",
        bound_at=LONG_AGO,
    )


# ------------------------------------------------------------------------- the rule


def test_the_last_administrators_link_is_refused_and_any_other_is_retired() -> None:
    """M27.7.11. Delete this and the last administrator can unlink themselves, which is an install
    nobody can sign in to link anybody; or the refusal can fire for a person who is not an
    administrator at all, which is nobody ever unlinked while one administrator exists."""
    assert (
        decide_unlink("u_admin", linked={"u_admin", "u_one"}, administrators={"u_admin"})
        is Unlinked.LAST_ADMINISTRATOR
    )
    assert (
        decide_unlink("u_one", linked={"u_admin", "u_one"}, administrators={"u_admin"})
        is Unlinked.UNLINKED
    )


def test_an_administrator_with_another_administrator_linked_may_be_unlinked() -> None:
    """The sibling. Delete this and every administrator's link is kept for ever, so nobody who
    administers can move to a new account."""
    assert (
        decide_unlink("u_admin", linked={"u_admin", "u_two"}, administrators={"u_admin", "u_two"})
        is Unlinked.UNLINKED
    )


def test_somebody_not_linked_is_not_linked_before_anything_else() -> None:
    """Delete this and a stale press on a row already unlinked is told it is the last
    administrator's, or an administrator not linked is unlinked, which writes nothing and says it
    did. An administrator who holds the authority and no link is not linked."""
    assert (
        decide_unlink("u_admin", linked={"u_one"}, administrators={"u_admin"})
        is Unlinked.NOT_LINKED
    )
    assert decide_unlink("u_gone", linked=(), administrators=()) is Unlinked.NOT_LINKED


# ------------------------------------------------------------------------- the screen


def test_only_the_authority_to_link_over_everything_opens_the_links() -> None:
    """Delete this and the listing can open for a department administrator, or for a reader
    holding the right capability in part of the company, and the map of who can be signed in as is
    handed out in slices. The capability is compared with the one the binding route uses."""
    everywhere = reach(Grant(capability=SIGN_IN_AUTHORITY, scope=Scope.unrestricted()))
    finance = reach(Grant(capability=SIGN_IN_AUTHORITY, scope=Scope.department("finance")))
    unrelated = reach(
        Grant(capability=Capability(value="read:session"), scope=Scope.unrestricted())
    )

    assert LINK_AUTHORITY == SIGN_IN_AUTHORITY
    assert may_see_links(everywhere, NOW)
    assert not may_see_links(finance, NOW)
    assert not may_see_links(unrelated, NOW)


def test_a_row_is_marked_the_last_administrators_from_every_administrator_not_the_page() -> None:
    """Delete this and the mark can be computed from the rows that fitted on a page, so the last
    administrator on a bounded listing is shown a control that will be refused, or two
    administrators on different pages are each marked as the last."""
    rows = link_rows([a_link("u_admin"), a_link("u_one")], administrators={"u_admin"})
    two = link_rows([a_link("u_admin")], administrators={"u_admin", "u_off_page"})

    assert [(one.principal_id, one.last_administrator) for one in rows] == [
        ("u_admin", True),
        ("u_one", False),
    ]
    assert [one.last_administrator for one in two] == [False]


def test_a_link_row_carries_no_account_digest_or_count() -> None:
    """Delete this and a row can grow the subject, the digest standing for it, or a field that
    counts what was not shown."""
    fields = set(LinkRow.__dataclass_fields__)

    assert fields == {
        "principal_id",
        "display_name",
        "department",
        "linked_at",
        "last_administrator",
    }
    assert hidden_count_fields((LinkRow, SignInLink)) == ()


# ------------------------------------------------------------- the store's orchestration


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows

    def first(self) -> Any:
        return self.rows[0] if self.rows else None


class StubSession:
    """An `AsyncSession` in the shape `SignInBindings.unlink` uses, answering by the SQL sent."""

    def __init__(self, reaches: list[tuple[str, Any]], sent: list[tuple[str, dict[str, Any]]]):
        self.reaches = reaches
        self.sent = sent

    async def __aenter__(self) -> StubSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> StubSession:
        return self

    async def execute(self, statement: Any, parameters: Any = None) -> StubResult:
        rendered = statement.compile(dialect=DIALECT)
        sql_text = " ".join(str(rendered).split())
        self.sent.append((sql_text, {**dict(rendered.params), **dict(parameters or {})}))
        if "gate.resolve_entitlements" in sql_text:
            return StubResult(self.reaches)
        if sql_text.startswith("UPDATE auth.principal_identity"):
            return StubResult([("row-id",)])
        return StubResult([])


def reach_of(principal_id: str, *capabilities: Capability) -> dict[str, Any]:
    """What the resolver returns for a principal, as the JSON `entitlements_from` reads."""
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities),
    ).model_dump(mode="json")


def stub_unlink(principal_id: str) -> tuple[Unlinked, list[tuple[str, dict[str, Any]]]]:
    sent: list[tuple[str, dict[str, Any]]] = []
    reaches = [
        ("u_admin", reach_of("u_admin", SIGN_IN_AUTHORITY)),
        ("u_other", reach_of("u_other")),
    ]
    writer = SignInBindings(
        sessions=lambda: StubSession(reaches, sent),  # type: ignore[arg-type]
        issuer=ISSUER,
    )
    outcome = run(
        lambda: writer.unlink(principal_id, unlinked_by="u_admin", now=NOW, trace_id="trace-1")
    )
    return outcome, sent


def test_an_unlink_counts_under_its_lock_and_writes_nothing_for_the_last_administrator() -> None:
    """M27.7.11, over a stub of the session. Delete this and `unlink` can count before it takes
    the lock, which is two administrators unlinking each other and nobody left; or write the
    update whatever the rule said; or leave the actor off the transaction, so `0047`'s entry
    names nobody. None of those needs a server to be noticed."""
    refused, refused_sent = stub_unlink("u_admin")
    unlinked, unlinked_sent = stub_unlink("u_other")

    def kinds(sent: list[tuple[str, dict[str, Any]]]) -> list[str]:
        return [
            "lock"
            if "pg_advisory_xact_lock" in sql_text
            else "count"
            if "gate.resolve_entitlements" in sql_text
            else "update"
            if sql_text.startswith("UPDATE")
            else "setting"
            for sql_text, _ in sent
        ]

    assert refused is Unlinked.LAST_ADMINISTRATOR
    assert "update" not in kinds(refused_sent)
    assert unlinked is Unlinked.UNLINKED
    assert kinds(unlinked_sent) == ["setting"] * 4 + ["lock", "count", "update"]
    settings = {params.get("name"): params.get("value") for _, params in unlinked_sent[:4]}
    assert settings["brain.actor_id"] == "u_admin"
    assert settings["brain.trace_id"] == "trace-1"


# ----------------------------------------------------------------------- the database


@contextmanager
def linked(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0047` and `0050` applied, as `test_session_store` has them."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0046")
            migrate(database, "upgrade", "0047")
            migrate(database, "stamp", "0049")
            migrate(database, "upgrade", "0050")
        yield url


def with_links[T](url: str, work: Callable[[SignInBindings], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            writer = sign_in_bindings(
                make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER}
            )
            return await work(writer)
        finally:
            await engine.dispose()

    return run(go)


async def bind_both(writer: SignInBindings) -> None:
    await writer.bind(SUBJECT, principal_id="u_admin", bound_by="u_seed", now=NOW)
    await writer.bind("s-other", principal_id="u_other", bound_by="u_seed", now=NOW)


def sign_in_entries(url: str) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (str(actor), str(subject), dict(details))
        for actor, subject, details in sql(
            url,
            "SELECT actor_id, subject, details FROM obs.audit_entry"
            " WHERE action = 'sign_in' ORDER BY seq",
        )
    ]


def test_the_last_administrator_is_refused_and_nothing_is_written() -> None:
    """M27.7.11, through the database and the one resolver. Delete this and the count can read the
    grant table instead of resolving, miss an administrator made some other way, or be skipped;
    and the refused unlink can still retire the row it was asked about."""
    with linked("brain_sil_last") as url:
        a_principal(url, "u_admin")
        a_principal(url, "u_other")
        a_grant(url, "u_admin", SIGN_IN_AUTHORITY.value)

        async def go(writer: SignInBindings) -> tuple[frozenset[str], Unlinked]:
            await bind_both(writer)
            administrators = await writer.administrators_linked(NOW)
            outcome = await writer.unlink("u_admin", unlinked_by="u_admin", now=NOW)
            return administrators, outcome

        administrators, outcome = with_links(url, go)
        live = sql(
            url,
            "SELECT principal_id FROM auth.principal_identity"
            " WHERE deleted_at IS NULL ORDER BY principal_id",
        )
        entries = sign_in_entries(url)

    assert administrators == frozenset({"u_admin"})
    assert outcome is Unlinked.LAST_ADMINISTRATOR
    assert live == [("u_admin",), ("u_other",)]
    assert [details["change"] for _, _, details in entries] == ["bound", "bound"]


def test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after() -> None:
    """M27.7.11's proof that the control reaches the system. The row: retired. The entry: `sign_in`
    retired, naming the administrator. The refusal: a real authority over the real directory
    admits the account before and finds nobody after. Delete this and any of the three can be
    missing while the screen reports the link gone."""
    with linked("brain_sil_unlink") as url:
        a_principal(url, "u_admin")
        a_principal(url, "u_other")
        a_grant(url, "u_admin", SIGN_IN_AUTHORITY.value)

        async def go(writer: SignInBindings) -> tuple[str, Unlinked, TokenRefusal, list[str]]:
            await writer.bind(SUBJECT, principal_id="u_other", bound_by="u_seed", now=NOW)
            await writer.bind("s-admin", principal_id="u_admin", bound_by="u_seed", now=NOW)
            authority = keycloak_authority(
                directory=StoredDirectory(writer.sessions),
                get=Idp().get,
                clock=Clock(),
                env={"INSTALL_OIDC_ISSUER": ISSUER},
            )
            presented = f"Bearer {token()}"
            before = await authority.authenticate(presented, now=NOW)
            outcome = await writer.unlink(
                "u_other", unlinked_by="u_admin", now=NOW, trace_id="trace-unlink-1"
            )
            try:
                await authority.authenticate(presented, now=NOW)
            except TokenRefusedError as refused:
                after = refused.reason
            listed, _ = await writer.links(limit=10)
            return before.principal.id, outcome, after, [one.principal_id for one in listed]

        before, outcome, after, listed = with_links(url, go)
        entries = sign_in_entries(url)

    assert before == "u_other"
    assert outcome is Unlinked.UNLINKED
    assert after is TokenRefusal.NO_PRINCIPAL
    assert listed == ["u_admin"]
    assert entries[-1][0:2] == ("u_admin", "principal:u_other")
    assert entries[-1][2] == {"change": "retired"}


@pytest.mark.parametrize("who", ["u_other", "u_nobody"])
def test_unlinking_somebody_with_no_link_writes_nothing(who: str) -> None:
    """Delete this and an unlink of somebody never linked, or already unlinked, can report success
    or write an entry for a retirement that did not happen."""
    with linked(f"brain_sil_none_{who[2:]}") as url:
        a_principal(url, "u_admin")
        a_principal(url, "u_other")

        async def go(writer: SignInBindings) -> Unlinked:
            await writer.bind(SUBJECT, principal_id="u_admin", bound_by="u_seed", now=NOW)
            if who == "u_other":
                await writer.bind("s-other", principal_id="u_other", bound_by="u_seed", now=NOW)
                await writer.retire("u_other", retired_by="u_seed")
            return await writer.unlink(who, unlinked_by="u_admin", now=NOW)

        outcome = with_links(url, go)
        retired = [one for one in sign_in_entries(url) if one[0] == "u_admin"]

    assert outcome is Unlinked.NOT_LINKED
    assert retired == []
