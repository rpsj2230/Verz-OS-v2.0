"""The install's checks for the running automation canvas: not run where it is off, judged where it
is on, and each able to fail with its own sentence.

They read what the deploy step reported for this release, so here the report is a stored row handed
through a stand-in for the setting reader and the install's switch is held with `hold_saved`, as
`tests/unit/test_acceptance_services.py` does for the trace ledger. Nothing is asked of docker,
which is the point: the facts are the step's, the judgement is these checks', and every way the
canvas can break the boundary is a row a test writes.

Task ids: M32.6.1.1, M32.6.1.2, M32.6.1.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from structlog.testing import capture_logs

from brain.install import hold_saved
from brain.ops import acceptance_checks_automation_canvas as canvas
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.automation import EGRESS_ALLOWLIST
from brain.ops.automation_report import FACTS_KEY, CanvasFacts, observation
from brain.ops.overlays import BY_NAME, OBSERVED_KEY
from brain.ops.wiring import component
from brain.settings import settings_from

MODULE = "brain.ops.acceptance_checks_automation_canvas"
RUNNING = "the_canvas_runs_as_three_services_each_held_to_its_budget"
BOUNDARY = "the_canvas_has_no_way_out_but_its_proxy_and_no_foreign_secret"
SWITCH = "the_canvas_runs_where_the_setting_names_it_and_nowhere_else"

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

CANVAS = BY_NAME["automation"].components


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def release() -> str:
    return settings_from({}).resolved_commit()


def reported(**changed: Mapping[str, object]) -> dict[str, object]:
    """The step's services report for this release: the canvas's three services running, healthy
    and at budget, with `changed` overriding one service (an empty dict removes it)."""
    services: dict[str, object] = {
        name: {"limit_mib": component(name).memory_mib, "state": "running", "health": "healthy"}
        for name in CANVAS
    }
    services["presidio-analyzer"] = {"limit_mib": 1024, "state": "running", "health": "healthy"}
    for name, body in changed.items():
        if body:
            services[name] = {**services[name], **body}  # type: ignore[dict-item]
        else:
            del services[name]
    return {"commit": release(), "services": services}


def facts(**changed: Any) -> dict[str, object]:
    """The step's report of the canvas for this release: a sound canvas with `changed` broken."""
    sound = CanvasFacts(
        networks=("u-overlays_automation", "brain-tool-api"),
        proxy_networks=("u-overlays_automation", "u-overlays_egress"),
        env_names=("AP_ENCRYPTION_KEY", "AP_JWT_SECRET", "AP_POSTGRES_PASSWORD", "PATH"),
        connection_strings=0,
        default_routes=0,
        allowlist=tuple(sorted(EGRESS_ALLOWLIST)),
        probe="HTTP/1.1 403 Forbidden",
    )
    return observation(replace(sound, **changed), commit=release())


def judged(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    *,
    services: object | None = None,
    canvas_facts: object | None = None,
) -> tuple[str, str]:
    """One check against stored reports, read through a stand-in for the setting reader."""
    from brain.ops import setting_store

    rows = {OBSERVED_KEY: services, FACTS_KEY: canvas_facts}

    async def held(session: object, namespace: str) -> dict[str, object]:
        assert namespace == "overlay"
        return {
            key: SimpleNamespace(value=value) for key, value in rows.items() if value is not None
        }

    monkeypatch.setattr(setting_store, "read_namespace", held)
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[name].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


@pytest.fixture
def canvas_on() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "presidio,automation"})
    yield
    hold_saved(before)


@pytest.fixture
def canvas_off() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "presidio"})
    yield
    hold_saved(before)


def test_each_check_claims_its_own_leaf_and_only_that_one() -> None:
    """Delete this and one check can drift onto another's leaf, so a canvas that runs closes the
    leaf about its network on evidence that never looked at a network."""
    assert mine()[RUNNING].leaves == ("M32.6.1.1",)
    assert mine()[BOUNDARY].leaves == ("M32.6.1.2",)
    assert mine()[SWITCH].leaves == ("M32.6.1.4",)
    assert set(mine()) == {RUNNING, BOUNDARY, SWITCH}


