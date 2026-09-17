"""Reading a write back from the source, per connector, from what the source actually sent.

Three families. The verdict is tested over the whole outcome vocabulary rather than at chosen
points, because the property is "exactly one combination is absent" and a list of examples
cannot say "exactly". Each connector's reading is driven from the recorded exchanges in
`tests/fixtures/cassettes.py` in that connector's own reply value, and every connector has an
absent case sitting beside its refusals, so a reading that answers INCONCLUSIVE for
everything fails as surely as one that answers ABSENT for a 429. And discovery is tested
against a second, independent list of connectors, so a connector added without an entry
fails by existing.

Every connector has recordings now, and every one is a documented shape rather than a live
capture; `tests/fixtures/cassettes.py` says which page each was written to.

Task ids: M17.3.3
"""

from __future__ import annotations

import pkgutil
import types
from collections.abc import Callable, Mapping
from typing import Any

import pytest

import brain.connectors
from brain.connectors import (
    freshdesk,
    google_drive,
    hubspot,
    laravel,
    lark_base,
    lark_wiki,
    throttle,
    write_verification,
    xero,
)
from brain.connectors.contract import AccessMode, CredentialBinding
from brain.connectors.lark_base import FieldBinding, FieldKind, LarkBaseTable
from brain.connectors.manifest import ConnectorManifest, FieldShape, HotUse
from brain.connectors.throttle import CallOutcome
from brain.connectors.write_verification import (
    NO_READ_BACK_PATH,
    NOTHING_IS_RECORDED,
    READ_BACKS,
    ReadBack,
    Reading,
    ReadingError,
    builds_a_manifest,
    connectors,
    declares_a_write,
    read_back_gaps,
    verdict,
)
from brain.core.envelope import SideEffect
from brain.ops.idempotency import (
    Operation,
    OperationState,
    Verification,
    derive_key,
    verify,
)
from brain.ops.secrets import SecretRef, VaultRole
from tests.fixtures.cassettes import CASSETTES, Cassette, Kind, Protocol, Source, for_source
from tests.invariants.test_cassettes import NOT_A_CONNECTOR

#: A read time pinned far outside any plausible wall clock, because nothing here is about the
#: present and a fixture with a near date is a clock that goes off.
FETCHED_AT = "2019-01-01T00:00:00+00:00"


def reading(connector: str) -> Callable[..., Reading]:
    """The reading a connector's entry names, refusing an entry that has none."""
    found = READ_BACKS[connector].reading
    assert found is not None, f"{connector} has no reading to drive"
    return found


def cassette(cid: str) -> Cassette:
    """One recording by id, so a test names the recording it is written against."""
    return next(c for c in CASSETTES if c.cid == cid)


class Resolver:
    """Every name answers with one public address. Nothing is fetched by anything here."""

    def resolve(self, host: str) -> list[str]:
        del host
        return ["93.184.216.34"]


# ------------------------------------------------------------ each connector's own reply value
def xero_answer(
    status: int | None, body: Any = None, *, entity: str = xero.ENTITY_INVOICE, **overrides: Any
) -> Verification:
    operation = xero.operation_for(entity, resolver=Resolver())
    reply = xero.interpret(operation, status=status, body=body, fetched_at=FETCHED_AT, **overrides)
    return verdict(reading("xero")(reply))


def hubspot_answer(
    status: int | None, body: Any = None, *, entity: str = hubspot.ENTITY_CLIENT, **overrides: Any
) -> Verification:
    operation = hubspot.operation_for(entity, resolver=Resolver())
    reply = hubspot.interpret(
        operation, status=status, body=body, fetched_at=FETCHED_AT, **overrides
    )
    return verdict(reading("hubspot")(reply))


def laravel_answer(reply: laravel.ViewReply) -> Verification:
    connection = laravel.LaravelConnection(
        schema="portal", bounds=laravel.ReadBounds(max_rows=200, timeout_seconds=5.0)
    )
    read = laravel.read_plan(connection, laravel.ENTITY_CLIENT)
    answered = laravel.interpret(read, reply, fetched_at=FETCHED_AT)
    return verdict(reading("laravel")(answered))


def freshdesk_answer(reply: freshdesk.Reply) -> Verification:
    operation = freshdesk.operation_for(
        freshdesk.Endpoint.SEARCH_TICKETS, domain="helpdesk.example.invalid"
    )
    return verdict(reading("freshdesk")(operation, reply))


