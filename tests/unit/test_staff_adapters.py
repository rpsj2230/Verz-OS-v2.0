"""The six roster payload shapes, held to the traps that parse cleanly and answer wrongly.

Every adapter here is a parser plus a declared trust, and both halves are tested from the raw
payload rather than from a record somebody built. That distinction is the reason this file is
long: when a producer and a consumer sit either side of a value, a test that hands the
consumer a finished value has tested the consumer twice. So the department a rule reads, the
identifier a rename is recognised by and the completeness a removal depends on are all
asserted after a walk from the recorded body, never from a `StaffRecord` written here.

The traps are the point. A payload that fails to parse is one somebody fixes; the ones worth
tests are the ones that succeed and lie. A Sheets row shorter than its header, an LDAP
attribute that is a list of one, an Active Directory referral that is an entry with no
distinguished name, a Lark refusal inside an HTTP 200, an archived Workspace user who looks
exactly like everybody else. Each produces a roster that is confidently wrong, and a
confidently short roster from a source trusted with completeness is a mass revocation.

Task ids: M1.6.4, M1.6.5, M1.6.6
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brain.identity import staff_adapters
from brain.identity.roles import Role
from brain.identity.staff_adapters import (
    ACCOUNT_DISABLE_BIT,
    ADAPTER_SOURCES,
    CHOOSABLE_SOURCES,
    GOOGLE_SHEET,
    GOOGLE_WORKSPACE,
    LARK,
    LDAP,
    MICROSOFT_ENTRA,
    SPREADSHEET,
    GoogleSheetSource,
    GoogleWorkspaceSource,
    LarkSource,
    LdapSource,
    MicrosoftEntraSource,
    RosterUnavailableError,
    SpreadsheetSource,
    choices_and_adapters_that_do_not_match,
    source_strings_the_trust_table_does_not_know,
)
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    STAFF_SOURCE_SETTING,
    Asserts,
    GroupRule,
    Roster,
    StaffRecord,
    StaffSource,
    StaffSourceError,
    assertions_from,
    departments_from,
    selected_source,
    trust_for,
)
from tests.fixtures import roster_payloads as recorded


def every_adapter() -> dict[str, StaffSource]:
    """One of each, built from the recorded payloads, so a rule can be asked of all six.

    Annotated as `StaffSource` rather than as the concrete classes, which makes mypy check
    what no runtime assertion can: the protocol is not `runtime_checkable`, so `isinstance`
    would answer nothing, and this is the only place the conformance is proved. An adapter
    that stopped satisfying it fails the type gate here rather than at its first caller."""
    return {
        SPREADSHEET: SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT),
        GOOGLE_SHEET: GoogleSheetSource(payload=recorded.GOOGLE_SHEET_VALUES),
        GOOGLE_WORKSPACE: GoogleWorkspaceSource(
            pages=[
                recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE,
                recorded.GOOGLE_WORKSPACE_USERS_PAGE_TWO,
            ],
            group_members=recorded.GOOGLE_WORKSPACE_GROUP_MEMBERS,
        ),
        MICROSOFT_ENTRA: MicrosoftEntraSource(
            pages=[recorded.ENTRA_USERS_PAGE_ONE, recorded.ENTRA_USERS_PAGE_TWO],
            group_members=recorded.ENTRA_GROUP_MEMBERS,
        ),
        LARK: LarkSource(
            pages=[recorded.LARK_USERS_PAGE_ONE, recorded.LARK_USERS_PAGE_TWO],
            department_names=recorded.LARK_DEPARTMENT_NAMES,
            group_members=recorded.LARK_GROUP_MEMBERS,
        ),
        LDAP: LdapSource(entries=recorded.ACTIVE_DIRECTORY_ENTRIES),
    }


def workspace() -> GoogleWorkspaceSource:
    return GoogleWorkspaceSource(
        pages=[recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE, recorded.GOOGLE_WORKSPACE_USERS_PAGE_TWO],
        group_members=recorded.GOOGLE_WORKSPACE_GROUP_MEMBERS,
    )


def entra() -> MicrosoftEntraSource:
    return MicrosoftEntraSource(
        pages=[recorded.ENTRA_USERS_PAGE_ONE, recorded.ENTRA_USERS_PAGE_TWO],
        group_members=recorded.ENTRA_GROUP_MEMBERS,
    )


def lark() -> LarkSource:
    return LarkSource(
        pages=[recorded.LARK_USERS_PAGE_ONE, recorded.LARK_USERS_PAGE_TWO],
        department_names=recorded.LARK_DEPARTMENT_NAMES,
        group_members=recorded.LARK_GROUP_MEMBERS,
    )


def person_at(roster: Roster, address: str) -> StaffRecord:
    return next(one for one in roster.people if one.work_address == address)


# --- what each adapter is trusted with ------------------------------------------------------


def test_every_adapter_names_a_source_the_trust_table_already_knows() -> None:
    """**The silent failure this file exists to make loud.** `trust_for` answers `LEAST_TRUST`
    for a name it does not recognise, which is the right answer for a client's own export
    script and a quiet demotion for a vendor adapter: one hyphen in the Workspace source
    string and the connector has stopped asserting departments and roles, with nothing raised
    anywhere and the first symptom a role that no longer gets conferred.

    Asserted against the keys of `DEFAULT_TRUST` rather than against the constants themselves,
    because a constant compared with itself is green for every value it could hold. The
    resulting trust is compared to the table's entry for the same reason.

    The count is asserted because this is a loop that finds nothing when it reads nothing: a
    renamed adapter would empty it and leave a green test that examined no adapter at all.

    Delete this and a typo in a source string is a directory that has quietly stopped
    conferring roles."""
    built = every_adapter()

    assert source_strings_the_trust_table_does_not_know() == ()
    assert len(built) == len(ADAPTER_SOURCES) == 6

    for name, adapter in built.items():
        roster = adapter.roster()
        assert roster.source == name
        assert name in DEFAULT_TRUST, name
        assert roster.asserts == DEFAULT_TRUST[name], name


def test_a_source_string_the_trust_table_does_not_know_is_demoted_without_a_word() -> None:
    """The hazard the check above guards, shown rather than described. A misspelling is not an
    error and never will be: an unrecognised source has to fall to existence alone, because a
    client naming their own export script should not have to add a line to `staff_source`.

    Both halves matter. The correct spelling asserts roles, the near miss asserts nothing but
    existence, and neither raises. That is the whole shape of the failure: it is safe, it is
    silent, and it is indistinguishable from a source that was configured cautiously.

    Delete this and the check above looks like a formality rather than the only thing standing
    between a hyphen and a directory that stops conferring roles."""
    correct = trust_for(GOOGLE_WORKSPACE)
    near_miss = trust_for("google-workspace")

    assert Asserts.ROLE in correct
    assert Asserts.DEPARTMENT in correct
    assert Asserts.ROLE not in near_miss
    assert Asserts.DEPARTMENT not in near_miss
    assert Asserts.EXISTENCE in near_miss


def test_the_two_editable_sources_may_list_people_and_the_four_directories_may_place_them() -> None:
    """The division M1.6.4 draws against M1.6.5 and M1.6.6, asserted as one property rather
    than left implicit in six separate adapters.

    A sheet anybody with the link can edit is a fine answer to who works here and a
    catastrophic answer to who is an approver: the edit that appoints somebody is one cell,
    and its history is in a document nobody reviews. Changing a Workspace group, an Entra
    group or a directory group needs an admin console and leaves a trail in it.

    Delete this and an adapter can be added on the spreadsheet side of the line with the
    directory side's trust, which is the one mistake the whole module is shaped to prevent."""
    built = every_adapter()

    for name in (SPREADSHEET, GOOGLE_SHEET):
        asserts = built[name].roster().asserts
        assert asserts == frozenset({Asserts.EXISTENCE}), name

    for name in (GOOGLE_WORKSPACE, MICROSOFT_ENTRA, LARK, LDAP):
        asserts = built[name].roster().asserts
        assert Asserts.DEPARTMENT in asserts, name
        assert Asserts.ROLE in asserts, name


