"""Model provider API keys, which cannot be leased and must not pretend to be.

`brain.ops.secrets` refuses read-by-path on purpose: a vault that hands over a standing
credential is a vault whose credentials live as long as the caller, and `brain.ops.openbao`
refuses a static engine outright for the same reason.

**A provider API key breaks that rule and there is no way to make it not.** OpenAI,
Anthropic and Moonshot issue a key that is valid until somebody revokes it in a dashboard.
There is no engine that mints a fresh one per request, so there is nothing to lease and
nothing to hand back. Pretending otherwise - wrapping a static value in a `Lease` with an
invented expiry - would be worse than this module: the caller would believe the credential
stops working at a time nothing enforces.

So this is a separate type, deliberately not implementing `Vault`, with the difference in
the name. Somebody reaching for `borrow()` and finding it does not work here should have to
notice why.

**What keeps it from becoming a general read-by-path.** The refusal lives on
`OpenBaoVault.read_static_kv`, not here, and that placement is the point: a guard on the
caller is a guard somebody bypasses by calling the other thing. Any path outside
`providers/` is refused by the object that would otherwise do the reading. Without it,
`read_static_kv("connectors/creds/xero")` works perfectly, hands out a standing connector
credential with nothing to revoke and no record of which run held it, and nobody sees the
difference until an audit asks.

**The key is read once and never travels.** It goes straight into the process environment
where the provider SDK finds it, which is where `brain.models.adapter` already argues it
should live: a key in the environment cannot be in a request object, cannot be in a trace,
and cannot be in an exception the adapter builds. This module therefore never returns the
value to application code at all - `load_into_environment` sets it and returns only the
names it set.

**Rotation reaches a running process without a restart.** Until 2026-09-17 this paragraph said
rotation was a restart, on the argument that a re-read loop over a value that must not be logged
was not worth it for a change made twice a year. The argument missed what rotation is for: a key
is usually replaced because it leaked, and every minute a process keeps the old one it goes on
sending it. On a panel that redeploys to restart, a restart is also a redeploy.
`brain.ops.credentials.Credentials.refresh` now reads each slot's metadata once a minute, which
holds no field of the secret, and calls `read_static` and `put_into_environment` only for a slot
whose version moved. The process an administrator's write went through still uses it at once.

**A value that was in the environment before the vault was asked outranks the vault, on
every start.** That is `load_into_environment`'s rule and it is kept: a developer's shell key
means it. `names_in_environment` is how a process remembers which names that was true of, so
a key written from the console into a slot the environment file also sets can be reported as
outranked rather than as in use.

Task ids: M5.1.2, M27.8.7, M31.3.2.5, M5.7.1, M5.7.2
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol

from brain.ops.openbao import (
    STATIC_PREFIX,
    OpenBaoVault,
    VaultUnreachableError,
    assert_static_path,
)
from brain.ops.secrets import SecretsUnavailableError
from brain.settings import process_environment, writable_process_environment

__all__ = [
    "PROVIDER_SLOTS",
    "STATIC_PREFIX",
    "ProviderSlot",
    "added_slot",
    "assert_static_path",
    "load_into_environment",
    "names_in_environment",
    "put_into_environment",
    "read_static",
]


#: What a provider slug may look like. Interpolated into a vault path and used to build an
#: environment variable name, so it is validated rather than trusted.
class StaticKvReader(Protocol):
    """A vault that reads one slot's fields under the static prefix. `OpenBaoVault` is one."""

    def read_static_kv(self, path: str) -> dict[str, Any]:
        """The slot's fields, or a `SecretsUnavailableError`."""
        ...


SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


@dataclass(frozen=True)
class ProviderSlot:
    """One provider's key: where it lives and what the SDK expects it to be called.

    The environment variable name is declared rather than derived. Deriving it - upper-case
    the slug and append `_API_KEY` - is right for three providers and wrong for the fourth,
    and being wrong means the SDK silently falls back to an unauthenticated call or to a key
    left over from something else.
    """

    slug: str
    env_var: str
    description: str = ""

    def __post_init__(self) -> None:
        if not SLUG_RE.match(self.slug):
            msg = f"{self.slug!r} is not a provider slug"
            raise ValueError(msg)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,60}", self.env_var):
            msg = f"{self.env_var!r} is not an environment variable name"
            raise ValueError(msg)

    @property
    def path(self) -> str:
        return f"{STATIC_PREFIX}{self.slug}"


