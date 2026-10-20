"""Install acceptance checks for the weekly rehearsal: asking for one, what the last one asked of
the copy, the recovery time it measured, how loudly a failure is said, and where copies are kept.

**Two kinds of check, and they say which they are.** The ones that call the product's own code with
a stand-in bucket prove the product does what its leaves say whatever the install holds: a press
leaves one request and a second leaves none, a rehearsal that did not verify is the loudest alert.
The ones that read the install's own backup bucket prove the install has done it: a rehearsal has
been recorded, it asked all three questions, a verified one carries a measured time, and the newest
copy says it is kept on another machine under the client's key. **A rehearsal cannot be started by a
check**, because it starts a container on the server, so those checks read what the server's drill
service has written and say `not run`, with the one sentence, when there is nothing yet to read.
That is a check waiting for the owner to press the button, not a pass.

**The press is proved against a bucket the check holds, never the install's own.** A request left
in the install's real bucket would be answered by its real service, and a check must not start a
copy of the company's records loading into a scratch container. The route, the switch, the
authority and the one-at-a-time rule are all the product's own; only the store is a stand-in
(`A_REQUEST_THE_CHECK_LEAVES_IS_NEVER_THE_INSTALLS_REAL_ONE`).

**A failed rehearsal on the install is a finding about the install, not about the machinery.** The
check that reads the newest record passes when all three questions were asked, whether or not the
copy passed them, because "the canary failed" is the rehearsal working and the Recovery screen and
the alert say so. What fails the check is a record that skipped a question.

Task ids: M30.3.3, M30.3.4, M30.3.6, M30.3.7, M30.3.8, M30.3.9, M30.3.11
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2322

A, _B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to a route's authority fails its check.
INSTALL_AUTHORITY: Final = "admin:install_setting"
SWITCHES_FEATURES: Final = "admin:feature"

# ------------------------------------------------------------------ written-down reasons
#: Why the press is proved against a stand-in bucket.
A_REQUEST_THE_CHECK_LEAVES_IS_NEVER_THE_INSTALLS_REAL_ONE: Final = (
    "The press is proved with a bucket the check holds. A request in the install's own bucket is "
    "read by the install's own drill service, which would load a copy of the company's records "
    "into a scratch container because a check asked."
)

NO_STORE_IS_READ_HERE: Final = (
    "this process builds no connection to the object store, so there is no backup bucket for the "
    "check to read; connect the store, and the next run judges it"
)
NO_COPY_HAS_BEEN_TAKEN: Final = (
    "no copy of the database has been recorded in the backup bucket yet, so there is nothing "
    "about where it is kept to judge; the next run after the first nightly copy judges it"
)
NO_REHEARSAL_HAS_BEEN_RECORDED: Final = (
    "no rehearsal has been recorded beside the copies yet, so there is nothing to judge; press "
    "Start a rehearsal on Backup and recovery once the drill service is set up, and the next run "
    "judges what it wrote"
)
NO_REHEARSAL_HAS_VERIFIED: Final = (
    "no rehearsal has verified a copy yet, so no recovery time has been measured; the next run "
    "after one does judges it"
)
THE_COPY_DOES_NOT_SAY_WHERE_IT_IS: Final = (
    "the newest copy was taken before copies declared where they are kept, so its manifest says "
    "nothing to judge; the next nightly copy declares it"
)

THE_PRESS_LEFT_NOTHING: Final = (
    "an administrator's press with the switch on left no request in the backup bucket"
)
THE_PRESS_WAS_REFUSED_TO_NOBODY: Final = (
    "a person holding only the Recovery screen's read, or nothing, was let leave a request"
)
THE_SWITCH_WAS_IGNORED: Final = "a press with the switch off left a request in the backup bucket"
A_SECOND_PRESS_ASKED_AGAIN: Final = "a second press while one waited left a second request"
THE_PRESS_CLAIMED_A_START: Final = (
    "the answer to a press said a rehearsal had started, which only the server can know"
)
THE_RECORD_SKIPPED_A_QUESTION: Final = (
    "the newest rehearsal record on this install did not ask all three questions"
)
A_VERIFIED_REHEARSAL_HAS_NO_TIME: Final = (
    "a rehearsal that verified a copy carries no recovery time"
)
A_FAILURE_WAS_NOT_THE_LOUDEST: Final = (
    "a rehearsal that did not verify was not the first alert beside a copy that is also late"
)
A_COPY_IS_KEPT_ON_THE_HOST: Final = (
    "the newest copy is kept on the machine it is a copy of, so the failure that destroys the "
    "database destroys the copy in the same second"
)
A_COPY_IS_READABLE_BY_ANYBODY: Final = (
    "the newest copy is not encrypted to a key the client holds, so anybody who reaches the "
    "bucket can read every record in it"
)


class _Bucket:
    """The backup bucket as the check holds it: a dictionary that remembers what it was given."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        del bucket_name, content_type
        self.puts.append(key)
        self.objects[key] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        del bucket_name
        return self.objects[key]

    def delete_object(self, bucket_name: str, key: str) -> None:
        del bucket_name
        self.objects.pop(key, None)

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        del bucket_name, prefix
        yield from sorted(self.objects)


