"""Install acceptance checks for the people side of the staff list: Sync now, what People says about
each person the list names, and adding a work email.

Each check calls the route the console page calls, as the reserved reader that page serves, in the
shape `brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`).
Everything a check writes is inside the harness's transaction and is rolled back with it.

**Sync now is proved up to the worker's door, and the sentence says so.** The press writes the same
run request the Scheduled jobs screen's Run now writes, and the worker's next tick starts the
control; running the sync here would be a second way to apply the list with the credential the
worker keeps. So the check proves the press, the one request it leaves, who may press, and what the
page then says about the last and next scheduled runs. It never reads a staff source.

**The route needs a source the worker reads, and an install without one is not run.** Sync now
refuses a source nothing reads on a schedule, in words, and the check asks the route as it is, so
on an install that reads no list the check says it was not run rather than choosing a source for
it. See `NO_SOURCE_THE_WORKER_READS`.

**What People says about a person is read from the rows the list left, as the page reads them.**
The check writes the roster rows a sync would have written for reserved people, under the source
this install reads, inside its transaction, joins each to a reserved person by the address digest,
and asks the People list and a person's page. Nothing outside the transaction ever holds the rows.

**A work email is added through the route, with the staff list's person made by the sync's own
function.** `provide_people` makes the list's person exactly as the nightly run does, so the join
the route performs is proved against the row the sync would have made and not one the check drew.

Task ids: M38.5.1, M1.10.2, M1.6.13, M1.10.4, M1.10.5, M1.6.19
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import insert, select, update

from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.identity.principal_directory import SIGN_IN_CHANNEL
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)
from brain.listing import ListAsked
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness
from brain.ops.staff_people_run import provide_people
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 600

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Said when this install's chosen staff source is not one the worker reads on a schedule.
NO_SOURCE_THE_WORKER_READS: Final = (
    "this install's chosen staff source is not one the worker reads on a schedule, so Sync now has "
    "nothing to ask for; it runs once a source the worker reads is chosen on Staff sources"
)

#: Said when this install reads no staff list, so People has no list to say anything about.
NO_STAFF_LIST_IS_READ: Final = (
    "this install reads no staff list, so People says nothing about where a list puts anybody; "
    "it runs once a staff source is chosen on Staff sources"
)

#: Why the one setting a check holds is process state, put back when the check ends.
A_SETTING_THE_CHECK_HOLDS_IS_PUT_BACK: Final = (
    "Where departments come from is read from the process's saved values, so the check holds one "
    "answer and then the other for the length of its own work and puts back what was held when it "
    "ends, whatever happened, as the settings check does. Nothing is saved to the database."
)

# ------------------------------------------------------------------------ the figures
#: The authorities the checks' administrators hold. Restated rather than imported, so a change to
#: a route's authority fails its check instead of moving with it.
CHANGES_SETTINGS: Final = "admin:install_setting"
MANAGES_CREDENTIALS: Final = "admin:credential"
SWITCHES_FEATURES: Final = "admin:feature"
APPROVES_GRANTS: Final = "approve:grant"
MANAGES_DEPARTMENTS: Final = "admin:department"
MANAGES_SCOPES: Final = "admin:scope"

#: How a directory would spell the first reserved department: what the harness founds it as.
SPELLED_A: Final = "Acceptance check A"


# ------------------------------------------------------------------------ the helpers
def _address(h: Harness, principal_id: str) -> str:
    """A made-up work address for a reserved principal, on a domain nothing delivers to."""
    return f"{principal_id.replace('.', '-')}-{h.run}@acceptance.invalid"


def _page(body: bytes | memoryview) -> dict[str, object]:
    found = json.loads(bytes(body))
    if not isinstance(found, dict):
        raise CheckFailedError("a route answered with something that is not an object")
    return found


async def _bound(h: Harness, principal_id: str) -> None:
    """The work email as the roster's join leaves it: an email binding that admits nothing."""
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            channel=Channel.EMAIL.value,
            identity_hash=digest_of(_address(h, principal_id)),
            principal_id=principal_id,
            bound_at=h.now,
            assurance=0,
        ),
    )


