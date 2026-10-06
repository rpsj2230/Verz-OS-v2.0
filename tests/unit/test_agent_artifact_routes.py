"""An agent's artifacts over HTTP: listed, filtered, fetched, retired and found for a client.

Driven through the real application with signed-in people. The refusal a reader without the
Artifacts tab gets is asserted over a stub pool; everything else runs on PostgreSQL as the
application role, with the product's report producer writing through the product's store and the
object store behind the real S3 client (`tests.fixtures.fake_s3.FakeS3`), so the policies, the
change table and the digest check are the ones an install has. The whole path on an install is an
acceptance check in `brain.ops.acceptance_workspace`.

Task ids: M39.5.1.5, M39.5.2.1, M39.5.2.2, M39.5.2.4, M39.8.5
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.agent_artifact_routes import (
    RETIRING_AN_ARTIFACT_NEEDS_THE_STEWARD_OR_ITS_PERSON,
    AgentArtifactsView,
    router,
)
from brain.agent_routes import one_agent, record_of
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.agent_output import ArtifactError, ArtifactInput, ArtifactKind
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, policy_from_rows
from brain.core.scope import Clause, Op, Scope
from brain.ops.artifact_report import Records, produce_report
from brain.ops.artifact_store import ARTIFACT_BUCKET, StoredArtifacts
from brain.ops.object_store import S3Backend, StoreCredential
from brain.ops.retention import DataClass
from brain.ops.storage import Backend, config_for
from brain.session import make_session_factory
from brain.tables.agent import AgentRow
from tests.fixtures.console_http import Stub, console_client, gate_wiring, get, headers
from tests.fixtures.fake_s3 import FakeS3
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_automation_owner_store import app_engine

AGENT = "web_desk"
KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test-secret")
ENDPOINT = "http://objects.example.test:8333"

TAB_READ: tuple[Capability, ...] = (
    tab(Tab.ARTIFACTS).read.requires,
    *(plane_capability(one) for one in Plane),
)


def everywhere(*capabilities: Capability | str) -> tuple[Grant, ...]:
    return tuple(
        Grant(
            capability=one if isinstance(one, Capability) else Capability(value=one),
            scope=Scope.unrestricted(),
        )
        for one in capabilities
    )


# ------------------------------------------------------------------------- the refusal
def answer(statement: Any) -> Result | None:
    if not isinstance(statement, Select):
        return None
    if statement.column_descriptions[0].get("entity") is AgentRow:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([agent_row(AGENT)] if wanted == AGENT else [])
    return None


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client({"u_admin": everywhere(*TAB_READ), "u_narrow": ()}, routers=(router,)) as (
        client,
        stub,
    ):
        stub.answerers.append(answer)
        # The lifespan attaches a store over whatever database the environment names; this
        # process is the one with no store, whatever the environment says.
        client.app.state.artifacts = None  # type: ignore[attr-defined]
        yield client, stub


def test_a_reader_without_the_artifacts_read_is_answered_as_an_agent_that_does_not_exist(
    served: tuple[TestClient, Stub],
) -> None:
    """The Artifacts address is never a way to learn whether an agent produced anything: without
    the tab's read the answer is the missing agent's, in the same words. Delete this and anybody
    who can open an agent can list what it produced for everybody."""
    client, _ = served
    refused = get(client, "u_narrow", f"{API_PREFIX}/agents/{AGENT}/artifacts")
    missing = get(client, "u_narrow", f"{API_PREFIX}/agents/no_such_agent/artifacts")
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]


def test_a_reader_of_the_tab_on_a_process_with_no_store_is_told_nothing_here_could_look(
    served: tuple[TestClient, Stub],
) -> None:
    """The sibling of the refusal: the reader is answered, with no list and a sentence rather than
    an empty table. Delete this and a process with no database reads as an agent that produced
    nothing."""
    client, _ = served
    body = AgentArtifactsView.model_validate(
        get(client, "u_admin", f"{API_PREFIX}/agents/{AGENT}/artifacts").json()
    )
    assert (body.artifacts, body.summary) == ([], None)
    assert body.unread.startswith("This process has no database attached")
    assert body.kinds == [one.value for one in ArtifactKind]


# ------------------------------------------------------------------------- the database
ENTITY = "price"
POLICY = policy_from_rows(
    [
        (ENTITY, "name", f"read:{ENTITY}", Classification.INTERNAL),
        (ENTITY, "sell_price", f"read:{ENTITY}", Classification.INTERNAL),
        (ENTITY, "cost", f"read:{ENTITY}.cost", Classification.RESTRICTED),
    ]
)
ROWS = (
    {"name": "design", "sell_price": "900", "cost": "400"},
    {"name": "build", "sell_price": "1200", "cost": "700"},
)
RECORDS = Records(
    entity=ENTITY,
    rows=ROWS,
    policy=POLICY,
    read_as=Capability(value=f"read:{ENTITY}"),
    source="price_list",
)
INPUTS = (
    ArtifactInput(
        label="price rows",
        data_class=DataClass.BUSINESS_RECORD,
        classification=Classification.RESTRICTED,
    ),
)


#: `u_admin` is the agent's steward and reads the tab, not the cost; `u_narrow` is the person
#: reports are produced for, holding the price list and its cost and not the tab; `u_prefix` reads
#: the tab and both price grants and is neither; `u_elsewhere` holds nothing and cannot see it.
def db_grants() -> dict[str, tuple[Grant, ...]]:
    return {
        "u_admin": everywhere(*TAB_READ, f"read:{ENTITY}"),
        "u_narrow": everywhere(f"read:{ENTITY}", f"read:{ENTITY}.cost"),
        "u_prefix": everywhere(*TAB_READ, f"read:{ENTITY}", f"read:{ENTITY}.cost"),
        "u_elsewhere": (),
    }


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_agent_artifacts_{uuid.uuid4().hex[:8]}") as url:
        sql(
            url,
            "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
            " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
            " created_by) VALUES (%s, 'Web desk', 'Answer briefly.', 'main', 'department',"
            " 'u_admin', 'web', '{\"clauses\": []}', '{read:price,read:price.cost}', '{}', '{}',"
            " 'none', 'u_admin')",
            AGENT,
        )
        yield url


def pressed[T](
    url: str,
    grants: Mapping[str, tuple[Grant, ...]],
    presses: Callable[[httpx.AsyncClient, StoredArtifacts, Any], Awaitable[T]],
) -> T:
    """The artifact routes over this database as the application role, the store behind a fake
    bucket, and the agent's record for a producer. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
            backend = S3Backend(
                config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT),
                KEY,
                transport=fake.transport(),
            )
            store = StoredArtifacts(sessions, backend, "brain")
            async with sessions() as session:
                row = (await session.execute(one_agent(AGENT))).scalar_one()
            record = record_of(row)
            assert record is not None
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(grants)
            app.state.db_sessions = sessions
            app.state.artifacts = store
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client, store, record)
        finally:
            await built.dispose()

    return run(go)


