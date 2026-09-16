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

They are therefore read once at startup, straight into the process environment where the
provider SDK finds it, and never held by application code. Rotation is a restart, which
costs three minutes here.

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

Done once on each install that runs a vault, by whoever holds a token that may write policy,
which during first setup is the root token before `UNSEAL.md` step 6 revokes it. No value in
these steps belongs to any particular install, and none is written into this repository.

1. Enable a version 2 kv engine at the prefix the code reads: `bao secrets enable -path=providers kv-v2`.
2. Load the policies, which now include the provider slots in `application.hcl`:
   `sh ops/openbao/load-policies.sh`.
3. Mint the application's token against that policy alone, as an orphan with a period, and
   read it once from the terminal: `bao token create -orphan -policy=application -period=768h`.
   Nothing in the application renews this token yet, so a process that outlives the period is
   refused by the vault and says so; restarting the application does not renew it either.
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

**Why step 5 is an overlay and is done by hand once.** The vault's network is created by the
vault's own compose project, so it exists only on a server that runs the vault, and a base compose
file naming it would stop every install without one from starting. The overlay is composed only
where the vault is, as `docker-compose.tunnel.yml` is for the tunnel, and the environment file's
address is the record that it was chosen. The installer does not compose it, because a vault is
unsealed, given its policies and asked for a token after the install has finished, never during
it. `brain.deployment.app_environment` argues the shape and `tests/unit/test_app_environment.py`
holds the overlay, both scripts and the base files to it.

**On a deployment panel that keeps its own copy of the compose file**, the scripts never run, so
step 5 is made in that copy: add the two variables to the `app` service's `environment` exactly as
`docker-compose.vault.yml` writes them, add `brain-vault` to its `networks`, declare `brain-vault`
at the bottom of the file as `external: true` with `name: brain-vault`, set both values in the
panel's environment variables, and redeploy.

## Webhook signing secrets

A webhook subscriber is told when something happens here, and every request it receives is
signed with a secret it shares with this system. A shared secret cannot be minted per request,
because the receiver checks every delivery against the same value, so it is stored rather than
leased, under an engine of its own at `webhooks/`, one path per subscriber named by the
subscriber's id. An administrator holding `admin:webhook_subscriber` writes it when registering
a subscriber on the console's Webhooks screen and replaces it there when rotating; the screen
says whether one is held and when it was written, and never shows it.

The application's policy may create and update `webhooks/data/+` and read `webhooks/metadata/+`,
and nothing else there. It never reads a signing secret back. Nothing on an install delivers to a
subscriber yet, and when a dispatcher is built it reads the secret under the worker's policy,
which does not name this engine today.

To let the application keep them, once per install that runs a vault:

1. Enable a version 2 kv engine at that prefix: `bao secrets enable -path=webhooks kv-v2`.
2. Load the policies: `sh ops/openbao/load-policies.sh`.

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
source's own settings as well. Nothing on an install reads from a connected source yet, because
no worker runs a connector, and when one does it reads the key under its own policy, which does not
name this engine today.

To let the application keep them, once per install that runs a vault:

1. Enable a version 2 kv engine at that prefix: `bao secrets enable -path=connector_keys kv-v2`.
2. Load the policies: `sh ops/openbao/load-policies.sh`.

Until both are done, connecting a source is refused with a sentence saying the vault refused, and
nothing is recorded as connected.

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
