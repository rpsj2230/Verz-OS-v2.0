"""Furnishing an install, followed into PostgreSQL: the rows, the ledger, the grant it unblocks.

The first half needs no server: the installer's furnishing step is held to the record the store
writes and to its place in the plan, and the command's refusals. The second half runs against a
database built through the migrations that ship, to `0059`, connected as the application role so
every table's policy applies, which is how the installer's command and a later Settings action
write. Each test reads the rows as the superuser, the ledger as `AuditEntry`s with the chain
verified, and the behaviour through the route a person presses. **The second half skips without
a server.**

The starts are the application's own lifespan, entered and left through
`app.router.lifespan_context` on the event loop `scratch_postgres.run` makes, as
`tests/unit/test_app_wiring.py` drives it, with nothing wired by hand. The failing start needs no
server: it is the lifespan over an address nothing answers on, with the furnishing refused.

Task ids: M41.2.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

import brain.ops.starter_store as starter_store
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.demo import DEMO_PREFIX
from brain.deployment.installer import FURNISHED_SETTING, PLAN, _in_the_database, step_named
from brain.firstrun import GRANTED_BY
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.administration_reconciliation import TRACE_PREFIX as START_TRACE
from brain.identity.lifecycle import STARTER_PACK
from brain.ops.starter import COMPANY_SCOPE, vocabulary
from brain.ops.starter_store import FURNISHED_KEY, Furnished, furnish, main, told
from brain.session import make_session_factory
from tests.fixtures.console_http import headers
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_app_wiring import realm as realm  # the fixture, by its name
from tests.unit.test_app_wiring import wired_app
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import pressed, seen, through_0059
from tests.unit.test_credential_writes import entries
from tests.unit.test_entitlement_store import a_principal

TRACE = "install.furnish.0123456789abcdef"

#: What the grant tests grant: a capability the product declares, in the pack it furnishes.
GRANTED = "read:knowledge"

#: Everything the furnishing is allowed to change, by table. The three furnished tables, the
#: setting that records the furnishing, the ledger entry its trigger appends, and the policy epoch
#: `0003`'s pack trigger bumps.
MAY_CHANGE = frozenset(
    {
        "gate.capability_registry",
        "gate.capability_pack",
        "gate.scope",
        "ops.setting",
        "obs.audit_entry",
        "gate.policy_epoch",
    }
)


def furnished(url: str, trace_id: str = TRACE) -> Furnished:
    """One furnishing as the application role."""

    async def go() -> Furnished:
        built = app_engine(url)
        try:
            return await furnish(make_session_factory(built), actor=GRANTED_BY, trace_id=trace_id)
        finally:
            await built.dispose()

    return run(go)


def counts(url: str) -> dict[str, int]:
    """Every base table outside the catalogues and its row count, as the superuser reads it."""
    tables = [
        str(one)
        for (one,) in sql(
            url,
            "SELECT table_schema || '.' || table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema', 'public')",
        )
    ]
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in tables}  # noqa: S608


# ------------------------------------------------------------------------------ no server


def test_the_installers_furnishing_step_asks_for_the_record_the_store_writes() -> None:
    """**The done test and the store must mean the same setting.** The step is skipped when a row
    of `ops.setting` under the store's own key exists, asked as the database's login, which sees a
    retired row too; it runs the store's own command in the application container; and it sits
    after readiness, because readiness is what says the migrations made the tables, and before the
    setup code is presented, so the person who claims the system finds a scope to grant over.

    Delete this and the installer's constant can drift from the store's key, and every re-run of
    the installer furnishes again or, worse, never furnishes at all while reporting it is done."""
    step = step_named("furnish the install")
    names = [one.name for one in PLAN]

    assert FURNISHED_SETTING == FURNISHED_KEY
    assert step.changes
    assert step.already_done == _in_the_database(
        f"select 1 from ops.setting where key = '{FURNISHED_KEY}'"  # noqa: S608
    )
    assert step.run == (
        f"docker compose $BRAIN_COMPOSE_FILES exec -T app python -m {starter_store.__name__}"
    )
    assert (
        names.index("wait for the application to report ready")
        < names.index(step.name)
        < names.index("present the setup code, once")
    )


def test_the_command_refuses_arguments_and_an_install_it_cannot_reach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command takes no arguments, so a typo cannot read as an option that changed what was
    written, and with no database configured it says so and writes nothing.

    Positive sibling:
    `test_the_installers_command_furnishes_as_first_run_and_its_done_test_then_holds`.

    Delete this and a command handed a flag it ignores reports success over whatever it did."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)

    assert main(["--force"]) == 2
    assert main([]) == 2


def test_the_command_says_what_it_wrote_and_says_so_when_it_wrote_nothing() -> None:
    """A furnishing that changed nothing is told as nothing, and one that wrote names the scope and
    the pack by the product's own names.

    Delete this and a re-run that wrote nothing can be reported as a furnishing, which is how an
    operator decides the install is fine when the store never ran."""
    nothing = Furnished()
    first = Furnished(registered=("read:knowledge",), scopes=("company",), packs=("starter",))

    assert nothing.wrote_nothing
    assert told(nothing).startswith("nothing to furnish")
    assert not Furnished(registered=("read:knowledge",)).wrote_nothing
    assert not first.wrote_nothing
    assert "company" in told(first)
    assert "starter" in told(first)


# ----------------------------------------------------------------------------- with a server


def test_furnishing_twice_writes_nothing_the_second_time() -> None:
    """**The furnishing, followed to its rows and its ledger entry, and then asked again.** The
    first furnishing writes one registry row per declared capability with its declared words, the
    company-wide scope as an unrestricted predicate that is no department, and the starter pack
    with its capabilities, and records itself as one `setting` entry naming first run under the
    trace it was given. The second writes nothing: no row in any table and no ledger entry, and
    the chain verifies.

    Delete this and a furnishing can be written twice, or written with nobody named as having done
    it, and nothing reading the tables would say so."""
    with through_0059("brain_furnish_twice") as url:
        first = furnished(url)
        after_first = counts(url)
        again = furnished(url, trace_id="install.furnish.fedcba9876543210")
        after_again = counts(url)
        registry = sql(
            url,
            "SELECT capability, description, required_by_tool FROM gate.capability_registry "
            'ORDER BY capability COLLATE "C"',
        )
        scopes = sql(url, "SELECT slug, predicate, is_department, label FROM gate.scope")
        packs = sql(url, "SELECT name, description, capabilities FROM gate.capability_pack")
        found = seen(url, "setting")
        chain = entries(url)

    declared = vocabulary()
    assert first == Furnished(
        registered=tuple(sorted(one.capability.value for one in declared)),
        scopes=(COMPANY_SCOPE.slug,),
        packs=(STARTER_PACK.slug,),
        first=True,
    )
    assert again.wrote_nothing
    assert after_again == after_first
    assert registry == [(one.capability.value, one.description, None) for one in declared]
    assert scopes == [("company", {}, False, COMPANY_SCOPE.label)]
    assert packs == [
        (
            STARTER_PACK.slug,
            STARTER_PACK.label,
            sorted(one.value for one in STARTER_PACK.capabilities),
        )
    ]
    assert [(one.actor_id, one.subject, dict(one.details), one.trace_id) for one in found] == [
        (GRANTED_BY, f"setting:{FURNISHED_KEY}", {"change": "switched_on"}, TRACE)
    ]
    assert AuditChain(chain).verify() is None


def test_furnishing_never_writes_a_person_or_a_demo_row() -> None:
    """**Held against every table in the database, not against the three it means to write.** On
    an install that already holds a person, furnishing changes the row count of no table outside
    the furnished tables, their record and what their triggers touch; gives the person nothing, no
    grant and no pack; writes no department and no team; and every name it writes is clear of the
    demonstration's prefix, with the only scope restricting nothing.

    Delete this and the starter set can grow a service account, a department with a company's
    name or a demonstration row, and a test that looked only at the furnished tables would pass."""
    with through_0059("brain_furnish_nobody") as url:
        a_principal(url, "u_admin")
        before = counts(url)
        furnished(url)
        after = counts(url)
        names = [
            str(one)
            for (one,) in sql(
                url,
                "SELECT capability FROM gate.capability_registry UNION ALL "
                "SELECT slug FROM gate.scope UNION ALL SELECT name FROM gate.capability_pack "
                "UNION ALL SELECT key FROM ops.setting",
            )
        ]
        predicates = sql(url, "SELECT predicate, is_department FROM gate.scope")

    changed = {one for one in after if after[one] != before.get(one)}
    assert changed, "nothing was written, so this test proves nothing"
    assert changed <= MAY_CHANGE, sorted(changed - MAY_CHANGE)
    for table in (
        "auth.principal",
        "gate.capability_grant",
        "gate.capability_pack_assignment",
        "gate.department",
        "gate.team",
    ):
        assert after[table] == before[table], table
    assert names
    assert not [one for one in names if DEMO_PREFIX in one]
    assert predicates == [({}, False)]


def test_a_scope_or_pack_retired_after_furnishing_is_never_put_back() -> None:
    """**A retirement is a decision, and the ledger remembers the furnishing the tables hide.**
    Once furnished, the scope, the pack and one registry row are retired. Furnishing again writes
    neither the scope nor the pack, because the ledger holds the furnishing's entry, and it does
    register the capability whose row is gone, because the vocabulary is the product's.

    Positive sibling: `test_furnishing_twice_writes_nothing_the_second_time`.

    Delete this and a later furnishing puts back the scope or pack an administrator took away,
    or never registers a capability a newer release declares."""
    with through_0059("brain_furnish_retired") as url:
        assert furnished(url).first
        sql(url, "UPDATE gate.scope SET deleted_at = now()")
        sql(url, "UPDATE gate.capability_pack SET deleted_at = now()")
        sql(
            url,
            "UPDATE gate.capability_registry SET deleted_at = now() WHERE capability = %s",
            GRANTED,
        )
        again = furnished(url, trace_id="install.furnish.1111222233334444")
        live_scopes = sql(url, "SELECT slug FROM gate.scope WHERE deleted_at IS NULL")
        live_packs = sql(url, "SELECT name FROM gate.capability_pack WHERE deleted_at IS NULL")

    assert again == Furnished(registered=(GRANTED,))
    assert live_scopes == []
    assert live_packs == []


def test_two_furnishings_at_once_furnish_once() -> None:
    """Two furnishings started together each find no record of a furnishing, and the live-row
    indexes serialise them: one writes, the other waits on its uncommitted rows and writes nothing,
    and there is one row of each and one ledger entry.

    Delete this and two replicas running the command at once can write the scope twice, or both
    report themselves as the install's first furnishing."""

    async def go() -> list[Furnished]:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            return list(
                await asyncio.gather(
                    furnish(sessions, actor=GRANTED_BY, trace_id=TRACE),
                    furnish(sessions, actor=GRANTED_BY, trace_id=TRACE),
                )
            )
        finally:
            await built.dispose()

    with through_0059("brain_furnish_race") as url:
        outcomes = run(go)
        scopes = sql(url, "SELECT slug FROM gate.scope")
        found = seen(url, "setting")

    assert sorted(one.first for one in outcomes) == [False, True]
    assert [one.wrote_nothing for one in outcomes].count(True) == 1
    assert scopes == [(COMPANY_SCOPE.slug,)]
    assert len(found) == 1


