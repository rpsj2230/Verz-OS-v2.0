"""Reading a source through custom code: the seam, with a stand-in runner and never a sandbox.

`brain.connectors.custom_code` plans and interprets through `brain.tools.run_skill.ScriptRunner`,
and `brain.ops.custom_code_run` makes every call itself with the leased key. These tests drive both
with the stand-in runner and ticket source the acceptance check uses
(`brain.ops.acceptance_checks_transports`); the sandbox behind a real runner is the deploy work's
optional service and nothing here claims it.

Task ids: M11.1.5
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.connectors.custom_code import (
    MAX_INTERPRETED_CHARS,
    MAX_PLANNED_CALLS,
    THE_KEY_NEVER_ENTERS_THE_SANDBOX,
    CustomCodeError,
    KeyInSandboxError,
    assert_keyless,
)
from brain.connectors.declaration import KeyScheme
from brain.connectors.manifest import manifest_digest
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import TransportError
from brain.ops import connectable
from brain.ops.acceptance_checks_transports import (
    BORROWED_CEILING,
    CODE_DECLARATION,
    CODE_ENTITY,
    CODE_HOST,
    CODE_READING,
    CODE_SOURCE,
    DEPARTMENT_SETTING,
    StandInRunner,
    TicketSource,
    code_manifest,
)
from brain.ops.connectable import key_reference, offered, reads
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import NO_SANDBOX, plan_for
from brain.ops.connector_sync_run import bare_headers
from brain.ops.custom_code_run import (
    CodeRunFailedError,
    installed_runner,
    read_once,
    run_code,
)
from brain.ops.mcp_session import CallNotAdmittedError, CallNotAnsweredError
from brain.tools.fetch import UnsafeAddressError
from brain.tools.run_skill import Egress, RunOutcome, RunStatus, SandboxSpec

#: Far from any wall clock, because nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)
SETTINGS = {DEPARTMENT_SETTING: "acceptance_a"}
KEY = "kq7-not-a-real-key-4c1d"
TICKET = {"id": "40017", "subject": "Printer jam", "state": "open", "body": "The tray sticks."}


class _Resolver:
    def __init__(self, address: str = "2000::1") -> None:
        self.address = address

    def resolve(self, host: str) -> list[str]:
        del host
        return [self.address]


@dataclass
class _Printing:
    """A runner printing one fixed output, or reporting a fixed status. Keeps every spec."""

    output: str
    status: RunStatus = RunStatus.COMPLETED
    elapsed: float = 0.01
    specs: list[SandboxSpec] = field(default_factory=list)

    def run(self, spec: SandboxSpec) -> RunOutcome:
        self.specs.append(spec)
        return RunOutcome(
            run_id="r-1",
            status=self.status,
            exit_code=0,
            output=self.output,
            elapsed_seconds=self.elapsed,
        )


def _read(runner: Any, source: Any, *, source_id: str | None = None, **changes: Any) -> Any:
    reading = replace(CODE_READING, **changes) if changes else CODE_READING
    return read_once(
        reading,
        CODE_ENTITY,
        source_id,
        settings=SETTINGS,
        headers=bare_headers(KeyScheme.BEARER, KEY),
        secret=KEY,
        runner=runner,
        caller=source,
        poster=None,
        resolver=_Resolver(),
        admit=lambda: True,
        fetched_at="2019-03-01T09:00:00Z",
    )


def _plan(*calls: Any) -> str:
    return json.dumps({"calls": list(calls)})


# ------------------------------------------------------------------ the key stays outside
def test_the_host_s_call_carries_the_leased_key_and_its_answer_is_interpreted() -> None:
    """**The positive half of `THE_KEY_NEVER_ENTERS_THE_SANDBOX`.** The code plans the call, the
    host makes it with the key in its one header, and the answer goes back into the sandbox and
    comes out as mapped records. Delete this and a seam that refused every read would pass the
    refusals below."""
    runner, source = StandInRunner(), TicketSource(tickets=(TICKET,))
    reply = _read(runner, source)
    assert source.keys == [KEY]
    assert source.asked == [f"https://{CODE_HOST}/v1/tickets"]
    assert reply.call is CallOutcome.OK and reply.rows is not None
    assert [one.model_dump() for one in reply.rows.records] == [
        {
            "entity": CODE_ENTITY,
            "id": "40017",
            "subject": "Printer jam",
            "status": "open",
            "body": "The tray sticks.",
        }
    ]
    assert [one.arguments[0] for one in runner.specs] == ["plan", "interpret"]


def test_neither_run_is_handed_the_key_nor_network() -> None:
    """Every spec the runner saw: no key in an argument, the environment empty, egress denied.
    Delete this and the key could ride into the sandbox on any field a later edit adds."""
    runner = StandInRunner()
    _read(runner, TicketSource(tickets=(TICKET,)))
    assert len(runner.specs) == 2
    for spec in runner.specs:
        assert KEY not in "".join(spec.arguments)
        assert dict(spec.environment) == {}
        assert spec.network is Egress.DENIED
        assert spec.digest == CODE_READING.code_digest
        assert spec.script == CODE_READING.transport.module


QUOTED = 'kq7"quoted-key'


@pytest.mark.parametrize(
    ("secret", "arguments"),
    [
        (KEY, ("interpret", "ticket", f"before {KEY} after")),
        (KEY, ("interpret", "ticket", '["' + KEY[:9], KEY[9:] + '"]')),
        (QUOTED, ("interpret", "ticket", json.dumps([f"echo {QUOTED}"]))),
    ],
    ids=["whole", "split_across_two_arguments", "json_escaped"],
)
def test_a_spec_carrying_the_key_is_refused_and_never_run(
    secret: str, arguments: tuple[str, ...]
) -> None:
    """A source that echoes the request puts the key in the answer handed back to interpret. The
    key whole, split across two arguments, and escaped as JSON escapes it. Delete this and the
    one secret this install holds for the source runs inside code nobody here wrote."""
    spec = replace(
        CODE_READING.plan_spec(CODE_ENTITY, settings={}, source_id=None), arguments=arguments
    )
    runner = _Printing(output="{}")
    with pytest.raises(KeyInSandboxError) as refused:
        run_code(runner, spec, secret=secret)
    assert str(refused.value) == THE_KEY_NEVER_ENTERS_THE_SANDBOX
    assert runner.specs == []


def test_a_spec_with_the_key_in_its_environment_is_refused() -> None:
    """Delete this and the environment, the one field a runner hands a process unprompted, could
    carry the key."""
    spec = replace(
        CODE_READING.plan_spec(CODE_ENTITY, settings={}, source_id=None), environment={"TZ": KEY}
    )
    with pytest.raises(KeyInSandboxError):
        assert_keyless(spec, KEY)


def test_a_source_echoing_the_key_in_its_answer_is_not_interpreted() -> None:
    """The way the key could actually arrive: an answer that quotes the request. Delete this and
    `assert_keyless` would be a check on specs the host builds itself, which never hold it."""

    @dataclass
    class _Echo(TicketSource):
        def get(self, url: str, **kwargs: Any) -> Any:
            from brain.ops.connector_sync_run import SourceAnswer

            del url
            echoed = {"tickets": [TICKET], "you_sent": kwargs["headers"]["Authorization"]}
            return SourceAnswer(status=200, headers={}, body=json.dumps(echoed).encode())

    runner = StandInRunner()
    with pytest.raises(KeyInSandboxError):
        _read(runner, _Echo(tickets=(TICKET,)))
    assert [one.arguments[0] for one in runner.specs] == ["plan"]


def test_a_source_that_takes_no_key_has_nothing_to_look_for() -> None:
    """An empty secret is a source that takes no key. Delete this and every spec of such a
    source would be refused, because the empty string is in every string."""
    assert_keyless(CODE_READING.plan_spec(CODE_ENTITY, settings={}, source_id=None), "")


# ------------------------------------------------------------------ the plan
def test_a_planning_run_is_handed_the_entity_the_id_and_the_settings() -> None:
    """Delete this and the code could be handed something other than what the declaration says
    a planning run gets, and nobody would see what."""
    spec = CODE_READING.plan_spec(CODE_ENTITY, settings={"b": "2", "a": "1"}, source_id="40017")
    assert spec.arguments == ("plan", CODE_ENTITY, "40017", "a=1", "b=2")


@pytest.mark.parametrize(
    "printed",
    [
        _plan({"method": "GET", "url": "https://elsewhere.example/v1/tickets"}),
        _plan(*({"method": "GET", "url": f"https://{CODE_HOST}/x"},) * (MAX_PLANNED_CALLS + 1)),
        _plan({"method": "GET", "url": f"https://{CODE_HOST}/x", "body": "q"}),
        _plan({"method": "DELETE", "url": f"https://{CODE_HOST}/x"}),
        _plan(),
        "not json",
    ],
    ids=["off_the_allowlist", "too_many", "body_on_a_get", "delete", "none", "not_json"],
)
def test_a_plan_this_seam_will_not_act_on_is_refused_and_nothing_is_called(printed: str) -> None:
    """`A_PLANNED_CALL_GOES_ONLY_WHERE_THE_DECLARATION_SAYS` and the plan's other bounds. Delete
    this and the code could have the host call any address with the key."""
    source = TicketSource(tickets=(TICKET,))
    with pytest.raises(CustomCodeError):
        _read(_Printing(output=printed), source)
    assert source.asked == []


def test_a_planned_address_inside_the_network_is_refused_before_it_is_called() -> None:
    """The address rule, applied to a planned call. Delete this and an allowlisted name that
    answers inside the network would be called with the key."""
    source = TicketSource(tickets=(TICKET,))
    with pytest.raises(UnsafeAddressError):
        read_once(
            CODE_READING,
            CODE_ENTITY,
            None,
            settings=SETTINGS,
            headers={},
            secret=KEY,
            runner=StandInRunner(),
            caller=source,
            poster=None,
            resolver=_Resolver("127.0.0.1"),
            admit=lambda: True,
            fetched_at="",
        )
    assert source.asked == []


def test_a_planned_call_the_ceiling_does_not_admit_is_not_made() -> None:
    """Delete this and planned calls could spend the source's allowance with the ceiling saying
    no."""
    source = TicketSource(tickets=(TICKET,))
    with pytest.raises(CallNotAdmittedError):
        read_once(
            CODE_READING,
            CODE_ENTITY,
            None,
            settings=SETTINGS,
            headers={},
            secret=KEY,
            runner=StandInRunner(),
            caller=source,
            poster=None,
            resolver=_Resolver(),
            admit=lambda: False,
            fetched_at="",
        )
    assert source.asked == []


def test_a_call_the_source_refused_is_raised_as_its_kind() -> None:
    """A source that sent no key is answered 401 by the stand-in. Delete this and a refused call
    could be read as an empty answer."""
    source = TicketSource(tickets=(TICKET,))
    with pytest.raises(CallNotAnsweredError) as refused:
        read_once(
            CODE_READING,
            CODE_ENTITY,
            None,
            settings=SETTINGS,
            headers={},
            secret=KEY,
            runner=StandInRunner(),
            caller=source,
            poster=None,
            resolver=_Resolver(),
            admit=lambda: True,
            fetched_at="",
        )
    assert refused.value.call is CallOutcome.REJECTED


# ------------------------------------------------------------------ the answers
def test_without_interpretation_the_field_mapping_reads_the_answers() -> None:
    """A connector whose answers the mapping can read needs one run, not two. Delete this and
    every custom connector would be bounded by what an argument list can carry."""
    runner, source = StandInRunner(), TicketSource(tickets=(TICKET,))
    reading = replace(
        CODE_READING,
        interprets=False,
        reads=(replace(CODE_READING.reads[0], records_at="tickets"),),
    )
    reply = read_once(
        reading,
        CODE_ENTITY,
        None,
        settings=SETTINGS,
        headers=bare_headers(KeyScheme.BEARER, KEY),
        secret=KEY,
        runner=runner,
        caller=source,
        poster=None,
        resolver=_Resolver(),
        admit=lambda: True,
        fetched_at="",
    )
    assert reply.rows is not None and [one.id for one in reply.rows.records] == ["40017"]
    assert [one.arguments[0] for one in runner.specs] == ["plan"]


def test_answers_too_long_to_hand_over_are_refused_rather_than_cut() -> None:
    """A cut JSON document is a different document. Delete this and the code could interpret
    half an answer as the whole of it."""
    long = {**TICKET, "body": "x" * MAX_INTERPRETED_CHARS}
    with pytest.raises(CustomCodeError):
        _read(StandInRunner(), TicketSource(tickets=(long,)))


@pytest.mark.parametrize(
    ("status", "elapsed", "output"),
    [
        (RunStatus.FAILED, 0.01, _plan()),
        (RunStatus.COMPLETED, 3600.0, _plan()),
        (RunStatus.COMPLETED, 0.01, "x" * (64 * 1024 + 1)),
    ],
    ids=["failed", "overran", "cut_to_the_leash"],
)
def test_a_run_that_did_not_complete_cleanly_is_not_read(
    status: RunStatus, elapsed: float, output: str
) -> None:
    """`THE_CEILING_APPLIES_TO_WHAT_CAME_BACK`, reused: a failed run, one past its deadline, and
    one whose output was cut. Delete this and the half of a plan that fit would be acted on."""
    source = TicketSource(tickets=(TICKET,))
    with pytest.raises(CodeRunFailedError):
        _read(_Printing(output=output, status=status, elapsed=elapsed), source)
    assert source.asked == []


def test_one_record_is_planned_by_its_id_and_read_live() -> None:
    """Delete this and a question could read the list and take whichever ticket came first."""
    source = TicketSource(tickets=(TICKET, {**TICKET, "id": "40018"}))
    reply = _read(StandInRunner(), source, source_id="40018")
    assert source.asked == [f"https://{CODE_HOST}/v1/tickets/40018"]
    assert reply.rows is not None and [one.id for one in reply.rows.records] == ["40018"]


# ------------------------------------------------------------------ no runner, no source
def test_no_runner_is_installed_on_this_release() -> None:
    """The sandbox is an optional service no release starts yet (needs-rupash 154). Delete this
    and a runner could appear here, and custom code be offered, with no sandbox behind it."""
    assert installed_runner() is None


def test_a_custom_code_source_is_readable_and_offered_only_with_a_runner() -> None:
    """`A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ` on the Connectors screen. Named as a source
    whose ceiling is measured, so the runner is the one thing that differs. Delete this and a
    custom-code source would be offered on an install that can never run it."""
    named = replace(CODE_DECLARATION, name=BORROWED_CEILING)
    assert not reads(named)
    assert BORROWED_CEILING not in offered({BORROWED_CEILING: named})[0]
    runner = StandInRunner()
    assert reads(named, runner=runner)
    assert BORROWED_CEILING in offered({BORROWED_CEILING: named}, runner=runner)[0]


def test_the_install_s_own_list_is_built_with_the_installed_runner() -> None:
    """The module-level lists are what the Connectors screen shows, so they must be built by
    asking the one place an install names its runner. Read off the call expression itself.
    Delete this and they could be built with no runner argument, and offer custom code the day
    a runner is configured and the list is not, or the other way about."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(connectable))
    # Since M11.7.8 the lists are `Derived` over the reviewed catalogue, so each is a lambda over
    # the declarations it is handed; both ask `offered` with the installed runner.
    built = [
        node
        for statement in tree.body
        if isinstance(statement, ast.AnnAssign)
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "offered"
    ]
    assert len(built) == 2
    for one in built:
        assert [ast.unparse(arg) for arg in one.args] == ["found"]
        assert {kw.arg: ast.unparse(kw.value) for kw in one.keywords} == {
            "runner": "installed_runner()"
        }


