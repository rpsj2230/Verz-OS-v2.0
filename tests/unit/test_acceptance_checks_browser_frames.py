"""The frames install check: what it names, that it passes on the product as it is, and that it
fails for each way a picture beside a credential could reach a judge, or a clean one be kept
from it.

It needs no database. Each failure is one defect injected into the function the driver or the
verification module calls, and the check must fail with its own sentence.

Task ids: M19.4.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain.browsing import driver, verification
from brain.ops import acceptance_checks_browser_frames as module
from brain.ops.acceptance import PASSED, CheckFailedError, registered
from brain.ops.acceptance_checks_browser_credentials import SECRET
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_frames"
NAME = "a_judge_is_shown_no_picture_beside_a_credential"
HARNESS = SimpleNamespace(run="r1", trace_id="t-1", now=datetime(2999, 1, 1, 12, tzinfo=UTC))


def run_it() -> None:
    asyncio.run(module.a_judge_is_shown_no_picture_beside_a_credential(HARNESS))  # type: ignore[arg-type]


def fails_with(sentence: str) -> None:
    with pytest.raises(CheckFailedError) as failed:
        run_it()
    assert failed.value.reason == sentence


def test_the_check_names_the_frame_leaf_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose its leaf with the page showing the same row, or sit
    outside the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M19.4.5",))]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


def test_the_check_passes_on_the_product_as_it_is() -> None:
    """The positive case for every failure below. Delete this and a check that fails on a healthy
    product satisfies all of them."""
    run_it()


def test_a_run_whose_records_carry_no_placeholder_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record line has no placeholder, so the driver supplies the one it sent. Delete this and
    a driver that stopped doing so, which makes every typed credential invisible to the judge's
    frame admission, passes."""
    real = vars(driver)["_record_of"]

    def forgetful(fields: Any, run_id: str, placeholder: str = "") -> Any:
        return real(fields, run_id, "")

    monkeypatch.setattr(driver, "_record_of", forgetful)

    fails_with(module.THE_RUN_RETURNED_NO_EVIDENCE)


def test_a_run_that_returns_no_frames_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a driver that stopped building the judge's input passes: a judge handed
    nothing is a judge that cannot be told a picture was refused."""
    monkeypatch.setattr(driver, "frames_of", lambda exchanged, run_id: ())

    fails_with(module.THE_RUN_RETURNED_NO_EVIDENCE)


def test_an_admission_that_lets_every_frame_through_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an admission that stopped withholding the picture beside a typed credential
    passes."""

    class All:
        def __init__(self, run_id: str, frames: Any) -> None:
            self.run_id, self.frames, self.withheld = run_id, tuple(frames), ()

    monkeypatch.setattr(
        verification, "admit_frames", lambda t, f, *, secret_sequences: All(t.run_id, f)
    )

    fails_with(module.A_FRAME_BESIDE_A_CREDENTIAL_WAS_ADMITTED)


def test_an_admission_that_withholds_everything_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling of the above. Delete this and an admission that withholds every picture passes
    a check that asks only whether the wrong one was shown."""
    from brain.browsing.verification import AdmittedFrames

    def nothing(trajectory: Any, frames: Any, *, secret_sequences: Any) -> Any:
        return AdmittedFrames(
            run_id=trajectory.run_id,
            frames=(),
            withheld=tuple((one.sequence, verification.CREDENTIAL_TYPED_HERE) for one in frames),
        )

    monkeypatch.setattr(verification, "admit_frames", nothing)

    fails_with(module.A_CLEAN_FRAME_WAS_WITHHELD)


def test_an_admission_that_never_lets_a_page_back_in_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A picture is clean again from the first opening after the typing. Delete this and an
    admission that withholds for the rest of the run, which gives the judge too little to judge,
    passes."""
    real = verification.admit_frames

    def never_again(trajectory: Any, frames: Any, *, secret_sequences: Any) -> Any:
        shown = real(trajectory, frames, secret_sequences=secret_sequences)
        kept = tuple(one for one in shown.frames if one.sequence < 2)
        late = tuple(
            (one.sequence, verification.CREDENTIAL_TYPED_HERE)
            for one in shown.frames
            if one.sequence >= 2
        )
        return replace(shown, frames=kept, withheld=(*shown.withheld, *late))

    monkeypatch.setattr(verification, "admit_frames", never_again)

    fails_with(module.A_PAGE_OPENED_AFTER_TYPING_WAS_NOT_ADMITTED)


@pytest.mark.parametrize(
    ("sequence", "sentence"),
    [
        (2, module.A_FRAME_BESIDE_A_CREDENTIAL_WAS_ADMITTED),
        (3, module.A_FRAME_WITH_THE_VALUE_IN_ITS_TREE_WAS_ADMITTED),
    ],
)
def test_a_frame_withheld_for_the_wrong_reason_fails_the_check(
    monkeypatch: pytest.MonkeyPatch, sequence: int, sentence: str
) -> None:
    """The reason says which condition held a picture back, and a report that names the wrong one
    sends an administrator looking in the wrong place. Delete this and a reason that is always the
    same passes."""
    real = verification.admit_frames

    def mislabelled(trajectory: Any, frames: Any, *, secret_sequences: Any) -> Any:
        shown = real(trajectory, frames, secret_sequences=secret_sequences)
        return replace(
            shown,
            withheld=tuple(
                (n, verification.NOT_MASKED if n == sequence else why) for n, why in shown.withheld
            ),
        )

    monkeypatch.setattr(verification, "admit_frames", mislabelled)

    fails_with(sentence)


def test_a_picture_the_runner_says_was_not_masked_is_not_shown_and_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner's statement that every form control was painted over is carried to the judge's
    admission and not assumed. Delete this and a driver that reports every frame as masked, whatever
    the runner said, passes."""
    from brain.browsing import runner
    from brain.browsing.wire import Kind

    real = vars(runner)["encode"]

    def unmasked(kind: Any, **fields: Any) -> bytes:
        if kind is Kind.FRAME:
            fields["inputs_masked"] = False
        return bytes(real(kind, **fields))

    monkeypatch.setattr("brain.browsing.runner.encode", unmasked)

    with pytest.raises(CheckFailedError):
        run_it()


def test_a_run_that_finds_no_value_in_any_tree_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a driver that stopped looking for the value in the trees passes, and the
    picture beside a page that drew the value is shown."""
    monkeypatch.setattr(driver, "secrets_seen", lambda exchanged, secrets: frozenset())

    fails_with(module.A_FRAME_WITH_THE_VALUE_IN_ITS_TREE_WAS_ADMITTED)


def test_a_reason_that_quotes_the_credential_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A report about withholding must not become a way round it. Delete this and a reason that
    carries the value passes."""
    real = verification.admit_frames

    def quoting(trajectory: Any, frames: Any, *, secret_sequences: Any) -> Any:
        shown = real(trajectory, frames, secret_sequences=secret_sequences)
        return replace(shown, withheld=tuple((n, f"{why}: {SECRET}") for n, why in shown.withheld))

    monkeypatch.setattr(verification, "admit_frames", quoting)

    fails_with(module.A_REASON_NAMED_THE_VALUE)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_frames") as url:
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