def lark_table() -> LarkBaseTable:
    return LarkBaseTable(
        base_id="bascnCMII2ORej2RItqpZZUNMIe",
        table_id="tblsRc9GRRXKqhvW",
        entity="maintenance",
        bindings=(
            FieldBinding(
                target="client",
                base_field="Client",
                kind=FieldKind.TEXT,
                uses=(HotUse.JOIN,),
                shape=FieldShape.JOIN_KEY,
            ),
            FieldBinding(
                target="hours_remaining", base_field="Hours Remaining", kind=FieldKind.NUMBER
            ),
        ),
    )


def lark_base_answer(reply: lark_base.LarkReply) -> Verification:
    operation = lark_table().operation(lark_base.Endpoint.LIST_RECORDS, host="open.larksuite.com")
    return verdict(reading("lark_base")(operation, reply))


def lark_wiki_answer(reply: lark_wiki.LarkReply) -> Verification:
    return verdict(reading("lark_wiki")(reply))


def drive_answer(reply: google_drive.Reply) -> Verification:
    operation = google_drive.operation_for(google_drive.Endpoint.LIST_FILES)
    return verdict(reading("google_drive")(operation, reply))


def a_documented_drive_file() -> dict[str, Any]:
    """One file in the shape Google documents for `files.list`. Not a recording: none exists."""
    return {
        "id": "fileA1Bc-_",
        "name": "a proposal.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": "2019-01-01T00:00:00+00:00",
        "headRevisionId": "rev1",
        "trashed": False,
        "parents": ["fld0447AbC-_x"],
        "driveId": "",
        "shortcutDetails": {"targetId": ""},
    }


def emptied(cid: str, **data: Any) -> dict[str, Any]:
    """A recorded Lark envelope with its items removed and the named data fields replaced.

    Built from the recording rather than typed, so the code, the envelope and every field the
    connector does not look at are the recorded ones.
    """
    body = dict(cassette(cid).body)
    body["data"] = {**body["data"], "items": [], **data}
    return body


def lark_reply(cid: str) -> lark_base.LarkReply:
    recorded = cassette(cid)
    return lark_base.LarkReply(status=recorded.status, headers=recorded.headers, body=recorded.body)


def wiki_reply(cid: str) -> lark_wiki.LarkReply:
    recorded = cassette(cid)
    return lark_wiki.LarkReply(status=recorded.status, body=recorded.body)


def fresh_reply(cid: str) -> freshdesk.Reply:
    recorded = cassette(cid)
    return freshdesk.Reply(status=recorded.status, headers=recorded.headers, body=recorded.body)


