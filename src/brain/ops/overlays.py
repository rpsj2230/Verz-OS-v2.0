"""The optional services an install switches on beside its profile, and what a release starts.

A profile is the product's answer to "what does this kind of install run", and
`brain.ops.wiring.components_for` is the only answer to it. That answer stopped describing the
owner's install the moment memory, rather than the kind of install, became the question: on
2026-10-05 item 120 gave the room freed on that server to the personal data detector and the
trace ledger and told the model server to wait. Both of the first two are `standard` or `full`
components and the model server is `standard` too, so no profile is the set item 120 decided,
and switching the profile would have made the product believe a model server runs that does
not. **So an install names the optional services it runs, one by one, in `INSTALL_SERVICES`**,
and each name is an `Overlay`: a set of components `brain.ops.wiring` already costs and the
compose files that already describe them.

**A release starts them, and nobody edits the server.** Coolify runs its own copy of the
compose file (`docs/install/coolify.md`), so a service added to the product never reaches a
Coolify install unless somebody pastes it into that copy, which is a hand edit of one server
that the next release does not know about. `ops/deploy/overlays/apply.sh` is in the image, and
the server's deploy hook copies it out and runs it after the application is ready, the way it
already applies the release's vault policies. It starts the switched-on services as a compose
project of their own beside the application's, on the image's own copies of the product's
compose files, and joins the application's containers to the networks those files declare.
Rejected: a profile change on the server (a variable in Coolify's copy, which is the hand edit
again, and the model server with it); and pasting the overlay into Coolify's copy once (true on
one server, and absent from the next company's).

**Whether a service fits is measured on the server at the moment it would start, and decided
here.** The script reads the machine's memory, every running container's limit and what every
container without a limit is using, and hands those facts to `plan`, which costs each
switched-on overlay from `brain.ops.wiring` against what is left. The script decides nothing;
this module decides and the script does what the plan says. That is the split
`brain.ops.limits` and `brain.ops.limit_store` make, for the same reason: arithmetic that
starts or refuses a container on somebody's server is arithmetic that has to be tested at the
boundary, and a shell loop cannot be. `HOST_TOTAL_MIB` and `NEIGHBOUR_MIB` in `wiring` are one
machine's record; this reads whatever machine it is on, which is why it is right on a server
belonging to a company nobody here has met.

**A container with no limit is counted at what it uses plus room to grow, never at nought.**
See `AN_UNLIMITED_NEIGHBOUR_IS_COUNTED_AT_WHAT_IT_USES` and the 2026-10-05 measurement in
`wiring.NEIGHBOUR_MIB`, where it was 1,389 MiB across eight containers that reserve nothing.

**An overlay that does not fit is refused in words, and the ones before it still start.**
Overlays are costed in declaration order, which is the order item 120 gave the room in, so a
refusal names exactly the one that did not fit and what it would have needed. A plan the
application cannot make (no database, a setting nobody declared) starts nothing and stops
nothing: the script leaves running services as they are, because a planner that fails into
"switch everything off" takes the detector away on the day the database restarts.

Task ids: M32.2.1.1
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.install import value_of
from brain.ops.wiring import HOST_RESERVE_MIB, WiringError, component, set_cost_mib

#: The installation setting that names the optional services. See `brain.install.INSTALLATION`.
SERVICES_SETTING: Final = "INSTALL_SERVICES"

#: The value meaning no optional service runs, and the setting's declared default.
NO_SERVICES: Final = "none"

#: Why a container without a limit is counted at what it uses and not at what it reserves.
AN_UNLIMITED_NEIGHBOUR_IS_COUNTED_AT_WHAT_IT_USES: Final = (
    "A limit is memory the kernel will hand to that container when it asks, so a container with "
    "one is counted at its limit. A container without one reserves nothing and can take "
    "anything, and counting it at nought hands this install the memory it is using now. So it is "
    "counted at what it uses, plus a tenth for it to grow, which is the margin the 2026-10-05 "
    "measurement on the owner's server left; a neighbour that grows past that is a reason to "
    "measure again, not to start a container on a guess."
)

#: The room an unlimited container is given to grow, as a fraction of what it uses.
UNLIMITED_GROWTH: Final = 0.1

#: Why a plan that cannot be made changes nothing on the server.
A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING: Final = (
    "The script stops an overlay that is no longer switched on, so a planner that answered "
    "'nothing' whenever it could not read the setting would take the personal data detector "
    "away on the day the database was restarting. A plan that cannot be made exits non-zero, "
    "and the script then leaves every running service as it is."
)


class OverlayError(Exception):
    """A setting names a service nobody declared, or the server's facts cannot be read."""