async def report_for(
    store: StoredArtifacts,
    record: Any,
    grants: Mapping[str, tuple[Grant, ...]],
    *,
    who: str = "u_narrow",
    at: datetime | None = None,
    client_id: str = "",
    supersedes: str = "",
) -> Any:
    return await produce_report(
        store,
        RECORDS,
        caller=EntitlementSet(principal_id=who, grants=grants[who]),
        agent=record,
        agent_version="1",
        run_id=f"run-{uuid.uuid4().hex[:8]}",
        inputs=INPUTS,
        at=at or datetime.now(UTC) - timedelta(minutes=5),
        client_id=client_id,
        supersedes=supersedes,
    )


PATH = f"{API_PREFIX}/agents/{AGENT}/artifacts"


def test_a_report_is_listed_filtered_and_fetched_only_while_its_requester_holds_what_it_drew_on(
    database: str,
) -> None:
    """**M39.5.2.1, M39.5.2.2 and M39.5.1.5 on PostgreSQL.** A report produced for the person is
    listed to the steward, with who it was for and when it goes, and the filters narrow it. The
    person fetches exactly the bytes that were kept; the steward, who may list it and does not
    hold the cost it holds, is refused the file in the words a missing one gets; and once the
    person loses the cost grant they are refused it too.

    Delete this and the list, the filters or the download can pass over hand-built records while
    the table, its policies and the bucket say otherwise."""
    grants = db_grants()

    async def act(client: httpx.AsyncClient, store: StoredArtifacts, record: Any) -> Any:
        made = await report_for(store, record, grants)
        listed = (await client.get(PATH, headers=headers("u_admin"))).json()
        decks = (await client.get(PATH, params={"kind": "deck"}, headers=headers("u_admin"))).json()
        theirs = (
            await client.get(PATH, params={"produced_for": "u_narrow"}, headers=headers("u_admin"))
        ).json()
        later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        future = (
            await client.get(PATH, params={"since": later}, headers=headers("u_admin"))
        ).json()
        file = f"{PATH}/{made.artifact_id}/download"
        fetched = await client.get(file, headers=headers("u_narrow"))
        steward = await client.get(file, headers=headers("u_admin"))
        missing = await client.get(f"{PATH}/{'f' * 32}/download", headers=headers("u_narrow"))
        grants["u_narrow"] = everywhere(f"read:{ENTITY}")
        narrowed = await client.get(file, headers=headers("u_narrow"))
        kept = await store.one(made.artifact_id)
        return made, listed, decks, theirs, future, fetched, steward, missing, narrowed, kept

    made, listed, decks, theirs, future, fetched, steward, missing, narrowed, kept = pressed(
        database, grants, act
    )
    (row,) = listed["artifacts"]
    assert (row["artifact_id"], row["produced_for"], row["kind"]) == (
        made.artifact_id,
        "u_narrow",
        "report",
    )
    assert (row["downloadable"], row["changeable"]) == (False, True)
    assert row["kept_until"] is None and row["kept_because"]
    assert listed["summary"]["count"] == 1 and listed["summary"]["bytes_stored"] > 0
    assert [one["principal_id"] for one in listed["people"]] == ["u_narrow"]
    assert decks["artifacts"] == [] and future["artifacts"] == []
    assert [one["artifact_id"] for one in theirs["artifacts"]] == [made.artifact_id]
    assert fetched.status_code == 200, fetched.text
    assert fetched.headers["content-type"].startswith("text/csv")
    assert fetched.content.decode().splitlines()[0] == "name,sell_price,cost"
    assert kept is not None and len(fetched.content) == made.bytes_stored
    assert steward.status_code == missing.status_code == narrowed.status_code == 404
    assert steward.json()["message"] == missing.json()["message"] == narrowed.json()["message"]


