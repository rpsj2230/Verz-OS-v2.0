"""The skills lifecycle (W2.8): a version retired and reinstated, a skill detached from an agent,
what is assigned now, the searchable library, and the queue's count of edits.

Four parts. `0139` rendered and held to the models and the recorder, with no server. The domain,
pure: `current_assignments`, `retiring`, `detachment`, and the queue's edits. The routes, through
the real application with `tests/unit/test_skill_routes.py`'s stub store and session. And the
store against a scratch PostgreSQL, as the application role, which **skips without a server**.

Task ids: M27.11.8, M27.15.55, M27.15.56
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateTable

from brain import skill_routes
from brain.agents.install_store import StoredAgentInstalls as InstallerStore
from brain.agents.template import materialise
from brain.audit.ledger import DIGEST, IDENTIFIER, AuditAction, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, SkillChange
from brain.console.skill_library import (
    DETACH_REASON,
    SKILL_AUTHORITY,
    SKILLS_PATH,
    AssignmentRecord,
    DetachmentRecord,
    Retirement,
    SkillLibraryError,
    assignment,
    current_assignments,
    decided,
    detachment,
    edited,
    holding,
    ledger_reference,
    queue_entries,
    retired_digests,
    retiring,
)
from brain.console.workspace import Part
from brain.db import metadata
from brain.ops.skill_store import StoredSkills
from brain.session import make_session_factory
from brain.tables import skill as table_module
from brain.tools.review import summarise
from brain.tools.skills import SKILL_NAME_RE, SkillPin
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_agent_install_store import MANIFEST, a_draft, finishing
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_memory_store import through_0061
from tests.unit.test_skill_library import (
    AGENT,
    AUDIENCE,
    IMPORTER,
    REVIEWER,
    a_library_skill,
    a_recorder,
    an_approved_skill,
    an_install,
    reach,
    text_with,
)
from tests.unit.test_skill_routes import (
    DIALECT,
    SKILLS,
    Stored,
    a_package,
    an_assignable_agent,
    an_edit,
    get,
    post,
    screen_refusal,
)
from tests.unit.test_skill_routes import client as client  # the fixture, re-exported
from tests.unit.test_skill_routes import stored as stored  # the fixture, re-exported
from tests.unit.test_skill_store import entries
from tests.unit.test_tables import VERSIONS, as_amended, migration_module, rendered, squash

MIGRATION = VERSIONS / "0139_skill_retirement_and_detachment.py"
TABLES = ("agent.skill_retirement", "agent.skill_detachment")
LIBRARY = f"{SKILLS}/library"
NOW = a_library_skill().submitted_at


# ------------------------------------------------------------------------------ 0139
def test_0139_copies_the_grammars_and_words_the_models_and_the_recorder_hold() -> None:
    """Delete this and one side can change alone: a skill name the detachment table refuses after
    the press, or a reason code the trigger writes that `AuditRecorder` no longer spells."""
    migration = migration_module(MIGRATION)

    assert migration.TABLES == TABLES
    assert (migration.IDENTIFIER, migration.DIGEST) == (IDENTIFIER, DIGEST)
    assert migration.SKILL_NAME_PATTERN == SKILL_NAME_RE.pattern == table_module.SKILL_NAME_PATTERN
    assert (migration.NAME_CHARS, migration.DIGEST_CHARS) == (
        table_module.NAME_CHARS,
        table_module.DIGEST_CHARS,
    )
    assert migration.PART == Part.SKILLS.value == SKILLS_PATH
    assert migration.DETACH_REASON == DETACH_REASON
    assert migration.down_revision == "0133"


@pytest.mark.parametrize("qualified", TABLES)
def test_0139_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared as rendered DDL, for `test_tables`' reason. Delete this and the model can gain a
    column or lose the key that holds one assignment to one detachment, with the database built
    the old way."""
    expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=DIALECT)))

    assert expected in as_amended(rendered("upgrade", MIGRATION))


