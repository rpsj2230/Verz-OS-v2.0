#!/bin/bash
# Moves a running secrets vault that people unseal onto the seal that opens itself, in place.
#
# Task ids: M31.3.2.1, M31.3.2.2
#
# For an install made before 2026-09-29, whose vault needs three of five unseal pieces after every
# restart and a root token from the same three before any release's policies take. The owner
# decided on 2026-09-29 (docs/needs-rupash.md item 114) that the vault opens itself from a key file
# only root on the server can read, that every release applies its own vault changes with a deploy
# token, and that recovery pieces are an optional emergency spare. A new install is made that way
# by ops/install/install.sh; this is the one command that moves an older one.
#
# WHAT IT DOES, IN ORDER. Nothing changes until the pieces have been proved against the running
# vault, and every step says what it did in counts and names, never a value.
#   1. Refuses unless the vault answers, is open, and was brought up by compose with its data on a
#      named volume, and unless three distinct pieces can be read from the pieces file.
#   2. Makes a root token from three pieces while the vault is still open. That is the proof the
#      pieces are right: a wrong piece stops here, before anything has changed.
#   3. Writes the seal key (32 random bytes, root-only) unless one is there already.
#   4. Stops the vault, copies its data volume to a dated tar under the backup directory, and
#      records how it was brought up (its compose files, copied) so --rollback can put it back.
#   5. Recreates it from this release's compose file on the same volumes, network and name, and
#      migrates the seal with three pieces. Every token, secret, engine and lease is kept as it is:
#      the application's and the worker's tokens are the same tokens afterwards, so nothing that
#      hands them out (a hosting panel's stored settings, an environment file) changes.
#   6. Restarts it once, to prove it opens itself.
#   7. Leaves one recovery key (the default: the old pieces are rekeyed into it and stop working)
#      or, with --recovery-split, keeps the old pieces as the recovery pieces.
#   8. Under the root token: applies this release's engines, policies, token role and slots
#      (apply-release.sh beside this file), raises the token method's ceiling to a year, mints the
#      deploy token into its root-only file, and checks every token the containers hold still works.
#   9. Restarts the containers that reach the vault, revokes the root token, and prints a summary.
#
# WHY IN PLACE AND NOT A NEW VAULT BESIDE THE OLD ONE. A new vault cannot take the old tokens:
# OpenBao 2.4.1 refuses a custom token id with the `s.` prefix every minted token has (measured
# 2026-09-29: "custom token ID cannot have the 's.' prefix"), so a rebuild changes the tokens and
# with them whatever stores them, which on a hosting panel is its own database. Seal migration keeps
# the storage and only changes what encrypts its root key, so there is nothing to copy and nothing
# to hand out again. It needs three pieces, and without them it refuses: see ops/openbao/UNSEAL.md,
# under If the pieces are lost.
#
# Usage, as root on the server, from a copy of this release's ops/openbao directory:
#   bash switch-to-auto-unseal.sh --pieces-file FILE [--recovery-split] [--vault NAME]
#                                 [--state-dir DIR] [--backups DIR]
#   bash switch-to-auto-unseal.sh --rollback --pieces-file FILE [--vault NAME] [--backups DIR]
#
# --pieces-file   a file holding the vault's unseal pieces as `bao operator init` printed them,
#                 one `Unseal Key N: <piece>` line each. Read, never printed, never copied.
# --recovery-split  keep the old five pieces as the recovery pieces (any three make a root token)
#                 rather than rekeying them into one recovery key.
# --vault         the vault's container (default brain-vault).
# --state-dir     where the seal key, deploy token and recovery key go (default /etc/brain-vault).
# --backups       where the dated tar and the rollback record go (default /root/brain-vault-backups).
# --rollback      put back the vault as it was before the last switch: its data from the tar, its
#                 own compose files, opened with three pieces. Anything written after the switch
#                 is lost, and the command says so before it starts.

set -euo pipefail
umask 077

HERE="$(cd "$(dirname "$0")" && pwd)"
VAULT="brain-vault"
STATE_DIR="/etc/brain-vault"
BACKUPS="/root/brain-vault-backups"
PIECES_FILE=""
RECOVERY="single"
MODE="switch"
THRESHOLD_NEEDED=3
ADDR="-e BAO_ADDR=http://127.0.0.1:8200"

say() { printf '%s\n' "$1"; }
step() { printf '\n== %s\n' "$1"; }
fail() { printf 'refused: %s\n' "$1" >&2; exit 1; }

