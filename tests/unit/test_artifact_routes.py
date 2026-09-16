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
def client() -> Iterator[TestClient]:
    """An install with nothing attached that records an artifact, which is every install."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        yield c


def attached(*artifacts: Artifact, agents: Sequence[AgentRow] = ()) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    AGENTS[:] = list(agents)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.artifact_source = lambda: artifacts
        yield c


def get(c: TestClient, pid: str) -> Response:
    response: Response = c.get(ARTIFACTS, headers={"authorization": f"Bearer {token_for(pid)}"})
    return response


# ------------------------------------------------------------------------ the answers
def test_an_install_recording_nothing_is_told_so_rather_than_shown_an_empty_list(
    client: TestClient,
) -> None:
    """**The rule the screen turns on.** Nothing records an artifact, so there is no list and a
    sentence, and the retention rule still travels.

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
