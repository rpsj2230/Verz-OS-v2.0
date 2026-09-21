"""The deploy script the server's timer runs, driven end to end against a stubbed docker.

`ops/deploy/brain-deploy` is what actually deploys an install that runs the pull timer, and its
three decisions are the ones that only run on a bad day: hold a new image back when it never
answers ready, roll back when the replacement does not, and record every ending. A rollback
nobody has run is discovered broken on the day it is needed, so each ending is produced here by
running the real script with `docker` replaced by a stub that keeps a log of every call.

The stub is semantic rather than scripted: a container answers ready when the image it runs is
in the set the scenario calls good, `docker compose up` makes the app run whatever the tag points
at, and `docker tag` moves the tag. So the assertions are about what the script decided, not
about a sequence the stub was told to expect.

Skipped where there is no `bash`; CI's runner has one.

Task ids: M38.1.3.3, M38.1.3.4, M38.1.3.5
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "deploy" / "brain-deploy"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="the deploy script is bash")

OLD = "sha256:old"
NEW = "sha256:new"
UUID = "stub-service"

#: The stub docker. Each call is appended to `calls`, one line, so order can be asserted.
STUB = r"""#!/bin/sh
S="$STUB_STATE"
echo "$*" >> "$S/calls"
ready_image() { grep -qxF "$1" "$S/good"; }
# The other containers, one per line of `containers`:
# name project service config-image image-id restart health(- for none) state
if [ "$1" = ps ]; then
  shift; all=0; proj=""; svc=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -a) all=1 ;;
      --filter) shift
        case "$1" in
          label=com.docker.compose.project=*) proj="${1#label=com.docker.compose.project=}" ;;
          label=com.docker.compose.service=*) svc="${1#label=com.docker.compose.service=}" ;;
        esac ;;
    esac
    shift
  done
  if [ -s "$S/running" ] && [ "$proj" = stub-project ] \
     && { [ -z "$svc" ] || [ "$svc" = app ]; }; then
    echo "app-stub-service"
  fi
  awk -v p="$proj" -v s="$svc" -v a="$all" \
    '(p == "" || $2 == p) && (s == "" || $3 == s) && (a == 1 || $8 == "running") { print $1 }' \
    "$S/containers"
  exit 0
fi
if [ "$1" = inspect ]; then
  line="$(awk -v n="$2" '$1 == n' "$S/containers")"
  if [ -n "$line" ]; then
    asked="$*"
    set -- $line
    case "$asked" in
      *RestartPolicy*) echo "$2|$3|$4|$6" ;;
      *State.Status*) h="$7"; [ "$h" = - ] && h=""; echo "$5|$8|$h" ;;
      *compose.project*) echo "$2" ;;
    esac
    exit 0
  fi
fi
[ "$1 $2" = "compose logs" ] && exit 0
if [ "$1" = compose ] && [ "${6:-app}" != app ]; then
  bad=0; grep -qxF "$6" "$S/broken" && bad=1
  awk -v s="$6" -v i="$(cat "$S/tag")" -v b="$bad" \
    '$2 == "stub-project" && $3 == s {
       $5 = i; if (b) { if ($7 == "-") $8 = "restarting"; else $7 = "unhealthy" } } { print }' \
    "$S/containers" > "$S/containers.new"
  mv "$S/containers.new" "$S/containers"
  exit 0
fi
case "$1" in
  pull) exit 0 ;;
  image)
    case "$*" in
      *'{{.Id}}'*) cat "$S/tag" ;;
      *Env*) printf 'PATH=/usr/bin\nCOMMIT_SHA=old\n' ;;
    esac
    exit 0 ;;
  inspect)
    case "$*" in
      *'{{.Image}}'*) [ -s "$S/running" ] || exit 1; cat "$S/running" ;;
      *Env*) printf 'PATH=/usr/bin\nCOMMIT_SHA=old\nDATABASE_URL=postgresql://db/brain\n' ;;
      *Networks*) cut -d' ' -f1 "$S/networks" ;;
      *compose.project*) echo "stub-project" ;;
      *Memory*) echo 1073741824 ;;
    esac
    exit 0 ;;
  network)
    case "$2" in
      inspect) awk -v n="$3" '$1 == n { print $2 }' "$S/networks" ;;
      connect) echo "$3 $4" >> "$S/connected" ;;
    esac
    exit 0 ;;
  run)
    cp "$S/tag" "$S/candidate"
    while [ $# -gt 0 ]; do [ "$1" = "--env-file" ] && cp "$2" "$S/envfile"; shift; done
    echo cid; exit 0 ;;
  exec)
    shift
    [ "$1" = "-i" ] && { shift; cat > "$S/published"; exit 0; }
    name="$1"
    case "$name" in
      brain-candidate-*) img="$(cat "$S/candidate")" ;;
      *) img="$(cat "$S/running")" ;;
    esac
    case "$*" in
      *health/ready*) ready_image "$img" ;;
      *health/live*) echo "commit-of-$img" ;;
    esac
    exit $? ;;
  tag) echo "$2" > "$S/tag"; exit 0 ;;
  compose) cp "$S/tag" "$S/running"; exit 0 ;;
  create) echo cid ;;
  cp) printf '{\n  "task_ids": [\n    "M1.1.1",\n    "M2.2.2"\n  ]\n}\n' ;;
