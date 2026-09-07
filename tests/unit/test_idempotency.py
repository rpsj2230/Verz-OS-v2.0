"""Doing a side-effecting thing exactly once, across a process that dies in the middle.

Almost everything here is downstream of one claim: `UNKNOWN` is a state, it is not a
synonym for `FAILED`, and the only thing that resolves it is asking the source. The tests
that pin that are the transition table's exhaustiveness, the closure over the graph, and
the crash model at the bottom of the file.

The crash model deserves its warning up front, and it is repeated on the test itself. It
does not kill a process. It enumerates the points at which one could die, constructs the
record the store would hold at each, and asserts that resuming from it never issues a
second side effect. That is at-most-once under a model rather than exactly-once under a
kill, and the difference is stated rather than glossed.

Task ids: M17.3.1, M17.3.2, M17.3.3, M17.3.4, M17.3.5
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import uuid

import pytest

from brain.connectors.contract import (
    AccessMode,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
)
from brain.connectors.manifest import (
    DIGEST_CHARS,
    ConnectorManifest,
    ManifestError,
    ToolDeclaration,
)
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import SideEffect
from brain.ops import idempotency
from brain.ops.idempotency import (
    ALLOWED_TRANSITIONS,
    KEY_CHARS,
    RESUME_PLAN,
    TERMINAL,
    Disposition,
    IdempotencyError,
    IllegalTransitionError,
    Operation,
    OperationState,
    Verification,
    advance,
    begin,
    declaration_for,
    derive_key,
    issuable_tools,
    reachable_from,
    read_only_reason,
    resume,
    state_after_call,
    state_after_verification,
    verify,
)
from brain.ops.secrets import SecretRef, VaultRole

WRITE_REF = SecretRef(path="xero/creds/rw", role=VaultRole.APPLICATION)
READ_REF = SecretRef(path="xero/creds/ro", role=VaultRole.APPLICATION)

#: A tool that can be written to: it has a side effect and it can be read back.
RAISE_INVOICE = ToolDeclaration(
    name="xero.create_invoice",
    description="Raise one invoice against a contact.",
    entity="invoice",
    side_effect=SideEffect.WRITE,
    verifies_write=True,
)

#: A tool that cannot. No side effect, so no operation is ever raised against it.
READ_INVOICE = ToolDeclaration(
    name="xero.read_invoice",
    description="One invoice by id.",
    entity="invoice",
)


def a_manifest(**overrides: object) -> ConnectorManifest:
    defaults: dict[str, object] = {
        "name": "xero",
        "version": "1.0.0",
        "transport": TransportKind.REST,
        "scope": ConnectorScope(resource_kind="tenant", selectors=("tenant_17",)),
        "credential": CredentialBinding(
            ref=WRITE_REF, mode=AccessMode.WRITE, write_granted_by="u_weiling"
        ),
        "tools": (RAISE_INVOICE, READ_INVOICE),
        "ceiling": "xero",
    }
    defaults.update(overrides)
    return ConnectorManifest(**defaults)  # type: ignore[arg-type]


def a_key(**overrides: object) -> str:
    defaults: dict[str, object] = {
        "principal_id": "p_alice",
        "tool": "xero.create_invoice",
        "intent_ref": "run_2026_09_07",
        "arguments": {"contact": "c_snm"},
    }
    defaults.update(overrides)
    return derive_key(**defaults)  # type: ignore[arg-type]


def an_operation(**overrides: object) -> Operation:
    defaults: dict[str, object] = {
        "key": a_key(),
        "connector": "xero",
        "tool": "xero.create_invoice",
        "principal_id": "p_alice",
        "intent_ref": "run_2026_09_07",
    }
    defaults.update(overrides)
    return Operation(**defaults)  # type: ignore[arg-type]


# ------------------------------------------------------------------ the key (M17.3.1)
def test_the_same_intent_derives_the_same_key_however_often_it_is_attempted() -> None:
    """The positive case, and the whole of what an idempotency key is for. Without it every
    other test here is satisfied by a function that returns a fresh random string, which is
    the exact failure the module exists to prevent."""
    first = a_key()
    second = a_key()
    assert first == second


def test_two_people_raising_the_same_invoice_derive_two_keys() -> None:
    """Delete this and the principal can be dropped from the derivation, at which point the
    second person's invoice is deduplicated against the first person's and silently never
    happens. It reads in every log as a successful idempotent retry."""
    assert a_key(principal_id="p_alice") != a_key(principal_id="p_bob")


def test_two_opposite_tools_on_the_same_arguments_derive_two_keys() -> None:
    """Delete this and the tool can be dropped, so `create_invoice` and `void_invoice` on
    one contact share a key: the void is deduplicated against the create and the invoice
    stays raised."""
    assert a_key(tool="xero.create_invoice") != a_key(tool="xero.void_invoice")


def test_two_decisions_to_do_the_same_thing_derive_two_keys() -> None:
    """The half of the intent reference that is easy to get wrong in the other direction.
    Without it, a monthly automation raising this month's invoice is deduplicated against
    last month's, so it runs once and never again, and nothing reports a failure."""
    assert a_key(intent_ref="run_september") != a_key(intent_ref="run_october")


