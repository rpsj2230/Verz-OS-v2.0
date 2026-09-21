# Configuration: every value you have to set

This is the whole list. Nothing else in this repository is edited for your install: you copy
`.env.example` to `.env` on your own server and fill values in, and that file is the only thing
that differs between your system and anybody else's.

**Read the profile column first.** Most installs run `lite`, which is the application, the
connection pooler, the database and the cache. Twenty of the rows below belong to components
that only `standard` and `full` deploy, and on `lite` there is nothing to set them for.

## Where the values come from

There are three answers and the table gives one of them per value. Two rows are not lines in
the environment file at all: `BRAIN_RELEASE` is the installer's first argument and
`BRAIN_RELEASE_URL` is read from the environment when it runs. They are in the table because
the leaf this page answers asks for every value in one table, and a value in a second place is
a value somebody misses.

**`installer`.** The install script mints it on your own server, with `openssl rand`, and
appends it to your `.env`. You never type it and it is never the same on two installs. If a row
says `installer`, leave it alone: setting it yourself after the first run is how a stack ends up
with a database password that does not match the database volume it already has.

**`wizard`.** The setup wizard asks for it on a numbered screen the first time you open the
console. You may set it in the file instead, and the wizard will show what is already there.

**`you`.** Nothing mints it and no screen asks for it. It has to be in the file before the
stack starts.

## What "default: none" means, and why it is not blank

A value with no default is a value that resolves to an empty string when nobody sets it. The
compose files spell that two ways and neither of them is an error: `${POSTGRES_PASSWORD}` and
`${APP_ROLE_PASSWORD:-}` both hand the container an empty password, the container starts, and
the first connection is refused with a message about authentication rather than about a
variable nobody set. So `none` in the default column means the install does not work until you
supply one, whatever it looks like at startup.

A value with a default works unset. Change it when you have a reason, not before.

## The table

The first four columns are checked against this repository on every test run:
`.env.example`, the install script's mint step, and the compose files each profile composes.
A variable added to any of the three without a row here fails
`tests/unit/test_install_docs.py`. **The last column is not checked.** It is the sentence
somebody wrote, and it is the reason the table is worth reading.

<!-- checked: every value a new client must set -->

