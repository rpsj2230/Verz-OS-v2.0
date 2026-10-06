"""Install acceptance checks for the routing chain's rules, one per clause of M5.6.3.

`brain.ops.acceptance_models` proves a step nobody can reach is fallen back from, which is one
clause of six. The leaf asks for the rest on the owner's install: a failure outside the closed
trigger set stops the chain, a breaker opens and recovers, a residency rule skips a step or refuses,
a content refusal is never tried on another model, an agent's level and the install's own key are
used, and every attempt is on the request's trace. Each is a check here, and each runs the whole
path a person's question takes: the upload, the passage search, the answer lane, the executor
planning from the ladder in the database, the attempt rows, the breaker replayed from them and the
request row, all inside one rolled-back transaction as `brain.ops.acceptance` requires.

**The failure shapes are answered in the process, by stand-ins speaking the documented error
bodies.** A real provider cannot be made to refuse on content, to say it does not serve a model, to
answer 503 or to come back after its breaker opened, on the day a deploy is checked. So each check's
steps name stand-in providers whose transport is the product's own (`brain.models.wire.
http_transport`, `brain.models.adapter.SdkDriver`) over an `httpx.MockTransport` that answers in the
chat completions shape's documented bodies: a 404 naming `model_not_found`, a 503 naming
`server_error`, a 400 naming `content_policy_violation`, a 200 whose finish reason is
`content_filter`, and a refused connection. Everything after the socket is the product's: the
adapter classifies the body, the executor decides whether to fall back, the answer lane decides what
the asker is told. Nothing leaves the server, and the stand-ins' addresses are under `.invalid`, so
nothing could. Rejected: asking a real provider for a model it does not serve, which is a metered
request proving one shape of five, and an address that answers, which is a request leaving the
server with a bearer on it. See `A_FAILURE_SHAPE_IS_ANSWERED_IN_THE_PROCESS`.

**One real call, where the clause is about the real thing.** "The company's own keys are used"
cannot be shown by a stand-in, so the agent check sends one short question to the Complex step of a
provider this install holds a key for, and asks the worker's key reader where that key was found:
the vault or the environment, never the key. See `THE_KEY_IS_NAMED_BY_WHERE_IT_WAS_FOUND`.

**The residency constraints are pinned inside the transaction, as the ladder is.** A stand-in has no
row in the provider registry, so it is `global` and satisfies no constraint, and a company-wide
residency rule on the install would refuse every question these checks ask. So each check retires
the live constraints and adds its own inside its transaction, which no real question reads. See
`THE_CONSTRAINTS_ARE_PINNED_INSIDE_THE_TRANSACTION`.

**A breaker's cooldown passes on the executor's clock, and its store is the install's.** The breaker
is not held anywhere: `brain.models.evidence` replays it from `ops.model_attempt` on every plan, so
the check's failures open it for exactly the check's own plans, and the rows go with the rollback.
The executor takes its clock as a parameter, so the check moves it past the cooldown the replayed
breaker states instead of waiting half a minute. See
`A_BREAKER_S_COOLDOWN_PASSES_ON_THE_CHECK_S_CLOCK`.

**What is not checked here.** The leaf's trace is asserted on the attempt rows, which carry the
request's trace id; a trace graph that draws them is another package's (M24) and not on this commit.
See `THE_TRACE_GRAPH_HALF_WAITS_ON_ITS_STORE`.

Task ids: M5.6.3
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import httpx
from sqlalchemy import func, insert, select, text, update

from brain.core.scope import Scope
from brain.models.evidence import OK, REFUSED, STOPPED
from brain.models.routing import DEFAULT_TIER, FallbackTrigger, Tier
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
from brain.ops.acceptance_models import (
    PROVIDERS,
    STAND_IN,
    STAND_IN_ADDRESS,
    STAND_IN_BEARER,
    STAND_IN_TIMEOUT_SECONDS,
    Paired,
    _live,
    a_reader_with_a_document,
    askable,
    asked,
    asking_app,
    models_for,
    paired_in,
    pinned,
    provider_steps,
    trace_of,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.core.errors import Degraded
    from brain.gate.answer import Answered
    from brain.gate.roster import AgentRoster, StoredAgents
    from brain.models.driver import ModelDriver
    from brain.ops.matrix_gate import RungAddition
    from brain.ops.model_service import ModelService

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 60

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the failure shapes are stand-ins in the process and not real providers.
A_FAILURE_SHAPE_IS_ANSWERED_IN_THE_PROCESS: Final = (
    "No real provider can be made to refuse on content, deny a model, answer 503 or recover on "
    "the day a deploy is checked. So the steps name stand-ins whose transport is the product's "
    "own over a responder in the process, answering in the documented error bodies, and the "
    "adapter, the executor and the answer lane decide what each means. Nothing leaves the server."
)

#: Why a check retires the install's residency constraints inside its transaction.
THE_CONSTRAINTS_ARE_PINNED_INSIDE_THE_TRANSACTION: Final = (
    "A stand-in has no registry row, so it is global and satisfies no residency constraint, and a "
    "company-wide rule would refuse every question a check asks. Each check retires the live "
    "constraints and adds its own inside its rolled-back transaction, which no real question "
    "reads, so the install's rules stand for everybody else throughout."
)

#: Why the breaker check waits for nothing.
A_BREAKER_S_COOLDOWN_PASSES_ON_THE_CHECK_S_CLOCK: Final = (
    "The breaker is replayed from the attempt rows on every plan, and the executor reads its "
    "clock as a parameter, so the check moves that clock past the cooldown the replayed breaker "
    "states. The attempts are the check's own rows in its transaction, so the breaker it opens "
    "is open for its plans alone and gone with the rollback."
)

#: Why the key is described by its source.
THE_KEY_IS_NAMED_BY_WHERE_IT_WAS_FOUND: Final = (
    "The check hears a provider's name each time a call reads its key and asks the worker's key "
    "reader whether the key came from the vault or the environment. It never holds, compares or "
    "prints the key, so proving the install's own vault key answered puts no key anywhere."
)

#: What the trace clause proves and what it leaves to the trace store.
THE_TRACE_GRAPH_HALF_WAITS_ON_ITS_STORE: Final = (
    "Every attempt of a walk is shown on the attempt rows under the request's trace id, in "
    "sequence, and counted against the request row. A trace graph drawing those attempts is the "
    "trace store's (M24), which is not on this commit, so that half is not checked here."
)

# ------------------------------------------------------------------------ the figures
#: The stand-in the registry documents in a region, for the residency check.
RESIDENT: Final = "acceptance_resident"

#: Where the resident is reached. Under `.invalid`, and apart from `STAND_IN_ADDRESS` so the
#: responder can say which of the two a request was sent to.
RESIDENT_ADDRESS: Final = "https://resident.acceptance.invalid/v1"

#: The region acceptance_a's rule allows and the resident is documented in. Not a real region, so
#: no provider of the install's can satisfy it by accident.
REGION: Final = "acceptance-region"

#: The region acceptance_b's rule allows, which no step is in.
ELSEWHERE: Final = "acceptance-elsewhere"

#: What each stand-in model does, by the model name its step asks for.
ANSWERS: Final = "answers"
NOT_SERVED: Final = "not-served"
OVERLOADED: Final = "overloaded"
REFUSES: Final = "refuses"
DECLINES: Final = "declines"
UNREACHABLE: Final = "unreachable"
RECOVERING: Final = "recovering"

#: What an answering stand-in says. Prose, which the answer lane composes and never parses.
STAND_IN_REPLY: Final = "The stand-in answered the acceptance check."

#: The error bodies, in the chat completions shape OpenAI documents for its error object
#: (`{"error": {"message", "type", "param", "code"}}`), which Moonshot and DeepSeek share.
SHAPES: Final[Mapping[str, tuple[int, dict[str, Any]]]] = {
    NOT_SERVED: (
        404,
        {
            "error": {
                "message": "The model does not exist or you do not have access to it.",
                "type": "invalid_request_error",
                "param": None,
                "code": "model_not_found",
            }
        },
    ),
    OVERLOADED: (
        503,
        {
            "error": {
                "message": "The server is overloaded or not ready yet.",
                "type": "server_error",
                "param": None,
                "code": None,
            }
        },
    ),
    REFUSES: (
        400,
        {
            "error": {
                "message": "Your request was rejected by the content policy.",
                "type": "invalid_request_error",
                "param": None,
                "code": "content_policy_violation",
            }
        },
    ),
}

#: The attempt outcomes the checks read, as `brain.models.evidence` records them.
CONNECTION_ERROR: Final = FallbackTrigger.CONNECTION_ERROR.value
PROVIDER_ERROR: Final = FallbackTrigger.PROVIDER_ERROR.value


# ------------------------------------------------------------------------ the stand-ins
@dataclass
class StandIns:
    """The failure shapes, answered where the request was built. See the reason above.

    Reads the model a request names and nothing else of it, and counts each request by the host
    and model it was sent to. `recovered` is the recovering stand-in coming back.
    """

    recovered: bool = False
    asked: Counter[tuple[str, str]] = field(default_factory=Counter)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        model = str(json.loads(request.content).get("model", ""))
        self.asked[(request.url.host, model)] += 1
        if model == UNREACHABLE or (model == RECOVERING and not self.recovered):
            raise httpx.ConnectError("no such host", request=request)
        shaped = SHAPES.get(model)
        if shaped is not None:
            return httpx.Response(shaped[0], json=shaped[1])
        declined = model == DECLINES
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-acceptance",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None if declined else STAND_IN_REPLY,
                        },
                        "finish_reason": "content_filter" if declined else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 0 if declined else 8},
            },
        )

    def sent_to(self, address: str, model: str | None = None) -> int:
        """How many requests went to the stand-in at `address`, for `model` or for any."""
        host = httpx.URL(address).host
        return sum(
            n for (at, named), n in self.asked.items() if at == host and model in (None, named)
        )


def stand_in_drivers(h: Harness, responder: StandIns) -> dict[str, ModelDriver]:
    """The two stand-ins, each the product's own driver over a transport the responder answers."""
    from brain.models.adapter import SdkDriver
    from brain.models.wire import added_wire, http_transport
    from brain.ops.provider_keys import added_slot

    client = httpx.Client(transport=httpx.MockTransport(responder), follow_redirects=False)
    h.removes(client.close)
    return {
        slug: SdkDriver(
            provider=slug,
            transport=http_transport(
                added_wire(slug, address, added_slot(slug)),
                client=client,
                key=lambda: STAND_IN_BEARER,
            ),
        )
        for slug, address in ((STAND_IN, STAND_IN_ADDRESS), (RESIDENT, RESIDENT_ADDRESS))
    }