def test_different_arguments_derive_different_keys() -> None:
    """Without the arguments in the derivation, every invoice one run raises collapses to
    one key, so the first is raised and the rest are dropped as duplicates."""
    assert a_key(arguments={"contact": "c_snm"}) != a_key(arguments={"contact": "c_other"})


def test_reordering_the_arguments_does_not_change_the_key() -> None:
    """The serialisation has to be canonical or a retry that builds its mapping in another
    order is a different key, which is a generated key with extra steps. Delete this and a
    dictionary literal reordered during a refactor duplicates a payment."""
    forwards = a_key(arguments={"contact": "c_snm", "amount": 1284})
    backwards = a_key(arguments={"amount": 1284, "contact": "c_snm"})
    assert forwards == backwards


def test_an_argument_that_names_this_attempt_is_refused() -> None:
    """The refusal that keeps the key derived. An argument called `attempt` or `now` changes
    on every retry, so the key does too and the source sees a fresh request each time.
    Delete this and the guard can be removed with every other test still green, because
    every other test passes arguments that happen to be stable."""
    for volatile in ("now", "attempt", "retry_count", "sent_at", "request_id", "nonce"):
        with pytest.raises(IdempotencyError, match="this attempt"):
            a_key(arguments={volatile: "x", "contact": "c_snm"})


def test_an_argument_that_merely_carries_a_date_is_not_refused() -> None:
    """The sibling of the refusal above, and the reason the rule is a word-part match on a
    closed list rather than a search for `_at`. A due date is part of the intent and has to
    be in the key; refusing it would make the guard unusable and the first fix anybody
    reaches for is deleting the guard."""
    assert a_key(arguments={"due_at": "2026-10-01", "contact": "c_snm"})


def test_deriving_a_key_is_handed_no_clock_and_no_duration() -> None:
    """The structural half of the rule, and the one that survives somebody being helpful.
    A guard against volatile *names* can be walked around by passing a clock reading under
    a stable name; what cannot be walked around is a module that is never handed a clock.
    Delete this and a `now: datetime` parameter can be added to any function here, which is
    also the shape a timeout that resolves UNKNOWN would arrive in."""
    time_types = ("datetime", "timedelta", "date")
    for name, member in vars(idempotency).items():
        if name.startswith("_") or getattr(member, "__module__", "") != idempotency.__name__:
            continue
        if inspect.isfunction(member):
            annotations = [str(p.annotation) for p in inspect.signature(member).parameters.values()]
        elif dataclasses.is_dataclass(member) and isinstance(member, type):
            annotations = [str(f.type) for f in dataclasses.fields(member)]
        else:
            continue
        for annotation in annotations:
            assert not any(t in annotation for t in time_types), (
                f"{name} takes {annotation}; nothing in this module may read a clock, "
                "because a timeout is the thing that must never resolve UNKNOWN"
            )


def test_the_key_carries_none_of_the_data_it_was_derived_from() -> None:
    """Why the key is hashed rather than joined. The key is sent to the source, stored in
    its records and written to both sides' logs, and a key built by concatenation would put
    a client name and an amount in all of them with no permissions attached.

    The two values are chosen to discriminate: `SNM` and the full stop in `1284.50` cannot
    appear in a hex digest at all, so this cannot pass by luck."""
    key = a_key(arguments={"client": "SNM", "amount": "1284.50"})
    assert "SNM" not in key
    assert "1284.50" not in key
    assert set(key) <= set("0123456789abcdef")