# ------------------------------------------------------------ 1. Sync now (M1.10.2)
@check(
    leaves=("M1.10.2",),
    sentence=(
        "Sync now on Staff sources asks the worker for the scheduled staff sync for a reader who "
        "may connect a source: pressing twice leaves one request, the page says it is waiting, "
        "and it says when the last run was and the next is due. A reader who only opens the page "
        "is refused. The worker's own run is not made here."
    ),
)
async def sync_now_asks_the_worker_for_the_scheduled_staff_sync(h: Harness) -> None:
    from sqlalchemy import text

    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.identity.staff_sync import SYNC_INTERVAL
    from brain.ops.controls import CONTROLS
    from brain.ops.features import SCHEDULE_CONTROL
    from brain.ops.schedule import schedulable
    from brain.ops.schedule_control import RUN_NAMESPACE, run_requests
    from brain.ops.staff_sync_run import READERS
    from brain.staff_source_routes import (
        SYNC_CONTROL,
        SYNC_WAITING,
        ask_staff_sync_now,
        staff_sync_now,
    )
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    admin, reader = h.principal(A, "sync"), h.principal(A, "reader")
    page = screen_grants("staff_sources")
    await h.person(
        admin,
        department=A,
        grants=(
            *page,
            (CHANGES_SETTINGS, Scope.unrestricted()),
            (MANAGES_CREDENTIALS, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
        ),
    )
    await h.person(reader, department=A, grants=page)
    console = console_for(h)

    strong = await asking_as(h, admin, strong=True)
    from brain.console.staff_source_view import selection

    chosen = selection(strong.reach, strong.now)
    if chosen is None or chosen.name not in READERS or not chosen.ready:
        raise CheckNotRunError(NO_SOURCE_THE_WORKER_READS)

    # What the install has, which a person who used the screen already has switched on: switching
    # it on again writes nothing, so the check never assumes the empty state.
    async with traced(h, 1):
        await switch_feature(
            console.request("POST"),
            SCHEDULE_CONTROL.name,
            SwitchAsked(on=True),
            await asking_as(h, admin, strong=True),
        )
    if not await refused(ask_staff_sync_now(console.request("POST"), await asking_as(h, reader))):
        raise CheckFailedError("a reader who may only open Staff sources pressed Sync now")
    if (await staff_sync_now(console.request(), await asking_as(h, reader))).may_sync:
        raise CheckFailedError("Staff sources offered Sync now to a reader who may not press it")
    before = await staff_sync_now(console.request(), await asking_as(h, admin, strong=True))
    if not before.may_sync:
        raise CheckFailedError("Staff sources did not offer Sync now to a reader who may connect")

    async with traced(h, 2):
        pressed = await ask_staff_sync_now(
            console.request("POST"), await asking_as(h, admin, strong=True)
        )
    said = _page(pressed.body)
    if (
        pressed.status_code != 200
        or said.get("waiting") is not True
        or said.get("told") != (SYNC_WAITING)
    ):
        raise CheckFailedError("pressing Sync now did not say the run was asked for and waiting")
    async with traced(h, 3):
        await ask_staff_sync_now(console.request("POST"), await asking_as(h, admin, strong=True))
    async with h.sessions() as session:
        asked = await run_requests(session)
        await session.commit()
    if SYNC_CONTROL not in asked:
        raise CheckFailedError("Sync now left no run request for the worker to start")
    rows = (
        await h.execute(
            text(
                "SELECT count(*) FROM ops.setting WHERE deleted_at IS NULL AND key = :key"
            ).bindparams(key=f"{RUN_NAMESPACE}.{SYNC_CONTROL}")
        )
    ).scalar_one()
    if int(rows) != 1:
        raise CheckFailedError("pressing Sync twice left more than one run request")

    [control] = [one for one in CONTROLS if one.name == SYNC_CONTROL]
    if control not in schedulable() or not any(
        symbol.endswith(":run_staff_sync_now") for symbol in control.symbols
    ):
        raise CheckFailedError("the control Sync now asks for is not the worker's staff sync")

    from brain.ops.acceptance_operations_console_2 import as_login

    last = datetime.now(UTC) - timedelta(hours=1)
    await as_login(
        h,
        insert(ControlRunRow).values(
            name=SYNC_CONTROL,
            started_at=last,
            finished_at=last + timedelta(seconds=1),
            outcome="ok",
            detail="acceptance run",
        ),
    )
    after = await staff_sync_now(console.request(), await asking_as(h, admin, strong=True))
    if after.last_run_at != last or after.next_run_at != last + SYNC_INTERVAL:
        raise CheckFailedError("Staff sources did not say when the last run was and the next is")


# ------------------------------------------------ 2. what People says about the list (M1.6.13)
@check(
    leaves=("M1.6.13",),
    sentence=(
        "On reserved people joined to the roster rows the chosen staff source left: People "
        "lists each person's status and employment type as the list says them, the filters on "
        "each return exactly the people they name, somebody the list does not name carries "
        "neither, and a suspended person's page says in words why they cannot sign in."
    ),
)
async def people_says_where_the_staff_list_puts_each_person(h: Harness) -> None:
    from sqlalchemy import insert as insert_row

    from brain.directory_routes import directory, person_page, the_list_read
    from brain.identity.standing import WHY_KEPT_OUT, KeptOut
    from brain.listing import ListAsked
    from brain.tables.staff import StaffMemberRow

    source = the_list_read()
    if source is None:
        raise CheckNotRunError(NO_STAFF_LIST_IS_READ)
    await h.found_departments()
    admin = h.principal(A, "people")
    suspended, unlisted = h.principal(A, "suspended"), h.principal(A, "unlisted")
    outsourced, regular = h.principal(A, "outsourced"), h.principal(A, "regular")
    await h.person(admin, department=A, grants=screen_grants("people", Scope.department(A)))
    listed: dict[str, tuple[EmploymentStatus, EmploymentType]] = {
        suspended: (EmploymentStatus.SUSPENDED, EmploymentType.REGULAR),
        outsourced: (EmploymentStatus.ACTIVE, EmploymentType.OUTSOURCED),
        regular: (EmploymentStatus.ACTIVE, EmploymentType.REGULAR),
    }
    for pid in (suspended, unlisted, outsourced, regular):
        await h.person(pid, department=A)
        await _bound(h, pid)
    for pid, (status, kind) in listed.items():
        await h.execute(
            insert_row(StaffMemberRow).values(
                source=source,
                address_hash=digest_of(_address(h, pid)),
                display_name="Acceptance check",
                first_listed_at=h.now,
                last_listed_at=h.now,
                status=status.value,
                employment_type=kind.value,
            )
        )
    console = console_for(h)

    async def page(*filters: str) -> dict[str, tuple[str | None, str | None]]:
        found = await directory(
            console.request(),
            await asking_as(h, admin, strong=True),
            ListAsked(limit=200, filters=filters),
        )
        return {
            one.principal_id: (one.staff_status, one.employment_type)
            for one in found.items
            if one.principal_id.startswith(f"acceptance.{h.run}.")
        }

    shown = await page()
    expected: dict[str, tuple[str | None, str | None]] = {
        pid: (status.value, kind.value) for pid, (status, kind) in listed.items()
    }
    expected[unlisted] = (None, None)
    expected[admin] = (None, None)
    if shown != expected:
        raise CheckFailedError("People did not say where the staff list puts each person")
    if set(await page("staff_status:suspended")) != {suspended}:
        raise CheckFailedError("filtering People by status did not return exactly who it names")
    if set(await page("employment_type:outsourced")) != {outsourced}:
        raise CheckFailedError("filtering People by type did not return exactly who it names")
    told = await person_page(console.request(), suspended, await asking_as(h, admin, strong=True))
    if told.kept_out != WHY_KEPT_OUT[KeptOut.SUSPENDED]:
        raise CheckFailedError("a suspended person's page did not say in words why they are out")
    other = await person_page(console.request(), regular, await asking_as(h, admin, strong=True))
    if other.kept_out is not None:
        raise CheckFailedError("the page of somebody the list lets in said they are kept out")


# ------------------------------------------------- 3. a work email, added (M1.10.4, M1.10.5)
async def _by_hand(h: Harness, role: str) -> str:
    """A person made by hand in the first reserved department, with no work email."""
    pid = h.principal(A, role)
    await h.person(pid, department=A)
    return pid


async def _the_lists_person(h: Harness, role: str, *, address_of: str | None = None) -> str:
    """The person the nightly sync makes for an address, by the sync's own function.

    The address is `address_of`'s when given, which is how a list person comes to be the one for a
    hand-made person's address; the list's person is placed in the first reserved department.
    """
    pid = h.principal(A, role)
    holder = address_of or pid
    roster = Roster(
        source="acceptance",
        complete=True,
        asserts=DEFAULT_TRUST["lark"],
        people=(StaffRecord(_address(h, holder), "Acceptance check list", department=SPELLED_A),),
    )
    made = await provide_people(h.sessions, roster, now=h.now, new_id=lambda: pid)
    if made.made != 1:
        raise CheckFailedError("the staff sync's own function did not make the list's person")
    return pid


async def _adding(h: Harness, admin: str, principal_id: str, address: str, *, confirm: bool) -> str:
    from brain.directory_routes import WorkEmailAdding, add_work_email

    async with traced(h, 90):
        outcome = await add_work_email(
            console_for(h).request("POST"),
            principal_id,
            WorkEmailAdding(address=address, confirm=confirm),
            await asking_as(h, admin, strong=True),
        )
    return outcome.outcome


async def _listed(h: Harness) -> set[str]:
    from brain.directory_routes import live_people

    return {str(row[0]) for row in (await h.execute(live_people(100_000))).all()}


async def _holder_of(h: Harness, address: str) -> str | None:
    found = await h.execute(
        select(PrincipalIdentityRow.principal_id).where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.identity_hash == digest_of(address),
            PrincipalIdentityRow.deleted_at.is_(None),
        )
    )
    found_one: str | None = found.scalar_one_or_none()
    return found_one


