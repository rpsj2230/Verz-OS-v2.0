"""What the server's docker saw of the running automation canvas, kept for the release and judged.

`brain.ops.automation` says the canvas is treated as hostile and `docker-compose.automation.yml`
deploys that: its own internal network, an egress proxy that is its only way out, no credential to
the application. Tests hold the file to the policy. **What nothing held until now is the container
that is running**, and a compose file is an intention: an install may start the canvas from a copy
that differs, a variable may be added in a hurry, a network may be joined by hand. Whether the
running thing keeps the boundary is known to the server's docker and to nothing inside the
application, which cannot see another container's networks or environment.

**So the step asks, and the checks judge.** `ops/deploy/overlays/automation.observe.sh` runs on the
host after the canvas is up and hands this module's `keep` what docker said, as `kind|value` lines
on standard input; this module parses it, keeps it in one `ops.setting` row for the release
(`FACTS_KEY`), and `brain.ops.acceptance_checks_automation_canvas` reads it back through `facts_in`
and `gaps`. The split is `brain.ops.overlays`'s: the script gathers and decides nothing, and the
arithmetic that says a fact is wrong is Python that a test can break, which a shell loop is not.

**Names, never values.** The step cuts every environment variable's value off before anything
leaves the host, so `FactsError` has nothing to refuse and a row cannot carry a secret: a name is
`AP_JWT_SECRET`, which says the canvas has one and not what it is. A count of values that are
connection strings is a number the host computes with a pattern held equal to
`brain.ops.automation._CONNECTION_SCHEMES` by a test.

**What counts as a credential the canvas should not hold**, decided by `gaps` over names: any name
that carries a credential (`brain.ops.automation.is_credential_name`) other than the three secrets
the canvas is given for itself (`CANVAS_OWN_SECRETS`, held equal to the compose file's own by a
test), and any name that begins as the application's own variables do
(`APPLICATION_NAME_PREFIXES`), plus any value that is a connection string. Rejected: judging by
allowing only the names the compose file declares, which would fail a canvas on every variable its
base image sets and teach an owner to read the check as noise; and judging by the three secrets
alone, which would pass `DATABASE_URL`.

**An unknown is a gap, not a pass.** A route count the step could not read is reported `unknown`,
and `gaps` treats unknown as unproven, because zero default routes is exactly the answer the check
is hoping for and a fact that could not be read must not be able to look like it. The same holds
for a probe that got no answer.

**One row, for the release that wrote it.** `facts_in` returns nothing for a row written by another
commit, as `brain.ops.overlays.seen_in` does, so a canvas judged on what an older release saw is a
canvas not judged.

Task ids: M32.6.1.2
"""

from __future__ import annotations

import enum
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.ops.automation import EGRESS_ALLOWLIST, is_credential_name

#: The `ops.setting` row the step's report is kept in, rewritten on every deploy that starts the
#: canvas. The namespace is `overlay`, beside `brain.ops.overlays.OBSERVED_KEY`.
FACTS_KEY: Final = "overlay.automation"

#: Who wrote it, as `ops.setting.updated_by` and the audit trigger record it.
WRITER: Final = "deploy.automation_canvas"

DESCRIPTION: Final = (
    "What the deploy step saw of the automation canvas after starting it: the networks it and its "
    "proxy sit on, the names of the canvas's variables, its routes, the hostnames its proxy was "
    "started with and the proxy's answer for a host on no list, and the release it ran."
)

#: The tool network, which the compose file names whatever the project is called.
TOOL_API_NETWORK: Final = "brain-tool-api"

#: The suffixes of the two networks the project's own compose file makes: the internal one the
#: canvas and its proxy and its database share, and the one the proxy alone also sits on.
SANDBOX_NETWORK_SUFFIX: Final = "_automation"
PROXY_EXIT_NETWORK_SUFFIX: Final = "_egress"

#: The three secrets the canvas is given for itself, none of them the application's. Held equal to
#: the compose file's own `${AUTOMATION_...}` variables by a test.
CANVAS_OWN_SECRETS: Final[frozenset[str]] = frozenset(
    {"AP_POSTGRES_PASSWORD", "AP_ENCRYPTION_KEY", "AP_JWT_SECRET"}
)

#: How the application's own variables begin. A canvas holding one has been given something of the
#: application's, whatever it is called.
APPLICATION_NAME_PREFIXES: Final[tuple[str, ...]] = (
    "BRAIN_",
    "INSTALL_",
    "DATABASE_",
    "VAULT_",
    "OPENBAO_",
    "VALKEY_",
    "REDIS_",
)

#: What a proxy that refuses a host on no list answers on the first line of its reply.
REFUSED_STATUS: Final = 403

#: What the step writes when it could not read a fact.
UNKNOWN: Final = "unknown"

#: Why the report says unknown rather than a good answer.
AN_UNREAD_FACT_IS_NEVER_THE_GOOD_ANSWER: Final = (
    "A route count read from nothing is zero, and zero is the answer the check hopes for, so the "
    "step prints a count only when the routing table was read and says unknown otherwise, and an "
    "unknown is a gap here and never a pass."
)


