"""The nightly copy and the drill that reads it back, run as shell scripts against stand-ins.

Both scripts run on a client's server beside docker, and no test here has a docker. So `docker`
and `aws` are replaced on the PATH by two small shell scripts that record every call and answer
the way the real commands do for the calls these scripts make, including refusing a flag plain
`docker exec` does not have. Every assertion is about what a script did: its exit status, the
argument vectors the stand-ins recorded, the statements it fed a database session, and the
manifest it uploaded. None is about the scripts' own text, which a comment could supply.

**The drill is tested against the manifest the taker actually wrote.** A module fixture runs
`brain-backup` once and every drill test loads that copy and that manifest. A drill tested
against a manifest written by hand here would be tested against the author's idea of the format,
which is the producer and consumer split CLAUDE.md warns about: one test for each side is two
tests for the consumer unless the producer's output is what the consumer reads.

**The refusal to load into the live database is the decision that loses data**, so it is held
from three directions: by name before docker is asked anything, by the identifier docker reports
so an alias is caught, and by the database name. The positive test beside them proves a scratch
target is still loaded and that nothing is ever executed in the live container.

What cannot be held here is whether the SQL is right against PostgreSQL. That is a real run, and
the drill page records whether one has happened.

Task ids: M42.3.5
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from brain.ops.backup_manifest import backup_from

REPO = Path(__file__).resolve().parents[2]
TAKER = REPO / "ops" / "backup" / "brain-backup"
DRILL = REPO / "ops" / "backup" / "brain-restore-drill"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="no POSIX shell here to run the scripts with")

LIVE = "db-live"
LIVE_ID = "a" * 64
LIVE_DB = "brain"
SCRATCH = "brain-drill-db"
SCRATCH_ID = "b" * 64
SCRATCH_DB = "brain_drill"
DRILL_NETWORK = "brain-drill"

#: The counts the live database answers with, and so the counts a faithful load gives back.
COUNTS: dict[str, int] = {"know.item": 42, "obs.audit_event": 1200, "public.alembic_version": 1}
HEAD = "0051"
SNAPSHOT = "00000003-0000001B-1"

#: The first and last statements of the taker's counting session.
READ_ONLY_BEGIN = "begin transaction isolation level repeatable read, read only;"

#: Every `docker exec` option the real command accepts, from its reference page.
DOCKER_EXEC_FLAGS = frozenset(
    {"-d", "--detach", "--detach-keys", "-e", "--env", "--env-file", "-i", "--interactive"}
    | {"--privileged", "-t", "--tty", "-u", "--user", "-w", "--workdir"}
)

FAKE_DOCKER = r"""#!/bin/sh
# docker, as far as brain-backup and brain-restore-drill use it. Records every call.
us="$(printf '\037')"
record=""
for arg in "$@"; do record="$record$arg$us"; done
printf '%s\036\n' "$record" >> "$FAKE_DIR/docker.log"

case "$1" in
container)
    [ "$2" = inspect ] && [ "$3" = --format ] || exit 1
    case "$4" in
        *.Id*)
            if [ ! -f "$FAKE_DIR/ids/$5" ]; then
                printf 'Error: No such container: %s\n' "$5" >&2
                exit 1
            fi
            cat "$FAKE_DIR/ids/$5" ;;
        *Networks*)
            [ -f "$FAKE_DIR/networks/$5" ] || exit 1
            cat "$FAKE_DIR/networks/$5" ;;
        *) exit 1 ;;
    esac ;;
network)
    [ "$2" = inspect ] && [ "$3" = --format ] || exit 1
    [ -f "$FAKE_DIR/internal/$5" ] || { printf 'Error: No such network: %s\n' "$5" >&2; exit 1; }
    cat "$FAKE_DIR/internal/$5" ;;
