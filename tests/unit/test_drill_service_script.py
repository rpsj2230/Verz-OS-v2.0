"""The server's drill service, run as a shell script against stand-ins for docker and the bucket.

No test here has a docker, so `docker` and `aws` are two small shell scripts on the PATH that record
every call and answer the way the real ones do for the calls this service makes. **The two Python
programs the service runs inside the application image are the real ones.** The stand-in for
`docker run ... python -m brain.ops.X` executes this checkout's `X` with the test's interpreter, so
the service, the planner and the record writer are held against each other and not each against the
author's idea of the others. The checks program is the real one too, against a real migrated
database when `DATABASE_URL` is set and against a stand-in's canned output when it is not.

Every assertion is about what the service did: its exit status, the argument vectors the stand-ins
recorded, and the record it uploaded, which is read back through `read_drills`, the reader the
product uses. None is about the script's own text.

The dates are 2999 where a fixture is not itself about the present. The one place the present
matters is the listing's times, which are written relative to the real clock the script reads.

What cannot be held here is whether the real `docker`, `aws` and PostgreSQL behave as the stand-ins
do; `docs/install/restore-drill.md` records whether a rehearsal has been run on a server.

Task ids: M30.3.6, M30.3.7, M30.3.8
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX, read_drills
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import database_url

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / "ops" / "backup" / "brain-drill-service"
CRYPT = REPO / "ops" / "backup" / "brain-backup-crypt"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="no POSIX shell here to run the scripts with")

LIVE = "db-live"
COPY = "database-29990614T020000Z"
OLDER = "database-29990607T020000Z"

FAKE_DOCKER = r"""#!/bin/sh
us="$(printf '\037')"
record=""
for arg in "$@"; do record="$record$arg$us"; done
printf '%s\036\n' "$record" >> "$FAKE_DIR/docker.log"
case "$1" in
rm) exit 0 ;;
network)
    case "$2" in
        create) [ ! -f "$FAKE_DIR/network_fails" ] || exit 1 ;;
    esac
    exit 0 ;;
inspect) printf 'postgres:18-stand-in\n' ;;
exec)
    shift
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -i|-t) shift ;;
            -*) shift 2 ;;
            *) break ;;
        esac
    done
    program="$2"
    case "$program" in
        pg_isready) [ ! -f "$FAKE_DIR/never_ready" ] || exit 2 ;;
        pg_dumpall) [ ! -f "$FAKE_DIR/roles_fail" ] || exit 1; printf 'CREATE ROLE brain_app;\n' ;;
        psql) cat > /dev/null ;;
        *) exit 127 ;;
    esac ;;
run)
    shift
    detached=no
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --rm|-i) shift ;;
            -d) detached=yes; shift ;;
            --network|--name|-e) shift 2 ;;
            -*) shift ;;
            *) break ;;
        esac
    done
    shift
    if [ "$detached" = yes ]; then
        [ ! -f "$FAKE_DIR/start_fails" ] || exit 1
        exit 0
    fi
    [ "$1" = python ] && [ "$2" = -m ] || exit 127
    module="$3"
    shift 3
    case "$module" in
        brain.ops.drill_service) exec "$FAKE_PYTHON" -m brain.ops.drill_service "$@" ;;
        brain.ops.drill_checks)
            [ ! -f "$FAKE_DIR/checks_fail" ] || exit 1
            if [ -n "${FAKE_CHECKS_URL:-}" ]; then
                exec "$FAKE_PYTHON" -m brain.ops.drill_checks "$FAKE_CHECKS_URL"
            fi
            cat "$FAKE_DIR/checks_output" ;;
        *) exit 127 ;;
    esac ;;
*) exit 1 ;;
esac
"""

FAKE_AWS = r"""#!/bin/sh
us="$(printf '\037')"
record=""
for arg in "$@"; do record="$record$arg$us"; done
printf '%s\036\n' "$record" >> "$FAKE_DIR/aws.log"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --endpoint-url) shift 2 ;;
        *) break ;;
    esac
done
case "$1" in
s3api) cat "$FAKE_DIR/listing" ;;
s3)
    case "$2" in
        cp)
            case "$3" in
                s3://*)
                    [ -f "$FAKE_DIR/bucket/${3##*/}" ] || exit 1
                    cp "$FAKE_DIR/bucket/${3##*/}" "$4" ;;
                *)
                    [ ! -f "$FAKE_DIR/upload_fails" ] || exit 1
                    mkdir -p "$FAKE_DIR/bucket"
                    cp "$3" "$FAKE_DIR/bucket/${4##*/}" ;;
            esac ;;
        rm) rm -f "$FAKE_DIR/bucket/${3##*/}" ;;
        *) exit 2 ;;
    esac ;;