class FactsError(Exception):
    """Raised for a report that is not `kind|value` lines, or a stored row that is not one."""


class Gap(enum.StrEnum):
    """Every way the running canvas can fail the boundary, each a thing a check says in one
    sentence and a log names."""

    #: A variable that carries a credential the canvas was not given for itself.
    FOREIGN_CREDENTIAL = "foreign_credential"
    #: A value that is a connection string, under any name.
    CONNECTION_STRING = "connection_string"
    #: A variable that begins as the application's own do.
    APPLICATION_VARIABLE = "application_variable"
    #: The canvas is on a network other than its own and the tool network, or on neither.
    CANVAS_NETWORKS = "canvas_networks"
    #: The proxy is on a network other than its two.
    PROXY_NETWORKS = "proxy_networks"
    #: The canvas has a default route, so it has a way out that is not the proxy.
    DEFAULT_ROUTE = "default_route"
    #: The route count could not be read.
    ROUTES_UNKNOWN = "routes_unknown"
    #: The hostnames the proxy was started with are not the policy's.
    ALLOWLIST = "allowlist"
    #: The proxy did not refuse a host on no list.
    NOT_REFUSED = "not_refused"


@dataclass(frozen=True)
class CanvasFacts:
    """What the host said of the running canvas. Names and counts, never a value."""

    networks: tuple[str, ...]
    proxy_networks: tuple[str, ...]
    env_names: tuple[str, ...]
    connection_strings: int | None
    default_routes: int | None
    allowlist: tuple[str, ...]
    probe: str

    def as_value(self) -> dict[str, object]:
        return {
            "networks": list(self.networks),
            "proxy_networks": list(self.proxy_networks),
            "env_names": list(self.env_names),
            "connection_strings": self.connection_strings,
            "default_routes": self.default_routes,
            "allowlist": list(self.allowlist),
            "probe": self.probe,
        }


def _count(raw: str) -> int | None:
    """A count the step printed, or None for `unknown` or anything that is not one."""
    return int(raw) if raw.isdigit() else None


def facts_from(lines: Iterable[str]) -> CanvasFacts:
    """The step's `kind|value` lines as facts. A line of another shape is a refusal.

    Names are checked to be names, so a report that somehow carried `NAME=value` is refused rather
    than kept: `FactsError` is the last place a value could be stopped.
    """
    networks: list[str] = []
    proxy_networks: list[str] = []
    names: list[str] = []
    allowlist: list[str] = []
    counts: dict[str, str] = {}
    probe = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        kind, separator, value = line.partition("|")
        if not separator:
            msg = f"a report line is not kind|value: {kind[:24]!r}"
            raise FactsError(msg)
        match kind:
            case "net":
                networks.append(value)
            case "proxynet":
                proxy_networks.append(value)
            case "env":
                if not value.replace("_", "a").isalnum():
                    msg = "an environment line holds more than a name"
                    raise FactsError(msg)
                names.append(value)
            case "allow":
                allowlist.append(value)
            case "connstr" | "routes":
                counts[kind] = value
            case "probe":
                probe = value
            case _:
                msg = f"a report line has a kind nothing reads: {kind[:24]!r}"
                raise FactsError(msg)
    return CanvasFacts(
        networks=tuple(sorted(networks)),
        proxy_networks=tuple(sorted(proxy_networks)),
        env_names=tuple(sorted(names)),
        connection_strings=_count(counts.get("connstr", UNKNOWN)),
        default_routes=_count(counts.get("routes", UNKNOWN)),
        allowlist=tuple(sorted(allowlist)),
        probe=probe,
    )


def observation(facts: CanvasFacts, *, commit: str) -> dict[str, object]:
    """The row's value: the release, then the facts."""
    return {"commit": commit, **facts.as_value()}


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        return None
    return tuple(value)


def facts_in(value: object, *, commit: str) -> CanvasFacts | None:
    """The facts a stored row holds, or None when it is not this release's or not the row's shape.

    Defensive, because the row is in a table somebody with a database prompt can write: a value of
    the wrong shape is no report rather than a reason to believe one.
    """
    if not isinstance(value, Mapping) or value.get("commit") != commit:
        return None
    networks = _strings(value.get("networks"))
    proxy = _strings(value.get("proxy_networks"))
    names = _strings(value.get("env_names"))
    allowed = _strings(value.get("allowlist"))
    probe = value.get("probe")
    if networks is None or proxy is None or names is None or allowed is None:
        return None
    if not isinstance(probe, str):
        return None

    def count(key: str) -> int | None:
        found = value.get(key)
        return found if isinstance(found, int) and not isinstance(found, bool) else None

    return CanvasFacts(
        networks=networks,
        proxy_networks=proxy,
        env_names=names,
        connection_strings=count("connection_strings"),
        default_routes=count("default_routes"),
        allowlist=allowed,
        probe=probe,
    )


