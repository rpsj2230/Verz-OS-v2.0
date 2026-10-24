"""The language checks: registered, passing on a real schema, and able to fail.

The database half adds an English, a Chinese and a mixed document and asks in each language; it
passes and leaves nothing. Then the product is broken where the check proves it: the Han leg of the
lexical search dropped (a Chinese question finds nothing), and the language not recorded at ingest.
The shell check says it was not run where the image carries no built console, and passes over a
bundle carrying the shell, and fails over one whose manifest names an icon nothing serves.

Task ids: M35.1.1.3, M35.4.3, M35.1.2.1, M35.1.2.2, M35.1.2.3, M35.3.2.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_localisation"
RETRIEVAL = "chinese_and_mixed_documents_are_found_in_either_language"
SHELL = "the_console_is_served_as_an_installable_shell"
RTL = "a_right_to_left_language_is_refused_by_name"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_each_check_names_the_leaves_it_proves_and_every_one_is_a_leaf() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        RETRIEVAL: ("M35.1.2.1", "M35.1.2.2", "M35.1.2.3"),
        SHELL: ("M35.3.2.1",),
        RTL: ("M35.1.1.3", "M35.4.3"),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def test_the_language_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [RETRIEVAL, SHELL, RTL]


def test_the_module_stands_inside_its_assigned_order_range() -> None:
    """Delete this and two modules can claim one place on the Install page."""
    from brain.ops import acceptance_checks_localisation as module

    assert 2000 <= module.CHECK_ORDER <= 2099


def test_the_chinese_question_shares_no_word_with_an_english_one() -> None:
    """The question is Han text and the English document holds none of it, so a pass cannot come
    from the English leg. Delete this and the check can be satisfied by the wrong index."""
    from brain.ops import acceptance_checks_localisation as module

    assert all(ord(one) > 0x2E80 for one in module.CHINESE_QUESTION)


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_retrieval_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes and every table
    it wrote holds what it held before. Delete this and a check that cannot pass on the real
    schema, or one that commits a document to a client's install, reaches the owner's server."""
    with at_head("brain_acceptance_localisation") as url:
        before = counts(url)
        outcomes = run_checks(url, (mine()[RETRIEVAL],))
        after = counts(url)

    assert outcomes == {RETRIEVAL: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        (
            "no_han_leg",
            "a question in Chinese did not find the Chinese document",
        ),
        ("no_language", "a Chinese document was not recorded as Chinese"),
    ],
)
def test_the_retrieval_check_fails_where_the_product_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks, each the way it happens: a search that no longer asks the Han index, so a
    Chinese question quietly finds nothing; and an ingest that records no language. Delete this and
    the check is satisfied by a search that cannot read Chinese."""
    from brain.knowledge import chunk_store, search

    if broken == "no_han_leg":
        monkeypatch.setattr(search, "lexical_tokens", lambda text: ())
    else:
        real = search.chunk_text_fields
        monkeypatch.setattr(
            chunk_store, "chunk_text_fields", lambda body: {**real(body), "language": None}
        )
    with at_head("brain_acceptance_localisation") as url:
        outcome = run_checks(url, (mine()[RETRIEVAL],))[RETRIEVAL]

    assert outcome == (FAILED, reason)


def build(root: Path, manifest: dict[str, Any], icons: Sequence[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text("<!doctype html><title>Brain</title>", encoding="utf-8")
    (root / "manifest.webmanifest").write_text(json.dumps(manifest), encoding="utf-8")
    for one in icons:
        (root / one).write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")


GOOD = {
    "name": "Company Brain",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
}


def shell_outcome(monkeypatch: pytest.MonkeyPatch, root: Path) -> tuple[str, str]:
    from brain import console_static

    monkeypatch.setattr(console_static, "CONSOLE_DIST", root)
    return run_shell()


def run_shell() -> tuple[str, str]:
    from brain.ops.acceptance_run import Harness

    check = mine()[SHELL]

    async def run() -> tuple[str, str]:
        harness = Harness.__new__(Harness)
        try:
            await check.run(harness)
        except Exception as exc:
            from brain.ops.acceptance import reason_for

            return reason_for(exc)
        return PASSED, ""

    return asyncio.run(run())


def test_the_shell_check_says_it_was_not_run_where_no_console_is_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Delete this and an image with no console reads as a console with a broken shell."""
    assert shell_outcome(monkeypatch, tmp_path / "none")[0] == NOT_RUN


def test_the_shell_check_passes_over_a_bundle_carrying_the_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive case: a manifest naming the application and an icon that is served. Delete
    this and the check can be satisfied by a check that refuses every bundle."""
    build(tmp_path / "dist", GOOD, ("icon.svg",))
    assert shell_outcome(monkeypatch, tmp_path / "dist") == (PASSED, "")


def test_the_shell_check_fails_over_a_manifest_naming_an_icon_nothing_serves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Delete this and a manifest whose icon is a 404 passes, and the browser never offers the
    install."""
    build(tmp_path / "dist", GOOD, ())
    outcome = shell_outcome(monkeypatch, tmp_path / "dist")
    assert outcome == (FAILED, "an icon the console's manifest names is not served")


def test_the_shell_check_fails_over_a_manifest_with_no_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Delete this and a manifest missing the field a browser needs to install passes."""
    without = {one: value for one, value in GOOD.items() if one != "scope"}
    build(tmp_path / "dist", without, ("icon.svg",))
    outcome = shell_outcome(monkeypatch, tmp_path / "dist")
    assert outcome == (FAILED, "the console's manifest is missing a field a shell needs")


def test_the_right_to_left_check_passes_at_head_and_fails_where_the_refusal_is_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case and the break in one test: the check passes against the product as it is,
    and fails when the settings refusal is the generic sentence that hides the deferral. Delete
    this and the check is satisfied by a settings screen that says nothing about right-to-left."""
    from brain.console import configuration

    check = mine()[RTL]

    def run() -> tuple[str, str]:
        from brain.ops.acceptance import reason_for

        async def go() -> tuple[str, str]:
            from brain.ops.acceptance_run import Harness

            try:
                await check.run(Harness.__new__(Harness))
            except Exception as exc:
                return reason_for(exc)
            return PASSED, ""

        return asyncio.run(go())

    assert run() == (PASSED, "")
    from brain.locale import SHIPPED_TAGS

    def generic(value: str) -> str:
        tags = [one.strip() for one in value.split(",")]
        return "" if all(one in SHIPPED_TAGS for one in tags) else "Use a shipped language."

    monkeypatch.setattr(configuration, "_locales_problem", generic)
    assert run() == (FAILED, "a right-to-left language was not refused with the deferral's words")
