"""The install checks for the names this company's people have and the environment a trace is
filed under, each passing on PostgreSQL at head and each failing with the product broken.

The names check runs the recognisers in this process, so what is shown failing is a recogniser
that finds nothing, one that finds a Han name and leaves its characters, and a scrub that alters a
sentence naming nobody. The environment check is shown failing with a fourth environment in the
span vocabulary alone and with a span accepted under a value nobody declared.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M32.2.1.4, M32.1.2.3
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, SENTENCE_CHARS, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

NAMES = "brain.ops.acceptance_checks_names"
ENVIRONMENT = "brain.ops.acceptance_checks_trace_environment"
NAME_CHECK = "chinese_malay_and_tamil_names_are_scrubbed_whole"
ENVIRONMENT_CHECK = "the_trace_environment_is_one_the_install_declares"


def test_each_module_declares_one_check_naming_the_leaf_it_proves() -> None:
    """One check each, naming exactly its own leaf. Delete this and a check can drift onto a leaf
    its sentence does not prove, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((NAMES,))] == [
        (NAME_CHECK, ("M32.2.1.4",))
    ]
    assert [(one.name, one.leaves) for one in registered((ENVIRONMENT,))] == [
        (ENVIRONMENT_CHECK, ("M32.1.2.3",))
    ]
    assert checks_in(NAMES) == [NAME_CHECK]
    assert checks_in(ENVIRONMENT) == [ENVIRONMENT_CHECK]


def test_the_sentences_and_the_reasons_fit_the_page_and_the_column() -> None:
    """Each sentence within its bound and each reason a check can end with within the column.
    Delete this and a sentence is cut on the Install page or a reason is refused by the column."""
    import importlib

    for module in (NAMES, ENVIRONMENT):
        for one in registered((module,)):
            assert 0 < len(one.sentence) <= SENTENCE_CHARS, one.name
        loaded = importlib.import_module(module)
        stored = [
            value
            for key, value in vars(loaded).items()
            if key.isupper()
            and isinstance(value, str)
            and " " in value
            and not key.startswith("A_")
        ]
        assert stored
        assert all(len(one) <= REASON_CHARS for one in stored)


def test_the_names_the_check_makes_up_belong_to_nobody_and_differ_between_runs() -> None:
    """The syllables are not common names and the pieces are drawn at random. Delete this and a
    result could quote a real person's name, or two runs could send the recognisers one name."""
    from brain.ops import acceptance_checks_names as module

    assert all(re.fullmatch(r"[一-鿿]", one) for one in module.HAN_SYLLABLES)
    assert len(set(module.MALAY_GIVEN)) >= 5 and len(set(module.TAMIL_SURNAME)) >= 5


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_names_environment") as url:
        yield url


def run_one(url: str, module: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((module,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install(install: str) -> None:
    """The two modules as the worker runs them. Delete this and a check that can never pass on a
    real install reaches the owner's server."""
    assert run_one(install, NAMES) == {NAME_CHECK: (PASSED, "")}
    assert run_one(install, ENVIRONMENT) == {ENVIRONMENT_CHECK: (PASSED, "")}


@pytest.mark.needs_db
def test_a_recogniser_that_finds_nothing_or_leaves_a_name_fails_the_names_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A detector that finds nothing, each of the three name recognisers taken away in turn, and a
    scrub that rewrites a sentence naming nobody. Delete this and M32.2.1.4 closes on recognisers
    that leave the names of the company's own people to a third party."""
    from brain.ops import pii

    with monkeypatch.context() as patched:
        patched.setattr(pii, "detect", lambda text: ())
        [(outcome, reason)] = run_one(install, NAMES).values()
        assert outcome == FAILED and "left in the text" in reason

    for kind in (
        pii.EntityKind.CJK_NAME,
        pii.EntityKind.PATRONYMIC_NAME,
        pii.EntityKind.INITIALLED_NAME,
    ):
        without = tuple(one for one in pii.RECOGNISERS if one.kind is not kind)
        with monkeypatch.context() as patched:
            patched.setattr(pii, "RECOGNISERS", without)
            [(outcome, reason)] = run_one(install, NAMES).values()
            assert outcome == FAILED, (kind, reason)

    real = pii.scrub

    def changing(text: str, detections: Any = None) -> str:
        return real(text, detections).replace("renewal", "[x]")

    with monkeypatch.context() as patched:
        patched.setattr(pii, "scrub", changing)
        [(outcome, reason)] = run_one(install, NAMES).values()
        assert (outcome == FAILED and "no name was altered" in reason) or "altered" in reason


@pytest.mark.needs_db
def test_a_vocabulary_that_drifted_or_a_span_accepted_anywhere_fails_the_environment_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fourth environment in the span vocabulary alone, then a span accepted under any value.
    Delete this and M32.1.2.3 closes while Langfuse is about to fix a vocabulary the install's own
    settings disagree with."""
    from brain.ops import tracing

    with monkeypatch.context() as patched:
        patched.setattr(
            tracing, "TRACE_ENVIRONMENTS", ("development", "staging", "production", "qa")
        )
        [(outcome, reason)] = run_one(install, ENVIRONMENT).values()
        assert outcome == FAILED and "same set" in reason

    with monkeypatch.context() as patched:
        patched.setattr(tracing, "assert_environment", lambda value: value)
        [(outcome, reason)] = run_one(install, ENVIRONMENT).values()
        assert outcome == FAILED and "nobody declared" in reason