while test "$#" -gt 0; do
  case "$1" in
    --pieces-file) PIECES_FILE="${2:?--pieces-file needs a path}"; shift 2 ;;
    --recovery-split) RECOVERY="split"; shift ;;
    --vault) VAULT="${2:?--vault needs a container name}"; shift 2 ;;
    --state-dir) STATE_DIR="${2:?--state-dir needs a directory}"; shift 2 ;;
    --backups) BACKUPS="${2:?--backups needs a directory}"; shift 2 ;;
    --rollback) MODE="rollback"; shift ;;
    --help|-h) sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "unknown option $1; --help lists them" ;;
  esac
done

SEAL_KEY="$STATE_DIR/seal.key"
DEPLOY_TOKEN="$STATE_DIR/deploy.token"
RECOVERY_FILE="$STATE_DIR/recovery.key"
RECORD="$BACKUPS/$VAULT.switch-record"

test "$(id -u)" -eq 0 || fail "run this as root: the seal key and the deploy token are root-only files"
command -v docker >/dev/null 2>&1 || fail "docker is not on this machine's PATH"
test -f "$HERE/compose.yml" && test -f "$HERE/apply-release.sh" && test -d "$HERE/policies" \
  || fail "this script has to run from this release's ops/openbao directory, beside compose.yml, apply-release.sh and policies/"
test -n "$PIECES_FILE" || fail "--pieces-file is required: the in-place move needs three of the vault's unseal pieces. Without them see ops/openbao/UNSEAL.md, under If the pieces are lost"
test -r "$PIECES_FILE" || fail "cannot read $PIECES_FILE"

