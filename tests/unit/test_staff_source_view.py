"""The staff source page held to the three things it has to do and the one it must never do.

M1.6.11 is "console page to choose, configure and test a staff source before it runs", and the
module it is written against says in terms that **nothing in the product called it**:
`brain.identity.staff_source.roster_from` names this page as the caller it was written for. So
the discriminating tests here are the ones that would pass if the page rendered a plausible
answer of its own instead of calling those functions, and every one of them compares what the
page shows against what the module that decided it said, rather than against a substring.

Three properties and a refusal.

*Choose.* Every source an install may pick is offered, read out of `SELECTABLE` in its declared
order, with the meaning that tuple carries and no summary of it.

*Configure.* The chosen source is named with the settings nobody has supplied, and the reason it
cannot be used is `selected_source`'s own message rather than console prose about the same
state.

*Test it before it runs.* A trial calls `roster_from` and `dry_run`, which are the two functions
a real sync calls, so what the page shows is what would happen rather than a rehearsal of a
different performance. It writes nothing, and the plan it carries is the plan the sync would
act on.

*And it never renders a credential.* A staff source is pointed somewhere, the setting that
points it is not credential-shaped by name, and the value in it is a directory address or half a
share link. The page carries setting names, the constructors refuse a name `brain.install` does
not declare, and a check reads every string every row carries against what this install actually
set. `brain.deployment.variables.is_secret_name` is asserted to answer False for that setting,
because that is the evidence for why a name filter would not have saved the page.

Real `EntitlementSet`s, real `SelectableSource`s from the module's own tuple, and a real
`Roster` throughout. A test that handed the page a `DryRun` it had built would be checking the
page against an agreement this file had made with itself, which is the producer-and-consumer
trap `CLAUDE.md` names.

Task ids: M1.6.11
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.staff_source_view import (
    PAGE_READ,
    PAGE_ROWS,
    TRIAL_READ,
    Selection,
    SourceOption,
    Trial,
    choices,
    selection,
    staff_source_gaps,
    trial,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.deployment.variables import is_secret_name
from brain.identity.directory import DirectoryAssertion
from brain.identity.roles import Role
from brain.identity.staff_source import (
    SELECTABLE,
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    Asserts,
    GroupRule,
    Roster,
    SelectableSource,
    StaffRecord,
    StaffSourceError,
    selectable_names,
    selected_source,
)
from brain.identity.staff_sync import dry_run
from brain.ops.jobs import hidden_count_fields

#: A fixed moment, pinned far from any wall clock for the reason
#: `tests/unit/test_scope_and_capability.py` gives: nothing below is about the present, so a
#: fixture that could expire would report a defect on a schedule nobody chose.
NOW = datetime(2027, 5, 1, 9, 0, tzinfo=UTC)

#: What this install's environment says, for the case where everything is wired.
WIRED = {STAFF_SOURCE_SETTING: "google_workspace", STAFF_SOURCE_LOCATION_SETTING: "a-tenant"}

#: The same choice with nobody having said where the list is.
POINTED_NOWHERE = {STAFF_SOURCE_SETTING: "google_workspace"}

#: A name no install can use, which is the refusal that lists what exists.
MISSPELLED = {STAFF_SOURCE_SETTING: "google_workspce"}

#: Two people a source names, and the principal this system already holds for one of them.
ANN = StaffRecord(
    work_address="ann@example.test",
    display_name="Ann",
    department="maintenance",
    groups=("approvers",),
)
BEN = StaffRecord(work_address="ben@example.test", display_name="Ben", department="maintenance")
KNOWN = {"ann@example.test": "u_ann", "gone@example.test": "u_gone"}


def a_roster(
    *,
    source: str = "google_workspace",
    people: tuple[StaffRecord, ...] = (ANN, BEN),
    complete: bool = True,
    asserts: frozenset[Asserts] = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}),
) -> Roster:
    """One real roster. Built here so a test can vary the one thing it is about."""
    return Roster(source=source, people=people, complete=complete, asserts=asserts)


@dataclass
class Answering:
    """A staff source that answers once and records that nothing else was asked of it.

    A real implementation of the `StaffSource` protocol rather than a stub of `roster_from`,
    because the property under test is that the page goes through `roster_from`, and a test
    that replaced it would be watching the call it wanted to see.
    """

    gives: Roster
    asked: int = field(default=0)

    def roster(self) -> Roster:
        self.asked += 1
        return self.gives


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONTENT,),
    scope: Scope | None = None,
) -> EntitlementSet:
    """A caller holding these capabilities in one scope, plus the plane grants named.

    Both halves decide whether a read is permitted, and the scope is separable from the
    capabilities so that a department-scoped reader can be built holding exactly what an
    unrestricted one holds.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id="u_test", grants=tuple(grants))


