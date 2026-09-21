"""Connecting a staff source from the console: test it, save it, and run its first sync.

The Staff sources screen used to say that choosing a source was an installation setting no route
could write, and that trying one needed a gatherer nothing attached. Both stopped being true: the
setup wizard and the Settings screen save installation values in `ops.setting` through
`brain.ops.install_settings`, and `brain.ops.staff_sync_run` reads Lark, Microsoft Entra and a
Google Sheet with an application's own credential. This module joins them into the three things
the owner asked to do from the console: test a source, save it, and run its first sync.

**A test reads and keeps nothing, and that is a property of what it is handed.** `check_connection`
takes the fields, a way to send a request and nothing else: no session, no vault, no settings. So
there is nothing it could write to, and the test that holds it read-only passes it a directory
stand-in and counts what it was asked. It reads a few pages rather than the whole directory, which
is enough to prove the credential, the permissions and the data range, and says how many people
those pages held. See `A_TEST_IS_A_READ_WITH_NOWHERE_TO_WRITE`.

**Saving reads again first, and keeps only what was just read with.** The setup wizard's rule
(`brain.setup_staff_routes.A_CREDENTIAL_THE_TRIAL_READ_WITH_IS_KEPT_FOR_THE_SCHEDULE`), taken to the
console: a credential the directory refused is never kept, so a save cannot leave the nightly sync
holding a secret that fails every night.

**The first sync is the nightly run, started now, with the credential the person just typed.** The
application may write the vault slot and never read it, so it cannot read back the credential it
kept; the browser still holds what was typed, and posts it again for the dry run and for the apply.
`sync_staff_on` is called exactly as the worker calls it, with a key holder that answers the typed
value, so the first run and every night after it are one code path. See
`THE_FIRST_SYNC_IS_THE_NIGHTLY_RUN_STARTED_NOW`.

Rejected: asking the worker to run it. The worker has no queue for a run somebody asked for, and a
dry run is a read the person wants to see before anything is applied, which is a request and an
answer rather than a job.

Task ids: M27.7.2, M1.8.6, M1.6.12
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.staff_directories import (
    REGISTRATION,
    DirectorySignInError,
    Fetch,
    location_problem,
)
from brain.console.staff_source_guide import LOCATION, Guide, field_problems
from brain.identity.staff_adapters import LARK, MICROSOFT_ENTRA, RosterUnavailableError
from brain.identity.staff_roster import Application, application_for
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    Roster,
    SelectableSource,
    StaffSource,
    StaffSourceError,
    roster_from,
    selected_source,
)
from brain.install import value_of
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.credentials import problems_with
from brain.ops.secrets import SecretRef
from brain.ops.staff_sync_run import (
    NOBODY_CHANGED,
    READERS,
    CredentialRefusedError,
    Reader,
    StaffSyncRun,
    read_lark,
    read_microsoft,
    sync_staff_on,
)
from brain.ops.staff_sync_store import read_last_applied, read_members

# ------------------------------------------------------------------ written-down reasons
#: Why the test cannot write, stated as what it is given.
A_TEST_IS_A_READ_WITH_NOWHERE_TO_WRITE: Final = (
    "A connection test is pressed before anything is saved, often more than once while somebody "
    "fixes a permission. It is handed the fields and a way to send a request, and no session, "
    "vault or settings store, so it has nowhere to write: nothing is saved, nobody is added and "
    "no credential is kept, however the directory answers."
)

#: Why the first sync is `sync_staff_on` and not a second apply.
THE_FIRST_SYNC_IS_THE_NIGHTLY_RUN_STARTED_NOW: Final = (
    "A first sync written separately would be a second account of what applying a staff list "
    "means, and the two would agree until one of them changed. So it is the nightly run, called "
    "the way the worker calls it, with the one difference that the credential comes from what "
    "the person typed rather than from the vault the application may not read."
)

#: How many pages a connection test reads. A department page and three pages of people.
TEST_PAGES: Final = 4


class PagedReader(Protocol):
    """A reader that can be told how many pages to read."""

    def __call__(
        self, fetch: Fetch, credential: str, location: str, *, pages: int
    ) -> Awaitable[StaffSource]: ...


#: The readers that can stop after a few pages. Any other registered reader reads the whole list,
#: which is still a read and still keeps nothing.
PAGED: Final[Mapping[str, PagedReader]] = {LARK: read_lark, MICROSOFT_ENTRA: read_microsoft}

#: What a test says after the reason, so nobody wonders whether a failed test changed anything.
NOTHING_SAVED: Final = "Nothing was saved."


class ConnectRefusedError(Exception):
    """The fields, the credential or the source said no. The message is words for the screen."""


@dataclass(frozen=True)
class ConnectionTest:
    """What one test read: how many people, whether that was all of them, and what was skipped."""

    source: str
    read: bool
    told: str
    people: int = 0
    #: True when the pages read were the whole directory.
    complete: bool = False
    #: Entries the source listed that could not become a person, such as a row with no work email.
    skipped: int = 0


def _words(said: str) -> str:
    """A reader's refusal, with the scheduled run's closing sentence swapped for the test's."""
    text = " ".join(said.split()).replace(NOBODY_CHANGED, "").strip()
    return f"{text.rstrip('.')}. {NOTHING_SAVED}"


