"""The authentication guide, held to what the wizard, the appointment and a binding actually do.

`docs/install/authentication.md` said the first administrator "is created with a role grant and
no capability grants at all" after 5cdf984 made it false, and it said a Google Sheet
and LDAP are "added afterwards from the console" when no route in this application writes a staff
source. Nothing read the page, so nothing noticed. **Delete this file and the page goes back to
being prose that agrees with itself**: a capability added to the appointment, a source added to
the wizard's screen or a heading added to the spreadsheet reader changes what an installer is
told by nothing at all.

**Every expectation here is the code's behaviour or value, never a constant compared with
itself.** The staff sources the wizard offers are the ones its own screen accepts when answered,
through `problems_with`, and what each writes is read off `settings_from` after `answer`; whether
a source is signed in to is asked of `brain.setup_staff_routes.source_for` with a stand-in
directory; the grant a binding writes is the insert `member_grant` builds, compiled, and the
binding is held to executing that insert by its call expression; the spreadsheet headings are read
by the adapter. The appointment's capabilities are compared with `GRANTED_AT_APPOINTMENT`, whose
value is the code's; that `appoint` writes exactly that set is
`tests/unit/test_first_administrator.py`'s database test, which runs in CI.

**Every table is found by its marker and parsed, and nothing asserts on a sentence.** The one
exception is the stale claim, whose absence can only be asserted on the page's words, and that
check is exercised against the sentence the page used to carry, wrapped across a line as a
markdown page wraps anything.

The parsing is `brain.ops.install_docs.table_after`, which refuses a missing marker and a table
with no rows, so a guide that loses a table fails here rather than reporting nothing to compare.

Task ids: M42.2.7, M42.5.7
"""

from __future__ import annotations

import ast
import asyncio
import re
import uuid
from collections.abc import Collection, Sequence
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.audit.ledger import SUBJECT_KINDS
from brain.connectors.staff_directories import (
    LARK_PLATFORMS,
    Answer,
    DirectorySignInError,
    Outbound,
    location_problem,
)
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import RUNG_AUTHORITY
from brain.core.scope import Scope
from brain.identity.first_administrator import (
    ADMINISTRATION,
    GOVERNANCE,
    GRANTED_AT_APPOINTMENT,
    OVERSIGHT,
)
from brain.identity.sign_in_binding import member_grant
from brain.identity.staff_adapters import (
    ADDRESS_COLUMNS,
    DEPARTED_COLUMNS,
    DEPARTMENT_COLUMNS,
    GROUP_COLUMNS,
    LARK,
    NAME_COLUMNS,
    SpreadsheetSource,
)
from brain.identity.staff_source import StaffRecord, selectable_names
from brain.knowledge.visibility import Visibility
from brain.knowledge.visibility import scope_for as visibility_scope
from brain.locale import FieldError
from brain.ops.install_docs import bare, sections, table_after
from brain.setup_staff_routes import StaffTrialAsked, source_for
from brain.setup_wizard import StepId, answer, new_draft, problems_with, settings_from, step_for
from tests.unit.test_setup_wizard import INSIDE, SECRET, an_enrolment

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "docs" / "install" / "authentication.md"
BINDING_MODULE = REPO / "src" / "brain" / "identity" / "sign_in_binding.py"

GRANTED_MARKER = "<!-- checked: what the first administrator is granted at appointment -->"
WITHHELD_MARKER = "<!-- checked: what the first administrator is not granted at appointment -->"
BINDING_MARKER = "<!-- checked: what binding a sign-in grants -->"
OFFERED_MARKER = "<!-- checked: the staff sources the wizard offers -->"
NOT_OFFERED_MARKER = (
    "<!-- checked: the staff sources the product reads and the wizard does not offer -->"
)
HEADINGS_MARKER = "<!-- checked: the headings a spreadsheet is read by -->"

#: The section the capability table belongs in.
FIRST_ADMINISTRATOR_SECTION = "Your first administrator, and your second"

#: What the guide's "Granted for" cells say, and the group of the appointment each one names.
GROUPS = {
    "running the system": ADMINISTRATION,
    "letting the second person in": GOVERNANCE,
    "reading how the system is run": OVERSIGHT,
}

#: The ways of saying the first administrator holds no capability, as the page once did.
STALE_CLAIMS = ("no capability grants", "no grants at all")

#: A location the wizard accepts for a directory that is named by a domain. Reserved for private
#: use, so it names nobody's company.
A_DOMAIN = "company.internal"

#: The two ways the guide says the screen reads a list.
SIGNED_IN = "sign in, then read"
FROM_A_FILE = "from a CSV file you choose"

