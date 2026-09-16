"""Setting a credential from the console, and seeing which are held, without reading one back.

`brain.ops.credentials` is the mechanism and argues the design. This module is the HTTP half: a
read that says, per slot, whether a secret is held and when it was written, and a write that puts
one in and answers with the same two facts. **Nothing a caller can send makes a response carry a
value**: the write's body is the only place a credential appears, its refusal by the model is
`brain.api.NoEchoRoute`'s and names the field without repeating it, and every other answer is
built from `Held`, `Kept` and a sentence.

**The capability is `admin:credential`, held over everything.** An `admin:` verb, so
`brain.gate.admission` already withholds it from a password-only session and from any channel
but the console, and neither ceiling is written here. Held over everything, because a provider
key is used by every question anybody in the company asks: a grant scoped to one department is a
grant to change what every other department's questions are sent with. The test is the one
`brain.identity.first_administrator.holds_everywhere` makes for signing people in. See
`A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION`.

**The capability is asked before the vault is, and before the slot is looked up.** A caller who
may not manage credentials is refused in one set of words whether the slot exists, whether the
install runs a vault and whether it answers, so the difference between a 404, a 409 and a 503 is
never readable by somebody who could not have acted on it. That is
`brain.routing_routes`' order for the same reason. A slot that does not exist is the same refusal
again: the slots are a closed list in the source, so naming one is not a disclosure, and one
answer is still simpler to keep than two.

**What a write answers, and in which status.** 200 with the slot, that it is held, when, whether
this process now uses it and a sentence saying what that means for the others. 422 with problems
named by code and said in words, judged before anything was sent. 409 when the install runs no
vault or the vault refused, and 503 when it did not answer, each with the vault's state and the
sentence from `brain.ops.credentials.TOLD` as its message; nothing was stored anywhere in
any of the three.

**The sentences are English and the codes are stable.** This console has no language selection,
and `brain.locale` is where the wizard's sentences live; a code beside each sentence is what a
translated console would key on. That is a gap and not a decision.

Rejected: a DELETE. Removing a provider key takes an install's questions off that provider
between one request and the next, the policy grants the application no delete, and the thing an
administrator actually does is replace a key, which is a write.

Rejected: answering the write with the value's length, a prefix, or a fingerprint so a person can
tell which key they saved. Each is part of the secret, a fingerprint of a key is a lookup for
anybody holding a candidate, and the time it was written is what tells two saves apart.

Task ids: M27.8.7
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
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.ops.credentials import (
    SLOTS,
    TOLD,
    CredentialProblemError,
    Credentials,
    CredentialSlot,
    CredentialsUnavailableError,
    Held,
    InUse,
    VaultState,
    told_in_use,
)

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the capability must be held over everything and not only held.
A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION: Final = (
    "A provider key is sent with every question anybody in the company asks that provider. A "
    "grant of admin:credential scoped to one department would let its holder change what every "
    "other department's questions go out with, and redirect them to an account they chose, so a "
    "scoped grant is not a grant here. Held over everything is the test, as it is for signing "
    "people in."
)

# ----------------------------------------------------------------- the capability

#: Setting a credential and reading which are held. An `admin:` verb, over everything.
CREDENTIAL_AUTHORITY: Final = Capability(value="admin:credential")

#: Where the slots are listed. A write is one slot below it, as `{family}/{name}`.
CREDENTIALS_PATH: Final = "/credentials"

#: The status a write that kept nothing answers, by what the vault's state was.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}

# ------------------------------------------------------------------------ the shapes


class SlotView(BaseModel):
    """One slot: what it is for, whether it holds a secret, and when that was written.

    `held` and `set_at` are None when the vault could not be asked, which `CredentialsView.vault`
    says in words. A None here is "not known", and never "not held".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    description: str
    held: bool | None
    set_at: datetime | None


class CredentialsView(BaseModel):
    """Every slot, and the state of the vault they were asked of."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vault: VaultState
    told: str
    slots: tuple[SlotView, ...]


class CredentialAsked(BaseModel):
    """The one field a write carries. No length on the model: `problems_with` judges it in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str


class CredentialKeptView(BaseModel):
    """A secret is held in a slot. Never the secret, its length, or anything derived from it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    held: bool
    set_at: datetime | None
    in_use: InUse
    told: str


class CredentialProblemView(BaseModel):
    """One thing wrong with what was sent: the field, a stable code, and what to do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    code: str
    message: str


class CredentialProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was stored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: tuple[CredentialProblemView, ...]


