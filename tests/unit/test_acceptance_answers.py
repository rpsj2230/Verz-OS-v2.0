"""The install checks for what an answer stands on and how it declines, each passing and failing.

The pure half holds the module's figures to things outside it: one check per leaf group, the
stand-in's two replies read by the product's own adapter as a reply that names a document and a
reply with no words, and the scope statement's names held to the route that renders them.

The database half runs the module against PostgreSQL at head as the worker would, with the hosted
profile and every provider's key in a vault the test answers for, so the stand-in is planned and no
product provider is asked. All four checks pass and leave nothing. Then each check's property is
broken in the product, the way it would plausibly break (a badge left off, a citation's link to a
passage lost, a row cited without its read time, the projection's refusal logged as an absence
again, the library left out of the scope statement), and the check for it is shown failing with
its own sentence. A check that passed whatever the product did would show up here as a mutation
surviving.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M8.1.1, M8.1.2, M8.1.4, M7.4.7, M8.2.1, M8.2.2, M9.2.1, M7.6.1, M15.4.1, M15.3.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from brain.gate import answer as answer_module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_answers import (
    CITES_ELSEWHERE,
    ELSEWHERE_REFERENCE,
    READS_ONE,
    SILENT,
    Replies,
)
from brain.ops.acceptance_models import STAND_IN_ADDRESS
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_models import Providers, laddered, live_ladder

MODULE = "brain.ops.acceptance_answers"

DOCUMENT = "a_document_answer_cites_the_passage_it_was_shown_with_its_badge"
RECORD = "a_record_answer_cites_the_record_field_and_read_time"
NOTHING = "four_kinds_of_nothing_are_kept_apart"
SCOPE = "an_answer_and_a_refusal_say_what_the_asker_s_reach_covers"
KIND = "a_question_narrowed_to_a_kind_is_answered_from_that_kind_alone"
TRIM = "a_prompt_too_long_for_every_model_is_answered_from_fewer"
FOLLOWED = "a_followed_citation_is_kept_as_a_place_and_nothing_else"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Seven checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same number of rows, and the leaf closes on a check that never looked."""
    checks = [(one.name, one.leaves) for one in registered((MODULE,))]
    assert checks == [
        (DOCUMENT, ("M8.1.2", "M8.1.4", "M7.4.7")),
        (RECORD, ("M8.1.1", "M9.2.1")),
        (NOTHING, ("M8.2.1",)),
        (SCOPE, ("M8.2.2",)),
        (KIND, ("M7.6.1",)),
        (TRIM, ("M15.4.1",)),
        (FOLLOWED, ("M15.3.4",)),
    ]


def _completion_of(model: str) -> Any:
    """What the product's own adapter reads from the stand-in's reply for `model`."""
    from brain.models.wire import PROVIDER_WIRES, completion_from

    responder = Replies()
    request = httpx.Request(
        "POST", f"{STAND_IN_ADDRESS}/chat/completions", content=json.dumps({"model": model})
    )
    return completion_from(PROVIDER_WIRES["openai"], responder(request).json())


def test_the_reading_stand_in_refuses_two_passages_in_the_shape_the_wire_reads_as_too_long() -> (
    None
):
    """The refusal is read by `brain.models.wire`, outside the module, as the context-length
    failure, and one passage is answered. Delete this and the stand-in's refusal can drift to a
    shape the wire reads as an ordinary provider error, so the M15.4.1 check fails on every
    install for a reason that is the stand-in's, or it can accept two passages and pass whatever
    the lane does."""
    from brain.models.adapter import ContextWindowExceededError
    from brain.models.wire import failure_for_status

    responder = Replies()

    def sent(passages: int) -> httpx.Response:
        body = {"model": READS_ONE, "messages": [{"content": "Passage 1 " * passages}]}
        request = httpx.Request(
            "POST", f"{STAND_IN_ADDRESS}/chat/completions", content=json.dumps(body)
        )
        return responder(request)

    refused = sent(2)
    assert isinstance(
        failure_for_status(refused.status_code, refused.json()), ContextWindowExceededError
    )
    assert sent(1).status_code == 200


def test_the_stand_in_s_two_replies_are_read_as_prose_naming_a_document_and_as_nothing() -> None:
    """Read by `brain.models.wire.completion_from`, outside the module. Delete this and the
    citing reply can stop naming the reference the check looks for, which makes the M8.1.4 half
    pass whatever the lane cites, or the silent reply can grow words, which makes the lane answer
    and the not-answering half fail on every install."""
    cites = _completion_of(CITES_ELSEWHERE)
    silent = _completion_of(SILENT)
    assert ELSEWHERE_REFERENCE in cites.text and cites.finish_reason == "stop"
    assert silent.text == "" and silent.finish_reason == "stop"


