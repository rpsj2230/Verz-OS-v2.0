"""The install's check for the personal data detector, run against an analyser that is a handler.

The check asks a real HTTP server on the install, so here the server is an `httpx.MockTransport`
whose answers are built from the request the check sent, the way Presidio builds its own: an entity
is found in a sentence only when that sentence carries one and the entity was asked for. So the
check is judged on what it asks as well as on what it does with the answer.

Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2, M32.1.2.6, M32.1.1.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from brain.install import hold_saved
from brain.ops import acceptance_checks_services as services
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.overlays import BY_NAME, OBSERVED_KEY
from brain.ops.pii import (
    PRESIDIO_BUILT_INS,
    PRESIDIO_LANGUAGE,
    PRESIDIO_PORT,
    PRESIDIO_PROBES,
    PRESIDIO_SERVICE,
)
from brain.ops.wiring import component
from brain.settings import settings_from

MODULE = "brain.ops.acceptance_checks_services"
DETECTOR = "the_detector_finds_every_entity_the_scrub_relies_on_it_for"

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def presidio_like(
    *, scores: dict[str, float] | None = None, deaf: frozenset[str] = frozenset()
) -> Handler:
    """An analyser that finds an entity when the text is that entity's probe and it was asked for.

    `scores` overrides the score it gives an entity, and `deaf` names entities it never finds.
    """

    def answer(request: httpx.Request) -> httpx.Response:
        asked = json.loads(request.content)
        assert request.url.path == "/analyze"
        assert asked["language"] == PRESIDIO_LANGUAGE
        found = [
            {"entity_type": name, "start": 0, "end": 4, "score": (scores or {}).get(name, 0.85)}
            for name in asked["entities"]
            if PRESIDIO_PROBES.get(name) == asked["text"] and name not in deaf
        ]
        return httpx.Response(200, json=found)

    return answer


@pytest.fixture
def analyser(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every client the check opens is pointed at whichever handler `use` installed, and every
    address it posted to is recorded."""
    seen: list[str] = []
    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        handler: Handler = getattr(client, "handler", presidio_like())

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return handler(request)

        kwargs["transport"] = httpx.MockTransport(recording)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    yield seen


def use(handler: Handler) -> None:
    httpx.AsyncClient.handler = handler  # type: ignore[attr-defined]


@pytest.fixture
def switched_on() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "presidio"})
    yield
    hold_saved(before)


def ran() -> tuple[str, str]:
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[DETECTOR].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def test_the_check_claims_the_leaf_the_detector_is_running_for() -> None:
    """Delete this and the check can be moved onto another leaf and the detector's row on the
    tracker closes on somebody else's evidence."""
    assert mine()[DETECTOR].leaves == ("M32.2.1.1",)


def test_an_install_that_has_not_switched_the_detector_on_is_not_run(
    analyser: list[str],
) -> None:
    """Not failed: an install without the detector has not got anything wrong, and the check asks
    nothing. Delete this and every lite install shows a red row it cannot act on."""
    before = hold_saved({})
    try:
        assert ran() == (NOT_RUN, services.NO_DETECTOR_HERE)
    finally:
        hold_saved(before)
    assert analyser == []


@pytest.mark.usefixtures("switched_on")
def test_a_detector_that_finds_every_entity_passes_and_was_asked_about_each_one(
    analyser: list[str],
) -> None:
    """The positive case, and it says where it asked: the product's own service by name and port,
    once per entity. Delete this and a check that refuses everything would pass every other test
    here."""
    use(presidio_like())
    with capture_logs() as logged:
        assert ran() == (PASSED, "")
    assert analyser == [f"http://{PRESIDIO_SERVICE}:{PRESIDIO_PORT}/analyze"] * len(
        PRESIDIO_BUILT_INS
    )
    [line] = [one for one in logged if one["event"] == "acceptance.detector_asked"]
    assert line["missed"] == []


@pytest.mark.usefixtures("switched_on")
def test_a_detector_that_misses_one_entity_fails_and_the_log_names_it(
    analyser: list[str],
) -> None:
    """One recogniser absent is the failure M32.2.1.1 is about: a detector running without the
    rules the scrub relies on. Delete this and the check passes on a detector that finds four of
    five."""
    use(presidio_like(deaf=frozenset({"IBAN_CODE"})))
    with capture_logs() as logged:
        assert ran() == (FAILED, services.THE_DETECTOR_MISSED_AN_ENTITY)
    [line] = [one for one in logged if one["event"] == "acceptance.detector_asked"]
    assert line["missed"] == ["IBAN_CODE"]
    assert analyser