def test_a_key_is_the_whole_digest_rather_than_a_prefix_of_one() -> None:
    """Anchored to `manifest.DIGEST_CHARS` and to the width of a SHA-256 in hex, not to the
    literal 64, so that shortening either one fails here. A truncated key is a collision
    surface bought for nothing: the key is compared for equality, never looked up, so there
    is no index to keep small."""
    assert KEY_CHARS == DIGEST_CHARS
    assert len(hashlib.sha256(b"").hexdigest()) == KEY_CHARS
    assert len(a_key()) == KEY_CHARS


def test_a_derivation_missing_any_of_its_four_parts_is_refused() -> None:
    """Each empty part merges two things that are not the same operation, and the merge is
    silent: the second one is deduplicated away and nobody is told it did not happen."""
    for missing in ("principal_id", "tool", "intent_ref"):
        with pytest.raises(IdempotencyError):
            a_key(**{missing: "  "})


def test_a_record_refuses_a_key_somebody_minted() -> None:
    """The shape check that catches the ordinary mistake, which is `uuid4().hex` in the
    field where a derived key goes. It cannot catch sixty-four random hex characters, and
    the module says so: this is why the derivation is a function rather than a convention.
    Delete this and a generated key reaches the source, which sees a new request per
    attempt."""
    with pytest.raises(IdempotencyError, match="derived key"):
        an_operation(key=uuid.uuid4().hex)
    assert an_operation(key=a_key()).key == a_key()


# ------------------------------------------------------- the state machine (M17.3.2)
def test_every_state_has_a_row_in_the_transition_table() -> None:
    """A member added without an entry is a state with no way out and a `KeyError` at the
    moment a record reaches it, which is during recovery. Delete this and the table can
    fall behind the enum silently."""
    assert set(ALLOWED_TRANSITIONS) == set(OperationState)


def test_unknown_moves_only_to_verifying() -> None:
    """The central rule. Anything else in this set is a way to resolve "nobody knows"
    without asking, and the two candidates are both plausible: FAILED because it looks like
    a failure, and SENT because retrying looks like recovery. Either one bills a client
    twice."""
    assert ALLOWED_TRANSITIONS[OperationState.UNKNOWN] == frozenset({OperationState.VERIFYING})


def test_no_path_of_any_length_leads_from_unknown_back_to_a_second_issue() -> None:
    """The row above is not enough, because the edge somebody adds is never the direct one.
    It is `VERIFYING -> PENDING`, added so a verified-absent operation can be tried again,
    and it puts a second issue two hops from "nobody knows" while the UNKNOWN row still
    reads correctly. Delete this and that edge lands with the suite green."""
    from_unknown = reachable_from(OperationState.UNKNOWN)
    assert OperationState.SENT not in from_unknown
    assert OperationState.PENDING not in from_unknown
    assert from_unknown == frozenset(
        {
            OperationState.VERIFYING,
            OperationState.UNKNOWN,
            OperationState.SUCCEEDED,
            OperationState.FAILED,
        }
    )


def test_an_operation_runs_the_whole_way_from_intent_to_success() -> None:
    """The positive case. A machine tested only by what it refuses is satisfied by one that
    refuses everything, and this is the path every ordinary operation takes: recorded,
    issued, acknowledged."""
    record = an_operation()
    assert record.state is OperationState.PENDING
    sent = record.advanced(OperationState.SENT)
    settled = sent.advanced(state_after_call(CallOutcome.OK))
    assert settled.state is OperationState.SUCCEEDED
    assert settled.is_settled


def test_a_settled_operation_cannot_be_moved_again() -> None:
    """Terminal means terminal. Without this, a recovery sweep that re-ran a succeeded
    operation would advance it back to SENT and issue it again, which is the whole failure
    in one line."""
    settled = an_operation(state=OperationState.SUCCEEDED)
    with pytest.raises(IllegalTransitionError):
        settled.advanced(OperationState.SENT)


def test_the_terminal_states_are_derived_from_the_table_rather_than_listed() -> None:
    """A hand-written list of terminal states can disagree with the table, and the way it
    disagrees is that something terminal is given an outgoing edge and nothing notices."""
    assert frozenset({OperationState.SUCCEEDED, OperationState.FAILED}) == TERMINAL
    for state in TERMINAL:
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_a_lost_answer_leaves_the_operation_unknown_rather_than_failed() -> None:
    """The branch the module exists for. A timeout, a dropped connection and a 500 all mean
    the request may have been processed and the answer lost. Mapping any of them to FAILED
    tells a caller it is safe to try again, and it is not."""
    assert state_after_call(CallOutcome.UNAVAILABLE) is OperationState.UNKNOWN


