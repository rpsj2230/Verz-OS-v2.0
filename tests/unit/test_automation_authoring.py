"""A new automation: the trigger, the one comparison, the tools, the rehearsal and the confirmation.

Every refusal has a sibling proving the permitted case still works, because a guard tested only by
its refusals is satisfied by a function that refuses everything.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.connectors.manifest import FieldShape
from brain.console import automation_authoring as module
from brain.console.automation_authoring import (
    AUTHORED_TASK,
    AUTHORED_TEMPLATE,
    NOTHING_FIRES_THIS_YET,
    NOTHING_WAS_WRITTEN_OR_SENT,
    REHEARSED_TRIGGERS,
    Authored,
    AuthoringRefusedError,
    Condition,
    ConditionField,
    ConditionOp,
    TriggerChoice,
    Verdict,
    authored_from_row,
    authoring_of,
    compose,
    may_author,
    ops_for,
    preview,
    rehearse,
)
from brain.console.automation_gallery import (
    AUTOMATION_AUTHORITY,
    BUILT_IN,
    Cadence,
    Every,
    GalleryError,
    NotConfirmedError,
)
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.visibility import Visibility
from brain.ops.automation_run import INSTRUCTION_TASK, TASKS, slots_before, task_gaps
from brain.orchestration.unattended import TriggerKind

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2031, 3, 14, 12, 0, tzinfo=UTC)

DAILY = Cadence(every=Every.DAY, hour_utc=7)
DUE = ConditionField(
    connector="invoicing", entity="invoice", name="due_date", shape=FieldShape.TIMESTAMP
)
STATUS = ConditionField(
    connector="invoicing", entity="invoice", name="status", shape=FieldShape.STATUS
)
FIELDS = {DUE.key: DUE, STATUS.key: STATUS}


def an_agent(*tools: str) -> AgentRecord:
    return AgentRecord(
        agent_id="quote_helper",
        display_name="Quote helper",
        persona="Answers pricing questions.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset(tools),
        ),
        created_by="u_builder",
    )


def a_person(pid: str = "u_author") -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
    )


def a_reach(pid: str = "u_author") -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=(
            Grant(capability=AUTOMATION_AUTHORITY, scope=Scope.unrestricted()),
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
    )


def written(**changes: object) -> Authored:
    """One valid automation from words, with whatever a test wants different."""
    values: dict[str, object] = {
        "name": "I check each morning whether any invoice is overdue",
        "instruction": "Look at the invoices and tell me which are overdue by more than a week.",
        "guards": "Without it an overdue invoice is found when the client chases, not by us.",
        "trigger": TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY),
        "tools": ("search_invoices",),
        "condition": None,
    }
    values.update(changes)
    return Authored(**values)  # type: ignore[arg-type]


# ------------------------------------------------------------------ the condition


def test_a_timestamp_is_over_when_it_is_further_back_than_the_days_and_not_otherwise() -> None:
    """The example the owner gave: an invoice more than seven days overdue. Delete this and a
    condition can hold for an invoice six days late, or fail for one eight days late."""
    over = Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")
    eight_days = (NOW - timedelta(days=8)).isoformat()
    six_days = (NOW - timedelta(days=6)).isoformat()

    assert over.holds(eight_days, now=NOW) is Verdict.HOLDS
    assert over.holds(six_days, now=NOW) is Verdict.DOES_NOT_HOLD
    assert over.holds(NOW - timedelta(days=7), now=NOW) is Verdict.DOES_NOT_HOLD


def test_under_and_within_read_the_same_instant_the_other_way_and_either_side() -> None:
    """Is under means recent, within means near in either direction. Delete this and a date in the
    future satisfies is-under, or a date a week ahead is not within seven days."""
    under = Condition(field=DUE.key, op=ConditionOp.IS_UNDER, value="7")
    within = Condition(field=DUE.key, op=ConditionOp.WITHIN_DAYS, value="7")
    recent = NOW - timedelta(days=2)
    ahead = NOW + timedelta(days=6)

    assert under.holds(recent, now=NOW) is Verdict.HOLDS
    assert under.holds(ahead, now=NOW) is Verdict.DOES_NOT_HOLD
    assert under.holds(NOW - timedelta(days=9), now=NOW) is Verdict.DOES_NOT_HOLD
    assert within.holds(ahead, now=NOW) is Verdict.HOLDS
    assert within.holds(NOW - timedelta(days=6), now=NOW) is Verdict.HOLDS
    assert within.holds(NOW + timedelta(days=8), now=NOW) is Verdict.DOES_NOT_HOLD


def test_text_is_compared_without_case_and_contains_searches_inside() -> None:
    """A status a source capitalises differently is the same status. Delete this and equals is
    case-sensitive, or contains is a whole-value match."""
    equals = Condition(field=STATUS.key, op=ConditionOp.EQUALS, value="Overdue")
    contains = Condition(field=STATUS.key, op=ConditionOp.CONTAINS, value="over")

    assert equals.holds("OVERDUE", now=NOW) is Verdict.HOLDS
    assert equals.holds("paid", now=NOW) is Verdict.DOES_NOT_HOLD
    assert contains.holds("Overdue by a week", now=NOW) is Verdict.HOLDS
    assert contains.holds("paid", now=NOW) is Verdict.DOES_NOT_HOLD


def test_a_missing_or_unreadable_fact_cannot_be_told_and_is_never_a_yes() -> None:
    """The fail-safe half: a run that cannot read the field does not go ahead on a guess. Delete
    this and a source that omits a date satisfies is-over."""
    over = Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")
    equals = Condition(field=STATUS.key, op=ConditionOp.EQUALS, value="overdue")

    assert over.holds(None, now=NOW) is Verdict.CANNOT_TELL
    assert over.holds("not a date", now=NOW) is Verdict.CANNOT_TELL
    assert over.holds("2031-01-01T00:00:00", now=NOW) is Verdict.CANNOT_TELL  # naive
    assert over.holds(42, now=NOW) is Verdict.CANNOT_TELL
    assert equals.holds(None, now=NOW) is Verdict.CANNOT_TELL
    assert equals.holds(7, now=NOW) is Verdict.CANNOT_TELL


def test_a_condition_measured_in_days_needs_whole_days_and_a_field_needs_three_names() -> None:
    """Delete this and a condition can say 'seven' or 'minus two' days, or name a field no source
    could report."""
    with pytest.raises(GalleryError):
        Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="seven")
    with pytest.raises(GalleryError):
        Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="0")
    with pytest.raises(GalleryError):
        Condition(field="due_date", op=ConditionOp.EQUALS, value="x")
    with pytest.raises(GalleryError):
        Condition(field=STATUS.key, op=ConditionOp.EQUALS, value="  ")
    assert Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7").days() == 7


def test_each_shape_offers_only_the_comparisons_that_mean_something_for_it() -> None:
    """Delete this and a status can be asked whether it is within days of now, or a date whether it
    contains a word."""
    assert ops_for(FieldShape.STATUS) == (ConditionOp.EQUALS,)
    assert ops_for(FieldShape.LABEL) == (ConditionOp.EQUALS, ConditionOp.CONTAINS)
    assert ops_for(FieldShape.TIMESTAMP) == (
        ConditionOp.IS_OVER,
        ConditionOp.IS_UNDER,
        ConditionOp.WITHIN_DAYS,
    )
    assert set(ConditionOp) == {op for shape in FieldShape for op in ops_for(shape)}


def test_a_condition_is_said_in_words_with_the_field_as_a_person_reads_it() -> None:
    """Delete this and the card says a key where a person expects a sentence."""
    over = Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")

    assert over.words() == "only when the invoice due date (invoicing) is more than 7 days ago"
    assert over.words(DUE.label) == over.words()


def test_a_condition_the_connector_does_not_report_is_refused_in_words() -> None:
    """Delete this and a condition names a field nothing reports, so it can never be decided. The
    sibling shows a field that is reported is accepted."""
    unknown = Condition(field="invoicing.invoice.nothing", op=ConditionOp.EQUALS, value="x")
    wrong_way = Condition(field=STATUS.key, op=ConditionOp.IS_OVER, value="7")
    fine = Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")

    assert module.condition_gaps(unknown, FIELDS)
    assert module.condition_gaps(wrong_way, FIELDS)
    assert module.condition_gaps(fine, FIELDS) == ()


# ------------------------------------------------------------------ the trigger


def test_a_trigger_carries_exactly_the_one_fact_its_kind_needs() -> None:
    """The same rule as `unattended.Trigger`, held here too. Delete this and a webhook can be
    saved with a cadence nothing reads, or a schedule with nothing to say when."""
    assert TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY).fires
    assert not TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid").fires
    assert not TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="invoicing").fires
    with pytest.raises(GalleryError):
        TriggerChoice(kind=TriggerKind.SCHEDULE)
    with pytest.raises(GalleryError):
        TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY, source="invoicing")
    with pytest.raises(GalleryError):
        TriggerChoice(kind=TriggerKind.WEBHOOK, cadence=DAILY, source="invoice_paid")
    with pytest.raises(GalleryError):
        TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT)
    with pytest.raises(GalleryError):
        TriggerChoice(kind=TriggerKind.WEBHOOK, source="Not A Name")


def test_each_trigger_kind_is_said_differently_in_words() -> None:
    """Delete this and the card cannot tell a person which kind they chose."""
    assert TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY).words() == (
        "Runs every day at 07:00 UTC"
    )
    assert (
        "changes in invoicing"
        in TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="invoicing").words()
    )
    assert (
        "called from outside"
        in TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid").words()
    )


# ------------------------------------------------------------------ what was written


def test_what_a_person_wrote_is_checked_against_the_agent_and_every_finding_comes_back() -> None:
    """A form is edited and not debugged, so all the findings arrive at once. Delete this and the
    first problem hides the second. The sibling is the same words made valid."""
    with pytest.raises(AuthoringRefusedError) as raised:
        compose(
            agent=an_agent("search_invoices"),
            name="when invoice then send",
            instruction="short",
            guards="no",
            trigger=TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY),
            tools=("send_email",),
            condition=Condition(
                field="invoicing.invoice.nothing", op=ConditionOp.EQUALS, value="x"
            ),
            fields=FIELDS,
        )

    findings = " ".join(raised.value.findings)
    assert "send_email" in findings  # a tool the agent's ceiling does not allow
    assert "field none of this install" in findings
    assert "instruction" in findings.lower()
    assert len(raised.value.findings) >= 4

    built = compose(
        agent=an_agent("search_invoices"),
        name="I check each morning whether any invoice is overdue",
        instruction="Look at the invoices and tell me which are overdue.",
        guards="Without it an overdue invoice is found when the client chases.",
        trigger=TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY),
        tools=("search_invoices",),
        condition=Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7"),
        fields=FIELDS,
    )
    assert built.task == AUTHORED_TASK
    assert built.template_id is None


def test_a_tool_the_agent_may_not_use_cannot_be_named_and_naming_one_it_may_is_fine() -> None:
    """Naming a tool grants nothing, so the only protection is that it is refused unless the
    agent's own ceiling allows it. Delete this and an automation names a tool its agent cannot
    use, and the run is the first to find out."""
    agent = an_agent("search_invoices")

    assert module.tool_gaps(("send_email",), agent)
    assert module.tool_gaps(("search_invoices",), agent) == ()
    assert module.tool_gaps((), agent) == ()


def test_a_template_start_takes_its_task_and_its_words_and_a_person_may_change_the_rest() -> None:
    """The start from a named outcome. Delete this and a template-based automation runs the
    instruction task, which this install cannot perform, instead of the template's own."""
    template = BUILT_IN[0]
    built = compose(
        agent=an_agent(),
        name=template.name,
        instruction=template.summary,
        guards=template.guards,
        trigger=TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY),
        tools=(),
        condition=None,
        fields={},
        template=template,
    )

    assert built.task == template.task
    assert built.template_id == template.template_id
    assert built.trigger.cadence == DAILY != template.cadence