exec)
    shift
    interactive=no
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -i|--interactive) interactive=yes; shift ;;
            -t|--tty|-d|--detach|--privileged) shift ;;
            -e|--env|-u|--user|-w|--workdir|--env-file|--detach-keys) shift 2 ;;
            -*) printf 'unknown shorthand flag: %s\n' "$1" >&2; exit 125 ;;
            *) break ;;
        esac
    done
    container="$1"
    program="$2"
    shift 2
    if [ ! -f "$FAKE_DIR/counts/$container" ]; then
        printf 'Error: No such container: %s\n' "$container" >&2
        exit 1
    fi
    case "$program" in
    psql)
        if [ "$interactive" = yes ]; then
            while IFS= read -r line; do
                printf '%s\n' "$line" >> "$FAKE_DIR/session.sql"
                case "$line" in
                    *pg_export_snapshot*)
                        if [ -f "$FAKE_DIR/session_fails" ]; then
                            echo 'psql:<stdin>:3: ERROR:  permission denied for table item'
                            exit 3
                        fi
                        echo "snapshot 00000003-0000001B-1" ;;
                    *query_to_xml*) cat "$FAKE_DIR/counts/$container" ;;
                    *alembic_version*) printf 'head %s\n' "$(cat "$FAKE_DIR/heads/$container")" ;;
                    *"'counted'"*) echo counted ;;
                esac
            done
        else
            sql=""
            while [ "$#" -gt 0 ]; do
                if [ "$1" = -c ]; then sql="$2"; break; fi
                shift
            done
            case "$sql" in
                *query_to_xml*) cat "$FAKE_DIR/counts/$container" ;;
                *alembic_version*) printf 'head %s\n' "$(cat "$FAKE_DIR/heads/$container")" ;;
                *) exit 1 ;;
            esac
        fi ;;
    pg_dump) printf 'PGDMP a copy of %s\n' "$container" ;;
    createdb) [ ! -f "$FAKE_DIR/createdb_fails" ] || exit 1 ;;
    pg_restore)
        cat > "$FAKE_DIR/loaded.dump"
        [ ! -f "$FAKE_DIR/restore_fails" ] || exit 1 ;;
    *) exit 127 ;;
    esac ;;
*) exit 1 ;;
esac
"""

FAKE_AWS = r"""#!/bin/sh
# aws, as far as brain-backup uses it: s3 cp into a directory standing in for the bucket.
us="$(printf '\037')"
record=""
for arg in "$@"; do record="$record$arg$us"; done
printf '%s\036\n' "$record" >> "$FAKE_DIR/aws.log"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --endpoint-url) shift 2 ;;
        s3) shift; break ;;
        *) exit 2 ;;
    esac
