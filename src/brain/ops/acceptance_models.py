"""Install acceptance checks that reach a model: each provider, a question through each, a fallback.

The checks before these proved the install without a provider, on purpose. These are the ones that
cannot: a provider answering is a fact about the install's keys, its switches and the provider, and
none of it can be shown with a transport that keeps what it is sent. So each check here makes real,
metered calls, and everything around the calls follows `brain.ops.acceptance`'s rules: reserved
people in reserved departments, one rolled-back transaction per check, and a reason that is a
sentence the source wrote.

**The keys are read as the model prober reads them, and never held anywhere a value can leak.**
`brain.ops.model_probe_run.worker_provider_keys` reads each provider's slot from the vault under
the worker's own policy, which names the four slots with `read` and nothing else, keeps the key in
memory and hands it to the product's transport as a lookup. The key never enters the environment, a
request object, a log line, a result or a reason. So these checks run in the worker, on the
schedule, with no change to any vault policy; run by hand in the application container, the
application's own token reads the same four slots. See
`A_MODEL_CHECK_READS_KEYS_AS_THE_PROBER_DOES`.

**The ladder a check needs is written inside its transaction, through the Routing screen's own
statements.** A check that pins a question to one provider, or puts a failing step in front of a
working one, reads the live ladder, retires every step and adds its own with
`brain.routing_routes.add_rung`, so the routing trigger records each change as the screen's would,
and the executor plans from those rows because it reads the ladder through the check's sessions.
The attempt rows, the health rings and any depth alert the calls leave are in the same transaction.
Nothing about the install's real ladder, switches or keys moves, and a real question planning
while a check runs reads the ladder the check has not committed. See
`THE_LADDER_IS_PINNED_INSIDE_THE_TRANSACTION`.

**A question a check asks is shown the check's own document and nothing else.** A provider is sent
the passages the asker may read, and a reserved reader may read every company-wide document, so a
check asking an ordinary question would send the company's words to a provider. The questions
here name a word nothing else holds, and the passage search is the text leg alone, whose query needs
every word of the question, so the only passage any provider is shown is the check's own sentence.
Rejected: the registered search with the install's embedding leg, whose nearest neighbours at a
reader's reach include every company-wide document whatever the question says. See
`A_CHECK_S_QUESTION_IS_SHOWN_ONLY_ITS_OWN_DOCUMENT`.

**A provider made to fail is a step nobody can reach.** The fallback check's first step names a
stand-in provider at an address under `.invalid`, which RFC 6761 reserves and no resolver answers,
so the product's own transport fails to connect, a trigger in `FallbackTrigger`'s closed set, and
the chain moves to the next step with no request having left the server. Rejected: a model the
provider cannot serve, which a provider answers with a 404 the closed set rightly does not fall back
on, and a timeout too short to answer, which sends a real request a provider may still bill. See
`A_STEP_NOBODY_CAN_REACH_IS_A_PROVIDER_MADE_TO_FAIL`.

**What a deployed commit costs.** One sixteen-token test per provider switched on with a key, one
short question per provider, one question behind the failing step, one routed question and one
question in the console: at most eleven calls, none carrying a word of the company's data. A
provider switched off, holding no key, or an install keeping text on its own hardware is not asked,
and its check says so rather than failing.

**What is not checked here, and why.** M31.3.2.5, rotation without a redeploy, needs a slot written
twice and read back by the running process. The worker's policy writes nothing; the application's
writes `providers/data/+` and deletes nothing, by design, so a slot a check wrote would stay in the
vault for good, and each write would reach the audit ledger through the vault's audit device, which
no transaction rolls back. Rotating a real provider's slot would handle a real key. So there is no
check for it; see `ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED`.

Task ids: M38.5.1, M3.6.3, M5.7.1, M5.6.1, M5.6.3, M38.2.2.2
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import httpx
from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

# The documents check's upload and its reader's grants, imported rather than copied, and imported
# first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from datetime import datetime

    from fastapi import FastAPI

    from brain.gate.answer import Answered
    from brain.models.calls import Planned
    from brain.models.driver import ModelDriver
    from brain.ops.matrix_gate import RungAddition
    from brain.ops.model_service import ModelService

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a check that calls a provider can read its key, and where the key goes.
A_MODEL_CHECK_READS_KEYS_AS_THE_PROBER_DOES: Final = (
    "The check reads each provider's key from the vault under the policy the model prober "
    "already reads it under, keeps it in memory and hands it to the product's transport as a "
    "lookup at the moment of the call. It never enters the environment, a request object, a log "
    "line, a stored result or a reason."
)

#: Why the ladder a check needs never reaches the install's own questions.
THE_LADDER_IS_PINNED_INSIDE_THE_TRANSACTION: Final = (
    "A check that needs a step of its own retires the live ladder and adds its steps through the "
    "Routing screen's statements inside its rolled-back transaction, so the executor plans from "
    "them for the check's calls alone, and every real question keeps planning from the committed "
    "ladder while the check runs and after it ends."
)

#: Why a question a check asks cannot send a company's words to a provider.
A_CHECK_S_QUESTION_IS_SHOWN_ONLY_ITS_OWN_DOCUMENT: Final = (
    "A reserved reader may read company-wide documents, and a model is shown what its asker may "
    "read. So the question names a word nothing else holds and the passage search is the text "
    "leg alone, whose query needs every word, and the only passage a provider is shown is the "
    "check's own sentence. The embedding leg is left out because its nearest neighbours are "
    "chosen by distance and not by the word."
)

#: Why the failing step is an address nobody answers.
A_STEP_NOBODY_CAN_REACH_IS_A_PROVIDER_MADE_TO_FAIL: Final = (
    "The first step names a stand-in provider under .invalid, which no resolver answers, so the "
    "product's transport fails to connect, a trigger in the closed set, and no request leaves "
    "the server. A model the provider cannot serve is answered 404, which the closed set does not "
    "fall back on, and a timeout too short to answer still sends a request a provider may bill."
)

#: Why rotation without a redeploy has no check, stated where the checks are.
ROTATION_IS_NOT_CHECKED_BECAUSE_A_SLOT_CANNOT_BE_RETIRED: Final = (
    "Proving a rotation needs a slot written twice and read back by the running process. The "
    "worker's vault policy writes nothing, and the application's writes provider slots and "
    "deletes none by design, so a slot a check wrote would stay in the vault for good and each "
    "write would reach the ledger through the vault's audit device, which no transaction rolls "
    "back. Rotating a real provider's slot would handle a real key, so M31.3.2.5 is not checked."
)

# ------------------------------------------------------------------------ the figures
#: The four providers the owner named, as the product spells them, with the names a person reads.
PROVIDERS: Final[Mapping[str, str]] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "moonshot": "Moonshot",
    "deepseek": "DeepSeek",
}

#: The stand-in the fallback check's first step names. A provider slug nothing else uses.
STAND_IN: Final = "acceptance_stand_in"

#: Where the stand-in is reached. `.invalid` is reserved by RFC 6761 and resolves nowhere.
STAND_IN_ADDRESS: Final = "https://stand-in.acceptance.invalid/v1"

#: What the stand-in's transport would present as a key, to nowhere. Not a key: nothing holds it.
STAND_IN_BEARER: Final = "acceptance-stand-in"

#: How long the stand-in's step waits. A connection refused by the resolver ends far sooner.
STAND_IN_TIMEOUT_SECONDS: Final = 10.0

#: The question the documents answer, around the key word the check's document pairs.
ASKED: Final = "What is {key} paired with?"

#: The one sentence each document of a check holds.
PAIRED: Final = "{key} is paired with {value}."


# ------------------------------------------------------------------------- the models
def _client() -> httpx.Client:
    """The HTTP client a check's calls share. A function, so a test can hand in its own."""
    return httpx.Client(follow_redirects=False)


