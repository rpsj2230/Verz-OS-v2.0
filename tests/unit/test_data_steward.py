"""Data access begins with a named data steward, granted every connected source's reads, and never
with the administrator by default.

The first half needs no server: the spellings the steward is granted, what a manifest declares,
and the two decisions the store makes before it writes. The second half builds a database through
`0047` and `0057`, so a principal, a grant, a connection and their ledger entries are all real, and
connects as the application role so every policy applies. **It skips without a server.** Dates are
pinned in 2019 for `tests/unit/test_setup_wizard.py`'s reason: nothing here is about the present.

Task ids: M27.9.9
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.connectors.manifest import manifest_digest
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.firstrun import GRANTED_BY
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.data_steward import (
    APPOINTED_WITH,
    APPOINTMENT_GRANT_ID,
    CONTENT_PLANE,
    DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD,
    GRANT_AUTHORITY,
    STEWARD_GRANTOR,
    DataStewards,
    NamedSteward,
    StewardRefusal,
    StewardRefusedError,
    declared_capabilities,
    not_held_everywhere,
    refusal_for,
    steward_grant_id,
)
from brain.identity.first_administrator import GRANTED_AT_APPOINTMENT, FirstAdministrators
from brain.knowledge.rows import entity_capability
from brain.ops.connectable import CONNECTABLE, manifest_for
from brain.ops.connector_store import StoredConnections
from brain.session import make_session_factory
from brain.setup_routes import steward_of
from brain.setup_wizard import StepId, answer, apply_install, new_draft, steward_answer
from tests.fixtures.console_http import headers
from tests.fixtures.retirable import has_pgvector
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_connector_store import entries
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_entitlement_store import a_grant, a_principal
from tests.unit.test_first_administrator import first_run_grant
from tests.unit.test_setup_wizard import INSIDE, SECRET, an_enrolment, answered
from tests.unit.test_sign_in_routes import audited

#: People a test token can be minted for, by `tests.unit.test_api_routes.SUBJECTS`.
ADMIN = "u_admin"
STEWARD = "u_wide"
SECOND = "u_narrow"
CONNECTING = "u_elsewhere"

#: One identifier per connectable source, as `tests/unit/test_connector_routes.py` names them.
SETTINGS: Mapping[str, Mapping[str, str]] = {
    "xero": {"tenant_id": "11111111-2222-3333-4444-555555555555"},
    "hubspot": {"portal_id": "12345678"},
}

FINANCE = "finance"


# ------------------------------------------------------------------------- no server


def test_data_access_begins_with_a_named_steward_and_not_with_the_administrator() -> None:
    """`DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD` as three facts about the code rather than the
    sentence. The first administrator is granted the authority to grant and not the content plane,
    so they are not the steward by their appointment; the wizard's steward screen answered with a
    name and an address is another person; and the setup route writes that person under an id that
    is not the administrator's. Delete this and the administrator can be made the steward by
    default, which is the one outcome the owner's decision rules out."""
    assert "never the administrator by default" in DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD
    assert set(GRANTED_AT_APPOINTMENT) & set(APPOINTED_WITH) == {GRANT_AUTHORITY}

    applied = apply_install(
        answered(), an_enrolment(), SECRET, principal_id="u_first", administrators=0, now=INSIDE
    )
    named = steward_of(applied, principal_id="u_first", steward_id="u_other")

    assert applied.steward == steward_answer(answered())
    assert named is not None
    assert (named.principal_id, named.same_as_administrator) == ("u_other", False)
    assert named.display_name == "A Steward"


def test_the_steward_holds_the_console_s_own_spellings_of_the_authority_and_the_content_plane() -> (
    None
):
    """Written out because the identity package must not import the console. Delete this and a
    renamed plane or authority leaves every steward holding a capability nothing asks for, so the
    steward can neither open a content screen nor grant anybody anything."""
    assert REACH_AUTHORITY.value == GRANT_AUTHORITY
    assert plane_capability(Plane.CONTENT).value == CONTENT_PLANE
    assert APPOINTED_WITH == (CONTENT_PLANE, GRANT_AUTHORITY)


