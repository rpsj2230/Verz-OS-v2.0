#!/bin/sh
# Deploy the current published image to the VPS, without going through the Coolify UI.
#
# Coolify writes the compose file and its env to disk and runs the stack from there, so
# this drives exactly what "Restart (pull latest)" in the UI drives: same file, same
# project name, same environment. Coolify reads container state rather than owning it, so
# its dashboard reflects the result correctly.
#
# This exists because every deploy otherwise needed someone to click a button, which made
# progress depend on a person being at a screen.
#
# Usage:
#   set -a; . ./.env; set +a      # DEPLOY_HOST, DEPLOY_UUID and DEPLOY_URL live there
#   ops/deploy.sh
#
# Task ids: M38.1.3

set -eu

# **The three values below have no defaults, and until 2026-09-09 they had one deployment's.**
# A shell fallback is the same defect as writing the host into the source, with the extra
# property that removing the value from the environment file changes nothing: the fallback
# answers first, so the file looks clean and the script still reaches that machine. A refusal
# costs one line in a shell profile; a wrong default costs a deploy onto somebody else's box,
# and the failure only shows up if that box happens to answer differently.
#
# `:?` rather than a hand-written test because `set -eu` is already on and the message it
# prints names the variable, which is the whole of what a reader needs. This is the shape the
# compose files already use for `KEYCLOAK_DB_PASSWORD`.
HOST="${DEPLOY_HOST:?set DEPLOY_HOST to the ssh destination; see ops/DEPLOY.md}"
UUID="${DEPLOY_UUID:?set DEPLOY_UUID to the Coolify service identifier; see ops/DEPLOY.md}"
URL="${DEPLOY_URL:?set DEPLOY_URL to the address this deployment answers on}"
DIR="/data/coolify/services/$UUID"
# These two are the product's own coordinates rather than a deployment's: every install pulls
# the same published image, so a default here is a fact about what is being deployed and not
# about where.
REPO="${DEPLOY_REPO:-rpsj2230/verz-brain-v2.0}"
IMAGE="${DEPLOY_IMAGE:-ghcr.io/rpsj2230/verz-brain-v2.0}"

echo "==> deploying to $HOST ($UUID)"

# A signature nothing checks is a signature that silently stops being made. This verifies
# on the server, before the image is pulled, that what is about to run was built by this
# repository's own workflow, not merely that it exists in the registry.
#
# cosign is optional here rather than required: a machine without it should not be unable
# to deploy, but it must say so rather than passing quietly. Skipping a check and passing
# a check look identical unless one of them is loud.
ssh -o BatchMode=yes "$HOST" "
  if command -v cosign >/dev/null 2>&1; then
    if cosign verify '$IMAGE:latest'         --certificate-identity-regexp '^https://github.com/$REPO/'         --certificate-oidc-issuer https://token.actions.githubusercontent.com         >/dev/null 2>&1; then
      echo '    signature verified against $REPO'
    else
      echo '    SIGNATURE DID NOT VERIFY - refusing to deploy' >&2
      exit 1
    fi
  else
    echo '    cosign not installed on $HOST; signature NOT checked'
  fi
"

# The SHA the image was built from, so /health/ready reports what is actually running
# rather than "unknown". Coolify's .env has no value for it and the compose default fills
# in "unknown", which makes the health endpoint disagree with the status page.
SHA="${DEPLOY_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo unknown)}"
echo "==> commit $SHA"

ssh -o BatchMode=yes "$HOST" "
  set -eu
  cd '$DIR'
  export BRAIN_COMMIT_SHA='$SHA'
  echo '--- pulling ---'
  docker compose pull 2>&1 | grep -E 'Pulled|Error' || true
  echo '--- recreating ---'
  docker compose up -d --remove-orphans 2>&1 | grep -E 'Started|Error|Recreated' || true
"

echo "==> waiting for readiness"
for i in $(seq 1 30); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$URL/health/ready" || echo 000)
  [ "$code" = "200" ] && break
  sleep 3
done

if [ "$code" != "200" ]; then
  echo "FAILED: /health/ready returned $code after 90s" >&2
  ssh -o BatchMode=yes "$HOST" "docker logs --tail 30 app-$UUID 2>&1 | tail -30" >&2
  exit 1
fi

echo "==> live"
# Split on commas first. Matching commit and percent in one pattern picked up
# commit_subject instead, because .* is greedy, and it reported 0% while the real
# figure was 8%, which is exactly the kind of wrong number this script exists to avoid.
# Only the top-level figures. Every wave object also carries "done" and "percent", so
# without the head the same fields print nine more times with per-wave values.
curl -sk --max-time 15 "$URL/api/status.json" \
  | tr ',' '\n' \
  | sed -n -e 's/^"commit":"\([^"]*\)"$/    commit \1/p' \
           -e 's/^"done":\([0-9]*\)$/    \1 tasks done/p' \
           -e 's/^"percent":\([0-9.]*\)$/    \1% complete/p' \
  | head -3

# The migrate container is expected to exit; it runs migrations and stops. Exit 0 is
# success, anything else is a failed migration and worth seeing immediately.
echo "==> migrations"
ssh -o BatchMode=yes "$HOST" "
  code=\$(docker inspect migrate-$UUID --format '{{.State.ExitCode}}' 2>/dev/null || echo '?')
  if [ \"\$code\" = '0' ]; then
    echo '    migrations applied cleanly'
  else
    echo \"    MIGRATION FAILED (exit \$code):\"
    docker logs --tail 12 migrate-$UUID 2>&1 | sed 's/^/      /'
  fi
"