async def models_for(
    h: Harness,
    *,
    stand_in: bool = False,
    standing: Mapping[str, ModelDriver] | None = None,
    clock: Callable[[], datetime] | None = None,
    told: Callable[[str], None] | None = None,
) -> ModelService:
    """The executor over the check's transaction, with keys read as the prober reads them.

    The drivers are the product's, one per provider this product reaches, each handed its key as
    a lookup; which keys are held is asked once, off the event loop, because asking may read the
    vault. `stand_in` adds the step nobody can reach, for the fallback check. See
    `A_MODEL_CHECK_READS_KEYS_AS_THE_PROBER_DOES`.

    For the routing checks (`brain.ops.acceptance_routing`): `standing` adds drivers answering in
    the process, each held as if keyed; `clock` is the executor's clock, so a breaker's cooldown
    can pass without anybody waiting for it; and `told` hears a provider's name each time a call
    reads its key, and never the key.
    """
    from brain.install import value_of
    from brain.models.adapter import SdkDriver
    from brain.models.calls import ModelCalls
    from brain.models.wire import PROVIDER_WIRES, KeyLookup, added_wire, http_transport
    from brain.ops.model_probe_run import worker_provider_keys
    from brain.ops.model_service import ModelService, SessionAttempts, SessionLadder, wall_clock
    from brain.ops.provider_health_store import SessionDepthAlerts, SessionHealth
    from brain.ops.provider_keys import PROVIDER_SLOTS, added_slot

    keys = worker_provider_keys(h.settings.vault_address, h.settings.vault_token)
    held = await asyncio.to_thread(keys.held, PROVIDER_SLOTS, time.monotonic())
    client = _client()
    h.removes(client.close)
    slots = {one.slug: one for one in PROVIDER_SLOTS}

    def key_of(slug: str) -> KeyLookup:
        lookup = keys.lookup(slots[slug])
        if told is None:
            return lookup

        def read() -> str | None:
            told(slug)
            return lookup()

        return read

    drivers: dict[str, ModelDriver] = {
        slug: SdkDriver(
            provider=slug,
            transport=http_transport(wire, client=client, key=key_of(slug)),
        )
        for slug, wire in PROVIDER_WIRES.items()
        if slug in slots
    }
    if stand_in:
        wire = added_wire(STAND_IN, STAND_IN_ADDRESS, added_slot(STAND_IN))
        drivers[STAND_IN] = SdkDriver(
            provider=STAND_IN,
            transport=http_transport(wire, client=client, key=lambda: STAND_IN_BEARER),
        )
        held = held | {STAND_IN}
    # Never over a product driver: a stand-in named like a provider would answer for it.
    extra = {slug: one for slug, one in (standing or {}).items() if slug not in PROVIDER_WIRES}
    drivers.update(extra)
    held = held | frozenset(extra)

    def profile() -> str:
        try:
            return value_of("INSTALL_MODEL_PROFILE")
        except Exception:
            # An unreadable profile is the local one, which sends nothing anywhere.
            return ""

    calls = ModelCalls(
        ladder=SessionLadder(h.sessions),
        attempts=SessionAttempts(h.sessions),
        drivers=drivers,
        profile=profile,
        held=lambda: held,
        clock=wall_clock if clock is None else clock,
        health=SessionHealth(h.sessions),
        alerts=SessionDepthAlerts(h.sessions),
    )
    return ModelService(calls=calls, client=client)