@dataclass(frozen=True)
class Overlay:
    """One optional service as an install names it, what it costs, and how it is started.

    `components` are names `brain.ops.wiring` costs, so an overlay cannot be cheaper than the
    budget says; `files` are the product's own compose files for it, read from the image; and
    `joins` names, for each network those files declare, the application's services that must
    be on it to reach the overlay by name.
    """

    name: str
    what: str
    components: tuple[str, ...]
    files: tuple[str, ...]
    joins: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", self.name):
            msg = f"{self.name!r} is not a name an administrator can type into a setting"
            raise OverlayError(msg)
        if not self.components or not self.files:
            msg = f"overlay {self.name!r} starts nothing, so switching it on would change nothing"
            raise OverlayError(msg)
        for one in self.components:
            try:
                component(one)
            except WiringError as error:
                msg = f"overlay {self.name!r} names a container nobody budgeted: {error}"
                raise OverlayError(msg) from error

    @property
    def cost_mib(self) -> int:
        """What this overlay's containers may hold, from the budget rather than from a file."""
        return set_cost_mib(self.components)


#: Every optional service, in the order the room is given to them. Item 120 gave it to the
#: personal data detector first.
OVERLAYS: Final[tuple[Overlay, ...]] = (
    Overlay(
        name="presidio",
        what="the personal data detector",
        components=("presidio-analyzer",),
        files=("docker-compose.presidio.yml",),
        # The detector's one network is internal, so the application and the worker are joined
        # to it rather than the detector being joined to anything with a route off the host.
        joins=(("pii", ("app", "brain-worker")),),
    ),
)

BY_NAME: Final[Mapping[str, Overlay]] = {one.name: one for one in OVERLAYS}


def switched_on(value: str) -> tuple[Overlay, ...]:
    """The overlays a setting's value names, in declaration order, or a refusal.

    Refuses rather than skipping a name it does not know: a typo that started nothing would
    read on the server as a service that failed to start, and in the setting as one that runs.
    """
    names = [one.strip() for one in value.split(",") if one.strip()]
    if names == [NO_SERVICES]:
        return ()
    unknown = sorted(set(names) - set(BY_NAME))
    if unknown or not names:
        msg = (
            f"{SERVICES_SETTING} names {', '.join(unknown) or 'nothing'}, which is not one of "
            f"{', '.join(BY_NAME)} or {NO_SERVICES}"
        )
        raise OverlayError(msg)
    return tuple(one for one in OVERLAYS if one.name in names)


def services_problem(value: str) -> str:
    """What is wrong with a value typed on the Settings screen, or empty when it may be saved."""
    try:
        switched_on(value)
    except OverlayError:
        choices = ", ".join(f"{one.name} for {one.what}" for one in OVERLAYS)
        return f"Write {NO_SERVICES}, or one or more of these separated by commas: {choices}."
    return ""


