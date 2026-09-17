# Credential slots: what each connector needs, and what it must not be given

Task ids: M38.4.1.3, M5.1.2

Every slot below is **defined and empty**. The path exists, the policy that reaches it
exists, and there is no credential in it until go-live. That ordering is the point: the
scopes are argued about now, while it costs nothing, rather than during the hour somebody
is trying to get a connector working.

**The rule for every row: request the narrowest scope the connector can do its job with, and
never a write scope for a connector that only reads.** A scope granted "to save a round trip
later" is a scope nobody removes.

| Slot | Connector | Scope to request | Deliberately NOT requested |
|---|---|---|---|
| `connectors/creds/xero` | Xero | `accounting.transactions.read`, `accounting.contacts.read` | `.write` on anything. The Brain answers questions about invoices; it does not raise them |
| `connectors/creds/lark_base` | Lark Base | `bitable:app:readonly`, `base:record:read` | `base:record:write`, `drive:drive`. Read-only is already what the existing bot holds |
| `connectors/creds/lark_wiki` | Lark Wiki | `wiki:wiki:readonly` | Anything under `docs:document` that would allow editing |
| `connectors/creds/freshdesk` | Freshdesk | Agent key, read scope | An admin key. An admin key can change SLAs and delete tickets |
| `connectors/creds/hubspot` | HubSpot | `crm.objects.contacts.read`, `crm.objects.deals.read` | `crm.objects.*.write`, and anything touching `settings` |
| `connectors/creds/laravel_readonly` | Laravel MySQL | A database user with SELECT on the allowlisted views only | SELECT on tables. The views are the contract; tables change shape without warning |
| `connectors/creds/google_drive` | Drive or M365 | Read on the specific shared drive | Domain-wide delegation. It reads everything, for everyone, for ever |
| `browser/creds/*` | Browser runner | One credential per site, per task | Anything reusable across sites |

## Model provider keys, which work differently

These are the one category that **cannot be leased**, and the difference is worth
understanding before somebody tries.

Every slot above is a credential the vault can mint fresh and take back: a database user, a
scoped OAuth token. A model provider's API key is not. OpenAI, Anthropic and Moonshot each
issue a key that is valid until a person revokes it in a dashboard, and no engine mints one
per request. So there is nothing to hand back, and wrapping one in a lease with an invented
expiry would be worse than admitting it: the caller would believe the key stops working at a
time nothing enforces.

They are therefore read at startup, straight into the process environment where the
provider SDK finds it, and never held by application code. **Rotation needs no restart**
since 2026-09-17: every application process reads each provider slot's metadata once a minute
and loads a key whose version moved (`brain.ops.credentials.keep_refreshing`), so a key
replaced from the console or with the vault's own command line is in use everywhere within a
minute. A variable the environment file sets still outranks the vault.

| Slot | Provider | Environment variable | Notes |
|---|---|---|---|
| `providers/anthropic` | Anthropic | `ANTHROPIC_API_KEY` | Claude, the default reasoner |
| `providers/openai` | OpenAI | `OPENAI_API_KEY` | Embeddings, and a fallback for completion |
| `providers/moonshot` | Moonshot | `MOONSHOT_API_KEY` | The cheaper reasoner; the v1 system routes here by default |

Since 2026-09-16 a provider key is **put in from the browser**: the setup wizard keeps the key
it asks for, and an administrator holding `admin:credential` sets or replaces one from the
console through `PUT /api/v1/credentials/providers/<provider>`. Both write the slot, both
answer that a key is held and when it was written, and neither ever answers with the key.
`brain.ops.credentials` argues why the application's policy may create and update these
slots, and the policy file says what it still refuses.

`providers/` is the **only** prefix the static read will touch, and the refusal lives on
`OpenBaoVault.read_static_kv` rather than on its caller. That placement matters: a guard on
the caller is a guard somebody bypasses by calling the other thing. Reading
`connectors/creds/xero` this way would work perfectly, hand out a standing credential with
nothing to revoke and no record of which run held it, and nobody would see the difference
until an audit asked.

