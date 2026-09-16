"""The streaming replica's configuration, held to the primary it copies and the disk it could fill.

`brain.console.read_replica` decides when a console page may be read from a replica and
`brain.ops.replica_store` measures one, and until `docker-compose.replica.yml` nothing in this
repository created one: `docs/install/operations.md` told the reader that setting up streaming
replication was their database administrator's job. This module is the checks over that overlay,
and each is a way a replica is either refused by PostgreSQL or harms the primary.

**The replica runs the primary's image, exactly.** Physical replication replays the primary's
WAL byte for byte, so the major version must match, and a standby reads rows whose types come
from the primary's extensions, so the extension libraries must be present too. A different tag
is a standby that refuses to start or a page that fails on the first vector column. See
`A_STANDBY_REPLAYS_THE_PRIMARY_AND_NEEDS_ITS_BINARIES`.

**The replica admits at least as many connections as the primary.** A hot standby checks
`max_connections` against the value recorded in the WAL and refuses to start when its own is
lower, and the reason it gives names a parameter rather than the compose file somebody tuned
down to save memory. `connection_floor_gaps` reads both commands.

**The slot has a ceiling, and that is the check this module exists for.** A physical slot keeps
every WAL segment its replica has not confirmed. Without a slot a replica that falls behind the
primary's own WAL retention has to be copied again; with a slot and no ceiling, a replica that
stops fills the primary's disk and the primary stops taking writes, which is an outage of the
system to protect a copy of it. `max_slot_wal_keep_size` is the ceiling: past it the slot is
invalidated and the replica has to be copied again, and the console notices first because the
replica stops being caught up and pages are read from the primary. See
`A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK`.

The ceiling is `WAL_KEPT_FOR_A_STOPPED_REPLICA`, twice PostgreSQL's default `max_wal_size`: a
stopped replica may cost the primary as much WAL again as a checkpoint cycle already keeps.
That figure is a judgement rather than a derivation, and it is the one number here an install
with a small disk should lower.

**The setup service mounts the primary's data volume and writes one line to one file.** A
replication connection needs a `replication` rule in `pg_hba.conf`, which SQL cannot write.
The alternatives were a configuration file bind-mounted over the primary's, which a stored
compose resolves to an empty directory and which would replace the image's own rules; and
`COPY ... TO` the rules file from SQL, which overwrites the whole file from a query. Appending
one rule when it is missing, and reloading, is the smallest write that works.
`setup_write_gaps` holds the command to exactly that. See
`THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE`.

What is not budgeted: the application reaches the replica with the same unpooled engine it uses
for PgBouncer, so the replica's connections are bounded by console traffic rather than by a
declared figure, and `brain.ops.connections` has no row for it. The replica's own
`max_connections` is the only ceiling.

What has not happened: no replica has been started from this overlay. The standby behaviour
above is PostgreSQL's documented behaviour, and the rehearsal is written in
`docs/install/scaling.md`.

Task ids: M36.1.2.1
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from brain.ops.compose import ComposeDoc

#: The overlay, by the name an operator passes with `-f`.
OVERLAY: Final = "docker-compose.replica.yml"

#: The primary, as the base files name it.
PRIMARY: Final = "db"

#: The one-shot that prepares the primary, and the standby itself.
SETUP_SERVICE: Final = "db-replication-setup"
REPLICA_SERVICE: Final = "db-replica"

#: The replication login and the slot, which the setup creates and the copy names.
REPLICATION_ROLE: Final = "brain_replicator"
SLOT: Final = "brain_replica"

#: The variable holding the replication login's password, required on both services.
REPLICATION_LOGIN_VARIABLE: Final = "BRAIN_REPLICATION_PASSWORD"

#: What the primary may keep for a replica that has stopped confirming, as PostgreSQL spells it.
WAL_KEPT_FOR_A_STOPPED_REPLICA: Final = "2GB"

#: Where the application is told the replica is.
REPLICA_URL_SETTING: Final = "BRAIN_READ_REPLICA_URL"

A_STANDBY_REPLAYS_THE_PRIMARY_AND_NEEDS_ITS_BINARIES: Final = (
    "A physical standby replays the primary's WAL as written, which needs the same major "
    "version, and reads rows whose types come from the primary's extensions, which need the "
    "same libraries. Any image other than the primary's is a standby that refuses to start or a "
    "read that fails on the first column of an extension type."
)

A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK: Final = (
    "A replication slot keeps every WAL segment its replica has not confirmed. A replica that "
    "stops while its slot remains makes the primary keep WAL until its disk is full, and a full "
    "disk stops the primary taking writes: an outage of the system in order to protect a copy "
    "of it. max_slot_wal_keep_size gives up the slot first, and a replica that has to be copied "
    "again is the cheaper failure."
)

THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE: Final = (
    "The setup service mounts the primary's data directory because pg_hba.conf lives there and "
    "SQL cannot append to it. A container holding that mount can destroy the database, so its "
    "command may redirect output only by appending, only to the rules file the server names, "
    "and may remove or move nothing."
)

_CONNECTIONS: Final = re.compile(r"-c\s+max_connections=(\d+)")
_REQUIRED: Final = re.compile(r"\A\$\{" + REPLICATION_LOGIN_VARIABLE + r":\?[^}]+\}\Z")
#: A shell redirect: `>`, `>>`, or a descriptor before either, with its target.
_REDIRECT: Final = re.compile(r"(?<![<>&])(\d?>>?)\s*(\"[^\"]*\"|\S+)")
_DESTRUCTIVE: Final = re.compile(r"(?:^|[\s;|&(])(rm|mv|truncate|dd|shred|find)\s")


def _services(document: ComposeDoc) -> dict[str, Mapping[str, Any]]:
    block = document.get("services") or {}
    return {str(name): body for name, body in block.items() if isinstance(body, Mapping)}


def _command(body: Mapping[str, Any]) -> str:
    command = body.get("command") or ""
    if isinstance(command, str):
        return command
    return "\n".join(str(one) for one in command)


def _environment(body: Mapping[str, Any]) -> dict[str, str]:
    environment = body.get("environment") or {}
    if isinstance(environment, Mapping):
        return {str(key): str(value) for key, value in environment.items()}
    found: dict[str, str] = {}
    for entry in environment:
        key, _, value = str(entry).partition("=")
        found[key] = value
    return found


def connection_floor_gaps(base: ComposeDoc, overlay: ComposeDoc) -> tuple[str, ...]:
    """The standby admits fewer connections than the primary, which PostgreSQL refuses."""
    primary = _CONNECTIONS.search(_command(_services(base).get(PRIMARY, {})))
    replica = _CONNECTIONS.search(_command(_services(overlay).get(REPLICA_SERVICE, {})))
    if primary is None or replica is None:
        return (
            f"max_connections is not set on both {PRIMARY!r} and {REPLICA_SERVICE!r}, so "
            "whether the standby may start cannot be read off the files",
        )
    if int(replica.group(1)) < int(primary.group(1)):
        return (
            f"{REPLICA_SERVICE!r} admits {replica.group(1)} connections and {PRIMARY!r} "
            f"admits {primary.group(1)}; a hot standby with fewer than its primary refuses to "
            "start",
        )
    return ()


def setup_write_gaps(overlay: ComposeDoc) -> tuple[str, ...]:
    """Anything the setup command writes to the primary's volume beyond one appended rule."""
    command = _command(_services(overlay).get(SETUP_SERVICE, {}))
    findings: list[str] = []
    redirects = _REDIRECT.findall(command)
    if [operator for operator, _ in redirects] != [">>"]:
        findings.append(
            f"{SETUP_SERVICE!r} redirects {redirects}; it may append once and nothing else. "
            f"{THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE}"
        )
    elif redirects[0][1] not in ('"$$hba"', '"$hba"'):
        findings.append(
            f"{SETUP_SERVICE!r} appends to {redirects[0][1]} rather than the rules file the "
            "server names"
        )
    if "SHOW hba_file" not in command:
        findings.append(
            f"{SETUP_SERVICE!r} does not ask the server where its rules file is, so the path it "
            "writes to is a guess about the image's layout"
        )
    destructive = sorted(set(_DESTRUCTIVE.findall(command)))
    if destructive:
        findings.append(
            f"{SETUP_SERVICE!r} runs {destructive} with the primary's data directory mounted. "
            f"{THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE}"
        )
    return tuple(findings)