*) exit 2 ;;
esac
"""

# The stand-in for the existing load-and-count script: it records the file it was given and exits
# as the test says. `brain-restore-drill` has its own tests in `test_backup_scripts.py`.
FAKE_LOAD = r"""#!/bin/sh
dump=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dump) dump="$2"; shift 2 ;;
        *) shift 2 ;;
    esac
done
printf '%s\n' "$dump" > "$FAKE_DIR/loaded_path"
cksum < "$dump" > "$FAKE_DIR/loaded_cksum"
[ ! -f "$FAKE_DIR/load_fails" ] || exit 1
"""

GOOD_CHECKS = [
    {"check": "schema_complete", "passed": True, "detail": "all schemas are present"},
    {"check": "permission_canary", "passed": True, "detail": "a stranger was refused"},
]


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S+00:00")


class Stage:
    """One directory holding the stand-ins, the bucket and what they recorded."""

    def __init__(self, root: Path) -> None:
        self.root = root
        for one in ("bin", "bucket", "tmp", "work"):
            (root / one).mkdir(parents=True, exist_ok=True)
        _executable(root / "bin" / "docker", FAKE_DOCKER)
        _executable(root / "bin" / "aws", FAKE_AWS)
        _executable(root / "bin" / "load", FAKE_LOAD)
        (root / "checks_output").write_text(json.dumps(GOOD_CHECKS), encoding="utf-8")
        self.listing: list[tuple[str, datetime]] = []

    def put(self, name: str, content: bytes | str, *, age: timedelta = timedelta(hours=8)) -> None:
        data = content.encode() if isinstance(content, str) else content
        (self.root / "bucket" / name).write_bytes(data)
        self.listing.append((name, datetime.now(UTC) - age))
        self._write_listing()

    def _write_listing(self) -> None:
        text = "".join(f"{name}\t{iso(when)}\n" for name, when in self.listing)
        (self.root / "listing").write_text(text or "None\n", encoding="utf-8", newline="\n")

    def a_copy(self, copy: str = COPY, *, dump: bytes = b"PGDMP stand-in\n") -> None:
        self.put(f"{copy}.dump", dump)
        self.put(f"{copy}{MANIFEST_SUFFIX}", json.dumps({"backup_id": copy}))

    def flag(self, name: str) -> None:
        (self.root / name).touch()

    def run(self, **env: str) -> subprocess.CompletedProcess[str]:
        assert SH is not None
        base = {
            **os.environ,
            "PATH": str(self.root / "bin") + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_DIR": self.root.as_posix(),
            "FAKE_PYTHON": sys.executable,
            "TMPDIR": (self.root / "tmp").as_posix(),
            "BRAIN_DB_CONTAINER": LIVE,
            "BRAIN_DB_NAME": "brain",
            "BRAIN_DB_USER": "brain",
            "BRAIN_BACKUP_BUCKET": "copies",
            "BRAIN_BACKUP_ENDPOINT": "http://127.0.0.1:9",
            "BRAIN_APP_IMAGE": "app-image:test",
            "BRAIN_RESTORE_DRILL": (self.root / "bin" / "load").as_posix(),
            "BRAIN_DRILL_WORK_DIR": (self.root / "work").as_posix(),
        }
        base.update(env)
        return subprocess.run(
            [SH, SERVICE.as_posix()],
            env=base,
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

    def started_a_scratch_database(self) -> bool:
        return any(call[:2] == ["run", "-d"] for call in self.calls("docker"))

    def records(self) -> list[Path]:
        return sorted((self.root / "bucket").glob(f"*{DRILL_SUFFIX}"))

    def verification(self) -> tuple[bool, float | None, dict[str, bool]]:
        [record] = self.records()
        text = record.read_text(encoding="utf-8")
        verified, unreadable = read_drills([(record.name, text)])
        assert not unreadable, unreadable
        passed = {one["check"]: one["passed"] for one in json.loads(text)["checks"]}
        return verified[0].verified, verified[0].rto_seconds, passed


@pytest.fixture
def stage(tmp_path: Path) -> Stage:
    return Stage(tmp_path)


# ---------------------------------------------------------------------------------- the script


def test_the_service_parses_under_the_shell_that_runs_it_and_carries_no_carriage_return() -> None:
    """Under dash, which is `/bin/sh` on the servers this ships to. Delete this and a quoting slip
    ships as a service that fails on the line meant to explain why it stopped, or a CRLF from a
    Windows edit ships as an interpreter nobody named."""
    assert SH is not None
    for script in (SERVICE, CRYPT):
        raw = script.read_bytes()
        checked = subprocess.run(
            [SH, "-n", script.as_posix()], capture_output=True, text=True, check=False
        )
        assert raw.startswith(b"#!/bin/sh\n"), script.name
        assert b"\r" not in raw, script.name
        assert checked.returncode == 0, (script.name, checked.stderr)


# ----------------------------------------------------------------------------- nothing is owed


def test_nothing_is_started_when_a_rehearsal_is_not_owed(stage: Stage) -> None:
    """A copy and a rehearsal an hour old. Delete this and the ten-minute timer loads the whole
    database into a scratch container every ten minutes."""
    stage.a_copy()
    stage.put(f"{COPY}-drill-x{DRILL_SUFFIX}", "{}", age=timedelta(hours=1))
    result = stage.run()
    assert result.returncode == 0, result.stderr
    assert "no rehearsal owed: not-due" in result.stdout
    assert not stage.started_a_scratch_database()
    assert [call for call in stage.calls("docker") if call[:1] == ["network"]] == []


def test_nothing_is_started_while_nothing_has_been_copied_and_an_empty_bucket_is_not_a_fault(
    stage: Stage,
) -> None:
    """The aws cli prints None for an empty bucket. Delete this and a fresh install's first timer
    tick fails on a line the planner refuses."""
    stage.put("drill-request.json", "{}", age=timedelta(minutes=1))
    stage.listing.clear()
    stage._write_listing()
    result = stage.run()
    assert result.returncode == 0, result.stderr
    assert "no rehearsal owed: nothing-copied" in result.stdout
    assert not stage.started_a_scratch_database()


# --------------------------------------------------------------------------- a healthy rehearsal


def test_a_copy_never_rehearsed_is_loaded_checked_and_recorded_as_verified(stage: Stage) -> None:
    """The whole path, with the product's own planner, record writer and reader. Delete this and
    the service can write a record the product reads as unreadable, or none at all."""
    stage.a_copy()
    result = stage.run()
    assert result.returncode == 0, result.stderr
    verified, rto, passed = stage.verification()
    assert verified
    assert rto is not None and rto >= 0
    assert passed == {
        "smoke_query": True,
        "schema_complete": True,
        "permission_canary": True,
    }
    [record] = stage.records()
    assert record.name.startswith(f"{COPY}-drill-")


def test_the_scratch_database_is_on_an_internal_network_from_the_live_image_and_is_removed(
    stage: Stage,
) -> None:
    """Delete this and the scratch copy can sit on a network with a way out, or outlive the
    rehearsal holding every record the install has."""
    stage.a_copy()
    stage.run()
    calls = stage.calls("docker")
    [created] = [call for call in calls if call[:2] == ["network", "create"]]
    assert "--internal" in created
    [started] = [call for call in calls if call[:2] == ["run", "-d"]]
    assert "postgres:18-stand-in" in started
    assert calls[-2][:3] == ["rm", "-f", "brain-drill-db"]
    assert calls[-1][:2] == ["network", "rm"]


def test_everything_downloaded_is_gone_afterwards_on_success(stage: Stage) -> None:
    """The copy and the roles file are the company's data. Delete this and a finished rehearsal
    leaves a second unencrypted copy in the work directory."""
    stage.a_copy()
    stage.run()
    assert list((stage.root / "work").iterdir()) == []


def test_the_application_image_is_run_with_no_network_for_the_planner_and_the_record_writer(
    stage: Stage,
) -> None:
    """Only the checks need to reach the scratch database. Delete this and the two programs that
    read the bucket's listing and the checks' output are given a way out."""
    stage.a_copy()
    stage.run()
    for module in ("plan", "record"):
        [call] = [one for one in stage.calls("docker") if module in one and one[:1] == ["run"]]
        assert call[call.index("--network") + 1] == "none"
    [checks] = [one for one in stage.calls("docker") if "brain.ops.drill_checks" in one]
    assert checks[checks.index("--network") + 1] == "brain-drill"


# ----------------------------------------------------------------------------- an unhealthy one


def test_a_copy_that_does_not_load_leaves_a_record_that_does_not_verify_and_asks_no_more(
    stage: Stage,
) -> None:
    """The failure is the evidence. Delete this and a load that failed leaves no record, and the
    previous success stands as the newest thing the panel knows."""
    stage.a_copy()
    stage.flag("load_fails")
    result = stage.run()
    assert result.returncode == 0, result.stderr
    verified, rto, passed = stage.verification()
    assert not verified and rto is None
    assert passed == {"smoke_query": False, "schema_complete": False, "permission_canary": False}
    assert [call for call in stage.calls("docker") if "brain.ops.drill_checks" in call] == []


def test_a_canary_that_failed_is_recorded_as_failed_and_the_copy_is_not_verified(
    stage: Stage,
) -> None:
    """The service writes the answer and the product decides. Delete this and a failed canary can
    be recorded as a pass because the script made the record."""
    stage.a_copy()
    bad = [
        GOOD_CHECKS[0],
        {**GOOD_CHECKS[1], "passed": False, "detail": "the stranger was shown a row"},
    ]
    (stage.root / "checks_output").write_text(json.dumps(bad), encoding="utf-8")
    stage.run()
    verified, _, passed = stage.verification()
    assert not verified
    assert passed["smoke_query"] is True and passed["permission_canary"] is False


def test_checks_that_could_not_be_run_are_recorded_as_failed_not_as_missing(stage: Stage) -> None:
    """Both directions of a program that falls over. Delete this and a crashed canary leaves a
    record with fewer checks, which reads as a shortfall nobody can act on."""
    stage.a_copy()
    stage.flag("checks_fail")
    stage.run()
    verified, _, passed = stage.verification()
    assert not verified
    assert passed["schema_complete"] is False and passed["permission_canary"] is False


@pytest.mark.parametrize("flag", ["network_fails", "start_fails", "never_ready", "roles_fail"])
def test_a_scratch_database_that_cannot_be_made_ready_still_leaves_a_failed_record(
    stage: Stage, flag: str
) -> None:
    """Each step before the load. Delete this and a rehearsal that fell over before it began
    leaves no evidence, which is the rehearsal whose absence matters most."""
    stage.a_copy()
    stage.flag(flag)
    result = stage.run()
    assert result.returncode == 0, result.stderr
    verified, rto, _ = stage.verification()
    assert not verified and rto is None
    assert list((stage.root / "work").iterdir()) == []


# ----------------------------------------------------------------------------------- the request


def test_a_request_is_removed_only_after_its_record_is_beside_the_copy(stage: Stage) -> None:
    """Delete this and the ask is removed first, and a record that failed to upload loses it."""
    stage.a_copy()
    stage.put(f"{COPY}-drill-x{DRILL_SUFFIX}", "{}", age=timedelta(minutes=5))
    stage.put("drill-request.json", "{}", age=timedelta(minutes=1))
    result = stage.run()
    assert result.returncode == 0, result.stderr
    assert not (stage.root / "bucket" / "drill-request.json").exists()
    assert len(stage.records()) == 2


def test_a_request_survives_a_record_that_could_not_be_uploaded(stage: Stage) -> None:
    """Delete this and a failed upload eats the ask, and the person presses a button that worked."""
    stage.a_copy()
    stage.put("drill-request.json", "{}", age=timedelta(minutes=1))
    stage.flag("upload_fails")
    result = stage.run()
    assert result.returncode == 1
    assert (stage.root / "bucket" / "drill-request.json").exists()
    assert "could not be uploaded" in result.stderr


def test_a_scheduled_rehearsal_leaves_nothing_to_remove_and_removes_nothing(stage: Stage) -> None:
    """Delete this and the service deletes a request it did not act on."""
    stage.a_copy()
    stage.run()
    assert not any(call[:3] == ["s3", "rm"] for call in (c[2:] for c in stage.calls("aws")))


# ---------------------------------------------------------------------------------- the refusals


def test_the_service_refuses_when_the_live_database_has_the_scratch_names(stage: Stage) -> None:
    """The live container or database called what a rehearsal removes. Delete this and a rehearsal
    removes the company's database container by name."""
    stage.a_copy()
    for env in ({"BRAIN_DB_CONTAINER": "brain-drill-db"}, {"BRAIN_DB_NAME": "brain_drill"}):
        result = stage.run(**env)
        assert result.returncode == 2, result.stderr
    assert stage.calls("docker") == []