#: Every provider this system can route to. Closed, and a member is added deliberately: a
#: provider that can be configured but was never argued about is a provider whose key
#: nobody decided to trust.
PROVIDER_SLOTS: tuple[ProviderSlot, ...] = (
    ProviderSlot(
        slug="anthropic",
        env_var="ANTHROPIC_API_KEY",
        description="Claude, the default reasoner",
    ),
    ProviderSlot(
        slug="openai",
        env_var="OPENAI_API_KEY",
        description="Embeddings, and a fallback for completion",
    ),
    ProviderSlot(
        slug="moonshot",
        env_var="MOONSHOT_API_KEY",
        description="The cheaper reasoner; the v1 system routes to it by default",
    ),
    ProviderSlot(
        slug="deepseek",
        env_var="DEEPSEEK_API_KEY",
        description="DeepSeek, reached through its OpenAI-compatible interface",
    ),
)

#: What an added provider's environment variable is called: the slug between a prefix and a
#: suffix no built-in provider's variable uses, so an added provider can never set one of theirs.
ADDED_ENV_PREFIX = "BRAIN_PROVIDER_"
ADDED_ENV_SUFFIX = "_KEY"


def added_slot(slug: str) -> ProviderSlot:
    """The key slot of a provider an administrator added from the console (M5.7.2).

    Its vault path is `providers/<slug>`, which the application policy's `providers/data/+`
    already admits, and its variable is `BRAIN_PROVIDER_<SLUG>_KEY`. Refuses a built-in slug:
    an added provider named `openai` would be a second writer of the key every question to
    OpenAI goes out with, at an address a person typed.
    """
    if any(one.slug == slug for one in PROVIDER_SLOTS):
        msg = f"{slug!r} is a built-in provider, so it cannot be added"
        raise ValueError(msg)
    return ProviderSlot(
        slug=slug,
        env_var=f"{ADDED_ENV_PREFIX}{slug.upper()}{ADDED_ENV_SUFFIX}",
        description=f"The key for {slug}, a provider added from the console",
    )


class AddedProviderSlots:
    """The key slots of the providers added from the console, as this process last read them.

    An added provider exists only as a row, so the process learns its slot when it reads the
    registry (`brain.ops.model_service`, on every planned call and every Models screen read), and
    the minute's key refresh (`brain.ops.credentials.Credentials.refresh`) then loads its key.
    A lock, because the refresh runs in a worker thread and the registry is read on the loop.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, ProviderSlot] = {}

    def learn(self, slugs: Iterable[str]) -> None:
        """Replace what this process knows with the live added providers' slugs."""
        found = {slug: added_slot(slug) for slug in slugs}
        with self._lock:
            self._slots = found

    def slots(self) -> tuple[ProviderSlot, ...]:
        """Every added provider's slot this process knows, by slug."""
        with self._lock:
            return tuple(self._slots[slug] for slug in sorted(self._slots))

    def slot(self, slug: str) -> ProviderSlot | None:
        """One added provider's slot, or None when this process has not read it."""
        with self._lock:
            return self._slots.get(slug)


#: The one this process holds. A process-wide fact, like the environment the keys are put in.
PROCESS_ADDED_SLOTS = AddedProviderSlots()


def read_static(vault: StaticKvReader, path: str) -> str:
    """One value out of the vault's kv engine. Never returned to application code.

    Public only so `load_into_environment` can be read as two steps rather than one long
    one. A caller that wants a provider key wants the environment variable set, not the
    string; anything holding the string is a place the string can be logged from.
    """
    # The prefix refusal and the kv v2 path rewrite both live on the vault, because a guard
    # on the caller is a guard somebody bypasses by calling the other thing.
    data = vault.read_static_kv(path)
    if not data:
        msg = f"no value in the vault at {path!r}; the slot exists and is empty"
        raise SecretsUnavailableError(msg)

    for key in ("api_key", "key", "value", "token"):
        if key in data:
            value = str(data[key])
            if not value.strip():
                msg = f"the slot at {path!r} holds an empty value"
                raise SecretsUnavailableError(msg)
            return value
    msg = f"the slot at {path!r} holds fields this does not recognise: {sorted(data)[:5]}"
    raise SecretsUnavailableError(msg)