async def _switched(h: Harness, administrator: str, *, on: bool, n: int) -> None:
    """The rehearsal switch through the Features route, as the administrator presses it."""
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.features_declared.backup_drill_requests import BACKUP_DRILL_REQUESTS

    async with traced(h, n):
        await switch_feature(
            console_for(h).request("POST"),
            BACKUP_DRILL_REQUESTS.name,
            SwitchAsked(on=on),
            await asking_as(h, administrator, strong=True),
        )


async def _install_listing(h: Harness) -> tuple[tuple[str, str], ...]:
    """What the install's own backup bucket holds, or the sentence for why it cannot be read."""
    from brain.ops.object_store import backup_objects, object_store_at_start

    store = await asyncio.to_thread(
        object_store_at_start, h.settings.vault_address, h.settings.vault_token
    )
    backend = store.backend
    if backend is None:
        raise CheckNotRunError(NO_STORE_IS_READ_HERE)
    return await asyncio.to_thread(lambda: backup_objects(backend)())


# ------------------------------------------------ 1. asking for a rehearsal (M30.3.9)
@check(
    leaves=("M30.3.9",),
    sentence=(
        "An administrator pressing Start a rehearsal on Backup and recovery leaves one request in "
        "the backup bucket for the server's drill service and is told only that one was asked; a "
        "second press asks nothing more; with the switch off, or for a person who only reads the "
        "screen, nothing is left."
    ),
)
async def a_rehearsal_is_asked_for_once_and_only_by_an_administrator(
    h: Harness,
) -> None:
    from brain.ops.drill_service import REQUEST_KEY
    from brain.ops.object_store import backup_objects
    from brain.rehearsal_routes import ask_for_a_rehearsal

    await h.found_departments()
    administrator, reader = h.principal(A, "rehearsal"), h.principal(A, "reader")
    await h.person(
        administrator,
        department=A,
        grants=(
            *screen_grants("recovery"),
            (INSTALL_AUTHORITY, Scope.unrestricted()),
            (SWITCHES_FEATURES, Scope.unrestricted()),
        ),
    )
    await h.person(reader, department=A, grants=screen_grants("recovery"))
    bucket = _Bucket()
    console = console_for(h)
    console.app.state.object_store = SimpleNamespace(backend=bucket)
    console.app.state.backup_objects = backup_objects(bucket)

    async def press(who: str) -> Any:
        return await ask_for_a_rehearsal(
            console.request("POST"), await asking_as(h, who, strong=True)
        )

    await _switched(h, administrator, on=False, n=1)
    if not await refused(press(administrator)) or bucket.puts:
        raise CheckFailedError(THE_SWITCH_WAS_IGNORED)
    await _switched(h, administrator, on=True, n=2)
    if not await refused(press(reader)) or bucket.puts:
        raise CheckFailedError(THE_PRESS_WAS_REFUSED_TO_NOBODY)
    first = await press(administrator)
    if bucket.puts != [REQUEST_KEY] or first.already_asked:
        raise CheckFailedError(THE_PRESS_LEFT_NOTHING)
    if "started" in first.says.replace("does not say it has started", ""):
        raise CheckFailedError(THE_PRESS_CLAIMED_A_START)
    second = await press(administrator)
    if bucket.puts != [REQUEST_KEY] or not second.already_asked:
        raise CheckFailedError(A_SECOND_PRESS_ASKED_AGAIN)


# --------------------------- 2. what the last rehearsal asked (M30.3.6, M30.3.7)
@check(
    leaves=("M30.3.6", "M30.3.7"),
    sentence=(
        "The newest rehearsal recorded beside this install's copies asked the loaded copy all "
        "three questions: that its schema is complete, that a known question has its known "
        "answer, and that a person without the grant is still refused."
    ),
)
async def the_newest_rehearsal_asked_all_three_questions(h: Harness) -> None:
    from brain.ops.backup_manifest import DRILL_SUFFIX, drill_from
    from brain.ops.recovery import REQUIRED_CHECKS

    listing = await _install_listing(h)
    newest = _newest_record(listing, DRILL_SUFFIX)
    if newest is None:
        raise CheckNotRunError(NO_REHEARSAL_HAS_BEEN_RECORDED)
    asked = {one.check for one in drill_from(json.loads(newest), where="the newest record").checks}
    if not set(REQUIRED_CHECKS) <= asked:
        raise CheckFailedError(THE_RECORD_SKIPPED_A_QUESTION)