#: How each recording a read-back names is answered, keyed by connector and recording. Written
#: here rather than read from the module, so the table and the readings are two accounts that
#: have to agree.
EXPECTED: Mapping[tuple[str, str], Verification] = {
    ("xero", "XERO-200-invoices"): Verification.FOUND,
    ("xero", "XERO-429"): Verification.INCONCLUSIVE,
    ("xero", "XERO-401-expired"): Verification.INCONCLUSIVE,
    ("hubspot", "HUBSPOT-200-empty"): Verification.ABSENT,
    ("laravel", "LARAVEL-500"): Verification.INCONCLUSIVE,
    ("freshdesk", "FRESH-200-search"): Verification.FOUND,
    ("freshdesk", "FRESH-429"): Verification.INCONCLUSIVE,
    ("lark_base", "LARK-200-records"): Verification.FOUND,
    ("lark_base", "LARK-200-code-permission"): Verification.INCONCLUSIVE,
    ("lark_wiki", "LARK-200-records"): Verification.FOUND,
    ("lark_wiki", "LARK-200-code-permission"): Verification.INCONCLUSIVE,
    ("xero", "XERO-200-contacts"): Verification.FOUND,
    ("xero", "XERO-200-invoices-full-page"): Verification.FOUND,
    ("hubspot", "HUBSPOT-200-companies-page"): Verification.FOUND,
    ("hubspot", "HUBSPOT-200-contacts"): Verification.FOUND,
    ("hubspot", "HUBSPOT-200-deals"): Verification.FOUND,
    ("hubspot", "HUBSPOT-200-associations"): Verification.FOUND,
    ("hubspot", "HUBSPOT-429"): Verification.INCONCLUSIVE,
    ("hubspot", "HUBSPOT-401"): Verification.INCONCLUSIVE,
    ("freshdesk", "FRESH-200-search-full-page"): Verification.FOUND,
    # The read-back reads a search page. A by-id object is not one, so it proves nothing there.
    ("freshdesk", "FRESH-200-ticket"): Verification.INCONCLUSIVE,
    ("freshdesk", "FRESH-200-contact"): Verification.INCONCLUSIVE,
    ("freshdesk", "FRESH-401"): Verification.INCONCLUSIVE,
    # One record under data.record says nothing about more, so it is unreadable as a listing.
    ("lark_base", "LARK-200-record"): Verification.INCONCLUSIVE,
    ("lark_base", "LARK-429"): Verification.INCONCLUSIVE,
    # The same for a wiki node read, which read ABSENT until the reading required has_more.
    ("lark_wiki", "LARK-WIKI-200-node"): Verification.INCONCLUSIVE,
    ("lark_wiki", "LARK-WIKI-200-nodes-page"): Verification.FOUND,
    ("lark_wiki", "LARK-WIKI-200-code-permission"): Verification.INCONCLUSIVE,
    ("lark_wiki", "LARK-WIKI-429"): Verification.INCONCLUSIVE,
    ("google_drive", "DRIVE-200-files-page"): Verification.FOUND,
    ("google_drive", "DRIVE-200-file"): Verification.FOUND,
    ("google_drive", "DRIVE-403-user-rate-limit"): Verification.INCONCLUSIVE,
    ("google_drive", "DRIVE-429"): Verification.INCONCLUSIVE,
    ("google_drive", "DRIVE-401"): Verification.INCONCLUSIVE,
    ("google_drive", "DRIVE-404"): Verification.INCONCLUSIVE,
    ("laravel", "LARAVEL-rows-clients"): Verification.FOUND,
    ("laravel", "LARAVEL-rows-users"): Verification.FOUND,
    ("laravel", "LARAVEL-rows-at-cap"): Verification.FOUND,
    ("laravel", "LARAVEL-1142"): Verification.INCONCLUSIVE,
    ("laravel", "LARAVEL-1146"): Verification.INCONCLUSIVE,
    ("laravel", "LARAVEL-3024"): Verification.INCONCLUSIVE,
    ("laravel", "LARAVEL-2006"): Verification.INCONCLUSIVE,
}


def hubspot_entity(recorded: Cassette) -> str:
    """Which operation a HubSpot recording was made against, read off its request line."""
    for fragment, entity in (
        ("/associations/", hubspot.ENTITY_ASSOCIATION),
        ("/contacts", hubspot.ENTITY_CONTACT),
        ("/deals", hubspot.ENTITY_DEAL),
    ):
        if fragment in recorded.request:
            return entity
    return hubspot.ENTITY_CLIENT


def answer_for_recording(connector: str, recorded: Cassette) -> Verification:
    """Drive one recording through one connector's reading, in that connector's reply value."""
    match connector:
        case "xero":
            entity = xero.ENTITY_CONTACT if "/Contacts" in recorded.request else xero.ENTITY_INVOICE
            return xero_answer(recorded.status, recorded.body, entity=entity)
        case "hubspot":
            return hubspot_answer(recorded.status, recorded.body, entity=hubspot_entity(recorded))
        case "laravel":
            if recorded.protocol is Protocol.HTTP:
                return laravel_answer(laravel.ViewReply(app_status=recorded.status))
            if "errno" in recorded.body:
                fault = laravel.fault_for_mysql_error(recorded.body["errno"])
                return laravel_answer(laravel.ViewReply(fault=fault))
            return laravel_answer(laravel.ViewReply(rows=tuple(recorded.body["rows"])))
        case "google_drive":
            endpoint = (
                google_drive.Endpoint.GET_FILE
                if recorded.kind is Kind.READ
                else google_drive.Endpoint.LIST_FILES
            )
            reply = google_drive.Reply(
                status=recorded.status, headers=recorded.headers, body=recorded.body
            )
            operation = google_drive.operation_for(endpoint)
            return verdict(reading("google_drive")(operation, reply))
        case "freshdesk":
            return freshdesk_answer(fresh_reply(recorded.cid))
        case "lark_base":
            return lark_base_answer(lark_reply(recorded.cid))
        case "lark_wiki":
            return lark_wiki_answer(wiki_reply(recorded.cid))
    msg = f"no way to drive {connector!r} from a recording is written in this test"
    raise AssertionError(msg)