def a_reader(
    *, planes: tuple[Plane, ...] = (Plane.CONTENT,), scope: Scope | None = None
) -> EntitlementSet:
    """Somebody granted the Staff sources screen's own capability, from the registry."""
    return holding(screen("staff_sources").read.requires.value, planes=planes, scope=scope)


# --- choose: every source an install may pick ------------------------------------------------


def test_the_page_offers_every_source_the_product_can_read_and_takes_none_of_them_on_trust() -> (
    None
):
    """**M1.6.11's first word.** The list of sources is `SELECTABLE` and the page reads it: a
    second list here would be a console offering an install a choice the module that resolves
    it has never heard of, and the symptom would be a source somebody picked and nothing could
    read.

    Names and meanings are compared against the tuple rather than spot-checked, and the order is
    compared too, because that order is the order `selected_source` lists in its refusal and a
    page sorted differently makes the refusal read as being about something else.

    Delete this and the seven options become a list in a template, and the eighth source is
    added to `SELECTABLE` and never appears on the page that exists to offer it."""
    offered = choices(a_reader(), NOW, env=WIRED)

    assert [one.name for one in offered] == list(selectable_names())
    assert [one.meaning for one in offered] == [one.meaning for one in SELECTABLE]
    assert [one.reads_a_list for one in offered] == [one.reads_a_list for one in SELECTABLE]
    assert [one.needs for one in offered] == [one.needs for one in SELECTABLE]


def test_the_source_this_install_chose_is_the_one_marked_chosen_and_the_others_are_not() -> None:
    """The page has to say which row is this install's, and it has to say so even when that row
    cannot be used, because the row and the refusal are read together.

    Two environments, so the mark moves. A page that marked everything, or nothing, satisfies a
    test that only looked at one.

    Delete this and `chosen` can be hard-coded or dropped, and an operator reads seven options
    with no indication which one their install is on."""
    on_workspace = {one.name for one in choices(a_reader(), NOW, env=WIRED) if one.chosen}
    unwired = {one.name for one in choices(a_reader(), NOW, env=POINTED_NOWHERE) if one.chosen}
    unrecognised = {one.name for one in choices(a_reader(), NOW, env=MISSPELLED) if one.chosen}

    assert on_workspace == {"google_workspace"}
    assert unwired == {"google_workspace"}
    assert unrecognised == set()


def test_a_reader_without_the_screens_grant_is_offered_no_source_and_told_no_number() -> None:
    """**DENIED and ABSENT, on the page's first function.** A reader holding nothing gets the
    empty tuple, which is what an install with no sources would return, and there is no second
    value carrying how many were withheld: `choices` returns one thing.

    The positive sibling is above and is named again here, because a function returning `()` for
    everybody passes every refusal test in this file.

    Delete this and the page can return the options with a flag on each, which is the same
    disclosure written as a column instead of as a count."""
    nothing = EntitlementSet(principal_id="u_test", grants=())

    assert choices(nothing, NOW, env=WIRED) == ()
    assert selection(nothing, NOW, env=WIRED) is None
    assert len(choices(a_reader(), NOW, env=WIRED)) == len(SELECTABLE)