async def _administrator(h: Harness) -> str:
    """An administrator over the first reserved department, who may open People and join there."""
    admin = h.principal(A, "joiner")
    await h.person(
        admin,
        department=A,
        grants=(
            *screen_grants("people", Scope.department(A)),
            (APPROVES_GRANTS, Scope.department(A)),
        ),
    )
    return admin


@check(
    leaves=("M1.10.4",),
    sentence=(
        "Adding a work email on a hand-made person's page binds it and joins the staff list's "
        "person for the address: at once when that person never signed in and holds only what "
        "the sync wrote, after a confirmation when somebody gave them something, never when they "
        "sign in with an account of their own, and never because two names match."
    ),
)
async def a_work_email_joins_the_list_person_only_where_nothing_is_lost(
    h: Harness,
) -> None:
    await h.found_departments()
    admin = await _administrator(h)

    # Nobody holds the address: it is bound, and nothing else changes.
    alone = await _by_hand(h, "alone")
    if (
        await _adding(h, admin, alone, _address(h, h.principal(A, "free")), confirm=False)
        != "bound"
    ):
        raise CheckFailedError("an address nobody holds was not simply bound")
    if await _holder_of(h, _address(h, h.principal(A, "free"))) != alone:
        raise CheckFailedError("an address nobody held was not bound to the person it was added to")

    # The list's person has never signed in and holds nothing the sync did not write: joined.
    plain = await _by_hand(h, "plain")
    theirs = await _the_lists_person(h, "plain-list", address_of=plain)
    if theirs not in await _listed(h):
        raise CheckFailedError("the staff list's person was not listed before the join")
    if await _adding(h, admin, plain, _address(h, plain), confirm=False) != "joined":
        raise CheckFailedError("a list person who never signed in and holds nothing was not joined")
    if theirs in await _listed(h) or await _holder_of(h, _address(h, plain)) != plain:
        raise CheckFailedError("a join left the list's person listed or the address elsewhere")

    # Somebody gave the list's person something: asked first, and joined once confirmed.
    held = await _by_hand(h, "held")
    held_list = await _the_lists_person(h, "held-list", address_of=held)
    await h.grant(held_list, "read:knowledge", Scope.department(A))
    if await _adding(h, admin, held, _address(h, held), confirm=False) != "ask":
        raise CheckFailedError("a list person holding something was joined without a question")
    if held_list not in await _listed(h) or await _holder_of(h, _address(h, held)) != held_list:
        raise CheckFailedError("a join that was only asked about changed something")
    if await _adding(h, admin, held, _address(h, held), confirm=True) != "joined":
        raise CheckFailedError("a confirmed join was not made")
    if held_list in await _listed(h):
        raise CheckFailedError("a confirmed join left the list's person listed")

    # The list's person signs in with an account of their own: never joined, confirmed or not.
    own = await _by_hand(h, "own")
    own_list = await _the_lists_person(h, "own-list", address_of=own)
    await h.execute(
        *h.attributed(),
        insert(PrincipalIdentityRow).values(
            channel=SIGN_IN_CHANNEL.value,
            identity_hash=digest_of(f"{h.run}-own-account"),
            principal_id=own_list,
            bound_at=h.now,
            assurance=0,
        ),
    )
    for confirmed in (False, True):
        if (
            await _adding(h, admin, own, _address(h, own), confirm=confirmed)
            != "signs_in_elsewhere"
        ):
            raise CheckFailedError("a list person who signs in on their own was joined")
    if own_list not in await _listed(h):
        raise CheckFailedError("refusing a join retired the list's person all the same")

    # Two people with one name are not one person: the address decides, never the name.
    twin = await _by_hand(h, "twin")
    twin_list = await _the_lists_person(h, "twin-list")
    await h.execute(
        update(PrincipalRow)
        .where(PrincipalRow.id.in_([twin, twin_list]))
        .values(display_name="Acceptance check twin")
    )
    if await _adding(h, admin, twin, _address(h, twin), confirm=True) != "bound":
        raise CheckFailedError("a person with a matching name was treated as the list's person")
    if twin_list not in await _listed(h):
        raise CheckFailedError("a matching name retired the list's person")


