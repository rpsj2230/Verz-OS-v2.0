"""What a person pastes from the old system, checked by the migration package and kept nowhere.

Driven through the real application with the migration route's own people, switch and stand-in for
the saved register, so the carry route compares the export with a register read back the way the
migration route reads it. Every refusal has a sibling that works.

The dates are 2019 and 2999 for the reason CLAUDE.md records.

Task ids: M37.1.2.1, M37.1.2.2, M37.1.2.3, M37.1.2.4, M37.2.2.2, M37.2.2.4, M37.2.2.5
Task ids: M37.2.3.4, M37.2.4.2, M37.2.4.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.migration_routes import MIGRATION_AUTHORITY
from brain.ops.features import MIGRATION_WORKSPACE
from brain.routers import ROUTERS
from brain.tables.migration_record import RecordKind
from tests.fixtures.console_http import Stub, console_client, headers, post
from tests.fixtures.setting_rows import SettingRows
from tests.unit.test_migration_routes import BASE, GRANTS, Records, a_register, held

PATHS = ("/skills/convert", "/carry", "/learning", "/audience")
BODIES: dict[str, dict[str, Any]] = {
    "/skills/convert": {"skills": []},
    "/carry": {},
    "/learning": {"memories": []},
    "/audience": {"agents": [], "mapping": {}, "owner_id": "u_example"},
}


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def records() -> Records:
    return Records()


@pytest.fixture
def served(settings: SettingRows, records: Records) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, records.answer])
        yield client, stub


@pytest.fixture
def switched_on(settings: SettingRows) -> None:
    settings.hold(MIGRATION_WORKSPACE.key, True, value_type="boolean")


def ask(client: TestClient, path: str, body: dict[str, Any], pid: str = "u_admin") -> Any:
    return post(client, pid, f"{BASE}{path}", body)


def an_agreed_register() -> dict[str, Any]:
    return a_register(
        surveyed=["knowledge", "prompt", "tool", "conversation"],
        items=[
            {
                "item_id": "k1",
                "holding": "knowledge",
                "name": "Price list",
                "permissions": ["view"],
            },
            {"item_id": "c1", "holding": "conversation", "name": "A chat"},
        ],
        decisions=[
            {"item_id": "k1", "disposition": "migrate", "because": "It is the company's data"},
            {"item_id": "c1", "disposition": "retire", "because": "History is archived"},
        ],
    )


def test_the_router_is_mounted_by_the_application() -> None:
    """Delete this and the routes can be written, tested and never served."""
    served_paths = {getattr(one, "path", "") for router in ROUTERS for one in router.routes}
    assert {f"{BASE}{path}" for path in PATHS} <= served_paths


# ------------------------------------------------------------------------------ authority
@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
@pytest.mark.parametrize("path", PATHS)
def test_a_caller_without_the_authority_is_refused_before_the_database(pid: str, path: str) -> None:
    """The same refusal with a database and without one, naming no capability and reaching no
    store. Delete this and a department-scoped holder runs a migration for the install."""
    with console_client(GRANTS, database=False) as (client, _):
        without = ask(client, path, BODIES[path], pid)
    with console_client(GRANTS) as (client, stub):
        with_pool = ask(client, path, BODIES[path], pid)
    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert MIGRATION_AUTHORITY.value not in with_pool.json()["message"]
    assert stub.statements == []


@pytest.mark.parametrize("path", PATHS)
def test_every_route_is_refused_while_the_migration_switch_is_off(
    served: tuple[TestClient, Stub], path: str
) -> None:
    """The same switch as the migration route. Delete this and these routes work on an install
    that has not turned a migration on."""
    client, _ = served
    answer = ask(client, path, BODIES[path])
    assert answer.status_code == 404 and "switched off" in answer.text


# --------------------------------------------------------------------------------- skills
@pytest.mark.usefixtures("switched_on")
def test_a_router_preamble_is_stripped_to_a_draft_and_the_skill_is_still_listed_as_router_style(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the conversion is never offered, or a description already about the skill
    is rewritten."""
    client, _ = served
    answer = ask(
        client,
        "/skills/convert",
        {
            "skills": [
                {"name": "quote", "description": "Use the quote skill to price a job"},
                {"name": "plain", "description": "Prices a job from the list"},
            ]
        },
    ).json()
    assert answer["descriptions"] == [
        {"name": "quote", "proposed_description": "price a job"},
        {"name": "plain", "proposed_description": "Prices a job from the list"},
    ]
    assert len(answer["still_written_at_a_router"]) == 1
    assert answer["nothing_was_imported"] is True


@pytest.mark.usefixtures("switched_on")
def test_a_skill_not_invoked_in_ninety_days_or_never_is_listed_to_leave_behind(
    served: tuple[TestClient, Stub],
) -> None:
    """Both sentences. Delete this and retirement is never suggested, or a fresh skill is."""
    client, _ = served
    answer = ask(
        client,
        "/skills/convert",
        {
            "now": "2019-06-01T00:00:00+00:00",
            "skills": [
                {
                    "name": "old",
                    "description": "Does an old thing",
                    "last_invoked_at": "2019-01-01T00:00:00+00:00",
                },
                {
                    "name": "fresh",
                    "description": "Does a fresh thing",
                    "last_invoked_at": "2019-05-20T00:00:00+00:00",
                },
                {"name": "never", "description": "Never recorded"},
            ],
        },
    ).json()
    assert sorted(one.split(":")[0] for one in answer["to_retire"]) == ["never", "old"]