def test_the_installers_command_furnishes_as_first_run_and_its_done_test_then_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**What the installer runs, run.** Before it, the step's done test finds nothing; the command
    furnishes the database the settings name through the application's own sessions and exits
    nought, the ledger names first run; after it, the done test's statement finds the record.

    Delete this and the step can run a command that writes nothing, or a done test that never
    holds, and the installer re-furnishes on every run or skips furnishing for ever."""
    query = f"select 1 from ops.setting where key = '{FURNISHED_KEY}'"  # noqa: S608
    with through_0059("brain_furnish_command") as url:
        before = sql(url, query)
        # Only for the command: the fixture reads the server's own URL from the same
        # environment to drop this database afterwards. The prefixed name wins in `Settings`.
        with monkeypatch.context() as patched:
            patched.setenv("BRAIN_DATABASE_URL", url)
            code = main([])
        after = sql(url, query)
        found = seen(url, "setting")
        scopes = sql(url, "SELECT slug FROM gate.scope WHERE deleted_at IS NULL")

    assert (before, code, after) == ([], 0, [(1,)])
    assert [one.actor_id for one in found] == [GRANTED_BY]
    assert found[0].trace_id.startswith(starter_store.FURNISHING_TRACE_PREFIX)
    assert scopes == [(COMPANY_SCOPE.slug,)]


# ------------------------------------------------------------------ the grant it unblocks

GRANTER = "u_admin"
HOLDER = "u_2"
EVERYWHERE = Scope.unrestricted()

#: What the People screen's grant needs of a granter, holding the capability it grants.
HOLDING: Mapping[str, tuple[Grant, ...]] = {
    GRANTER: (
        Grant(capability=Capability(value="read:grant"), scope=EVERYWHERE),
        Grant(capability=Capability(value="read:scope"), scope=EVERYWHERE),
        Grant(capability=REACH_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=Capability(value=GRANTED), scope=EVERYWHERE),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=EVERYWHERE),
    ),
}

#: The same granter without the capability, which `scoped_authority.may_grant` refuses.
NOT_HOLDING: Mapping[str, tuple[Grant, ...]] = {
    GRANTER: tuple(one for one in HOLDING[GRANTER] if one.capability.value != GRANTED),
}


def grant_status(url: str, grants: Mapping[str, tuple[Grant, ...]]) -> int:
    """POST one grant of `GRANTED` to `HOLDER` over the company-wide scope, as `GRANTER`."""

    async def press(client: httpx.AsyncClient) -> int:
        response = await client.post(
            f"{API_PREFIX}/govern/grants",
            json={
                "principal_id": HOLDER,
                "capability": GRANTED,
                "scope_slug": COMPANY_SCOPE.slug,
                "reason": "reading the company's knowledge",
            },
            headers=headers(GRANTER),
        )
        return response.status_code

    return pressed(url, grants, press)


def holds(url: str) -> bool:
    """Whether the resolver, read as the application role, gives `HOLDER` the capability
    everywhere."""

    async def load() -> bool:
        built = app_engine(url)
        now = datetime.now(UTC)
        try:
            reach = await StoredEntitlements(make_session_factory(built)).load(HOLDER, now)
        finally:
            await built.dispose()
        scope = reach.scope_for(Capability(value=GRANTED), now)
        return scope is not None and scope.is_unrestricted()

    return run(load)


def with_people(url: str) -> None:
    a_principal(url, GRANTER)
    a_principal(url, HOLDER)


def test_a_grant_over_the_company_wide_scope_is_refused_before_furnishing() -> None:
    """**F2 as it was.** On an install nobody has furnished, a granter holding `approve:grant` and
    the capability everywhere asks to grant it over the company-wide scope, and is refused with the
    one refusal, because no scope row carries that name. No grant row is written.

    Positive sibling: `test_a_grant_over_the_company_wide_scope_is_written_after_furnishing`.

    Delete this and the positive test could pass on an install where the scope was never the
    thing missing, which would say nothing about furnishing."""
    with through_0059("brain_furnish_grant_before") as url:
        with_people(url)
        status = grant_status(url, HOLDING)
        rows = sql(url, "SELECT count(*) FROM gate.capability_grant")

    assert status == 404
    assert rows == [(0,)]


def test_a_grant_over_the_company_wide_scope_is_written_after_furnishing() -> None:
    """**The grant furnishing unblocks, pressed over HTTP.** After furnishing, the same granter
    without the capability is still refused, which is `may_grant`'s rule and not the missing
    scope; holding it, the grant is written over the company-wide scope, recorded as a `grant`
    entry naming the granter, and the resolver then gives the holder the capability everywhere.

    Delete this and furnishing can write a scope the grant route cannot resolve, or one whose
    predicate is not the whole company, and the first administrator is still unable to grant."""
    with through_0059("brain_furnish_grant_after") as url:
        with_people(url)
        furnished(url)
        refused = grant_status(url, NOT_HOLDING)
        held_before = holds(url)
        written = grant_status(url, HOLDING)
        held_after = holds(url)
        stored = sql(
            url,
            "SELECT granted_by, scope FROM gate.capability_grant "
            "WHERE principal_id = %s AND deleted_at IS NULL",
            HOLDER,
        )
        granted = [one for one in seen(url, "grant") if one.details.get("capability") == GRANTED]
        chain = entries(url)

    assert (refused, held_before, written, held_after) == (404, False, 201, True)
    assert stored == [(GRANTER, EVERYWHERE.model_dump(mode="json"))]
    assert [one.actor_id for one in granted] == [GRANTER]
    assert AuditChain(chain).verify() is None


# ------------------------------------------------------------- furnished at every start


def started(url: str) -> int:
    """One start and stop of the application over this database, and what `/health/live` said
    while it ran. Migrations are not run by it: the database was built by the fixture."""
    app = create_app(
        Settings(env="development", database_url=url, run_migrations=False, valkey_url="")
    )

    async def go() -> int:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as c:
                return (await c.get("/health/live")).status_code

    return run(go)


def furniture(url: str) -> tuple[list[tuple[object, ...]], ...]:
    """Every row of the furnished tables and the furnishing's record, retired ones included."""
    return (
        sql(url, 'SELECT slug, deleted_at IS NULL FROM gate.scope ORDER BY slug COLLATE "C"'),
        sql(
            url,
            'SELECT name, deleted_at IS NULL FROM gate.capability_pack ORDER BY name COLLATE "C"',
        ),
        sql(
            url,
            "SELECT capability FROM gate.capability_registry WHERE deleted_at IS NULL "
            'ORDER BY capability COLLATE "C"',
        ),
        sql(url, 'SELECT key FROM ops.setting ORDER BY key COLLATE "C"'),
    )


