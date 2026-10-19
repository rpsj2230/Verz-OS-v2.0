#!/bin/sh
# What only the host can see of the automation canvas once it is running, handed to the application
# to keep for this release (python -m brain.ops.automation_report keep). Run by apply.sh after the
# canvas is started and waited for. Facts only: the application's checks decide what they mean
# (brain.ops.acceptance_checks_automation_canvas), and this decides nothing.
#
# WHAT IT ASKS DOCKER, and why only the host can. Which networks the canvas and its proxy sit on
# (the canvas must sit on its own internal network and the tool network and no other); the NAMES of
# the canvas's environment variables (never one value: a name is cut from `NAME=value` by a filter
# here, before anything leaves this script, so no secret is read into a file, a log or a pipe the
# application sees) and how many of the values are connection strings, counted by a pattern that
# prints a number; whether the canvas has any default route (an internal network gives it none, so
# it has no way out that is not the proxy); the hostnames the running proxy was started with; and
# what the proxy answers when it is asked, from its own address, to open a tunnel to a name that is
# on no list. `.invalid` is reserved never to resolve, so a proxy that wrongly let it through would
# still reach nothing.
#
# A FACT IT CANNOT GET IS REPORTED AS NOT KNOWN, never as the good answer. A route count read from
# nothing would be zero, and zero is the answer the check is hoping for, so the count is printed
# only when the routing table was actually read (its header line is seen) and is `unknown` otherwise.
#
# WHAT IT NEVER DOES. Print the value of any variable, send anything to the internet, or change a
# container. The probe is a request to the proxy's own port from inside the proxy's own container.
#
# Task ids: M32.6.1.2
set -eu

APP="${BRAIN_APP_CONTAINER:?the step names the application container}"

say() { printf 'overlays: automation: %s\n' "$*"; }

project="$(docker inspect "$APP" --format '{{index .Config.Labels "com.docker.compose.project"}}' \
  2>/dev/null || true)"
if [ -z "$project" ]; then
  say "the application carries no compose project label, so the canvas cannot be found"
  exit 1
fi
overlays="${project}-overlays"

named() {
  docker ps --filter "label=com.docker.compose.project=$overlays" \
    --filter "label=com.docker.compose.service=$1" --format '{{.Names}}' | head -n 1
}
canvas="$(named activepieces || true)"
proxy="$(named automation-egress || true)"
if [ -z "$canvas" ] || [ -z "$proxy" ]; then
  say "the canvas or its proxy is not running, so there is nothing to report"
  exit 1
fi

networks_of() {
  docker inspect "$1" \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}'
}
# Every variable the container was created with, as `NAME=value`. It is read only through the two
# filters that use it below: one cuts the value off and one prints a count.
environment_of() {
  docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}'
}

code=0
said="$({
  networks_of "$canvas" | sed -n 's/^\(..*\)$/net|\1/p'
  networks_of "$proxy" | sed -n 's/^\(..*\)$/proxynet|\1/p'
  environment_of "$canvas" | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*$/env|\1/p'
  # The schemes are brain.ops.automation._CONNECTION_SCHEMES, held equal by a test.
  printf 'connstr|%s\n' "$(environment_of "$canvas" |
    grep -ciE '^[A-Za-z_][A-Za-z0-9_]*=(postgres|postgresql|postgresql\+psycopg|redis|rediss|amqp|mongodb)://' ||
    true)"
  docker exec "$canvas" cat /proc/net/route 2>/dev/null |
    awk 'NR == 1 && $1 == "Iface" { seen = 1 }
         NR > 1 && $2 == "00000000" { n++ }
         END { if (seen) printf "routes|%d\n", n + 0; else print "routes|unknown" }'
  docker exec "$proxy" cat /etc/squid/squid.conf 2>/dev/null |
    sed -n 's/^acl allowed_sources dstdomain \(..*\)$/allow|\1/p'
  printf 'probe|%s\n' "$(docker exec "$proxy" timeout 10 bash -c \
    'ip=$(hostname -i | cut -d" " -f1); exec 3<>"/dev/tcp/$ip/3128"; printf "CONNECT unlisted.invalid:443 HTTP/1.1\r\nHost: unlisted.invalid:443\r\n\r\n" >&3; head -n 1 <&3' \
    2>/dev/null | tr -d '\r' || true)"
} | docker exec -i "$APP" python -m brain.ops.automation_report keep)" || code=$?
printf '%s\n' "$said" | sed -n 's/^SAY /overlays: automation: /p'
exit "$code"