@check(
    leaves=("M1.10.5",),
    sentence=(
        "The first administrator, made by hand, adds their work email on their own People page "
        "and the person the staff sync made for that address is no longer listed, while the "
        "administrator is listed once and holds the address."
    ),
)
async def the_first_administrator_adds_a_work_email_and_the_duplicate_goes(
    h: Harness,
) -> None:
    from brain.directory_routes import directory, person_page

    await h.found_departments()
    admin = await _administrator(h)
    duplicate = await _the_lists_person(h, "duplicate", address_of=admin)
    console = console_for(h)

    async def people() -> list[str]:
        found = await directory(
            console.request(),
            await asking_as(h, admin, strong=True),
            ListAsked(limit=200),
        )
        return [
            one.principal_id
            for one in found.items
            if one.principal_id.startswith(f"acceptance.{h.run}.")
        ]

    before = await people()
    if admin not in before or duplicate not in before:
        raise CheckFailedError(
            "the administrator and the person the sync made were not both listed"
        )
    own_page = await person_page(console.request(), admin, await asking_as(h, admin, strong=True))
    if own_page.person.principal_id != admin:
        raise CheckFailedError("an administrator was not shown their own People page")
    if await _adding(h, admin, admin, _address(h, admin), confirm=False) != "joined":
        raise CheckFailedError(
            "adding the administrator's own work email did not join the duplicate"
        )
    after = await people()
    if duplicate in after or after.count(admin) != 1:
        raise CheckFailedError(
            "the person the staff list made is still listed beside the administrator"
        )
    if await _holder_of(h, _address(h, admin)) != admin:
        raise CheckFailedError("the administrator does not hold the address they added")
    if not await refused(
        person_page(console.request(), duplicate, await asking_as(h, admin, strong=True))
    ):
        raise CheckFailedError("the retired list person still has a People page")