def test_the_service_refuses_without_the_application_image_before_it_asks_docker_anything(
    stage: Stage,
) -> None:
    """The image holds the checks. Delete this and a missing variable is a rehearsal that loads
    the copy and then cannot ask it anything."""
    stage.a_copy()
    result = stage.run(BRAIN_APP_IMAGE="")
    assert result.returncode != 0
    assert stage.calls("docker") == []


def test_a_listing_the_planner_refuses_starts_nothing(stage: Stage) -> None:
    """Delete this and a mangled listing reads as a bucket with fewer copies."""
    stage.a_copy()
    (stage.root / "listing").write_text("not a listing\n", encoding="utf-8")
    result = stage.run()
    assert result.returncode == 1
    assert not stage.started_a_scratch_database()


# ------------------------------------------------------------------------------ an encrypted copy


def _keys(tmp_path: Path) -> tuple[Path, Path]:
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(private), "2048"], capture_output=True, check=True
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(private), "-pubout", "-out", str(public)],
        capture_output=True,
        check=True,
    )
    return private, public


@pytest.mark.skipif(shutil.which("openssl") is None, reason="no openssl here")
def test_an_encrypted_copy_is_decrypted_with_the_identity_and_loaded_as_the_original_bytes(
    stage: Stage, tmp_path: Path
) -> None:
    """Producer and consumer: the copy is encrypted by the product's own script and read back by
    the service. Delete this and the two can disagree about the layout and no encrypted copy is
    ever rehearsed."""
    private, public = _keys(tmp_path)
    original = tmp_path / "original.dump"
    original.write_bytes(b"PGDMP the original bytes\n" * 50)
    subprocess.run(
        [
            SH or "sh",
            CRYPT.as_posix(),
            "encrypt",
            "--recipient",
            str(public),
            "--in",
            str(original),
            "--out",
            str(tmp_path / "c.enc"),
            "--key-out",
            str(tmp_path / "c.key"),
        ],
        check=True,
        capture_output=True,
    )
    stage.put(f"{COPY}.dump.enc", (tmp_path / "c.enc").read_bytes())
    stage.put(f"{COPY}.dump.key", (tmp_path / "c.key").read_bytes())
    stage.put(f"{COPY}{MANIFEST_SUFFIX}", json.dumps({"backup_id": COPY}))
    result = stage.run(BRAIN_BACKUP_IDENTITY=str(private), BRAIN_BACKUP_CRYPT=str(CRYPT))
    assert result.returncode == 0, result.stderr
    verified, _, _ = stage.verification()
    assert verified
    expected = subprocess.run(
        ["cksum"], input=original.read_bytes(), capture_output=True, check=True
    )
    assert (stage.root / "loaded_cksum").read_bytes() == expected.stdout


