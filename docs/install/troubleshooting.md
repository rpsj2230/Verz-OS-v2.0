# Troubleshooting

Every entry below is a failure that actually happened while this system was being built, on a
real server or in a real pipeline. Nothing here is a plausible failure somebody imagined; a
guide padded with those teaches you to distrust the ones that are real.

Each entry starts with what you see, because when you are troubleshooting you know the symptom
and not the name.

---

## A container restarts every minute or two, and its log has one line in it about build-time options

The identity provider was started with `--optimized`. That flag tells it to skip its own build
step and use a configuration baked into the image, and the stock image has no such build in it.
It says so on every boot: a warning that the build-time options differ from what is persisted
and will not be used, naming the database and the health endpoint as the two.

Those two are exactly the wrong two to lose. The container comes up against a development file
store with nothing answering on its health port, the health check never passes, and it
restart-loops for ever.

**What to do.** Remove `--optimized`. Without it the provider runs its own build at startup,
which is why the health check's start period is ninety seconds rather than thirty. A slow start
beats a container that never becomes ready.

**How this was found.** On the server, in the log, not in a review. Three containers, database
healthy, the realm job exited 0, and the provider cycling with that warning as the only line.

---

## A container is killed and `docker inspect` says exit 137

The process wanted more memory than its cgroup limit allowed and the kernel killed it. Exit 137
is that, every time.

**What to do.** Raise the limit for that service, and check the total still fits the machine.
Do not remove the limit: an unlimited container on a machine with anything else on it is
somebody else's outage as well as yours, and it is invisible until the night it happens.

**How this was found.** The identity provider was killed at a 512 MiB limit. Run at 768 it
settled at 477 MiB steady, about 62 per cent, which is where its declared figure comes from.
That is a measurement rather than a guess, and it is the reason the number is what it is.

---

## Everything comes up healthy and `docker stats` shows no memory limit on anything

You are running the old `docker-compose` tool rather than `docker compose`. Every memory
ceiling in this deployment is written under `deploy.resources.limits`, and **the v1 tool ignores
that whole block without a warning**.

This is the one requirement in the whole install whose absence produces no error message at any
point. The install works, the containers run, and the first runaway query takes the machine.

**What to do.** `docker compose version` should print 2.10 or newer. If `docker-compose
--version` is what works on your server, install the compose plugin.

---

## A database container restart-loops with a message about an unused mount, and it reads like corruption

The volume is mounted at the old data path. PostgreSQL 18 keeps its data in a major-version
subdirectory, so that `pg_upgrade --link` never crosses a mount boundary, and mounting the old
path makes it refuse to start with a message that sounds much worse than it is.

**What to do.** Mount the volume at the parent, not at the data directory itself.

**And note the version.** On PostgreSQL 16 the old path is correct, so a compose file running
16 is right exactly as it is. The rule belongs to 18 and later.

**How this was found.** By deploying the identity stack for the first time. One compose file
carried the explanation in a comment; the file written afterwards did not, and a comment in one
file is not a check on another.

---

## Sign-in fails for everybody and there is nothing near the login page saying why

The realm was never imported, and there are two ways that happens.

**The realm file was rejected outright.** It carries explanatory comments, which is why it is
readable, and the identity provider refuses any field it does not recognise: it fails with a
message about an unrecognised field rather than about a comment. A helper container now
generates a stripped copy for the import so that both the explanation and the import survive.

**The realm was not in the image at all.** The build excluded the directory it lives in, so the
copy step failed with a plain not-found on that path. Both ends of the arrangement were correct
and the middle was missing: one file said to copy it in, another said to read it back out, and
nothing between them could reach the file.

**What to do.** Check the helper container ran and exited 0 before the provider started. It has
to: a provider that starts with no realm answers on its port and fails every sign-in.

**The general shape, which is worth more than either fix.** Two checks either side of a value
are not two checks. Asserting that one thing copies a file and another reads it back proves the
two ends agree and says nothing about whether anything can reach the file.

