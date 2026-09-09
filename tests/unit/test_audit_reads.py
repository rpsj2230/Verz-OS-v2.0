"""The read log: the declared set, the refusals, who may read it and how long it is kept.

Needs Rupash item 45, Option A. Every test here is about one of the four things that make a
read log a smaller disclosure than the thing it is auditing, and every one of them is a rule a
future edit could quietly relax.

The dates are 2019, deliberately and for the reason `tests/unit/test_scope_and_capability.py`
gives: nothing here is about the present, and a fixture with a plausible date in it is a clock
that goes off on a day nobody chose.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import FIELD_NAME, REDACTED, AuditAction, AuditChain
from brain.audit.reads import (
    READ_LOG_CAPABILITY,
    READ_LOG_RETENTION_DAYS,
    WRITTEN_DOWN,
    LoggedRead,
    ReadLogError,
    may_read_a_read_entry,
    read_details,
    read_log_gaps,
    written_down_because,
)
from brain.audit.record import AuditRecorder
from brain.audit.view import AUDIT_NOUN, CAPABILITY_BY_KIND, AuditFilter, AuditView
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.member_activity import MemberError, ReadsOfMyRecord, who_read_my_record
from brain.ops.retention import METADATA_LEDGER_RETENTION_DAYS, TRACE_RETENTION_DAYS

NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)
ENT = "b" * 32


def a_recorder(actor_id: str = "u_reader") -> tuple[AuditRecorder, AuditChain]:
    chain = AuditChain()
    ticks = iter(NOW + timedelta(minutes=i) for i in range(200))
    return (
        AuditRecorder(
            chain,
            actor_id=actor_id,
            ent_hash=ENT,
            trace_id="trace1",
            clock=lambda: next(ticks),
        ),
        chain,
    )


def reader_holding(*values: str, principal_id: str = "u_subject") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted()) for one in values
        ),
    )


# ------------------------------------------------------------------ the declared set
def test_the_written_down_set_is_personnel_and_a_salary_and_nothing_else() -> None:
    """The whole of Option A, pinned. Item 45 says personnel records and anything carrying a
    salary, and nothing else; the difference between that and Option B is this tuple.

    Delete this and the set can grow by one convenient entry at a time with nothing failing,
    which is precisely how a narrow read log becomes a log of every read of every row. The
    argument per entry is asserted too, because an entry nobody can weigh is one that gets
    added without being weighed."""
    assert {one.name for one in WRITTEN_DOWN} == {"personnel", "salary"}
    assert len(WRITTEN_DOWN) == 2
    for one in WRITTEN_DOWN:
        assert one.because.strip(), one.name
        assert len(one.because) > 100, one.name


def test_every_declared_reason_survives_the_ledgers_own_redaction() -> None:
    """A reason recorded as the marker is a ledger row saying a read happened and not why.

    `brain.audit.ledger.redact_details` admits field names and reduces everything else to
    `<redacted>`, so a declaration named `Personnel Records` would be stored as the marker and
    the entry would carry nothing. Delete this and the first declaration somebody writes with
    a capital letter or a space is silently unrecordable."""
    for one in WRITTEN_DOWN:
        assert re.match(FIELD_NAME, one.name), one.name
        assert REDACTED not in str(read_details((one.name,), entity="personnel"))


def test_an_ordinary_read_is_not_written_down() -> None:
    """The negative half of Option A, and the one that keeps the log affordable.

    Delete this and `written_down_because` could return a reason for everything, which is
    Option B with Option A's docstring on it."""
    assert written_down_because("client", ("name", "contract_value")) == ()


def test_a_read_of_a_personnel_record_is_written_down_whatever_it_showed() -> None:
    """The positive sibling of the test above, per CLAUDE.md: a guard tested only by its
    refusals is satisfied by a function that refuses everything.

    Delete this and `written_down_because` could return nothing at all and every refusal test
    in this file would still pass."""
    assert written_down_because("personnel", ("name",)) == ("personnel",)


def test_a_salary_writes_the_read_down_whatever_record_type_carried_it() -> None:
    """The reason the salary entry is declared as a field and not as a record type. Pay
    appears on payroll rows and on per-person budget lines, and a rule written only against
    the personnel type would miss every one of those while looking complete.

    Delete this and the field declaration could be read as an entity declaration with nothing
    failing, so every salary outside a personnel record would be read with no entry."""
    assert written_down_because("payroll_run", ("salary",)) == ("salary",)
    assert written_down_because("personnel", ("name", "salary")) == ("personnel", "salary")