esac
exit 0
"""


@dataclass
class Ran:
    code: int
    calls: list[str]
    records: list[dict[str, str]]
    running: str
    published: str
    output: str
    containers: dict[str, list[str]]


#: The app's networks as `docker inspect` lists them, by name, each with the compose project
#: its labels name ("-" for none). The default is one network, the app's own.
ONE_NETWORK = (("stub-network", "stub-project"),)


def deploy(
    tmp_path: Path,
    *,
    running: str,
    good: set[str],
    failed_before: int = 0,
    stub: str = STUB,
    networks: tuple[tuple[str, str], ...] = ONE_NETWORK,
    containers: tuple[str, ...] = (),
    broken: tuple[str, ...] = (),
) -> Ran:
    """Run the real script once: the app runs `running`, the registry's tag is `NEW`."""
    state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    service = tmp_path / "service"
    for one in (state, bin_dir, service):
        one.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(stub, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    (state / "tag").write_text(NEW + "\n", encoding="utf-8", newline="\n")
    (state / "running").write_text(
        running + ("\n" if running else ""), encoding="utf-8", newline="\n"
    )
    (state / "good").write_text("".join(f"{one}\n" for one in good), encoding="utf-8", newline="\n")
    (state / "calls").write_text("", encoding="utf-8", newline="\n")
    (state / "networks").write_text(
        "".join(f"{name} {project}\n" for name, project in networks),
        encoding="utf-8",
        newline="\n",
    )
    for name, rows in (("containers", containers), ("broken", broken)):
        (state / name).write_text(
            "".join(f"{one}\n" for one in rows), encoding="utf-8", newline="\n"
        )
    uuid_file = tmp_path / "uuid"
    uuid_file.write_text(UUID, encoding="utf-8", newline="\n")
    faildir = tmp_path / "failed"
    if failed_before:
        faildir.mkdir()
        (faildir / "sha256_new").write_text(f"{failed_before}\n", encoding="utf-8", newline="\n")
    record = tmp_path / "deployments.jsonl"

    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "BRAIN_DEPLOY_UUID_FILE": uuid_file.as_posix(),
        "BRAIN_DEPLOY_SERVICE_DIR": service.as_posix(),
        "BRAIN_DEPLOY_RECORD": record.as_posix(),
        "BRAIN_DEPLOY_FAILDIR": faildir.as_posix(),
        "BRAIN_DEPLOY_READY_TRIES": "2",
        "BRAIN_DEPLOY_READY_GAP": "0",
    }
    assert BASH is not None
    done = subprocess.run(
        [BASH, SCRIPT.as_posix()], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    lines = record.read_text(encoding="utf-8").splitlines() if record.exists() else []
    published = state / "published"
    return Ran(
        code=done.returncode,
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        records=[json.loads(line) for line in lines],
        running=(state / "running").read_text(encoding="utf-8").strip(),
        published=published.read_text(encoding="utf-8") if published.exists() else "",
        output=done.stdout + done.stderr,
        containers={
            line.split()[0]: line.split()
            for line in (state / "containers").read_text(encoding="utf-8").splitlines()
        },
    )


def first(calls: list[str], prefix: str) -> int:
    return next(i for i, call in enumerate(calls) if call.startswith(prefix))


def test_a_healthy_image_answers_ready_beside_the_old_one_before_the_old_one_is_replaced(
    tmp_path: Path,
) -> None:
    """M38.1.3.3 as an order of calls: the candidate is started and asked for readiness, and only
    after that is `docker compose up` run, which is the call that stops the old container.

    Delete this and the recreate can move back in front of the health check, which is how the
    install deployed until 2026-09-17: a broken image replaced a working one before anything
    had asked it a question."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW})

    assert ran.code == 0, ran.output
    started = first(ran.calls, "run -d --name brain-candidate-")
    asked = first(ran.calls, "exec brain-candidate-")
    replaced = first(ran.calls, "compose up")
    assert started < asked < replaced
    assert ran.running == NEW
    assert [one["outcome"] for one in ran.records] == ["deployed"]
    assert ran.records[0]["image"] == NEW
    assert ran.records[0]["previous"] == OLD
    assert ran.records[0]["commit"] == f"commit-of-{NEW}"


def test_the_candidate_is_given_the_apps_settings_and_not_the_old_images_own(
    tmp_path: Path,
) -> None:
    """The candidate must reach the same database as the app, so it takes the container's
    settings; the variables the old image supplied itself are dropped, or the new image would be
    told the old image's commit.

    Delete this and the candidate can start with no settings, never reach a database, and hold
    back every healthy release; or start with the old image's own values and report the wrong
    commit."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW})

    run = ran.calls[first(ran.calls, "run -d --name brain-candidate-")]
    assert "--network stub-network" in run
    assert "--memory 1073741824" in run
    assert run.endswith("ghcr.io/rpsj2230/verz-brain-v2.0:latest")
    settings = (tmp_path / "state" / "envfile").read_text(encoding="utf-8").splitlines()
    assert settings == ["DATABASE_URL=postgresql://db/brain"]


def test_the_candidate_starts_on_the_apps_own_network_and_joins_every_other_one_it_is_on(
    tmp_path: Path,
) -> None:
    """The app is on its compose project's network, which holds the database, and on a network
    that sorts first by name and holds no database (a vault's, say), plus one with no labels at
    all. The candidate is started on the project's network and connected to the other two, so it
    sees exactly what the app sees, and it is never connected to a network twice.

    Delete this and the candidate can go back to the first network by name, which is how every
    image on an install was held back once the app joined the vault's network: the candidate
    never reached its database and never answered ready."""
    networks = (
        ("a-vault", "a-vault"),
        ("stub-service", "-"),
        ("stub-service_default", "stub-project"),
    )
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, networks=networks)

    assert ran.code == 0, ran.output
    started = first(ran.calls, "run -d --name brain-candidate-")
    assert "--network stub-service_default " in ran.calls[started]
    joined = [call for call in ran.calls if call.startswith("network connect ")]
    assert sorted(joined) == [
        f"network connect a-vault brain-candidate-{UUID}",
        f"network connect stub-service brain-candidate-{UUID}",
    ]
    assert (
        started
        < min(ran.calls.index(call) for call in joined)
        < first(ran.calls, "exec brain-candidate-")
    )


