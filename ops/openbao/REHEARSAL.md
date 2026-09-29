# Rehearsing the secrets vault on a server that can run it

Task ids: M42.6.2, M42.5.14, M13.8.10, M31.3.2.1, M31.3.2.2

The vault steps of `ops/install/install.sh` are read by `tests/unit/test_vault_setup.py` and run
there against a stand-in `docker` that answers as `bao` does, and `apply-release.sh` is run there
against the same stand-in. Neither is OpenBao. What only a server can show is that a real vault
opens itself from its seal key, answers in the shapes the scripts read, and that a fresh install
then keeps a provider key and lands in the console with nothing edited by hand. Run this on a
throwaway server, in order, and record each result against the leaf it proves. No value here
belongs to any company: use any release tag you have published and a provider key you can revoke.

**Nothing below prints a secret, and nothing should.** Where a check needs a token, it is read into
the shell and passed to `docker exec` by name (`-e BAO_TOKEN`), never typed onto a command line.

## What has already been measured on a server (2026-09-29, openbao 2.4.1)

On throwaway containers beside a live install, never touching its vault:

- A `seal "static"` stanza with a 32-byte key file is accepted; the vault reports `Seal Type
  static`, `Recovery Seal Type shamir`, and comes back `Sealed false` after `docker restart` with
  nobody typing anything. The key file stays root-only on the host; the entrypoint copies it into a
  tmpfs the vault's own user reads, and the vault process runs as `openbao`.
- `bao operator init -recovery-shares=1 -recovery-threshold=1` answers with one `Recovery Key 1:`
  line and one `Initial Root Token:` line, and the vault is open when it returns.
- A token minted with `-period=8760h` comes back with 768 hours to live until the token method's
  maximum is raised (`auth tune -max-lease-ttl=8760h token/`), which is why the installer raises it.
- The deploy policy (`policies/deploy.hcl`) may enable an engine, load another policy, read a
  policy back, define a token role and a slot, and renew itself; it is refused writing its own
  policy or the default one, reading a secret and minting a token.
