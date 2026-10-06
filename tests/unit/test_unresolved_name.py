"""A name that belongs to more than one client the asker reads is said to be ambiguous, and a
withheld record never makes it so (M14.6.5).

Run against the real `fast_lane.respond`, the real `answer_lane` and the real row plane, with a
stand-in only for the registry, which `StoredAmbiguity` is on an install and the last test here
runs against a real database.

**Three properties carry the weight.** Two in-reach records that are two clients are answered
with the unresolved sentence and no figure from either. One record the asker reads is answered
exactly as it was before this existed, and the registry is not even asked, so a second record
the asker may not read cannot change a byte of the reply. And the review reference reaches only
a reader holding the reviewer's capability over everything, so whether a review item is open is
never told to anybody else.

Task ids: M14.6.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.core.scope import Scope
from brain.gate.abstain import AbstentionReason
from brain.gate.answer import (
    THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED,
    Answered,
    answer_lane,
    unresolved_text,
)
from brain.gate.context import Channel
from brain.gate.fast_lane import (
    NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS,
    AmbiguityReader,
    FastLaneAnswer,
    FastLaneUnresolved,
    FastPathRule,
    respond,
)
from brain.gate.finish import Origin
from brain.gate.streaming import Event, frames
from brain.identity.first_administrator import ADMINISTRATION
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.rows import RowQuery, RowTool
from brain.resolution.guardrails import REVIEWER_CAPABILITY, UNRESOLVED_TEXT, UnresolvedNotice
from tests.unit.test_streaming import decode

#: Pinned far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 4, 12, tzinfo=UTC)

CLIENTS = TableClassification(
    entity="client",
    rules=(
        ColumnRule(
            column="name",
            required_capability=Capability(value="read:client.name"),
            classification=Classification.INTERNAL,
        ),
        ColumnRule(
            column="hours_remaining",
            required_capability=Capability(value="read:client.hours_remaining"),
            classification=Classification.CONFIDENTIAL,
        ),
    ),
)
TOOL = RowTool(source="laravel", classification=CLIENTS, description="Read a client.")
HOURS = FastPathRule(
    rule_id="client_hours_remaining",
    template="hours left on {client}",
    slot="client",
    source="laravel",
    entity="client",
    match_field="name",
    answer_field="hours_remaining",
)
QUESTION = "hours left on Acme"
ACME = {"entity": "client", "id": "c_447", "name": "Acme", "hours_remaining": "37"}
OTHER = {"entity": "client", "id": "c_448", "name": "Acme", "hours_remaining": "40"}
KEY_ACME = ("laravel", "client", "c_447")
KEY_OTHER = ("laravel", "client", "c_448")
SEES = ("read:client", "read:client.name", "read:client.hours_remaining")


def ents(*caps: str, scope: Scope | None = None, principal: str = "p_asker") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=c), scope=scope or Scope()) for c in caps),
    )


class Rows:
    """A `RowSource` answering with fixed rows."""

    def __init__(self, *returns: Mapping[str, Any]) -> None:
        self.returns = list(returns)

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        return self.returns


class Registry:
    """An `AmbiguityReader` that answers from a fixed mapping and records whether it was asked."""

    def __init__(self, current: Mapping[tuple[str, str, str], str], review: str | None) -> None:
        self.current = dict(current)
        self.review = review
        self.asked: list[object] = []

    async def current_entities(
        self, records: Sequence[tuple[str, str, str]]
    ) -> Mapping[tuple[str, str, str], str]:
        self.asked.append(tuple(records))
        return {one: self.current[one] for one in records if one in self.current}

    async def open_review(self, entity_ids: Sequence[str]) -> str | None:
        self.asked.append(tuple(entity_ids))
        return self.review


class Sink:
    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        return None


def two_clients(review: str | None = "rev_1") -> Registry:
    return Registry({KEY_ACME: "ent_a", KEY_OTHER: "ent_b"}, review)


def lane(
    *rows: Mapping[str, Any], reach: EntitlementSet, ambiguity: AmbiguityReader | None
) -> FastLaneAnswer | FastLaneUnresolved | None:
    return asyncio.run(
        respond(
            QUESTION,
            rules=[HOURS],
            readers={("laravel", "client"): TOOL.reader(Rows(*rows))},
            entitlement=reach,
            now=NOW,
            ambiguity=ambiguity,
        )
    )


def asked(
    *rows: Mapping[str, Any], reach: EntitlementSet, ambiguity: AmbiguityReader | None
) -> Answered:
    return asyncio.run(
        answer_lane(
            QUESTION,
            origin=Origin(
                trace_id="t-unresolved",
                principal=Principal(
                    id=reach.principal_id,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name="Asker",
                ),
                channel=Channel.CONSOLE,
            ),
            recorders=(),
            rules=[HOURS],
            readers={("laravel", "client"): TOOL.reader(Rows(*rows))},
            entitlement=reach,
            policies={"client": CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=Sink(),
            now=NOW,
            clock=lambda: NOW,
            ambiguity=ambiguity,
        )
    )


def said(answered: Answered) -> str:
    return "".join(
        one.data for one in decode(frames(answered.frames)) if one.event == Event.TEXT.value
    )


# ------------------------------------------------------------------- the fast lane decides


def test_two_records_the_registry_calls_two_clients_are_named_as_unresolved() -> None:
    """The positive case: two records the asker read, two current entities, and the lane says
    so, with the reference the registry has open between exactly those two entities.

    Delete this and the lane can go back to falling through, where a model picks one of two
    clients or adds their figures together and nothing reads the result."""
    registry = two_clients()

    found = lane(ACME, OTHER, reach=ents(*SEES), ambiguity=registry)

    assert found == FastLaneUnresolved(review_ref="rev_1")
    assert registry.asked == [(KEY_ACME, KEY_OTHER), ("ent_a", "ent_b")]


def test_two_records_that_are_one_client_still_fall_through() -> None:
    """Two records merged into one entity are one client, and the name is not ambiguous.

    Delete this and every client a source holds twice, which is what a merge exists for, is
    answered as ambiguous for ever."""
    registry = Registry({KEY_ACME: "ent_a", KEY_OTHER: "ent_a"}, "rev_1")

    assert lane(ACME, OTHER, reach=ents(*SEES), ambiguity=registry) is None


def test_a_record_the_registry_has_not_linked_is_not_called_a_client() -> None:
    """A record the registry never linked is one it has said nothing about, so the name is not
    known to be ambiguous and the lane falls through as it did before.

    Delete this and two rows of one service in an uploaded price list, which no registry links,
    are told to the asker as two clients."""
    registry = Registry({KEY_ACME: "ent_a"}, None)

    assert lane(ACME, OTHER, reach=ents(*SEES), ambiguity=registry) is None
    assert lane(ACME, OTHER, reach=ents(*SEES), ambiguity=Registry({}, None)) is None


def test_without_a_registry_two_records_fall_through_as_before() -> None:
    """A process with no database hands no reader, and nothing changes for it.

    Delete this and a lane with no registry could invent an ambiguity it has no evidence for."""
    assert lane(ACME, OTHER, reach=ents(*SEES), ambiguity=None) is None


def test_one_record_the_asker_reads_is_answered_and_the_registry_is_not_asked() -> None:
    """**The withheld record's half.** A record the asker may not read never comes back from the
    row plane, so the lane holds one record and answers it, and the registry, which knows about
    both, is not asked anything. Asking it would be the only way a withheld record could reach
    this branch.

    Delete this and the registry's knowledge of a record the asker may not read could decide
    what they are told about one they may."""
    registry = two_clients()

    found = lane(ACME, reach=ents(*SEES), ambiguity=registry)

    assert isinstance(found, FastLaneAnswer)
    assert [one.id for one in found.result.records] == ["c_447"]
    assert registry.asked == []


# ----------------------------------------------------------------- what the asker is told


def test_two_in_reach_clients_are_told_the_unresolved_sentence_and_no_figure() -> None:
    """The asker reading both records is told the one sentence, and neither client's figure,
    and the outcome is recorded as records retrieved and not answering.

    Delete this and the lane can name the ambiguity in the trace and still hand the asker a
    figure, or both."""
    answered = asked(ACME, OTHER, reach=ents(*SEES), ambiguity=two_clients())

    assert said(answered) == UNRESOLVED_TEXT
    assert "37" not in frames(answered.frames) and "40" not in frames(answered.frames)
    assert answered.abstention is not None
    assert answered.abstention.reason is AbstentionReason.RETRIEVED_BUT_NOT_ANSWERING


def test_a_withheld_second_record_leaves_the_reply_byte_identical() -> None:
    """**The test this leaf is held to.** An asker who reads one of two records answering to the
    name, with a registry that knows both are different clients, is sent exactly the frames they
    would be sent if the second record did not exist and there were no registry at all.

    Delete this and a reply can differ by a byte when somebody else's client shares a name with
    one the asker reads, which tells them that client exists."""
    withheld = asked(ACME, reach=ents(*SEES), ambiguity=two_clients())
    absent = asked(ACME, reach=ents(*SEES), ambiguity=None)

    assert withheld.frames == absent.frames
    assert "37" in said(withheld)


def test_only_a_reviewer_over_everything_is_handed_the_review_reference() -> None:
    """A reader holding the reviewer's capability over everything is told where to check it; one
    holding it over one department, and one not holding it, are told the plain sentence.

    Delete this and the review link can be handed to anybody whose question met an ambiguity."""
    reviewer = ents(*SEES, REVIEWER_CAPABILITY.value)
    narrow = EntitlementSet(
        principal_id="p_asker",
        grants=(
            *ents(*SEES).grants,
            Grant(capability=REVIEWER_CAPABILITY, scope=Scope.department("sales")),
        ),
    )

    assert said(asked(ACME, OTHER, reach=reviewer, ambiguity=two_clients())) == (
        UnresolvedNotice(review_ref="rev_1").render()
    )
    assert said(asked(ACME, OTHER, reach=narrow, ambiguity=two_clients())) == UNRESOLVED_TEXT
    assert said(asked(ACME, OTHER, reach=ents(*SEES), ambiguity=two_clients())) == (UNRESOLVED_TEXT)


def test_a_non_reviewer_cannot_tell_whether_a_review_item_is_open() -> None:
    """The plain sentence does not depend on whether a review item exists, so a non-reviewer's
    frames are identical either way. A reviewer with nothing open is given the plain sentence.

    Delete this and the presence of a link-shaped difference tells a non-reviewer what
    reviewers have open."""
    reach = ents(*SEES)
    with_item = asked(ACME, OTHER, reach=reach, ambiguity=two_clients("rev_1"))
    without = asked(ACME, OTHER, reach=reach, ambiguity=two_clients(None))
    reviewer = ents(*SEES, REVIEWER_CAPABILITY.value)

    assert with_item.frames == without.frames
    assert unresolved_text(FastLaneUnresolved(None), entitlement=reviewer, now=NOW) == (
        UNRESOLVED_TEXT
    )


# --------------------------------------------------------------------- the written rules


def test_the_reviewer_capability_is_one_an_administrator_is_granted() -> None:
    """Decision (c): the Owner and the Administrator review pairs. Held against the list the
    first administrator is granted rather than against itself, so a misspelt capability, which
    nobody holds, cannot pass by agreeing with its own constant.

    Delete this and the review link can be keyed on a capability no person holds."""
    from brain.resolution_routes import ENTITY_MERGE_CAPABILITY

    assert REVIEWER_CAPABILITY.value in ADMINISTRATION
    assert ENTITY_MERGE_CAPABILITY == REVIEWER_CAPABILITY


def test_the_exception_is_written_beside_the_rule_it_narrows() -> None:
    """The asker-is-never-told rule names its one exception, and the exception names the rule it
    keeps for withheld records, so a reader of either finds the other.

    Delete this and the two constants can drift into contradicting each other."""
    assert "NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS" in (
        THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED
    )
    assert "exactly the answer they would get if the other did not exist" in (
        NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS
    )


# --------------------------------------------------------------------- the registry's half


def test_the_answer_route_hands_the_lane_the_registry() -> None:
    """The answer route's call to the lane passes the registry reader the route builds from its
    own state. Read from the call expression rather than from text, so a comment naming the
    argument cannot satisfy it.

    Delete this and the route can stop passing the reader, and every ambiguous name on an install
    goes back to falling through while each unit test above stays green."""
    import ast
    import inspect

    import brain.api_routes as routes

    tree = ast.parse(inspect.getsource(routes.answered_for))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "answer_lane"
    ]
    passed = [
        ast.unparse(one.value) for call in calls for one in call.keywords if one.arg == "ambiguity"
    ]

    assert len(calls) == 1
    assert passed == ["ambiguity_of(request.app.state)"]


def test_a_process_with_a_database_hands_the_registry_and_one_without_hands_nothing() -> None:
    """A process whose state holds a session factory hands the lane the stored registry; one with
    none hands nothing, so a lane with no database falls through rather than failing on a read.

    Delete this and a process with no database can hand the lane a registry over nothing, and the
    first ambiguous name it meets is a server error."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from brain.api_routes import ambiguity_of
    from brain.resolution.ambiguity_store import StoredAmbiguity

    assert ambiguity_of(SimpleNamespace()) is None
    assert ambiguity_of(SimpleNamespace(db_sessions=object())) is None
    assert isinstance(
        ambiguity_of(SimpleNamespace(db_sessions=async_sessionmaker())), StoredAmbiguity
    )


