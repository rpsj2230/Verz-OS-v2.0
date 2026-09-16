"""The setup wizard's appointment over HTTP, which is the one place a real install calls `appoint`.

`brain.setup_wizard` decides every screen and `brain.identity.first_administrator` writes the
first administrator, and until this module no route drove either, so on a real install nothing
ever called `FirstAdministrators.appoint`, the finishing screen at `POST /setup/sign-in` found
nobody to bind, and nobody could sign in. **`POST /setup/appointment` is that route, and it runs
the appointment in exactly the order e81c8b9 argued: count the administrators, `apply_install`,
keep what the result carries, and appoint last.** See
`THE_APPOINTMENT_RUNS_IN_THE_ORDER_THAT_KEEPS_AN_INSTALL_FINISHABLE`.

**The whole draft arrives in one request, and every screen is still the wizard's own entry
point.** No middle screen is served over HTTP and the console has no wizard screens, so the
answers are posted together and each is recorded through `answer` or `skip`, which ask for the
setup code and the count exactly as they do on their own. Nothing here validates an answer:
what is wrong with one is `problems_with`'s finding, told by step, field and catalogue key.
Resuming a half-finished install from `setup-draft.json` (M42.5.12) is not served by this route.

**The setup code is asked before anything is said about the answers**, so somebody without it
learns neither that a screen is unfinished nor that a setting differs. A finished install, a
wrong, expired or missing code, an install with no setup code at all and an appointment refused
because another landed first are one 404 with one body. See
`EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER`.

**The settings are saved, and the 409 is now about the one answer that cannot be.** Until this
change every value the person typed had to already equal what `brain.install.value_of` read
from the process environment, and a difference was a 409 naming the settings to go and set by
hand. That made the wizard a form for confirming a file somebody had already edited. The
answers now go into `ops.setting` in the same transaction as the appointment, through
`Appointer.appoint`, and `brain.install.value_of` resolves a saved value ahead of the
environment, so a fresh install needs no hand-edited environment file for anything the wizard
collects. `brain.ops.install_settings` argues the mechanism, the order and what still has to be
in the file.

**A provider key is kept in the vault now, before anybody is appointed, and the 409 is only
for an install that cannot keep one.** Until 2026-09-16 the vault client read a static slot and
wrote none, so a hosted install's key had to be the one already in the process environment and
anything else was a 409 naming `providers/anthropic`; on the owner's staging install that meant
a hand edit of the server's environment. `brain.ops.credentials.Credentials.keep` is the write,
the same one the console's credential route makes, and it leaves the same ledger entry, with
`brain.firstrun.GRANTED_BY` as its actor. It runs after `apply_install` and before
`appoint`, which is the order `THE_APPOINTMENT_RUNS_IN_THE_ORDER_THAT_KEEPS_AN_INSTALL_FINISHABLE`
already argues: a vault that refuses leaves the wizard open to try again. The 409 remains for
an install that names no vault, whose key is still accepted when the environment already
carries that same key, compared with `hmac.compare_digest`; for a vault that did not answer or
refused; and for a key with a space inside it. Each says which, by `NotKeptReason`, and never
by a value. `brain.tables.config` still refuses a credential in a table, and nothing here falls
back to one. See `A_PROVIDER_KEY_IS_KEPT_BEFORE_THE_DOOR_CLOSES`.

**The finishing screen is told which processes use the key**, as `ProviderKeyKept`: in use by
the process that appointed and by every other from its next start, or outranked by a variable
the environment file sets. That is
`brain.ops.credentials.A_KEY_IN_USE_HERE_IS_NOT_IN_USE_EVERYWHERE`, and it is on the response
because the person who typed the key is about to ask the system a question.

**The appointing process reads its own answers back without restarting**, because it holds what
it wrote rather than re-reading the table it just wrote to. Which processes that reaches, and
which it does not, is
`brain.ops.install_settings.A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER`.

**No refused body is repeated.** The appointment carries the setup code and the provider key,
and FastAPI's own 422 for a body in the wrong shape quotes the input it refused, so the router is
built on `brain.api.NoEchoRoute`. Before 2026-09-16 a setup code over the length cap came back
in the response that refused it.

**The server chooses the administrator's principal id.** See
`THE_SERVER_CHOOSES_WHO_IS_APPOINTED`.

**It is built only where a sign-in could follow it.** See
`NO_APPOINTMENT_WHERE_NOBODY_COULD_SIGN_IN_AFTER_IT` for why the lifespan builds the store
beside `app.state.sign_in_bindings` rather than beside the database alone.

Rejected: writing `/opt/brain/.env` from the application. The container has no mount onto it,
and a process that rewrites its own configuration file is a second writer beside the variables
repository M42.1.1 makes the record of an install, whose next deploy would silently undo it.
That argument has not changed, and it is why the values go to a table instead.

**82afbfb rejected a table here in these words: "it needs a migration and a second reader
beside `value_of`, which is `brain.install.ONE_READER_OR_TWO_DEFAULTS` exactly." Both halves
were wrong, and measurably so.** The table already exists, `ops.setting` from `0004`, with
row-level security, its constraints and a partial unique index, so there is no migration. And
the saved values are resolved inside `value_of` rather than beside it, so there is still one
reader and one order. What the sentence had actually found was that nothing under `src` reads
or writes `ops.setting` at all, which made a table that shipped in September look like a table
that would have to be built.

Rejected: appointing and discarding the settings. It is what a route reaching for `appoint`
would do first, and it is the door closed before the settings are written.

Task ids: M42.5.6, M42.5.10, M42.5.14, M27.8.7
"""

