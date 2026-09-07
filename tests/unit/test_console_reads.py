"""The console held to being a caller, not a back door.

Every test here is about one of the three ways a reporting surface undoes a permission model:
a query of its own, a row the redactor cannot walk, and an audience computed by union. The
fourth is the plane collapse, where "can see the settings" quietly becomes "can see the
records", and the fifth is the self-grant nobody is told about.

Real `EntitlementSet`s and real `AuditEntry`s throughout. A test that built a stand-in for
either would be testing this module against a fixture rather than against the two objects it
has to agree with, and the agreement is the whole point: `intersect` is the gate's and
`is_self_grant` reads a subject in the ledger's own grammar.

Task ids: M27.5.1, M27.5.2, M27.5.3, M27.5.4, M27.5.5
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import AuditAction, AuditEntry, compute_entry_hash
from brain.audit.record import subject
from brain.console import reads as reads_module
from brain.console.reads import (
    CONSOLE_CAPABILITY_PREFIX,
    PRINCIPAL_SUBJECT,
    ConsoleRead,
    Plane,
    SelfGrant,
    StewardNotice,
    admits,
    audience,
    console_gaps,
    is_self_grant,
    notices_for,
    permitted,
    plane_capability,
    planes_reachable,
    self_grants,
    tagged,
    untagged_rows,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.redaction import ChannelPayload
from brain.core.scope import Clause, Op, Scope

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
ZERO = "0" * 64


def ents(*caps: str, scope: Scope | None = None, principal: str = "u_lead") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope or Scope()) for one in caps
        ),
    )


def maintenance() -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value="maintenance"),))


def entry(
    *,
    actor: str,
    subject_id: str,
    action: AuditAction = AuditAction.GRANT,
    kind: str = "principal",
    at: datetime = NOW,
    seq: int = 1,
    prev: str = ZERO,
) -> AuditEntry:
    """One real ledger entry, hashed the way the chain hashes one.

    Through `compute_entry_hash` and `record.subject` rather than with literals, so the
    subject grammar this module parses is the grammar the ledger writes rather than one the
    test agreed with itself about, and so an entry that would be refused by the chain is
    refused here too.
    """
    said = subject(kind, subject_id)
    common = {
        "seq": seq,
        "at": at,
        "actor_id": actor,
        "action": action,
        "subject": said,
        "ent_hash": "0" * 32,
        "trace_id": "t_console",
        "details": {},
        "prev_hash": prev,
    }
    return AuditEntry(**common, entry_hash=compute_entry_hash(**common))  # type: ignore[arg-type]


# --- the three planes ----------------------------------------------------------------------


def test_the_planes_nest_so_a_wider_reader_still_sees_the_narrower_thing() -> None:
    """Each plane contains the last: you cannot show a thing's configuration without
    disclosing that it exists, and you cannot show its content without disclosing both. A
    reader who may see content and is refused the listing is being refused a disclosure they
    already have.

    Asserted over every ordered pair rather than on a couple of examples, because a
    comparison written as an equality passes the examples somebody picks first.

    Delete this and `admits` becomes `held is wanted`, and the content reader loses the
    listing with nothing to explain why."""
    for held in Plane:
        for wanted in Plane:
            assert admits(held, wanted) is (held.value >= wanted.value), (held, wanted)


def test_a_configuration_reader_never_reaches_content() -> None:
    """The direction that matters. Existence and configuration are what an auditor and a
    connector administrator hold, and content is the one they must never have: M33.4.5 asks
    for that absence to be asserted by test and this is where the ordering makes it true.

    Delete this and the nesting is asserted in the abstract with nothing naming the pair the
    system exists to keep apart."""
    assert admits(Plane.CONFIGURATION, Plane.EXISTENCE) is True
    assert admits(Plane.CONFIGURATION, Plane.CONTENT) is False
    assert admits(Plane.CONTENT, Plane.CONFIGURATION) is True


def test_each_plane_needs_its_own_grant_rather_than_one_that_covers_them() -> None:
    """A single `read:console` covering all three makes an auditor's role indistinguishable
    from a super administrator's at the point it matters, because the capability the gate
    checks would be the same string.

    Asserted as three distinct capabilities, and as the negative: a caller holding one does
    not reach the others.

    Delete this and the three planes collapse into one grant, and the model survives only in
    the docstring."""
    values = {plane_capability(one).value for one in Plane}
    assert len(values) == len(Plane)

    only_existence = ents(plane_capability(Plane.EXISTENCE).value)
    assert planes_reachable(only_existence) == (Plane.EXISTENCE,)


def test_a_reader_holding_two_planes_reaches_both_and_no_more() -> None:
    """The positive sibling. Without it every assertion above is satisfied by
    `planes_reachable` returning nothing at all, which refuses everybody and is not a console.

    Delete this and the whole file is green for a function that always returns an empty
    tuple."""
    held = ents(
        plane_capability(Plane.EXISTENCE).value,
        plane_capability(Plane.CONFIGURATION).value,
    )

    assert planes_reachable(held) == (Plane.EXISTENCE, Plane.CONFIGURATION)


def test_there_is_no_fourth_plane_for_a_summary() -> None:
    """A middle plane for "summary" or "aggregate" is the one every reporting system grows,
    and it is where a figure derived from content gets classified as configuration. Three
    members, and the fourth is the point.

    Delete this and `AGGREGATE = 2.5` arrives with a good story attached."""
    assert [one.name for one in Plane] == ["EXISTENCE", "CONFIGURATION", "CONTENT"]


# --- a console read is a tool call ----------------------------------------------------------


def test_a_console_read_has_nowhere_to_put_a_query() -> None:
    """**M27.5.1, structurally.** A reporting service with its own connection and a list of
    allowed queries is faster to write and is the second data path with no projection, no
    redactor and no audit row.

    Asserted on the field names rather than on behaviour, because behaviour today says
    nothing about what a `query` added tomorrow would do, and it would arrive looking like a
    performance fix.

    Delete this and `ConsoleRead(sql=...)` appears the first time a screen is slow."""
    names = {one.name for one in dataclass_fields(ConsoleRead)}

    for forbidden in ("query", "sql", "statement", "table", "connection", "dsn", "cursor"):
        assert forbidden not in names, forbidden

    assert names == {"screen", "tool", "requires", "plane"}


def test_a_read_cannot_lean_on_the_plane_grant_instead_of_a_grant_over_what_it_reads() -> None:
    """**Written after the first version of this guard turned out to be unreachable.** It
    refused an empty capability, and `Capability` refuses a value under three characters one
    frame earlier, so the branch could not fire and no test could exercise it.

    The real failure is a read whose requirement is one of the three plane capabilities. Then
    the tool's own grant is doing nothing and anybody trusted with the console reaches what it
    returns, which is the back door wearing the shape of the thing that was supposed to
    replace it. Refused at every plane and not only at content, because a listing anybody
    with a console grant can pull is still a listing they were never granted.

    Delete this and `reports.usage` requires `read:console.content` and the plane model
    becomes the only check on a data read."""
    for plane in Plane:
        with pytest.raises(ValueError, match="rather than a grant over what it reads"):
            ConsoleRead(
                screen="usage",
                tool="reports.usage",
                requires=plane_capability(plane),
                plane=plane,
            )

    with pytest.raises(ValueError, match="names nothing anybody can audit"):
        ConsoleRead(
            screen="",
            tool="rows.read_client",
            requires=Capability(value="read:client"),
            plane=Plane.EXISTENCE,
        )


def test_the_console_namespace_is_one_constant_and_not_two_spellings() -> None:
    """`plane_capability` builds these and `ConsoleRead` refuses them, so the two have to
    agree. A second spelling would make the refusal stop firing with nothing failing, because
    the answer would simply be False.

    Delete this and the prefix drifts in one of the two places and the guard goes quiet."""
    for plane in Plane:
        assert plane_capability(plane).value.startswith(CONSOLE_CAPABILITY_PREFIX)


def test_a_read_needs_both_the_tools_capability_and_the_planes() -> None:
    """Two checks and they are conjunctive. The tool's own capability is what an agent making
    the same call would need; the plane's is what the console adds. A screen showing the
    configuration of something the caller may only know exists is refused by the second even
    though the first passes.

    Delete this and holding the tool's capability is enough, and the plane model stops being
    enforced anywhere."""
    read = ConsoleRead(
        screen="agents",
        tool="agents.list",
        requires=Capability(value="read:agent"),
        plane=Plane.CONFIGURATION,
    )

    both = ents("read:agent", plane_capability(Plane.CONFIGURATION).value)
    tool_only = ents("read:agent")
    plane_only = ents(plane_capability(Plane.CONFIGURATION).value)
    too_narrow = ents("read:agent", plane_capability(Plane.EXISTENCE).value)

    assert permitted(read, both) is True
    assert permitted(read, tool_only) is False
    assert permitted(read, plane_only) is False
    assert permitted(read, too_narrow) is False


# --- the rows the redactor can walk ---------------------------------------------------------


def test_a_report_row_carries_the_two_keys_the_redactor_looks_for() -> None:
    """**M27.5.2.** `brain.core.redaction` finds records by `@entity` and `@id`. A row without
    them is not refused, it is not recognised, so the walker leaves it alone and every column
    reaches the screen.

    Asserted by handing the row to a real `ChannelPayload`, so what is checked is that the
    shape the redactor consumes accepts it, rather than that two strings are present.

    Delete this and a report row is a plain dictionary, and the first confidential column in
    one goes out whole."""
    row = tagged("client", "c_447", {"name": "Acme", "hours_remaining": "37"})

    assert row["@entity"] == "client"
    assert row["@id"] == "c_447"
    assert ChannelPayload(records=(row,)).records[0]["name"] == "Acme"


def test_a_row_carrying_its_own_reserved_key_is_refused() -> None:
    """A value called `@id` would replace the tag and produce a row the walker recognises and
    mis-identifies, which is worse than one it walks past: the redactor would apply the wrong
    record's policy to it.

    Delete this and a report over a table with a column called `@id` silently reclassifies
    every row in it."""
    for reserved in ("@entity", "@id"):
        with pytest.raises(ValueError, match="claim to be a record it is not"):
            tagged("client", "c_447", {reserved: "something else"})


def test_an_untagged_row_is_reported_by_position_and_never_by_content() -> None:
    """The diagnostic half. A function that returned the offending rows would be a second
    copy of exactly the data that has not been redacted, handed to whoever called the
    diagnostic.

    Delete this and the diagnostic starts returning rows, because that is more useful, and
    the more useful thing is a copy of unredacted records."""
    rows = [
        tagged("client", "c_1", {"name": "Acme"}),
        {"name": "Untagged"},
        tagged("client", "c_2", {"name": "Zephyr"}),
        {"@entity": "client"},
    ]

    found = untagged_rows(rows)

    assert found == (1, 3)
    assert all(isinstance(one, int) for one in found)


def test_a_fully_tagged_report_reports_no_gaps() -> None:
    """The positive sibling, without which the check is satisfied by a function that flags
    every row and a console that can render none of them.

    Delete this and `untagged_rows` can return every index with the file green."""
    assert untagged_rows([tagged("client", "c_1", {"name": "Acme"})]) == ()


# --- the audience ---------------------------------------------------------------------------


def test_a_report_is_read_at_the_intersection_and_never_at_the_union() -> None:
    """**M27.5.3, and the union is one character away.** A screen headed Maintenance reads as
    though it should show the whole department, and `caller | department` is what that reads
    like in code.

    The caller here holds one capability the report does not and the report holds one the
    caller does not, so an intersection and a union differ in both directions and neither
    can pass by accident.

    Delete this and the audience becomes the union the day somebody notices a department head
    cannot see their own department's figures, which is the feature request that breaks the
    model."""
    caller = ents("read:client.name", "read:client.hours_remaining")
    report = ents("read:client.name", "read:client.contract_value", principal="report")

    seen = audience(caller, report)
    held = {grant.capability.value for grant in seen.grants}

    assert held == {"read:client.name"}
    assert "read:client.contract_value" not in held
    assert "read:client.hours_remaining" not in held


def test_the_audience_narrows_the_scope_as_well_as_the_capability() -> None:
    """An intersection of capabilities with a union of scopes is the same leak wearing a
    different hat: the caller would hold the right capability over rows they were never
    granted.

    `intersect` is the gate's own, so this asserts the console uses it rather than comparing
    capability strings itself.

    Delete this and somebody writes a capability-only intersection, which reads correct and
    hands a department head every department's rows."""
    caller = ents("read:client.name", scope=maintenance())
    report = ents("read:client.name", principal="report")

    seen = audience(caller, report)

    assert seen.grants
    for grant in seen.grants:
        assert grant.scope.clauses, "the narrower scope did not survive the intersection"


