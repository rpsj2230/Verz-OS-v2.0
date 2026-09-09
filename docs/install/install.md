# Installing on a clean server

This is the whole install, from a server with nothing on it to a console asking you for a
setup code. It assumes you have never seen this system before and it names nobody else's
installation.

**Read the two paragraphs under "What you cannot do today" before you start.** One step of
this sequence has nothing to fetch, and knowing that first saves you the twenty minutes it
takes to find out.

## Before you start

The server needs six things, and each of them is a requirement rather than a preference. The
list lives in `brain.deployment.requirements.RUNTIME_REQUIREMENTS`, where each entry carries the
sentence saying what breaks without it, because a requirement whose reason nobody wrote down is
one that gets waived by the person under the most time pressure. The short version:

- a 64-bit Linux with cgroup v2
- Docker Engine 24 or newer
- Docker Compose v2, as the `docker compose` subcommand and not the older `docker-compose`
- `curl` and `tar`
- `openssl`
- a reverse proxy terminating TLS on port 443

The Compose version is the one that catches people out and it fails silently. Every memory
ceiling in this deployment is written under `deploy.resources.limits`, and **the old v1 tool
ignores that whole block without a warning**. An install on the old tool comes up healthy with
every container unlimited, `docker stats` shows no ceiling anywhere, and the first runaway
query takes the machine with it. Check with `docker compose version`, not with
`docker-compose --version`.

The reverse proxy is on the list because nothing in this deployment publishes a port. See
[network.md](network.md) for what to point where.

## Sizing

Three profiles, and the one to pick is the smallest that has what you need.

| Profile | What it runs | Memory | Cores | Disk | Containers |
| --- | --- | --- | --- | --- | --- |
| `lite` | the application, the connection pooler, the database, the cache | 3968 MiB | 2 | 28 GiB | 4 |
| `standard` | the above plus two workers, the file store, the identity provider and the inference server | 9920 MiB | 5 | 36 GiB | 12 |
| `full` | the above plus the trace ledger and the automation canvas | 12864 MiB | 7 | 48 GiB | 19 |

The memory figures are measured: they are the sum of every memory ceiling in the profile's
compose files, plus what the profile budgets for a component that has no service yet, plus what
the host keeps for itself. The cores and the disk are ratios rather than measurements, and they
say so in `brain.deployment.requirements.ServerSpec.notes`, because nothing here has been run
under load and a figure invented to look precise is worse than one that admits what it is.

`lite` is what a company without background automation runs, and it is not a cut-down or a
development configuration.

## The install, step by step

Each step either checks something or writes something, each one that writes something can say
when it has already been done, and **the whole sequence is safe to run twice**: a second run
skips what it already did rather than repeating it. The number of steps is deliberately not
written in this sentence: the plan's own comment said ten while it held twelve, which is what a
hand-kept count does.

The table below is checked against the plan on every test run, so a step added to the installer
and not to this table fails `tests/unit/test_install_docs.py`. What each step does and what to
do when it fails are prose.

Two variables have to be in the environment before you begin. `BRAIN_RELEASE` is the release
tag you are installing, and there is deliberately no default: a default of `latest` is what
makes an install unpinned. `BRAIN_RELEASE_URL` is where the release archive is fetched from.

<!-- checked: the steps the installer runs -->

| Step | What it does | If it fails |
| --- | --- | --- |
| `check the machine` | Confirms Docker and Compose v2 are installed, before anything is written. | Install Docker Engine 24 or newer with the compose plugin and run it again. Nothing has been written yet. |
| `check the machine is large enough` | Compares total memory against what this profile needs. | Use a larger machine, or install `lite`. An install that starts on a machine that cannot hold it fails later, one container at a time, as whichever service asks for memory last is killed. |
| `create the install directory` | Makes `/opt/brain`. Everything lives in one directory, so an uninstall is one removal. | Run it as a user that can write `/opt/brain`. |
| `download and unpack the release` | Fetches one archive of one tag and unpacks it, then records the tag in `/opt/brain/RELEASE`. Never a clone: a build that fetches a second repository is how a client ends up running a copy a fix never reached. | Check the tag exists and that the server can reach the release host. Nothing has been started, so it is safe to run again. **See "What you cannot do today": no release archive is published yet.** |
| `change into the release directory` | Changes into `/opt/brain` before running compose. | The previous step reported success and left nothing behind, so the archive unpacked somewhere else. Remove it and run again. |
| `write the environment file from the template` | Copies `.env.example` to `.env`. The template is copied, never edited in place. | Copy it yourself into `/opt/brain/.env` and run again; the step writes nothing else. |
| `mint this installation's secrets` | Generates the database password, the application role password and the setup code with `openssl rand`, under `umask 077`, and appends them with the instant the code was minted. | Install `openssl` and run again. The file is written in one go, so a failure leaves nothing half-minted. |
| `pull the images this profile runs` | Pulls before anything starts, so an unreachable registry fails while the machine is still empty rather than half up. | Check the server can reach the image registry and run again. Pulling an image that is already present does nothing. |
| `start the database and wait for it` | Starts the database alone and waits until it accepts connections, because the application runs its own migrations at startup and needs a database that is ready rather than one that is starting. | Read the database container's logs. A database that will not start is almost always a volume from a different major version. |
| `start everything else` | Brings the rest of the profile up. This is the one command the whole installer is about, over the file list for your profile. | Read `docker compose ps` for the container that is not running, then its logs. Bringing the stack up again is safe. |
| `wait for the application to report ready` | Polls `/health/ready` for five minutes. Readiness, never liveness: a container that is up but cannot reach its database still answers questions, from whatever it can still reach. | Read the application's logs. Readiness fails while the migrations are still running, which on a first install takes about a minute. |
| `present the setup code, once` | Prints the setup code to whoever is standing at the terminal. It is the only step permitted to print a value. | Read it out of `/opt/brain/.env` yourself; the install is complete either way. |

