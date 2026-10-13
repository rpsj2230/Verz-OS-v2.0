"""A half-finished setup is kept behind the setup code and read back with it, so closing the browser
continues where it stopped, and no credential is ever in what is kept.

Task ids: M42.5.12
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from brain.core.errors import Absent
from brain.setup_routes import (
    AppointmentAsked,
    DraftView,
    keep_draft,
    read_kept_draft,
)
from brain.setup_wizard import StepId
from tests.unit.test_credentials import KEY
from tests.unit.test_setup_routes import EVERY_SCREEN, HOSTED, Store
from tests.unit.test_setup_wizard import INSIDE, SECRET, WRONG, an_enrolment

COMPANY = {StepId.COMPANY: EVERY_SCREEN[StepId.COMPANY]}


def asked(code: str = SECRET, answers: Any = None, skipped: tuple[StepId, ...] = ()) -> Any:
    given = answers or COMPANY
    return AppointmentAsked(
        setup_code=code, answers={k: dict(v) for k, v in given.items()}, skipped=skipped
    )


def keep(path: Path, body: Any, *, held: int = 0, enrolment: Any = "yes") -> Any:
    return asyncio.run(
        keep_draft(
            Store(held=held),
            body,
            enrolment=an_enrolment() if enrolment == "yes" else enrolment,
            path=path,
            now=INSIDE,
        )
    )


def read(path: Path, code: str = SECRET, *, held: int = 0, enrolment: Any = "yes") -> DraftView:
    return asyncio.run(
        read_kept_draft(
            Store(held=held),
            code,
            enrolment=an_enrolment() if enrolment == "yes" else enrolment,
            path=path,
            now=INSIDE,
        )
    )


def test_what_was_answered_is_kept_and_read_back_and_the_next_screen_is_the_first_unanswered(
    tmp_path: Path,
) -> None:
    """One screen kept comes back as itself and the next screen is the one after it. Delete this
    and a person who closes the browser at the second screen starts at the first."""
    path = tmp_path / "draft.json"
    assert keep(path, asked()) == (StepId.COMPANY,)
    told = read(path)
    assert told.answers == {StepId.COMPANY: dict(EVERY_SCREEN[StepId.COMPANY])}
    assert told.next_step == StepId.ADMINISTRATOR


def test_a_screen_with_something_wrong_is_not_kept_and_nothing_kept_reads_as_empty(
    tmp_path: Path,
) -> None:
    """A company name left blank is not saved, and with nothing saved the read is an empty view
    and not a refusal. Delete this and a bad screen is written down, or a first visit is told no."""
    path = tmp_path / "draft.json"
    bad = {StepId.COMPANY: {"company_name": " ", "web_address": "not an address"}}
    assert keep(path, asked(answers=bad)) == ()
    assert read(path).answers == {}
    assert read(tmp_path / "never.json") == DraftView(answers={}, skipped=[], next_step=None)


def test_a_provider_key_is_never_in_the_file(tmp_path: Path) -> None:
    """The model screen's key is dropped by the snapshot, so the file holds the screen and not the
    key, and the key is asked for again. Delete this and a resume file is a key nobody rotates."""
    path = tmp_path / "draft.json"
    kept = keep(path, asked(answers=HOSTED))
    assert StepId.MODEL_PROVIDER in kept
    assert KEY not in path.read_text(encoding="utf-8")
    assert (
        "provider_key"
        not in json.loads(path.read_text(encoding="utf-8"))["answers"][StepId.MODEL_PROVIDER.value]
    )
    assert "provider_key" not in read(path).answers[StepId.MODEL_PROVIDER]
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    ("code", "held", "enrolment"),
    [(WRONG, 0, "yes"), (SECRET, 1, "yes"), (SECRET, 0, None)],
    ids=["a wrong code", "an install with an administrator", "no setup code at all"],
)
def test_every_refusal_is_the_same_refusal_and_keeps_and_reads_nothing(
    tmp_path: Path, code: str, held: int, enrolment: Any
) -> None:
    """A wrong code, a finished install and an install with no code are one answer for both
    routes, and nothing is written. Delete this and the draft routes tell a stranger which of the
    three it was."""
    path = tmp_path / "draft.json"
    messages = []
    for call in (
        lambda: keep(path, asked(code=code), held=held, enrolment=enrolment),
        lambda: read(path, code, held=held, enrolment=enrolment),
    ):
        with pytest.raises(Absent) as refused:
            call()
        messages.append(str(refused.value))
    assert messages[0] == messages[1]
    assert not path.exists()


def test_a_file_this_release_cannot_read_is_no_draft(tmp_path: Path) -> None:
    """A file with a version this release does not know reads as an empty view, so the person
    starts again instead of meeting a 500. Delete this and an old draft stops the wizard."""
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"version": 99, "answers": {}}), encoding="utf-8")
    assert read(path) == DraftView(answers={}, skipped=[], next_step=None)