def test_the_steward_supersedes_the_person_archives_and_a_colleague_is_told_who_may(
    database: str,
) -> None:
    """**M39.5.2.4 on PostgreSQL.** A colleague who may see an artifact and is neither the steward
    nor the person it was for is refused, in the sentence naming who may. The steward supersedes
    the older report by the newer one and the person archives the newer, each a row in the change
    table in their own name; the two artifacts' own rows are untouched and both are still listed,
    and archiving twice is refused as a change the artifact cannot take.

    Delete this and the routes can answer 200 over writes the change table's policies refuse, or
    anybody who may read the Artifacts tab can retire somebody else's report."""
    grants = db_grants()

    async def act(client: httpx.AsyncClient, store: StoredArtifacts, record: Any) -> Any:
        old = await report_for(store, record, grants, at=datetime.now(UTC) - timedelta(hours=2))
        new = await report_for(store, record, grants)
        refused = await client.post(
            f"{PATH}/{old.artifact_id}/archive", headers=headers("u_prefix")
        )
        superseded = await client.post(
            f"{PATH}/{old.artifact_id}/supersede",
            json={"by": new.artifact_id},
            headers=headers("u_admin"),
        )
        archived = await client.post(
            f"{PATH}/{new.artifact_id}/archive", headers=headers("u_narrow")
        )
        again = await client.post(f"{PATH}/{new.artifact_id}/archive", headers=headers("u_narrow"))
        listed = (await client.get(PATH, headers=headers("u_admin"))).json()
        return old, new, refused, superseded, archived, again, listed

    old, new, refused, superseded, archived, again, listed = pressed(database, grants, act)
    assert refused.status_code == 403
    assert refused.json()["message"] == RETIRING_AN_ARTIFACT_NEEDS_THE_STEWARD_OR_ITS_PERSON
    assert superseded.status_code == 200, superseded.text
    assert superseded.json() == {
        "artifact_id": old.artifact_id,
        "state": "superseded",
        "superseded_by": new.artifact_id,
    }
    assert archived.status_code == 200 and archived.json()["state"] == "archived"
    assert again.status_code == 409
    states = {one["artifact_id"]: one["state"] for one in listed["artifacts"]}
    assert states == {old.artifact_id: "superseded", new.artifact_id: "archived"}
    changes = sql(
        database,
        "SELECT artifact_id, state, superseded_by, changed_by FROM agent.artifact_change"
        " ORDER BY changed_at, state",
    )
    assert changes == [
        (old.artifact_id, "superseded", new.artifact_id, "u_admin"),
        (new.artifact_id, "archived", None, "u_narrow"),
    ]
    assert sql(database, "SELECT count(*) FROM agent.artifact") == [(2,)]


