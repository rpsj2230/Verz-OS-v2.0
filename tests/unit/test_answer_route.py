"""The answer lane over HTTP, and the two things a route can get wrong that the lane cannot.

`tests/unit/test_answer_lane.py` holds the lane to what it may say. This file is about the
transport around it: whether the question can end up in a URL, whether an answer computed at
one caller's reach can be stored by anything in front of this process, and whether the frames
survive being written as a response body.

The harness is `tests/unit/test_api_routes.py`'s: the real application from `create_app`, the
real token path, the real registry, and a row source that hands back more than the query asked
for so that anything missing from an answer was removed by the projection or the redactor
rather than never fetched.

Nothing here mocks the lane. A route test that stubbed it would prove the route calls
something, which is the thing that was already true of every module it now calls.

Task ids: none
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Iterator, Sequence
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from brain.api import API_PREFIX
from brain.api_routes import (
    EVENT_STREAM,
    field_policies,
    row_readers,
)
from brain.app import Settings, create_app
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.fast_lane import FastPathRule
from brain.gate.rule_store import load_rules, rule_ids
from brain.ops.trace_sink import CountingTraceSink
from brain.tools.registry import ToolRegistry
from brain.tools.startup import build_registry, classification_for
from tests.unit.test_api_routes import (
    CANARY_COST,
    CANARY_MARGIN,
    SEEDED_ROWS,
    SOURCE,
    UnfilteredRows,
    token_for,
    wiring,
)
from tests.unit.test_streaming import decode

HOURS = FastPathRule(
    rule_id="price_list_sell_price",
    template="what is the price of {sku}",
    slot="sku",
    source=SOURCE,
    entity="price_list",
    match_field="sku",
    answer_field="sell_price",
)


class OneRow(UnfilteredRows):
    """`UnfilteredRows` narrowed to a single record, because two is a fall-through.

    `fast_lane.respond` returns None when two records answer to one name, which is correct
    and makes the parent class unusable for the positive case here: it hands back every
    seeded row whatever the statement asked for, so a rule matching one sku sees two records
    and the lane declines.

    Still unfiltered in the way that matters. The row it returns carries every column
    including the ones the caller may not read, so anything absent from an answer was removed
    by the projection or the redactor rather than never fetched.
    """

    async def rows(self, query: Any) -> Sequence[Any]:
        await super().rows(query)
        return SEEDED_ROWS[:1]


@pytest.fixture
def rows() -> UnfilteredRows:
    return OneRow()


@pytest.fixture
def client(rows: UnfilteredRows) -> Iterator[TestClient]:
    """The real application with the answer lane's own two seams filled in.

    The rules are set on the state the way `lifespan` sets them, rather than loaded from a
    database that does not exist in a unit test. Everything else the route touches is what
    `create_app` produced, including the sink.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=rows)
        app.state.fast_path_rules = (HOURS,)
        yield c


def question(c: TestClient, text: str, pid: str = "u_wide") -> Response:
    answered: Response = c.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for(pid)}"},
        json={"question": text},
    )
    return answered


def events(answered: Response) -> list[tuple[str, str]]:
    return [(one.event, one.data) for one in decode(answered.text)]


def texts(answered: Response) -> list[str]:
    return [data for name, data in events(answered) if name == "text"]


# --- the transport ---------------------------------------------------------------------------


def test_a_question_comes_back_as_an_event_stream(client: TestClient) -> None:
    """**The route this whole chain existed without.** Four modules were correct, tested and
    called by nothing; this is the request that reaches all four.

    Asserted on the decoded stream rather than on the status alone, because a 200 carrying a
    JSON body would pass a status check and be read by no event-stream client.

    Delete this and the media type can drift to application/json, which every test that reads
    the body as text still passes."""
    answered = question(client, "what is the price of WEB-1001")

    assert answered.status_code == 200
    assert answered.headers["content-type"].startswith(EVENT_STREAM)

    seen = [name for name, _ in events(answered)]
    assert seen[0] == "step"
    assert seen[-1] == "done"
    assert "text" in seen