#: A PostgreSQL dialect to compile a statement against. Taken from an engine because the dialect's
#: own constructor is untyped and mypy runs strict here; creating the engine performs no I/O.
_DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

LOCATION = "staff_source_location"
LOCATION_NEEDED = FieldError(field=LOCATION, key="setup.error.location_needed")
LOCATION_NOT_WANTED = FieldError(field=LOCATION, key="setup.error.location_not_wanted")

PERSON = "u_bound_person"
BINDER = "u_binding_administrator"
ADDRESS = "a.person@company.internal"
NAME = "A Person"

CODE_SPAN = re.compile(r"`([^`]+)`")


# ------------------------------------------------------------------------------ reading
def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def spans(cell: str) -> tuple[str, ...]:
    """Every code span in one cell, in order."""
    return tuple(CODE_SPAN.findall(cell))


def first_cells(text: str, marker: str) -> list[str]:
    """The first cell of every row of the table after `marker`, with its code span removed."""
    return [bare(row[0]) for row in table_after(text, marker)]


def disagreement(stated: Sequence[str], actual: Collection[str], *, what: str) -> tuple[str, ...]:
    """Every name stated twice, stated and not in the code, and in the code and not stated."""
    found = [
        f"{one}: listed twice in {what}"
        for one in sorted({x for x in stated if stated.count(x) > 1})
    ]
    found += [
        f"{one}: the guide lists it in {what} and the code does not"
        for one in sorted(set(stated) - set(actual))
    ]
    found += [
        f"{one}: the code has it and the guide leaves it out of {what}"
        for one in sorted(set(actual) - set(stated))
    ]
    return tuple(found)


def stale_claims(text: str) -> tuple[str, ...]:
    """Every stale way of saying the first administrator holds nothing that the text still says.

    Whitespace is collapsed first, because a markdown page wraps a sentence wherever the line runs
    out, and a claim split across two lines is the same claim.
    """
    folded = " ".join(text.split()).casefold()
    return tuple(one for one in STALE_CLAIMS if one in folded)


def offered_by_the_wizard() -> set[str]:
    """Every source the product reads that the wizard's own screen accepts as an answer."""
    step = step_for(StepId.STAFF_SOURCE)
    return {
        name
        for name in selectable_names()
        if not any(
            one.field == "staff_source" for one in problems_with(step, {"staff_source": name})
        )
    }


def offered_rows(text: str) -> tuple[tuple[str, ...], ...]:
    return table_after(text, OFFERED_MARKER)


def needs_a_location(row: Sequence[str]) -> bool:
    """What the guide's "Where the list is" cell says, refusing a cell that says neither."""
    verdict = row[3].split(":", 1)[0].strip()
    assert verdict in {"needed", "refused"}, row
    return verdict == "needed"


def a_location_for(row: Sequence[str]) -> str:
    """A location the guide's own row offers, or a private domain when it names none."""
    if not needs_a_location(row):
        return ""
    named = spans(row[3])
    return named[0] if named else A_DOMAIN


def doctored(text: str, marker: str, drop: str, add: str) -> str:
    """The guide with one row of the table after `marker` removed and another added after it."""
    at = text.index(marker)
    head, tail = text[:at], text[at:]
    kept = [line for line in tail.splitlines() if f"`{drop}`" not in line]
    rule = next(index for index, line in enumerate(kept) if line.startswith("| ---"))
    kept.insert(rule + 1, add)
    return head + "\n".join(kept)


# ============================================================ the first administrator's grants
def test_the_guide_lists_exactly_the_capabilities_the_appointment_grants() -> None:
    """The positive case, and the reason this file exists. Delete this and a capability added to
    the appointment, or one taken out of it, leaves the page telling an installer the first
    administrator holds something they do not, or not naming a screen they can open."""
    stated = first_cells(guide(), GRANTED_MARKER)

    assert disagreement(stated, GRANTED_AT_APPOINTMENT, what="the appointment table") == ()


def test_a_capability_the_guide_leaves_out_or_adds_is_a_finding() -> None:
    """The check above against a page built to fail it, in both directions and for a repeat.
    Delete this and `disagreement` could return nothing for every input with the test above
    still green."""
    wrong = doctored(
        guide(),
        GRANTED_MARKER,
        drop="admin:sign_in",
        add="| `read:everything` | running the system |\n| `approve:grant` | running the system |",
    )

    assert disagreement(
        first_cells(wrong, GRANTED_MARKER), GRANTED_AT_APPOINTMENT, what="the appointment table"
    ) == (
        "approve:grant: listed twice in the appointment table",
        "read:everything: the guide lists it in the appointment table and the code does not",
        "admin:sign_in: the code has it and the guide leaves it out of the appointment table",
    )


