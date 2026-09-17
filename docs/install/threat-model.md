# Threat model: what an install exposes

This page is for whoever answers for the security of one install. It lists every surface a person or
a machine outside the server can reach, what an attacker would want from each, and what stands in
the way. It ships inside every release archive, so the model you read matches the release you run.

**Checked by `tests/unit/test_threat_model.py`, in both directions.** Every first path segment the
application serves has a row below, and every row naming a path is one the application serves.
Every service a compose file publishes a port for, and every service the network guide says a
browser reaches through your proxy, has a row. A surface added to the product without a row here
fails the build. What each row says is prose, and nothing checks it.

## What is being protected

1. **Your business records**, which the connectors read. The whole design rests on one rule: an
   answer never contains more than the person asking may see, and an agent never sees more than the
   person it runs for. A leak here is silent: a plausible answer that is simply too wide.
2. **The credentials** the install holds for your source systems and model providers, kept in the
   vault and never written to the database or a log.
3. **The audit ledger**, which is append-only and is the record of who saw what.
4. **The server itself**: every container, the database and every environment value.

## Who we assume is trying

| Actor | What they can already do | What they want |
| --- | --- | --- |
| Anyone on the internet | Reach whatever your proxy publishes | Records, credentials, a foothold on the server |
| A signed-in member of staff | Everything their own grants allow | A record their grants do not allow, or proof that one exists |
| An administrator of one department | Grant within that department | Reach outside it |
| A compromised source system or model provider | Send the install data it chooses | Make an answer or an automation do something nobody asked for |
| Somebody who can change this repository | Ship code to every install | Anything; this is why review is required on the files that decide reach |

## Every exposed surface

<!-- checked: every exposed surface -->

| Surface | Who reaches it | What an attacker wants from it | What stands in the way |
| --- | --- | --- | --- |
| `/` | Anyone, through your proxy | Nothing: the console's shell and its static files | Serves no record; every read the console makes goes through `/api` |
| `/login` | Anyone, through your proxy | A session | Sign-in is the identity provider's, with a second factor required of every account; the application holds no password |
| `/setup` | Anyone, until the first administrator is appointed | To appoint themselves | The setup code is asked before anything else, and a finished install, a wrong code and an expired one all answer the same 404 |
| `/admin` | Signed-in staff | Reach they were not granted | Every screen decides what its reader may see and writes nothing; reach is the one intersection in `brain.core.entitlement` |
| `/me` | Signed-in staff | Another person's details | Answers for the session's own principal only |
| `/ask` | Signed-in staff | A record outside their reach, or a count of hidden records | The gate: identify, entitle, screen, and a redactor that removes fields the asker may not see. DENIED and ABSENT answer identically |
| `/api` | Signed-in staff and the channel adapters | Every route above, without the console in the way, and inbound webhooks | The same gate on every route; an inbound webhook is trusted only as far as `brain.ops.inbound_webhooks.INBOUND` records its signature check as written, and that table says which channels have none yet; `/api/status.json` and `/api/deploy-checks.json` are public and name no record, no count of records and no finding |
| `/build` | Anyone, through your proxy | Which release you run, to match it against known flaws | Describes the build and never a client record. Consider restricting it at the proxy |
| `/health` | Your proxy and monitoring | Which commit you run | Reports status and the commit only |
| `/docs`, `/redoc`, `/openapi.json` | Anyone, when `BRAIN_ENV` is not `production` | The full map of every route and field name | Switched off in production. A staging install serves them, so keep a staging install off the public internet or behind the proxy's allowlist |
| `keycloak` | Staff browsers, through your proxy | Accounts, and the admin console's control of every account | Second factor required; the admin paths behind the proxy's address allowlist (see the network guide) |
| `activepieces` | Staff, through your proxy, on `full` | A flow that reaches something it should not | Flows call tools through the same gate as a person, and the egress proxy refuses every destination not allowed |
| `langfuse-web` | Whoever operates the install, through your proxy, on `full` | Every question and answer after masking | Sign-in through the identity provider; not for staff |
| `cloudflared` | Nothing inbound: it dials out | A way in that bypasses your firewall | Carries only the application and identity provider addresses, joins only their network, and its token is kept off the command line |
| `pgbouncer` | The data host's private address, on the split profile only | The database | Bound to a private address; the application role cannot bypass row-level security |
| `pgbouncer-session` | The data host's private address, on the split profile only | The database, for the workers | As above |
| `seaweedfs` | The data host's private address, on the split profile only | Stored documents | Bound to a private address; not published on a single host |
| `ssh` | Whoever holds a key for the server | The whole server | Yours to restrict to keys; nothing in the product needs a deployment key held anywhere off the server |
| `deployment panel` | Administrators, where one is used | Every container and environment value | Its own second factor and the address allowlist in the network guide; the product never calls its API from outside the server |
| `registry pull` | The server, outbound | To ship a malicious image to your server | Images are signed at build and the release tag is put only on a digest whose signature verifies against this repository's workflow |
| `outbound calls` | The server, to your source systems and model providers | To feed the install data that changes an answer or starts an action | Source data is treated as data and never as an instruction to the gate; an answer only ever narrows what the asker can already see, and an action waits on the approval its tool requires |

## What the product itself checks, and where

| Control | Checked by |
| --- | --- |
| Row-level security on every table | `brain.ops.sweeps rls` in CI, and after every staging deploy by `brain.ops.post_deploy` |
| Every reach is offered exactly its grants, and a refusal is identical to an absence | The permission canaries: twice a day on the worker, and after every staging deploy |
| Licences, archived and stale dependencies, every image's terms | `brain.ops.dependency_policy`, the `Dependency audit` job |
| Known vulnerabilities in every lock and the image | `brain.ops.vulnerabilities`, the `Vulnerability scan, locks and image` job, with exceptions in `ops/security/vulnerability-exceptions.json` |
| Review of the files that decide reach | `.github/CODEOWNERS`, enforced only when branch protection requires code owner review |

## What this model does not cover

- **Your own network and identity provider policy.** Password rules, who may be an administrator
  and how staff devices are managed are yours.
- **A model provider's handling of what it is sent.** The install sends a provider only what the
  asker may see, after masking; what the provider keeps is governed by your agreement with it.
- **A person with root on the server.** They can read everything, by design of any self-hosted
  system. Protect that account as you would the database itself.
