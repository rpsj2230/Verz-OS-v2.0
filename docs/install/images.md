# The images this product pulls, and the day each tag was seen to exist

Every container image the compose files and the Dockerfiles name, other than this product's own
(which `APP_IMAGE` selects), with the tag it is pinned to and the day somebody asked the registry
whether that tag exists. A server pulls these by name on the first start, so a tag that is not
published fails there, on a machine nobody is watching, as `manifest unknown` or `tag not found`
and a service that never starts.

That happened once. The automation canvas's egress proxy was pinned to a tag that Docker Hub
does not publish, and the first server to try it found out at the pull. Nothing in a unit test can
ask a registry, so the register below is what the test can hold the compose files to: **an image
the files pin that this page does not list fails `tests/unit/test_image_pins.py`**, and so does a
row here that nothing pins. Whoever changes a tag looks it up first and writes the day here.

An image pinned by digest (`name@sha256:...`) needs no row: a digest names exactly one manifest,
so a mistyped one cannot be mistaken for a tag that exists.

## How to check a tag

For an image on Docker Hub, which most of these are, the status is 200 when the tag exists and 404
when it does not (put `library/` before the name for an official image such as `postgres`):

```
curl -s -o /dev/null -w "%{http_code}\n" https://hub.docker.com/v2/repositories/ubuntu/squid/tags/6.6-24.04_edge
```

For the others, ask the registry named in the first part of the image's name for the tag's
manifest. The rows below were read on the day written beside each one.

## The register

| Image | Used by | Checked | How |
| --- | --- | --- | --- |
| `activepieces/activepieces:0.39.5` | the automation canvas | 2026-10-13 | Docker Hub tag API |
| `chrislusf/seaweedfs:3.80` | the object store, and the trace ledger's file store | 2026-10-13 | Docker Hub tag API |
| `clickhouse/clickhouse-server:24.12-alpine` | the trace ledger | 2026-10-13 | Docker Hub tag API |
| `cloudflare/cloudflared:2026.9.1` | the optional tunnel | 2026-10-13 | Docker Hub tag API |
| `edoburu/pgbouncer:v1.24.1-p1` | the connection poolers | 2026-10-13 | Docker Hub tag API |
| `ghcr.io/astral-sh/uv:0.12.9` | the application and matcher builds | 2026-10-13 | the registry's manifest API |
| `langfuse/langfuse:3` | the trace ledger | 2026-10-13 | Docker Hub tag API |
| `langfuse/langfuse-worker:3` | the trace ledger | 2026-10-13 | Docker Hub tag API |
| `mcr.microsoft.com/playwright/python:v1.55.0-noble` | the browser runner's build | 2026-10-13 | the registry's manifest API |
| `mcr.microsoft.com/presidio-analyzer:2.2.362` | the personal data detector | 2026-10-13 | the registry's manifest API |
| `mitmproxy/mitmproxy:11.1.3` | the browser sandbox's egress proxy | 2026-10-13 | Docker Hub tag API |
| `node:22-bookworm-slim` | the console build | 2026-10-13 | Docker Hub tag API |
| `openbao/openbao:2.4.1` | the secrets vault | 2026-10-13 | Docker Hub tag API |
| `pgvector/pgvector:pg18` | the database | 2026-10-13 | Docker Hub tag API |
| `postgres:16-alpine` | the automation canvas's own database | 2026-10-13 | Docker Hub tag API |
| `postgres:18-alpine` | the identity provider's database | 2026-10-13 | Docker Hub tag API |
| `python:3.13-slim-bookworm` | the application and matcher builds | 2026-10-13 | Docker Hub tag API |
| `quay.io/keycloak/keycloak:26.0` | the identity provider | 2026-10-13 | the registry's tag API |
| `ubuntu/squid:6.6-24.04_edge` | the automation canvas's egress proxy | 2026-10-13 | Docker Hub tag API |
| `valkey/valkey:8-alpine` | the cache | 2026-10-13 | Docker Hub tag API |

**The squid tag.** `6.10-24.04_edge`, which the canvas's file named until 2026-10-13, is not
published (Docker Hub answers 404): squid 6.10 is published for Ubuntu 24.10 only, and the nearest
build for Ubuntu 24.04 is `6.6-24.04_edge`. The allowlist uses only directives squid has had for many releases (`acl ... dstdomain`,
`http_access`), and it is worth proving rather than assuming: before the first start,
`docker run --rm -v /opt/brain/settings/automation/egress.conf:/etc/squid/squid.conf:ro ubuntu/squid:6.6-24.04_edge squid -k parse`
reads the file under the pinned image and changes nothing. The image stays on Ubuntu 24.04 like
the rest of what runs here. Moving to the 24.10 line is a decision about a release that is not
long-term supported, so it is a change somebody makes on purpose, with a row here.
