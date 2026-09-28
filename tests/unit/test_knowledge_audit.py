"""Every write of a knowledge item appends a ledger entry, and the Audit screen's reader finds it.

The entry is written by `0115`'s trigger on `know.item`, so what can be held without a server is
the trigger's own text and the shape of what it writes: the action and subject kind the ledger
accepts, the details the ledger's grammar admits, and nothing of the document itself. The entry is
then built in that shape from an item the text path really made and handed to `AuditView`, the
decision the Audit screen reads through. Against a server the trigger fires for real in
`tests/unit/test_knowledge_upload_db.py`.

Task ids: M7.6.3, M7.6.1
"""

from __future__ import annotations

import importlib.util
import re
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from brain.audit.ledger import IDENTIFIER, SUBJECT_KINDS, AuditAction, AuditChain
from brain.audit.view import AuditView
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.ingest import MediaType, admit_upload
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
from brain.knowledge.visibility import KnowledgeVisibility
from tests.fixtures.documents import LINE

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
KIND_MIGRATION = MIGRATION / "0115_knowledge_item_kind.py"

AT = datetime(2999, 1, 1, tzinfo=UTC)
UPLOADER = "u_uploader"
TITLE = "Tealwhisper handover"
BODY = "Sign the TEALSECRET list before leaving."


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0115_audit", KIND_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def an_upload() -> KnowledgeItem:
    content = LINE.join([f"# {TITLE}", "", BODY]).encode()
    upload = admit_upload(
        filename=f"{TITLE}.md", declared_type=MediaType.MARKDOWN.value, content=content
    )
    read = read_for_text_path(
        ReceivedUpload(upload=upload, body=content),
        kind=KnowledgeKind.SOP,
        placement=KnowledgeVisibility.of_department("web", owner_id=UPLOADER),
        owner_id=UPLOADER,
    )
    assert isinstance(read, ReadUpload)
    return read.item


def entry_details(item: KnowledgeItem, *, change: str = "added") -> dict[str, object]:
    """The details `know.record_item` builds for this item, key for key, nulls stripped."""
    built: dict[str, object | None] = {
        "change": change,
        "source": "knowledge_item",
        "kind": None if item.kind is None else item.kind.value,
        "level": item.visibility.level.value,
        "department": item.visibility.department or None,
        "state": item.state.value,
    }
    return {key: value for key, value in built.items() if value is not None}


def reader(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_auditor",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def test_the_trigger_records_the_item_its_kind_and_place_and_never_its_title_or_text() -> None:
    """Delete this and the trigger can grow a `title` or a column of the text into the ledger,
    which every auditor reads whatever their reach over the document, or drop the kind and the
    department the owner asked every upload to be audited with."""
    module = migration()
    body = module.CREATE_AUDIT_FUNCTION
    built = re.findall(r"'([a-z_]+)', (?:NEW\.[a-z_]+|'[a-z_]+')", body)

    assert tuple(dict.fromkeys(built)) == (*module.AUDIT_DETAILS, "actor")
    assert "NEW.title" not in body and "body" not in body
    assert "current_setting('brain.ent_hash'" in body
    assert "AFTER INSERT OR UPDATE ON know.item" in module.AUDIT_TRIGGER


def test_the_subject_and_action_are_ones_the_ledger_accepts_for_the_longest_item_id() -> None:
    """Delete this and a long item id makes a subject the ledger's check refuses, and the check
    refusing it inside the trigger fails the upload itself."""
    module = migration()
    kind, _, prefix = module.AUDIT_SUBJECT_PREFIX.partition(":")

    assert AuditAction(module.AUDIT_ACTION) is AuditAction.SETTING
    assert kind in SUBJECT_KINDS
    assert re.match(IDENTIFIER, prefix + "x" * module.AUDIT_ID_CHARS)
    assert not re.match(IDENTIFIER, prefix + "x" * (module.AUDIT_ID_CHARS + 1))
    assert re.match(IDENTIFIER, prefix + "0" * 64)


def test_the_audit_screens_reader_finds_an_upload_and_it_names_no_word_of_the_document() -> None:
    """**The entry as the Audit screen reads it.** Built in the trigger's shape from an item the
    text path made, it constructs under the ledger's details grammar, `AuditView` shows it to a
    reader holding `read:audit.setting`, which every first administrator holds, and nothing on it
    is the title or the text. A reader without the capability is shown nothing.

    Delete this and the trigger's details can stop constructing as an entry, which the Audit route
    drops with a log line, so every upload would vanish from the screen that is meant to show it."""
    item = an_upload()
    module = migration()
    chain = AuditChain()
    entry = chain.append(
        action=AuditAction(module.AUDIT_ACTION),
        actor_id=UPLOADER,
        subject=module.AUDIT_SUBJECT_PREFIX + item.item_id,
        ent_hash="a" * 32,
        trace_id="t-upload",
        at=AT,
        details=entry_details(item),
    )

    assert entry.details == {
        "change": "added",
        "source": "knowledge_item",
        "kind": "sop",
        "level": "department",
        "department": "web",
        "state": "published",
    }
    seen = AuditView([entry], reader=reader("read:audit.setting"), now=AT).page()
    unseen = AuditView([entry], reader=reader("read:audit.grant"), now=AT).page()
    assert [(row.subject_kind, row.subject_id, row.actor_id) for row in seen.rows] == [
        ("setting", f"knowledge_item.{item.item_id}", UPLOADER)
    ]
    assert seen.rows[0].details == entry.details
    assert unseen.rows == ()
    shown = repr(seen.rows[0])
    assert "Tealwhisper" not in shown and "TEALSECRET" not in shown