- A custom token id with the `s.` prefix every minted token has is refused ("custom token ID cannot
  have the 's.' prefix"), so a new vault can never take over an old vault's tokens. That is why an
  older install moves in place.
- **The whole move of an older install, `switch-to-auto-unseal.sh`, rehearsed end to end** against
  a stand-in shaped like a real one (a compose project owning its network, Shamir five of three,
  the 2026-09-21 policies, a secret in each engine, and two containers holding the application's
  and the worker's tokens in a stored compose file): wrong pieces and a missing pieces file refused
  with nothing changed; after the move, the same tokens read the same secrets through the vault's
  service name, the new engine and grant are in force, the deploy token confirms it, the three files
  are root-only, `docker restart` reopens it, an old piece no longer makes a root token, a second
  run is safe, a later release's policy change is applied by the deploy token and a change to the
  deploy policy is refused, `--rollback` restores the Shamir vault with the same tokens and
  secrets, `--recovery-split` keeps five recovery pieces, and no piece or token appears in any of
  its output. The record of that run is in the pull request that added the script.

## 1. A fresh install writes the seal key and keeps one recovery key

On a clean server, `standard` profile, at a terminal:

```
sudo BRAIN_RELEASE_URL=<the archive> bash install.sh --release <tag> --profile standard \
  --console-address <the proxy's address>
```

Expected, and each is a check:

- Step `make the secrets vault's seal key` says where the key is, and prints no key.
- Step `initialise the secrets vault and keep its recovery key` says where the recovery key is and
  prints no key and no root token.
- `sudo stat -c '%a %U %s' /etc/brain-vault /etc/brain-vault/*` shows `700 root` for the
  directory and `400 root` for `seal.key` (32 bytes), `recovery.key` and `deploy.token`.
- `docker exec brain-vault bao status` reports `Seal Type static`, `Sealed false` and `Total
  Recovery Shares 1`.
- Step `apply this release's vault policies, engines and roles` says `already done, skipping`,
  because the deploy token already confirms everything; `sudo sh /opt/brain/ops/openbao/apply-release.sh --check`
  prints the `in force` line.
- `sudo grep -c '^BRAIN_VAULT_ADDRESS=http://vault:8200$' /opt/brain/.env` is `1`, and
  `BRAIN_VAULT_TOKEN` and `BRAIN_WORKER_VAULT_TOKEN` each have a value.
- Run once more with `--recovery-split` on another clean server: five `piece N of 5` lines are
  printed once, no `recovery.key` is written, and the status shows five recovery shares.

## 2. The root token is gone and the tokens are what was minted

Make a root token from the recovery key (`UNSEAL.md`, In an emergency, steps 1 to 3), then:

```
docker exec -e BAO_TOKEN brain-vault bao list auth/token/accessors
docker exec -e BAO_TOKEN brain-vault bao token lookup -accessor <each accessor>
```

Expected: no token with policy `root` other than the one just made; one with `application,
default` and one with `default, worker`, each `period 768h`, `renewable true`, `orphan true`; one
with `deploy` only, `period 8760h`, `orphan true`. `bao secrets list` shows `providers/`,
`webhooks/`, `connector_keys/` and `template_signing/` as `kv` version 2, `bao audit list` shows
`file/` and `stdout/`, `bao policy list` shows every file in `ops/openbao/policies`. Revoke the
root token.

## 3. The wizard keeps the key with no hand edit (M42.6.2)

Open `/first-run`, choose a hosted provider and paste a key. Expected: the appointment answers
200, not 409, and with a root token from the recovery key `docker exec -e BAO_TOKEN brain-vault bao
kv metadata get providers/anthropic` shows version 1. Nothing was typed into `/opt/brain/.env`.

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

## 5b. The template signing key is minted once and cannot be replaced (M13.8.10)

- The installer printed `step N of M: keep this install's template signing key - already done,
  skipping` (the application minted it at start), or ran it and printed `Template signing key:
  held.`
- With a root token from the recovery key: `docker exec -e BAO_TOKEN brain-vault bao kv metadata get
  -mount=template_signing key` shows `current_version 1`.
- The application's token cannot write it again: pipe `{"data":{"key":"x"}}` into
  `docker exec -i -e BAO_TOKEN brain-vault bao write template_signing/data/key -` with `BAO_TOKEN`
  set from `/opt/brain/.env`'s `BRAIN_VAULT_TOKEN`. It is refused with `permission denied`, because
  a write to a slot that holds a version needs `update`, and the metadata still shows version 1.
- `docker compose <files> restart app`, then the metadata still shows version 1 and the log shows
  `template signing key held minted_here=False` for every process.
- **Credentials** says "Template signing key: held"; publish an agent from a draft and install it.
- Revoke the root token.

## 6. A restart, a reboot, then an update that changes a policy

- `docker restart brain-vault`: `bao status` says `Sealed false` within seconds and the application
  still answers. Reboot the server: the same, with nobody typing anything.
- Run `ops/update/update.sh standard <tag>` onto a release whose `ops/openbao/policies` differ from
  the running one. Step `apply this release's vault policies, engines and roles` prints the
  `in force` line, and `docker exec -e BAO_TOKEN brain-vault bao policy read application` (root
  token from the recovery key) shows the new text. The `app` and `brain-worker` containers are on
  the `brain-vault` network afterwards: `docker network inspect brain-vault`.

## 7. The automatic deploy applies a release's vault changes (M31.3.2.2)

On a server deploying itself with `ops/deploy/brain-deploy`: publish an image whose policies differ.
The deploy's journal (`journalctl -u brain-autodeploy.service`) shows the `vault: in force` line
before `health gate: starting`, and the policy reads back as the new text. Remove the deploy token
file for one deploy: the journal says there is none and the deploy goes on.

## What stays open until this has run

- **M31.3.2.1 and M31.3.2.2, the half that is a server**: sections 1, 2, 6 and 7 on a fresh
  install, and the owner's own install moved with `switch-to-auto-unseal.sh`.
- **M13.8.10, the half that is a server**: that the owner's install, with this release's policies
  in force, mints and holds its template signing key.
- **M42.6.2, the half that is a server**: sections 1 and 3.
- **M42.5.14, the same half, and one more**: an application container at its default memory
  starts four uvicorn workers, so on that install the finishing screen honestly asks for a restart
  rather than landing at once. It lands at once only where the application serves alone.