def switched_on_here(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> tuple[Overlay, ...]:
    """The overlays this install has switched on, read through the one installation reader."""
    return switched_on(value_of(SERVICES_SETTING, env=env, saved=saved))


def components_switched_on(overlays: Iterable[Overlay]) -> frozenset[str]:
    """Every container the switched-on overlays run, for a reader asking whether one deploys."""
    return frozenset(name for one in overlays for name in one.components)


# ---------------------------------------------------------------- what the server holds
@dataclass(frozen=True)
class Host:
    """The server as the script measured it, in mebibytes."""

    total_mib: int
    #: The limits of every running container outside the overlays' own project.
    reserved_mib: int
    #: What every running container without a limit is using, outside that project.
    unlimited_used_mib: int

    @property
    def unlimited_floor_mib(self) -> int:
        """What the unlimited containers use, with room to grow.

        See `AN_UNLIMITED_NEIGHBOUR_IS_COUNTED_AT_WHAT_IT_USES`.
        """
        return math.ceil(self.unlimited_used_mib * (1 + UNLIMITED_GROWTH))

    @property
    def available_mib(self) -> int:
        """What the overlays may hold together, after everything else and the host's own reserve."""
        return self.total_mib - self.reserved_mib - self.unlimited_floor_mib - HOST_RESERVE_MIB


_UNITS: Final[Mapping[str, float]] = {
    "B": 1 / (1024 * 1024),
    "KIB": 1 / 1024,
    "KB": 1 / 1024,
    "MIB": 1.0,
    "MB": 1.0,
    "GIB": 1024.0,
    "GB": 1024.0,
    "TIB": 1024.0 * 1024.0,
}
_AMOUNT: Final = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*$")


def mebibytes(amount: str) -> float:
    """`880.3MiB` as docker stats writes it, in mebibytes."""
    found = _AMOUNT.match(amount)
    if found is None or found.group(2).upper() not in _UNITS:
        msg = f"{amount!r} is not an amount of memory docker writes"
        raise OverlayError(msg)
    return float(found.group(1)) * _UNITS[found.group(2).upper()]


def read_host(facts: Iterable[str], *, project: str) -> Host:
    """The server, from the three sections the script writes: meminfo, inspect and stats.

    `inspect` lines are `name|compose project|limit in bytes`, and `stats` lines are
    `name|used / limit`. A container in `project`, the overlays' own, is left out of both
    sums: those are the services this plan is about to cost from the budget, and counting
    their current limits as well would make a running overlay pay for itself twice.
    """
    section = ""
    total_kib = 0
    limits: dict[str, int] = {}
    projects: dict[str, str] = {}
    used: dict[str, float] = {}
    for raw in facts:
        line = raw.rstrip("\n")
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.strip():
            continue
        if section == "meminfo" and line.startswith("MemTotal:"):
            total_kib = int(line.split()[1])
        elif section == "inspect":
            name, owner, limit = line.rsplit("|", 2)
            name = name.lstrip("/")
            projects[name] = owner
            limits[name] = int(limit)
        elif section == "stats":
            name, usage = line.split("|", 1)
            used[name.lstrip("/")] = mebibytes(usage.split("/", 1)[0])
    if total_kib <= 0:
        msg = "the server's facts carry no MemTotal line, so nothing here can be costed"
        raise OverlayError(msg)
    others = [name for name in limits if projects.get(name) != project]
    reserved = sum(limits[name] for name in others) // (1024 * 1024)
    unlimited = sum(used.get(name, 0.0) for name in others if limits[name] == 0)
    return Host(
        total_mib=total_kib // 1024,
        reserved_mib=reserved,
        unlimited_used_mib=math.ceil(unlimited),
    )


# ---------------------------------------------------------------- the plan
@dataclass(frozen=True)
class Plan:
    """What the script starts, what it refuses and why, and the room it was decided against."""

    start: tuple[Overlay, ...]
    refused: tuple[tuple[Overlay, str], ...]
    available_mib: int


def plan(switched: Sequence[Overlay], host: Host) -> Plan:
    """Each switched-on overlay started while it fits, in declaration order, or refused in words."""
    remaining = host.available_mib
    start: list[Overlay] = []
    refused: list[tuple[Overlay, str]] = []
    for one in switched:
        if one.cost_mib <= remaining:
            start.append(one)
            remaining -= one.cost_mib
            continue
        refused.append(
            (
                one,
                f"{one.what} ({one.name}) needs {one.cost_mib} MiB and this server has "
                f"{max(remaining, 0)} MiB left for it, so it is not started",
            )
        )
    return Plan(start=tuple(start), refused=tuple(refused), available_mib=host.available_mib)


def render(planned: Plan, host: Host) -> str:
    """The plan as the script reads it: FILE, JOIN and SAY lines, one fact per line."""
    lines = [
        f"SAY this server has {host.total_mib} MiB; other containers reserve "
        f"{host.reserved_mib} and those without a limit use {host.unlimited_used_mib} "
        f"(counted at {host.unlimited_floor_mib}); {planned.available_mib} MiB is left for "
        "optional services",
    ]
    for one in planned.start:
        lines.append(f"SAY starting {one.what} ({one.name}) at {one.cost_mib} MiB")
        lines.extend(f"FILE {name}" for name in one.files)
        lines.extend(f"JOIN {network} {' '.join(services)}" for network, services in one.joins)
    lines.extend(f"SAY {reason}" for _, reason in planned.refused)
    if not planned.start:
        lines.append("SAY no optional service is started on this server")
    return "\n".join(lines) + "\n"


def _saved_from_database() -> Mapping[str, str]:
    """The installation values this install has saved, read once over a connection of its own."""
    from sqlalchemy import create_engine

    from brain.db import normalise_database_url
    from brain.ops.install_settings import saved_query, values_from
    from brain.settings import Settings

    url = Settings().owner_database_url()
    if not url:
        msg = "neither BRAIN_MIGRATION_DATABASE_URL nor DATABASE_URL is set, so no setting is read"
        raise OverlayError(msg)
    engine = create_engine(normalise_database_url(url))
    try:
        with engine.connect() as conn:
            return values_from(conn.execute(saved_query()).all())
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """`plan --project NAME`, with the server's facts on standard input.

    Any failure to read the facts or the setting is a plan that cannot be made, which exits 1 and
    says why. See `A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING`.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3 or args[0] != "plan" or args[1] != "--project" or not args[2]:
        print("usage: python -m brain.ops.overlays plan --project NAME < facts", file=sys.stderr)
        return 64
    try:
        host = read_host(sys.stdin, project=args[2])
        switched = switched_on_here(saved=_saved_from_database())
    except Exception as error:
        from brain.ops.safe_error import describe

        print(f"SAY no plan was made, so nothing is started or stopped: {describe(error)}")
        return 1
    sys.stdout.write(render(plan(switched, host), host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