def test_an_answer_is_uncacheable_by_anything_between_here_and_the_reader(
    client: TestClient,
) -> None:
    """A permission requirement, not a performance note. Every answer is computed at one
    caller's entitlements, so a shared cache in front of this route would key on the URL and
    the body and serve one person's answer to the next person who asked the same question.

    `no-store` rather than `no-cache`, because `no-cache` permits storing and requires
    revalidation, and a stored answer is one a misconfigured proxy can serve.

    Delete this and a CDN in front of the application defeats the entire permission model with
    a default setting."""
    answered = question(client, "what is the price of WEB-1001")

    assert answered.headers["cache-control"] == "no-store"
    assert answered.headers["x-accel-buffering"] == "no"


def test_the_question_cannot_be_put_in_a_url(client: TestClient) -> None:
    """A URL is written to the proxy access log, kept in browser history, and sent as a
    referer. A question here names the client, the invoice or the person somebody is asking
    about, before any entitlement has been applied to it.

    So the route declares POST and nothing else, and a GET carrying the question as a query
    parameter is refused by the router rather than answered.

    Delete this and somebody adds a GET for the convenience of `EventSource`, which is a real
    convenience and puts every question into three logs nobody governs."""
    got = client.get(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for('u_wide')}"},
        params={"question": "what is the price of WEB-1001"},
    )

    assert got.status_code == 405


def test_an_unauthenticated_question_is_refused(client: TestClient) -> None:
    """The route is under the versioned prefix and takes the same dependency every other route
    there takes. `test_api_routes` asserts that over the whole mounted set; this asserts it for
    the one route that answers a question rather than serving a row.

    Delete this and the route can lose its dependency in a refactor, and the sweep that would
    catch it is one somebody could also change."""
    refused = client.post(
        f"{API_PREFIX}/answer", json={"question": "what is the price of WEB-1001"}
    )

    assert refused.status_code == 401


def test_a_question_that_is_empty_or_longer_than_the_cache_can_key_is_refused(
    client: TestClient,
) -> None:
    """The bound is `caches.MAX_QUESTION_CHARS` rather than a number chosen at the route, so
    there is no length that is answerable and uncacheable. An empty question is refused
    because it matches every rule template's prefix and none of its holes, which is a
    fall-through dressed as a request.

    Anchored to the imported constant rather than to a literal, and the constant belongs to
    another module, so this is not a value compared against itself.

    Delete this and a question one character past the cache bound is answered and can never be
    cached, which presents as a lane that is fast for everybody except one caller."""
    assert question(client, "").status_code == 422
    assert question(client, "a" * (MAX_QUESTION_CHARS + 1)).status_code == 422
    assert question(client, "a" * MAX_QUESTION_CHARS).status_code == 200


def test_the_body_refuses_a_field_nobody_declared(client: TestClient) -> None:
    """`extra="forbid"`, so a client sending `{"question": ..., "entitlement": ...}` is
    refused rather than quietly answered at the reach the token carries. An ignored field is
    the shape a caller uses to find out what the server reads.

    Delete this and an unknown field is dropped in silence, which is the same failure the
    records route's declared filter parameter exists to avoid one layer up."""
    got = client.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {token_for('u_wide')}"},
        json={"question": "what is the price of WEB-1001", "reach": "everything"},
    )

    assert got.status_code == 422


# --- what the route may say --------------------------------------------------------------


def test_every_kind_of_nothing_reaches_the_asker_as_one_sentence(client: TestClient) -> None:
    """Over HTTP, because the property has to hold at the surface a person touches and not
    only inside the lane.

    Both questions are asked by the same caller, deliberately. The scope statement names the
    sources this person may be told about, so it is a fact about their own account and varies
    between people by design; comparing two callers would compare two things that are supposed
    to differ. Within one caller, a question no rule matches and a question about an entity
    they reach no column of are the same bytes.

    The second is the sharper half: the record exists, the rule matched, and the projection
    knew before it ran that nothing could come back.

    Delete this and the lane keeps the property while the route reintroduces the difference in
    a status code."""
    unmatched = question(client, "what is the weather today", pid="u_none")
    unreachable = question(client, "what is the price of WEB-1001", pid="u_none")

    assert unmatched.status_code == unreachable.status_code == 200
    assert unmatched.text == unreachable.text
    assert NOT_FOUND_TEXT in texts(unmatched)[0]