# ------------------------------------------------------------------ the verdict
def every_valid_reading() -> list[Reading]:
    """Every reading the constructor accepts, over the whole outcome vocabulary."""
    found: list[Reading] = []
    for outcome in CallOutcome:
        for matched in (0, 1, 300):
            for complete in (False, True):
                try:
                    found.append(Reading(outcome=outcome, matched=matched, complete=complete))
                except ReadingError:
                    continue
    return found


def test_exactly_one_kind_of_reading_is_absent_and_it_is_an_answered_complete_empty_one() -> None:
    """**The property the leaf exists for, stated over every reading there is.** ABSENT
    settles an operation as FAILED, which is terminal and invites a second attempt, so the
    set of readings that produce it has to be exactly the one that means "looked everywhere
    and it is not there".

    Delete this and a verdict that calls a quota refusal, a truncated read or an unfinished
    walk absent passes every example-based test below that happens not to name that case."""
    readings = every_valid_reading()
    absent = [r for r in readings if verdict(r) is Verification.ABSENT]

    assert absent == [Reading(outcome=CallOutcome.OK, matched=0, complete=True)]
    assert {r.outcome for r in readings} == set(CallOutcome), "the sweep skipped an outcome"


def test_a_read_that_matched_anything_is_found_whether_or_not_it_finished() -> None:
    """The positive case. A record on the first page of an unfinished walk, or in a read cut
    short by a cap, has been seen. Delete this and a verdict that only ever answers
    INCONCLUSIVE passes the absence test above, and every operation stays UNKNOWN for ever."""
    for outcome in (CallOutcome.OK, CallOutcome.TRUNCATED):
        for complete in (False, True):
            if outcome is CallOutcome.TRUNCATED and complete:
                continue
            reading = Reading(outcome=outcome, matched=1, complete=complete)
            assert verdict(reading) is Verification.FOUND


def test_an_empty_read_that_did_not_reach_the_end_is_inconclusive() -> None:
    """An empty first page of a walk that has more pages has not looked where the record may
    be. Delete this and the one-line change from `complete` to `True` in the verdict passes,
    which turns every unfinished search into a verified absence."""
    assert verdict(Reading(CallOutcome.OK, matched=0, complete=False)) is Verification.INCONCLUSIVE
    assert (
        verdict(Reading(CallOutcome.TRUNCATED, matched=0, complete=False))
        is Verification.INCONCLUSIVE
    )


def test_every_outcome_that_is_not_an_answer_is_inconclusive() -> None:
    """A 429, a timeout and a refusal have not looked. Delete this and an arm of the verdict
    could map REJECTED, which is permission loss, to ABSENT, which is the collapse
    `A_REFUSAL_IS_NOT_AN_ABSENCE` names."""
    for outcome in (CallOutcome.QUOTA, CallOutcome.UNAVAILABLE, CallOutcome.REJECTED):
        assert verdict(Reading(outcome, matched=0, complete=False)) is Verification.INCONCLUSIVE


def test_a_reading_that_did_not_answer_cannot_claim_rows_or_completeness() -> None:
    """The constructor is what makes the verdict's last arm safe. Delete this and a reading
    could say "refused, and complete", and a verdict reordered to look at completeness first
    would call it absent."""
    for outcome in (CallOutcome.QUOTA, CallOutcome.UNAVAILABLE, CallOutcome.REJECTED):
        with pytest.raises(ReadingError, match="matched rows or completeness"):
            Reading(outcome, matched=1, complete=False)
        with pytest.raises(ReadingError, match="matched rows or completeness"):
            Reading(outcome, matched=0, complete=True)
    with pytest.raises(ReadingError, match="truncated"):
        Reading(CallOutcome.TRUNCATED, matched=0, complete=True)
    with pytest.raises(ReadingError, match="no reply can"):
        Reading(CallOutcome.OK, matched=-1, complete=True)
    assert Reading(CallOutcome.OK, matched=0, complete=True).complete


# ------------------------------------------------- each connector, from what was recorded
def test_every_recording_a_read_back_names_reads_as_this_test_expects() -> None:
    """**The raw payload rule.** Each reading is driven by the recorded exchange in that
    connector's own reply value, through that connector's own classifier, and the answers are
    written in this file rather than taken from the module.

    Delete this and a reading could be tested only against replies its author built, which
    for Lark is how a 91403 inside a 200 gets read as an empty table."""
    named = {(name, cid) for name, entry in READ_BACKS.items() for cid in entry.recorded}
    assert named == set(EXPECTED)
    for (name, cid), expected in EXPECTED.items():
        assert answer_for_recording(name, cassette(cid)) is expected, (name, cid)


