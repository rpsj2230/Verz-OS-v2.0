"""The host's half of a custom-code source: run the plan, make the calls, hand the answers back.

`brain.connectors.custom_code` decides what a run is handed and what its output means; this runs
it through the install's `brain.tools.run_skill.ScriptRunner`, makes each planned call with the
leased key, and reads what came back. The worker's run (`brain.ops.connector_sync_run`) and a
question's read (`brain.ops.live_read_run`) both read through `read_once`, so a scheduled read and
a live one cannot come to plan, call or interpret differently.

**The runner is handed in, and `installed_runner` is the one place an install says it has one.**
It answers None on every install today: the sandbox is an optional service the deploy work is
adding (needs-rupash 154), and when it lands, this function is what it changes. A source whose
reading is custom code is then neither offered (`brain.ops.connectable.reads`) nor read: the
worker's plan has no runner to hand over and the attempt records that it could not be read, and
nothing here runs the code any other way. See
`brain.connectors.custom_code.A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ`.

**Every spec is checked for the key before the runner sees it**
(`custom_code.assert_keyless`), and **every outcome is held to the leash before its output is
read** (`run_skill.accept_outcome`, reused rather than restated): a run that overran is a
timeout whatever it says, a non-zero exit is a failure, and an output cut to the leash is refused
here rather than parsed, because the end of a JSON document is where its closing brackets are.

**Each planned call is made as a REST reading's call is made**: the address rule and the pinned
connection (`brain.tools.fetch.assert_fetchable`, then `SourceCaller.get` or `SourcePoster.post`
to the address it checked), the run's timeout and response bound, the source's ceiling admitting
each one through `admit`, and the headers the run built with the key in one of them. The code
sets no header: it names a body type from a closed set and the host writes the header.

Task ids: M11.1.5
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Final

from brain.connectors.custom_code import (
    CustomCodeError,
    PlannedCall,
    PlannedMethod,
    assert_keyless,
)
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.mcp_session import CallNotAdmittedError, CallNotAnsweredError
from brain.tools.fetch import Resolver, assert_fetchable
from brain.tools.run_skill import RunStatus, ScriptRunner, accept_outcome

if TYPE_CHECKING:
    from brain.connectors.declaration import CodeReading, PageReply
    from brain.ops.connector_sync_run import SourceAnswer, SourceCaller, SourcePoster
    from brain.tools.run_skill import SandboxSpec

#: What a refused run is told when it has nowhere to post a planned call with a body.
NO_POSTER_FOR_A_PLANNED_POST: Final = (
    "the code planned a call with a body, and this process was given no way to post"
)


class CodeRunFailedError(Exception):
    """A sandboxed run did not complete with output this seam can read. Names the status only."""

    def __init__(self, status: RunStatus) -> None:
        super().__init__(f"a custom connector's run ended {status.value}")
        self.status = status


def installed_runner() -> ScriptRunner | None:
    """The runner this install runs custom code with, or None when it runs none.

    None on every install today, and said so rather than hidden behind a flag: the sandbox is an
    optional service (needs-rupash 154) and nothing on this release starts one. The service's
    wiring answers here when it lands; until then no custom-code source is offered or read.
    """
    return None


def run_code(runner: ScriptRunner, spec: SandboxSpec, *, secret: str) -> str:
    """One sandboxed run's output, checked for the key before and held to the leash after.

    Raises `custom_code.KeyInSandboxError` before the runner is asked, for a spec carrying the
    key, and `CodeRunFailedError` for a run that did not complete or whose output was cut.
    """
    assert_keyless(spec, secret)
    record = accept_outcome(spec, runner.run(spec))
    if record.status is not RunStatus.COMPLETED:
        raise CodeRunFailedError(record.status)
    if record.truncated:
        raise CodeRunFailedError(RunStatus.KILLED)
    return record.output


def send_call(
    call: PlannedCall,
    *,
    headers: Mapping[str, str],
    caller: SourceCaller,
    poster: SourcePoster | None,
    resolver: Resolver,
) -> SourceAnswer:
    """One planned call, made by the host to the address the rule checked, or refused by it."""
    where = assert_fetchable(call.url, resolver)
    if call.method is PlannedMethod.GET:
        return caller.get(
            where.url, address=where.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
        )
    if poster is None:
        raise CustomCodeError(NO_POSTER_FOR_A_PLANNED_POST)
    return poster.post(
        where.url,
        address=where.address,
        headers={**headers, "Content-Type": call.content_type.value},
        body=call.body or b"",
        max_bytes=MAX_RESPONSE_BYTES,
    )


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.casefold() == "retry-after":
            try:
                return float(str(value).strip())
            except ValueError:
                return None
    return None


def read_once(
    reading: CodeReading,
    entity: str,
    source_id: str | None,
    *,
    settings: Mapping[str, str],
    headers: Mapping[str, str],
    secret: str,
    runner: ScriptRunner,
    caller: SourceCaller,
    poster: SourcePoster | None,
    resolver: Resolver,
    admit: Callable[[], bool],
    fetched_at: str,
) -> PageReply:
    """One entity listed, or one record read: planned, called, and read.

    Raises `CallNotAdmittedError` for a call the ceiling refused, `CallNotAnsweredError` for one
    the source did not answer, `UnsafeAddressError` for an address the rule refuses,
    `KeyInSandboxError`, `CodeRunFailedError`, and `CustomCodeError` for a plan or an output this
    seam will not act on. Nothing is called before the whole plan has been read and allowed.
    """
    planned = reading.planned(
        run_code(
            runner,
            reading.plan_spec(entity, settings=settings, source_id=source_id),
            secret=secret,
        )
    )
    bodies: list[bytes] = []
    for call in planned:
        if not admit():
            raise CallNotAdmittedError
        answer = send_call(call, headers=headers, caller=caller, poster=poster, resolver=resolver)
        outcome = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if outcome is not CallOutcome.OK:
            wait = _retry_after(answer.headers or {}) if outcome is CallOutcome.QUOTA else None
            raise CallNotAnsweredError(outcome, timed_out=answer.timed_out, retry_after=wait)
        bodies.append(answer.body)
    spec = reading.interpret_spec(entity, tuple(bodies))
    if spec is None:
        decoded: tuple[Any, ...] = tuple(json.loads(body) for body in bodies)
        return reading.from_answers(entity, decoded, fetched_at=fetched_at)
    return reading.from_output(entity, run_code(runner, spec, secret=secret), fetched_at=fetched_at)