def test_a_department_scoped_grant_over_staff_sources_reaches_no_source_at_all() -> None:
    """A roster is one list for the whole company and the department is a column inside it, so
    `brain.console.govern_surfaces` places a source at `brain.console.govern.NOWHERE` and
    `Clause.matches` refuses a field the row does not have. This page inherits that, and it is
    what makes every answer here whole or absent: there is no partial page for a count to sit
    beside.

    The two readers hold exactly the same capability and differ only in the scope, so this
    cannot pass because one of them was built without a grant.

    Delete this and a department admin is shown the company's staff source configuration, and
    the argument that it is harmless is the argument `A_ROSTER_IS_THE_WHOLE_COMPANYS_LIST_AND_
    SITS_IN_NO_DEPARTMENT` already refuses."""
    scoped = a_reader(scope=Scope.department("maintenance"))
    unrestricted = a_reader()

    assert choices(scoped, NOW, env=WIRED) == ()
    assert selection(scoped, NOW, env=WIRED) is None
    assert (
        trial(Answering(a_roster()), scoped, NOW, known=KNOWN, last_applied=NOW, env=WIRED) is None
    )

    assert len(choices(unrestricted, NOW, env=WIRED)) == len(SELECTABLE)


# --- configure: what is still unset, in the refusing module's own words -----------------------


def test_a_source_pointed_nowhere_is_named_with_the_setting_nobody_supplied() -> None:
    """**M1.6.11's second word, and the refusal is `selected_source`'s rather than this
    page's.** The message is compared against the exception that function actually raises, so a
    page that composed its own sentence about the same state fails here even if the sentence is
    better.

    `unsupplied` names the setting rather than describing it, which is what makes the answer
    something an operator can act on: they set that variable.

    Delete this and the console grows a second description of a misconfiguration, and the two
    drift in the direction where the console's is the one somebody reads."""
    with pytest.raises(StaffSourceError) as refused:
        selected_source(POINTED_NOWHERE)

    found = selection(a_reader(), NOW, env=POINTED_NOWHERE)

    assert found is not None
    assert found.name == "google_workspace"
    assert found.ready is False
    assert found.refusal == str(refused.value)
    assert found.unsupplied == (STAFF_SOURCE_LOCATION_SETTING,)
    assert found.meaning == next(
        one.meaning for one in SELECTABLE if one.name == "google_workspace"
    )


def test_a_source_nobody_recognises_is_refused_with_the_names_that_exist() -> None:
    """The other refusal `selected_source` raises, and the one where the page has to show the
    value the install set: the message quotes it, and a page displaying that message while
    withholding what it is about would be an argument with the subject removed.

    There is no meaning, because there is no source to be meaningful about, and inventing a
    sentence there would be the page answering a refusal.

    Delete this and a misspelled setting reads as a source that exists and is merely not
    configured, which sends somebody to set a variable that would not have helped."""
    with pytest.raises(StaffSourceError) as refused:
        selected_source(MISSPELLED)

    found = selection(a_reader(), NOW, env=MISSPELLED)

    assert found is not None
    assert found.name == "google_workspce"
    assert found.ready is False
    assert found.refusal == str(refused.value)
    assert found.meaning == ""
    assert found.unsupplied == ()


def test_a_source_that_is_wired_is_ready_with_nothing_outstanding() -> None:
    """The positive case, and without it every assertion above is satisfied by a page that
    refuses everything.

    The one option that reads no list is asserted beside it, because `none` is a choice an
    install makes rather than the absence of one, and a page that treated it as unconfigured
    would send somebody looking for a setting to fill in.

    Delete this and `ready` can be `False` for every install, and the page never says a source
    is usable."""
    wired = selection(a_reader(), NOW, env=WIRED)
    nothing_chosen = selection(a_reader(), NOW, env={STAFF_SOURCE_SETTING: "none"})

    assert wired is not None
    assert wired.ready is True
    assert wired.refusal == ""
    assert wired.unsupplied == ()
    assert wired.reads_a_list is True

    assert nothing_chosen is not None
    assert nothing_chosen.ready is True
    assert nothing_chosen.reads_a_list is False


