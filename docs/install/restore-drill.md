# Rehearsing a restore

**Nobody has followed this page on a server.** It is written from the backup script, the drill
script, the record format the product reads and the checks it requires, and every command on it
is one those files imply. The two scripts have been run once, end to end, on a development machine
against two local PostgreSQL clusters with docker and the object store stood in for; the steps
around them have not been rehearsed at all. Read it the way you would read a runbook somebody
wrote carefully and never ran on a real install, and expect the first run to find something.

**A script does part of this for you, and only part.** `ops/backup/brain-restore-drill` loads a
copy into the scratch database and checks that every table's row count and the migration head
came back as the copy's manifest states them. Downloading the copy, starting the scratch
database, creating the roles, the schema check, the row-level security sweep, the permission
canary and the record are still yours. No timer schedules a drill, and the console control the
recovery screen describes is not built. The table near the foot of this page says so piece by
piece, and a test holds that table to the repository.

## What a drill proves, and what it does not

A copy nobody has read back is a file. The nightly copy is written, uploaded and described by a
manifest beside it, and none of that says whether it can be read: a truncated dump, a copy taken
while something was wrong, and a good copy all look the same in a bucket listing.

A drill reads one copy back into a throwaway database and asks it three questions. It proves
something only if all three are asked and all three pass, and the product decides that, not you:
the record you write says what you asked and what came back, and never whether it verified.

**A restore can bring back every row and none of the rules about who may read them.** That is
why the third question exists, and why a drill that skips it is a drill that did not verify. The
drill script's row counts are the second question, not the third: a load can match every count
and still have lost a policy.

## Before you start

- Work on the server where `ops/backup/brain-install-backup` was run, as root. It wrote
  `/etc/brain-backup.env`, which holds the database container, the database name and user, the
  bucket, the object store's address, and the key that may read the bucket.
- Have `brain-restore-drill` on that server. The release archive does not carry `ops/backup`, so
  copy `ops/backup/brain-restore-drill` from the repository at the release tag the install runs,
  the same way `brain-backup` reached `/usr/local/bin`.
- Pick a copy younger than the window copies are kept for (the figures table below). An older
  one has already been expired by the bucket's own rule.
- Pick a copy whose manifest carries `migration_head` and `row_counts`. Copies taken by a
  `brain-backup` older than those two fields have neither, and the drill script refuses them
  because it has nothing to compare the load with.
- Have free disk for the copy twice over: once downloaded, once loaded.
- Never point any step at the live database container except the two that only read from it,
  which say so. The drill script refuses to: see step 7.

## The questions a drill asks the copy

<!-- checked: the questions a drill asks the copy -->

| Check | What it asks | How |
| --- | --- | --- |
| `schema_complete` | every schema the application expects is present in the loaded copy | `python -m brain.ops.schema_check <scratch database url>` |
| `smoke_query` | a question with a known answer returns that answer | `brain-restore-drill`, which asks the loaded copy for its revision in `alembic_version` and every table's row count, and compares each with what the copy's manifest states |
| `permission_canary` | row-level security is still switched on for every entity table, and a restricted field is still refused to somebody who may not read it | `python -m brain.ops.sweeps rls` for the first half; nothing runs the second half for you |

The schema check looks at schemas and not at tables or policies, so it catches a load that
stopped early and not one that lost a policy. The drill script's counts catch a load that brought
back fewer rows, or more, than the copy held, table by table; the manifest's figures were read
inside the snapshot the copy was taken from, so a busy database does not make them disagree. The
row-level security sweep catches a table whose protection did not come back. **None of them asks
a question as a person**, and that is the half of the canary that sees the failure that matters
most: an application pointed at the copy, asked by somebody without the grant for a restricted
field, has to refuse. Nothing in this product asks that for you yet. Until you have asked it,
record the canary as not passed and say why in its detail; a canary nobody asked is not a canary
that passed.

## The procedure

1. **Load the install's values.**

   ```sh
   set -a; . /etc/brain-backup.env; set +a
   mkdir -p /var/tmp/brain-drill && cd /var/tmp/brain-drill
   ```

