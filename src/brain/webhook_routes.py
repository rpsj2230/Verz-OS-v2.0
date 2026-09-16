"""The Webhooks screen over HTTP: what is registered, where it points, and three confirmed writes.

`brain.console.subscribers` decides what a reader is shown of the subscribers and
`brain.ops.outbox.may_manage` decides who may change one; `brain.ops.webhook_admin` judges a
registration and keeps its secret; `brain.ops.webhook_store` holds the rows. This module asks
each of them in order and decides nothing any of them already decides.

**One capability decides the whole surface, and a reader without it is shown what an install with
no subscribers shows.** That is `brain.console.subscribers.
A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS`, followed rather than restated:
the listing is `subscriber_lines`, which answers nothing for such a reader, and the route asks no
store and no vault first, so a process with a database and one without answer that reader alike.
`manageable` says whether this reader may change anything, which is a fact about the reader and
none about what exists. Every write refuses such a reader with the one refusal, before it judges
what was sent. See `THE_QUESTION_IS_ASKED_BEFORE_ANY_STORE`.

**Every write is judged whole before anything is written, and the answers are four sentences.**
200 with what changed, when, and what that means. 422 with every problem by field and code, of
which a subscriber id already taken is one, because it is a field the person fixes. 409 when the
install runs no vault or the vault refused, and 503 when it did not answer, each with the sentence
from `brain.ops.webhook_admin.TOLD` and nothing written anywhere. 404 for a subscriber that is not
switched on, which a manager can see the list of, so the refusal hides nothing from them.

**No response carries a secret, and a refused body is not echoed.** The router is
`brain.api.NoEchoRoute`, whose refusal names the field without repeating it, and every answer is
built from a subscriber id, times and sentences. Whether a secret is held is read from the vault's
metadata per subscriber and says held, not held, or not known with the vault's state.

**What the screen cannot do is served beside it**, for `brain.skill_routes`' reason: the day a
fact changes, its sentence changes in the same commit. No channel receives a webhook, and each
channel's check is listed with how far it has got; an automation's inbound credential is listed
nowhere.

**Delivery is said in two parts: how it works, and what the dispatch last did.** The first is a
sentence with the code's own figures in it. The second is read from the schedule's record of the
newest `outbox_dispatch` run and from whether a person paused it, and it is judged against this
install's profile first: a profile that runs no worker sends nothing, however long the list of
pending deliveries grows, and that is the sentence such an install is shown. A failed run is shown
by its exception's type and never its message, for `brain.jobs_routes`' reason, except the one
failure whose message is this product's own sentence: a worker with no vault. See
`dispatcher_told`.

Task ids: M27.8.12
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked
from brain.automation_routes import TOOL_CALL_PATH
from brain.console.subscribers import findings, subscriber_lines
from brain.core.errors import Absent, Failed
from brain.install_routes import settings_of
from brain.jobs_routes import failure_kind
from brain.ops.credentials import VaultState
from brain.ops.inbound_webhooks import INBOUND, Verification
from brain.ops.outbox import EventKind, Subscriber, may_manage
from brain.ops.webhook_admin import (
    AN_AUTOMATION_CALLS_IN_WITH_ITS_OWN_CREDENTIAL,
    MINIMUM_SIGNING_SECRET_CHARS,
    NO_CHANNEL_RECEIVES_A_WEBHOOK,
    REGISTERING_A_SUBSCRIBER,
    REPLACING_A_SIGNING_KEY,
    SWITCHING_A_SUBSCRIBER_OFF,
    TOLD,
    Field,
    FieldProblem,
    SecretHeld,
    SigningSecrets,
    SigningSecretsUnavailableError,
    event_kinds,
    how_delivery_works,
    registration_problems,
    secret_problems,
    signing_secret_ref,
    subscriber_id_problems,
)
from brain.ops.webhook_delivery import NO_VAULT_ON_THIS_WORKER
from brain.ops.webhook_store import (
    DispatcherLine,
    NoActiveSubscriberError,
    Registered,
    StoredWebhooks,
    SubscriberTakenError,
    WebhookRecords,
)
from brain.ops.wiring import components_for
from brain.routing_routes import sessions_of
from brain.tables.webhook_change import WebhookChange

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why no store and no vault is asked for a reader who may not manage subscribers.
THE_QUESTION_IS_ASKED_BEFORE_ANY_STORE: Final = (
    "A reader who may not manage subscribers is answered before the database or the vault is "
    "asked, so an install that cannot reach either answers them exactly as one that can. Asking "
    "first would let that reader tell a broken install from a working one by the refusal."
)

#: What a success says, per change.
REGISTERED: Final = (
    "The subscriber is registered and its signing secret is held in the vault. It is included "
    "whenever an event of a kind it takes is written."
)
REPLACED: Final = "The new signing secret is held in the vault and signs every request from now on."
SWITCHED_OFF: Final = "The subscriber is switched off. It is told nothing more."

#: The component that runs the dispatch. `brain.ops.worker.DEFAULT_WORKER_COMPONENT` is the general
#: worker, the one container that ticks the schedule, and a test holds the two equal; it is not
#: imported, because that module brings the queue driver into the process that serves this screen.
DELIVERING_COMPONENT: Final = "brain-worker"

#: What the screen says about the dispatch, by what its state is.
NO_WORKER_ON_THIS_PROFILE: Final = (
    "This install's profile runs no worker, so no webhook is sent: every delivery waits as "
    "pending. The standard and full profiles run the worker that sends them."
)
NOT_RUN_YET: Final = (
    "The worker has not run the dispatch on this install yet, so nothing has been sent. It runs "
    "every minute once the worker is started."
)
PAUSED: Final = (
    "The dispatch is paused on the Scheduled jobs screen, so nothing is sent until somebody "
    "resumes it there. Deliveries wait as pending and none is lost."
)
LAST_RUN_FAILED: Final = (
    "The dispatch's last run failed, so nothing it claimed was recorded as sent, and each of those "
    "deliveries is tried again on the next run. The Scheduled jobs screen has every run."
)
RUNNING: Final = "The dispatch runs every minute, and its last run is shown here."

#: Where the screen is read, and the three writes beneath it.
WEBHOOKS_PATH: Final = "/webhooks"
SUBSCRIBERS_PATH: Final = f"{WEBHOOKS_PATH}/subscribers"
SECRET_PATH: Final = f"{SUBSCRIBERS_PATH}/{{subscriber_id}}/secret"
SWITCH_OFF_PATH: Final = f"{SUBSCRIBERS_PATH}/{{subscriber_id}}/switch-off"

#: The status a write that kept nothing answers, by what the vault's state was.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}

# ------------------------------------------------------------------------ the shapes


class DeliveryView(BaseModel):
    """One recent delivery: its kind, where it got to and why. No record id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind
    state: str
    attempts: int
    occurred_at: datetime
    last_attempt_at: datetime | None
    reason: str | None
    next_attempt_at: datetime | None