| Variable | Profiles | Comes from | Default | What it is for |
| --- | --- | --- | --- | --- |
| `APP_IMAGE` | every profile | installer | none | **Required.** The image this install runs, as `ghcr.io/rpsj2230/verz-brain-v2.0:<release tag>`, and every container of it reads this one variable, the realm importer included. The installer and the update script write it from the tag you give them, so you only type it on a deployment tool that keeps its own environment. There is no default: left unset, every compose file refuses to start and names this variable, because an install that names no image is not pinned to one. Setting it to another tag holds the whole install back. The application is handed the same value, and it is how the Version and updates screen names the release that is running. |
| `APP_ROLE_PASSWORD` | every profile | installer | none | The password for the database role the application connects as. Never the same as the database superuser's: if it is, the pooler's ceiling and the connections it reserves are one leaked value away from being nobody's ceiling. |
| `AUTOMATION_DB_PASSWORD` | full | you | none | The automation canvas's own database. It is a separate database with a separate login, and that is deliberate: the canvas runs work somebody assembled in a browser. |
| `AUTOMATION_ENCRYPTION_KEY` | full | you | none | What the automation canvas encrypts its own stored connections with. |
| `AUTOMATION_JWT_SECRET` | full | you | none | What the automation canvas signs its own sessions with. |
| `AUTOMATION_PUBLIC_URL` | full | you | none | The address your staff reach the automation canvas on. It is a second web address, separate from the console's. |
| `BRAIN_COMMIT_SHA` | every profile | you | yes | Which build is running, shown on `/health/ready`. The image bakes its own in, so setting it here replaces a true answer with whatever your deployment tool happens to know. Leave it. |
| `BRAIN_CORS_ORIGINS` | every profile | you | none | The console's own origin, only when you serve the console from a different address than the API. A normal install serves both from one address and leaves this empty. A JSON list of origins (scheme, host, optional port, no path); a wildcard is refused in every environment. |
| `BRAIN_DATABASE_URL` | every profile | you | none | The application's own login, when it should not be the owner's. Empty, the application uses `DATABASE_URL`. Set it to `postgresql://brain_app:<APP_ROLE_PASSWORD>@pgbouncer:5432/brain` (with `BRAIN_MIGRATION_DATABASE_URL` naming the owner, so migrations still run) and no request can read past row-level security. The bundled pooler admits `brain_app` by looking it up, and admits no role that bypasses row security that way. Use letters and digits only in this password: a `$` in a value that Coolify or Docker Compose writes to an environment file is read as a variable and silently removed, so the application sends a different password and every connection is refused. In Coolify, tick **Is Literal?** on the variable if the password already has one. |
| `BRAIN_ENV` | every profile | you | yes | `development`, `staging` or `production`. Production turns off the interactive API documentation, which otherwise lists every tool and capability the system has. Set it to `production`. |
| `BRAIN_INFERENCE_URL` | every profile | you | none | Whether this install is allowed a model-reading destination at all. Startup refuses it on a profile that deploys no inference server, because a value copied from another install is somebody declaring a destination they did not choose. It is not the address anything dials: that is `INSTALL_MODEL_ENDPOINT`. Leave it empty on `lite`, and if you set it on `standard` or `full`, set it to the same host, or `python -m brain.knowledge.embed --check` will tell you that one address was approved and another is used. |
| `BRAIN_LANGFUSE_HOST` | every profile | you | none | Where request traces are sent. Leave it empty unless this profile runs the trace ledger. |
| `BRAIN_LANGFUSE_PUBLIC_KEY` | every profile | you | none | The trace ledger's public key. Half of a pair, and meant to be copied. |
| `BRAIN_LANGFUSE_SECRET_KEY` | every profile | you | none | The trace ledger's secret key. |
| `BRAIN_RELEASE` | every profile | you | none | The release tag you are installing. It is the installer's first argument rather than a line in the file, and it deliberately has no default anywhere: a default of `latest` is what makes an install unpinned. |
| `BRAIN_RELEASE_URL` | every profile | you | none | Where the release archive is fetched from. The installer refuses to run without it. Nothing publishes an archive for it to point at yet; see the install page. |
| `BRAIN_RELEASE_CHECK` | every profile | you | yes | Whether this install looks for a newer release. `false`, the default, asks nobody outside your network, and the Version and updates screen says the check is switched off rather than that you are up to date. `true` asks the product's published list of releases in the background when somebody opens that screen, at most every six hours, and sends nothing about this install but the request itself. |
| `BRAIN_RELEASE_FEED_URL` | every profile | you | none | The https address of a copy of the release list to ask instead of the product's own, such as one you serve inside your network, which keeps the request from leaving it. Read only while `BRAIN_RELEASE_CHECK` is `true`. Empty asks the product's published list. |
| `BRAIN_MIGRATION_DATABASE_URL` | every profile | you | none | The database owner's login, used only to apply migrations. Set it and point `DATABASE_URL` at the `brain_app` login with `APP_ROLE_PASSWORD`, and no request can ever run as the owner; `database_login` on `/health/ready` and the console's Overview say ready once that is so. Empty, migrations run through `DATABASE_URL` as before. **Not yet usable through the bundled pooler**: the compose files in this release give `pgbouncer` only the owner's login, so `brain_app` cannot connect through it until they list that login too. |
| `BRAIN_PROFILE` | every profile | you | yes | `lite`, `standard` or `full`. Which set of components this install runs. Unset means `lite`, deliberately: forgetting it should leave you under-featured rather than running a trace stack nobody sized. |
| `BRAIN_READ_REPLICA_URL` | every profile | you | none | A streaming replica of the database, for console pages that only display. Empty means every console read goes to the primary. Pages more than ten seconds behind carry a staleness banner, and past five minutes, or when the replica is unreachable, they are read from the primary instead. See `operations.md`. |
| `BRAIN_REQUEST_TIMEOUT_SECONDS` | every profile | you | yes | The ceiling on a whole request. Distinct from the model's own timeout, and larger. |
| `BRAIN_RUN_MIGRATIONS` | every profile | you | yes | Whether the application applies its own database migrations at startup, under a lock, before it reports ready. Set it false only if you apply them by hand with `alembic upgrade head`. |
| `BRAIN_SETUP_ISSUED_AT` | every profile | installer | none | When the setup code was minted. The window in which somebody may claim this system is measured from it, so an instant that arrived with the template would date that window to whenever the release was cut. |
| `BRAIN_SETUP_SECRET` | every profile | installer | none | The code the first wizard screen demands. Without it, whoever loads the console's address first becomes your administrator. The installer prints it once to whoever is standing at the terminal. |
| `BRAIN_TOOL_SOURCE` | every profile | you | yes | Which system the built-in row tools read from. It becomes the first half of every tool name, so `local` gives `local.read_price_list`, and it is part of a tool's identity rather than a label. An install that shows the seeded demonstration company sets `demo`: it is the source the seed writes records under, and the only value that registers the demo's own entities. |
| `BRAIN_VAULT_ADDRESS` | every profile | installer | none | Where this install's secrets vault answers, as an address the application and worker containers can reach. The installer runs the vault from `ops/openbao/compose.yml` and writes `http://vault:8200` here, which is the vault's service name on its own network; nothing publishes it on the host. Empty, with the token below empty too, means this install runs no vault, which only a `lite` install run with `--no-vault` is: the setup wizard and the console then keep no provider key and say so, and nothing stores one anywhere else. One without the other is treated as no vault and the startup log names the missing one. Neither reaches the application from the base compose files: `docker-compose.vault.yml` hands both over and joins the application to the vault's network, and the installer, the update and the rollback compose it in whenever this line holds a value. `ops/openbao/UNSEAL.md` says what the installer did and what you keep. |
| `BRAIN_VAULT_TOKEN` | every profile | installer | none | The token the application presents to that vault, minted by the installer on your own vault against the `application` policy, with a period of 768 hours, and never copied from another install. It lets the application put in and replace model provider keys, signing secrets and source keys, read when each was written, borrow what its policy leases, and renew itself; `ops/openbao/policies/application.hcl` is the whole of what it may do. The application renews it while it runs, long before the period ends. |
| `BRAIN_WIDGET_ORIGINS` | every profile | you | none | The websites that embed the chat widget, as a JSON list of origins (scheme, host, optional port, no path). With `BRAIN_CORS_ORIGINS`, the only origins allowed to call the API from a browser. A wildcard is refused in every environment, because here an allowed origin may start anonymous chat sessions. |
| `BRAIN_WORKER_VAULT_TOKEN` | every profile | installer | none | The general worker's own token on that vault, minted by the installer against the `worker` policy with the same period, on a profile that runs the worker; a `lite` install has no worker and none is written. `docker-compose.vault.worker.yml` hands it to the worker as `BRAIN_VAULT_TOKEN`, the name the worker reads, and it is never the application's token, which would give the process nobody watches every provider key. It lets the worker read the signing secrets it signs webhook deliveries with and renew itself; the worker's schedule renews it as `vault_token_renewal`. |
| `DATABASE_URL` | every profile | you | yes | Where the database is and which role connects to it. The template's copy carries no password on purpose: a password in a file people copy is the password the install runs with. Put yours in `PGPASSWORD`, in `~/.pgpass`, or into this line in your own `.env`. |
| `DEPLOY_HOST` | every profile | you | none | Not used by your install. It belongs to `ops/deploy.sh`, which is this repository's own deployment script. See the note under the table. |
| `DEPLOY_URL` | every profile | you | none | Not used by your install. As above. |
| `DEPLOY_UUID` | every profile | you | none | Not used by your install. As above. |
| `INFERENCE_IMAGE` | standard, full | you | none | The inference server's image. No image is published for this service yet, so `standard` and `full` refuse to start until you name one. |
| `INSTALL_ACCENT_COLOUR` | every profile | you | yes | One hex colour the console's accents are derived from. |
| `INSTALL_BROKERED_CLIENT_ID` | every profile | you | yes | The client id of the application you registered with that directory: a Google OAuth client or a Microsoft Entra app registration. `unset` means sign-in is not brokered. Its secret is never set here: it is a file in the identity provider's vault, see [Authentication](authentication.md). |
| `INSTALL_BROKERED_DIRECTORY` | every profile | you | yes | Which directory sign-in is brokered to: `google`, `microsoft`, `lark`, `ldap` or `none`. `none` means the identity provider holds the passwords itself. |
| `INSTALL_COMPANY_NAME` | every profile | wizard | yes | Your own name, as your staff should see it on every screen. |
| `INSTALL_CURRENCY` | every profile | you | yes | The ISO 4217 code money figures are rendered in. `XXX` is the code meaning no currency, so an install that has not chosen one shows something visibly unset rather than a figure that reads correctly in the wrong currency. |
| `INSTALL_EMBEDDING_DIMENSIONS` | every profile | you | yes | How many numbers your embedding model returns for each passage of text, which is the width of the column your documents are stored in. The default is what the model this system serves by default produces, so leave it alone unless you are serving a different one. Set it before you ingest your first document: the width is part of the column's type, and changing it afterwards means re-embedding everything you have ever uploaded, so the migration that sets it refuses to move a column that already holds vectors. |
| `INSTALL_EMBEDDING_REVISION` | every profile | you | yes | Which weights of the embedding model your inference server holds, exactly as the server states them. It is recorded beside every vector, and a vector the server returns under a different revision is refused rather than stored. `unset` means you have not said, and while it is unset nothing is embedded: your documents are still chunked and found by text search, and questions are answered without the nearest-neighbour leg. |
| `INSTALL_LOCALES` | every profile | you | yes | The languages this install offers, most preferred first. Only languages with a complete catalogue are accepted. |
| `INSTALL_LOGO_URL` | every profile | wizard | yes | An absolute address for your logo, served from somewhere you control. It is an address rather than an upload. |
| `INSTALL_MODEL_ENDPOINT` | every profile | you | yes | Where the inference server answers, and the one address the text of your documents is posted to. Inside your own network by default, naming the service this product ships. It has to be a bare address with no path, no query and no credentials in it: those are the shape of somebody else's API, and an address with a path would be joined to ours and sent somewhere neither of us meant. |
| `INSTALL_MODEL_PROFILE` | every profile | wizard | yes | `local` for the inference server alone, `hosted` to allow an external provider. `local` is the default because a company that has not chosen to send text off its own hardware has not chosen it. It governs the model that answers questions and never the one that indexes your documents: embedding reads every passage of everything you have ever uploaded, so it goes to the address above on both settings. |
| `INSTALL_OBJECT_STORE_BACKEND` | every profile | you | yes | Which kind of store the endpoint below is: `seaweedfs`, `cloudflare_r2` or `aws_s3`. It decides how a request is addressed and signed and which vault slot holds the key. `aws_s3` is refused at start today, because its key is a lease and nothing renews one. |
| `INSTALL_OBJECT_STORE_PREFIX` | every profile | you | yes | The bucket or path prefix under the object store endpoint. Separate from the address so two installs can share an endpoint without sharing a namespace. |
| `INSTALL_OBJECT_STORE_URL` | every profile | you | yes | The S3-compatible endpoint holding assets, recordings and exports. Your own file store, or your S3 or R2 if you would rather. |
| `INSTALL_OIDC_CLIENT_ID` | every profile | you | yes | The client id the console authenticates as, registered in the realm below. |
| `INSTALL_OIDC_ISSUER` | every profile | you | none | The issuer address of your identity realm. There is no safe default: an issuer guessed wrong is a sign-in page that redirects to somebody else's identity provider, and an empty string is a perfectly valid string. The system refuses to start without it. |
| `INSTALL_OIDC_REALM` | every profile | you | yes | The realm name inside your identity provider. Asked for separately from the issuer because the setup script needs it before the issuer exists. |
| `INSTALL_OIDC_REDIRECT_URIS` | every profile | you | none | Comma-separated addresses the realm will accept a sign-in back on. Wrong here is a sign-in that completes and then sends the person to a page you do not own. The system refuses to start without it. |
| `INSTALL_PRODUCT_NAME` | every profile | wizard | yes | What you call this system internally. It is composed with the company name, so leaving it alone reads as "Your Company Brain" and changing it reads as "Your Company Knowledge Desk". |
| `INSTALL_SENDER_ADDRESS` | every profile | you | yes | The address notifications come from. It has to be on a domain you can make this system a sender for, or every message it sends is a deliverability problem. The default delivers nothing. |
| `INSTALL_STAFF_SOURCE` | every profile | wizard | yes | Where you keep the list of who works here: `spreadsheet`, `google_sheet`, `google_workspace`, `microsoft_entra`, `lark`, `ldap`, or `none`. It is a separate question from the brokered directory above, because a staff list is read on a schedule and a sign-in provider is a live protocol, and a spreadsheet can only be the first. A name that is not one of those seven is refused with the list of the ones that are, rather than falling back to one: there is no default source, because a default would hand every later install whatever the first one happened to use. `none` means no list is read at all and you create people in the console. |
| `INSTALL_STAFF_SOURCE_LOCATION` | every profile | wizard | yes | Which sheet, which tenant or which directory the source above reads, including the base a directory search starts from. For Google Workspace it is your primary domain, for Microsoft Entra your tenant ID or its domain, and for Lark `larksuite.com` or `feishu.cn`. `unset` is the value meaning you have not said, so a source you chose and did not point anywhere refuses instead of reading a company with nobody in it. Leave it alone when the source is `none` or `spreadsheet`: a file you upload is its own answer to where the list is. |
| `INSTALL_TIME_ZONE` | every profile | you | yes | The IANA zone a timestamp is rendered in for a reader with no zone of their own. UTC by default because it is nobody's local time, so a wrong rendering is visibly wrong rather than out by an hour on some days of the year. |
| `INSTALL_VECTOR_STORE` | every profile | you | yes | Where embeddings live. `postgres` means the column in your own database, and it is the only option built today. |
| `KEYCLOAK_ADMIN` | standard, full | you | none | A username for the identity provider's temporary administrator, used once to create your real account. |
| `KEYCLOAK_ADMIN_PASSWORD` | standard, full | you | none | Its password. Change it after you have made your own account, and do not delete the variable: the stack refuses to start without it, and it is the way back in if every administrator is ever lost. |
| `KEYCLOAK_DB_PASSWORD` | standard, full | you | none | The identity provider's own database password, never typed by a person after the install. |
| `KEYCLOAK_HOSTNAME` | standard, full | you | none | The web address the identity provider answers on. It is a second address, separate from the console's, because the browser is redirected to it. |
| `LANGFUSE_CLICKHOUSE_PASSWORD` | full | you | none | The trace ledger's column store. |
| `LANGFUSE_ENCRYPTION_KEY` | full | you | none | What the trace ledger encrypts its stored keys with. |
| `LANGFUSE_NEXTAUTH_SECRET` | full | you | none | What the trace ledger signs its own sessions with. |
| `LANGFUSE_POSTGRES_PASSWORD` | full | you | none | The trace ledger's own relational database. |
| `LANGFUSE_PUBLIC_URL` | full | you | none | The address the trace ledger's own console answers on. |
| `LANGFUSE_S3_ACCESS_KEY_ID` | full | you | none | The object store credential the trace ledger writes its payloads with. |
| `LANGFUSE_S3_SECRET_ACCESS_KEY` | full | you | none | Its secret half. |
| `LANGFUSE_SALT` | full | you | none | What the trace ledger salts its stored hashes with. |
| `MATCHER_IMAGE` | full | you | none | The record matcher's image, built from `matcher/Dockerfile`. It is a job that matches an export of your records and writes suggestions for a person to confirm, and it merges nothing. No image is published for it, so `full` refuses to start until you name one. |
| `POSTGRES_PASSWORD` | every profile | installer | none | The database superuser's password. It appears in no template on purpose, because a default password in a file people copy is the password the install runs with. |
| `VALKEY_URL` | every profile | you | yes | Where the cache is. Absent means the cache is skipped, not that the application fails. |

