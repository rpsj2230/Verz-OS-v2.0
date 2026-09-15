# The record matcher's image: the application's code, the matcher's locked packages, one job.
# Built from the repository root: docker build -f matcher/Dockerfile -t brain-matcher .
#
# Separate from ../Dockerfile because of `docs/needs-rupash.md` item 55, Option A: Splink and
# DuckDB never enter the image that answers requests. The dependency set is
# `matcher/pyproject.toml` and `matcher/uv.lock`, and the application is installed into it from
# this checkout rather than copied, so there is one cascade and not two.
#
# Never built. There is no Docker on the machine this was written on. See
# `docker-compose.matcher.yml` for what has run instead. The licence step below accepts numpy's
# licence expression since the owner allowed its three extra licences (needs-rupash item 64).
#
# Task ids: M14.4.1

FROM python:3.13-slim-bookworm AS builder

# The same pinned uv the application image uses, for the same reason: a combined base image
# tag is not published for every release.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

# The application's project files, because the matcher depends on it by path.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY matcher/pyproject.toml matcher/uv.lock ./matcher/

# Locked, without dev dependencies, and not editable: the image holds an installed copy of the
# application, so nothing in it refers back to a checkout that is not there at run time.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project matcher --locked --no-dev --no-editable

# The application's licence rule over this image's larger set. Refuses the build on a licence
# the application would refuse, which is the point of running it here rather than in CI alone.
RUN /opt/venv/bin/python -m brain.resolution.splink_job --check-licences


FROM python:3.13-slim-bookworm AS runtime

# Non-root, no shell, as the application image runs.
RUN groupadd --system --gid 1001 brain \
 && useradd --system --uid 1001 --gid brain --shell /usr/sbin/nologin --no-create-home brain

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=brain:brain /opt/venv /opt/venv

USER brain

# A job, not a server: no port, no health check. It exits 0 having written a suggestions file,
# 3 when it was handed no export, and non-zero on anything else.
CMD ["python", "-m", "brain.resolution.splink_job"]
