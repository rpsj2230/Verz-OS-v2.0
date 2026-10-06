"""Reading a source through custom code: the code plans, the host calls, the key stays outside.

`brain.connectors.transports.CustomTransport` declared a module and a sandbox profile, and until
this module nothing could run one. This is the seam a custom connector reads through, and **it is
the seam and not the sandbox**: the code runs through `brain.tools.run_skill.ScriptRunner`, the
one contract every sandboxed run in this product uses, and the runner itself (the process, the
filesystem, the cgroup) is an optional service an install runs or does not
(`brain.tools.run_skill.SANDBOX_PROPERTIES`, needs-rupash 154).

**The code turns a request into planned calls, and makes none of them.** A planning run is handed
the entity, the record's id where one record is read, and the connection's settings, and prints
the calls that would read it: a method, an address, a body. That is a pure function with no
input but its arguments and no output but what it prints, which is exactly what a sandbox with no
network can run. The host then makes each call itself, through the path every REST reading's calls
take: the address rule and the pinned connection, the source's verified ceiling admitting each
call, the run's timeout and response bound, and the leased key in the one header the reading's
`KeyScheme` names. **Where the connector needs it, the answers go back into the sandbox to be
interpreted**, in a second run that is just as credential-free; otherwise the declared field
mapping reads them, as it reads a REST answer. Either way what is kept is the entity's declared
index fields, and every record is mapped by `brain.connectors.rest.mapped_row`, so an unmapped
field never arrives.

**The key never enters the sandbox** (`THE_KEY_NEVER_ENTERS_THE_SANDBOX`). The browsing agent's
rule that the credential never reaches the model, for the same reason: code a company did not
write is a reader whose output nobody can audit before it is printed. `SandboxSpec` already has no
field a key could be put in, and `assert_keyless` checks every spec this module builds against
the key the host holds before it is run, because the one way a key could still arrive is inside
an answer handed back for interpretation, from a source that echoes the request. A spec carrying
it is refused and nothing is run.

**A planned call goes only to a host the declaration allowlists.**
`CustomTransport.egress_allowlist` was written for a sandbox with egress, and the sandbox now
never has any (`Egress.DENIED` is the only member). The list is read here instead, by the host,
before it calls anything on the code's behalf, and a profile with no list plans no call that will
be made. So the list a reviewer approved is still the whole of where this connector reaches.

Rejected, both on the coordinator's answer of 2026-10-06:

- **Passing the key to the sandbox.** It needs a field `SandboxSpec` deliberately lacks, and it
  would put the one secret this install holds for the source into a process running code nobody
  here wrote, whose output is then read by the product.
- **Giving the sandbox network.** The sandbox's egress is denied by construction
  (`run_skill.Egress`), and the calls would then leave from a process the address rule, the pinned
  connection and the ceiling never see, which are the three things that make a call to a source
  safe to make at all.

**No runner on the install means the source is neither readable nor offered.** The runner is
handed in, never found: `brain.ops.custom_code_run.installed_runner` is the one place an install
says it has one, and `brain.ops.connectable.reads` says no for a custom-code reading when it does
not. The code is never run another way. See `A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ`.

**The sandbox's input is its argument list, and that bounds what can be interpreted.**
`SandboxSpec` carries argv and nothing else (`run_skill.MAX_ARGUMENTS` of
`run_skill.MAX_ARGUMENT_CHARS` each), so answers handed back for interpretation are bounded to
`MAX_INTERPRETED_CHARS` and a larger set is refused rather than cut. A connector whose answers
the field mapping can read needs no interpretation and has no such bound. Whether the contract
should carry a bounded input is a question for the coordinator, not a field added here.

Scope: domain logic. Nothing here runs a process, opens a connection or reads a key. Connectors
never bulk-sync: a reading built here keeps a minimal index and reads every value live.

Task ids: M11.1.5
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

from pydantic import ValidationError

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import SCHEMES_SENT_AS_THEY_ARE, KeyScheme, PageReply
from brain.connectors.projection import ProjectedRecord, ProjectedValue
from brain.connectors.rest import ID_TARGET, mapped_row, rows_at
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import (
    CustomTransport,
    FieldMapping,
    TransportError,
    is_source_path,
    normalise,
)
from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode
from brain.tools.run_skill import (
    MAX_ARGUMENT_CHARS,
    MAX_ARGUMENTS,
    Egress,
    SandboxSpec,
    ScriptLeash,
    ScriptRequest,
    build_environment,
)

# ------------------------------------------------------------------ written-down reasons
#: The rule this module exists to keep. Tested in both directions.
THE_KEY_NEVER_ENTERS_THE_SANDBOX: Final = (
    "A custom connector's code never holds the source's key. It plans calls and interprets "
    "answers in a sandbox with no network, and the host makes every call with the leased key, "
    "through the address rule, the pinned connection and the source's ceiling. Every spec handed "
    "to the runner is checked for the key first, and one carrying it is refused and not run, "
    "because code nobody here wrote is a reader whose output nobody audits before it is printed."
)

#: Why a custom-code source is not read, and not offered, without a runner.
A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ: Final = (
    "A custom connector's code runs only through the sandbox runner an install configures, and "
    "an install with none neither reads such a source nor offers it on the Connectors screen. "
    "The code is never run another way, because the sandbox is what makes running it safe."
)

#: Why the host checks a planned call's host against the declaration's allowlist.
A_PLANNED_CALL_GOES_ONLY_WHERE_THE_DECLARATION_SAYS: Final = (
    "The code plans calls and the host makes them, so the egress allowlist the declaration names "
    "is read by the host, before it calls anything on the code's behalf. A planned call to any "
    "other host is refused and nothing from the plan is called."
)

#: The first argument of a planning run and of an interpreting run.
PLAN: Final = "plan"
INTERPRET: Final = "interpret"

#: The most calls one planning run may ask the host to make for one entity.
MAX_PLANNED_CALLS: Final = 8

#: The most characters of answers an interpreting run can be handed, which is what its argument
#: list holds after the two words naming the run. See the module docstring.
MAX_INTERPRETED_CHARS: Final = (MAX_ARGUMENTS - 2) * MAX_ARGUMENT_CHARS

#: The longest record id handed to a planning run.
MAX_ID_CHARS: Final = 200

_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class PlannedMethod(enum.StrEnum):
    """What a planned call may be. A read either asks with a query or posts a question."""

    GET = "GET"
    POST = "POST"


class PlannedBody(enum.StrEnum):
    """The content types a planned call's body may be sent as. Closed: the host sets the header."""

    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    XML = "text/xml"


