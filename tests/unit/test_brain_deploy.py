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

Since 2026-09-29 (needs-rupash 114) it also applies the new release's own vault changes, read out
of the new image, with the deploy token the server keeps root-only, before anything runs that
image. The stub carries a stand-in for the image's `ops/openbao` directory whose apply script
records that it ran and exits as the scenario says.

Task ids: M38.1.3.3, M38.1.3.4, M38.1.3.5, M31.3.2.2, M32.2.1.1
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "deploy" / "brain-deploy"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="the deploy script is bash")


def _gnu_date() -> bool:
    """Whether `date -Is` answers, as it does on the Linux servers the script runs on and does not
    on the BSD `date` a Mac ships, where it prints nothing and the record has no timestamp."""
    done = subprocess.run(["date", "-Is"], capture_output=True, text=True, check=False)
    return done.returncode == 0 and bool(done.stdout.strip())


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
      *'{{.Image}}'*) echo "$5" ;;
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
  create)
    # An image the scenario calls unopenable cannot be created from, as one that is gone cannot.
    grep -qxF "$2" "$S/unopenable" 2>/dev/null && exit 1
    echo "cid-$2" ;;
  cp)
    case "$2" in
      *:/app/RELEASE.json)
        # `cid-<image>:/app/RELEASE.json`: the manifest the scenario gave that image, if any.
        img="${2#cid-}"; img="${img%:/app/RELEASE.json}"
        key="$(printf '%s' "$img" | tr -c 'A-Za-z0-9' '_')"
        if [ -f "$S/manifests/$key" ]; then cat "$S/manifests/$key"; exit 0; fi ;;
      *:/app/ops/openbao/.) [ -d "$S/openbao" ] || exit 1; cp -R "$S/openbao/." "$3"; exit 0 ;;
      *:/app/ops/keycloak/accounts-client.sh)
        [ -f "$S/accounts" ] || exit 1; cp "$S/accounts" "$3"; exit 0 ;;
      *:/app/ops/deploy/overlays/.)
        [ -d "$S/overlays" ] || exit 1; cp -R "$S/overlays/." "$3"; exit 0 ;;
    esac
    printf '{\n  "task_ids": [\n    "M1.1.1",\n    "M2.2.2"\n  ]\n}\n' ;;
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
    applied: str
    containers: dict[str, list[str]]
    accounts: str
    overlays: str


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
    deploy_token: bool = False,
    apply_exit: int | None = None,
    accounts_exit: int | None = None,
    overlays_exit: int | None = None,
    manifests: Mapping[str, str] | None = None,
    unopenable: tuple[str, ...] = (),
    recreate_all: bool = False,
) -> Ran:
    """Run the real script once: the app runs `running`, the registry's tag is `NEW`.

    `deploy_token` puts a deploy token file where the script looks; `apply_exit` gives the new
    image an `ops/openbao/apply-release.sh` that exits with it, and None gives it none, as an image
    from before the vault changes shipped in it. `accounts_exit` gives the running application an
    `ops/keycloak/accounts-client.sh` that records whom it was pointed at and exits with it.
    `overlays_exit` gives the new image an `ops/deploy/overlays/apply.sh` that does the same, and
    None gives it none, as an image from before the optional services step shipped in it.
    `manifests` gives an image, by its id, the `RELEASE.json` text `docker cp` reads out of it, and
    an image with none has the one the stub always had, which names no fingerprint; `unopenable`
    names images `docker create` refuses; `recreate_all` sets the operator's override.
    """
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
    (state / "manifests").mkdir()
    for image, text in (manifests or {}).items():
        key = "".join(c if c.isalnum() else "_" for c in image)
        (state / "manifests" / key).write_text(text, encoding="utf-8", newline="\n")
    (state / "unopenable").write_text(
        "".join(f"{one}\n" for one in unopenable), encoding="utf-8", newline="\n"
    )
    uuid_file = tmp_path / "uuid"
    uuid_file.write_text(UUID, encoding="utf-8", newline="\n")
    faildir = tmp_path / "failed"
    if failed_before:
        faildir.mkdir()
        (faildir / "sha256_new").write_text(f"{failed_before}\n", encoding="utf-8", newline="\n")
    record = tmp_path / "deployments.jsonl"
    token = tmp_path / "deploy.token"
    if deploy_token:
        token.write_text("a-deploy-token", encoding="utf-8", newline="\n")
    if apply_exit is not None:
        carried = state / "openbao"
        carried.mkdir()
        (carried / "apply-release.sh").write_text(
            f'#!/bin/sh\necho "applied with $BRAIN_VAULT_DEPLOY_TOKEN_FILE" > "{state}/applied"\n'
            f"exit {apply_exit}\n",
            encoding="utf-8",
            newline="\n",
        )

    if accounts_exit is not None:
        (state / "accounts").write_text(
            f'#!/bin/sh\necho "ran with $BRAIN_APP_CONTAINER" > "{state}/accounts-ran"\n'
            f"exit {accounts_exit}\n",
            encoding="utf-8",
            newline="\n",
        )

    if overlays_exit is not None:
        carried = state / "overlays"
        carried.mkdir()
        (carried / "apply.sh").write_text(
            f'#!/bin/sh\necho "ran with $1" > "{state}/overlays-ran"\nexit {overlays_exit}\n',
            encoding="utf-8",
            newline="\n",
        )

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
        "BRAIN_DEPLOY_VAULT_TOKEN_FILE": token.as_posix(),
        **({"BRAIN_DEPLOY_RECREATE_ALL": "1"} if recreate_all else {}),
    }
    assert BASH is not None
    done = subprocess.run(
        [BASH, SCRIPT.as_posix()], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    lines = record.read_text(encoding="utf-8").splitlines() if record.exists() else []
    published = state / "published"
    applied = state / "applied"
    accounts = state / "accounts-ran"
    overlays = state / "overlays-ran"
    return Ran(
        code=done.returncode,
        calls=(state / "calls").read_text(encoding="utf-8").splitlines(),
        records=[json.loads(line) for line in lines],
        running=(state / "running").read_text(encoding="utf-8").strip(),
        published=published.read_text(encoding="utf-8") if published.exists() else "",
        output=done.stdout + done.stderr,
        applied=applied.read_text(encoding="utf-8").strip() if applied.exists() else "",
        accounts=accounts.read_text(encoding="utf-8").strip() if accounts.exists() else "",
        overlays=overlays.read_text(encoding="utf-8").strip() if overlays.exists() else "",
        containers={
            line.split()[0]: line.split()
            for line in (state / "containers").read_text(encoding="utf-8").splitlines()
        },
    )


def first(calls: list[str], prefix: str) -> int:
    return next(i for i, call in enumerate(calls) if call.startswith(prefix))


def first_copy_of(calls: list[str], path: str) -> int:
    """The first `docker cp` out of a created container of `path`. The stub names a container
    after the image it was made from (`cid-<image>`), so the call is not one fixed string."""
    return next(
        i for i, call in enumerate(calls) if call.startswith("cp cid-") and f":{path} " in call
    )


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


@pytest.mark.skipif(not _gnu_date(), reason="the record is stamped with GNU `date -Is`")
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


# ------------------------------------------------------------------ the vault (M31.3.2.2)
def test_a_release_applies_its_own_vault_changes_before_anything_runs_its_image(
    tmp_path: Path,
) -> None:
    """Owner decision 2 of needs-rupash 114: the new image's own apply script, copied out of the
    image, runs with the deploy token before the candidate starts, so the application that passes
    the gate is the one written against those policies. Delete this and the apply can drift after
    the gate, where an application needing a new grant is held back for want of it, or stop reading
    the token from where the server keeps it."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, deploy_token=True, apply_exit=0)

    assert ran.code == 0, ran.output
    assert ran.applied == f"applied with {(tmp_path / 'deploy.token').as_posix()}"
    copied = first_copy_of(ran.calls, "/app/ops/openbao/.")
    started = first(ran.calls, "run -d --name brain-candidate-")
    assert copied < started
    assert ran.running == NEW
    assert [one["outcome"] for one in ran.records] == ["deployed"]
    assert "a-deploy-token" not in ran.output


def test_a_release_whose_vault_changes_do_not_take_is_held_back_before_the_gate(
    tmp_path: Path,
) -> None:
    """Refused loudly: the image is held back exactly as one that never answers ready, the app is
    untouched and no candidate is started. Delete this and a release can go live against a vault
    that refused its policies, and fail at its first secret instead of at the deploy."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, deploy_token=True, apply_exit=1)

    assert ran.code == 1
    assert "vault policies, engines or roles did not take" in ran.output
    assert not any(call.startswith(("run ", "compose")) for call in ran.calls)
    assert ran.running == OLD
    assert [one["outcome"] for one in ran.records] == ["held_back"]


def test_a_server_with_no_deploy_token_says_so_and_deploys_as_before(tmp_path: Path) -> None:
    """An install whose vault is still opened by people has no deploy token, and its deploys must go
    on. Delete this and every deploy on such a server stops until somebody moves its vault, or the
    note that its vault changes were not applied disappears."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, deploy_token=False, apply_exit=0)

    assert ran.code == 0, ran.output
    assert "no deploy token" in ran.output
    assert ran.applied == ""
    assert ran.running == NEW


def test_an_image_from_before_the_vault_changes_shipped_deploys_as_before(tmp_path: Path) -> None:
    """An older image carries no `ops/openbao`, which is not a failure: it has nothing to apply.
    Delete this and a rollback to an older image is held back by the vault step for ever."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, deploy_token=True, apply_exit=None)

    assert ran.code == 0, ran.output
    assert "carries no vault changes" in ran.output
    assert ran.running == NEW


# ------------------------------------------------------------ the staff accounts client (M1.6.16)
def test_once_the_app_is_ready_the_release_s_accounts_client_step_runs_against_it(
    tmp_path: Path,
) -> None:
    """The release's own `ops/keycloak/accounts-client.sh`, copied out of the application after it
    answers ready and run here pointed at it, so every install upgraded into the release gets the
    staff sync's accounts client with nobody doing anything. Delete this and the step can run
    before the application that keeps the secret is up, or not at all on an upgraded install."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, accounts_exit=0)

    assert ran.code == 0, ran.output
    assert ran.accounts == f"ran with app-{UUID}"
    copied = first(ran.calls, f"cp app-{UUID}:/app/ops/keycloak/accounts-client.sh")
    assert first(ran.calls, "compose up") < copied
    assert [one["outcome"] for one in ran.records] == ["deployed"]


def test_an_accounts_client_step_that_fails_is_said_and_the_deploy_still_succeeds(
    tmp_path: Path,
) -> None:
    """The application is healthy and serving, so a sign-in service that refused is a line in the
    journal and the step is tried again on the next deploy. Delete this and a Keycloak with a
    changed administrator password rolls back or fails every release."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, accounts_exit=1)

    assert ran.code == 0, ran.output
    assert "ACCOUNTS CLIENT NOT SET UP" in ran.output
    assert ran.running == NEW
    assert [one["outcome"] for one in ran.records] == ["deployed"]


def test_an_image_held_back_or_older_than_the_step_never_runs_it(tmp_path: Path) -> None:
    """A held-back image never reaches the step, and an image from before it shipped says so and
    deploys. Delete this and the step can run against an application that never answered ready,
    or an older image's missing script can fail its deploy."""
    (tmp_path / "held").mkdir()
    (tmp_path / "older").mkdir()
    held = deploy(tmp_path / "held", running=OLD, good={OLD}, accounts_exit=0)
    older = deploy(tmp_path / "older", running=OLD, good={OLD, NEW}, accounts_exit=None)

    assert held.code == 1
    assert held.accounts == ""
    assert older.code == 0, older.output
    assert "carries no accounts client step" in older.output


# ------------------------------------------------------- the optional services step (M32.2.1.1)
def test_once_the_app_and_its_workers_are_ready_the_release_s_optional_services_step_runs(
    tmp_path: Path,
) -> None:
    """The release's own `ops/deploy/overlays/apply.sh`, copied out of the image just deployed and
    run here with the application's container, after the application and every sibling were
    recreated: a recreate drops the joins the step makes, so the step has to come after the last
    one. Delete this and the step can run before the worker is recreated, which leaves the worker
    off the detector's network until the next deploy, or not run at all."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, containers=INSTALL, overlays_exit=0)

    assert ran.code == 0, ran.output
    assert ran.overlays == f"ran with app-{UUID}"
    copied = first_copy_of(ran.calls, "/app/ops/deploy/overlays/.")
    recreated = max(i for i, call in enumerate(ran.calls) if call.startswith("compose up"))
    assert recreated < copied
    assert [one["outcome"] for one in ran.records] == ["deployed"]


def test_an_optional_services_step_that_fails_is_said_and_the_deploy_still_succeeds(
    tmp_path: Path,
) -> None:
    """The application is serving, so a service that did not start is a line in the journal and is
    tried again on the next deploy. Delete this and a detector that is slow to load rolls back or
    fails every release."""
    ran = deploy(tmp_path, running=OLD, good={OLD, NEW}, overlays_exit=1)

    assert ran.code == 0, ran.output
    assert "OPTIONAL SERVICES NOT ALL STARTED" in ran.output
    assert ran.running == NEW
    assert [one["outcome"] for one in ran.records] == ["deployed"]


def test_an_image_held_back_or_older_than_the_optional_services_step_never_runs_it(
    tmp_path: Path,
) -> None:
    """A held-back image never reaches the step, and an image from before it shipped says so and
    deploys. Delete this and the step can start services beside an application that never answered
    ready, or a rollback to an older image fails for want of a script it never had."""
    (tmp_path / "held").mkdir()
    (tmp_path / "older").mkdir()
    held = deploy(tmp_path / "held", running=OLD, good={OLD}, overlays_exit=0)
    older = deploy(tmp_path / "older", running=OLD, good={OLD, NEW}, overlays_exit=None)

    assert held.code == 1
    assert held.overlays == ""
    assert older.code == 0, older.output
    assert "carries no optional services step" in older.output


# ------------------------------------------------ a service is left running when nothing changed
#: Two fingerprints of what a worker runs, as `brain.ops.restart_scope` writes them: sixty-four
#: lower-case hexadecimal characters. Not made by the module under test, because a fixture the
#: producer made would be the producer agreeing with itself; the end-to-end test below makes real
#: ones.
FP_A = "a" * 64
FP_B = "b" * 64


def manifest_text(fingerprint: str | None) -> str:
    """The `RELEASE.json` text CI writes into an image, made by the manifest's own writer, so the
    script reads the indented form the producer produces and not one this file imagined."""
    from datetime import UTC, datetime

    from brain.ops.release_manifest import ReleaseManifest
    from brain.ops.restart_scope import WORKER_FINGERPRINT_KEY

    return ReleaseManifest(
        commit="0" * 40,
        built_at=datetime(2019, 1, 1, tzinfo=UTC),
        extra={} if fingerprint is None else {WORKER_FINGERPRINT_KEY: fingerprint},
    ).to_json()


def recreated(ran: Ran) -> list[str]:
    """The services `docker compose up` was run for, in order, by name."""
    return [call.rsplit(" ", 1)[1] for call in ran.calls if call.startswith("compose up")]


def test_a_service_whose_image_runs_the_same_files_as_the_new_one_is_left_running(
    tmp_path: Path,
) -> None:
    """The merge changed nothing a worker runs (documents, a test, the console's source), so the
    two images carry one fingerprint: the app is recreated, because it serves what changed, and
    each worker keeps its container, its process and the acceptance run in it. The deployment
    record says which were kept, and the line is one `brain.ops.deployments` still parses.

    Delete this and every merge kills the worker again, which is what ended an acceptance run
    thirty-five minutes long on the owner's install every few minutes through a night."""
    from datetime import datetime

    from brain.ops.deployments import Deployment

    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={OLD: manifest_text(FP_A), NEW: manifest_text(FP_A)},
    )

    assert ran.code == 0, ran.output
    assert recreated(ran) == ["app"]
    assert ran.running == NEW
    assert ran.containers[f"brain-worker-{UUID}"][4] == OLD
    assert ran.containers[f"brain-parse-worker-{UUID}"][4] == OLD
    assert "brain-worker is left running" in ran.output
    assert ran.records[0]["outcome"] == "deployed"
    assert ran.records[0]["services_updated"] == ""
    assert ran.records[0]["services_kept"] == "brain-worker,brain-parse-worker"
    assert ran.records[0]["services_failed"] == ""
    line = {**ran.records[0], "at": datetime(2019, 1, 1).astimezone().isoformat()}
    assert Deployment.from_line(json.dumps(line)).outcome == "deployed"


def test_a_service_whose_image_differs_in_what_a_worker_runs_is_recreated(tmp_path: Path) -> None:
    """The sibling of the test above: with different fingerprints every service follows the app as
    it always did. A rule tested only by the case where it leaves things alone is satisfied by a
    script that never recreates a worker.

    Delete this and the worker can stay on old code for ever, with everything else green."""
    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={OLD: manifest_text(FP_A), NEW: manifest_text(FP_B)},
    )

    assert ran.code == 0, ran.output
    assert recreated(ran) == ["app", "brain-worker", "brain-parse-worker"]
    assert ran.containers[f"brain-worker-{UUID}"][4] == NEW
    assert ran.records[0]["services_updated"] == "brain-worker,brain-parse-worker"
    assert ran.records[0]["services_kept"] == ""


