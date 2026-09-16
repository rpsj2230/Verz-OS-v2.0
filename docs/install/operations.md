# Backup, monitoring, logging and health checks

**Read this section first, before the rest of the page.** Fourteen mechanisms in this system
are meant to run on a schedule. Ten of them have no caller of any kind: the code is written,
it is tested, and nothing anywhere invokes it. That includes the one that takes a backup and the
one that measures how long you have gone without a copy. Three more have a caller and no
schedule, which is one link of a chain rather than the chain, and one of the three is the one
that proves a copy can be restored: the recovery screen asks whether a drill is due, and nothing
performs one. The table below says so per mechanism rather than in a count.

So this page is in two halves. What answers today, which is the health checks and the audit
ledger. And what is written down and switched off, which is nearly everything else.

You are not being handed a monitored system. You are being handed a system with the monitoring
built and not wired, and told which pieces those are, by name, in a table the code checks.

## Health checks, which do work

Two endpoints, and the difference between them is the whole of what a health check is for.

`/health/live` says the process is running. It says nothing about whether the system can answer
anything.

`/health/ready` says every dependency is reachable. It returns 503 when one is not, and it
carries a per-dependency breakdown so a failure names what is unreachable rather than reporting
a colour. Both endpoints report the commit the running image was built from, so "what is
actually live" is answerable without guessing.

**Point your deployment tool and your uptime monitor at `/health/ready`, not at
`/health/live`.** A container that is up but cannot reach its database still answers questions,
from whatever it can still reach, which is how a system starts giving wrong answers while
appearing healthy. Liveness is the check that lets that happen.

Every container in this deployment declares its own health check, and one-shot helpers declare
none because a one-shot is ready when it has exited. `brain.deployment.installer.health_report`
prints, per profile, which services have one and what "ready" means for each component that
does not.

## What "ready" means, per component

Every component in this system is required to carry a sentence saying what ready means for it,
in words, before it can be declared at all. That is not decoration: a component whose readiness
nobody wrote down gets whatever check the person wiring it up invents, which is almost always a
TCP connect, and a TCP connect proves a socket is listening. That is liveness wearing
readiness' clothes.

Some of them are worth knowing before you build a dashboard:

- The inference server is ready when **every** model it serves answers a probe of its own. One
  loaded out of three refuses two thirds of what it is asked while presenting a listening
  socket.
- The identity provider is ready when its own health endpoint answers, which is true only once
  the realm has been imported.
- The object store is ready when its gateway lists a known bucket, not when its port opens.
- A worker is ready when its queue driver has fetched at least once and the database is
  reachable.

## Installing the job queue, which is not part of `alembic upgrade`

The queue's tables are the driver's own, versioned by the driver and created by the DDL it
ships. Transcribing that into a migration would fork it at the driver's next release, with no
error until a query names a column that is not there, so these four steps are applied by an
operator rather than by the migration history. That argument is
`brain.ops.queue.THE_QUEUE_SCHEMA_IS_NOT_ALEMBICS` and it is why this section exists at all.

Until step four has run, `python -m brain.ops.sweeps rls` is red, because the driver's tables
arrive with row-level security off in a schema that sweep enumerates. A red sweep with no
remedy written down is a sweep somebody switches off, so the remedy is here.

`python -m brain.ops.worker --deploy-plan` prints this same plan with the full reasoning for
each step, and `--install-queue` runs steps two to four. Run them on the connection `QUEUE_URL`
names, which is the workers' session-mode pooler, and never through the application's pooler:
the driver needs `LISTEN`, which that pooler does not carry in transaction mode.

<!-- checked: the steps that install the job queue -->

| Step | What it does | Skippable |
| --- | --- | --- |
| `dependency` | The driver is in the project's dependencies and the lock file. Without it nothing can be enqueued or fetched, and every step below is a command that cannot be run. | required |
| `schema` | `CREATE SCHEMA IF NOT EXISTS ops`, because the driver's DDL is unqualified and lands wherever `search_path` points, which on a fresh connection is `public`. | optional |
| `tables` | `python -m brain.ops.worker --install-queue`, which applies the driver's own schema manager. It is not idempotent: run against a database that already has the tables it raises `DuplicateObject`, so this is applied once and reported as present afterwards. | required |
| `row_level_security` | `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` for every table the step above created, derived from the catalogue rather than from a transcribed list, so a table a future driver release adds is secured by the run that creates it. | required |

The skippable column is the one to read carefully rather than the one to skim. `schema` is
optional only because the migration history already creates `ops` on any database the
application has started against; on a database that has never run a migration it is not
optional at all. Every other row is required, and `tables` is the row where getting this wrong
costs the most in both directions: skipping it leaves a worker that starts and drains nothing,
and repeating it raises on a database that was already correct.