def test_a_salary_the_reader_was_never_shown_is_not_a_salary_read() -> None:
    """`WHAT_WAS_SHOWN_IS_THE_READ_AND_WHAT_THE_RECORD_HOLDS_IS_NOT`. The redactor removes
    fields this caller may not see before the record reaches them, so membership decided on
    the source would write down a disclosure that did not happen.

    Delete this and the log over-reports, and the person it is written for is told a colleague
    saw their pay when the mask had taken it out. A log that over-reports is one nobody
    believes."""
    assert written_down_because("payroll_run", ("employee_id",)) == ()


def test_widening_the_declared_set_is_one_line_and_takes_effect_immediately() -> None:
    """Item 45 asks for a set that is his to widen. This is the property that makes that
    claim true rather than aspirational: a third `LoggedRead` changes behaviour with no other
    edit anywhere.

    Delete this and `written_down_because` could ignore the table it is handed and read the
    module constant instead, so widening would look like an edit and do nothing."""
    wider = (
        *WRITTEN_DOWN,
        LoggedRead(
            name="medical",
            entity="medical",
            because=(
                "a third entry, written exactly as a fourth would be, to prove that widening "
                "the set really is one reviewable line and not a change spread over modules"
            ),
        ),
    )
    assert written_down_because("medical", ("note",), declared=wider) == ("medical",)
    assert written_down_because("medical", ("note",)) == ()


def test_removing_a_declaration_stops_the_read_being_written_down() -> None:
    """The other direction of the same property, and the one that says the tuple is really
    the source of truth rather than a decoration beside a hard-coded rule.

    Delete this and a branch could be added that logs personnel reads regardless of the
    table, so narrowing the set would silently do nothing."""
    without_personnel = tuple(one for one in WRITTEN_DOWN if one.name != "personnel")
    assert written_down_because("personnel", ("name",), declared=without_personnel) == ()


def test_a_declaration_that_names_neither_an_entity_nor_a_field_is_refused() -> None:
    """A `LoggedRead` with both empty matches every read there has ever been, which is Option
    B arriving in a row that looks like a typo.

    Delete this and the whole set can be widened to everything by leaving two fields out."""
    with pytest.raises(ReadLogError, match="every read there has ever been"):
        LoggedRead(name="everything", because="x" * 40)


def test_a_declaration_that_names_both_an_entity_and_a_field_is_refused() -> None:
    """Two rules sharing one argument, and one of them unreviewed. The `because` a reviewer
    reads would be about the entity while the field half did something else.

    Delete this and a declaration can carry a rule nobody argued for."""
    with pytest.raises(ReadLogError, match="exactly one of them is the claim"):
        LoggedRead(name="both", entity="personnel", field="salary", because="x" * 40)


def test_a_declaration_with_no_argument_is_refused() -> None:
    """`brain.ops.retention.Horizon` requires a reason for the same reason: an entry nobody
    can weigh is one that gets added without being weighed, and the set then grows by
    accretion rather than by decision.

    Delete this and `WRITTEN_DOWN` can acquire entries with no argument at all."""
    with pytest.raises(ReadLogError, match="states no reason"):
        LoggedRead(name="quiet", entity="personnel", because="   ")


# ------------------------------------------------------ what an entry may and may not say
def test_a_read_entry_names_the_kind_of_record_and_nothing_the_reader_was_shown() -> None:
    """`AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN`. The row says what
    was read and never what came back.

    Delete this and `record_read` can pass `disclosed` straight into the details, where it
    would survive redaction intact because field names are exactly what the ledger admits."""
    recorder, chain = a_recorder()
    recorder.record_read(
        subject_id="u_subject", entity="personnel", disclosed=("name", "salary", "start_date")
    )
    entry = chain.entries[-1]
    assert entry.details == {"record_kind": "personnel"}
    assert "start_date" not in str(entry.details)