# ----------------------------------------------- 4. departments managed on People (M1.6.19)
def _holding_departments_from(h: Harness, word: str) -> None:
    """Hold this install's answer to where departments come from, and put it back when the check
    ends, whatever happened. Process state only: nothing is written to the database. See
    `A_SETTING_THE_CHECK_HOLDS_IS_PUT_BACK`."""
    from brain.identity.departments_from import DEPARTMENTS_FROM_SETTING
    from brain.install import hold_saved, saved_values

    before = dict(saved_values())
    h.removes(lambda: hold_saved(before))
    hold_saved({**before, DEPARTMENTS_FROM_SETTING: word})


@check(
    leaves=("M1.6.19",),
    sentence=(
        "With departments managed on People, the staff sync's own questions answer that it "
        "places nobody: a person it makes sits in no department, no department the list names "
        "is offered to found, and the pack follows the department People set with no team or "
        "lead; the same checks with departments from the list place and offer them, and a move "
        "on People is refused there and made here."
    ),
)
async def departments_managed_on_people_are_not_the_staff_sync_s(h: Harness) -> None:
    from brain.directory_routes import DepartmentMoving, move_people, the_list_read
    from brain.govern_people_routes import source_departments
    from brain.identity.departments_from import (
        DepartmentsFrom,
        as_the_console_places_them,
        the_list_places_people,
    )
    from brain.tables.staff import StaffMemberRow

    source = the_list_read()
    if source is None:
        raise CheckNotRunError(NO_STAFF_LIST_IS_READ)
    await h.found_departments()
    admin = h.principal(A, "organiser")
    await h.person(
        admin,
        department=A,
        grants=(
            *screen_grants("people"),
            (APPROVES_GRANTS, Scope.unrestricted()),
            (MANAGES_DEPARTMENTS, Scope.unrestricted()),
            (MANAGES_SCOPES, Scope.unrestricted()),
        ),
    )
    console = console_for(h)
    named = "Acceptance check Zed"
    await h.execute(
        insert(StaffMemberRow).values(
            source=source,
            address_hash=digest_of(_address(h, h.principal(B, "named"))),
            display_name="Acceptance check",
            department=named,
            first_listed_at=h.now,
            last_listed_at=h.now,
        )
    )

    async def offered() -> list[str]:
        shown = await source_departments(console.request(), await asking_as(h, admin, strong=True))
        return [one.name for one in shown.to_found]

    async def made(role: str) -> str | None:
        """The department a person the sync makes is placed in, as the sync's own question says."""
        pid = h.principal(A, role)
        roster = Roster(
            source="acceptance",
            complete=True,
            asserts=DEFAULT_TRUST["lark"],
            people=(StaffRecord(_address(h, pid), "Acceptance check", department=SPELLED_A),),
        )
        await provide_people(
            h.sessions, roster, now=h.now, new_id=lambda: pid, place=the_list_places_people()
        )
        found = await h.execute(
            select(PrincipalRow.primary_department).where(PrincipalRow.id == pid)
        )
        placed: str | None = found.scalar_one()
        return placed

    # Departments from the staff list: the sync places the person and the list's department is
    # offered; People's move is refused, since the list would put them back.
    _holding_departments_from(h, DepartmentsFrom.STAFF_SOURCE.value)
    if await made("listed") != A:
        raise CheckFailedError("with departments from the list the sync did not place its person")
    if named not in await offered():
        raise CheckFailedError(
            "with departments from the list the list's department was not offered"
        )
    mover = h.principal(A, "mover")
    await h.person(mover, department=A)
    wanted = DepartmentMoving(principal_ids=[mover], department=B)
    if not await refused(
        move_people(console.request("POST"), wanted, await asking_as(h, admin, strong=True))
    ):
        raise CheckFailedError("with departments from the list a move on People was made")

    # Departments managed on People: the same questions, the other answers.
    _holding_departments_from(h, DepartmentsFrom.CONSOLE.value)
    if await made("people") is not None:
        raise CheckFailedError("with departments on People the sync placed the person it made")
    if await offered():
        raise CheckFailedError("with departments on People the list's departments were offered")
    moved = await move_people(
        console.request("POST"), wanted, await asking_as(h, admin, strong=True)
    )
    if moved.moved != [mover]:
        raise CheckFailedError("with departments on People a move on People was not made")
    placed = as_the_console_places_them(
        Roster(
            source="acceptance",
            complete=True,
            asserts=DEFAULT_TRUST["lark"],
            people=(
                StaffRecord(
                    _address(h, mover), "Acceptance check", department=A, leads=True, teams=("t",)
                ),
            ),
        ),
        {_address(h, mover).casefold(): B},
    )
    if [(one.department, one.teams, one.leads) for one in placed.people] != [(B, (), False)]:
        raise CheckFailedError("the pack did not follow the department People set, with no lead")