class CustomCodeError(TransportError):
    """Custom code planned or printed something this seam will not act on. Quotes none of it."""


class KeyInSandboxError(CustomCodeError):
    """A spec carried the key the host holds, so nothing was run. See
    `THE_KEY_NEVER_ENTERS_THE_SANDBOX`."""


@dataclass(frozen=True)
class PlannedCall:
    """One call the code asked the host to make. The host adds every header, the key among them."""

    method: PlannedMethod
    url: str
    body: bytes | None = field(default=None, repr=False)
    content_type: PlannedBody = PlannedBody.JSON


def assert_keyless(spec: SandboxSpec, secret: str) -> None:
    """Refuse a spec that carries `secret` anywhere a runner would hand to the code.

    Every string the spec holds is searched, the argument list joined as well as one by one,
    because answers handed back for interpretation are split across arguments and a key could
    straddle two. Searched raw and as JSON escapes it, because answers are handed over as JSON.
    An empty secret is a source that takes no key, and there is nothing to find.
    """
    if not secret.strip():
        return
    needles = {secret, json.dumps(secret)[1:-1]}
    haystacks = (
        spec.skill,
        spec.digest,
        spec.script,
        spec.reach_hash,
        "".join(spec.arguments),
        *spec.arguments,
        *spec.environment.keys(),
        *spec.environment.values(),
    )
    if any(needle in hay for needle in needles for hay in haystacks):
        raise KeyInSandboxError(THE_KEY_NEVER_ENTERS_THE_SANDBOX)


@dataclass(frozen=True)
class CustomEntity:
    """One entity custom code reads, and how the records it yields are mapped and indexed."""

    entity: str
    fields: tuple[FieldMapping, ...]
    index: tuple[str, ...]
    records_at: str = ""

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.entity):
            msg = f"custom reading entity {self.entity!r} is not a name"
            raise TransportError(msg)
        if not any(one.target == ID_TARGET for one in self.fields):
            msg = f"the mapping for {self.entity!r} names no {ID_TARGET!r} target"
            raise TransportError(msg)
        if self.records_at and not is_source_path(self.records_at):
            msg = f"records path {self.records_at!r} for {self.entity!r} is not a plain dotted path"
            raise TransportError(msg)
        unmapped = sorted(set(self.index) - {one.target for one in self.fields})
        if unmapped:
            msg = f"{self.entity!r} keeps {unmapped} in its index, which its mapping never reads"
            raise TransportError(msg)