def test_nothing_in_the_audience_signature_could_widen_a_reach() -> None:
    """Asserted on the signature, because behaviour today says nothing about a parameter
    added tomorrow, and it would arrive as `include_department=True` on a ticket about a
    department head who cannot see their own report.

    Delete this and the widening arrives as an option rather than as a change to the model."""
    taken = set(inspect.signature(audience).parameters)

    assert taken == {"caller", "report"}
    for forbidden in ("union", "widen", "include", "extra", "also", "full"):
        assert forbidden not in taken, forbidden


# --- the self-grant --------------------------------------------------------------------------


def test_a_grant_somebody_made_to_themselves_is_recognised_from_the_entry() -> None:
    """**M27.5.5.** A separate audit action was the obvious design and it is the one the next
    person to write a grant path forgets to use. A self-grant is a `GRANT` whose subject names
    its own actor, which is a fact about the entry and needs nobody to remember anything.

    Built through `compute_entry_hash` and `record.subject`, so the grammar parsed here is the
    grammar the ledger writes.

    Delete this and self-grants are found only when somebody declares one, which is never the
    case that matters."""
    mine = entry(actor="u_admin", subject_id="u_admin")
    theirs = entry(actor="u_admin", subject_id="u_other")

    assert is_self_grant(mine) is True
    assert is_self_grant(theirs) is False


