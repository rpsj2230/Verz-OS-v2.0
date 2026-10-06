"""A skill's example tasks, rehearsed against one version before it may be approved (M12.3.4).

The first half reads examples out of a `SKILL.md` and judges rehearsals of them: a line of the
wrong shape, an example expecting a tool the skill does not name and two examples stating one task
are refused at the door; an outcome passes exactly when every expected tool is reachable; and only
a rehearsal of the exact digest that covered every example, every one passing, clears approval.
The second half is the route, through the application: a reviewer rehearses a waiting version
through an agent, approval is refused until a rehearsal clears it and allowed once one has, a
failing example keeps it refused, an edit needs a rehearsal of its own, and the result always says
what it could not judge. The third builds PostgreSQL to head: the row, its ledger entry naming no
task, and a row in somebody else's name refused.

Task ids: M12.3.4
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from brain.console.skill_library import SkillLibraryError, added, read_package
from brain.tools.skill_examples import (
    A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER,
    ExampleOutcome,
    Rehearsal,
    RehearsalKind,
    SkillExample,
    examples_of,
    rehearsal_clears,
    rehearse_reach,
)
from brain.tools.skills import SkillError, skill_from_markdown
from tests.unit.test_skill_library import SKILL_MD
from tests.unit.test_skill_routes import (
    SKILLS,
    Stored,
    a_package,
    an_assignable_agent,
    post,
)
from tests.unit.test_skill_routes import client as client
from tests.unit.test_skill_routes import stored as stored

#: Far outside any plausible wall clock. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

#: Two examples: one the company desk's client tool reaches, one its ceiling does not allow.
REACHED = "Is example.com due for renewal this month => crm.read_client"
UNREACHED = "Open a renewal ticket for example.com => desk.read_ticket"


def with_examples(*lines: str, text: str = SKILL_MD) -> str:
    return text + "\n## Examples\n" + "".join(f"- {line}\n" for line in lines)


# ------------------------------------------------------------------ the examples


def test_a_version_s_examples_are_read_from_its_body_in_order() -> None:
    """**EXAMPLES_ARE_PART_OF_THE_VERSION.** Each line under the heading is one example, its task
    and the tools it expects, `none` for an example expecting no tool, and a heading after the
    section ends it. Delete this and the examples a reviewer sees can differ from the ones a
    rehearsal checks."""
    text = with_examples(REACHED, "Say hello to the client => none") + "## Notes\n- not one\n"

    found = examples_of(skill_from_markdown(text))

    assert found == (
        SkillExample(
            task="Is example.com due for renewal this month", expects=("crm.read_client",)
        ),
        SkillExample(task="Say hello to the client", expects=()),
    )
    assert examples_of(skill_from_markdown(SKILL_MD)) == ()


@pytest.mark.parametrize(
    ("lines", "words"),
    [
        (("A line with no arrow",), "is not"),
        (("Find the client => crm.read_client, not a tool!",), "not a tool list"),
        (("Send the invoice => billing.send_invoice",), "does not list in its tools"),
        ((REACHED, REACHED), "the same task"),
        (("=> crm.read_client",), "empty"),
    ],
)
def test_an_example_that_cannot_be_rehearsed_is_refused_at_the_door(
    lines: tuple[str, ...], words: str
) -> None:
    """A malformed line, a tool list that is not one, a tool the skill does not name, two examples
    stating one task, and an empty task are each refused, by the reader and by the library's way
    in, saying which. Delete this and a version can carry an example no rehearsal can ever clear,
    or two outcomes nobody can tell apart."""
    text = with_examples(*lines)

    with pytest.raises(SkillError, match=words):
        examples_of(skill_from_markdown(text))
    with pytest.raises(SkillLibraryError, match=words):
        read_package("SKILL.md", text.encode("utf-8"))


def test_an_example_passes_exactly_when_every_tool_it_expects_is_reached() -> None:
    """Delete this and an example can pass with one of its tools out of reach, or fail with all of
    them in it."""
    examples = examples_of(skill_from_markdown(with_examples(REACHED, UNREACHED)))

    outcomes = rehearse_reach(examples, ("crm.read_client",))

    assert outcomes == (
        ExampleOutcome(task="Is example.com due for renewal this month", passed=True),
        ExampleOutcome(
            task="Open a renewal ticket for example.com",
            passed=False,
            missing=("desk.read_ticket",),
        ),
    )
    assert all(
        one.passed for one in rehearse_reach(examples, ("crm.read_client", "desk.read_ticket"))
    )


def test_only_a_passing_rehearsal_of_the_exact_digest_covering_every_example_clears_it() -> None:
    """**A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_ONCE_A_REHEARSAL_OF_ITS_DIGEST_CLEARS_THEM.** A
    passing rehearsal of the same digest clears; one of another digest, one that failed an example,
    and one that covered only some examples do not; a version with no examples has nothing to
    clear. Delete this and approval can rest on a rehearsal of other bytes, or of half the cases."""
    examples = examples_of(skill_from_markdown(with_examples(REACHED, UNREACHED)))
    passing = rehearse_reach(examples, ("crm.read_client", "desk.read_ticket"))
    digest, other = "a" * 64, "b" * 64

    def made(on: str, outcomes: tuple[ExampleOutcome, ...]) -> Rehearsal:
        return Rehearsal(digest=on, kind=RehearsalKind.REACH, outcomes=outcomes)

    assert rehearsal_clears(digest, examples, [made(digest, passing)])
    assert not rehearsal_clears(digest, examples, [made(other, passing)])
    assert not rehearsal_clears(digest, examples, [made(digest, rehearse_reach(examples, ()))])
    assert not rehearsal_clears(digest, examples, [made(digest, passing[:1])])
    assert not rehearsal_clears(digest, examples, [])
    assert rehearsal_clears(digest, (), [])
    # A rehearsal of nothing is not a pass, which is what its row says it was.
    assert made(digest, ()).passed is False


def test_every_kind_a_rehearsal_records_fits_the_column_that_holds_it() -> None:
    """The kind is held to a grammar in the table and in `0191`, so a new kind needs no migration;
    every kind this release writes fits both. Delete this and a kind can be added that the table
    refuses at the first rehearsal."""
    from brain.tables.skill import REHEARSAL_KIND_PATTERN
    from tests.unit.test_tables import VERSIONS, migration_module

    migration = migration_module(VERSIONS / "0191_skill_export_and_rehearsal.py")

    assert migration.REHEARSAL_KIND_PATTERN == REHEARSAL_KIND_PATTERN
    assert all(re.fullmatch(REHEARSAL_KIND_PATTERN, one.value) for one in RehearsalKind)


def test_a_rehearsal_row_of_a_kind_this_release_does_not_know_clears_nothing() -> None:
    """A later release's kind read here is no rehearsal at all, rather than one that cleared
    approval. Delete this and a row this release cannot interpret is read as a pass."""
    from types import SimpleNamespace
    from typing import Any, cast

    from brain.ops.skill_store import rehearsal_of

    row = SimpleNamespace(
        digest="a" * 64,
        kind="telepathy",
        agent_id="company_desk",
        passed=True,
        outcomes=[{"task": "Anything", "passed": True, "missing": []}],
        rehearsed_by="u_admin",
        created_at=NOW,
    )

    assert rehearsal_of(cast("Any", row)) is None
    assert rehearsal_of(cast("Any", SimpleNamespace(**{**vars(row), "kind": "reach"}))) is not None


# ------------------------------------------------------------------ the route


def added_waiting(client: TestClient, text: str) -> str:
    response = post(client, "u_admin", SKILLS, a_package(text))
    assert response.status_code == 201, response.text
    return str(response.json()["digest"])


def test_a_version_is_approved_only_after_a_rehearsal_of_its_examples_passes(
    client: TestClient, stored: Stored
) -> None:
    """**M12.3.4 through the application.** Approving a waiting version with examples is refused
    and says why; a reviewer rehearses it through an agent and every example passes, recorded in
    their name and answered with what the rehearsal could not judge; then the same approval is
    allowed. Delete this and a version is approved with examples nobody rehearsed."""
    an_assignable_agent(stored)
    digest = added_waiting(client, with_examples(REACHED))

    early = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    rehearsed = post(
        client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "company_desk"}
    )
    later = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    assert early.status_code == 404
    assert "rehearse this version's 1 example tasks" in early.json()["message"]
    assert rehearsed.status_code == 201, rehearsed.text
    body = rehearsed.json()
    assert (body["passed"], body["kind"], body["agent_id"]) == (True, "reach", "company_desk")
    assert body["limit"] == A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER
    assert [(one.digest, one.rehearsed_by) for one in stored.library.rehearsed] == [
        (digest, "u_admin")
    ]
    assert later.status_code == 200, later.text
    assert later.json()["review"] == "approved"


def test_a_failing_example_keeps_the_version_unapproved_and_says_what_it_lacked(
    client: TestClient, stored: Stored
) -> None:
    """One example expects a tool the agent's ceiling does not allow: the rehearsal is recorded as
    failed, naming that tool for that example, and approval stays refused. Rejecting is never
    held. Delete this and a version can be approved on a rehearsal one of whose cases failed, or a
    reviewer held from rejecting what they cannot rehearse."""
    an_assignable_agent(stored)
    digest = added_waiting(client, with_examples(REACHED, UNREACHED))

    rehearsed = post(
        client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "company_desk"}
    )
    approve = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    reject = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "reject"})

    assert rehearsed.status_code == 201
    assert rehearsed.json()["passed"] is False
    assert [(one["task"], one["missing"]) for one in rehearsed.json()["outcomes"]] == [
        ("Is example.com due for renewal this month", []),
        ("Open a renewal ticket for example.com", ["desk.read_ticket"]),
    ]
    assert approve.status_code == 404
    assert reject.status_code == 200


def test_an_edit_needs_a_rehearsal_of_its_own_bytes(client: TestClient, stored: Stored) -> None:
    """A version is rehearsed and approved; an edit saved from it is a new digest, and its approval
    is refused until it is rehearsed itself. Delete this and an edit inherits the rehearsal of the
    version it replaced, which is a statement about other bytes."""
    an_assignable_agent(stored)
    first = added_waiting(client, with_examples(REACHED))
    post(client, "u_admin", f"{SKILLS}/{first}/rehearsals", {"agent_id": "company_desk"})
    assert (
        post(client, "u_admin", f"{SKILLS}/{first}/review", {"decision": "approve"}).status_code
        == 200
    )

    edited = with_examples(REACHED).replace("version: 1.0.0", "version: 1.1.0")
    saved = post(client, "u_admin", f"{SKILLS}/{first}/versions", {"content": edited})
    assert saved.status_code == 201, saved.text
    second = str(saved.json()["digest"])

    refused = post(client, "u_admin", f"{SKILLS}/{second}/review", {"decision": "approve"})
    post(client, "u_admin", f"{SKILLS}/{second}/rehearsals", {"agent_id": "company_desk"})
    allowed = post(client, "u_admin", f"{SKILLS}/{second}/review", {"decision": "approve"})

    assert (refused.status_code, allowed.status_code) == (404, 200)


def test_a_version_with_no_examples_cannot_be_rehearsed_and_is_not_held(
    client: TestClient, stored: Stored
) -> None:
    """A version carrying no examples is refused a rehearsal saying how to add them, and its
    approval is not held, so every skill added before examples existed can still be reviewed.
    Delete this and a rehearsal can be recorded of nothing, or every older skill held for ever."""
    an_assignable_agent(stored)
    digest = added_waiting(client, SKILL_MD)

    rehearsed = post(
        client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "company_desk"}
    )
    approved = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})

    assert rehearsed.status_code == 404
    assert "carries no example tasks" in rehearsed.json()["message"]
    assert approved.status_code == 200
    assert stored.library.rehearsed == []


def test_a_reader_who_may_not_review_or_an_agent_they_cannot_see_is_the_one_404(
    client: TestClient, stored: Stored
) -> None:
    """A reader holding only the screen, a reviewer naming an agent that does not exist, and one
    naming an agent outside their audience, get the refusal that names the screen and nothing else;
    nothing is recorded. Delete this and a
    rehearsal can be recorded by somebody who may not review, or say which agents exist."""
    from brain.knowledge.visibility import Visibility

    an_assignable_agent(stored)
    an_assignable_agent(stored, "sales_desk", level=Visibility.DEPARTMENT, department="sales")
    digest = added_waiting(client, with_examples(REACHED))

    reader = post(client, "u_narrow", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "company_desk"})
    nowhere = post(client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "nobody_desk"})
    hidden = post(client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "sales_desk"})

    assert (reader.status_code, nowhere.status_code, hidden.status_code) == (404, 404, 404)
    assert reader.json()["message"] == nowhere.json()["message"] == hidden.json()["message"]
    assert stored.library.rehearsed == []


def test_the_review_pane_shows_the_examples_the_newest_rehearsal_and_whether_to_rehearse(
    client: TestClient, stored: Stored
) -> None:
    """The version's view carries its examples, the newest rehearsal of it with its limit, and
    `rehearsable` for a reviewer while it waits; a reader the body is not disclosed to sees none
    of them. Delete this and the page cannot show what approval is waiting for."""
    from tests.unit.test_skill_export import _headers

    an_assignable_agent(stored)
    digest = added_waiting(client, with_examples(REACHED))

    def mine(pid: str) -> dict[str, object]:
        page = client.get(SKILLS, headers=_headers(pid)).json()
        return next(one for one in page["library"] if one["digest"] == digest)

    before = mine("u_admin")
    post(client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"agent_id": "company_desk"})
    after, narrow = mine("u_admin"), mine("u_narrow")

    assert before["examples"] == [
        {"task": "Is example.com due for renewal this month", "expects": ["crm.read_client"]}
    ]
    assert (before["rehearsal"], before["rehearsable"]) == (None, True)
    rehearsal = after["rehearsal"]
    assert isinstance(rehearsal, dict)
    assert rehearsal["passed"] is True
    assert rehearsal["limit"] == A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER
    assert (narrow["examples"], narrow["rehearsal"], narrow["rehearsable"]) == ([], None, False)


# ------------------------------------------------------------------ on PostgreSQL


@pytest.mark.needs_db
def test_on_a_real_database_a_rehearsal_is_a_row_and_an_entry_that_names_no_task() -> None:
    """The rehearsal as the application role: one row read back as the rehearsal it records, and
    one `skill` entry with the change `rehearsed`, the kind and whether it passed, and never an
    example's words; a row in somebody else's name is refused. Delete this and a rehearsal can be
    recorded as somebody else, or carry the author's prose into the ledger."""
    import psycopg

    from brain.ops.skill_store import StoredSkills
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head
    from tests.unit.test_suspension_store import app_engine

    waiting = added(
        read_package("SKILL.md", with_examples(REACHED).encode("utf-8")), by="u_admin", at=NOW
    )
    examples = examples_of(waiting.imported.skill)
    made = Rehearsal(
        digest=waiting.digest,
        kind=RehearsalKind.REACH,
        outcomes=rehearse_reach(examples, ("crm.read_client",)),
        rehearsed_by="u_admin",
        agent_id="company_desk",
    )
    with at_head("brain_skill_rehearsal") as url:

        async def work() -> tuple[Rehearsal, ...]:
            engine = app_engine(url)
            try:
                store = StoredSkills(make_session_factory(engine))
                await store.add(waiting, ent_hash="0" * 32, trace_id="t-add")
                await store.rehearse(made, ent_hash="1" * 32, trace_id="t-rehearse")
                return (await store.rehearsals([waiting.digest]))[waiting.digest]
            finally:
                await engine.dispose()

        (read,) = asyncio.run(work())
        entries = sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry "
            "WHERE action = 'skill' AND details->>'change' = 'rehearsed'",
        )
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config('app.principal_id', 'u_admin', false)")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO agent.skill_rehearsal (digest, kind, agent_id, passed, outcomes,"
                    " rehearsed_by) VALUES (%s, 'reach', 'company_desk', true, '[]', 'u_other')",
                    (waiting.digest,),
                )

    assert (read.outcomes, read.passed, read.rehearsed_by) == (made.outcomes, True, "u_admin")
    ((actor, details),) = entries
    assert actor == "u_admin"
    assert details == {
        "change": "rehearsed",
        "digest": waiting.digest,
        "kind": "reach",
        "passed": True,
    }
    assert "renewal" not in str(details)