def test_an_outcome_named_as_wiring_is_refused_by_the_gallerys_own_rule() -> None:
    """The name rule is the gallery's, and an authored automation does not get round it. Delete
    this and a person can name an automation as a trigger and an action."""
    with pytest.raises(AuthoringRefusedError):
        written(name="When an invoice arrives, then send an email")


# ------------------------------------------------------------------ the confirmation


def test_the_confirmation_changes_with_every_term_and_not_with_the_clock() -> None:
    """The digest covers what the person agrees to and leaves the rehearsal out, which moves with
    the clock. Delete this and either a changed term is not noticed, or a confirmation goes stale
    every hour."""
    agent = an_agent("search_invoices")
    base = preview(written(), agent, author=a_person(), author_reach=a_reach())
    same = preview(written(), agent, author=a_person(), author_reach=a_reach())

    assert base.confirmation == same.confirmation
    for changed in (
        written(instruction="Look at the invoices and tell me which are overdue by ten days."),
        written(tools=()),
        written(trigger=TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=Cadence(Every.DAY, 8))),
        written(trigger=TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid")),
        written(condition=Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")),
        written(guards="Without it an invoice that is overdue is found late, by a client."),
    ):
        other = preview(changed, agent, author=a_person(), author_reach=a_reach())
        assert other.confirmation != base.confirmation, changed
    assert (
        preview(
            written(), agent, author=a_person("u_other"), author_reach=a_reach("u_other")
        ).confirmation
        != base.confirmation
    )


def test_a_preview_is_for_the_author_whose_reach_it_was_handed() -> None:
    """Delete this and one person is shown a reach computed from another's grants."""
    with pytest.raises(GalleryError):
        preview(written(), an_agent(), author=a_person("u_author"), author_reach=a_reach("u_other"))


def test_an_authored_automation_is_written_paused_as_its_author_with_its_registry_entry() -> None:
    """The gallery's rules, kept: the author is the principal and there is no next run. Delete this
    and writing the words yourself becomes the way round the approval a start needs. The sibling
    is a stale confirmation, refused."""
    agent = an_agent("search_invoices")
    shown = preview(written(), agent, author=a_person(), author_reach=a_reach())

    made = authoring_of(shown, confirmation=shown.confirmation, automation_id="auto_new")

    assert made.installation.automation.next_run_at is None
    assert made.installation.automation.runs_as.id == "u_author"
    assert made.installation.template_id == AUTHORED_TEMPLATE
    assert made.installation.entry.next_run_at is None
    assert made.installation.entry.guards == written().guards.strip()
    with pytest.raises(NotConfirmedError):
        authoring_of(shown, confirmation="0" * 64, automation_id="auto_new")


def test_an_automation_may_be_written_only_by_whoever_holds_the_authority_over_it() -> None:
    """Delete this and the tab's read is enough to write. The authority's scope is asked of the
    agent, the task and the person."""
    on_other = EntitlementSet(
        principal_id="u_author",
        grants=(
            Grant(
                capability=AUTOMATION_AUTHORITY,
                scope=Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value="other"),)),
            ),
        ),
    )
    nothing = EntitlementSet(principal_id="u_author", grants=())

    assert not may_author("quote_helper", AUTHORED_TASK, nothing)
    assert not may_author("quote_helper", AUTHORED_TASK, on_other)
    assert not may_author("quote_helper", AUTHORED_TASK, a_reach())  # the tab is not readable


