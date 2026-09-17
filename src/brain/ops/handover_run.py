"""A handover carried out: every store exported in open formats, the install removed, a certificate.

`brain.ops.handover` is the domain and reaches nothing: what a return must cover, that a teardown
is planned only from a complete return, and that a certificate is refused while anything is
outstanding. This module is the command an operator runs on the install, and it keeps those rules
by going through that module rather than restating them.

**Five steps, each one a subcommand, each one writing a file into one directory.**
`export` reads every schema in `brain.db.SCHEMAS` as CSV inside one repeatable-read transaction
(so the audit ledger and the rows it describes are one moment) and every bucket under this
install's prefix as the files themselves, then writes `manifest.json` and a `SHA256SUMS` the
company can check with `sha256sum -c` and no software of ours. `verify` re-hashes. `plan` refuses
unless the return is complete and verifies, then writes `teardown.json`: one step per store and per
residue, each saying whether this command performs it or the operator does, and how. `remove`
performs the command's steps and needs the handover id typed back. `record` marks an operator step
done. `certify` issues the certificate only when every step is done.

**The operator's steps are steps, not a footnote.** The identity realm, the vault, the proxy route,
the containers, the environment file, connector authorisations and the chat app live outside the
database and outside any credential this process holds. Pretending to remove them from here would
make the certificate lie where `brain.ops.handover.A_DROPPED_DATABASE_IS_NOT_AN_UNINSTALL` says
it must not, so each is written with its command and `certify` waits for it.

Procedure: docs/install/handover.md. Task ids: M41.2.6, M41.4.1
"""

from __future__ import annotations

import argparse
import enum
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Final, Protocol

from brain.db import SCHEMAS
from brain.ops.handover import (
    Certificate,
    Handover,
    HandoverError,
    Reason,
    Removed,
    Residue,
    Return,
    assemble_return,
    certify,
    plan_teardown,
    teardown_order,
)
from brain.ops.retention import STORES, Store, facts_for
from brain.ops.storage import BUCKETS

MANIFEST: Final = "manifest.json"
SUMS: Final = "SHA256SUMS"
TEARDOWN: Final = "teardown.json"
CERTIFICATE: Final = "certificate.json"
CERTIFICATE_TEXT: Final = "certificate.txt"
#: Where the exported files go, relative to the handover directory.
DATA: Final = "data"


class By(enum.StrEnum):
    """Who removes one thing: this command, or the operator at a console this process cannot see."""

    COMMAND = "command"
    OPERATOR = "operator"


def _claimed_by_first(kind: str) -> dict[str, Store]:
    """Each schema or bucket attributed to the first store claiming it, in `Store` order.

    `obs` is claimed by the ledger, traces, payloads and the audit chain, which differ by retention
    and not by table. Counting its rows four times would make the return's total a lie, so a count
    goes to one store and the manifest lists every claimant beside the file.
    """
    owner: dict[str, Store] = {}
    for facts in STORES:
        for name in facts.schemas if kind == "schema" else facts.buckets:
            owner.setdefault(name, facts.store)
    return owner


SCHEMA_OWNER: Final = _claimed_by_first("schema")
BUCKET_OWNER: Final = _claimed_by_first("bucket")


def claimants(*, schema: str = "", bucket: str = "") -> list[str]:
    return [
        facts.store.value
        for facts in STORES
        if (schema and schema in facts.schemas) or (bucket and bucket in facts.buckets)
    ]


#: Stores with no schema and no bucket, and why they carry nothing to export.
DERIVED: Final[Mapping[Store, str]] = {
    Store.CACHE: "answers recomputed from the knowledge and records already exported",
    Store.INDEX: "embeddings sit in the know schema (INSTALL_VECTOR_STORE=postgres), exported",
}


# ------------------------------------------------------------------ what this command reaches
class Database(Protocol):
    """The database as the export and the teardown need it. `PsycopgDatabase` on an install."""

    def tables(self, schema: str) -> list[str]: ...

    def copy_csv(self, schema: str, table: str, sink: BinaryIO) -> int: ...

    def live_connectors(self) -> list[str]: ...

    def schema_exists(self, schema: str) -> bool: ...

    def drop_schema(self, schema: str) -> None: ...