def test_the_latest_report_for_a_client_is_found_through_a_merge_and_only_by_who_may_fetch_it(
    database: str,
) -> None:
    """**M39.8.5 on PostgreSQL.** A report recorded against a client that was later merged into
    another is the latest for the survivor, asked at the agent's run reach by the person it was
    for; a colleague who may see the agent and not the report, an unknown client and another kind
    are each the missing answer; and a report naming a client that resolves to nothing is refused
    when it is kept, with nothing left in the bucket.

    Delete this and "the latest proposal for this client" misses everything recorded before a
    merge, or answers somebody the report was not for."""
    grants = db_grants()
    for entity in ("c_kept", "c_gone"):
        sql(
            database,
            "INSERT INTO er.canonical (entity_id, entity_type, created_by, created_from_source,"
            " created_from_entity, created_from_source_id) VALUES (%s, 'company', 'u_admin',"
            " 'crm', 'company', %s)",
            entity,
            entity,
        )
    sql(
        database,
        "UPDATE er.canonical SET merged_into = 'c_kept', merged_at = now()"
        " WHERE entity_id = 'c_gone'",
    )

    async def act(client: httpx.AsyncClient, store: StoredArtifacts, record: Any) -> Any:
        made = await report_for(store, record, grants, client_id="c_gone")
        latest = f"{PATH}/latest"
        asked = {"kind": "report", "client": "c_kept"}
        found = await client.get(latest, params=asked, headers=headers("u_narrow"))
        colleague = await client.get(latest, params=asked, headers=headers("u_prefix"))
        unknown = await client.get(
            latest, params={"kind": "report", "client": "c_nobody"}, headers=headers("u_narrow")
        )
        deck = await client.get(
            latest, params={"kind": "deck", "client": "c_kept"}, headers=headers("u_narrow")
        )
        with pytest.raises(ArtifactError, match="resolves to nothing"):
            await report_for(store, record, grants, client_id="c_nobody")
        return made, found, colleague, unknown, deck

    made, found, colleague, unknown, deck = pressed(database, grants, act)
    assert found.status_code == 200, found.text
    assert (found.json()["artifact_id"], found.json()["client_id"]) == (made.artifact_id, "c_gone")
    assert colleague.status_code == unknown.status_code == deck.status_code == 404
    assert sql(database, "SELECT count(*) FROM agent.artifact") == [(1,)]


OTHER = "sales_desk"


