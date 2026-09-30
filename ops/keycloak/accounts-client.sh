#!/bin/sh
# Set up the staff sync's sign-in accounts client in this install's Keycloak, and keep its secret
# in the vault, so the staff sync can give each active person an account with nobody doing
# anything by hand; and give the realm the mail relay saved on Notifications, so Forgot password's
# email is sent with it and nobody types the relay into Keycloak a second time. Run on the server
# by ops/deploy/brain-deploy after every release is ready, and by the installer. Safe to run again:
# once the vault holds the credential the client is left alone, and the realm's mail is written
# only when the relay changed.
#
# WHY HERE. Nothing else holds both halves. The accounts client has to be made, given its three
# roles and have its secret read by an administrator of the sign-in service, and the only such
# credential on an install is the one Keycloak itself was started with, which lives in Keycloak's
# container. The secret then has to reach the vault through the application, which may write
# connector_keys/ and never read it. The realm file cannot do it: --import-realm never touches a
# realm that already exists, so every install made before this release would be left out.
#
# WHAT NEVER HAPPENS. The administrator's password is used inside Keycloak's container, through
# KC_CLI_PASSWORD from that container's own environment, and is never an argument, a file here or
# a line of output. The client's secret goes from kcadm's output straight into the application's
# standard input through a pipe: never an argument, never a file, never printed. The relay's
# password goes the other way, from the application's output straight into kcadm's input, the same
# way. The kcadm session file is inside Keycloak's container and is removed on every way out.
#
# WHAT IT DOES, IN ORDER.
#   1. Asks the application whether the vault already holds the credential. Yes: steps 4 to 7
#      are skipped.
#   2. Finds Keycloak beside the application, by the compose project's labels, never by a name.
#   3. Signs in as Keycloak's own administrator, inside its container.
#   4. Makes the brain-accounts client from the reviewed realm if the realm has none.
#   5. Gives its service account manage-users, view-users and query-users, and no other role.
#   6. Declares the three account marks in the realm's user profile, because Keycloak drops an
#      attribute its profile does not declare (sign_in_accounts.AN_UNDECLARED_ATTRIBUTE_IS_...).
#   7. Hands the client's secret to the application, which keeps it and records the write.
#   8. Gives the realm the mail relay saved on Notifications (brain.ops.sign_in_mail): asks the
#      application whether the realm's mail is the relay's; when it is not, pipes the relay's
#      settings, password included, from the application straight into kcadm, reads the realm
#      back and hands that to the application to record. No relay saved: the realm is left alone.
#      Never fatal: a relay that could not be given is said in one line and tried on the next run.
#
# Usage, on the server:
#   BRAIN_APP_CONTAINER=app-<service> sh ops/keycloak/accounts-client.sh
#   BRAIN_KEYCLOAK_CONTAINER may name Keycloak's container; unset, it is found by label.
#
# Task ids: M1.6.16, M40.7.1

set -eu

APP="${BRAIN_APP_CONTAINER:-}"
KC="${BRAIN_KEYCLOAK_CONTAINER:-}"
KCADM=/opt/keycloak/bin/kcadm.sh
# Inside Keycloak's container, never on this host.
SESSION=/tmp/brain-accounts-client.kcadm
CLIENT=brain-accounts
ACCOUNT="service-account-$CLIENT"

say() { printf 'accounts client: %s\n' "$*"; }
fail() {
  say "$*" >&2
  exit 1
}

[ -n "$APP" ] || fail "BRAIN_APP_CONTAINER does not name the application's container"

app() { docker exec -i "$APP" python -m brain.ops.accounts_key "$@"; }
relay() { docker exec -i "$APP" python -m brain.ops.sign_in_mail "$@"; }

# 1. Done already?
HELD=no
if app --held </dev/null; then
  HELD=yes
fi

# 2. Keycloak beside the application.
if [ -z "$KC" ]; then
  project="$(docker inspect "$APP" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
  if [ -n "$project" ]; then
    KC="$(docker ps --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=keycloak" --format '{{.Names}}' | head -n 1 || true)"
  fi
fi
if [ -z "$KC" ]; then
  say "no Keycloak runs beside $APP, so the staff sync makes no sign-in accounts here and the sign-in service's email is its own to set; an install signing in elsewhere keeps brain-accounts:<secret> at connector_keys/sign_in_accounts from the Credentials screen"
  exit 0
fi

REALM="$(app --realm </dev/null)" || fail "the application could not say which realm it signs in with"