def test_a_spreadsheet_department_reaches_the_record_and_is_still_refused_by_the_trust() -> None:
    """**Which layer decides, asserted from both sides.** The parser carries the department
    column into the record and `departments_from` declines to read it. Filtering in the parser
    as well would be a second implementation of the trust rule, and the two would disagree the
    day an installation raises its sheet's trust and finds the column already thrown away by a
    parse that ran before the configuration was read.

    Delete this and somebody tidies the parse by dropping the column, the trust rule becomes
    unraisable, and nothing anywhere says why an installation that configured
    `Asserts.DEPARTMENT` still gets an empty map."""
    roster = SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT).roster()

    assert person_at(roster, "ada@example.com").department == "engineering"
    assert departments_from(roster) == {}


def test_an_installation_may_raise_a_sheets_trust_without_the_parser_changing() -> None:
    """The positive case for the layering above, and the reason the defaults are defaults.

    An installation whose sheet is locked to two named people may decide it can place them,
    and the only thing that has to change is the configured trust. If the parser had dropped
    the column there would be nothing for the raised trust to read.

    Delete this and the trust argument becomes one-directional: lowering works and raising
    silently does nothing."""
    raised = SpreadsheetSource(
        rows=recorded.SPREADSHEET_EXPORT,
        configured_trust=frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT}),
    ).roster()

    assert departments_from(raised)["ada@example.com"] == "engineering"


# --- the hand-kept spreadsheet, M1.6.4 -------------------------------------------------------


def test_a_spreadsheet_is_never_a_complete_list_however_many_rows_it_has() -> None:
    """**A file has no field that could say whether it was filtered before export.** An export
    somebody took with a filter applied is byte-for-byte a company that has halved, so the
    absence of a truncation signal is read as no rather than as a promise.

    The consequence is asserted through `may_remove` rather than through the flag, because
    that is the question the rest of the system asks: nobody may be removed on the strength of
    a spreadsheet.

    Delete this and a filtered export deprovisions everybody it filtered out, and the audit
    ledger records it as deliberate."""
    roster = SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT).roster()

    assert roster.people
    assert not roster.complete
    assert not roster.may_remove()


def test_a_spreadsheet_says_somebody_has_left_in_a_column_rather_than_by_omitting_them() -> None:
    """The escape hatch that makes the rule above liveable. A source that may never remove by
    omission can still say a person has left, and that is the one removal that needs no
    promise of completeness because it is a statement rather than a silence.

    The sibling is the whole test: everybody else is still here. Without it a parse that
    marked the entire sheet inactive would pass.

    Delete this and a spreadsheet installation has no way to retire anybody at all."""
    roster = SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT).roster()

    assert person_at(roster, "alan@example.com").active is False
    assert [one.work_address for one in roster.people if one.active] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    ]


def test_a_ragged_row_keeps_its_columns_and_a_blank_trailing_row_is_not_a_person() -> None:
    """Two shapes every hand-exported sheet has, and both parse into something wrong rather
    than raising.

    A row shorter than its header is what an editor leaves when the last cells were empty.
    Indexing past it raises on a CSV; padding it silently is fine; shifting the remaining
    columns to fill the gap is the failure, and it would put a group name in the department.
    A blank trailing row has no address, which `StaffRecord` refuses, so a parse that does not
    skip it fails the whole file for a row containing nothing.

    Delete this and one trailing newline in an export takes the entire staff list with it."""
    reading = SpreadsheetSource(rows=recorded.SPREADSHEET_EXPORT).reading()

    short = person_at(reading.roster, "katherine@example.com")
    assert short.department == "finance"
    assert short.groups == ()
    assert len(reading.roster.people) == 4
    assert reading.dropped == ()