def test_a_caller_who_reaches_nothing_is_told_the_same_thing_as_everybody_else(
    client: TestClient,
) -> None:
    """A caller with no reachable column gets a statement the projection already knows is
    empty, so no rows come back and the lane abstains. The sentence is the one everybody gets
    for a record that is not there.

    The scope statement differs, and that is correct and deliberate: it names the sources this
    caller may be told about, which is a fact about their own account rather than about the
    data, and `SearchScope` argues it at length.

    Delete this and a caller who reaches nothing gets a 403, which tells them the entity
    exists."""
    nothing = question(client, "what is the price of WEB-1001", pid="u_none")

    assert nothing.status_code == 200
    assert NOT_FOUND_TEXT in texts(nothing)[0]


def test_a_caller_who_reaches_the_column_is_given_the_value(client: TestClient) -> None:
    """**The positive case, and without it every assertion above is satisfied by a route that
    declines everything.**

    Delete this and the route can refuse unconditionally with the file green."""
    answered = question(client, "what is the price of WEB-1001")

    assert "1200" in texts(answered)[0]
    assert any(name == "citation" for name, _ in events(answered))


#: Phrasings that are a count of hidden things. Matched as words rather than as substrings,
#: because the first version of this check searched for "of 2" and fired on the "as of 2026"
#: in a citation's timestamp, which is the trap CLAUDE.md describes about asserting on text
#: that also appears nearby.
A_COUNT_OF_HIDDEN_THINGS = re.compile(
    r"\b(?:showing|found|and)\s+\d+\s+(?:of|more|others?|hidden|withheld)\b"
    r"|\b\d+\s+(?:hidden|withheld|locked|redacted|restricted)\b",
    re.IGNORECASE,
)


def test_no_frame_names_a_field_this_caller_may_not_read(client: TestClient) -> None:
    """The structural half. A citation is derived from what survived redaction, so a citation
    naming a column the caller cannot read would mean the derivation is reading the wrong
    payload. The seeded rows carry a distinctive value in each restricted column, so its
    appearance anywhere in the body is unambiguous.

    Asserted over the whole response rather than over the text frames, because a value that
    leaked into a step label or a citation would pass a check that only reads the prose.

    Delete this and the citations can be built from the fetched record instead of the payload,
    which is one line and reads as a simplification."""
    answered = question(client, "what is the price of WEB-1001", pid="u_prefix")

    assert CANARY_COST not in answered.text
    assert CANARY_MARGIN not in answered.text
    assert "cost" not in answered.text
    assert "margin" not in answered.text


def test_no_frame_carries_a_count_of_what_was_not_shown(client: TestClient) -> None:
    """ "Showing 3 of 47" tells the reader there are 44 things they may not see, which is 44
    facts they did not have. The lane's shapes have no field that could hold such a number and
    `test_answer_lane` asserts that; this asserts the rendered form, because a renderer can
    write a sentence a dataclass could not hold.

    The pattern matches words rather than substrings for the reason beside it.

    Delete this and a helpful "and 2 more fields" is added to a citation frame."""
    answered = question(client, "what is the price of WEB-1001", pid="u_prefix")

    for name, data in events(answered):
        assert not A_COUNT_OF_HIDDEN_THINGS.search(data), (name, data)


# --- the three helpers the route assembles the lane from -----------------------------------


def test_the_route_offers_the_lane_every_row_tool_and_filters_none(
    rows: UnfilteredRows,
) -> None:
    """Filtering here would be a second permission decision, taken in a route, about a
    question `compile_projection` already answers inside the query. Two answers to one
    question means the day they disagree the wrong one wins, and it will be whichever was
    easier to change.

    Delete this and a helpful `if reaches` appears here, and a rule stops matching for a
    reason no test explains."""
    registry = build_registry(source=SOURCE, records=rows)

    offered = row_readers(registry)

    entities = {entity for _, entity in offered}
    assert entities == {one.entity for one in registry.definitions() if one.entity and one.source}
    assert entities

    # **The signature is the enforcement**, in the same way `streaming.step_label` has nowhere
    # to put a tool. A behavioural test cannot catch this one: filtering here produces the
    # same sentence either way, because a rule excluded matches nothing and a rule left in
    # fetches nothing. What filtering costs is architectural, so what is asserted is
    # architectural: this function cannot be handed a caller, so it cannot decide anything
    # about one.
    taken = list(inspect.signature(row_readers).parameters)
    assert taken == ["registry"], taken


