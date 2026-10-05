"""Every recording, replayed through the connector it belongs to, and every declaration covered.

`tests/fixtures/cassettes/` says what each recording is an example of and what the
connector's own code must conclude from it, one file per source, and each file carries the
replay that drives its recordings through that connector's own code. This file is where that
is checked, and it is the check that made "tested against recorded responses" a property
rather than a word: until it existed, the contract invariant asked only whether a connector's
test file mentioned the cassettes, and `test_google_drive.py` satisfied it by saying none
existed.

**A replay calls the connector's own functions and nothing of this file's.** Each one hands a
recording to the reader, interpreter, walk or projection the connector ships, and reads the
outcome off what that code did: the reply it built, the exception it raised, the page it asked
for next, the record it kept. A replay that classified the recording itself would be a second
implementation of the connector, and it would agree with the recording by construction.

**The sweep is written from the manifests, not from the recordings.** Every tool a connector
declares must be answered by a recording of its own, every projection must be fed by one whose
rows the connector actually keeps, and every connector must have a page that says there is
more, a rate limit and an error. A connector that declares a tool nobody recorded fails
`test_every_declared_tool_is_answered_by_a_recording`, and the exemptions below are named with
the reason each cannot be recorded.

What this does not prove is that a vendor answers this way today. Every recording is a
documented shape, and `test_no_recording_claims_a_live_read_it_does_not_date` holds that.

Task ids: M0.6.5, M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime

import pytest

from brain.connectors import laravel, lark_base, lark_wiki
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import shipped
from brain.connectors.manifest import ConnectorManifest
from brain.ops.connector_recordings import RECORDINGS, recorded_in_words
from tests.fixtures.cassettes import (
    CASSETTES,
    FETCHED_AT,
    FILES,
    Cassette,
    Expect,
    Kind,
    Origin,
    Replayed,
    Source,
)
from tests.fixtures.cassettes.lark_base import replay as _replay_lark_base

#: One replay per connector, read off each source's cassette file. A connector joins by having one.
REPLAYS: Mapping[str, Callable[[Cassette], Replayed]] = {
    name: file.replay for name, file in FILES.items()
}


def _manifests() -> dict[str, ConnectorManifest]:
    """Every connector's manifest, built by the builder its cassette file names."""
    return {name: file.manifest() for name, file in FILES.items()}


#: Connectors whose tools are named after a table a deployment chooses, so a recording names
#: the table as `{entity}`.
NAMED_AFTER_THE_TABLE = frozenset(
    name for name, file in FILES.items() if file.tools_named_after_the_table
)

#: Kinds a connector need not have, and why each cannot be recorded for it.
NOT_RECORDABLE: Mapping[tuple[str, Kind], str] = {
    (name, kind): why for name, file in FILES.items() for kind, why in file.not_recordable.items()
}

#: Projections whose positive path no documented shape can replay, and why.
PROJECTION_NOT_REPLAYABLE: Mapping[tuple[str, str], str] = {
    (name, entity): why
    for name, file in FILES.items()
    for entity, why in file.projection_not_replayable.items()
}


def _declared(name: str, manifest: ConnectorManifest) -> tuple[set[str], set[str]]:
    tools = {
        tool.name.replace(tool.entity, "{entity}") if name in NAMED_AFTER_THE_TABLE else tool.name
        for tool in manifest.tools
    }
    projections = {
        "{entity}" if name in NAMED_AFTER_THE_TABLE else one.entity for one in manifest.projections
    }
    return tools, projections


def _connector_names() -> set[str]:
    return set(shipped())


ANSWERING = frozenset({Kind.LIST, Kind.READ, Kind.PAGINATION})
ANSWERED = frozenset({Expect.ANSWERED, Expect.ABSENT, Expect.MORE_TO_READ})