def test_only_a_grant_counts_and_only_over_a_principal() -> None:
    """Two ways a lookalike entry could be mistaken for one. A revoke somebody performs on
    themselves is not a widening and must not raise the alarm that a widening does, and a
    grant whose subject is a connector or an agent cannot name an actor however it is worded.

    **The connector case is chosen and not incidental, and the first version of this test got
    it wrong.** It used `artifact`, which is eight letters, so dropping the prefix check left
    the slice one character short of the actor id and the answer came out False anyway: the
    test passed while the guard did nothing, and a mutation removing the guard survived.
    `connector` is nine letters, the same as `principal`, so `connector:u_admin` slices to
    exactly `u_admin`. That is the only shape where the check is doing work, and a connector
    id and a principal id are both free-form identifiers, so the collision is real rather than
    contrived.

    Delete this and every administrator revoking their own stale grant sets off the loudest
    notice in the system, and a grant over a connector that shares a person's id joins it."""
    revoked = entry(actor="u_admin", subject_id="u_admin", action=AuditAction.REVOKE)
    a_connector = entry(actor="u_admin", subject_id="u_admin", kind="connector")

    assert len("connector:") == len(PRINCIPAL_SUBJECT), (
        "the discriminating case rests on the two prefixes being the same length; pick "
        "another kind of the same width if this ever stops being true"
    )
    assert a_connector.subject[len(PRINCIPAL_SUBJECT) :] == a_connector.actor_id

    assert is_self_grant(revoked) is False
    assert is_self_grant(a_connector) is False


