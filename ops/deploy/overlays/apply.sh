#!/bin/sh
# The optional services this install has switched on, started beside the application by the
# release itself. Copied out of the image by the server's deploy hook (ops/deploy/brain-deploy,
# apply_overlays) and run on the host once the application is ready, with the application's
# container name as its one argument. It is in the image so that what it does is exactly what
# the release was tested against, and so that changing it never needs anybody on the server.
#
# WHAT IT DECIDES: NOTHING. It writes down what the server holds (the machine's memory, every
# running container's limit, what each container without a limit is using) and hands that to
# `python -m brain.ops.overlays plan` inside the application, which reads INSTALL_SERVICES and
# answers with the compose files to start, the networks to join and what to say. The arithmetic
# is in that module, where it is tested; a shell loop that decided whether a container fits
# would be arithmetic nobody can test on somebody else's server.
#
# WHERE THE SERVICES RUN. As their own compose project, named after the application's with
# `-overlays` on the end, on the product's own compose files copied out of the same image.
# Never inside the application's project: on Coolify that project is the panel's copy of the
# compose file, and anything added to it by hand is a change the next release does not know
# about. A service's networks are the ones its compose file declares, and the application's
# containers named by a JOIN line are joined to them, so the application reaches it by service
# name and nothing else does. A deploy recreates those containers and drops the join, which is
# why this runs after every deploy and joins again.
#
# WHAT AN OVERLAY MAY NEED FIRST. A START line opens an overlay and its PREPARE lines name scripts
# beside this one that put on the server what its compose files expect: settings files, secrets
# minted on this server, a database (langfuse.prepare.sh says what the trace ledger needs). An
# overlay whose preparation fails is left out and the others start. The secrets are kept in an
# environment file only root can read, under the settings directory the product's compose files
# already name, and handed to compose with --env-file; nothing here prints one.
#
# WHAT IT REPORTS. Once the services are started and waited for, docker's own account of each
# (its memory limit, state and health) goes to `python -m brain.ops.overlays observe`, which keeps
# it for the release, so the install's checks can read what only the host can see.
#
# WHAT IT NEVER DOES. Stop anything when no plan could be made (brain.ops.overlays,
# A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING), remove a volume, or fail the deploy: the
# application is already serving, and a service that would not start is said in the journal.
#
# Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2
set -eu

APP="${1:?usage: apply.sh <application container>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# Overridable for tests/unit/test_overlays.py, which runs this on machines with no /proc.
MEMINFO="${BRAIN_OVERLAYS_MEMINFO:-/proc/meminfo}"
# Where the product's compose files expect settings files (docs/install/coolify.md, step 3), and
# the environment file the overlays' secrets are kept in. Overridable for the same tests.
SETTINGS="${BRAIN_OVERLAYS_SETTINGS:-/opt/brain/settings}"
ENV_FILE="${BRAIN_OVERLAYS_ENV:-$SETTINGS/overlays.env}"

say() { printf 'overlays: %s\n' "$*"; }

project="$(docker inspect "$APP" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
if [ -z "$project" ]; then
  say "$APP carries no compose project label, so there is no project to start services beside"
  exit 1
fi
overlays="${project}-overlays"
# The image the application runs, which an overlay built from this product's own image (the
# script sandbox) is started from. Exported for compose's interpolation and nothing else.
APP_IMAGE="$(docker inspect "$APP" --format '{{.Config.Image}}')"
export APP_IMAGE

facts="$(mktemp)"
planned="$(mktemp)"
trap 'rm -f "$facts" "$planned"' EXIT

{
  echo "## meminfo"
  cat "$MEMINFO"
  echo "## inspect"
  docker ps -q | xargs -r docker inspect \
    --format '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.HostConfig.Memory}}'
  echo "## stats"
  docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}'
  echo "## runtimes"
  docker info --format '{{range $name, $_ := .Runtimes}}{{println $name}}{{end}}'
} > "$facts"

if ! docker exec -i "$APP" python -m brain.ops.overlays plan --project "$overlays" \
    < "$facts" > "$planned"; then
  sed -n 's/^SAY /overlays: /p' "$planned"
  say "no plan, so every optional service is left as it is"
  exit 1
