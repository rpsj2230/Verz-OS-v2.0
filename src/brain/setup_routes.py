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

**Settings are confirmed, not written, because nothing in this process can write them.** An
installation value is read from this process's environment through `brain.install.value_of`,
that environment is the install's environment file, the installer fills it from the variables
repository, and the application container has no mount onto it. The provider key's home is the
vault, and `brain.ops.openbao` reads a static slot and writes none. Appointing over values that
were collected and then kept nowhere closes the wizard on an install configured differently
from what its installer approved on the review screen, which is the failure
`APPOINTING_IS_THE_LAST_WRITE` names. So the step that e81c8b9 called writing the settings is,
today, confirming that the running install already carries each one, and a setting it does not
carry is named back and nobody is appointed. See
`A_SETTING_THIS_PROCESS_CANNOT_WRITE_IS_CONFIRMED_BEFORE_THE_DOOR_CLOSES`.

**The server chooses the administrator's principal id.** See
`THE_SERVER_CHOOSES_WHO_IS_APPOINTED`.

**It is built only where a sign-in could follow it.** See
`NO_APPOINTMENT_WHERE_NOBODY_COULD_SIGN_IN_AFTER_IT` for why the lifespan builds the store
beside `app.state.sign_in_bindings` rather than beside the database alone.

Rejected: writing `/opt/brain/.env` from the application. The container has no mount onto it,
and a process that rewrites its own configuration file is a second writer beside the variables
repository M42.1.1 makes the record of an install, whose next deploy would silently undo it.

Rejected: a table of installation values. It needs a migration and a second reader beside
`value_of`, which is `brain.install.ONE_READER_OR_TWO_DEFAULTS` exactly.

Rejected: appointing and discarding the settings. It is what a route reaching for `appoint`
would do first, and it is the door closed before the settings are written.

Task ids: M42.5.6, M42.5.10, M42.5.14
"""

from __future__ import annotations

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

from brain.api import COMMON_RESPONSES
from brain.core.errors import Absent, BrainError, Failed
from brain.firstrun import Enrolment
from brain.identity.first_administrator import FirstAdministratorRefusedError
from brain.identity.roles import RoleGrant
from brain.install import InstallError, value_of
from brain.ops.provider_keys import PROVIDER_SLOTS
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

#: Why the settings are confirmed rather than written.
A_SETTING_THIS_PROCESS_CANNOT_WRITE_IS_CONFIRMED_BEFORE_THE_DOOR_CLOSES: Final = (
    "An installation value is this process's environment, which the installer fills from the "
    "variables repository and which the application cannot write, and a provider key lives in a "
    "vault this process only reads. An answer appointed over and kept nowhere is lost when the "
    "wizard closes. So each setting the draft sets must already be what the running install "
    "carries, and a provider key must already be the one loaded from its slot, or the names of "
    "the ones that are not are told back and nobody is appointed. Names, never values."
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


# ------------------------------------------------------------------------ the store


@runtime_checkable
class Appointer(Protocol):
    """What this route needs from the first administrator store. `FirstAdministrators` is one."""

    async def administrators(self, now: datetime) -> int:
        """How many administrators this install has."""
        ...

    async def appoint(self, grant: RoleGrant, *, display_name: str, trace_id: str = "") -> None:
        """Write the first administrator, or raise `FirstAdministratorRefusedError`."""
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
    """The settings the running install does not carry, by name. Nobody was appointed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    unkept: tuple[str, ...]


class AppointedView(BaseModel):
    """Who was appointed, and the screen that signs them in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    finish_path: str


@dataclass(frozen=True)
class Appointment:
    """What came of asking. Appointed exactly when `principal_id` is set."""

    principal_id: str = ""
    problems: tuple[ProblemView, ...] = ()
    unkept: tuple[str, ...] = ()


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


def unkept(applied: Applied, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Every setting and provider slot `applied` carries that the running install does not.

    Names only. A setting this process cannot read is not carried, and a provider key is carried
    only when its slot's key is loaded and is the same key, compared in constant time. See
    `A_SETTING_THIS_PROCESS_CANNOT_WRITE_IS_CONFIRMED_BEFORE_THE_DOOR_CLOSES`. `env` is for tests.
    """
    names: list[str] = []
    for name, wanted in sorted(applied.settings.items()):
        try:
            running = value_of(name, env)
        except InstallError:
            running = ""
        if running != wanted:
            names.append(name)
    if applied.provider:
        source = process_environment() if env is None else env
        for slot in PROVIDER_SLOTS:
            if slot.slug != applied.provider:
                continue
            loaded = source.get(slot.env_var, "")
            if not loaded or not hmac.compare_digest(loaded, applied.provider_key):
                names.append(slot.path)
    return tuple(names)


async def appoint_first_administrator(
    appointer: Appointer,
    asked: AppointmentAsked,
    *,
    enrolment: Enrolment | None,
    principal_id: str,
    trace_id: str,
    now: datetime,
    env: Mapping[str, str] | None = None,
) -> Appointment:
    """Run the appointment in its order, or refuse before the answers in one way.

    See `THE_APPOINTMENT_RUNS_IN_THE_ORDER_THAT_KEEPS_AN_INSTALL_FINISHABLE`. Raises
    `_nothing_to_appoint` for every refusal in `EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER`,
    and returns problems or unkept settings, with nobody appointed, for the rest.
    """
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
    missing = unkept(applied, env)
    if missing:
        log.info("appointment refused", reason="settings_unkept", settings=list(missing))
        return Appointment(unkept=missing)
    try:
        await appointer.appoint(
            applied.grant,
            display_name=draft.values_for(StepId.ADMINISTRATOR)["full_name"],
            trace_id=trace_id,
        )
    except FirstAdministratorRefusedError as refused:
        log.info("appointment refused", reason=refused.reason.value)
        raise _nothing_to_appoint() from refused
    return Appointment(principal_id=principal_id)


# ------------------------------------------------------------------------- the wiring


def appointer_of(request: Request) -> Appointer | None:
    """The first administrator store this process was built with, or None."""
    found = getattr(request.app.state, "first_administrators", None)
    return found if isinstance(found, Appointer) else None


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.sign_in_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


router = APIRouter(tags=["setup"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": UnkeptView, "description": "Settings the running install does not carry."},
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
        )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives.
        raise Failed(f"appointing: {type(exc).__name__}") from exc
    if result.problems:
        told = ProblemsView(problems=result.problems)
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    if result.unkept:
        return JSONResponse(
            status_code=409, content=UnkeptView(unkept=result.unkept).model_dump(mode="json")
        )
    view = AppointedView(principal_id=result.principal_id, finish_path=FINISH_PATH)
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