The checkpointer's tables are installed the same way and for the same reason, by
`python -m brain.ops.worker --install-checkpointer` on the connection `BRAIN_CHECKPOINTER_URL`
names. It runs the graph library's own setup into the `agent` schema and then enables row-level
security on every `checkpoint*` table it finds there. Unlike the queue's step it is safe to run on
every deploy: the library records which of its migrations it has applied and applies only the
rest.

A control can be run once, on demand, through the queue rather than waiting for the schedule:
`python -m brain.ops.worker --run-control <name>` enqueues it, and the general worker runs it
under the same lock and records it in the same table as a scheduled run.


## Starting the workers for the first time

The workers have never been started on a server, and neither has the pooler they reach the
database through. These steps start them on their own, beside a running stack, and each check
says what it proves. Run them on a server running `docker-compose.yml`, from `/opt/brain`.

Set this once in the shell you run them from. It names the three files, and `--profile standard`
is what switches the workers on:

```
F="-f docker-compose.yml -f docker-compose.worker.yml -f docker-compose.parse-worker.yml --profile standard"
```

1. **Start the workers' pooler.** `docker compose $F up -d pgbouncer-session`, then
   `docker compose $F ps pgbouncer-session` shows `healthy`. It is in session mode, so a worker's
   `LISTEN` keeps its connection, and it admits at most twenty connections to the database for
   both workers together.
2. **Install the queue and the checkpointer through it.**
   `docker compose $F run --rm brain-worker python -m brain.ops.worker --install-queue`, then the
   same with `--install-checkpointer`. Both connect through the pooler, so this is the first proof
   that the pooler passes the driver's own statements.
3. **Start both workers.** `docker compose $F up -d brain-worker brain-parse-worker`. Within a
   minute `docker compose $F ps` shows both `healthy`, which means each has fetched from the queue
   and written its heartbeat.
4. **Check the listeners are on the pooler.** This lists the connections waiting for
   notifications, and the address each came from, which is the pooler's:

   ```
   docker compose $F exec db psql -U brain -d brain -c "SELECT client_addr, state, left(query, 40) FROM pg_stat_activity WHERE query ILIKE 'LISTEN%'"
   ```

5. **Check a job is woken rather than polled.** Enqueue a control, and read when it started:

   ```
   docker compose $F exec brain-worker python -m brain.ops.worker --run-control retention_sweep
   docker compose $F exec db psql -U brain -d brain -c "SELECT name, started_at, outcome FROM ops.control_run ORDER BY started_at DESC LIMIT 1"
   ```

   Note the time you enqueued it and the `started_at`. Repeat five times. If every start follows
   its enqueue by well under five seconds, notifications are arriving; a start that lands on a
   five-second boundary each time means the workers are polling, and the pooler is not carrying
   `LISTEN`.
6. **Check the ceiling.** Count the database connections by where they come from. The row for the
   workers' pooler never exceeds twenty:

   ```
   docker compose $F exec db psql -U brain -d brain -c "SELECT client_addr, count(*) FROM pg_stat_activity WHERE datname = 'brain' GROUP BY 1"
   ```

Write down what each step showed, with the date and `docker compose version`. That record is what
lets the task for the workers' deployment and the task for their pooler be closed.

## Starting the trace ledger on its own

The trace ledger's five services, its interface, worker, column store, cache and the file store,
have never been started together. These steps start them beside `docker-compose.yml` without the
rest of `full`, so they can be tried on a server with enough memory for their limits. Set this
once in the shell you run them from:

```
T="-f docker-compose.yml -f docker-compose.objectstore.yml -f docker-compose.langfuse.yml"
```

1. Put `ops/seaweedfs/s3.json`, `ops/seaweedfs/provision.sh` and `ops/langfuse/clickhouse-memory.xml`
   from the release under `/opt/brain/settings/`, keeping the path after `ops/`.
2. Set every `LANGFUSE_` value [configuration.md](configuration.md) lists for `full`, and point
   `LANGFUSE_PUBLIC_URL`'s address at the server through your proxy on port 3000.
3. `docker compose $T up -d db`, then run the statements of the installer step "create the databases
   the compose files do not", from `ops/install/install.sh`, so the trace ledger has its database.
4. `docker compose $T up -d`. Within a few minutes `docker compose $T ps` shows `langfuse-web`,
   `langfuse-worker`, `langfuse-clickhouse`, `langfuse-cache` and `seaweedfs` running and healthy,
   and `seaweedfs-init` exited with `0`.