def test_no_intersection_is_computed_in_the_module() -> None:
    """The one place a reach is computed is `flow_reach`. Delete this and a second copy of the
    central rule can arrive here."""
    assert intersections_in(inspect.getsource(module)) == ()


# ------------------------------------------------------------------ the rehearsal


def test_a_schedule_is_rehearsed_at_its_last_slots_and_writes_and_sends_nothing() -> None:
    """Three earlier triggers, newest first, each saying what the agent would have been told and
    that nothing was written. Delete this and the rehearsal shows nothing a person can judge."""
    lines = rehearse(written(), reach_words=("read:client.name",), now=NOW)

    assert len(lines) == REHEARSED_TRIGGERS
    assert [one.at for one in lines] == sorted((one.at for one in lines), reverse=True)  # type: ignore[type-var]
    assert all(one.at is not None and one.at < NOW for one in lines)
    for one in lines:
        assert "Look at the invoices" in one.says
        assert "search_invoices" in one.says
        assert "read:client.name" in one.says
        assert one.says.endswith(NOTHING_WAS_WRITTEN_OR_SENT)
        assert one.verdict is None


def test_a_rehearsal_says_when_it_would_have_reached_nothing_and_when_it_used_no_tools() -> None:
    """Delete this and an empty reach reads as a rehearsal that found nothing to do."""
    lines = rehearse(written(tools=()), reach_words=(), now=NOW)

    assert "reached nothing" in lines[0].says
    assert "no tools" in lines[0].says