def test_a_source_declares_each_entity_it_reaches_as_its_row_and_its_fields_and_no_write() -> None:
    """Built from every connectable source's real manifest. Each entity a tool or a projection
    reaches is declared as `entity_capability` and the wildcard over its fields, and nothing is a
    write. Delete this and a source can declare a spelling the row reader never asks for, so the
    steward holds reads that admit no row, or a write can reach the steward by connecting a
    source."""
    for name, settings in SETTINGS.items():
        manifest = manifest_for(name, settings)
        entities = {one.entity for one in manifest.tools} | {
            one.entity for one in manifest.projections
        }
        declared = declared_capabilities(manifest)

        assert entities, name
        assert set(declared) == {
            value
            for entity in entities
            for value in (entity_capability(entity).value, f"{entity_capability(entity).value}.*")
        }
        assert list(declared) == sorted(declared)
        assert all(one.startswith("read:") for one in declared)
    assert set(SETTINGS) == set(CONNECTABLE)


def test_the_same_person_is_refused_unless_said_and_said_only_of_an_administrator() -> None:
    """Both refusals and both agreements. Delete this and an administrator can be made the steward
    without anybody saying so, or somebody who administers nothing can be appointed on the strength
    of a flag that claims they do."""
    assert refusal_for(administrator=True, same_as_administrator=False) is (
        StewardRefusal.SAME_PERSON_UNSAID
    )
    assert refusal_for(administrator=False, same_as_administrator=True) is (
        StewardRefusal.NOT_AN_ADMINISTRATOR
    )
    assert refusal_for(administrator=True, same_as_administrator=True) is None
    assert refusal_for(administrator=False, same_as_administrator=False) is None


def test_a_steward_grant_id_is_one_per_person_and_capability_and_the_appointment_s_is_fixed() -> (
    None
):
    """Delete this and a retired steward grant stops conflicting with the next attempt to write it,
    so connecting a source again gives back what somebody took away, or two installs' appointments
    stop sharing the key that makes a second one conflict."""
    assert steward_grant_id("u_a", "read:client") == steward_grant_id("u_a", "read:client")
    assert steward_grant_id("u_a", "read:client") != steward_grant_id("u_b", "read:client")
    assert steward_grant_id("u_a", "read:client") != steward_grant_id("u_a", "read:deal")
    assert steward_grant_id("u_a", CONTENT_PLANE) == APPOINTMENT_GRANT_ID
    assert steward_grant_id("u_b", CONTENT_PLANE) == APPOINTMENT_GRANT_ID


def test_a_reach_is_short_of_a_capability_held_nowhere_or_narrower_than_everything() -> None:
    """The positive case beside both shortfalls. Delete this and a steward holding the content
    plane over one department passes as a steward, which is a root of data access that is not
    one."""
    everything = Scope.unrestricted()
    finance = Scope.department(FINANCE)
    reach = EntitlementSet(
        principal_id="u_a",
        grants=(
            Grant(capability=REACH_AUTHORITY, scope=everything),
            Grant(capability=plane_capability(Plane.CONTENT), scope=finance),
        ),
    )

    assert not_held_everywhere(reach, (GRANT_AUTHORITY,), INSIDE) == ()
    assert not_held_everywhere(reach, APPOINTED_WITH, INSIDE) == (CONTENT_PLANE,)
    assert not_held_everywhere(reach, ("read:client", GRANT_AUTHORITY), INSIDE) == ("read:client",)


def test_the_steward_screen_is_read_as_the_administrator_only_when_that_answer_is_given() -> None:
    """Delete this and the wizard can hand the route a steward who is the administrator because
    the name was left blank, rather than because somebody chose it."""
    chosen, problems = answer(
        new_draft(),
        StepId.DATA_STEWARD,
        {"steward_is_administrator": "yes"},
        an_enrolment(),
        SECRET,
        administrators=0,
        now=INSIDE,
    )

    assert problems == ()
    assert steward_answer(chosen).same_as_administrator is True
    assert steward_answer(new_draft()).same_as_administrator is False


# ------------------------------------------------------------------------ the database