def test_0139_reads_and_writes_in_the_session_s_name_and_never_edits_or_removes() -> None:
    """Row-level security on both, SELECT and INSERT only, each insert in the session's own name,
    a trigger after every insert, and a downgrade that drops what the upgrade made.

    Delete this and an UPDATE grant, or a policy admitting a retirement in somebody else's name,
    ships with every other test here green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    for qualified, column in (
        ("agent.skill_retirement", "set_by"),
        ("agent.skill_detachment", "detached_by"),
    ):
        assert f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY" in emitted
        assert f"GRANT SELECT, INSERT ON {qualified} TO brain_app" in emitted
        assert f"UPDATE ON {qualified}" not in emitted
        assert f"DELETE ON {qualified}" not in emitted
        assert f"FOR INSERT TO brain_app WITH CHECK ({column} = {principal})" in emitted
    assert (
        "CREATE TRIGGER skill_retirement_is_audited AFTER INSERT ON agent.skill_retirement "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_retirement()"
    ) in emitted
    assert (
        "CREATE TRIGGER skill_detachment_is_audited AFTER INSERT ON agent.skill_detachment "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_detachment()"
    ) in emitted
    down = squash(rendered("downgrade", MIGRATION))
    assert down.index("DROP TABLE agent.skill_detachment") < down.index(
        "DROP TABLE agent.skill_retirement"
    )
    assert "DROP FUNCTION agent.record_skill_retirement()" in down


def test_0139_s_triggers_write_what_the_recorder_writes() -> None:
    """A retirement is a `skill` entry saying `retired` or `reinstated` with the digest; a
    detachment is a `compose_change` about the agent, detached, under the folded name.

    Delete this and the entry a deployed database keeps can drift from the recorder's, and the
    audit screen fails to load the first detachment of a hyphenated skill."""
    migration = migration_module(MIGRATION)
    one = an_approved_skill()
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    retired = recorder.skill(name=one.name, digest=one.digest, change=SkillChange.RETIRED)
    detached = recorder.compose_change(
        agent_id=AGENT,
        part=SKILLS_PATH,
        reference=ledger_reference(one.name),
        attached=False,
        reason_code=DETACH_REASON,
    )
    retirement = " ".join(migration.SKILL_RETIREMENT_TRIGGER_FUNCTION.split())
    detachment_body = " ".join(migration.SKILL_DETACHMENT_TRIGGER_FUNCTION.split())

    assert dict(retired.details) == {"change": "retired", "digest": one.digest}
    assert SkillChange.REINSTATED.value == "reinstated"
    assert (
        "'change', CASE WHEN NEW.retired THEN 'retired' ELSE 'reinstated' END, "
        "'digest', NEW.digest" in retirement
    )
    assert "v_seq, v_at, NEW.set_by, 'skill', v_subject" in retirement
    assert dict(detached.details) == {
        "part": "skills",
        "reference": "hosting_expiry",
        "direction": "detached",
        "reason_code": DETACH_REASON,
    }
    assert (
        "'part', 'skills', 'reference', replace(NEW.skill_name, '-', '_'), "
        "'direction', 'detached', 'reason_code', 'skill_detach'" in detachment_body
    )
    assert "v_seq, v_at, NEW.detached_by, 'compose_change', v_subject" in detachment_body


# ------------------------------------------------------------------------------ the domain
def a_record(n: int, *, agent: str = AGENT, digest: str = "a" * 64) -> AssignmentRecord:
    return AssignmentRecord(
        assignment_id=f"assignment-{n}",
        agent_id=agent,
        skill_name="hosting-expiry",
        digest=digest,
        assigned_by="u_admin",
        at=NOW + timedelta(minutes=n),
    )


def test_the_assignments_in_force_are_the_newest_per_agent_that_no_detachment_names() -> None:
    """**M27.15.55.** Two agents assigned; one replaced by a later version, which is the one in
    force; the other detached, so none is. The positive case is the first agent's replacement.

    Delete this and a detached skill reads as still assigned, or a replaced version as current
    beside the one that replaced it."""
    first = a_record(0)
    replaced_by = a_record(2, digest="b" * 64)
    other = a_record(1, agent="web_helper")
    ended = DetachmentRecord(
        assignment_id=other.assignment_id,
        agent_id=other.agent_id,
        skill_name=other.skill_name,
        digest=other.digest,
        detached_by="u_admin",
        at=NOW + timedelta(minutes=3),
    )

    assert current_assignments((first, other, replaced_by), (ended,)) == (replaced_by,)
    assert current_assignments((first, other), ()) == (first, other)


def test_a_detachment_naming_no_assignment_ends_none() -> None:
    """A template's own skill detached has no assignment to name. Delete this and a detachment
    with an empty assignment ends whichever assignment has no id, which is none today and every
    one the day an id is missing."""
    one = a_record(0)
    template_pin = DetachmentRecord(
        assignment_id=None,
        agent_id=AGENT,
        skill_name="hosting-expiry",
        digest="a" * 64,
        detached_by="u_admin",
        at=NOW,
    )

    assert current_assignments((one,), (template_pin,)) == (one,)


def test_retiring_what_is_retired_or_reinstating_what_is_not_is_refused() -> None:
    """**M27.15.56.** Each would add a row and an entry for nothing. The positive cases are the two
    that change something. Delete this and the history shows a version retired twice."""
    one = an_approved_skill()
    retired = Retirement(digest=one.digest, retired=True, set_by="u_admin", at=NOW)
    back = Retirement(digest=one.digest, retired=False, set_by="u_admin", at=NOW)

    retiring(one, retire=True, current=None)
    retiring(one, retire=True, current=back)
    retiring(one, retire=False, current=retired)
    with pytest.raises(SkillLibraryError, match="nothing was retired"):
        retiring(one, retire=True, current=retired)
    with pytest.raises(SkillLibraryError, match="nothing was reinstated"):
        retiring(one, retire=False, current=None)
    with pytest.raises(SkillLibraryError, match="nothing was reinstated"):
        retiring(one, retire=False, current=back)
    assert retired_digests({one.digest: retired}) == {one.digest}
    assert retired_digests({one.digest: back}) == frozenset()


def test_the_agents_holding_a_version_are_those_running_those_bytes_each_once() -> None:
    """Delete this and a retirement lists an agent running another version as holding this one."""
    pins = (
        SkillPin(agent_id="b_agent", skill_name="hosting-expiry", digest="a" * 64),
        SkillPin(agent_id="a_agent", skill_name="hosting-expiry", digest="a" * 64),
        SkillPin(agent_id="c_agent", skill_name="hosting-expiry", digest="b" * 64),
    )

    assert holding("a" * 64, pins) == ("a_agent", "b_agent")


def test_a_detachment_writes_the_agent_s_skills_without_it_and_nothing_else() -> None:
    """**M27.15.55, the domain half.** An assigned skill detached leaves the skills path empty and
    the authority where it was; bytes the agent does not run, or a skill it does not run at all,
    are refused in words.

    Delete this and detaching one version can remove another, or report a change that did not
    happen."""
    one = an_approved_skill()
    signed, instance, record = an_install()
    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
    )
    held = materialise(signed, made.instance, audience=AUDIENCE)

    off = detachment(
        one,
        record=held.record,
        signed=signed,
        instance=made.instance,
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
    )
    after = materialise(signed, off.instance, audience=AUDIENCE)

    assert off.instance.overlay[SKILLS_PATH] == []
    assert after.skill_pins == ()
    assert after.record.authority == held.record.authority
    assert (off.digest, off.detached_by) == (one.digest, "u_admin")
    other = an_approved_skill(text_with(version="1.1.0"))
    with pytest.raises(SkillLibraryError, match="runs another version"):
        detachment(
            other,
            record=held.record,
            signed=signed,
            instance=made.instance,
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(AuditChain()),
            now=NOW,
        )
    with pytest.raises(SkillLibraryError, match="does not run"):
        detachment(
            one,
            record=after.record,
            signed=signed,
            instance=off.instance,
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(AuditChain()),
            now=NOW,
        )


def test_an_edit_of_a_version_still_waiting_is_counted_as_an_edit() -> None:
    """**The queue's known bug.** A version added and edited before anybody approved it: both wait,
    and the edit is one, so the summary says one of them is an edit. Until 2026-09-28 only an
    approved version was a baseline and it said nought beside it.

    Delete this and the queue goes back to telling a reviewer an edit is a first submission, which
    is the difference between reading two changed lines and reading the whole skill."""
    first = a_library_skill()
    edit = edited(first, an_edit(), by=IMPORTER, at=NOW + timedelta(minutes=1), library=(first,))

    queued = queue_entries((first, edit), NOW + timedelta(minutes=2))
    summary = summarise([one.record for one in queued], NOW + timedelta(minutes=2))

    assert (summary.waiting, summary.edits) == (2, 1)
    assert [one.record.is_edit for one in queued] == [False, True]


# ------------------------------------------------------------------------------ the routes
def an_assigned_skill(c: TestClient, store: Stored, agent_id: str = "company_desk") -> str:
    """A skill added, approved by a second person and assigned to one agent; its digest."""
    an_assignable_agent(store, agent_id)
    digest = str(post(c, "u_admin", SKILLS, a_package()).json()["digest"])
    post(c, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assigned = post(c, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": agent_id})
    assert assigned.status_code == 201, assigned.text
    return digest


def test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached(
    client: TestClient, stored: Stored
) -> None:
    """**M27.15.56 end to end.** A version assigned to one agent is retired: the answer lists that
    agent for detaching, the agent still runs it, the library says it is retired and not
    assignable, and assigning it to a second agent is refused in words. Reinstating it makes the
    second assignment succeed.

    Delete this and retiring either takes the skill off live agents without anybody deciding it,
    or leaves the version assignable while saying it is retired."""
    digest = an_assigned_skill(client, stored)
    an_assignable_agent(stored, "sales_helper")

    retired = post(client, "u_admin", f"{SKILLS}/{digest}/retirement", {})

    assert retired.status_code == 200, retired.text
    assert retired.json()["retired"] is True
    assert retired.json()["holding"] == [
        {"agent_id": "company_desk", "display_name": "Company Desk"}
    ]
    page = get(client, "u_admin").json()
    assert [one["agent_id"] for one in page["items"][0]["pinned_by"]] == ["company_desk"]
    row = page["library"][0]
    assert (row["retired"], row["assignable"], row["retirable"]) == (True, False, True)
    refused = post(
        client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "sales_helper"}
    )
    assert refused.status_code == 404
    assert "is retired" in refused.json()["message"]
    again = post(client, "u_admin", f"{SKILLS}/{digest}/retirement", {})
    assert "nothing was retired" in again.json()["message"]

    back = post(client, "u_admin", f"{SKILLS}/{digest}/reinstatement", {})
    assert (back.status_code, back.json()["retired"], back.json()["holding"]) == (200, False, [])
    assigned = post(
        client, "u_admin", f"{SKILLS}/{digest}/assignments", {"agent_id": "sales_helper"}
    )
    assert assigned.status_code == 201, assigned.text
    assert [(one.retired, one.set_by) for one in stored.library.retired] == [
        (True, "u_admin"),
        (False, "u_admin"),
    ]


def test_retiring_needs_the_skill_authority_and_asks_it_before_anything_is_read(
    client: TestClient, stored: Stored
) -> None:
    """A reviewer who may not add is given the screen's one sentence for a retirement and a
    reinstatement, and the library is never asked. Delete this and deciding about skills becomes
    enough to withdraw one from every agent."""
    digest = an_assigned_skill(client, stored)
    stored.library.calls.clear()

    for path in ("retirement", "reinstatement"):
        refused = post(client, "u_wide", f"{SKILLS}/{digest}/{path}", {})
        assert refused.status_code == 404
        assert refused.json()["message"] == screen_refusal(client)
    assert stored.library.calls == []


def test_a_detached_skill_is_gone_from_the_agent_and_its_assignment_is_no_longer_in_force(
    client: TestClient, stored: Stored
) -> None:
    """**M27.15.55 end to end.** A skill assigned and then detached: the agent no longer runs it,
    the detachment row names the assignment it ended, the assignment row is still there, and none
    is in force. Detaching it again is refused in words.

    Delete this and a detachment can leave the skill in the manifest a run reads, or remove the
    assignment it ended from the history."""
    digest = an_assigned_skill(client, stored)

    off = {"agent_id": "company_desk"}
    detached = post(client, "u_admin", f"{SKILLS}/{digest}/detachments", off)

    assert detached.status_code == 201, detached.text
    assert (detached.json()["agent_id"], detached.json()["digest"]) == ("company_desk", digest)
    assert get(client, "u_admin").json()["items"] == []
    [assigned] = stored.library.records
    [ended] = stored.library.detachments
    assert ended.assignment_id == assigned.assignment_id
    assert current_assignments(stored.library.records, stored.library.detachments) == ()
    again = post(client, "u_admin", f"{SKILLS}/{digest}/detachments", off)
    assert again.status_code == 404
    assert "does not run" in again.json()["message"]


def test_detaching_from_an_agent_outside_the_audience_or_the_authority_is_refused_as_absent(
    client: TestClient, stored: Stored
) -> None:
    """`u_elsewhere` holds the skill authority in finance only: an agent in sales and an agent that
    does not exist are both the screen's one sentence, and nothing is written. The positive case is
    the test above. Delete this and detaching reaches agents the assignment route refuses."""
    digest = an_assigned_skill(client, stored)

    for agent in ("company_desk", "no_such_agent"):
        refused = post(client, "u_elsewhere", f"{SKILLS}/{digest}/detachments", {"agent_id": agent})
        assert refused.status_code == 404
        assert refused.json()["message"] == screen_refusal(client)
    assert stored.library.detached == []


def test_the_library_is_searched_and_filtered_on_the_server(
    client: TestClient, stored: Stored
) -> None:
    """**M27.11.8.** One row per version with its state, whether it is retired, its categories
    and how many of the reader's agents run it; a search, a state filter, a retired filter and a
    category filter each narrow it on the server. The queue's summary rides on the page.

    Delete this and the library is filtered in the browser over whatever arrived, which is a
    statement about a page dressed as one about the library."""
    digest = an_assigned_skill(client, stored)
    post(client, "u_admin", f"{SKILLS}/{digest}/categories", {"categories": ["hosting"]})
    quote = text_with(name="quote-format", description="Use when a client asks for a quote")
    waiting = post(client, "u_admin", SKILLS, a_package(quote)).json()["digest"]
    post(client, "u_admin", f"{SKILLS}/{waiting}/retirement", {})

    def rows(query: str = "") -> list[tuple[str, str, bool, int]]:
        body = get(client, "u_admin", f"{LIBRARY}{query}").json()
        return [
            (one["name"], one["review"], one["retired"], one["agents_running"])
            for one in body["items"]
        ]

    assert rows() == [
        ("hosting-expiry", "approved", False, 1),
        ("quote-format", "pending", True, 0),
    ]
    assert rows("?q=quote") == [("quote-format", "pending", True, 0)]
    assert rows("?filter=review:approved") == [("hosting-expiry", "approved", False, 1)]
    assert rows("?filter=retired:true") == [("quote-format", "pending", True, 0)]
    assert rows("?filter=categories:hosting") == [("hosting-expiry", "approved", False, 1)]
    body = get(client, "u_admin", LIBRARY).json()
    assert body["categories"] == ["hosting"]
    assert (body["queue"]["waiting"], body["may_add"], body["total"]) == (1, True, None)


def test_a_reader_the_library_is_not_listed_to_is_answered_the_empty_page(
    client: TestClient, stored: Stored
) -> None:
    """`u_elsewhere` may open the screen in finance only, which reaches no library row: the
    library listing answers them exactly as an empty library answers, with no queue. A caller
    holding nothing is refused. Delete this and the listing becomes a second way to read the
    library around `may_read_library`."""
    an_assigned_skill(client, stored)

    body = get(client, "u_elsewhere", LIBRARY).json()

    assert (body["items"], body["queue"]["entries"], body["categories"]) == ([], [], [])
    assert get(client, "u_none", LIBRARY).status_code == 404


def test_people_are_named_beside_their_identifiers(client: TestClient, stored: Stored) -> None:
    """Who added, decided and assigned a skill is sent as the directory's display name, and the
    identifier stays for the Advanced section. Delete this and the page goes back to printing
    principal ids where a person's name belongs."""
    stored.people.update({"u_admin": "Alex Admin", "u_wide": "Wendy Wide"})
    an_assigned_skill(client, stored)

    page = get(client, "u_admin").json()

    row = page["library"][0]
    assert (row["submitted_by"], row["submitted_by_name"]) == ("u_admin", "Alex Admin")
    assert (row["reviewer"], row["reviewer_name"]) == ("u_wide", "Wendy Wide")
    assert page["items"][0]["pinned_by"][0]["assigned_by"] == "Alex Admin"