def checked_credential(guide: Guide, values: Mapping[str, str]) -> str:
    """The credential this form makes, or a refusal in words. Never repeats a value."""
    if not guide.connectable:
        raise ConnectRefusedError(guide.unavailable)
    problems = field_problems(guide, values)
    if problems:
        raise ConnectRefusedError(" ".join(problems))
    credential = guide.credential_from(values)
    if problems_with(credential):
        msg = (
            "One of the values has a space, a line break or a character a credential cannot "
            "hold. Copy it again from where you created it."
        )
        raise ConnectRefusedError(msg)
    return credential


async def read_source(
    guide: Guide,
    values: Mapping[str, str],
    fetch: Fetch,
    *,
    pages: int | None = None,
    readers: Mapping[str, Reader] = READERS,
    paged: Mapping[str, PagedReader] = PAGED,
) -> StaffSource:
    """Read the source this form describes, a few pages or all of it, or refuse in words."""
    credential = checked_credential(guide, values)
    location = values[LOCATION].strip()
    few = paged.get(guide.source)
    try:
        if pages is not None and few is not None:
            return await few(fetch, credential, location, pages=pages)
        return await readers[guide.source](fetch, credential, location)
    except (
        CredentialRefusedError,
        DirectorySignInError,
        RosterUnavailableError,
        StaffSourceError,
    ) as refused:
        raise ConnectRefusedError(_words(str(refused))) from refused


def _reading(source: StaffSource) -> tuple[Roster, int]:
    """The roster and how many entries did not become a person."""
    reading = getattr(source, "reading", None)
    if callable(reading):
        read = reading()
        return read.roster, len(read.dropped)
    return source.roster(), 0


async def check_connection(
    guide: Guide,
    values: Mapping[str, str],
    fetch: Fetch,
    *,
    pages: int = TEST_PAGES,
    readers: Mapping[str, Reader] = READERS,
    paged: Mapping[str, PagedReader] = PAGED,
) -> ConnectionTest:
    """Read a few pages of the directory with these fields and say how many people they held.

    See `A_TEST_IS_A_READ_WITH_NOWHERE_TO_WRITE`: the parameters are the whole of what it can
    touch.
    """
    try:
        source = await read_source(guide, values, fetch, pages=pages, readers=readers, paged=paged)
        roster, skipped = _reading(source)
    except ConnectRefusedError as refused:
        return ConnectionTest(source=guide.source, read=False, told=str(refused))
    except ValueError as refused:
        return ConnectionTest(source=guide.source, read=False, told=_words(str(refused)))
    people = len(roster.people)
    if roster.complete:
        told = f"Connected. The directory lists {people} people, and all of them were read."
    else:
        told = (
            f"Connected. The first pages listed {people} people. There are more: the first "
            "sync reads them all."
        )
    if skipped:
        told += (
            f" {skipped} entries could not be read as a person, usually because they have no "
            "work email address; check the permissions in the steps above."
        )
    return ConnectionTest(
        source=guide.source,
        read=True,
        told=f"{told} {NOTHING_SAVED}",
        people=people,
        complete=roster.complete,
        skipped=skipped,
    )