def test_the_scope_statement_names_the_library_and_the_tables_only_to_their_readers() -> None:
    """`brain.api_routes.covered_at`, the route's own function, at three reaches. Delete this and
    the statement can name the library to a reader who holds no knowledge read, which tells them
    the install searches documents they cannot read, or drop it for one who does."""
    from datetime import UTC, datetime

    from brain.api_routes import KNOWLEDGE_COVERED, TABLES_COVERED, covered_at
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.knowledge.search import KNOWLEDGE_READ
    from brain.tools.startup import build_registry

    now = datetime(2999, 1, 1, tzinfo=UTC)

    class _NoRows:
        async def rows(self, query: Any) -> tuple[()]:
            return ()

    registry = build_registry(source="local", records=_NoRows())

    def reach(*capabilities: str) -> EntitlementSet:
        return EntitlementSet(
            principal_id="p_reader",
            grants=tuple(
                Grant(capability=Capability(value=one), scope=Scope.department("sales"))
                for one in capabilities
            ),
        )

    tables = ("acceptance_prices",)
    everything = reach(KNOWLEDGE_READ.value, "read:acceptance_prices")
    assert covered_at(registry, everything, now, tables=tables) == (
        KNOWLEDGE_COVERED,
        TABLES_COVERED,
    )
    assert covered_at(registry, reach("read:acceptance_prices"), now, tables=tables) == (
        TABLES_COVERED,
    )
    assert covered_at(registry, reach(KNOWLEDGE_READ.value), now, tables=tables) == (
        KNOWLEDGE_COVERED,
    )
    assert covered_at(registry, reach(), now, tables=tables) == ()


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """One database at head for the module, with the ladder the wizard writes."""
    with at_head("brain_acceptance_answers") as url:
        laddered(url)
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """`vault_the_providers`, as a fixture."""
    return vault_the_providers(monkeypatch)


