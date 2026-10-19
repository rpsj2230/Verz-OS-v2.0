# The model server's image: this repository's `inference_server` package, the libraries of every part,
# and nothing of the application. Built from the repository root:
#
#     docker build -f modelserver/Dockerfile -t brain-modelserver .
#
# **It has never been built.** There is no Docker on the machine this was written on, so nothing
# below has run, and the package list is not locked (see `requirements.txt`). Every claim in this file
# is a claim about what the build should do, and the first build on a machine with Docker is the
# first test of it. `docs/wbs/progress.js` says which leaves wait on that.
#
# One image carries every part's libraries and the supervisor loads only the parts an install chose
# (`INSTALL_MODEL_PARTS`), so what an install pays for in memory is what it chose, and what it pays
# for in disk is this image once. Rejected: an image per choice of parts, which would be a naming
# convention for the release step to get right on every server and a registry of combinations to
# publish; disk is cheap, and the memory the image is unable to cost is the point of the design.
#
# The application is not in it, which is the permission boundary as a fact of the image: a process
# that holds a client's document has no code to reach the application's database with. The package
# imports nothing from `brain`, and `tests/unit/test_inference_server.py` holds it to that.
#
# Task ids: M7.2.1, M7.3.3

FROM python:3.13-slim-bookworm AS builder

# The same pinned uv the application image uses, for the same reason: a combined base image tag is
# not published for every release.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

# llama.cpp is compiled here and not in the runtime stage, which carries no compiler.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN uv venv /opt/venv

WORKDIR /build
COPY modelserver/requirements.txt ./requirements.txt
# torch from its CPU index: the default wheel carries the CUDA libraries, which are gigabytes of disk
# this server never uses and a CPU host cannot. Everything else from the default index.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --index-strategy unsafe-best-match \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt


FROM python:3.13-slim-bookworm AS runtime

# Tesseract and its English data for the scanned-page part, and a JRE for the general reader. Both are
# programs the parts run, so they are in the image whether or not an install chose the part: neither
# holds memory until the part's process starts it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng default-jre-headless \
 && rm -rf /var/lib/apt/lists/*

# Non-root, no shell, as the application image runs.
RUN groupadd --system --gid 1001 brain \
 && useradd --system --uid 1001 --gid brain --shell /usr/sbin/nologin --no-create-home brain

# The weights directory exists and is owned by the user the server runs as, so the named volume
# mounted over it takes that owner when it is first made: a new volume takes its owner from the
# directory it is mounted over, and a root-owned one is a fetch that cannot write (the same trap
# `Dockerfile` records for `/out`).
RUN mkdir /models && chown brain:brain /models

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1

COPY --from=builder --chown=brain:brain /opt/venv /opt/venv
COPY --chown=brain:brain src/inference_server /app/inference_server

WORKDIR /app
USER brain
EXPOSE 8080

# The compose file's health check is the readiness check. A part is loaded when work arrives and not
# before, so this never holds a model.
CMD ["python", "-m", "inference_server"]
