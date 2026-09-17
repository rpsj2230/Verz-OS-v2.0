# Deploying with Coolify

This page is for a server that runs Coolify, a self-hosted deployment panel, instead
of the one-command installer. Coolify runs the same compose files, puts its own proxy in front of
them and issues a certificate for every address you give a service. Nothing about the product
changes. Three things about how the stack is run do, and each of them has caught a real install:

- **Coolify runs its own copy of the compose file**, which you paste into a text box and edit
  there. A new release of this product changes the release archive and not that copy. Updating
  is a job you do in the panel, and it is described below.
- **Coolify keeps a variable's value from the first time it saw it.** A `${NAME:-default}` in the
  file becomes a variable holding that default, and reloading the file later does not change it.
- **There is no installer.** Everything the installer does on a plain server, minting passwords
  and copying settings files into place, is a step you take by hand. The tables below say which.

The argument for each of those is in `brain.ops.coolify`, and the tables on this page are
computed from the compose files by that module and compared against this page on every test run.

## Before you start

- A server with Coolify installed, and ports 80 and 443 open to it. Coolify's proxy answers on
  both and issues its certificates over them.
- The console's address, with a DNS A record pointing at the server. On `standard` and `full`, a
  second address for the identity provider, and on `full` two more, as
  [network.md](network.md) explains.
- The release you are installing, unpacked on any machine with Docker. You need its compose
  files to paste and, on `standard` and `full`, its `ops/` directory.
- The image this release runs, as `APP_IMAGE`. If your registry needs a sign-in to pull it, add
  the registry in Coolify's settings for registries first.

## 1. Paste the compose file

1. In Coolify, create a project for this install. Do not add it to a project that already holds
   something else.
2. Add a resource of the Docker Compose kind with an empty compose file, so Coolify gives you a
   text box rather than asking for a repository.
3. Paste the file for your profile.
   - On `lite`, paste `docker-compose.lite.yml` from the release as it is.
   - On `standard` and `full`, the profile is several files and Coolify takes one. Merge them on
     the machine where you unpacked the release, without filling in any variable, and paste what
     it prints. The files are the ones the line beginning `standard)` or `full)` in
     `ops/update/update.sh` lists:

     ```
     docker compose -f docker-compose.yml -f docker-compose.worker.yml -f docker-compose.parse-worker.yml -f docker-compose.objectstore.yml -f docker-compose.keycloak.yml -f docker-compose.inference.yml --profile standard config --no-interpolate
     ```

4. Save. Coolify now lists every variable the file names.

The same merge is how an optional overlay reaches a Coolify install: the Cloudflare Tunnel's
two files, `docker-compose.replica.yml`, or anything else this documentation composes with a
second `-f`. Add them to the command above and paste the result. The two-host split in
[scaling.md](scaling.md) is the exception, because it starts different services on each host and
Coolify starts every service in the file.

## 2. Set the variables

Every value is described in [configuration.md](configuration.md). Coolify marks a variable the
file requires, written `${NAME:?...}`, and refuses to deploy until it has a value, so an unset
password is found here rather than by a container that cannot sign in to its own database.

**Mint these yourself.** On a plain server the installer generates them on that server; on
Coolify nobody does. Generate each one on your own machine, paste it into the variable, and never
reuse a value from another install. `openssl rand -hex 32` makes a password, and
`date -u +%Y-%m-%dT%H:%M:%SZ` gives the instant for `BRAIN_SETUP_ISSUED_AT`, which you set at the
same moment as `BRAIN_SETUP_SECRET` and never change afterwards.

<!-- checked: the values the installer mints and a Coolify install mints by hand -->