class CredentialNotKeptView(ErrorBody):
    """The vault could not take it. Nothing was stored anywhere.

    `ErrorBody`'s message and trace id, so a console drawing any failure draws this one's
    sentence and a reference somebody can quote, and two fields of its own, so a screen that
    knows this route can say which slot and which state. A shape of its own under the API
    prefix, named in `tests/unit/test_api.py` beside the one other route that has one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    vault: VaultState


# ------------------------------------------------------------------------ the decisions


def may_manage(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `CREDENTIAL_AUTHORITY` over everything, at this instant."""
    scope = reach.scope_for(CREDENTIAL_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def listing(store: Credentials) -> CredentialsView:
    """Every slot as `store` holds it, in path order, or every slot unknown with the reason.

    One failure answers for the whole list rather than per slot, because a vault that did not
    answer for one slot will not answer for the next, and a list half known and half not is a
    list somebody reads as half held.
    """
    slots = [SLOTS[path] for path in sorted(SLOTS)]
    try:
        found: list[Held] = [store.held(slot) for slot in slots]
    except CredentialsUnavailableError as unavailable:
        return CredentialsView(
            vault=unavailable.state,
            told=TOLD[unavailable.state],
            slots=tuple(
                SlotView(slot=one.path, description=one.description, held=None, set_at=None)
                for one in slots
            ),
        )
    return CredentialsView(
        vault=VaultState.READY,
        told=TOLD[VaultState.READY],
        slots=tuple(
            SlotView(slot=one.path, description=one.description, held=it.held, set_at=it.set_at)
            for one, it in zip(slots, found, strict=True)
        ),
    )


def _not_answerable() -> Absent:
    """The one refusal this router makes. See the module note on the order of the checks."""
    return Absent("credentials are not answerable for this caller")


# ------------------------------------------------------------------------- the wiring


def credentials_of(request: Request) -> Credentials:
    """What this process was built with, or a store with no vault.

    A process whose lifespan attached nothing is a process that can keep no credential, which is
    exactly what `Credentials(None)` answers, so there is no second spelling of "no vault" here.
    """
    found = getattr(request.app.state, "credentials", None)
    return found if isinstance(found, Credentials) else Credentials(None)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.setup_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


router = APIRouter(prefix=API_PREFIX, tags=["credentials"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": CredentialNotKeptView, "description": "No vault, or the vault refused."},
    422: {"model": CredentialProblemsView, "description": "What is wrong with what was sent."},
    503: {"model": CredentialNotKeptView, "description": "The vault did not answer."},
}


@router.get(CREDENTIALS_PATH, response_model=CredentialsView, responses=COMMON_RESPONSES)
async def credentials(request: Request, asked: Asked) -> CredentialsView:
    """Which slots hold a secret, and when each was written. Never a secret."""
    if not may_manage(asked.reach, asked.now):
        log.info("credentials not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return await asyncio.to_thread(listing, credentials_of(request))


@router.put(
    CREDENTIALS_PATH + "/{family}/{name}", response_model=CredentialKeptView, responses=_TOLD
)
async def set_credential(
    request: Request, family: str, name: str, body: CredentialAsked, asked: Asked
) -> JSONResponse:
    """Put a secret into one slot and say that it is held. Nothing sent comes back."""
    if not may_manage(asked.reach, asked.now):
        log.info("credentials not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    slot: CredentialSlot | None = SLOTS.get(f"{family}/{name}")
    if slot is None:
        log.info("credential slot not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    store = credentials_of(request)
    try:
        kept = await asyncio.to_thread(
            store.keep, slot, body.value, actor=asked.reach.principal_id, trace_id=_trace_id()
        )
        in_use = store.put_to_use(slot, body.value)
    except CredentialProblemError as refused:
        told = CredentialProblemsView(
            problems=tuple(
                CredentialProblemView(field="value", code=one.code, message=one.message)
                for one in refused.problems
            )
        )
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    except CredentialsUnavailableError as unavailable:
        view = CredentialNotKeptView(
            message=TOLD[unavailable.state],
            trace_id=_trace_id(),
            slot=slot.path,
            vault=unavailable.state,
        )
        return JSONResponse(
            status_code=NOT_KEPT_STATUS[unavailable.state], content=view.model_dump(mode="json")
        )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives, and the type name alone for the
        # reason this module exists: an exception's message is a place a value can be quoted.
        raise Failed(f"keeping a credential: {type(exc).__name__}") from exc
    answered = CredentialKeptView(
        slot=kept.slot,
        held=True,
        set_at=kept.set_at,
        in_use=in_use,
        told=told_in_use(slot, in_use),
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