2. **Choose the copy.** Copies are named `database-<when it began>` and each has a manifest.

   ```sh
   aws --endpoint-url "$BRAIN_BACKUP_ENDPOINT" s3 ls "s3://$BRAIN_BACKUP_BUCKET/"
   ```

3. **Download the copy and its manifest**, under the names the bucket gives them. The drill
   script compares the size the manifest states with the size you downloaded and refuses to load
   a copy whose sizes disagree, which is exactly when the upload was truncated. A truncated copy
   ends the drill there: record it as not passed.

   ```sh
   ID=database-YYYYMMDDTHHMMSSZ
   aws --endpoint-url "$BRAIN_BACKUP_ENDPOINT" s3 cp "s3://$BRAIN_BACKUP_BUCKET/$ID.dump" .
   aws --endpoint-url "$BRAIN_BACKUP_ENDPOINT" s3 cp "s3://$BRAIN_BACKUP_BUCKET/$ID.manifest.json" .
   ```

4. **Note the time.** The drill starts now, and the recovery time is measured from here to the
   last check.

   ```sh
   date -u +%Y-%m-%dT%H:%M:%SZ
   ```

5. **Start a scratch database on a network with no way out**, from the same image the live
   database runs, and wait until it answers. `--internal` is what keeps anything in it from
   reaching anything else, and the drill script refuses a scratch container on any network that
   is not internal.

   ```sh
   IMAGE="$(docker inspect --format '{{.Config.Image}}' "$BRAIN_DB_CONTAINER")"
   docker network create --internal brain-drill
   docker run -d --name brain-drill-db --network brain-drill -e POSTGRES_PASSWORD=drill "$IMAGE"
   until docker exec brain-drill-db pg_isready -U postgres; do sleep 2; done
   ```

6. **Create the roles before loading anything.** A dump holds a database and not the roles its
   policies name, and a load without them brings back the rows and fails the policies, which is
   exactly the failure the canary exists to see. This step reads the live database and changes
   nothing in it. A role the scratch database already has, such as `postgres` when the live
   database has one too, is reported as already existing, and that error is harmless.

   ```sh
   docker exec "$BRAIN_DB_CONTAINER" pg_dumpall -U "$BRAIN_DB_USER" --roles-only --no-role-passwords > roles.sql
   docker exec -i brain-drill-db psql -U postgres < roles.sql
   ```

7. **Load the copy and check it with the drill script.** Name the scratch container and a
   scratch database name the live database does not have.

   ```sh
   brain-restore-drill --manifest "$ID.manifest.json" --dump "$ID.dump" \
       --scratch-container brain-drill-db --scratch-database brain_drill
   ```

   Before it writes anything, it refuses (and exits 2) when a scratch target is not named, when
   the scratch container is `$BRAIN_DB_CONTAINER` by name or by the identifier docker reports, when
   the scratch database name is `$BRAIN_DB_NAME`, when the scratch container is on a network that
   is not internal, and when the manifest does not state a size, a migration head and row counts
   in the layout `brain-backup` writes. It never runs anything in the live container.

   Then it creates the scratch database fresh, loads the copy in one transaction that stops at
   the first error, asks the loaded copy for every table's row count and its migration head, and
   compares both with the manifest. It exits 0 when everything came back, and 1 when anything did
   not, naming each table whose count differs. If the load stops with a role that does not exist,
   step 6 was skipped: destroy the scratch container, start again at step 5, and do not count the
   attempt. Its result is your answer to `smoke_query`.

8. **Ask the other two questions.** Both run from the application image, on the drill network,
   against the scratch database only. Find the application image with `docker ps`.

   ```sh
   SCRATCH="postgresql://postgres:drill@brain-drill-db:5432/brain_drill"
   docker run --rm --network brain-drill <application image> python -m brain.ops.schema_check "$SCRATCH"
   docker run --rm --network brain-drill -e DATABASE_URL="$SCRATCH" <application image> python -m brain.ops.sweeps rls
   ```

   Then ask the second half of the canary as described above, and note the time again when the
   last answer is in.

