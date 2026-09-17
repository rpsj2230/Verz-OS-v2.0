# Rehearsing the installer's secrets vault on a server that can run it

Task ids: M42.6.2, M42.5.14

The vault steps of `ops/install/install.sh` are read by `tests/unit/test_vault_setup.py` and run
there against a stand-in `docker` that answers as `bao` does. Neither is OpenBao. What only a
server can show is that a real vault answers in the shapes the script reads, opens with pieces
piped to it, and that a fresh hosted install then keeps a provider key and lands in the console
with nothing edited by hand. Run this on a throwaway server, in order, and record each result
against the leaf half it proves. No value here belongs to any company: use any release tag you
have published and a provider key you can revoke afterwards.

## 1. A fresh install runs the vault and prints the pieces once

On a clean server, `standard` profile, at a terminal:

```
sudo BRAIN_RELEASE_URL=<the archive> bash install.sh --release <tag> --profile standard \
  --console-address <the proxy's address>
```

Expected, and each is a check:

- Step `initialise the secrets vault and show its unseal pieces, once` prints `piece 1 of 5` to
  `piece 5 of 5` and waits for Enter. It never prints `Initial Root Token`. If it prints the vault's
  whole answer instead, the table shape differs from OpenBao 2.4.1's: record the output shape.
- `docker exec brain-vault bao status` reports `Sealed false`.
- `sudo grep -c '^BRAIN_VAULT_ADDRESS=http://vault:8200$' /opt/brain/.env` is `1`, and
  `BRAIN_VAULT_TOKEN` and `BRAIN_WORKER_VAULT_TOKEN` each have a value.
- `sudo ls -l /opt/brain/.env` is mode `-rw-------`.
- Nothing under `/opt/brain`, `/tmp` or the root user's home holds a piece:
  `sudo grep -rl '<the first piece>' /opt/brain /tmp /root` prints nothing.

## 2. The root token is gone and the tokens are what was minted

With three pieces and `bao operator generate-root`, generate a root token for this check only:

```
docker exec -e BAO_TOKEN=<that token> brain-vault bao list auth/token/accessors
docker exec -e BAO_TOKEN=<that token> brain-vault bao token lookup -accessor <each accessor>
```

Expected: no token with policy `root` other than the one just generated; one with policies
`application, default` and one with `default, worker`, each `period 768h`, `renewable true`,
`orphan true`. `bao secrets list` shows `providers/`, `webhooks/` and `connector_keys/` as `kv`
version 2, `bao audit list` shows `file/` and `stderr/`, `bao policy list` shows every file in
`ops/openbao/policies`. Revoke the generated token.

## 3. The wizard keeps the key with no hand edit (M42.6.2)

Open `/first-run`, choose a hosted provider and paste a key. Expected: the appointment answers
200, not 409, and `docker exec -e BAO_TOKEN=<a regenerated root token> brain-vault bao kv metadata
get providers/anthropic` shows version 1. Nothing was typed into `/opt/brain/.env`.

## 4. The finishing screen (M42.5.14)

- Record `docker compose <files> exec app sh -c 'ps -eo args | grep -c "multiprocessing.spawn"'`.
  Zero children means the application serves alone, and the finishing screen must land on the
  Overview signed in with no sentence. Any children means it must stop on the restart sentence.
- Ask a question that reaches the hosted provider, straight after landing. On a single process
  it answers. With several, it answers once `docker compose <files> restart app` has run.

## 5. The tokens renew

- `docker compose <files> logs app | grep "vault token checked"` shows a check at start.
- `docker compose <files> exec brain-worker python -m brain.ops.worker --run-control
  vault_token_renewal` (or wait for the schedule) and the Scheduled jobs screen shows
  `vault_token_renewal` as ok with `not owed a renewal: 767h left`.

## 6. A restart, then an update

- `docker restart brain-vault`, unseal with three pieces, and confirm the application still
  answers; then reboot the server, unseal, `restart app`, and confirm it loads the key again.
- Run `ops/update/update.sh standard <tag>` and confirm the `app` and `brain-worker` containers
  are on the `brain-vault` network afterwards: `docker network inspect brain-vault`.

## What stays open until this has run

- **M42.6.2**, the half that is a server: that OpenBao 2.4.1 answers `bao operator init` in the
  table shape the script reads, accepts a piece on `bao write sys/unseal key=-`, and mints the
  tokens with the flags as written. Everything that decides is tested; nothing has met a vault.
- **M42.5.14**, the same half, and one more: an application container at its default memory
  starts four uvicorn workers, so on that install the finishing screen honestly asks for a restart
  rather than landing at once. It lands at once only where the application serves alone.
