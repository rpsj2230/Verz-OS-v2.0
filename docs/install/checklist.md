# Deployment checklist

One page to tick through, in the order the work happens. Every line points at the page that
explains it, and this page does not repeat those explanations: a checklist that restates a guide
is a second copy of the guide, and the two disagree the first time either is corrected.

**Nobody has walked this list on a server yet.** Read "What you cannot do today" in
[install.md](install.md) before the first line, because two of the items below cannot be done
until a release has been published.

## Pre-deployment

- [ ] Pick the smallest profile that has what you need: `lite`, `standard` or `full`. See the
  sizing table in [install.md](install.md).
- [ ] Read "What you cannot do today" in [install.md](install.md). Only `lite` starts today, and
  nothing has been published to download.
- [ ] Decide where scheduled jobs run, and which mechanism you switch on first. See "What to do
  about it" in [operations.md](operations.md).
- [ ] Keep this install's variables file in a private repository that holds install files and no
  product code, one file per install. A repository holding product code is a fork, and
  `brain.deployment.variables.variables_repository_gaps` reports it as one.
- [ ] If this server, its disk, a home directory or a deployment project was copied from another
  install, cut the four links below before anything starts.

### Four links a copied install carries

A copy carries more than its credentials, and three of these four are invisible from the
directory you are looking at. Each one acts on the install it was copied from the moment the copy
starts.

<!-- checked: the four links a copied install carries -->

| Link | Where it hides | What to do |
| --- | --- | --- |
| `platform project files` | A deployment tool's own stored copy of the project: its compose file and its environment, saved when somebody set it up and resolved there rather than read from the release. See "`/health/ready` reports `commit: unknown`" in [troubleshooting.md](troubleshooting.md). | Create a new project for this install. Never duplicate the project of another one. |
| `temporary CLI state` | Tool state outside the release directory: a registry login in `~/.docker/config.json`, an ssh destination in `~/.ssh/config`, any `.env.*` file somebody left beside the real one. None of it is in the release archive and all of it survives a copied disk. | Sign out of each tool and sign in again as this install's own account. Delete what you did not create. |
| `git remotes` | A checkout's remote still names the repository it was cloned from, so a pull, a push or a script reading the remote acts on somebody else's system. | Install from the release archive, which carries no `.git`. A directory with `.git` in it is not an install. |
| `scheduled jobs` | Timers survive a copied disk and keep running against whatever they were pointed at: a copy written into another install's bucket, a deploy pulling another install's image. | Run `systemctl list-timers` and account for every line. The ones this repository installs are in the table below. |

### Scheduled jobs this repository installs

<!-- checked: every scheduled job this repository installs -->

| Timer | Installed by | What it does |
| --- | --- | --- |
| `brain-backup.timer` | `ops/backup/brain-install-backup` | Copies the database every night at 02:00 into the bucket it discovers from the running system. On a copied disk, check what it discovered. |
| `brain-autodeploy.timer` | `ops/deploy/brain-install-autodeploy` | Pulls `:latest` every two minutes and redeploys when it moved. An install that pins a release has no use for it, and an install running it is not pinned. |

## Server

- [ ] The seven requirements in "Before you start" in [install.md](install.md), including Docker
  Compose v2 as `docker compose`. Check with `docker compose version`, not with
  `docker-compose --version`. Swap for the secrets vault: `cat /proc/swaps` lists nothing, or
  only dm-crypt or zram devices, or you have decided to accept plain swap (the installer asks,
  or takes `--accept-unencrypted-swap`).
- [ ] Memory, cores and disk for the profile you picked, from the sizing table in
  [install.md](install.md).
- [ ] Firewall: 80 and 443 to the proxy, your own administrative access, and nothing else. See
  [network.md](network.md).
- [ ] Any rule for a port Docker publishes goes in the `DOCKER-USER` chain and is persisted by a
  unit ordered after Docker starts. See [network.md](network.md).

## Application

- [ ] `BRAIN_RELEASE` set to the release tag and `BRAIN_RELEASE_URL` to its archive, then the
  installer run. See [install.md](install.md).
- [ ] Every step of the install reported done or already done. The table in
  [install.md](install.md) says what to do when one fails.