def test_a_refusal_the_source_stated_is_a_failure_rather_than_an_unknown() -> None:
    """The other side of the same rule, and the reason FAILED is worth having at all. A 4xx
    and a 429 are the source saying it did not process the request. Reading them as UNKNOWN
    would send every rate-limited write through a read-back, which teaches whoever is on
    call that UNKNOWN is routine."""
    assert state_after_call(CallOutcome.REJECTED) is OperationState.FAILED
    assert state_after_call(CallOutcome.QUOTA) is OperationState.FAILED


def test_a_truncated_result_is_not_an_outcome_an_operation_can_have() -> None:
    """TRUNCATED describes a result set that came back short, which no write produces. A
    caller that reaches this has classified a read and is one line from recording a write
    as succeeded on the strength of it."""
    with pytest.raises(IdempotencyError, match="read"):
        state_after_call(CallOutcome.TRUNCATED)


# ------------------------------------------------------- the read-back (M17.3.3)
def test_a_verification_records_that_it_started_before_it_asks() -> None:
    """The same write-ahead argument as SENT, one level down. If the move to VERIFYING
    happened after the read-back returned, a crash during verification would leave the
    record in UNKNOWN with no way to tell that from a verification nobody has started."""
    seen: list[OperationState] = []

    def read_back(operation: Operation) -> Verification:
        seen.append(operation.state)
        return Verification.FOUND

    verify(an_operation(state=OperationState.UNKNOWN), read_back)
    assert seen == [OperationState.VERIFYING]


def test_a_read_back_that_found_it_settles_the_operation_as_done() -> None:
    """The positive case for verification, and the reason a read-back is the safe way out
    of UNKNOWN: it settles without doing anything to the world."""
    settled = verify(an_operation(state=OperationState.UNKNOWN), lambda _: Verification.FOUND)
    assert settled.state is OperationState.SUCCEEDED


def test_a_read_back_that_looked_and_found_nothing_settles_it_as_failed() -> None:
    """The only thing that may state a definite failure after a request has gone out. Delete
    this and ABSENT could be mapped to PENDING so the operation could be issued again, which
    is the edge the closure test refuses from the other direction."""
    settled = verify(an_operation(state=OperationState.UNKNOWN), lambda _: Verification.ABSENT)
    assert settled.state is OperationState.FAILED


def test_a_read_back_that_could_not_answer_returns_the_operation_to_unknown() -> None:
    """A verification that timed out has not shown the effect to be absent. Collapsing
    INCONCLUSIVE into ABSENT is the original mistake wearing a verification's clothes: it
    produces a FAILED record for an operation that may well have happened."""
    settled = verify(
        an_operation(state=OperationState.UNKNOWN), lambda _: Verification.INCONCLUSIVE
    )
    assert settled.state is OperationState.UNKNOWN
    assert state_after_verification(Verification.INCONCLUSIVE) is OperationState.UNKNOWN


def test_a_verification_interrupted_midway_is_simply_asked_again() -> None:
    """The state a worker finds after dying during a read-back. Refusing it would leave the
    record stuck in VERIFYING for ever, and the obvious fix somebody would reach for is to
    reset it to PENDING, which issues."""
    settled = verify(an_operation(state=OperationState.VERIFYING), lambda _: Verification.FOUND)
    assert settled.state is OperationState.SUCCEEDED


def test_an_operation_that_is_not_in_doubt_is_not_verified() -> None:
    """A read-back against a record that is not in doubt is a second answer to a question
    that already has one, and the one it produces would overwrite the first.

    Refused by the transition table rather than by a guard on `verify`. There was a guard,
    and mutation testing showed it was equivalent: no state but UNKNOWN and VERIFYING has an
    edge to VERIFYING, so `advanced` already raises for all of them. What this test now pins
    is that the table keeps it that way, which is why an added `PENDING -> VERIFYING` edge
    fails here."""
    for state in (OperationState.PENDING, OperationState.SENT, OperationState.SUCCEEDED):
        with pytest.raises(IllegalTransitionError):
            verify(an_operation(state=state), lambda _: Verification.FOUND)