done
[ "$1" = cp ] || exit 2
mkdir -p "$FAKE_DIR/bucket"
cp "$2" "$FAKE_DIR/bucket/${3##*/}"
"""


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


@dataclass
class Stage:
    """One directory holding the stand-ins, what they answer with, and what they recorded."""

    root: Path

    @classmethod
    def at(cls, root: Path) -> Stage:
        for one in ("bin", "ids", "networks", "internal", "counts", "heads", "tmp", "work"):
            (root / one).mkdir(parents=True, exist_ok=True)
        _executable(root / "bin" / "docker", FAKE_DOCKER)
        _executable(root / "bin" / "aws", FAKE_AWS)
        stage = cls(root)
        stage.container(LIVE, LIVE_ID)
        return stage

    def container(
        self,
        name: str,
        identifier: str,
        *,
        networks: str = "",
        counts: dict[str, int] | None = None,
        head: str = HEAD,
    ) -> None:
        (self.root / "ids" / name).write_text(identifier, encoding="utf-8", newline="\n")
        (self.root / "networks" / name).write_text(networks, encoding="utf-8", newline="\n")
        lines = "".join(
            f"{json.dumps(table)}: {rows}\n" for table, rows in (counts or COUNTS).items()
        )
        (self.root / "counts" / name).write_text(lines, encoding="utf-8", newline="\n")
        (self.root / "heads" / name).write_text(json.dumps(head), encoding="utf-8", newline="\n")

    def network(self, name: str, *, internal: bool) -> None:
        (self.root / "internal" / name).write_text(
            "true" if internal else "false", encoding="utf-8", newline="\n"
        )

    def flag(self, name: str) -> None:
        (self.root / name).touch()

    def run(
        self, script: Path, *args: str, unset: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": str(self.root / "bin") + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_DIR": self.root.as_posix(),
            "TMPDIR": (self.root / "tmp").as_posix(),
            "BRAIN_DB_CONTAINER": LIVE,
            "BRAIN_DB_NAME": LIVE_DB,
            "BRAIN_DB_USER": LIVE_DB,
            "BRAIN_BACKUP_BUCKET": "copies",
            "BRAIN_BACKUP_ENDPOINT": "http://127.0.0.1:9",
            "BRAIN_BACKUP_WORK_DIR": (self.root / "work").as_posix(),
        }
        for name in unset:
            env.pop(name)
        assert SH is not None
        return subprocess.run(
            [SH, script.as_posix(), *args],
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
        )

    def calls(self, tool: str) -> list[list[str]]:
        log = self.root / f"{tool}.log"
        if not log.exists():
            return []
        records = log.read_bytes().decode("utf-8").split("\x1e\n")
        return [record.split("\x1f")[:-1] for record in records if record]

    def execs(self) -> list[list[str]]:
        return [one[1:] for one in self.calls("docker") if one[:1] == ["exec"]]


def _program_of(call: list[str]) -> tuple[str, str, list[str]]:
    """An exec call's container, program and the program's own arguments.

    The scripts pass `exec` no option that takes a value, so the container is the first
    argument that is not an option."""
    at = next(index for index, one in enumerate(call) if not one.startswith("-"))
    return call[at], call[at + 1], call[at + 2 :]


# ------------------------------------------------------------------ the copy the taker takes
@pytest.fixture(scope="module")
def taken(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[Stage, subprocess.CompletedProcess[str]]]:
    stage = Stage.at(tmp_path_factory.mktemp("taker"))
    yield stage, stage.run(TAKER)


def _uploaded(stage: Stage, suffix: str) -> Path:
    found = sorted((stage.root / "bucket").glob(f"*{suffix}"))
    assert len(found) == 1, found
    return found[0]


def test_both_scripts_parse_under_the_shell_that_runs_them_and_carry_no_carriage_return() -> None:
    """Both run as `/bin/sh`, which is dash on the servers this ships to, so they are checked
    with `sh -n` rather than with bash in its own mode. That difference is not academic: bash
    outside POSIX mode rejects the taker's `${VAR:?...}` lines, whose messages hold an
    apostrophe, and dash and `bash --posix` both accept them.

    Delete this and a quoting slip in a refusal ships as a drill that fails on the line meant to
    explain why it stopped, or a CRLF from a Windows edit ships as an interpreter nobody named."""
    assert SH is not None
    for script in (TAKER, DRILL):
        raw = script.read_bytes()
        checked = subprocess.run(
            [SH, "-n", script.as_posix()], capture_output=True, text=True, check=False
        )

        assert raw.startswith(b"#!/bin/sh\n"), script.name
        assert b"\r" not in raw, script.name
        assert checked.returncode == 0, (script.name, checked.stderr)


def test_the_taker_states_every_count_and_the_head_its_session_read_and_dumps_that_snapshot(
    taken: tuple[Stage, subprocess.CompletedProcess[str]],
) -> None:
    """The manifest now says what a drill must get back, and the dump is taken from the snapshot
    those figures were read in. The snapshot is what makes the counts comparable at all: counted
    a second apart from the copy, a busy install's audit ledger differs on every drill.

    The uploaded manifest is still one `brain.ops.backup_manifest` reads, so the new fields did
    not cost the old reader anything.

    Delete this and the counts can come from outside the snapshot, or not reach the manifest,
    and every drill of every copy either always fails or has nothing to compare with."""
    stage, result = taken
    assert result.returncode == 0, result.stderr

    manifest_path = _uploaded(stage, ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dumps = [call for call in stage.execs() if _program_of(call)[1] == "pg_dump"]

    assert manifest["row_counts"] == COUNTS
    assert manifest["migration_head"] == HEAD
    assert manifest["size_bytes"] == _uploaded(stage, ".dump").stat().st_size
    assert backup_from(manifest, where=manifest_path.name).backup_id == manifest["backup_id"]
    assert len(dumps) == 1
    assert f"--snapshot={SNAPSHOT}" in _program_of(dumps[0])[2]
    assert [call[-1].rsplit("/", 1)[-1] for call in stage.calls("aws")] == [
        f"{manifest['backup_id']}.dump",
        f"{manifest['backup_id']}.manifest.json",
    ]
    assert sorted(path.name for path in (stage.root / "work").iterdir()) == []


def test_the_taker_counts_inside_one_read_only_transaction_on_the_live_database(
    taken: tuple[Stage, subprocess.CompletedProcess[str]],
) -> None:
    """**This replaced a textual ban on `psql` in the taker**, which `tests/unit/test_seed.py`
    records. A read-only transaction is refused a write by PostgreSQL, so the one file allowed to
    read the whole database still cannot change it, and that is held on the statements the
    session was actually fed.

    Delete this and the session can open without `read only`, or commit before the dump has used
    its snapshot, with nothing red."""
    stage, result = taken
    assert result.returncode == 0, result.stderr

    statements = [
        line
        for line in (stage.root / "session.sql").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sessions = [call for call in stage.execs() if _program_of(call)[1] == "psql"]

    assert statements[0] == READ_ONLY_BEGIN
    assert statements[-1] == "commit;"
    assert sum(one.startswith(("begin", "commit", "rollback", "end")) for one in statements) == 2
    assert len(sessions) == 1
    container, _, arguments = _program_of(sessions[0])
    assert container == LIVE
    assert arguments[arguments.index("-d") + 1] == LIVE_DB


def test_every_docker_exec_the_taker_runs_uses_only_flags_plain_docker_accepts(
    taken: tuple[Stage, subprocess.CompletedProcess[str]],
) -> None:
    """**Written for a defect found by reading, not by a run.** The taker said `docker exec -T`
    until 2026-09-17. `-T` belongs to `docker compose exec`; plain `docker exec` has no such flag
    and refuses the command, so every nightly run failed before copying anything, and nothing in
    this repository ever ran the script to notice.

    Delete this and the flag can come back, and the only symptom is a bucket with no copies."""
    stage, result = taken
    assert result.returncode == 0, result.stderr

    for call in stage.execs():
        at = next(index for index, one in enumerate(call) if not one.startswith("-"))
        assert set(call[:at]) <= DOCKER_EXEC_FLAGS, call[:at]


def test_a_session_that_cannot_count_takes_no_copy_and_uploads_nothing(tmp_path: Path) -> None:
    """A copy whose manifest cannot say what it holds is a copy no drill can verify, and the
    usual cause, a role that may not read a table, would also have made the dump fail.

    Delete this and a failed count can fall through to a dump and a manifest with no figures,
    which the drill then refuses every morning with nobody having been told at night."""
    stage = Stage.at(tmp_path)
    stage.flag("session_fails")

    result = stage.run(TAKER)

    assert result.returncode == 1
    assert [call for call in stage.execs() if _program_of(call)[1] == "pg_dump"] == []
    assert stage.calls("aws") == []
    assert sorted(path.name for path in (stage.root / "work").iterdir()) == []


# ------------------------------------------------------------------ the drill's arguments
@pytest.fixture
def drill(
    tmp_path: Path, taken: tuple[Stage, subprocess.CompletedProcess[str]]
) -> tuple[Stage, Path, Path]:
    """A stage with a live container, an internal scratch container, and the taker's own copy."""
    source, result = taken
    assert result.returncode == 0, result.stderr
    stage = Stage.at(tmp_path)
    stage.container(SCRATCH, SCRATCH_ID, networks=f"{DRILL_NETWORK} none ")
    stage.network(DRILL_NETWORK, internal=True)
    download = tmp_path / "download"
    download.mkdir()
    manifest = download / _uploaded(source, ".manifest.json").name
    dump = download / _uploaded(source, ".dump").name
    shutil.copyfile(_uploaded(source, ".manifest.json"), manifest)
    shutil.copyfile(_uploaded(source, ".dump"), dump)
    return stage, manifest, dump


