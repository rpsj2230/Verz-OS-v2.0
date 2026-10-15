# Growing past one server: a read replica, and two hosts

Two changes an install makes when one server is no longer enough, each behind a trigger that
`brain.ops.scaling` states: a read replica when console pages start to slow the answers staff are
waiting for, and a second host when memory runs short or the database has to survive the
application's server. Neither is part of a normal install. Both are overlays: compose files added
with a second `-f` on top of your profile's own files, so nothing in the profile changes and
removing the overlay puts the install back as it was.

**Neither has been run.** Both overlays are checked against the files they sit on top of, on every
test run, and neither has been started on a server. Each section below ends with the checks that
would show it working, and those checks are the rehearsal.

**The release archive does not carry these files yet.** Take `docker-compose.replica.yml` and the
three `docker-compose.split*.yml` files from this repository at the tag your install runs, and put
them in `/opt/brain` beside the others. The update and rollback scripts do not compose them either,
so an update on an install using one is run by hand with the same commands as below.

## A read replica for console pages

What the application does with a replica, and when a page falls back to the main database, is in
[operations.md](operations.md). This is how to create one on the same server as the database.

The overlay adds two services. `db-replication-setup` runs once: it creates a login that may copy
the database, allows that login to connect for copying, creates a replication slot, and limits how
much history the database keeps for the replica. `db-replica` copies the database the first time
it starts and follows it from then on. The application is told the replica's address with
`BRAIN_READ_REPLICA_URL`.

**The limit is what protects the main database.** A slot makes the database keep every change the
replica has not received. Without a limit, a replica that stops would fill the database's disk and
stop it taking writes. With the limit, which is `2GB`, the database gives up the slot instead, the
replica has to be copied again, and console pages are read from the main database meanwhile. On a
server with little free disk, lower it in `docker-compose.replica.yml` before you start.

### Steps

1. Add a password for the copying login to `/opt/brain/.env`, generated on the server:

   ```
   printf 'BRAIN_REPLICATION_PASSWORD=%s\n' "$(openssl rand -hex 32)" | sudo tee -a /opt/brain/.env > /dev/null
   ```

2. Start it, with your profile's files first. On `lite`:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.replica.yml up -d
   ```

3. Check the setup finished. `db-replication-setup` shows `Exited (0)`:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.replica.yml ps -a
   ```

4. Check the replica is following. On the main database the slot is active, and the replica says
   it is in recovery:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.replica.yml exec db psql -U brain -d brain -c "SELECT slot_name, active, wal_status FROM pg_replication_slots"
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.replica.yml exec db-replica psql -U brain -d brain -c "SELECT pg_is_in_recovery()"
   ```

   The first shows `brain_replica | t | reserved`. The second shows `t`.
5. Check the limit is set: `SHOW max_slot_wal_keep_size` on `db` shows `2GB`.
6. Check the fallback. Open the routing matrix page in the console. Stop the replica with
   `stop db-replica` in place of `up -d`, reload the page, and it still loads, from the main
   database. Start the replica again.

### Removing it

Remove the two containers, and **then drop the slot**, or the main database keeps history for a
replica that no longer exists until the limit is reached:

```
docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.replica.yml rm -sf db-replica db-replication-setup
docker compose -f /opt/brain/docker-compose.lite.yml exec db psql -U brain -d brain -c "SELECT pg_drop_replication_slot('brain_replica')"
```

## Two hosts: the application on one, the database on the other

The application host runs the application, the cache, the workers, the identity provider and the
inference server. The data host runs the database, both connection poolers and the file store. The
application finds the database from a connection string, so the split changes connection strings
and published ports and nothing else: the image, its settings and its commands are the same on
both hosts as on one. `brain.ops.split` refuses an overlay that changes anything more.

It covers `lite` and `standard`. It does not cover `full`: the trace ledger connects to the
database and to the file store by their names on one host, and no overlay here moves it.

**Only the poolers and the file store cross between the hosts, and only on one private address.**
The data host publishes the transaction pooler on `6432`, the workers' session pooler on `6433` and
the file store on `8333`, each on the address in `BRAIN_DATA_HOST_ADDRESS` and on no other
interface. The database itself is never published. Nothing gives these connections a certificate,
so **the address has to be on an encrypted link between the two servers**, such as WireGuard. A
hosting provider's private network that other customers share is not one.

### What you need

- Two servers with Docker, and an encrypted private link between them with an IPv4 address on
  each end. The data host's address on that link is `BRAIN_DATA_HOST_ADDRESS`.
- The same release in `/opt/brain` on both, including the split files, and the same
  `/opt/brain/.env` on both. Copy it over SSH: it holds every password.

### Steps

1. **Check the address.** On either host, with the image your install runs, which is the value of
   `APP_IMAGE` in `/opt/brain/.env`:

   ```
   docker run --rm <APP_IMAGE> python -m brain.ops.split --check-address <data host link address>
   ```

   It prints nothing wrong and exits 0 for a private IPv4 address. It refuses the address that
   means every interface, a loopback or public address, IPv6 and a hostname, and says why.
2. **Set it on both hosts.** Add `BRAIN_DATA_HOST_ADDRESS=<data host link address>` to
   `/opt/brain/.env` on each.
3. **Find which services each host starts.** Run this for `data` and for `application`, with your
   profile:

   ```
   docker run --rm -v /opt/brain:/opt/brain:ro <APP_IMAGE> python -m brain.ops.split --services lite data --in /opt/brain
   ```

   On `lite` it prints `db pgbouncer` for the data host and `app cache` for the application host.
4. **Start the data host.** Your profile's files, then the split files your profile needs: the
   first always, `docker-compose.split.workers.yml` and `docker-compose.split.objectstore.yml` on
   `standard`. Then the data host's services. On `lite`:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.split.yml up -d db pgbouncer
   ```

