"""The credential install check: what it names, that it passes on the product as it is, and that it
fails for each way a value could reach somewhere it must not.

It needs no database (the driver's ledger is a quiet stand-in and the recordings go to memory). Each
failure is one defect injected into the function the driver, the recording or the vault borrow
calls, and the check must fail with its own sentence.

Task ids: M19.4.4, M19.1.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain.browsing import driver, observation, recording
from brain.browsing.credentials import Binding
from brain.browsing.recording import record as real_record
from brain.ops import acceptance_checks_browser_credentials as module
from brain.ops.acceptance import PASSED, CheckFailedError, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_credentials"
NAME = "a_credential_reaches_the_page_and_is_kept_nowhere"
HARNESS = SimpleNamespace(run="r1", trace_id="t-1", now=datetime(2999, 1, 1, 12, tzinfo=UTC))


def run_it() -> None:
    asyncio.run(module.a_credential_reaches_the_page_and_is_kept_nowhere(HARNESS))  # type: ignore[arg-type]


def fails_with(sentence: str) -> None:
    with pytest.raises(CheckFailedError) as failed:
        run_it()
    assert failed.value.reason == sentence


def test_the_check_names_the_credential_leaves_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose a leaf with the page showing the same row, or sit outside
    the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (NAME, ("M19.4.4", "M19.1.4"))
    ]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_value_the_check_hides_needs_escaping_in_a_line_and_is_long_enough_to_scrub() -> None:
    """The value is chosen to be the hard case: a quote and a backslash, which a line holds
    escaped, and not shorter than the shortest value a scrub will search for. Delete this and the
    value is made plain, and a scrub that only finds the plain form passes."""
    import json

    from brain.browsing.credentials import MIN_SCRUBBABLE

    assert json.dumps(module.SECRET)[1:-1] != module.SECRET
    assert len(module.SECRET) >= MIN_SCRUBBABLE


def test_the_check_passes_on_the_product_as_it_is() -> None:
    """The positive case for every failure below. Delete this and a check that fails on a healthy
    product satisfies all of them."""
    run_it()


def test_a_transcript_that_is_not_scrubbed_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a recording that keeps what the runner was sent, value and all, passes."""
    monkeypatch.setattr(recording, "scrub_outbound", lambda text, secrets: (text, ()))

    fails_with(module.A_VALUE_WAS_KEPT)


def test_a_lease_never_given_back_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a borrow that stopped revoking in its `finally` passes."""
    monkeypatch.setattr("brain.ops.secrets._revoke_quietly", lambda vault, lease: None)

    fails_with(module.A_LEASE_WAS_LEFT)


def test_a_placeholder_that_is_not_resolved_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a driver that types the placeholder itself, or nothing, passes."""
    monkeypatch.setattr(driver, "resolve", lambda *args, **kw: "")

    fails_with(module.A_VALUE_DID_NOT_REACH_THE_PAGE)


def test_a_binding_that_substitutes_on_any_origin_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a binding that stopped being tied to its origin passes."""
    monkeypatch.setattr(Binding, "substitutes_on", lambda self, origin: True)

    fails_with(module.A_VALUE_WENT_TO_THE_WRONG_ORIGIN)


def test_a_page_that_shows_the_value_back_and_is_not_reported_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a driver that stopped reporting a value found in what the runner sent back
    passes: the incident is the only signal that something upstream failed."""

    def quiet(*args: Any, **kw: Any) -> Any:
        return replace(real_record(*args, **kw), leaked=())

    monkeypatch.setattr("brain.browsing.driver.record", quiet)
    monkeypatch.setattr(driver, "scrub_history", lambda messages, secrets: (tuple(messages), ()))

    fails_with(module.A_SHOWN_VALUE_WAS_NOT_AN_INCIDENT)


def test_a_type_that_could_carry_a_picture_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and the structural guard on observations is a function nothing on an install
    asks."""
    monkeypatch.setattr(observation, "vision_gaps", lambda observed=(): ("Snapshot.picture",))

    fails_with(module.AN_OBSERVATION_HELD_A_PICTURE)


def test_a_value_taken_without_a_lease_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a driver that learnt the value from somewhere that is not the vault
    passes."""
    monkeypatch.setattr(driver, "resolve", lambda *args, **kw: module.SECRET)

    fails_with(module.A_LEASE_WAS_LEFT)


