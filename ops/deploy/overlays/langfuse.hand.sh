#!/bin/sh
# The trace ledger's project keys, handed from the server to the application, which keeps them in
# the vault with its own token (python -m brain.ops.ledger_export keep). Run by apply.sh once the
# ledger is started. The keys go on standard input and never on a command line, and nothing here
# prints them; the application says only whether it kept them.
#
# Task ids: M32.1.2.6
set -eu

ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
APP="${BRAIN_APP_CONTAINER:?the step names the application container}"

public="$(sed -n 's/^LANGFUSE_INIT_PROJECT_PUBLIC_KEY=//p' "$ENV_FILE" | tail -n 1)"
private="$(sed -n 's/^LANGFUSE_INIT_PROJECT_SECRET_KEY=//p' "$ENV_FILE" | tail -n 1)"
if [ -z "$public" ] || [ -z "$private" ]; then
  echo "overlays: langfuse: the ledger's project keys are not in the environment file"
  exit 1
fi
code=0
said="$(printf '%s\n%s\n' "$public" "$private" |
  docker exec -i "$APP" python -m brain.ops.ledger_export keep)" || code=$?
printf '%s\n' "$said" | sed -n 's/^SAY /overlays: langfuse: /p'
exit "$code"