5. **Check the data host listens on the link only.**

   ```
   sudo ss -tlnp | grep -E ':(6432|6433|8333) '
   ```

   Every line shows the link address, never `0.0.0.0` or `*`.
6. **Start the application host**, with the same files and its own services, and `--no-deps`,
   which is not optional: without it compose starts an empty database on this host for the
   application to depend on. On `lite`:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.split.yml up -d --no-deps app cache
   ```

7. **On `standard`, point the file store address at the data host.** Set
   `INSTALL_OBJECT_STORE_URL` to `http://<data host link address>:8333` in `/opt/brain/.env` on
   the application host, and run the command in step 6 again so the application reads it.
8. **Check it works.** `https://<console address>/health/ready` answers `200`. Sign in and ask a
   question. `docker compose ps` on the application host lists no `db` and no `pgbouncer`.

Forgetting the service list on the application host fails loudly rather than quietly: the poolers
try to bind the data host's address, which is not on that machine, and compose refuses to start.

### Moving an install that already runs on one server

The simplest direction keeps the data where it is: the existing server becomes the data host and
the new server becomes the application host. Stop the application on the existing server, follow
the steps above, and only then remove `app` and `cache` from the existing server with
`rm -sf app cache`. The database volume never moves.

### Backups on a split install

The database is on the data host, so the backup timer and the restore drill run there.

## Partitions of the metadata ledger

Nothing to set up, and it is not an overlay. The ledger, which records who asked what and how it
was answered, is cut into one table per calendar month. On `standard` and `full` the general
worker keeps them in order every day, as part of the retention sweep's run: it creates the current
month and the next three, moves any rows sitting in the catch-all partition into their month, and
detaches a month once every row in it is older than the ledger's five-year window. It uses plain
SQL, so the database needs no extension.

**Detaching keeps the rows.** A detached month leaves the live ledger and stays in the database as
its own table, which the retention sweep's report counts as past its window. Nothing drops it yet,
and detaching waits for the same release the retention sweep does, so until somebody releases the
sweep the run only reports which months it would detach.