def test_a_column_is_found_however_the_person_who_typed_it_spelled_it() -> None:
    """`Work Email` and ` Department ` with a stray space are what people type into a sheet,
    and an exact-match lookup finds neither. Folding here rather than asking an installation
    to rename its columns, because the installation will not.

    Delete this and a client's own sheet produces a roster of nobody, with no error, because
    every address cell resolved to the empty string."""
    rows = recorded.SPREADSHEET_EXPORT

    assert rows[0][0] == "Work Email"
    assert rows[0][2] == " Department "
    roster = SpreadsheetSource(rows=rows).roster()

    assert person_at(roster, "ada@example.com").department == "engineering"


def test_a_spreadsheet_that_lists_one_person_twice_is_refused_and_not_de_duplicated() -> None:
    """The adapter does not soften a refusal the governing module makes. Which of two rows for
    one person survives a de-duplication decides what department they are in and which groups
    they hold, and neither row is more true than the other.

    Case-folded, because a sheet two people edit gets one address in two capitalisations.

    Delete this and an adapter can quietly keep the last row it saw, and reconciliation becomes
    a function of row order."""
    with pytest.raises(ValueError, match="more than once"):
        SpreadsheetSource(rows=recorded.SPREADSHEET_WITH_A_REPEATED_PERSON).roster()


# --- the Google Sheet, M1.6.4 -----------------------------------------------------------------


def test_a_sheets_read_that_filled_its_range_is_not_known_to_be_the_whole_sheet() -> None:
    """**The one thing a Sheets response can say that a file cannot**, and it is the
    difference between an installation whose sheet can retire somebody and one whose sheet can
    only ever add.

    The API returns every non-empty row inside the range it was asked for. A read that came
    back with as many rows as the range is tall may be the whole sheet or may be the first
    page of it, and nothing else in the body distinguishes them. A read with room left in its
    range read everything there was.

    Both directions, because a rule that answered incomplete for every range would pass the
    first half alone and would make every Google Sheet unable to remove anybody.

    Delete this and a staff list that outgrew its range removes everybody past the last row."""
    roomy = GoogleSheetSource(payload=recorded.GOOGLE_SHEET_VALUES).roster()
    exactly_full = GoogleSheetSource(payload=recorded.GOOGLE_SHEET_VALUES_AT_THE_RANGE_LIMIT)

    assert recorded.GOOGLE_SHEET_VALUES["range"] == "Staff!A1:E1000"
    assert roomy.complete
    assert recorded.GOOGLE_SHEET_VALUES_AT_THE_RANGE_LIMIT["range"] == "Staff!A1:E5"
    assert len(recorded.GOOGLE_SHEET_VALUES_AT_THE_RANGE_LIMIT["values"]) == 5
    assert not exactly_full.roster().complete


def test_an_unbounded_sheets_range_is_the_whole_sheet() -> None:
    """`Staff!A:E` asks for every row in those columns, so there is no capacity to compare
    against and the answer is the sheet. Reading an unbounded range as incomplete would make
    the most natural configuration the one that can never remove anybody.

    Delete this and the range check turns into "complete only when I can parse the numbers",
    which is a rule about this parser rather than about the sheet."""
    whole = GoogleSheetSource(
        payload={"range": "Staff!A:E", "values": recorded.GOOGLE_SHEET_VALUES["values"]}
    ).roster()

    assert whole.complete


def test_a_sheets_row_shorter_than_its_header_reads_the_columns_it_does_have() -> None:
    """Sheets omits trailing empty cells rather than padding them, so a row is routinely
    narrower than its header. Grace's row stops after her department.

    Delete this and every person whose last columns are blank loses the columns before them,
    which is a department read out of a groups cell."""
    roster = GoogleSheetSource(payload=recorded.GOOGLE_SHEET_VALUES).roster()

    grace = person_at(roster, "grace@example.com")
    assert grace.department == "engineering"
    assert grace.groups == ()
    assert grace.active is True


# --- Google Workspace, M1.6.5 -------------------------------------------------------------


def test_a_workspace_page_still_carrying_a_continuation_is_not_a_complete_roster() -> None:
    """**The most expensive trap in this file.** A caller that read one page of a two-page
    company holds a roster that parses perfectly and contains half the staff. On a source
    trusted with completeness, half a company is a mass revocation of the other half.

    Both directions, because a rule that answered incomplete for everything would make a
    Workspace source unable to remove anybody and would pass the first half of this alone.

    Delete this and a paging bug is indistinguishable from a redundancy."""
    partial = GoogleWorkspaceSource(pages=[recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE])

    assert recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE["nextPageToken"]
    assert not partial.roster().complete
    assert workspace().roster().complete


def test_a_caller_that_fetched_no_pages_at_all_has_not_read_a_complete_roster() -> None:
    """Zero pages is a caller who fetched nothing, and answering complete for it would make an
    empty roster the strongest statement in the system: every person in the company absent
    from a source that promised the whole list.

    Delete this and a failed fetch that returns no pages proposes removing everybody."""
    nothing = GoogleWorkspaceSource(pages=[]).roster()

    assert nothing.people == ()
    assert not nothing.complete


def test_an_archived_workspace_user_is_as_gone_as_a_suspended_one() -> None:
    """Two fields and both mean the person is not working here. `archived` is the one that is
    missed: it is newer, and an archived user appears in `users.list` looking exactly like
    everybody else.

    The sibling is what stops a parse that marks everybody inactive from passing.

    Delete this and every archived leaver keeps whatever they held, indefinitely, because
    nothing in the sync ever notices them."""
    roster = workspace().roster()

    assert person_at(roster, "grace@example.com").active is False
    assert person_at(roster, "ada@example.com").active is True


