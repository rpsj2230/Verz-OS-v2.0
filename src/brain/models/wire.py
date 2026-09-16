"""The transports that actually reach a provider: one HTTP request per call, and nothing else.

`brain.models.adapter` built the other side of the driver seam and stopped at one missing
part: `litellm_transport` imports an SDK that is an optional extra (`pyproject.toml`'s `models`
group) and is installed on no install, so `ProviderSdkMissingError` was the only thing a call
could ever produce. The SDK itself was never the point. `Transport` is "a single function from a
`DriverRequest` to a `Completion`", and this module is that function written against each
provider's own HTTP API with `httpx`, which is already a dependency. `SdkDriver`, `failure_from`
and the closed `TransportError` family are used exactly as they stand, so every rule the
adapter's invariants hold (one call out per call in, the unknown stops the chain, a refusal is
not a trigger, nothing of the request in an exception) holds for these transports by
construction rather than by a second copy.

**Two wire shapes, and a closed table of which provider speaks which.** Anthropic's Messages API
is one; the chat completions shape OpenAI published is the other, and Moonshot and every local
inference runtime speak it too. `PROVIDER_WIRES` names each provider this system holds a key
slot for, its address and its shape, built beside `brain.ops.provider_keys.PROVIDER_SLOTS` and
held to it by a test, so a slot with no wire is a failing test rather than a rung that cannot
answer. See `A_PROVIDER_IS_REACHED_AT_ITS_OWN_ADDRESS_AND_NEVER_ONE_A_PERSON_TYPED`.

**The address is the product's, never the console's.** A provider's base URL is not a setting.
Somebody who can edit where a provider is reached can point the key every question is sent with
at a server they run, which is the redirection `brain.credential_routes` refuses a department
admin for. The one address that is configuration is the install's own inference server, and it
is resolved where every other reader of it resolves it: `INSTALL_MODEL_ENDPOINT` through
`brain.install.value_of`, refused by `brain.knowledge.embed_policy.endpoint_refusals` when it is
not an origin.

**The key is read at the moment the header is built, from the environment it was loaded into,
and it goes nowhere else.** `brain.ops.provider_keys` puts a key into the process environment
"where the provider SDK finds it", and `brain.ops.credentials.Credentials.put_to_use` replaces it
there when an administrator saves a new one. A transport that copied the key at construction
would go on sending the old one after a rotation that told the person "in use by the server
process that answered". So `environment_key` reads the variable through
`brain.settings.process_environment` each call, which is exactly what an SDK does, moved into
this process. The value becomes one header on one request; it is not on the `DriverRequest`,
not in a `Completion`, not in a log line and not in an exception. See
`THE_KEY_IS_READ_WHERE_THE_SDK_WOULD_READ_IT`.

**What a failure may say is decided by a closed list and a class, never by a provider's
sentence.** An error body's `type` or `code` is read only to choose between the members of the
`TransportError` family: `context_length_exceeded` becomes `ContextWindowExceededError`, a named
content refusal becomes `ContentPolicyRefusedError`, and everything else is a
`TransportStatusError` whose code `adapter.safe_code` drops unless it is already known. The
`message` field is never read. Anthropic reports an over-long prompt as an ordinary 400 whose
only distinguishing feature is that message, so on that provider an overflow stops the chain
instead of escalating a tier; that is the conservative direction and it is stated rather than
papered over with a string match. See `A_PROVIDERS_SENTENCE_DECIDES_NOTHING`.

What was rejected. *Installing LiteLLM after all.* It is a second dependency tree the size of
this repository's, the routing it offers is refused by `driver.LITELLM_IS_A_DRIVER_NOT_A_PROXY`,
and what is left of it is two POST requests. *The providers' own SDKs.* Neither is a dependency,
each brings its own retry loop that would have to be switched off to keep
`test_the_adapter_never_retries_on_its_own` true, and each stringifies its request into its
exceptions, which is the leak `NOTHING_FROM_THE_REQUEST_IN_AN_EXCEPTION` names. *An async
client.* `ModelDriver` is synchronous on purpose and the executor runs a call in a worker thread,
so a synchronous client is the one that matches the seam.

Task ids: M5.1.1, M5.1.2
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import httpx

from brain.models.adapter import (
    Completion,
    ContentPolicyRefusedError,
    ContextWindowExceededError,
    Transport,
    TransportConnectionError,
    TransportError,
    TransportStatusError,
    TransportTimeoutError,
)
from brain.models.driver import DriverRequest, Role
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.settings import process_environment

# ------------------------------------------------------------------- written-down reasons

#: Why a provider's address is a constant of the product and not a setting.
A_PROVIDER_IS_REACHED_AT_ITS_OWN_ADDRESS_AND_NEVER_ONE_A_PERSON_TYPED: Final = (
    "A hosted provider's key goes out with every request to its address. An address somebody "
    "can edit is a key somebody can redirect to a server they run, and the questions with it, "
    "so a hosted provider is reached where the product says it is and nowhere else. The only "
    "address that is configuration is the install's own inference server, read through "
    "brain.install.value_of and refused unless it is an origin."
)

#: Why the key is read on every call rather than held by the transport.
THE_KEY_IS_READ_WHERE_THE_SDK_WOULD_READ_IT: Final = (
    "brain.ops.provider_keys loads a key into the process environment for the provider's own "
    "client to find, and brain.ops.credentials replaces it there when an administrator saves a "
    "new one. A transport holding a copy would send the old key after a rotation this process "
    "reported as in use. So the variable is read when the header is built, the value is that "
    "header and nothing else, and no object this module returns can carry it."
)

#: Why the text of an error body never decides anything.
A_PROVIDERS_SENTENCE_DECIDES_NOTHING: Final = (
    "An error body's message is the provider's prose, it changes when they reword it, and it "
    "routinely quotes the request. Only the error's type or code is read, and only to choose a "
    "member of the closed TransportError family. Where a provider distinguishes a failure by its "
    "message alone, the failure is treated as the ordinary status it arrived with, which stops "
    "the chain rather than retrying it."
)

# --------------------------------------------------------------------------- the figures

#: The version of Anthropic's Messages API this transport writes. A header the provider
#: requires on every request; a different version is a different wire shape, so it is a
#: constant here beside the shape rather than something a caller chooses.
ANTHROPIC_VERSION: Final = "2023-06-01"

#: What a request asks for when the caller named no output limit. The Messages API refuses a
#: request without one, and a chat completions request without one is bounded only by the
#: model's window, which is a bill nobody chose. A person is usually waiting, and a thousand
#: tokens is several paragraphs.
DEFAULT_MAX_OUTPUT_TOKENS: Final = 1024

#: Where each hosted provider is, declared once at the top of the file, which is what
#: `brain.ops.independence` admits a vendor's host by.
ANTHROPIC_BASE_URL: Final = "https://api.anthropic.com"
OPENAI_BASE_URL: Final = "https://api.openai.com/v1"
MOONSHOT_BASE_URL: Final = "https://api.moonshot.ai/v1"

#: The provider name a rung uses for this install's own inference server. Not a key slot: the
#: server needs no key, and it sits inside the client's network.
LOCAL_PROVIDER: Final = "local"

#: Error codes that mean the request did not fit the model's window, by the name the chat
#: completions shape uses for it. A closed set of names, never a pattern.
CONTEXT_EXCEEDED_CODES: Final[frozenset[str]] = frozenset({"context_length_exceeded"})

#: Error codes that mean the provider declined on content grounds rather than failing.
REFUSAL_CODES: Final[frozenset[str]] = frozenset({"content_filter", "content_policy_violation"})


class Wire(enum.StrEnum):
    """The two request shapes this module can write."""

    #: `POST /v1/messages`, the system prompt as a field of its own, `x-api-key`.
    ANTHROPIC_MESSAGES = "anthropic_messages"
    #: `POST /chat/completions`, the system prompt as a message, a bearer token.
    CHAT_COMPLETIONS = "chat_completions"


@dataclass(frozen=True)
class ProviderWire:
    """How one provider is reached: its address, its shape, and which key slot, if any.

    `output_limit` is the body field the output ceiling is written under. The chat completions
    shape has two spellings and they are not interchangeable: OpenAI's current models refuse
    `max_tokens` and require `max_completion_tokens`, while Moonshot and the local runtimes take
    `max_tokens`. Declared per provider rather than guessed per model.
    """

    provider: str
    wire: Wire
    base_url: str
    slot: ProviderSlot | None
    output_limit: str = "max_tokens"

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("https://", "http://")):
            msg = f"{self.provider} is reached at {self.base_url!r}, which is not an origin"
            raise ValueError(msg)
        if self.slot is not None and self.slot.slug != self.provider:
            msg = f"{self.provider} is given the key slot for {self.slot.slug}"
            raise ValueError(msg)

    @property
    def url(self) -> str:
        """Where a request is posted: the base with the shape's own path joined on."""
        base = self.base_url.rstrip("/")
        if self.wire is Wire.ANTHROPIC_MESSAGES:
            return f"{base}/v1/messages"
        return f"{base}/chat/completions"


