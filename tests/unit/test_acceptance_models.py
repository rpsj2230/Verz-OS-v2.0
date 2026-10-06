"""The install acceptance checks that reach a model, run against providers answering as the four do.

The pure half holds the figures to things outside themselves: the four providers are the product's
key slots, the stand-in is on no network, a provider is asked only when the profile, its switch and
a key all allow it, and a pinned step names the install's own model where it has one.

The database half runs the module's checks as the worker would, against PostgreSQL at head, with a
key for each provider in the environment and `httpx.MockTransport` in the place of the internet.
The transport answers in the two documented shapes `brain.models.wire.completion_from` reads
(Anthropic's Messages API, and the chat completions shape OpenAI, Moonshot and DeepSeek share),
refuses to connect to anything under `.invalid` as a resolver does, and echoes the value a check's
document pairs with its word, which is what a model reading that passage would answer. It refuses
a reasoning effort sent to a model that takes none, and treats Moonshot's `kimi-k3` as Kimi
documents it and the owner's install measured it on 2026-09-29: sent no effort, it thinks at its
maximum and runs past the step's time. So the
product's own transport, adapter, executor, answer lane and recorders run whole, and only the
network is replaced. Every check passes, nothing a check wrote is left, and the two checks with an
argument to fail are shown failing: a stand-in that answers is no fallback, and a model that answers
wrongly has not answered.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1, M3.6.3, M5.7.1, M5.6.1, M5.6.3, M38.2.2.2
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from brain.models.default_ladder import DEFAULT_MODELS, DEFAULT_TIERS
from brain.models.routing import Tier
from brain.models.wire import PROVIDER_WIRES
from brain.ops import acceptance_models, acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, CheckNotRunError, registered
from brain.ops.acceptance_models import (
    PROVIDERS,
    STAND_IN,
    STAND_IN_ADDRESS,
    askable,
    provider_steps,
)
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

#: The sentence a check's document holds, as a model reading it would find it.
PAIRED = re.compile(r"(QZ[0-9A-F]{16}) is paired with (QZ[0-9A-F]{16})")

#: Moonshot's model that always thinks, as the transport knows it: where it is reached and its
#: name. Kimi's K3 quickstart: it takes a reasoning effort of low, high or max, and thinks at max
#: when it is sent none, which on the owner's install on 2026-09-29 ran past the step's twelve
#: seconds on the M5.6.1 check's one-sentence question.
THINKING = (httpx.URL(PROVIDER_WIRES["moonshot"].base_url).host, "kimi-k3")

#: The efforts that model takes. Anything else in the field is refused, as a provider refuses it.
THINKING_EFFORTS = frozenset({"low", "high", "max"})

MODULE = "brain.ops.acceptance_models"


# ------------------------------------------------------------------------ the figures
def test_the_four_providers_are_the_key_slots_and_wires_the_product_holds() -> None:
    """Held against `PROVIDER_SLOTS` and `PROVIDER_WIRES`, outside this module. Delete this and a
    provider the owner named can drop out of the checks, or a check can be written for a provider
    the product cannot reach, and the page shows a row that can never pass."""
    slugs = {one.slug for one in PROVIDER_SLOTS}
    assert set(PROVIDERS) == slugs == set(PROVIDER_WIRES)
    assert STAND_IN not in slugs


def test_the_stand_in_is_on_a_name_no_resolver_answers() -> None:
    """`A_STEP_NOBODY_CAN_REACH_IS_A_PROVIDER_MADE_TO_FAIL`: RFC 6761 reserves `.invalid`. Delete
    this and the failing step can be pointed at a host that answers, which is a request leaving the
    server with a bearer on it, or a fallback check that never falls back."""
    host = httpx.URL(STAND_IN_ADDRESS).host
    assert host.endswith(".invalid") and STAND_IN_ADDRESS.startswith("https://")


def test_each_provider_has_its_own_check_for_each_leaf_and_the_rest_follow() -> None:
    """One row per provider per leaf, so the page says which provider did not answer without a
    reason built from a value. Delete this and a provider can lose its row, and a leaf is closed
    on three of the four."""
    checks = [(one.name, one.leaves) for one in registered((MODULE,))]
    assert checks == [
        *((f"the_{one}_provider_answers_the_models_screen_test", ("M5.7.1",)) for one in PROVIDERS),
        *((f"a_question_is_answered_end_to_end_via_{one}", ("M5.6.1",)) for one in PROVIDERS),
        ("a_step_that_cannot_be_reached_falls_back_to_the_next", ("M5.6.3",)),
        ("a_request_row_holds_the_route_it_was_given", ("M3.6.3",)),
        ("a_console_question_is_answered_from_the_askers_department_only", ("M38.2.2.2",)),
    ]


def _plan(*, profile: str = "hosted", off: frozenset[str] = frozenset(), held: set[str]) -> Any:
    return SimpleNamespace(
        profile=profile, held=frozenset(held), state=SimpleNamespace(switched_off=off)
    )


def test_a_provider_is_asked_only_when_the_profile_its_switch_and_a_key_allow_it() -> None:
    """Each of the three refusals says not run, and a provider all three allow is asked. Delete
    this and a switched-off provider is sent a question by a check, or the guard refuses every
    provider and every model check is not run for ever."""
    for plan in (
        _plan(profile="local", held={"openai"}),
        _plan(off=frozenset({"openai"}), held={"openai"}),
        _plan(held={"anthropic"}),
    ):
        with pytest.raises(CheckNotRunError):
            askable(plan, "openai")
    # Returns rather than raising: the one plan all three allow is asked.
    askable(_plan(held={"openai"}), "openai")


def test_a_pinned_step_names_the_install_s_own_model_and_the_default_where_it_has_none() -> None:
    """The model an administrator put on the ladder is the one a question is pinned to; a level
    with no live step for the provider takes the product's default. Delete this and a check pins a
    model the install never chose, and fails on a provider that answers every real question."""
    live = [
        SimpleNamespace(provider="openai", tier="main", model="gpt-own", enabled=True),
        SimpleNamespace(provider="openai", tier="heavy", model="gpt-off", enabled=False),
        SimpleNamespace(provider="anthropic", tier="heavy", model="claude-own", enabled=True),
    ]
    steps = provider_steps("openai", live)
    assert [(one.tier, one.provider, one.model) for one in steps] == [
        (Tier.MAIN, "openai", "gpt-own"),
        (Tier.HEAVY, "openai", DEFAULT_MODELS["openai"][Tier.HEAVY]),
    ]
    assert tuple(one.tier for one in steps) == DEFAULT_TIERS
    assert all(one.attempts >= 1 and one.timeout_seconds > 0 for one in steps)


# --------------------------------------------------------------------- the providers
@dataclass
class Providers:
    """The four providers as `httpx.MockTransport` answers for them, and nothing else reached.

    A request under `.invalid` fails to connect, as a resolver makes it; any other is answered in
    its provider's documented shape with the value the passage pairs, or `ready` for the Models
    screen's fixed sentence. `wrong` answers every question with a value no document holds, and
    `stand_in_answers` lets the stand-in answer as a provider would.

    A reasoning effort is refused with a 400 by every model but `THINKING`, and by that one when
    it is not an effort it takes, as a provider refuses a field or a value it does not know. Sent
    none, or its maximum, `THINKING` runs past the step's time, as it did on the owner's install;
    `slow_thinking` makes it run past at every effort, as a slow provider would.
    """

    wrong: bool = False
    stand_in_answers: bool = False
    slow_thinking: bool = False
    sent: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if request.url.host.endswith(".invalid") and not self.stand_in_answers:
            raise httpx.ConnectError("no such host", request=request)
        body = json.loads(request.content)
        thinks = (request.url.host, body.get("model")) == THINKING
        effort = body.get("reasoning_effort")
        if effort is not None and not (thinks and effort in THINKING_EFFORTS):
            return httpx.Response(
                400, json={"error": {"type": "invalid_request_error", "message": "unknown"}}
            )
        if thinks and (self.slow_thinking or effort in (None, "max")):
            raise httpx.ReadTimeout("still thinking", request=request)
        found = PAIRED.search(json.dumps(body))
        reply = "QZ0000000000000000" if self.wrong else found.group(2) if found else "ready"
        if request.url.path.endswith("/v1/messages"):
            return httpx.Response(
                200,
                json={
                    "id": "msg_acceptance",
                    "type": "message",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [{"type": "text", "text": reply}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 40, "output_tokens": 4},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-acceptance",
                "object": "chat.completion",
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 4},
            },
        )

    def hosts(self) -> set[str]:
        return {one.url.host for one in self.sent}


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """A key for each provider in the environment, the hosted profile, and the transport above.

    The keys are test values of this file's own, which reach nothing: the transport answers every
    request in the process."""
    answering = Providers()
    for one in PROVIDER_SLOTS:
        monkeypatch.setenv(one.env_var, f"test-{one.slug}-not-a-key")
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    monkeypatch.setattr(
        acceptance_models,
        "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(answering)),
    )
    return answering


def laddered(url: str, provider: str = "anthropic") -> None:
    """The ladder the wizard writes for one provider, committed, as an install has one.

    As the superuser, so the routing trigger records it as inferred; what matters here is that a
    check's own ladder is written over it and the committed one is what is left afterwards."""
    from brain.models.default_ladder import default_ladder
    from brain.ops.default_ladder_store import UNRESTRICTED_SCOPE
    from tests.fixtures.scratch_postgres import sql

    for one in default_ladder(provider):
        sql(
            url,
            "INSERT INTO ops.routing_rung (tier, scope, position, role, deployment_id, provider,"
            " model, attempts, timeout_seconds, max_concurrency, enabled)"
            " VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, true)",
            one.tier.value,
            json.dumps(UNRESTRICTED_SCOPE),
            one.position,
            one.role.value,
            one.deployment_id,
            one.provider,
            one.model,
            one.attempts,
            one.timeout_seconds,
            one.max_concurrency,
        )