# ------------------------------------------------------------------ not switched on
@pytest.mark.usefixtures("canvas_off")
@pytest.mark.parametrize("name", [RUNNING, BOUNDARY])
def test_an_install_without_the_canvas_is_not_run_by_the_two_that_judge_it(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Not switched on is not wrong. Delete this and every install that chose not to run the canvas
    shows two red rows it cannot act on."""
    assert judged(monkeypatch, name, services=reported(), canvas_facts=facts()) == (
        NOT_RUN,
        canvas.NO_CANVAS_HERE,
    )


# ----------------------------------------------------------- not reported for this release
@pytest.mark.usefixtures("canvas_on")
@pytest.mark.parametrize("name", [RUNNING, SWITCH])
def test_a_services_report_from_another_release_or_none_is_not_judged(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Only this release's report counts. Delete this and a canvas stopped since the last deploy
    passes on what an older release saw."""
    stale = {**reported(), "commit": "an-older-release"}
    assert judged(monkeypatch, name, services=None) == (
        NOT_RUN,
        canvas.THE_SERVICES_ARE_NOT_REPORTED,
    )
    assert judged(monkeypatch, name, services=stale) == (
        NOT_RUN,
        canvas.THE_SERVICES_ARE_NOT_REPORTED,
    )


@pytest.mark.usefixtures("canvas_on")
def test_a_canvas_report_from_another_release_or_none_is_not_judged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the boundary is judged on facts a previous deploy gathered about a container
    that may no longer exist."""
    stale = {**facts(), "commit": "an-older-release"}
    for row in (None, stale, {"commit": release()}):
        assert judged(monkeypatch, BOUNDARY, canvas_facts=row) == (
            NOT_RUN,
            canvas.THE_CANVAS_FACTS_ARE_NOT_REPORTED,
        )


# ---------------------------------------------------------------------------- M32.6.1.1
@pytest.mark.usefixtures("canvas_on")
def test_three_running_healthy_services_at_their_budget_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case, beside another overlay's service in the same report. Delete this and a
    check that refuses everything passes every other test here."""
    assert judged(monkeypatch, RUNNING, services=reported()) == (PASSED, "")


@pytest.mark.usefixtures("canvas_on")
@pytest.mark.parametrize("service", CANVAS)
@pytest.mark.parametrize(
    "broken",
    [{"health": "unhealthy"}, {"health": "starting"}, {"state": "restarting"}, {}],
    ids=["unhealthy", "starting", "restarting", "absent"],
)
def test_any_of_the_three_services_not_running_and_healthy_fails_the_set(
    monkeypatch: pytest.MonkeyPatch, service: str, broken: dict[str, object]
) -> None:
    """Each way a container is not serving, on each of the three. Delete this and a canvas whose
    proxy never came up, or whose database is restarting, passes as a running set."""
    row = reported(**{service: broken})
    with capture_logs() as logged:
        assert judged(monkeypatch, RUNNING, services=row) == (
            FAILED,
            canvas.A_CANVAS_SERVICE_IS_NOT_RUNNING,
        )
    [line] = [one for one in logged if one["event"] == "acceptance.canvas_services"]
    assert line["down"] == [service]


@pytest.mark.usefixtures("canvas_on")
@pytest.mark.parametrize("service", CANVAS)
@pytest.mark.parametrize("limit", [0, 1, 99999], ids=["unlimited", "under", "over"])
def test_a_service_under_any_limit_but_its_budget_fails_the_limits(
    monkeypatch: pytest.MonkeyPatch, service: str, limit: int
) -> None:
    """No limit is the failure the leaf's second half exists for, and a limit either side of the
    budget is a container somebody resized without deciding where the memory comes from. Delete
    this and an unlimited canvas closes the leaf."""
    budget = component(service).memory_mib
    assert limit != budget
    row = reported(**{service: {"limit_mib": limit}})
    assert judged(monkeypatch, RUNNING, services=row) == (
        FAILED,
        canvas.A_CANVAS_SERVICE_IS_NOT_HELD_TO_ITS_BUDGET,
    )


@pytest.mark.usefixtures("canvas_on")
def test_the_three_services_are_the_three_the_canvas_is_costed_as() -> None:
    """Delete this and a fourth container added to the canvas's file is one the check never asks
    after, because the check reads the overlay's own list and that list drifted."""
    assert set(CANVAS) == {"activepieces", "automation-egress", "automation-db"}


# ---------------------------------------------------------------------------- M32.6.1.2
@pytest.mark.usefixtures("canvas_on")
def test_a_canvas_that_keeps_the_boundary_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive case. Delete this and a check that fails every canvas passes every other test
    here."""
    assert judged(monkeypatch, BOUNDARY, canvas_facts=facts()) == (PASSED, "")


@pytest.mark.usefixtures("canvas_on")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        (
            {"env_names": ("AP_JWT_SECRET", "OPENAI_API_KEY")},
            canvas.THE_CANVAS_HOLDS_A_CREDENTIAL_IT_WAS_NOT_GIVEN,
        ),
        (
            {"env_names": ("BRAIN_DATABASE_URL",)},
            canvas.THE_CANVAS_HOLDS_A_CREDENTIAL_IT_WAS_NOT_GIVEN,
        ),
        ({"connection_strings": 1}, canvas.THE_CANVAS_HOLDS_A_CREDENTIAL_IT_WAS_NOT_GIVEN),
        (
            {"networks": ("u-overlays_automation", "u_default")},
            canvas.THE_CANVAS_IS_ON_A_NETWORK_THAT_IS_NOT_ITS_OWN,
        ),
        (
            {"proxy_networks": ("u-overlays_automation", "u_default")},
            canvas.THE_CANVAS_IS_ON_A_NETWORK_THAT_IS_NOT_ITS_OWN,
        ),
        ({"default_routes": 1}, canvas.THE_CANVAS_HAS_A_WAY_OUT_THAT_IS_NOT_ITS_PROXY),
        ({"default_routes": None}, canvas.THE_CANVAS_ROUTES_WERE_NOT_READ),
        (
            {"allowlist": (*sorted(EGRESS_ALLOWLIST), "extra.example")},
            canvas.THE_PROXY_RUNS_ANOTHER_ALLOWLIST,
        ),
        (
            {"probe": "HTTP/1.1 200 Connection established"},
            canvas.THE_PROXY_DID_NOT_REFUSE_AN_UNLISTED_HOST,
        ),
        ({"probe": ""}, canvas.THE_PROXY_DID_NOT_REFUSE_AN_UNLISTED_HOST),
    ],
)
def test_each_way_the_running_canvas_breaks_the_boundary_fails_with_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch, broken: dict[str, Any], reason: str
) -> None:
    """Ten breaks of a sound canvas, each judged on the facts the step reported. Delete this and a
    canvas holding the application's database URL, joined to the application's network, with a
    route out, or with an open proxy, passes as sandboxed."""
    assert judged(monkeypatch, BOUNDARY, canvas_facts=facts(**broken)) == (FAILED, reason)


@pytest.mark.usefixtures("canvas_on")
def test_the_log_names_the_variables_and_the_reason_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A foreign variable's name goes to the worker's log and not into the sentence a page serves.
    Delete this and an owner is told a canvas holds a credential and not which, or the sentence
    carries the name."""
    with capture_logs() as logged:
        outcome, reason = judged(
            monkeypatch, BOUNDARY, canvas_facts=facts(env_names=("AP_JWT_SECRET", "OPENAI_API_KEY"))
        )
    assert outcome == FAILED
    assert "OPENAI" not in reason
    [line] = [one for one in logged if one["event"] == "acceptance.canvas_gaps"]
    assert line["variables"] == ["OPENAI_API_KEY"]
    assert line["gaps"] == ["foreign_credential"]


# ---------------------------------------------------------------------------- M32.6.1.4
@pytest.mark.usefixtures("canvas_on")
def test_a_named_canvas_that_runs_passes_the_switch_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a check that fails every install passes every other test here."""
    assert judged(monkeypatch, SWITCH, services=reported()) == (PASSED, "")


@pytest.mark.usefixtures("canvas_on")
@pytest.mark.parametrize("service", CANVAS)
@pytest.mark.parametrize("broken", [{"state": "exited"}, {}], ids=["stopped", "absent"])
def test_a_canvas_the_setting_names_and_that_is_not_running_fails(
    monkeypatch: pytest.MonkeyPatch, service: str, broken: dict[str, object]
) -> None:
    """The setting says on and docker says no, for each of the three services. Delete this and a
    setting that does nothing, which is a switch nobody can turn, closes the leaf."""
    row = reported(**{service: broken})
    assert judged(monkeypatch, SWITCH, services=row) == (
        FAILED,
        canvas.THE_CANVAS_IS_NAMED_AND_NOT_RUNNING,
    )


@pytest.mark.usefixtures("canvas_off")
def test_an_install_that_does_not_name_the_canvas_and_runs_none_passes_the_switch_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The report holds another overlay's service and none of the canvas's. Delete this and the
    check can only ever pass on an install that runs the canvas, so an install that did not choose
    it can never show the switch working in the other direction."""
    off = reported(**{name: {} for name in CANVAS})
    assert judged(monkeypatch, SWITCH, services=off) == (PASSED, "")


@pytest.mark.usefixtures("canvas_off")
@pytest.mark.parametrize("service", CANVAS)
def test_a_canvas_that_runs_where_the_setting_does_not_name_it_fails(
    monkeypatch: pytest.MonkeyPatch, service: str
) -> None:
    """One of the three still running after the setting stopped naming it. Delete this and a fork
    that runs the canvas on every install whatever it says passes as the canvas being optional."""
    row = reported(**{name: {} for name in CANVAS if name != service})
    assert judged(monkeypatch, SWITCH, services=row) == (
        FAILED,
        canvas.THE_CANVAS_RUNS_AND_IS_NOT_NAMED,
    )


@pytest.mark.usefixtures("canvas_off")
def test_an_install_with_no_report_for_this_release_is_not_judged_on_the_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an install that runs no optional service at all, so the step reports
    nothing, is told the canvas is correctly off on evidence that does not exist."""
    assert judged(monkeypatch, SWITCH, services=None) == (
        NOT_RUN,
        canvas.THE_SERVICES_ARE_NOT_REPORTED,
    )


def test_the_canvas_ships_off() -> None:
    """The setting's declared default names no optional service. Delete this and a release that
    changes the default switches the canvas on for every install that did not choose it."""
    from brain.ops.overlays import NO_SERVICES, switched_on

    assert switched_on(NO_SERVICES) == ()
    assert BY_NAME["automation"] not in switched_on("presidio")
    assert BY_NAME["automation"] in switched_on("automation")


# ------------------------------------------------------------------- on a real database
def run_on_a_database(url: str) -> dict[str, tuple[str, str]]:
    """The three checks as the worker runs them, over PostgreSQL at head."""
    import sys

    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine
    from tests.unit.test_acceptance import INSTALL

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                tuple(mine().values()),
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.mark.needs_db
def test_on_an_install_that_has_not_named_the_canvas_all_three_say_so_and_leave_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Against PostgreSQL at head with the setting's own default: the two that judge the running
    canvas are not run and say why, and the switch check, which has no report from a deploy that
    started nothing, says it has nothing to judge. Delete this and the whole-suite install test is
    the only thing that finds a check whose default outcome on a fresh install is a failure."""
    from tests.unit.test_acceptance import INSTALL, at_head, counts

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    with at_head("brain_acceptance_canvas") as url:
        before = counts(url)
        outcomes = run_on_a_database(url)
        after = counts(url)
    assert outcomes == {
        RUNNING: (NOT_RUN, canvas.NO_CANVAS_HERE),
        BOUNDARY: (NOT_RUN, canvas.NO_CANVAS_HERE),
        SWITCH: (NOT_RUN, canvas.THE_SERVICES_ARE_NOT_REPORTED),
    }
    assert after == before