@pytest.mark.usefixtures("switched_on")
def test_a_finding_below_the_threshold_the_scrub_uses_counts_as_missed(
    analyser: list[str],
) -> None:
    """The scrub ignores a finding under its threshold, so the check must too, and at the
    boundary: exactly the threshold is found, a hair under is not. Delete this and a detector
    whose scores fell below every threshold would pass while the scrub used none of them."""
    person = next(one for one in PRESIDIO_BUILT_INS if one.presidio_name == "PERSON")

    use(presidio_like(scores={"PERSON": person.score_threshold}))
    assert ran() == (PASSED, "")
    use(presidio_like(scores={"PERSON": person.score_threshold - 0.001}))
    assert ran() == (FAILED, services.THE_DETECTOR_MISSED_AN_ENTITY)
    assert analyser


@pytest.mark.usefixtures("switched_on")
@pytest.mark.parametrize(
    "broken",
    [
        lambda request: httpx.Response(503),
        lambda request: httpx.Response(200, content=b"not json"),
    ],
    ids=["refused", "garbled"],
)
def test_a_detector_that_does_not_answer_fails_with_its_own_sentence(
    analyser: list[str], broken: Handler
) -> None:
    """Switched on and not answering is a failure, and a different one from missing an entity.
    Delete this and an unreachable detector reads as one that found nothing, which sends somebody
    to the wrong half of the problem."""
    use(broken)
    assert ran() == (FAILED, services.THE_DETECTOR_DID_NOT_ANSWER)
    assert analyser


# ------------------------------------------------------------------------ the trace ledger
RUNNING = "the_trace_ledger_runs_as_its_five_services"
LIMITED = "every_trace_ledger_service_runs_under_its_budgeted_limit"
LEDGER = BY_NAME["langfuse"]


def reported(**changed: Mapping[str, object]) -> dict[str, object]:
    """The step's report for this release: every ledger service running, healthy and at budget,
    with `changed` overriding one service's entry (an empty dict removes it)."""
    services: dict[str, object] = {
        name: {"limit_mib": component(name).memory_mib, "state": "running", "health": "healthy"}
        for name in LEDGER.components
    }
    services["langfuse-events-bucket"] = {"limit_mib": 64, "state": "exited", "health": ""}
    for name, body in changed.items():
        if body:
            services[name] = {**services[name], **body}  # type: ignore[dict-item]
        else:
            del services[name]
    return {"commit": settings_from({}).resolved_commit(), "services": services}


@pytest.fixture
def ledger_on() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "presidio,langfuse"})
    yield
    hold_saved(before)


def judged(monkeypatch: pytest.MonkeyPatch, name: str, row: object | None) -> tuple[str, str]:
    """One ledger check against a stored report, read through a stand-in for the setting reader."""
    from brain.ops import setting_store

    async def held(session: object, namespace: str) -> dict[str, object]:
        assert namespace == "overlay"
        return {} if row is None else {OBSERVED_KEY: SimpleNamespace(value=row)}

    monkeypatch.setattr(setting_store, "read_namespace", held)
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[name].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def test_the_ledger_checks_claim_the_leaves_the_service_set_and_its_limits_are() -> None:
    """Delete this and either check can drift onto the other's leaf, so a set that runs closes the
    limits leaf on evidence that never looked at a limit."""
    assert mine()[RUNNING].leaves == ("M32.1.1.1",)
    assert mine()[LIMITED].leaves == ("M32.1.1.2",)


