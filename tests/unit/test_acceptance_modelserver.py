"""The install's checks for the model server, run against a report and a server that are stand-ins.

The first check reads what the deploy step reported of the container, so it is judged against a
stored report built the way `brain.ops.overlays.observation` builds one; the second asks the
server's readiness route, so it is judged against an `httpx.MockTransport` whose answer is built
from the request the check sent. Both are shown failing with their own sentence, because a check
nobody has watched fail is a check nobody knows works.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from brain.install import hold_saved
from brain.ops import acceptance_checks_modelserver as modelserver
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.model_server import config_from, effective_limit_mib
from brain.ops.overlays import OBSERVED_KEY
from brain.settings import settings_from

MODULE = "brain.ops.acceptance_checks_modelserver"
LIMITED = "the_model_server_runs_under_the_limit_this_install_costed"
READY = "the_model_server_reports_ready_for_exactly_the_parts_chosen"

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


@pytest.fixture
def on() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "modelserver"})
    yield
    hold_saved(before)


def report(**changed: object) -> dict[str, object]:
    """The step's report for this release: the model server running, healthy and at its limit."""
    body: dict[str, object] = {
        "limit_mib": effective_limit_mib(config_from()),
        "state": "running",
        "health": "healthy",
    }
    body.update(changed)
    return {
        "commit": settings_from({}).resolved_commit(),
        "services": {"inference-server": body},
    }


def judged(monkeypatch: pytest.MonkeyPatch, row: object | None) -> tuple[str, str]:
    from brain.ops import setting_store

    async def held(session: object, namespace: str) -> dict[str, object]:
        assert namespace == "overlay"
        return {} if row is None else {OBSERVED_KEY: SimpleNamespace(value=row)}

    monkeypatch.setattr(setting_store, "read_namespace", held)
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[LIMITED].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def test_both_checks_claim_the_leaf_the_model_server_serves() -> None:
    """Delete this and either check can be moved onto a leaf it says nothing about, so a server
    that runs closes a leaf on evidence that never looked at it."""
    assert mine()[LIMITED].leaves == ("M7.3.3",)
    assert mine()[READY].leaves == ("M7.3.3",)


def test_an_install_that_has_not_switched_the_model_server_on_is_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not failed: an install without the server has nothing wrong, and a red row it cannot act
    on teaches an owner to ignore the page. Delete this and every install that chose not to run
    one shows two.

    Asked of both checks, and with a report that would otherwise fail, so the silence is the
    switch's and not the report's."""
    before = hold_saved({})
    try:
        assert judged(monkeypatch, report(state="exited")) == (
            NOT_RUN,
            modelserver.NO_MODEL_SERVER_HERE,
        )
        harness = Harness(
            run="0a1b2c3d",
            now=LONG_AGO,
            settings=settings_from({}),
            connection=None,  # type: ignore[arg-type]
        )
        with pytest.raises(Exception) as raised:
            asyncio.run(mine()[READY].run(harness))
        assert reason_for(raised.value) == (NOT_RUN, modelserver.NO_MODEL_SERVER_HERE)
    finally:
        hold_saved(before)


@pytest.mark.usefixtures("on")
def test_a_report_from_no_deploy_yet_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switched on and not yet reported is neither right nor wrong. Delete this and the first
    install to switch the server on is told it failed before a deploy has looked."""
    assert judged(monkeypatch, None) == (NOT_RUN, modelserver.NOT_REPORTED_FOR_THIS_RELEASE)
    stale = {**report(), "commit": "an-earlier-release"}
    assert judged(monkeypatch, stale) == (NOT_RUN, modelserver.NOT_REPORTED_FOR_THIS_RELEASE)