---

## A direct database connection fails with `missing "=" after ...`, and the message seems to be about the password

The connection string is in the ORM's form, `postgresql+psycopg://`, and the low-level driver
cannot read it. It falls back to parsing the string as keyword and value pairs, and the syntax
error it reports lands near the password, which sends you to look at credentials rather than at
a scheme.

**What to do.** Strip the `+driver` part for anything that connects without the ORM.

**How this was found.** It blocked every deploy for a stretch. Nothing could have caught it
earlier: the checks that open those connections skip when no database is configured, which is
every run on a laptop, so the only thing that could see it was the job that starts the whole
stack, and it did.

---

## A service starts and reports a missing database

Something is pointed at a database that nothing creates. The database server in this deployment
creates one database, and two of the trace ledger's services connect to a different one by
name. On a fresh install they fail to start, and the message is about a missing database rather
than about the real problem, which is that nothing was ever told to make it.

**What to do.** Create it during the install. Do not repoint those services at the main
database: that puts a second system's tables beside your business records with one login
covering both.

---

## A container reads a settings file, finds nothing, and starts anyway

A relative bind mount in a compose file is resolved against the directory the compose file was
read from. If your deployment tool stores its own copy of the compose file and writes it out
somewhere with no repository beside it, Docker creates an **empty directory** where the file
should be and starts the container with no error at all.

Four services in this deployment take something they need at startup from a path like that: a
memory limit, an egress allowlist, and a set of object-store credentials. Three of them then run
with no settings and say nothing about it. The egress allowlist is the one that matters most,
because it is what stops the automation sandbox reaching anything it was not allowed to.

**What to do.** Run compose from the directory the release was unpacked into, and name the
compose files by absolute path under that directory. The installer does both, and that single
change of directory is what makes these mounts a non-issue on that path.

---

## Production is recreated every few minutes and in-flight requests are dropped

Two deploy timers on the server, and the older one redeploys unconditionally whether or not
anything changed.

**What to do.** Find every timer and every script that deploys, not the first one. Disable the
old one and delete its script, so that the next person reading that directory does not find two
that look interchangeable and re-enable the wrong one.

**How this was found, and the part worth keeping.** The first diagnosis was wrong, and it was
wrong because only one of two possible causes was checked. The evidence that settled it was the
process's own log: in the ninety minutes before the fix, the old timer had run twenty-one times
and deployed on all twenty-one, with no new image published in that window.

---

## Every check is green and production is running an old commit

Deployment is gated on the test pipeline. A red pipeline does not fail the deploy: it means the
deploy never runs at all, so the server stays on the last good image and nothing anywhere is
red about it.

**What to do.** Compare what `/health/ready` reports against the commit you expect. It carries
the commit the running image was built from, which is why it is there.

---

## `/health/ready` reports `commit: unknown`

Something is overriding the value the image baked in at build time. A deployment tool that
stores its own copy of the environment resolves a default once, at save time, and never updates
it, so the container is told the commit is the literal string it was given.

**What to do.** Do not set `BRAIN_COMMIT_SHA` in the deployment's own environment. The image
knows its own commit and anything you set replaces a true answer with a stale one.

---

## Two servers installed on two different days are running different code, and both report the same image name

An image reference with no tag resolves to `latest`, and `latest` moves.

**What to do.** Pin the tag. That is what release pinning is for, and it is how one install
holds a version back while others move on. Note that today several services default to a
`:latest` reference, so **an install that pins nothing is not pinned at all**.

Note also that one image in this deployment is selected by two different variables. Setting one
of them pins some containers and leaves the rest on the other one's default, so an install can
be running two builds of one product at once while every version figure it reports is true of
only part of it.

---

## A firewall rule on a published port never seems to do anything

Docker publishes a port to all interfaces and inserts its own rules **ahead of** the host
firewall's chain, so the packet is accepted before your rule is ever consulted. A `ufw deny` on
that port does nothing at all, and there is no error to tell you.

