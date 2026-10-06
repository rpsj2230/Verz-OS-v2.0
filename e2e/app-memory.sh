#!/bin/sh
# The application container's memory across a browser harness run, so a slow leak is a trend in
# the nightly log rather than a restart somebody notices months later.
#
# The application fills its container on purpose: `brain.runtime` starts as many workers as its
# memory limit allows, each one importing the whole application. Measured on 2026-10-06 that is
# about 872 MiB at rest in a 1024M cgroup, about 905 MiB after the specs, and flat after a minute
# idle. A figure that keeps rising between "after the specs" and "after idle", run after run, is
# the one to read.
#
#   sh e2e/app-memory.sh start           begin sampling anon every five seconds
#   sh e2e/app-memory.sh snapshot LABEL  the cgroup's anon and file, and each process's own
#   sh e2e/app-memory.sh report          every sample taken so far
#
# Reads only: the container's cgroup files on the runner and /proc inside the container.
#
# Task ids: M27.10.6

set -eu

SAMPLES="${RUNNER_TEMP:-/tmp}/app-anon.txt"

app=$(docker compose ps -q app)
stat="/sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' "$app").scope/memory.stat"

anon() {
  awk '$1 == "anon" { print $2 }' "$stat"
}

case "${1:-}" in
  start)
    # Detached from the step that starts it, so it outlives that step's shell.
    nohup sh "$0" sample > "$SAMPLES" 2>&1 &
    echo "sampling the application's anon memory every 5 s from $(date +%s)"
    ;;
  sample)
    while :; do
      printf '%s %s\n' "$(date +%s)" "$(anon)"
      sleep 5
    done
    ;;
  snapshot)
    echo "--- ${2:-now} at $(date +%s): cgroup anon=$(anon) file=$(awk '$1 == "file" { print $2 }' "$stat")"
    # pid, parent, RssAnon, RssFile, command: one line per process inside the container.
    docker exec "$app" python -c '
import pathlib
for p in sorted(pathlib.Path("/proc").glob("[0-9]*"), key=lambda x: int(x.name)):
    try:
        lines = (p / "status").read_text().splitlines()
        cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode()[:80]
    except OSError:
        continue
    status = dict(line.split(":", 1) for line in lines if ":" in line)
    if cmd.startswith("python -c"):
        continue
    print(p.name, status.get("PPid", "").strip(), status.get("RssAnon", "").strip(),
          status.get("RssFile", "").strip(), cmd)
'
    ;;
  report)
    echo "--- samples (unix seconds, anon bytes)"
    cat "$SAMPLES" 2>/dev/null || echo "no samples were taken"
    ;;
  *)
    echo "usage: sh e2e/app-memory.sh start | snapshot LABEL | report" >&2
    exit 64
    ;;
esac