def askable(plan: Planned, provider: str) -> None:
    """Whether this provider may be asked on this install now, or the check not run and why."""
    from brain.models.assembly import local_only

    if local_only(plan.profile):
        raise CheckNotRunError(
            "this install keeps text on its own hardware, so no provider is asked"
        )
    if provider in plan.state.switched_off:
        raise CheckNotRunError(
            "an administrator has switched this provider off, so it is not asked"
        )
    if provider not in plan.held:
        raise CheckNotRunError(
            "this provider holds no key the process can read, so it is not asked"
        )


# ------------------------------------------------------------------------- the ladder
async def _live(h: Harness) -> list[Any]:
    """The live ladder as the Routing screen reads it, in chain order."""
    from brain.routing_routes import MAX_RUNGS_PER_PAGE, live_rungs

    return list((await h.execute(live_rungs(MAX_RUNGS_PER_PAGE))).scalars().all())


def provider_steps(provider: str, live: Sequence[Any]) -> tuple[RungAddition, ...]:
    """One step per default level for `provider`: the model the install's own first live step for
    it names in that level, else the product's default, with a default step's numbers."""
    from brain.models.default_ladder import DEFAULT_MODELS, DEFAULT_TIERS, default_rung
    from brain.ops.matrix_gate import RungAddition

    steps: list[RungAddition] = []
    for tier in DEFAULT_TIERS:
        own = next(
            (
                str(row.model)
                for row in live
                if row.provider == provider and row.tier == tier.value and row.enabled
            ),
            None,
        )
        model = own or DEFAULT_MODELS[provider][tier]
        numbers = default_rung(provider, tier, model)
        steps.append(
            RungAddition(
                tier=tier,
                provider=provider,
                model=model,
                attempts=numbers.attempts,
                timeout_seconds=numbers.timeout_seconds,
                max_concurrency=numbers.max_concurrency,
            )
        )
    return tuple(steps)


