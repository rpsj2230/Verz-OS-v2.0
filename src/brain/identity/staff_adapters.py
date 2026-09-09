"""The six things a client already keeps their staff list in, read without a vendor SDK.

`brain.identity.staff_source` decides what a roster source is and what each kind may assert.
This file is the other half: the payloads those sources actually answer with, and the parse
from each of them to a `Roster`. It adds no rule that module does not already have, and where
it looks like it is deciding something the decision is being read out of `trust_for`.

**An adapter is a parser plus a declared trust, and it owns no transport.** There is no
Google client library here, no `msal`, no `lark-oapi` and no `ldap3`, and adding one would be
the wrong trade twice over. It would put four vendor SDKs, their transitive dependencies and
their release schedules into a single-tenant product that a client hosts and rarely upgrades;
and it would make every one of these adapters untestable except against a live tenant, which
is the position `brain.connectors` deliberately refused when it put the transport behind a
callable and tested the parse against recorded payloads instead. So each adapter takes the
pages a caller has already fetched, by whatever means that caller likes, and turns them into
records. Nothing here opens a socket, and `tests/fixtures/roster_payloads.py` is what they
are parsed against.

**The parser reads and the trust decides, and those are two different layers on purpose.**
An adapter carries whatever the payload said into `StaffRecord`, including a department a
source may not assert. It is `Roster.asserts` that governs what may be read back out, and
`departments_from` and `assertions_from` are where that happens. Filtering here as well
would be a second implementation of the trust rule, and the two would drift the day somebody
raises an installation's trust and finds the department already thrown away by a parse that
ran before the configuration was read. See `THE_PARSER_READS_AND_THE_TRUST_DECIDES`.

**Completeness is read off the payload and a caller cannot declare it.** Every adapter here
derives `complete` from what the source said: a `nextPageToken`, an `@odata.nextLink`, a
`has_more`, an LDAP result code, a range that came back full. There is no argument anywhere
in this file that lets a caller promise on a source's behalf, because that promise is what
decides whether anybody may be removed, and a caller in a hurry is exactly who would make it.
Where a payload has no way to say, the answer is no: **a hand-kept spreadsheet is never
complete**, not because its rows are suspect but because a file that has been filtered before
export is byte-for-byte identical to a company that has shrunk. See
`A_SOURCE_THAT_CANNOT_SAY_IT_IS_COMPLETE_IS_NOT`, and note that this leaves the spreadsheet
installation able to remove somebody only by saying so in the sheet, which is
`StaffRecord.active` and is the escape hatch the design already has.

**A refusal is raised and a truncation is recorded.** Lark answers a permission failure with
HTTP 200 and a non-zero `code`, which a parser reading `data.items` records as a company with
no staff; an LDAP server answers a search its own limit truncated with results and a result
code. The first is the source declining to answer and there is no roster to build, so it
raises. The second is a real partial answer, so it is a roster marked incomplete. Collapsing
them either way is wrong: raising on a truncation throws away the people who were returned,
and recording a refusal as an incomplete roster of nobody is how a directory outage becomes
a quiet zero.

**Each adapter pins its own source string and none of them takes one.** `trust_for` answers
`LEAST_TRUST` for a name it does not recognise, which is right for a client's own export
script and is a silent demotion for a vendor adapter: `"google-workspace"` with a hyphen is
a Workspace connector that has quietly stopped asserting departments and roles, with nothing
anywhere reporting it. So the strings are constants, they are checked against `DEFAULT_TRUST`
rather than against themselves, and a caller who wants a different trust changes the trust
rather than the name. See `A_SOURCE_STRING_THAT_MATCHES_NOTHING_IS_A_SILENT_DEMOTION`.

**Those strings are also what a client's install chooses by name**, which makes them a third
thing to keep in step: `staff_source.SELECTABLE` is the set an install may pick from and
`ADAPTER_SOURCES` is the set this file can parse. `choices_and_adapters_that_do_not_match`
reports both directions, because they fail differently. A parser nothing can choose is dead
code wearing a docstring that says otherwise; a choice nothing parses is offered on a setup
screen, picked, and then has nothing to read the list with, on the client's server rather than
here.

**`RosterReading` is not a second protocol method.** `StaffSource` has exactly one method and
must keep having exactly one, for the reason `A_SPREADSHEET_CANNOT_BE_AUTHENTICATED_AGAINST`
gives. `roster()` is that method and every adapter here satisfies it. `reading()` is more of
the same answer for the person wiring the source up rather than for the person consuming it:
the identifiers the source uses, the other addresses it says belong to somebody, and the rows
it carried that are not people. A consumer holding a `StaffSource` never sees it, and nothing
in it is a credential or can be used to authenticate anybody.

Rejected: making the source string a constructor argument so that two Workspace tenants could
be reconciled separately. Two tenants of one vendor is a real configuration and this does not
support it, because supporting it means keying the trust table on something other than the
vendor's name and that is a change to `staff_source`, not to this file. Today both tenants
would reconcile against each other's rows under one source name, and `source_gaps` would not
say so.

Task ids: M1.6.4, M1.6.5, M1.6.6
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from brain.identity.staff_source import (
    DEFAULT_TRUST,
    SELECTABLE,
    Asserts,
    Roster,
    StaffRecord,
    trust_for,
)

# ------------------------------------------------------------------ written-down reasons
#: Why an adapter carries a field its source is not trusted to assert.
THE_PARSER_READS_AND_THE_TRUST_DECIDES: Final = (
    "An adapter turns a payload into records and `Roster.asserts` governs what may be read "
    "back out of them. Dropping a department at parse time as well would be a second "
    "implementation of the same rule, and the two would disagree the day an installation "
    "raises a source's trust: the configuration would say the department may be read and the "
    "roster would already have thrown it away, with nothing saying which layer decided. One "
    "rule, one place, and the place is the one a reviewer already reads."
)

#: Why a payload with no truncation signal is not evidence of completeness.
A_SOURCE_THAT_CANNOT_SAY_IT_IS_COMPLETE_IS_NOT: Final = (
    "Completeness is a promise that this is every person, and only the source can make it. A "
    "paged API says so by running out of pages and a directory says so by returning success "
    "rather than a size limit. A file says nothing at all: an export somebody took with a "
    "filter applied is byte-for-byte a company that has shrunk, and there is no field to "
    "check. Treating the absence of a truncation signal as a promise is how a filtered "
    "export becomes a mass revocation, so the absence of evidence is read as no."
)

#: Why a vendor's non-zero code inside a success is raised and a truncation is not.
A_REFUSAL_IS_RAISED_AND_A_TRUNCATION_IS_RECORDED: Final = (
    "A source declining to answer and a source answering partly are different facts and they "
    "arrive looking alike. Lark refuses with HTTP 200 and a non-zero body code, which reads "
    "as an empty list; an LDAP server truncates at its own limit and returns real people "
    "with a result code beside them. Raising on the first is right because there is no "
    "roster; raising on the second would throw away the people who came back. Recording the "
    "first as an incomplete roster of nobody would turn an outage into a quiet zero."
)

#: Why each adapter pins its source string instead of accepting one.
A_SOURCE_STRING_THAT_MATCHES_NOTHING_IS_A_SILENT_DEMOTION: Final = (
    "`trust_for` answers LEAST_TRUST for a name it does not recognise, which is the right "
    "answer for a client's own export script and the wrong one for a vendor adapter. A "
    "Workspace source string spelled with a hyphen is a directory that has quietly stopped "
    "asserting departments and roles: nothing raises, nothing warns, and the first symptom "
    "is a role that stops being conferred. So the strings are constants here, and they are "
    "asserted against the keys of DEFAULT_TRUST rather than against themselves."
)

#: Why the identifier is the vendor's stable one and never the address or the path.
THE_ADDRESS_IS_THE_JOIN_AND_IS_NOT_THE_IDENTITY: Final = (
    "A work address is what joins a roster entry to a sign-in identity and it is not what "
    "makes somebody the same person as yesterday: it changes when they marry and when the "
    "company rebrands its domain. Every directory here carries something that does not, and "
    "it is never the obvious field. Lark's `open_id` is per application, so reinstalling the "
    "app renames everybody; Active Directory's distinguished name changes when somebody "
    "moves organisational unit. `union_id` and `objectGUID` are the stable ones, and a "
    "source with nothing stable at all says so by carrying no identifiers."
)

#: The source strings, which must be keys of `DEFAULT_TRUST` or the trust silently falls to
#: existence alone. Asserted against that table rather than against themselves.
SPREADSHEET: Final = "spreadsheet"
GOOGLE_SHEET: Final = "google_sheet"
GOOGLE_WORKSPACE: Final = "google_workspace"
MICROSOFT_ENTRA: Final = "microsoft_entra"
LARK: Final = "lark"
LDAP: Final = "ldap"

#: Every source string this file pins, for the check that each one is a name the trust table
#: knows. A tuple rather than a set derived at import, so the day somebody adds an adapter and
#: forgets to add it here the omission is visible in a diff.
ADAPTER_SOURCES: Final[tuple[str, ...]] = (
    SPREADSHEET,
    GOOGLE_SHEET,
    GOOGLE_WORKSPACE,
    MICROSOFT_ENTRA,
    LARK,
    LDAP,
)

#: The Lark body code that means the call succeeded. Every other value is a refusal arriving
#: inside an HTTP 200. Named rather than compared to a literal, because `code == 0` reads as
#: an error check and is the opposite one.
LARK_SUCCESS_CODE: Final = 0

#: The LDAP result code for a search the server's own administrative limit cut short. It is
#: a partial answer rather than a failure: the entries returned are real.
LDAP_SIZE_LIMIT_EXCEEDED: Final = 4

#: The LDAP result code for an ordinary success.
LDAP_SUCCESS: Final = 0

#: The Active Directory `userAccountControl` bit that means the account is disabled. A bit
#: rather than a value: 512 is enabled, 514 is disabled, 66048 is enabled with a
#: non-expiring password, and comparing the whole number to 512 marks most of an estate gone.
ACCOUNT_DISABLE_BIT: Final = 0x2

#: A bounded A1 range, so the row capacity of a Sheets read can be compared with what came
#: back. An unbounded range (`Staff!A:E`) matches nothing here and is read as the whole sheet,
#: which is what it is.
_BOUNDED_RANGE_RE: Final = re.compile(r"(?:^|!)[A-Z]+(\d+):[A-Z]+(\d+)$")


class RosterUnavailableError(Exception):
    """The source declined to answer, so there is no roster to build.

    Distinct from an empty roster, which is a source saying there is nobody, and from an
    incomplete one, which is a source saying it answered partly. Both of those are rosters.
    """


@dataclass(frozen=True)
class RosterReading:
    """One adapter's whole answer: the roster, and what a `Roster` has nowhere to put.

    `StaffSource` is one method and stays one method. This is not part of it. A consumer that
    holds a source and calls `roster()` never sees any of this; it is for the sync that has to
    decide what a changed address means and for the person wiring the source up, and it
    carries no credential and nothing that could authenticate anybody.
    """

    roster: Roster
    #: Casefolded work address to the identifier this source uses for that person, for the
    #: sources that have a stable one. Empty for a spreadsheet, which has nothing.
    stable_ids: Mapping[str, str] = field(default_factory=dict)
    #: Casefolded work address to the other addresses the source says are also theirs. This
    #: is where a rename leaves its evidence: Workspace keeps the old address as an alias and
    #: Entra keeps it as a lower-case `smtp:` proxy address, so an address that appears here
    #: is one the source is still holding rather than one it could hand to somebody else.
    aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: What the payload carried that did not become part of the roster, and why. Meeting
    #: rooms, service accounts, referrals and rows with nothing to join on. Named rather than
    #: counted, because an operator reading "four rows skipped" cannot act on it.
    dropped: tuple[str, ...] = ()


def _assemble(
    source: str,
    people: Sequence[StaffRecord],
    *,
    complete: bool,
    configured: frozenset[Asserts] | None,
    stable_ids: Mapping[str, str],
    aliases: Mapping[str, tuple[str, ...]],
    dropped: Sequence[str],
) -> RosterReading:
    """Build the reading. The one place a `Roster` is constructed in this file.

    `Roster.__post_init__` refuses a source that lists one person twice and that refusal is
    not softened here. Which of two rows for one person survives a de-duplication decides
    what department they are in and which groups they hold, and neither row is more true than
    the other, so the honest answer is that the source is wrong and somebody has to fix it.
    """
    return RosterReading(
        roster=Roster(
            source=source,
            people=tuple(people),
            complete=complete,
            asserts=trust_for(source, configured),
        ),
        stable_ids=dict(stable_ids),
        aliases=dict(aliases),
        dropped=tuple(dropped),
    )


def _record(
    address: str,
    name: str,
    *,
    department: str = "",
    groups: tuple[str, ...] = (),
    active: bool = True,
) -> StaffRecord | str:
    """A record, or the reason this row is not one.

    Returned rather than raised, because the rows that fail here are meeting rooms, shared
    mailboxes and service accounts, and a directory has them. Refusing the whole parse
    because a customer owns a meeting room would leave that installation unable to sync at
    all, and the alternative to a skip is not a better roster but no roster.
    """
    try:
        return StaffRecord(
            work_address=address.strip(),
            display_name=name.strip(),
            department=department.strip(),
            groups=groups,
            active=active,
        )
    except ValueError as why:
        label = address.strip() or name.strip() or "a row with neither an address nor a name"
        return f"{label}: {why}"


# ------------------------------------------------------------------------- tabular sources
def _header_index(header: Sequence[str]) -> dict[str, int]:
    """Column name to position, folded and stripped.

    `Work Email` and ` department ` are what people type into a spreadsheet, and an exact
    lookup finds neither. Folding here rather than asking the installation to rename its
    columns, because the installation will not.
    """
    return {name.strip().casefold(): at for at, name in enumerate(header) if name.strip()}


def _cell(row: Sequence[str], columns: Mapping[str, int], name: str) -> str:
    """One cell, or empty when the row is shorter than the header.

    A row shorter than its header is the ordinary state of both a hand-edited CSV and a
    Sheets response, because trailing empty cells are omitted rather than padded. Indexing
    without this check raises on the CSV and reads the wrong column on nothing, which is the
    quieter failure and the reason this returns rather than raises.
    """
    at = columns.get(name)
    if at is None or at >= len(row):
        return ""
    return row[at].strip()


#: What the address, name, department, group and departure columns may be called. Several
#: spellings each, because a client's sheet is a client's sheet and the cost of guessing
#: wrong is a roster of nobody.
ADDRESS_COLUMNS: Final[tuple[str, ...]] = ("work email", "email", "email address", "work address")
NAME_COLUMNS: Final[tuple[str, ...]] = ("full name", "name", "display name")
DEPARTMENT_COLUMNS: Final[tuple[str, ...]] = ("department", "dept", "team")
GROUP_COLUMNS: Final[tuple[str, ...]] = ("groups", "group")
DEPARTED_COLUMNS: Final[tuple[str, ...]] = ("left?", "left", "departed", "inactive")

#: What a departure column has to say for somebody to be marked as having left. Anything else,
#: including an empty cell, means they are here: a truthiness test would make the word "no"
#: mean gone, since a non-empty string is truthy.
DEPARTED_VALUES: Final[frozenset[str]] = frozenset({"yes", "y", "true", "1", "left", "departed"})


def _first_present(columns: Mapping[str, int], names: Sequence[str]) -> str:
    """The first of several spellings this sheet actually uses, or the first as a fallback."""
    for name in names:
        if name in columns:
            return name
    return names[0]


def _tabular_people(rows: Sequence[Sequence[str]]) -> tuple[list[StaffRecord], list[str]]:
    """Rows under a header, as records, with the rows that are not people and why.

    Shared by both tabular adapters because a Google Sheet read as values and a CSV somebody
    exported are the same thing once the transport is gone, and writing the column handling
    twice would give an installation two different answers about what its address column is
    called depending on which of the two it configured.
    """
    if not rows:
        return [], []
    columns = _header_index(rows[0])
    address_at = _first_present(columns, ADDRESS_COLUMNS)
    name_at = _first_present(columns, NAME_COLUMNS)
    department_at = _first_present(columns, DEPARTMENT_COLUMNS)
    group_at = _first_present(columns, GROUP_COLUMNS)
    departed_at = _first_present(columns, DEPARTED_COLUMNS)

    people: list[StaffRecord] = []
    dropped: list[str] = []
    for at, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            # A blank trailing row, which every hand-exported sheet has. Not reported: it is
            # not a person the source failed to describe, it is the end of the file.
            continue
        groups = tuple(
            one.strip() for one in _cell(row, columns, group_at).split(",") if one.strip()
        )
        built = _record(
            _cell(row, columns, address_at),
            _cell(row, columns, name_at),
            department=_cell(row, columns, department_at),
            groups=groups,
            active=_cell(row, columns, departed_at).casefold() not in DEPARTED_VALUES,
        )
        if isinstance(built, str):
            dropped.append(f"row {at}: {built}")
            continue
        people.append(built)
    return people, dropped


@dataclass(frozen=True)
class SpreadsheetSource:
    """A staff list somebody keeps by hand, read as a header row and rows of strings.

    **Existence only, and the reason is not that the data is bad.** A sheet anybody with the
    link can edit is a perfectly good answer to who works here and a catastrophic answer to
    who is an approver, because the edit that appoints somebody is one cell and its history
    is in a document nobody reviews. `A_SPREADSHEET_IS_A_ROSTER_AND_NEVER_AN_AUTHORITY` is
    that argument and this class does not restate it: the trust comes from `trust_for`, an
    installation whose sheet is locked to two people may raise it, and nothing here refuses a
    department column. It is carried into the record and `departments_from` declines to read
    it, which is `THE_PARSER_READS_AND_THE_TRUST_DECIDES`.

    **Never complete.** There is no field in a list of rows that could say whether the export
    was filtered, and the failure is silent and total: a sheet exported with a filter applied
    is indistinguishable from a company that has halved. An installation that needs a
    spreadsheet to remove somebody says so in the sheet, in a column this reads as
    `active=False`, which is the one removal a source may make without promising completeness.
    """

    rows: tuple[tuple[str, ...], ...]
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        people, dropped = _tabular_people(self.rows)
        return _assemble(
            SPREADSHEET,
            people,
            complete=False,
            configured=self.configured_trust,
            stable_ids={},
            aliases={},
            dropped=dropped,
        )


@dataclass(frozen=True)
class GoogleSheetSource:
    """A `spreadsheets.values.get` response, which is a spreadsheet that can say one thing.

    The one thing is its range, and it is the difference between this and the file above. The
    API returns every non-empty row inside the range it was asked for, so a read that did not
    fill its range read everything the sheet has to give within it; a read that came back with
    exactly as many rows as the range is tall may be the whole sheet or may be the first page
    of it, and the body cannot tell you which. So a full range is incomplete and a range with
    room left in it is complete, and an unbounded range (`Staff!A:E`) is the whole sheet.

    That is a narrow promise and it is worth having: it is the difference between an
    installation whose sheet can retire somebody and one whose sheet can only ever add.
    """

    payload: Mapping[str, Any]
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        values: Sequence[Sequence[str]] = self.payload.get("values") or []
        people, dropped = _tabular_people(values)
        return _assemble(
            GOOGLE_SHEET,
            people,
            complete=_range_had_room(str(self.payload.get("range", "")), len(values)),
            configured=self.configured_trust,
            stable_ids={},
            aliases={},
            dropped=dropped,
        )


def _range_had_room(a1: str, rows: int) -> bool:
    """Whether a Sheets read finished inside the range it asked for.

    An unbounded range is the whole sheet and is therefore complete. A bounded one is complete
    only when fewer rows came back than it could hold: a full range is a range that may have
    clipped, and there is nothing else in the response that would say so.
    """
    found = _BOUNDED_RANGE_RE.search(a1)
    if found is None:
        return bool(a1)
    first, last = int(found.group(1)), int(found.group(2))
    return rows < (last - first + 1)


# ------------------------------------------------------------------------- paged directories
def _members_by_address(group_members: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """Group to members, inverted to member to groups, casefolded on the address.

    Group membership is a second endpoint in both Google's and Microsoft's APIs rather than a
    field on the user, which is why every adapter here takes it as a separate argument. An
    installation that has not granted the group scope passes nothing and gets a roster with
    no groups in it, which is a roster that can place people and cannot appoint them.
    """
    found: dict[str, list[str]] = {}
    for group, members in group_members.items():
        for address in members:
            found.setdefault(address.strip().casefold(), []).append(group)
    return found


@dataclass(frozen=True)
class GoogleWorkspaceSource:
    """Admin SDK Directory `users.list` pages, plus the group memberships from a second walk.

    **Two fields mean gone and `archived` is the one that is missed.** A suspended user is
    obviously not working; an archived user appears in `users.list` looking exactly like
    everybody else and is a licence Google is no longer charging for. Reading only `suspended`
    leaves every archived leaver holding whatever they held.

    **`nextPageToken` on the last page handed over is the whole completeness answer.** A
    caller that read one page of a two-page company has a roster that parses perfectly and
    contains half the staff, and a roster trusted with completeness that contains half the
    staff removes the other half.

    **The organisational unit path is the department, minus its leading slash, and it is not
    flattened.** `/Engineering/Platform` is a different department from `/Engineering`, and
    collapsing them would put a sub-team inside its parent's scope, which is a widening.
    """

    pages: Sequence[Mapping[str, Any]]
    group_members: Mapping[str, Sequence[str]] = field(default_factory=dict)
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        groups_for = _members_by_address(self.group_members)
        people: list[StaffRecord] = []
        dropped: list[str] = []
        stable: dict[str, str] = {}
        aliases: dict[str, tuple[str, ...]] = {}
        for page in self.pages:
            for one in page.get("users") or []:
                address = str(one.get("primaryEmail") or "")
                folded = address.strip().casefold()
                built = _record(
                    address,
                    str((one.get("name") or {}).get("fullName") or ""),
                    # Stripped before the slash is removed, not after. An administrator who
                    # typed a trailing space into the console produces `"  /Engineering  "`,
                    # and `lstrip("/")` on that removes nothing at all, so the department
                    # keeps its leading slash and matches no scope.
                    department=str(one.get("orgUnitPath") or "").strip().lstrip("/"),
                    groups=tuple(groups_for.get(folded, ())),
                    active=not one.get("suspended", False) and not one.get("archived", False),
                )
                if isinstance(built, str):
                    dropped.append(built)
                    continue
                people.append(built)
                identifier = str(one.get("id") or "")
                if identifier:
                    stable[folded] = identifier
                known = tuple(str(alias).casefold() for alias in one.get("aliases") or ())
                if known:
                    aliases[folded] = known
        return _assemble(
            GOOGLE_WORKSPACE,
            people,
            complete=_finished(self.pages, "nextPageToken"),
            configured=self.configured_trust,
            stable_ids=stable,
            aliases=aliases,
            dropped=dropped,
        )


def _finished(pages: Sequence[Mapping[str, Any]], continuation: str) -> bool:
    """Whether the last page handed over said there was nothing after it.

    No pages at all is not a finished walk. It is a caller who fetched nothing, and answering
    complete for it would make an empty roster the strongest statement in the system.
    """
    if not pages:
        return False
    return not pages[-1].get(continuation)


@dataclass(frozen=True)
class MicrosoftEntraSource:
    """Microsoft Graph `/users` pages, plus group memberships from a second walk.

    **The join is `userPrincipalName` and never `mail`, and this is the field this adapter
    exists to get right.** The UPN is what somebody signs in with and therefore what Keycloak
    brokers and what the roster has to match; `mail` is what the outside world writes to, is
    routinely on a different domain after an acquisition, and is null for anybody without a
    mailbox. Joining on `mail` produces a roster full of people who match no principal, and
    the failure presents as a sync that runs cleanly and grants nothing.

    **A guest is in `/users` with everybody else.** Their UPN carries `#EXT#` and they are a
    supplier's employee with a foothold in this tenant. Listing them as staff hands somebody
    else's employee a principal here, so they are dropped and named rather than skipped
    quietly: an installation that genuinely wants its contractors in the roster should see
    that this is why they are missing.

    **`accountEnabled` is the whole of not-here.** Graph has no second field for it, unlike
    Workspace, and reading it is not optional: a disabled account whose roster entry says
    active keeps every role it held.
    """

    pages: Sequence[Mapping[str, Any]]
    group_members: Mapping[str, Sequence[str]] = field(default_factory=dict)
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        groups_for = _members_by_address(self.group_members)
        people: list[StaffRecord] = []
        dropped: list[str] = []
        stable: dict[str, str] = {}
        aliases: dict[str, tuple[str, ...]] = {}
        for page in self.pages:
            for one in page.get("value") or []:
                address = str(one.get("userPrincipalName") or "")
                folded = address.strip().casefold()
                if "#ext#" in folded:
                    dropped.append(
                        f"{address}: a guest account, which is somebody else's employee with "
                        "a foothold in this tenant rather than a member of this company"
                    )
                    continue
                built = _record(
                    address,
                    str(one.get("displayName") or ""),
                    department=str(one.get("department") or ""),
                    groups=tuple(groups_for.get(folded, ())),
                    active=bool(one.get("accountEnabled", False)),
                )
                if isinstance(built, str):
                    dropped.append(built)
                    continue
                people.append(built)
                identifier = str(one.get("id") or "")
                if identifier:
                    stable[folded] = identifier
                known = _proxy_addresses(one.get("proxyAddresses") or (), folded)
                if known:
                    aliases[folded] = known
        return _assemble(
            MICROSOFT_ENTRA,
            people,
            complete=_finished(self.pages, "@odata.nextLink"),
            configured=self.configured_trust,
            stable_ids=stable,
            aliases=aliases,
            dropped=dropped,
        )


#: How Entra spells an address it is holding but not sending from. The upper-case `SMTP:` is
#: the current one, and the difference between the two prefixes is the whole of the reading.
RETAINED_ADDRESS_PREFIX: Final = "smtp:"


def _proxy_addresses(declared: Sequence[Any], primary: str) -> tuple[str, ...]:
    """The other addresses Entra is holding for somebody, without the prefix.

    **The case of the four-letter prefix is the field.** Entra spells the current primary
    address `SMTP:` and every other one it retains `smtp:`, and a case-insensitive match
    reports the person's live mail address as a former one. That matters because this list is
    read as evidence that an old address is still held rather than free to be reissued, and
    an address somebody never had before is not evidence of anything.

    The primary is also removed by value, for a tenant that lists it in both spellings.
    """
    found: list[str] = []
    for entry in declared:
        text = str(entry)
        if not text.startswith(RETAINED_ADDRESS_PREFIX):
            continue
        address = text[len(RETAINED_ADDRESS_PREFIX) :].casefold()
        if address and address != primary and address not in found:
            found.append(address)
    return tuple(found)


@dataclass(frozen=True)
class LarkSource:
    """Lark contact pages, with the department names from a second call.

    **A non-zero `code` inside an HTTP 200 is a refusal and it raises here.** This is the one
    trap in this file that is recorded rather than reasoned: `LARK-200-code-permission` in
    the cassette corpus is a real Base call answering `{"code": 91403}` inside a 200, and the
    contact endpoints answer in the same envelope. A parser reading `data.items` past that
    records "app permission denied" as a company with nobody in it, which on a complete
    roster is every person in the company being removed at once.

    **`enterprise_email` is the work address and `email` is theirs.** The personal one is
    populated more often, which is what makes it the tempting field, and it joins to nothing.

    **Three status flags and none of them is `active`.** `is_frozen` is suspended,
    `is_resigned` is left, `is_activated` false is somebody who has never signed in. All
    three mean the person is not working here today.

    **A department identifier is not a department name.** `department_ids` are opaque `od-`
    strings, and passing one through creates a department that no scope predicate matches, so
    the person sees nothing with nothing anywhere saying why. Somebody in more than one known
    department is left unplaced rather than assigned the first: guessing which of two
    departments bounds a person's grants is guessing at their reach.

    **The identifier is `union_id` and not `open_id`.** An open id is issued per application,
    so reinstalling the app renames every person in the company at once and every rename
    would read as a departure and an arrival.
    """

    pages: Sequence[Mapping[str, Any]]
    department_names: Mapping[str, str] = field(default_factory=dict)
    group_members: Mapping[str, Sequence[str]] = field(default_factory=dict)
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        groups_for = _members_by_address(self.group_members)
        people: list[StaffRecord] = []
        dropped: list[str] = []
        stable: dict[str, str] = {}
        for page in self.pages:
            code = page.get("code", LARK_SUCCESS_CODE)
            if code != LARK_SUCCESS_CODE:
                msg = (
                    f"Lark answered {code} ({page.get('msg', 'no message')}) inside an HTTP "
                    "200, which is a refusal and not an empty company. There is no roster to "
                    "build from it, and building one would propose removing everybody"
                )
                raise RosterUnavailableError(msg)
            for one in (page.get("data") or {}).get("items") or []:
                address = str(one.get("enterprise_email") or "")
                folded = address.strip().casefold()
                status = one.get("status") or {}
                placed = [
                    self.department_names[at]
                    for at in one.get("department_ids") or ()
                    if at in self.department_names
                ]
                if len(placed) > 1:
                    dropped.append(
                        f"{address}: placed in {sorted(placed)}, so no one department bounds "
                        "them and this reading places them nowhere rather than guessing"
                    )
                built = _record(
                    address,
                    str(one.get("name") or ""),
                    department=placed[0] if len(placed) == 1 else "",
                    groups=tuple(groups_for.get(folded, ())),
                    active=(
                        not status.get("is_frozen", False)
                        and not status.get("is_resigned", False)
                        and bool(status.get("is_activated", True))
                    ),
                )
                if isinstance(built, str):
                    dropped.append(built)
                    continue
                people.append(built)
                identifier = str(one.get("union_id") or "")
                if identifier:
                    stable[folded] = identifier
        return _assemble(
            LARK,
            people,
            complete=_lark_finished(self.pages),
            configured=self.configured_trust,
            stable_ids=stable,
            aliases={},
            dropped=dropped,
        )


def _lark_finished(pages: Sequence[Mapping[str, Any]]) -> bool:
    """Whether Lark's last page said there was no more. Nested under `data`, unlike the rest."""
    if not pages:
        return False
    return not (pages[-1].get("data") or {}).get("has_more", False)


