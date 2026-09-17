"""The handover command: export every store in open formats, remove the install, certify it.

Over fakes of the database and the object store; the run on a scratch install is the proof.

Task ids: M41.2.6, M41.4.1
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import pytest

from brain.db import SCHEMAS
from brain.ops.handover import Handover, HandoverError, Reason, Residue
from brain.ops.handover_run import (
    CERTIFICATE,
    CERTIFICATE_TEXT,
    MANIFEST,
    SUMS,
    TEARDOWN,
    By,
    export,
    issue,
    plan,
    preview_steps,
    read_teardown,
    record,
    remove,
    verify,
)
from brain.ops.retention import BACKUP_RETENTION_DAYS, Store

# Far from any wall clock, so no fixture here expires.
AT = datetime(2031, 3, 4, 10, 0, tzinfo=UTC)
PREFIX = "tenant"


class FakeDatabase:
    def __init__(self) -> None:
        self.schemas: dict[str, dict[str, list[str]]] = {
            name: {"thing": [f"{name}-1", f"{name}-2"]} for name in SCHEMAS
        }
        self.schemas["obs"]["audit_ledger"] = ["granted", "refused", "changed"]
        self.connectors = ["drive", "mail"]

    def tables(self, schema: str) -> list[str]:
        return sorted(self.schemas.get(schema, {}))

    def copy_csv(self, schema: str, table: str, sink: BinaryIO) -> int:
        rows = self.schemas[schema][table]
        sink.write(("value\n" + "".join(f"{one}\n" for one in rows)).encode())
        return len(rows)

    def live_connectors(self) -> list[str]:
        return list(self.connectors)

    def schema_exists(self, schema: str) -> bool:
        return schema in self.schemas

    def drop_schema(self, schema: str) -> None:
        del self.schemas[schema]


class FakeObjects:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {
            "assets": {f"{PREFIX}/logo.png": b"png", "other/elsewhere.png": b"not ours"},
            "recordings": {f"{PREFIX}/run/1.webm": b"video"},
            "exports": {},
            "backups": {"2031-03-03.dump": b"dump"},
        }

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.buckets[bucket_name][key]

    def delete_object(self, bucket_name: str, key: str) -> None:
        del self.buckets[bucket_name][key]

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        return iter(sorted(k for k in self.buckets.get(bucket_name, {}) if k.startswith(prefix)))


def _handover() -> Handover:
    return Handover(
        handover_id="hand-7",
        reason=Reason.CONTRACT_ENDED,
        instructed_by="the client's board",
        instruction_reference="termination letter, clause 9",
        requested_at=AT,
    )


def _exported(
    tmp_path: Path, objects: FakeObjects | None = None
) -> tuple[FakeDatabase, FakeObjects]:
    database, store = FakeDatabase(), objects if objects is not None else FakeObjects()
    export(tmp_path, handover=_handover(), database=database, objects=store, prefix=PREFIX, now=AT)
    return database, store


def test_the_export_writes_every_schema_and_bucket_with_sums_a_company_can_check(
    tmp_path: Path,
) -> None:
    """The return is the one thing a leaving company keeps. Delete this and a schema, the audit
    ledger or a bucket can drop out of the export, or `SHA256SUMS` can name bytes that are not the
    file's, and nothing about the directory looks wrong."""
    _exported(tmp_path)
    manifest = json.loads((tmp_path / MANIFEST).read_text(encoding="utf-8"))
    sources = {one["source"] for one in manifest["files"]}
    assert {f"{name}.thing" for name in SCHEMAS} <= sources
    assert "obs.audit_ledger" in sources
    assert f"assets:{PREFIX}/logo.png" in sources
    assert "backups:2031-03-03.dump" in sources
    assert "assets:other/elsewhere.png" not in sources, "another install's object was taken"
    for line in (tmp_path / SUMS).read_text(encoding="utf-8").splitlines():
        digest, path = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() == digest
    assert {one["store"] for one in manifest["stores"]} == {one.value for one in Store}
    assert all(one["reached"] for one in manifest["stores"])
    assert manifest["connectors"] == ["drive", "mail"]
    audit = next(one for one in manifest["files"] if one["source"] == "obs.audit_ledger")
    assert audit["rows"] == 3
    assert verify(tmp_path) == ()