def test_the_scope_statement_names_only_what_this_caller_reaches(client: TestClient) -> None:
    """`SearchScope` is derived from the asker's reach and never from what ran. The route is
    where the reach is known, so this is where the derivation happens, and it uses
    `row_scope_for` rather than a check written at the route: the same function `read_rows`
    consults, so "does this caller reach rows of this kind" has one answer.

    Both directions, because a function naming every source and one naming none both pass a
    single-sided check. Exercised through the route rather than by rebuilding an `Asking` by
    hand, so what is asserted is the reach a request actually arrives at.

    Delete this and the statement is built from the registry, and it tells a caller who
    reaches nothing which sources this installation runs."""
    wide = texts(question(client, "what is the price of WEB-1001"))[0]
    none = texts(question(client, "what is the price of WEB-1001", pid="u_none"))[0]

    assert f"This covers {SOURCE}." in wide
    assert SOURCE not in none


def test_a_policy_is_chosen_before_the_question_is_read(rows: UnfilteredRows) -> None:
    """A mapping rather than a callback, so a policy cannot be chosen to fit the rows that
    came back. The lane takes a mapping for the same reason and this is where it is built.

    Delete this and `policies` becomes a lambda the lane calls with the entity it found,
    which is one refactor from being called with the rows as well."""
    registry = build_registry(source=SOURCE, records=rows)

    policies = field_policies(registry)

    assert "price_list" in policies
    assert set(policies) == {
        one.entity
        for one in registry.definitions()
        if one.entity and classification_for(one.entity) is not None
    }


def test_an_entity_nothing_classifies_gets_no_policy_rather_than_a_default(
    rows: UnfilteredRows,
) -> None:
    """**Written because a mutation survived.** Every entity this application registers is
    classified, so a two-line `else` handing an unclassified one a bare `FieldPolicy` changes
    nothing anybody could observe here and ships an unclassified column the day somebody adds
    an entity and forgets its classification.

    A stand-in registry rather than the real one, because the property is about an entity that
    does not exist in it: `field_policies` reads `definitions()` and nothing else, which is
    what makes a stand-in honest here rather than a way of avoiding the real object.

    The lane already answers an unclassified entity the way it answers every other nothing,
    and `test_answer_lane` asserts that. This is the other half: the policy must be missing
    for the lane to notice.

    Delete this and a default policy arrives as a robustness improvement."""

    class Unclassified:
        def definitions(self) -> tuple[Any, ...]:
            built = build_registry(source=SOURCE, records=rows).definitions()
            return (*built, _nameless())

    policies = field_policies(cast(ToolRegistry, Unclassified()))

    assert "not_a_real_entity" not in policies
    assert "price_list" in policies


# --- the sink and the rule loader ----------------------------------------------------------


def test_the_trace_sink_records_that_a_trace_happened_and_keeps_no_payload() -> None:
    """A post-redaction payload written to the application log is readable by whoever can read
    logs, which is a different set of people from whoever could read the records. M3.9.2 gives
    a trace one destination precisely so the destination's permissions are the answer's.

    What is kept is counts, which `RedactionTrace` says belong in the object an auditor reads
    and `ChannelPayload` has no field to hold.

    Asserted structurally: the sink has no attribute that could accumulate a payload, which is
    the shape a helpful buffer would take.

    Delete this and the sink starts keeping the last few payloads for debugging."""
    sink = CountingTraceSink()
    payload = ChannelPayload(records=({"entity": "price_list", "id": "p_web_1"},))
    trace = RedactionTrace(policy_epoch="e1", ent_hash="0" * 32)

    sink.emit("ref", payload, trace)

    assert not any(
        isinstance(getattr(sink, name, None), list | dict | tuple)
        for name in dir(sink)
        if not name.startswith("__")
    )
    for forbidden in ("records", "payloads", "seen", "history", "buffer"):
        assert not hasattr(sink, forbidden), forbidden


