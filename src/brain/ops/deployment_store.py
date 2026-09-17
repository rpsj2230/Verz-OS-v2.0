"""Write the deploy script's records into `ops.deployment_record`, as a command the deploy runs.

The deploy script appends one JSON line per deploy to a file on the host, including the deploys
where the application never came up, because those are the lines worth reading and a database
behind that application cannot be written at that moment. Once a container answers ready, the
script pipes the whole file into this command inside it:

    docker exec -i <app container> python -m brain.ops.deployment_store < deployments.jsonl

**The whole file every time, and that is what makes it safe to run after any deploy.**
`brain.ops.deployments.reconcile` takes in only what the stored chain lacks, by fingerprint, and
the table's unique fingerprint refuses a second copy if two runs ever raced past the lock. So a
deploy that failed, and the rollback that recorded it, are both taken in by the next deploy that
reaches a ready container, and nothing is recorded twice.

**On the login, never on `brain_app`.** The application role holds SELECT on the table and no
more (`0091`), so no request can add or change a deploy. This module is imported by nothing the
application's sessions reach, which is what `brain.ops.application_privileges` checks.

**Serialised by an advisory lock in the transaction**, so two deploys finishing together cannot
both read the same head and write two rows claiming the same place.

**A malformed line refuses the whole run and names the line.** `read_records` argues it: a
trailing partial line is indistinguishable from tampering, and dropping it would make the stored
history silently shorter than the file it is derived from. The deploy script runs this after the
deploy has finished and does not fail the deploy on it, so the refusal is a line in the journal
rather than an outage.

Task ids: M38.1.3.5
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from typing import Any, Final, Protocol

from sqlalchemy import create_engine, insert, text

from brain.ops.deployment_history import chain_from_rows, recorded
from brain.ops.deployments import ChainedDeployment, Deployment, DeploymentRecordError, reconcile
from brain.tables.deployment_record import DeploymentRecordRow

#: The advisory lock every writer of the history takes. A number of its own, not the migration's.
DEPLOYMENT_HISTORY_LOCK: Final = 8274419038

EXIT_REFUSED: Final = 1
EXIT_USAGE: Final = 2


class Connection(Protocol):
    def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


def parse(lines: Iterable[str]) -> tuple[Deployment, ...]:
    """Every record in the lines, oldest first by file order; blank lines skipped."""
    return tuple(Deployment.from_line(line) for line in lines if line.strip())


def row_of(link: ChainedDeployment) -> dict[str, Any]:
    """One link as the table stores it."""
    one = link.deployment
    return {
        "seq": link.seq,
        "at": one.at,
        "outcome": one.outcome,
        "commit": one.commit,
        "image": one.image,
        "previous": one.previous,
        "task_ids": sorted(one.task_ids),
        "prev_hash": link.prev_hash,
        "entry_hash": link.entry_hash,
        "fingerprint": one.fingerprint(),
    }


def record(conn: Connection, records: Sequence[Deployment]) -> tuple[ChainedDeployment, ...]:
    """Append what the stored chain lacks, in one transaction the caller owns. Returns it."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": DEPLOYMENT_HISTORY_LOCK})
    stored = conn.execute(recorded()).all()
    chain = chain_from_rows(stored)
    added = reconcile(records, chain)
    if added:
        conn.execute(insert(DeploymentRecordRow), [row_of(link) for link in added])
    return added


def main(argv: Sequence[str] | None = None, stdin: Iterable[str] | None = None) -> int:
    """Read the deploy script's file on standard input and record what is new."""
    from brain.db import normalise_database_url
    from brain.settings import Settings

    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("usage: python -m brain.ops.deployment_store < deployments.jsonl", file=sys.stderr)
        return EXIT_USAGE
    try:
        records = parse(sys.stdin if stdin is None else stdin)
    except DeploymentRecordError as error:
        print(f"REFUSED: {error}. Nothing was recorded.", file=sys.stderr)
        return EXIT_REFUSED
    url = Settings().database_url.strip()
    if not url:
        print("DATABASE_URL is not set, so there is nowhere to record deploys", file=sys.stderr)
        return EXIT_USAGE
    engine = create_engine(normalise_database_url(url))
    try:
        with engine.begin() as conn:
            added = record(conn, records)
    finally:
        engine.dispose()
    print(f"recorded {len(added)} deploy(s) not already in the history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