def test_each_service_is_judged_by_the_image_it_is_running_and_not_by_the_apps(
    tmp_path: Path,
) -> None:
    """A worker an earlier deploy failed to move can be two images behind while its neighbour is one
    behind, and the app's own previous image says nothing about either. The one whose image has
    the new fingerprint is kept and the one that has not is recreated.

    Delete this and the comparison can be made against the app's image, which leaves a stale worker
    running whenever the app was current and the worker was not."""
    older = "sha256:older"
    stale = (INSTALL[0], INSTALL[1].replace(OLD, older), *INSTALL[2:])
    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD, NEW},
        containers=stale,
        manifests={
            OLD: manifest_text(FP_A),
            older: manifest_text(FP_B),
            NEW: manifest_text(FP_A),
        },
    )

    assert ran.code == 0, ran.output
    assert recreated(ran) == ["app", "brain-parse-worker"]
    assert ran.records[0]["services_kept"] == "brain-worker"
    assert ran.records[0]["services_updated"] == "brain-parse-worker"


@pytest.mark.parametrize(
    ("label", "manifests", "unopenable", "recreate_all"),
    [
        ("the running image carries no fingerprint", {NEW: FP_A}, (), False),
        ("the new image carries no fingerprint", {OLD: FP_A}, (), False),
        ("neither image carries one", {}, (), False),
        (
            "both carry a value that is not sixty-four hexadecimal",
            {OLD: "a" * 63, NEW: "a" * 63},
            (),
            False,
        ),
        ("both carry an upper-case value", {OLD: "A" * 64, NEW: "A" * 64}, (), False),
        ("the running image cannot be opened", {OLD: FP_A, NEW: FP_A}, (OLD,), False),
        ("the new image cannot be opened", {OLD: FP_A, NEW: FP_A}, (NEW,), False),
        ("the operator asks for everything to be recreated", {OLD: FP_A, NEW: FP_A}, (), True),
    ],
)
def test_every_doubt_about_whether_a_worker_changed_recreates_it(
    tmp_path: Path,
    label: str,
    manifests: dict[str, str | None],
    unopenable: tuple[str, ...],
    recreate_all: bool,
) -> None:
    """A worker is left alone only on proof, and each of these is a way of not having it: an image
    built before the fingerprint existed (which every install meets once), one that cannot be read,
    a value that is not a fingerprint, and the operator's own override. In each the worker is
    recreated as every deploy did before.

    Delete this and a missing or malformed fingerprint can read as 'nothing changed', which leaves a
    worker on old code with every check green: the quiet direction to be wrong in. (case: {label})
    """
    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={image: manifest_text(fp) for image, fp in manifests.items()},
        unopenable=unopenable,
        recreate_all=recreate_all,
    )

    assert ran.code == 0, f"{label}: {ran.output}"
    assert recreated(ran) == ["app", "brain-worker", "brain-parse-worker"], label
    assert ran.records[0]["services_kept"] == "", label