def test_each_capability_is_listed_under_the_group_the_appointment_grants_it_for() -> None:
    """The three groups are what a reader uses the table for: running the system, letting the
    second person in, reading how it is run. Delete this and `approve:grant` could sit under
    reading, which is the one line a reader deciding whom to trust with the account reads."""
    rows = table_after(guide(), GRANTED_MARKER)

    assert {row[1] for row in rows} == set(GROUPS)
    for row in rows:
        assert bare(row[0]) in GROUPS[row[1]], row


def test_the_capabilities_the_guide_says_are_withheld_are_withheld_and_are_the_whole_list() -> None:
    """The withheld table says what the first administrator cannot do, and each line is a
    promise about the data. Held both ways: nothing in it is granted, and it is exactly the
    content plane, approving an action, and every audit kind the appointment does not grant.
    Delete this and the content plane can be added to the appointment with the page still saying
    Learning and Memory do not open, or an audit kind can be added to the ledger and withheld
    without the page saying so."""
    text = guide()
    withheld = first_cells(text, WITHHELD_MARKER)
    granted = set(GRANTED_AT_APPOINTMENT)
    audit_kinds_not_granted = {f"read:audit.{kind}" for kind in SUBJECT_KINDS} - granted

    assert not set(withheld) & granted
    assert (
        disagreement(
            withheld,
            {plane_capability(Plane.CONTENT).value, RUNG_AUTHORITY.value, *audit_kinds_not_granted},
            what="the withheld table",
        )
        == ()
    )


def test_the_guide_no_longer_says_the_first_administrator_holds_no_capability_grants() -> None:
    """The sentence 5cdf984 made false. Held two ways, because the absence of a phrase is weak on
    its own: no stale phrasing remains, and the capability table sits inside the first
    administrator's own section, so the page states what they hold where it discusses them.
    Delete this and the old sentence can come back in a merge beside the table that contradicts
    it."""
    text = guide()
    found = [body for title, body in sections(text) if title == FIRST_ADMINISTRATOR_SECTION]

    assert stale_claims(text) == ()
    assert len(found) == 1, (
        f"the guide has {len(found)} sections titled {FIRST_ADMINISTRATOR_SECTION!r}"
    )
    assert GRANTED_MARKER in found[0]
    assert WITHHELD_MARKER in found[0]


def test_the_sentence_the_guide_carried_before_is_found_even_across_a_line_break() -> None:
    """The positive case for the check above, against the page's own former wording wrapped across
    a line, and a sentence that says no such thing. Delete this and `stale_claims` could return
    nothing for every text, or everything."""
    before = (
        "first administrator is created with a role grant and no capability\n"
        "grants at all, and a Super Admin sees exactly what somebody wrote a grant for."
    )
    shorter = "the first administrator holds\nno grants at all"

    assert stale_claims(before) == ("no capability grants",)
    assert stale_claims(shorter) == ("no grants at all",)
    assert stale_claims("the first administrator is granted what the table lists") == ()


# ============================================================ what binding a sign-in grants
def test_the_grant_the_guide_says_a_binding_writes_is_the_insert_the_binding_builds() -> None:
    """The member grant 2f21276 added. The insert is compiled rather than run, so what is read is
    the row a binding writes: its capability, its scope and its author. Delete this and the grant
    can widen to the company, or be written under the person's own name, with the page still
    saying their own things and whoever bound them."""
    [(capability, over, granted_by)] = table_after(guide(), BINDING_MARKER)
    written = member_grant(uuid.UUID(int=7), PERSON, granted_by=BINDER).compile(dialect=_DIALECT)
    scope = Scope.model_validate(written.params["scope"])

    assert bare(capability) == written.params["capability"]
    assert written.params["principal_id"] == PERSON
    assert over == "their own things"
    assert scope == visibility_scope(Visibility.PERSONAL, owner_id=PERSON)
    assert not scope.is_unrestricted()
    assert granted_by == "whoever bound the sign-in"
    assert written.params["granted_by"] == BINDER