## Two things in this table that are wrong, and are not yours to fix

**`DEPLOY_HOST`, `DEPLOY_URL` and `DEPLOY_UUID` are not yours to set.** They are read by
`ops/deploy.sh`, which is the script this repository's own maintainers use to push a build at
their own server. Nothing in your install reads them, and all three are blank in the template
with a comment above them saying what each would hold. They are listed above because the check
that keeps this table complete reads `.env.example`, and a variable that is in the register and
not in the table would be a hole in the check rather than a tidy omission. Delete the three
lines from your own `.env`; nothing will notice.

**`INSTALL_SENDER_ADDRESS` has a default that cannot deliver mail.** The default is a local
address, chosen so that an unconfigured install is visibly unconfigured rather than quietly
sending from somewhere plausible. It is in the "yes" column because something is supplied, not
because the supplied thing works.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| Every variable in `.env.example` has a row | `test_install_docs.py` |
| Every variable the installer mints has a row | the same test, reading the install plan |
| Every `${VAR}` in a profile's compose files has a row | the same test, reading the compose files |
| No row names a variable nothing reads | the same test, in the other direction |
| The profile column | the same test |
| The "comes from" column | the same test, against the install plan and the wizard's questions |
| The "default" column | the same test, against the template and the compose interpolations |
| **What each value is for** | **nobody. It is prose, and it is kept true by hand.** |
| **The advice about what to set it to** | **nobody. As above.** |

## Task ids

M42.2.5, M34.3.3.2