def held_problems(guide: Guide, values: Mapping[str, str]) -> tuple[str, ...]:
    """What is wrong with a form that connects with a credential the vault already holds.

    Every box that is not part of the credential must be filled, and no box that is may be sent:
    in this mode a secret has nowhere to go, and one dropped silently is one somebody pasted
    believing it was used. A location for a directory signed in to is checked as the reader would.
    """
    kept = set(guide.credential_fields)
    asked = [one for one in guide.fields if one.key not in kept]
    found = [f'"{one.label}" is empty.' for one in asked if not values.get(one.key, "").strip()]
    if set(values) - {one.key for one in asked}:
        found.append(
            "A credential was sent with a connection that uses the one already kept. Choose one."
        )
    where = values.get(LOCATION, "").strip()
    if not found and guide.source in REGISTRATION:
        problem = location_problem(guide.source, where)
        if problem:
            found.append(problem)
    return tuple(found)


def settings_for(guide: Guide, values: Mapping[str, str]) -> dict[str, str]:
    """The two installation values a connection saves. The credential is never one of them."""
    return {
        STAFF_SOURCE_SETTING: guide.source,
        STAFF_SOURCE_LOCATION_SETTING: values[LOCATION].strip(),
    }


def connected_to(guide: Guide, values: Mapping[str, str], saved: Mapping[str, str]) -> str:
    """Why this form is not the saved connection, in words, or the empty string.

    The first sync reads the source the nightly run will read, so it is refused for a form that
    describes anything else: a first sync of a source nobody saved would apply a list the next
    night's run does not read.
    """
    chosen = value_of(STAFF_SOURCE_SETTING, saved=saved)
    location = value_of(STAFF_SOURCE_LOCATION_SETTING, saved=saved)
    if chosen != guide.source or location != values.get(LOCATION, "").strip():
        return "Save this connection before running its first sync."
    return ""


@dataclass(frozen=True)
class TypedKey:
    """The credential the person typed, handed to the run in the shape the vault's lease has."""

    value: str

    def key(self) -> str:
        return self.value

    def close(self, now: datetime) -> LeaseOutcome:
        # No token was minted, so nothing is revoked: `LeaseOutcome.NONE` is exactly that.
        return LeaseOutcome.NONE


@dataclass(frozen=True)
class TypedKeys:
    """Hands every lease the typed credential.

    See `THE_FIRST_SYNC_IS_THE_NIGHTLY_RUN_STARTED_NOW`.
    """

    value: str

    def lease(self, ref: SecretRef, *, now: datetime) -> TypedKey:
        return TypedKey(self.value)


async def first_sync_plan(
    guide: Guide,
    values: Mapping[str, str],
    fetch: Fetch,
    sessions: async_sessionmaker[AsyncSession],
    *,
    saved: Mapping[str, str],
    readers: Mapping[str, Reader] = READERS,
) -> Application:
    """What the first sync would write, computed exactly as the run computes it, writing nothing.

    The whole list is read, the roster checked against the saved choice by `roster_from`, and the
    members and the last applied run read from the tables the run reads. No statement here writes.
    """
    source = await read_source(guide, values, fetch, readers=readers)
    try:
        chosen: SelectableSource = selected_source(saved)
        roster = roster_from(source, chosen)
    except (StaffSourceError, RosterUnavailableError, ValueError) as refused:
        raise ConnectRefusedError(_words(str(refused))) from refused
    read = getattr(source, "reading", None)
    stable_ids: Mapping[str, str] = {}
    aliases: Mapping[str, tuple[str, ...]] = {}
    if callable(read):
        reading = read()
        stable_ids, aliases = reading.stable_ids, reading.aliases
    async with sessions() as session, session.begin():
        members = await read_members(session, chosen.name)
        last_applied = await read_last_applied(session, chosen.name)
    return application_for(
        roster,
        stable_ids=stable_ids,
        aliases=aliases,
        members=members,
        last_applied=last_applied,
    )


async def run_first_sync(
    guide: Guide,
    values: Mapping[str, str],
    fetch: Fetch,
    sessions: async_sessionmaker[AsyncSession],
    *,
    saved: Mapping[str, str],
    now: datetime,
    clock: Callable[[], datetime],
    readers: Mapping[str, Reader] = READERS,
) -> StaffSyncRun:
    """Apply the first sync: the nightly run, now, reading with the typed credential."""
    credential = checked_credential(guide, values)
    return await sync_staff_on(
        sessions=sessions,
        now=now,
        env={},
        keys=TypedKeys(credential),
        fetch=fetch,
        clock=clock,
        readers=readers,
        saved=saved,
    )
