#!/bin/sh
# What the trace ledger's compose files expect to find on the server before they start, put
# there by the release rather than by a person. Run by apply.sh before the ledger is composed,
# on the host, as root; idempotent, so it runs on every deploy and changes nothing the second time.
#
# 1. The settings files the files mount: ClickHouse's memory ceiling and the object store's
#    provisioning script, copied from the image if they are not there, never overwritten (an
#    install may have tuned them). `docs/install/coolify.md` step 3 is this, done by hand.
# 2. The ledger's secrets and its project keys, minted on this server from /dev/urandom the first
#    time and kept in an environment file only root can read. They never leave the server and are never printed.
# 3. The object store's access file, written from those secrets every time, with one identity
#    that may read, write and list the ledger's bucket and nothing else. Never the repository's
#    placeholder identity: a placeholder key in a running store is a key anybody can read.
# 4. The ledger's database and its role in the application's PostgreSQL, the password set from
#    the environment file every time so the two cannot drift. The password goes to psql on
#    standard input, never on a command line another process can read.
# 5. The network the application's database is on, written for the attach file to join.
#
# Task ids: M32.1.1.1
set -eu

SETTINGS="${BRAIN_OVERLAYS_SETTINGS:?the step names the settings directory}"
ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
PROJECT="${BRAIN_APP_PROJECT:?the step names the compose project of the application}"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf 'overlays: langfuse: %s\n' "$*"; }
fail() { say "$1"; exit 1; }
hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }

umask 077
mkdir -p "$SETTINGS/langfuse" "$SETTINGS/seaweedfs"
chmod 0700 "$SETTINGS"

# 1. settings files, never overwritten
for pair in "langfuse/clickhouse-memory.xml" "seaweedfs/provision.sh"; do
  if [ ! -f "$SETTINGS/$pair" ]; then
    cp "$HERE/settings/$pair" "$SETTINGS/$pair" || fail "the image carries no $pair"
    chmod 0644 "$SETTINGS/$pair"
  fi
done

# 2. secrets, minted once
touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"
mint() {
  grep -q "^$1=." "$ENV_FILE" || printf '%s=%s\n' "$1" "$(hex "$2")" >> "$ENV_FILE"
}
mint LANGFUSE_POSTGRES_PASSWORD 32
mint LANGFUSE_CLICKHOUSE_PASSWORD 32
mint LANGFUSE_S3_ACCESS_KEY_ID 16
mint LANGFUSE_S3_SECRET_ACCESS_KEY 32
mint LANGFUSE_NEXTAUTH_SECRET 32
mint LANGFUSE_SALT 32
mint LANGFUSE_ENCRYPTION_KEY 32
# The ledger's project keys, in the shapes the ledger gives its own: its first start creates the
# project with them (langfuse.attach.yml), and langfuse.hand.sh gives them to the application,
# which keeps them in the vault (brain.ops.ledger_export).
grep -q "^LANGFUSE_INIT_PROJECT_PUBLIC_KEY=." "$ENV_FILE" ||
  printf 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-%s\n' "$(hex 16)" >> "$ENV_FILE"
grep -q "^LANGFUSE_INIT_PROJECT_SECRET_KEY=." "$ENV_FILE" ||
  printf 'LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-%s\n' "$(hex 32)" >> "$ENV_FILE"
# Not a secret: the address the ledger's own console calls itself. It is reached over the
# server's network only, so the default names the service; an install that gives it an address
# of its own writes that here and it is kept.
grep -q "^LANGFUSE_PUBLIC_URL=." "$ENV_FILE" ||
  printf 'LANGFUSE_PUBLIC_URL=http://langfuse-web:3000\n' >> "$ENV_FILE"

value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }

# 3. the object store's access file, from the secrets
access="$(value LANGFUSE_S3_ACCESS_KEY_ID)"
secret="$(value LANGFUSE_S3_SECRET_ACCESS_KEY)"
cat > "$SETTINGS/seaweedfs/s3.json.new" <<JSON
{
  "identities": [
    {
      "name": "langfuse",
      "credentials": [{ "accessKey": "$access", "secretKey": "$secret" }],
      "actions": ["Read:langfuse-events", "Write:langfuse-events", "List:langfuse-events"]
    }
  ]
}
JSON
chmod 0644 "$SETTINGS/seaweedfs/s3.json.new"
mv "$SETTINGS/seaweedfs/s3.json.new" "$SETTINGS/seaweedfs/s3.json"

# 4. the database and its role
db="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=db" --format '{{.Names}}' | head -n 1)"
[ -n "$db" ] || fail "no running db service in $PROJECT, so the ledger has no database to use"
user="$(docker exec "$db" printenv POSTGRES_USER)" || fail "$db names no POSTGRES_USER"
name="$(docker exec "$db" printenv POSTGRES_DB)" || fail "$db names no POSTGRES_DB"
password="$(value LANGFUSE_POSTGRES_PASSWORD)"
docker exec -i "$db" psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$name" <<SQL >/dev/null || fail "the ledger's database or role could not be made in $db"
DO \$\$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'langfuse') THEN
    ALTER ROLE langfuse WITH LOGIN PASSWORD '$password';
  ELSE
    CREATE ROLE langfuse WITH LOGIN PASSWORD '$password';
  END IF;
END \$\$;
SELECT 'CREATE DATABASE langfuse OWNER langfuse'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
SQL

# 5. the network the database is on, for langfuse.attach.yml
network="$(docker inspect "$db" \
  --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' |
  grep -v '^$' | head -n 1)"
[ -n "$network" ] || fail "$db is on no network the ledger could join"
grep -v '^BRAIN_APP_NETWORK=' "$ENV_FILE" > "$ENV_FILE.new" || true
printf 'BRAIN_APP_NETWORK=%s\n' "$network" >> "$ENV_FILE.new"
chmod 0600 "$ENV_FILE.new"
mv "$ENV_FILE.new" "$ENV_FILE"

say "settings, secrets, database and network are in place"
