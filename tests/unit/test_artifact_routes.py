"""The Artifacts screen over HTTP.

Driven through the real application, with the token machinery borrowed from
`tests/unit/test_api_routes.py` and the agent rows from `tests/unit/test_agent_routes.py`, for the
reason `tests/unit/test_estate_routes.py` gives about borrowing them. What is under test is a read
assembled from decisions `brain.console.agent_output` and `brain.console.govern_estate` own, so
the records here are records `brain.console.agent_output.record` builds and the readers are
entitlement sets.

**Every refusal has a sibling proving the permitted case is answered.**

The present is the wall clock, because the route reads it through `brain.api_routes.asking` and an
artifact's retention is measured from it. So an artifact here is produced an hour or ten years
before the test runs, never on a date.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.artifact_routes import (
    NOTHING_HERE_RECORDS_WHAT_AN_AGENT_PRODUCED,
    ArtifactsView,
    artifact_view,
)
from brain.console.agent_output import (
    AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
    Artifact,
    ArtifactInput,
    ArtifactKind,
    record,
)
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.scope import Clause, Op, Scope
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.ops.retention import DataClass, horizon_for
from brain.tables.agent import AgentRow
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

ARTIFACTS = f"{API_PREFIX}/govern/artifacts"
REPO = Path(__file__).resolve().parents[2]

#: The Artifacts screen's capability, spelled out rather than read off the registry, so a
#: repointed screen key is a failure here rather than a constant compared with itself.
ARTIFACT_READ = Capability(value="read:artifact")
EXISTENCE = plane_capability(Plane.EXISTENCE)


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


#: `u_admin` holds the screen company-wide. `u_narrow` holds it only over the quoting agent's
#: artifacts. `u_prefix` holds the capability with no console plane, which a bare capability check
#: would let in. `u_wide` holds the plane and no capability. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": _everywhere(ARTIFACT_READ, EXISTENCE),
    "u_narrow": (
        Grant(
            capability=ARTIFACT_READ,
            scope=Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value="quoting"),)),
        ),
        *_everywhere(EXISTENCE),
    ),
    "u_prefix": _everywhere(ARTIFACT_READ),
    "u_wide": _everywhere(EXISTENCE),
    "u_none": (),
    "u_elsewhere": _everywhere(EXISTENCE),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


def ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def produced(
    artifact_id: str,
    *,
    agent_id: str = "quoting",
    caller_id: str = "u_caller",
    at: datetime | None = None,
    data_class: DataClass = DataClass.PAYLOAD,
) -> Artifact:
    """One artifact, recorded by the one function that records them."""
    return record(
        artifact_id=artifact_id,
        agent_id=agent_id,
        kind=ArtifactKind.REPORT,
        run_id=f"run_{artifact_id}",
        agent_version="3",
        caller_id=caller_id,
        reach=EntitlementSet(principal_id=caller_id, grants=()),
        at=at or ago(hours=1),
        inputs=(
            ArtifactInput(
                label="source", data_class=data_class, classification=Classification.INTERNAL
            ),
        ),
    )


#: The agent rows the stub database holds, replaced by `attached` for each application.
AGENTS: list[AgentRow] = []


class StubResult:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class StubSession(AsyncSession):
    """Answers the one load the route makes, the agent roster."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        assert statement.column_descriptions[0]["entity"] is AgentRow
        return StubResult(AGENTS)

    async def close(self) -> None:
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A process with no database, so nothing attached that reads the artifact records.

    Pinned rather than assumed, because CI's environment carries a database and the lifespan would
    otherwise attach a store; see `tests.fixtures.no_database`."""
    as_if_ci_had_a_database(monkeypatch)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        yield c


def attached(*artifacts: Artifact, agents: Sequence[AgentRow] = ()) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    AGENTS[:] = list(agents)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)

        async def source() -> tuple[Artifact, ...]:
            return artifacts

        app.state.artifact_source = source
        yield c


def get(c: TestClient, pid: str, query: str = "") -> Response:
    response: Response = c.get(
        ARTIFACTS + query, headers={"authorization": f"Bearer {token_for(pid)}"}
    )
    return response


def many(count: int, *, agent: str = "quoting") -> list[Artifact]:
    """`count` artifacts of one agent, the first the newest and each an hour older than the last.

    The identifiers sort the way the artifacts are ordered, so a test can read a page's position
    off its names."""
    return [
        produced(f"art_{agent}_{index:03d}", agent_id=agent, at=ago(hours=index + 1))
        for index in range(count)
    ]


# ------------------------------------------------------------------------ the answers
def test_an_install_recording_nothing_is_told_so_rather_than_shown_an_empty_list(
    client: TestClient,
) -> None:
    """**The rule the screen turns on.** Nothing on this process reads the records, so there is no
    list and a sentence, and the retention rule still travels.

    Delete this and the route may answer an empty list, which renders as an estate that produced
    nothing, a statement about the company nobody established."""
    response = get(client, "u_admin")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["artifacts"] is None
    assert body["unread"] == NOTHING_HERE_RECORDS_WHAT_AN_AGENT_PRODUCED
    assert body["kept_rule"] == AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM


def test_an_attached_source_lists_what_the_reader_may_see_with_provenance_and_retention() -> None:
    """The sibling of the test above: the sentence is a branch and not the only answer. A visible
    agent's artifact is listed with the run, the version, the person it was for, and the date it
    stops being kept, which is the payload class's window from when it was produced.

    Delete this and the route could be hard-wired to the sentence, and attaching a store would
    change nothing."""
    one = produced("art_1", at=ago(hours=2))
    for c in attached(one, agents=[agent_row("quoting")]):
        response = get(c, "u_admin")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unread"] == ""
    [row] = body["artifacts"]
    assert row["artifact_id"] == "art_1"
    assert row["produced_for"] == "u_caller"
    assert row["run_id"] == "run_art_1"
    assert row["agent_version"] == "3"
    assert row["kept_as"] == DataClass.PAYLOAD.value
    days = horizon_for(DataClass.PAYLOAD).days
    assert days is not None
    assert datetime.fromisoformat(row["kept_until"]) == one.at + timedelta(days=days)
    assert str(days) in row["kept_because"]


def test_an_artifact_past_its_window_is_absent_rather_than_listed_as_expired() -> None:
    """`visible_artifacts` drops an aged-out artifact before it filters, and the route must not
    add it back. Delete this and a row reading expired says something used to be here."""
    old = produced("art_old", at=ago(days=3650))
    fresh = produced("art_new")
    for c in attached(old, fresh, agents=[agent_row("quoting")]):
        body = get(c, "u_admin").json()

    assert [one["artifact_id"] for one in body["artifacts"]] == ["art_new"]


def test_a_class_with_no_clock_says_why_there_is_no_date() -> None:
    """A business record is kept while its record exists, so the row has no date and says so.

    Delete this and the row may carry an empty date beside nothing, which a renderer draws as a
    dash and a reader takes as not applicable."""
    view = artifact_view(produced("art_record", data_class=DataClass.BUSINESS_RECORD))

    assert view.kept_until == ""
    assert view.kept_because == "kept while the record it describes exists"


def test_a_scoped_reader_sees_only_the_artifacts_their_grant_admits_and_no_count() -> None:
    """A grant scoped to one agent's artifacts admits that agent's rows and no other, and the
    response has nowhere to say how many were left out.

    Delete this and the route could list every artifact of every visible agent to anybody who
    may open the screen, which is somebody else's run's output shown to a reader who holds
    nothing over it."""
    rows = [
        produced("art_quote", agent_id="quoting"),
        produced("art_hr", agent_id="hiring"),
    ]
    agents = [agent_row("quoting"), agent_row("hiring")]
    for c in attached(*rows, agents=agents):
        narrow = get(c, "u_narrow").json()
        wide = get(c, "u_admin").json()

    assert [one["artifact_id"] for one in narrow["artifacts"]] == ["art_quote"]
    assert sorted(one["artifact_id"] for one in wide["artifacts"]) == ["art_hr", "art_quote"]
    assert set(narrow) == set(ArtifactsView.model_fields)
    assert {"total", "count", "hidden", "withheld"}.isdisjoint(narrow)


def test_an_artifact_of_an_agent_outside_the_readers_audience_is_absent() -> None:
    """`artifact_estate` is handed the agents the reader's audience admits. An artifact of a
    personal agent belonging to somebody else is absent even for a company-wide reader.

    Delete this and the route could hand every stored agent to the estate, which lists what a
    colleague's private agent produced."""
    rows = [produced("art_private", agent_id="private")]
    agents = [agent_row("private", level=Visibility.PERSONAL, owner_id="u_someone")]
    for c in attached(*rows, agents=agents):
        body = get(c, "u_admin").json()

    assert body["artifacts"] == []


