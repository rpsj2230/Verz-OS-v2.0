#!/bin/sh
# The application's object store key pair, handed from the server to the application, which keeps
# it in the vault slot the store's client reads at start (python -m brain.ops.object_store keep).
# Run by apply.sh once the store is started. The two values go on standard input and never on a
# command line, and nothing here prints them; the application says only whether it kept them.
#
# THE APPLICATION CONNECTS WHEN IT NEXT STARTS. It builds its store client once, at start, from
# this slot, so a store switched on beside a running application is not used until the application
# is next recreated, which the next release does. The slot is kept again on every deploy and holds
# the same pair each time.
#
# Task ids: M32.3.1.4
set -eu

ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
APP="${BRAIN_APP_CONTAINER:?the step names the application container}"

access="$(sed -n 's/^OBJECT_STORE_ACCESS_KEY_ID=//p' "$ENV_FILE" | tail -n 1)"
secret="$(sed -n 's/^OBJECT_STORE_SECRET_ACCESS_KEY=//p' "$ENV_FILE" | tail -n 1)"
if [ -z "$access" ] || [ -z "$secret" ]; then
  echo "overlays: objectstore: the application's key pair is not in the environment file"
  exit 1
fi
code=0
said="$(printf '%s\n%s\n' "$access" "$secret" |
  docker exec -i "$APP" python -m brain.ops.object_store keep)" || code=$?
printf '%s\n' "$said" | sed -n 's/^SAY /overlays: objectstore: /p'
exit "$code"
