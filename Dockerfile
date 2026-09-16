# Multi-stage. The builder carries uv and the toolchain; the runtime carries neither.
# Task ids: M0.4, M38.1.2

FROM python:3.13-slim-bookworm AS builder

# uv is copied in as a pinned binary rather than taken from a combined base image.
# The `<uv-version>-python<x.y>-<distro>` tags are not published for every uv release
# (0.12.9 has none), so depending on one is a build that breaks on an upstream tagging
# decision. This pins both uv and Python exactly and depends on neither.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, as their own layer: application code changes on every commit,
# the lock file does not, so this layer survives most rebuilds.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# The API document the console types itself against, exported from the application object at
# this commit. It is here rather than in the console stage because producing it needs the
# Python environment two layers up and no server: `create_app` mounts routes and touches
# nothing, and `FastAPI.openapi()` builds the document from what is mounted.
#
# The generated types are deliberately not committed (see `console/.gitignore`), so an image
# build that skipped this step would compile the console against whatever stale copy happened
# to be in the build context, or fail to resolve `src/api/schema.ts` at all.
COPY console ./console
RUN uv run --no-sync python console/scripts/export-openapi.py


# The console, built with the Node major `.github/workflows/ci.yml` runs its type check,
# boundary check, tests and build on. A second Node here would mean the bundle that ships is
# produced by a toolchain nothing in CI ever exercised.
#
# This whole stage is discarded. Only `dist` is copied forward, so neither Node nor
# `node_modules` reaches the runtime image, and the console costs it the size of the bundle.
FROM node:22-bookworm-slim AS console

WORKDIR /console

# The lockfile's own layer, for the reason the Python dependencies have one: it changes far
# less often than the source. `npm ci` rather than `npm install`, so the build installs what
# the lockfile says and cannot quietly resolve a newer version of anything.
COPY console/package.json console/package-lock.json ./
RUN npm ci

COPY console/ ./
COPY --from=builder /app/console/src/api/generated/openapi.internal.json ./src/api/generated/
RUN npm run api:types && npm run build


FROM python:3.13-slim-bookworm AS runtime

# The image runs as a non-root user with no shell. A container that cannot open a shell
# is one fewer thing to reason about if an injected instruction ever reaches a tool call.
RUN groupadd --system --gid 1001 brain \
 && useradd --system --uid 1001 --gid brain --shell /usr/sbin/nologin --no-create-home brain

# The image carries its own identity rather than being told at runtime. Coolify resolves
# ${VAR:-default} at save time and bakes the literal into its stored compose, so a runtime
# variable could not be overridden by the deploy at all: /health/ready reported "unknown"
# while the status page reported the truth. An image knowing what it is is also simply
# more correct: the answer cannot depend on how it was started.
ARG COMMIT_SHA=unknown
ENV BRAIN_COMMIT_SHA=${COMMIT_SHA}

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder --chown=brain:brain /app/.venv /app/.venv
COPY --from=builder --chown=brain:brain /app/src /app/src
# The migrations and their config. Without these the migrate container starts, finds no
# alembic.ini, and exits with "No 'script_location' key found" - which looks like a
# configuration mistake rather than a missing file.
# What this build contains, written by CI immediately before the build. The glob is what
# makes a local `docker build` work without one: COPY fails on a missing literal path and
# succeeds with zero matches on a pattern. A missing manifest is not an error - the app
# treats it as "running from a checkout" - and making it one would break the build for the
# only person able to fix it.
COPY --chown=brain:brain RELEASE.jso[n] /app/
COPY --chown=brain:brain alembic.ini /app/alembic.ini
COPY --chown=brain:brain migrations /app/migrations
# The tracker, architecture and the status computed from git at build time. Baking the
# status in means the page can never disagree with the binary serving it.
COPY --chown=brain:brain docs /app/docs
# The realm, because the identity stack has to be deployable without a checkout.
#
# `docker-compose.keycloak.yml` used to bind-mount this from `./ops/keycloak/`, which works
# when the compose file sits in a git working tree. This Coolify installation does not do
# that: its resources are stored compose files written out at deploy time, and the directory
# they land in holds a `.env`, a `README.md` and the compose, with no repository anywhere
# near it. Measured on the server rather than assumed. A relative bind mount there resolves
# to a path that does not exist, and the realm job would have failed at first deploy with a
# message about a missing file rather than about a missing checkout.
#
# In the image instead, where the transform that reads it already lives. One file rather than
# the whole of `ops/`, because the rest of that directory is runbooks and host scripts that
# have no business in a container that serves requests.
COPY --chown=brain:brain ops/keycloak/realm-export.json /app/ops/keycloak/realm-export.json
# The built console, which this application serves at the root of the install's web address.
# `brain.console_static` looks for it here and serves nothing at all when it is absent, so a
# local `docker build` that dropped this line would produce an image whose only symptom is a
# build status page where the console should be. See that module for why one image rather
# than a second container behind the same proxy.
COPY --from=console --chown=brain:brain /console/dist /app/console/dist

USER brain
EXPOSE 8000

# Readiness, not liveness. Coolify must not route traffic to a container that is up but
# cannot reach the database, the cache or the secret store: a half-connected instance
# answers questions wrongly rather than not at all.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status==200 else 1)"

# Started through a launcher that reads the container's own cgroup limits. os.cpu_count()
# reports the host's cores, not the container's share, so a 1 GiB container on a
# thirty-two-core host would otherwise start sixty-five workers, each with a pool.
CMD ["python", "-m", "brain.serve"]