def test_a_start_furnishes_an_install_nobody_furnished_and_records_it_as_first_run() -> None:
    """**The deploy that needs no command.** An install holding nothing furnished is started, as
    every deploy starts it: the application serves, the company-wide scope and the starter pack
    are live, every declared capability is registered, and the ledger holds one `setting` entry
    for the furnishing naming first run under a start's trace.

    Delete this and the start can stop furnishing, or furnish as some actor no reader of the
    ledger recognises, and an existing install goes on refusing every grant until somebody with a
    shell runs the command."""
    with through_0059("brain_furnish_start") as url:
        before = furniture(url)
        live = started(url)
        after = furniture(url)
        found = seen(url, "setting")
        chain = entries(url)

    assert before == ([], [], [], [])
    assert live == 200
    assert after == (
        [(COMPANY_SCOPE.slug, True)],
        [(STARTER_PACK.slug, True)],
        [(one.capability.value,) for one in vocabulary()],
        [(FURNISHED_KEY,)],
    )
    assert [(one.actor_id, one.subject) for one in found] == [
        (GRANTED_BY, f"setting:{FURNISHED_KEY}")
    ]
    assert found[0].trace_id.startswith(START_TRACE)
    assert AuditChain(chain).verify() is None


def test_a_second_start_writes_nothing() -> None:
    """A furnished install started again changes no furnished row, writes no second record and
    appends no ledger entry about furnishing.

    Delete this and every restart can append to the ledger, which on an install behind a process
    manager that restarts a crashing worker is an entry a minute, or write the furniture twice."""
    with through_0059("brain_furnish_restart") as url:
        assert started(url) == 200
        once = furniture(url)
        entries_once = seen(url, "setting")
        assert started(url) == 200
        twice = furniture(url)
        entries_twice = seen(url, "setting")

    assert once[0] == [(COMPANY_SCOPE.slug, True)]
    assert twice == once
    assert entries_twice == entries_once