def test_an_app_with_no_compose_label_still_gets_a_candidate_on_all_of_its_networks(
    tmp_path: Path,
) -> None:
    """The positive case for an app started outside compose: no network carries its project, so
    the first is used to start on and the rest are joined, and the deploy still goes through.

    Delete this and the label lookup can refuse, or skip networks, whenever it finds nothing."""
    networks = (("one", "-"), ("two", "-"))
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, networks=networks)

    assert ran.code == 0, ran.output
    assert "--network one " in ran.calls[first(ran.calls, "run -d --name brain-candidate-")]
    assert [c for c in ran.calls if c.startswith("network connect ")] == [
        f"network connect two brain-candidate-{UUID}"
    ]


def test_an_image_that_never_answers_ready_is_held_back_and_the_old_container_is_untouched(
    tmp_path: Path,
) -> None:
    """The gate's refusal: no `compose up` at all, the app still runs the old image, and the
    ending is recorded as `held_back` and published through the container that is still ready.

    Delete this and a gate that waits and then replaces anyway passes the healthy-path test."""
    ran = deploy(tmp_path, running=OLD, good={OLD})

    assert ran.code == 1
    assert not any(call.startswith("compose") for call in ran.calls)
    assert ran.running == OLD
    assert [one["outcome"] for one in ran.records] == ["held_back"]
    assert '"outcome":"held_back"' in ran.published