async def pinned(h: Harness, steps: Sequence[RungAddition]) -> None:
    """The ladder, inside the check's transaction, as exactly `steps`, each level in the order
    given. See `THE_LADDER_IS_PINNED_INSIDE_THE_TRANSACTION`."""
    from brain.models.routing import RungRole
    from brain.routing_routes import add_rung, retire_rungs

    live = await _live(h)
    statements: list[Any] = [retire_rungs([row.id for row in live])] if live else []
    first: dict[str, str] = {}
    placed: dict[str, int] = {}
    for step in steps:
        position = placed.get(step.tier.value, 0)
        placed[step.tier.value] = position + 1
        lead = first.setdefault(step.tier.value, step.provider)
        role = (
            RungRole.PRIMARY
            if position == 0
            else RungRole.SAME_PROVIDER_FAILOVER
            if lead == step.provider
            else RungRole.CROSS_PROVIDER_FAILOVER
        )
        statements.append(add_rung(uuid.uuid4(), step, position, role))
    await h.execute(*h.attributed(), *statements)


# ---------------------------------------------------------------------- the asking
@dataclass(frozen=True)
class Paired:
    """A document uploaded for one check: the key word it pairs and the value it pairs it with."""

    key: str
    value: str

    @property
    def question(self) -> str:
        return ASKED.format(key=self.key)


async def paired_in(h: Harness, department: str, uploader: str, key: str | None = None) -> Paired:
    """A Markdown document placed in `department` by `uploader`, pairing two words nothing else
    holds, through the upload route's own sequence."""
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.ops.acceptance_documents import a_markdown_document

    made = Paired(key=key or h.word(), value=h.word())
    body = a_markdown_document("Acceptance check", PAIRED.format(key=made.key, value=made.value))
    read = await _upload(
        h,
        uploader,
        filename="Acceptance.md",
        declared=MediaType.MARKDOWN.value,
        body=body,
        department=department,
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed document the door accepts could not be read")
    return made


async def a_reader_with_a_document(h: Harness) -> tuple[str, Paired]:
    """Both departments founded, a document in acceptance_a, and a member there who reads it."""
    await h.found_departments()
    library, reader = h.principal(A, "library"), h.principal(A, "member")
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    return reader, await paired_in(h, A, library)


async def asking_app(h: Harness, models: ModelService) -> FastAPI:
    """The state `/answer` reads, each part over the check's transaction, with `models`.

    What `brain.app.lifespan` installs, built here because nothing under src imports the
    application: the registry over the install's rows, its rules, the recorders of the ledger's
    row and its cost, and a passage search that is the text leg alone, for
    `A_CHECK_S_QUESTION_IS_SHOWN_ONLY_ITS_OWN_DOCUMENT`. No cache and no windows, so nothing
    outlives the transaction.
    """
    from fastapi import FastAPI

    from brain.gate.model_lane import DocumentSearchTool
    from brain.gate.rule_store import load_rules
    from brain.knowledge.document_tools import searcher
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.telemetry_store import TelemetryRecorder
    from brain.ops.trace_sink import CountingTraceSink
    from brain.ops.usage_store import UsageRecorder
    from brain.tools.startup import build_registry

    try:
        rules = await load_rules(h.sessions)
    except Exception:
        # The lifespan's choice for a rule table that cannot be read: an empty rule set.
        rules = ()
    app = FastAPI()
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    state.fast_path_rules = rules
    state.trace_sink = CountingTraceSink()
    state.request_recorders = (TelemetryRecorder(h.sessions), UsageRecorder(h.sessions))
    state.models = models
    state.passage_search = DocumentSearchTool(handler=searcher(SessionRowSource(h.sessions)))
    return app


async def asked(
    h: Harness,
    app: FastAPI,
    principal_id: str,
    question: str,
    n: int,
    *,
    agent: str | None = None,
    at: datetime | None = None,
) -> Answered:
    """One question through `/answer`'s own function, as `principal_id` in the console.

    `brain.api_routes.answered_for` for the reserved person at the reach the console admits a
    signed-in person, under a trace of this check's own, which the request row and every attempt
    row then carry. A window refusing it is a failure: the check installs no windows. `agent` is
    the agent picked beside the question, as the web application sends it.

    `at` is the instant the question is asked, the check's start unless said otherwise. A check
    reading an answer's freshness asks at the moment it asks, because everything it wrote since
    its start carries a later time, and a read time after the moment of asking is one the product
    rightly refuses to date.
    """
    from starlette.requests import Request

    from brain.api_routes import Answering, Question, answered_for
    from brain.gate.admission import Assurance, admit
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    now = h.now if at is None else at
    outcome = await answered_for(
        request,
        open_trace(trace_of(h, n), now, Channel.CONSOLE),
        Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=now),
        Question(question=question, agent=agent),
    )
    if not isinstance(outcome, Answered):
        raise CheckFailedError("a question was refused by a window the check never installs")
    return outcome


