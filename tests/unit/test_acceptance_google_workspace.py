"""The Google Workspace check: registered, passing on a real schema, and failing where it proves.

The database half builds PostgreSQL to head and runs the check as the install runs it: a made-up
Workspace connected for mail and calendar, a person consenting for their own account through the
consent routes' bodies, and their question read by the passage reader the answer lane is handed.
Then it is run against the product broken where it proves, and each break fails with its own
sentence. Every table the check writes holds afterwards what it held before.

Task ids: M11.7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_google_workspace"
NAME = "a_persons_own_workspace_is_read_with_their_token_for_them_alone"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_workspace_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.6",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_workspace_checks_are_listed_in_their_page_order() -> None:
    """One check, the Workspace from a person's consent to their own passages. Delete this and a
    check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_persons_own_workspace_is_read_for_them_alone() -> None:
    """**The check as the install runs it, against PostgreSQL at head.** It passes, and the
    connections, the consents' effects and the ledger hold what they held before. Delete this and
    the path from a person's consent to their own passages can break with nothing on the owner's
    install saying so."""
    with at_head("brain_acceptance_workspace") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("every_scope", "the consent asked Google for a scope of a service not chosen"),
        ("anyone", "a person who has not connected their account was read something"),
        ("every_service", "a service the connection did not choose was called"),
    ],
)
def test_the_workspace_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: a consent asking for every scope whatever was chosen, a
    question read with the first consent held rather than the asker's own, and every service read
    whatever was chosen. Each fails the check with its own sentence. Delete this and the check can
    pass with any of them gone."""
    import brain.connector_routes as connector_routes
    import brain.ops.google_workspace_live as workspace_live
    from brain.connectors import google_workspace as gws

    if broken == "every_scope":
        monkeypatch.setattr(connector_routes, "asked_scopes", lambda consent, settings: None)
    elif broken == "anyone":
        access = workspace_live.personal_access
        first: dict[str, Any] = {}

        def somebodys(consent: Any, **kwargs: Any) -> Any:
            # The first person's consent, kept and used for whoever asks next.
            first.setdefault("principal_id", kwargs["principal_id"])
            return access(consent, **{**kwargs, "principal_id": first["principal_id"]})

        monkeypatch.setattr(workspace_live, "personal_access", somebodys)
    else:
        every = tuple(gws.Service)

        def all_of_them(settings: Any) -> Any:
            made = gws.WorkspaceConnection(
                client_id=settings[gws.CLIENT_ID_SETTING].strip(),
                services=every,
                department=settings[gws.DEPARTMENT_SETTING].strip(),
            )
            return made

        monkeypatch.setattr(gws.WorkspaceConnection, "from_settings", all_of_them)
    with at_head(f"brain_acceptance_workspace_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_workspace_check_steps_aside_where_the_install_has_it_connected() -> None:
    """The check stands its own Workspace up, so on an install with one connected it does not,
    rather than moving the real connection aside. Delete this and the check could disturb the
    owner's own Workspace connection."""
    from brain.ops.acceptance_checks_google_workspace import WORKSPACE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_workspace_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('google_workspace', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, WORKSPACE_IS_CONNECTED_HERE_ALREADY)