@contextmanager
def connectable_install(database: str) -> Iterator[str]:
    """A database with `0047` and `0057` applied, so a first administrator, a sign-in, a
    connection and every ledger entry are real. Without pgvector `audited` stops at `0047`;
    `0049` is run from `0048`, `0050` to `0053` are stamped and `0054` to `0057` are run, as
    `tests/unit/test_connector_store.through_0057` runs them."""
    with audited(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0048")
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0057")
        yield url


def over[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    """One unit of work through the application role's own sessions."""

    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def at_setup(url: str, steward: NamedSteward | None) -> str:
    """The wizard's appointment of `ADMIN`, with this steward: `appointed` or the refusal."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> str:
        try:
            await FirstAdministrators(sessions).appoint(
                first_run_grant(ADMIN),
                display_name="The Administrator",
                trace_id="trace-setup",
                steward=steward,
            )
        except StewardRefusedError as refused:
            return refused.reason.value
        return "appointed"

    return over(url, work)


def from_console(url: str, steward: NamedSteward, *, actor: str = ADMIN) -> str:
    """The console store's appointment: `appointed` or the refusal."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> str:
        try:
            await DataStewards(sessions).appoint(
                steward, actor=actor, ent_hash="c" * 32, trace_id="trace-console", now=INSIDE
            )
        except StewardRefusedError as refused:
            return refused.reason.value
        return "appointed"

    return over(url, work)


async def _nothing_to_keep() -> datetime | None:
    return None


def connect(
    url: str,
    name: str,
    *,
    actor: str = CONNECTING,
    keep_key: Callable[[], Awaitable[datetime | None]] = _nothing_to_keep,
    declared: Sequence[str] | None = None,
) -> str:
    """Connect one source through the store, granting what its manifest declares unless told."""
    manifest = manifest_for(name, SETTINGS[name])

    async def work(sessions: async_sessionmaker[AsyncSession]) -> str:
        try:
            await StoredConnections(sessions).connect(
                connector=name,
                settings=SETTINGS[name],
                digest=manifest_digest(manifest),
                actor=actor,
                trace_id=f"trace-connect-{name}",
                ent_hash="d" * 32,
                keep_key=keep_key,
                declared=declared_capabilities(manifest) if declared is None else declared,
            )
        except Exception as failed:
            return type(failed).__name__
        return "connected"

    return over(url, work)


def disconnect(url: str, name: str) -> None:
    over(
        url,
        lambda sessions: StoredConnections(sessions).disconnect(
            name, actor=ADMIN, trace_id=f"trace-disconnect-{name}", ent_hash="d" * 32
        ),
    )


def reach_of(url: str, principal_id: str) -> EntitlementSet:
    return over(url, lambda sessions: StoredEntitlements(sessions).load(principal_id, INSIDE))


def declared_by(name: str) -> tuple[str, ...]:
    return declared_capabilities(manifest_for(name, SETTINGS[name]))


def steward_rows(url: str) -> list[tuple[Any, ...]]:
    """Every live steward grant: holder, capability, whether over everything, and its reason."""
    return sql(
        url,
        "SELECT principal_id, capability, scope = '{\"clauses\": []}'::jsonb, reason"
        " FROM gate.capability_grant WHERE granted_by = %s AND deleted_at IS NULL"
        " ORDER BY principal_id, capability",
        STEWARD_GRANTOR,
    )


def counted(url: str) -> tuple[int, int, int]:
    """Principals, grants live or not, and ledger entries, for a write that must write nothing."""
    [(principals,)] = sql(url, "SELECT count(*) FROM auth.principal")
    [(grants,)] = sql(url, "SELECT count(*) FROM gate.capability_grant")
    [(ledger,)] = sql(url, "SELECT count(*) FROM obs.audit_entry")
    return int(principals), int(grants), int(ledger)


A_STEWARD = NamedSteward(
    principal_id=STEWARD, display_name="A Steward", same_as_administrator=False
)


def test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot() -> None:
    """The bootstrap Part 6.1 found missing, end to end through the People screen's real grant
    route. The wizard's appointment names a steward; HubSpot is connected; the steward, signed in
    with the reach the resolver returns for them, grants `read:client.name` over one department to
    a second person and is answered 201; the first administrator, with theirs, asks for the same
    grant and is refused; the second person then resolves it over that department and nowhere
    else; and the administrator still holds no content plane and no read of a client.

    Delete this and every half can pass alone while nobody on an install can be granted a read of
    the company's data, which is where every install was until 2026-09-17. **Skips without a
    server.**"""
    with connectable_install("brain_steward_bootstrap") as url:
        appointed = at_setup(url, A_STEWARD)
        connected = connect(url, "hubspot")
        a_principal(url, SECOND)
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate, is_department, label)"
            " VALUES (%s, %s::jsonb, true, 'Finance')",
            FINANCE,
            f'{{"department": "{FINANCE}"}}',
        )
        signed_in = {
            STEWARD: reach_of(url, STEWARD).grants,
            ADMIN: reach_of(url, ADMIN).grants,
        }

        async def grant_as(client: httpx.AsyncClient) -> dict[str, int]:
            said: dict[str, int] = {}
            for who in (ADMIN, STEWARD):
                response = await client.post(
                    f"{API_PREFIX}/govern/grants",
                    json={
                        "principal_id": SECOND,
                        "capability": "read:client.name",
                        "scope_slug": FINANCE,
                        "reason": "reading client names for the finance close",
                    },
                    headers=headers(who),
                )
                said[who] = response.status_code
            return said

        answered_to = pressed(url, signed_in, grant_as)
        second = reach_of(url, SECOND)
        administrator = reach_of(url, ADMIN)
        [(actor,)] = sql(
            url,
            "SELECT e.actor_id FROM obs.audit_entry e JOIN gate.capability_grant g"
            " ON e.subject = 'grant:' || g.id WHERE g.principal_id = %s AND e.action = 'grant'",
            SECOND,
        )

    assert (appointed, connected) == ("appointed", "connected")
    assert answered_to == {ADMIN: 404, STEWARD: 201}
    granted = second.scope_for(Capability(value="read:client.name"), INSIDE)
    assert granted is not None
    assert granted.matches({"department": FINANCE})
    assert not granted.matches({"department": "sales"})
    assert actor == STEWARD
    assert administrator.scope_for(plane_capability(Plane.CONTENT), INSIDE) is None
    assert administrator.scope_for(entity_capability("client"), INSIDE) is None