def live_ladder(url: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT tier, position, provider, model FROM ops.routing_rung WHERE deleted_at IS NULL"
        " ORDER BY tier, position",
    )


def run_models(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=registered((MODULE,)),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
class Embedder:
    """An install's declared embedding leg, which no check may ask: it records every question."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def vector(self, question: str) -> Any:
        self.asked.append(question)
        raise AssertionError("a check's question was sent to the embedding leg")


def test_every_model_check_passes_against_answering_providers_and_leaves_nothing(
    providers: Providers,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**The module run as the worker runs it, against PostgreSQL at head.** Every check passes:
    each provider answers the Models screen's test and a question pinned to it, a question behind a
    step nobody can reach is answered by the next, both routed questions leave their whole route on
    their rows, and the console question is answered from the asker's department. Every provider
    was reached, the stand-in was tried and reached nothing, and every table a check wrote to holds
    what it held before. With an embedding leg declared, no check's question reached it, which is
    `A_CHECK_S_QUESTION_IS_SHOWN_ONLY_ITS_OWN_DOCUMENT`; and no key reached a line of output,
    which is `A_MODEL_CHECK_READS_KEYS_AS_THE_PROBER_DOES`. Delete this and a check that can never
    pass, one that commits a ladder, or one that shows a provider a company document by distance,
    reaches the owner's server first."""
    embedder = Embedder()
    monkeypatch.setattr("brain.tools.startup.question_embedder", lambda *_, **__: embedder)
    with at_head("brain_acceptance_models") as url:
        laddered(url)
        before, ladder = counts(url), live_ladder(url)
        outcomes = run_models(url)
        after, left = counts(url), live_ladder(url)
    said = capsys.readouterr()

    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == len(registered((MODULE,)))
    assert after == before and left == ladder and ladder
    reached = providers.hosts()
    assert {httpx.URL(one.base_url).host for one in PROVIDER_WIRES.values()} <= reached
    assert httpx.URL(STAND_IN_ADDRESS).host in reached
    assert embedder.asked == []
    assert "not-a-key" not in said.out + said.err


@pytest.mark.needs_db
def test_a_question_pinned_to_a_model_that_always_thinks_is_sent_the_lanes_effort(
    providers: Providers,
) -> None:
    """**The owner's install on 2026-09-29, reproduced.** With the owner's matrix as the ladder, the
    moonshot check pins Medium to `kimi-k3`, which thinks at its maximum when it is sent no effort
    and ran past the step's time. The check passes because every request to it carried the answer
    lane's effort in its own word, and no request to any other model carried the field at all,
    which a provider would refuse with a 400 that stops the chain. Delete this and the executor
    can stop sending the effort, and the moonshot check fails on the install again with every
    model check here still green but this one, or start sending it to Anthropic and break them."""
    with at_head("brain_acceptance_models_think") as url:
        laddered(url)
        outcomes = run_models(url)
    assert outcomes["a_question_is_answered_end_to_end_via_moonshot"] == (PASSED, "")
    bodies = [
        ((one.url.host, json.loads(one.content).get("model")), json.loads(one.content))
        for one in providers.sent
        if not one.url.host.endswith(".invalid")
    ]
    thinking = [body.get("reasoning_effort") for name, body in bodies if name == THINKING]
    assert thinking and set(thinking) == {"low"}
    assert all("reasoning_effort" not in body for name, body in bodies if name != THINKING)


@pytest.mark.needs_db
def test_a_model_that_runs_past_its_step_fails_the_check_saying_it_did_not_answer_in_time(
    providers: Providers,
) -> None:
    """The failure half: a thinking model that runs past its step at every effort fails the check,
    and the reason says the provider did not answer in time rather than naming an exception type.
    Delete this and the reason can go back to "stopped on ProviderUnavailable", which is what sent
    the 2026-09-29 diagnosis to the planner rather than to the provider's time."""
    providers.slow_thinking = True
    with at_head("brain_acceptance_models_slow") as url:
        laddered(url)
        outcomes = run_models(url)
    assert outcomes["a_question_is_answered_end_to_end_via_moonshot"] == (
        FAILED,
        "a model call stopped the check: The provider did not answer in time.",
    )
    assert outcomes["a_question_is_answered_end_to_end_via_anthropic"] == (PASSED, "")


@pytest.mark.needs_db
def test_a_stand_in_that_answers_is_no_fallback_and_the_check_says_so(
    providers: Providers,
) -> None:
    """The fallback check's argument, failing: when the first step answers, the chain never moves
    on, and the check fails rather than passing on an answer. Delete this and the check can be
    satisfied by any answer at all, which is not the property M5.6.3 names."""
    providers.stand_in_answers = True
    with at_head("brain_acceptance_models_nofall") as url:
        laddered(url)
        outcomes = run_models(url)
    assert outcomes["a_step_that_cannot_be_reached_falls_back_to_the_next"] == (
        FAILED,
        "the request row did not count one fallback to the working step",
    )


@pytest.mark.needs_db
def test_a_model_that_answers_wrongly_fails_the_console_check(providers: Providers) -> None:
    """The console check reads the words: a model answering with a value no document holds fails
    it. Delete this and the check passes on any prose, whatever the asker was told."""
    providers.wrong = True
    with at_head("brain_acceptance_models_wrong") as url:
        laddered(url)
        outcomes = run_models(url)
    assert outcomes["a_console_question_is_answered_from_the_askers_department_only"] == (
        FAILED,
        "the answer did not say what the asker's own document says",
    )


@pytest.mark.needs_db
def test_with_no_key_every_model_check_says_it_was_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An install whose process can read no key is not asked anything, and says so on every row
    rather than failing. Delete this and an install before its first key reads as broken."""
    for one in PROVIDER_SLOTS:
        monkeypatch.delenv(one.env_var, raising=False)
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")
    with at_head("brain_acceptance_models_nokey") as url:
        outcomes = run_models(url)
    assert {outcome for outcome, _ in outcomes.values()} == {NOT_RUN}


# ------------------------------------------------------------------ what is not checked
def test_rotation_is_not_checked_because_no_policy_lets_a_check_retire_what_it_wrote() -> None:
    """`ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED`, held against the policies it
    rests on: the worker only reads provider slots and the application deletes none, so a slot a
    check wrote would stay; and no check claims M31.3.2.5. Delete this and a policy gaining delete
    leaves the reason standing, or a check claiming rotation arrives with the reason unrevised."""
    from brain.ops.acceptance_models import ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED
    from brain.ops.secrets import VaultRole
    from tests.unit.test_vault_policies import _granted_paths, _policy_file

    def providers(role: VaultRole) -> set[str]:
        granted = _granted_paths(_policy_file(role).read_text(encoding="utf-8"))
        return {
            cap for path, caps in granted.items() if path.startswith("providers") for cap in caps
        }

    assert providers(VaultRole.WORKER) == {"read"}
    assert not providers(VaultRole.APPLICATION) & {"delete", "destroy"}
    assert "M31.3.2.5" in ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED
    assert all("M31.3.2.5" not in one.leaves for one in registered())


# ------------------------------------------------------------------- the run by hand
class _Engine:
    """An engine that is never connected to, for a load that is replaced."""

    async def dispose(self) -> None:
        return None


def test_a_run_by_hand_holds_the_settings_saved_in_the_console_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process started by hand has no lifespan, so it reads the saved profile before it checks,
    as the worker does before every tick. Delete this and every model check run by hand in the
    application container reads an install saved as hosted as local, and is not run."""
    from brain.install import hold_saved, value_of
    from tests.unit.test_install_settings import _fake_sessions

    sessions = _fake_sessions(monkeypatch, [{"INSTALL_MODEL_PROFILE": "hosted"}])
    monkeypatch.setattr("brain.session.make_session_factory", lambda engine: sessions)
    monkeypatch.setattr(acceptance_run, "make_app_engine", lambda url: _Engine())
    before = hold_saved({})
    try:
        asyncio.run(acceptance_run.hold_what_was_saved("postgresql+psycopg://nowhere.invalid/b"))
        assert value_of("INSTALL_MODEL_PROFILE", {}) == "hosted"
    finally:
        hold_saved(before)


def test_a_run_by_hand_that_cannot_read_the_settings_says_so_and_goes_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive sibling's failure: an unreadable table is one line and no exception, so the
    checks still run on the environment's values. Delete this and a database hiccup stops a run
    by hand before it has checked anything."""

    from tests.unit.test_install_settings import _fake_sessions

    async def unreadable(_: object) -> dict[str, str]:
        raise OSError("refused")

    sessions = _fake_sessions(monkeypatch, [])
    monkeypatch.setattr("brain.ops.install_settings.load", unreadable)
    monkeypatch.setattr("brain.session.make_session_factory", lambda engine: sessions)
    monkeypatch.setattr(acceptance_run, "make_app_engine", lambda url: _Engine())
    asyncio.run(acceptance_run.hold_what_was_saved("postgresql+psycopg://nowhere.invalid/b"))
    assert "the saved settings could not be read" in capsys.readouterr().err