# ------------------------------------------------- read-back implies read-only (M17.3.4)
def test_a_tool_with_a_side_effect_and_a_read_back_may_be_operated_on() -> None:
    """The positive case for the permission rule. Without it, `issuable_tools` returning
    nothing at all would satisfy every refusal test below and no write would ever be
    possible."""
    assert issuable_tools(a_manifest()) == ("xero.create_invoice",)
    assert read_only_reason(a_manifest()) == ""
    assert declaration_for(a_manifest(), "xero.create_invoice") is RAISE_INVOICE


def test_a_connector_that_declares_no_writable_tool_is_read_only() -> None:
    """The rule stated the way M17.3.4 states it. A connector that cannot be read back
    cannot resolve an UNKNOWN, so it must never make one; here that is derived from the
    declarations rather than remembered, so a connector added with only read tools has an
    empty writable set by construction."""
    read_only = a_manifest(tools=(READ_INVOICE,), credential=CredentialBinding(ref=READ_REF))
    assert issuable_tools(read_only) == ()
    assert "read-only" in read_only_reason(read_only)


def test_a_tool_that_declares_a_read_back_but_changes_nothing_is_still_not_operable() -> None:
    """An operation record exists to make a side effect happen once. A read that declares a
    read-back is not a side effect, and admitting it would put every fetch through the state
    machine. This is also what stops the side-effect half of the derivation being dropped:
    without this test, `issuable_tools` could return every tool that verifies."""
    reader_that_verifies = ToolDeclaration(
        name="xero.read_contact",
        description="One contact by id.",
        entity="contact",
        verifies_write=True,
    )
    assert issuable_tools(a_manifest(tools=(reader_that_verifies,))) == ()


def test_an_operation_cannot_be_raised_against_a_tool_nobody_declared() -> None:
    """The one shape the manifest review cannot have caught, because a manifest can only
    refuse what it was shown. A call site naming a tool that was never declared is how a
    connector acquires a write path that nobody granted."""
    with pytest.raises(IdempotencyError, match="does not declare it"):
        declaration_for(a_manifest(), "xero.delete_everything")
    with pytest.raises(IdempotencyError):
        begin(
            manifest=a_manifest(),
            tool="xero.delete_everything",
            principal_id="p_alice",
            intent_ref="run_1",
        )


def test_an_operation_cannot_be_raised_against_a_read_only_tool() -> None:
    """The refusal a read-only connector relies on. Without it, `begin` would happily record
    an operation for a fetch and the whole permission rule would be advisory."""
    with pytest.raises(IdempotencyError, match=r"xero\.read_invoice"):
        begin(
            manifest=a_manifest(),
            tool="xero.read_invoice",
            principal_id="p_alice",
            intent_ref="run_1",
        )


def test_the_manifest_still_refuses_a_side_effecting_tool_with_no_read_back() -> None:
    """This module's precondition, pinned from outside it. `issuable_tools` derives rather
    than re-checks, on the argument that two enforcement points which are really one get
    half-deleted; that argument only holds while the manifest's own refusal holds. If
    somebody relaxes `ToolDeclaration`, this goes red and tells them that the derivation in
    `brain.ops.idempotency` is now the only thing holding the rule."""
    with pytest.raises(ManifestError, match="UNKNOWN"):
        ToolDeclaration(
            name="xero.pay_bill",
            description="Pay a bill.",
            entity="bill",
            side_effect=SideEffect.MONEY,
            verifies_write=False,
        )


def test_beginning_an_operation_derives_its_key_from_the_declared_tool() -> None:
    """The constructor call sites use. Delete this and `begin` could return a record whose
    key was derived from something other than the tool it resolved, which is two identities
    for one operation."""
    operation = begin(
        manifest=a_manifest(),
        tool="xero.create_invoice",
        principal_id="p_alice",
        intent_ref="run_2026_09_07",
        arguments={"contact": "c_snm"},
    )
    assert operation.key == a_key()
    assert operation.state is OperationState.PENDING
    assert operation.connector == "xero"