kc() { docker exec -i "$KC" "$KCADM" "$@" --config "$SESSION"; }
TMP="$(mktemp)"
cleanup() {
  docker exec "$KC" rm -f "$SESSION" >/dev/null 2>&1 || true
  rm -f "$TMP" "$TMP.out"
}
trap cleanup EXIT INT TERM

# 3. Sign in as the administrator Keycloak was started with, inside its own container. The single
# quotes are the point: the variables expand in Keycloak's shell, from Keycloak's environment.
# shellcheck disable=SC2016
docker exec "$KC" sh -c 'KC_CLI_PASSWORD="${KC_BOOTSTRAP_ADMIN_PASSWORD:-${KEYCLOAK_ADMIN_PASSWORD:-}}" exec "$0" config credentials --config "$1" --server http://localhost:8080 --realm master --user "${KC_BOOTSTRAP_ADMIN_USERNAME:-${KEYCLOAK_ADMIN:-admin}}"' \
  "$KCADM" "$SESSION" </dev/null >/dev/null \
  || fail "could not sign in to $KC as the administrator it was started with"

client_id() {
  kc get clients -r "$REALM" -q "clientId=$CLIENT" --fields id --format csv --noquotes </dev/null
}

# 8. The realm's mail, as a function so a failure is said and the step goes on. See the header.
sign_in_mail() {
  kc get "realms/$REALM" --fields smtpServer </dev/null > "$TMP" \
    || { say "SIGN-IN MAIL NOT SET: could not read the realm's email settings"; return 0; }
  decision="$(relay --decide < "$TMP")" \
    || { say "SIGN-IN MAIL NOT SET: the application could not compare the relay"; return 0; }
  case "$decision" in
    unset)
      say "no mail relay is saved on Notifications, so the realm's email settings are left as they are"
      return 0 ;;
    same)
      say "the realm already sends Forgot password with the relay saved on Notifications"
      return 0 ;;
    write) ;;
    *)
      say "SIGN-IN MAIL NOT SET: the application answered neither unset, same nor write"
      return 0 ;;
  esac
  relay --server </dev/null | kc update "realms/$REALM" --merge -f - >/dev/null \
    || { say "SIGN-IN MAIL NOT SET: Keycloak refused the relay's settings; tried again on the next run"; return 0; }
  kc get "realms/$REALM" --fields smtpServer </dev/null > "$TMP" \
    || { say "SIGN-IN MAIL NOT SET: could not read the realm's email settings back"; return 0; }
  relay --read-back < "$TMP" \
    || { say "SIGN-IN MAIL NOT SET: the realm did not keep the relay's settings"; return 0; }
  say "gave the realm the mail relay saved on Notifications"
}

if [ "$HELD" = yes ]; then
  say "the vault already holds its credential; the client is left as it is"
  sign_in_mail
  exit 0
fi

# 4. The client, from the reviewed realm, if the realm has none.
id="$(client_id)" || fail "could not list the realm's clients"
if [ -z "$id" ]; then
  app --client </dev/null > "$TMP" || fail "the application could not print the client"
  kc create clients -r "$REALM" -f - < "$TMP" >/dev/null || fail "Keycloak refused the $CLIENT client"
  id="$(client_id)" || fail "could not list the realm's clients"
  [ -n "$id" ] || fail "Keycloak made the $CLIENT client and then did not list it"
  say "made the $CLIENT client in realm $REALM"
fi

# 5. Its three roles, and no other. Adding a role it holds already changes nothing.
kc add-roles -r "$REALM" --uusername "$ACCOUNT" --cclientid realm-management \
  --rolename manage-users --rolename view-users --rolename query-users </dev/null \
  || fail "could not give $ACCOUNT its roles"

# 6. The marks, declared, leaving every other attribute as it was.
kc get users/profile -r "$REALM" </dev/null > "$TMP" || fail "could not read the realm's user profile"
app --profile < "$TMP" > "$TMP.out" || fail "the application could not declare the marks"
kc update users/profile -r "$REALM" -f - < "$TMP.out" >/dev/null \
  || fail "Keycloak refused the user profile with the marks declared"

# 7. The secret, from kcadm's output into the application's input, and nowhere else.
kc get "clients/$id/client-secret" -r "$REALM" --fields value --format csv --noquotes </dev/null \
  | app --keep || fail "the secret was not kept; the staff sync makes no accounts until it is"
say "set up; the staff sync can make sign-in accounts from its next run"

# 8. The realm's mail.
sign_in_mail