def test_a_binding_executes_the_member_grant_with_its_binder_as_the_author() -> None:
    """The test above holds what the insert writes, and this holds that a binding runs it, by the
    call expression in `SignInBindings.bind` rather than by a word a comment could supply. Delete
    this and the call can be removed or given another author with the table still agreeing with
    a statement nothing executes; the database test that proves it end to end skips without a
    server."""
    tree = ast.parse(BINDING_MODULE.read_text(encoding="utf-8"))
    [bindings] = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SignInBindings"
    ]
    [bind] = [
        node
        for node in bindings.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "bind"
    ]
    calls = [
        node
        for node in ast.walk(bind)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "member_grant"
    ]

    assert len(calls) == 1
    [author] = [one.value for one in calls[0].keywords if one.arg == "granted_by"]
    assert isinstance(author, ast.Name)
    assert author.id == "bound_by"
    assert [ast.unparse(one) for one in calls[0].args] == ["binding.id", "principal_id"]


# ======================================================================== the staff sources
def test_the_staff_sources_the_guide_says_the_wizard_offers_are_the_ones_its_screen_accepts() -> (
    None
):
    """The positive case. Delete this and a source added to or removed from the wizard's question
    leaves the page offering a choice the screen refuses, or hiding one it accepts."""
    stated = [bare(row[1]) for row in offered_rows(guide())]

    assert offered_by_the_wizard()
    assert disagreement(stated, offered_by_the_wizard(), what="the offered sources") == ()


def test_a_staff_source_the_guide_adds_or_leaves_out_is_a_finding() -> None:
    """The check above against a page built to fail it. Delete this and the comparison could be
    satisfied by any table at all."""
    wrong = doctored(
        guide(),
        OFFERED_MARKER,
        drop="lark",
        add="| LDAP | `ldap` | `ldap` | needed: the directory address | sign in, then read |",
    )
    stated = [bare(row[1]) for row in offered_rows(wrong)]

    assert disagreement(stated, offered_by_the_wizard(), what="the offered sources") == (
        "ldap: the guide lists it in the offered sources and the code does not",
        "lark: the code has it and the guide leaves it out of the offered sources",
    )


def test_the_sources_the_guide_says_are_not_offered_are_every_other_source_the_product_reads() -> (
    None
):
    """The page tells a reader that a Google Sheet, LDAP and no list exist and are not on the
    screen. Delete this and a source added to the product appears in neither table, or one the
    wizard starts offering is still described as missing from it."""
    text = guide()
    offered = [bare(row[1]) for row in offered_rows(text)]
    not_offered = [bare(row[1]) for row in table_after(text, NOT_OFFERED_MARKER)]

    assert not set(not_offered) & offered_by_the_wizard()
    assert (
        disagreement([*offered, *not_offered], selectable_names(), what="the two source tables")
        == ()
    )


def test_each_offered_source_writes_the_settings_the_guide_says_it_writes() -> None:
    """Each row is answered on the wizard's own screen and the settings the appointment would save
    are read back. Delete this and the brokered directory a choice derives, or whether a location
    is saved at all, can change with the page naming the old value."""
    for row in offered_rows(guide()):
        location = a_location_for(row)
        values = {"staff_source": bare(row[1]), LOCATION: location}
        draft, problems = answer(
            new_draft(),
            StepId.STAFF_SOURCE,
            values,
            an_enrolment(),
            SECRET,
            administrators=0,
            now=INSIDE,
        )
        written = settings_from(draft)

        assert problems == (), row
        assert written["INSTALL_STAFF_SOURCE"] == bare(row[1])
        assert written["INSTALL_BROKERED_DIRECTORY"] == bare(row[2])
        assert written.get("INSTALL_STAFF_SOURCE_LOCATION", "") == location


def test_a_location_is_needed_or_refused_for_each_source_exactly_as_the_guide_says() -> None:
    """Both halves of each verdict: the refusal the page promises, and the answer that is
    accepted. Delete this and a spreadsheet could start saving a location nothing reads, or a
    directory could be accepted pointed nowhere, with the page saying the opposite."""
    step = step_for(StepId.STAFF_SOURCE)
    for row in offered_rows(guide()):
        name = bare(row[1])
        if needs_a_location(row):
            assert problems_with(step, {"staff_source": name}) == (LOCATION_NEEDED,), row
            assert problems_with(step, {"staff_source": name, LOCATION: a_location_for(row)}) == ()
        else:
            assert problems_with(step, {"staff_source": name, LOCATION: A_DOMAIN}) == (
                LOCATION_NOT_WANTED,
            ), row
            assert problems_with(step, {"staff_source": name}) == ()


def test_the_lark_locations_the_guide_names_are_the_ones_a_lark_source_accepts() -> None:
    """A Lark location decides which host the client secret is sent to, so the two the page names
    are the whole of what may be typed. Delete this and a third platform can be accepted, or one
    of the two dropped, with the page naming the old pair."""
    [row] = [row for row in offered_rows(guide()) if bare(row[1]) == LARK]
    named = spans(row[3])

    assert disagreement(named, LARK_PLATFORMS, what="the Lark row") == ()
    for one in named:
        assert location_problem(LARK, one) == ""
    assert location_problem(LARK, A_DOMAIN) != ""


