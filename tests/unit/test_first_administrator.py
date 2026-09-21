"""The first administrator is written once, holding every administration capability over
everything, and after that the finishing screen accepts them.

The first two tests need no server. The rest build the database through `0047` with
`tests.fixtures.retirable` and skip when `DATABASE_URL` is unset. Dates are pinned in 2019 for
the reason `tests/unit/test_setup_wizard.py` gives: nothing here is about the present.

Task ids: M42.5.6, M41.2.4
"""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.firstrun import GRANT_REASON, GRANTED_BY
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.first_administrator import (
    ADMINISTRATION,
    FIRST_RUN_LOCK,
    GRANTED_AT_APPOINTMENT,
    SIGN_IN_AUTHORITY,
    AppointmentRefusal,
    FirstAdministratorRefusedError,
    FirstAdministrators,
    assert_bought_by_first_run,
    holds_everywhere,
)
from brain.identity.oidc import VerifiedClaims
from brain.identity.principal_directory import StoredDirectory
from brain.identity.roles import Role, RoleGrant
from brain.identity.sign_in_binding import Binding, sign_in_bindings
from brain.session import make_session_factory
from brain.setup_wizard import StepId, apply_install
from brain.sign_in_routes import finish_sign_in
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_api_routes import ISSUER
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_grant, a_principal
from tests.unit.test_setup_wizard import INSIDE, SECRET, an_enrolment, answered

REPO = Path(__file__).resolve().parents[2]

#: The installer's own Keycloak subject. Opaque, as a `sub` is.
INSTALLER = "9a8b7c6d-0000-4000-8000-0000000000bb"

FIRST = "u_first"
NAME = "A Person"
FINANCE = Scope.department("finance")


def first_run_grant(principal_id: str = FIRST) -> RoleGrant:
    return RoleGrant(
        principal_id=principal_id,
        role=Role.SUPER_ADMIN,
        granted_by=GRANTED_BY,
        reason=GRANT_REASON,
        granted_at=INSIDE,
    )


# ------------------------------------------------------------------------- no server


def declared_administration() -> set[str]:
    """Every `Capability(value="admin:...")` written anywhere under `src/brain`, read as syntax."""
    found: set[str] = set()
    for path in (REPO / "src" / "brain").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "Capability":
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "value"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and value.value.startswith("admin:")
                ):
                    found.add(value.value)
    return found


def test_the_first_administrator_holds_every_administration_capability_the_source_declares() -> (
    None
):
    """See `AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA`. Held against the source rather
    than against the constant. Delete this and an administrative capability added later is one
    nobody on any install holds, and its screen can never be opened."""
    assert set(ADMINISTRATION) == declared_administration()
    assert SIGN_IN_AUTHORITY.value in ADMINISTRATION
    assert all(one.startswith("admin:") for one in ADMINISTRATION)
    assert len(set(ADMINISTRATION)) == len(ADMINISTRATION)


def test_only_the_standing_grant_first_run_produces_can_appoint_a_first_administrator() -> None:
    """The positive case and two refusals. Delete this and a department admin's grant, or one
    somebody else authored, can be handed to `appoint` and written as the widest role."""
    assert_bought_by_first_run(first_run_grant())
    for wrong in (
        first_run_grant().model_copy(update={"granted_by": "u_somebody"}),
        first_run_grant().model_copy(update={"role": Role.AUDITOR}),
    ):
        with pytest.raises(FirstAdministratorRefusedError) as refused:
            assert_bought_by_first_run(wrong)
        assert refused.value.reason is AppointmentRefusal.NOT_FIRST_RUN


class NoSessions:
    """A session factory that must never be asked, so a test can prove nothing was opened."""

    def __call__(self) -> Any:
        raise AssertionError("a session was opened")


def test_a_name_the_principal_type_refuses_is_refused_before_anything_is_opened() -> None:
    """Delete this and the name can go unchecked until the database refuses it, after the lock is
    taken and the count run, as a driver error rather than the type's own sentence."""
    store = FirstAdministrators(sessions=cast(Any, NoSessions()))
    with pytest.raises(ValidationError):
        run(lambda: store.appoint(first_run_grant(), display_name=""))


# ----------------------------------------------------------------------- the database