def test_every_recording_of_a_source_is_named_by_that_connectors_read_back() -> None:
    """The table's `recorded` field checked against the corpus rather than against itself. A
    recording added for a source joins its read-back's test the day it is added.

    Delete this and a new recorded failure, say a Xero 503, could be left out of `recorded`
    and never driven through the reading at all."""
    for source in Source:
        recorded = {c.cid for c in for_source(source)}
        assert recorded <= set(READ_BACKS[source.value].recorded), source


def test_xero_reads_an_empty_ledger_as_absent_and_an_unfinished_or_failed_one_as_not() -> None:
    """No empty ledger is recorded, so the absent case is the recorded envelope with its list
    emptied. Delete this and Xero's ABSENT branch is reached by nothing, and a `more_pages`
    read of an empty first page could settle an invoice as never raised."""
    assert xero_answer(200, {"Invoices": []}) is Verification.ABSENT
    assert xero_answer(200, {"Invoices": []}, more_pages=True) is Verification.INCONCLUSIVE
    assert xero_answer(None, timed_out=True) is Verification.INCONCLUSIVE
    assert xero_answer(403, {"Title": "Forbidden"}) is Verification.INCONCLUSIVE
    assert xero_answer(503, {"Title": "Service Unavailable"}) is Verification.INCONCLUSIVE


def test_hubspot_reads_its_recorded_absence_as_absent_only_when_it_finished() -> None:
    """HUBSPOT-200-empty is the only genuine absence in the corpus. Delete this and the same
    body read with more pages behind it, or a timeout, could settle a deal as absent."""
    empty = cassette("HUBSPOT-200-empty")
    assert hubspot_answer(empty.status, empty.body) is Verification.ABSENT
    assert hubspot_answer(empty.status, empty.body, more_pages=True) is Verification.INCONCLUSIVE
    assert hubspot_answer(None, connection_failed=True) is Verification.INCONCLUSIVE
    assert hubspot_answer(429, {"message": "rate limit"}) is Verification.INCONCLUSIVE


def test_laravel_reads_an_empty_view_as_absent_and_a_withdrawn_view_as_not() -> None:
    """A view the grant no longer covers and a view that is gone are REJECTED in the
    connector, and a withdrawn contract is not an absent row. Delete this and a dropped view
    could verify every operation against it as never having happened."""
    assert laravel_answer(laravel.ViewReply(rows=())) is Verification.ABSENT
    for fault in laravel.DatabaseFault:
        assert laravel_answer(laravel.ViewReply(fault=fault)) is Verification.INCONCLUSIVE, fault


def test_freshdesk_reads_an_answered_empty_page_as_absent_and_a_refusal_as_not() -> None:
    """The recorded search with its results emptied is the one complete empty reading
    Freshdesk can give. Delete this and a 403 from a narrowed key, or a body nothing can
    project, could read as no ticket."""
    body = {**cassette("FRESH-200-search").body, "results": []}
    assert freshdesk_answer(freshdesk.Reply(status=200, body=body)) is Verification.ABSENT
    refused = freshdesk.Reply(status=403, body={"description": "Access denied"})
    assert freshdesk_answer(refused) is Verification.INCONCLUSIVE
    assert freshdesk_answer(freshdesk.Reply(status=502)) is Verification.INCONCLUSIVE
    unreadable = freshdesk.Reply(status=200, body="<html>proxy</html>")
    assert freshdesk_answer(unreadable) is Verification.INCONCLUSIVE


def test_lark_base_reads_only_a_finished_empty_list_as_absent() -> None:
    """Built from the recorded envelope. Delete this and an empty page with `has_more` set, a
    not-found business code or a single-record reply with no `has_more` at all could each
    settle a record as absent."""
    finished = lark_base.LarkReply(status=200, body=emptied("LARK-200-records", has_more=False))
    assert lark_base_answer(finished) is Verification.ABSENT
    unfinished = lark_base.LarkReply(status=200, body=emptied("LARK-200-records"))
    assert lark_base_answer(unfinished) is Verification.INCONCLUSIVE
    not_found = lark_base.LarkReply(status=200, body={"code": 1254043, "msg": "NotFound"})
    assert lark_base_answer(not_found) is Verification.INCONCLUSIVE
    single = lark_base.LarkReply(status=200, body={"code": 0, "data": {"record": {}}})
    assert lark_base_answer(single) is Verification.INCONCLUSIVE
    assert lark_base_answer(lark_base.LarkReply(status=503)) is Verification.INCONCLUSIVE