def test_two_readers_shown_different_fields_leave_identical_entries() -> None:
    """The property the test above protects, stated as the thing a person reading their own
    log would otherwise learn: that the second reader was refused something.

    **This test found a defect in the first version of this module**, which recorded the
    declared reasons that matched. Two readers of one personnel record then left
    `personnel,salary` and `personnel`, which is the same subtraction as listing the fields
    with fewer words, and the constant claiming the leak was closed sat two functions away.

    Delete this and an entry can carry the shape of one reader's answer again, in whatever
    form is convenient, and comparing two rows hands the subject a fact about a colleague's
    reach."""
    recorder, chain = a_recorder()
    recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=("name", "salary"))
    recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=("name",))
    first, second = chain.entries[-2], chain.entries[-1]
    assert first.details == second.details


def test_a_record_the_reader_was_shown_nothing_of_is_not_a_read() -> None:
    """`A_RECORD_NOBODY_WAS_SHOWN_WAS_NOT_READ`. The redactor drops a record whose fields the
    caller may not see, so a read can end with nothing disclosed, and an entity declaration
    would otherwise match it on the type alone.

    Delete this and a refusal is written onto the subject's own page as a disclosure: the one
    page in the system where somebody would read 'u_x read my personnel record' about a person
    who was shown none of it."""
    assert written_down_because("personnel", ()) == ()
    recorder, chain = a_recorder()
    with pytest.raises(ReadLogError, match="has no entry to write"):
        recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=())
    assert chain.entries == ()


def test_a_read_outside_the_declared_set_writes_nothing_and_says_so() -> None:
    """`AN_ORDINARY_READ_IS_REFUSED_AND_NEVER_WRITTEN_QUIETLY`. A recorder that returned
    quietly would be a general read log with a filter in front of it, and it would look
    exactly like a recorder nobody had wired up.

    Delete this and the refusal can be replaced by a silent return, after which the set is a
    suggestion."""
    recorder, chain = a_recorder()
    with pytest.raises(ReadLogError, match="has no entry to write"):
        recorder.record_read(subject_id="u_subject", entity="client", disclosed=("name",))
    assert chain.entries == ()


def test_a_reason_that_is_not_declared_cannot_be_written_into_an_entry() -> None:
    """`read_details` is the last door, and it is shut from the inside. Without it the reason
    list is a channel: field names survive `redact_details` untouched, so anything shaped like
    one would be recorded.

    Delete this and an entry can carry whatever a caller calls a reason."""
    with pytest.raises(ReadLogError, match="are not declared reasons"):
        read_details(("salary", "contract_value"), entity="personnel")


def test_a_record_kind_that_is_not_name_shaped_is_refused() -> None:
    """A value the ledger reduces to `<redacted>` produces a row saying a record of a kind
    somebody hid was read, which is a more alarming statement than the truth and is not a
    statement anybody can act on.

    Delete this and the one detail an entry carries can arrive as the marker."""
    with pytest.raises(ReadLogError, match="is not a record kind"):
        read_details(("personnel",), entity="Personnel Records")


def test_no_value_from_the_record_reaches_a_read_entry() -> None:
    """The canary, inverted like `test_no_canary_value_survives_into_an_entry`: it fails if
    the data arrives. A read entry is written on the path where a whole personnel record was
    just in memory, which is the worst possible moment for a details mapping to be permissive.

    Delete this and the one action that fires while somebody's salary is on the stack has no
    test asserting the salary stayed off the ledger."""
    recorder, chain = a_recorder()
    recorder.record_read(
        subject_id="u_subject", entity="personnel", disclosed=("name", "salary"), agent_id="hr_desk"
    )
    text = str(chain.entries[-1].model_dump())
    for canary in ("123456", "$", "Wei", "wei ling"):
        assert canary not in text


def test_an_agent_is_recorded_and_an_absent_one_leaves_no_marker() -> None:
    """The leaf asks which *agents* read the record, so the agent has to be on the row; and a
    read a person made at a console has no agent, which must read as absence rather than as
    `<redacted>`.

    Delete this and the agent can stop being recorded, which loses the leaf, or an empty one
    can be attached, which tells every reader that an agent's name was hidden from them."""
    recorder, chain = a_recorder()
    recorder.record_read(
        subject_id="u_subject", entity="personnel", disclosed=("name",), agent_id="hr_desk"
    )
    recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=("name",))
    assert chain.entries[-2].details["agent"] == "hr_desk"
    assert "agent" not in chain.entries[-1].details


def test_an_agent_id_that_is_not_slug_shaped_is_refused_rather_than_stored_as_a_marker() -> None:
    """A value the ledger would reduce to `<redacted>` produces a row reading as an agent
    whose name was hidden, which is a different and more alarming statement than the truth.

    Delete this and a malformed agent id is recorded as a redaction marker on somebody's
    personal page."""
    with pytest.raises(ReadLogError, match="is not an agent id"):
        read_details(("personnel",), entity="personnel", agent_id="HR Desk")