| Variable | What to put in it |
| --- | --- |
| `APP_IMAGE` | The image and release tag this install runs. Never a tag that moves. |
| `APP_ROLE_PASSWORD` | A new random password. |
| `BRAIN_SETUP_ISSUED_AT` | The current time in UTC, written when you set the setup code. |
| `BRAIN_SETUP_SECRET` | A new random value. It is the code the first wizard screen asks for. |
| `BRAIN_VAULT_ADDRESS` | `http://vault:8200`, once you run the secrets vault beside the stack by hand: `ops/openbao/UNSEAL.md`, under First install by hand. Leave it empty, with both tokens, and the wizard keeps no provider key. |
| `BRAIN_VAULT_TOKEN` | The application's token, minted on that vault as `ops/openbao/credential-slots.md` says. The vault's pieces stay with people, never in Coolify. |
| `BRAIN_WORKER_VAULT_TOKEN` | On `standard` or `full`, the worker's token, minted the same way against the worker policy. |
| `POSTGRES_PASSWORD` | A new random password. Set it once: the database volume keeps the first one. |

**These values arrive with a default, and Coolify keeps the default you first saw.** A later
release that changes one of them does not change your install. After every update, compare each
row with the release's compose file.

<!-- checked: the non-empty defaults Coolify stores on the first save -->

| Variable | Default in the files |
| --- | --- |
| `BRAIN_ENV` | `production` |

Leave `BRAIN_COMMIT_SHA` unset. The image knows which commit it was built from, and a variable
set in Coolify replaces that answer with whatever the panel knew on the day it was saved.

## 3. Put the settings files on the server

`standard` and `full` only. Some containers read a settings file from a fixed path on the server.
On a plain server the installer copies them there; on Coolify, if a file is missing, Docker
creates an empty directory at that path and starts the container anyway, and an object store
with no credentials file has no access control.

On the server, as root, copy each file from the release's `ops/` directory to the path in the
first column, keeping the part after `settings/`. For example, `ops/seaweedfs/s3.json` goes to
`/opt/brain/settings/seaweedfs/s3.json`. Do this before the first deploy.

<!-- checked: the files a Coolify install puts on the server before the first deploy -->

| Path on the server | Read by | Profiles |
| --- | --- | --- |
| `/opt/brain/settings/automation/egress.conf` | `automation-egress` | full |
| `/opt/brain/settings/langfuse/clickhouse-memory.xml` | `langfuse-clickhouse` | full |
| `/opt/brain/settings/seaweedfs/provision.sh` | `seaweedfs-init` | standard, full |
| `/opt/brain/settings/seaweedfs/s3.json` | `seaweedfs` | standard, full |

On `full`, the trace ledger also needs its own database and login, which the installer's step
"create the databases the compose files do not" makes. That step is in `ops/install/install.sh`
in the release. After the database is up, run its two statements in a terminal on the `db`
container in Coolify, with the trace ledger's password from your variables, and do not paste the
password anywhere else.

## 4. Give each service its address

Coolify routes an address to a container port and issues a certificate for it when the address
starts with `https://`. None of these services publishes a port, so the port goes in the address
itself, after the host: in the service's domain field, write `https://<address>:<port>`, with
the port from the table. Your staff still open the address without a port.

<!-- checked: the services Coolify routes, and the port each listens on -->

| Service | Port | Profiles | Which address |
| --- | --- | --- | --- |
| `activepieces` | `80` | full | The automation canvas, `AUTOMATION_PUBLIC_URL`. |
| `app` | `8000` | lite, standard, full | The console. The same address `INSTALL_OIDC_REDIRECT_URIS` names. |
| `keycloak` | `8080` | standard, full | The identity provider, `KEYCLOAK_HOSTNAME`. |
| `langfuse-web` | `3000` | full | The trace ledger's own console, `LANGFUSE_PUBLIC_URL`. |

**The identity provider joins Coolify's own network.** On `standard` and `full` the files expect
a Docker network that Coolify creates, so on a Coolify server there is nothing to do. On a server
without Coolify that network does not exist, and compose refuses to start the identity provider.

<!-- checked: the networks the files expect the server to have already -->

| Network | Profiles |
| --- | --- |
| `coolify` | standard, full |

## 5. Deploy, and check it

