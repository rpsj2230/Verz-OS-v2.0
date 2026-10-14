#!/bin/sh
# What the automation canvas's compose file expects to find on the server before it starts, put
# there by the release rather than by a person. Run by apply.sh before the canvas is composed, on
# the host, as root; idempotent, so it runs on every deploy and changes nothing the second time.
#
# 1. The egress proxy's allowlist, which the compose file mounts at an absolute path: copied from the
#    image if it is not there, never overwritten (an install may have tuned it). It is the only
#    thing between a flow somebody on the client's staff assembled and the internet, and a proxy
#    whose file is missing starts with no allowlist and looks exactly like one that has it, which is
#    why the compose file mounts an absolute path and this puts a file there first.
#    `docs/install/coolify.md` step 3 is this, done by hand.
# 2. The canvas's three secrets, minted on this server from /dev/urandom the first time and kept in
#    the environment file only root can read: its own database password, the key it encrypts its
#    stored credentials with (32 hexadecimal characters, the length the canvas requires) and the
#    secret it signs sessions with. None is the application's, and the application's database
#    password is never given to the canvas.
# 3. The address staff open the editor on. Not a secret and not something this server can know: an
#    install that gives the canvas an address of its own writes it into the environment file and it
#    is kept. Until then it names the service, which the canvas accepts and which no browser can
#    reach, so the editor is unreachable by staff, and says nothing wrong, until the address is set.
#
# Task ids: M32.6.1.1
set -eu

SETTINGS="${BRAIN_OVERLAYS_SETTINGS:?the step names the settings directory}"
ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf 'overlays: automation: %s\n' "$*"; }
fail() { say "$1"; exit 1; }
hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }

umask 077
mkdir -p "$SETTINGS/automation"
chmod 0700 "$SETTINGS"

# 1. the allowlist, never overwritten
if [ ! -f "$SETTINGS/automation/egress.conf" ]; then
  cp "$HERE/settings/automation/egress.conf" "$SETTINGS/automation/egress.conf" ||
    fail "the image carries no automation/egress.conf"
  chmod 0644 "$SETTINGS/automation/egress.conf"
fi

# 2. secrets, minted once
touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"
mint() {
  grep -q "^$1=." "$ENV_FILE" || printf '%s=%s\n' "$1" "$(hex "$2")" >> "$ENV_FILE"
}
mint AUTOMATION_DB_PASSWORD 24
mint AUTOMATION_ENCRYPTION_KEY 16
mint AUTOMATION_JWT_SECRET 32

# 3. the address, kept when an install has set it
grep -q "^AUTOMATION_PUBLIC_URL=." "$ENV_FILE" ||
  printf 'AUTOMATION_PUBLIC_URL=http://activepieces\n' >> "$ENV_FILE"

say "allowlist, secrets and address are in place"
