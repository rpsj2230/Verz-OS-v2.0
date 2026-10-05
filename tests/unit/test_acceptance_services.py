"""The install's check for the personal data detector, run against an analyser that is a handler.

The check asks a real HTTP server on the install, so here the server is an `httpx.MockTransport`
whose answers are built from the request the check sent, the way Presidio builds its own: an entity
is found in a sentence only when that sentence carries one and the entity was asked for. So the
check is judged on what it asks as well as on what it does with the answer.

Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2
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
