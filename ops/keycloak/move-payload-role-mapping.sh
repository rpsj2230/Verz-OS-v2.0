#!/bin/sh
# Repairs a realm imported between 2026-09-30 and the release that fixed it, where the trace
# payload role was mapped to the `brain-identity` client scope. Keycloak applies a client scope
# that has role scope mappings only to a person who holds one of those roles, so on such a realm
# nobody without the payload role is given that scope, and the console's tokens carry no
# audience for the API: every sign-in is refused with `wrong_audience`.
#
# The realm file is fixed for every install that imports it from now on. An install that has
# already imported it keeps its realm, because `--import-realm` never overwrites a realm that
# exists, so this moves the one mapping on that install: off the scope, onto the console client.
# It changes nothing else and can be run again; a realm that is already right is left as it is.
#
# Run from any machine that can reach the install's Keycloak:
#
#   KC_URL=https://<the install's identity address> KEYCLOAK_ADMIN=<admin user> \
#     KEYCLOAK_ADMIN_PASSWORD=<its password> sh ops/keycloak/move-payload-role-mapping.sh
#
# The password is read from the environment and sent on standard input, never on a command line,
# and the admin token is never printed. Needs curl and jq.
#
# Task ids: M1.1.1

set -eu

: "${KC_URL:?set KC_URL to the Keycloak address, with no trailing slash}"
: "${KEYCLOAK_ADMIN:?set KEYCLOAK_ADMIN to a Keycloak administrator}"
: "${KEYCLOAK_ADMIN_PASSWORD:?set KEYCLOAK_ADMIN_PASSWORD}"
REALM="${REALM:-brain}"
SCOPE_NAME="brain-identity"
CLIENT_ID="brain-console"
ROLE="brain-langfuse-payload"
CURL="curl -sSf ${KC_INSECURE:+-k}"

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

scope=$(call GET /client-scopes | jq -r --arg n "$SCOPE_NAME" '.[] | select(.name == $n) | .id')
client=$(call GET "/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')
role=$(call GET "/roles/$ROLE")
[ -n "$scope" ] && [ -n "$client" ] && [ "$client" != "null" ] || {
  echo "the realm has no $SCOPE_NAME scope or no $CLIENT_ID client; nothing was changed" >&2
  exit 1
}

call POST "/clients/$client/scope-mappings/realm" -d "[$role]" > /dev/null
call DELETE "/client-scopes/$scope/scope-mappings/realm" -d "[$role]" > /dev/null

on_scope=$(call GET "/client-scopes/$scope/scope-mappings/realm" | jq -c '[.[].name]')
on_client=$(call GET "/clients/$client/scope-mappings/realm" | jq -c '[.[].name]')
echo "realm roles mapped to $SCOPE_NAME: $on_scope"
echo "realm roles mapped to $CLIENT_ID: $on_client"
[ "$on_scope" = "[]" ] && [ "$on_client" = "[\"$ROLE\"]" ] || {
  echo "the mapping did not end where it should; check the two lines above" >&2
  exit 1
}
echo "repaired: $SCOPE_NAME applies to everybody again, and $ROLE reaches only its holders' console tokens"
