#!/bin/sh
# What the class pooler's compose file expects to find on the server before it starts, put there
# by the release. Run by apply.sh before the pooler is composed, on the host, as root; idempotent,
# and it rewrites everything every time, so the pooler always starts on this release's figures.
#
# 1. The pooler's configuration, written by the application from brain.ops.class_pools.render_ini
#    against the database the application's `db` service creates. It holds no secret and is
#    readable by the pooler's own user, which is not root.
# 2. The owner login the pooler's userlist holds, read by the application from its own settings
#    (Settings.owner_database_url, the one reader of it) straight into the environment file only
#    root can read. Never printed, never on a command line, never in the journal: what the
#    application writes goes to a file under umask 077 and is merged into that file.
# 3. The network the application's database is on, as the trace ledger's preparation finds it.
#
# A step that fails exits non-zero, which leaves the pooler out of this deploy and every process
# on the pooler it already had (brain.ops.class_pools,
# A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING).
#
# Task ids: M22.2.2
set -eu

SETTINGS="${BRAIN_OVERLAYS_SETTINGS:?the step names the settings directory}"
ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
PROJECT="${BRAIN_APP_PROJECT:?the step names the compose project of the application}"
APP="${BRAIN_APP_CONTAINER:?the step names the application container}"

say() { printf 'overlays: class-pools: %s\n' "$*"; }
fail() { say "$1"; exit 1; }

umask 077
mkdir -p "$SETTINGS/class-pools"
chmod 0700 "$SETTINGS"

login="$(mktemp)"
trap 'rm -f "$login" "$ENV_FILE.new" "$SETTINGS/class-pools/pgbouncer.ini.new"' EXIT

# 1. the configuration
db="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=db" --format '{{.Names}}' | head -n 1)"
[ -n "$db" ] || fail "no running db service in $PROJECT, so the pools have no database to point at"
name="$(docker exec "$db" printenv POSTGRES_DB)" || fail "$db names no POSTGRES_DB"
ini="$SETTINGS/class-pools/pgbouncer.ini"
if ! docker exec "$APP" python -m brain.ops.class_pools ini --database "$name" > "$ini.new"; then
  sed -n 's/^SAY /overlays: class-pools: /p' "$ini.new"
  fail "the configuration could not be written"
fi
chmod 0644 "$ini.new"
mv "$ini.new" "$ini"

# 2. the owner login, into the root-only environment file and nowhere else
if ! docker exec "$APP" python -m brain.ops.class_pools owner-login > "$login"; then
  # On a refusal the application wrote one SAY line and no value.
  sed -n 's/^SAY /overlays: class-pools: /p' "$login"
  fail "the owner login could not be read"
fi

# 3. the network the database is on
network="$(docker inspect "$db" \
  --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' |
  grep -v '^$' | head -n 1)"
[ -n "$network" ] || fail "$db is on no network the pooler could join"

touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"
grep -v -e '^BRAIN_CLASS_POOL_OWNER=' -e '^BRAIN_CLASS_POOL_OWNER_PASSWORD=' \
  -e '^BRAIN_CLASS_POOLS_INI=' -e '^BRAIN_APP_NETWORK=' "$ENV_FILE" > "$ENV_FILE.new" || true
cat "$login" >> "$ENV_FILE.new"
printf 'BRAIN_CLASS_POOLS_INI=%s\n' "$ini" >> "$ENV_FILE.new"
printf 'BRAIN_APP_NETWORK=%s\n' "$network" >> "$ENV_FILE.new"
chmod 0600 "$ENV_FILE.new"
mv "$ENV_FILE.new" "$ENV_FILE"

say "configuration, owner login and network are in place"
