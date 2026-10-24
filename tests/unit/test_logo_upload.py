"""The company logo as an upload: kept behind the setup code, served to the console, refused when
it could run, and pointed at by the appointment only when no address was given.

Task ids: M42.5.5
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.branding import (
    LOGO_FILE_NAME,
    LOGO_PATH,
    MAX_LOGO_BYTES,
    LogoRefusedError,
    checked,
    from_base64,
    keep,
    read,
)
from brain.logo_routes import UPLOAD_PATH
from brain.setup_wizard import StepId
from tests.unit.test_setup_routes import (  # noqa: F401  (carried is an autouse fixture)
    EVERY_SCREEN,
    Store,
    appointing,
    body,
    carried,
    serving,
)
from tests.unit.test_setup_wizard import COMPANY_ANSWERS, SECRET, WRONG

pytestmark = pytest.mark.usefixtures("carried")

BLANK_LOGO = {**COMPANY_ANSWERS, "logo_url": ""}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture
def where(tmp_path: Path) -> Path:
    return tmp_path


def _upload(client: TestClient, data: bytes, *, code: str = SECRET) -> Any:
    return client.post(UPLOAD_PATH, json={"setup_code": code, "image": b64(data)})


@pytest.fixture
def client(where: Path) -> Iterator[TestClient]:
    with serving(Store()) as c:
        c.app.state.setup_draft_path = where / "draft.json"  # type: ignore[attr-defined]
        yield c


# ---------------------------------------------------------------- what is accepted
@pytest.mark.parametrize(
    ("data", "media_type"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"), (WEBP, "image/webp")],
)
def test_each_raster_kind_is_known_by_its_first_bytes(data: bytes, media_type: str) -> None:
    """The four kinds, by their bytes and not their names. Delete this and a kind added or
    dropped changes what a company can upload without a test noticing."""
    assert checked(data).media_type == media_type


def test_the_size_limit_is_inclusive_and_one_more_byte_is_refused() -> None:
    """Delete this and the cap is off by one in the direction nobody tests, or absent."""
    assert MAX_LOGO_BYTES == 262_144
    assert checked(PNG + b"\x00" * (262_144 - len(PNG))).media_type == "image/png"
    with pytest.raises(LogoRefusedError, match="larger"):
        checked(PNG + b"\x00" * (262_144 - len(PNG) + 1))


@pytest.mark.parametrize(
    ("data", "words"),
    [
        (b"", "empty"),
        (SVG, "SVG"),
        (b"<?xml version='1.0'?><svg></svg>", "SVG"),
        (b"%PDF-1.7 ...", "not an image"),
        (b"just text", "not an image"),
    ],
)
def test_what_is_not_a_raster_image_is_refused_in_words(data: bytes, words: str) -> None:
    """An SVG can carry script and the file is served from the install's own origin. Delete this
    and a scriptable logo is accepted, which is a stored cross-site-scripting hole."""
    with pytest.raises(LogoRefusedError, match=words):
        checked(data)


def test_a_base64_string_that_is_not_base64_is_refused() -> None:
    """Delete this and a truncated paste is decoded as far as it goes and kept."""
    with pytest.raises(LogoRefusedError, match="intact"):
        from_base64("not base64!!")


def test_a_kept_file_is_read_back_and_a_file_that_fails_the_rule_is_not(where: Path) -> None:
    """The rule is held when the file is read as well as when it is written. Delete this and a file
    put in the directory by hand is served as whatever it is."""
    keep(where, checked(PNG))
    assert read(where) is not None and read(where).media_type == "image/png"  # type: ignore[union-attr]
    (where / LOGO_FILE_NAME).write_bytes(SVG)
    assert read(where) is None
    (where / LOGO_FILE_NAME).unlink()
    assert read(where) is None


# ---------------------------------------------------------------- the routes
def test_an_uploaded_logo_is_kept_and_served_with_headers_that_stop_it_running(
    client: TestClient, where: Path
) -> None:
    """The positive case, end to end. Delete this and the upload and the served image can part
    company, or the image is served in a way a browser may run."""
    kept = _upload(client, PNG)

    assert kept.status_code == 200
    assert kept.json() == {"media_type": "image/png", "bytes_kept": len(PNG), "path": LOGO_PATH}
    assert (where / LOGO_FILE_NAME).read_bytes() == PNG
    served = client.get(LOGO_PATH)
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in served.headers["content-security-policy"]


def test_a_second_upload_replaces_the_first(client: TestClient) -> None:
    """Delete this and choosing a different logo keeps the first."""
    _upload(client, PNG)
    _upload(client, JPEG)

    assert client.get(LOGO_PATH).headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("data", [SVG, b"", b"text"])
def test_a_refused_upload_says_why_and_keeps_nothing(
    client: TestClient, where: Path, data: bytes
) -> None:
    """Delete this and a refused file leaves something to be served, or a refusal with no
    sentence."""
    answer = _upload(client, data)

    assert answer.status_code == 422 and answer.json()["problem"]
    assert not (where / LOGO_FILE_NAME).exists()
    assert client.get(LOGO_PATH).status_code == 404


def test_a_wrong_code_a_finished_install_and_no_code_are_the_one_refusal_and_write_nothing(
    where: Path,
) -> None:
    """The order every setup route keeps: the code before the body. Delete this and a stranger can
    write a file to the install, or learn from the answer which of the three refused them."""
    refusals = []
    with serving(Store()) as wrong:
        wrong.app.state.setup_draft_path = where / "a" / "draft.json"  # type: ignore[attr-defined]
        refusals.append(_upload(wrong, PNG, code=WRONG))
    with serving(Store(held=1)) as finished:
        finished.app.state.setup_draft_path = where / "b" / "draft.json"  # type: ignore[attr-defined]
        refusals.append(_upload(finished, PNG))
    with serving(Store(), with_code=False) as nocode:
        nocode.app.state.setup_draft_path = where / "c" / "draft.json"  # type: ignore[attr-defined]
        refusals.append(_upload(nocode, PNG))

    assert {one.status_code for one in refusals} == {404}
    assert len({one.text.replace(one.json().get("trace_id", ""), "") for one in refusals}) == 1
    assert not list(where.rglob(LOGO_FILE_NAME))


def test_an_install_with_no_logo_serves_the_one_refusal(client: TestClient) -> None:
    """Delete this and the logo path answers something for an install that uploaded nothing."""
    assert client.get(LOGO_PATH).status_code == 404


# ---------------------------------------------------------------- the appointment
def test_the_appointment_points_the_logo_setting_at_the_upload_when_no_address_was_given(
    where: Path,
) -> None:
    """The upload becomes the install's logo in the appointment's own transaction. Delete this and
    an uploaded logo sits in a directory and the header draws the product's own icon."""
    store = Store()
    with serving(store) as c:
        c.app.state.setup_draft_path = where / "draft.json"  # type: ignore[attr-defined]
        _upload(c, PNG)
        answered = appointing(c, body(answers={**EVERY_SCREEN, StepId.COMPANY: BLANK_LOGO}))

    assert answered.status_code == 200
    assert store.kept[0]["INSTALL_LOGO_URL"] == LOGO_PATH


