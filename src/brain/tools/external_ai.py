"""An outside AI service that is not a chat model, registered as a tool an agent must be given.

M12.3.7 asks that an external AI service other than a chat model, such as image generation or
speech to text, be registered as a tool with a required capability and a side-effect class, and be
refused to any agent whose ceiling does not name it. The refusal already worked for every tool:
`brain.gate.catalogue.project` offers a run a tool only when the agent's ceiling names it, the
side effect is no larger than the agent's, and the caller holds the capability. What nothing did was
let an install say that such a service exists, so there was nothing to register. This is that, and
it is the registration and the refusal and **not the call**, for the reason below.

**A service is data an install declares, never code and never a company's name.** An
`ExternalAiService` is a name, a sentence saying what it does, a kind (`image_generation`,
`speech_to_text`: a label, not a list) and the address it is called at. Nothing here names a
provider, and the addresses are the install's own values, kept as `ops.setting` rows beside the
switches (`brain.ops.external_ai_store`). A company-specific service is a declaration, which is how
`brain.plugins.points` says a company's own parts arrive.

**The capability, the side effect and the key's place are derived and never declared**, which is
the whole of why a declaration cannot widen anything:

- *The capability is `invoke:external_ai.<service>`.* A declaration that chose its own capability
  could name `read:client.name`, and everybody who may read a client's name could then spend the
  company's account with an outside company. Derived, it is one nobody holds until an administrator
  grants it for that service, and the capability grammar already treats `invoke:` as a permission
  to act and not to see.
- *The side effect is `SideEffect.SEND`, and a declaration has no field for it.* A call sends the
  person's material to an outside company, which is the product's own rule for a tool that sends
  something out: a person approves each call, and the rung is capped at Assisted
  (`brain.tools.registry.leash_ceiling`). Needs-rupash 184 asks whether speech to text should count
  as a read and image generation as a draft, which would mean fewer approvals. **That is a
  loosening, so it is the owner's and it is not built**: the safe class is the only one a
  declaration can have, and the day the owner answers B the change is one reviewed line here.
  `extra="forbid"` is what turns a declaration that tries to set it into a refusal.
- *The key is kept at `connector_keys/ai_<service>`*, one path segment the application's vault
  policy already admits and the audit ledger can name (`brain.ops.credentials.connector_key_slot`).
  Nothing reads it today and nothing here ever holds one: a declaration has no field a secret could
  arrive in, and the address may carry no query, which is where a key is usually put.

**Registered as a name and never a way to call, and that is deliberate.** An agent run offers a
model nothing that changes something unless a connector prepares the action for a person to approve
(`brain.gate.runtime.ONLY_A_TOOL_THAT_READS_IS_OFFERED_UNLESS_THE_LEASH_HOLDS_THE_REST`), and a
service call has no record to read first and a different answer for each kind of service: speech to
text answers words and image generation answers a file. How the request is built, how the key is
sent and what becomes of the answer cannot be written without a first service, and which one comes
first is needs-rupash 184, still open. So the handler a registry holds refuses every call, as
`brain.tools.proposed_writes.never_called_directly` does for a connector's write, and a service is
offered to no model today. What this makes true now is the part that decides who may ever use one:
the tool, its capability and its class are in the catalogue and on the Tools screen, and an agent
whose ceiling does not name it is shown nothing.

**Why that is not a tool that is present and cannot answer.** The failure `brain.tools.startup`
describes is a tool a model is offered and then cannot use. A `SEND` tool is not offered to a model
by any run today, and nothing is declared on any install until an administrator does it and switches
the feature on, so nothing registered here can be chosen by a model and refused after.

**The switch ships off and is applied at start.** The registry is built once, so a service is
registered when the application starts with the feature on and one declared; turning the switch
later changes what the next start registers, which the feature's own declaration
(`brain.ops.features_declared.external_ai_services`) says in words. Rejected: rebuilding the
registry whenever a setting changes, which is a second way for the catalogue to move under a run
already in flight.

**One bad declaration never stops the others and never stops the application.** A row that no
longer constructs is absent (`brain.ops.external_ai_store`), and a service the registry refuses (a
name that collides) is logged by the kind of refusal and skipped, because a start that raised over
one install's declaration would take the whole product down for it.

Task ids: M12.3.7
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Denied
from brain.core.scope import Clause, Op, Scope
from brain.ops.credentials import ConnectorKeySlot, connector_key_slot
from brain.tools.registry import ResultContract, ToolRegistrationError, ToolRegistry

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why a declaration has no field for what a call counts as.
A_SERVICE_COUNTS_AS_SENDING_SOMETHING_OUT_AND_THE_DECLARATION_CANNOT_SAY_OTHERWISE: Final = (
    "A call hands the person's own material to an outside company, so it is a tool that sends "
    "something out: a person approves each call and its rung is capped at Assisted. Counting "
    "speech to text as a read or image generation as a draft would mean fewer approvals, "
    "which only the owner may decide (needs-rupash 184). A declaration therefore has no field for "
    "the class, and one that names one is refused."
)

#: Why the capability is derived from the service and never chosen by its declaration.
A_SERVICE_S_CAPABILITY_IS_ITS_OWN_AND_NOBODY_ELSE_S: Final = (
    "The capability that opens a service is `invoke:external_ai.<service>` and is worked out from "
    "the service's name. A declaration that chose its own could name a capability many people "
    "already hold, and each of them could then spend the company's account with an outside company."
)

#: Why the registered handler refuses every call.
A_REGISTERED_SERVICE_IS_A_NAME_AND_NOT_YET_A_WAY_TO_CALL: Final = (
    "The service is in the catalogue so that an administrator sees what it needs and what it "
    "counts as and so that an agent's ceiling can name it. Building the request, sending the "
    "key and keeping the answer depend on which service comes first, which is the owner's to say "
    "(needs-rupash 184), so nothing calls one yet and every call is refused."
)

#: What a refused call is answered with. One sentence, naming nothing.
OUTSIDE_SERVICES_ARE_NOT_CALLED_YET: Final = "this outside service is not available to call yet"

# ------------------------------------------------------------------ the vocabulary
#: A service's name, which is a tool source, an entity and a key slot, so one lower-case segment.
SERVICE_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]{1,30}$"
_SERVICE_NAME: Final = re.compile(SERVICE_NAME_PATTERN)

#: What a kind may be called. A label for a screen, never a list somebody has to extend.
KIND_PATTERN: Final = r"^[a-z][a-z0-9_]{1,40}$"

#: How long the sentence saying what a service does may be, and the tool's description is built
#: from it with the service's name beside it, so it stays under the registry's own 400.
DOES_CHARS: Final = 300

#: How long an address may be.
ENDPOINT_CHARS: Final = 300

#: How much a model may ask of a service in one call.
INSTRUCTION_CHARS: Final = 2000

#: The first segment of every outside service's tool name, so no service can take the source
#: another part of the product already uses.
TOOL_SOURCE_PREFIX: Final = "ai_"

#: What every outside service's tool is named after its source, in the registry's own grammar.
TOOL_VERB_NOUN: Final = "call_service"

#: What the service's result is called. Nothing is returned today.
ENTITY_PREFIX: Final = "external_ai_"

#: The capability's noun, and the prefix of the key's slot name.
CAPABILITY_NOUN: Final = "external_ai"
KEY_SLOT_PREFIX: Final = "ai_"

#: What a service counts as, always. See
#: `A_SERVICE_COUNTS_AS_SENDING_SOMETHING_OUT_AND_THE_DECLARATION_CANNOT_SAY_OTHERWISE`.
SERVICE_SIDE_EFFECT: Final = SideEffect.SEND


class ExternalAiService(BaseModel):
    """One outside AI service an install has declared.

    Four fields and none of them can hold a secret, a capability or a class. `extra="forbid"` is
    the refusal of a declaration that tries to say what it counts as.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str = Field(pattern=SERVICE_NAME_PATTERN)
    does: str = Field(min_length=1, max_length=DOES_CHARS)
    kind: str = Field(pattern=KIND_PATTERN)
    endpoint: str = Field(min_length=1, max_length=ENDPOINT_CHARS)

    @field_validator("does")
    @classmethod
    def _one_plain_sentence(cls, v: str) -> str:
        """A sentence on one line: it is shown to a model and an administrator in a list."""
        if v != v.strip() or any(ord(one) < 32 for one in v):
            msg = "what a service does is one plain line of words"
            raise ValueError(msg)
        return v

    @field_validator("endpoint")
    @classmethod
    def _an_address_a_key_could_not_travel_in(cls, v: str) -> str:
        """An https address with a name, and nothing a key could be put in.

        No credentials, no query and no fragment, because the usual place to put a key is the
        address and a declaration is shown on screens. No address literal and no single-label
        host, so a declaration cannot point a call at the network the install sits in; the call,
        when there is one, is checked again at the moment it is made, as every outside request is
        (`brain.tools.fetch.assert_fetchable`).
        """
        parts = urlsplit(v)
        host = parts.hostname or ""
        if parts.scheme != "https":
            msg = "an outside service is called over https"
            raise ValueError(msg)
        if "@" in parts.netloc or parts.query or parts.fragment:
            msg = (
                "the address carries no credentials, query or fragment: a key is kept in the vault"
            )
            raise ValueError(msg)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            msg = "the address is a name, never a number"
            raise ValueError(msg)
        if "." not in host:
            msg = "the address is a public name with a dot in it, and there is one"
            raise ValueError(msg)
        return v