# ------------------------------------------------------------------------ the pages
def _ids(body: dict[str, Any]) -> list[str]:
    return [one["artifact_id"] for one in body["artifacts"]]


def test_a_page_is_bounded_and_the_cursor_walks_every_row_once() -> None:
    """The page is cut on the server (M32.5.2.1): a limit of three over seven artifacts answers
    three, three and one, newest first, each row exactly once, and the last page carries no cursor.

    Delete this and the screen could go back to answering the whole estate in one body, or a
    cursor could skip or repeat a row between two pages, which a reader sees as a missing
    artifact."""
    rows = many(7)
    agents = [agent_row("quoting")]
    seen: list[str] = []
    cursors: list[str | None] = []
    for c in attached(*rows, agents=agents):
        query = "?limit=3"
        while True:
            body = get(c, "u_admin", query).json()
            assert len(body["artifacts"]) <= 3
            seen.extend(_ids(body))
            cursors.append(body["next_cursor"])
            if body["next_cursor"] is None:
                break
            query = f"?limit=3&cursor={body['next_cursor']}"

    assert seen == [f"art_quoting_{index:03d}" for index in range(7)]
    assert [one is None for one in cursors] == [False, False, True]


def test_a_search_a_filter_and_an_order_are_the_servers_and_read_only_what_the_row_shows() -> None:
    """Search matches the artifact, the agent and the person it was for; a filter is an equality on
    a declared column; the order is by when it was produced and can be turned round. A search for a
    value the row does not carry as a searched column (the run) finds nothing.

    Delete this and the narrowing could drift back into the browser, where it narrows only what
    arrived, or a search could match a column the screen does not show."""
    rows = [*many(2, agent="quoting"), *many(2, agent="hiring")]
    agents = [agent_row("quoting"), agent_row("hiring")]
    for c in attached(*rows, agents=agents):
        by_search = _ids(get(c, "u_admin", "?q=hiring").json())
        by_filter = _ids(get(c, "u_admin", "?filter=agent_id:quoting").json())
        by_run = _ids(get(c, "u_admin", "?q=run_art_quoting_000").json())
        oldest_first = _ids(get(c, "u_admin", "?sort=produced_at&filter=agent_id:hiring").json())
        newest_first = _ids(get(c, "u_admin", "?filter=agent_id:hiring").json())

    assert by_search == ["art_hiring_000", "art_hiring_001"]
    assert by_filter == ["art_quoting_000", "art_quoting_001"]
    assert by_run == []
    assert newest_first == ["art_hiring_000", "art_hiring_001"]
    assert oldest_first == ["art_hiring_001", "art_hiring_000"]