from __future__ import annotations

import enum
import hmac
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import COMMON_RESPONSES, NoEchoRoute
from brain.core.errors import Absent, BrainError, Failed
from brain.firstrun import GRANTED_BY, Enrolment
from brain.identity.first_administrator import FirstAdministratorRefusedError
from brain.identity.roles import RoleGrant
from brain.install import hold_saved, saved_values
from brain.ops.credentials import (
    SLOTS,
    CredentialProblemError,
    Credentials,
    CredentialSlot,
    CredentialsUnavailableError,
    InUse,
    VaultState,
)
from brain.settings import process_environment
from brain.setup_wizard import (
    MAX_ANSWER_CHARS,
    REVIEW_STATES,
    WIZARD,
    Applied,
    Draft,
    StepId,
    WizardClosedError,
    WizardLockedError,
    answer,
    apply_install,
    assert_open,
    assert_unlocked,
    is_answered,
    new_draft,
    skip,
)
from brain.sign_in_routes import FINISH_PATH, enrolment_of

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the appointment is four steps in this order.
THE_APPOINTMENT_RUNS_IN_THE_ORDER_THAT_KEEPS_AN_INSTALL_FINISHABLE: Final = (
    "The administrators are counted first, because apply_install and every screen take the count "
    "and a closed wizard must refuse before anything else is judged. apply_install next, because "
    "it is the one act that spends the code and produces the grant. Then what it carries is kept, "
    "and appoint is last, because appointing closes the wizard on every screen and a door closed "
    "before the settings are kept is an install that can neither be finished nor started again."
)

#: Why a wrong code, a closed wizard and a lost race are one answer.
EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER: Final = (
    "The appointment is reachable by anybody who finds the address. A finished install, a wrong, "
    "expired or missing code, an install with no setup code and an appointment another one beat "
    "are one 404, so nobody learns whether the install is finished, whether their code was ever "
    "right, or who was appointed. Problems with the answers are told only after the code is "
    "accepted, and the reason for a refusal goes to the log."
)

#: Why the provider key is written before the appointment, and what happens without a vault.
A_PROVIDER_KEY_IS_KEPT_BEFORE_THE_DOOR_CLOSES: Final = (
    "An installation value is kept in ops.setting in the appointment's own transaction. A "
    "provider key cannot follow it into a table, so it is written to the vault, through the same "
    "store the console's credential route uses, after apply_install and before appoint: a vault "
    "that is missing, silent or refusing leaves nobody appointed and the wizard open to try "
    "again. An install that names no vault still finishes when its environment already carries "
    "that same key. Otherwise the slot's path, the variable it would be read as and the reason "
    "are told back. A path, a name and a reason, never a value."
)

#: Why the principal id is not taken from the request.
THE_SERVER_CHOOSES_WHO_IS_APPOINTED: Final = (
    "appoint writes a principal the directory already holds in place, and refuses a held one that "
    "is not live. An id taken from the body would let the holder of the setup code name an "
    "existing member of staff as the widest role, and the difference between that refusal and "
    "success would say which ids are held. A new id every attempt names nobody, and the "
    "finishing screen is handed it."
)

#: Why the store is built beside the sign-in bindings writer and not beside the database alone.
NO_APPOINTMENT_WHERE_NOBODY_COULD_SIGN_IN_AFTER_IT: Final = (
    "A process with a database and no usable issuer has no gate and no bindings writer, so the "
    "finishing screen refuses there. An appointment made on it closes the wizard, and the setup "
    "code's window runs out while the issuer is being fixed, which leaves an administrator nobody "
    "can ever sign in as. So the appointment is offered only where the finishing screen is."
)