@pytest.mark.parametrize("recorded", CASSETTES, ids=[c.cid for c in CASSETTES])
def test_every_recording_replays_to_what_it_says_through_its_own_connector(
    recorded: Cassette,
) -> None:
    """**The replay.** The connector's own code reads the recording and must conclude what the
    recording says, and a success that feeds a projection must leave kept records.

    Delete this and a recording can say a 429 is a rate limit while the connector reads it as
    an empty table, with every other test green."""
    replayed = REPLAYS[recorded.source](recorded)

    assert replayed.outcome is recorded.expect, (
        f"{recorded.cid}: the connector concluded {replayed.outcome}, the recording says "
        f"{recorded.expect}"
    )
    replayable = (recorded.source, recorded.projects) not in PROJECTION_NOT_REPLAYABLE
    if recorded.projects and recorded.expect in ANSWERED and replayable:
        assert replayed.projected > 0, f"{recorded.cid} feeds a projection and kept nothing"
    leaked = [
        (one.source_id, name)
        for one in replayed.kept
        for name, value in one.fields.items()
        if "CANARY" in str(value)
    ]
    assert not leaked, f"{recorded.cid} kept a value a canary guards: {leaked}"


def test_the_replay_tells_a_refusal_from_an_absence_and_an_outage() -> None:
    """The positive sibling of the replay: the four outcomes are all reached, so a replay that
    returned one answer for everything could not pass.

    Delete this and every replay can collapse to ANSWERED with the parametrised test failing
    only for the recordings somebody happens to read."""
    reached = {REPLAYS[c.source](c).outcome for c in CASSETTES}
    assert {
        Expect.ANSWERED,
        Expect.ABSENT,
        Expect.MORE_TO_READ,
        Expect.RATE_LIMITED,
        Expect.REFUSED,
        Expect.UNREACHABLE,
        Expect.NOT_FOUND,
    } <= reached


def test_every_connector_has_a_replay_and_a_manifest() -> None:
    """Discovered, so a connector added to the package fails here until it is replayed.

    Delete this and the sweeps below compare nothing for the connector nobody registered."""
    assert _connector_names() == set(REPLAYS) == set(_manifests())


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_declared_tool_is_answered_by_a_recording(name: str) -> None:
    """**The sweep.** A tool the manifest declares with no recording answering it is a tool
    nobody has run against the source's shape, and it fails here by name.

    Delete this and a fourth HubSpot tool ships described as tested."""
    tools, _ = _declared(name, _manifests()[name])
    recorded = [c for c in CASSETTES if c.source == name]
    answered = {
        tool for c in recorded if c.kind in ANSWERING and c.expect in ANSWERED for tool in c.tools
    }
    assert tools, f"{name} declares no tools, so this compared nothing"
    assert not tools - answered, f"{name} declares tools no recording answers: {tools - answered}"
    orphaned = {tool for c in recorded for tool in c.tools} - tools
    assert not orphaned, f"recordings for {name} name tools it does not declare: {orphaned}"


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_declared_projection_is_fed_by_a_recording(name: str) -> None:
    """A projection no recording feeds is a table of kept rows nobody has built from the source's
    shape. The exceptions are named with the reason.

    Delete this and a projection can be declared, digested and connected with no row ever
    having been kept from anything the vendor sends."""
    _, projections = _declared(name, _manifests()[name])
    fed = {
        c.projects for c in CASSETTES if c.source == name and c.projects and c.expect in ANSWERED
    }
    missing = projections - fed
    assert not missing, f"{name} projects {missing} and no recording feeds it"


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_connector_has_a_page_a_rate_limit_and_an_error(name: str) -> None:
    """Pagination, rate limit and error are what a mock leaves out. Each is required of every
    connector unless `NOT_RECORDABLE` says why it cannot happen.

    Delete this and a connector can be recorded answering and never failing."""
    kinds = {c.kind for c in CASSETTES if c.source == name}
    for required in (Kind.PAGINATION, Kind.RATE_LIMIT, Kind.ERROR):
        if (name, required) in NOT_RECORDABLE:
            assert required not in kinds, (
                f"{name} is exempt from {required} and has a recording of it; drop the exemption"
            )
            continue
        assert required in kinds, f"{name} has no {required} recording"