# ------------------------------------------------------------------------------ the database
@pytest.fixture
def database() -> Iterator[str]:
    """A scratch database with every migration applied. **Skips without a server.**"""
    with through_0061("brain_skill_lifecycle") as url:
        yield url


def test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store(
    database: str,
) -> None:
    """**M27.15.55 and M27.15.56 through the store and the application role.** An agent installed,
    a skill added, approved and assigned to it through the store; a detachment with a hash from
    before the assignment is refused and writes nothing; one with the current hash writes the
    install and a row naming the assignment it ended; the version is retired and reinstated. The
    history reads back with nothing in force, the newest retirement row is the reinstatement, the
    agent's install runs no skill, and the ledger holds one entry per write; the chain verifies.

    Delete this and the detachment's lock, its lookup of the assignment it ends and both triggers
    are claims about SQL nobody has run."""
    one = a_library_skill()
    good = decided(one, reviewer=REVIEWER, approve=True, at=NOW)
    admin = reach(SKILL_AUTHORITY.value)

    async def go() -> tuple[Any, ...]:
        built = app_engine(database)
        try:
            sessions = make_session_factory(built)
            await finishing(InstallerStore(sessions), a_draft())()
            skills = StoredSkills(sessions)
            installs = skill_routes.StoredAgentInstalls(sessions)
            assert await skills.add(one, ent_hash="a" * 32, trace_id="t-add")
            assert await skills.decide(good, ent_hash="b" * 32, trace_id="t-decide")
            found = await installs.agent(MANIFEST.identity.template_id)
            assert found is not None and found.install is not None
            signed, instance = found.install
            made = assignment(
                good,
                record=found.record,
                signed=signed,
                instance=instance,
                library=(good,),
                by=admin,
                recorder=a_recorder(AuditChain()),
                now=NOW,
            )
            assert await skills.assign(
                made, expected_hash=str(found.effective_hash), ent_hash="c" * 32, trace_id="t-as"
            )
            held = await installs.agent(MANIFEST.identity.template_id)
            assert held is not None and held.install is not None
            off = detachment(
                good,
                record=held.record,
                signed=held.install[0],
                instance=held.install[1],
                by=admin,
                recorder=a_recorder(AuditChain()),
                now=NOW,
            )
            stale = await skills.detach(
                off, expected_hash=str(found.effective_hash), ent_hash="d" * 32, trace_id="t-old"
            )
            done = await skills.detach(
                off, expected_hash=str(held.effective_hash), ent_hash="d" * 32, trace_id="t-off"
            )
            for retired in (True, False):
                await skills.retire(
                    good.digest, retired=retired, by="u_admin", ent_hash="e" * 32, trace_id="t-r"
                )
            after = await installs.agent(MANIFEST.identity.template_id)
            return (
                stale,
                done,
                await skills.assignment_history([good.name]),
                await skills.retirements([good.digest]),
                after,
            )
        finally:
            await built.dispose()

    stale, done, history, retirements, after = run(go)
    chain = entries(database)

    assert (stale, done) == (False, True)
    assigned, detached = history
    assert [one.assignment_id for one in detached] == [assigned[0].assignment_id]
    assert current_assignments(assigned, detached) == ()
    assert retirements[good.digest].retired is False
    assert after is not None and after.install is not None
    assert materialise(*after.install, audience=after.record.audience).skill_pins == ()
    lifecycle = [
        (entry.action, entry.subject, dict(entry.details))
        for entry in chain
        if entry.subject in (f"skill:{good.name}", f"agent:{MANIFEST.identity.template_id}")
        and entry.action in (AuditAction.SKILL, AuditAction.COMPOSE_CHANGE)
    ]
    assert lifecycle[-3:] == [
        (
            AuditAction.COMPOSE_CHANGE,
            f"agent:{MANIFEST.identity.template_id}",
            {
                "part": "skills",
                "reference": "hosting_expiry",
                "direction": "detached",
                "reason_code": DETACH_REASON,
            },
        ),
        (AuditAction.SKILL, f"skill:{good.name}", {"change": "retired", "digest": good.digest}),
        (
            AuditAction.SKILL,
            f"skill:{good.name}",
            {"change": "reinstated", "digest": good.digest},
        ),
    ]
    assert AuditChain(chain).verify() is None