def load_into_environment(
    vault: OpenBaoVault,
    slots: tuple[ProviderSlot, ...] = PROVIDER_SLOTS,
    *,
    environ: MutableMapping[str, str] | None = None,
    required: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Set each provider's environment variable from the vault. Returns the names set.

    **Returns names, never values.** A function that handed back the keys would be a
    function whose return value must not be logged, and every caller would have to know
    that. Returning the names means the result is safe to print, which is what makes the
    startup log line "loaded ANTHROPIC_API_KEY, OPENAI_API_KEY" possible at all.

    **A missing slot is skipped unless it is required.** Before go-live every slot is empty
    by design, and refusing to start would mean the system cannot run at all until every
    provider is configured - including the ones this deployment does not use. `required`
    names the ones this deployment genuinely cannot work without.

    **An existing value is not overwritten.** A developer running with a key in their shell
    means it; and on the server there is nothing in the environment to collide with, because
    the compose file deliberately sets none of these.
    """
    env: MutableMapping[str, str] = (
        environ if environ is not None else writable_process_environment()
    )
    loaded: list[str] = []
    missing: list[str] = []
    silent = False

    for slot in slots:
        if env.get(slot.env_var):
            # Already set, and deliberately left alone. Overwriting would make a developer's
            # explicit local key silently ineffective, which is a confusing hour.
            loaded.append(slot.env_var)
            continue
        if silent:
            # A vault that did not answer for one slot will not answer for the next inside the
            # same second, and each asking costs `TIMEOUT_SECONDS` of a process that is starting.
            missing.append(slot.slug)
            continue
        try:
            env[slot.env_var] = read_static(vault, slot.path)
        except VaultUnreachableError:
            silent = True
            missing.append(slot.slug)
            continue
        except SecretsUnavailableError:
            # Not re-raised, and the message is not logged here: it names the path, and a
            # path names which provider is unconfigured, which is fine - but the caller
            # decides what to say. What matters is that a missing key is not a crash.
            missing.append(slot.slug)
            continue
        loaded.append(slot.env_var)

    unmet = sorted(set(required) & set(missing))
    if unmet:
        msg = (
            f"no key in the vault for {', '.join(unmet)}, and this deployment requires them. "
            "The slot exists and is empty; put a key in it rather than setting an "
            "environment variable, or the vault stops being the record of what is configured."
        )
        raise SecretsUnavailableError(msg)
    return tuple(loaded)


def names_in_environment(
    slots: Iterable[ProviderSlot] = PROVIDER_SLOTS, *, environ: Mapping[str, str] | None = None
) -> frozenset[str]:
    """Which of these slots' variables the environment sets right now. Names, never values.

    Asked once, before `load_into_environment`, by whoever needs to know which keys came from
    somewhere other than the vault and will again on the next start.
    """
    env = process_environment() if environ is None else environ
    return frozenset(slot.env_var for slot in slots if env.get(slot.env_var))


def put_into_environment(
    slot: ProviderSlot, value: str, *, environ: MutableMapping[str, str] | None = None
) -> None:
    """Hand a key just written to the vault to this process's provider SDK. Returns nothing.

    The one other writer of the process environment beside `load_into_environment`, and in
    this module for the reason that one is: `brain.settings.writable_process_environment`
    exists for provider keys alone. Overwrites, unlike the start-up load, because the value in
    hand is the one an administrator has just chosen; whether this process should use it at all
    is the caller's decision, which is `brain.ops.credentials.Credentials.put_to_use`.
    """
    if not value.strip():
        msg = f"refusing to hand {slot.env_var} an empty key; the vault would hold one it cannot"
        raise SecretsUnavailableError(msg)
    env = writable_process_environment() if environ is None else environ
    env[slot.env_var] = value
