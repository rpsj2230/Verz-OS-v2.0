"""The egress acceptance check: registered, passing on the install's own drivers, and able to fail.

It reads no database, so it is run here on a harness with no connection, as the worker would run
it: on a profile with no analyser, where the rules' scrub is what is checked; with an analyser that
answers, where an English name has to leave as a placeholder too; with one that does not answer,
which fails with its own sentence; and against the transport and the scrub broken where they prove.

Task ids: M32.2.2.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_egress
from brain.ops.acceptance import FAILED, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.pii import Detection, EntityKind
from brain.settings import settings_from
from tests.unit.test_acceptance import checks_in

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_egress"
NAME = "a_hosted_model_is_sent_placeholders_and_the_reader_the_values"

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def ran() -> tuple[str, str]:
    # The check reads nothing: it is handed a harness with no connection on purpose.
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[NAME].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


def with_an_analyser(monkeypatch: pytest.MonkeyPatch, answers: bool) -> None:
    """The profile deploys an analyser, which finds the check's English name or does not answer."""
    import brain.ops.egress as egress
    import brain.ops.pii as pii
    from brain.ops.egress import AnalyserUnavailableError

    monkeypatch.setattr(pii, "analyzer_address", lambda profile, configured="": "http://a.test")

    def install_analyser(address: str, client: Any) -> Any:
        def detect(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
            if not answers:
                raise AnalyserUnavailableError
            at = text.find(acceptance_egress.ENGLISH_NAME)
            if at < 0:
                return ()
            end = at + len(acceptance_egress.ENGLISH_NAME)
            return (Detection(kind=EntityKind.UNPATTERNED_NAME, start=at, end=end, confidence=0.9),)

        return detect

    monkeypatch.setattr(egress, "analyser", install_analyser)


def test_the_egress_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M32.2.2.1",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_egress_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


def test_on_a_profile_with_no_analyser_the_rules_scrub_passes() -> None:
    """The positive run on lite, the owner's profile: the NRIC, email, number and patronymic name
    leave as placeholders and come back. Delete this and the check can refuse the install's own
    transport, which reads on the Install page as personal data leaving."""
    assert ran() == (PASSED, "")


def test_with_an_analyser_that_answers_an_english_name_leaves_as_a_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive run where the profile deploys the analyser. Delete this and the check can
    fail every install that deploys one."""
    with_an_analyser(monkeypatch, answers=True)
    assert ran() == (PASSED, "")


def test_with_an_analyser_that_does_not_answer_the_check_fails_saying_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An install that deploys an analyser it cannot reach sends every question's names to the
    provider, and the check says so rather than passing on the rules. Delete this and a dead
    analyser is invisible on the Install page."""
    with_an_analyser(monkeypatch, answers=False)
    assert ran() == (FAILED, acceptance_egress.ANALYSER_DID_NOT_FIND_A_NAME)


@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("unscrubbed", "a value a hosted model would have been sent was not scrubbed"),
        ("kept", "the answer did not come back with its values put back"),
    ],
)
def test_the_egress_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks: the transport posting a third party's body without the scrub, and the scrub
    handing the reader the placeholders. Each fails the check with its own sentence. Delete this
    and the check can pass with either property gone."""
    import brain.models.wire as wire
    import brain.ops.egress as egress

    if broken == "unscrubbed":
        monkeypatch.setattr(
            wire, "third_party_call", lambda request, send, *, provider, detector: send(request)
        )
    else:
        monkeypatch.setattr(egress.EgressScrub, "put_back", lambda self, answer: answer)
    assert ran() == (FAILED, reason)