def _arguments(manifest: Path, dump: Path, /, **changes: str | None) -> list[str]:
    chosen: dict[str, str | None] = {
        "--manifest": manifest.as_posix(),
        "--dump": dump.as_posix(),
        "--scratch-container": SCRATCH,
        "--scratch-database": SCRATCH_DB,
    }
    chosen.update({f"--{key.replace('_', '-')}": value for key, value in changes.items()})
    return [part for key, value in chosen.items() if value is not None for part in (key, value)]


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_the_usage_and_runs_nothing(drill: tuple[Stage, Path, Path], flag: str) -> None:
    """Delete this and asking the script what it does can start doing it."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, flag, *_arguments(manifest, dump))

    assert result.returncode == 0
    assert result.stdout.splitlines()[0].startswith("usage: brain-restore-drill ")
    assert stage.calls("docker") == []


@pytest.mark.parametrize(
    "extra",
    [["--scratch"], ["--manifest=x"], ["--scratch-database"], ["--dump", "--manifest"]],
    ids=["unknown", "equals-form", "no-value-at-end", "option-as-value"],
)
def test_an_unknown_argument_or_an_option_without_a_value_is_refused_before_anything_runs(
    drill: tuple[Stage, Path, Path], extra: list[str]
) -> None:
    """A mistyped option skipped rather than refused is how a drill runs with a default nobody
    chose, and an option swallowing the next flag as its value is how a target becomes a file
    name. Delete this and either is carried into a load."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump), *extra)

    assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