def test_a_replacement_that_is_not_ready_is_rolled_back_to_the_image_id_it_replaced(
    tmp_path: Path,
) -> None:
    """M38.1.3.4. The candidate passed, the replacement did not, and the tag is pointed back at
    the old image by its id before the second recreate. The record says `rolled_back`.

    Delete this and a rollback that re-pulls `:latest`, which is the broken build by then, reads
    exactly like one that worked."""
    stub = STUB.replace(
        'compose) cp "$S/tag" "$S/running"; exit 0 ;;',
        'compose) cp "$S/tag" "$S/running"; grep -vxF "' + NEW + '" "$S/good" > "$S/g" || true; '
        'mv "$S/g" "$S/good"; exit 0 ;;',
    )
    assert stub != STUB
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, stub=stub)

    assert ran.code == 1
    assert f"tag {OLD} ghcr.io/rpsj2230/verz-brain-v2.0:latest" in ran.calls
    assert first(ran.calls, f"tag {OLD}") < max(
        i for i, call in enumerate(ran.calls) if call.startswith("compose up")
    )
    assert ran.running == OLD
    assert [one["outcome"] for one in ran.records] == ["rolled_back"]
    assert '"outcome":"rolled_back"' in ran.published


def test_when_neither_version_answers_the_ending_is_recorded_as_a_failed_rollback(
    tmp_path: Path,
) -> None:
    """The worst ending is recorded rather than lost: `rollback_failed`, and nothing is published
    because no container answers to publish through.

    Delete this and the line for the deploy worth reading most can be dropped."""
    stub = STUB.replace(
        'compose) cp "$S/tag" "$S/running"; exit 0 ;;',
        'compose) cp "$S/tag" "$S/running"; : > "$S/good"; exit 0 ;;',
    )
    assert stub != STUB
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, stub=stub)

    assert ran.code == 1
    assert [one["outcome"] for one in ran.records] == ["rollback_failed"]
    assert ran.published == ""


def test_an_image_that_has_failed_the_limit_is_not_tried_again(tmp_path: Path) -> None:
    """Without the ceiling the timer retries a broken image every two minutes for ever, and each
    retry is a candidate started against the database. The positive case is every other test
    here, which runs with no failures counted.

    Delete this and the ceiling can be removed with every other test green."""
    ran = deploy(tmp_path, running=OLD, good={OLD}, failed_before=2)

    assert ran.code == 0
    assert not any(call.startswith(("run", "compose")) for call in ran.calls)
    assert ran.records == []


def test_a_first_deploy_has_nothing_to_gate_against_and_records_that_it_deployed(
    tmp_path: Path,
) -> None:
    """With no app container there is no running version to protect, so no candidate is started
    and the app is created directly. The record names no previous image.

    Delete this and a first install can be refused by a gate asking for a container that does
    not exist yet."""
    ran = deploy(tmp_path, running="", good={NEW})

    assert ran.code == 0, ran.output
    assert not any(call.startswith("run") for call in ran.calls)
    assert [(one["outcome"], one["previous"]) for one in ran.records] == [("deployed", "")]


def test_every_record_carries_the_task_ids_baked_into_the_image_and_reads_as_a_deployment(
    tmp_path: Path,
) -> None:
    """M38.1.3.5. The line the script writes is the line `brain.ops.deployments` parses, with the
    task ids read out of the image's indented manifest, and the whole file is handed to
    `brain.ops.deployment_store` inside the ready container.

    Delete this and the script and the parser can drift apart, and the history on the Version
    screen stops growing with every deploy still reporting success."""
    from brain.ops.deployments import Deployment

    ran = deploy(tmp_path, running=OLD, good={OLD, NEW})

    parsed = Deployment.from_line(json.dumps(ran.records[0]))
    assert parsed.task_ids == ("M1.1.1", "M2.2.2")
    assert any(
        call.startswith("exec -i app-") and "brain.ops.deployment_store" in call
        for call in ran.calls
    )
    assert Deployment.from_line(ran.published.splitlines()[0]) == parsed