def test_a_meeting_room_is_named_and_dropped_rather_than_failing_the_whole_company() -> None:
    """A Workspace customer's user list holds resources, shared mailboxes and service accounts,
    and this one has no `primaryEmail` at all. Refusing the parse for it would leave an
    installation with one meeting room unable to sync anybody.

    Named rather than counted, because an operator reading "one row skipped" cannot tell
    whether it was a room or a person whose address is missing.

    Delete this and either one meeting room breaks the sync or the rows that are people
    disappear as quietly as the rooms."""
    reading = workspace().reading()

    assert [one.work_address for one in reading.roster.people] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    ]
    assert any("Meeting Room 3" in one for one in reading.dropped), reading.dropped


def test_a_workspace_group_becomes_a_role_assertion_a_rule_can_match() -> None:
    """**M1.6.5 end to end, from the recorded body to the row reconciliation consumes.** The
    group walk is a second endpoint rather than a field on the user, the group is named by its
    own address, and the assertion carries that name because `source_group` is part of the
    identity of a grant rather than a detail hanging off it.

    Asserted as the whole `DirectoryAssertion` rather than as a count: an assertion with the
    wrong `source_group` reconciles as a different row, so a count would pass on a grant
    nobody intended.

    Delete this and the group side of a Workspace source can stop resolving with the roster
    still looking correct."""
    roster = workspace().roster()

    found = assertions_from(
        roster,
        [GroupRule(source_group="approvers@example.com", role=Role.APPROVER)],
        principal_for={"ada@example.com": "p_ada"},
    )

    assert [(one.principal_id, one.role, one.source_group) for one in found] == [
        ("p_ada", Role.APPROVER, "approvers@example.com")
    ]


def test_a_group_member_listed_in_another_capitalisation_is_still_a_member() -> None:
    """Group membership arrives from a second endpoint, and the address it returns is the one
    that endpoint happens to store rather than the one on the user record. Workspace and Graph
    both return them in whatever case they were typed in, so an exact match drops memberships
    for the half of a company whose addresses were entered with a capital.

    A dropped membership is a role that is never conferred, and it fails silently: the roster
    is complete, the person is in it, and the rule matches nobody.

    Delete this and a group rule works for whoever happened to be added in lower case."""
    shouted = GoogleWorkspaceSource(
        pages=[recorded.GOOGLE_WORKSPACE_USERS_PAGE_ONE],
        group_members={"approvers@example.com": ("ADA@Example.COM",)},
    ).roster()

    assert person_at(shouted, "ada@example.com").groups == ("approvers@example.com",)


def test_an_organisational_unit_path_becomes_a_department_without_being_flattened() -> None:
    """The leading slash goes because a department is a name rather than a path, and nothing
    else does: `/Engineering/Platform` is a different department from `/Engineering`, and
    collapsing them would put a sub-team inside its parent's scope, which is a widening.

    Delete this and a nested organisational unit sees everything its parent sees."""
    roster = workspace().roster()

    assert departments_from(roster) == {
        "ada@example.com": "Engineering",
        "grace@example.com": "Engineering",
        "katherine@example.com": "Finance",
    }
    assert (
        GoogleWorkspaceSource(
            pages=[
                {
                    "users": [
                        {
                            "id": "1",
                            "primaryEmail": "nested@example.com",
                            "name": {"fullName": "Nested Person"},
                            "orgUnitPath": "/Engineering/Platform",
                        }
                    ]
                }
            ]
        )
        .roster()
        .people[0]
        .department
        == "Engineering/Platform"
    )


# --- Microsoft Entra, M1.6.5 -----------------------------------------------------------------


def test_the_entra_join_is_the_user_principal_name_and_never_the_mail_attribute() -> None:
    """**The field this adapter exists to get right.** The user principal name is what
    somebody signs in with and therefore what the roster has to match; `mail` is what the
    outside world writes to, is routinely on another domain after an acquisition, and is null
    for anybody without a mailbox.

    Ada's two fields are deliberately different in the recording, so a parse that read `mail`
    would produce a roster that looks complete and matches no principal, which presents as a
    sync that runs cleanly and grants nothing.

    Delete this and the quietest possible misconfiguration ships."""
    roster = entra().roster()

    assert recorded.ENTRA_USERS_PAGE_ONE["value"][0]["mail"] == "ada.lovelace@example.co.uk"
    assert [one.work_address for one in roster.people] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    ]


def test_a_disabled_entra_account_is_not_active_and_an_enabled_one_is() -> None:
    """Graph has one field for this and no second one, unlike Workspace, so reading it is not
    optional: an account disabled in the tenant whose roster entry says active keeps every
    role it held.

    Delete this and disabling somebody in Entra does nothing here."""
    roster = entra().roster()

    assert person_at(roster, "grace@example.com").active is False
    assert person_at(roster, "katherine@example.com").active is True


def test_a_guest_account_is_not_a_member_of_this_company() -> None:
    """A guest is in `/users` with everybody else and their user principal name carries
    `#EXT#`. They are a supplier's employee with a foothold in this tenant, and listing them as
    staff hands somebody else's employee a principal here.

    Named in the dropped list rather than skipped quietly, so an installation that genuinely
    wants its contractors in the roster can see this is why they are missing.

    Delete this and every external collaborator in the tenant becomes staff."""
    reading = entra().reading()

    assert not any("#EXT#" in one.work_address for one in reading.roster.people)
    assert any("guest account" in one for one in reading.dropped), reading.dropped


def test_an_entra_page_carrying_a_next_link_is_not_a_complete_roster() -> None:
    """Graph's continuation is a whole URL under a different key from Google's, and a caller
    that stopped at one page holds two thirds of a company.

    Delete this and the Entra adapter's completeness answer is whatever the last page happened
    to contain."""
    partial = MicrosoftEntraSource(pages=[recorded.ENTRA_USERS_PAGE_ONE])

    assert recorded.ENTRA_USERS_PAGE_ONE["@odata.nextLink"]
    assert not partial.roster().complete
    assert entra().roster().complete