# ---------------------------------------------------------------------------------- helpers
bao_() { docker exec $ADDR "$VAULT" bao "$@" </dev/null; }
as_root() { BAO_TOKEN="$ROOT" docker exec -e BAO_TOKEN $ADDR "$VAULT" bao "$@" </dev/null; }
as_root_in() { BAO_TOKEN="$ROOT" docker exec -i -e BAO_TOKEN $ADDR "$VAULT" bao "$@"; }
is_open() { bao_ status >/dev/null 2>&1; }
seal_type() { { bao_ status -format=json 2>/dev/null || true; } | sed -n 's/^ *"type": "\([a-z]*\)",*$/\1/p' | head -n 1; }
recovery_shares() { { bao_ status 2>/dev/null || true; } | awk '/^Total Recovery Shares/ {print $4}'; }
wait_open() {
  local i=0
  while test "$i" -lt 30; do
    is_open && return 0
    i=$((i + 1)); sleep 2
  done
  return 1
}
# The pieces, by the label `bao operator init` prints them under, first three distinct ones. Held in
# this shell only; each reaches the vault through printf, a builtin, into docker exec's stdin.
read_pieces() {
  P1=""; P2=""; P3=""
  local n=0 piece
  while IFS= read -r piece; do
    test -n "$piece" || continue
    n=$((n + 1))
    case "$n" in 1) P1="$piece" ;; 2) P2="$piece" ;; 3) P3="$piece" ;; esac
  done < <(sed -n 's/^Unseal Key [0-9][0-9]*: *\([^ ]*\) *$/\1/p' "$PIECES_FILE" | awk '!seen[$0]++')
  test "$n" -ge "$THRESHOLD_NEEDED" || fail "$PIECES_FILE holds $n distinct pieces under an 'Unseal Key N:' label, and $THRESHOLD_NEEDED are needed"
  say "pieces: $n distinct pieces read from the file, $THRESHOLD_NEEDED will be used"
}
piece() { case "$1" in 1) printf '%s' "$P1" ;; 2) printf '%s' "$P2" ;; 3) printf '%s' "$P3" ;; esac; }
env_of() { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null; }
# A root token from a key the vault verifies: unseal pieces before the move, recovery keys after.
# The one-time password and the nonce are not secrets on their own; the encoded token is decoded
# from standard input, so no argument list ever holds both halves.
make_root() {
  local attempt nonce otp encoded n
  bao_ delete sys/generate-root/attempt >/dev/null 2>&1 || true
  attempt="$(bao_ write -format=json -f sys/generate-root/attempt)" || fail "the vault would not start making a root token"
  nonce="$(printf '%s' "$attempt" | sed -n 's/.*"nonce": "\([^"]*\)".*/\1/p')"
  otp="$(printf '%s' "$attempt" | sed -n 's/.*"otp": "\([^"]*\)".*/\1/p')"
  encoded=""
  for n in $(seq 1 "$1"); do
    encoded="$("$2" "$n" | docker exec -i $ADDR "$VAULT" bao write -field=encoded_token sys/generate-root/update nonce="$nonce" key=- 2>/dev/null)" \
      || { bao_ delete sys/generate-root/attempt >/dev/null 2>&1 || true; fail "the vault did not accept key $n of $1 for a root token, so the keys in hand are not this vault's. Nothing has been changed"; }
  done
  test -n "$encoded" || fail "the vault took the keys and gave no token back. Nothing has been changed"
  ROOT="$(printf '%s' "$encoded" | docker exec -i $ADDR "$VAULT" bao operator generate-root -decode=- -otp="$otp" 2>/dev/null)" \
    || fail "the root token could not be decoded. Nothing has been changed"
  as_root token lookup >/dev/null 2>&1 || fail "the root token just made was refused. Nothing has been changed"
}
recovery_piece() { cat "$RECOVERY_FILE"; }
revoke_root() {
  if test -n "${ROOT:-}"; then
    as_root token revoke -self >/dev/null 2>&1 \
      || say "note: the root token this run made could not be revoked. Make one from the recovery key and revoke every root token: ops/openbao/UNSEAL.md, In an emergency"
    ROOT=""
  fi
}
restart_dependents() {
  local net c restarted=0
  net="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$VAULT" | grep -v '^$' | head -n 1)"
  for c in $(docker network inspect -f '{{range .Containers}}{{println .Name}}{{end}}' "$net" 2>/dev/null | grep -v '^$'); do
    test "$c" = "$VAULT" && continue
    env_of "$c" | grep -q '^BRAIN_VAULT_ADDRESS=' || continue
    docker restart "$c" >/dev/null && restarted=$((restarted + 1)) && say "restarted $c"
  done
  say "restarted $restarted containers that reach the vault"
}

# ---------------------------------------------------------------------------------- rollback
if test "$MODE" = "rollback"; then
  test -r "$RECORD" || fail "there is no record of a switch at $RECORD, so there is nothing to put back"
  # shellcheck disable=SC1090
  . "$RECORD"
  test -s "$RECORDED_BACKUP" || fail "the backup the switch took, $RECORDED_BACKUP, is missing"
  read_pieces
  step "putting back the vault as it was before the switch of $RECORDED_AT"
  say "Everything written to the vault after that moment is lost: a key replaced from the console since then goes back to its old value."
  docker stop "$VAULT" >/dev/null 2>&1 || true
  mount="$(docker volume inspect -f '{{.Mountpoint}}' "$RECORDED_DATA_VOLUME")"
  find "$mount" -mindepth 1 -delete
  tar -xzf "$RECORDED_BACKUP" -C "$mount"
  say "data volume $RECORDED_DATA_VOLUME restored from $(basename "$RECORDED_BACKUP")"
  set --
  for f in "$BACKUPS/$VAULT.compose"/*; do set -- "$@" -f "$f"; done
  docker compose -p "$RECORDED_PROJECT" --project-directory "$RECORDED_WORKDIR" "$@" up -d --force-recreate >/dev/null \
    || fail "the vault could not be brought up from its old compose files in $BACKUPS/$VAULT.compose"
  sleep 3
  for n in 1 2 3; do piece "$n" | docker exec -i $ADDR "$VAULT" bao write sys/unseal key=- >/dev/null; done
  wait_open || fail "the restored vault did not open with three pieces; read docker logs $VAULT"
  say "the vault is open again under its old seal ($(seal_type)); the pieces open it after every restart, as before"
  if test -f "$DEPLOY_TOKEN"; then mv "$DEPLOY_TOKEN" "$DEPLOY_TOKEN.rolled-back-$(date -u +%Y%m%dT%H%M%SZ)"; say "the deploy token file was set aside: that token no longer exists in the restored vault"; fi
  restart_dependents
  say "rolled back. The seal key file stays in $STATE_DIR and opens nothing now."
  exit 0
fi

# ---------------------------------------------------------------------------------- 1. refuse
step "1. checking the vault and the pieces"
docker inspect "$VAULT" >/dev/null 2>&1 || fail "there is no container called $VAULT"
is_open || fail "$VAULT does not answer as open. It has to be running and unsealed before it is moved"
BEFORE_TYPE="$(seal_type)"
PROJECT="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$VAULT")"
SERVICE="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$VAULT")"
WORKDIR="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$VAULT")"
FILES="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$VAULT")"
DATA_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/openbao/file"}}{{.Name}}{{end}}{{end}}' "$VAULT")"
LOGS_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/openbao/logs"}}{{.Name}}{{end}}{{end}}' "$VAULT")"
NETWORKS="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$VAULT" | grep -v '^$' || true)"
test -n "$PROJECT" && test -n "$WORKDIR" && test -n "$FILES" || fail "$VAULT was not brought up by docker compose, so there is no project to recreate it in"
test "$SERVICE" = "vault" || fail "$VAULT is the compose service '$SERVICE'; this release's compose file names it 'vault', and recreating it under another name would leave two"
test -n "$DATA_VOLUME" || fail "$VAULT keeps its data somewhere other than a named volume at /openbao/file"
test -n "$LOGS_VOLUME" || fail "$VAULT keeps its audit log somewhere other than a named volume at /openbao/logs"
test "$(printf '%s\n' "$NETWORKS" | grep -c .)" -eq 1 || fail "$VAULT is on $(printf '%s\n' "$NETWORKS" | grep -c .) networks; this moves a vault on exactly one"
NETWORK="$NETWORKS"
say "vault: $VAULT, compose project $PROJECT, seal $BEFORE_TYPE, data on $DATA_VOLUME, audit log on $LOGS_VOLUME, network $NETWORK"
read_pieces

if test "$BEFORE_TYPE" = "static"; then
  say "the vault already opens itself; the move is done, and the steps after it are checked and finished"
  test -s "$SEAL_KEY" || fail "the vault opens itself but $SEAL_KEY is missing, so its next restart will not open it. Put the copy back first"
  if test "$(recovery_shares)" = "1" && ! test -s "$RECOVERY_FILE"; then
    fail "the move finished earlier and its one recovery key has left this server, which is where it belongs. To run the finishing steps again, put it back at $RECOVERY_FILE for the length of the run"
  fi
fi

# ---------------------------------------------------------------------------------- 2. prove
step "2. proving the keys by making a root token while the vault is open"
# Made and revoked at once. It is made again after the move, so the copy of the vault's data taken
# in step 4 never holds a live root token that nobody has the value of.
make_any_root() {
  if test "$(seal_type)" != "static"; then
    make_root "$THRESHOLD_NEEDED" piece
  elif test "$(recovery_shares)" = "1"; then
    make_root 1 recovery_piece
  else
    make_root "$THRESHOLD_NEEDED" piece
  fi
}
make_any_root
revoke_root
say "the keys are this vault's: a root token was made from them and revoked again"

if test "$BEFORE_TYPE" != "static"; then
  # ------------------------------------------------------------------------------ 3. seal key
  step "3. the seal key"
  mkdir -p "$STATE_DIR" "$BACKUPS"
  chmod 0700 "$STATE_DIR" "$BACKUPS"
  if test -s "$SEAL_KEY"; then
    say "kept the seal key already at $SEAL_KEY"
  else
    head -c 32 /dev/urandom > "$SEAL_KEY.new"
    test "$(wc -c < "$SEAL_KEY.new")" -eq 32 || fail "the seal key came out short; nothing has been changed"
    chmod 0400 "$SEAL_KEY.new"
    mv "$SEAL_KEY.new" "$SEAL_KEY"
    say "wrote a new seal key to $SEAL_KEY (root-only)"
  fi

  # ------------------------------------------------------------------------------ 4. back up
  step "4. stopping the vault and copying its data"
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP="$BACKUPS/$VAULT-data-$STAMP.tar.gz"
  rm -rf "$BACKUPS/$VAULT.compose"
  mkdir -p "$BACKUPS/$VAULT.compose"
  n=0
  IFS=',' read -r -a CONFIG_FILES <<< "$FILES"
  for f in "${CONFIG_FILES[@]}"; do
    test -r "$f" || fail "$VAULT was brought up from $f, which is no longer there, so --rollback would have nothing to bring it back with. Nothing has been changed"
    n=$((n + 1)); cp "$f" "$BACKUPS/$VAULT.compose/$n-$(basename "$f")"
  done
  docker stop "$VAULT" >/dev/null
  MOUNT="$(docker volume inspect -f '{{.Mountpoint}}' "$DATA_VOLUME")"
  tar -czf "$BACKUP" -C "$MOUNT" .
  chmod 0400 "$BACKUP"
  {
    printf 'RECORDED_AT=%q\n' "$STAMP"
    printf 'RECORDED_BACKUP=%q\n' "$BACKUP"
    printf 'RECORDED_PROJECT=%q\n' "$PROJECT"
    printf 'RECORDED_WORKDIR=%q\n' "$WORKDIR"
    printf 'RECORDED_DATA_VOLUME=%q\n' "$DATA_VOLUME"
  } > "$RECORD"
  say "stopped $VAULT; its data is in $BACKUP ($(du -h "$BACKUP" | cut -f1)), and how it was brought up is kept for --rollback"

  # ------------------------------------------------------------------------------ 5. migrate
  step "5. recreating it on the seal that opens itself, and moving the seal"
  BRAIN_VAULT_CONTAINER="$VAULT" BRAIN_VAULT_NETWORK="$NETWORK" BRAIN_VAULT_DATA_VOLUME="$DATA_VOLUME" \
    BRAIN_VAULT_LOGS_VOLUME="$LOGS_VOLUME" BRAIN_VAULT_SEAL_KEY="$SEAL_KEY" \
    docker compose -p "$PROJECT" -f "$HERE/compose.yml" up -d --force-recreate >/dev/null \
    || fail "the vault could not be recreated from this release's compose file. Put it back with: $0 --rollback --pieces-file $PIECES_FILE"
  i=0
  until bao_ status >/dev/null 2>&1 || test "$(bao_ status 2>&1 | grep -c 'Seal Migration in Progress *true')" -eq 1; do
    i=$((i + 1)); test "$i" -lt 30 || fail "the recreated vault never answered; read docker logs $VAULT, then: $0 --rollback --pieces-file $PIECES_FILE"
    sleep 2
  done
  for n in 1 2 3; do
    printf '{"key":"%s","migrate":true}' "$(piece "$n")" | docker exec -i $ADDR "$VAULT" bao write sys/unseal - >/dev/null \
      || fail "the vault refused piece $n for the seal move. Put it back with: $0 --rollback --pieces-file $PIECES_FILE"
  done
  wait_open || fail "the vault did not open after the seal move; read docker logs $VAULT, then: $0 --rollback --pieces-file $PIECES_FILE"
  test "$(seal_type)" = "static" || fail "the vault opened but its seal is $(seal_type); put it back with: $0 --rollback --pieces-file $PIECES_FILE"
  say "the seal moved: $VAULT now opens itself; its old pieces are its recovery pieces for now"
fi

# ---------------------------------------------------------------------------------- 6. restart
step "6. restarting the vault once, to prove it opens itself"
docker restart "$VAULT" >/dev/null
wait_open || fail "$VAULT did not open itself after a restart; read docker logs $VAULT. The seal key is $SEAL_KEY"
say "$VAULT restarted and opened itself with nobody typing anything"
make_any_root
trap revoke_root EXIT
say "a root token for the steps below, from the recovery keys; it exists only in this shell and is revoked at the end"

# ---------------------------------------------------------------------------------- 7. recovery
step "7. the recovery key"
if test "$RECOVERY" = "split"; then
  say "kept the old pieces as the recovery pieces: $(recovery_shares) of them, any three make a root token in an emergency; none opens the vault"
elif test "$(recovery_shares)" = "1" && test -s "$RECOVERY_FILE"; then
  say "kept the one recovery key already at $RECOVERY_FILE"
else
  body="$(printf '{"secret_shares":1,"secret_threshold":1}' | as_root_in write -format=json sys/rekey-recovery-key/init -)" \
    || fail "the vault would not start a rekey of the recovery pieces"
  nonce="$(printf '%s' "$body" | sed -n 's/.*"nonce": "\([^"]*\)".*/\1/p')"
  answer=""
  for n in 1 2 3; do
    answer="$(piece "$n" | BAO_TOKEN="$ROOT" docker exec -i -e BAO_TOKEN $ADDR "$VAULT" bao write -format=json sys/rekey-recovery-key/update nonce="$nonce" key=-)" \
      || fail "the vault refused piece $n as a recovery piece"
  done
  mkdir -p "$STATE_DIR"
  printf '%s' "$answer" | tr -d '\n ' | sed -n 's/.*"keys_base64":\["\([^"]*\)"\].*/\1/p' > "$RECOVERY_FILE.new"
  answer=""
  test -s "$RECOVERY_FILE.new" || fail "the rekey answered in a shape this script cannot read; the vault may now hold a new recovery key nobody has. Read ops/openbao/UNSEAL.md, In an emergency"
  chmod 0400 "$RECOVERY_FILE.new"
  mv "$RECOVERY_FILE.new" "$RECOVERY_FILE"
  test "$(recovery_shares)" = "1" || fail "the vault still reports $(recovery_shares) recovery pieces after the rekey"
  say "the old pieces were rekeyed into one recovery key, in $RECOVERY_FILE (root-only). The old pieces open nothing now"
fi

# ---------------------------------------------------------------------------------- 8. release
step "8. this release's engines, policies, role and slots, and the deploy token"
BAO_TOKEN="$ROOT" BRAIN_VAULT_CONTAINER="$VAULT" sh "$HERE/apply-release.sh" \
  || fail "this release's vault changes did not take under the root token; the lines above say which"
as_root auth tune -max-lease-ttl=8760h token/ >/dev/null || fail "the vault would not raise the token method's ceiling"
if test -s "$DEPLOY_TOKEN" && BAO_TOKEN="$(cat "$DEPLOY_TOKEN")" docker exec -e BAO_TOKEN $ADDR "$VAULT" bao token lookup >/dev/null 2>&1; then
  say "kept the working deploy token at $DEPLOY_TOKEN"
else
  mkdir -p "$STATE_DIR"
  as_root token create -policy=deploy -no-default-policy -orphan -period=8760h -field=token > "$DEPLOY_TOKEN.new" \
    || fail "the vault would not mint the deploy token"
  chmod 0400 "$DEPLOY_TOKEN.new"
  mv "$DEPLOY_TOKEN.new" "$DEPLOY_TOKEN"
  say "minted the deploy token into $DEPLOY_TOKEN (root-only); every release now applies its own vault changes with it"
fi
BRAIN_VAULT_CONTAINER="$VAULT" BRAIN_VAULT_DEPLOY_TOKEN_FILE="$DEPLOY_TOKEN" sh "$HERE/apply-release.sh" --check >/dev/null \
  || fail "the deploy token cannot confirm this release's vault changes"
say "the deploy token confirms this release's vault changes are in force"

held=0; working=0
net_containers="$(docker network inspect -f '{{range .Containers}}{{println .Name}}{{end}}' "$NETWORK" 2>/dev/null | grep -v '^$' || true)"
for c in $net_containers; do
  test "$c" = "$VAULT" && continue
  for name in BRAIN_VAULT_TOKEN BRAIN_WORKER_VAULT_TOKEN; do
    value="$(env_of "$c" | sed -n "s/^$name=//p" | head -n 1)"
    test -n "$value" || continue
    held=$((held + 1))
    if BAO_TOKEN="$value" docker exec -e BAO_TOKEN $ADDR "$VAULT" bao token lookup >/dev/null 2>&1; then
      working=$((working + 1))
    else
      say "note: $c's $name is refused by the vault"
    fi
  done
done
value=""
test "$held" -eq "$working" || fail "$((held - working)) of the $held tokens the containers hold were refused after the move"
say "every token the containers hold still works: $working of $held, unchanged"

# ---------------------------------------------------------------------------------- 9. finish
step "9. restarting what reaches the vault, and revoking the root token"
restart_dependents
revoke_root
trap - EXIT

cat <<SUMMARY

Done. The vault opens itself now.

  What changed    $VAULT keeps every secret, engine and token it had; only what locks its data
                  changed. This release's policies and engines are in force.
  Kept on this    $SEAL_KEY      the seal key. Without it the vault never opens again.
  server, root    $DEPLOY_TOKEN  lets each release apply its own vault changes.
  only
SUMMARY
if test "$RECOVERY" = "split"; then
  say "  Recovery        your five old pieces are now the recovery pieces: any three make a root token"
  say "                  in an emergency, and none of them opens the vault any more. Hand them to five"
  say "                  people, then delete $PIECES_FILE."
else
  say "  Recovery        $RECOVERY_FILE holds the one recovery key. Move it into your password"
  say "                  manager, then delete that file. The pieces in $PIECES_FILE open nothing now:"
  say "                  delete that file too."
fi
cat <<SUMMARY

  Copy the seal key somewhere off this server that is not beside any backup of the vault's data
  (a password manager entry of its own is right): ops/openbao/UNSEAL.md, under What to keep.

  To check: docker restart $VAULT, then docker exec $VAULT bao status says Sealed false with
  nobody typing anything. The console's Credentials screen shows the template signing key held.
  The vault's data before the move is in $BACKUPS; --rollback puts it back while that copy exists.
SUMMARY
