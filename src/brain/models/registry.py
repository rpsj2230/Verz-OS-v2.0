"""The install's record of each model provider: where it processes, what it agreed, how to call it.

`ops.model_provider` is the storage and this is what a row means. Four leaves meet here, and
they meet in one type because they are four facts about the same provider:

- **M5.6.4**: the processing region, the retention and training terms and a link to the signed
  agreement. Words the company's own agreement uses, kept where the console can list and export
  them, rather than a provider's marketing page somebody remembers.
- **M5.5.3**: the residency registry with a documented storage location. A row that names a
  region and the class `region_pinned` is what makes an assembled rung satisfy a residency
  constraint; a provider nobody documented stays `global`, which satisfies none. See
  `A_RESIDENCY_CLAIM_IS_WHAT_THE_REGISTRY_SAYS_AND_NOTHING_ELSE`.
- **M5.1.3**: the per-lane timeout and attempt overrides, which `driver.ProviderClient` applied
  and nothing could edit. They are a column of this row and edited beside the terms.
- **M5.7.2**: a provider with an OpenAI-compatible interface added from the console with its
  address, key and model names.

**An added provider's address is fixed when it is added.** `brain.models.wire` refuses to let a
person type where a hosted provider is reached, because the key goes with every request to that
address. An added provider is a provider a person did type, so the argument is kept a different
way: the address is written once, with a key written at the same moment into that provider's
own vault slot, and there is no edit of it. Pointing the provider somewhere else means adding a
new one and entering a key for it, so nobody can redirect a key somebody else entered. See
`AN_ADDED_PROVIDERS_ADDRESS_IS_BOUND_TO_THE_KEY_ENTERED_WITH_IT`.

**An added provider's slug cannot be a built-in one's.** A slug is the vault path and the
environment variable, so an added `openai` would be a second writer of the key every question to
OpenAI goes out with, at an address a person typed.

Rejected: a free-form address for the built-in providers, so an install could use a regional
endpoint. That is the redirection above in its plainest form; a regional endpoint is added as an
OpenAI-compatible provider with its own key.

Scope: pure. Rows arrive as mappings; nothing here reads a database, the vault or a clock.

Task ids: M5.6.4, M5.5.3, M5.1.3, M5.7.2
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from brain.core.lane import Lane
from brain.models.driver import LaneOverride, ProviderClient
from brain.models.routing import ResidencyClass

# ------------------------------------------------------------------- written-down reasons

#: Why an added provider's address is never edited.
AN_ADDED_PROVIDERS_ADDRESS_IS_BOUND_TO_THE_KEY_ENTERED_WITH_IT: Final = (
    "The key goes with every request to the provider's address. An address somebody could edit "
    "after another person entered the key is a key they could send to a server they run, with "
    "every question beside it. So an added provider's address is written once, together with "
    "its own key in its own slot, and is never changed: a new address is a new provider and a "
    "new key."
)

#: Why only the registry can make a rung satisfy a residency constraint.
A_RESIDENCY_CLAIM_IS_WHAT_THE_REGISTRY_SAYS_AND_NOTHING_ELSE: Final = (
    "A rung satisfies a residency constraint when the provider's row names a region and the "
    "class region_pinned, which is the company recording what its agreement promises. A "
    "provider with no row, or a row that names no region, is global, and global satisfies no "
    "constraint, so an undocumented provider fails closed."
)

#: A provider slug: one vault path segment and part of an environment variable name. The same
#: grammar as `brain.ops.provider_keys.SLUG_RE`, which a test holds equal.
SLUG_PATTERN: Final = r"^[a-z][a-z0-9_]{1,30}$"
_SLUG_RE: Final = re.compile(SLUG_PATTERN)

#: An https origin with an optional path and nothing else: no user, query or fragment. The same
#: as `brain.tables.model_registry.HTTPS_ADDRESS_PATTERN`, which a test holds equal.
HTTPS_ADDRESS_PATTERN: Final = r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$"
_ADDRESS_RE: Final = re.compile(HTTPS_ADDRESS_PATTERN)

#: A model name as providers write them: `gpt-4o-mini`, `deepseek-chat`, `org/model:tag`.
MODEL_NAME_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$"
_MODEL_RE: Final = re.compile(MODEL_NAME_PATTERN)

#: The most model names one added provider may list. A resource bound, far above a real one.
MAX_MODELS: Final = 20

#: The lanes an override may name. The fast lane takes no model, so it has no call policy.
OVERRIDABLE_LANES: Final[tuple[Lane, ...]] = (Lane.ANSWER, Lane.TASK)

#: The most seconds an override may set, the ladder's own ceiling in `brain.routing_routes`.
MAX_OVERRIDE_TIMEOUT_SECONDS: Final = 600.0

#: The most attempts an override may set. A person is waiting on the answer lane, and a retry
#: storm on the task lane is still a bill.
MAX_OVERRIDE_ATTEMPTS: Final = 5


class ProviderKind(enum.StrEnum):
    """Whether the product reaches this provider at its own address or at one a person gave."""

    #: One of `brain.models.wire.PROVIDER_WIRES`. The row carries terms and no address.
    BUILTIN = "builtin"
    #: Added from the console: the chat completions shape at the address on the row.
    OPENAI_COMPATIBLE = "openai_compatible"


class RegistryError(ValueError):
    """A provider described in a way the registry refuses, with the reason in words."""


def parse_lane_overrides(raw: Mapping[str, Any]) -> Mapping[Lane, LaneOverride]:
    """The stored `lane_overrides` object as overrides, or a `RegistryError` saying what is wrong.

    Only the answer and task lanes, only the two fields `LaneOverride` has, and each bounded:
    a stored override that could not be applied would be a configuration the screen shows and
    the executor ignores.
    """
    parsed: dict[Lane, LaneOverride] = {}
    for key, value in raw.items():
        try:
            lane = Lane(key)
        except ValueError:
            msg = f"{key!r} is not a lane an override may name"
            raise RegistryError(msg) from None
        if lane not in OVERRIDABLE_LANES:
            msg = f"the {lane} lane takes no model, so it has no call policy to override"
            raise RegistryError(msg)
        if not isinstance(value, Mapping) or set(value) - {"timeout_seconds", "attempts"}:
            msg = f"the {lane} override may set timeout_seconds and attempts and nothing else"
            raise RegistryError(msg)
        timeout = value.get("timeout_seconds")
        attempts = value.get("attempts")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not 0 < timeout <= MAX_OVERRIDE_TIMEOUT_SECONDS
        ):
            msg = f"the {lane} timeout must be above 0 and at most {MAX_OVERRIDE_TIMEOUT_SECONDS}"
            raise RegistryError(msg)
        if attempts is not None and (
            isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or not 1 <= attempts <= MAX_OVERRIDE_ATTEMPTS
        ):
            msg = f"the {lane} attempts must be between 1 and {MAX_OVERRIDE_ATTEMPTS}"
            raise RegistryError(msg)
        parsed[lane] = LaneOverride(
            timeout_seconds=None if timeout is None else float(timeout), attempts=attempts
        )
    return MappingProxyType(parsed)


def check_added(slug: str, base_url: str, models: Iterable[str], *, taken: Iterable[str]) -> None:
    """Refuse an added provider whose slug, address or model names the registry cannot hold.

    `taken` is every slug already in use: the built-in providers, the local server and every
    live added provider. See the module docstring on why a built-in slug is refused.
    """
    if not _SLUG_RE.fullmatch(slug):
        msg = "the name must be 2 to 31 lower-case letters, digits or underscores, a letter first"
        raise RegistryError(msg)
    if slug in set(taken):
        msg = f"{slug!r} is already a provider on this install; choose another name"
        raise RegistryError(msg)
    if not _ADDRESS_RE.fullmatch(base_url):
        msg = "the address must be an https address with no user, query or fragment"
        raise RegistryError(msg)
    names = tuple(models)
    if not names or len(names) > MAX_MODELS:
        msg = f"list between 1 and {MAX_MODELS} model names"
        raise RegistryError(msg)
    for name in names:
        if not _MODEL_RE.fullmatch(name):
            msg = f"{name!r} is not a model name"
            raise RegistryError(msg)
    if len(set(names)) != len(names):
        msg = "a model name is listed twice"
        raise RegistryError(msg)


def check_agreement(url: str | None) -> None:
    """Refuse an agreement link that is not an https address."""
    if url is not None and not _ADDRESS_RE.fullmatch(url):
        msg = "the agreement link must be an https address with no user, query or fragment"
        raise RegistryError(msg)


@dataclass(frozen=True)
class ProviderRecord:
    """One row of `ops.model_provider`, as routing and the console read it."""

    slug: str
    kind: ProviderKind
    label: str
    base_url: str | None = None
    models: tuple[str, ...] = ()
    processing_region: str = "global"
    residency_class: ResidencyClass = ResidencyClass.GLOBAL
    storage_location: str = ""
    retention_terms: str = ""
    training_terms: str = ""
    agreement_url: str | None = None
    lane_overrides: Mapping[Lane, LaneOverride] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if (self.kind is ProviderKind.OPENAI_COMPATIBLE) != (self.base_url is not None):
            msg = "an added provider has an address and a built-in one never does"
            raise RegistryError(msg)
        if self.residency_class is not ResidencyClass.GLOBAL and (
            not self.processing_region or self.processing_region == "global"
        ):
            msg = "a pinned residency names the region it is pinned to"
            raise RegistryError(msg)

    @property
    def client(self) -> ProviderClient:
        """The M5.1.3 client: this provider's per-lane overrides, applied by the executor."""
        return ProviderClient(provider=self.slug, lanes=self.lane_overrides)

    @property
    def region(self) -> str:
        """The region an assembled rung carries: the documented one, or `global` with none."""
        if self.residency_class is ResidencyClass.GLOBAL:
            return "global"
        return self.processing_region