def test_a_selection_cannot_say_it_is_ready_while_carrying_a_setting_nobody_supplied() -> None:
    """The contradiction the page would otherwise be able to render: a green tick beside a list
    of variables somebody still has to set. `selected_source` refuses exactly that state, so a
    row claiming it is the page disagreeing with the refusal it exists to display.

    The valid row is built in the same shape, so this is the constructor refusing one case
    rather than refusing everything.

    Delete this and a renderer can show a source as usable because its name resolved, and the
    sync fails on the night it runs."""
    with pytest.raises(ValueError, match="shown as ready to read"):
        Selection(
            name="google_workspace",
            meaning="a source a test built so the constructor has something to refuse",
            reads_a_list=True,
            unsupplied=(STAFF_SOURCE_LOCATION_SETTING,),
        )

    allowed = Selection(
        name="google_workspace",
        meaning="a source a test built so the constructor has something to accept",
        reads_a_list=True,
        unsupplied=(STAFF_SOURCE_LOCATION_SETTING,),
        refusal="the words of whichever module refused it",
    )

    assert allowed.ready is False


# --- and it never renders a credential --------------------------------------------------------


def test_a_setting_that_points_a_source_somewhere_is_not_credential_shaped_by_name() -> None:
    """**The evidence for the whole credential decision, measured rather than asserted.** The
    tempting rule is to render a setting's value unless its name looks like a password.
    `brain.deployment.variables.is_secret_name` is this repository's one answer to that question
    and it says no about the setting that points a staff source, correctly, because the name
    states a place. The values that go in it are a directory address carrying the base a search
    starts from and a sheet identifier that is half a share link.

    The positive half is a name that check does say yes about, so this is not passing because
    `is_secret_name` answers no to everything.

    Delete this and the reason the page shows names rather than values is a sentence in a
    docstring, and the first person who wants to see what a source is pointed at reads the
    docstring as caution rather than as a finding."""
    assert is_secret_name(STAFF_SOURCE_LOCATION_SETTING) is False
    assert is_secret_name(STAFF_SOURCE_SETTING) is False
    assert is_secret_name("LANGFUSE_POSTGRES_PASSWORD") is True

    assert all(is_secret_name(name) is False for one in SELECTABLE for name in one.needs)


def test_no_row_of_this_page_carries_what_a_setting_is_set_to() -> None:
    """The rule as a measurement over what the page actually renders. This install's location is
    a value a test chose, and no string on any row may contain it: not the meaning, not the
    needs, not the refusal.

    Asserted over both halves of the page and over three environments, including the one where
    the refusal is longest, because the refusal is the string most likely to grow a helpful
    "currently set to".

    Delete this and a field called `location` is the obvious next column, and the page that
    shows where a directory is shows the bind credential inside the address the day a source
    needs one."""
    value = WIRED[STAFF_SOURCE_LOCATION_SETTING]

    for env in (WIRED, POINTED_NOWHERE, MISSPELLED):
        rows: list[object] = [*choices(a_reader(), NOW, env=env)]
        chosen = selection(a_reader(), NOW, env=env)
        assert chosen is not None
        rows.append(chosen)
        for row in rows:
            for carried in _every_string(row):
                assert value not in carried, (row, carried)

    assert staff_source_gaps(WIRED) == ()


def test_a_row_offering_a_value_where_a_setting_name_belongs_cannot_be_built() -> None:
    """The check no value can pass, which is `brain.firstrun`'s shape rather than a rule
    somebody keeps: `brain.install` declares the settings an install can set, and a sheet
    identifier, a directory address and a client secret are none of them.

    Both row types are held to it, because the leak arrives on whichever one somebody is editing
    when they decide the page would be more useful with the value on it.

    Delete this and `needs=(value_of(STAFF_SOURCE_LOCATION_SETTING, env),)` is a one-line edit
    that reads like a fix for a page showing an unhelpful variable name."""
    with pytest.raises(ValueError, match=r"brain\.install declares none of them"):
        SourceOption(
            name="ldap",
            meaning="a source a test built so the constructor has something to refuse",
            reads_a_list=True,
            needs=("ldaps://directory.example.test/dc=example",),
            unsupplied=(),
            chosen=False,
        )

    with pytest.raises(ValueError, match=r"brain\.install declares none of them"):
        Selection(
            name="ldap",
            meaning="a source a test built so the constructor has something to refuse",
            reads_a_list=True,
            unsupplied=("ldaps://directory.example.test/dc=example",),
            refusal="the words of whichever module refused it",
        )

    allowed = SourceOption(
        name="ldap",
        meaning="a source a test built so the constructor has something to accept",
        reads_a_list=True,
        needs=(STAFF_SOURCE_LOCATION_SETTING,),
        unsupplied=(STAFF_SOURCE_LOCATION_SETTING,),
        chosen=True,
    )

    assert allowed.unsupplied == (STAFF_SOURCE_LOCATION_SETTING,)