def vault_the_providers(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile, every provider's key in a vault the test answers for, and the
    providers answering in the process, as `tests/unit/test_acceptance_routing.py` sets them. The
    keys are this file's test values and reach nothing, and no check here should ask a provider
    of the product at all."""
    from brain.ops import acceptance_models, model_probe_run
    from brain.ops.openbao import OpenBaoVault
    from brain.ops.provider_keys import PROVIDER_SLOTS

    answering = Providers()
    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(model_probe_run, "_PROCESS_KEYS", {})
    monkeypatch.setattr(
        OpenBaoVault,
        "read_static_kv",
        lambda self, path: {"api_key": f"test-{path.rsplit('/', 1)[-1]}-not-a-key"},
    )
    monkeypatch.setattr(
        acceptance_models,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(answering)),
    )
    return answering


#: What these checks write beyond the suite's list: the rule the nothing-connected half adds.
ALSO_WRITTEN = ("gate.fast_path_rule",)


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


def run_answers(url: str, *names: str) -> dict[str, tuple[str, str]]:
    """The module's checks, or the ones named, run as the worker runs them."""
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
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


@pytest.mark.needs_db
def test_every_answer_check_passes_on_an_install_and_leaves_nothing(
    install: str, vaulted: Providers
) -> None:
    """**The module run as the worker runs it, against PostgreSQL at head.** All four pass; every
    table a check wrote to holds what it held before, the rule table and the verifications among
    them, and so does the ladder; and no request reached a provider of the product, because every
    question was answered by the stand-in or by a rule. Delete this and a check that can never
    pass, or one that commits the rule it adds, reaches the owner's server first."""
    before, ladder = _counts(install), live_ladder(install)
    outcomes = run_answers(install)
    after = _counts(install)

    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 7
    assert after == before and live_ladder(install) == ladder and ladder
    assert vaulted.sent == []


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_answers(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_badge_left_off_a_cited_document_fails_the_document_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane handed no item lookup badges nothing, which is what a process that lost its
    database wiring would do. Delete this and M7.4.7 closes on a check that never read a badge."""
    from brain.gate import model_lane

    original = model_lane.evidence_of

    async def unbadged(composed: Any, *, lane: Any, **kwargs: Any) -> Any:
        from dataclasses import replace

        return await original(composed, lane=replace(lane, items=None), **kwargs)

    monkeypatch.setattr(model_lane, "evidence_of", unbadged)
    assert "unverified" in _failed(install, DOCUMENT)


@pytest.mark.needs_db
def test_a_citation_built_from_the_model_s_words_fails_the_document_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lane that read a reference out of the reply and cited it is the failure M8.1.4 names.
    Delete this and the check's reading of the citations can be satisfied by any citation at all."""
    from brain.gate import model_lane, provenance

    original = model_lane.trace_of

    def from_the_reply(payload: Any, *, reach: Any) -> Any:
        from dataclasses import replace

        traced = original(payload, reach=reach)
        invented = provenance.DocumentCitation(
            document_id=ELSEWHERE_REFERENCE,
            title="",
            anchor=provenance.Anchor(chunk_id=ELSEWHERE_REFERENCE),
        )
        return replace(traced, passages=(*traced.passages, invented))

    monkeypatch.setattr(model_lane, "trace_of", from_the_reply)
    said = _failed(install, DOCUMENT)
    assert "nobody uploaded" in said or "other than" in said


@pytest.mark.needs_db
def test_a_row_cited_without_its_read_time_fails_the_record_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A citation with no read time cannot say how fresh it is. Delete this and M8.1.1 closes on a
    check that never looked at the time."""
    from brain.gate import provenance

    original = provenance.Evidence.view

    def timeless(self: Any) -> dict[str, str]:
        return {**original(self), "read_at": ""}

    monkeypatch.setattr(provenance.Evidence, "view", timeless)
    assert "time" in _failed(install, RECORD)


@pytest.mark.needs_db
def test_the_projection_s_refusal_logged_as_an_absence_fails_the_nothing_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane as it was until 2026-09-29: a column the reader holds no grant for, never fetched,
    recorded as absent. Delete this and the not-entitled half can go back to unreachable with the
    check green."""
    monkeypatch.setattr(answer_module, "_held_no_grant_for", lambda *args: False)
    assert _failed(install, NOTHING)


@pytest.mark.needs_db
def test_the_library_left_out_of_the_statement_fails_the_scope_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route handing the lane the connector sources alone, as it did until 2026-09-29. Delete
    this and M8.2.2 closes on a statement that never names what a document answer searched."""
    from brain import api_routes

    monkeypatch.setattr(
        api_routes,
        "covered_at",
        lambda registry, reach, now, **kw: api_routes.sources_at(registry, reach, now),
    )
    assert "library" in _failed(install, SCOPE)


@pytest.mark.needs_db
def test_a_kind_the_search_ignores_fails_the_kind_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route's kinds dropped on the way to the passage search, as they were until 2026-09-29.
    Delete this and M7.6.1 closes on a check that a search of every kind passes."""
    from brain import api_routes

    original = api_routes.model_lane_for

    def unnarrowed(
        state: Any, agent: Any, registry: Any, kinds: Any = (), follow_up: Any = None
    ) -> Any:
        return original(state, agent, registry, follow_up=follow_up)

    monkeypatch.setattr(api_routes, "model_lane_for", unnarrowed)
    assert "another kind" in _failed(install, KIND)


@pytest.mark.needs_db
def test_a_lane_that_gives_up_on_a_prompt_too_long_fails_the_trim_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane with nothing fewer to send, as it was until 2026-09-29: the provider's failure is
    the answer. Delete this and M15.4.1 closes on a check a lane that never trims passes."""
    from brain.gate import model_lane

    monkeypatch.setattr(model_lane, "fewer", lambda payload: None)
    assert "provider's failure" in _failed(install, TRIM)


@pytest.mark.needs_db
def test_an_answer_silent_about_its_trimmed_passages_fails_the_trim_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane trimming and the answer saying nothing of it. Delete this and M15.4.1 closes with
    the silent truncation the owner's requirement forbids."""
    from brain.gate import model_lane

    monkeypatch.setattr(model_lane.Trimmed, "sentence", lambda self: "")
    assert "did not say" in _failed(install, TRIM)


@pytest.mark.needs_db
def test_a_search_that_notes_nothing_fails_the_retrieval_log_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The passage search noting nothing for the request, as it did until 2026-09-29. Delete this
    and M15.3.4 closes on a check a product that logs no retrieval passes."""
    from brain.knowledge import document_tools

    monkeypatch.setattr(document_tools, "note", lambda searched: None)
    assert "kept no retrieval" in _failed(install, FOLLOWED)


@pytest.mark.needs_db
def test_a_citation_without_its_place_fails_the_retrieval_log_check(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane placing no passage in the reader's list. Delete this and M15.3.4 closes with a
    cited page that has nothing to send back."""
    from brain.gate import model_lane

    original = model_lane.trace_of

    def unplaced(payload: Any, *, reach: Any) -> Any:
        from dataclasses import replace

        trace = original(payload, reach=reach)
        return replace(trace, passages=tuple(replace(one, position=0) for one in trace.passages))

    monkeypatch.setattr(model_lane, "trace_of", unplaced)
    assert "place in the reader's list" in _failed(install, FOLLOWED)
def test_the_answers_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_answers") == [
        "a_document_answer_cites_the_passage_it_was_shown_with_its_badge",
        "a_record_answer_cites_the_record_field_and_read_time",
        "four_kinds_of_nothing_are_kept_apart",
        "an_answer_and_a_refusal_say_what_the_asker_s_reach_covers",
        "a_question_narrowed_to_a_kind_is_answered_from_that_kind_alone",
        "a_prompt_too_long_for_every_model_is_answered_from_fewer",
        "a_followed_citation_is_kept_as_a_place_and_nothing_else",
    ]