@pytest.mark.parametrize("missing", ["manifest", "dump", "scratch_container", "scratch_database"])
def test_a_drill_missing_any_required_argument_is_refused_before_docker_is_asked(
    drill: tuple[Stage, Path, Path], missing: str
) -> None:
    """**The target is never chosen for the operator.** A script that defaulted the scratch
    container would default it to something, and the day that something is renamed is the day a
    drill finds a container by that name that is not scratch.

    Delete this and any of the four can be left out and filled in by whatever the script finds."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump, **{missing: None}))

    assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


@pytest.mark.parametrize("unset", ["BRAIN_DB_CONTAINER", "BRAIN_DB_NAME"])
def test_a_drill_that_cannot_tell_which_database_is_live_is_refused(
    drill: tuple[Stage, Path, Path], unset: str
) -> None:
    """Every refusal of the live target compares against these two. Delete this and an operator
    who forgot to load the install's environment file gets a drill that compares the target with
    an empty string, which every name passes."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump), unset=(unset,))

    assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


# ------------------------------------------------------------------ the live database
def test_the_live_container_named_as_the_scratch_target_is_refused_before_docker_is_asked(
    drill: tuple[Stage, Path, Path],
) -> None:
    """Delete this and the check by identifier below is the only one, so a drill whose docker
    cannot be asked about the scratch container is no longer refused for naming the live one."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump, scratch_container=LIVE))

    assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


def test_the_live_database_name_as_the_scratch_database_is_refused_before_docker_is_asked(
    drill: tuple[Stage, Path, Path],
) -> None:
    """The second, independent refusal: even a container check that was somehow passed would
    then create a new database beside the live one, never load into it.

    Delete this and the container check is the only thing between a mistyped target and a load
    on top of the company's data."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump, scratch_database=LIVE_DB))

    assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


@pytest.mark.parametrize("alias", ["a" * 12, "db-live-renamed"], ids=["id-prefix", "other-name"])
def test_the_live_container_under_another_name_is_refused_and_nothing_is_executed(
    drill: tuple[Stage, Path, Path], alias: str
) -> None:
    """Docker resolves a container by name, by full identifier and by any unique prefix of it,
    so a name comparison alone passes the live container typed as `aaaaaaaaaaaa`. The identifier
    docker reports for both is what is compared.

    Delete this and the live container is refused only when it is spelled the way the install's
    environment file spells it."""
    stage, manifest, dump = drill
    stage.container(alias, LIVE_ID, networks=f"{DRILL_NETWORK} ")

    result = stage.run(DRILL, *_arguments(manifest, dump, scratch_container=alias))

    assert result.returncode == 2, result.stderr
    assert stage.execs() == []
    assert {tuple(call[:2]) for call in stage.calls("docker")} == {("container", "inspect")}