## Why the credentials are minted here and not sent to you

Nobody outside your organisation creates a password on your behalf, and nothing in this product
ships one. The three values above are generated on your server, by your server, and appended to
a file created with `umask 077`. Two consequences worth knowing.

**No two installs share a credential**, so another company's leak is not your incident.

**The mint step is guarded on the database password rather than on the file.** Running the
installer again does not mint a second set. That guard is the sharpest one in the sequence: a
second mint would write a new database password beside a volume that still holds the old one,
the stack would come up unable to authenticate to its own data, and the value that would have
fixed it would be gone.

## The setup code, and the twenty minutes it protects

The last step prints one value. **Until somebody enters it, the console has no administrator,
and whoever loads the address first becomes one.** A fresh server with an open wizard belongs
to whoever finds it, and the window is however long it takes you to walk to your laptop.

So: read the code off the terminal, open the console, and enter it on the first screen. It is
required before any of the other screens can be reached, not only before the last one. The
window it opens is measured from the instant the installer minted it, and nothing anywhere can
reopen it: if it closes, reinstall rather than editing a date into the file, because a date
typed now opens a window nobody minted.

Re-running the installer prints the same code again. That is not a leak: anybody who can run
the installer already has a shell on the server and could read the file directly.

## After the wizard

The wizard is eight screens with a back button on every one, and **nothing is written until you
approve the review screen**. A wizard that committed each screen as it went could not be
corrected, and the company name mistyped on screen two would be discovered on screen seven, by
which time it is in the branding, in the realm and in the first notification you send.

Closing the browser halfway does not start the install again. It continues where it stopped,
except that a provider key is asked for a second time: the draft it resumes from deliberately
does not keep one.

The moment the first administrator exists, the wizard becomes unreachable. Not hidden:
unreachable. Hiding it would leave an unauthenticated route to the widest role in the system
behind a value somebody printed once and probably still has.

## What you cannot do today

Three things, stated here rather than discovered at the terminal.

**No release archive is published.** The pipeline publishes a signed container image and
nothing else. The fourth step fetches `$BRAIN_RELEASE_URL`, and there is no workflow in this
repository that produces an archive for that address to point at. Until there is, the compose
files and the `ops/` directory have to reach `/opt/brain` some other way, and the sequence above
is a plan rather than something you can run start to finish.

**There is no rendered `install.sh` either.** The script is produced by a function from the
plan, and no build step writes its output anywhere a client could fetch. That is why this page
is a table a person follows rather than one command.

**After a complete install, the console is reachable from nowhere.** No service in any profile
publishes a port to the host. That is right for the database, the cache and the pooler, and it
means the reverse proxy holding your certificate is part of the install rather than an optional
extra. No compose file declares one. See [network.md](network.md).

`standard` and `full` have further blockers of their own, and they are computed rather than
listed here: `brain.deployment.installer.one_command_blockers` reports them per profile. Today
it names one component that is budgeted and has no service, one service declared twice with
bodies that disagree, and two services pointed at a database nothing creates.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The step list, and the order | `test_install_docs.py`, against the install plan |
| The sizing table | `test_deployment_requirements.py`, against the compose files |
| The requirements list | `test_deployment_requirements.py` |
| **What each step does, and what to do when it fails** | **nobody. Prose, kept true by hand.** |
| **Everything under "Why the credentials are minted here", "The setup code" and "After the wizard"** | **nobody. Prose, kept true by hand.** |

## Task ids

M42.2.3 is not claimed. See "What you cannot do today": the fourth step fetches an archive that
nothing publishes, so nobody can follow this page to a working install yet.