def trace_of(h: Harness, n: int) -> str:
    """The trace the check's `n`th request runs under."""
    return f"{h.trace_id}-{n}"


#: The columns of a request row a check reads. Names and counts only, as the ledger holds.
ROW_COLUMNS: Final = (
    "lane",
    "routed_lane",
    "lane_basis",
    "routed_tier",
    "tier_basis",
    "provider",
    "model",
    "fallback_count",
    "tokens_in",
)


async def request_row(h: Harness, trace_id: str) -> dict[str, Any] | None:
    """The one request row this trace left in the check's transaction, or None."""
    rows = (
        await h.execute(
            text(
                f"SELECT {', '.join(ROW_COLUMNS)} FROM obs.request_telemetry"  # noqa: S608
                " WHERE trace_id = :trace"
            ).bindparams(trace=trace_id)
        )
    ).all()
    return dict(zip(ROW_COLUMNS, rows[0], strict=True)) if len(rows) == 1 else None


async def attempts_of(h: Harness, trace_id: str) -> list[tuple[str, str | None, str]]:
    """Each attempt this trace made, in order: the step's provider, how it ended, its level."""
    rows = (
        await h.execute(
            text(
                "SELECT r.provider, a.outcome, r.tier FROM ops.model_attempt a"
                " JOIN ops.routing_rung r ON r.id = a.rung_id"
                " WHERE a.trace_id = :trace ORDER BY a.sequence"
            ).bindparams(trace=trace_id)
        )
    ).all()
    return [(str(provider), outcome, str(tier)) for provider, outcome, tier in rows]


def shown(answered: Answered) -> str:
    """Every passage the model was shown, as one text: the composed answer's payload."""
    if answered.composed is None:
        return ""
    return json.dumps([dict(one) for one in answered.composed.payload.records], default=str)


# -------------------------------------------------------------- M5.7.1 each provider
async def _tested(h: Harness, provider: str) -> None:
    """The Models screen's Test for one provider, pressed by a reserved administrator."""
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.provider_routes import checked_through, may_switch, switchable
    from brain.routing_routes import MATRIX_WRITE

    await h.found_departments()
    admin = h.principal(A, "models")
    await h.person(admin, department=A, grants=((MATRIX_WRITE.value, Scope.unrestricted()),))
    reach = await h.reach(admin)
    if not may_switch(reach, h.now):
        raise CheckFailedError("an administrator holding the routing authority could not test")
    models = await models_for(h)
    plan = await models.calls.planned()
    askable(plan, provider)
    if provider not in switchable(plan):
        raise CheckFailedError("the Models screen does not offer this provider to test")
    person = await StoredPrincipals(h.sessions).live_principal(admin)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    view = await checked_through(
        models.calls,
        plan,
        provider,
        origin=Origin(trace_id=trace_of(h, 1), principal=person, channel=Channel.CONSOLE),
        at=h.now,
        entitlement_hash=reach.ent_hash(),
        recorders=asking_recorders(h),
    )
    if not view.answered:
        raise CheckFailedError("the provider did not answer the Models screen's test")
    row = await request_row(h, trace_of(h, 1))
    if row is None or row["provider"] != provider or not row["tokens_in"]:
        raise CheckFailedError("the test's request row did not name the provider and its tokens")