@pytest.mark.usefixtures("on")
def test_a_server_running_healthy_at_the_limit_the_settings_cost_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case: without it a check that refuses everything passes every refusal test
    here. Delete this and a limit check that always fails goes unnoticed."""
    assert judged(monkeypatch, report()) == (PASSED, "")


@pytest.mark.usefixtures("on")
@pytest.mark.parametrize(
    ("changed", "sentence"),
    [
        ({"state": "exited"}, modelserver.THE_MODEL_SERVER_IS_NOT_RUNNING),
        ({"health": "unhealthy"}, modelserver.THE_MODEL_SERVER_IS_NOT_RUNNING),
        ({"limit_mib": 4096}, modelserver.THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT),
        ({"limit_mib": 0}, modelserver.THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT),
    ],
    ids=["stopped", "unhealthy", "larger-than-costed", "unlimited"],
)
def test_a_server_that_is_down_or_held_to_a_different_limit_fails_with_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch, changed: dict[str, object], sentence: str
) -> None:
    """Both directions of the limit, because a server running under more memory than was costed
    takes the neighbours' and one running under less is killed by its first large request.
    Delete this and the limit the plan costed and the limit the server runs under can part with
    every test green."""
    assert judged(monkeypatch, report(**changed)) == (FAILED, sentence)


@pytest.mark.usefixtures("on")
def test_a_report_with_no_model_server_in_it_fails_as_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switched on, and the server's docker lists nothing of it, is not a server that is fine.
    Delete this and a server that never started passes by being absent."""
    empty = {"commit": settings_from({}).resolved_commit(), "services": {}}

    assert judged(monkeypatch, empty) == (FAILED, modelserver.THE_MODEL_SERVER_IS_NOT_RUNNING)


