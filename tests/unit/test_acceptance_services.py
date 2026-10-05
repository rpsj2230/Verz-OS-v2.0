"""The install's check for the personal data detector, run against an analyser that is a handler.

The check asks a real HTTP server on the install, so here the server is an `httpx.MockTransport`
whose answers are built from the request the check sent, the way Presidio builds its own: an entity
is found in a sentence only when that sentence carries one and the entity was asked for. So the
check is judged on what it asks as well as on what it does with the answer.

Task ids: M32.2.1.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from brain.install import hold_saved
from brain.ops import acceptance_checks_services as services
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.pii import (
    PRESIDIO_BUILT_INS,
    PRESIDIO_LANGUAGE,
    PRESIDIO_PORT,
    PRESIDIO_PROBES,
    PRESIDIO_SERVICE,
)
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