def test_only_the_lower_case_proxy_prefix_is_an_address_entra_is_still_holding() -> None:
    """Entra spells the current primary address `SMTP:` and every other one it retains
    `smtp:`, so the case of the four-letter prefix is the whole reading. Ada's upper-case
    entry is her live mail address on the acquired company's domain, which is not a former
    address of hers.

    That matters because this list is read as evidence that an old address is still held
    rather than free to be handed to somebody else, and an address she never had before is not
    evidence of anything.

    Delete this and a case-insensitive match reports somebody's live mail address as one they
    used to have."""
    reading = entra().reading()

    assert reading.aliases["ada@example.com"] == ("ada.l@example.com",)


# --- Lark, M1.6.5 -----------------------------------------------------------------------------


def test_a_lark_refusal_inside_a_success_is_raised_rather_than_read_as_an_empty_company() -> None:
    """**The trap this vendor is known for, and the only one in this file that is recorded
    rather than reasoned.** `LARK-200-code-permission` in the cassette corpus is a real call
    answering `{"code": 91403}` inside an HTTP 200, and the contact endpoints use the same
    envelope. A parser that checks the status and reads `data.items` records "app permission
    denied" as a company with nobody in it.

    Raised rather than returned as an empty incomplete roster, because an empty roster is a
    statement and there is nothing here to state. The sibling proves an ordinary page still
    parses, without which a parser that raised on everything would pass.

    Delete this and the ordinary state of a Lark app on the day it is installed, before
    anybody approves its scope, is a proposal to remove every person in the company."""
    with pytest.raises(RosterUnavailableError, match="99991663"):
        LarkSource(pages=[recorded.LARK_USERS_REFUSED]).roster()

    assert len(lark().roster().people) == 3


def test_the_lark_work_address_is_the_enterprise_email_and_not_the_personal_one() -> None:
    """`email` is the person's own address and `enterprise_email` is the work one. The
    personal field is populated more often, which is what makes it the tempting one, and it
    joins to nothing this system knows.

    Delete this and a Lark roster is a list of personal mailboxes that matches no principal."""
    roster = lark().roster()

    assert recorded.LARK_USERS_PAGE_ONE["data"]["items"][0]["email"].endswith("gmail.example")
    assert [one.work_address for one in roster.people] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    ]


def test_a_resigned_lark_user_has_left_and_an_ordinary_one_has_not() -> None:
    """Three status flags and none of them is called active. `is_frozen` is suspended,
    `is_resigned` is left, and `is_activated` false is somebody who has never signed in.

    Delete this and a resignation recorded in Lark confers roles until somebody deletes the
    row by hand."""
    roster = lark().roster()

    assert person_at(roster, "grace@example.com").active is False
    assert person_at(roster, "ada@example.com").active is True


def test_a_department_identifier_is_translated_and_never_passed_through() -> None:
    """`department_ids` are opaque `od-` strings. Passing one through creates a department
    that no scope predicate can match, so the person sees nothing with nothing anywhere saying
    why, which is the worst shape a permission failure can take.

    Delete this and a Lark installation's departments are identifiers, and every grant bounded
    by one of them is a grant that matches nobody."""
    roster = lark().roster()

    assert departments_from(roster) == {
        "ada@example.com": "engineering",
        "grace@example.com": "engineering",
        "katherine@example.com": "finance",
    }


def test_somebody_in_two_departments_is_left_unplaced_and_said_so_rather_than_guessed_at() -> None:
    """A department is the scope a person's grants are bounded by, so choosing one of two is
    choosing how far somebody can see. There is one department on a roster record and Lark
    genuinely allows several, so the honest answer is that this reading cannot place them.

    Reported in the dropped list, because a person who is unplaced and does not know it looks
    exactly like a person whose department was never filled in.

    Delete this and whichever department happens to sort first decides somebody's reach."""
    reading = LarkSource(
        pages=[recorded.LARK_USERS_IN_TWO_DEPARTMENTS],
        department_names=recorded.LARK_DEPARTMENT_NAMES,
    ).reading()

    assert person_at(reading.roster, "jean@example.com").department == ""
    assert any("no one department bounds them" in one for one in reading.dropped), reading.dropped


def test_the_lark_identifier_is_the_union_id_and_not_the_per_application_open_id() -> None:
    """An open id is issued per application, so reinstalling the app renames every person in
    the company at once and every one of those renames reads as a departure and an arrival.
    The union id is the one that survives.

    Asserted against the recorded payload's own two fields rather than against a constant, so
    it cannot pass by comparing the adapter with itself.

    Delete this and one reinstall of the Lark app looks like the entire company leaving."""
    reading = lark().reading()
    first = recorded.LARK_USERS_PAGE_ONE["data"]["items"][0]

    assert first["open_id"] != first["union_id"]
    assert reading.stable_ids["ada@example.com"] == first["union_id"]


def test_a_lark_page_that_says_there_is_more_is_not_a_complete_roster() -> None:
    """`has_more` is nested under `data`, unlike every other continuation in this file, which
    is exactly the sort of difference a shared helper gets wrong.

    Delete this and the Lark adapter reads the top-level body for a key that lives one level
    down, finds nothing, and calls every partial read complete."""
    partial = LarkSource(pages=[recorded.LARK_USERS_PAGE_ONE])

    assert recorded.LARK_USERS_PAGE_ONE["data"]["has_more"] is True
    assert not partial.roster().complete
    assert lark().roster().complete


# --- LDAP and Active Directory, M1.6.6 ---------------------------------------------------------


def test_an_ldap_attribute_is_a_list_and_the_address_is_its_first_value() -> None:
    """**Every LDAP attribute is a list**, whatever the schema says, so `attributes["mail"]` is
    `["ada@example.com"]`. Using it directly produces the work address `['ada@example.com']`,
    which `StaffRecord` accepts because it contains an `@` and which matches no principal.

    Asserted against the recorded attribute rather than a literal, so the test moves with the
    payload rather than agreeing with a copy of it.

    Delete this and the whole directory parses into records that join to nobody."""
    reading = LdapSource(entries=recorded.ACTIVE_DIRECTORY_ENTRIES).reading()
    _, attributes = recorded.ACTIVE_DIRECTORY_ENTRIES[0]

    assert attributes["mail"] == ["ada@example.com"]
    assert person_at(reading.roster, "ada@example.com").display_name == "Ada Lovelace"