def asking_recorders(h: Harness) -> tuple[Any, ...]:
    """The ledger's row and the cost, over the check's transaction."""
    from brain.ops.telemetry_store import TelemetryRecorder
    from brain.ops.usage_store import UsageRecorder

    return (TelemetryRecorder(h.sessions), UsageRecorder(h.sessions))


# --------------------------------------------------------- M5.6.1 a question through each
async def _answered_through(h: Harness, provider: str) -> None:
    """A question answered end to end with the ladder pinned to one provider."""
    reader, paired = await a_reader_with_a_document(h)
    await pinned(h, provider_steps(provider, await _live(h)))
    models = await models_for(h)
    askable(await models.calls.planned(), provider)
    answered = await asked(h, await asking_app(h, models), reader, paired.question, 1)
    if answered.composed is None:
        raise CheckFailedError("a question the reader's own document answers was not answered")
    row = await request_row(h, trace_of(h, 1))
    if row is None or row["provider"] != provider or row["lane"] != "answer":
        raise CheckFailedError("the question's request row did not name the provider pinned")
    if [one[:2] for one in await attempts_of(h, trace_of(h, 1))] != [(provider, "ok")]:
        raise CheckFailedError("the question was not answered by the one step pinned for it")


def _per_provider(
    provider: str,
    body: Callable[[Harness, str], Coroutine[Any, Any, None]],
    name: str,
) -> Callable[[Harness], Coroutine[Any, Any, None]]:
    """A check body for one provider, named for it, so each has its own row on the page."""

    async def one(h: Harness) -> None:
        await body(h, provider)

    one.__name__ = one.__qualname__ = name
    return one


for _slug, _named in PROVIDERS.items():
    check(
        leaves=("M5.7.1",),
        sentence=(
            f"{_named}, switched on with a key, answers the Models screen's test pressed by a "
            "reserved administrator: one fixed sentence through the product's adapter, metered, "
            "its request row naming the provider and its tokens."
        ),
    )(_per_provider(_slug, _tested, f"the_{_slug}_provider_answers_the_models_screen_test"))

for _slug, _named in PROVIDERS.items():
    check(
        leaves=("M5.6.1",),
        sentence=(
            f"With the ladder pinned to {_named} inside the check, a member of acceptance_a asks "
            "Ask a question their department's document answers, and it is answered end to end, "
            "its request row and its one attempt naming the provider."
        ),
    )(_per_provider(_slug, _answered_through, f"a_question_is_answered_end_to_end_via_{_slug}"))


# -------------------------------------------------------------------- M5.6.3 fallback
@check(
    leaves=("M5.6.3",),
    sentence=(
        "With a first step nobody can reach in front of a working provider, a question is "
        "answered by the second step: the request row counts one fallback and names that "
        "provider, and the attempt rows record the refused connection and then the answer."
    ),
)
async def a_step_that_cannot_be_reached_falls_back_to_the_next(h: Harness) -> None:
    from brain.models.default_ladder import DEFAULT_TIERS
    from brain.models.routing import FallbackTrigger
    from brain.ops.matrix_gate import RungAddition

    reader, paired = await a_reader_with_a_document(h)
    models = await models_for(h, stand_in=True)
    plan = await models.calls.planned()
    working = next(
        (one for one in PROVIDERS if one in plan.held and one not in plan.state.switched_off),
        None,
    )
    if working is None:
        raise CheckNotRunError("no provider is switched on with a key, so nothing can answer")
    askable(plan, working)
    real = provider_steps(working, await _live(h))
    level = DEFAULT_TIERS[0]
    first = RungAddition(
        tier=level,
        provider=STAND_IN,
        model=STAND_IN,
        attempts=1,
        timeout_seconds=STAND_IN_TIMEOUT_SECONDS,
        max_concurrency=1,
    )
    await pinned(h, (first, *real))
    answered = await asked(h, await asking_app(h, models), reader, paired.question, 1)
    if answered.composed is None:
        raise CheckFailedError("the question was not answered once its first step failed")
    row = await request_row(h, trace_of(h, 1))
    if row is None or row["fallback_count"] != 1 or row["provider"] != working:
        raise CheckFailedError("the request row did not count one fallback to the working step")
    tried = [one[:2] for one in await attempts_of(h, trace_of(h, 1))]
    if tried != [(STAND_IN, FallbackTrigger.CONNECTION_ERROR.value), (working, "ok")]:
        raise CheckFailedError(
            "the attempt rows did not record the failed step and then the answer"
        )