# ------------------------------------------------------- the crash model (M17.3.5)
class _Source:
    """A source that counts what was actually done to it and can be read back.

    The counter is the whole assertion: exactly-once is a statement about how many times a
    side effect happened, and a test that asserted on states alone would pass against a
    machine that issued twice and recorded once.
    """

    def __init__(self, *, landed: bool = False) -> None:
        self.issued = 1 if landed else 0

    def issue(self) -> None:
        self.issued += 1

    def read_back(self, operation: Operation) -> Verification:
        return Verification.FOUND if self.issued else Verification.ABSENT


def _recover(record: Operation, source: _Source, *, rounds: int = 6) -> Operation:
    """A worker restarting on this record and running it to a settled state.

    Written as the loop a real worker would run rather than as a sequence of asserted
    transitions, so that the thing under test is what `resume` tells a caller to do and not
    what this test already believes.
    """
    for _ in range(rounds):
        plan = resume(record)
        record = plan.operation
        if plan.disposition is Disposition.ISSUE:
            record = record.advanced(OperationState.SENT)
            source.issue()
            record = record.advanced(state_after_call(CallOutcome.OK))
        elif plan.disposition is Disposition.VERIFY:
            record = verify(record, source.read_back)
        else:
            return record
    msg = "the recovery loop did not settle; a resume plan is cycling"
    raise AssertionError(msg)


def test_only_a_pending_operation_resumes_by_issuing() -> None:
    """Exactly-once written as data rather than as a branch. Every other state has had a
    request leave the process or has settled, and the count is what a reviewer can check in
    ten seconds. Delete this and a second ISSUE row can be added to the plan without any
    single-state test noticing."""
    issues = [state for state, (_, plan) in RESUME_PLAN.items() if plan is Disposition.ISSUE]
    assert issues == [OperationState.PENDING]


def test_every_state_has_a_resume_plan() -> None:
    """A state with no plan is a `KeyError` during crash recovery, which is the worst
    possible moment for one: the process that raises it is the one recovering."""
    assert set(RESUME_PLAN) == set(OperationState)


def test_a_record_found_in_sent_becomes_unknown_rather_than_being_retried() -> None:
    """The crash this module exists for, in one assertion. A request left the process and no
    outcome was recorded, so nobody knows whether the invoice was raised. Delete this and
    SENT could resume by issuing, which is the duplicate-payment bug."""
    plan = resume(an_operation(state=OperationState.SENT))
    assert plan.operation.state is OperationState.UNKNOWN
    assert plan.disposition is Disposition.VERIFY
    assert not plan.may_issue


#: Every point at which the process could die, the record the store would hold at that
#: moment, and whether the side effect had actually happened by then.
#:
#: The pairing is not free. `PENDING` appears only with `landed=False`, because the record
#: is written before the request goes out, so a record that says nothing was issued means
#: nothing was issued. That is the write-ahead earning its keep, and
#: `test_the_write_ahead_is_what_makes_a_pending_record_safe_to_issue` states it separately.
CRASH_POINTS: list[tuple[str, OperationState, bool]] = [
    ("after the record was written, before the request went out", OperationState.PENDING, False),
    ("after the request went out, and it never arrived", OperationState.SENT, False),
    ("after the request went out and the source acted", OperationState.SENT, True),
    ("after the source answered, before the answer was recorded", OperationState.SENT, True),
    ("after the record was moved to unknown, effect absent", OperationState.UNKNOWN, False),
    ("after the record was moved to unknown, effect present", OperationState.UNKNOWN, True),
    ("during the read-back, effect absent", OperationState.VERIFYING, False),
    ("during the read-back, effect present", OperationState.VERIFYING, True),
    ("after the read-back answered, before it was recorded", OperationState.VERIFYING, True),
    ("after success was recorded", OperationState.SUCCEEDED, True),
    ("after failure was recorded", OperationState.FAILED, False),
]


