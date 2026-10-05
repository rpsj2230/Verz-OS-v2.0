"""The people step: every active person on the staff list is a Brain person before they sign in.

The pure choice of whom to make is tested without a database; what the step writes, that it never
makes a second person, and that a later sign-in and the standing step both reach the person it made
are tested against a real PostgreSQL at head, which CI provides. Without `DATABASE_URL` and
pgvector those skip.

Task ids: M1.10.1
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.principal_store import StoredPrincipals
from brain.identity.sign_in_binding import SignInBindings
from brain.identity.staff_accounts import DEFAULT_ALLOWED, HeldAccount
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)
from brain.identity.standing import standings
from brain.ops.staff_accounts_run import CONTRACTED_ENGAGEMENT_LASTS, person_for
from brain.ops.staff_people_run import (
    PeopleRun,
    people_to_make,
    provide_people,
)
from brain.ops.standing_run import apply_standing, plan_standing
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_entitlement_store import a_principal

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
NOW = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
ISSUER = "https://sign-in.example.test/realms/brain"
SOURCE = "lark"


def person(
    name: str,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
    *,
    department: str = "",
    kind: EmploymentType | None = EmploymentType.REGULAR,
) -> StaffRecord:
    return StaffRecord(
        f"{name}@example.test",
        f"Person {name}",
        department=department,
        active=status is EmploymentStatus.ACTIVE,
        status=status,
        employment_type=kind,
    )


def roster(*people: StaffRecord) -> Roster:
    return Roster(source=SOURCE, complete=True, asserts=DEFAULT_TRUST["lark"], people=people)


# ------------------------------------------------------------------ whom to make, no database


def test_every_active_person_nobody_is_joined_to_is_made_and_nobody_else() -> None:
    """Delete this and the step can make a leaver, a suspended person or somebody already joined,
    or stop making the active people the owner could not see on People."""
    listed = roster(
        person("ada"),
        person("bo", EmploymentStatus.LEFT),
        person("cy", EmploymentStatus.SUSPENDED),
        person("di", EmploymentStatus.NOT_ACTIVATED),
        person("ed"),
        person("fay", kind=EmploymentType.OUTSOURCED),
    )

    made = people_to_make(listed, joined={digest_of("ed@example.test")})

    assert [one.work_address for one in made] == ["ada@example.test", "fay@example.test"]


def test_a_run_says_how_many_it_added_and_a_trial_says_it_would() -> None:
    """Delete this and the run row loses the one sentence that says the list reached People."""
    assert PeopleRun(made=3).sentences() == ("People: 3 on the list added to People.",)
    assert PeopleRun(made=3).sentences(trial=True) == (
        "People: 3 on the list would be added to People.",
    )


# ------------------------------------------------------------------ against PostgreSQL


@pytest.fixture
def url() -> Iterator[str]:
    with at_head("brain_test_staff_people_run") as scratch:
        yield scratch


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def made_for(url: str, address: str) -> list[tuple[object, ...]]:
    """The principal the email binding for this address points at, with the binding's assurance."""
    return sql(
        url,
        "SELECT p.id, p.display_name, p.employment, p.primary_department, p.kind, i.assurance"
        " FROM auth.principal_identity i JOIN auth.principal p ON p.id = i.principal_id"
        " WHERE i.channel = %s AND i.identity_hash = %s AND i.deleted_at IS NULL",
        Channel.EMAIL.value,
        digest_of(address),
    )


def test_the_step_makes_each_active_person_a_joined_person_attributed_to_the_sync(
    url: str,
) -> None:
    """The owner's install: 123 active rows and nobody on People. Delete this and the step can
    make nothing, make a person with no join, bind the join at an assurance that admits a verb,
    or leave the ledger without who made them."""
    sql(
        url,
        "INSERT INTO gate.scope (slug, predicate) VALUES ('finance', %s)",
        '{"department": "finance"}',
    )
    sql(
        url,
        "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
        " VALUES ('c_1', 'finance', 'Finance', 'finance')",
    )
    listed = roster(
        person("ada", department="Finance"),
        person("fay", kind=EmploymentType.CONTRACTOR),
        person("bo", EmploymentStatus.LEFT),
    )

    ran = through(url, lambda sessions: provide_people(sessions, listed, now=NOW))

    assert ran == PeopleRun(made=2)
    [ada] = made_for(url, "ada@example.test")
    assert ada[1:] == ("Person ada", "staff", "finance", "human", int(Assurance.UNVERIFIED))
    [fay] = made_for(url, "fay@example.test")
    assert fay[2] == "contractor"
    ends = sql(url, "SELECT id, not_after FROM auth.principal WHERE id IN (%s, %s)", ada[0], fay[0])
    assert dict(ends) == {ada[0]: None, fay[0]: NOW + CONTRACTED_ENGAGEMENT_LASTS}
    assert made_for(url, "bo@example.test") == []
    actors = sql(
        url,
        "SELECT DISTINCT actor_id FROM obs.audit_entry WHERE subject = %s",
        f"principal:{ada[0]}",
    )
    assert (f"roster.{SOURCE}",) in actors