def step(model: str, *, provider: str = STAND_IN, tier: Tier = DEFAULT_TIER) -> RungAddition:
    """One stand-in step at the level an unpinned question is asked at, tried once."""
    from brain.ops.matrix_gate import RungAddition

    return RungAddition(
        tier=tier,
        provider=provider,
        model=model,
        attempts=1,
        timeout_seconds=STAND_IN_TIMEOUT_SECONDS,
        max_concurrency=1,
    )


class Clock:
    """The executor's clock for one check: now, until the check moves it."""

    def __init__(self, start: datetime) -> None:
        self.at = start

    def __call__(self) -> datetime:
        return self.at


# -------------------------------------------------------------- the install, pinned
async def constrained(h: Harness, rules: Sequence[tuple[str, str]]) -> None:
    """The residency constraints, inside the check's transaction, as exactly `rules`: each a
    department and the one region it allows. See
    `THE_CONSTRAINTS_ARE_PINNED_INSIDE_THE_TRANSACTION`.

    Refused first by the Models screen's own rule, then written with the statement its route runs.
    """
    from brain.models.residency import requirement_of
    from brain.tables.model_health import ResidencyConstraintRow

    live = (
        (
            await h.execute(
                select(ResidencyConstraintRow.id).where(ResidencyConstraintRow.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    statements: list[Any] = []
    if live:
        statements.append(
            update(ResidencyConstraintRow)
            .where(
                ResidencyConstraintRow.id.in_(list(live)),
                ResidencyConstraintRow.deleted_at.is_(None),
            )
            .values(deleted_at=func.statement_timestamp())
        )
    for department, region in rules:
        requirement_of([region], on_prem_only=False)
        statements.append(
            insert(ResidencyConstraintRow).values(
                scope=Scope.department(department).model_dump(mode="json"),
                allowed_regions=[region],
                on_prem_only=False,
                note="Added by an install acceptance check for the length of the check",
                created_by=h.actor,
            )
        )
    if statements:
        await h.execute(*h.attributed(), *statements)


async def documented(h: Harness, provider: str, region: str) -> None:
    """The registry row the Models screen's terms route writes for a provider with none: this one
    pinned to `region`, which is what makes its steps satisfy a rule allowing it."""
    from brain.models.registry import ProviderKind
    from brain.models.routing import ResidencyClass
    from brain.tables.model_registry import ModelProviderRow

    await h.execute(
        *h.attributed(),
        insert(ModelProviderRow).values(
            slug=provider,
            kind=ProviderKind.BUILTIN.value,
            label="Acceptance check stand-in",
            processing_region=region,
            residency_class=ResidencyClass.REGION_PINNED.value,
            updated_by=h.actor,
        ),
    )


def roster_over(h: Harness) -> AgentRoster:
    """The stored agents `/answer` selects from, read through the check's transaction.

    What `brain.app.agent_roster_for` installs, built here because nothing under src imports the
    application: every agent row, and the ones that construct.
    """
    from brain.agent_routes import read_stored_agents

    async def read() -> StoredAgents:
        async with h.sessions() as session:
            return await read_stored_agents(session)

    return read


@dataclass(frozen=True)
class StandingBy:
    """What a stand-in check starts from: a reader, their document, the responder, the executor."""

    reader: str
    paired: Paired
    responder: StandIns
    models: ModelService
    app: FastAPI


async def standing_by(h: Harness, *, clock: Callable[[], datetime] | None = None) -> StandingBy:
    """A member of acceptance_a with a document, no residency rule, and the stand-ins held.

    Not run on an install keeping text on its own hardware: every stand-in is a hosted provider as
    the assembly reads it, so none would be planned, whatever it would have answered.
    """
    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    responder = StandIns()
    models = await models_for(h, standing=stand_in_drivers(h, responder), clock=clock)
    askable(await models.calls.planned(), STAND_IN)
    return StandingBy(reader, paired, responder, models, await asking_app(h, models))


# ------------------------------------------------------------------- asking, and reading
async def asking(
    h: Harness,
    app: FastAPI,
    principal_id: str,
    question: str,
    n: int,
    *,
    agent: str | None = None,
) -> Answered | Degraded:
    """`asked`, with a refusal to answer returned rather than raised, as the route would say it."""
    from brain.core.errors import Degraded

    try:
        return await asked(h, app, principal_id, question, n, agent=agent)
    except Degraded as refused:
        return refused


def answered(outcome: Answered | Degraded) -> bool:
    """Whether a question was answered with prose the passages stand behind."""
    from brain.gate.answer import Answered

    return isinstance(outcome, Answered) and outcome.composed is not None


async def walked(h: Harness, trace_id: str) -> list[tuple[str, str, str | None, str]]:
    """Each attempt this trace made, in order: the step's provider, its model, how it ended, its
    level."""
    rows = (
        await h.execute(
            text(
                "SELECT r.provider, r.model, a.outcome, r.tier FROM ops.model_attempt a"
                " JOIN ops.routing_rung r ON r.id = a.rung_id"
                " WHERE a.trace_id = :trace ORDER BY a.sequence"
            ).bindparams(trace=trace_id)
        )
    ).all()
    return [(str(p), str(m), outcome, str(tier)) for p, m, outcome, tier in rows]


#: The columns of a request row these checks read. Names and counts only.
REQUEST_COLUMNS: Final = (
    "trace_id",
    "provider",
    "model",
    "fallback_count",
    "retry_count",
    "routed_tier",
    "tier_basis",
    "selected_agent",
)


async def request_of(h: Harness, trace_id: str) -> dict[str, Any]:
    """The one request row this trace left, or an empty mapping."""
    rows = (
        await h.execute(
            text(
                f"SELECT {', '.join(REQUEST_COLUMNS)} FROM obs.request_telemetry"  # noqa: S608
                " WHERE trace_id = :trace"
            ).bindparams(trace=trace_id)
        )
    ).all()
    return dict(zip(REQUEST_COLUMNS, rows[0], strict=True)) if len(rows) == 1 else {}


async def breaker_state(models: ModelService, deployment_id: str, at: datetime) -> str:
    """The breaker the next plan replays for this deployment, advanced to `at`."""
    from brain.models.routing import BreakerState

    health = (await models.calls.planned()).health.get(deployment_id)
    if health is None:
        return BreakerState.CLOSED.value
    return health.breaker.advance(at).state.value


# ------------------------------------------------------------ 1. the closed trigger set
@check(
    leaves=("M5.6.3",),
    sentence=(
        "Behind a step answering as a provider does for a model it does not serve (404), a "
        "question from a member of acceptance_a is not tried on the next step and is told no model "
        "could be reached; behind a step answering 503, the next step answers it."
    ),
)
async def only_a_failure_in_the_closed_set_moves_to_the_next_step(h: Harness) -> None:
    from brain.models.driver import ProviderUnavailable

    s = await standing_by(h)
    await pinned(h, (step(NOT_SERVED), step(ANSWERS)))
    stopped = await asking(h, s.app, s.reader, s.paired.question, 1)
    if (
        not isinstance(stopped, ProviderUnavailable)
        or await walked(h, trace_of(h, 1)) != [(STAND_IN, NOT_SERVED, STOPPED, DEFAULT_TIER)]
        or s.responder.sent_to(STAND_IN_ADDRESS, ANSWERS)
    ):
        raise CheckFailedError(
            "a failure outside the closed set did not stop the chain at its step"
        )
    await pinned(h, (step(OVERLOADED), step(ANSWERS)))
    moved = await asking(h, s.app, s.reader, s.paired.question, 2)
    row = await request_of(h, trace_of(h, 2))
    if (
        not answered(moved)
        or row.get("fallback_count") != 1
        or [one[1:3] for one in await walked(h, trace_of(h, 2))]
        != [(OVERLOADED, PROVIDER_ERROR), (ANSWERS, OK)]
    ):
        raise CheckFailedError("a failure inside the closed set was not answered by the next step")


# ----------------------------------------------------------------- 2. the breaker
@check(
    leaves=("M5.6.3",),
    sentence=(
        "A step that cannot be reached fails three questions in a row, each answered by the "
        "next step; its breaker, replayed from the attempt rows, opens and the fourth question "
        "skips it; past the cooldown on the executor's clock the next question is let through as "
        "the probe, is answered, and the breaker closes."
    ),
)
async def a_failing_step_s_breaker_opens_and_closes_after_its_cooldown(h: Harness) -> None:
    from brain.models.routing import BreakerState

    clock = Clock(h.now)
    s = await standing_by(h, clock=clock)
    await pinned(h, (step(RECOVERING), step(ANSWERS)))
    recovering = step(RECOVERING).deployment_id
    for n in (1, 2, 3):
        clock.at += timedelta(seconds=1)
        one = await asking(h, s.app, s.reader, s.paired.question, n)
        if not answered(one) or [x[1:3] for x in await walked(h, trace_of(h, n))] != [
            (RECOVERING, CONNECTION_ERROR),
            (ANSWERS, OK),
        ]:
            raise CheckFailedError("a step that could not be reached was not fallen back from")
    if await breaker_state(s.models, recovering, clock()) != BreakerState.OPEN.value:
        raise CheckFailedError("three failures in a row did not open the step's breaker")
    clock.at += timedelta(seconds=1)
    skipped = await asking(h, s.app, s.reader, s.paired.question, 4)
    if (
        not answered(skipped)
        or [x[1:3] for x in await walked(h, trace_of(h, 4))] != [(ANSWERS, OK)]
        or s.responder.sent_to(STAND_IN_ADDRESS, RECOVERING) != 3
    ):
        raise CheckFailedError("a step whose breaker was open was sent a question")
    health = (await s.models.calls.planned()).health.get(recovering)
    until = None if health is None else health.breaker.cooldown_until
    if until is None:
        raise CheckFailedError("an open breaker stated no end to its cooldown")
    s.responder.recovered = True
    clock.at = until + timedelta(seconds=1)
    if await breaker_state(s.models, recovering, clock()) != BreakerState.HALF_OPEN.value:
        raise CheckFailedError("the breaker did not come half open once its cooldown had passed")
    probe = await asking(h, s.app, s.reader, s.paired.question, 5)
    if not answered(probe) or [x[1:3] for x in await walked(h, trace_of(h, 5))] != [
        (RECOVERING, OK)
    ]:
        raise CheckFailedError(
            "the first question after the cooldown was not let through as the probe"
        )
    if await breaker_state(s.models, recovering, clock()) != BreakerState.CLOSED.value:
        raise CheckFailedError("the probe answering did not close the breaker")


# --------------------------------------------------------------------- 3. residency
@check(
    leaves=("M5.6.3",),
    sentence=(
        "With acceptance_a's residency rule allowing one region and acceptance_b's another, a "
        "member of acceptance_a is answered by the step documented in their region and the step "
        "documented nowhere is sent nothing; a member of acceptance_b, whose region no step is in, "
        "is refused with the product's sentence and nothing is sent."
    ),
)
async def a_residency_rule_skips_steps_outside_its_region_or_refuses(h: Harness) -> None:
    from brain.core.errors import to_public
    from brain.models.routing import RESIDENCY_REFUSAL, NoCompliantRoute

    s = await standing_by(h)
    library, member = h.principal(B, "library"), h.principal(B, "member")
    await h.person(library, department=B, grants=_in(B, "admin:knowledge"))
    await h.person(member, department=B, grants=_in(B, *KNOWLEDGE_READS))
    theirs = await paired_in(h, B, library)
    await documented(h, RESIDENT, REGION)
    await constrained(h, ((A, REGION), (B, ELSEWHERE)))
    await pinned(h, (step(ANSWERS), step(ANSWERS, provider=RESIDENT)))
    kept = await asking(h, s.app, s.reader, s.paired.question, 1)
    if not answered(kept) or [x[:3] for x in await walked(h, trace_of(h, 1))] != [
        (RESIDENT, ANSWERS, OK)
    ]:
        raise CheckFailedError("a question under a residency rule was not answered in its region")
    if s.responder.sent_to(STAND_IN_ADDRESS):
        raise CheckFailedError("a step outside the department's region was sent its question")
    refused = await asking(h, s.app, member, theirs.question, 2)
    if not isinstance(refused, NoCompliantRoute) or to_public(refused) != RESIDENCY_REFUSAL:
        raise CheckFailedError(
            "a question whose region no step is in was not refused with the product's sentence"
        )
    if await walked(h, trace_of(h, 2)) or s.responder.sent_to(RESIDENT_ADDRESS) != 1:
        raise CheckFailedError("a question whose region no step is in was sent to a model")


# ------------------------------------------------------------------ 4. a content refusal
@check(
    leaves=("M5.6.3",),
    sentence=(
        "A step whose model declines on content, once as a 400 naming the content policy and once "
        "as a reply whose finish reason is the content filter, is not tried on the next step: the "
        "member of acceptance_a is told the model declined, and each question has one attempt."
    ),
)
async def a_content_refusal_is_never_tried_on_another_model(h: Harness) -> None:
    from brain.gate.abstain import AbstentionReason
    from brain.gate.answer import Answered

    s = await standing_by(h)
    for n, declining, ended in ((1, REFUSES, REFUSED), (2, DECLINES, OK)):
        await pinned(h, (step(declining), step(ANSWERS)))
        told = await asking(h, s.app, s.reader, s.paired.question, n)
        if (
            not isinstance(told, Answered)
            or told.abstention is None
            or told.abstention.reason is not AbstentionReason.REFUSED
        ):
            raise CheckFailedError("a model declining on content was not told to the asker as such")
        if [x[1:3] for x in await walked(h, trace_of(h, n))] != [(declining, ended)]:
            raise CheckFailedError("a refusal on content was tried on another model")
    if s.responder.sent_to(STAND_IN_ADDRESS, ANSWERS):
        raise CheckFailedError("a refusal on content was tried on another model")


# ------------------------------------------------- 5. an agent's level and the install's key
@check(
    leaves=("M5.6.3",),
    sentence=(
        "A member of acceptance_a asks through an agent whose level is Complex: the request row "
        "records the heavy level the agent pinned, the one attempt is the Complex step of a "
        "provider whose key the call read from the install's vault, and the Medium step, a "
        "stand-in, is sent nothing."
    ),
)
async def an_agents_complex_question_uses_heavy_and_the_vault_key(h: Harness) -> None:
    from brain.models.routing import TierBasis
    from brain.ops.acceptance_checks_skills import _an_agent
    from brain.ops.model_probe_run import KeySource, worker_provider_keys
    from brain.ops.provider_keys import PROVIDER_SLOTS

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    agent = await _an_agent(
        h, h.principal(A, "library"), tier=Tier.HEAVY, capabilities=KNOWLEDGE_READS
    )
    responder = StandIns()
    reads: list[str] = []
    models = await models_for(h, standing=stand_in_drivers(h, responder), told=reads.append)
    plan = await models.calls.planned()
    keys = worker_provider_keys(h.settings.vault_address, h.settings.vault_token)
    slots = {one.slug: one for one in PROVIDER_SLOTS}
    usable = [one for one in PROVIDERS if one in plan.held and one not in plan.state.switched_off]
    if not usable:
        raise CheckNotRunError("no provider is switched on with a key, so nothing can answer")
    sources = {
        one: await asyncio.to_thread(keys.source, slots[one], time.monotonic()) for one in usable
    }
    working = next((one for one in usable if sources[one] is KeySource.VAULT), usable[0])
    askable(plan, working)
    heavy = next(one for one in provider_steps(working, await _live(h)) if one.tier is Tier.HEAVY)
    await pinned(h, (step(ANSWERS, tier=Tier.MAIN), heavy))
    app = await asking_app(h, models)
    app.state.agent_roster = roster_over(h)
    through = await asking(h, app, reader, paired.question, 1, agent=agent)
    if not answered(through):
        raise CheckFailedError("a question asked through an agent was not answered")
    row = await request_of(h, trace_of(h, 1))
    if (
        row.get("routed_tier") != Tier.HEAVY.value
        or row.get("tier_basis") != TierBasis.PINNED.value
        or row.get("selected_agent") != agent
    ):
        raise CheckFailedError("an agent's Complex question was not routed to the level it pins")
    if await walked(h, trace_of(h, 1)) != [(working, heavy.model, OK, Tier.HEAVY.value)] or (
        responder.sent_to(STAND_IN_ADDRESS)
    ):
        raise CheckFailedError("the agent's question was not answered by the Complex step alone")
    if working not in reads:
        raise CheckFailedError("the call that answered did not read its provider's key")
    if sources[working] is not KeySource.VAULT:
        raise CheckFailedError("the key the call read was not the install's vault key")


# ----------------------------------------------------------------- 6. every attempt traced
@check(
    leaves=("M5.6.3",),
    sentence=(
        "A question from a member of acceptance_a walks three steps, a refused connection, a 503 "
        "and an answer: every attempt made on the check's steps carries the request's trace id, in "
        "sequence from the first, and they number the request row's one attempt plus its "
        "fallbacks and retries."
    ),
)
async def every_attempt_of_a_walk_is_on_the_request_s_trace(h: Harness) -> None:
    s = await standing_by(h)
    await pinned(h, (step(UNREACHABLE), step(OVERLOADED), step(ANSWERS)))
    if not answered(await asking(h, s.app, s.reader, s.paired.question, 1)):
        raise CheckFailedError("a question behind two failing steps was not answered by the third")
    row = await request_of(h, trace_of(h, 1))
    made = (
        await h.execute(
            text(
                "SELECT a.trace_id, a.sequence, a.outcome FROM ops.model_attempt a"
                " JOIN ops.routing_rung r ON r.id = a.rung_id"
                " WHERE r.provider = :provider ORDER BY a.started_at, a.sequence"
            ).bindparams(provider=STAND_IN)
        )
    ).all()
    if not row or any(one[0] != row["trace_id"] for one in made):
        raise CheckFailedError("an attempt of the walk was not on the request's trace")
    if [one[1] for one in made] != list(range(len(made))):
        raise CheckFailedError("the walk's attempts were not in sequence from the first")
    if [one[2] for one in made] != [CONNECTION_ERROR, PROVIDER_ERROR, OK]:
        raise CheckFailedError("the attempt rows did not record each step the walk took")
    if len(made) != 1 + (row["fallback_count"] or 0) + (row["retry_count"] or 0):
        raise CheckFailedError("the request row counted attempts the attempt rows do not hold")