def test_a_live_container_docker_cannot_find_is_refused_rather_than_assumed_to_differ(
    drill: tuple[Stage, Path, Path],
) -> None:
    """A live container that was renamed is not found under its old name, and "not found" read
    as "so the target cannot be it" passes the live container under its new name.

    Delete this and the identifier check fails open whenever the environment file is stale."""
    stage, manifest, dump = drill
    (stage.root / "ids" / LIVE).unlink()

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 2, result.stderr
    assert stage.execs() == []


def test_a_scratch_container_on_a_network_that_is_not_internal_is_refused(
    drill: tuple[Stage, Path, Path],
) -> None:
    """The scratch database holds every record the install holds. Delete this and a drill run
    on the default bridge leaves a second, unguarded copy of the company reachable from every
    container on it. The positive sibling is the load test below, whose scratch container is on
    an internal network and on `none`."""
    stage, manifest, dump = drill
    stage.container(SCRATCH, SCRATCH_ID, networks=f"{DRILL_NETWORK} bridge ")
    stage.network("bridge", internal=False)

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 2, result.stderr
    assert stage.execs() == []


def test_a_scratch_target_is_loaded_checked_and_is_the_only_container_anything_runs_in(
    drill: tuple[Stage, Path, Path],
) -> None:
    """**The positive sibling of every refusal above.** A guard tested only by its refusals is
    satisfied by a script that refuses everything, and a script that refused correctly and then
    loaded into the wrong container would pass all of them.

    So this asserts the whole of what was executed: a fresh database created, the copy loaded
    into it byte for byte, and the two questions asked of it, every one in the scratch container
    and against the scratch database. The live container is inspected and never executed in.

    Delete this and the load can be aimed at the live container or the live database with every
    refusal test still green."""
    stage, manifest, dump = drill

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 0, result.stderr
    executed = [_program_of(call) for call in stage.execs()]
    assert [(container, program) for container, program, _ in executed] == [
        (SCRATCH, "createdb"),
        (SCRATCH, "pg_restore"),
        (SCRATCH, "psql"),
        (SCRATCH, "psql"),
    ]
    assert executed[0][2][-1] == SCRATCH_DB
    for _, program, arguments in executed[1:]:
        assert arguments[arguments.index("-d") + 1] == SCRATCH_DB, program
    assert (stage.root / "loaded.dump").read_bytes() == dump.read_bytes()
    for call in stage.calls("docker"):
        assert LIVE not in call or call[:2] == ["container", "inspect"], call


# ------------------------------------------------------------------ the manifest check
def _named(stderr: str) -> set[str]:
    """The tables a failed drill named, read as the JSON keys its difference lines begin with."""
    decoder = json.JSONDecoder()
    return {decoder.raw_decode(line)[0] for line in stderr.splitlines() if line.startswith('"')}


@pytest.mark.parametrize(
    ("loaded", "named"),
    [
        ({**COUNTS, "know.item": 41}, {"know.item"}),
        (
            {"know.item": 42, "public.alembic_version": 1, "public.stray": 3},
            {"obs.audit_event", "public.stray"},
        ),
    ],
    ids=["one-count-differs", "one-missing-one-extra"],
)
def test_a_table_whose_rows_did_not_come_back_fails_the_drill_and_is_named(
    drill: tuple[Stage, Path, Path], loaded: dict[str, int], named: set[str]
) -> None:
    """The point of the manifest's counts, and the positive load test above is its sibling:
    there every table matched and the drill passed. Here the loader exited zero and the rows are
    wrong, and the drill fails naming exactly the tables that differ, both ways round.

    Delete this and the comparison can pass on any count at all, which is a drill judged by the
    loader's exit status again."""
    stage, manifest, dump = drill
    stage.container(SCRATCH, SCRATCH_ID, networks=f"{DRILL_NETWORK} ", counts=loaded)

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 1, result.stderr
    assert _named(result.stderr) == named