5. Sign in to the trace ledger's console, create a project and its keys, and send one trace:

   ```
   curl -s -u <public key>:<secret key> -H 'Content-Type: application/json' -X POST https://<trace ledger address>/api/public/ingestion -d '{"batch":[{"id":"rehearsal-event-1","timestamp":"2026-01-01T00:00:00Z","type":"trace-create","body":{"id":"rehearsal-trace-1","name":"rehearsal"}}]}'
   ```

6. Read it back with `curl -s -u <public key>:<secret key> https://<trace ledger address>/api/public/traces/rehearsal-trace-1`.
   An answer naming `rehearsal-trace-1` means the interface took it, the worker wrote it and the
   column store returned it.

Write down what each step showed, with `docker stats --no-stream` for the five services.

## Creating, migrating and seeding the database

Three commands, run where the application runs, and each of them is safe to run twice. They read
`DATABASE_URL` from the application's environment, so on an install they are run inside the
application container:

```
docker compose $BRAIN_COMPOSE_FILES exec app python -m brain.deployment.database create
```

<!-- checked: the database commands -->

| Command | How to run it | What it does, and what it refuses |
| --- | --- | --- |
| `create` | `python -m brain.deployment.database create` | Creates the database `DATABASE_URL` names, on the server it names, by connecting to that server's `postgres` database. If the database exists it says so and writes nothing. You need it when the database server is one you already run; the database container on a standard install creates the database itself, and running `create` there reports that it already exists. |
| `migrate` | `python -m brain.deployment.database migrate` | Brings the schema to this release, in one transaction under the same lock the application takes at startup. At this release already, it applies nothing and says so. Refuses a database the server does not have and tells you to run `create`. |
| `seed` | `python -m brain.deployment.database seed` | Loads the demo company, for a demonstration or staging server only. Refuses a schema behind this release and tells you to run `migrate`, and refuses any database holding rows the demo did not write, which is every live install. A second run over its own demo writes nothing. It has no way past that refusal; see the seed's own `--force` in `python -m brain.seed` if you are rebuilding a development database. |

The three are the same in every profile. `full` also needs the trace ledger's own database and
login, and the installer creates those in its step "create the databases the compose files do
not", so there is nothing extra to run here.

**A full disk is reported by name and exits with status 3.** Refusals exit 1, a missing
`DATABASE_URL` or an unknown command exits 2. `migrate` and `seed` each write in one transaction,
so when the disk fills part of the way through, nothing they wrote is kept: free space on the
server's disk and run the same command again. That is only true of these three commands. A disk
that fills while the application is serving surfaces as an ordinary failure of whatever was
writing, and is not yet reported by name.

## Logging

**The audit ledger is not optional and is not a log.** It records who read what, it is
append-only, it is hash-chained, and its retention never expires. Every profile writes to it,
including the smallest.

**Traces are optional and only `full` has anywhere to put them.** A trace is the step-by-step
record an operator reads to explain how one answer was assembled. It is a diagnostic aid rather
than an obligation, and the trace ledger is four containers and about two gigabytes.

This distinction catches people out during an incident on a `lite` install, so it is worth
stating in advance: **`lite` is not "logging off"**. What `lite` gives up is the trace, not the
record of who saw what.

**Do not set a trace destination on a profile that runs no trace ledger.** Startup refuses it,
deliberately, and the reason is worth knowing because the failure it prevents is silent in both
directions: a refused span is retried and dropped inside the client library, and an accepted one
means your traces are sitting on a host chosen by whoever last copied an environment file. The
same rule and a heavier version of it apply to `BRAIN_INFERENCE_URL`: a trace host receives
metadata about a request, and a model-reading destination receives the text of the document
itself. `BRAIN_INFERENCE_URL` is the declaration that startup judges; the address actually
dialled is `INSTALL_MODEL_ENDPOINT`, and `python -m brain.knowledge.embed --check` prints it,
says it is the only one, and reports the two naming different hosts.

## Backups, and the honest position

The schedule is written down and nothing runs it.

| What is covered | How | How often |
| --- | --- | --- |
| The database | continuous write-ahead archiving | every 60 seconds |
| The database | incremental | daily |
| The database | full | weekly |
| The object store | content-addressed snapshot | hourly |
| Configuration | snapshot | hourly |

The intervals are argued rather than round numbers. A write-ahead segment is archived every
minute whether or not it is full, so a quiet database does not accumulate an hour of exposure
waiting for a segment to fill. A daily incremental bounds how many segments a restore has to
replay, which is the difference between a recovery time in minutes and one in hours. A weekly
full bounds the incremental chain, and a chain with no full at the bottom is a set of copies
that restores nothing. Configuration is hourly because it changes rarely and matters entirely:
an install restored with last month's realm and policies is a different install.

