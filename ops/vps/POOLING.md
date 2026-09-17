# Adding the database poolers and memory settings to an install that predates them

For an install deployed from a stored compose file (Coolify keeps its own copy) that runs
`app`, `migrate`, `db` and `cache` only. The product's `docker-compose.yml` has had the
transaction pooler since M0.3.4 was first written, so a stored copy made before then has the
application connecting straight to `db`, and a `db` command without `autovacuum_work_mem`.
Neither is repaired by a new image: the stored copy is the install's, and only its owner edits it.

Nothing below names a server, a password or an address. Every value comes from the install's
own stored compose file or its own environment file.

Task ids: M0.3.4, M0.3.5, M0.3.6

## What changes, and what it costs

| Change | Why | Interruption |
| --- | --- | --- |
| a `pgbouncer` service, transaction mode | M0.3.4: the application's connections pooled to twenty server connections | none until the app is redeployed |
| `app` connects to `pgbouncer:5432` instead of `db:5432` | the engine is already built for transaction pooling (`brain.session.make_app_engine`) | the app restarts once |
| `db` gains `-c autovacuum_work_mem=128MB` | M0.3.6: unset, autovacuum may take 3 x 256 MiB nobody chose (`brain.deployment.postgres_settings`) | the database restarts once, seconds |
| `migrate` stays on `db:5432` | a one-shot administrator's connection, counted in the database's headroom rather than in the pool | none |
| `pgbouncer-session` (M0.3.5) | only for the two workers' LISTEN and checkpointer; an install that runs no worker has nothing for it to serve | add it with the worker, not before |

## Steps

1. **Take a backup first.** The database restarts in step 5. Use the install's normal backup, and
   confirm the file exists and is not empty before going on.

2. **Open the stored compose file.** In Coolify: the project, then the resource, then
   *Edit Compose File*. Everything below is an edit to that text.

3. **Add the pooler.** Under `services:`, add this block at the same indent as `app:`. It is the
   `pgbouncer` service from the product's `docker-compose.yml`, unchanged:

   ```yaml
   pgbouncer:
     image: edoburu/pgbouncer:v1.24.1-p1
     restart: unless-stopped
     depends_on:
       db:
         condition: service_healthy
     environment:
       DB_HOST: db
       DB_PORT: "5432"
       DB_USER: brain
       DB_PASSWORD: ${POSTGRES_PASSWORD}
       DB_NAME: brain
       POOL_MODE: transaction
       MAX_CLIENT_CONN: "200"
       DEFAULT_POOL_SIZE: "20"
       AUTH_TYPE: scram-sha-256
     expose:
       - "5432"
     deploy:
       resources:
         limits:
           memory: 128M
     healthcheck:
       test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -p 5432 -U brain"]
       interval: 10s
       timeout: 5s
       retries: 15
       start_period: 20s
   ```

   `POSTGRES_PASSWORD` is already in the install's environment file; the database uses it.

4. **Point the application at it.** In the `app` service:
   - under `depends_on:`, replace `db:` with `pgbouncer:` (keep `condition: service_healthy`,
     and keep `cache:` as it is);
   - in `DATABASE_URL`, change only the host: `@db:5432/` becomes `@pgbouncer:5432/`. Leave the
     user, the password and the database name exactly as they are.

   Leave `migrate` pointing at `db:5432`.

5. **Set the autovacuum memory.** In the `db` service's `command:`, add
   `-c autovacuum_work_mem=128MB` after `-c maintenance_work_mem=256MB`. The four memory figures
   must then read `shared_buffers=512MB`, `work_mem=16MB`, `maintenance_work_mem=256MB`,
   `autovacuum_work_mem=128MB`, with the container limit at `2048M`.

6. **Save and deploy** the resource in Coolify.

## How to confirm it worked

Run on the server. Container names carry the resource's suffix; `docker ps` shows them.

```sh
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^(app|pgbouncer|db|cache)-'
```
Expect `pgbouncer-...` as `(healthy)` and `app-...` as `(healthy)`.

```sh
docker exec <db container> psql -U brain -d brain -tAc "SHOW autovacuum_work_mem"
```
Expect `128MB`.

```sh
docker inspect <pgbouncer container> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}'
docker exec <db container> psql -U brain -d brain -tAc \
  "SELECT DISTINCT client_addr FROM pg_stat_activity WHERE datname = 'brain' AND backend_type = 'client backend'"
```
Expect the database's client addresses to be the pooler's address (and nothing from the app's).

Then sign in to the console and open any screen that reads records. The readiness endpoint
answering 200 is the application's own statement that a query ran through the pooler
(`brain.session.check_reachable` runs a statement, not a connect).

## If it goes wrong

Put `DATABASE_URL` back to `@db:5432/` and `depends_on` back to `db:`, and deploy. The pooler can
be left in place; nothing else connects to it.