def test_the_exemptions_name_connectors_and_kinds_that_exist() -> None:
    """The guard on the lists above: an exemption naming a typo exempts nothing and reads as a
    considered decision.

    Delete this and `NOT_RECORDABLE` can quietly outlive the connector it described. No
    projection has been exempt since 2026-09-30, when Google Drive's listing gained the reading
    that reduces its permissions to a verdict, so the second list may be empty."""
    names = _connector_names()
    assert NOT_RECORDABLE
    assert {name for name, _ in NOT_RECORDABLE} <= names
    for (name, entity), _why in PROJECTION_NOT_REPLAYABLE.items():
        assert entity in _declared(name, _manifests()[name])[1]


def test_no_recording_claims_a_live_read_it_does_not_date() -> None:
    """A live capture is a claim that a real account answered, and it has to say when. Nothing
    in the corpus makes that claim today, and a documented shape must name its page.

    Delete this and a recording can be relabelled live with nothing behind it, and the console
    would say so."""
    for c in CASSETTES:
        assert c.reference.strip(), f"{c.cid} names no reference"
        if c.origin is Origin.LIVE_CAPTURE:
            datetime.fromisoformat(c.captured_at)
        else:
            assert not c.captured_at, f"{c.cid} is a documented shape with a capture time"
    assert all(c.origin is Origin.DOCUMENTED_SHAPE for c in CASSETTES)


def test_the_console_record_of_recordings_agrees_with_the_corpus() -> None:
    """**Two records of one fact.** `brain.ops.connector_recordings.RECORDINGS` is what the
    Connectors screen says about each connector, and the corpus and this file are what make it
    true. Tested and gaps are compared here, never believed.

    Delete this and the screen can say a connector is tested against recorded responses the day
    its recordings are deleted."""
    assert set(RECORDINGS) == set(REPLAYS)
    for name, said in RECORDINGS.items():
        recorded = [c for c in CASSETTES if c.source == name]
        assert said.tested is bool(recorded)
        assert said.live_capture is any(c.origin is Origin.LIVE_CAPTURE for c in recorded)
        gaps = tuple(
            sorted(why for (who, _), why in PROJECTION_NOT_REPLAYABLE.items() if who == name)
        )
        assert said.not_replayed == gaps
        words = recorded_in_words(name)
        assert ("live account" in words) and (
            "not answers captured from a live account" in words
        ) is not said.live_capture


# ------------------------------------------ what the documented shapes found about the code
def test_a_documented_wiki_page_is_admitted_on_its_settings_and_never_its_listing() -> None:
    """**A finding, pinned.** Lark's documented node listing carries no permission field, so a
    listed page is UNDETERMINED and `admit_page` withholds it; what admits it is its documented
    permission settings saying `lock_switch` false, and a locked page stays withheld. Until
    2026-09-28 the verdict came off an undocumented listing key and the wiki answered nothing.

    Delete this and the day somebody reads a verdict off the listing again nothing notices."""
    from tests.unit.test_lark_wiki import SPACES

    listing = next(c for c in CASSETTES if c.cid == "LARK-WIKI-200-nodes-page")
    item = listing.body["data"]["items"][0]
    node = lark_wiki.node_from(item, space_id=SPACES[0].space_id)
    spaces = lark_wiki.declarations_by_space(SPACES)

    assert not {lark_wiki.PERMISSION_KEY, lark_wiki.LOCK_KEY} & set(item)
    assert node.restriction is lark_wiki.NodeRestriction.UNDETERMINED
    with pytest.raises(lark_wiki.PageWithheldError):
        lark_wiki.admit_page(node, spaces=spaces)
    for cid, admitted in (
        ("LARK-WIKI-200-permission-follows", True),
        ("LARK-WIKI-200-permission-locked", False),
    ):
        recorded = next(c for c in CASSETTES if c.cid == cid)
        verdict = lark_wiki.permission_of(
            lark_wiki.LarkReply(status=recorded.status, body=recorded.body)
        )
        judged = replace(node, restriction=verdict)
        if admitted:
            assert lark_wiki.admit_page(judged, spaces=spaces).node.node_id == node.node_id
        else:
            with pytest.raises(lark_wiki.PageWithheldError):
                lark_wiki.admit_page(judged, spaces=spaces)
    assert "carries no permissions" in recorded_in_words("lark_wiki")