**What the run said is in the retention sweep's run record**, on a line starting `ledger
partitions:`. On `lite`, which runs no worker, every row stays in the catch-all partition, which is
correct and does not age out.

## The peak load test

Nothing starts it for you, and it ships switched off. It asks your install's own answer route the
number of questions per second your profile states for its busiest minute, for ten minutes, and tells
you whether each lane held the service levels (answers inside eight seconds, record lookups inside
half a second, more than 99.5 in 100 requests succeeding). **It spends your model provider's calls**:
most of what it asks goes to the model, so the full run at the `full` profile is 1,200 requests, about
960 of them to the model. Run it at a quiet time.

The stated peaks are the capacity model's and are shown on **Install > Capacity**: `lite` 0.5 a second
(2 in flight at once), `full` 2 a second (8 in flight), `ha` 8 a second (32 in flight). The run reports
the most it really had in flight at once beside that figure.

### Steps

1. **Switch it on.** On the console's Features page, turn on "Allow the peak load test to be run
   against this install".
2. **Make the people it asks as.** Create a department called `load_test`, put two or more people in
   it (each needs their own sign-in, because each person has their own rate limit and the run spreads
   its questions over them), and add one small document the department alone may read. Write the
   questions in a file, one per line as `answer`, a tab, then a question the document answers, and
   `fast`, a tab, then a record lookup a rule of that department answers. The run **refuses** any
   token that is not a person in that department, so it can never be sent as a real person.
3. **Get a token for each test person** and put them in a file, one per line, kept off the server's
   disk afterwards. Nothing prints a token.
4. **Run it in the application's container**, with the same number twice. A short run first:

   ```
   docker exec -i <application container> python -m brain.ops.load_peak \
     --base-url http://localhost:8000 --token-file /path/tokens --questions-file /path/questions \
     --profile full --seconds 100 --max-requests 200 --confirm-requests 200
   ```

   The full run is `--seconds 600 --max-requests 1200 --confirm-requests 1200`. A run below the stated
   peak is reported, and says it is not the peak test.
5. **Read the result.** It prints each lane's 95th percentile and success rate against the target and
   ends `held at the stated peak`, `held, on a run smaller than the stated peak`, or `not held`. The
   same figures are kept as one row in your own database (no token, person or question in it).

**It stops itself** if the install starts refusing most of what it is asked (at least 20 replies in,
half of them refused): it sends nothing further and says how many requests it did not send. It never
changes a limit. **What it leaves behind:** each question is an ordinary request in the request
ledger, which is append-only, attributed to the test people alone; nothing else is written except the
result row. **What it does not measure:** the network or proxy in front of the address it is given, or
the server's memory headroom.

The install's checks prove the machinery on every run without spending anything: a short run through
the same driver inside a transaction that is rolled back, with no model called.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The run's stated peak is the capacity model's, a smaller run says so, the most in flight at once is measured, and it stops when the install refuses most of what it is sent | `test_load_peak.py` and `test_load_peak_run.py`, without a server |
| It refuses before sending anything while the switch is off, for a token that is not a test person, and without the number typed twice, and nothing but the command builds its sender | `test_load_peak_run.py` |
| A short run is driven, judged, kept and read back inside a rolled-back transaction, with each request recorded on the lane it was sent to | `test_acceptance_load_peak.py`, against a real database in CI, and the install's own check |
| **That the full run at a profile's stated peak holds the service levels on your hardware** | **nobody until you run it. The command is the proof and the stored row is its record.** |
| The replica runs the main database's image, admits at least as many connections, copies through the slot the setup creates, and the application is pointed at it | `test_streaming_replica.py`, against `docker-compose.replica.yml` and both files that describe `db` |
| The slot has the limit, and the setup writes one rule to the database's volume and nothing else | the same test |
| Each host's service list, and that together they start every service once | `test_split.py`, against every profile's files |
| Every published port is a pooler or the file store, bound to the required address, and the database is never published | the same test, against the three split files |
| Nothing on the application host still names a data-host service, a rewritten address reaches the right pooler's port, and the split changes nothing but addresses | the same test |
| The address check's answers | the same test |
| A month is a half-open UTC calendar month, the months ahead cover the backup window, a month leaves only when its newest row is past the window, and no statement drops, truncates or deletes anything but a move's copied rows | `test_ledger_partitions.py`, without a server |
| That rows either side of a month boundary land in their own partitions, a second run changes nothing, and a detached month keeps every row | the same test, against a real server in CI |
| **That compose merges an overlay's environment by key and appends its ports** | **nobody here. Compose's documented behaviour, not run.** |
| **That a replica copies, follows and falls back as described** | **nobody. The rehearsal steps above have not been run.** |
| **That a split install serves a question** | **nobody. As above.** |

## Task ids

M36.1.1.1, M36.1.2.1, M36.1.4.1, M36.1.4.2, M22.3.3