def test_an_address_the_company_gave_wins_over_an_upload(where: Path) -> None:
    """Delete this and typing an address is ignored because a file was chosen first."""
    store = Store()
    answers = {
        **EVERY_SCREEN,
        StepId.COMPANY: {**COMPANY_ANSWERS, "logo_url": "https://assets.example.invalid/logo.png"},
    }
    with serving(store) as c:
        c.app.state.setup_draft_path = where / "draft.json"  # type: ignore[attr-defined]
        _upload(c, PNG)
        appointing(c, body(answers=answers))

    assert store.kept[0]["INSTALL_LOGO_URL"] == "https://assets.example.invalid/logo.png"


def test_no_upload_leaves_the_logo_setting_alone(where: Path) -> None:
    """Delete this and every install without an upload is pointed at a file that is not there."""
    store = Store()
    with serving(store) as c:
        c.app.state.setup_draft_path = where / "draft.json"  # type: ignore[attr-defined]
        appointing(c, body(answers={**EVERY_SCREEN, StepId.COMPANY: BLANK_LOGO}))

    assert store.kept[0].get("INSTALL_LOGO_URL") in (None, "")


def test_characters_outside_base64_are_refused_and_not_skipped() -> None:
    """A paste with stray characters is not decoded as far as it goes. Delete this and a mangled
    upload that still happens to decode is kept as if it had arrived intact."""
    with pytest.raises(LogoRefusedError, match="intact"):
        from_base64(b64(PNG) + "!!")


def test_a_failure_putting_the_file_down_leaves_the_earlier_logo_whole(
    where: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is written aside and put in place whole. Delete this and a crash half way through
    leaves a logo that is neither the old one nor the new one, served to every browser."""
    keep(where, checked(PNG))

    def failing(self: Path, target: object) -> Path:
        raise OSError("the last step failed")

    monkeypatch.setattr(Path, "replace", failing)
    with pytest.raises(OSError, match="last step"):
        keep(where, checked(JPEG))

    assert (where / LOGO_FILE_NAME).read_bytes() == PNG
    assert [one.name for one in where.iterdir() if one.name.startswith(".logo-")] == []


def test_the_appointment_holds_the_logo_it_wrote_for_this_process(
    where: Path,
) -> None:
    """The process that appointed answers with the install's own values at once. Delete this and
    the header draws the product's icon until the process restarts."""
    from brain.install import saved_values

    with serving(Store()) as c:
        c.app.state.setup_draft_path = where / "draft.json"  # type: ignore[attr-defined]
        _upload(c, PNG)
        appointing(c, body(answers={**EVERY_SCREEN, StepId.COMPANY: BLANK_LOGO}))

    assert saved_values()["INSTALL_LOGO_URL"] == LOGO_PATH