def test_a_read_entry_with_no_subject_is_refused() -> None:
    """The subject is how the person the record is about ever sees the row: `brain.audit.view`
    admits them by matching their own principal. A blank subject is a row nobody can find that
    still says somebody's record was read.

    Delete this and reads can be filed under an empty principal, where they are invisible to
    the one person the feature exists for."""
    recorder, _chain = a_recorder()
    with pytest.raises(ReadLogError, match="no subject"):
        recorder.record_read(subject_id="   ", entity="personnel", disclosed=("name",))


def test_a_read_entry_chains_and_verifies_like_every_other_entry() -> None:
    """The tenth action is written through the same seam as the other nine, so the chain has
    to hold across it. A member the chain could not carry would be a rule with no mechanism.

    Delete this and `record_read` could bypass `_write` and append something the walk
    rejects, which would break every verification run rather than only the read log."""
    recorder, chain = a_recorder()
    recorder.grant(principal_id="u_subject", capability=Capability(value="read:personnel.name"))
    recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=("name", "salary"))
    assert chain.verify() is None
    assert chain.entries[-1].action is AuditAction.RECORD_READ


# --------------------------------------------------------------- who may read the read log
def a_chain_with_one_read_and_one_grant() -> AuditChain:
    recorder, chain = a_recorder(actor_id="u_hr")
    recorder.grant(principal_id="u_subject", capability=Capability(value="read:personnel.name"))
    recorder.record_read(
        subject_id="u_subject", entity="personnel", disclosed=("name", "salary"), agent_id="hr_desk"
    )
    return chain


def actions_seen(chain: AuditChain, reader: EntitlementSet) -> set[AuditAction]:
    page = AuditView(chain.entries, reader=reader, now=NOW).page(AuditFilter())
    return {row.action for row in page.rows}


def test_the_person_the_record_is_about_always_sees_who_read_it() -> None:
    """The whole of M40.4.2.4 at the visibility layer, and the rule that needs no grant: a
    person may always read their own audit trail.

    Delete this and the read log can be made to require a capability the subject does not
    hold, which is a feature that answers everybody's question except the one it was built
    for."""
    seen = actions_seen(a_chain_with_one_read_and_one_grant(), reader_holding())
    assert AuditAction.RECORD_READ in seen


def test_holding_the_audit_wildcard_does_not_reach_somebody_elses_read_log() -> None:
    """`THE_READ_LOG_ANSWERS_TO_ITS_OWN_NOUN_SO_NO_AUDIT_WILDCARD_REACHES_IT`, and the
    obvious wrong answer item 45 warns about. A read entry's subject kind is `principal`, so
    without a rule of its own every holder of `read:audit.principal` acquires the read log on
    the day it ships, with nobody having granted it.

    Delete this and the narrowing can be removed with the whole suite green, because every
    other audit test uses a reader who holds the wildcard and expects to see everything."""
    chain = a_chain_with_one_read_and_one_grant()
    wildcard = reader_holding(f"read:{AUDIT_NOUN}.*", principal_id="u_auditor")
    seen = actions_seen(chain, wildcard)
    assert AuditAction.GRANT in seen
    assert AuditAction.RECORD_READ not in seen


def test_the_capability_that_opens_the_audit_page_does_not_open_the_read_log() -> None:
    """**A mutation found this and it is the hole the whole noun decision exists to close.**

    Renaming `READ_LOG_NOUN` to `audit` passed every test in this file. The two written for
    the narrowing both ask about the wildcard, `read:audit.*`, and a wildcard covers children
    rather than the parent, so neither could tell the two nouns apart. The reader who would
    actually acquire the log is the one holding the bare noun.

    That reader is not hypothetical. `brain.identity.staff_sync.AUDIT_PAGE_CAPABILITY` is
    `read:audit` and it is what opens the Activity screen, so as of 2026-09-10 every
    department head holds it. Had the noun been a child of `audit`, shipping this module would
    have handed all of them everybody's read log, with nobody having granted it.

    Asserted against the capability the other module actually declares rather than against a
    string built here, so this stays true if that page's capability is renamed.

    Delete this and the noun can move into the audit family, which is the one change that
    would give the read log away silently."""
    from brain.identity.staff_sync import AUDIT_PAGE_CAPABILITY

    assert AUDIT_PAGE_CAPABILITY.value == f"read:{AUDIT_NOUN}"
    assert not AUDIT_PAGE_CAPABILITY.covers(READ_LOG_CAPABILITY)
    assert READ_LOG_CAPABILITY.value != AUDIT_PAGE_CAPABILITY.value

    chain = a_chain_with_one_read_and_one_grant()
    page_reader = reader_holding(AUDIT_PAGE_CAPABILITY.value, principal_id="u_head")
    seen = actions_seen(chain, page_reader)

    assert AuditAction.RECORD_READ not in seen