def test_a_file_changed_after_export_is_reported_by_verify(tmp_path: Path) -> None:
    """Delete this and `verify` can answer intact over an altered export, which is the check the
    teardown relies on before it removes the only other copy."""
    _exported(tmp_path)
    (tmp_path / "data/db/obs/audit_ledger.csv").write_text("value\nforged\n", encoding="utf-8")
    assert verify(tmp_path) == ("data/db/obs/audit_ledger.csv does not match its recorded digest",)


def test_a_second_export_into_the_same_directory_is_refused(tmp_path: Path) -> None:
    """Delete this and two moments mix in one manifest, so the return describes neither."""
    _exported(tmp_path)
    with pytest.raises(HandoverError, match="already holds an export"):
        _exported(tmp_path)


def test_an_object_key_that_climbs_out_of_the_directory_is_refused(tmp_path: Path) -> None:
    """Delete this and an object named `../../x` is written outside the export directory."""
    objects = FakeObjects()
    objects.buckets["assets"][f"{PREFIX}/../../escape"] = b"x"
    with pytest.raises(HandoverError, match="not a relative path"):
        _exported(tmp_path, objects)


def test_without_the_object_store_the_plan_refuses_to_tear_anything_down(tmp_path: Path) -> None:
    """Delete this and an install whose buckets could not be read is torn down anyway, removing
    files the company never received."""
    database = FakeDatabase()
    returned = export(
        tmp_path, handover=_handover(), database=database, objects=None, prefix=PREFIX, now=AT
    )
    assert set(returned.unreached()) == {
        Store.RECORDING,
        Store.ATTACHMENT,
        Store.EXPORT,
        Store.BACKUP,
    }
    with pytest.raises(HandoverError, match="could not be read"):
        plan(tmp_path, realm="acme")
    assert not (tmp_path / TEARDOWN).exists()


def test_a_plan_is_refused_over_an_export_that_no_longer_verifies(tmp_path: Path) -> None:
    """Delete this and a teardown can be planned from an export somebody altered."""
    _exported(tmp_path)
    (tmp_path / "data/db/auth/thing.csv").write_bytes(b"changed")
    with pytest.raises(HandoverError, match="does not verify"):
        plan(tmp_path, realm="acme")


def test_remove_needs_the_handover_id_typed_back_and_removes_nothing_without_it(
    tmp_path: Path,
) -> None:
    """The one destructive step. Delete this and a mistyped command drops every schema."""
    database, objects = _exported(tmp_path)
    plan(tmp_path, realm="acme")
    with pytest.raises(HandoverError, match="does not match"):
        remove(
            tmp_path, confirm="hand-8", database=database, objects=objects, prefix=PREFIX, now=AT
        )
    assert set(database.schemas) == set(SCHEMAS)


def test_remove_refuses_once_the_export_has_changed_since_it_was_planned(tmp_path: Path) -> None:
    """Delete this and a file altered between plan and remove goes unnoticed, and the teardown
    removes the only copy the company's altered export was made from."""
    database, objects = _exported(tmp_path)
    plan(tmp_path, realm="acme")
    (tmp_path / "data/db/know/thing.csv").write_bytes(b"changed")
    with pytest.raises(HandoverError, match="no longer verifies"):
        remove(
            tmp_path, confirm="hand-7", database=database, objects=objects, prefix=PREFIX, now=AT
        )
    assert set(database.schemas) == set(SCHEMAS)