def test_a_search_reads_the_agent_and_the_person_and_not_only_the_artifact() -> None:
    """The identifiers here share nothing with the agent or the person, so a search can only match
    through the column it names. `payroll` finds the artifact of that agent, `u_bob` the one made
    for that person, and neither finds the other.

    Delete this and a search that stopped reading the agent or the person would still pass every
    test whose artifact identifiers happen to contain the word searched for."""
    rows = [
        produced("art_a", agent_id="payroll", caller_id="u_ann"),
        produced("art_b", agent_id="rota", caller_id="u_bob", at=ago(hours=2)),
    ]
    agents = [agent_row("payroll"), agent_row("rota")]
    for c in attached(*rows, agents=agents):
        by_agent = _ids(get(c, "u_admin", "?q=payroll").json())
        by_person = _ids(get(c, "u_admin", "?q=u_bob").json())
        by_both = _ids(get(c, "u_admin", "?q=rota%20u_bob").json())
        by_neither = _ids(get(c, "u_admin", "?q=payroll%20u_bob").json())

    assert by_agent == ["art_a"]
    assert by_person == ["art_b"]
    assert by_both == ["art_b"]
    assert by_neither == []


def test_a_column_the_list_does_not_declare_and_a_page_too_large_are_refused() -> None:
    """The declaration is the API document: a filter or an order on a column the list does not
    offer, a page over the bound and a page of none are refused before the route runs, the same
    for every reader.

    Delete this and `?filter=run_id:...` could be accepted and ignored, which is a filter box with
    a word in it and every row still on the screen."""
    for c in attached(*many(2), agents=[agent_row("quoting")]):
        refused = [
            get(c, "u_admin", "?filter=run_id:run_art_quoting_000"),
            get(c, "u_admin", "?sort=run_id"),
            get(c, "u_admin", "?limit=201"),
            get(c, "u_admin", "?limit=0"),
        ]
        allowed = get(c, "u_admin", "?limit=200")

    assert [one.status_code for one in refused] == [422, 422, 422, 422]
    assert allowed.status_code == 200