**The worst gap on that schedule is one hour**, which is what the object store and the
configuration snapshots set.

### What the recovery figures mean, and what you should sign

Each profile carries a recovery point (how much work you can lose) and a recovery time (how
long you are down).

| Profile | Recovery point | Recovery time |
| --- | --- | --- |
| `lite` | 24 hours | 8 hours |
| `standard` | 4 hours | 4 hours |
| `full` | 1 hour | 2 hours |

**A recovery time nobody has measured is a guess in a contract.** This system will refuse to
render a service level statement that promises a recovery point the schedule cannot deliver,
one that no drill has ever measured, or one that the last drill exceeded. All three are
promises somebody signs and only the first is visible to anybody reading the schedule.

No drill has ever run here. So none of those figures has been verified against a real restore,
and the statement generator refuses accordingly. Do not sign one until it does not.

### A backup nobody has restored is a file

This is the sharpest thing on the page. The vocabulary in this system distinguishes a backup
that exists from a backup that has been restored, and only the second one counts, because the
first is a file whose contents nobody has ever read back.

There is a deliberate rule in the code that nothing under `src/brain` may be named "restore"
except the one function that answers "when was a restore last verified". A console field
labelled "last verified restore" beside a backup timestamp is the field somebody checks before
deciding not to worry, and the rule exists so that the day somebody builds a restore is the day
that screen gets written.

## Eight of the fifteen mechanisms are started by nothing

Named individually, because "monitoring is not wired" is a sentence somebody skims. The last
column is the registry's own word for what starts each one, and this table is checked against
that registry in both directions: a mechanism this install carries and the table does not name
fails a test, and so does a row whose last column disagrees with the code.

That check exists because this section was wrong. It read "the twelve mechanisms nothing runs"
on the morning of 2026-09-09 and eleven was already true, because one had acquired a caller and
the heading, the table and the count were three hand-kept copies of a fact the code holds. Ten
became true on 2026-09-11, when the console page that lets somebody choose a staff source and
test it before it runs became the first caller of the roster dry run. Nine became true on
2026-09-15, when the general worker began ticking the control schedule and the retention
sweep was the first of these it started. Eight became true the same day, when the schedule began
starting the re-verification nag.

<!-- checked: every scheduled mechanism and whether anything starts it -->

| Mechanism | What it would guard | Started by |
| --- | --- | --- |
| `retention_sweep` | that nothing is kept past the window its data class was given | `in_process` |
| `canary_run` | that the gate still refuses today what it refused yesterday | `nothing` |
| `restore_drill` | that the copies being taken can actually be restored | `in_process` |
| `backup_exposure` | that a stretch of work with no copy anywhere is noticed while it is still short | `nothing` |
| `denial_digest` | that a colleague who keeps being told there is nothing there is noticed by somebody who can fix it | `nothing` |
| `directory_sync` | that the roster follows employment: joiners, movers and leavers | `in_process` |
| `knowledge_reverification` | that an answer drawn from something somebody once approved is not still being given long afterwards | `in_process` |
| `resolution_calibration` | that the weights deciding whether two records are the same person stay fitted to the data | `nothing` |
| `queue_redrive` | that a job whose worker died underneath it is reclaimed rather than left | `nothing` |
| `side_effect_resume` | that a side effect issued by a process which then died is read back from the source before anything is retried | `nothing` |
| `audit_anchor` | that entries removed from the end of the audit ledger are detectable rather than silent | `on_a_route` |
| `model_health_probes` | that a provider which has stopped answering is found by asking it rather than by a person's question failing | `nothing` |
| `spend_correction` | that the cost estimator every budget decision is taken against stays anchored to what actually ran | `in_process` |
| `outbox_dispatch` | that a webhook subscriber is told about the events it asked for, retried while it is down | `nothing` |
| `spend_report_refresh` | that the spend report a reader is shown is rebuilt daily from what runs actually cost | `in_process` |