def record_of(row: Mapping[str, Any]) -> ProviderRecord:
    """One stored row as a record. Raises `RegistryError` on a row the registry cannot hold."""
    return ProviderRecord(
        slug=str(row["slug"]),
        kind=ProviderKind(row["kind"]),
        label=str(row["label"]),
        base_url=row.get("base_url"),
        models=tuple(str(one) for one in row.get("models") or ()),
        processing_region=str(row.get("processing_region") or "global"),
        residency_class=ResidencyClass(row.get("residency_class") or ResidencyClass.GLOBAL),
        storage_location=str(row.get("storage_location") or ""),
        retention_terms=str(row.get("retention_terms") or ""),
        training_terms=str(row.get("training_terms") or ""),
        agreement_url=row.get("agreement_url"),
        lane_overrides=parse_lane_overrides(row.get("lane_overrides") or {}),
    )


@dataclass(frozen=True)
class ModelPin:
    """A provider and model an administrator pinned for an agent (M5.7.3).

    Tried first, through the rung on the ladder that serves exactly this pair, with the agent's
    tier behind it. A pin that names no answering rung is passed over and the tier answers:
    a pin is a preference about which model, never a way round the ladder's switches, keys,
    residency or breakers, all of which the pinned rung is subject to like any other.
    """

    provider: str
    model: str

    def __post_init__(self) -> None:
        if not _SLUG_RE.fullmatch(self.provider) and self.provider != "local":
            msg = f"{self.provider!r} is not a provider name"
            raise RegistryError(msg)
        if not _MODEL_RE.fullmatch(self.model):
            msg = f"{self.model!r} is not a model name"
            raise RegistryError(msg)