class DispatcherView(BaseModel):
    """What the dispatch last did on this install, and the sentence that says what it means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs_here: bool
    paused: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_outcome: str | None
    last_report: str | None
    told: str


class ChangeView(BaseModel):
    """One change made to a subscriber from the console, and who made it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    change: WebhookChange
    changed_by: str
    changed_at: datetime
    secret_written_at: datetime | None


class WebhookSubscriberView(BaseModel):
    """One subscriber. `secret_held` is None when the vault could not be asked, never False.

    Named apart from `brain.govern_people_routes.SubscriberView`, whose name the generated schema
    would otherwise have to qualify with both modules' paths.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subscriber_id: str
    endpoint: str
    kinds: list[str]
    active: bool
    created_by: str
    created_at: datetime
    deactivated_at: datetime | None
    last_delivered_at: datetime | None
    secret_held: bool | None
    secret_written_at: datetime | None
    deliveries: list[DeliveryView]
    changes: list[ChangeView]


class InboundChannelView(BaseModel):
    """One channel a platform would call in on, and how far its check has got."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    verification: Verification
    check: str
    how: str


class InboundView(BaseModel):
    """What arrives from outside: each channel's check, and one door for automations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channels: list[InboundChannelView]
    channels_told: str
    automation_path: str
    automation_told: str


class WebhooksView(BaseModel):
    """The Webhooks screen: outbound subscribers, what the vault says, and what cannot be done."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manageable: bool
    vault: VaultState
    vault_told: str
    subscribers: list[WebhookSubscriberView]
    findings: list[str]
    kinds: list[str]
    delivery: str
    dispatcher: DispatcherView | None
    inbound: InboundView
    registering: str
    replacing: str
    switching_off: str
    secret_minimum: int