Three words appear in that last column and they are not degrees of the same thing. `nothing`
means no call site of any kind. `in_process` means another module calls it, and the word alone
says nothing about whether *that* module is ever reached. For `retention_sweep`,
`knowledge_reverification` and `spend_report_refresh` it is: the general worker ticks the control
schedule and starts all three. The sweep runs in report-only mode, deleting nothing, until the
installation releases it: every run writes a report an administrator reads at
`GET /api/v1/govern/retention`, and somebody holding `admin:retention` over everything releases
the sweep after the newest report with `POST /api/v1/govern/retention/release`, or puts it back
to reporting with `POST /api/v1/govern/retention/withdrawal`. A legal hold placed with
`POST /api/v1/govern/legal-holds` by somebody holding `admin:legal_hold` keeps the rows it covers
from the next run on. The re-verification nag records each nag in the webhook outbox, asks
the owner only while the owner can still reach the document, and sends nothing yet, because
nothing drains the outbox.
For `spend_correction` it means a console screen nobody opens on a schedule, for
`directory_sync` a console page somebody presses, and for `restore_drill` a recovery panel that
can only show an alarm, because nothing performs a drill. `on_a_route` is started from outside:
an external timer calls an HTTP route, and it is what makes it detectable if entries are ever
removed from the end of the audit ledger.

**A safety mechanism with no caller is worse than no safety mechanism**, because the console
says the estate is protected. That is why they are listed here by name rather than summarised,
and why the registry that tracks them is checked in both directions: a mechanism that gets
wired without being recorded fails a test, and so does one that was wired and stops being.

## What to do about it

Two questions belong to whoever owns this install, and neither has a default answer.

**Where do scheduled jobs run?** There are three shapes: a small scheduler inside the
application container, external timers calling HTTP routes (which is how the one working
mechanism runs today), or timers on the server itself. The trade-off is between something that
follows the deploy and something an operator can see and disable without a release.

**Which mechanisms do you switch on first?** The backup one, then the drill that proves it,
before anything else on the list.

## A read replica for the console, if you add one

This is optional. `docker-compose.replica.yml` creates a replica on the same server as the
database, and [scaling.md](scaling.md) has the steps; a replica you already run elsewhere works
the same way. What the application does once you have one is described here.

Set `BRAIN_READ_REPLICA_URL` to the replica's address. Leave it empty, which is the default, and
every console page is read from the main database exactly as before.

When it is set:

- **Console pages that only display are read from the replica.** Today that is the routing
  matrix page. Anything that decides who may do what, and anything that writes, is always read
  from the main database, however healthy the replica is. A permission removed a second ago may
  not have reached the replica yet.
- **The application measures how far behind the replica is**, at most once every two seconds,
  and gives up on a measurement after one second.
- **Up to 10 seconds behind:** the page is read from the replica and says nothing.
- **More than 10 seconds and up to 5 minutes behind:** the page is read from the replica and its
  response carries a `staleness` field stating how many seconds behind it is. The console shows
  that as a banner.
- **More than 5 minutes behind, unreachable, or not a replica at all:** the page is read from the
  main database, with no banner. "Not a replica" includes a replica that has been promoted after a
  failover, which is a separate database and is never read.

**Falling back to the main database is deliberate.** Replicas fall furthest behind when the main
database is busiest, so a console page may add load to the main database at exactly that moment.
The alternative is showing numbers that are minutes old, which this system does not do.

**One limit to know about.** If the network between the two databases fails silently, the replica
can look up to date for as long as PostgreSQL's `wal_receiver_timeout` (sixty seconds by default)
before PostgreSQL notices. Lower that setting on the replica if sixty seconds is too long for you.

The replica's database role only needs to read. The application runs every console read with
`SET TRANSACTION READ ONLY` on both databases, so a read-only role is enough.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| Which database a console page is read from, and when it carries a staleness banner | `test_read_replica.py` and `test_replica_store.py`; the lag query itself against a real server that is a primary, never against a real replica |
| The backup schedule and its intervals | `test_recovery.py`, against the schedule |
| The recovery figures per profile | `test_reliability.py` |
| That a service level statement is refused when the arithmetic does not support it | `test_launch.py` |
| The thirteen mechanisms, and which have a caller | `test_controls.py`, read out of the source in both directions |
| That every component declares what ready means | `test_wiring.py` |
| That the database command table names every command, no other, and how to run it | `test_install_docs.py`, against `brain.deployment.database` |
| That the commands refuse in order, run twice safely, and name a full disk | `test_deployment_database.py`, against a real server where `DATABASE_URL` is set |
| **That `migrate` reaches the newest schema on a server without pgvector** | **nobody, and it cannot: the first migration installs `vector`** |
| **Everything about what you should do next** | **nobody. Prose, kept true by hand.** |

## Task ids

M42.2.8 is not claimed. The leaf asks for backup, monitoring, logging and health-check
configuration. Two of the four are configured and documented above: the health checks answer and
every container declares one, and the logging split between the audit ledger and the optional
trace ledger is real in every profile. The other two are not configuration at all today. The
backup schedule is a set of constants that nothing runs, no drill has ever verified a restore,
and almost every mechanism in the table above is the monitoring. A client following this page
ends with health checks and no backups.