# ------------------------------------------------------------ M3.6.3 the whole route
#: The four columns M3.6.3 names: the lane and the rule that chose it, the tier and its step.
ROUTE_COLUMNS: Final = ("routed_lane", "lane_basis", "routed_tier", "tier_basis")


def routed(row: dict[str, Any] | None) -> dict[str, Any]:
    """The row, when it holds the whole routing decision; otherwise the check fails."""
    if row is None or any(row[one] is None for one in ROUTE_COLUMNS):
        raise CheckFailedError("a request row did not hold its lane, tier and both reasons")
    return row


@check(
    leaves=("M3.6.3",),
    sentence=(
        "Two questions from a member of acceptance_a, one a rule answers without a model and one "
        "a model answers through the install's own ladder, each leave a request row holding the "
        "routed lane, the rule that chose it, the tier and the step that settled it, the second "
        "the tier its call was sent to."
    ),
)
async def a_request_row_holds_the_route_it_was_given(h: Harness) -> None:
    from brain.ops.acceptance_checks_chat import uploaded

    reader, paired = await a_reader_with_a_document(h)
    table = await uploaded(h)
    for capability, scope in table.reads(A, held=False):
        await h.grant(reader, capability, scope)
    models = await models_for(h)
    plan = await models.calls.planned()
    if not plan.assembly.answering:
        raise CheckNotRunError("no step of this install's ladder can be called now")
    app = await asking_app(h, models)
    by_rule = await asked(h, app, reader, table.asking(table.open_column), 1)
    # Whether the model's words were right is the console check's business; this one reads rows.
    await asked(h, app, reader, paired.question, 2)
    if by_rule.composed is None or table.seen not in (by_rule.text or ""):
        raise CheckFailedError("a question an uploaded table answers was not answered by it")
    ruled = routed(await request_row(h, trace_of(h, 1)))
    modelled = routed(await request_row(h, trace_of(h, 2)))
    if ruled["model"] is not None or ruled["lane"] != "fast":
        raise CheckFailedError("the question a rule answered was recorded as reaching a model")
    walked = await attempts_of(h, trace_of(h, 2))
    if not walked or walked[0][2] != modelled["routed_tier"]:
        raise CheckFailedError("the row's tier was not the level the model call was sent to")


# --------------------------------------------------------- M38.2.2.2 asked in the console
@check(
    leaves=("M38.2.2.2",),
    sentence=(
        "Documents in acceptance_a and acceptance_b pair one word with two different values; a "
        "member of acceptance_a asks about the word in the console and is answered by a model "
        "with their own department's value, and the other value is never shown to the model."
    ),
)
async def a_console_question_is_answered_from_the_askers_department_only(h: Harness) -> None:
    reader, own = await a_reader_with_a_document(h)
    elsewhere = h.principal(B, "library")
    await h.person(elsewhere, department=B, grants=_in(B, "admin:knowledge"))
    other = await paired_in(h, B, elsewhere, key=own.key)
    models = await models_for(h)
    if not (await models.calls.planned()).assembly.answering:
        raise CheckNotRunError("no step of this install's ladder can be called now")
    answered = await asked(h, await asking_app(h, models), reader, own.question, 1)
    if answered.composed is None:
        raise CheckFailedError("the member's question was not answered from their document")
    seen = shown(answered)
    if own.value not in seen or other.value in seen:
        raise CheckFailedError("the model was shown a document outside the asker's department")
    said = "\n".join(answered.frames)
    if own.value not in said or other.value in said:
        raise CheckFailedError("the answer did not say what the asker's own document says")