def test_the_worker_does_not_plan_a_custom_code_source_with_no_runner() -> None:
    """`NO_SANDBOX`, and the plan that runs with a runner. Delete this and the worker would lease
    the key for a source it has nowhere to run."""
    connection = Connection(
        connector=CODE_SOURCE,
        settings=SETTINGS,
        digest=manifest_digest(code_manifest(SETTINGS, key_reference(CODE_SOURCE))),
        connected_by="u_admin",
        connected_at=NOW,
    )

    def plan(runner: Any) -> Any:
        return plan_for(
            connection,
            last=None,
            now=NOW,
            readings={CODE_SOURCE: CODE_READING},
            runner=runner,
            manifests=lambda name, settings: code_manifest(settings, key_reference(name)),
        )

    assert plan(None).refused == NO_SANDBOX
    ran = plan(StandInRunner())
    assert not ran.refused and ran.due and ran.reading is CODE_READING


def test_a_custom_reading_names_the_digest_of_its_reviewed_code() -> None:
    """`SandboxSpec.digest` is how the runner materialises the bytes somebody read. Delete this
    and a reading could run whatever sits under the module's name."""
    with pytest.raises(TransportError):
        replace(CODE_READING, code_digest="latest")
    with pytest.raises(TransportError):
        replace(CODE_READING, scheme=KeyScheme.GOOGLE_SERVICE_ACCOUNT)
