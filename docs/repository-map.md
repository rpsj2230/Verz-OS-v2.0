# What is in this repository, and which parts a client install touches

**The repository is the template.** A client install is a release tag plus one environment
file, and that is the whole of it: there is no per-client branch, no per-client fork and no
per-client directory. The reason is not tidiness. A copy diverges the first time a bug is
fixed in one and not the other, and nothing anywhere reports that it has: both copies keep
passing their own tests, and the client on the older one finds out when the bug reaches them.

So every directory below is one of three things, and the third column is the one to read.

| Path | What lives there | Touched by an install? |
| --- | --- | --- |
| `src/` | The application. Every rule, every route, every connector. | Never |
| `migrations/` | Alembic revisions. The database is built from these and from nothing else. | Never |
| `console/` | The web console: Vite, React, vitest. | Never |
| `tests/` | The suite, the invariants, the fixtures and the golden corpus. | Never |
| `docs/` | The work breakdown, the build pages the application serves, and this file. | Never |
| `ops/` | The Keycloak realm, OpenBao policies, runbooks and git hooks. | Never |
| `Dockerfile` | How the image is built. One image for every client. | Never |
| `docker-compose*.yml` | What runs, and what each container may have. Values come from the environment. | Never |
| `pyproject.toml`, `uv.lock` | Dependencies, pinned. | Never |
| `alembic.ini`, `Makefile` | Tooling. | Never |
| `CLAUDE.md`, `README.md` | How to work here, and what this is. | Never |
| `.env.example` | Every variable, with what it is for. **Copied, never edited in place.** | Copied |

**Nothing in the table is edited per client.** The one file an install owns is its own `.env`,
which is a copy of `.env.example` with values filled in, is gitignored, and does not exist in
this repository at all.

## Where a client's own values live, and why none of them are here

`src/brain/install.py` declares every value that belongs to the installation rather than to
the product: the company name, the logo, the accent colour, the sender address, the identity
provider, the model profile, the object store. Each has a meaning written for whoever supplies
it and either a neutral default or a refusal to start.

`brain.install.value_of` is the only place any of them is read. `brain.ops.independence` fails
the build when a second module reads one, and when a literal in `src`, `migrations`, `console`
or the served `docs` pages looks like a client value: an address, an IP, or a URL to a host
this deployment does not declare. Between them, a client value cannot get into the product by
accident, only on purpose and visibly.

**Verz is one deployment of this and nothing more.** Its company name, its colours and its
addresses live in its own `.env` on its own server, exactly like every other client's, and the
sweep is what keeps that true rather than a habit.

## Where to start reading

- `README.md` for the one rule the whole system serves.
- `CLAUDE.md` for the conventions, the traps and the mutation discipline.
- `src/brain/core/` for the invariant's home: principals, entitlements, redaction, field policy.
- `src/brain/gate/` for the request pipeline, in the order a request meets it.
- `docs/needs-rupash.md` for the decisions the owner has not made yet.

## Task ids

M41.3.1, M41.3.2, M41.3.3, M41.3.4