def _newest_record(listing: tuple[tuple[str, str], ...], suffix: str) -> str | None:
    """The content of the newest record whose name ends in `suffix`, newest by started_at."""
    best: tuple[str, str] | None = None
    for name, content in listing:
        if not name.endswith(suffix):
            continue
        try:
            started = str(json.loads(content)["started_at"])
        except (ValueError, KeyError, TypeError):
            continue
        if best is None or started > best[0]:
            best = (started, content)
    return None if best is None else best[1]


# ------------------------------------------------- 3. the measured time (M30.3.8)
@check(
    leaves=("M30.3.8",),
    sentence=(
        "A rehearsal recorded on this install that verified a copy carries the recovery time it "
        "measured, and one that did not verify carries none."
    ),
)
async def a_verified_rehearsal_states_its_measured_time(
    h: Harness,
) -> None:
    from brain.ops.backup_manifest import read_drills

    listing = await _install_listing(h)
    verifications, _ = read_drills(listing)
    verified = [one for one in verifications if one.verified]
    if not verified:
        raise CheckNotRunError(NO_REHEARSAL_HAS_VERIFIED)
    if any(one.rto_seconds is None for one in verified):
        raise CheckFailedError(A_VERIFIED_REHEARSAL_HAS_NO_TIME)


# --------------------------------------------- 4. the loudest alert (M30.3.11)
@check(
    leaves=("M30.3.11",),
    sentence=(
        "A rehearsal that ran and did not verify is the first alert raised, above a copy that is "
        "also late, and it says that no copy held is known to be readable."
    ),
)
async def a_rehearsal_that_did_not_verify_is_the_loudest_alert(h: Harness) -> None:
    from brain.ops.recovery import (
        Backup,
        Check,
        CheckRun,
        Coverage,
        Drill,
        Method,
        Severity,
        alerts,
        verification_of,
    )

    long_ago = h.now - timedelta(days=3)
    late = Backup(
        backup_id=f"acceptance-{h.run}",
        coverage=Coverage.DATABASE,
        method=Method.FULL,
        destination="acceptance",
        started_at=long_ago - timedelta(minutes=4),
        finished_at=long_ago,
        recoverable_to=long_ago,
        size_bytes=1024,
    )
    failed = verification_of(
        Drill(
            backup_id=late.backup_id,
            started_at=h.now - timedelta(hours=2),
            finished_at=h.now - timedelta(hours=1),
            into_scratch=True,
            checks=(
                CheckRun(check=Check.SCHEMA_COMPLETE, passed=True, detail="all schemas present"),
                CheckRun(check=Check.SMOKE_QUERY, passed=True, detail="every count came back"),
                CheckRun(check=Check.PERMISSION_CANARY, passed=False, detail="a row was shown"),
            ),
        )
    )
    raised = alerts(backups=[late], verifications=[failed], profile="lite", now=h.now)
    if not raised or raised[0].severity is not Severity.VERIFICATION_FAILED:
        raise CheckFailedError(A_FAILURE_WAS_NOT_THE_LOUDEST)
    if not any(one.severity is Severity.BACKUP_AGED for one in raised):
        raise CheckFailedError(A_FAILURE_WAS_NOT_THE_LOUDEST)
    if "readable" not in raised[0].text:
        raise CheckFailedError(A_FAILURE_WAS_NOT_THE_LOUDEST)


# ---------------------------------------------- 5. where copies are kept (M30.3.3, M30.3.4)
@check(
    leaves=("M30.3.3", "M30.3.4"),
    sentence=(
        "The newest copy of the database on this install is kept on another machine than the one "
        "it copies, and is encrypted to a key the client holds."
    ),
)
async def the_newest_copy_is_off_the_host_under_the_clients_key(h: Harness) -> None:
    from brain.ops.backup_manifest import read_manifests
    from brain.ops.recovery import Coverage, KeyHolder, latest

    listing = await _install_listing(h)
    backups, _ = read_manifests(listing)
    newest = latest(backups, Coverage.DATABASE)
    if newest is None:
        raise CheckNotRunError(NO_COPY_HAS_BEEN_TAKEN)
    if newest.off_host is None or newest.key_held_by is None:
        raise CheckNotRunError(THE_COPY_DOES_NOT_SAY_WHERE_IT_IS)
    if not newest.off_host:
        raise CheckFailedError(A_COPY_IS_KEPT_ON_THE_HOST)
    if newest.key_held_by is not KeyHolder.CLIENT:
        raise CheckFailedError(A_COPY_IS_READABLE_BY_ANYBODY)
