"""The install checks for a person's threads, each passing on PostgreSQL at head and each failing.

The pure half holds what an answer leaves in a thread to the product's own rules: a referred
question leaves nothing, a cached answer's references are unreadable, a cited field is recorded
under its own column's capability and a passage under the document's, and a chat's thread id is
the same for one person in one chat and different for anybody or anywhere else.

The database half runs the module as the worker would, with the Lark app set up in memory and the
issuer the chat checks use, and every check passes and leaves nothing. Then each is shown failing
with the product broken the way it would plausibly break: nothing kept at all, the thread a page
names ignored, the chat's thread named by the message rather than the conversation, and the search
reading answers.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M9.1.1, M9.1.2, M9.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest

from brain.chat import remember as remember_module
from brain.chat.remember import exchange_of, refs_of
from brain.chat.thread_store import chat_thread_id
from brain.core.entitlement import Capability
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.gate.answer import Answered
from brain.gate.context import Channel
from brain.gate.provenance import Provenance
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, counts

MODULE = "brain.ops.acceptance_threads"
KEPT = "a_question_is_kept_in_its_askers_thread_and_searched_by_them"
LARK = "a_thread_begun_in_lark_is_listed_and_continued_on_the_web"

DONE = "event: done\ndata: \n\n"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Two checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (KEPT, ("M9.1.1", "M9.1.3")),
        (LARK, ("M9.1.2",)),
    ]


def _evidence(view: dict[str, str]) -> Any:
    return SimpleNamespace(view=lambda: view)


def _answered(*evidence: Any, cached: bool = False, referred: bool = False) -> Answered:
    provenance = cast(Provenance, SimpleNamespace(evidence=evidence)) if evidence else None
    return cast(
        Answered,
        SimpleNamespace(
            frames=("event: text\ndata: An answer.\n\n", DONE),
            from_cache=cached,
            provenance=provenance,
            referred=referred,
        ),
    )


POLICY = FieldPolicy(
    rules=(
        FieldRule.of("price", "cost", "read:price.cost", Classification.CONFIDENTIAL),
        FieldRule.of("price", "name", "read:price", Classification.INTERNAL),
    )
)


def test_a_cited_field_is_kept_under_its_own_column_rule_and_a_passage_under_the_document() -> None:
    """`A_CITED_FIELD_IS_RE_CHECKED_UNDER_ITS_OWN_RULE`: a cost is kept under the cost grant, an
    open column under the table's, a field nothing classifies under a column capability nobody is
    granted, and a passage under the document's text capability. Delete this and a stored answer
    quoting a cost is shown again after the cost grant is revoked."""
    refs = refs_of(
        _answered(
            _evidence({"kind": "record", "entity": "price", "record_id": "7", "field": "cost"}),
            _evidence({"kind": "record", "entity": "price", "record_id": "7", "field": "name"}),
            _evidence({"kind": "record", "entity": "price", "record_id": "7", "field": "odd"}),
            _evidence({"kind": "document", "document_id": "upload.abc"}),
        ),
        {"price": POLICY},
    )
    assert refs is not None
    assert [(one.entity, one.record_id, one.required.value) for one in refs] == [
        ("price", "7", "read:price.cost"),
        ("price", "7", "read:price"),
        ("price", "7", "read:price.odd"),
        ("knowledge", "upload.abc", "read:knowledge.document"),
    ]


def test_a_referred_question_leaves_nothing_and_a_cached_answer_is_kept_unreadable() -> None:
    """A referred question is written nowhere (M24.2.2) and a cached answer is kept with no
    references anybody can read, so it is never shown again; an abstention drew on nothing. Delete
    this and the sensitive question's words land in a transcript, or a cached answer is re-shown
    after the grant behind it is gone."""
    assert exchange_of("a sensitive question", _answered(referred=True), {}) is None
    cached = exchange_of("a question", _answered(cached=True), {})
    assert cached is not None and cached.refs is None and cached.answer == "An answer."
    declined = exchange_of("a question", _answered(), {})
    assert declined is not None and declined.refs == ()
    assert Capability(value="read:price.odd")


def test_a_chat_thread_is_one_person_in_one_conversation() -> None:
    """`A_CHAT_S_THREAD_IS_NAMED_BY_ITS_CONVERSATION`: the same person in the same chat names the
    same thread every time, and another person, chat or channel names another. Delete this and two
    people in one room share a transcript, or every Lark message starts a thread of its own."""
    one = chat_thread_id(Channel.LARK, "p_a", "oc_1")
    assert one == chat_thread_id(Channel.LARK, "p_a", "oc_1")
    assert (
        len(
            {
                one,
                *(
                    chat_thread_id(channel, person, where)
                    for channel, person, where in (
                        (Channel.LARK, "p_b", "oc_1"),
                        (Channel.LARK, "p_a", "oc_2"),
                        (Channel.TELEGRAM, "p_a", "oc_1"),
                    )
                ),
            }
        )
        == 4
    )


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_threads") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_threads(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


#: What these checks write beyond the suite's list.
ALSO_WRITTEN = ("chat.conversation", "chat.message")


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_every_thread_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """**The module as the worker runs it.** Both pass and nothing a check wrote is left, the
    threads and messages included. Delete this and a check that can never pass on a real schema,
    or one that commits a person's transcript, reaches the owner's server first."""
    before = _counts(install)
    outcomes = run_threads(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_threads(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_keeping_nothing_fails_both_checks(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routes as they were until 2026-09-29, keeping no exchange. Delete this and M9.1.1 and
    M9.1.2 close on checks that pass over an empty history."""
    monkeypatch.setattr(remember_module, "threads_of", lambda state: None)
    assert _failed(install, KEPT)
    assert _failed(install, LARK)


@pytest.mark.needs_db
def test_a_named_thread_ignored_fails_the_kept_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every question starting a thread of its own, the page's thread ignored. Delete this and a
    follow-up is never one conversation with the check green."""
    original = remember_module.remember

    async def ignoring(threads: Any, **kwargs: Any) -> Any:
        return await original(threads, **{**kwargs, "thread_id": None})

    monkeypatch.setattr(remember_module, "remember", ignoring)
    assert "in order" in _failed(install, KEPT)


@pytest.mark.needs_db
def test_a_search_reading_answers_fails_the_kept_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The search matching every message, answers included. Delete this and a search can say the
    words of an answer the reader no longer reaches are still there, with M9.1.3 green."""
    from brain.chat import thread_store

    monkeypatch.setattr(thread_store, "SEARCHED_ROLES", ("user", "assistant"))
    assert "answer's words" in _failed(install, KEPT) or "an answer" in _failed(install, KEPT)


@pytest.mark.needs_db
def test_a_chat_thread_named_by_the_message_fails_the_lark_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chat's thread named afresh for every message rather than by its conversation. Delete this
    and M9.1.2 closes with every Lark message a thread of its own."""
    import uuid

    from brain.chat import thread_store

    monkeypatch.setattr(
        thread_store, "chat_thread_id", lambda channel, principal, where: str(uuid.uuid4())
    )
    assert "Lark chat" in _failed(install, LARK)