fi
sed -n 's/^SAY /overlays: /p' "$planned"

# Each overlay's lines, kept only when its preparation succeeded.
files=""
waits=""
afters=""
joins="$(mktemp)"
trap 'rm -f "$facts" "$planned" "$joins"' EXIT
current=""
skipped=""
anyskipped=""
while IFS= read -r line; do
  case "$line" in
    "START "*) current="${line#START }"; skipped="" ;;
    "PREPARE "*)
      if [ -z "$skipped" ] && ! BRAIN_OVERLAYS_SETTINGS="$SETTINGS" BRAIN_OVERLAYS_ENV="$ENV_FILE" \
          BRAIN_APP_PROJECT="$project" sh "$HERE/${line#PREPARE }" < /dev/null; then
        say "$current is not started: its preparation did not finish"
        skipped=1
        anyskipped=1
      fi ;;
    "FILE "*) [ -n "$skipped" ] || files="$files -f $HERE/${line#FILE }" ;;
    "JOIN "*) [ -n "$skipped" ] || echo "$line" >> "$joins" ;;
    "WAIT "*) [ -n "$skipped" ] || waits="$waits ${line#WAIT }" ;;
    "AFTER "*) [ -n "$skipped" ] || afters="$afters ${line#AFTER }" ;;
  esac
done < "$planned"

envfile=""
[ -f "$ENV_FILE" ] && envfile="--env-file $ENV_FILE"
# A service is removed when it is no longer switched on, and never because its preparation failed
# this time: with an overlay left out, its running containers would read as orphans.
orphans="--remove-orphans"
[ -z "$anyskipped" ] || orphans=""

if [ -z "$files" ] && [ -n "$anyskipped" ]; then
  say "nothing else to start, and nothing is stopped while a preparation has not finished"
  exit 1
fi
if [ -z "$files" ]; then
  if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$overlays")" ]; then
    say "stopping the optional services no longer switched on; their volumes are kept"
    docker compose -p "$overlays" down
  fi
  exit 0
fi

# Started first and joined straight away, and only then waited for: the worker's acceptance run
# can begin within minutes of the worker being recreated, and a join that waited for the detector
# to load its model would leave the worker off its network for those minutes.
# shellcheck disable=SC2086 # $files is a list of -f arguments, split on purpose.
if ! docker compose -p "$overlays" $envfile $files up -d $orphans; then
  say "docker compose could not start the optional services; docker compose -p $overlays ps says which"
  exit 1
fi

while read -r _ key services; do
  network="${overlays}_${key}"
  for service in $services; do
    docker ps --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=$service" --format '{{.Names}}' |
      while IFS= read -r container; do
        if docker inspect "$container" \
            --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' |
            grep -qxF "$network"; then
          continue
        fi
        if docker network connect "$network" "$container"; then
          say "joined $container to $network"
        else
          say "could not join $container to $network"
        fi
      done
  done
done < "$joins"

code=0
# Only the services the budget costs are waited for: a one-shot that provisions something exits,
# and waiting on it would read its success as a failure.
# shellcheck disable=SC2086
docker compose -p "$overlays" $envfile $files up -d --wait --wait-timeout 300 $waits || code=$?
if [ "$code" -ne 0 ]; then
  say "a service did not report healthy within five minutes; docker compose -p $overlays ps says which"
fi

# What the application must be handed from the server once the services run, such as keys
# minted here. A failure is said and changes nothing that runs.
for after in $afters; do
  if ! BRAIN_OVERLAYS_ENV="$ENV_FILE" BRAIN_APP_CONTAINER="$APP" sh "$HERE/$after" < /dev/null; then
    say "$after did not finish; it is tried again on the next deploy"
  fi
done

{
  docker info --format '{{range $name, $_ := .Runtimes}}{{println $name}}{{end}}' |
    sed -n 's/^\(..*\)$/runtime|\1/p'
  docker ps -aq --filter "label=com.docker.compose.project=$overlays" | xargs -r docker inspect \
    --format '{{index .Config.Labels "com.docker.compose.service"}}|{{.HostConfig.Memory}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.HostConfig.Runtime}}'
} | docker exec -i "$APP" python -m brain.ops.overlays observe | sed -n 's/^SAY /overlays: /p' || true
exit "$code"