#: The app's compose project as the owner's install runs it, plus what shares the server: a
#: container of another project named like the worker and running this very image, and one from
#: the other `verz-brain` project the server also hosts.
REPO_IMAGE = "ghcr.io/rpsj2230/verz-brain-v2.0"
INSTALL = (
    f"brain-worker-{UUID} stub-project brain-worker {REPO_IMAGE}:latest {OLD}"
    " unless-stopped healthy running",
    f"brain-parse-worker-{UUID} stub-project brain-parse-worker {REPO_IMAGE}:v2 {OLD}"
    " unless-stopped - running",
    f"migrate-{UUID} stub-project migrate {REPO_IMAGE}:latest {OLD} no - running",
    f"pgbouncer-{UUID} stub-project pgbouncer edoburu/pgbouncer:v1.24.1-p1 sha256:pgb"
    " unless-stopped healthy running",
    f"brain-worker-{UUID}x other-project worker {REPO_IMAGE}:latest {OLD}"
    " unless-stopped healthy running",
    "verz-brain-worker-1 verz-brain worker verz-brain-worker sha256:foreign"
    " unless-stopped - running",
)
FOREIGN = (f"brain-worker-{UUID}x", "verz-brain-worker-1")


def test_every_service_on_the_same_image_follows_the_app_once_it_is_ready_and_nothing_else(
    tmp_path: Path,
) -> None:
    """Found on the install on 2026-09-21: only `app` was recreated, so the worker kept running
    the old image and a worker fix never reached it. Now each service of the app's compose
    project on this repository follows, one at a time, waited for, and only once the app answers
    ready on the new image. The one-shot `migrate`, a service on another image, and two
    containers outside the project (one named like the worker and on this very image) are left
    alone.

    Delete this and the worker can silently stay on the old release again, or a name match can
    recreate a container that belongs to another project on the shared server."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, containers=INSTALL)

    assert ran.code == 0, ran.output
    ups = [call for call in ran.calls if call.startswith("compose up")]
    assert ups == [
        "compose up -d --force-recreate --no-deps app",
        "compose up -d --force-recreate --no-deps brain-worker",
        "compose up -d --force-recreate --no-deps brain-parse-worker",
    ]
    app_up = ran.calls.index(ups[0])
    app_ready = next(
        i
        for i, c in enumerate(ran.calls)
        if i > app_up and c.startswith(f"exec app-{UUID} ") and "health/ready" in c
    )
    worker_up = ran.calls.index(ups[1])
    waited = first(ran.calls, "ps -a --filter label=com.docker.compose.project=stub-project")
    assert app_ready < worker_up < waited < ran.calls.index(ups[2])
    assert ran.containers[f"brain-worker-{UUID}"][4] == NEW
    assert ran.containers[f"brain-parse-worker-{UUID}"][4] == NEW
    for untouched in (f"migrate-{UUID}", *FOREIGN):
        assert ran.containers[untouched][4] != NEW
    # A foreign container may be looked at, never acted on.
    assert not any(
        name in call for call in ran.calls if not call.startswith("inspect") for name in FOREIGN
    )
    assert ran.records[0]["outcome"] == "deployed"
    assert ran.records[0]["services_updated"] == "brain-worker,brain-parse-worker"
    assert ran.records[0]["services_failed"] == ""


def test_a_worker_that_fails_on_the_new_image_is_reported_and_the_healthy_app_is_kept(
    tmp_path: Path,
) -> None:
    """A worker that is not healthy on the new image does not roll back an app that is: the old
    worker is gone either way. The failure is logged loudly and recorded, the next service is
    still tried, and the run exits non-zero so the journal shows it.

    Delete this and a failed worker can pass as a clean deploy, or pull a healthy app back."""
    ran = deploy(
        tmp_path, running=OLD, good={OLD, NEW}, containers=INSTALL, broken=("brain-worker",)
    )

    assert ran.code == 1
    assert not any(call.startswith("tag ") for call in ran.calls)
    assert ran.running == NEW
    assert "SERVICE NOT UPDATED: brain-worker" in ran.output
    assert [one["outcome"] for one in ran.records] == ["deployed"]
    assert ran.records[0]["services_updated"] == "brain-parse-worker"
    assert ran.records[0]["services_failed"] == "brain-worker"
    assert '"services_failed":"brain-worker"' in ran.published


def test_an_image_the_gate_held_back_never_reaches_the_workers(tmp_path: Path) -> None:
    """The workers follow the app only when the app is ready on the new image.

    Delete this and a worker can be moved onto an image the gate refused."""
    ran = deploy(tmp_path, running=OLD, good={OLD}, containers=INSTALL)

    assert ran.code == 1
    assert ran.containers[f"brain-worker-{UUID}"][4] == OLD
    assert not any(call.startswith("compose") for call in ran.calls)