# ------------------------------------------------------------------------ the readiness route
@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every client the check opens is pointed at whichever handler `answer` installed, and every
    address it asked is recorded."""
    seen: list[str] = []
    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        handler: Handler = getattr(client, "handler")  # noqa: B009 - set by `answer`

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return handler(request)

        kwargs["transport"] = httpx.MockTransport(recording)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    yield seen


def answer(handler: Handler) -> None:
    httpx.AsyncClient.handler = handler  # type: ignore[attr-defined]


def ready_judged() -> tuple[str, str]:
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[READY].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def says(body: object, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


@pytest.mark.usefixtures("on")
def test_a_server_that_is_ready_for_exactly_the_parts_chosen_passes_and_loads_nothing(
    server: list[str],
) -> None:
    """The positive case, and it says where it asked: the readiness route, once, by the
    install's own address, with a GET that carries nothing. Delete this and a check that sent a
    document to prove a part works would pass, and would hold the memory it is there to show is
    given back."""
    answer(says({"ready": True, "parts": ["embedding"], "loaded": None, "gaps": []}))

    assert ready_judged() == (PASSED, "")
    assert server == ["http://inference-server:8080/ready"]


@pytest.mark.usefixtures("on")
@pytest.mark.parametrize(
    ("body", "status", "sentence"),
    [
        (
            {"ready": False, "parts": ["embedding"], "gaps": ["the embedding part is not here"]},
            503,
            modelserver.A_PART_IS_NOT_READY,
        ),
        (
            {"ready": True, "parts": ["embedding", "layout"], "gaps": []},
            200,
            modelserver.IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN,
        ),
        (
            {"ready": True, "parts": [], "gaps": []},
            200,
            modelserver.IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN,
        ),
        (["not", "a", "mapping"], 200, modelserver.THE_MODEL_SERVER_DID_NOT_ANSWER),
    ],
    ids=["a-part-is-missing", "runs-more", "runs-none", "garbled"],
)
def test_a_server_not_ready_or_running_other_parts_fails_with_its_own_sentence(
    server: list[str], body: object, status: int, sentence: str
) -> None:
    """A server that runs a part nobody chose holds memory nobody costed, which is what the
    design exists to prevent, so it fails and not merely warns. Delete this and the parts a
    server runs and the parts an install chose can part with every test green."""
    answer(says(body, status))

    assert ready_judged() == (FAILED, sentence)
    assert server


@pytest.mark.usefixtures("on")
def test_a_server_that_does_not_answer_at_all_fails_and_not_as_unready(server: list[str]) -> None:
    """Switched on and silent is a different failure from not ready, and sends somebody to a
    different half of the problem. Delete this and an unreachable server reads as one with a
    missing weights file."""

    def silent(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    answer(silent)

    assert ready_judged() == (FAILED, modelserver.THE_MODEL_SERVER_DID_NOT_ANSWER)
    assert server == ["http://inference-server:8080/ready"]


@pytest.mark.usefixtures("on")
def test_the_parts_it_is_held_to_are_the_ones_the_settings_name(server: list[str]) -> None:
    """The comparison is with this install's own choice and not with the default, so an install
    that chose two parts is held to two. Delete this and the check compares against a constant
    and passes only for the default choice."""
    before = hold_saved({"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "embedding,ocr"})
    try:
        answer(says({"ready": True, "parts": ["embedding", "ocr"], "gaps": []}))
        assert ready_judged() == (PASSED, "")
        answer(says({"ready": True, "parts": ["embedding"], "gaps": []}))
        assert ready_judged() == (FAILED, modelserver.IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN)
    finally:
        hold_saved(before)
    assert server


# ------------------------------------------------------------------------ the revision it holds
REVISION = "the_declared_embedding_revision_is_the_one_the_server_holds"
HELD = "abc123def456"


def revision_judged() -> tuple[str, str]:
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[REVISION].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


@pytest.fixture
def declared() -> Iterator[None]:
    before = hold_saved({"INSTALL_SERVICES": "modelserver", "INSTALL_EMBEDDING_REVISION": HELD})
    yield
    hold_saved(before)


def test_the_revision_check_claims_the_leaf_the_embedding_part_serves() -> None:
    """Delete this and the check can be moved onto a leaf it says nothing about."""
    assert mine()[REVISION].leaves == ("M7.3.3",)


def test_an_install_that_cannot_be_compared_is_not_run_with_the_reason_that_is_true(
    server: list[str],
) -> None:
    """No server, no embedding part and no declared revision each leave nothing to compare, and
    each says which, because a red row an install cannot act on teaches its owner to ignore the
    page. Delete this and any of them shows a failure.

    Nothing is asked of a server in any of the three."""
    before = hold_saved({})
    try:
        assert revision_judged() == (NOT_RUN, modelserver.NO_MODEL_SERVER_HERE)
        hold_saved({"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "ocr"})
        assert revision_judged() == (NOT_RUN, modelserver.NO_EMBEDDING_PART_HERE)
        hold_saved({"INSTALL_SERVICES": "modelserver"})
        assert revision_judged() == (
            NOT_RUN,
            modelserver.NO_EMBEDDING_REVISION_IS_DECLARED_HERE,
        )
    finally:
        hold_saved(before)
    assert server == []


@pytest.mark.usefixtures("declared")
def test_a_declared_revision_the_server_says_it_holds_passes(server: list[str]) -> None:
    """The positive case, asked of the readiness route and nothing else.

    Delete this and a check that fails everything passes every refusal below."""
    answer(says({"ready": True, "parts": ["embedding"], "revisions": {"embedding": HELD}}))

    assert revision_judged() == (PASSED, "")
    assert server == ["http://inference-server:8080/ready"]


@pytest.mark.usefixtures("declared")
@pytest.mark.parametrize(
    ("body", "sentence"),
    [
        (
            {"revisions": {"embedding": "000000000000"}},
            modelserver.THE_DECLARED_REVISION_IS_NOT_THE_HELD_ONE,
        ),
        ({"revisions": {"embedding": None}}, modelserver.THE_SERVER_STATES_NO_REVISION),
        ({"revisions": {}}, modelserver.THE_SERVER_STATES_NO_REVISION),
        ({}, modelserver.THE_SERVER_STATES_NO_REVISION),
        ({"revisions": {"embedding": ""}}, modelserver.THE_SERVER_STATES_NO_REVISION),
    ],
    ids=["other-weights", "none-recorded", "empty", "absent", "blank"],
)
def test_a_revision_that_differs_or_is_not_stated_fails_with_its_own_sentence(
    server: list[str], body: dict[str, object], sentence: str
) -> None:
    """Different weights and no statement of weights are two failures with two remedies: set the
    setting, or fetch the file.

    Delete this and every vector is refused for a revision nobody told the owner to change."""
    answer(says(body))

    assert revision_judged() == (FAILED, sentence)


@pytest.mark.usefixtures("declared")
def test_a_server_that_does_not_answer_fails_the_revision_check_as_unanswering(
    server: list[str],
) -> None:
    """Silent is the same sentence as the readiness check gives, not a revision that differs.

    Delete this and an unreachable server reads as the owner having declared the wrong thing."""

    def silent(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    answer(silent)

    assert revision_judged() == (FAILED, modelserver.THE_MODEL_SERVER_DID_NOT_ANSWER)