@dataclass(frozen=True)
class CustomReading:
    """A source read through custom code in a sandbox, on a schedule and live (M11.1.5).

    Satisfies `brain.connectors.declaration.CodeReading` for the worker and `LiveLookup` for a
    question. `code_digest` is the SHA-256 of the module as it was reviewed, which the runner
    materialises by (`SandboxSpec.digest`), so the code that runs is the code somebody read.
    """

    connector: str
    transport: CustomTransport
    code_digest: str
    reads: tuple[CustomEntity, ...]
    interval: timedelta
    scheme: KeyScheme = KeyScheme.BEARER
    #: Whether the answers go back into the sandbox to be interpreted, rather than being read by
    #: the field mapping. Only where the connector needs it: see `MAX_INTERPRETED_CHARS`.
    interprets: bool = False
    leash: ScriptLeash = field(default_factory=ScriptLeash)

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.connector):
            msg = f"custom reading connector {self.connector!r} is not a name"
            raise TransportError(msg)
        if not _DIGEST_RE.match(self.code_digest):
            msg = (
                "a custom reading names no SHA-256 of its reviewed code, so the runner could run "
                "whatever sits under the module's name"
            )
            raise TransportError(msg)
        if not self.reads:
            msg = "a custom reading reads no entity"
            raise TransportError(msg)
        names = [one.entity for one in self.reads]
        if len(names) != len(set(names)):
            msg = "a custom reading reads one entity twice"
            raise TransportError(msg)
        if self.scheme not in SCHEMES_SENT_AS_THEY_ARE:
            msg = (
                f"a custom reading's key is sent as it is, and {self.scheme.value!r} is a key "
                "file exchanged for a token, which only a REST reading names a scope for"
            )
            raise TransportError(msg)
        if self.interval <= timedelta(0):
            msg = "a custom reading's interval must be longer than nothing"
            raise TransportError(msg)

    def _entity(self, entity: str) -> CustomEntity:
        for one in self.reads:
            if one.entity == entity:
                return one
        msg = f"this reading reads {[one.entity for one in self.reads]}, not {entity!r}"
        raise ConnectorContractError(msg)

    def _spec(self, arguments: tuple[str, ...]) -> SandboxSpec:
        """A spec for one run of the declared module, its arguments held to `ScriptRequest`'s.

        The bounds are `run_skill`'s own, applied by building the request it validates, so a
        connector's run and a skill's run are refused by one rule rather than two.
        """
        try:
            ScriptRequest(skill=self.connector, script=self.transport.module, arguments=arguments)
        except ValidationError:
            msg = "a run's arguments are outside the bounds a sandboxed run is held to"
            raise CustomCodeError(msg) from None
        return SandboxSpec(
            skill=self.connector,
            digest=self.code_digest,
            script=self.transport.module,
            arguments=arguments,
            environment=build_environment({}),
            leash=self.leash,
            network=Egress.DENIED,
        )

    # ------------------------------------------------------------- `CodeReading`
    def entities(self) -> tuple[str, ...]:
        return tuple(one.entity for one in self.reads)

    def refresh_interval(self) -> timedelta:
        return self.interval

    def key_scheme(self) -> KeyScheme:
        return self.scheme

    def plan_spec(
        self, entity: str, *, settings: Mapping[str, str], source_id: str | None
    ) -> SandboxSpec:
        self._entity(entity)
        if source_id is not None:
            _checked_id(source_id)
        pairs = tuple(f"{name}={value}" for name, value in sorted(settings.items()))
        return self._spec((PLAN, entity, source_id or "", *pairs))

    def planned(self, output: str) -> tuple[PlannedCall, ...]:
        try:
            printed = json.loads(output)
        except ValueError:
            msg = "a planning run printed something that is not JSON"
            raise CustomCodeError(msg) from None
        calls = printed.get("calls") if isinstance(printed, Mapping) else None
        if not isinstance(calls, list) or not calls or len(calls) > MAX_PLANNED_CALLS:
            msg = f"a planning run must print between one and {MAX_PLANNED_CALLS} calls"
            raise CustomCodeError(msg)
        return tuple(self._call(one) for one in calls)

    def _call(self, one: Any) -> PlannedCall:
        if not isinstance(one, Mapping) or not isinstance(one.get("url"), str):
            msg = "a planned call names no address"
            raise CustomCodeError(msg)
        try:
            method = PlannedMethod(one.get("method", "GET"))
            content_type = PlannedBody(one.get("content_type", PlannedBody.JSON.value))
        except ValueError:
            msg = "a planned call names a method or a body type this seam does not send"
            raise CustomCodeError(msg) from None
        body = one.get("body")
        if body is not None and (method is PlannedMethod.GET or not isinstance(body, str)):
            msg = "a planned call carries a body that is not text, or carries one on a GET"
            raise CustomCodeError(msg)
        host = (urlsplit(one["url"]).hostname or "").lower()
        if host not in {allowed.lower() for allowed in self.transport.egress_allowlist}:
            raise CustomCodeError(A_PLANNED_CALL_GOES_ONLY_WHERE_THE_DECLARATION_SAYS)
        return PlannedCall(
            method=method,
            url=one["url"],
            body=None if body is None else body.encode("utf-8"),
            content_type=content_type,
        )

    def interpret_spec(self, entity: str, answers: tuple[bytes, ...]) -> SandboxSpec | None:
        self._entity(entity)
        if not self.interprets:
            return None
        try:
            texts = [one.decode("utf-8") for one in answers]
        except UnicodeDecodeError:
            msg = "an answer to interpret was not UTF-8"
            raise CustomCodeError(msg) from None
        handed = json.dumps(texts, separators=(",", ":"), ensure_ascii=True)
        if len(handed) > MAX_INTERPRETED_CHARS:
            msg = (
                f"the answers are longer than the {MAX_INTERPRETED_CHARS} characters a sandboxed "
                "run's arguments hold, and are refused rather than cut"
            )
            raise CustomCodeError(msg)
        chunks = tuple(
            handed[start : start + MAX_ARGUMENT_CHARS]
            for start in range(0, len(handed), MAX_ARGUMENT_CHARS)
        )
        return self._spec((INTERPRET, entity, *chunks))

    def from_answers(self, entity: str, answers: tuple[Any, ...], *, fetched_at: str) -> PageReply:
        one = self._entity(entity)
        found: list[Mapping[str, Any]] = []
        for answer in answers:
            records = rows_at(answer, one.records_at)
            if records is None:
                msg = "an answer holds no records where the reading declares them"
                raise CustomCodeError(msg)
            found.extend(records)
        return self._page(one, tuple(found), fetched_at=fetched_at)

    def from_output(self, entity: str, output: str, *, fetched_at: str) -> PageReply:
        one = self._entity(entity)
        try:
            printed = json.loads(output)
        except ValueError:
            msg = "an interpreting run printed something that is not JSON"
            raise CustomCodeError(msg) from None
        records = rows_at(printed, one.records_at)
        if records is None:
            msg = "an interpreting run printed no records where the reading declares them"
            raise CustomCodeError(msg)
        return self._page(one, records, fetched_at=fetched_at)

    def _page(
        self, one: CustomEntity, records: tuple[Mapping[str, Any], ...], *, fetched_at: str
    ) -> PageReply:
        rows = tuple(mapped_row(row, one.fields) for row in records)
        return PageReply(
            call=CallOutcome.OK,
            rows=normalise(one.entity, rows, source=self.connector, fetched_at=fetched_at),
        )

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        one = self._entity(entity)
        kept: dict[str, ProjectedValue] = {
            name: row[name]
            for name in one.index
            if isinstance(row.get(name), str | int | float | bool)
        }
        return ProjectedRecord(
            source=self.connector,
            entity=entity,
            source_id=str(row[ID_TARGET]),
            last_seen_at=seen_at,
            fields=kept,
        )

    # ------------------------------------------------------------- `LiveLookup`
    def identity_mode(self, entity: str) -> IdentityMode:
        del entity
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        self._entity(entity)
        return {ID_TARGET: _checked_id(source_id)}

    def operation(self, entity: str, *, settings: Mapping[str, str], resolver: Any) -> None:
        """None: a record is read by a planned call, never by a REST operation."""
        del entity, settings, resolver


def _checked_id(source_id: str) -> str:
    if (
        not source_id.strip()
        or len(source_id) > MAX_ID_CHARS
        or any(character < " " or character == "\x7f" for character in source_id)
    ):
        msg = "a record id is not the shape a source issues"
        raise ConnectorContractError(msg)
    return source_id