class Objects(Protocol):
    """`brain.ops.storage.StorageBackend`, the three methods used here."""

    def get_object(self, bucket_name: str, key: str) -> bytes: ...

    def delete_object(self, bucket_name: str, key: str) -> None: ...

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]: ...


@dataclass(frozen=True)
class Exported:
    """One file written: where, its digest, and where it came from. Never its content."""

    path: str
    sha256: str
    size: int
    source: str
    rows: int | None
    stores: list[str]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_key(key: str) -> PurePosixPath:
    """An object key as a relative path, refusing one that would climb out of the directory."""
    parts = PurePosixPath(key).parts
    if not parts or key.startswith("/") or any(part in ("", ".", "..") for part in parts):
        msg = f"object key {key!r} is not a relative path and would be written outside the export"
        raise HandoverError(msg)
    return PurePosixPath(*parts)


def bucket_prefix(bucket_name: str, prefix: str) -> str:
    """Where this install's objects are: under its prefix, the backup bucket at the root.

    `brain.ops.object_store.key_prefix`, whose rule is imported rather than retyped.
    """
    from brain.ops.object_store import key_prefix

    return key_prefix(bucket_name, prefix)


def export(
    out: Path,
    *,
    handover: Handover,
    database: Database,
    objects: Objects | None,
    prefix: str,
    now: datetime,
) -> Return:
    """Write every schema and every bucket into `out`, then the manifest and the sums.

    `objects` is None when the object store is not connected; the bucket stores are then recorded
    as not reached, which is what stops `plan` rather than a teardown deleting files nobody got.
    """
    if (out / MANIFEST).exists():
        msg = f"{out} already holds an export; a second one over it would mix two moments"
        raise HandoverError(msg)
    written: list[Exported] = []
    found: dict[Store, int] = {}
    for schema in SCHEMAS:
        for table in database.tables(schema):
            relative = f"{DATA}/db/{schema}/{table}.csv"
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as sink:
                rows = database.copy_csv(schema, table, sink)
            written.append(
                Exported(
                    relative,
                    sha256_of(target),
                    target.stat().st_size,
                    f"{schema}.{table}",
                    rows,
                    claimants(schema=schema),
                )
            )
            owner = SCHEMA_OWNER.get(schema)
            if owner is not None:
                found[owner] = found.get(owner, 0) + rows
    unreachable: list[Store] = []
    for bucket in BUCKETS:
        owner = BUCKET_OWNER.get(bucket.name)
        if objects is None:
            if owner is not None:
                unreachable.append(owner)
            continue
        under = bucket_prefix(bucket.name, prefix)
        for key in objects.list_objects(bucket.name, under):
            relative = f"{DATA}/objects/{bucket.name}/{_safe_key(key)}"
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(objects.get_object(bucket.name, key))
            written.append(
                Exported(
                    relative,
                    sha256_of(target),
                    target.stat().st_size,
                    f"{bucket.name}:{key}",
                    None,
                    claimants(bucket=bucket.name),
                )
            )
            if owner is not None:
                found[owner] = found.get(owner, 0) + 1
    returned = assemble_return(handover=handover, at=now, found=found, unreachable=unreachable)
    manifest = {
        "handover": instruction_document(handover),
        "exported_at": now.isoformat(),
        "formats": "tables as CSV with a header row; objects as the bytes stored",
        "check": f"sha256sum -c {SUMS}",
        "stores": [
            {
                "store": one.store.value,
                "holds": one.holds,
                "items": one.items,
                "reached": one.reached,
                "derived": DERIVED.get(one.store, ""),
            }
            for one in returned.holdings
        ],
        "connectors": database.live_connectors(),
        "files": [vars(one) for one in written],
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    sums = "".join(f"{one.sha256}  {one.path}\n" for one in written)
    (out / SUMS).write_text(sums, encoding="utf-8", newline="\n")
    return returned


def read_manifest(out: Path) -> dict[str, Any]:
    try:
        document: dict[str, Any] = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError as missing:
        msg = f"{out} holds no {MANIFEST}; run export first"
        raise HandoverError(msg) from missing
    return document


def verify(out: Path) -> tuple[str, ...]:
    """Every file the manifest names that is missing or whose bytes changed. Empty when intact."""
    problems: list[str] = []
    for entry in read_manifest(out)["files"]:
        path = out / entry["path"]
        if not path.is_file():
            problems.append(f"{entry['path']} is missing")
        elif sha256_of(path) != entry["sha256"]:
            problems.append(f"{entry['path']} does not match its recorded digest")
    return tuple(problems)


def instruction_document(handover: Handover) -> dict[str, str]:
    return {
        "handover_id": handover.handover_id,
        "reason": handover.reason.value,
        "instructed_by": handover.instructed_by,
        "instruction_reference": handover.instruction_reference,
        "requested_at": handover.requested_at.isoformat(),
    }


def handover_from(document: Mapping[str, str]) -> Handover:
    return Handover(
        handover_id=document["handover_id"],
        reason=Reason(document["reason"]),
        instructed_by=document["instructed_by"],
        instruction_reference=document["instruction_reference"],
        requested_at=datetime.fromisoformat(document["requested_at"]),
    )


def return_from(manifest: Mapping[str, Any]) -> Return:
    """The return the manifest records, rebuilt by `assemble_return` so its rules apply again."""
    stores = manifest["stores"]
    return assemble_return(
        handover=handover_from(manifest["handover"]),
        at=datetime.fromisoformat(manifest["exported_at"]),
        found={Store(one["store"]): int(one["items"]) for one in stores if one["reached"]},
        unreachable=[Store(one["store"]) for one in stores if not one["reached"]],
    )


# ------------------------------------------------------------------ the teardown
@dataclass(frozen=True)
class Step:
    """One thing to remove, who removes it, and how, in words an operator can follow."""

    what: Store | Residue
    by: By
    how: str


def residue_step(residue: Residue, *, realm: str, connectors: Sequence[str]) -> Step:
    """The operator's instruction for each residue, or this command's own check."""
    named = ", ".join(connectors) or "the export lists the ones connected"
    match residue:
        case Residue.IDENTITY_REALM:
            return Step(residue, By.OPERATOR, f"kcadm.sh delete realms/{realm} (Keycloak admin)")
        case Residue.OBJECT_STORE:
            return Step(residue, By.COMMAND, "checks every bucket lists nothing under the prefix")
        case Residue.VAULT_SECRETS:
            return Step(
                residue,
                By.OPERATOR,
                "bao kv metadata delete every path under providers/, webhooks/ and "
                "connector_keys/ (list them with bao kv list), then bao token revoke the "
                "application token",
            )
        case Residue.SCHEDULED_WORK:
            return Step(
                residue, By.COMMAND, "checks the ops schema, which holds every job, is gone"
            )
        case Residue.NETWORK_ROUTE:
            return Step(
                residue,
                By.OPERATOR,
                "delete the proxy route and its certificate, then the DNS record for the hostname",
            )
        case Residue.RUNTIME:
            return Step(
                residue,
                By.OPERATOR,
                "docker compose down --volumes --rmi all in the install directory; delete a "
                "bucket that was created for this install only",
            )
        case Residue.INSTALL_CONFIGURATION:
            return Step(residue, By.OPERATOR, "delete the install directory and its .env file")
        case Residue.CONNECTOR_AUTHORISATIONS:
            return Step(
                residue,
                By.OPERATOR,
                f"revoke the grant in each source's own admin console: {named}",
            )
        case Residue.CHAT_APP:
            return Step(
                residue,
                By.OPERATOR,
                "delete the chat app (Lark, Slack or Teams) in that platform's developer console",
            )


def store_step(store: Store) -> Step:
    facts = facts_for(store)
    if store is Store.CACHE:
        return Step(store, By.OPERATOR, "removed with the valkey volume by the runtime step")
    if store is Store.INDEX:
        return Step(store, By.COMMAND, "checks the know schema, which holds the index, is gone")
    where = [f"schema {one}" for one in sorted(facts.schemas)]
    where += [f"bucket {one}" for one in sorted(facts.buckets)]
    return Step(store, By.COMMAND, "drops " + ", ".join(where))


def steps_for(returned: Return, *, realm: str, connectors: Sequence[str]) -> tuple[Step, ...]:
    """The plan as steps. Refuses through `plan_teardown` when the return is incomplete."""
    plan = plan_teardown(returned)
    return tuple(store_step(one) for one in plan.stores) + tuple(
        residue_step(one, realm=realm, connectors=connectors) for one in plan.residue
    )


def preview_steps(*, realm: str) -> tuple[Step, ...]:
    """The steps a handover of this install would take, before any export: the Settings screen's.

    Connectors are named at export, from the rows then live, so here the sentence says so.
    """
    return tuple(store_step(one) for one in teardown_order()) + tuple(
        residue_step(one, realm=realm, connectors=()) for one in Residue
    )


def _what(value: str) -> Store | Residue:
    try:
        return Store(value)
    except ValueError:
        return Residue(value)


def plan(out: Path, *, realm: str) -> tuple[Step, ...]:
    """Write `teardown.json`, only from an export that verifies and reached every store."""
    if problems := verify(out):
        msg = "the export does not verify, so it cannot be relied on: " + "; ".join(problems)
        raise HandoverError(msg)
    manifest = read_manifest(out)
    planned = steps_for(return_from(manifest), realm=realm, connectors=manifest["connectors"])
    document = {
        "steps": [
            {
                "what": one.what.value,
                "by": one.by.value,
                "how": one.how,
                "done": False,
                "items": 0,
                "at": "",
            }
            for one in planned
        ]
    }
    _write_teardown(out, document)
    return planned


def _write_teardown(out: Path, document: Mapping[str, Any]) -> None:
    (out / TEARDOWN).write_text(json.dumps(document, indent=2), encoding="utf-8", newline="\n")


def read_teardown(out: Path) -> dict[str, Any]:
    try:
        document: dict[str, Any] = json.loads((out / TEARDOWN).read_text(encoding="utf-8"))
    except FileNotFoundError as missing:
        msg = f"{out} holds no {TEARDOWN}; run plan first"
        raise HandoverError(msg) from missing
    return document


def remove(
    out: Path,
    *,
    confirm: str,
    database: Database,
    objects: Objects | None,
    prefix: str,
    now: datetime,
) -> list[str]:
    """Carry out this command's steps, in plan order. Returns the ones still not done.

    Destructive, so it asks for the handover id typed back and re-verifies the export first: a
    teardown after the export was altered would remove data the company holds no good copy of.
    """
    manifest = read_manifest(out)
    if confirm != manifest["handover"]["handover_id"]:
        msg = "the confirmation does not match this handover's id, so nothing was removed"
        raise HandoverError(msg)
    if problems := verify(out):
        msg = "the export no longer verifies, so nothing was removed: " + "; ".join(problems)
        raise HandoverError(msg)
    document = read_teardown(out)
    counts = {Store(one["store"]): int(one["items"]) for one in manifest["stores"]}
    # Until nothing moves: a check that runs before the drop it checks for passes next round.
    progressed = True
    while progressed:
        progressed = False
        for step in document["steps"]:
            if step["done"] or step["by"] != By.COMMAND.value:
                continue
            what = _what(step["what"])
            if _carry_out(what, database=database, objects=objects, prefix=prefix):
                step.update(done=True, at=now.isoformat())
                step["items"] = counts.get(what, 0) if isinstance(what, Store) else 0
                progressed = True
    _write_teardown(out, document)
    return [one["what"] for one in document["steps"] if not one["done"]]


def _carry_out(
    what: Store | Residue, *, database: Database, objects: Objects | None, prefix: str
) -> bool:
    """Remove one thing, then look again. True only when the second look finds it gone."""
    if what is Store.INDEX:
        return not database.schema_exists("know")
    if what is Residue.SCHEDULED_WORK:
        return not database.schema_exists("ops")
    if what is Residue.OBJECT_STORE:
        return objects is not None and not any(
            _any(objects.list_objects(one.name, bucket_prefix(one.name, prefix))) for one in BUCKETS
        )
    if isinstance(what, Store):
        facts = facts_for(what)
        for schema in sorted(facts.schemas):
            if database.schema_exists(schema):
                database.drop_schema(schema)
        for name in sorted(facts.buckets):
            if objects is None:
                return False
            under = bucket_prefix(name, prefix)
            for key in list(objects.list_objects(name, under)):
                objects.delete_object(name, key)
            if _any(objects.list_objects(name, under)):
                return False
        return not any(database.schema_exists(one) for one in facts.schemas)
    return False


def _any(keys: Iterator[str]) -> bool:
    return next(keys, None) is not None


def record(out: Path, *, what: str, now: datetime) -> None:
    """Mark an operator's step done. A command step is refused: it is done by being checked."""
    document = read_teardown(out)
    for step in document["steps"]:
        if step["what"] == what:
            if step["by"] != By.OPERATOR.value:
                msg = f"{what} is removed and checked by the command; run remove instead"
                raise HandoverError(msg)
            step.update(done=True, at=now.isoformat())
            _write_teardown(out, document)
            return
    msg = f"{what} is not a step of this teardown"
    raise HandoverError(msg)


def issue(out: Path) -> Certificate:
    """The certificate, through `brain.ops.handover.certify`, which refuses while a step is open."""
    returned = return_from(read_manifest(out))
    steps = read_teardown(out)["steps"]
    removed = [
        Removed(what=_what(one["what"]), items=int(one["items"]), completed=bool(one["done"]))
        for one in steps
    ]
    finished = [datetime.fromisoformat(one["at"]) for one in steps if one["done"]]
    completed_at = max(finished) if finished else returned.at
    certificate = certify(returned, removed=removed, completed_at=completed_at)
    document = {
        "handover": instruction_document(certificate.handover),
        "returned_at": certificate.returned_at.isoformat(),
        "completed_at": certificate.completed_at.isoformat(),
        "returned_items": certificate.returned_items,
        "removed": [{"what": str(one.what), "items": one.items} for one in certificate.removed],
        "recoverable_from_backup_until": certificate.recoverable_from_backup_until.isoformat(),
        "manifest_sha256": sha256_of(out / MANIFEST),
    }
    (out / CERTIFICATE).write_text(json.dumps(document, indent=2), encoding="utf-8", newline="\n")
    (out / CERTIFICATE_TEXT).write_text(told(certificate), encoding="utf-8", newline="\n")
    return certificate


def told(certificate: Certificate) -> str:
    """The certificate as a person reads it. States a date, never that anything is complete."""
    last = certificate.recoverable_from_backup_until.date().isoformat()
    return (
        f"Handover {certificate.handover.handover_id} ({certificate.handover.reason.value}), "
        f"instructed by {certificate.handover.instructed_by} under "
        f"{certificate.handover.instruction_reference}.\n"
        f"{certificate.returned_items} item(s) were returned on "
        f"{certificate.returned_at.date().isoformat()}, listed with their digests in {MANIFEST}.\n"
        f"{len(certificate.removed)} stores and install parts were removed by "
        f"{certificate.completed_at.date().isoformat()}.\n"
        f"The last backup that can contain this data expires on {last}.\n"
    )


# ------------------------------------------------------------------ the install's own connections
class PsycopgDatabase:
    """The install's database. Reads in one repeatable-read transaction; drops in autocommit."""

    def __init__(self, url: str) -> None:
        import psycopg

        from brain.db import libpq_url

        self._url = libpq_url(url)
        self._read = psycopg.connect(self._url)
        self._read.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        self._read.read_only = True

    def close(self) -> None:
        self._read.close()

    def tables(self, schema: str) -> list[str]:
        # Ordinary and partitioned parents only: a partition's rows are read through its parent.
        rows = self._read.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
            "ORDER BY c.relname",
            (schema,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def copy_csv(self, schema: str, table: str, sink: BinaryIO) -> int:
        from psycopg import sql

        name = sql.Identifier(schema, table)
        counted = self._read.execute(sql.SQL("SELECT count(*) FROM {}").format(name)).fetchone()
        statement = sql.SQL("COPY (SELECT * FROM {}) TO STDOUT WITH (FORMAT csv, HEADER true)")
        with self._read.cursor().copy(statement.format(name)) as copy:
            for block in copy:
                sink.write(bytes(block))
        return int(counted[0]) if counted else 0

    def live_connectors(self) -> list[str]:
        if not self.schema_exists("ops"):
            return []
        rows = self._read.execute(
            "SELECT connector FROM ops.connector_connection WHERE disconnected_at IS NULL "
            "ORDER BY connector"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def schema_exists(self, schema: str) -> bool:
        import psycopg

        with psycopg.connect(self._url, autocommit=True) as conn:
            row = conn.execute("SELECT to_regnamespace(%s) IS NOT NULL", (schema,)).fetchone()
        return bool(row and row[0])

    def drop_schema(self, schema: str) -> None:
        import psycopg
        from psycopg import sql

        with psycopg.connect(self._url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _connect() -> tuple[PsycopgDatabase, Objects | None, str, str]:
    from brain.install import value_of
    from brain.ops.object_store import object_store_at_start
    from brain.settings import Settings

    settings = Settings()
    if not settings.database_url:
        msg = "DATABASE_URL is not set, so there is no install to hand over"
        raise HandoverError(msg)
    store = object_store_at_start(settings.vault_address, settings.vault_token)
    if store.backend is None:
        print(f"object store not connected: {store.unconnected}", file=sys.stderr)
    return (
        PsycopgDatabase(settings.database_url),
        store.backend,
        store.prefix or value_of("INSTALL_OBJECT_STORE_PREFIX"),
        value_of("INSTALL_OIDC_REALM"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.handover_run <step> <directory>`. See docs/install/handover.md."""
    parser = argparse.ArgumentParser(prog="python -m brain.ops.handover_run")
    sub = parser.add_subparsers(dest="step", required=True)
    exporting = sub.add_parser("export", help="export every store and the audit ledger")
    exporting.add_argument("directory", type=Path)
    exporting.add_argument("--handover-id", required=True)
    exporting.add_argument("--reason", required=True, choices=[one.value for one in Reason])
    exporting.add_argument("--instructed-by", required=True)
    exporting.add_argument("--instruction-reference", required=True)
    for name in ("verify", "plan", "certify"):
        sub.add_parser(name).add_argument("directory", type=Path)
    removing = sub.add_parser("remove", help="carry out this command's teardown steps")
    removing.add_argument("directory", type=Path)
    removing.add_argument("--confirm", required=True, help="the handover id, typed back")
    recording = sub.add_parser("record", help="mark an operator step done")
    recording.add_argument("directory", type=Path)
    recording.add_argument("what", choices=[one.value for one in (*Store, *Residue)])
    asked = parser.parse_args(argv)
    now = datetime.now(UTC)
    out: Path = asked.directory
    try:
        if asked.step == "verify":
            problems = verify(out)
            for one in problems:
                print(one)
            print("intact" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
        if asked.step == "record":
            record(out, what=asked.what, now=now)
            print(f"{asked.what} recorded as removed")
            return 0
        if asked.step == "certify":
            certificate = issue(out)
            print(told(certificate), end="")
            return 0
        database, objects, prefix, realm = _connect()
        try:
            if asked.step == "export":
                out.mkdir(parents=True, exist_ok=True)
                handover = Handover(
                    handover_id=asked.handover_id,
                    reason=Reason(asked.reason),
                    instructed_by=asked.instructed_by,
                    instruction_reference=asked.instruction_reference,
                    requested_at=now,
                )
                returned = export(
                    out,
                    handover=handover,
                    database=database,
                    objects=objects,
                    prefix=prefix,
                    now=now,
                )
                unreached = ", ".join(one.value for one in returned.unreached())
                print(f"{returned.items} item(s) exported to {out}; check with sha256sum -c {SUMS}")
                if unreached:
                    print(f"not reached, so plan will refuse: {unreached}")
                    return 1
                return 0
            if asked.step == "plan":
                for step in plan(out, realm=realm):
                    print(f"{step.what.value:<26} {step.by.value:<9} {step.how}")
                return 0
            open_steps = remove(
                out,
                confirm=asked.confirm,
                database=database,
                objects=objects,
                prefix=prefix,
                now=now,
            )
            print("still to do: " + (", ".join(open_steps) or "nothing"))
            return 0
        finally:
            database.close()
    except HandoverError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    except Exception as exc:
        # The class and never the message, which can carry a connection string.
        print(f"handover failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