def _slot(slug: str) -> ProviderSlot:
    for one in PROVIDER_SLOTS:
        if one.slug == slug:
            return one
    msg = f"no key slot for {slug!r}"
    raise ValueError(msg)


#: Every hosted provider this system can call, keyed by the slug a rung names it by.
PROVIDER_WIRES: Final[Mapping[str, ProviderWire]] = MappingProxyType(
    {
        "anthropic": ProviderWire(
            provider="anthropic",
            wire=Wire.ANTHROPIC_MESSAGES,
            base_url=ANTHROPIC_BASE_URL,
            slot=_slot("anthropic"),
        ),
        "openai": ProviderWire(
            provider="openai",
            wire=Wire.CHAT_COMPLETIONS,
            base_url=OPENAI_BASE_URL,
            slot=_slot("openai"),
            output_limit="max_completion_tokens",
        ),
        "moonshot": ProviderWire(
            provider="moonshot",
            wire=Wire.CHAT_COMPLETIONS,
            base_url=MOONSHOT_BASE_URL,
            slot=_slot("moonshot"),
        ),
    }
)


def local_wire(address: str) -> ProviderWire:
    """The install's own inference server, at the address the install configured.

    The chat completions shape under `/v1`, which is what the local runtimes serve. No slot: a
    key sent to a server inside the client's network would be a key with nothing to protect.
    """
    return ProviderWire(
        provider=LOCAL_PROVIDER,
        wire=Wire.CHAT_COMPLETIONS,
        base_url=f"{address.rstrip('/')}/v1",
        slot=None,
    )


