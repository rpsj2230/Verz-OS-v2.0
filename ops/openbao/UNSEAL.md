# The secrets vault: what it does by itself, what you keep, and what to do when it goes wrong

For whoever runs the Company Brain on their own server. Written to be followed by someone who has
not read the code.

Task ids: M31.3.2.1, M31.3.2.2, M42.6.2

---

## What this is, in one paragraph

The vault holds the passwords and keys the system uses to reach your model provider, your mail
relay, Lark, Xero, Freshdesk and the rest. It keeps them out of configuration files, where they
would live as long as the server and appear in every backup and every screen-share. The console
only ever writes a key into it; nothing shows a key back.

## What happens when the server or the vault restarts

**Nothing you need to do.** The vault opens itself. When its container starts it reads a key file
that only root on this server can read, `/etc/brain-vault/seal.key`, and uses it to unlock its own
data. A reboot, `docker restart brain-vault` or an update all come back with the vault open and
nobody typing anything.

**The trade-off, said plainly** (your decision of 2026-09-29, Needs Rupash item 114): anyone who
has root on this server can open the vault. On one server that person can already read the
running application's memory, where every key the vault hands out ends up, so pieces held by five
people bought a ceremony at every restart rather than protection. It is reversible: see the last
section.

## What to keep, and where

Two things leave the server. Nothing else needs keeping.

1. **The seal key, `/etc/brain-vault/seal.key`.** Without it the vault's data can never be opened
   again, by anybody, and every key in it has to be issued again by hand. Copy it into your
   password manager as its own entry (it is 32 bytes: `sudo base64 /etc/brain-vault/seal.key`
   prints it in a form you can paste, and `base64 -d` turns it back), or into your company's own
   key store. **Never put it beside a backup of the vault's data**: whoever holds both can open
   that copy. The product's own nightly backup copies the database and never this directory.
2. **The recovery key, `/etc/brain-vault/recovery.key`.** It does not open the vault. It makes a
   root token in an emergency (below). Move it into your password manager, then delete the file:
   `sudo shred -u /etc/brain-vault/recovery.key`. If your install chose five recovery pieces
   instead (see the numbers, below), there is no file: five people hold one piece each.

**What stays on the server, root-only, and needs nothing from you:** the seal key itself (the vault
reads it at every start) and `/etc/brain-vault/deploy.token`, which lets each release apply its own
vault changes. The directory is mode `0700` and each file `0400`.

The application's and the worker's own tokens are in `/opt/brain/.env` (or your hosting panel's
settings) and renew themselves while they run.

## The numbers, and where they live

The vault is initialised once, with a recovery split. The default is one recovery key; a company
that wants no single person able to make a root token chooses five pieces, any three of which are
needed, with `--recovery-split` on the installer. **Neither number is typed into this page.** They
live in `brain.ops.vault_quorum`, which refuses the combinations that initialise perfectly and ruin
you later (five pieces any one of which works alone; five pieces all of which are needed), and a
test compares what it prints against this page. To see both choices and every command below:

    uv run python -m brain.ops.vault_quorum

The default, which the installer runs:

    docker exec -it brain-vault bao operator init -recovery-shares=1 -recovery-threshold=1

The stricter choice:

    docker exec -it brain-vault bao operator init -recovery-shares=5 -recovery-threshold=3

**Changing the split later is not an edit.** It is `bao operator rekey -target=recovery`, which
needs the current recovery key or pieces.

## First install, which the installer does for you

`ops/install/install.sh` runs the vault on every profile (a `lite` install may decline it with
`--no-vault`). In five steps of its own it writes the seal key, starts the vault, initialises it
and keeps the recovery key, configures it and hands out its tokens, and applies the release's vault
changes with the deploy token to prove that works. `brain.deployment.vault_setup` is the code and
the argument. What you do afterwards is the two copies under "What to keep".

## First install by hand

For a server where the installer does not run, a hosting panel for instance. Each step is one the
installer makes, and the order matters: the seal key has to exist before the vault first starts.

1. The seal key, root-only: `sudo install -d -m 0700 /etc/brain-vault`, then
   `sudo sh -c 'head -c 32 /dev/urandom > /etc/brain-vault/seal.key && chmod 0400 /etc/brain-vault/seal.key'`.