def test_an_attribute_name_is_matched_without_regard_to_its_case() -> None:
    """Attribute names are case-insensitive in the protocol and case-sensitive in a dict. A
    server that answers `sAMAccountName` to a request for `samaccountname` is behaving
    correctly, and the lookup that misses returns nothing rather than raising.

    Delete this and one server's spelling of `userAccountControl` marks a whole estate as
    present, or one server's spelling of `mail` produces a roster of nobody."""
    shouted = LdapSource(
        entries=[
            (
                "CN=Shouty,OU=People,DC=example,DC=com",
                {
                    "MAIL": ["shouty@example.com"],
                    "DISPLAYNAME": ["Shouty Person"],
                    "USERACCOUNTCONTROL": ["514"],
                },
            )
        ]
    ).roster()

    assert shouted.people[0].work_address == "shouty@example.com"
    assert shouted.people[0].active is False


def test_a_referral_is_not_a_person_and_makes_the_search_incomplete() -> None:
    """Active Directory answers a search that crosses a partition boundary with a continuation
    reference in the result stream, and it is an entry with no distinguished name. A client
    that iterates results without checking gets a person who is not one.

    It is also evidence, and that is the half nobody handles: a search that was referred
    elsewhere did not cover everything it was asked about, so its answer is not the whole list.

    Delete this and a forest with two domains proposes removing the second one."""
    reading = LdapSource(entries=recorded.AD_ENTRIES_WITH_A_REFERRAL).reading()

    assert [one.work_address for one in reading.roster.people] == ["ada@example.com"]
    assert not reading.roster.complete
    assert any("continuation reference" in one for one in reading.dropped), reading.dropped


def test_a_size_limit_is_a_truncation_that_keeps_the_people_it_returned() -> None:
    """Active Directory's default `MaxPageSize` is a thousand, so a company of twelve hundred
    whose client does not page gets a thousand people and a result code nobody read.

    The entries that came back are real, so this is an incomplete roster rather than an error:
    raising would throw away the people who were returned, and treating it as success would
    absent the two hundred who were not.

    **Both codes are passed explicitly and the default is checked against the recording**,
    because a first version of this relied on the default for the success case and a mutation
    survived it: the module's success constant is both the default and the value the check
    compares against, so moving it moved both sides together and every assertion held. A
    server that really did answer 0 would then have been refused. The independent fact is the
    protocol's own numbering, which `tests/fixtures/roster_payloads.py` records separately.

    Delete this and the most common misconfiguration of an LDAP sync removes everybody past
    the server's own page size."""
    truncated = LdapSource(
        entries=recorded.ACTIVE_DIRECTORY_ENTRIES,
        result_code=recorded.LDAP_SIZE_LIMIT_EXCEEDED,
    ).roster()

    assert len(truncated.people) == 3
    assert not truncated.complete

    finished = LdapSource(
        entries=recorded.ACTIVE_DIRECTORY_ENTRIES, result_code=recorded.LDAP_SUCCESS
    ).roster()

    assert len(finished.people) == 3
    assert finished.complete
    assert LdapSource(entries=()).result_code == recorded.LDAP_SUCCESS


def test_a_result_that_is_neither_success_nor_a_size_limit_has_no_roster_in_it() -> None:
    """The other half of the split. A truncation is a partial answer and everything else is
    the directory declining to answer, and reading a decline as an empty roster is how a bind
    failure becomes a proposal to remove the company.

    Delete this and any result code the parser does not know about is silently a company with
    nobody in it."""
    with pytest.raises(RosterUnavailableError, match="result code 32"):
        LdapSource(entries=(), result_code=32).roster()


def test_the_account_disable_flag_is_read_as_a_bit_and_never_as_a_number() -> None:
    """`userAccountControl` is a bit field: 512 is an ordinary enabled account, 514 is that
    account disabled, and 66048 is enabled with a password that does not expire. Comparing the
    whole number against 512 marks most of a real estate as departed.

    All three values, and the bit itself asserted against the values rather than against
    itself, so the constant cannot be changed to something that passes by agreeing with the
    test.

    Delete this and every account with a non-expiring password, a smartcard requirement or a
    locked-out flag reads as somebody who has left."""
    assert 512 & ACCOUNT_DISABLE_BIT == 0
    assert 514 & ACCOUNT_DISABLE_BIT != 0
    assert 66048 & ACCOUNT_DISABLE_BIT == 0

    roster = LdapSource(entries=recorded.ACTIVE_DIRECTORY_ENTRIES).roster()
    assert person_at(roster, "ada@example.com").active is True
    assert person_at(roster, "grace@example.com").active is False
    assert person_at(roster, "katherine@example.com").active is True


def test_a_directory_with_no_account_control_attribute_reports_everybody_as_present() -> None:
    """Plain LDAP has no `userAccountControl` at all, so an installation behind OpenLDAP has
    no way to say anybody has left. Defaulting the other way would have every such sync report
    the entire company as departed, which is a real limitation of that deployment read as a
    catastrophe.

    Delete this and the safe direction of that default is nobody's decision."""
    roster = LdapSource(entries=recorded.OPENLDAP_ENTRIES).roster()

    assert [one.active for one in roster.people] == [True, True]
    assert departments_from(roster) == {
        "ada@example.com": "engineering",
        "grace@example.com": "engineering",
    }


