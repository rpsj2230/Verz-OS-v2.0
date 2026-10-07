## What

PgBouncer's `default_pool_size` is per login and database. The application reaches the transaction pooler as `brain_app` and as the owner, so `DEFAULT_POOL_SIZE` 20 could hold forty server connections while `brain.ops.connections` counts twenty. This is follow-up (b) from #374.

- **Product half:** every compose file's `pgbouncer` now sets `MAX_DB_CONNECTIONS` equal to its pool. The edoburu image writes that as `max_db_connections`, which caps the database across logins. `docker-compose.full.yml` is regenerated with `python -m brain.ops.compose`.
- **The install's half:** Coolify's stored compose is never edited by a release, so an older install stays uncapped. `docs/install/operations.md` now names the limit and why it exists, gives the exact line to add beside `DEFAULT_POOL_SIZE`, and says to redeploy once.

## Proof

- Three new tests:
  - the cap equals the pool in all four compose files;
  - it equals the budget's `pgbouncer` row;
  - the page's section gives the line, with the figure the product's compose file carries.
- 1732 passed: test_install_docs, test_connections, test_session_pool, test_pooler_logins, test_compose, test_wiring and tests/invariants.
- ruff, format and the client_independence and house_style sweeps all exit 0.

Mutation (1 of 1 caught): `MAX_DB_CONNECTIONS` set to 40 in docker-compose.yml is caught by all three tests.

## Not done

- **Applying the line on the owner's staging install** is an operator step; nothing here touches a server.
- **Follow-up (a)** comes separately: /health/ready probing the engine each process uses.

Reused: `brain.ops.compose` (the generator), `brain.ops.connections.CLIENTS`, and the edoburu image's own `MAX_DB_CONNECTIONS` setting, which the session pooler already uses.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