def test_an_artifact_is_answered_only_through_its_own_agent_and_only_to_who_may_see_it(
    database: str,
) -> None:
    """**M39.5.1.5 and M39.5.2.4 on PostgreSQL.** Three refusals the other tests reach only from
    the side that is admitted, each with its sibling admitted beside it:

    - another agent's report, fetched or archived through this agent's address by the very person
      it was made for, is the missing answer, and the same file through its own agent's address is
      handed over;
    - a reader the whole company's agent is visible to, holding the artifact grant only for
      decks, is told somebody else's report does not exist when asking to archive it, and
      archives their own;
    - the person a report was made for may not supersede it by somebody else's report they cannot
      see, and superseding it by their own newer report is accepted.

    Delete this and an artifact id becomes a key that opens every agent's door, a scoped artifact
    grant admits what its scope excludes the moment somebody posts to it, and a supersede can
    point a person's report at a file they were never entitled to know exists."""
    grants = db_grants()
    grants["u_wide"] = (
        *everywhere(f"read:{ENTITY}", f"read:{ENTITY}.cost"),
        Grant(
            capability=tab(Tab.ARTIFACTS).read.requires,
            scope=Scope(clauses=(Clause(field="kind", op=Op.EQ, value="deck"),)),
        ),
    )
    sql(
        database,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Sales desk', 'Answer briefly.', 'main', 'company',"
        " 'u_admin', NULL, '{\"clauses\": []}', '{read:price,read:price.cost}', '{}', '{}',"
        " 'none', 'u_admin')",
        OTHER,
    )
    other_path = f"{API_PREFIX}/agents/{OTHER}/artifacts"

    async def act(client: httpx.AsyncClient, store: StoredArtifacts, record: Any) -> Any:
        theirs = await report_for(store, record.model_copy(update={"agent_id": OTHER}), grants)
        crossed = await client.get(
            f"{PATH}/{theirs.artifact_id}/download", headers=headers("u_narrow")
        )
        own_door = await client.get(
            f"{other_path}/{theirs.artifact_id}/download", headers=headers("u_narrow")
        )
        crossed_archive = await client.post(
            f"{PATH}/{theirs.artifact_id}/archive", headers=headers("u_narrow")
        )
        old = await report_for(store, record, grants, at=datetime.now(UTC) - timedelta(hours=2))
        deck_reader_archive = await client.post(
            f"{other_path}/{theirs.artifact_id}/archive", headers=headers("u_wide")
        )
        own = await report_for(
            store, record.model_copy(update={"agent_id": OTHER}), grants, who="u_wide"
        )
        deck_reader_own = await client.post(
            f"{other_path}/{own.artifact_id}/archive", headers=headers("u_wide")
        )
        colleagues = await report_for(store, record, grants, who="u_prefix")
        unseen = await client.post(
            f"{PATH}/{old.artifact_id}/supersede",
            json={"by": colleagues.artifact_id},
            headers=headers("u_narrow"),
        )
        newer = await report_for(store, record, grants)
        seen = await client.post(
            f"{PATH}/{old.artifact_id}/supersede",
            json={"by": newer.artifact_id},
            headers=headers("u_narrow"),
        )
        return (
            crossed,
            own_door,
            crossed_archive,
            deck_reader_own,
            deck_reader_archive,
            unseen,
            seen,
        )

    crossed, own_door, crossed_archive, deck_reader_own, deck_reader_archive, unseen, seen = (
        pressed(database, grants, act)
    )
    assert own_door.status_code == 200, own_door.text
    assert crossed.status_code == crossed_archive.status_code == 404
    assert crossed.json()["message"] == crossed_archive.json()["message"]
    assert deck_reader_own.status_code == 200, deck_reader_own.text
    assert deck_reader_archive.status_code == 404
    assert deck_reader_archive.json()["message"] == crossed.json()["message"]
    assert unseen.status_code == 409
    assert seen.status_code == 200, seen.text
    assert seen.json()["state"] == "superseded"