def test_an_encrypted_copy_with_no_identity_on_the_server_leaves_a_failed_record_saying_so(
    stage: Stage,
) -> None:
    """The client chose not to leave the key. Delete this and an encrypted install is never
    rehearsed and never says so, or the service reads the encrypted bytes as a dump."""
    stage.put(f"{COPY}.dump.enc", b"opaque")
    stage.put(f"{COPY}.dump.key", b"opaque")
    stage.put(f"{COPY}{MANIFEST_SUFFIX}", json.dumps({"backup_id": COPY}))
    result = stage.run()
    assert result.returncode == 0, result.stderr
    verified, _, passed = stage.verification()
    assert not verified and passed["smoke_query"] is False
    [record] = stage.records()
    assert "no private key is left" in record.read_text(encoding="utf-8")
    assert not (stage.root / "loaded_path").exists()


# ------------------------------------------------------------------------- on a real database


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    if database_url() is None:
        pytest.skip("DATABASE_URL is unset, so there is no server; CI always sets it")
    with retirable("brain_test_drill_service") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to head need pgvector, which CI's server has")
        yield url


def test_the_real_checks_against_a_real_migrated_database_make_a_verified_record(
    stage: Stage, migrated: str
) -> None:
    """The service end to end with only docker and the bucket standing in. Delete this and the
    checks' output and the record writer can drift apart with every unit test green."""
    stage.a_copy()
    result = stage.run(FAKE_CHECKS_URL=migrated)
    assert result.returncode == 0, result.stderr
    verified, _, passed = stage.verification()
    assert verified, passed
