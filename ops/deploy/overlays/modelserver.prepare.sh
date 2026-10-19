#!/bin/sh
# The weights the model server's chosen parts read, put in the volume before the server starts, by the
# release rather than by a person. Run by apply.sh before the server is composed, on the host, as root;
# idempotent, so it runs on every deploy and fetches nothing the second time.
#
# WHY IT IS A SEPARATE CONTAINER. The server's own network is internal and its weights volume is
# mounted read-only (docker-compose.inference.yml), so the server cannot fetch anything and a replaced
# file cannot appear under it. This runs the server's own image once, on docker's default network, with
# the volume writable, and the only program it runs is `inference_server.fetch`: it asks a public
# address for a public file. It is handed no document, no credential and no setting but the names of
# the parts, and it is not given the application's network.
#
# WHAT IT NEEDS FROM THE STEP. INFERENCE_PARTS, exported by apply.sh from the plan's ENV lines (the
# install's choice, not this script's), and the image's name, which the step derived from the
# application's or the overlays' environment file named. A part with nothing to fetch says so.
#
# A FAILURE LEAVES THE SERVER OUT OF THIS DEPLOY, and nothing already running is stopped. An install
# with no route out at this moment keeps whatever weights it already has: a file already in the volume
# and unchanged is not fetched again.
#
# Task ids: M7.3.3
set -eu

ENV_FILE="${BRAIN_OVERLAYS_ENV:?the step names the environment file}"
PARTS="${INFERENCE_PARTS:?the step exports the parts this install chose}"
PROJECT="${BRAIN_APP_PROJECT:?the step names the compose project of the application}"

say() { printf 'overlays: modelserver: %s\n' "$*"; }
fail() { say "$1"; exit 1; }

# The image, from the step's export or from the overlays' environment file an install may have set.
IMAGE="${INFERENCE_IMAGE:-}"
if [ -z "$IMAGE" ] && [ -f "$ENV_FILE" ]; then
  IMAGE="$(sed -n 's/^INFERENCE_IMAGE=//p' "$ENV_FILE" | tail -n 1)"
fi
[ -n "$IMAGE" ] || fail "no image is named for the model server, so there is nothing to fetch weights with"

# The volume as the overlay project names it, so the server that starts next finds what is put here.
VOLUME="${PROJECT}-overlays_inference-models"
docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null ||
  fail "the weights volume could not be made"

docker pull -q "$IMAGE" >/dev/null 2>&1 ||
  fail "$IMAGE could not be pulled; the model server's image has to be published before it can start"

# shellcheck disable=SC2046 # the parts are a comma list of lowercase words, split on purpose.
docker run --rm -e INFERENCE_MODEL_DIR=/models -v "$VOLUME":/models "$IMAGE" \
  python -m inference_server.fetch $(printf '%s' "$PARTS" | tr ',' ' ') ||
  fail "the weights for $PARTS were not all fetched"

say "the weights for $PARTS are in the volume"