def test_self_grants_come_back_oldest_first() -> None:
    """A reviewer works forwards through what happened, and two self-grants in one sitting are
    a sequence rather than a set: the second one is often the interesting one, because it says
    the first was not enough.

    Delete this and the order becomes whatever the store returned, which is not an order."""
    older = entry(actor="u_admin", subject_id="u_admin", at=NOW - timedelta(hours=1))
    newer = entry(actor="u_admin", subject_id="u_admin", at=NOW)

    found = self_grants([newer, older])

    assert [one.at for one in found] == [older.at, newer.at]


def test_a_self_grant_carries_no_capability_value() -> None:
    """What was granted is in the ledger under its own redaction rules. Copying it into this
    record would put a capability into a notification that travels further than the ledger
    does, on whatever channel the steward reads.

    Delete this and the notice grows the capability, because that is the most useful thing
    anybody could add to it."""
    names = {one.name for one in dataclass_fields(SelfGrant)}

    assert names == {"principal_id", "entry_hash", "at"}
    for forbidden in ("capability", "value", "grant", "scope", "details"):
        assert forbidden not in names, forbidden


def test_a_steward_notice_has_nowhere_to_be_switched_off() -> None:
    """A notification about somebody widening their own reach is the one that gets turned off
    first when a dashboard is noisy, so the type has nowhere to turn it off from.

    Delete this and `enabled: bool = True` arrives during the first quiet-hours discussion."""
    names = {one.name for one in dataclass_fields(StewardNotice)}

    assert names == {"steward_id", "grant"}
    for forbidden in ("enabled", "severity", "quiet", "suppressed", "muted", "level"):
        assert forbidden not in names, forbidden