# ---------------------------------------------------------------- LDAP and Active Directory
def _attribute(attributes: Mapping[str, Sequence[str]], name: str) -> str:
    """The first value of an attribute, looked up without regard to case.

    **Every LDAP attribute is a list**, whatever the schema says, so `attributes["mail"]` is
    `["ada@example.com"]` and using it as an address produces the string `['ada@...']`, which
    `StaffRecord` accepts because it contains an `@`. That record then matches no principal
    and nothing anywhere says why.

    **Attribute names are case-insensitive in the protocol and case-sensitive in a dict.** A
    server that answers `sAMAccountName` to a request for `samaccountname` is correct, and
    the lookup that misses returns nothing rather than raising.
    """
    wanted = name.casefold()
    for held, values in attributes.items():
        if held.casefold() == wanted and values:
            return str(values[0]).strip()
    return ""


def _attributes(attributes: Mapping[str, Sequence[str]], name: str) -> tuple[str, ...]:
    """Every value of an attribute, looked up without regard to case."""
    wanted = name.casefold()
    for held, values in attributes.items():
        if held.casefold() == wanted:
            return tuple(str(one).strip() for one in values if str(one).strip())
    return ()


def _still_employed(attributes: Mapping[str, Sequence[str]]) -> bool:
    """Whether Active Directory says this account is enabled, defaulting to yes.

    `userAccountControl` is a bit field and `ACCOUNTDISABLE` is 0x2. Plain LDAP has no such
    attribute at all, so an installation behind OpenLDAP has no way to say anybody has left
    and everybody reads as present. That is a real limitation of that deployment rather than
    a parsing failure, and defaulting to yes is the only safe direction: defaulting to no
    would have an OpenLDAP sync report the entire company as departed.
    """
    control = _attribute(attributes, "userAccountControl")
    if not control:
        return True
    try:
        return not int(control) & ACCOUNT_DISABLE_BIT
    except ValueError:
        return True