def test_a_condition_a_rehearsal_cannot_decide_says_so_and_one_it_can_decides() -> None:
    """A rehearsal never reads a live record: with no facts the condition cannot be told, and with
    a fact it is decided at each slot. Delete this and a rehearsal quietly claims a condition held,
    or quietly skips what it could not read."""
    with_condition = written(condition=Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7"))

    unread = rehearse(with_condition, reach_words=(), now=NOW, fields=FIELDS)
    old = rehearse(
        with_condition,
        reach_words=(),
        now=NOW,
        fields=FIELDS,
        facts={DUE.key: "2000-01-01T00:00:00+00:00"},
    )
    recent = rehearse(
        with_condition, reach_words=(), now=NOW, fields=FIELDS, facts={DUE.key: NOW.isoformat()}
    )

    assert {one.verdict for one in unread} == {Verdict.CANNOT_TELL}
    assert "cannot be told" in unread[0].says
    assert {one.verdict for one in old} == {Verdict.HOLDS}
    assert {one.verdict for one in recent} == {Verdict.DOES_NOT_HOLD}
    assert "would not have run" in recent[0].says
    assert "Look at the invoices" not in recent[0].says


def test_a_trigger_that_is_not_a_schedule_has_no_history_and_does_not_invent_one() -> None:
    """Delete this and a webhook is rehearsed at times it was never called."""
    lines = rehearse(
        written(trigger=TriggerChoice(kind=TriggerKind.WEBHOOK, source="invoice_paid")),
        reach_words=(),
        now=NOW,
    )

    assert len(lines) == 1
    assert lines[0].at is None
    assert "no earlier triggers" in lines[0].says


def test_the_slots_are_the_mirror_of_the_next_run_and_a_weekly_cadence_finds_last_weeks() -> None:
    """Delete this and the rehearsal replays slots the scheduler would never have used."""
    friday = Cadence(every=Every.WEEK, hour_utc=15, weekday=4)
    slots = slots_before(friday, NOW, 3)

    assert [one.weekday() for one in slots] == [4, 4, 4]
    assert slots[0] - slots[1] == timedelta(days=7)
    assert all(one < NOW for one in slots)
    weekdays = slots_before(Cadence(every=Every.WEEKDAY, hour_utc=9), NOW, 10)
    assert all(one.weekday() < 5 for one in weekdays)
    assert len(set(weekdays)) == 10
    exact = NOW.replace(hour=7)
    assert slots_before(DAILY, exact, 1)[0] == exact - timedelta(days=1)
    with pytest.raises(Exception, match="naive"):
        slots_before(DAILY, datetime(2031, 3, 14, 12, 0), 1)


# ------------------------------------------------------------------ the run side


def test_the_instruction_task_is_declared_and_says_what_it_still_needs() -> None:
    """An instruction cannot be run yet and the install says so: it is declared unbuilt, so a
    start is refused in words rather than scheduled to fail. Delete this and either the task has
    no declaration, or it reads as runnable and every run is a failure."""
    declared = [one for one in TASKS if one.task == INSTRUCTION_TASK]

    assert INSTRUCTION_TASK == AUTHORED_TASK
    assert len(declared) == 1
    assert not declared[0].runnable
    assert task_gaps() == ()


def test_a_trigger_nothing_fires_says_so_in_the_one_sentence() -> None:
    """Delete this and the card's sentence about a trigger that cannot start drifts from the
    module's."""
    assert "cannot be started" in NOTHING_FIRES_THIS_YET


# ------------------------------------------------------------------ reading a row back


class Row:
    """The columns of one stored row, as the ORM row carries them."""

    def __init__(self, **values: object) -> None:
        defaults: dict[str, object] = {
            "template_id": AUTHORED_TEMPLATE,
            "name": "I check each morning whether any invoice is overdue",
            "guards": "Without it an overdue invoice is found when the client chases.",
            "task": AUTHORED_TASK,
            "trigger_kind": "schedule",
            "trigger_source": None,
            "cadence_every": "day",
            "cadence_hour": 7,
            "cadence_weekday": None,
            "condition_field": DUE.key,
            "condition_op": "is_over",
            "condition_value": "7",
            "instruction": "Look at the invoices and tell me which are overdue.",
            "tools": ["search_invoices"],
            "from_template_id": None,
        }
        defaults.update(values)
        self.__dict__.update(defaults)


def test_a_stored_row_reads_back_as_what_was_written_and_a_template_row_reads_as_none() -> None:
    """Delete this and what the card says about a stored automation is not what its owner wrote."""
    one = authored_from_row(Row())  # type: ignore[arg-type]

    assert one is not None
    assert one.trigger == TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=DAILY)
    assert one.condition == Condition(field=DUE.key, op=ConditionOp.IS_OVER, value="7")
    assert one.tools == ("search_invoices",)
    assert authored_from_row(Row(template_id="weekly_work_summary")) is None  # type: ignore[arg-type]
    webhook = authored_from_row(
        Row(  # type: ignore[arg-type]
            trigger_kind="webhook",
            trigger_source="invoice_paid",
            cadence_every=None,
            cadence_hour=None,
            condition_field=None,
            condition_op=None,
            condition_value=None,
        )
    )
    assert webhook is not None and webhook.trigger.source == "invoice_paid"
    assert replace(one, tools=()).tools == ()


def test_a_row_whose_columns_could_not_have_come_from_the_form_is_refused_not_drawn() -> None:
    """The second place the rules are held, after the database's. Delete this and a hand-edited
    row is drawn on the card as if it were sound."""
    for bad in (
        Row(trigger_kind="telepathy"),
        Row(instruction="short"),
        Row(cadence_every="fortnight"),
        Row(condition_op="matches_regex"),
    ):
        with pytest.raises((ValueError, GalleryError)):
            authored_from_row(bad)  # type: ignore[arg-type]