@pytest.mark.usefixtures("switched_on")
def test_a_skill_with_no_real_task_run_through_it_and_one_whose_answer_changed_are_both_named(
    served: tuple[TestClient, Stub],
) -> None:
    """Parsing is not behaviour. Delete this and a clean-looking import hides both."""
    client, _ = served
    answer = ask(
        client,
        "/skills/convert",
        {
            "skills": [
                {"name": "a", "description": "A thing"},
                {"name": "b", "description": "B thing"},
            ],
            "checks": [
                {"skill_name": "a", "task": "price a job", "same_answer": False, "checked_by": "X"}
            ],
        },
    ).json()
    assert any(one.startswith("b:") for one in answer["unproven"])
    assert any("differently" in one for one in answer["unproven"])


@pytest.mark.usefixtures("switched_on")
def test_a_skill_with_a_blank_description_is_refused_in_the_packages_words(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a blank description is converted to a blank draft."""
    client, _ = served
    answer = ask(client, "/skills/convert", {"skills": [{"name": "a", "description": "   "}]})
    assert answer.status_code == 404 and "nothing to convert" in answer.text


# ---------------------------------------------------------------------------------- carry
EXPORT = {"item_id": "k1", "content_digest": "abc123"}


@pytest.mark.usefixtures("switched_on")
def test_without_a_saved_register_the_plan_is_made_and_the_comparison_says_why_it_is_not(
    served: tuple[TestClient, Stub],
) -> None:
    """The parts that need no register are answered either way. Delete this and a missing
    register hides the vectors that are discarded, or an export is judged against nothing."""
    client, _ = served
    answer = ask(
        client,
        "/carry",
        {
            "exports": [
                {**EXPORT, "vector_count": 4, "vector_width": 1536, "embedded_by": "old-model"}
            ],
            "seeds": [{"external_id": "e1", "name": "Acme Ltd", "source_record": "r1"}],
        },
    ).json()
    assert answer["reparse"] == [{"item_id": "k1", "content_digest": "abc123"}]
    assert answer["vectors_discarded"] == ["k1: 4 vector(s) from 'old-model', discarded"]
    assert answer["register_agreed"] is False and "no register has been saved" in answer["why"]
    assert answer["export_gaps"] == [] and answer["archive"] is None
    assert "vector" not in str(answer["reparse"])


@pytest.mark.usefixtures("switched_on")
def test_two_seeds_that_collapse_to_one_name_are_a_question_and_not_a_merge(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a collision is silently merged into one entity."""
    client, _ = served
    answer = ask(
        client,
        "/carry",
        {
            "seeds": [
                {"external_id": "e1", "name": "Acme Ltd", "source_record": "r1"},
                {"external_id": "e2", "name": "ACME  Ltd.", "source_record": "r2"},
            ]
        },
    ).json()
    assert len(answer["seed_findings"]) == 1 and "e1 and e2" in answer["seed_findings"][0]


@pytest.mark.usefixtures("switched_on")
def test_with_an_agreed_register_the_export_is_compared_in_both_directions_and_history_archived(
    served: tuple[TestClient, Stub], records: Records
) -> None:
    """Delete this and an item promised and not delivered, or one delivered that was retired,
    passes, or a conversation is left searchable."""
    client, _ = served
    records.rows.append(held(RecordKind.REGISTER, an_agreed_register()))
    clean = ask(
        client,
        "/carry",
        {
            "exports": [EXPORT],
            "conversations_kept": [],
        },
    ).json()
    assert clean["register_agreed"] is True, clean["why"]
    assert clean["export_gaps"] == []
    assert clean["archive"] == {"archived": ["c1"], "kept_as_artefacts": [], "searchable": []}
    wrong = ask(client, "/carry", {"exports": [{"item_id": "c1", "content_digest": "d"}]}).json()
    assert any(
        "k1: decided migrate and nothing was exported" in one for one in wrong["export_gaps"]
    )
    assert any("c1: exported and decided retire" in one for one in wrong["export_gaps"])


@pytest.mark.usefixtures("switched_on")
def test_a_conversation_kept_needs_a_name_and_a_reason_and_must_be_a_conversation(
    served: tuple[TestClient, Stub], records: Records
) -> None:
    """Delete this and a document is kept out of retrieval by a rule meant for conversations."""
    client, _ = served
    records.rows.append(held(RecordKind.REGISTER, an_agreed_register()))
    kept = ask(
        client,
        "/carry",
        {"conversations_kept": [{"item_id": "c1", "because": "A contract term", "stated_by": "X"}]},
    ).json()
    assert kept["archive"]["kept_as_artefacts"] == ["c1"] and kept["archive"]["searchable"] == []
    stranger = ask(
        client,
        "/carry",
        {"conversations_kept": [{"item_id": "k1", "because": "Why", "stated_by": "X"}]},
    )
    assert stranger.status_code == 404 and "not a conversation" in stranger.text


@pytest.mark.usefixtures("switched_on")
def test_a_register_not_yet_agreed_is_said_and_the_comparison_is_left_empty(
    served: tuple[TestClient, Stub], records: Records
) -> None:
    """Delete this and an export is checked against a register nobody agreed."""
    client, _ = served
    records.rows.append(held(RecordKind.REGISTER, a_register(decisions=[])))
    answer = ask(client, "/carry", {"exports": [EXPORT]}).json()
    assert answer["register_agreed"] is False
    assert "not agreed yet" in answer["why"] and answer["export_gaps"] == []


@pytest.mark.usefixtures("switched_on")
def test_an_export_with_vectors_and_no_record_of_what_made_them_is_refused(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a vector of unknown origin is kept as a fact about nothing."""
    client, _ = served
    answer = ask(client, "/carry", {"exports": [{**EXPORT, "vector_count": 3}]})
    assert answer.status_code == 404 and "no record of what produced them" in answer.text


# -------------------------------------------------------------------------------- learning
MEMORY = {"source_file": "memory/prefs.md", "text": "Likes short answers"}


def derivation(change: str, **more: Any) -> dict[str, Any]:
    return {
        "source_file": "memory/prefs.md",
        "change": change,
        "subject": "short answers",
        "derived_by": "A Person",
        "because": "The file says so",
        **more,
    }


@pytest.mark.usefixtures("switched_on")
def test_a_preference_is_re_derived_and_a_widening_is_refused_without_stopping_the_rest(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and one scope-widening conclusion carries across, or refuses the whole paste."""
    client, _ = served
    answer = ask(
        client,
        "/learning",
        {
            "memories": [MEMORY],
            "derivations": [
                derivation("preference"),
                derivation("scope_widening"),
                derivation("session_context"),
                derivation("fast_path_rule"),
            ],
        },
    ).json()
    assert [one["change"] for one in answer["derived"]] == ["preference"]
    assert len(answer["refused"]) == 3
    assert any("who may see what" in one["because"] for one in answer["refused"])
    assert answer["files_read"] == 1 and answer["readers"] == ["A Person"]
    assert "without the learning" in answer["note"]
    assert answer["nothing_was_filed"] is True


@pytest.mark.usefixtures("switched_on")
def test_a_derivation_from_a_file_not_handed_over_or_with_an_unknown_change_is_refused_by_name(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the note counts a file nobody exported, or an unknown change is a 500."""
    client, _ = served
    answer = ask(
        client,
        "/learning",
        {
            "memories": [MEMORY],
            "derivations": [
                derivation("preference", source_file="memory/other.md"),
                derivation("not_a_change"),
            ],
        },
    ).json()
    assert answer["derived"] == [] and len(answer["refused"]) == 2
    assert answer["files_read"] == 0


@pytest.mark.usefixtures("switched_on")
def test_a_file_two_people_drew_conclusions_from_is_named(served: tuple[TestClient, Stub]) -> None:
    """Delete this and one belief is counted twice as two."""
    client, _ = served
    answer = ask(
        client,
        "/learning",
        {
            "memories": [MEMORY],
            "derivations": [
                derivation("preference"),
                derivation("retrieval_boost", derived_by="Another Person"),
            ],
        },
    ).json()
    assert len(answer["derived_twice"]) == 1
    assert "A Person and Another Person" in answer["derived_twice"][0]


# -------------------------------------------------------------------------------- audience
@pytest.mark.usefixtures("switched_on")
def test_availability_is_mapped_by_the_mapping_given_and_an_unmapped_one_is_never_defaulted(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and an availability nobody mapped becomes the narrowest level in silence, or
    the widest."""
    client, _ = served
    answer = ask(
        client,
        "/audience",
        {
            "agents": [
                {"name": "helper", "availability": "everyone"},
                {"name": "secret", "availability": "private-ish"},
            ],
            "mapping": {"everyone": "company"},
            "owner_id": "u_example",
        },
    ).json()
    assert answer["audiences"] == [{"name": "helper", "level": "company"}]
    assert [one["subject"] for one in answer["unmapped"]] == ["secret"]
    assert "nothing says what that means here" in answer["unmapped"][0]["because"]
    assert answer["authority_is_not_decided_here"] is True


@pytest.mark.usefixtures("switched_on")
def test_a_level_this_system_does_not_have_is_refused_as_a_malformed_request(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a mapping to a level that does not exist reaches the package."""
    client, _ = served
    answer = ask(
        client,
        "/audience",
        {
            "agents": [{"name": "a", "availability": "x"}],
            "mapping": {"x": "world"},
            "owner_id": "u_example",
        },
    )
    assert answer.status_code == 422


def test_the_helpers_the_test_file_borrows_are_the_migration_routes_own() -> None:
    """Delete this and a rename in the migration route's tests breaks these silently."""
    assert headers("u_admin")