# ------------------------------------------------------------------ what a declaration derives
def tool_name_of(service: str) -> str:
    """The tool's name: `ai_<service>.call_service`, in the registry's `source.verb_noun`."""
    return f"{TOOL_SOURCE_PREFIX}{service}.{TOOL_VERB_NOUN}"


def entity_of(service: str) -> str:
    """The object the tool's results would be about, one name for the service."""
    return f"{ENTITY_PREFIX}{service}"


def capability_of(service: str) -> Capability:
    """`invoke:external_ai.<service>`. See `A_SERVICE_S_CAPABILITY_IS_ITS_OWN_AND_NOBODY_ELSE_S`."""
    return Capability(value=f"invoke:{CAPABILITY_NOUN}.{service}")


def key_slot_of(service: str) -> ConnectorKeySlot:
    """Where the service's key is kept: `connector_keys/ai_<service>`. Nothing reads it yet."""
    return connector_key_slot(f"{KEY_SLOT_PREFIX}{service}")


class ServiceAsked(BaseModel):
    """What a model would pass a service: what it wants done, in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instruction: str = Field(min_length=1, max_length=INSTRUCTION_CHARS)


class OutsideAiResult(Entity):
    """The record a service's tool promises and has none to return today."""


async def never_called_directly(
    request: ServiceAsked, *, entitlement: EntitlementSet, now: datetime | None = None
) -> TypedResult[OutsideAiResult]:
    """Refuse. See `A_REGISTERED_SERVICE_IS_A_NAME_AND_NOT_YET_A_WAY_TO_CALL`.

    `Denied` so a run that reached it goes on with the sentence every unavailable tool gets rather
    than ending on an exception.
    """
    del request, entitlement, now
    raise Denied(OUTSIDE_SERVICES_ARE_NOT_CALLED_YET)