def test_the_whole_handover_ends_in_a_certificate_naming_the_backup_expiry(tmp_path: Path) -> None:
    """The end the command is for. Delete this and remove can leave a schema or this install's
    objects behind, touch another install's objects, or certify with an operator step open, or the
    certificate can state a backup date that is not the retention policy's."""
    database, objects = _exported(tmp_path)
    steps = plan(tmp_path, realm="acme")
    assert {one.what for one in steps} == set(Store) | set(Residue)
    finished = AT + timedelta(hours=2)
    still = remove(
        tmp_path, confirm="hand-7", database=database, objects=objects, prefix=PREFIX, now=finished
    )
    assert database.schemas == {}
    assert objects.buckets["assets"] == {"other/elsewhere.png": b"not ours"}
    assert objects.buckets["backups"] == {}
    operator = {one.what.value for one in steps if one.by is By.OPERATOR}
    assert set(still) == operator
    with pytest.raises(HandoverError, match="could not be removed"):
        issue(tmp_path)
    for what in sorted(operator):
        record(tmp_path, what=what, now=finished)
    certificate = issue(tmp_path)
    assert certificate.recoverable_from_backup_until == finished + timedelta(
        days=BACKUP_RETENTION_DAYS
    )
    document = json.loads((tmp_path / CERTIFICATE).read_text(encoding="utf-8"))
    assert document["recoverable_from_backup_until"] == (
        certificate.recoverable_from_backup_until.isoformat()
    )
    assert document["returned_items"] == certificate.returned_items > 0
    expiry = certificate.recoverable_from_backup_until.date().isoformat()
    assert f"expires on {expiry}" in (tmp_path / CERTIFICATE_TEXT).read_text(encoding="utf-8")


def test_a_command_step_cannot_be_recorded_by_hand(tmp_path: Path) -> None:
    """Delete this and an operator can mark a schema dropped that was never dropped, and the
    certificate says the data is gone."""
    _exported(tmp_path)
    plan(tmp_path, realm="acme")
    with pytest.raises(HandoverError, match="run remove instead"):
        record(tmp_path, what=Store.KNOWLEDGE.value, now=AT)
    record(tmp_path, what=Residue.IDENTITY_REALM.value, now=AT)
    done = {one["what"] for one in read_teardown(tmp_path)["steps"] if one["done"]}
    assert done == {Residue.IDENTITY_REALM.value}


def test_the_operator_steps_name_this_installs_realm_and_connectors(tmp_path: Path) -> None:
    """Delete this and the realm step names a realm other than the install's, or the connector
    step leaves the operator to guess which grants to revoke."""
    _exported(tmp_path)
    steps = {one.what: one for one in plan(tmp_path, realm="acme")}
    assert steps[Residue.IDENTITY_REALM].how.endswith("realms/acme (Keycloak admin)")
    assert steps[Residue.CONNECTOR_AUTHORISATIONS].how.endswith(": drive, mail")
    assert steps[Residue.CHAT_APP].by is By.OPERATOR


def test_the_preview_shown_on_the_settings_screen_covers_everything() -> None:
    """Delete this and the Settings screen can describe a handover that leaves a store or an
    install part out."""
    steps = preview_steps(realm="acme")
    assert {one.what for one in steps} == set(Store) | set(Residue)
    assert len(steps) == len(Store) + len(Residue)


def test_the_procedure_names_every_subcommand_and_every_part_the_operator_removes() -> None:
    """Delete this and docs/install/handover.md can drift from the command: a step renamed, or a
    part added to the teardown that the procedure never tells the operator to remove."""
    page = (Path(__file__).parents[2] / "docs/install/handover.md").read_text(encoding="utf-8")
    for step in ("export", "verify", "plan", "remove", "record", "certify"):
        assert f"python -m brain.ops.handover_run {step} " in page, step
    operator = {one.what.value for one in preview_steps(realm="r") if one.by is By.OPERATOR}
    for part in operator:
        assert f"record ... {part}`" in page or f"record /srv/handover {part}`" in page, part