1. Deploy the resource in Coolify.
2. **Helpers that finish show as exited, and that is correct.** Each of these runs once and stops.
   To keep them out of the resource's health in Coolify, add `exclude_from_hc: true` under each one
   in Coolify's copy of the file. Never add that line to a file you run with `docker compose`
   yourself: compose refuses a service carrying it.

   <!-- checked: the services that finish and show as exited -->

   | Service | Profiles |
   | --- | --- |
   | `keycloak-realm` | standard, full |
   | `record-matcher` | full |
   | `seaweedfs-init` | standard, full |

3. Open `https://<console address>/health/ready`. It answers `200` when the application can
   reach everything it needs, and names what it cannot reach when it answers `503`. Coolify reads
   the same health checks from the compose file, so there is no health check to set in the panel.
4. Check the certificate. From any machine:

   ```
   curl -sv https://<console address>/health/ready -o /dev/null
   ```

   The output names the certificate's issuer and the address it was issued for. If the command
   reports a certificate problem, the address's DNS record is not pointing at this server yet, or
   port 80 is closed, and Coolify's proxy logs say which.
5. Open `https://<console address>/first-run` and finish the wizard with `BRAIN_SETUP_SECRET`.

On `standard` and `full`, install the job queue next, as [operations.md](operations.md) describes,
by opening a terminal on the `brain-worker` container in Coolify and running the command there.

## Updating

1. Unpack the new release. Compare its compose file, merged as in step 1 for your profile, with
   the copy in Coolify. Paste in whatever changed.
2. Compare the defaults table in step 2 of this page, from the new release's copy of this page,
   with your variables.
3. Set `APP_IMAGE` to the new tag, and deploy.

Going back is the same three steps with the previous release.

## If the console does not answer

- **A certificate error, or the proxy's own "no available server" page.** The domain field is
  missing the port, or names a different one from the table in step 4.
- **The console answers some requests and not others, or never, with a gateway error.** The
  application is on two networks, its own and the one the automation canvas reaches it on, and
  the proxy has to use the first. If Coolify's proxy picks the second, add the label
  `traefik.docker.network` to the `app` service in Coolify's copy, set to the name of the network
  Coolify created for this resource, which `docker network ls` on the server shows. This has not
  been seen on an install; it is what the proxy's documentation says it does when a container is
  on more than one network.
- **A container restarts because its settings file is a directory.** Step 3 was skipped for that
  file. Stop the resource, delete the empty directory, copy the file and deploy again.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The variables the installer mints, and that this page lists every one | `test_coolify.py`, against `brain.deployment.installer.PLAN` |
| Every non-empty default in any profile's files | the same test, against `brain.ops.coolify.stored_defaults` |
| The settings files and the services that read them | the same test, against the mounts in the compose files |
| Every service given an address, and that its port is the one its compose entry declares | the same test, against `brain.ops.coolify.route_gaps` |
| The networks the files expect, and the helpers that exit | the same test |
| That no product file carries a relative mount, a published port, `BRAIN_COMMIT_SHA` or a panel-only key | the same test, against `brain.ops.coolify.coolify_gaps` for every profile |
| **Where each setting is in Coolify's screens** | **nobody. Coolify renames its menus, and this page describes what to look for.** |
| **That a certificate is issued, and that the proxy picks the right network** | **nobody here. Both happen on the client's server.** |
| **That the merged file Coolify is given matches a release** | **nobody. It lives in the panel, and the update steps above are how an operator checks it.** |

## What has been done and what has not

An install of this product runs on Coolify today, with the application and the identity provider
routed by Coolify's proxy over HTTPS. The stored copy, the kept defaults, the variable that froze
the reported commit and the identity provider's missing setting were all found on that install,
and each is on this page because of it.

This page as a sequence has not been walked from a bare Coolify server, and neither has any
profile other than `lite` with the identity provider beside it. The merge command in step 1 has
not been run against a release archive.

## Task ids

M30.1.1, M30.1.2