def test_a_cursor_is_refused_for_another_reader_another_question_and_a_garbage_one() -> None:
    """A cursor is a position bound to the reader and the exact question that minted it, so one
    copied to another reader, carried across an order or made up is the same 422, and it is the
    same 422 on a process with no store, because the question is checked before a record is read.

    Delete this and a cursor could be replayed under a different reader's grants or a different
    order, or its refusal could depend on whether a store is attached."""
    rows = many(4)
    agents = [agent_row("quoting")]
    for c in attached(*rows, agents=agents):
        minted = get(c, "u_admin", "?limit=2").json()["next_cursor"]
        assert minted is not None
        replayed = get(c, "u_narrow", f"?limit=2&cursor={minted}")
        reordered = get(c, "u_admin", f"?limit=2&sort=kind&cursor={minted}")
        garbage = get(c, "u_admin", "?cursor=not-a-cursor")
        honest = get(c, "u_admin", f"?limit=2&cursor={minted}")

    assert [one.status_code for one in (replayed, reordered, garbage)] == [422, 422, 422]
    assert honest.status_code == 200
    # Everything but the trace id, which is minted per request.
    assert {k: v for k, v in replayed.json().items() if k != "trace_id"} == {
        k: v for k, v in garbage.json().items() if k != "trace_id"
    }


def test_a_garbage_cursor_is_the_same_refusal_with_no_store_attached(client: TestClient) -> None:
    """The sibling of the test above for a process that records nothing: the question is checked
    before the source is looked for, so the refusal does not say whether one is attached.

    Delete this and a malformed cursor could be answered with the sentence about the missing store
    on one install and a 422 on another."""
    assert get(client, "u_admin", "?cursor=not-a-cursor").status_code == 422
    assert get(client, "u_admin", "?limit=3").json()["artifacts"] is None


def test_a_cursor_says_more_only_when_a_row_the_reader_may_see_follows() -> None:
    """A reader scoped to one agent holds two artifacts and the estate holds seven more of another
    agent's. A page of two says there is no more, and a page of one says there is, then there is
    not: the cursor is computed over rows the reader may see and never over what was withheld.

    Delete this and the cursor could be present because withheld rows follow, which is a count of
    them arrived at by a boolean."""
    rows = [*many(2, agent="quoting"), *many(7, agent="hiring")]
    agents = [agent_row("quoting"), agent_row("hiring")]
    for c in attached(*rows, agents=agents):
        whole = get(c, "u_narrow", "?limit=2").json()
        first = get(c, "u_narrow", "?limit=1").json()
        second = get(c, "u_narrow", f"?limit=1&cursor={first['next_cursor']}").json()

    assert _ids(whole) == ["art_quoting_000", "art_quoting_001"]
    assert whole["next_cursor"] is None
    assert _ids(first) == ["art_quoting_000"]
    assert first["next_cursor"] is not None
    assert _ids(second) == ["art_quoting_001"]
    assert second["next_cursor"] is None


def test_a_search_for_what_the_reader_may_not_see_answers_as_a_search_for_nothing() -> None:
    """A scoped reader searching another agent's name gets the answer a search for nothing gets,
    body for body. Delete this and the search could leak that the other agent has artifacts, by
    answering differently from a search that matches nothing anywhere."""
    rows = [*many(2, agent="quoting"), *many(3, agent="hiring")]
    agents = [agent_row("quoting"), agent_row("hiring")]
    for c in attached(*rows, agents=agents):
        withheld = get(c, "u_narrow", "?q=hiring").json()
        nothing = get(c, "u_narrow", "?q=zzzzzz").json()

    assert withheld == nothing
    assert withheld["artifacts"] == []


# ------------------------------------------------------------------------ the refusals
def test_a_reader_without_the_screen_is_refused_and_cannot_tell_whether_a_store_is_attached(
    client: TestClient,
) -> None:
    """The screen's question comes before the source is looked for, so a caller who may not open
    it is refused identically with and without a store. A reader holding the capability with no
    console plane is refused too, which is `permitted` rather than a bare capability check.

    Delete this and moving the check below the source makes the refusal depend on the wiring."""
    bare = [get(client, pid) for pid in ("u_none", "u_prefix", "u_wide")]
    for c in attached(produced("art_1"), agents=[agent_row("quoting")]):
        wired = [get(c, pid) for pid in ("u_none", "u_prefix", "u_wide")]

    for one, other in zip(bare, wired, strict=True):
        assert one.status_code == other.status_code == 404
        assert one.json()["message"] == other.json()["message"]
    assert get(client, "u_admin").status_code == 200


def test_the_route_computes_no_reach_of_its_own() -> None:
    """Delete this and an intersection written here would be a second implementation of the
    platform's central rule, on a screen that lists what runs produced."""
    source = (REPO / "src" / "brain" / "artifact_routes.py").read_text(encoding="utf-8")
    assert intersections_in(source) == ()