def test_when_the_new_image_has_no_fingerprint_no_running_image_is_opened_to_compare(
    tmp_path: Path,
) -> None:
    """With nothing to compare against there is nothing to learn from the running images, so none
    is opened, and each worker is recreated.

    Delete this and every deploy of an image without a fingerprint creates a container from each
    worker's image for an answer that cannot matter."""
    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={OLD: manifest_text(FP_A)},
    )

    assert recreated(ran) == ["app", "brain-worker", "brain-parse-worker"]
    assert not any(call.startswith(f"create {OLD}") for call in ran.calls)


def test_an_image_the_gate_held_back_leaves_every_worker_alone_whatever_its_fingerprint(
    tmp_path: Path,
) -> None:
    """The comparison is made after the app is ready on the new image and never before, so a held
    back image reads no fingerprint and recreates nothing.

    Delete this and a fingerprint read can move in front of the gate, which is where a decision
    about a worker would be made on an image that never answered ready."""
    ran = deploy(
        tmp_path,
        running=OLD,
        good={OLD},
        containers=INSTALL,
        manifests={OLD: manifest_text(FP_A), NEW: manifest_text(FP_B)},
    )

    assert ran.code == 1
    assert recreated(ran) == []
    # The task ids are read from the tag; a fingerprint is read from an image id, and none was.
    assert not any(call.startswith("cp cid-sha256:") for call in ran.calls)