9. **Write the record and put it beside the copy.** Name it after the copy, ending in the drill
   record suffix below, with the fields in the next section. Then upload it.

   ```sh
   aws --endpoint-url "$BRAIN_BACKUP_ENDPOINT" s3 cp "$ID.drill.json" "s3://$BRAIN_BACKUP_BUCKET/$ID.drill.json"
   ```

10. **Destroy the scratch database and everything downloaded.** The dump holds every record the
    install holds, and `roles.sql` names every role.

    ```sh
    docker rm -f brain-drill-db
    docker network rm brain-drill
    rm -rf /var/tmp/brain-drill
    ```

## The record you write

<!-- checked: the fields a drill record carries -->

| Field | Where | What to write |
| --- | --- | --- |
| `backup_id` | the record | the copy's identifier, exactly as its manifest states it |
| `started_at` | the record | the time from step 4, in UTC |
| `finished_at` | the record | the time the last answer came in, in UTC |
| `into_scratch` | the record | `true`, and only because step 5 made a database nothing else uses |
| `checks` | the record | one entry per question, as a list even if you asked one |
| `check` | each check | `schema_complete`, `smoke_query` or `permission_canary` |
| `passed` | each check | `true` or `false`, written bare and never in quotes |
| `detail` | each check | a sentence saying what you asked and what came back, never a value read out of the copy |

**There is no field for whether it verified, and no field for how long it took.** Both are
worked out from the record by the product. A record that said it verified would put the
definition of a verified restore in whoever wrote the record, and a runner that never asked the
canary would have nothing to report and would write yes. That is also why the drill script writes
no record: it asks one of the three questions, and a record carrying only its answer would be a
drill that skipped two.

`"passed": "false"` in quotes is a string, and the product refuses the whole record rather than
reading a string of five letters as a pass.

The copy the examples below read, as its manifest describes it. `migration_head` and `row_counts`
are what the drill script compares the load with; the product's own reader reads the fields
before them.

<!-- checked: the manifest of the copy the drill read -->
```json
{
  "backup_id": "database-20190303T020000Z",
  "coverage": "database",
  "method": "full",
  "destination": "s3://backups",
  "started_at": "2019-03-03T02:00:00Z",
  "finished_at": "2019-03-03T02:04:10Z",
  "recoverable_to": "2019-03-03T02:04:10Z",
  "size_bytes": 48213990,
  "migration_head": "0051",
  "row_counts": {
    "know.item": 18204,
    "obs.audit_event": 412977,
    "public.alembic_version": 1
  }
}
```

A drill of that copy which verifies:

<!-- checked: a drill record that verifies -->
```json
{
  "backup_id": "database-20190303T020000Z",
  "started_at": "2019-03-04T09:00:00Z",
  "finished_at": "2019-03-04T09:41:30Z",
  "into_scratch": true,
  "checks": [
    {
      "check": "schema_complete",
      "passed": true,
      "detail": "the schema check reported every expected schema present in the scratch copy"
    },
    {
      "check": "smoke_query",
      "passed": true,
      "detail": "the drill script reported every table's row count and the revision in the scratch copy matching the copy's manifest"
    },
    {
      "check": "permission_canary",
      "passed": true,
      "detail": "the row-level security sweep passed on the scratch copy, and the application pointed at it refused a restricted field to a person without the grant"
    }
  ]
}
```

The same drill with the roles step skipped and the copy loaded by hand without stopping at errors,
which brings back every row and none of the policies and fails the canary. It does not verify, it carries no recovery time, and the panel treats
every copy as unproven until a later drill does:

<!-- checked: a drill record that does not verify -->
```json
{
  "backup_id": "database-20190303T020000Z",
  "started_at": "2019-03-04T09:00:00Z",
  "finished_at": "2019-03-04T09:38:05Z",
  "into_scratch": true,
  "checks": [
    {
      "check": "schema_complete",
      "passed": true,
      "detail": "the schema check reported every expected schema present in the scratch copy"
    },
    {
      "check": "smoke_query",
      "passed": true,
      "detail": "the drill script reported every table's row count and the revision in the scratch copy matching the copy's manifest"
    },
    {
      "check": "permission_canary",
      "passed": false,
      "detail": "the row-level security sweep reported tables without their protection, because the roles the policies name were not created before the load"
    }
  ]
}
```