## Letting the application keep a provider key

**The installer does every step of this on a fresh install**, and of the two sections below
about signing secrets and a connected source's key, since 2026-09-17: see `UNSEAL.md`, under
First install, which the installer now does for you. These are the same steps by hand, for an
install made before it did, or a `lite` install run with `--no-vault` that later wants a vault.
Done once, by whoever holds a token that may write policy, which during first setup is the root
token before `UNSEAL.md` step 6 revokes it. No value in these steps belongs to any particular
install, and none is written into this repository.

1. Enable a version 2 kv engine at the prefix the code reads: `bao secrets enable -path=providers kv-v2`.
2. Load the policies, which now include the provider slots in `application.hcl`:
   `sh ops/openbao/load-policies.sh`.
3. Mint the application's token against that policy alone, as an orphan with a period, and
   read it once from the terminal: `bao token create -orphan -policy=application -period=768h`.
   The application renews it itself while it runs, once less than half the period is left
   (`brain.ops.vault_renewal`), so it lapses only if no application process runs for longer
   than the period. A token minted without a period cannot be kept alive that way, and the
   renewal says so.
4. Put the vault's address as the application container reaches it, and that token, into the
   install's environment file as `BRAIN_VAULT_ADDRESS` and `BRAIN_VAULT_TOKEN`. With the vault
   run from `ops/openbao/compose.yml` beside the install, the address is `http://`, then the
   vault's service name as that file declares it, then a colon and the port it exposes: the
   name on the vault's own network, never an address on the host, because the vault publishes
   none.
5. Compose the vault overlay onto the application, from the install directory:
   `docker compose <the profile's -f files> -f /opt/brain/docker-compose.vault.yml up -d app`.
   `docker-compose.vault.yml` hands the application both variables and joins it to the
   `brain-vault` network, and it refuses to compose when either variable is missing, naming it.
   You do this once: from then on `ops/update/update.sh` and `ops/update/rollback.sh` compose it
   in themselves whenever the environment file holds a `BRAIN_VAULT_ADDRESS` value.