def test_what_ci_writes_for_a_documents_only_merge_is_what_the_script_leaves_a_worker_for(
    tmp_path: Path,
) -> None:
    """The producer and the consumer together, from a real repository and not a fixture of either:
    three commits (the start, a change to a build document and a test, then a change to the
    application's source), each turned into a `RELEASE.json` by `build_manifest` as CI does. The
    script run between the first two leaves the worker running, and between the last two recreates
    it.

    Delete this and the fingerprint's format and the script's reading of it can drift apart, each
    right by its own test, and a worker is then restarted by every merge again or never at all."""
    import subprocess

    from brain.ops.release_manifest import build_manifest

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    def write(name: str, text: str) -> None:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        git("add", "-A")

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Test")
    write("src/brain/thing.py", "VALUE = 1\n")
    write("docs/page.md", "one\n")
    write("tests/test_thing.py", "def test_x() -> None: ...\n")
    git("commit", "-q", "-m", "start")
    start = build_manifest(repo).to_json()
    write("docs/page.md", "two\n")
    write("tests/test_thing.py", "def test_y() -> None: ...\n")
    git("commit", "-q", "-m", "documents and a test")
    documents = build_manifest(repo).to_json()
    write("src/brain/thing.py", "VALUE = 2\n")
    git("commit", "-q", "-m", "the application")
    application = build_manifest(repo).to_json()

    (tmp_path / "quiet").mkdir()
    (tmp_path / "loud").mkdir()
    quiet = deploy(
        tmp_path / "quiet",
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={OLD: start, NEW: documents},
    )
    loud = deploy(
        tmp_path / "loud",
        running=OLD,
        good={OLD, NEW},
        containers=INSTALL,
        manifests={OLD: documents, NEW: application},
    )

    assert quiet.code == 0, quiet.output
    assert recreated(quiet) == ["app"]
    assert loud.code == 0, loud.output
    assert recreated(loud) == ["app", "brain-worker", "brain-parse-worker"]