def test_asking_the_read_log_rule_about_an_entry_that_is_not_a_read_is_refused() -> None:
    """The guard that keeps this module from becoming a second visibility rule for the rest of
    the ledger, and a mutation says nothing reached it.

    `brain.audit.view` decides who may see every other kind of entry, against a scope over the
    four fields the ledger holds. This function answers a narrower question with an extra way
    in, the subject seeing their own, and applying that to a grant or a revocation would widen
    who can read those by exactly that route. It refuses rather than falling through, because
    a caller handed False would read it as "not permitted" and a caller handed True would have
    the widening.

    Delete this and the extra way in silently applies to the whole ledger."""
    chain = a_chain_with_one_read_and_one_grant()
    not_a_read = next(one for one in chain.entries if one.action is not AuditAction.RECORD_READ)
    anybody = reader_holding(READ_LOG_CAPABILITY.value, principal_id="u_auditor")

    with pytest.raises(ReadLogError, match="is not a read entry"):
        may_read_a_read_entry(not_a_read, reader=anybody, now=NOW, row={})


def test_no_audit_capability_covers_the_read_log_capability() -> None:
    """The mechanism behind the test above, asserted on `Capability.covers` rather than on a
    view. A capability named `read:audit.read` would be covered by `read:audit.*`; a different
    noun is not, and the grammar admits no verb-level wildcard that could reach both.

    Delete this and the noun can be renamed into the audit family, which would pass every
    behavioural test written against a reader who happened not to hold the wildcard."""
    for capability in CAPABILITY_BY_KIND.values():
        assert not capability.covers(READ_LOG_CAPABILITY), capability.value
    assert not Capability(value=f"read:{AUDIT_NOUN}.*").covers(READ_LOG_CAPABILITY)
    assert READ_LOG_CAPABILITY.covers(READ_LOG_CAPABILITY)


def test_a_read_log_grant_reaches_somebody_elses_read_entries() -> None:
    """The positive sibling. A rule tested only by its refusals is satisfied by one that
    refuses everybody, and a read log nobody but the subject can read cannot answer an
    investigation.

    Delete this and the branch can be replaced by `return entry.subject == ...`, which passes
    every refusal test above."""
    chain = a_chain_with_one_read_and_one_grant()
    officer = reader_holding(READ_LOG_CAPABILITY.value, principal_id="u_officer")
    assert AuditAction.RECORD_READ in actions_seen(chain, officer)


def test_a_read_log_grant_is_narrowed_by_its_scope_like_any_other_audit_grant() -> None:
    """The scope is evaluated against the four closed fields every other audit grant uses, so
    a read-log grant can be written for named subjects and cannot be written against anything
    the ledger does not hold.

    Delete this and the read-log branch can ignore the scope entirely, turning every narrow
    grant into a company-wide one."""
    chain = a_chain_with_one_read_and_one_grant()
    narrowed = EntitlementSet(
        principal_id="u_officer",
        grants=(
            Grant(
                capability=READ_LOG_CAPABILITY,
                scope=Scope(
                    clauses=(Clause(field="subject", op=Op.EQ, value="principal:u_someone_else"),)
                ),
            ),
        ),
    )
    assert AuditAction.RECORD_READ not in actions_seen(chain, narrowed)


# ---------------------------------------------------------------------------- retention
def test_the_read_log_window_sits_between_the_trace_and_the_ledger() -> None:
    """The number is asserted against two other modules' own constants and never against
    itself, which is CLAUDE.md's rule after three authors compared a constant with an import
    of the same constant in one afternoon.

    The relation is the argument, not the figure: a read log kept as long as the trace cannot
    answer a question asked months later, and one kept as long as the metadata ledger has
    inherited an accounting period that says nothing about who looked at a personnel file.

    Delete this and 730 can become 30 or 1825 with nothing failing, which is exactly the
    inheritance the retention decision exists to refuse."""
    assert TRACE_RETENTION_DAYS < READ_LOG_RETENTION_DAYS < METADATA_LEDGER_RETENTION_DAYS
    assert READ_LOG_RETENTION_DAYS == 2 * 365