def test_lark_wiki_reads_only_a_finished_empty_listing_as_absent() -> None:
    """Driven by the Lark recordings, which share the envelope. Delete this and a listing that
    says there is more and names no token, or a body with no code in it, could read as a page
    nobody wrote."""
    finished = lark_wiki.LarkReply(status=200, body=emptied("LARK-200-records", has_more=False))
    assert lark_wiki_answer(finished) is Verification.ABSENT
    tokenless = lark_wiki.LarkReply(
        status=200, body=emptied("LARK-200-records", has_more=True, page_token="")
    )
    assert lark_wiki_answer(tokenless) is Verification.INCONCLUSIVE
    continued = lark_wiki.LarkReply(status=200, body=emptied("LARK-200-records"))
    assert lark_wiki_answer(continued) is Verification.INCONCLUSIVE
    assert lark_wiki_answer(lark_wiki.LarkReply(status=200, body={})) is Verification.INCONCLUSIVE
    assert lark_wiki_answer(lark_wiki.LarkReply(status=429)) is Verification.INCONCLUSIVE


def test_drive_never_reads_a_not_found_as_absent_and_can_read_a_finished_listing_as_absent() -> (
    None
):
    """Drive's 404 means gone or not visible to us, and the source does not say which. Delete
    this and a file somebody unshared verifies as never created. The absent sibling is here
    so a reading that is inconclusive for everything fails too."""
    assert drive_answer(google_drive.Reply(status=200, body={"files": []})) is Verification.ABSENT
    listed = google_drive.Reply(status=200, body={"files": [a_documented_drive_file()]})
    assert drive_answer(listed) is Verification.FOUND
    more = google_drive.Reply(status=200, body={"files": [], "nextPageToken": "t1"})
    assert drive_answer(more) is Verification.INCONCLUSIVE
    for status in (404, 403, 401, 503):
        reply = google_drive.Reply(status=status, body={"error": {"code": status}})
        assert drive_answer(reply) is Verification.INCONCLUSIVE, status


def test_a_read_back_built_from_a_refusal_leaves_the_operation_unknown() -> None:
    """End to end through `brain.ops.idempotency.verify`, which is where a read-back's answer
    is spent. A recorded permission failure must put the record back in UNKNOWN and a
    recorded match must settle it.

    Delete this and the readings could be correct in isolation and wired to the machine in a
    shape that settles the wrong state."""
    operation = Operation(
        key=derive_key(principal_id="u_one", tool="lark_wiki.create_page", intent_ref="run_1"),
        connector="lark_wiki",
        tool="lark_wiki.create_page",
        principal_id="u_one",
        intent_ref="run_1",
        state=OperationState.UNKNOWN,
    )

    refused = verify(operation, lambda _: lark_wiki_answer(wiki_reply("LARK-200-code-permission")))
    found = verify(operation, lambda _: lark_wiki_answer(wiki_reply("LARK-200-records")))

    assert refused.state is OperationState.UNKNOWN
    assert found.state is OperationState.SUCCEEDED


# ------------------------------------------------------------------ findings against facts
def test_the_two_connectors_recorded_as_read_only_really_are() -> None:
    """Two findings claim a write cannot be issued as built. Checked against the connectors
    rather than against the sentence, so the day one of them gains a write credential the
    finding is wrong in a test rather than in a file nobody rereads."""
    ref = SecretRef(path="connectors/creds/laravel", role=VaultRole.APPLICATION)
    connection = laravel.LaravelConnection(
        schema="portal", bounds=laravel.ReadBounds(max_rows=200, timeout_seconds=5.0)
    )
    visibility = {entity: brain_scope() for entity in laravel.ENTITIES}
    built = laravel.laravel_manifest(connection, ref=ref, visibility=visibility)
    assert built.credential.mode is AccessMode.READ_ONLY

    writing = CredentialBinding(
        ref=SecretRef(path="connectors/creds/lark_wiki", role=VaultRole.APPLICATION),
        mode=AccessMode.WRITE,
        write_granted_by="u_owner",
    )
    with pytest.raises(lark_wiki.LarkWikiError, match="write-capable binding"):
        lark_wiki.assert_read_only(writing)
    lark_wiki.assert_read_only(
        CredentialBinding(
            ref=SecretRef(path="connectors/creds/lark_wiki", role=VaultRole.APPLICATION)
        )
    )