def test_lark_documents_its_wait_in_a_header_the_connectors_do_not_read() -> None:
    """**A finding, pinned.** Lark states the wait in `x-ogw-ratelimit-reset`; `lark_base` reads
    only `Retry-After`, so on the documented 429 it waits its own sixty seconds. That is never
    shorter than the documented reset here, which is why it is recorded rather than fixed.

    Delete this and a documented reset longer than the fallback would go unnoticed."""
    recorded = next(c for c in CASSETTES if c.cid == "LARK-429")
    reply = lark_base.LarkReply(
        status=recorded.status, headers=recorded.headers, body=recorded.body
    )

    assert lark_base.wait_seconds(reply) == lark_base.WAIT_WHEN_UNSTATED
    assert lark_base.wait_seconds(reply) >= float(recorded.headers["x-ogw-ratelimit-reset"])


@pytest.mark.parametrize(
    ("errno", "fault"),
    [
        (1142, laravel.DatabaseFault.ACCESS_DENIED),
        (1143, laravel.DatabaseFault.ACCESS_DENIED),
        (1146, laravel.DatabaseFault.UNKNOWN_VIEW),
        (3024, laravel.DatabaseFault.TIMED_OUT),
        (2006, laravel.DatabaseFault.UNAVAILABLE),
        (1064, laravel.DatabaseFault.UNAVAILABLE),
    ],
)
def test_a_mysql_error_number_is_the_fault_mysql_documents_it_as(
    errno: int, fault: laravel.DatabaseFault
) -> None:
    """The table a live reader and a replay share. 1064 is a number nobody listed, and it is
    read as the database not answering rather than as an empty view or a withdrawn grant.

    Delete this and a dropped view can be classified as an outage, which pages the wrong person."""
    assert laravel.fault_for_mysql_error(errno) is fault


def test_a_withdrawn_view_is_never_an_empty_one_when_replayed() -> None:
    """The positive and negative halves of the table meeting the interpreter.

    Delete this and 1146 could map to a fault that `interpret` reads as zero rows."""
    from tests.unit.test_laravel import a_read

    gone = laravel.interpret(
        a_read(),
        laravel.ViewReply(fault=laravel.fault_for_mysql_error(1146)),
        fetched_at=FETCHED_AT,
    )
    assert gone.outcome is laravel.LaravelOutcome.REFUSED
    assert gone.rows is None


def test_a_recording_for_a_connector_that_is_not_one_is_refused() -> None:
    """Every cassette file is named after a shipped connector, so no recording sits unreplayed.
    The legacy `Source` names are held to the same set, so one cannot outlive its connector.

    Delete this and a cassette file can outlive its connector, replayed through nothing."""
    assert set(FILES) == _connector_names()
    assert {one.value for one in Source} <= _connector_names()


def test_a_contract_error_in_a_replay_is_not_swallowed() -> None:
    """A body that does not say whether there is more is a failure, not an answer. The replay
    must let the connector's own refusal through rather than classify it.

    Delete this and a replay that caught everything would pass every recording."""
    broken = Cassette(
        cid="LARK-broken",
        source="lark_base",
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=200,
        body={"code": 0, "data": {"items": []}},
        kind=Kind.LIST,
        expect=Expect.ABSENT,
        origin=Origin.DOCUMENTED_SHAPE,
        reference="test",
    )
    with pytest.raises(ConnectorContractError):
        _replay_lark_base(broken)