def test_a_notice_cannot_be_addressed_to_the_person_who_made_the_grant() -> None:
    """Loud means somebody else finds out. A notification whose recipient is the principal who
    performed the act tells nobody anything, and it passes every test that checks a
    notification was produced.

    Delete this and a super administrator who is also the steward self-grants in silence,
    with a notice in the outbox addressed to themselves."""
    grant = SelfGrant(principal_id="u_admin", entry_hash="a" * 64, at=NOW)

    with pytest.raises(ValueError, match="loud means somebody else finds out"):
        StewardNotice(steward_id="u_admin", grant=grant)

    assert StewardNotice(steward_id="u_steward", grant=grant).steward_id == "u_steward"


def test_the_whole_batch_is_refused_when_the_steward_is_one_of_the_actors() -> None:
    """Refused rather than filtered. A partial batch is the shape where the interesting notice
    is the one that went missing, and a caller who sees a shorter list than they expected has
    no way to tell which one it was.

    Delete this and the steward's own self-grant is dropped from the batch and everybody
    else's is delivered, which is the exact inverse of what this exists for."""
    entries = [
        entry(actor="u_admin", subject_id="u_admin"),
        entry(actor="u_steward", subject_id="u_steward", at=NOW + timedelta(minutes=1)),
    ]

    with pytest.raises(ValueError, match="loud means somebody else finds out"):
        notices_for(entries, steward_id="u_steward")


def test_a_notice_says_who_and_when_and_never_what() -> None:
    """The sentence a steward reads names the principal and points at the ledger entry. What
    was granted stays in the ledger, which has its own redaction rules and its own audience.

    The entry reference is quotable and carries no authority, which is the argument
    `ComposedAnswer.trace_ref` makes about its own.

    Delete this and the sentence grows the capability, and the notification channel becomes a
    second place capabilities are published."""
    grant = SelfGrant(principal_id="u_admin", entry_hash="b" * 64, at=NOW)

    said = StewardNotice(steward_id="u_steward", grant=grant).render()

    assert "u_admin" in said
    assert "granted themselves" in said
    assert "read:" not in said
    assert "audit ledger" in said


def test_every_self_grant_produces_exactly_one_notice() -> None:
    """The positive case. Without it every assertion above is satisfied by `notices_for`
    returning nothing, which is a system where nobody is ever told.

    Delete this and the refusal path is tested and the delivery path is not."""
    entries = [
        entry(actor="u_admin", subject_id="u_admin"),
        entry(actor="u_admin", subject_id="u_other", at=NOW + timedelta(minutes=1)),
        entry(actor="u_two", subject_id="u_two", at=NOW + timedelta(minutes=2)),
    ]

    notices = notices_for(entries, steward_id="u_steward")

    assert [one.grant.principal_id for one in notices] == ["u_admin", "u_two"]


def test_the_subject_prefix_is_the_ledgers_own_and_not_a_second_spelling() -> None:
    """`is_self_grant` parses a subject, so it has to agree with the function that writes one.
    Two spellings of `principal:` would make every self-grant invisible and nothing would
    fail, because the answer would simply be False.

    Anchored to `record.subject` rather than to the literal, so a change to the ledger's
    grammar fails here rather than going quiet.

    Delete this and the prefix drifts, and the loudest alarm in the system stops firing with
    the file green."""
    assert subject("principal", "u_x") == f"{PRINCIPAL_SUBJECT}u_x"


# --- the diagnostic, watched reporting something ---------------------------------------------