@dataclass(frozen=True)
class LdapSource:
    """Search results from an LDAP directory or Active Directory, and the server's own verdict.

    Entries are `(distinguished name, attributes)` pairs, which is what every client hands
    over, and `result_code` is what the server said about the search as a whole.

    **A referral is an entry with no distinguished name**, which Active Directory returns
    whenever a subtree crosses into another domain in the forest. It is not a person, and it
    is evidence: a search that was referred elsewhere did not cover everything it was asked
    about, so the answer is not complete.

    **`sizeLimitExceeded` is a truncation and not a failure.** Active Directory's default
    `MaxPageSize` is a thousand, so a company of twelve hundred whose client does not page
    gets a thousand people and a result code nobody read, and the remaining two hundred are
    absent from a roster that claimed to be the whole list. The entries that came back are
    real, so this is an incomplete roster rather than an error.

    **The identity is `objectGUID` or `entryUUID`, never the distinguished name.** Moving
    somebody between organisational units rewrites their DN, and a roster keyed on it would
    read a reorganisation as everybody leaving and an equal number of strangers arriving.

    **A group is its full distinguished name.** Matching a rule on the common name alone would
    make `CN=Approvers,OU=Groups` and `CN=Approvers,OU=Legacy` the same group, which is how a
    retired group goes on conferring a role.
    """

    entries: Sequence[tuple[str | None, Mapping[str, Sequence[str]]]]
    result_code: int = LDAP_SUCCESS
    configured_trust: frozenset[Asserts] | None = None

    def roster(self) -> Roster:
        return self.reading().roster

    def reading(self) -> RosterReading:
        if self.result_code not in (LDAP_SUCCESS, LDAP_SIZE_LIMIT_EXCEEDED):
            msg = (
                f"the directory answered result code {self.result_code}, which is neither "
                "success nor a size limit, so there is no roster to build. Treating it as an "
                "empty answer would propose removing everybody"
            )
            raise RosterUnavailableError(msg)

        people: list[StaffRecord] = []
        dropped: list[str] = []
        stable: dict[str, str] = {}
        referred = False
        for name, attributes in self.entries:
            if name is None:
                referred = True
                dropped.append(
                    "a continuation reference rather than an entry, so this search did not "
                    "cover everything it was asked about"
                )
                continue
            address = _attribute(attributes, "mail") or _attribute(attributes, "userPrincipalName")
            built = _record(
                address,
                _attribute(attributes, "displayName") or _attribute(attributes, "cn"),
                department=_attribute(attributes, "department") or _attribute(attributes, "ou"),
                groups=_attributes(attributes, "memberOf"),
                active=_still_employed(attributes),
            )
            if isinstance(built, str):
                dropped.append(f"{name}: {built}")
                continue
            people.append(built)
            identifier = _attribute(attributes, "objectGUID") or _attribute(attributes, "entryUUID")
            if identifier:
                stable[built.work_address.casefold()] = identifier
        return _assemble(
            LDAP,
            people,
            complete=self.result_code == LDAP_SUCCESS and not referred,
            configured=self.configured_trust,
            stable_ids=stable,
            aliases={},
            dropped=dropped,
        )