def replica_overlay_gaps(base: ComposeDoc, overlay: ComposeDoc) -> tuple[str, ...]:
    """Every way this overlay would give a replica that PostgreSQL refuses or that harms `db`.

    `base` is the file that describes the primary, which is `docker-compose.yml` or
    `docker-compose.lite.yml`; they describe the same service.
    """
    services = _services(overlay)
    primary = _services(base).get(PRIMARY)
    setup = services.get(SETUP_SERVICE)
    replica = services.get(REPLICA_SERVICE)
    if primary is None or setup is None or replica is None:
        missing = [
            name
            for name, body in (
                (PRIMARY, primary),
                (SETUP_SERVICE, setup),
                (REPLICA_SERVICE, replica),
            )
            if body is None
        ]
        return (f"no {missing} to check, so there is no replica configuration here",)

    findings: list[str] = []
    for name, body in ((SETUP_SERVICE, setup), (REPLICA_SERVICE, replica)):
        if body.get("image") != primary.get("image"):
            findings.append(
                f"{name!r} runs {body.get('image')!r} and {PRIMARY!r} runs "
                f"{primary.get('image')!r}. {A_STANDBY_REPLAYS_THE_PRIMARY_AND_NEEDS_ITS_BINARIES}"
            )
        if body.get("ports"):
            findings.append(f"{name!r} publishes {body.get('ports')}; nothing here is published")

    findings.extend(connection_floor_gaps(base, overlay))

    setup_command = _command(setup)
    if f"pg_create_physical_replication_slot('{SLOT}')" in setup_command:
        ceiling = re.search(r"max_slot_wal_keep_size\s*=\s*'([^']+)'", setup_command)
        if ceiling is None or ceiling.group(1) != WAL_KEPT_FOR_A_STOPPED_REPLICA:
            found = "no" if ceiling is None else repr(ceiling.group(1))
            findings.append(
                f"{SETUP_SERVICE!r} creates slot {SLOT!r} with {found} max_slot_wal_keep_size "
                f"against {WAL_KEPT_FOR_A_STOPPED_REPLICA!r}. "
                f"{A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK}"
            )
    if f"--slot={SLOT}" not in _command(replica):
        findings.append(
            f"{REPLICA_SERVICE!r} does not copy through slot {SLOT!r}, so the slot the setup "
            "creates keeps WAL for nobody"
        )
    if f"--username={REPLICATION_ROLE}" not in _command(replica):
        findings.append(f"{REPLICA_SERVICE!r} does not copy as {REPLICATION_ROLE!r}")

    primary_mounts = {str(one).split(":", 1)[1] for one in primary.get("volumes") or ()}
    for entry in setup.get("volumes") or ():
        source, _, target = str(entry).partition(":")
        if target.split(":", 1)[0] not in primary_mounts:
            findings.append(
                f"{SETUP_SERVICE!r} mounts {source!r} at {target!r}, which is not where "
                f"{PRIMARY!r} mounts it, so the rules file the server names is not at that path"
            )
    findings.extend(setup_write_gaps(overlay))

    for name, body in ((SETUP_SERVICE, setup), (REPLICA_SERVICE, replica)):
        environment = _environment(body)
        value = environment.get(
            REPLICATION_LOGIN_VARIABLE if name == SETUP_SERVICE else "PGPASSWORD", ""
        )
        if not _REQUIRED.match(value):
            findings.append(
                f"{name!r} takes the replication password as {value!r}; it has to be "
                f"${{{REPLICATION_LOGIN_VARIABLE}:?...}} so an unset password refuses to start"
            )

    dependency = (replica.get("depends_on") or {}).get(SETUP_SERVICE) or {}
    if dependency.get("condition") != "service_completed_successfully":
        findings.append(
            f"{REPLICA_SERVICE!r} does not wait for {SETUP_SERVICE!r} to succeed, so the first "
            "copy races the replication login it needs"
        )

    url = _environment(services.get("app", {})).get(REPLICA_URL_SETTING, "")
    host = urlsplit(url).hostname if url else None
    if host != REPLICA_SERVICE:
        findings.append(
            f"the application's {REPLICA_URL_SETTING} reaches {host!r}, not {REPLICA_SERVICE!r}"
        )
    return tuple(findings)