# --------------------------------------------------------------------- the figures

#: Where the appointment is served. Beside the finishing screen, outside the API prefix, because
#: it takes the setup code and no token.
APPOINTMENT_PATH: Final = "/setup/appointment"

#: The prefix a first administrator's principal id is minted under.
PRINCIPAL_PREFIX: Final = "u_"

#: What a screen that was never finished is told as, in the review screen's own words.
NOT_GIVEN: Final = REVIEW_STATES["not_given"]


class NotKeptReason(enum.StrEnum):
    """Why a provider key was not kept, so the screen can say what to do. Nobody was appointed."""

    #: The install names no vault, and its environment does not already carry this key.
    NO_VAULT = "no_vault"
    #: The vault did not answer.
    VAULT_UNREACHABLE = "vault_unreachable"
    #: The vault answered and refused.
    VAULT_REFUSED = "vault_refused"
    #: What was given has a space or a character a key cannot hold inside it.
    NOT_A_KEY = "not_a_key"


#: The reason a vault's state is told as. `VaultState.READY` is never raised, so it has no row.
NOT_KEPT_BECAUSE: Final[Mapping[VaultState, NotKeptReason]] = {
    VaultState.ABSENT: NotKeptReason.NO_VAULT,
    VaultState.UNREACHABLE: NotKeptReason.VAULT_UNREACHABLE,
    VaultState.REFUSED: NotKeptReason.VAULT_REFUSED,
}


class ProviderKeyKept(enum.StrEnum):
    """What became of the wizard's provider key, told to the finishing screen."""

    #: The install keeps questions on its own hardware, so no key was asked for.
    NOT_ASKED = "not_asked"
    #: Kept in the vault, and in use by the process that appointed; the others from their start.
    IN_USE = "in_use"
    #: Kept in the vault, and the environment file sets the same variable, which wins on start.
    OUTRANKED = "outranked"
    #: The install names no vault, and its environment already carries this same key.
    FROM_ENVIRONMENT = "from_environment"


#: Every provider key's slot, by the provider's slug as the wizard names it.
SLOT_BY_PROVIDER: Final[Mapping[str, CredentialSlot]] = {
    one.provider.slug: one for one in SLOTS.values()
}


# ------------------------------------------------------------------------ the store


@runtime_checkable
class Appointer(Protocol):
    """What this route needs from the first administrator store. `FirstAdministrators` is one."""

    async def administrators(self, now: datetime) -> int:
        """How many administrators this install has."""
        ...

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        display_name: str,
        trace_id: str = "",
        settings: Mapping[str, str] | None = None,
        # `Protocol` does not carry a default's value into the implementation, so this says
        # what an implementation must accept and never what it must do without one.
    ) -> None:
        """Write the first administrator and the install's settings, or raise.

        One call rather than two, because the rows and the grants have to commit together. See
        `brain.identity.first_administrator.THE_SETTINGS_AND_THE_DOOR_CLOSE_IN_ONE_TRANSACTION`.
        """
        ...


# ------------------------------------------------------------------------ the shapes


class AppointmentAsked(BaseModel):
    """The setup code and every screen's answers. No principal id: see the module note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_code: str = Field(max_length=MAX_ANSWER_CHARS)
    answers: dict[StepId, dict[str, str]] = Field(default_factory=dict)
    skipped: tuple[StepId, ...] = ()


class ProblemView(BaseModel):
    """One thing wrong with the answers: the screen, the field, and a catalogue key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step: StepId
    field: str
    key: str


class ProblemsView(BaseModel):
    """Every problem with the answers. Nobody was appointed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: tuple[ProblemView, ...]


class UnkeptView(BaseModel):
    """What this install could not keep, by name, and why. Nobody was appointed.

    `unkept` is the vault slot's path and `variables` the environment variable the key would be
    read as, one each, because a provider key is the only answer that can fail to be kept.
    `unkept` keeps the name 82afbfb gave it. `reason` is what makes the screen able to say what
    to do: set up a vault, start or unseal it, load its policy, or paste the key again.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    unkept: tuple[str, ...]
    variables: tuple[str, ...]
    reason: NotKeptReason