def _allowed(network: str, suffixes: Sequence[str], exact: Sequence[str] = ()) -> bool:
    return network in exact or any(network.endswith(one) for one in suffixes)


def _status(probe: str) -> int | None:
    """The status code on the first line of a proxy's reply, as `HTTP/1.1 403 Forbidden`."""
    parts = probe.split()
    return (
        int(parts[1])
        if len(parts) >= 2 and parts[0].startswith("HTTP/") and parts[1].isdigit()
        else None
    )


def gaps(facts: CanvasFacts) -> tuple[Gap, ...]:
    """Every way the running canvas fails the boundary, in a fixed order, each named once.

    Pure, so every one is tested by breaking one fact. See
    `AN_UNREAD_FACT_IS_NEVER_THE_GOOD_ANSWER` for why an unknown count is a gap.
    """
    found: list[Gap] = []
    foreign = [
        name
        for name in facts.env_names
        if is_credential_name(name) and name not in CANVAS_OWN_SECRETS
    ]
    if foreign:
        found.append(Gap.FOREIGN_CREDENTIAL)
    if facts.connection_strings is None or facts.connection_strings > 0:
        found.append(Gap.CONNECTION_STRING)
    if any(name.startswith(APPLICATION_NAME_PREFIXES) for name in facts.env_names):
        found.append(Gap.APPLICATION_VARIABLE)
    own = (SANDBOX_NETWORK_SUFFIX,)
    # A canvas on no network at all has none of its own, which the second half of the condition
    # says, so emptiness is not tested twice.
    canvas_ok = all(_allowed(one, own, (TOOL_API_NETWORK,)) for one in facts.networks)
    if not canvas_ok or not any(one.endswith(SANDBOX_NETWORK_SUFFIX) for one in facts.networks):
        found.append(Gap.CANVAS_NETWORKS)
    proxy_ok = bool(facts.proxy_networks) and all(
        _allowed(one, (SANDBOX_NETWORK_SUFFIX, PROXY_EXIT_NETWORK_SUFFIX))
        for one in facts.proxy_networks
    )
    if not proxy_ok:
        found.append(Gap.PROXY_NETWORKS)
    if facts.default_routes is None:
        found.append(Gap.ROUTES_UNKNOWN)
    elif facts.default_routes > 0:
        found.append(Gap.DEFAULT_ROUTE)
    if sorted(facts.allowlist) != sorted(EGRESS_ALLOWLIST):
        found.append(Gap.ALLOWLIST)
    if _status(facts.probe) != REFUSED_STATUS:
        found.append(Gap.NOT_REFUSED)
    return tuple(found)


def foreign_credential_names(facts: CanvasFacts) -> tuple[str, ...]:
    """The names behind a `FOREIGN_CREDENTIAL` or `APPLICATION_VARIABLE` gap, for a log line.

    A name is not a secret: it says a variable exists and not what it holds. It is what an owner
    needs to find the line to remove, and a check's reason is a literal that cannot carry it.
    """
    return tuple(
        name
        for name in facts.env_names
        if (is_credential_name(name) and name not in CANVAS_OWN_SECRETS)
        or name.startswith(APPLICATION_NAME_PREFIXES)
    )


# ------------------------------------------------------------------------------- the hand
def _keep(value: dict[str, object]) -> None:
    """Write the observation over a connection of its own, attributed to the deploy step."""
    from sqlalchemy import create_engine

    from brain.db import normalise_database_url
    from brain.ops.setting_store import put_statement
    from brain.settings import Settings
    from brain.tables.audit import attributed_to
    from brain.tables.config import SettingType

    url = Settings().owner_database_url()
    if not url:
        msg = "neither BRAIN_MIGRATION_DATABASE_URL nor DATABASE_URL is set, so nothing is kept"
        raise FactsError(msg)
    engine = create_engine(normalise_database_url(url))
    try:
        with engine.begin() as conn:
            for statement in attributed_to(
                actor_id=WRITER, ent_hash="0" * 32, trace_id=f"automation-canvas-{value['commit']}"
            ):
                conn.execute(statement)
            conn.execute(
                put_statement(
                    FACTS_KEY,
                    value_type=SettingType.JSON,
                    value=value,
                    description=DESCRIPTION,
                    updated_by=WRITER,
                )
            )
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """`keep`, with the step's lines on standard input: what the deploy step runs in the app.

    Prints `SAY` lines the step relays and exits non-zero, saying why, when the report cannot be
    read or kept. A report that cannot be kept is a canvas whose checks are not run, never one that
    passes.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["keep"]:
        print("usage: python -m brain.ops.automation_report keep < facts", file=sys.stderr)
        return 64
    try:
        from brain.settings import Settings

        facts = facts_from(sys.stdin)
        _keep(observation(facts, commit=Settings().resolved_commit()))
    except Exception as error:
        from brain.ops.safe_error import describe

        print(f"SAY the canvas's facts were not kept: {describe(error)}")
        return 1
    print("SAY the canvas's facts are kept for this release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