6. Remove any `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `MOONSHOT_API_KEY` line from the
   environment file once the vault holds that key. A variable the environment sets outranks the
   vault on every start, so a key replaced from the console would otherwise not be the one in use.
7. Restart the application, and turn on the audit device if it is not on (`enable-audit.sh`),
   because the vault's log is the one record of each write by path until the ledger has one.

**Why step 5 is an overlay.** The vault's network is created by the vault's own compose project,
so it exists only on a server that runs the vault, and a base compose file naming it would stop
every install without one from starting. The overlay is composed only where the vault is, as
`docker-compose.tunnel.yml` is for the tunnel, and the environment file's address is the record
that it was chosen. The installer composes it in as its own step once it has written that address,
and the update and rollback read the same line. `brain.deployment.app_environment` argues the
shape and `tests/unit/test_app_environment.py` holds the overlay, the scripts and the base files
to it.

**On a deployment panel that keeps its own copy of the compose file**, the scripts never run, so
step 5 is made in that copy: add the two variables to the `app` service's `environment` exactly as
`docker-compose.vault.yml` writes them, add `brain-vault` to its `networks`, declare `brain-vault`
at the bottom of the file as `external: true` with `name: brain-vault`, set both values in the
panel's environment variables, and redeploy.

## The mail relay's password

Email is sent through a relay an administrator configures on the console's Notifications screen:
its host, port, whether the connection starts in TLS or is upgraded with STARTTLS, the sender
address and a user name are saved there, and a relay that offers neither form of TLS is refused.
The password is written from the same screen into `providers/mail_relay`, under the field
`password`, and is never shown again; the screen says whether one is held and when it was written.
The write is recorded as a `credential` entry in the audit ledger, as every credential written
from the console is.

It sits in the providers engine because it is the same kind of thing: issued by whoever runs the
relay, valid until they revoke it, and read by the application, which is the process that sends.
The application's policy already grants that engine create, update and read, so nothing more is
loaded for it. A test message on the same screen proves the relay, the password and the sender
together, and is sent once for each saved configuration.

## Webhook signing secrets

A webhook subscriber is told when something happens here, and every request it receives is
signed with a secret it shares with this system. A shared secret cannot be minted per request,
because the receiver checks every delivery against the same value, so it is stored rather than
leased, under an engine of its own at `webhooks/`, one path per subscriber named by the
subscriber's id. An administrator holding `admin:webhook_subscriber` writes it when registering
a subscriber on the console's Webhooks screen and replaces it there when rotating; the screen
says whether one is held and when it was written, and never shows it.

The application's policy may create and update `webhooks/data/+` and read `webhooks/metadata/+`,
and nothing else there. It never reads a signing secret back. The general worker delivers every
minute and reads each subscriber's secret under the worker's policy, which may read
`webhooks/data/+` and nothing else under that engine. A worker is given the vault the way the
application is: `BRAIN_VAULT_ADDRESS`, and a `BRAIN_VAULT_TOKEN` minted against the worker policy
rather than the application's. A worker without them sends nothing, and every dispatch run fails
naming the two settings, which the Webhooks screen shows.

To let the application keep them, once per install that runs a vault:

1. Enable a version 2 kv engine at that prefix: `bao secrets enable -path=webhooks kv-v2`.
2. Load the policies: `sh ops/openbao/load-policies.sh`.
3. Mint the worker's token against its policy: `bao token create -orphan -policy=worker -period=768h`, and
   append it to the install's environment file as `BRAIN_WORKER_VAULT_TOKEN`. On `standard` and
   `full` the installer, the update and the rollback then compose `docker-compose.vault.worker.yml`
   in, which hands it to the worker as `BRAIN_VAULT_TOKEN` with `BRAIN_VAULT_ADDRESS` beside it
   and joins the worker to the vault's network. The worker's schedule renews it as
   `vault_token_renewal`.

## A connected source's key

Connecting a source from the console's Connectors screen keeps the key that source's vendor
issued for this company: a helpdesk's agent key, a CRM's private app token. Like a provider key,
nothing can mint one per run, so it is stored rather than leased, under an engine of its own at
`connector_keys/`, one path per source named by the source's short name. An administrator holding
`admin:connector` writes it by connecting the source; the screen says whether a key is held and
when it was written, and never shows it. The scopes to ask the vendor for are the ones in the
table at the top of this file.

The application's policy may create and update `connector_keys/data/+` and read
`connector_keys/metadata/+`, and nothing else there. It never reads a source's key back, and it
cannot delete one: disconnecting a source leaves its key in the vault, so revoke the key in the
source's own settings as well.

The worker reads a connected source on a schedule (`brain.ops.connector_sync_run`), and since
2026-09-17 its own token reads no key. For each attempt it mints a run token against the
`connector-run` token role, which carries the `connector-run` policy alone (read on
`connector_keys/data/+`, and revoking itself), lives fifteen minutes and cannot be renewed; it reads
the key with that token and revokes it when the attempt ends, and the attempt's row says whether the
revocation was confirmed. The worker's policy may mint against that role and nothing else under
`auth/token`. It asks only for the slot a live connection's own declaration names, and it needs its
own token, minted against the worker policy, in `BRAIN_VAULT_ADDRESS` and `BRAIN_VAULT_TOKEN` in the
worker's environment. The Secrets vault screen counts each source's leases over the last day. Without one every due source is recorded as failed with a sentence saying the worker
has no vault, and the Connectors screen shows it.

To let the application keep them and the worker read them, once per install that runs a vault:

1. Enable a version 2 kv engine at that prefix: `bao secrets enable -path=connector_keys kv-v2`.
2. Load the policies: `sh ops/openbao/load-policies.sh`, which also loads `connector-run.hcl`.
3. Create the token role the worker mints against, exactly as the installer does:
   `bao write auth/token/roles/connector-run allowed_policies=connector-run orphan=false renewable=false token_no_default_policy=true token_explicit_max_ttl=3600`.
4. Define every source's slot with its scopes and no key, as the installer does, one
   `bao kv metadata put -mount=connector_keys` per row of the table below, with the two columns as
   `-custom-metadata='scopes=...'` and `-custom-metadata='not_requested=...'`. The Secrets vault
   screen then says each slot is defined and empty, rather than missing.

Where each source's key is kept, and what the installer defines it with (`brain.ops.connector_slots`
is the catalogue, and a test holds this table to it):

| Key slot | Source | Scopes | Not requested |
|---|---|---|---|
| `connector_keys/freshdesk` | freshdesk | an agent API key with read access | an admin key, which can change SLAs and delete tickets |
| `connector_keys/google_drive` | google_drive | read on the named shared drive only | domain-wide delegation |
| `connector_keys/hubspot` | hubspot | crm.objects.contacts.read; crm.objects.deals.read | crm.objects.*.write; anything touching settings |
| `connector_keys/laravel` | laravel | SELECT on the allowlisted views only | SELECT on tables; any write |
| `connector_keys/lark_base` | lark_base | bitable:app:readonly; base:record:read | base:record:write; drive:drive |
| `connector_keys/lark_wiki` | lark_wiki | wiki:wiki:readonly | docs:document edit scopes |
| `connector_keys/xero` | xero | accounting.transactions.read; accounting.contacts.read | any .write scope |

Until both are done, connecting a source is refused with a sentence saying the vault refused, and
nothing is recorded as connected.

## The object store's key

The application reads and writes the object store with one key pair, read from the vault once when
it starts. Nothing else gives it one: `brain.ops.object_store` signs every request with exactly the
key it was handed, and deliberately uses no client library that would find a key in the
environment. Until the slot holds a key, the Storage screen says the store is not connected and
why, the Backup and recovery screen says nothing has looked in the backup bucket, and nothing can
keep an artifact.

The slot is the one for the backend `INSTALL_OBJECT_STORE_BACKEND` names, and it holds two fields,
`access_key_id` and `secret_access_key`. The application's policy already reads
`providers/data/+`, so no policy changes.

| Slot | Backend | Holds | Deliberately NOT |
|---|---|---|---|
| `providers/seaweedfs` | the file store this product ships | the key pair of the `brain-application` identity in `ops/seaweedfs/s3.json`, which may read, write and list | an identity with `Admin`, which can delete a bucket |
| `providers/cloudflare-r2` | Cloudflare R2 | an R2 API token's key pair scoped to this install's buckets, object read and write | an account-wide token |

AWS S3 has no slot here. Its key is a lease from the vault's `aws` engine, and the application
holds its store client for as long as it runs and renews nothing, so a client built from a lease
would stop working when the lease ran out. The application refuses to connect to it and says so.

Once per install that runs a vault, with a token that may write the slot:

1. Put the same key pair in the file store's identities file, `/opt/brain/settings/seaweedfs/s3.json`,
   in place of the two `REPLACE_AT_DEPLOY_FROM_OPENBAO` values, and restart the `seaweedfs` service.
2. Write the two fields into the slot with the vault's command line, as a version 2 key-value
   write to the slot above, typing both values at the prompt from where you generated them rather
   than into a file or a command someone could read back from the shell history.
3. Restart the application. Its log says `object store connected`, or the Storage screen says why not.

## Three things worth deciding before the keys are issued, not after

**Xero's limit is per tenant and it is 5,000 a day.** That is a documented ceiling and it is
the one most likely to be hit by a backfill. The rate limits configured in the connector must
match the real account tier rather than the documentation, which is M38.4.2.3.

**Freshdesk search returns at most 300 records, ever.** Not a page size: a ceiling. Anything
that reads "all tickets matching" is wrong beyond 300 and will look correct in testing.

**Lark Base's 100 requests per minute is permanently uncapped** and does not rise with a
plan. Sizing anything against a higher number is sizing against a number that does not exist.

## What happens at go-live

M38.4.2.1 puts real credentials in these slots. Until then every one of them returns nothing,
and a connector asking for one gets a vault error rather than an empty string, which is the
difference between a visible outage and a connector that silently reads nothing and reports
that there is nothing there.