def test_an_option_cannot_report_a_setting_unset_that_the_source_does_not_need() -> None:
    """A row asking somebody to set a variable that would change nothing about whether the
    source can be read. It is the smaller half of the same guard and it is the one that fires
    when a later edit computes `unsupplied` from somewhere other than the source's own `needs`.

    Delete this and the page can list every unset installation setting under every source."""
    with pytest.raises(ValueError, match=r"reports .* unset and does not need them"):
        SourceOption(
            name="spreadsheet",
            meaning="a source a test built so the constructor has something to refuse",
            reads_a_list=True,
            needs=(),
            unsupplied=(STAFF_SOURCE_LOCATION_SETTING,),
            chosen=False,
        )


# --- test it before it runs -------------------------------------------------------------------


def test_a_trial_asks_the_source_once_and_shows_the_plan_a_real_sync_would_act_on() -> None:
    """**M1.6.11's third word, and the half that makes the page worth opening.** The trial goes
    through `roster_from`, which is the function that checks the answer against the choice this
    install made, and hands what comes back to `dry_run`, which is what the scheduled sync hands
    it to. The plan is compared against one computed directly from the same roster, so a page
    that assembled its own diff fails here.

    The source is asked exactly once, and the mappings handed in are unchanged afterwards, which
    is what "changes nothing" amounts to at this layer.

    Delete this and the page can show a plausible preview computed from the roster it fetched,
    and the operator reads a rehearsal of a different performance."""
    source = Answering(a_roster())
    held = (DirectoryAssertion(principal_id="u_ann", role=Role.APPROVER, source_group="approvers"),)
    rules = (GroupRule(source_group="approvers", role=Role.APPROVER),)

    found = trial(
        source,
        a_reader(),
        NOW,
        known=dict(KNOWN),
        last_applied=NOW,
        rules=rules,
        held=held,
        env=WIRED,
    )

    assert found is not None
    assert source.asked == 1
    assert found.source == "google_workspace"
    assert found.refusals == ()
    assert found.safe_to_apply is True
    assert found.plan == dry_run(
        a_roster(), known=dict(KNOWN), last_applied=NOW, rules=rules, held=held
    )
    assert KNOWN == {"ann@example.test": "u_ann", "gone@example.test": "u_gone"}


def test_a_trial_names_who_would_join_and_who_the_source_never_mentioned() -> None:
    """What "test it before it runs" is for. An operator wiring a connector at one part of a
    directory needs the names, because the failure they are looking for is a source that is
    complete and correct about the wrong question.

    Ben is in the roster and not in this system, so he would be added; the person this system
    holds and the roster never names is reported as absent. Both come out of `dry_run` and
    neither is recomputed here.

    Delete this and the trial can carry a plan whose lists nobody reads, and a source pointed at
    one office passes its test."""
    found = trial(
        Answering(a_roster()), a_reader(), NOW, known=dict(KNOWN), last_applied=NOW, env=WIRED
    )

    assert found is not None
    assert found.plan is not None
    assert [one.work_address for one in found.plan.would_add] == ["ben@example.test"]
    assert found.plan.absent == ("gone@example.test",)


