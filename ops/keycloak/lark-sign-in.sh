#!/bin/sh
# Gives a realm that was imported before Sign in with Lark existed the two things the realm file
# now carries for a fresh install: the first-login flow that links a person to the account the staff
# sync made and creates nobody, and the Lark identity provider that names it. Keycloak imports a
# realm only when it has none of that name, so an install whose realm already exists keeps the old
# one, and this adds the two pieces to it. It changes nothing else and can be run again: a flow
# that exists is left as it is, and an identity provider that exists is replaced by the new entry.
#
# The entry is the one the install's own settings ask for, printed by the application:
#
#   docker compose exec -T app python -m brain.ops.realm_import --identity-provider > lark.json
#
# which exits with the reason, and prints nothing for this script to use, when the install does not
# broker sign-in to Lark. Run this from any machine that can reach the install's Keycloak:
#
#   KC_URL=https://<the install's identity address> KEYCLOAK_ADMIN=<admin user> \
#     KEYCLOAK_ADMIN_PASSWORD=<its password> sh ops/keycloak/lark-sign-in.sh lark.json
#
# The password is read from the environment and sent on standard input, never on a command line,
# and the admin token is never printed. The Lark application's secret is not an input here: it is
# a file in Keycloak's vault (docs/install/authentication.md, "Signing in with Lark"). Needs curl
# and jq.
#
# Task ids: M1.1.8

set -eu

: "${KC_URL:?set KC_URL to the Keycloak address, with no trailing slash}"
: "${KEYCLOAK_ADMIN:?set KEYCLOAK_ADMIN to a Keycloak administrator}"
: "${KEYCLOAK_ADMIN_PASSWORD:?set KEYCLOAK_ADMIN_PASSWORD}"
ENTRY="${1:?give the file the application printed with --identity-provider}"
REALM="${REALM:-brain}"
FLOW="brain link by work address"
ALIAS="lark"
CURL="curl -sSf ${KC_INSECURE:+-k}"

[ "$(jq -r .alias "$ENTRY")" = "$ALIAS" ] && [ "$(jq -r '.firstBrokerLoginFlowAlias' "$ENTRY")" = "$FLOW" ] || {
  echo "$ENTRY is not the Lark entry this script adds; nothing was changed" >&2
  exit 1
}

token=$(printf '%s' "$KEYCLOAK_ADMIN_PASSWORD" | $CURL "$KC_URL/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  --data-urlencode "username=$KEYCLOAK_ADMIN" --data-urlencode "password@-" | jq -r .access_token)
api="$KC_URL/admin/realms/$REALM"

call() {
  method=$1
  path=$2
  shift 2
  $CURL -X "$method" -H "Authorization: Bearer $token" -H "Content-Type: application/json" "$api$path" "$@"
}

encoded=$(printf '%s' "$FLOW" | jq -sRr @uri)

# 1. The flow, with its two steps, both required. Created only when the realm has none of that name.
if [ "$(call GET /authentication/flows | jq -r --arg n "$FLOW" '[.[] | select(.alias == $n)] | length')" = "0" ]; then
  call POST /authentication/flows -d "$(jq -n --arg n "$FLOW" \
    '{alias: $n, description: "Links a brokered Lark person to the account the staff sync made, and creates nobody", providerId: "basic-flow", topLevel: true, builtIn: false}')" > /dev/null
  for step in idp-detect-existing-broker-user idp-auto-link; do
    call POST "/authentication/flows/$encoded/executions/execution" -d "{\"provider\": \"$step\"}" > /dev/null
  done
  call GET "/authentication/flows/$encoded/executions" | jq -c '.[]' | while read -r one; do
    call PUT "/authentication/flows/$encoded/executions" -d "$(printf '%s' "$one" | jq -c '.requirement = "REQUIRED"')" > /dev/null
  done
fi

# 2. The identity provider: replaced when there is one, made when there is not.
if $CURL -o /dev/null -H "Authorization: Bearer $token" "$api/identity-provider/instances/$ALIAS" 2>/dev/null; then
  call PUT "/identity-provider/instances/$ALIAS" -d @"$ENTRY" > /dev/null
else
  call POST /identity-provider/instances -d @"$ENTRY" > /dev/null
fi

# 3. Read back, because the two steps above are the ones that can half work.
steps=$(call GET "/authentication/flows/$encoded/executions" | jq -c '[.[] | [.providerId, .requirement]]')
echo "first-login flow steps: $steps"
[ "$steps" = '[["idp-detect-existing-broker-user","REQUIRED"],["idp-auto-link","REQUIRED"]]' ] || {
  echo "the flow did not end with its two required steps; check the line above" >&2
  exit 1
}
on=$(call GET "/identity-provider/instances/$ALIAS" | jq -r '[.alias, .enabled, .firstBrokerLoginFlowAlias] | @tsv')
echo "identity provider: $on"
echo "done: $ALIAS signs a person in to the account the staff sync made for them, and creates nobody"