@contextmanager
def audited(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0047` applied, as `test_sign_in_routes` builds them."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0046")
            migrate(database, "upgrade", "0047")
        yield url


def with_store[T](
    url: str, work: Callable[[FirstAdministrators], Awaitable[T]], *, options: str = ""
) -> T:
    async def go() -> T:
        engine = (
            create_async_engine(
                normalise_database_url(url),
                poolclass=NullPool,
                connect_args={"options": f"-c role=brain_app {options}"},
            )
            if options
            else app_engine(url)
        )
        try:
            return await work(FirstAdministrators(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def appoint(url: str, principal_id: str = FIRST, *, name: str = NAME) -> str:
    """Appoint, and say what came of it: `appointed` or the refusal's reason."""

    async def work(store: FirstAdministrators) -> str:
        try:
            await store.appoint(
                first_run_grant(principal_id), display_name=name, trace_id="trace-first-run"
            )
        except FirstAdministratorRefusedError as refused:
            return f"{refused.reason.value}: {refused}"
        return "appointed"

    return with_store(url, work)


def reach_of(url: str, principal_id: str) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            return await StoredEntitlements(make_session_factory(engine)).load(principal_id, INSIDE)
        finally:
            await engine.dispose()

    return run(go)


def grant_entries(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT actor_id, trace_id, details FROM obs.audit_entry"
        " WHERE action = 'grant' ORDER BY seq",
    )


def test_the_first_administrator_is_a_live_person_holding_administration_everywhere() -> None:
    """The positive case the finishing screen depends on. Delete this and the principal can be
    written as a service, under another name, with a capability or its unrestricted scope
    missing, or with the ledger guessing its author, and every refusal test still passes."""
    with audited("brain_fa_written") as url:
        before = with_store(url, lambda s: s.administrators(INSIDE))
        outcome = appoint(url)
        after = with_store(url, lambda s: s.administrators(INSIDE))
        [row] = sql(
            url,
            "SELECT kind, employment, display_name, disabled_at, deleted_at FROM auth.principal",
        )
        grants = sql(
            url,
            "SELECT capability, scope, granted_by, reason FROM gate.capability_grant"
            " WHERE principal_id = %s ORDER BY capability",
            FIRST,
        )
        reach = reach_of(url, FIRST)
        entries = grant_entries(url)

    assert (before, outcome, after) == (0, "appointed", 1)
    assert row == ("human", "staff", NAME, None, None)
    assert [one[0] for one in grants] == sorted(GRANTED_AT_APPOINTMENT)
    assert {(Scope.model_validate(one[1]).is_unrestricted(), one[2], one[3]) for one in grants} == {
        (True, GRANTED_BY, GRANT_REASON)
    }
    assert holds_everywhere(reach, INSIDE)
    # One entry per capability, and one recording them as Super Admin (M1.3.2, `0102`).
    assert len(entries) == len(GRANTED_AT_APPOINTMENT) + 1
    assert [d["role"] for _, _, d in entries if d.get("source") == "role_grant"] == ["super_admin"]
    # Told the actor rather than inferring it from granted_by, and carrying the request's trace.
    assert {(actor, trace, "actor" in details) for actor, trace, details in entries} == {
        (GRANTED_BY, "trace-first-run", False)
    }


def test_a_second_appointment_is_refused_naming_nobody_and_writes_nothing() -> None:
    """See `AN_APPOINTMENT_REFUSED_NAMES_NOBODY` and
    `firstrun.THE_FIRST_ADMINISTRATOR_CLOSES_THE_DOOR`. Delete this and the count can be skipped,
    and anybody still holding a setup code appoints a second widest account on a running
    install."""
    with audited("brain_fa_second") as url:
        first = appoint(url)
        second = appoint(url, "u_second", name="Somebody Else")
        again = appoint(url)
        principals = sql(url, "SELECT id FROM auth.principal")
        grants = sql(url, "SELECT count(*) FROM gate.capability_grant")

    assert first == "appointed"
    assert second.startswith(AppointmentRefusal.ALREADY_ADMINISTERED.value)
    assert again.startswith(AppointmentRefusal.ALREADY_ADMINISTERED.value)
    for refusal in (second, again):
        assert FIRST not in refusal
        assert NAME not in refusal
        assert "u_second" not in refusal
    assert principals == [(FIRST,)]
    assert grants == [(len(GRANTED_AT_APPOINTMENT),)]


def test_an_administrator_by_a_pack_closes_first_run_and_one_over_a_department_does_not() -> None:
    """See `ONE_TEST_OF_AN_ADMINISTRATOR`. A sign-in authority held over one department is not an
    administrator, so first run stays open; held over everything by a pack it is one, and first
    run is closed. Delete this and the count can read the grant table for the capability, miss a
    pack, or count a department administrator and close the wizard with nobody the finishing
    screen accepts."""
    with audited("brain_fa_other") as url:
        a_principal(url, "u_narrow")
        a_grant(url, "u_narrow", SIGN_IN_AUTHORITY.value, scope=FINANCE)
        narrow = appoint(url)
    with audited("brain_fa_pack") as url:
        a_principal(url, "u_packed")
        [(pack_id,)] = sql(
            url,
            "INSERT INTO gate.capability_pack (name, description, capabilities)"
            " VALUES ('administration', 'held by hand', %s) RETURNING id",
            [SIGN_IN_AUTHORITY.value],
        )
        sql(
            url,
            "INSERT INTO gate.capability_pack_assignment (principal_id, pack_id, scope, granted_by,"
            " reason) VALUES ('u_packed', %s, %s, 'u_operator', 'an operator wrote it')",
            pack_id,
            '{"clauses": []}',
        )
        packed = appoint(url)
        principals = sql(url, "SELECT id FROM auth.principal ORDER BY id")

    assert narrow == "appointed"
    assert packed.startswith(AppointmentRefusal.ALREADY_ADMINISTERED.value)
    assert principals == [("u_packed",)]


def test_a_principal_already_held_is_appointed_in_place_and_a_disabled_one_is_not() -> None:
    """A live principal keeps its own record and gains the grants; a disabled one is refused and
    nothing is written. Delete this and an existing principal either fails the appointment on its
    key or a disabled leaver is handed the widest role."""
    with audited("brain_fa_existing") as url:
        a_principal(url, FIRST)
        in_place = appoint(url, name="Not The Directory's Name")
        [(kept,)] = sql(url, "SELECT display_name FROM auth.principal WHERE id = %s", FIRST)
    with audited("brain_fa_disabled") as url:
        a_principal(url, FIRST)
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", FIRST)
        disabled = appoint(url)
        # Live in the table and past the end of their engagement at the appointment's instant.
        a_principal(url, "u_ended", employment="contractor", not_after=INSIDE - timedelta(days=1))
        ended = appoint(url, "u_ended")
        grants = sql(url, "SELECT count(*) FROM gate.capability_grant")

    assert in_place == "appointed"
    assert kept == f"Person {FIRST}"
    assert disabled.startswith(AppointmentRefusal.NO_LIVE_PRINCIPAL.value)
    assert FIRST not in disabled
    assert ended.startswith(AppointmentRefusal.NO_LIVE_PRINCIPAL.value)
    assert grants == [(0,)]


def test_an_appointment_waits_for_another_appointment_holding_the_first_run_lock() -> None:
    """See `THE_DOOR_IS_COUNTED_UNDER_A_LOCK`. Another connection holds the lock and the
    appointment is given a short lock timeout, so it must give up rather than count past it;
    released, the same engine appoints. Delete this and the lock can go, and two racing
    appointments both count zero."""
    lock = f"SELECT pg_advisory_xact_lock({FIRST_RUN_LOCK})"

    async def attempt(store: FirstAdministrators) -> str:
        try:
            await store.appoint(first_run_grant(), display_name=NAME)
        except DBAPIError as waited:
            return type(waited.orig).__name__
        return "appointed"

    with audited("brain_fa_lock") as url:
        with psycopg.connect(url) as holding:
            holding.execute(lock)
            waited = with_store(url, attempt, options="-c lock_timeout=200")
            holding.rollback()
        released = with_store(url, attempt, options="-c lock_timeout=200")

    assert (waited, released) == ("LockNotAvailable", "appointed")


# --------------------------------------------------------------------------- end to end


def claims_for(subject: str) -> VerifiedClaims:
    """Claims as `validate_token` returns them; the route tests hold how they are produced."""
    return VerifiedClaims(
        issuer=ISSUER,
        subject=subject,
        audience=("brain-api",),
        issued_at=INSIDE,
        expires_at=INSIDE + timedelta(minutes=5),
        session_id="sess-installer",
        key_id="k1",
        algorithm="RS256",
        verified_at=INSIDE,
        claims={"sub": subject},
    )


def test_after_the_wizard_appoints_the_first_administrator_the_finishing_screen_signs_them_in() -> (
    None
):
    """The gap this module closes, end to end: counted, `apply_install`, appointed, then
    `finish_sign_in` over the real stores binds the installer's subject. Before the appointment
    the same screen refuses, which is what every real install did. Delete this and the two halves
    can drift apart, an appointment the finishing screen does not recognise, with each half
    green."""
    enrolment = an_enrolment()
    draft = answered()

    async def finish(url: str) -> Binding | str:
        engine = app_engine(url)
        try:
            factory = make_session_factory(engine)
            return await finish_sign_in(
                sign_in_bindings(factory, env={"INSTALL_OIDC_ISSUER": ISSUER}),
                StoredEntitlements(factory),
                enrolment=enrolment,
                presented=SECRET,
                claims=claims_for(INSTALLER),
                principal_id=FIRST,
                trace_id="trace-finish",
                now=INSIDE,
            )
        except Absent:
            return "refused"
        finally:
            await engine.dispose()

    async def who(url: str) -> str | None:
        engine = app_engine(url)
        try:
            found = await StoredDirectory(make_session_factory(engine)).principal_for_subject(
                ISSUER, INSTALLER
            )
            return None if found is None else found.id
        finally:
            await engine.dispose()

    with audited("brain_fa_end_to_end") as url:
        unappointed = run(lambda: finish(url))
        counted = with_store(url, lambda s: s.administrators(INSIDE))
        applied = apply_install(
            draft, enrolment, SECRET, principal_id=FIRST, administrators=counted, now=INSIDE
        )
        name = draft.values_for(StepId.ADMINISTRATOR)["full_name"]

        async def write(store: FirstAdministrators) -> None:
            await store.appoint(applied.grant, display_name=name, trace_id="trace-apply")

        with_store(url, write)
        finished = run(lambda: finish(url))
        signed_in_as = run(lambda: who(url))

    assert (unappointed, counted) == ("refused", 0)
    assert finished is Binding.BOUND
    assert signed_in_as == FIRST