def test_the_administrator_is_the_steward_only_when_said_and_nobody_else_can_say_it() -> None:
    """The same person as administrator and steward, through the console's store. Unsaid, the
    administrator is refused and nothing is written; said of somebody who administers nothing, it
    is refused too; said of the administrator, they are appointed and hold the content plane over
    everything. Delete this and the check can stop reading the resolver, and the widest governance
    and the widest data reach can be put in one account by leaving a box unticked. **Skips without
    a server.**"""
    with connectable_install("brain_steward_same_person") as url:
        at_setup(url, None)
        a_principal(url, SECOND)
        before = counted(url)
        unsaid = from_console(url, NamedSteward(ADMIN, "", same_as_administrator=False))
        claimed = from_console(url, NamedSteward(SECOND, "", same_as_administrator=True))
        after_refusals = counted(url)
        said = from_console(url, NamedSteward(ADMIN, "", same_as_administrator=True))
        holds = not_held_everywhere(reach_of(url, ADMIN), APPOINTED_WITH, INSIDE)

    assert unsaid == StewardRefusal.SAME_PERSON_UNSAID.value
    assert claimed == StewardRefusal.NOT_AN_ADMINISTRATOR.value
    assert after_refusals == before
    assert said == "appointed"
    assert holds == ()


def test_a_connection_grants_the_steward_in_its_own_transaction_and_a_failed_one_grants_none() -> (
    None
):
    """Three connections of Xero with a steward appointed. The first is refused by the vault before
    its row; the second fails on a grant after its row, so the row it wrote must go with it; the
    third connects, and the steward holds exactly what Xero declares, over everything, beside what
    the appointment gave them. Delete this and the grants can be written in a transaction of their
    own, so a connection that failed leaves a steward reading a source that is not connected, or a
    connection that succeeded leaves nobody able to grant its data. **Skips without a server.**"""

    async def refused() -> datetime | None:
        raise RuntimeError("the vault refused")

    with connectable_install("brain_steward_connect") as url:
        at_setup(url, A_STEWARD)
        before = steward_rows(url)
        by_vault = connect(url, "xero", keep_key=refused)
        by_grant = connect(url, "xero", declared=("read:invoice", "not a capability"))
        after_failures = (
            steward_rows(url),
            sql(url, "SELECT count(*) FROM ops.connector_connection"),
        )
        connected = connect(url, "xero")
        after = steward_rows(url)

    assert by_vault == "RuntimeError"
    assert by_grant in {"IntegrityError", "DBAPIError"}
    assert after_failures == (before, [(0,)])
    assert connected == "connected"
    assert [one[1] for one in before] == sorted(APPOINTED_WITH)
    assert {one[1] for one in after} == {*APPOINTED_WITH, *declared_by("xero")}
    assert {(one[0], one[2]) for one in after} == {(STEWARD, True)}