def test_a_trial_reports_every_refusal_that_would_have_stopped_it_rather_than_raising() -> None:
    """**The one tool for finding a misconfiguration has to survive every misconfiguration**,
    which is `A_DRY_RUN_THAT_CANNOT_SURVIVE_A_BAD_CONFIGURATION_IS_NO_USE_AT_ALL` one layer up:
    a trial is read at exactly the moment somebody is finding out whether a source is wired
    correctly.

    Four refusals, from both modules that raise one: a name nobody recognises, a source pointed
    nowhere, a roster that came from somewhere else, and a roster of nobody. Every one carries
    no plan and closes `safe_to_apply`, and each message is the refusing module's own.

    Delete this and pressing Test on a half-wired source raises out of the page, and the tool
    for diagnosing the configuration is the tool that cannot be opened while it is wrong."""
    reader = a_reader()
    elsewhere = Answering(a_roster(source="ldap", asserts=frozenset({Asserts.EXISTENCE})))
    nobody = Answering(a_roster(people=()))

    cases = [
        (Answering(a_roster()), MISSPELLED, "is not a staff list this product can read"),
        (Answering(a_roster()), POINTED_NOWHERE, "is the chosen staff list and"),
        (elsewhere, WIRED, "was handed a roster from"),
        (nobody, WIRED, "answered with nobody"),
    ]
    for source, env, says in cases:
        found = trial(source, reader, NOW, known=dict(KNOWN), last_applied=NOW, env=env)

        assert found is not None, says
        assert found.plan is None, says
        assert found.safe_to_apply is False, says
        assert len(found.refusals) == 1, says
        assert says in found.refusals[0], found.refusals


def test_a_trial_of_a_source_configured_to_assert_more_than_it_may_is_not_safe_to_apply() -> None:
    """The refusal `dry_run` catches inside itself rather than one that stops the trial, so this
    is the case where a plan exists and must still be closed. A spreadsheet wired to role rules
    is the misconfiguration `assertions_from` exists to refuse, and refusing at configuration
    time means refusing while somebody is looking at this page.

    `safe_to_apply` asks the plan rather than repeating its rule, and this is what holds it to
    that: the trial's own `refusals` are empty here.

    Delete this and `safe_to_apply` can be written as "nothing stopped the trial", and the page
    offers an Apply button for a configuration the sync will refuse."""
    sheet = Answering(
        a_roster(source="spreadsheet", asserts=frozenset({Asserts.EXISTENCE}), people=(ANN,))
    )
    found = trial(
        sheet,
        a_reader(),
        NOW,
        known=dict(KNOWN),
        last_applied=NOW,
        rules=(GroupRule(source_group="approvers", role=Role.APPROVER),),
        env={STAFF_SOURCE_SETTING: "spreadsheet"},
    )

    assert found is not None
    assert found.refusals == ()
    assert found.plan is not None
    assert found.plan.refusals
    assert found.safe_to_apply is False


def test_naming_who_would_join_needs_the_content_plane_and_the_page_itself_does_not() -> None:
    """**The trial is a wider read than the page it sits on, and this is where that is
    visible.** A reader holding the Staff sources screen at the configuration plane is shown the
    choice and what is unset, and no trial: the trial names the company's staff, and existence,
    configuration and content are three separate grants for exactly this reason.

    The same reader with the content plane gets the trial, so the absence is a property of the
    grant rather than of the function returning nothing.

    Delete this and pressing Test shows a configuration reader every name the roster carries,
    from a screen whose own row deliberately carries no headcount at all."""
    configuration = a_reader(planes=(Plane.EXISTENCE, Plane.CONFIGURATION))
    content = a_reader(planes=(Plane.EXISTENCE, Plane.CONFIGURATION, Plane.CONTENT))

    assert selection(configuration, NOW, env=WIRED) is not None
    assert len(choices(configuration, NOW, env=WIRED)) == len(SELECTABLE)
    assert (
        trial(
            Answering(a_roster()),
            configuration,
            NOW,
            known=dict(KNOWN),
            last_applied=NOW,
            env=WIRED,
        )
        is None
    )

    assert (
        trial(Answering(a_roster()), content, NOW, known=dict(KNOWN), last_applied=NOW, env=WIRED)
        is not None
    )