2. The network and the vault: `docker network create brain-vault`, then
   `docker compose -f ops/openbao/compose.yml up -d`.
3. Initialise it once, with the line under "The numbers" above. It prints a recovery key (or five
   pieces) and a root token, once. Keep the recovery key as "What to keep" says, and put the root
   token into this shell without it reaching the screen: `read -rs BAO_TOKEN; export BAO_TOKEN`,
   then paste it.
4. The release's engines, policies, token role and slots: `sudo -E sh ops/openbao/apply-release.sh`.
5. The token method's ceiling, so the deploy token lives a year between releases:
   `docker exec -e BAO_TOKEN brain-vault bao auth tune -max-lease-ttl=8760h token/`.
6. The application's and the worker's tokens, as `ops/openbao/credential-slots.md` says, handed to
   the application with the vault's address `http://vault:8200`; and the deploy token, as step 4 of
   "In an emergency" below says.
7. Step 5 of "In an emergency": revoke the root token.

## Every release keeps the vault up to date by itself

A release can change a policy (what the application or the worker may read) or add an engine (a
new kind of secret). Each release carries its own `ops/openbao/apply-release.sh` and policy files,
and its deploy runs them with the deploy token before the new application starts:

- on a server that updates with `ops/update/update.sh`, step "apply this release's vault
  policies, engines and roles";
- on a server that deploys itself on a timer (`ops/deploy/brain-deploy`), from inside the new
  image, before anything runs it.

It enables any engine the release adds, loads every policy, defines the connector-run token role
and the source slots, reads every one back, and prints one line:

    vault: in force: 4 engines, 5 policies, the connector-run token role and 8 credential slots

It never removes anything and never reads a secret. A release that changed nothing changes nothing.

### When a release's vault changes do not take

The deploy stops (a timer deploy holds the new image back; an update stops before recreating the
containers) and the lines above it name what did not take. What they mean:

- **"the vault refused the token this ran with"**: the deploy token has lapsed (it lives a year and
  every deploy renews it) or was revoked. Make a new one: "In an emergency", then step 4 there.
- **"this release changes the deploy token's own policy"**: the one policy a deploy may not load
  itself, so a deploy can never widen its own reach. Load it with a root token: "In an emergency".
- **"not running, or is sealed"**: see "If the vault stays sealed".
- anything else names an engine, a policy or a slot; running the step again is safe.

To check by hand at any time, as root in the release directory:

    sh ops/openbao/apply-release.sh --check

## If the vault stays sealed

`docker exec brain-vault bao status` says `Sealed true` and does not change. The vault could not
read its seal key:

1. `sudo ls -l /etc/brain-vault/seal.key` must show `-r-------- 1 root root 32`. If the file is
   missing, put your copy back (`base64 -d` from your password manager entry into that path, then
   `sudo chmod 0400` it), then `docker restart brain-vault`.
2. `docker logs brain-vault` names the fault if the file is there but wrong: a key that is not the
   one the vault was initialised with cannot open it, and nothing but the right key will.

The console's Credentials screen says the same thing in words while it lasts.

## In an emergency: a root token from the recovery key

Needed only for the two cases above (a lapsed deploy token, a change to the deploy token's own
policy) or to finish an interrupted install. The root token can do anything, so it lives for this
sitting only.

1. Start: `docker exec -it brain-vault bao operator generate-root -init`. It prints a **Nonce** and
   an **OTP**. Leave both on the screen.
2. Give the recovery key: `docker exec -it brain-vault bao operator generate-root -nonce=<the Nonce>`
   and paste it at the prompt, which does not show it. With five pieces, three people do this in
   turn. The last one prints an **Encoded Token**.
3. Put the root token into this shell without it reaching the screen, the encoded token on standard
   input so no process list ever holds both halves:
   `export BAO_TOKEN="$(printf '%s' '<the Encoded Token>' | docker exec -i brain-vault bao operator generate-root -decode=- -otp=<the OTP>)"`.
   Step 5 revokes it, which makes anything left in this shell's history useless.