class AppointedView(BaseModel):
    """Who was appointed, the screen that signs them in, and what became of the provider key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    finish_path: str
    provider_key: ProviderKeyKept


@dataclass(frozen=True)
class Appointment:
    """What came of asking. Appointed exactly when `principal_id` is set."""

    principal_id: str = ""
    problems: tuple[ProblemView, ...] = ()
    unkept: tuple[str, ...] = ()
    variables: tuple[str, ...] = ()
    reason: NotKeptReason | None = None
    provider_key: ProviderKeyKept = ProviderKeyKept.NOT_ASKED


# ------------------------------------------------------------------------ the decisions


def _nothing_to_appoint() -> Absent:
    """The one refusal before the answers. See `EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER`."""
    return Absent("no setup appointment is answerable here")


def new_principal_id() -> str:
    """A principal id nobody holds. See `THE_SERVER_CHOOSES_WHO_IS_APPOINTED`."""
    return f"{PRINCIPAL_PREFIX}{uuid.uuid4().hex}"


def draft_of(
    asked: AppointmentAsked, enrolment: Enrolment, *, administrators: int, now: datetime
) -> tuple[Draft, tuple[ProblemView, ...]]:
    """The draft the posted answers make, through the wizard's own entry points, and its problems.

    Every storing screen in wizard order: skipped, answered, or neither. A screen neither answered
    nor skipped, and a screen skipped that may not be, is told as `NOT_GIVEN` against the screen.
    The screens' own entry points raise for a closed wizard and a refused code, and the caller
    has asked both before this.
    """
    draft = new_draft()
    found: list[ProblemView] = []
    for step in WIZARD:
        if not step.stores:
            continue
        if step.key in asked.skipped:
            if not step.skippable:
                found.append(ProblemView(step=step.key, field="", key=NOT_GIVEN))
                continue
            draft = skip(
                draft,
                step.key,
                enrolment,
                asked.setup_code,
                administrators=administrators,
                now=now,
            )
            continue
        if step.key not in asked.answers:
            continue
        draft, problems = answer(
            draft,
            step.key,
            asked.answers[step.key],
            enrolment,
            asked.setup_code,
            administrators=administrators,
            now=now,
        )
        found.extend(ProblemView(step=step.key, field=one.field, key=one.key) for one in problems)
    if not found:
        found.extend(
            ProblemView(step=step.key, field="", key=NOT_GIVEN)
            for step in WIZARD
            if step.stores and not is_answered(step, draft)
        )
    return draft, tuple(found)


def slot_for(applied: Applied) -> CredentialSlot | None:
    """The slot `applied`'s provider key goes into, or None when it carries no key.

    A provider the wizard accepted is one of `PROVIDER_SLOTS`' slugs by its own check, so a
    lookup that misses raises rather than dropping a key nothing would then keep.
    """
    return SLOT_BY_PROVIDER[applied.provider] if applied.provider else None


async def keep_provider_key(
    slot: CredentialSlot,
    applied: Applied,
    credentials: Credentials,
    *,
    trace_id: str,
    env: Mapping[str, str] | None = None,
) -> NotKeptReason | None:
    """Keep `applied`'s key in `slot`, before anybody is appointed. None when it is kept.

    With a vault, the key is written through `Credentials.keep`, attributed to first run, and
    a vault that is silent or refuses, or a key with a space inside it, is the reason told back.
    With none, the key is accepted only when the environment already carries that same key,
    compared in constant time, because that install will read it from there on every start;
    anything else is `NotKeptReason.NO_VAULT`. See `A_PROVIDER_KEY_IS_KEPT_BEFORE_THE_DOOR_CLOSES`.
    `env` is for tests.
    """
    if not credentials.configured:
        source = process_environment() if env is None else env
        loaded = source.get(slot.provider.env_var, "")
        carried = hmac.compare_digest(loaded, applied.provider_key)
        return None if carried else NotKeptReason.NO_VAULT
    try:
        # No reach to digest: first run has none, and the ledger entry says so by its sentinel.
        await credentials.keep(slot, applied.provider_key, actor=GRANTED_BY, trace_id=trace_id)
    except CredentialProblemError:
        return NotKeptReason.NOT_A_KEY
    except CredentialsUnavailableError as unavailable:
        return NOT_KEPT_BECAUSE[unavailable.state]
    return None


def put_provider_key_to_use(
    slot: CredentialSlot | None, applied: Applied, credentials: Credentials
) -> ProviderKeyKept:
    """Hand a key kept by this appointment to this process, and say which processes use it.

    After `appoint`, never before: a key handed to this process by an appointment that was then
    refused would be a key nobody appointed choosing what every question is sent with.
    """
    if slot is None:
        return ProviderKeyKept.NOT_ASKED
    if not credentials.configured:
        return ProviderKeyKept.FROM_ENVIRONMENT
    in_use = credentials.put_to_use(slot, applied.provider_key)
    return ProviderKeyKept.IN_USE if in_use is InUse.HERE else ProviderKeyKept.OUTRANKED


async def appoint_first_administrator(
    appointer: Appointer,
    asked: AppointmentAsked,
    *,
    enrolment: Enrolment | None,
    principal_id: str,
    trace_id: str,
    now: datetime,
    credentials: Credentials | None = None,
    env: Mapping[str, str] | None = None,
) -> Appointment:
    """Run the appointment in its order, or refuse before the answers in one way.

    See `THE_APPOINTMENT_RUNS_IN_THE_ORDER_THAT_KEEPS_AN_INSTALL_FINISHABLE`. Raises
    `_nothing_to_appoint` for every refusal in `EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER`,
    and returns problems, or the key that could not be kept, with nobody appointed, for the
    rest. `credentials` None is an install with no vault.
    """
    store = credentials if credentials is not None else Credentials(None)
    if enrolment is None:
        log.info("appointment refused", reason="no_setup_code")
        raise _nothing_to_appoint()
    administrators = await appointer.administrators(now)
    try:
        assert_open(administrators)
        assert_unlocked(enrolment, asked.setup_code, now=now)
        draft, problems = draft_of(asked, enrolment, administrators=administrators, now=now)
        if problems:
            return Appointment(problems=problems)
        applied = apply_install(
            draft,
            enrolment,
            asked.setup_code,
            principal_id=principal_id,
            administrators=administrators,
            now=now,
        )
    except (WizardClosedError, WizardLockedError) as refused:
        log.info("appointment refused", reason=type(refused).__name__)
        raise _nothing_to_appoint() from refused
    slot = slot_for(applied)
    if slot is not None:
        why = await keep_provider_key(slot, applied, store, trace_id=trace_id, env=env)
        if why is not None:
            log.info("appointment refused", reason="not_kept", names=[slot.path], why=why)
            return Appointment(unkept=(slot.path,), variables=(slot.provider.env_var,), reason=why)
    try:
        await appointer.appoint(
            applied.grant,
            display_name=draft.values_for(StepId.ADMINISTRATOR)["full_name"],
            trace_id=trace_id,
            settings=applied.settings,
        )
    except FirstAdministratorRefusedError as refused:
        log.info("appointment refused", reason=refused.reason.value)
        raise _nothing_to_appoint() from refused
    # Held from what was written rather than read back, so this process answers with the
    # install's own values on the very next request. See the module note.
    hold_saved({**saved_values(), **applied.settings})
    return Appointment(
        principal_id=principal_id,
        provider_key=put_provider_key_to_use(slot, applied, store),
    )


# ------------------------------------------------------------------------- the wiring


def appointer_of(request: Request) -> Appointer | None:
    """The first administrator store this process was built with, or None."""
    found = getattr(request.app.state, "first_administrators", None)
    return found if isinstance(found, Appointer) else None


def credentials_of(request: Request) -> Credentials | None:
    """Where this process keeps a credential, or None, which is an install with no vault."""
    found = getattr(request.app.state, "credentials", None)
    return found if isinstance(found, Credentials) else None


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.sign_in_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


router = APIRouter(tags=["setup"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": UnkeptView, "description": "The provider key this install could not keep."},
    422: {"model": ProblemsView, "description": "What is wrong with the answers, by field."},
}


@router.post(APPOINTMENT_PATH, response_model=AppointedView, responses=_TOLD)
async def appoint_from_setup(request: Request, body: AppointmentAsked) -> JSONResponse:
    """Appoint the first administrator from a finished wizard, once."""
    now = datetime.now(UTC)
    appointer = appointer_of(request)
    if appointer is None:
        raise Failed("no first administrator store on this process")
    try:
        result = await appoint_first_administrator(
            appointer,
            body,
            enrolment=enrolment_of(request),
            principal_id=new_principal_id(),
            trace_id=_trace_id(),
            now=now,
            credentials=credentials_of(request),
        )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives.
        raise Failed(f"appointing: {type(exc).__name__}") from exc
    if result.problems:
        told = ProblemsView(problems=result.problems)
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    if result.reason is not None:
        unkept = UnkeptView(unkept=result.unkept, variables=result.variables, reason=result.reason)
        return JSONResponse(status_code=409, content=unkept.model_dump(mode="json"))
    view = AppointedView(
        principal_id=result.principal_id,
        finish_path=FINISH_PATH,
        provider_key=result.provider_key,
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