def test_a_trial_a_reader_may_not_see_is_absent_and_the_source_is_never_asked() -> None:
    """A refusal that fetched the roster first would have read the company's staff list in order
    to decide not to show it, which is the disclosure happening anywhere except the screen.

    The counter is the evidence: the source is untouched, and the same source answers once for a
    reader who may see it.

    Delete this and the permission check can move below the fetch, where it still looks correct
    and the roster has already been read."""
    refused = Answering(a_roster())
    allowed = Answering(a_roster())
    nothing = EntitlementSet(principal_id="u_test", grants=())

    assert trial(refused, nothing, NOW, known=dict(KNOWN), last_applied=NOW, env=WIRED) is None
    assert refused.asked == 0

    assert trial(allowed, a_reader(), NOW, known=dict(KNOWN), last_applied=NOW, env=WIRED)
    assert allowed.asked == 1


def test_a_trial_refuses_to_hold_a_plan_beside_a_refusal_or_neither_of_the_two() -> None:
    """Exactly one of the two, refused here rather than left to whatever draws the page. A plan
    shown next to a refusal is a plan somebody applies and the refusal becomes a note beside the
    rows; a missing plan with nothing saying why sends the reader looking for a setting that
    would not have helped.

    Both halves, because a constructor refusing only the first lets the second through, and the
    second is the state a caught exception with an empty message produces.

    Delete this and the page can render an Apply button under a refusal."""
    plan = dry_run(a_roster(), known=dict(KNOWN), last_applied=NOW)

    with pytest.raises(ValueError, match="a plan is set beside the refusal"):
        Trial(source="google_workspace", plan=plan, refusals=("something refused it",))

    with pytest.raises(ValueError, match="produced no plan and nothing says why"):
        Trial(source="google_workspace", plan=None, refusals=())

    with pytest.raises(ValueError, match="naming no source"):
        Trial(source="   ", plan=plan, refusals=())

    assert Trial(source="google_workspace", plan=plan, refusals=()).safe_to_apply is True


# --- the diagnostics --------------------------------------------------------------------------


def test_no_row_of_this_page_has_anywhere_to_put_a_count_of_what_was_withheld() -> None:
    """The subtraction disclosure as a shape rather than as a rule. A field called `hidden` or
    `filtered` on any of these rows would tell a reader how much they were not shown, and the
    rule that lives only in prose is defeated by somebody adding one field while making a screen
    better.

    The constructed type proves the check is live. Without it this assertion is satisfied by a
    function that finds nothing anywhere.

    Delete this and `SourceOption.filtered` is what somebody adds the day a filter is put on
    this page."""
    assert hidden_count_fields(PAGE_ROWS) == ()

    @dataclass(frozen=True)
    class WithACount:
        name: str
        hidden: int

    assert hidden_count_fields([WithACount]) == ("WithACount.hidden",)
    assert staff_source_gaps() == ()


def test_the_gaps_report_a_row_that_carries_what_this_install_set_a_setting_to() -> None:
    """The credential check exercised with the broken input, which is the only interesting case
    and is why the diagnostic takes its sources rather than reading the module's tuple. A source
    whose meaning quotes the location is what a helpful edit looks like, and the check reads
    every string every row carries rather than a list of field names somebody maintains.

    The quiet baseline is above and is the sibling: a check that reported on everything would
    satisfy this and be switched off inside a week.

    Delete this and the rule about values is enforced only by the constructors, which catch a
    value in a tuple of setting names and not one interpolated into a sentence."""
    leaking = (
        SelectableSource(
            name="ldap",
            meaning="An LDAP directory, currently pointed at a-tenant by this installation.",
            needs=(STAFF_SOURCE_LOCATION_SETTING,),
        ),
    )

    gaps = staff_source_gaps(WIRED, sources=leaking)

    assert [one for one in gaps if one.startswith("a row of this page carries what")], gaps
    assert staff_source_gaps(WIRED, sources=leaking[:0]) == ()