def test_the_directory_identity_is_the_object_identifier_and_never_the_distinguished_name() -> None:
    """Moving somebody between organisational units rewrites their distinguished name, so a
    roster keyed on it reads a reorganisation as everybody leaving and an equal number of
    strangers arriving. `objectGUID` and `entryUUID` do not move.

    Both flavours, because the attribute is named differently in Active Directory and in plain
    LDAP and an adapter that reads only one of them silently carries no identity for the other.

    Delete this and the first departmental reshuffle looks like a company replacing its
    entire staff."""
    ad = LdapSource(entries=recorded.ACTIVE_DIRECTORY_ENTRIES).reading()
    plain = LdapSource(entries=recorded.OPENLDAP_ENTRIES).reading()

    assert ad.stable_ids["ada@example.com"] == "{0a1b2c3d-0000-4000-8000-000000000001}"
    assert not any("CN=" in one for one in ad.stable_ids.values()), (
        "a distinguished name is being used as an identity"
    )
    assert plain.stable_ids["ada@example.com"] == "0a1b2c3d-0000-4000-8000-000000000001"


def test_an_account_with_no_mailbox_joins_on_its_user_principal_name() -> None:
    """An Active Directory account with a user principal name and no `mail` is a person who
    signs in and has no mailbox, which is ordinary in a company that keeps its mail elsewhere.
    The join is to the sign-in identity, so the principal name is the right fallback and
    dropping the row is the wrong one.

    The order matters and is asserted through the first entry of the recorded set, where the
    two agree: `mail` first, because a tenant whose principal names are on the internal
    `.local` domain and whose addresses are real would otherwise join to nothing.

    Delete this and every account without a mailbox disappears from the roster, silently, and
    the sync proposes removing them."""
    no_mailbox = LdapSource(
        entries=[
            (
                "CN=No Mailbox,OU=People,DC=example,DC=com",
                {
                    "userPrincipalName": ["nomail@example.com"],
                    "displayName": ["No Mailbox"],
                    "objectGUID": ["{0a1b2c3d-0000-4000-8000-0000000000aa}"],
                },
            )
        ]
    ).roster()

    assert [one.work_address for one in no_mailbox.people] == ["nomail@example.com"]


def test_a_directory_group_is_its_whole_distinguished_name() -> None:
    """Matching a rule on the common name alone would make `CN=Approvers,OU=Groups` and
    `CN=Approvers,OU=Legacy` the same group, which is how a group somebody retired goes on
    conferring a role from an organisational unit nobody looks at.

    Delete this and two groups with one name become one group, and leaving either stops
    conferring nothing."""
    roster = LdapSource(entries=recorded.ACTIVE_DIRECTORY_ENTRIES).roster()

    found = assertions_from(
        roster,
        [GroupRule(source_group="CN=Approvers,OU=Groups,DC=example,DC=com", role=Role.APPROVER)],
        principal_for={"ada@example.com": "p_ada"},
    )

    assert [one.source_group for one in found] == ["CN=Approvers,OU=Groups,DC=example,DC=com"]
    assert (
        assertions_from(
            roster,
            [GroupRule(source_group="Approvers", role=Role.APPROVER)],
            principal_for={"ada@example.com": "p_ada"},
        )
        == ()
    )


# --- what an adapter is, structurally ----------------------------------------------------------