def test_a_start_after_the_scope_and_pack_are_retired_puts_nothing_back() -> None:
    """**A retirement survives the next deploy.** Started once, the company-wide scope and the
    starter pack are then retired, as an administrator retires them; the next start serves and
    leaves both retired, with no live row of either and no second furnishing record.

    Delete this and every deploy puts back the scope an administrator took away, which is the
    one grant surface nobody asked to be widened growing back on a schedule."""
    with through_0059("brain_furnish_restart_retired") as url:
        assert started(url) == 200
        sql(url, "UPDATE gate.scope SET deleted_at = now()")
        sql(url, "UPDATE gate.capability_pack SET deleted_at = now()")
        retired = furniture(url)
        live = started(url)
        after = furniture(url)
        found = seen(url, "setting")

    assert live == 200
    assert after == retired
    assert after[0] == [(COMPANY_SCOPE.slug, False)]
    assert after[1] == [(STARTER_PACK.slug, False)]
    assert len(found) == 1


class FurnishingRefusedError(Exception):
    """What the database answers a furnishing with in the failing start, whatever it is."""


#: A message the refusal carries, which must never reach a log line.
REFUSAL_SAID = "password=never-logged"


def test_a_start_whose_furnishing_fails_still_serves_and_logs_only_the_class(
    realm: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Furnishing is never the reason an install is down.** The furnishing is refused at start;
    the start still completes and serves, the refusal is logged once as a warning naming the
    exception's class, and the exception's message, which can carry a connection string, is in
    no logged value.

    Delete this and a furnishing that raises can take the whole process down at start, which is
    every screen gone over a scope, or log a database's own words into the application log."""
    del realm

    async def refused(*_: object, **__: object) -> Furnished:
        raise FurnishingRefusedError(REFUSAL_SAID)

    monkeypatch.setattr("brain.app.furnish_install", refused)
    with capture_logs() as logged, TestClient(wired_app()) as client:
        live = client.get("/health/live").status_code

    warned = [one for one in logged if one.get("event") == "install could not be furnished"]
    assert live == 200
    assert warned == [
        {
            "event": "install could not be furnished",
            "error": FurnishingRefusedError.__name__,
            "log_level": "warning",
        }
    ]
    assert not [one for one in logged if REFUSAL_SAID in repr(one)]