def test_a_second_read_makes_nobody_and_a_person_already_joined_is_not_made_again(
    url: str,
) -> None:
    """Delete this and every night's run makes the whole list again, or a person the accounts
    step or an administrator already joined gets a second self on People."""
    a_principal(url, "u_known")
    sql(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at,"
        " assurance) VALUES (%s, %s, %s, %s, %s)",
        Channel.EMAIL.value,
        digest_of("known@example.test"),
        "u_known",
        NOW,
        int(Assurance.UNVERIFIED),
    )
    listed = roster(person("known"), person("ada"))

    first = through(url, lambda sessions: provide_people(sessions, listed, now=NOW))
    second = through(url, lambda sessions: provide_people(sessions, listed, now=NOW))

    assert (first, second) == (PeopleRun(made=1), PeopleRun(made=0))
    assert [row[0] for row in made_for(url, "known@example.test")] == ["u_known"]
    assert sql(url, "SELECT count(*) FROM auth.principal WHERE display_name = 'Person ada'") == [
        (1,)
    ]


def test_a_trial_counts_the_people_it_would_make_and_writes_none(url: str) -> None:
    """Delete this and Try a read, which promises to change nobody, fills People."""
    listed = roster(person("ada"), person("bo"))

    ran = through(url, lambda sessions: provide_people(sessions, listed, now=NOW, trial=True))

    assert ran == PeopleRun(made=2)
    assert made_for(url, "ada@example.test") == []


def test_a_later_sign_in_binds_to_the_person_the_list_made_and_makes_no_second(
    url: str,
) -> None:
    """The other direction: the accounts step's `person_for` and an administrator's link both
    reach the person this step made. Delete this and a person's first sign-in can make a second
    person beside the one People shows, holding none of what was granted to the first."""
    listed = roster(person("ada"), person("bo"))
    through(url, lambda sessions: provide_people(sessions, listed, now=NOW))
    [(ada, *_)] = made_for(url, "ada@example.test")
    [(bo, *_)] = made_for(url, "bo@example.test")
    account = HeldAccount(account_id="kc-ada", email="ada@example.test", enabled=True)

    found = through(
        url,
        lambda sessions: person_for(
            sessions,
            account=account,
            person=listed.people[0],
            issuer=ISSUER,
            actor=f"roster.{SOURCE}",
            now=NOW,
            trace_id="staff-accounts-test",
        ),
    )
    through(
        url,
        lambda sessions: SignInBindings(sessions, ISSUER).bind(
            "subject-bo", principal_id=str(bo), bound_by="u_seed", now=NOW
        ),
    )

    assert found == ada
    signed = sql(
        url,
        "SELECT identity_hash, principal_id FROM auth.principal_identity WHERE channel = %s",
        SIGN_IN_CHANNEL.value,
    )
    assert sorted(signed) == sorted(
        [(subject_digest(ISSUER, "kc-ada"), ada), (subject_digest(ISSUER, "subject-bo"), bo)]
    )
    assert sql(url, "SELECT count(*) FROM auth.principal WHERE kind = 'human'") == [(2,)]