def source_strings_the_trust_table_does_not_know() -> tuple[str, ...]:
    """Every adapter source string that `DEFAULT_TRUST` has no entry for.

    A function rather than a test-only comprehension, so the check can also be run by an
    installation against its own configuration. The failure it names is silent by
    construction: `trust_for` answers `LEAST_TRUST` for an unrecognised name and never says
    it did, so a misspelled vendor string is a directory that has quietly stopped asserting
    departments and roles with nothing raised anywhere.
    """
    return tuple(one for one in ADAPTER_SOURCES if one not in DEFAULT_TRUST)


#: The staff sources an install may choose that this file is expected to have a parser for.
#:
#: Derived from `SELECTABLE` rather than written again, so the two cannot drift by one being
#: edited. The option that reads no list is not in it: `none` is the absence of a source and a
#: parser for it would be a parser for nothing.
CHOOSABLE_SOURCES: Final[tuple[str, ...]] = tuple(
    one.name for one in SELECTABLE if one.reads_a_list
)


def choices_and_adapters_that_do_not_match(
    parsed: Iterable[str] = ADAPTER_SOURCES,
    choosable: Iterable[str] = CHOOSABLE_SOURCES,
) -> tuple[str, ...]:
    """Where the list a client chooses from and the list this file can parse disagree.

    Two directions and they fail differently, which is why both are reported rather than one
    set difference. **A parser no install can choose is dead code that looks live**: it has
    tests, it appears in this module's docstring as one of the sources a client keeps their
    people in, and no setup screen will ever offer it. **A choice with no parser is worse**,
    because it is offered, chosen, and then there is nothing to read the list with, on the
    client's server rather than here.

    The same shape as `source_strings_the_trust_table_does_not_know` above and separate from it
    on purpose: that one is about a name the trust table has never heard of, which demotes
    silently, and this one is about a name nobody can pick or nobody can parse.

    Both lists are parameters defaulting to the real ones, for the reason
    `brain.ops.independence.independence_gaps` takes `extra_allowed`: a check whose findings
    nothing can reproduce is indistinguishable from one that returns nothing, and this one is
    expected to be empty on every run of this repository.
    """
    can_choose = set(choosable)
    can_parse = set(parsed)
    found = [
        f"{one!r} is parsed here and is not a staff source any install can choose"
        for one in sorted(can_parse - can_choose)
    ]
    found.extend(
        f"{one!r} can be chosen at install time and nothing here parses it"
        for one in sorted(can_choose - can_parse)
    )
    return tuple(found)