@pytest.mark.parametrize(("crash_point", "recorded", "landed"), CRASH_POINTS)
def test_resuming_from_any_recorded_state_never_issues_a_second_side_effect(
    crash_point: str, recorded: OperationState, landed: bool
) -> None:
    """M17.3.5, and the caveat is the point of the docstring.

    **This is a model of a crash, not a killed process.** Nothing here kills anything. Each
    case constructs the record the store would hold at one point where the process could
    die, and drives a recovering worker from it. What is proved is at-most-once under that
    model, together with `test_recovery_still_does_the_work_that_had_not_started` for the
    other half of exactly-once, which is that work not yet started does get done.

    Covered: the eleven points in `CRASH_POINTS`, each paired with whether the side effect
    had actually happened, which is the axis a worker cannot observe and therefore must not
    assume.

    Not covered, and named rather than implied. There is no killed process anywhere in this
    file. The store must make the write durable and the key unique: two workers that both
    find no record will both write one and both issue, and only a unique index on the key
    stops that, which is a migration this repository does not yet have. The source must
    honour the key it is sent, or exactly-once rests entirely on the read-back. And a source
    that returns a definite refusal after having acted has lied about whether it acted, which
    is why `FAILED` appears here only with the effect absent.
    """
    source = _Source(landed=landed)
    before = source.issued
    settled = _recover(an_operation(state=recorded), source)

    assert source.issued <= 1, f"{crash_point}: recovery issued more than one side effect"
    if before:
        assert source.issued == before, (
            f"{crash_point}: the side effect had already happened and recovery repeated it"
        )
    assert settled.is_settled, f"{crash_point}: recovery left the operation unsettled"


def test_the_write_ahead_is_what_makes_a_pending_record_safe_to_issue() -> None:
    """Why `CRASH_POINTS` pairs `PENDING` only with an effect that never happened, and why
    that is a property rather than a convenience.

    The record is written before the request goes out, so `PENDING` means no request has
    left this process and the world is unchanged. Record it afterwards instead and the
    combination becomes reachable: the process dies between the source acting and the row
    being written, the recovering worker finds `PENDING`, resumes by issuing, and the client
    is billed twice. That ordering is the only thing separating those two worlds, and
    nothing in a type can enforce it, so it is asserted here and stated in
    `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL`.

    Delete this and the pairing in `CRASH_POINTS` looks like a gap in the coverage somebody
    should fill by adding the missing combination, which would then fail for the right
    reason with nothing explaining it."""
    assert resume(an_operation(state=OperationState.PENDING)).may_issue
    assert not resume(an_operation(state=OperationState.SENT)).may_issue
    assert idempotency.THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL.startswith(
        "SENT is recorded before the request is made"
    )


def test_recovery_still_does_the_work_that_had_not_started() -> None:
    """The positive half of the crash model, and without it every assertion above is
    satisfied by a `resume` that returns STOP for everything. A process that died before
    issuing anything has to be finished, once, by whoever picks the record up."""
    source = _Source(landed=False)
    settled = _recover(an_operation(state=OperationState.PENDING), source)
    assert source.issued == 1
    assert settled.state is OperationState.SUCCEEDED


def test_an_operation_verified_absent_is_not_quietly_reissued() -> None:
    """The design decision the module records as rejected, pinned. Verification proving the
    effect absent is exactly when re-issuing looks safe, and adding that edge is what puts a
    second issue two hops from UNKNOWN. Another go is a new intent, raised by somebody."""
    source = _Source(landed=False)
    settled = _recover(an_operation(state=OperationState.SENT), source)
    assert settled.state is OperationState.FAILED
    assert source.issued == 0
    assert resume(settled).disposition is Disposition.STOP


def test_a_resumption_says_why_and_not_only_what() -> None:
    """A worker that parks an operation puts it in front of a person, and "verify" on its
    own does not tell them why this row is theirs. Delete this and the reasons can go empty
    with every verdict test still green."""
    for state in OperationState:
        plan = resume(an_operation(state=state))
        assert plan.reason.strip()


def test_advance_refuses_a_move_the_table_has_no_edge_for() -> None:
    """The guard behind every transition. Without it the table is documentation, and the
    move that gets made anyway is UNKNOWN straight to SUCCEEDED by an operator clearing a
    queue."""
    with pytest.raises(IllegalTransitionError, match="cannot move"):
        advance(OperationState.UNKNOWN, OperationState.SUCCEEDED)
    assert advance(OperationState.UNKNOWN, OperationState.VERIFYING) is OperationState.VERIFYING


def test_an_operation_record_names_who_and_what_it_was_for() -> None:
    """A record missing its connector, tool, principal or intent cannot be resumed by
    anybody: the read-back needs the tool and the person looking at a quarantined row needs
    the rest."""
    for missing in ("connector", "tool", "principal_id", "intent_ref"):
        with pytest.raises(IdempotencyError, match="cannot be resumed"):
            an_operation(**{missing: ""})