def test_a_person_the_list_made_who_then_leaves_is_kept_out_by_the_standing_step(
    url: str,
) -> None:
    """Delete this and a person the sync made stays live after the list says they left, because
    nothing but the email join ties them to their row."""
    through(url, lambda sessions: provide_people(sessions, roster(person("ada")), now=NOW))
    [(ada, *_)] = made_for(url, "ada@example.test")
    gone = (person("ada", EmploymentStatus.LEFT),)

    async def keep_out(sessions: async_sessionmaker[AsyncSession]) -> None:
        plan = await plan_standing(
            sessions,
            source=SOURCE,
            standings=standings(members=(), writes=(), people=gone),
            allowed=DEFAULT_ALLOWED,
            now=NOW,
        )
        await apply_standing(sessions, plan, source=SOURCE, now=NOW)

    through(url, keep_out)

    assert (
        through(url, lambda sessions: StoredPrincipals(sessions).live_principal(str(ada))) is None
    )


# ------------------------------------------------------------------ a contractor's end date


def ends(url: str, address: str) -> datetime | None:
    [(end,)] = sql(
        url,
        "SELECT p.not_after FROM auth.principal p JOIN auth.principal_identity i"
        " ON i.principal_id = p.id WHERE i.channel = 'email' AND i.identity_hash = %s"
        " AND i.deleted_at IS NULL",
        digest_of(address),
    )
    return end if isinstance(end, datetime) or end is None else None


def test_a_contractor_still_on_the_list_never_lapses_and_one_the_list_dropped_does(
    url: str,
) -> None:
    """Every run that still lists a contractor moves their end date on by the same span, so it
    lapses only once the list has stopped naming them for that long. Delete this and a contractor
    who is still working is locked out ninety days after the first sync."""
    contracted = EmploymentType.CONTRACTOR
    both = roster(person("fay", kind=contracted), person("gus", kind=contracted))
    through(url, lambda sessions: provide_people(sessions, both, now=NOW))
    later = NOW + timedelta(days=80)
    # Gus is still on the list, marked as having left, which is the list dropping him too.
    only_fay = roster(
        person("fay", kind=contracted), person("gus", EmploymentStatus.LEFT, kind=contracted)
    )

    ran = through(url, lambda sessions: provide_people(sessions, only_fay, now=later))

    past_the_first_span = NOW + timedelta(days=100)
    fay, gus = ends(url, "fay@example.test"), ends(url, "gus@example.test")
    assert (fay, gus) == (later + CONTRACTED_ENGAGEMENT_LASTS, NOW + CONTRACTED_ENGAGEMENT_LASTS)
    assert fay is not None and fay > past_the_first_span
    assert gus is not None and gus < past_the_first_span
    assert ran == PeopleRun(made=0, renewed=1)
    assert (
        ran.sentences()[1] == "People: 1 contracted on the list kept engaged for another 90 days."
    )


def test_an_end_date_later_than_the_span_is_left_and_a_trial_moves_none(url: str) -> None:
    """Delete this and a run shortens an end date an administrator set further out, or a trial
    read, which promises to change nobody, moves one."""
    contracted = roster(person("fay", kind=EmploymentType.CONTRACTOR))
    through(url, lambda sessions: provide_people(sessions, contracted, now=NOW))
    far = NOW + timedelta(days=1000)
    sql(
        url,
        "UPDATE auth.principal SET not_after = %s WHERE display_name = 'Person fay'",
        far,
    )
    through(url, lambda sessions: provide_people(sessions, contracted, now=NOW + timedelta(days=5)))
    kept = ends(url, "fay@example.test")
    sql(url, "UPDATE auth.principal SET not_after = %s WHERE display_name = 'Person fay'", NOW)
    tried = through(
        url,
        lambda sessions: provide_people(
            sessions, contracted, now=NOW + timedelta(days=5), trial=True
        ),
    )

    assert kept == far
    assert ends(url, "fay@example.test") == NOW
    assert tried.renewed == 0


def test_the_accounts_step_makes_a_contractor_with_the_same_end_date(url: str) -> None:
    """`person_for` makes a person when the people step has not, and a contractor with no end date
    is refused by the database. Delete this and the first outsourced account the accounts step
    makes fails its whole person."""
    fay = person("fay", kind=EmploymentType.CONTRACTOR)
    account = HeldAccount(account_id="kc-fay", email="fay@example.test", enabled=True)

    through(
        url,
        lambda sessions: person_for(
            sessions,
            account=account,
            person=fay,
            issuer=ISSUER,
            actor=f"roster.{SOURCE}",
            now=NOW,
            trace_id="staff-accounts-test",
        ),
    )

    assert ends(url, "fay@example.test") == NOW + CONTRACTED_ENGAGEMENT_LASTS
