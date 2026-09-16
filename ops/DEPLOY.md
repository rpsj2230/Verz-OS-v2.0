# Deploying to the VPS

Laptop → GitHub → GHCR, and the VPS pulls from GHCR.

**The server deploys itself, and that is the only automatic deploy there is.** A systemd timer on
the server checks the registry every two minutes and installs a new image when `:latest` moves.
Nothing outside the server tells it to deploy.

## Why the server pulls

Two reasons, and either would be enough.

- **No inbound access to the server.** A deploy is a connection the server opens to the registry,
  never one something else opens to the server. The deployment panel's port stays firewalled, and
  nothing about deploying asks for an address range to be let in. The ports that are open, 80 and
  443 for the people using the system and 22 for its administrators, are open for those reasons and
  would be open without deploys.
- **No deployment secrets in GitHub.** A token that can redeploy every container on the host is not
  stored in a repository's settings, where every workflow and every administrator of the repository
  can reach it.

**And the CI gate is kept.** `:latest` is moved only by the `Deploy` workflow's build job, which
runs only when CI succeeded, so the tag moving is the statement that the tests passed.

Until 2026-09-15 the workflow also had a step calling the panel's deploy API with three repository
secrets, `COOLIFY_URL`, `COOLIFY_SERVICE_UUID` and `COOLIFY_TOKEN`. They were empty on every run,
the panel is not reachable from GitHub, and every deploy that ever happened came through the timer,
so the step was removed. The three secrets are read by nothing now and can be deleted from the
repository's settings.

## What already works

Every push to `main` runs CI. If CI passes, `Deploy` builds the image and pushes it to
`ghcr.io/rpsj2230/verz-brain-v2.0`, tagged with the short commit SHA and `latest`, and signs
it. Its second job then waits up to eight minutes for the live site's `/api/status.json` to
report that commit, and **fails if it does not**, because a published image nobody pulled is
not a deploy.

Verified 2026-09-04: `ghcr.io/rpsj2230/verz-brain-v2.0:6593cf3`,
digest `sha256:131e228179c16705a9cb6c31fc15ef05a18bed91f892d0d3048e5e3d278d5f53`.

## The target box

**Every value in this runbook that names a machine is a placeholder**, written as
`<deploy-host>`, `<deploy-uuid>` and `<deploy-url>`. They are the three variables in
`.env.example`, and `ops/deploy.sh` refuses to run until they are set rather than falling
back to any of them. This file named one deployment's server until 2026-09-09, which is a
runbook telling the next administrator to open somebody else's panel and paste their token
into it.

- `<deploy-host>` the ssh destination, as spelled in `~/.ssh/config`
- `<deploy-uuid>` the Coolify service identifier, the last path segment of that resource's URL
- `<deploy-url>` the address this deployment answers on, with its scheme

The box this was measured on at the time: Docker 29.7.2, 11.7 GiB RAM, 86 GiB free disk.

**It may be shared, and this one was.** At last check it ran 29 containers using about
4.5 GiB, including Coolify itself, a Dify stack, Langfuse, Activepieces, and an unrelated
Coolify project. Anything already on the box is live and must not be touched.

Two consequences, already handled in `docker-compose.yml`:

- Every service declares an explicit memory limit. Without one, a runaway query here
  could take down someone else's production on the same host.
- Postgres is on `expose`, not `ports`. Nothing outside this compose project reaches the
  database, which matters more than usual on a box with no firewall.

Budget for this stack: about **3.8 GiB** (app 1 GiB, Postgres 2 GiB, cache 0.5 GiB,
migrate 0.25 GiB one-shot). That leaves roughly 3 GiB headroom. Adding OpenBao, a worker
and the browser sandbox later will need a hard look at what else the box is running -
Langfuse alone documents a 25.5 GiB minimum, so it does not belong on this host.

## Steps

### 1. Give Coolify a GHCR credential

The package is private because the repo is private, so Coolify cannot pull it anonymously.

Create a classic PAT on the `rpsj2230` account with **`read:packages`** only, then in
Coolify: **Keys & Tokens → Docker Registries → Add**, registry `ghcr.io`, username
`rpsj2230`, password the PAT.

### 2. Create the project

In Coolify: **Projects → + New**, and give it a name of its own. Do not add resources to a
project that is already there; those belong to something else that is live.

Inside the new project add a **Docker Compose** resource, source this repository, compose
file `docker-compose.yml`.

### 3. Set the environment

On the resource, set:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | generate one; Coolify can do this |
| `APP_IMAGE` | `ghcr.io/rpsj2230/verz-brain-v2.0:latest` (required: the compose file has no default and refuses to deploy without it) |
| `BRAIN_ENV` | `production` |
| `BRAIN_COMMIT_SHA` | leave to the pipeline |

Set the health check path to `/health/ready`. **Not `/health/live`** - liveness only says
the process is running. A container that is up but cannot reach the database still answers
questions, from whatever it can still reach, which is how this system would start
returning wrong answers while appearing healthy.

### 4. Install the pull timer

On the server, as root, once:

1. Copy `ops/deploy/brain-autodeploy` and `ops/deploy/brain-deploy` to `/usr/local/bin/` and
   make both executable.
2. Write `<deploy-uuid>` into `/root/.coolify-service-uuid`. Both scripts refuse without it
   rather than guessing which containers are this deployment's.
3. Run `/usr/local/bin/brain-install-autodeploy`, copied from `ops/deploy/` the same way. It
   writes `brain-autodeploy.service` and `brain-autodeploy.timer` and switches the timer on.

After that, every merge to `main` that passes CI is live within a few minutes, and the
`Deploy` workflow goes red if it is not. `journalctl -u brain-autodeploy.service -n 50` is
the history, and `/var/lib/brain-deploy/heartbeat.json` says what the last check decided.

`brain-deploy` prefers to ask Coolify to deploy, on `127.0.0.1` with a token in
`/root/.coolify-deploy-token`, so the panel's own record stays true; with no token it
recreates the app with compose from Coolify's own directory. Either way the call is made on
the server, to the server.

**By hand, when you need one now.** `make deploy` runs `ops/deploy.sh` from a machine with
ssh access to the server. It uses the administrative SSH access that is already open, and
nothing automatic depends on it.

## This is not how a client is given the system

Everything above is one deployment of this product, deployed from `main` on every push. A
client is given a tag: an archive they fetch and an image their compose file pins, both
published by the `Release` workflow and neither produced by anything on this page. See
[RELEASE.md](RELEASE.md) for how a tag is cut, what it produces, how both artefacts are proved
to exist from a machine that has never seen this repository, and the two publication settings
that still stop a client install from working.

## Rollback

Images are tagged by commit SHA, so rolling back is redeploying an older tag - set
`APP_IMAGE` to `ghcr.io/rpsj2230/verz-brain-v2.0:<sha>` and redeploy. Nothing needs
rebuilding, and the SHA in `/health/ready` says exactly what is running.

## What is deliberately not automated

Creating the Coolify project and its tokens is a manual step on purpose. Both require
credentials on the account holder's own infrastructure, and a pipeline that could mint
them would be a pipeline that could also point production somewhere else.
