"""A personal project's tables hold what the migration says they do.

Task ids: M40.7.7
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from brain.tables.project import KINDS, NAME_CHARS, PRINCIPAL_ID_CHARS, REF_CHARS

MIGRATION = Path(__file__).parents[2] / "migrations" / "versions" / "0232_personal_project.py"


def _migration() -> object:
    spec = importlib.util.spec_from_file_location("m0232", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_model_and_the_migration_agree_on_widths_and_kinds() -> None:
    """The model and the migration copy the same widths and the same two kinds. Delete this and a
    width changed in one is a column the other cannot hold, or a kind the database refuses."""
    module = _migration()
    assert module.KINDS == KINDS  # type: ignore[attr-defined]
    assert (module.NAME_CHARS, module.REF_CHARS) == (NAME_CHARS, REF_CHARS)  # type: ignore[attr-defined]
    assert module.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS  # type: ignore[attr-defined]


def test_every_policy_asks_the_person_the_session_names_and_nothing_can_delete_a_project() -> None:
    """No policy is open to everybody, an item's policies ask it of its project, and the grants
    delete items and never projects. Delete this and a project becomes readable by anybody, or a
    person's whole project can be deleted out from under what refers to it."""
    module = _migration()
    policies = " ".join(module.RLS)  # type: ignore[attr-defined]
    assert "USING (true)" not in policies and "WITH CHECK (true)" not in policies
    assert policies.count("app.principal_id") >= 6
    assert not any(
        "DELETE" in grant and "agent.project " in grant + " "
        for grant in module.GRANTS  # type: ignore[attr-defined]
    )