def test_the_tables_refuse_a_second_end_to_one_assignment_and_a_row_in_another_s_name(
    database: str,
) -> None:
    """Measured as the application role: a detachment naming an assignment already ended, a
    retirement or a detachment in somebody else's name, a retirement of bytes nobody added, and
    an update of a retirement are each refused by the database itself.

    Delete this and every rule here is a claim about a table definition nobody has run."""
    one = a_library_skill(text_with(name="quote-format", description="Use when asked to quote"))
    good = decided(one, reviewer=REVIEWER, approve=True, at=NOW)

    async def seed() -> None:
        built = app_engine(database)
        try:
            skills = StoredSkills(make_session_factory(built))
            assert await skills.add(one, ent_hash="a" * 32, trace_id="t")
            assert await skills.decide(good, ent_hash="b" * 32, trace_id="t")
        finally:
            await built.dispose()

    run(seed)
    with as_app(database, ("app.principal_id", "u_admin")) as conn:
        conn.execute(
            "INSERT INTO agent.skill_assignment (agent_id, skill_name, digest, assigned_by)"
            " VALUES (%s, %s, %s, 'u_admin')",
            (AGENT, one.name, one.digest),
        )
    [(assignment_id,)] = sql(database, "SELECT id FROM agent.skill_assignment")
    detaching = (
        "INSERT INTO agent.skill_detachment"
        " (assignment_id, agent_id, skill_name, digest, detached_by)"
        " VALUES (%s, %s, %s, %s, %s)"
    )
    with as_app(database, ("app.principal_id", "u_admin")) as conn:
        conn.execute(detaching, (assignment_id, AGENT, one.name, one.digest, "u_admin"))
    with (
        as_app(database, ("app.principal_id", "u_admin")) as conn,
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        conn.execute(detaching, (assignment_id, AGENT, one.name, one.digest, "u_admin"))
    with (
        as_app(database, ("app.principal_id", "u_admin")) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(detaching, (None, AGENT, one.name, one.digest, "u_somebody_else"))
    with (
        as_app(database, ("app.principal_id", "u_admin")) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "INSERT INTO agent.skill_retirement (digest, retired, set_by)"
            " VALUES (%s, true, 'u_somebody_else')",
            (one.digest,),
        )
    with (
        as_app(database, ("app.principal_id", "u_admin")) as conn,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        conn.execute(
            "INSERT INTO agent.skill_retirement (digest, retired, set_by) VALUES (%s, true, %s)",
            ("f" * 64, "u_admin"),
        )
    with as_app(database, ("app.principal_id", "u_admin")) as conn:
        conn.execute(
            "INSERT INTO agent.skill_retirement (digest, retired, set_by) VALUES (%s, true, %s)",
            (one.digest, "u_admin"),
        )
    with (
        as_app(database, ("app.principal_id", "u_admin")) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("UPDATE agent.skill_retirement SET retired = false")
    chain: list[AuditEntry] = entries(database)
    assert AuditChain(chain).verify() is None