# ---------------------------------------------------------------------------- the key

#: Reads a key at the moment of a call, or None when none is held.
KeyLookup = Callable[[], str | None]


def environment_key(slot: ProviderSlot) -> KeyLookup:
    """The slot's variable, read from this process's environment at each call.

    See `THE_KEY_IS_READ_WHERE_THE_SDK_WOULD_READ_IT`. A blank value is no key, for the reason
    `brain.settings.A_BLANK_VARIABLE_IS_AN_UNSET_ONE` gives about every other setting.
    """

    def read() -> str | None:
        found = process_environment().get(slot.env_var, "").strip()
        return found or None

    return read


class KeyNotHeldError(TransportError):
    """The provider needs a key and this process holds none at the moment of the call.

    A bare member of the family, so `failure_from` gives it no trigger and the chain stops. A
    key that was present when the chain was planned and is absent now is a process whose
    environment changed under it, and retrying on the next rung would hide that.
    """


# ------------------------------------------------------------------------- the bodies


def _system_and_turns(request: DriverRequest) -> tuple[str, list[dict[str, str]]]:
    """The system text joined, and the other turns in order, as both shapes need them."""
    system = "\n\n".join(m.content for m in request.messages if m.role is Role.SYSTEM)
    turns = [
        {"role": m.role.value, "content": m.content}
        for m in request.messages
        if m.role is not Role.SYSTEM
    ]
    return system, turns


def request_body(wire: ProviderWire, request: DriverRequest) -> dict[str, Any]:
    """The JSON body one call posts. The provider's knobs in `extra` are passed through.

    `extra` is added last and cannot replace the model, the messages or the output limit: a
    caller-supplied `model` would answer from a deployment the router never chose, which is the
    second router `DriverRequest` exists to refuse.
    """
    limit = request.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
    system, turns = _system_and_turns(request)
    body: dict[str, Any] = {
        key: value
        for key, value in request.extra.items()
        if key not in {"model", "messages", "system", wire.output_limit}
    }
    if wire.wire is Wire.ANTHROPIC_MESSAGES:
        body.update({"model": request.model, "max_tokens": limit, "messages": turns})
        if system:
            body["system"] = system
        return body
    messages = ([{"role": Role.SYSTEM.value, "content": system}] if system else []) + turns
    body.update({"model": request.model, wire.output_limit: limit, "messages": messages})
    return body