def test_console_gaps_is_quiet_on_a_wiring_that_is_correct() -> None:
    """The baseline for the two below, and on its own it proves nothing: an empty tuple is
    what a diagnostic returns whether its checks are there or not.

    Delete this and a real gap has no test that would notice it at all."""
    good = ConsoleRead(
        screen="records",
        tool="rows.read_client",
        requires=Capability(value="read:client"),
        plane=Plane.CONTENT,
    )

    assert console_gaps([good], ents("read:console.existence", "read:console.content")) == ()


def test_console_gaps_reports_a_screen_wired_to_something_that_is_not_a_tool() -> None:
    """**Written because a diagnostic nobody has watched report anything is one nobody can
    rely on.** A screen wired to something named like a query rather than like a registered
    tool has a row that went through no projection, so the redactor gets it untagged.

    The constructor cannot refuse this one: a tool name is a string and `rows.read_client`
    and `sql.usage_by_department` are the same shape. What the name gives is a signal, and a
    signal in a diagnostic is the right strength for it.

    Delete this and that check can be removed with every other test in this file still green,
    because they all call the diagnostic on a healthy wiring."""
    hand_rolled = ConsoleRead(
        screen="usage",
        tool="sql.usage_by_department",
        requires=Capability(value="read:usage"),
        plane=Plane.CONTENT,
    )

    gaps = console_gaps([hand_rolled])

    assert any("named like a query" in one for one in gaps), gaps


def test_console_gaps_reports_a_reader_who_reaches_content_and_not_existence() -> None:
    """The planes nest, so a caller holding the wider grant and not the narrower is a grant
    set nobody meant to write. It is reported rather than repaired here, because repairing it
    would mean this module deciding somebody reaches more than their grants say.

    Delete this and the misconfiguration presents as a screen that shows a record and refuses
    to list it, which reads as a bug in the listing."""
    odd = ents(plane_capability(Plane.CONTENT).value)

    gaps = console_gaps([], odd)

    assert any("nobody meant to write" in one for one in gaps), gaps


def test_console_gaps_reports_a_read_shape_that_grew_a_query_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Written because a mutation survived.** The field scan inside the diagnostic could not
    fire: `ConsoleRead`'s fields are fixed at import and `test_a_console_read_has_nowhere_to_
    put_a_query` asserts them directly, so the diagnostic's copy was reporting on this module
    rather than on anything a caller hands in.

    It is kept rather than deleted, because the two say different things: the direct test is
    about this class today, and the diagnostic is what a wiring check would report if the
    class ever grew one. Patching the class is how that becomes watchable.

    Delete this and the check goes back to being a branch nothing can reach."""

    @dataclass(frozen=True)
    class WithAQuery:
        screen: str
        tool: str
        requires: Capability
        plane: Plane
        query: str

    monkeypatch.setattr(reads_module, "ConsoleRead", WithAQuery)

    gaps = console_gaps()

    assert any("nothing projects or redacts" in one for one in gaps), gaps


def test_console_gaps_reports_an_audience_that_could_widen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The signature check inside the diagnostic, watched. Patching `audience` for a function
    that takes a widening parameter is how this test says what a broken module looks like
    without requiring one.

    Delete this and the check inside `console_gaps` can go while every other test passes."""

    def widened(
        caller: EntitlementSet, report: EntitlementSet, union: bool = False
    ) -> EntitlementSet:
        return caller

    monkeypatch.setattr(reads_module, "audience", widened)

    assert any("more than the caller's own reach" in one for one in console_gaps())


# --- the honest gap ---------------------------------------------------------------------------


def test_nothing_yet_renders_a_console_read() -> None:
    """**The honest gap, asserted so it cannot be forgotten quietly.**

    This module decides what a console screen may read and what shape its rows must be in.
    Nothing calls it: `brain.api_routes` has no reporting route and `console/src/pages` has no
    page built on one. The five leaves here are policy, and the screens they govern are M27.2
    to M27.4, which are unbuilt.

    Delete this and the gap stops being visible, and the day somebody builds a report screen
    they write their own row shape because they do not know this one exists."""
    from brain import api_routes

    mounted = {name for name in dir(api_routes) if not name.startswith("_")}

    assert "console_read" not in mounted
    assert "report" not in mounted