def test_no_adapter_here_reaches_a_vendor_library_or_a_socket() -> None:
    """**The dependency decision, asserted rather than promised.** Four vendor SDKs in a
    single-tenant product a client hosts and rarely upgrades is four release schedules and
    four sets of transitive dependencies, and it makes every adapter here untestable except
    against a live tenant. `brain.connectors` refused the same trade and put the transport
    behind a callable.

    Read off the import statements rather than off the dependency list, because a vendor
    library can arrive as a transitive dependency of something else and still be imported
    here. Sockets are covered by the same reading: there is no `httpx`, no `socket` and no
    `urllib` either, so there is nothing in this module that could open one.

    Delete this and the first adapter that needs one more field imports a client to fetch it,
    and the module stops being testable without a tenant."""
    allowed = {"__future__", "re", "collections", "dataclasses", "typing", "brain"}
    source = Path(staff_adapters.__file__).read_text(encoding="utf-8")

    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(one.name.split(".")[0] for one in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported, "nothing was read, so this examined no imports at all"
    assert imported <= allowed, sorted(imported - allowed)


def test_an_adapter_is_a_roster_and_a_reading_and_nothing_else() -> None:
    """**`StaffSource` has exactly one method and adding a second is how sign-in collapses into
    the roster.** That rule is asserted on the protocol itself in `test_staff_source`; this is
    the sibling on the six classes that implement it, because a protocol with one method is no
    protection at all if the adapters grow a `verify` beside it.

    `reading` is the one addition and it is named here rather than left to a count, so a third
    method is a failing test with a diff to argue about rather than a number going up.

    The credential scan is the same one the protocol's own test runs, for the same reason: a
    method called `bind`, `check` or `verify` is the same failure whatever it is called, and a
    parameter that takes a secret is what it would need.

    Delete this and the Workspace adapter grows a sign-in method because it has the tokens
    already, and the first installation to notice is one whose staff list is a spreadsheet."""
    import inspect

    secrets = ("password", "secret", "token", "credential", "authenticate")
    classes = [type(one) for one in every_adapter().values()]
    assert len(classes) == 6

    for cls in classes:
        declared = {
            name
            for name, value in vars(cls).items()
            if not name.startswith("_") and callable(value)
        }
        assert declared == {"roster", "reading"}, f"{cls.__name__} declares {sorted(declared)}"
        for name in declared:
            parameters = " ".join(inspect.signature(getattr(cls, name)).parameters).casefold()
            assert not any(one in parameters for one in secrets), f"{cls.__name__}.{name}"


def test_no_adapter_hands_a_roster_a_value_with_space_around_it() -> None:
    """**Written from a gap in `Roster`'s own duplicate check, which this closes upstream of
    it rather than by editing it.**

    `Roster` refuses one person listed twice and case-folds to do it, because "a directory
    that exports one address in two capitalisations is a directory, not a hypothetical". It
    does not strip. So `" ada@example.com"` and `"ada@example.com"` are two rows that pass the
    check, and every set difference below them is then ambiguous in exactly the way that check
    exists to prevent: `assertions_from` looks a principal up by `work_address.casefold()`, so
    one of the two rows matches a principal and the other silently matches nobody.

    Padding arrives by three routes and all three are here, because a first version of this
    test used the tabular route alone and two mutations survived it: the cell reader strips,
    so nothing downstream of it was being exercised.

    - *A cell in a sheet*, where the departure marker is the field that matters. `" yes "` has
      to mean gone, and a comparison against an unstripped cell quietly means present.
    - *A field in a directory payload*, which reaches the record with no cell reader in front
      of it. An administrator who typed a trailing space into a console produces exactly this.
    - *`Roster` itself*, which is the third assertion and is the finding rather than the fix:
      it shows the pair still admitted a layer down, so a reader can see this is a narrowing
      here and not a rule enforced there.

    Delete this and one padded value becomes a person who exists twice, holds their roles
    under one spelling and none under the other."""
    from_a_sheet = SpreadsheetSource(
        rows=(
            ("Work Email", "Full Name", "Left?"),
            ("  ada@example.com  ", "  Ada Lovelace  ", "  yes  "),
        )
    ).roster()

    assert [one.work_address for one in from_a_sheet.people] == ["ada@example.com"]
    assert from_a_sheet.people[0].display_name == "Ada Lovelace"
    assert from_a_sheet.people[0].active is False

    from_a_directory = GoogleWorkspaceSource(
        pages=[
            {
                "users": [
                    {
                        "id": "100000000000000000001",
                        "primaryEmail": "  ada@example.com  ",
                        "name": {"fullName": "  Ada Lovelace  "},
                        "orgUnitPath": "  /Engineering  ",
                    }
                ]
            }
        ]
    ).reading()

    assert [one.work_address for one in from_a_directory.roster.people] == ["ada@example.com"]
    assert from_a_directory.roster.people[0].display_name == "Ada Lovelace"
    assert from_a_directory.stable_ids == {"ada@example.com": "100000000000000000001"}
    # Found by writing this test: the organisational unit path was stripped of its slash
    # before its spaces, so a padded `"  /Engineering  "` kept the slash and matched no scope.
    assert from_a_directory.roster.people[0].department == "Engineering"

    padded_department = MicrosoftEntraSource(
        pages=[
            {
                "value": [
                    {
                        "id": "8f1a0e5c-0000-4000-8000-000000000001",
                        "displayName": "Ada Lovelace",
                        "userPrincipalName": "ada@example.com",
                        "accountEnabled": True,
                        "department": "  Engineering  ",
                    }
                ]
            }
        ]
    ).roster()

    assert departments_from(padded_department) == {"ada@example.com": "Engineering"}

    admitted = Roster(
        source="somewhere",
        people=(
            StaffRecord(work_address=" ada@example.com", display_name="Ada"),
            StaffRecord(work_address="ada@example.com", display_name="Ada"),
        ),
        complete=True,
    )
    assert len(admitted.people) == 2, (
        "Roster now strips before its duplicate check, so this adapter-side narrowing is no "
        "longer the only thing standing between a padded value and two rows for one person"
    )


def test_every_adapter_returns_a_real_roster_from_its_recorded_payload() -> None:
    """The positive case for the whole file. Every rule above is a refusal or a narrowing, and
    a set of refusals is satisfied by six adapters that return nothing at all.

    Delete this and an adapter that produced an empty roster for every payload would pass
    every completeness, trust and dropped-row test in this file."""
    for name, adapter in every_adapter().items():
        roster = adapter.roster()
        assert isinstance(roster, Roster), name
        assert roster.people, f"{name} produced nobody"
        assert all(one.display_name for one in roster.people), name


def test_every_staff_list_this_file_parses_is_one_an_install_can_choose_and_the_reverse() -> None:
    """The two lists that have to stay in step, and they fail differently. A parser no install
    can choose is dead code that reads as live, because it has tests and a docstring naming it
    as one of the places a client keeps their people. A choice nothing parses is worse: it is
    offered on a setup screen, picked, and then there is nothing to read the list with, on the
    client's own server rather than here.

    Asserted against the real lists, and the reporting itself is asserted against made-up ones
    below, because a check that always returns nothing looks identical to one that is passing.

    Delete this and a seventh adapter can be written that no install can select, or a seventh
    option offered that nothing can read."""
    assert choices_and_adapters_that_do_not_match() == ()
    assert set(CHOOSABLE_SOURCES) == set(ADAPTER_SOURCES)


def test_a_parser_nobody_can_choose_and_a_choice_nothing_parses_are_reported_separately() -> None:
    """The findings the check above is expected never to produce, produced deliberately, so
    that its empty answer on the real lists is evidence rather than a tautology.

    Both directions in one test because the pair is the point: a single set difference would
    report one of them and be silent about the other, and the silent one is the one that
    reaches a client.

    Delete this and the check can be reduced to a function returning an empty tuple, and every
    test of it stays green."""
    orphaned = choices_and_adapters_that_do_not_match(parsed=("lark",), choosable=())
    unreadable = choices_and_adapters_that_do_not_match(parsed=(), choosable=("lark",))

    assert orphaned == ("'lark' is parsed here and is not a staff source any install can choose",)
    assert unreadable == ("'lark' can be chosen at install time and nothing here parses it",)


def test_a_source_string_no_install_can_choose_is_offered_by_nothing() -> None:
    """The hazard the check above guards, shown rather than described, and it is the sibling of
    the near-miss demotion earlier in this file. A source string spelled differently in the two
    lists does not raise anywhere: the adapter parses, the trust resolves, and the only symptom
    is that no setup screen ever offers it.

    Delete this and the pairing above looks like bookkeeping rather than the thing that keeps
    a written adapter reachable."""
    assert GOOGLE_WORKSPACE in CHOOSABLE_SOURCES

    with pytest.raises(StaffSourceError):
        selected_source({STAFF_SOURCE_SETTING: "google-workspace"})