def brain_scope() -> Any:
    from brain.core.scope import Clause, Op, Scope

    return Scope(clauses=(Clause(field="department", op=Op.IN, value=("one",)),))


def test_an_entry_resting_on_no_recording_is_the_one_that_says_so() -> None:
    """The corpus says which sources are recorded, not the table. Drive had none until its
    documented shapes were recorded, and its entry stopped saying so in the same change.

    Delete this and a recording added for a source would leave its entry still claiming there
    is none, or an entry for a recorded source could claim the same."""
    recorded_sources = {source.value for source in Source}
    for name, entry in READ_BACKS.items():
        says_none = NOTHING_IS_RECORDED in entry.findings
        has_none = name not in recorded_sources and not entry.recorded
        assert says_none is has_none, name
    assert READ_BACKS["google_drive"].recorded


def test_the_drive_entry_states_that_a_not_found_cannot_prove_absence() -> None:
    """The Drive finding is checked against the connector: a 404 is raised as its own type,
    neither refusal nor absence. Delete this and the finding can fall off the entry while the
    ambiguity it describes is still in the connector, and the table reads as though Drive can
    prove absence by file id."""
    with pytest.raises(google_drive.DriveNotFoundError):
        google_drive.assert_answered(google_drive.Reply(status=404, body={"error": {"code": 404}}))
    assert (
        write_verification.DRIVE_A_NOT_FOUND_CANNOT_PROVE_ABSENCE
        in READ_BACKS["google_drive"].findings
    )


# ------------------------------------------------------------------ discovery and the gate
def test_every_connector_the_package_holds_is_stated_in_the_read_back_table() -> None:
    """**The gate.** A connector added to `brain.connectors` with no entry fails here by
    existing, and one that declares a write with no reading fails here too.

    Delete this and a new connector's operations could be left with no way out of UNKNOWN,
    found only when a crash leaves one there."""
    assert read_back_gaps(connectors()) == ()


def test_discovery_agrees_with_the_cassette_contracts_own_list_of_connectors() -> None:
    """Two derivations of "which modules are connectors" that must agree: this module's, from
    whether a module builds a manifest, and the cassette contract's, from a named exclusion
    list. Delete this and a connector whose factory lost its return annotation silently
    leaves discovery, and the gate above passes over it."""
    listed = {
        info.name
        for info in pkgutil.iter_modules(brain.connectors.__path__)
        if info.name not in NOT_A_CONNECTOR
    }
    assert set(connectors()) == listed
    assert len(listed) >= 7, f"only {sorted(listed)} were found, so this compared almost nothing"


def test_a_connector_with_no_entry_is_a_gap() -> None:
    """The refusal. Delete this and `read_back_gaps` could return nothing for any input and
    the gate above would still be green."""
    gaps = read_back_gaps({"newsource": False}, table={})
    assert len(gaps) == 1 and "newsource" in gaps[0] and "no read-back entry" in gaps[0]


def test_a_connector_that_writes_with_no_read_back_path_is_a_gap_and_a_read_only_one_is_not() -> (
    None
):
    """The rule `NO_READ_BACK_MEANS_READ_ONLY` states, checked where a table can break it. Both
    halves, because a gate that refused every entry with no reading would also refuse a
    read-only connector that has nothing to read back."""
    nothing = ReadBack(reading=None, recorded=(), findings=(NO_READ_BACK_PATH, NOTHING_IS_RECORDED))

    writes = read_back_gaps({"source": True}, table={"source": nothing})
    reads = read_back_gaps({"source": False}, table={"source": nothing})

    assert len(writes) == 1 and "declares a write" in writes[0]
    assert reads == ()


def test_an_entry_for_a_connector_that_does_not_exist_is_a_gap() -> None:
    """A stale entry states a finding about nothing, which reads as coverage. Delete this and a
    renamed connector keeps its old entry and gains no new one without any test noticing."""
    entry = READ_BACKS["xero"]
    gaps = read_back_gaps({}, table={"retired": entry})
    assert len(gaps) == 1 and "'retired'" in gaps[0]
    assert read_back_gaps({"retired": False}, table={"retired": entry}) == ()