**What to do.** Put the rule in the `DOCKER-USER` chain, which Docker leaves alone for exactly
this purpose. And persist it with a unit ordered after Docker starts, because Docker flushes and
rebuilds its chains on start and will wipe anything you inserted by hand.

**How this was found.** An administrative panel answering plain HTTP on a public address, with a
deny rule in place that had never once seen a packet.

---

## The install completed and the console is not reachable from anywhere

Nothing in this deployment publishes a port. Every service uses `expose`, which opens a port on
the compose network only.

**What to do.** Put a reverse proxy in front of it. See [network.md](network.md). This is a
requirement of the install rather than an optional extra, and no compose file in this product
declares one.

---

## Readiness fails for the first minute of a fresh install

The application applies its own database migrations at startup, under a lock, before readiness
passes. On a first install that takes about a minute.

**What to do.** Wait. The installer polls for five minutes for this reason. If it is still
failing after that, read the application's logs rather than restarting: a restart puts you back
at the beginning of the same migration.

---

## A helper container shows as a red "Exited" beside three healthy services

A one-shot that succeeded. Some deployment tools have no way to be told that a container is
meant to stop, so a migration or a file-preparation step that did its job correctly displays as
a failure.

**What to do.** Check its exit code rather than its colour. In this deployment the application
runs its own migrations, so there is no migrate container at all in the current compose file;
the file-preparation helper for the identity provider is genuinely a one-shot and is meant to
exit.

---

## A prepared statement fails, and only in production

The connection pooler runs in transaction mode, so it hands a different backend to every
transaction. A statement prepared on one and executed on another fails, and development has no
pooler, so this is invisible until it is live.

The same shape has cost twice more. A session-level advisory lock taken through a transaction
pooler is released by whichever transaction happens to end first, which is why the migration
lock is transaction-scoped. And the quietest version has no error at all: a `LISTEN` behind a
transaction pooler simply stops receiving notifications, so a queue that never wakes up looks
exactly like a queue with nothing in it. That is why the workers connect straight to the
database rather than through the pooler.

**What to do.** Anything that needs session state does not go behind the transaction pooler.
Every component in this system declares which of the two it needs, and the combination is
refused rather than trusted to whoever writes the compose entry.

---

## The setup wizard refuses a code you are sure is right

Check that both halves are present in the environment file. The setup code and the instant it
was minted are one value written in two lines, and one of the two blank is refused rather than
guessed.

**What to do.** Reinstall rather than typing a date. A date typed now opens a window nobody
minted. If both lines are blank, this install never had a code, which is what a development
machine should look like.

---

## A search comes back with a suspiciously round number of results and reads as complete

Your helpdesk's search returns at most three hundred records, ever. Not per page: a hard ceiling
on the result set, and the three-hundredth record and the last record are reported identically
by the source.

**What to do.** Nothing, and this is here so you recognise it rather than so you fix it. This
system stops at the ceiling deliberately and marks the result truncated, so an answer built from
a search that hit it says so. What you should not do is read a count of three hundred as a
complete answer.

---

## Failures from this build that you will not meet

Three more things went wrong here and none of them can happen on your server. They are listed so
that this page is honest about where it came from rather than looking exhaustive.

**A repository rename broke the deploy.** The pipeline derived the image name from the
repository's name and the server did not, so the two stopped agreeing. It was caught only
because the new name happened to contain capital letters, which the registry refuses. A rename
to a lowercase name would have published to a package nobody pulls, gone green, and left the
server on the old image with every check passing.

**A suite was green on a laptop and red in the pipeline on a constraint no local run can
enforce.** Some duplicate rows were harmless in memory and violated a unique constraint the
moment they reached a real database, and there is no PostgreSQL on the development machine.

**A tool spawned from a temporary directory was intermittently refused by the operating
system.** It presented as a build step failing with no step having an opinion, which is worse
than a consistent failure.

## Task ids

M42.2.9