4. Do what you came for:
   - a new deploy token: `docker exec -e BAO_TOKEN brain-vault bao token create -policy=deploy -no-default-policy -orphan -period=8760h -field=token | sudo tee /etc/brain-vault/deploy.token >/dev/null`,
     then `sudo chmod 0400 /etc/brain-vault/deploy.token`;
   - a release's deploy policy: `sudo sh ops/openbao/apply-release.sh` from the release directory,
     which uses `BAO_TOKEN` when it is set.
5. Step `revoke_root`. Revoke the root token and clear it:

       docker exec -it brain-vault bao token revoke -self

   then `unset BAO_TOKEN`.

**Why the root token is never kept, not even in an envelope.** It bypasses every policy in
`ops/openbao/policies`, and the audit log cannot tell its use from an administrator's: an entry
records a token as an HMAC with no field marking it as root. An envelope protects the paper, not
the token. The recovery key makes a new one whenever it is needed, and leaves a record that it did.

## Finishing what the installer began

The root token existed only in the shell that initialised the vault. If the install stopped after
"initialise the secrets vault and keep its recovery key" and before `/opt/brain/.env` held the
tokens, a second run stops at the same place and sends you here:

1. Make a root token from `/etc/brain-vault/recovery.key`: "In an emergency", steps 1 to 3.
2. Apply the release's vault changes as root: `sudo -E sh ops/openbao/apply-release.sh` from
   `/opt/brain`.
3. Mint the tokens as `ops/openbao/credential-slots.md` says, append `BRAIN_VAULT_ADDRESS`,
   `BRAIN_VAULT_TOKEN` and, on `standard` or `full`, `BRAIN_WORKER_VAULT_TOKEN` to `/opt/brain/.env`,
   and mint the deploy token (step 4 above).
4. Revoke the root token (step 5 above) and run the installer again: every step already done says
   so and skips.

## Moving an older install

An install made before 2026-09-29 has a vault that people unseal, and its releases' vault changes
wait for three of them. One command moves it onto the seal that opens itself, in place: every
secret, engine and token stays exactly as it is, so nothing that hands the application its token
(a hosting panel's stored settings, `/opt/brain/.env`) changes. It needs three of the vault's
unseal pieces, in a file shaped as `bao operator init` printed them (`Unseal Key 1: ...` lines).

As root on the server, from this release's `ops/openbao` directory:

    sudo bash switch-to-auto-unseal.sh --pieces-file <the file holding the pieces>

It proves the pieces against the running vault before changing anything, stops the vault for
under a minute, keeps a dated copy of its data under `/root/brain-vault-backups`, moves the seal,
restarts the vault once to prove it opens itself, rekeys the old pieces into one recovery key
(`--recovery-split` keeps them as five recovery pieces instead), applies the release's vault
changes, mints the deploy token, checks every token the containers hold, restarts them, and prints
what to keep. The old pieces open nothing afterwards. It is safe to run again.

**To go back**, while that dated copy exists:

    sudo bash switch-to-auto-unseal.sh --rollback --pieces-file <the same file>

It restores the data as it was before the move and opens it with the pieces, as before. Anything
written to the vault after the move is lost, and it says so first.

### If the pieces are lost

The in-place move needs three pieces and refuses without them. A vault whose pieces are gone keeps
working for as long as its container is never restarted, because it is open now; a restart seals
it for good. Do not restart it, and ask for the rebuild described in Needs Rupash item 114: a new
vault beside it, the secrets copied by the tokens that can read them, and new tokens handed to the
application, which is the one change a hosting panel's stored settings would need.

## Things worth knowing before they happen

**Losing the seal key means losing the vault.** Not the data the Brain holds, which is in
Postgres, but every credential stored here: every key re-issued by hand from every provider.
That is the reason for the copy under "What to keep".

**The seal key and a copy of the vault's data are two halves of the same key.** Keep them apart.

**The deploy token can widen what the application's tokens reach**, because it loads their
policies, so it is as sensitive as the vault and lives beside the seal key. It cannot read a
secret, write one, mint a token, remove anything, or change its own policy.

**Going back to pieces held by people** is `bao operator rekey` and a seal migration the other way,
with the recovery key. Ask for it and it will be written up; nothing about this install stops it.