def request_headers(wire: ProviderWire, key: str | None) -> dict[str, str]:
    """The headers one call sends. The key is in exactly one of them, or in none."""
    headers = {"content-type": "application/json"}
    if wire.wire is Wire.ANTHROPIC_MESSAGES:
        headers["anthropic-version"] = ANTHROPIC_VERSION
        if key is not None:
            headers["x-api-key"] = key
    elif key is not None:
        headers["authorization"] = f"Bearer {key}"
    return headers


# ---------------------------------------------------------------------- the responses


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def completion_from(wire: ProviderWire, payload: object) -> Completion:
    """A successful response body, in our vocabulary. Defensive on every field.

    A body that is not an object is not a completion at all and is raised as an unrecognised
    failure, so the chain stops. Anything missing inside one is ordinary: a response with no
    usage block is an answer whose cost was not reported, and reporting a working provider as
    an outage over it would be worse.
    """
    if not isinstance(payload, dict):
        raise TransportError
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    served = payload.get("model")
    served_model = served if isinstance(served, str) else ""
    if wire.wire is Wire.ANTHROPIC_MESSAGES:
        blocks = payload.get("content")
        text = "".join(
            str(block.get("text", ""))
            for block in (blocks if isinstance(blocks, list) else [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        stop = payload.get("stop_reason")
        return Completion(
            text=text,
            finish_reason=stop if isinstance(stop, str) else "",
            input_tokens=_int(usage.get("input_tokens")),
            output_tokens=_int(usage.get("output_tokens")),
            cached_input_tokens=_int(usage.get("cache_read_input_tokens")),
            served_model=served_model,
        )
    choices = payload.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else {}
    first = first if isinstance(first, dict) else {}
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    finish = first.get("finish_reason")
    details = usage.get("prompt_tokens_details")
    return Completion(
        text=content if isinstance(content, str) else "",
        finish_reason=finish if isinstance(finish, str) else "",
        input_tokens=_int(usage.get("prompt_tokens")),
        output_tokens=_int(usage.get("completion_tokens")),
        cached_input_tokens=_int(details.get("cached_tokens") if isinstance(details, dict) else 0),
        served_model=served_model,
    )


def error_name(payload: object) -> str:
    """The error's machine name out of an error body: its code, else its type. Never the message.

    See `A_PROVIDERS_SENTENCE_DECIDES_NOTHING`.
    """
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    for field in ("code", "type"):
        value = error.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().casefold()
    return ""


def failure_for_status(status: int, payload: object) -> TransportError:
    """A non-success response, as a member of the closed family."""
    name = error_name(payload)
    if name in CONTEXT_EXCEEDED_CODES:
        return ContextWindowExceededError()
    if name in REFUSAL_CODES:
        return ContentPolicyRefusedError(status=status)
    return TransportStatusError(status, code=name)


def _json_or_none(response: httpx.Response) -> object:
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


# ------------------------------------------------------------------------ the transport


def http_transport(
    wire: ProviderWire,
    *,
    client: httpx.Client,
    key: KeyLookup | None = None,
) -> Transport:
    """One provider's `Transport`: build the body, post it once, read the answer.

    `key` defaults to the slot's environment variable; a test hands a lookup of its own, and a
    wire with no slot is sent with no key whatever it is handed. Every exception `httpx` raises
    is translated and raised `from None`, for the reason `adapter.SdkDriver.complete` gives:
    chaining keeps the client's own exception, which names the URL and may carry more, in
    `__cause__` where every traceback formatter renders it.
    """
    lookup = key if key is not None else (environment_key(wire.slot) if wire.slot else None)

    def send(request: DriverRequest) -> Completion:
        held: str | None = None
        if wire.slot is not None:
            held = lookup() if lookup is not None else None
            if held is None:
                raise KeyNotHeldError
        try:
            response = client.post(
                wire.url,
                json=request_body(wire, request),
                headers=request_headers(wire, held),
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException:
            raise TransportTimeoutError from None
        except httpx.TransportError:
            raise TransportConnectionError from None
        payload = _json_or_none(response)
        if response.status_code >= 300:
            raise failure_for_status(response.status_code, payload) from None
        return completion_from(wire, payload)

    return send