def test_an_appointment_after_sources_are_connected_grants_what_they_declare() -> None:
    """HubSpot connected with nobody appointed grants nothing to anybody; a steward named from the
    console afterwards holds what HubSpot declares, over everything. Delete this and an install that
    connected its sources before naming a steward, which is every install set up before
    2026-09-17, has a steward who can grant none of them. **Skips without a server.**"""
    with connectable_install("brain_steward_after") as url:
        at_setup(url, None)
        connected = connect(url, "hubspot")
        before = steward_rows(url)
        appointed = from_console(url, A_STEWARD)
        after = steward_rows(url)

    assert (connected, before, appointed) == ("connected", [], "appointed")
    assert {one[1] for one in after} == {*APPOINTED_WITH, *declared_by("hubspot")}
    assert {(one[0], one[2]) for one in after} == {(STEWARD, True)}


def test_disconnecting_retires_nothing_and_a_read_taken_from_the_steward_is_not_given_back() -> (
    None
):
    """HubSpot connected, disconnected and connected again. The disconnection retires no grant and
    appends no revocation; a read somebody retired between the two connections stays retired when
    the source is connected again. Delete this and a disconnection can become a second, silent path
    to revocation, or a reconnection can undo a revocation nobody asked to undo. **Skips without a
    server.**"""
    with connectable_install("brain_steward_disconnect") as url:
        at_setup(url, A_STEWARD)
        connect(url, "hubspot")
        connected = steward_rows(url)
        disconnect(url, "hubspot")
        disconnected = steward_rows(url)
        revocations = sql(url, "SELECT count(*) FROM obs.audit_entry WHERE action = 'revoke'")
        sql(
            url,
            "UPDATE gate.capability_grant SET deleted_at = statement_timestamp()"
            " WHERE principal_id = %s AND capability = 'read:client.*'",
            STEWARD,
        )
        reconnected = connect(url, "hubspot")
        after = steward_rows(url)

    assert disconnected == connected
    assert revocations == [(0,)]
    assert reconnected == "connected"
    assert {one[1] for one in after} == {one[1] for one in connected} - {"read:client.*"}


def test_a_second_appointment_writes_nothing_even_after_the_first_was_taken_away() -> None:
    """A steward named at setup, then a console appointment of the administrator: refused, and not a
    principal, a grant or a ledger entry more. With the first appointment's grant retired, a second
    appointment of somebody new is refused as well and writes nothing, the principal it would have
    minted included. Delete this and the console becomes a way to replace a steward, which leaves
    two roots of data access where the ledger names one. **Skips without a server.**"""
    with connectable_install("brain_steward_twice") as url:
        at_setup(url, A_STEWARD)
        before = counted(url)
        again = from_console(url, NamedSteward(ADMIN, "", same_as_administrator=True))
        after_again = counted(url)
        sql(
            url,
            "UPDATE gate.capability_grant SET deleted_at = statement_timestamp() WHERE id = %s",
            APPOINTMENT_GRANT_ID,
        )
        retired = counted(url)
        replaced = from_console(url, NamedSteward("u_new", "Somebody New", False))
        after_replaced = counted(url)
        newcomer = sql(url, "SELECT count(*) FROM auth.principal WHERE id = 'u_new'")

    assert again == StewardRefusal.ALREADY_APPOINTED.value
    assert after_again == before
    assert replaced == StewardRefusal.ALREADY_APPOINTED.value
    assert after_replaced == retired
    assert newcomer == [(0,)]