@pytest.mark.needs_db
def test_the_stored_registry_follows_a_merge_and_finds_the_open_review() -> None:
    """`StoredAmbiguity` over a real registry: two registered records are two entities with the
    review item between them found, and after a merge both resolve to the survivor. A record
    nobody registered is left out, and a decided item is not an open one.

    Delete this and the SQL that walks the forwarding pointer can stop at the merged entity,
    calling one client two."""
    import json

    from brain.db import normalise_database_url
    from brain.resolution.ambiguity_store import StoredAmbiguity
    from brain.resolution.canonical import EntityType, SourceRef
    from brain.resolution.merge import MoneyBearing, MoneyCheck, ReviewedMerge
    from brain.resolution.merge_store import merge_entities
    from brain.resolution.registry_store import StoredRegistry
    from brain.session import make_app_engine, make_session_factory
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    one = SourceRef("hubspot", "hubspot_company", "c1")
    two = SourceRef("hubspot", "hubspot_company", "c2")
    keys = [(r.source, r.entity, r.source_id) for r in (one, two)]
    nobody = ("hubspot", "hubspot_company", "c3")
    with at_head("brain_ambiguity_store") as url:
        for ref in (one, two):
            sql(
                url,
                "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
                " VALUES (%s, %s, %s, %s::jsonb, %s)",
                ref.source,
                ref.entity,
                ref.source_id,
                json.dumps({"name": f"Northwind {ref.source_id}"}),
                NOW,
            )

        async def go() -> tuple[Any, ...]:
            engine = make_app_engine(normalise_database_url(url))
            try:
                sessions = make_session_factory(engine)
                await StoredRegistry(sessions).register([one, two], pepper="ab" * 32, now=NOW)
                [(a,), (b,)] = sql(url, "SELECT entity_id FROM er.link ORDER BY source_id")
                sql(
                    url,
                    "INSERT INTO er.review_item (item_id, entity_type, left_source, left_entity,"
                    " left_source_id, right_source, right_entity, right_source_id,"
                    " left_entity_id, right_entity_id, origin, stage, reason, evidence, state)"
                    " VALUES ('rev_1', %s, 'hubspot', 'hubspot_company', 'c1', 'hubspot',"
                    " 'hubspot_company', 'c2', %s, %s, 'cascade', 4, 'r', '[]'::jsonb, 'open')",
                    EntityType.COMPANY.value,
                    a,
                    b,
                )
                store = StoredAmbiguity(sessions)
                before = await store.current_entities([*keys, nobody])
                review = await store.open_review([a, b])
                elsewhere = await store.open_review([a, "ent_unrelated"])
                none = MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
                await merge_entities(
                    sessions,
                    survivor_id=a,
                    merged_id=b,
                    authority=ReviewedMerge(
                        reviewer_id="u_reviewer",
                        review_ref="rev_1",
                        money=MoneyCheck(left=none, right=none),
                    ),
                    at=NOW,
                    trace_id="t",
                    reason="the same",
                )
                after = await store.current_entities(keys)
                sql(
                    url,
                    "UPDATE er.review_item SET state = 'rejected', decided_by = 'u_reviewer',"
                    " decided_at = %s WHERE item_id = 'rev_1'",
                    NOW,
                )
                decided = await store.open_review([a, b])
                return a, b, before, review, elsewhere, after, decided
            finally:
                await engine.dispose()

        a, b, before, review, elsewhere, after, decided = asyncio.run(go())

    assert before == {keys[0]: a, keys[1]: b}
    assert review == "rev_1" and elsewhere is None
    assert after == {keys[0]: a, keys[1]: a}
    assert decided is None