def test_the_declared_window_is_reported_as_unenforced_while_nothing_removes_an_entry() -> None:
    """The honest half. `brain.ops.retention` puts the hash chain in a class that never
    expires and `brain.tables.audit`'s trigger refuses DELETE from every role, so the two
    years is a statement rather than a control, and a reader who was not told that would
    believe the read log expires.

    Delete this and the gap goes unreported, which is the shape CLAUDE.md calls a scheduled
    control nobody calls: correct, documented, and absent from the one direction that
    matters."""
    findings = read_log_gaps(chain_expires=False)
    assert len(findings) == 2
    assert any("never expires" in one for one in findings)
    assert any("prefix" in one for one in findings)


def test_the_gap_stops_being_reported_once_something_removes_an_entry() -> None:
    """The other direction, so this is a check rather than a constant. A diagnostic that
    cannot go green is one somebody deletes rather than satisfies.

    Delete this and `read_log_gaps` can hard-code its findings, and the day retention is built
    it will still report that it is not."""
    assert read_log_gaps(chain_expires=True) == ()


# ------------------------------------------------------------------ the person's own page
def test_a_person_sees_who_read_their_own_record_and_through_which_agent() -> None:
    """M40.4.2.4 end to end, which is the question item 45 is about. Who, when, and which
    agent, off the ledger and through the view.

    Delete this and the surface can return an empty page for ever with every unit test in
    `brain.audit.reads` still green, because none of them renders one."""
    chain = a_chain_with_one_read_and_one_grant()
    page = who_read_my_record(
        chain.entries, principal_id="u_subject", reader=reader_holding(), now=NOW
    )
    assert isinstance(page, ReadsOfMyRecord)
    assert [(one.actor_id, one.agent_id, one.record_kind) for one in page.reads] == [
        ("u_hr", "hr_desk", "personnel")
    ]


def test_a_personal_read_page_shows_no_read_of_anybody_elses_record() -> None:
    """The narrowing, and the reason it is done on the input rather than on the output: the
    view then fills its page from what remains, so a short page means the end of this
    person's own reads and never that rows were taken out of it.

    Delete this and a member holding a read-log grant sees the whole company's read log on a
    page headed with their own name."""
    recorder, chain = a_recorder(actor_id="u_hr")
    recorder.record_read(subject_id="u_someone_else", entity="personnel", disclosed=("name",))
    recorder.record_read(subject_id="u_subject", entity="personnel", disclosed=("name",))
    officer = reader_holding(READ_LOG_CAPABILITY.value, principal_id="u_subject")
    page = who_read_my_record(chain.entries, principal_id="u_subject", reader=officer, now=NOW)
    assert len(page.reads) == 1


def test_a_personal_read_page_carries_no_count_of_anything() -> None:
    """The house rule that DENIED and ABSENT are indistinguishable, applied to the one page
    where a total would look most reasonable. A number beside a window over a ledger reads as
    how many times the record has been read, which is true of neither the window nor the log.

    Delete this and a `total` or a `hidden` field can be added to either value by somebody
    making the screen better, and the subtraction is back."""
    fields = set(ReadsOfMyRecord.__dataclass_fields__)
    assert fields == {"subject_id", "reads", "next_cursor"}
    assert not any(name in fields for name in ("total", "hidden", "omitted", "of_total"))


def test_a_personal_read_page_refuses_a_reach_belonging_to_somebody_else() -> None:
    """The check every other personal surface in `brain.member_activity` makes: a caller that
    passes a name in one argument and a reach in another can pass two different people, and
    the page then answers confidently for whichever the renderer believed.

    Delete this and one person's read log can be rendered under another person's heading, and
    both halves of the page are internally consistent."""
    chain = a_chain_with_one_read_and_one_grant()
    with pytest.raises(MemberError, match="belongs to"):
        who_read_my_record(
            chain.entries,
            principal_id="u_subject",
            reader=reader_holding(principal_id="u_someone_else"),
            now=NOW,
        )