def test_a_migration_head_that_did_not_come_back_fails_the_drill(
    drill: tuple[Stage, Path, Path],
) -> None:
    """Every count matches and the revision does not, so this is the head check alone. Delete
    this and a copy loaded from a different release's database passes on its row counts."""
    stage, manifest, dump = drill
    stage.container(SCRATCH, SCRATCH_ID, networks=f"{DRILL_NETWORK} ", head="0050")

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 1, result.stderr
    assert _named(result.stderr) == set()


def test_a_copy_whose_size_disagrees_with_its_manifest_is_never_loaded(
    drill: tuple[Stage, Path, Path],
) -> None:
    """The size is the check that catches a truncated download before an hour is spent loading
    it. Delete this and a truncated copy is loaded, fails part way, and reads as a loader fault."""
    stage, manifest, dump = drill
    dump.write_bytes(dump.read_bytes()[:-1])

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 1, result.stderr
    assert stage.execs() == []


def _without(manifest: Path, field: str) -> None:
    kept: list[str] = []
    inside = False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith(f'  "{field}"'):
            inside = line.endswith("{")
            continue
        if inside:
            inside = line not in ("  }", "  },")
            continue
        kept.append(line)
    manifest.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")


@pytest.mark.parametrize("field", ["row_counts", "migration_head", "size_bytes", "backup_id"])
def test_a_manifest_that_does_not_state_what_a_load_is_compared_with_is_refused(
    drill: tuple[Stage, Path, Path], field: str
) -> None:
    """Every copy taken before the taker wrote counts and a head has a manifest like this. A
    drill of one has nothing to compare with, and treating an absent figure as a match is a
    verification of nothing. Delete this and those copies pass."""
    stage, manifest, dump = drill
    _without(manifest, field)

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 2, result.stderr
    assert stage.execs() == []


def test_a_copy_and_a_manifest_of_two_different_backups_are_refused(
    drill: tuple[Stage, Path, Path],
) -> None:
    """Delete this and a drill can check last night's copy against the week before's manifest,
    and report the difference as lost rows."""
    stage, manifest, dump = drill
    renamed = dump.with_name("database-29990101T020000Z.dump")
    dump.rename(renamed)

    result = stage.run(DRILL, *_arguments(manifest, renamed))

    assert result.returncode == 2, result.stderr
    assert stage.execs() == []


@pytest.mark.parametrize("failing", ["createdb_fails", "restore_fails"])
def test_a_database_that_exists_or_a_load_that_stops_fails_and_is_not_checked(
    drill: tuple[Stage, Path, Path], failing: str
) -> None:
    """A scratch database that already exists is one something else wrote to, and a load that
    stopped is a partial copy. Delete this and either goes on to be counted, where the partial
    load fails loudly but the pre-filled database can pass."""
    stage, manifest, dump = drill
    stage.flag(failing)

    result = stage.run(DRILL, *_arguments(manifest, dump))

    assert result.returncode == 1, result.stderr
    assert "psql" not in [_program_of(call)[1] for call in stage.execs()]


def test_the_drill_asks_the_scratch_database_what_the_taker_asked_the_live_one(
    drill: tuple[Stage, Path, Path], taken: tuple[Stage, subprocess.CompletedProcess[str]]
) -> None:
    """Two copies of one query in two scripts drift, and a drift here reads as data loss: a
    drill that counted partitions and a taker that did not would report every partitioned
    table as wrong. Held on the statements each script actually sent, not on their source.

    Delete this and one script's query can change alone."""
    stage, manifest, dump = drill
    source, _ = taken
    assert stage.run(DRILL, *_arguments(manifest, dump)).returncode == 0

    session = (source.root / "session.sql").read_text(encoding="utf-8")
    asked = [
        arguments[arguments.index("-c") + 1]
        for _, program, arguments in (_program_of(call) for call in stage.execs())
        if program == "psql"
    ]

    assert len(asked) == 2
    for statement in asked:
        assert statement in session
