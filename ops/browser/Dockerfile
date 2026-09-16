# The browser runner image: the brain package, Playwright for Python and Chromium, and nothing that
# listens. Built beside the application image for every release and pushed as the application's own
# tag with `-browser` on the end, which is the name `brain.browsing.sandbox.runner_image_for`
# derives, so `APP_IMAGE` selects this image as it selects every other container of the product.
#
#   docker build -f ops/browser/Dockerfile -t "${APP_IMAGE}-browser" .
#
# The Playwright base image and the Playwright package must be the same version, because the
# package finds its browsers in the image by that version. Neither pin has been pulled or built on
# the machine this was written on; ops/browser/REHEARSAL.md is the first build.
#
# Python comes from uv rather than the base image, whose Python is older than the 3.13 the package
# requires.
#
# Task ids: M19.1.2

FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_COMPILE_BYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/opt/brain-runner/.venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv venv --python 3.13 /opt/brain-runner/.venv \
    && VIRTUAL_ENV=/opt/brain-runner/.venv uv pip install --no-cache . playwright==1.55.0 \
    && rm -rf /build

COPY ops/browser/playwright_browser.py /opt/brain-runner/playwright_browser.py

WORKDIR /opt/brain-runner
USER pwuser
ENTRYPOINT ["python"]
CMD ["/opt/brain-runner/playwright_browser.py"]
