# The desktop runner image: the brain package, a virtual display, the accessibility bus and the
# applications an install allows, and nothing that listens. Built beside the application image for
# every release and pushed as the application's own tag with `-desktop` on the end, which is the
# name `brain.browsing.desktop_app.desktop_image_for` derives.
#
#   docker build -f ops/desktop/Dockerfile -t "${APP_IMAGE}-desktop" .
#
# Never built on the machine this was written on, and so never run: it is the first thing
# ops/desktop/REHEARSAL.md would do, and that file does not exist yet because no launcher starts
# this image. The applications an install allows are copied into /opt/desktop-apps by that install's
# own derived image (FROM this one); this image carries none, because which applications are
# allowed is configuration and not a release.
#
# Task ids: M19.8.1

# The base is the one the application's own build already pins and the images page already records
# (docs/install/images.md), which has Python 3.13 and so needs no interpreter of its own. Debian
# bookworm carries girepository 1.0 only, so PyGObject is held below the release that moved to 2.0.
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

ENV DEBIAN_FRONTEND=noninteractive \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/desktop-runner/.venv/bin:$PATH"

# xvfb is the display, at-spi2-core the accessibility bus the application reports its widgets on,
# and the dev packages are only what building PyGObject needs, removed again in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb dbus dbus-x11 at-spi2-core gir1.2-atspi-2.0 libgirepository-1.0-1 \
        gcc pkg-config libgirepository1.0-dev libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv venv --python 3.13 /opt/desktop-runner/.venv \
    && VIRTUAL_ENV=/opt/desktop-runner/.venv uv pip install --no-cache . "pygobject<3.51" pillow \
    && rm -rf /build \
    && apt-get purge -y gcc pkg-config libgirepository1.0-dev libcairo2-dev \
    && apt-get autoremove -y

RUN useradd --create-home --shell /usr/sbin/nologin desktop \
    && mkdir -p /opt/desktop-apps
COPY ops/desktop/desktop_runner.py /opt/desktop-runner/desktop_runner.py

WORKDIR /opt/desktop-runner
USER desktop
ENTRYPOINT ["python"]
CMD ["/opt/desktop-runner/desktop_runner.py"]