def test_an_entry_must_state_what_it_lacks() -> None:
    """An entry with no reading, or with no recording, carries the finding that says so or it
    is refused. Delete this and a table can omit a connector's gap by writing an entry that is
    silent about it."""
    with pytest.raises(ReadingError, match="state it as a finding"):
        ReadBack(reading=None, recorded=(), findings=(NOTHING_IS_RECORDED,))
    with pytest.raises(ReadingError, match="no recorded exchange"):
        ReadBack(reading=write_verification.classified_reading, recorded=(), findings=())
    assert ReadBack(
        reading=write_verification.classified_reading, recorded=("XERO-429",), findings=()
    ).recorded


def test_discovery_counts_a_module_that_builds_a_manifest_and_not_one_that_only_uses_one() -> None:
    """`throttle` takes a manifest as a parameter throughout and builds none; `xero` builds
    one. Delete this and a discovery that matched on the word would count framework modules
    as connectors, and the gate would demand entries for them."""
    assert builds_a_manifest(xero) is True
    assert builds_a_manifest(throttle) is False
    assert builds_a_manifest(write_verification) is False


def test_a_factory_counts_where_it_is_defined_and_not_where_it_is_imported() -> None:
    """A module that imports another connector's factory is not a second connector, and a
    factory annotated with the class itself counts as much as one annotated with its name.

    Delete this and discovery could count every module that imports a factory, or miss a
    connector written without postponed annotations, and both look the same from the gate."""

    def by_class() -> None: ...

    def by_name() -> None: ...

    for factory, annotation in ((by_class, ConnectorManifest), (by_name, "ConnectorManifest")):
        own = types.ModuleType("brain.connectors.somewhere")
        factory.__module__ = own.__name__
        factory.__annotations__ = {"return": annotation}
        vars(own)["factory"] = factory
        assert builds_a_manifest(own) is True, annotation

    borrower = types.ModuleType("brain.connectors.borrower")
    vars(borrower)["xero_manifest"] = xero.xero_manifest
    assert builds_a_manifest(borrower) is False


def test_the_write_scan_finds_a_side_effect_and_finds_nothing_in_a_read_only_declaration() -> None:
    """The syntactic half of the gate, written against source text. Delete this and a scan
    that never returns True makes every connector read-only to the gate, including the first
    one that writes."""
    writing = (
        "ToolDeclaration(name='x.create_y', description='d', entity='y', "
        "side_effect=SideEffect.MONEY, verifies_write=True)"
    )
    reading = "ToolDeclaration(name='x.read_y', description='d', entity='y')"
    explicit = "manifest.ToolDeclaration(name='x.read_y', side_effect=SideEffect.NONE)"
    unreadable = "ToolDeclaration(**settings)"
    flag_only = "ToolDeclaration(name='x.read_y', verifies_write=True)"
    elsewhere = "Something(side_effect=SideEffect.WRITE)"

    assert declares_a_write(writing) is True
    assert declares_a_write(unreadable) is True
    assert declares_a_write(flag_only) is True
    assert declares_a_write(reading) is False
    assert declares_a_write(explicit) is False
    assert declares_a_write("ToolDeclaration(verifies_write=False)") is False
    assert declares_a_write(elsewhere) is False
    assert declares_a_write("ToolDeclaration(side_effect=SideEffect.WRITE)") is True
    assert declares_a_write("ToolDeclaration(side_effect=Kind.NONE)") is True


def test_no_connector_in_this_repository_declares_a_write_today() -> None:
    """**The honest gap, written to go red on the right day.** Every reading in this file is
    for a write nobody issues, and the request that would look for one is not built: see
    `THE_QUERY_HALF_IS_OWED_BY_THE_FIRST_WRITE`.

    When this fails, a connector has declared a side effect. The fix is not to change this
    assertion: it is to write that connector's read-back request and decide its search
    freshness, and then to rewrite this test as the claim that the request exists."""
    writing = sorted(name for name, writes in connectors().items() if writes)
    assert writing == [], (
        f"{writing} now declare a write, so the query half of their read-back is owed. "
        f"{write_verification.THE_QUERY_HALF_IS_OWED_BY_THE_FIRST_WRITE}"
    )


def test_the_write_scan_agrees_with_the_manifests_the_connectors_actually_build() -> None:
    """The syntactic scan against the runtime declarations, which are a second account of the
    same fact. Delete this and a connector that builds its tools somewhere the scan cannot see
    could declare a write the gate never learns about."""
    from tests.unit.test_install_docs import manifests

    built = manifests()
    runtime_writes = any(tool.side_effect is not SideEffect.NONE for m in built for tool in m.tools)

    assert len(built) == len(connectors())
    assert runtime_writes is any(connectors().values())