## What the recovery screen makes of it

The product reads every record in the bucket whose name ends in the drill record suffix, works
out from each whether it verified and how long the recovery took, and the recovery screen's
verdict is built from those and from the copies. Its runbook, `docs/console/runbooks/recovery.md`,
lists every verdict and what to do about each.

**The screen cannot be opened yet, and nothing reads the bucket into it on a schedule.** So
today a record you upload is correct, is in the place the product reads, and is shown to
nobody.

## The figures this procedure depends on

<!-- checked: the figures this procedure depends on -->

| Figure | Value |
| --- | --- |
| Days between rehearsals | `7` |
| Days a copy is kept | `35` |
| A copy's manifest name ends | `.manifest.json` |
| A drill record's name ends | `.drill.json` |

Rehearse more often than copies expire, or a copy can be taken, kept and expired without anybody
having read it back once. No copy is kept past the window above, because every erasure
certificate this product writes promises that window. The retention ladder is thirty daily copies
and weekly copies to the end of that window, decided that way so it fits inside the promise
rather than the year the plan first named.

## What this procedure has no machine for

<!-- checked: what this procedure has no machine for -->

| Piece | Exists today |
| --- | --- |
| A script that performs a drill | `no` |
| A timer that schedules a drill | `no` |
| A console control that starts a drill | `no` |
| The recovery screen can be opened | `no` |
| A reader that turns a drill record into a verdict | `yes` |

Every `no` is a row a test compares with the repository, and it goes red on the day that piece is
built. That is the day to read this procedure again, because some of it will have become a
button.

The first row stays `no` with `brain-restore-drill` in the repository, and that is the test being
right rather than stale. A script that performs a drill writes the record, and this one performs
step 7 and writes nothing: steps 1 to 6 and 8 to 10 are still a person's.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The three questions, in the order the product requires them | `test_install_drill_page.py`, against the checks a drill needs to verify |
| That every `python -m` command in that table is a module that runs as one | the same test, against the modules in the product |
| Every field a record carries and where it sits, and no field the product does not read | the same test, against the fields the record reader requires |
| The four figures | the same test, against the rehearsal interval, the bucket's window and the two file suffixes |
| That the example that verifies does, that the one that does not does not, and that both read the example copy after it was taken | the same test, by running the product's own readers and verdict over the examples on this page |
| Which pieces of a drill exist | the same test, against the scripts and timers under `ops/` and the console tools the application registers |
| That the drill script refuses a missing target, the live container by name and by identifier, the live database name and a network that is not internal, before anything is written | `test_backup_scripts.py`, by running the script against stand-ins for docker that record every call |
| That a scratch target is loaded, and that nothing is ever run in the live container | the same test, on the calls the stand-ins recorded |
| That a count or a head that did not come back fails naming the table, and a manifest without them is refused | the same test, against the manifest `brain-backup` itself wrote |
| That `brain-backup` counts inside one read-only transaction and dumps the snapshot it counted in | the same test, on the statements its session was fed and the dump's arguments |
| **Every command in the procedure** | **nobody on an install. It has never been run on a server.** Both scripts ran once on a development machine against two local PostgreSQL 17 clusters, with docker and the object store replaced by shims that ran the real client programs: the counts matched while rows were being written during the copy, a load before the roles existed stopped at the first policy, and a manifest stating a wrong count and head failed naming both. The image, the containers, the bucket and the product's full schema were not part of that run. |
| **That a load with the roles created first brings back working policies** | **nobody. It is what the canary is for, and no drill has run.** |

## Task ids

M34.3.3.4 is claimed: the leaf asks for a restore drill procedure, which this page is, and the
parts of it a machine can hold are held.

M42.3.5 is not claimed by this page. Its scripts exist and are held by tests that need no
server; its verified half is a drill on an install, and none has run.

M30.3.9 is not claimed. It is the one-click drill, and the table above says there is no control.
The retention ladder, M30.3.5, is not this page's claim: it is decided and held in
`brain.ops.recovery`, and nothing but the bucket's own rule removes a copy yet.
