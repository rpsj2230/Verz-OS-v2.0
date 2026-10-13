#!/bin/sh
# What the object store's compose file expects to find on the server before it starts, put there by
# the release rather than by a person. Run by apply.sh before the store is composed, on the host, as
# root; idempotent, so it runs on every deploy and changes nothing the second time.
#
# 1. The store's provisioning script, which the compose file mounts at an absolute path: copied from
#    the image if it is not there, never overwritten (an install may have tuned it).
#    `docs/install/coolify.md` step 3 is this, done by hand.
# 2. The application's key pair, minted on this server from /dev/urandom the first time and kept in
#    the environment file only root can read. It never leaves the server except to the vault, and
#    is never printed. objectstore.hand.sh gives it to the application once the store runs.
# 3. The application's identity in the store's access file, merged in from that key pair, replacing
#    only its own and leaving every other identity as it is (ops/deploy/overlays/s3-identity.sh):
#    the trace ledger keeps an identity in the same file. It may read, write and list and nothing
#    else, never administer a bucket: buckets are made once by the provisioning script.
#
# Task ids: M32.3.1.1, M32.3.1.4
set -eu

SETTINGS="${BRAIN_OVERLAYS_SETTINGS:?the step names the settings directory}"
ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=s3-identity.sh
. "$HERE/s3-identity.sh"

say() { printf 'overlays: objectstore: %s\n' "$*"; }
fail() { say "$1"; exit 1; }
hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }

umask 077
mkdir -p "$SETTINGS/seaweedfs"
chmod 0700 "$SETTINGS"

# 1. the provisioning script, never overwritten
if [ ! -f "$SETTINGS/seaweedfs/provision.sh" ]; then
  cp "$HERE/settings/seaweedfs/provision.sh" "$SETTINGS/seaweedfs/provision.sh" ||
    fail "the image carries no seaweedfs/provision.sh"
  chmod 0644 "$SETTINGS/seaweedfs/provision.sh"
fi

# 2. the application's key pair, minted once
touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"
mint() {
  grep -q "^$1=." "$ENV_FILE" || printf '%s=%s\n' "$1" "$(hex "$2")" >> "$ENV_FILE"
}
mint OBJECT_STORE_ACCESS_KEY_ID 16
mint OBJECT_STORE_SECRET_ACCESS_KEY 32

value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }

# 3. the application's identity in the access file
access="$(value OBJECT_STORE_ACCESS_KEY_ID)"
secret="$(value OBJECT_STORE_SECRET_ACCESS_KEY)"
merge_s3_identity brain-application "$access" "$secret" '["Read","Write","List"]' ||
  fail "the object store's access file could not be merged, so it is left as it is"

say "settings, key pair and access file are in place"