def test_a_retired_rule_is_not_loaded_and_the_order_does_not_move() -> None:
    """The rule table has no DELETE and retires with `deleted_at`, because "which rule
    answered that in March" is asked after a wrong answer. A loader ignoring the column would
    answer with a rule somebody retired.

    Ordered by id so two processes started from one database hold the same tuple, which is
    what makes two identical incidents read as one.

    Driven against a stand-in session: the assertion is about the statement the loader builds,
    which needs no server to establish.

    Delete this and the WHERE clause goes, and a retired rule answers questions until somebody
    notices the answer is old."""
    seen: list[Any] = []

    class Result:
        def scalars(self) -> Result:
            return self

        def all(self) -> Sequence[Any]:
            return ()

    class Session:
        async def execute(self, statement: Any) -> Result:
            seen.append(statement)
            return Result()

        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    def sessions() -> Session:
        return Session()

    loaded = asyncio.run(load_rules(sessions))  # type: ignore[arg-type]

    assert loaded == ()
    rendered = str(seen[0])
    assert "deleted_at IS NULL" in rendered
    assert "ORDER BY" in rendered and "rule_id" in rendered


def test_a_log_line_names_the_rules_by_id_and_never_by_template() -> None:
    """A template is the question shape somebody wrote, so a log line carrying it puts the
    shape of what this installation can be asked into a stream with different permissions from
    the rule table. The id names the row for anybody entitled to open it.

    Delete this and the startup line becomes more useful and more disclosing at once."""
    named = rule_ids((HOURS,))

    assert named == (HOURS.rule_id,)
    assert HOURS.template not in " ".join(named)


def test_the_lane_is_reachable_from_the_application_that_is_actually_built(
    client: TestClient,
) -> None:
    """**The assertion that replaces `test_nothing_yet_streams_an_answer_from_a_route`.**

    That test existed so the gap could not be forgotten quietly, and it named the day somebody
    closed it. This is that day, and this is the test that says so: the route is mounted on
    the application `create_app` produces, not on one assembled by a fixture.

    Delete this and the route can be dropped from the router with only a 404 to show for it,
    in a suite where four modules pass their own tests either way."""
    document = client.get("/openapi.json").json()

    assert f"{API_PREFIX}/answer" in document["paths"]
    assert "post" in document["paths"][f"{API_PREFIX}/answer"]


def test_a_process_with_no_rules_answers_rather_than_failing(
    rows: UnfilteredRows,
) -> None:
    """A rule table that cannot be read is an empty rule set and not a dead process. The lane
    abstains for every question, which is the same answer it gives when no rule matches, and
    refusing to start would take `/records` and `/me` down over configuration only one route
    reads.

    Built without setting `fast_path_rules` at all, so the route's own default is what is
    under test rather than a fixture's.

    Delete this and an installation with no rules yet answers 500 to every question, which
    reads as an outage."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=rows)
        answered = question(c, "what is the price of WEB-1001")

    assert answered.status_code == 200
    assert NOT_FOUND_TEXT in texts(answered)[0]


def test_the_question_is_never_written_to_the_log_line_that_records_the_answer(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """A log is an audit surface with its own permissions. The abstention reason belongs there
    because it is the audit half of the outcome; the question is the caller's and the answer
    is theirs, and a log line carrying either puts them in front of whoever can read logs.

    **`capsys` and not `caplog`, and the difference is the whole test.** This application logs
    through structlog's own writer to stdout rather than through the standard library, so
    `caplog.text` is empty for every line this route emits and the first version of this test
    passed with the question added to the log call. A mutation caught it.

    The positive half is asserted too: the line does exist and does name the caller and the
    outcome, so a check that the question is absent cannot be satisfied by no logging at all.

    Delete this and the question is added to make an incident easier to reproduce, and every
    question anybody asks is in the log stream for its whole retention period."""
    marker = "WEB-1001"
    capsys.readouterr()

    question(client, f"what is the price of {marker}")

    written = capsys.readouterr().out
    assert "answered" in written, written
    assert "principal=u_wide" in written, written
    assert marker not in written, written


def _nameless() -> Any:
    """A tool definition for an entity nothing classifies, for the test above.

    Built by copying a real definition and renaming its entity, so it carries every field a
    definition has rather than the two `field_policies` happens to read today.
    """
    real = build_registry(source=SOURCE, records=UnfilteredRows()).definitions()[0]
    return real.model_copy(update={"entity": "not_a_real_entity"})