@pytest.mark.parametrize("name", [RUNNING, LIMITED])
def test_an_install_without_the_ledger_is_not_run(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Not switched on is not wrong. Delete this and every install that did not choose the ledger
    shows two red rows."""
    before = hold_saved({"INSTALL_SERVICES": "presidio"})
    try:
        assert judged(monkeypatch, name, reported()) == (NOT_RUN, services.NO_LEDGER_HERE)
    finally:
        hold_saved(before)


@pytest.mark.usefixtures("ledger_on")
@pytest.mark.parametrize("name", [RUNNING, LIMITED])
def test_a_report_from_another_release_or_none_at_all_is_not_judged(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """`THE_SERVER_REPORTS_WHAT_RUNS_AND_THE_CHECK_READS_IT`: only this release's report counts.
    Delete this and a ledger stopped since the last deploy passes on what an older release saw."""
    stale = {**reported(), "commit": "an-older-release"}
    assert judged(monkeypatch, name, None) == (NOT_RUN, services.NOT_REPORTED_FOR_THIS_RELEASE)
    assert judged(monkeypatch, name, stale) == (NOT_RUN, services.NOT_REPORTED_FOR_THIS_RELEASE)


@pytest.mark.usefixtures("ledger_on")
def test_five_running_healthy_services_at_their_budget_pass_both_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case, with the one-shot that made the bucket in the report as it will be, exited
    and costed nowhere. Delete this and checks that refuse everything pass every other test here."""
    assert judged(monkeypatch, RUNNING, reported()) == (PASSED, "")
    assert judged(monkeypatch, LIMITED, reported()) == (PASSED, "")


@pytest.mark.usefixtures("ledger_on")
@pytest.mark.parametrize(
    "broken",
    [{"health": "unhealthy"}, {"health": "starting"}, {"state": "restarting"}, {}],
    ids=["unhealthy", "starting", "restarting", "absent"],
)
def test_a_ledger_service_not_running_and_healthy_fails_the_set(
    monkeypatch: pytest.MonkeyPatch, broken: dict[str, object]
) -> None:
    """Each way a container is not serving, on the column store, which is the one the others wait
    for. Delete this and a ledger whose ClickHouse never came up passes as a running set."""
    row = reported(**{"langfuse-clickhouse": broken})
    with capture_logs() as logged:
        assert judged(monkeypatch, RUNNING, row) == (
            FAILED,
            services.A_LEDGER_SERVICE_IS_NOT_RUNNING,
        )
    [line] = [one for one in logged if one["event"] == "acceptance.ledger_services"]
    assert line["down"] == ["langfuse-clickhouse"]


@pytest.mark.usefixtures("ledger_on")
@pytest.mark.parametrize("limit", [0, 511, 513], ids=["unlimited", "under", "over"])
def test_a_ledger_service_under_any_limit_but_its_budget_fails_the_limits(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    """No limit is the failure M32.1.1.2 exists for, and a limit either side of the budget is a
    container somebody resized without deciding where the memory comes from. The running check is
    unaffected, because the set does run. Delete this and an unlimited ledger closes the leaf."""
    row = reported(**{"langfuse-web": {"limit_mib": limit}})
    assert component("langfuse-web").memory_mib == 512
    assert judged(monkeypatch, LIMITED, row) == (
        FAILED,
        services.A_LEDGER_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET,
    )
    assert judged(monkeypatch, RUNNING, row) == (PASSED, "")


# ------------------------------------------------------------------- the ledger's spans
SENT = "a_run_sent_to_the_ledger_is_found_there_with_its_model_call"
NOWHERE = "with_the_ledger_off_a_run_is_sent_nowhere"
VAULTED = {"BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid", "BRAIN_VAULT_TOKEN": "t"}


def ledger_like(
    *, takes: bool = True, shows: bool = True, kinds: tuple[str, ...] = ("GENERATION",)
) -> Handler:
    """A ledger that keeps what it is sent and shows it back by trace id, as the real one does."""
    kept: dict[str, list[dict[str, object]]] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            if not takes:
                return httpx.Response(401)
            batch = json.loads(request.content)["batch"]
            for event in batch:
                body = event["body"]
                kept.setdefault(body.get("traceId", body["id"]), [])
            return httpx.Response(207, json={"successes": batch, "errors": []})
        trace_id = request.url.path.rsplit("/", 1)[-1]
        if not shows or trace_id not in kept:
            return httpx.Response(404)
        return httpx.Response(
            200, json={"id": trace_id, "observations": [{"type": k} for k in kinds]}
        )

    return answer


def ledger_run(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    *,
    keys: bool = True,
    env: dict[str, str] | None = None,
) -> tuple[str, str]:
    from brain.ops import ledger_export
    from brain.ops.leases import SealedSecret

    held = ledger_export.LedgerKeys(public="pk-lf-0123", secret=SealedSecret("sk-lf-4567"))
    monkeypatch.setattr(ledger_export, "read_keys", lambda vault: held if keys else None)
    monkeypatch.setattr(services, "LEDGER_READ_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(services, "LEDGER_READ_EVERY_SECONDS", 0.0)
    harness = Harness(
        run="0a1b2c3d",
        now=LONG_AGO,
        settings=settings_from(VAULTED if env is None else env),
        connection=None,  # type: ignore[arg-type]
    )
    try:
        asyncio.run(mine()[name].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def test_the_span_checks_claim_the_export_leaf_and_the_flag_leaf() -> None:
    """Delete this and the sibling can stop proving the flag M32.1.1.4 names."""
    assert mine()[SENT].leaves == ("M32.1.2.6",)
    assert mine()[NOWHERE].leaves == ("M32.1.2.6", "M32.1.1.4")


@pytest.mark.usefixtures("ledger_on")
def test_a_run_sent_to_the_ledger_and_shown_with_its_model_call_passes(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """The positive case: posted to the product's own ledger with the vault's keys, read back by its
    trace id with a generation in it. Delete this and a check that refuses everything passes every
    test that follows."""
    use(ledger_like())
    assert ledger_run(monkeypatch, SENT) == (PASSED, "")
    assert analyser[0] == "http://langfuse-web:3000/api/public/ingestion"
    assert analyser[1] == "http://langfuse-web:3000/api/public/traces/acceptance-0a1b2c3d-ledger"


@pytest.mark.usefixtures("ledger_on")
@pytest.mark.parametrize(
    ("ledger", "keys", "reason"),
    [
        (ledger_like(), False, "THE_LEDGER_KEYS_ARE_NOT_KEPT"),
        (ledger_like(takes=False), True, "THE_LEDGER_DID_NOT_TAKE_THE_RUN"),
        (ledger_like(shows=False), True, "THE_RUN_WAS_NOT_FOUND_IN_THE_LEDGER"),
        (ledger_like(kinds=("SPAN",)), True, "THE_RUN_WAS_NOT_FOUND_IN_THE_LEDGER"),
    ],
    ids=["no keys kept", "the keys refused", "never shown", "no model call shown"],
)
def test_each_way_a_run_does_not_reach_the_ledger_fails_with_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str], ledger: Handler, keys: bool, reason: str
) -> None:
    """Four different faults, four different sentences, so whoever reads the Install page goes to
    the right half of the problem. Delete this and a ledger that drops model calls passes as one
    that shows them."""
    use(ledger)
    assert ledger_run(monkeypatch, SENT, keys=keys) == (FAILED, getattr(services, reason))
    del analyser


@pytest.mark.usefixtures("ledger_on")
def test_with_no_vault_the_keys_are_not_kept_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """An install that names no vault has nowhere the keys could be. Delete this and the check asks
    a vault it was never given."""
    use(ledger_like())
    assert ledger_run(monkeypatch, SENT, env={}) == (FAILED, services.THE_LEDGER_KEYS_ARE_NOT_KEPT)
    assert analyser == []


def test_with_the_ledger_off_nothing_is_sent_and_the_check_passes(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """M32.1.1.4 on an install without the ledger: no destination, and a send reaches nothing. And
    it is not run where the ledger is on, where its sibling is the check that applies. Delete this
    and an install that never chose the ledger can send its traces somewhere with this row green."""
    before = hold_saved({"INSTALL_SERVICES": "presidio"})
    try:
        assert ledger_run(monkeypatch, NOWHERE) == (PASSED, "")
        hold_saved({"INSTALL_SERVICES": "presidio,langfuse"})
        assert ledger_run(monkeypatch, NOWHERE) == (NOT_RUN, services.THE_LEDGER_IS_ON_HERE)
    finally:
        hold_saved(before)
    assert analyser == []


def test_with_the_ledger_off_a_configured_destination_is_still_sent_nothing(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """A `LANGFUSE_HOST` copied from another install's environment file resolves to nothing here, so
    the check passes and nothing is asked. Delete this and the check can be satisfied by an install
    whose only destination is one it was never meant to have."""
    before = hold_saved({"INSTALL_SERVICES": "none"})
    try:
        env = {**VAULTED, "BRAIN_LANGFUSE_HOST": "https://cloud.langfuse.invalid"}
        assert ledger_run(monkeypatch, NOWHERE, env=env) == (PASSED, "")
    finally:
        hold_saved(before)
    assert analyser == []


# ------------------------------------------------------------------------ the script sandbox
SANDBOXED = "the_sandbox_finds_no_network_and_stops_scripts_at_their_limits"


def sandbox_like(
    *, isolated: bool = True, network: str = "network:none", holds: bool = True
) -> Handler:
    """A sandbox that answers each probe as a real one would, or as one whose isolation failed."""
    from brain.ops.sandbox import AnswerStatus

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            runtime = "runsc" if isolated else "runc"
            return httpx.Response(200, json={"runtime": runtime, "network": "none"})
        sent = json.loads(request.content)
        kind = sent["run_id"].rsplit("-", 1)[-1]
        status, output = {
            "network": (AnswerStatus.COMPLETED, network),
            "time": (AnswerStatus.TIMED_OUT if holds else AnswerStatus.COMPLETED, ""),
            "memory": (AnswerStatus.MEMORY_EXCEEDED, ""),
        }[kind]
        return httpx.Response(
            200,
            json={
                "run_id": sent["run_id"],
                "status": status.value,
                "exit_code": 0,
                "output": output,
                "elapsed_seconds": 0.1,
                "truncated": False,
            },
        )

    return answer


def sandbox_report(runtime: str = "runsc") -> dict[str, object]:
    return {
        "commit": settings_from({}).resolved_commit(),
        "runtimes": ["runc", "runsc"],
        "services": {
            name: {
                "limit_mib": component(name).memory_mib,
                "state": "running",
                "health": "healthy",
                "runtime": runtime,
            }
            for name in BY_NAME["sandbox"].components
        },
    }


@pytest.fixture
def sandbox_on() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "sandbox"})
    yield
    hold_saved(before)


def test_the_sandbox_check_claims_the_code_sandbox_leaf() -> None:
    """Delete this and the check can drift onto a leaf it does not prove."""
    assert mine()[SANDBOXED].leaves == ("M12.4.5",)


def test_an_install_without_the_sandbox_is_not_run(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """Delete this and every install that chose no sandbox shows a red row."""
    before = hold_saved({"INSTALL_SERVICES": "none"})
    try:
        assert judged(monkeypatch, SANDBOXED, sandbox_report()) == (
            NOT_RUN,
            services.NO_SANDBOX_HERE,
        )
    finally:
        hold_saved(before)
    assert analyser == []


@pytest.mark.usefixtures("sandbox_on")
def test_a_sandbox_isolated_by_every_witness_and_held_to_its_limits_passes(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """The positive case: docker says gVisor, the kernel says gVisor and no network, and each probe
    is answered as a sandbox that holds. Delete this and a check that refuses everything passes
    every test that follows."""
    use(sandbox_like())
    assert judged(monkeypatch, SANDBOXED, sandbox_report()) == (PASSED, "")
    assert analyser[0].endswith("/health")
    assert len(analyser) == 4


@pytest.mark.usefixtures("sandbox_on")
@pytest.mark.parametrize(
    ("report", "sandbox", "reason"),
    [
        (sandbox_report(runtime="runc"), sandbox_like(), "THE_SANDBOX_IS_NOT_UNDER_GVISOR"),
        (sandbox_report(), sandbox_like(isolated=False), "THE_SANDBOX_IS_NOT_ISOLATED"),
        (sandbox_report(), sandbox_like(network="network:reached"), "A_SANDBOX_LIMIT_DID_NOT_HOLD"),
        (sandbox_report(), sandbox_like(holds=False), "A_SANDBOX_LIMIT_DID_NOT_HOLD"),
    ],
    ids=[
        "docker says not gVisor",
        "the kernel says not gVisor",
        "a network found",
        "time not held",
    ],
)
def test_each_witness_that_disagrees_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
    analyser: list[str],
    report: dict[str, object],
    sandbox: Handler,
    reason: str,
) -> None:
    """Three witnesses and each is decisive alone. Delete this and a sandbox started on docker's
    own runtime, or one whose scripts reach the application, passes on the other two."""
    use(sandbox)
    assert judged(monkeypatch, SANDBOXED, report) == (FAILED, getattr(services, reason))
    del analyser


@pytest.mark.usefixtures("sandbox_on")
def test_a_release_the_step_has_not_reported_is_not_judged(
    monkeypatch: pytest.MonkeyPatch, analyser: list[str]
) -> None:
    """Delete this and a sandbox gone since the last deploy passes on what an older one ran."""
    use(sandbox_like())
    assert judged(monkeypatch, SANDBOXED, None) == (NOT_RUN, services.NOT_REPORTED_FOR_THIS_RELEASE)
    assert analyser == []
