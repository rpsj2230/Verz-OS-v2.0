"""The kind a knowledge item carries: a closed list, held equal where it is stored, and two rules.

Every test here runs without a server. What the database does with the column is
`tests/unit/test_knowledge_upload_db.py`'s, against a database migrated to head.

Task ids: M7.6.1
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import CheckConstraint, String, Table

from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.item_store import row_values
from brain.knowledge.kinds import (
    A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS,
    AN_APPROVED_SOLUTION_IS_APPROVED_AND_NEVER_UPLOADED,
    KIND_CHARS,
    KIND_LABELS,
    KIND_ORDER,
    KindError,
    KnowledgeKind,
    assert_kind_holds,
    assert_uploadable,
    uploadable_kinds,
)
from brain.knowledge.visibility import KnowledgeVisibility
from brain.tables.knowledge import KnowledgeItemRow

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
KIND_MIGRATION = MIGRATION / "0115_knowledge_item_kind.py"

#: The owner's closed list, in his words and his order, written out so that a kind renamed or
#: dropped in the enum is a failure here rather than a narrowing nobody decided.
THE_OWNERS_LIST: tuple[str, ...] = (
    "SOP",
    "Policy",
    "FAQ",
    "Pricing note",
    "Service information",
    "Service package",
    "Brand guidelines",
    "Company rule",
    "Best practice",
    "Template",
    "Training material",
    "Approved solution",
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0115_kinds", KIND_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def an_item(kind: KnowledgeKind | None) -> KnowledgeItem:
    return KnowledgeItem(
        item_id="upload.handover",
        content="A site is handed over after the checklist is signed.",
        title="Handover",
        visibility=KnowledgeVisibility.of_department("web", owner_id="u_owner"),
        owner_id="u_owner",
        state=KnowledgeState.PUBLISHED,
        kind=kind,
    )


def test_the_closed_list_is_the_owners_twelve_in_his_order() -> None:
    """Delete this and a kind can be renamed, dropped or reordered in the enum, and the list a
    person picks from stops being the one the requirement names, with every other test green."""
    assert [KIND_LABELS[kind] for kind in KIND_ORDER] == list(THE_OWNERS_LIST)
    assert set(KIND_ORDER) == set(KnowledgeKind)
    assert len(KIND_ORDER) == len(set(KIND_ORDER))
    assert max(len(kind.value) for kind in KnowledgeKind) <= KIND_CHARS


def test_the_migration_the_model_and_the_enum_name_the_same_kinds() -> None:
    """The check `0115` writes, the check the model declares and the enum are one list.

    Delete this and a kind added to the enum is refused by the database at the first upload
    that names it, after every Python test passed, or a kind dropped from it stays writable."""
    module = migration()
    table = KnowledgeItemRow.__table__
    assert isinstance(table, Table)
    declared = {
        str(one.sqltext)
        for one in table.constraints
        if isinstance(one, CheckConstraint) and one.name == "ck_item_kind"
    }
    column = table.c.kind

    assert tuple(sorted(kind.value for kind in KnowledgeKind)) == module.KINDS
    assert declared == {module.KIND_CHECK}
    assert module.KIND_CHARS == KIND_CHARS
    assert isinstance(column.type, String) and column.type.length == KIND_CHARS
    assert column.nullable


def test_an_item_is_stored_with_the_kind_it_was_added_as() -> None:
    """Delete this and the row can drop the kind the person chose, and the library and every
    narrowed search then treat the item as one added before kinds existed."""
    assert row_values(an_item(KnowledgeKind.SOP))["kind"] == "sop"
    assert row_values(an_item(None))["kind"] is None


def test_an_approved_solution_cannot_be_uploaded_and_every_other_kind_can() -> None:
    """Delete this and an upload can carry the approved-solution label with no approval behind
    it; the positive half proves the refusal is about that kind and not about uploading."""
    with pytest.raises(KindError) as refused:
        assert_uploadable(KnowledgeKind.APPROVED_SOLUTION)
    assert AN_APPROVED_SOLUTION_IS_APPROVED_AND_NEVER_UPLOADED in str(refused.value)

    offered = uploadable_kinds()
    assert KnowledgeKind.APPROVED_SOLUTION not in offered
    assert offered == tuple(
        kind for kind in KIND_ORDER if kind is not KnowledgeKind.APPROVED_SOLUTION
    )
    for kind in offered:
        assert_uploadable(kind)


def test_a_pricing_note_holding_a_table_is_refused() -> None:
    """Delete this and a price table pasted into a note is indexed as text, readable by everybody
    the note reaches, with no column for the redactor to withhold cost or margin from."""
    with pytest.raises(KindError) as refused:
        assert_kind_holds(KnowledgeKind.PRICING_NOTE, holds_a_table=True, tables_are_visible=True)
    assert A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS in str(refused.value)


def test_a_pricing_note_in_a_format_whose_tables_cannot_be_seen_is_refused() -> None:
    """Delete this and a pricing note uploaded as a PDF passes the rule unread, because this path
    reads a PDF's tables as prose and would report that it found none."""
    with pytest.raises(KindError):
        assert_kind_holds(KnowledgeKind.PRICING_NOTE, holds_a_table=False, tables_are_visible=False)


def test_a_pricing_note_without_a_table_and_any_other_kind_with_one_are_accepted() -> None:
    """The positive cases. Delete this and both refusals above are satisfied by a rule refusing
    every pricing note, or every document holding a table."""
    assert_kind_holds(KnowledgeKind.PRICING_NOTE, holds_a_table=False, tables_are_visible=True)
    assert_kind_holds(KnowledgeKind.SOP, holds_a_table=True, tables_are_visible=True)
    assert_kind_holds(KnowledgeKind.SOP, holds_a_table=False, tables_are_visible=False)
