"""Deciding when a rehearsal is owed, and writing down what one found: the two judgements the
server's drill service must not make in shell.

`ops/backup/brain-drill-service` is the half of a rehearsal that starts containers, and it can only
be shell: nothing the product runs holds the access to start one (needs-rupash item 235, which asks
what may start a drill and has not been answered). Two things inside it are not plumbing, though,
and a shell script is the worst place for either. **When a rehearsal is owed** is a date comparison
with a rule about which copy to rehearse and which objects in a bucket are not copies. **What a
rehearsal's record may say** is the format `brain.ops.backup_manifest.drill_from` reads and refuses
to read, and a record assembled by `printf` is a record whose quoting decides whether the product
believes a check passed. So the service asks this module for both, through the application's own
image, and the shell around it is plumbing with nothing to get wrong that a stand-in cannot show.

**The plan is made from a listing and a clock and nothing else.** Every input is a parameter, for
the reason `brain.ops.recovery.drill_due` takes its clock as one: a test advances a date, and the
case that is always wrong, a rehearsal that is exactly seven days old, is reachable. A request for a
rehearsal outranks the schedule and a schedule outranks nothing, and the order is the only thing
deciding which reason the journal gives.

**Due is measured from the last attempt and not from the last success.** `drill_due` on a
`Verification` asks about a verified restore and is right for the panel, which must never read a
failure as reassurance. A service that asked the same question would start a rehearsal on every
poll for as long as the newest one was failing, loading the company's whole database into a
scratch container every ten minutes. The failure is already the loudest thing the product says
(`brain.ops.recovery.Severity.VERIFICATION_FAILED`), and a person who has fixed what it named asks
for the next attempt with the button. **Two clocks again**, as `brain.ops.schedule_runner` argues.

**A copy is rehearsed only when its pair is in the bucket.** A manifest with no copy beside it is
a taker that failed between its two uploads (`ops/backup/brain-backup` uploads the copy first, so
the reverse should not happen, and the guard is for the day somebody reorders it). It is skipped in
favour of the newest copy that has both, and the skip is said.

**The record states what was asked and the verdict is the product's.** `record_document` builds the
document the drill page specifies and then reads it back through `drill_from` and `verification_of`
before printing it, so a record this module writes is one the product can read, and a field the
reader would refuse is refused here, on the server, where somebody is looking, and not weeks later
as an unreadable file on a screen. The rehearsal's own `smoke_query` answer is the row-count
comparison `brain-restore-drill` makes, passed in by the script as a flag and a sentence.

Rejected: reading the schedule from `ops.control_run`. A rehearsal that happens beside the database
cannot depend on the database being up to say whether to run, which is the case it is for.

Rejected: a plan that retries a failed rehearsal after a shorter interval. It is what a person
wants and it is a loop; see above.

Task ids: M30.3.6, M30.3.8
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX, ManifestError, read_drills
from brain.ops.recovery import DRILL_INTERVAL_DAYS, Check

#: The object a console writes to ask for a rehearsal. A name no manifest or drill record can have.
REQUEST_KEY: Final = "drill-request.json"

#: What a copy of the database is called and the suffixes it may carry.
COPY_PREFIX: Final = "database-"
COPY_SUFFIXES: Final[tuple[str, ...]] = (".dump", ".dump.enc")

#: Why a request is a key in the bucket and not a message to a process.
A_REQUEST_IS_AN_OBJECT_THE_SERVICE_FINDS_BECAUSE_NOTHING_CAN_CALL_IT: Final = (
    "The product starts nothing on the server and the service holds no listening port, so the "
    "only thing both can reach is the bucket the copies are in. A request is a small object "
    "there, found by the service's next poll and removed when the rehearsal it asked for has "
    "its record."
)


class Why:
    """The reasons a plan gives, as words a journal and a test can both read."""

    REQUESTED: Final = "requested"
    NEVER: Final = "never"
    WEEKLY: Final = "weekly"
    NOT_DUE: Final = "not-due"
    NOTHING_COPIED: Final = "nothing-copied"


@dataclass(frozen=True)
class Listed:
    """One object in the backup bucket and when it was last written."""

    key: str
    modified: datetime


@dataclass(frozen=True)
class Plan:
    """Whether to rehearse, which copy, and why."""

    run: bool
    backup_id: str | None
    why: str

    def line(self) -> str:
        """The one line the script reads: `run <id> <why>` or `skip <why>`."""
        return f"run {self.backup_id} {self.why}" if self.run else f"skip {self.why}"


def parse_listing(text: str) -> tuple[Listed, ...]:
    """A listing as `aws s3api list-objects-v2 --output text` prints it: key, tab, instant.

    A line that is not that is refused rather than skipped. A listing the script mangled would
    otherwise read as a bucket with fewer copies, which plans a rehearsal of an older one.
    """
    rows: list[Listed] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        key, separator, stamp = line.partition("\t")
        if not separator or not key.strip() or not stamp.strip():
            msg = f"line {number} of the listing is not a key, a tab and a time"
            raise ValueError(msg)
        try:
            when = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
        except ValueError as error:
            msg = f"line {number} of the listing has a time that is not ISO 8601"
            raise ValueError(msg) from error
        if when.tzinfo is None:
            msg = f"line {number} of the listing has a time with no offset"
            raise ValueError(msg)
        rows.append(Listed(key=key.strip(), modified=when))
    return tuple(rows)


def _copy_id(key: str) -> str | None:
    """The copy a copy object belongs to, or None when the key is not a copy of the database."""
    if not key.startswith(COPY_PREFIX):
        return None
    for suffix in COPY_SUFFIXES:
        if key.endswith(suffix):
            return key.removesuffix(suffix)
    return None


def newest_complete_copy(listing: Sequence[Listed]) -> str | None:
    """The newest copy with both its artefact and its manifest in the bucket, or None.

    Ordered by the identifier, which embeds the UTC moment the copy began, so two copies written in
    one second by a retried upload do not swap places between two polls.
    """
    manifests = {
        one.key.removesuffix(MANIFEST_SUFFIX)
        for one in listing
        if one.key.endswith(MANIFEST_SUFFIX)
    }
    copies = {found for one in listing if (found := _copy_id(one.key)) is not None}
    complete = manifests & copies
    return max(complete) if complete else None


def plan(
    listing: Sequence[Listed],
    *,
    now: datetime,
    interval: timedelta = timedelta(days=DRILL_INTERVAL_DAYS),
) -> Plan:
    """Whether a rehearsal is owed now, and of which copy."""
    if now.tzinfo is None:
        msg = "a naive now decides a schedule at this machine's offset"
        raise ValueError(msg)
    chosen = newest_complete_copy(listing)
    if chosen is None:
        return Plan(run=False, backup_id=None, why=Why.NOTHING_COPIED)
    if any(one.key == REQUEST_KEY for one in listing):
        return Plan(run=True, backup_id=chosen, why=Why.REQUESTED)
    attempts = [one.modified for one in listing if one.key.endswith(DRILL_SUFFIX)]
    if not attempts:
        return Plan(run=True, backup_id=chosen, why=Why.NEVER)
    if now - max(attempts) >= interval:
        return Plan(run=True, backup_id=chosen, why=Why.WEEKLY)
    return Plan(run=False, backup_id=None, why=Why.NOT_DUE)


def record_document(
    *,
    backup_id: str,
    started_at: datetime,
    finished_at: datetime,
    smoke_passed: bool,
    smoke_detail: str,
    checks: Sequence[dict[str, object]],
) -> dict[str, object]:
    """The drill record, refused unless the product's own reader can read it.

    `checks` are the entries `brain.ops.drill_checks` printed. The smoke entry is first so the
    record reads in the order the questions were asked. **`into_scratch` is always true here**: this
    function is only called by the service, which made the scratch database a moment earlier and
    refused to run against anything else.
    """
    document: dict[str, object] = {
        "backup_id": backup_id,
        "started_at": started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "into_scratch": True,
        "checks": [
            {"check": Check.SMOKE_QUERY.value, "passed": smoke_passed, "detail": smoke_detail},
            *checks,
        ],
    }
    # Read back through the reader, so a record this module writes is a record the product reads.
    # `read_drills` and not the two functions it is made of: the rule for what counts as verified
    # is applied in one place, and a second caller of it is refused by tests/unit/test_installation.
    _, unreadable = read_drills(
        [(f"the record this service is about to write{DRILL_SUFFIX}", json.dumps(document))]
    )
    if unreadable:
        raise ManifestError(unreadable[0].why)
    return document


def _instant(text: str) -> datetime:
    when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if when.tzinfo is None:
        msg = f"{text!r} has no offset, and a recovery time measured from it would not be"
        raise ValueError(msg)
    return when


def main(argv: Sequence[str] | None = None) -> int:
    """`plan` reads a listing on stdin and prints a line; `record` prints the record as JSON."""
    parser = argparse.ArgumentParser(prog="python -m brain.ops.drill_service")
    commands = parser.add_subparsers(dest="command", required=True)
    planned = commands.add_parser("plan", help="whether a rehearsal is owed")
    planned.add_argument("--now", required=True, help="the current instant, ISO 8601 with offset")
    written = commands.add_parser("record", help="the drill record as JSON")
    written.add_argument("--backup-id", required=True)
    written.add_argument("--started", required=True)
    written.add_argument("--finished", required=True)
    written.add_argument("--smoke", choices=("passed", "failed"), required=True)
    written.add_argument("--smoke-detail", required=True)
    written.add_argument(
        "--checks-file", type=Path, required=True, help="the checks as JSON, or - for stdin"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    try:
        if args.command == "plan":
            print(plan(parse_listing(sys.stdin.read()), now=_instant(args.now)).line())
            return 0
        # `-` is standard input, so the application's image is run with nothing mounted into it.
        reading = sys.stdin.read() if str(args.checks_file) == "-" else None
        entries = json.loads(
            reading if reading is not None else args.checks_file.read_text(encoding="utf-8")
        )
        document = record_document(
            backup_id=args.backup_id,
            started_at=_instant(args.started),
            finished_at=_instant(args.finished),
            smoke_passed=args.smoke == "passed",
            smoke_detail=args.smoke_detail,
            checks=entries,
        )
    except (ValueError, ManifestError, OSError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(document, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