- [ ] A reverse proxy in front of the application, because nothing publishes a port. See
  [network.md](network.md).
- [ ] The setup code entered on the first wizard screen straight away, and the wizard finished.
  See "The setup code" in [install.md](install.md).

## Database

- [ ] Readiness passed after the first start. It fails for about a minute while the migrations
  run; see [troubleshooting.md](troubleshooting.md).
- [ ] The job queue installed, which `alembic upgrade` does not do. See "Installing the job
  queue" in [operations.md](operations.md).
- [ ] On `full`, the trace ledger's own database exists. See "A service starts and reports a
  missing database" in [troubleshooting.md](troubleshooting.md).
- [ ] You know that nothing restores a copy yet. See "Backups, and the honest position" in
  [operations.md](operations.md).

## Environment

- [ ] Every value in the table in [configuration.md](configuration.md) set, reading "default:
  none" as a value that fails when blank.
- [ ] The credentials the installer minted stay on this server and were not copied from another
  install. See "Why the credentials are minted here" in [install.md](install.md).
- [ ] `DEPLOY_HOST`, `DEPLOY_URL` and `DEPLOY_UUID` deleted from your `.env`, and
  `INSTALL_SENDER_ADDRESS` set to an address that can deliver. See
  [configuration.md](configuration.md).
- [ ] `BRAIN_COMMIT_SHA` not set in your deployment tool's environment. See
  [troubleshooting.md](troubleshooting.md).

## Integrations

- [ ] The staff source chosen. See [authentication.md](authentication.md).
- [ ] Each connector's credential created at the source first, with the least it can work with,
  from `ops/openbao/credential-slots.md`. See [integrations.md](integrations.md).
- [ ] Every credential in the vault and none in the environment file.
- [ ] A visibility rule supplied for every source that cannot say who may see a row.

## Security

- [ ] A second Super Admin appointed on the first day. See
  [authentication.md](authentication.md).
- [ ] On `standard` and `full`, the identity provider's temporary administrator deleted and
  `KEYCLOAK_ADMIN_PASSWORD` changed, with the variable kept. See
  [authentication.md](authentication.md).
- [ ] No administrative panel answering plain HTTP on a public address. See
  [network.md](network.md).
- [ ] Every administrative console that answers from the internet has a second factor switched
  on and an IP allowlist in front of it, and the identity provider's allowlist covers only its
  admin paths. See "Administrative consoles" in [network.md](network.md).
- [ ] The four links a copied install carries, above, all cut.

## Testing

- [ ] Your deployment tool and your uptime monitor point at `/health/ready`, not at
  `/health/live`. See [operations.md](operations.md).
- [ ] `/health/ready` reports the commit you meant to deploy.
- [ ] `docker stats` shows a memory limit on every container. See
  [troubleshooting.md](troubleshooting.md).
- [ ] A question about a record that does not exist and a question the system cannot match get
  the same answer. An answer that tells them apart has told its reader which records exist.

## Go-live

- [ ] No service level statement signed that the system refuses to render. See "What the
  recovery figures mean" in [operations.md](operations.md).
- [ ] The backup switched on first, then the drill that proves it. See
  [operations.md](operations.md).
- [ ] The release tag you are on written down. See [update-and-rollback.md](update-and-rollback.md).

## Post-deployment

- [ ] The recovery panel read as it is: "never verified" is the alarm it was built to raise
  while nothing restores a copy.
- [ ] Every update and every rollback run from [update-and-rollback.md](update-and-rollback.md).
- [ ] When something is wrong, [troubleshooting.md](troubleshooting.md) looked up by what you
  are seeing.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The ten sections, in this order, each with something to tick | `test_install_docs.py` |
| The four links a copied install carries, by name, in both directions | the same test |
| Every timer this repository installs has a row, and no row names a timer it does not | the same test, against the timer units under `ops/` |
| That the release archive carries no `.git`, no install's `.env`, and this page | the same test, against `brain.deployment.release` |
| **What each line tells you to do** | **nobody. Each line points at the page that explains it, and that page says what of it is checked.** |

## Task ids

M42.3.7, M34.3.3.1, M30.2.8