def test_a_source_the_guide_says_is_signed_in_to_is_read_only_through_a_sign_in() -> None:
    """Asked of the trial route's own source reader, with a stand-in directory. A source the page
    says is read from a file reads the file and contacts nobody, even with sign-in fields filled
    in; a source the page says is signed in to ignores a file, refuses without a secret before any
    request, and with one sends an authorisation code exchange first. Delete this and a directory
    could be read from a pasted file, or a spreadsheet could send somebody's secret somewhere, with
    the page describing neither."""
    sheet = f"Email,Name\n{ADDRESS},{NAME}\n"
    for row in offered_rows(guide()):
        how = row[4]
        assert how in {SIGNED_IN, FROM_A_FILE}, row
        sent: list[Outbound] = []

        async def directory(outbound: Outbound, sent: list[Outbound] = sent) -> Answer:
            sent.append(outbound)
            msg = "the stand-in directory stops here"
            raise DirectorySignInError(msg)

        def asked(client_secret: str, row: Sequence[str] = row) -> StaffTrialAsked:
            return StaffTrialAsked(
                setup_code=SECRET,
                staff_source=bare(row[1]),
                location=a_location_for(row),
                sheet=sheet,
                client_id="an-application",
                client_secret=client_secret,
                code="a-returned-code",
                verifier="v" * 43,
                redirect_uri="https://brain.company.internal/first-run/staff-list",
            )

        if how == FROM_A_FILE:
            source = asyncio.run(source_for(asked("a-client-secret"), directory))
            assert [one.work_address for one in source.roster().people] == [ADDRESS]
            assert sent == []
            continue

        with pytest.raises(DirectorySignInError):
            asyncio.run(source_for(asked(""), directory))
        assert sent == []
        with pytest.raises(DirectorySignInError, match="the stand-in directory stops here"):
            asyncio.run(source_for(asked("a-client-secret"), directory))
        [first] = sent
        carried = {**(first.form or {}), **(first.json_body or {})}
        assert carried["grant_type"] == "authorization_code"
        assert carried["code"] == "a-returned-code"


# ================================================================ the spreadsheet's headings
#: The guide's column names, and what reading a sheet under one of its headings must produce.
READ_UNDER: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    # column: (the other headings, the other cells, the cell under the heading being tried)
    "Work address": (("Name",), (NAME,), ADDRESS),
    "Name": (("Email",), (ADDRESS,), NAME),
    "Department": (("Email", "Name"), (ADDRESS, NAME), "Operations"),
    "Groups, separated by commas": (("Email", "Name"), (ADDRESS, NAME), "approvers, auditors"),
    "Has left": (("Email", "Name"), (ADDRESS, NAME), "yes"),
}

#: The spellings the adapter holds for each column, to hold the page to the whole list.
SPELLINGS = {
    "Work address": ADDRESS_COLUMNS,
    "Name": NAME_COLUMNS,
    "Department": DEPARTMENT_COLUMNS,
    "Groups, separated by commas": GROUP_COLUMNS,
    "Has left": DEPARTED_COLUMNS,
}


def read_as(column: str, record: StaffRecord) -> object:
    """The field of a record a column fills, in the shape the page's example cell produces."""
    return {
        "Work address": record.work_address,
        "Name": record.display_name,
        "Department": record.department,
        "Groups, separated by commas": ", ".join(record.groups),
        "Has left": "yes" if not record.active else "no",
    }[column]


def test_every_spreadsheet_heading_the_guide_names_is_read_and_none_is_left_out() -> None:
    """A person preparing a CSV reads this table and names their columns after it. Each heading
    is tried by reading a one-person sheet through the adapter, and the list is held to the
    adapter's own spellings so a heading the reader gains is a heading the page names. Delete this
    and a sheet built from the page can be read as nobody, with the check telling the person only
    that their list names nobody."""
    rows = table_after(guide(), HEADINGS_MARKER)

    assert {row[0] for row in rows} == set(READ_UNDER)
    for column, headings in rows:
        named = spans(headings)
        assert (
            disagreement([one.strip().casefold() for one in named], SPELLINGS[column], what=column)
            == ()
        )
        others, cells, value = READ_UNDER[column]
        for heading in named:
            [person] = SpreadsheetSource(rows=((*others, heading), (*cells, value))).roster().people
            assert read_as(column, person) == value, (column, heading)
