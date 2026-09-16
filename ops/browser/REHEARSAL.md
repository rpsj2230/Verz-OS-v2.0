# Rehearsing the browser sandbox on a server that can run it

Everything in `brain.browsing` that decides something is tested in the repository. Nothing that
needs Docker, gVisor or a browser has run, because the machine it was written on has none of them.
This is the rehearsal that turns the open M19 runner leaves into claims. Run it on a staging
server, in order, and record each result against the leaf it proves. Nothing here needs any value
belonging to a company: the target in step 5 is any public page the operator chooses.

## 1. gVisor is installed and Docker knows it as `runsc`

Install gVisor from its own documentation for the host's distribution, then register it and
restart Docker:

```
sudo runsc install
sudo systemctl restart docker
docker info --format '{{json .Runtimes}}'          # must list "runsc"
docker run --rm --runtime=runsc alpine dmesg | head -3   # must mention gVisor
```

If `runsc` is missing, the launcher's health check fails and says so. That is the intended result on
a host without it.

## 2. The two images exist and agree with what the code expects

```
docker build -f ops/browser/Dockerfile -t "${APP_IMAGE}-browser" .
docker run --rm --runtime=runsc --entrypoint python "${APP_IMAGE}-browser" \
  -c "import playwright, brain.browsing.runner; print('ok')"
docker pull mitmproxy/mitmproxy:11.1.3
docker run --rm --entrypoint id mitmproxy/mitmproxy:11.1.3 mitmproxy   # the user must exist
```

Unverified until this step: that `mcr.microsoft.com/playwright/python:v1.55.0-noble` exists and
matches `playwright==1.55.0`, that the mitmproxy tag exists, and that its image has a `mitmproxy`
user whose home is `/home/mitmproxy`. Any change here is a change to `brain.browsing.sandbox` and
`ops/browser/Dockerfile`, with their tests.

## 3. The launcher starts healthy

Compose the overlay after the profile's own files, as `ops/update/update.sh` composes the others:

```
docker compose <the profile's -f files> -f docker-compose.browser.yml up -d browser-launcher brain-worker
docker inspect --format '{{.State.Health.Status}}' <the browser-launcher container>   # healthy
docker network ls --filter name=brain-browser-egress                                 # created at start
```

## 4. A start line that names a gap is refused before anything is created

From inside the worker container, send a start message with an origin that is not an origin
(`https://example.org/path`). The connection closes and `docker ps -a --filter label=brain.browser.run`
stays empty.

## 5. One read-only run, by hand

From inside the worker container, build an envelope for a target with one read surface on the
chosen public page, send `brain.browsing.wire.start_fields(envelope, target, approved=False)` as the
first line to `browser-launcher:7300`, then one `act` line opening that surface. While the run is
open, from the host:

| Leaf | Check | Expected |
| --- | --- | --- |
| M19.1.1 | `docker inspect -f '{{.HostConfig.Runtime}}'` on both run containers | `runsc` |
| M19.1.1 | the two containers' names and labels | named and labelled with the run id |
| M19.1.5 | `docker exec <runner> touch /probe` | refused: read-only file system |
| M19.1.5 | `docker exec <runner> touch /tmp/probe` | allowed |
| M19.1.6 | `docker network inspect brain-browser-<run>` | `Internal: true`, two members |
| M19.1.6 | from the runner, a direct connection to any address on 443 | fails: no route |
| M19.3.5 | from the runner, a request through its proxy (host `egress`, port 8080) to the allowed origin | answered |
| M19.3.5 | the same to any other host, or with a Host header naming another host | refused |
| M19.6.4 | `docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.HostConfig.PidsLimit}}'` | 1342177280, 1000000000, 512 |
| M19.1.2, M19.1.3 | the lines returned on the connection | a `snapshot` with named nodes, a masked `frame`, a `record` |

Then close the connection. Within seconds `docker ps -a --filter label=brain.browser.run` and
`docker network ls --filter label=brain.browser.run` must show nothing but the shared egress
network. That is M19.1.5's "destroyed at run end" and M19.1.1's "per run".

## 6. The things most likely to need a change

Each of these is written from documentation and has not been observed:

- Chromium started with `chromium_sandbox=False`. Try `True` first under gVisor and keep it if it
  launches; record which.
- mitmproxy's hook names (`http_connect`, `requestheaders`, `tcp_start`, `udp_start`,
  `dns_request`), `flow.kill()`, and `request.host_header` as `brain.browsing.egress_addon` uses them.
- `mitmdump -s` loading the addon from the container's `/tmp`, which is mounted `noexec`.
- The runner resolving `egress` through Docker's embedded DNS on an internal network under `runsc`.
- The Engine API at `v1.44` (Docker 25 or later) and the attach upgrade answering `101`.
- `AutoRemove` removing the runner while the launcher is still attached after it exits.
- DevTools `Accessibility.getFullAXTree` returning `backendDOMNodeId` on the nodes a page acts on,
  and `DOM.getBoxModel` returning a content quad for them.
- A memory-hungry page against the 1280 MiB runner cap: the tab should crash or the container be
  killed, and the run should end with a reason on its last line.

## 7. What this rehearsal cannot close

M19.6.6, the full session recording, needs the worker side of the channel, which is not built: the
transcript is recorded by the worker, and nothing in the worker opens a run yet. Rehearse
`brain.browsing.recording` once that exists.
