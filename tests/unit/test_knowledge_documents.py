"""The rules under the console's Knowledge module that need no server: what a ledger entry about a
document says happened, where its entries are filed, and what the list may be narrowed by.

The routes themselves, over a real database, are `tests/unit/test_knowledge_documents_db.py`'s.

Task ids: M27.15.40
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from brain.knowledge.lifecycle import HistoryEvent, event_of
from brain.knowledge.lifecycle_store import (
    ITEM_SUBJECT_ID_CHARS,
    ITEM_SUBJECT_PREFIX,
    item_subject,
)
from brain.knowledge_lifecycle_routes import (
    DOCUMENTS,
    REVIEW_DUE,
    REVIEW_NOT_DUE,
    DocumentView,
)
from brain.listing import ListAsked

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{name}", MIGRATION / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(change: str, *, changed: str = "", state: str = "published", level: str = "department"):
    """Details as `0120`'s trigger writes them for one write of `know.item`."""
    details: dict[str, object] = {
        "change": change,
        "source": "knowledge_item",
        "kind": "sop",
        "level": level,
        "department": "web",
        "state": state,
    }
    if changed:
        details["changed"] = changed
    return details


def test_each_ledger_entry_about_a_document_reads_as_the_act_that_wrote_it() -> None:
    """The entries the lifecycle's acts write, as the trigger spells them, read as those acts: an
    insert is added, the three verification columns are verified, the steward's column is a
    hand-over, a move to superseded or archived is that, a widening to company is company-wide, and
    a review date alone is a new date. The link a newer version keeps says nothing.

    Delete this and the history can call a verification a new review date, which would list it to
    a reader the verifier's name is withheld from, or call a hand-over a verification."""
    assert event_of(entry("added")) is HistoryEvent.ADDED
    assert event_of(entry("replaced", changed="review_by,verified_at,verified_by")) is (
        HistoryEvent.VERIFIED
    )
    assert event_of(entry("replaced", changed="owner_id")) is HistoryEvent.HANDED_OVER
    assert event_of(entry("replaced", changed="state", state="superseded")) is (
        HistoryEvent.REPLACED
    )
    assert event_of(entry("replaced", changed="state", state="archived")) is HistoryEvent.ARCHIVED
    assert event_of(entry("replaced", changed="review_by,visibility", level="company")) is (
        HistoryEvent.COMPANY_WIDE
    )
    assert event_of(entry("replaced", changed="review_by")) is HistoryEvent.REVIEW_DATE
    assert event_of(entry("replaced", changed="supersedes")) is None
    assert event_of(entry("replaced")) is None


def test_a_visibility_change_that_does_not_reach_the_company_is_not_called_company_wide() -> None:
    """A widening is company-wide only when the row stands at company afterwards. Delete this and
    a department move would be drawn as the gated promotion it is not."""
    assert event_of(entry("replaced", changed="visibility", level="department")) is None


def test_a_documents_entries_are_filed_where_the_trigger_files_them() -> None:
    """The subject prefix and the longest id kept as itself are `0120`'s, and a longer id is its
    sha256. Delete this and a history reads a subject nothing writes, and says a document has none."""
    shipped = migration("0120_knowledge_lifecycle.py")
    assert shipped.ITEM_SUBJECT_PREFIX == ITEM_SUBJECT_PREFIX
    assert shipped.ITEM_ID_CHARS == ITEM_SUBJECT_ID_CHARS
    short = "upload." + "a" * (ITEM_SUBJECT_ID_CHARS - len("upload."))
    assert item_subject(short) == f"{ITEM_SUBJECT_PREFIX}{short}"
    longer = short + "b"
    digest = hashlib.sha256(longer.encode("utf-8")).hexdigest()
    assert item_subject(longer) == f"{ITEM_SUBJECT_PREFIX}{digest}"


def a_row(item_id: str, *, due: bool, department: str | None = "web") -> DocumentView:
    return DocumentView(
        item_id=item_id,
        title=item_id,
        kind="sop",
        kind_label="SOP",
        level="department",
        department=department,
        steward_id="u_somebody",
        state="published",
        verification="due" if due else "verified",
        review_by=datetime(2999, 1, 1, tzinfo=UTC),
        due=due,
        steward_name="Somebody",
    )


def test_the_list_filters_by_department_visibility_state_type_and_review_and_nothing_withheld() -> (
    None
):
    """The list's filters are the five SCREEN 7 draws, each over a field the row sends, and the
    Review due filter matches a due row and not a current one. Delete this and a filter can match a
    value the row withholds, one guess at a time."""
    assert set(DOCUMENTS.filters()) == {"department", "level", "state", "kind", "review"}
    assert set(DOCUMENTS.searches()) == {"title", "steward"}
    rows = [a_row("upload.due", due=True), a_row("upload.fine", due=False)]
    due = DOCUMENTS.page(rows, ListAsked(filters=(f"review:{REVIEW_DUE}",)), reader="u_x")
    fine = DOCUMENTS.page(rows, ListAsked(filters=(f"review:{REVIEW_NOT_DUE}",)), reader="u_x")
    assert [one.item_id for one in due.items] == ["upload.due"]
    assert [one.item_id for one in fine.items] == ["upload.fine"]