def test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it() -> None:
    """Three writers, three actors, never inferred. The wizard's appointment is first run; a
    connection is the person connecting; the console's appointment is the administrator who made
    it, with their reach's digest and the request's trace. Delete this and a steward's grants can
    be recorded against the row's grantor, which names the appointment and nobody who can be asked
    about it. **Skips without a server.**"""

    def by_actor(url: str) -> dict[str, tuple[str, str, bool]]:
        rows = sql(
            url,
            "SELECT id, capability FROM gate.capability_grant WHERE granted_by = %s",
            STEWARD_GRANTOR,
        )
        subjects = {f"grant:{one[0]}": str(one[1]) for one in rows}
        return {
            subjects[entry.subject]: (entry.actor_id, entry.trace_id, "actor" in entry.details)
            for entry in entries(url)
            if entry.action.value == "grant" and entry.subject in subjects
        }

    with connectable_install("brain_steward_ledger_setup") as url:
        at_setup(url, A_STEWARD)
        connect(url, "xero")
        at_setup_and_connect = by_actor(url)
    with connectable_install("brain_steward_ledger_console") as url:
        at_setup(url, None)
        from_console(url, A_STEWARD)
        from_the_console = by_actor(url)
        [(ent_hash,)] = sql(
            url,
            "SELECT e.ent_hash FROM obs.audit_entry e WHERE e.subject = %s",
            f"grant:{APPOINTMENT_GRANT_ID}",
        )

    assert set(at_setup_and_connect) == {*APPOINTED_WITH, *declared_by("xero")}
    for capability, recorded in at_setup_and_connect.items():
        if capability in APPOINTED_WITH:
            assert recorded == (GRANTED_BY, "trace-setup", False)
        else:
            assert recorded == (CONNECTING, "trace-connect-xero", False)
    assert set(from_the_console) == set(APPOINTED_WITH)
    assert set(from_the_console.values()) == {(ADMIN, "trace-console", False)}
    assert ent_hash == "c" * 32


def test_a_person_holding_part_of_a_steward_s_reach_narrower_or_not_live_is_not_appointed() -> None:
    """Four people who are not appointed and one who is. The content plane held over one
    department, the authority to grant held over one department, a disabled person and a service
    principal are each refused, with nothing written; a live person holding neither is appointed.
    Delete this and a steward who holds their reach over one department passes as the root of data
    access, or a service account becomes it. **Skips without a server.**"""
    finance = Scope.department(FINANCE)
    outcomes: dict[str, str] = {}
    with connectable_install("brain_steward_refused") as url:
        at_setup(url, None)
        for pid in ("u_content", "u_authority", "u_disabled", "u_live"):
            a_principal(url, pid)
        a_grant(url, "u_content", CONTENT_PLANE, scope=finance)
        a_grant(url, "u_authority", GRANT_AUTHORITY, scope=finance)
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'u_disabled'")
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES ('s_service', 'service', 'staff', 'A Service')",
        )
        before = counted(url)
        for pid in ("u_content", "u_authority", "u_disabled", "s_service"):
            outcomes[pid] = from_console(url, NamedSteward(pid, "", same_as_administrator=False))
        after = counted(url)
        outcomes["u_live"] = from_console(url, NamedSteward("u_live", "", False))

    assert outcomes == {
        "u_content": StewardRefusal.HOLDS_PART_ALREADY.value,
        "u_authority": StewardRefusal.HOLDS_PART_ALREADY.value,
        "u_disabled": StewardRefusal.NO_LIVE_PERSON.value,
        "s_service": StewardRefusal.NO_LIVE_PERSON.value,
        "u_live": "appointed",
    }
    assert after == before