class RegistrationAsked(BaseModel):
    """A registration. No length on any field: `registration_problems` judges them in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subscriber_id: str
    endpoint: str
    kinds: list[str]
    secret: str


class SecretAsked(BaseModel):
    """A replacement signing secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    secret: str


class WebhookChangedView(BaseModel):
    """What one write changed, when, and what that means. Never a secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subscriber_id: str
    change: WebhookChange
    changed_at: datetime
    secret_written_at: datetime | None
    told: str


class WebhookProblemView(BaseModel):
    """One thing wrong with what was sent: the field, a stable code, and what to do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: Field
    code: str
    message: str


class WebhookProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[WebhookProblemView]


# ------------------------------------------------------------------------- the wiring


def records_of(request: Request) -> WebhookRecords:
    """What `app.state.webhook_records` holds, or the database, or one process fault."""
    found = getattr(request.app.state, "webhook_records", None)
    if isinstance(found, WebhookRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredWebhooks(sessions)


def signing_secrets_of(request: Request) -> SigningSecrets:
    """What this process was built with, or a store with no vault. See `credentials_of`."""
    found = getattr(request.app.state, "signing_secrets", None)
    return found if isinstance(found, SigningSecrets) else SigningSecrets(None)


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable() -> Absent:
    return Absent("webhook subscribers are not answerable for this caller")


def _problems(found: tuple[FieldProblem, ...]) -> JSONResponse:
    told = WebhookProblemsView(
        problems=[
            WebhookProblemView(field=one.field, code=one.code, message=one.message) for one in found
        ]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _not_kept(state: VaultState) -> JSONResponse:
    body = ErrorBody(message=TOLD[state], trace_id=_trace_id())
    return JSONResponse(status_code=NOT_KEPT_STATUS[state], content=body.model_dump())


def _inbound() -> InboundView:
    return InboundView(
        channels=[
            InboundChannelView(
                channel=one.channel.value,
                verification=one.verification,
                check=one.check,
                how=one.how,
            )
            for one in INBOUND
        ],
        channels_told=NO_CHANNEL_RECEIVES_A_WEBHOOK,
        automation_path=f"{API_PREFIX}{TOOL_CALL_PATH}",
        automation_told=AN_AUTOMATION_CALLS_IN_WITH_ITS_OWN_CREDENTIAL,
    )


def runs_the_dispatch(profile: str) -> bool:
    """Whether an install on this profile runs the worker that sends webhooks."""
    return any(one.name == DELIVERING_COMPONENT for one in components_for(profile))


def dispatcher_told(line: DispatcherLine, *, runs_here: bool) -> str:
    """The one sentence about the dispatch, in the order a person should hear them.

    The profile first, because nothing else matters on an install with no worker; then a pause,
    because a person chose it and is the one to undo it; then whether it has ever run; then how
    its last run ended.
    """
    if not runs_here:
        return NO_WORKER_ON_THIS_PROFILE
    if line.paused:
        return PAUSED
    if line.started_at is None:
        return NOT_RUN_YET
    if line.outcome == "failed":
        return LAST_RUN_FAILED
    return RUNNING


def last_report(line: DispatcherLine) -> str | None:
    """What the last run recorded, as far as it may be shown.

    A run that finished well recorded counts and nothing else. A failed one is its exception's
    type, except a worker with no vault, whose message is this product's own sentence and is the
    one thing a person can act on from here. See the module docstring.
    """
    if line.detail is None:
        return None
    if line.outcome == "ok":
        return line.detail
    if line.outcome == "failed":
        if line.detail.endswith(NO_VAULT_ON_THIS_WORKER):
            return NO_VAULT_ON_THIS_WORKER
        kind = failure_kind(line.detail)
        return None if kind is None else f"The run failed with {kind}."
    return None


def dispatcher_view(line: DispatcherLine, *, runs_here: bool) -> DispatcherView:
    """The dispatcher as the screen draws it, from the schedule's record and the profile."""
    return DispatcherView(
        runs_here=runs_here,
        paused=line.paused,
        last_started_at=line.started_at,
        last_finished_at=line.finished_at,
        last_outcome=line.outcome,
        last_report=last_report(line),
        told=dispatcher_told(line, runs_here=runs_here),
    )


def _page(
    *,
    manageable: bool,
    vault: VaultState,
    subscribers: list[WebhookSubscriberView],
    found: tuple[str, ...],
    dispatcher: DispatcherView | None = None,
) -> WebhooksView:
    return WebhooksView(
        manageable=manageable,
        vault=vault,
        vault_told=TOLD[vault],
        subscribers=subscribers,
        findings=list(found),
        kinds=[one.value for one in EventKind],
        delivery=how_delivery_works(),
        dispatcher=dispatcher,
        inbound=_inbound(),
        registering=REGISTERING_A_SUBSCRIBER,
        replacing=REPLACING_A_SIGNING_KEY,
        switching_off=SWITCHING_A_SUBSCRIBER_OFF,
        secret_minimum=MINIMUM_SIGNING_SECRET_CHARS,
    )


def secrets_held(
    secrets: SigningSecrets, ids: list[str]
) -> tuple[VaultState, dict[str, SecretHeld]]:
    """Whether each subscriber's secret is held, or nothing known and the vault's state.

    One failure answers for the whole list, for `brain.credential_routes.listing`'s reason: a
    vault that did not answer for one subscriber will not answer for the next.
    """
    try:
        return VaultState.READY, {one: secrets.held(one) for one in ids}
    except SigningSecretsUnavailableError as unavailable:
        return unavailable.state, {}


router = APIRouter(prefix=API_PREFIX, tags=["webhooks"], route_class=NoEchoRoute)

_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": WebhookProblemsView, "description": "What is wrong with what was sent."},
}


@router.get(WEBHOOKS_PATH, response_model=WebhooksView, responses=COMMON_RESPONSES)
async def webhooks(request: Request, asked: Asked) -> WebhooksView:
    """Every subscriber, where it points, whether its secret is held, and its recent outcomes."""
    if not may_manage(asked.reach, asked.now):
        # See THE_QUESTION_IS_ASKED_BEFORE_ANY_STORE.
        return _page(manageable=False, vault=VaultState.ABSENT, subscribers=[], found=())
    records = records_of(request)
    registered = await records.registered()
    domain: list[Subscriber] = [one.subscriber for one in registered]
    delivered = {
        one.subscriber.subscriber_id: one.last_delivered_at
        for one in registered
        if one.last_delivered_at is not None
    }
    lines = subscriber_lines(asked.reach, domain, delivered, now=asked.now)
    by_id: dict[str, Registered] = {one.subscriber.subscriber_id: one for one in registered}
    vault, held = await asyncio.to_thread(
        secrets_held, signing_secrets_of(request), [one.subscriber_id for one in lines]
    )
    views = [
        WebhookSubscriberView(
            subscriber_id=line.subscriber_id,
            endpoint=line.endpoint,
            kinds=list(line.kinds),
            active=line.active,
            created_by=line.created_by,
            created_at=by_id[line.subscriber_id].created_at,
            deactivated_at=by_id[line.subscriber_id].deactivated_at,
            last_delivered_at=line.last_delivered_at,
            secret_held=held[line.subscriber_id].held if line.subscriber_id in held else None,
            secret_written_at=(
                held[line.subscriber_id].written_at if line.subscriber_id in held else None
            ),
            deliveries=[
                DeliveryView(
                    kind=one.kind,
                    state=one.state,
                    attempts=one.attempts,
                    occurred_at=one.occurred_at,
                    last_attempt_at=one.last_attempt_at,
                    reason=one.reason,
                    next_attempt_at=one.next_attempt_at,
                )
                for one in by_id[line.subscriber_id].deliveries
            ],
            changes=[
                ChangeView(
                    change=one.change,
                    changed_by=one.changed_by,
                    changed_at=one.changed_at,
                    secret_written_at=one.secret_written_at,
                )
                for one in by_id[line.subscriber_id].changes
            ],
        )
        for line in lines
    ]
    return _page(
        manageable=True,
        vault=vault,
        subscribers=views,
        found=findings(asked.reach, domain, now=asked.now),
        dispatcher=dispatcher_view(
            await records.dispatcher(),
            runs_here=runs_the_dispatch(settings_of(request).profile),
        ),
    )


@router.post(SUBSCRIBERS_PATH, response_model=WebhookChangedView, responses=_WRITE_RESPONSES)
async def register(request: Request, body: RegistrationAsked, asked: Asked) -> JSONResponse:
    """Register a subscriber and keep its signing secret, or write nothing and say why."""
    if not may_manage(asked.reach, asked.now):
        log.info("webhook registration not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = registration_problems(
        subscriber_id=body.subscriber_id,
        endpoint=body.endpoint,
        kinds=body.kinds,
        secret=body.secret,
    )
    if found:
        return _problems(found)
    secrets = signing_secrets_of(request)
    if not secrets.configured:
        return _not_kept(VaultState.ABSENT)
    actor = asked.reach.principal_id
    subscriber = Subscriber(
        subscriber_id=body.subscriber_id,
        endpoint=body.endpoint,
        secret_ref=signing_secret_ref(body.subscriber_id),
        kinds=event_kinds(body.kinds),
        created_by=actor,
    )
    try:
        written = await records_of(request).register(
            subscriber,
            actor=actor,
            at=asked.now,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
            keep_secret=lambda: secrets.keep(body.subscriber_id, body.secret, actor=actor),
        )
    except SubscriberTakenError:
        return _problems(
            (
                FieldProblem(
                    Field.SUBSCRIBER_ID,
                    "taken",
                    "A subscriber with this id is already registered, switched on or off. "
                    "Choose another id.",
                ),
            )
        )
    except SigningSecretsUnavailableError as unavailable:
        return _not_kept(unavailable.state)
    answered = WebhookChangedView(
        subscriber_id=body.subscriber_id,
        change=WebhookChange.REGISTERED,
        changed_at=asked.now,
        secret_written_at=written,
        told=REGISTERED,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(SECRET_PATH, response_model=WebhookChangedView, responses=_WRITE_RESPONSES)
async def replace_secret(
    request: Request, subscriber_id: str, body: SecretAsked, asked: Asked
) -> JSONResponse:
    """Replace a switched-on subscriber's signing secret, or write nothing and say why."""
    if not may_manage(asked.reach, asked.now) or subscriber_id_problems(subscriber_id):
        log.info("webhook secret not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = secret_problems(body.secret)
    if found:
        return _problems(found)
    secrets = signing_secrets_of(request)
    if not secrets.configured:
        return _not_kept(VaultState.ABSENT)
    actor = asked.reach.principal_id
    try:
        written = await records_of(request).replace_secret(
            subscriber_id,
            actor=actor,
            at=asked.now,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
            keep_secret=lambda: secrets.keep(subscriber_id, body.secret, actor=actor),
        )
    except NoActiveSubscriberError as absent:
        raise _not_answerable() from absent
    except SigningSecretsUnavailableError as unavailable:
        return _not_kept(unavailable.state)
    answered = WebhookChangedView(
        subscriber_id=subscriber_id,
        change=WebhookChange.SECRET_REPLACED,
        changed_at=asked.now,
        secret_written_at=written,
        told=REPLACED,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(SWITCH_OFF_PATH, response_model=WebhookChangedView, responses=COMMON_RESPONSES)
async def switch_off(request: Request, subscriber_id: str, asked: Asked) -> WebhookChangedView:
    """Switch a subscriber off for good, and record who did."""
    if not may_manage(asked.reach, asked.now) or subscriber_id_problems(subscriber_id):
        log.info("webhook switch-off not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        await records_of(request).switch_off(
            subscriber_id, actor=asked.reach.principal_id, at=asked.now
        )
    except NoActiveSubscriberError as absent:
        raise _not_answerable() from absent
    return WebhookChangedView(
        subscriber_id=subscriber_id,
        change=WebhookChange.SWITCHED_OFF,
        changed_at=asked.now,
        secret_written_at=None,
        told=SWITCHED_OFF,
    )