def test_a_run_that_stores_nothing_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a driver that stopped writing recordings passes a check that only asks
    whether what was written holds the value."""
    monkeypatch.setattr(driver, "write", lambda backend, recording: ())

    fails_with(module.A_VALUE_WAS_KEPT)


def test_a_clean_run_reported_as_leaking_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a driver that cries incident on every run passes, which makes the real one
    unreadable."""
    monkeypatch.setattr(driver, "scrub_history", lambda messages, secrets: (tuple(messages), (0,)))

    fails_with(module.A_VALUE_WAS_KEPT)


def test_a_transcript_that_scrubs_the_typed_line_and_not_the_shown_one_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page that shows the value back is the case a scrub that only knows the line it sent
    misses. Delete this and a scrub that skips snapshots passes."""
    real = vars(recording)["scrub_outbound"]

    def skip_the_echo(text: str, secrets: Any) -> Any:
        if "Welcome" in text:
            return text, ()
        return real(text, secrets)

    monkeypatch.setattr("brain.browsing.recording.scrub_outbound", skip_the_echo)

    fails_with(module.A_VALUE_WAS_KEPT)


def test_a_binding_that_issues_a_lease_for_another_origin_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The origin is checked before the vault is asked, so a refusal never causes a credential to
    be issued. Delete this and a substitution that asks first and refuses after passes."""
    from datetime import timedelta

    real = vars(driver)["resolve"]

    def issue_then_refuse(placeholder: str, bindings: Any, **kw: Any) -> str:
        binding = bindings.get(placeholder)
        if not binding.substitutes_on(kw["origin"]):
            kw["vault"].issue(binding.ref, timedelta(seconds=30))
        return str(real(placeholder, bindings, **kw))

    monkeypatch.setattr(driver, "resolve", issue_then_refuse)

    fails_with(module.A_VALUE_WENT_TO_THE_WRONG_ORIGIN)


def test_a_credential_typed_on_another_origin_without_a_lease_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a substitution that no longer compares the origin, and takes no lease for
    the wrong one either, passes a check that asks only whether a lease was issued."""
    real = vars(driver)["resolve"]

    def free_elsewhere(placeholder: str, bindings: Any, **kw: Any) -> str:
        if not bindings.get(placeholder).substitutes_on(kw["origin"]):
            return module.SECRET
        return str(real(placeholder, bindings, **kw))

    monkeypatch.setattr(driver, "resolve", free_elsewhere)

    fails_with(module.A_VALUE_WENT_TO_THE_WRONG_ORIGIN)


def _rewritten(monkeypatch: pytest.MonkeyPatch, change: Any) -> None:
    def record(*args: Any, **kw: Any) -> Any:
        made = real_record(*args, **kw)
        return replace(made, entries=tuple((d, change(t)) for d, t in made.entries))

    monkeypatch.setattr("brain.browsing.driver.record", record)


def test_a_snapshot_that_carries_a_picture_field_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an observation that arrives with a picture beside its tree passes."""
    import json

    def with_picture(text: str) -> str:
        parsed = json.loads(text)
        if parsed.get("kind") == "snapshot":
            parsed["picture"] = "aGVsbG8="
        return json.dumps(parsed, separators=(",", ":"), sort_keys=True)

    _rewritten(monkeypatch, with_picture)

    fails_with(module.AN_OBSERVATION_HELD_A_PICTURE)


def test_a_transcript_with_no_snapshot_in_it_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a check that found no snapshot to inspect passes as though it had found
    clean ones."""
    _rewritten(monkeypatch, lambda text: text.replace('"kind":"snapshot"', '"kind":"frame"'))

    fails_with(module.AN_OBSERVATION_HELD_A_PICTURE)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_credentials") as url:
        yield url


@pytest.mark.needs_db
def test_the_check_passes_as_the_worker_runs_it_and_leaves_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The module as the worker runs it**, through the harness and over a migrated database.
    Delete this and a check that passes called directly but not through the harness, or one that
    writes a row, reaches the owner first."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    before = counts(install)

    assert run_checks(install, registered((MODULE,)))[NAME] == (PASSED, "")
    assert counts(install) == before
