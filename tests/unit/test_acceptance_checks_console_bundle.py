"""The install check for the console's fonts: not run without a bundle, passing over a good one, and
failing, in one fixed sentence each, over every fault the bundle audit finds or the server shows.

The check asks the product's own fallback route over the bundle the image carries, so each case
here is a fabricated bundle (`tests/unit/test_bundle_audit.py` builds them) pointed at by the
module's constant, and the outcome is read the way the Install page reads it: pass, fail with a
reason, or not run with a reason.

Task ids: M27.15.75
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from tests.unit.test_bundle_audit import FONT_FILE, FONT_SHEET, bundle

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_console_bundle"
NAME = "the_console_names_no_font_host_and_serves_every_font_it_ships"


def mine() -> Check:
    found = {one.name: one for one in registered((MODULE,))}
    assert list(found) == [NAME]
    return found[NAME]


def outcome(monkeypatch: pytest.MonkeyPatch, root: Path) -> tuple[str, str]:
    """What the check comes to over the bundle at `root`, as the page would record it."""
    from brain import console_static
    from brain.ops.acceptance_run import Harness

    monkeypatch.setattr(console_static, "CONSOLE_DIST", root)
    check = mine()

    async def run() -> tuple[str, str]:
        try:
            await check.run(Harness.__new__(Harness))
        except Exception as exc:
            return reason_for(exc)
        return PASSED, ""

    return asyncio.run(run())


def test_the_check_names_the_leaf_it_proves_and_that_leaf_exists() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert mine().leaves == ("M27.15.75",)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert "M27.15.75" in {one for module in wbs["modules"] for one in module["leaf_ids"]}


def test_the_check_says_it_was_not_run_where_the_image_carries_no_console(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Delete this and an image with no console reads as a console with a hosted font."""
    from brain.ops.acceptance_checks_console_bundle import NO_CONSOLE_BUNDLE_IS_BUILT_HERE

    assert outcome(monkeypatch, tmp_path / "none") == (NOT_RUN, NO_CONSOLE_BUNDLE_IS_BUILT_HERE)


def test_the_check_passes_over_a_bundle_that_names_only_itself_and_ships_its_fonts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive case: a font served as a font that may be kept, and its notice served as text.
    Delete this and the check can be satisfied by one that refuses every bundle."""
    assert outcome(monkeypatch, bundle(tmp_path / "dist")) == (PASSED, "")


@pytest.mark.parametrize(
    ("changes", "sentence"),
    [
        (
            {
                "sheet": '@import url("https://fonts.googleapis.com/css2?family=Inter");\n'
                + FONT_SHEET
            },
            "a page or stylesheet of the console names an address on another host",
        ),
        (
            {
                "sheet": "@font-face{font-family:X;src:url(/assets/missing-400-normal-Zz.woff2)}\n"
                + FONT_SHEET
            },
            "a page or stylesheet of the console names a file the bundle does not carry",
        ),
        (
            {"script": 'const h="fonts.gstatic.com";\n'},
            "a script of the console names a host that serves fonts",
        ),
        ({"notices": None}, "a font the console ships has no licence notice beside it"),
        (
            {"sheet": "body{margin:0}\n", "font_name": None, "notices": None},
            "the console's stylesheets name no font file the bundle carries",
        ),
    ],
)
def test_the_check_fails_over_each_fault_the_audit_finds_in_one_fixed_sentence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, object],
    sentence: str,
) -> None:
    """One bundle per fault, and the sentence recorded is the module's own and names no address.
    Delete this and a hosted font, a missing font or a font with no notice passes on the install
    where the build job already refused it."""
    root = bundle(tmp_path / "dist", **changes)  # type: ignore[arg-type]
    assert outcome(monkeypatch, root) == (FAILED, sentence)


def test_the_check_fails_when_a_font_is_of_a_type_the_install_does_not_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The install's server is asked, not just the directory, and a font is judged by the type the
    product names for its extension. An embedded-OpenType file is found by the audit as a font and
    is one the product has no type for, so the install would guess. Delete this and the check
    proves the files exist and says nothing about how they are answered."""
    root = bundle(tmp_path / "dist")
    odd = "plex-sans-latin-400-normal-AbC123.eot"
    sheet = (root / "assets" / "app-1.css").read_text(encoding="utf-8").replace(FONT_FILE, odd)
    (root / "assets" / "app-1.css").write_text(sheet, encoding="utf-8", newline="\n")
    (root / "assets" / FONT_FILE).rename(root / "assets" / odd)
    assert outcome(monkeypatch, root) == (
        FAILED,
        "a font the console names was not served as a font",
    )


def test_the_check_fails_when_the_install_answers_a_font_as_something_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A font the product has a type for, answered as another. The bundle and its notice are
    sound, so only the install's own answer can fail this: the server is made to answer every
    bundle file as plain text. Delete this and the check compares nothing about the answer."""
    from fastapi.responses import FileResponse

    from brain import console_static

    root = bundle(tmp_path / "dist")
    monkeypatch.setattr(
        console_static,
        "bundle_file_response",
        lambda found, root=None: FileResponse(found, media_type="text/plain"),
    )
    assert outcome(monkeypatch, root) == (
        FAILED,
        "a font the console names was not served as a font",
    )


def test_the_check_fails_when_a_font_is_served_with_no_long_lifetime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A font outside `assets/` is served as a font and, its name not being a hash, may not be kept
    for ever. Delete this and the fonts, the largest files a page loads, can be revalidated with
    the install on every visit without anything saying so."""
    root = bundle(tmp_path / "dist")
    (root / "fonts").mkdir()
    (root / "fonts" / FONT_FILE).write_bytes(b"wOF2")
    sheet = (root / "assets" / "app-1.css").read_text(encoding="utf-8")
    sheet = sheet.replace(f"/assets/{FONT_FILE}", f"/fonts/{FONT_FILE}")
    (root / "assets" / "app-1.css").write_text(sheet, encoding="utf-8", newline="\n")
    assert outcome(monkeypatch, root) == (
        FAILED,
        "a font the console names was served with no long lifetime",
    )


def test_the_check_fails_when_the_licence_notice_is_not_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The notice is read by the audit as a file and must also be answered by the install, which is
    where the licence's condition is met. A notice that is a link to a file outside the bundle is
    found by the audit and refused by the server. Delete this and a notice that exists and answers
    nobody satisfies the condition on paper."""
    from brain.ops import bundle_audit

    root = bundle(tmp_path / "dist")
    notice = root / bundle_audit.FONT_LICENCES_FILE
    outside = tmp_path / "notices.txt"
    outside.write_text(notice.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    notice.unlink()
    notice.symlink_to(outside)
    assert outcome(monkeypatch, root) == (
        FAILED,
        "the licence notice of the console's fonts was not served",
    )