def test_the_gaps_read_a_trial_handed_to_them_because_they_cannot_build_one() -> None:
    """**A mutation found the tuple half of the scan unreachable and this is the repair.**
    `Trial.refusals` is a tuple of sentences another module wrote, and it is the one long string
    on this page that neither constructor checks, because neither constructor wrote it. It was
    also the one row the diagnostic could not build, since building a trial means calling a live
    staff source, so the check walked two row types whose every tuple field is already refused a
    value at construction and the walk was dead code.

    So a caller hands its trial over. The refusal here quotes where the source is pointed, which
    is what a sentence appended to a carried message looks like from outside.

    The quiet half is the real trial from the function above, handed to the same check, so this
    is not passing because anything handed in is reported.

    Delete this and `_strings_on` can stop looking inside tuples with nothing failing, and the
    day a refusal names a credential the check that was written for it walks past."""
    quoting = Trial(
        source="google_workspace",
        plan=None,
        refusals=(f"the source at {WIRED[STAFF_SOURCE_LOCATION_SETTING]} answered with nobody",),
    )

    gaps = staff_source_gaps(WIRED, shown=(quoting,))

    assert [one for one in gaps if one.startswith("a row of this page carries what")], gaps

    honest = trial(
        Answering(a_roster()), a_reader(), NOW, known=dict(KNOWN), last_applied=NOW, env=WIRED
    )

    assert honest is not None
    assert staff_source_gaps(WIRED, shown=(honest,)) == ()


def test_the_gaps_report_a_trial_readable_by_everybody_who_can_read_the_page() -> None:
    """The trial's plane, watched. Set it to the page's own and naming who would be added
    becomes a configuration disclosure on a screen whose row deliberately carries no headcount,
    and nothing about the page would look different.

    The module's own pair is asserted to be the healthy shape, so this is a check about a state
    that can exist rather than one about the tree as it stands.

    Delete this and widening the page or narrowing the trial is a one-word edit with no failure
    behind it."""
    assert TRIAL_READ.plane is Plane.CONTENT
    assert PAGE_READ.plane is Plane.CONFIGURATION

    gaps = staff_source_gaps(trial_read=PAGE_READ)

    assert [one for one in gaps if "is reachable by everybody who can read the screen" in one], gaps


def test_the_gaps_report_a_trial_wired_to_a_second_tool_or_a_second_capability() -> None:
    """The trial is the same screen's read one plane wider, and the two things that must not
    drift are the tool and the capability. A second capability is a grant nobody writes; a
    second tool is a console read outside `SCREENS`, which is the one place
    `brain.console.screens.unregistered_tools` looks to ask whether anything answers it.

    Both are provoked, because a check comparing only one of the pair passes the other half.

    Delete this and the trial acquires a tool of its own, and nothing in the repository is
    counting whether it exists."""
    from brain.console.reads import ConsoleRead

    other_tool = ConsoleRead(
        screen=PAGE_READ.screen,
        tool="console.staff_source_trial",
        requires=PAGE_READ.requires,
        plane=Plane.CONTENT,
    )
    other_capability = ConsoleRead(
        screen=PAGE_READ.screen,
        tool=PAGE_READ.tool,
        requires=Capability(value="read:staff_source.trial"),
        plane=Plane.CONTENT,
    )

    for read in (other_tool, other_capability):
        gaps = staff_source_gaps(trial_read=read)

        assert [one for one in gaps if "a grant nobody writes" in one], gaps


def _every_string(row: object) -> list[str]:
    """Every string one of this page's rows carries, walked by the test rather than imported.

    A second implementation on purpose, and the only one in this file. The module's own walker
    is what the credential check uses, so importing it would leave that check comparing itself
    against itself, which is the trap `CLAUDE.md` names about a producer and a consumer either
    side of a value.
    """
    found: list[str] = []
    for name in getattr(type(row), "__dataclass_fields__", {}):
        value = getattr(row, name)
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, tuple):
            found.extend(one for one in value if isinstance(one, str))
    return found