def definition_of(service: ExternalAiService) -> ToolDefinition:
    """What the catalogue and the Tools screen describe for one service.

    `IdentityMode.SERVICE`, because the key a call would be sent with is the install's own, shared
    by everybody who may use the service, and a SERVICE tool must carry a scope that narrows
    something (`brain.tools.registry.assert_service_tool_is_scoped`); `scope_of` is that.
    """
    return ToolDefinition(
        name=tool_name_of(service.service),
        description=f"{service.does} (outside AI service {service.service})",
        entity=entity_of(service.service),
        args_schema=ServiceAsked.model_json_schema(),
        required_capability=capability_of(service.service).value,
        side_effect=SERVICE_SIDE_EFFECT,
        identity_mode=IdentityMode.SERVICE,
    )


def scope_of(service: ExternalAiService) -> Scope:
    """The one narrowing a SERVICE tool carries: this service and no other."""
    return Scope(clauses=(Clause(field="service", op=Op.EQ, value=service.service),))


def register_external_ai(
    registry: ToolRegistry, services: Iterable[ExternalAiService]
) -> tuple[str, ...]:
    """Register each declared service through the one door every tool uses; say which were.

    In service-name order, so two starts register the same tools in the same order. A service
    declared twice is registered once, and one the registry refuses is skipped and logged by the
    kind of refusal alone: see the module docstring on one bad declaration.
    """
    registered: list[str] = []
    for service in sorted({one.service: one for one in services}.values(), key=lambda s: s.service):
        try:
            registry.register(
                definition_of(service),
                never_called_directly,
                result_contract=ResultContract.TYPED,
                scope=scope_of(service),
            )
        except ToolRegistrationError as refused:
            log.warning(
                "external_ai.not_registered", service=service.service, error=type(refused).__name__
            )
            continue
        registered.append(tool_name_of(service.service))
    return tuple(registered)


def is_a_service_name(name: str) -> bool:
    """Whether `name` could be a service: one lower-case segment a letter first."""
    return _SERVICE_NAME.fullmatch(name) is not None
