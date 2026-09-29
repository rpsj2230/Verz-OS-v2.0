"""The standing step against a real PostgreSQL at head: who is disabled, let back in, and kept.

`brain.ops.standing_run` reads the email bindings, the principals and the ledger's last
`principal_state` entry, and writes through `StoredPrincipalStates`; these tests hold each of those
to the tables and the triggers they drive, which the pure plan in `tests/unit/test_standing.py`
cannot. CI sets `DATABASE_URL` and has pgvector; without either every test here skips.

Task ids: M1.6.14
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.first_administrator import SIGN_IN_AUTHORITY
from brain.identity.principal_state_store import StoredPrincipalStates
from brain.identity.principal_store import StoredPrincipals
from brain.identity.sign_in_binding import SignInBindings
from brain.identity.staff_accounts import DEFAULT_ALLOWED
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import EmploymentStatus, EmploymentType, StaffRecord
from brain.identity.standing import KeptOut, StandingPlan, standings
from brain.ops.standing_run import apply_standing, plan_standing
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_entitlement_store import a_grant, a_principal

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
NOW = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
ISSUER = "https://sign-in.example.test/realms/brain"
SOURCE = "lark"


@pytest.fixture
def url() -> Iterator[str]:
    with at_head("brain_test_standing_run") as scratch:
        yield scratch


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def joined(url: str, name: str) -> str:
    """A person with a Brain principal and the roster's email join, as the accounts step leaves."""
    pid = f"u_{name}"
    a_principal(url, pid)
    sql(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at,"
        " assurance) VALUES (%s, %s, %s, %s, %s)",
        Channel.EMAIL.value,
        digest_of(f"{name}@example.test"),
        pid,
        NOW,
        int(Assurance.UNVERIFIED),
    )
    return pid


def administrator(url: str, name: str) -> str:
    """A joined person who can sign in and holds the sign-in authority over everything."""
    pid = joined(url, name)
    a_grant(url, pid, SIGN_IN_AUTHORITY.value)
    through(
        url,
        lambda sessions: SignInBindings(sessions, ISSUER).bind(
            f"subject-{name}", principal_id=pid, bound_by="u_seed", now=NOW
        ),
    )
    return pid


def listed(
    name: str,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
    kind: EmploymentType = EmploymentType.REGULAR,
) -> StaffRecord:
    return StaffRecord(
        f"{name}@example.test",
        name.title(),
        active=status is EmploymentStatus.ACTIVE,
        status=status,
        employment_type=kind,
    )


def stand(url: str, *people: StaffRecord, at: datetime = NOW) -> StandingPlan:
    """One standing step, planned and applied, as the run makes it."""

    async def go(sessions: async_sessionmaker[AsyncSession]) -> StandingPlan:
        plan = await plan_standing(
            sessions,
            source=SOURCE,
            standings=standings(members=(), writes=(), people=people),
            allowed=DEFAULT_ALLOWED,
            now=at,
        )
        await apply_standing(sessions, plan, source=SOURCE, now=at)
        return plan

    return through(url, go)


def live(url: str, pid: str) -> bool:
    """Whether the gate's own read finds this person: whether they can sign in or ask."""
    return through(url, lambda sessions: StoredPrincipals(sessions).live_principal(pid)) is not None


def state_entries(url: str, pid: str) -> list[tuple[str, str]]:
    return [
        (str(actor), str(details["change"]))
        for actor, details in sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE action = 'principal_state'"
            " AND subject = %s AND details->>'change' IN ('disabled', 'enabled') ORDER BY seq",
            f"principal:{pid}",
        )
    ]


def test_the_list_keeps_out_whom_it_says_under_its_own_name_and_lets_them_back(url: str) -> None:
    """Suspended and outsourced people are disabled, which the gate's read refuses, under the
    source's sync in the ledger; a working person is untouched; when the list lists the suspended
    one as active again they are enabled. Delete this and the plan can be right with no write
    reaching the table, or a write that the ledger records under nobody."""
    ada, bo, ed = joined(url, "ada"), joined(url, "bo"), joined(url, "ed")

    first = stand(
        url,
        listed("ada", EmploymentStatus.SUSPENDED),
        listed("bo"),
        listed("ed", kind=EmploymentType.OUTSOURCED),
    )
    assert first.to_disable == ((ada, KeptOut.SUSPENDED), (ed, KeptOut.TYPE_NOT_ALLOWED))
    assert (live(url, ada), live(url, bo), live(url, ed)) == (False, True, False)
    assert state_entries(url, ada) == [("roster.lark", "disabled")]

    again = stand(url, listed("ada"), listed("bo"), at=NOW + timedelta(days=1))
    assert again.to_enable == (ada,)
    assert live(url, ada) is True
    assert state_entries(url, ada) == [("roster.lark", "disabled"), ("roster.lark", "enabled")]


def test_somebody_an_administrator_disabled_stays_disabled_whatever_the_list_says(
    url: str,
) -> None:
    """The ledger's last word on them was a person's. Delete this and the nightly run undoes an
    administrator's decision to disable somebody."""
    cy = joined(url, "cy")
    through(
        url,
        lambda sessions: StoredPrincipalStates(sessions).set_disabled(
            cy,
            disabled=True,
            may=lambda _department: True,
            by="u_admin",
            ent_hash="0" * 32,
            trace_id="by-hand",
        ),
    )
    plan = stand(url, listed("cy"))

    assert plan.to_enable == ()
    assert live(url, cy) is False
    assert state_entries(url, cy) == [("u_admin", "disabled")]


def test_the_only_administrator_is_kept_able_to_sign_in_and_one_of_two_is_not(url: str) -> None:
    """Through the one resolver and the real sign-in bindings. Delete this and a directory marking
    the only administrator suspended locks the company out of its install, or the guard shields an
    administrator who is not the last."""
    admin = administrator(url, "admin")

    alone = stand(url, listed("admin", EmploymentStatus.SUSPENDED))
    assert alone.kept_in == (admin,)
    assert live(url, admin) is True

    administrator(url, "second")
    paired = stand(url, listed("admin", EmploymentStatus.SUSPENDED), at=NOW + timedelta(days=1))
    assert paired.to_disable == ((admin, KeptOut.SUSPENDED),)
    assert live(url, admin) is False
