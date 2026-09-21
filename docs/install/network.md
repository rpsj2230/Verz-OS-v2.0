# Domain, DNS, reverse proxy, TLS and firewall

**Nothing in this deployment publishes a port.** Every service uses `expose`, which opens a
port on the compose network only, and no service in any profile uses `ports`, which is what
opens one on the machine. So a server that has run the install to completion is answering on
nothing at all from outside its own Docker network.

That is correct for the database, the cache and the pooler. It means the reverse proxy holding
your certificate is **part of the install rather than an optional extra**, and no compose file
in this product declares one. You supply it, or, on `lite`, you use the Cloudflare Tunnel
option further down this page, which takes its place and opens no inbound port at all.

## The one number this deployment does not write down

The application listens on **8000**, and it declares neither `ports` nor `expose`, so that
number appears in exactly two places: inside the application container's own healthcheck
command, and inside the installer's readiness step. There is no `expose: "8000"` to read it off.

Point your proxy at the application service on port 8000, over HTTP, inside the compose
network. Terminate TLS at the proxy.

This is worth saying plainly rather than leaving somebody to find: a port that is documented
only inside a healthcheck is a port that changes when somebody edits a healthcheck.

## Addresses you need

**One for the console**, which is what your staff open. It is also what
`INSTALL_OIDC_REDIRECT_URIS` has to name, and the console's callback path is `/auth/callback`.
The wizard derives the redirect URI from the web address you give it rather than asking for it
separately, because a redirect URI typed by hand is the one value whose being wrong is an open
redirect.

**A second one for the identity provider**, on `standard` and `full`. It is a separate address
because the browser is genuinely redirected to it during sign-in, and it is set with
`KEYCLOAK_HOSTNAME`. Sharing one address between the two does not work.

**A third and a fourth**, on `full` only, for the automation canvas (`AUTOMATION_PUBLIC_URL`)
and the trace ledger's own console (`LANGFUSE_PUBLIC_URL`).

Point each of them at the server with an A record, or an AAAA record if the server has an IPv6
address. Nothing here needs a wildcard.

## Where the console comes from, and how your staff reach it

**The console is inside the application's own image and is served by it.** There is no second
container, no static host and no bucket, and nothing for you to upload. The image the deploy
pulls carries the built console, and the application serves it at the **root of the console
address** you pointed at the app service on port 8000. So a proxy configured as the section
above describes, sending everything for that address to the application, is the whole of it:

- `https://<your console address>/` is the console.
- `https://<your console address>/first-run` is the install wizard, which is where the
  installer sends you and the one address a fresh install cannot work without.
- `https://<your console address>/auth/callback` is where sign-in returns to. This is the
  value `INSTALL_OIDC_REDIRECT_URIS` has to hold, and the wizard derives it for you.
- `https://<your console address>/api/v1/...` is the API, on the same address on purpose.
- `https://<your console address>/build` is the build status page, which used to be at the
  root and moved here when the console took it. Every link on it already pointed here.

**Do not route parts of that address to different places.** The console signs in with PKCE and
keeps its token in memory, and it calls the API on its own origin: that is why no CORS policy
has to be configured for a normal install and why `BRAIN_CORS_ORIGINS` is empty. Splitting
`/api` off onto a second host makes every console request cross-origin and needs both a CORS
allow list here and a web origin added to the realm, neither of which fails loudly on its own.

**The console learns which installation it belongs to at runtime, not at build time.** It reads
`/api/console.js`, which the application serves from `INSTALL_OIDC_ISSUER`,
`INSTALL_OIDC_CLIENT_ID` and the API's own prefix. Nothing about your company is compiled into
the JavaScript, which is what makes one published image installable by every client. A proxy
that does not pass `/api/` through therefore breaks sign-in with a message on the screen saying
so, rather than silently.

**What you must add to Keycloak yourself.** The realm import registers what
`INSTALL_OIDC_REDIRECT_URIS` names, so on a standard install you set that value and the import
does the rest. If you are pointing this at a Keycloak you already run, add to the
`brain-console` client:

- a valid redirect URI of `https://<your console address>/auth/callback`,
- a valid post-logout redirect URI of `https://<your console address>/signed-out`,
- and a web origin of `https://<your console address>`.

All three are exact matches. A trailing slash, `http` instead of `https`, or the address of the
identity provider instead of the console will each produce a Keycloak error page that names
none of the settings involved.

## TLS

Terminate it at the proxy, on 443, and redirect port 80 to it.

**The issuer address has to be `https`.** `INSTALL_OIDC_ISSUER` is the one setting in this
product with no safe default at all, because an issuer guessed wrong is a sign-in page that
completes against an identity provider you do not control, and an empty string is a perfectly
valid string. The system refuses to start without it rather than guessing. An issuer on plain
HTTP puts the whole sign-in exchange, including the authorisation code, in clear on the wire.

**The redirect URIs have to match the console's address exactly.** Wrong here is a sign-in that
completes and then sends the person to a page you do not own.

Certificates from an automatic issuer are fine and are what most installs will use. What
matters is that the proxy renews them without anybody remembering to.

## Every port this deployment opens

Every service below opens a port on the compose network. **None of them should be reachable
from outside it except the three that a browser talks to**, and those three reach it through
your proxy rather than through a published port.

The table is checked against the compose files on every test run: a service that gains a port
and has no row here fails `tests/unit/test_install_docs.py`, because a port nobody wrote a row
for is a port nobody decided about. The third column is prose.

<!-- checked: every port this deployment opens -->

| Service | Port | Who may reach it |
| --- | --- | --- |
| `activepieces` | `80` | Staff, through your proxy, on the automation canvas's own address. `full` only. |
| `automation-db` | `5432` | The automation canvas alone. It is a separate database from yours, deliberately: the canvas runs work somebody assembled in a browser. |
| `automation-egress` | `3128` | The automation canvas alone. This is the proxy that stops an assembled flow reaching anything it was not allowed to, so it is the one container here whose reachability is a security control rather than a convenience. |
| `cache` | `6379` | The application alone. Never from outside. |
| `db` | `5432` | The two poolers. Never from outside, and never from the application or the workers directly. |
| `inference-server` | `8080` | The application alone. It is handed the text of documents that have already passed the permission layer, so anything that can reach it can ask it to read them. `standard` and `full`. |
| `keycloak` | `8080` | Staff browsers, through your proxy, on the identity provider's own address. `standard` and `full`. |
| `langfuse-cache` | `6379` | The trace ledger alone. `full` only. |
| `langfuse-clickhouse` | `8123` | The trace ledger alone. `full` only. |
| `langfuse-web` | `3000` | Whoever operates this install, through your proxy, on the trace ledger's own address. Not your staff. `full` only. |
| `pgbouncer` | `5432` | The application alone. Everything the application does to the database goes through here. |
| `pgbouncer-session` | `5432` | The two workers alone. It is in session mode, so a worker's `LISTEN` keeps its connection, and it caps what both workers together may hold against the database. `standard` and `full`. |
| `presidio-analyzer` | `3000` | The application alone, on the internal `pii` network, which has no route off the server. It is handed text before that text is scrubbed, so never put it behind your proxy. `standard` and `full`. |
| `seaweedfs` | `8333` | The application, the workers and, on `full`, the trace ledger. `standard` and `full`. |

The application itself is deliberately not in that table, because it opens no declared port at
all. See the section above.

## Firewall

Two rules and one trap.

**Allow 80 and 443 to the proxy, and your own administrative access, and nothing else.** The
services above are on a Docker network and are not published, so there is nothing else to
allow. With the Cloudflare Tunnel option above, allow only your own administrative access: the
tunnel needs no inbound rule.

**The trap: a host firewall does not block a port Docker published.** If you ever add a
`ports:` entry to a compose file, or run any other container that publishes a port, `ufw deny`
on that port does nothing at all. Docker publishes to `0.0.0.0` and inserts its own iptables
rules **ahead of** the host firewall's chain, so the packet is accepted before your rule is ever
consulted. The rule has to go in the `DOCKER-USER` chain, which Docker leaves alone for exactly
this purpose:

```
iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport <port> -j DROP
```

This is not hypothetical. It was found on a real server here, where an administrative panel was
answering plain HTTP on a public address with a `ufw deny` rule in place that had never once
seen a packet.

**And that rule does not survive a reboot.** Docker flushes and rebuilds its chains when it
starts, so anything you insert by hand is gone. Persist it with a small unit ordered
`After=docker.service`, or the thing you are constraining wipes the constraint on every boot.
`ops/vps/brain-firewall.service` in this repository is one worked example of that unit.

## Administrative consoles

**The decision: the administrative consoles stay on public addresses, and every one of them has
a second factor and an IP allowlist.** Both, on every install, for as long as the console answers
from the internet. One without the other is not a lighter version of this decision; it is a
sign-in page that fails on the day its single protection does.

These are the consoles that control the server rather than the product. Reaching any of them
hands over every container, every account or every secret. The console your staff use, and the
identity provider's sign-in page they are sent to, are not on this list: those have to answer the
people who use them, and they are protected by the sign-in itself.

<!-- checked: the administrative consoles -->

| Console | What reaching it hands over | Second factor | IP allowlist | In this repository |
| --- | --- | --- | --- | --- |
| `deployment panel` | Every container, database and environment variable on the host | The panel's own two-factor sign-in, switched on for every account on it | The `admin-allowlist` middleware, passed first by every router in `ops/vps/traefik-coolify-panel.yaml` | The allowlist, in that template, with `<admin-source-range>` to replace. The second factor is a setting on each account inside the panel, and no file can hold it |
| `identity provider admin console` | Every account, every role and every sign-in policy | A one-time password required of every administrator of the `master` realm | The same middleware, on a router matching only the admin paths on the identity provider's address, described below | Nothing. `ops/keycloak/realm-export.json` asks every new account in the product's own realm to set up a second factor, and the admin console signs in against `master`, which no file here configures |
| `secrets vault interface` | Every secret the system holds | Required on every sign-in method the interface accepts, if it is ever switched on | Required on its router, if it is ever switched on | Not served. `ops/openbao/compose.yml` sets `ui = false` and the vault publishes no port, so there is no page to protect until somebody switches it on |
| `trace ledger dashboard` | Every trace, which is every question and answer after masking | Sign-in through the identity provider, whose one-time password is the second factor, with the dashboard's own password sign-in switched off | The same middleware, on the router for the address `LANGFUSE_PUBLIC_URL` names | Nothing. `docker-compose.langfuse.yml` configures no single sign-on, so as shipped the dashboard signs in with a password alone |

### How the allowlist is configured

It is a middleware on the reverse proxy, attached to each console's router **ahead of every other
middleware**, so nothing on that route answers an address it refuses. On Traefik it reads:

```yaml
http:
  middlewares:
    admin-allowlist:
      ipAllowList:
        sourceRange:
          - "<admin-source-range>"
```

`<admin-source-range>` is the addresses your administrators sign in from, in CIDR form, one entry
per range. `ops/vps/traefik-coolify-panel.yaml` carries this middleware for the deployment panel,
and it is the worked example for the other three.

- **The placeholder refuses to route, on purpose.** Until it is replaced, Traefik rejects the
  middleware and every router naming it, so the panel answers nobody rather than everybody.
- **The identity provider shares its address with your staff's sign-in**, so its allowlist goes on
  a router for the admin paths and never on the whole host. Match the host together with a path
  prefix of `/admin` or of `/realms/master`, give that rule a higher priority than the host's own
  router, and leave the host's own router without the allowlist. An allowlist on the whole host
  locks every member of staff out of signing in.
- **Behind a CDN or a second proxy**, the address Traefik sees is that proxy's rather than the
  person's, and an allowlist of it admits everybody. Set the middleware's `ipStrategy` so it reads
  the forwarded address, and only from that proxy.
- **Traefik 2 names the middleware `ipWhiteList`.** The `sourceRange` key under it is the same.
- **The panel's own port stays closed.** The allowlist guards the route; it guards nothing if the
  panel also answers on its published port, which is what the `DOCKER-USER` rule above is for.

### Second factor

The deployment panel's is a setting on each account inside the panel, and switching it on is its
own step in the go-live work. The identity provider's is a required action on each administrator
of the `master` realm, which is a different realm from the one this product imports. The trace
ledger dashboard has no second factor of its own to switch on, which is why it signs in through
the identity provider. The vault's interface is off; if it is ever switched on, it takes a second
factor on every sign-in method before it takes a router.

### What was rejected

<!-- checked: the options rejected for the consoles -->

| Option | Why it was not taken |
| --- | --- |
| `an SSH tunnel on every install` | The safest of the three: every console listens on the server's loopback address only, and an administrator reaches one with a single `ssh -L` command, so a leaked password or an unpatched sign-in page is reachable by nobody without the server's key. Not taken because an IT team with no SSH habit could not administer its own server, and a control people cannot use is one they work around. What this decision accepts in exchange is that the sign-in pages are on the internet and both protections above have to be right on every install for as long as it runs. |
| `a choice made per client` | The product would have to document and test both arrangements, and the weaker one is the one somebody picks under time pressure. |

## Cloudflare Tunnel instead of opening 80 and 443

An option, and not the default. Instead of a reverse proxy answering on 80 and 443, one small
container on the server dials out to Cloudflare and carries your staff's requests back over
that connection. The server then needs **no inbound port at all**, apart from whatever you
administer it through.

Read these three things before choosing it.

**Cloudflare reads every request.** Cloudflare holds the certificate and decrypts each request
at its edge before the tunnel carries it on, so every question your staff ask and every answer
this system gives passes through Cloudflare in the clear. With a reverse proxy on your own
server, nothing outside that server does. If your company's data may not pass through a third
party, use the reverse proxy described above instead.

**On `standard` and `full` it takes a second file, and it does not close the panel's ports.**
Those profiles run the identity provider, which is not on the network the tunnel joins, so
`docker-compose.tunnel.identity.yml` is composed as well and puts the tunnel and the identity
provider on a private network of their own. Those profiles also need the deployment panel,
and if the panel runs its own proxy on this server, that proxy goes on publishing 80 and 443
whatever the tunnel does. "No inbound port" is then true of this product's containers and not
of the server.

**Updates keep it.** The release carries both files, and the update and rollback scripts
compose them in whenever `/opt/brain/.env` holds the tunnel token. See
[update-and-rollback.md](update-and-rollback.md).

### What you need

- The install finished, so `/opt/brain/.env` and the compose files are on the server.
- A domain whose DNS Cloudflare manages. The console's address has to be a name in it.
- A Cloudflare account that can create tunnels, which live in its Zero Trust dashboard.
- SSH access to the server, so closing 80 and 443 does not close you out.

### Steps

1. **Create the tunnel.** In the Cloudflare dashboard, open Zero Trust, then Networks, then
   Tunnels, and create a tunnel of the `Cloudflared` type. Name it after the server. Cloudflare
   renames these menus from time to time; what you are looking for is a tunnel whose connector
   is installed with Docker.
2. **Copy the token.** Choose Docker as the environment. The page shows a command ending in
   `--token` followed by one long string. Copy that string only. Do not run the command: this
   install starts the container itself, in step 6.
3. **Put the token in the install's environment file.** On the server, add one line to
   `/opt/brain/.env`, reading `CLOUDFLARE_TUNNEL_TOKEN=` followed by the string from step 2.
   Anybody holding that string can connect a machine as your tunnel, so it is a password: it
   lives in that file and nowhere else.
4. **Point the console's address at the application.** In the dashboard, on the tunnel's public
   hostname page, add one hostname. The subdomain and domain are the console's address, the one
   `INSTALL_OIDC_REDIRECT_URIS` names. The service type is `HTTP` and the URL is `app:8000`,
   which is the application service on the compose network and the port from the section above.
   Cloudflare creates the DNS record for that address itself, so delete any A or AAAA record
   you made for it earlier.
5. **On `standard` and `full`, point the sign-in address at the identity provider.** Add a
   second public hostname on the same tunnel. The subdomain and domain are the address
   `KEYCLOAK_HOSTNAME` names in `/opt/brain/.env`, the service type is `HTTP` and the URL is
   `keycloak:8080`. Skip this step on `lite`, which has no identity provider of its own.
6. **Start it.** The release put `docker-compose.tunnel.yml` and
   `docker-compose.tunnel.identity.yml` in `/opt/brain/` already, beside the other compose
   files. On `lite`:

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.tunnel.yml up -d
   ```

   On `standard`, the profile's own files, then both tunnel files:

   ```
   docker compose -f /opt/brain/docker-compose.yml -f /opt/brain/docker-compose.worker.yml -f /opt/brain/docker-compose.parse-worker.yml -f /opt/brain/docker-compose.objectstore.yml -f /opt/brain/docker-compose.keycloak.yml -f /opt/brain/docker-compose.inference.yml -f /opt/brain/docker-compose.tunnel.yml -f /opt/brain/docker-compose.tunnel.identity.yml up -d
   ```

   On `full`, the same two tunnel files after the `full` profile's own files, which the line
   beginning `full)` in `/opt/brain/ops/update/update.sh` lists. If `CLOUDFLARE_TUNNEL_TOKEN` is not set, compose
   refuses to start and names it. The tunnel container waits until the application reports
   ready.
7. **Check it connected.** The tunnel's status in the dashboard reads healthy, and this shows
   it registering its connections (on `standard` and `full`, with the same files as step 6):

   ```
   docker compose -f /opt/brain/docker-compose.lite.yml -f /opt/brain/docker-compose.tunnel.yml logs cloudflared
   ```

   Then open the console's address in a browser.
8. **Close 80 and 443.** Only once the console answers through the tunnel. Allow SSH first, or
   enabling the firewall closes your own session:

   ```
   sudo ufw allow OpenSSH
   sudo ufw delete allow 80/tcp
   sudo ufw delete allow 443/tcp
   sudo ufw default deny incoming
   sudo ufw enable
   ```

   A `delete` for a rule you never added says so and changes nothing. The tunnel needs
   **outbound** port 7844, over TCP and UDP, to reach Cloudflare. `ufw` allows outbound traffic
   by default; if your server or your network restricts outbound traffic, allow 7844.

### Confirm there is no inbound port

Three checks, in this order, because each one misses something the next one catches.

1. **Nothing on the server is listening on 80 or 443.**

   ```
   sudo ss -tlnp
   sudo ss -ulnp
   ```

   No line may show `0.0.0.0:80`, `0.0.0.0:443`, `[::]:80`, `[::]:443`, `*:80` or `*:443`. The
   SSH port is expected.
2. **No container publishes a port.** A firewall cannot tell you this, for the reason in the
   firewall section below:

   ```
   docker ps --format '{{.Names}}  {{.Ports}}'
   ```

   No line may contain `0.0.0.0:` or `[::]:`. An entry such as `5432/tcp` with no address in
   front of it is a port on the compose network and is expected. If the deployment panel runs
   its own proxy on this server, that proxy publishes 80 and 443 itself, and the tunnel does not
   change it.
3. **Nothing answers from outside.** From a machine on a different network, with the server's
   public address from your hosting provider's control panel:

   ```
   nc -vz -w 5 <server address> 443
   nc -vz -w 5 <server address> 80
   ```

   Both must time out or be refused.

### After an update or a rollback

Nothing to do. Both scripts read `/opt/brain/.env`, and when it holds a value for
`CLOUDFLARE_TUNNEL_TOKEN` they compose the tunnel's files onto every command they run, from the
release they have just unpacked. Each prints a line saying so near its start; if that line is
missing, the token line is missing or empty.

To stop using the tunnel, remove its container first, with the files from step 6 and
`rm -sf cloudflared` in place of `up -d`, and only then delete the token line. Deleted first,
the scripts stop composing the tunnel and the container that already holds the token keeps
running.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The tunnel overlay publishes nothing, runs a release tag, requires its token, keeps it off the command line, joins only `default` and waits for the application | `test_tunnel_option.py`, against `docker-compose.tunnel.yml` |
| That every profile with the tunnel composed on top still publishes no port | the same test |
| That the tunnel section names both overlays, the variable, the application's and the identity provider's addresses, the outbound port and the listening check | the same test, reading the section alone |
| That the second overlay only puts the tunnel and the identity provider on one internal, unnamed network, is composed exactly on the profiles that run the identity provider, and that composed together the tunnel shares a network with the application and the identity provider and with nothing else | the same test, against `docker-compose.tunnel.identity.yml` and every profile's files |
| That the release archive carries both overlays, and that the update and rollback scripts compose them exactly when the environment file holds a value for the token | the same test, and `test_deployment_release.py`, which runs the scripts' opening against an environment file |
| **That compose merges a service's networks across files as a union** | **nobody here. Read from compose's own merge rules, never run.** |
| **Whether the tunnel connects, and what its public hostname points at** | **nobody. Both are settings in the client's own Cloudflare account.** |
| Every service that opens a port has a row, and no row names one that does not | `test_install_docs.py`, against the compose files |
| The port numbers | the same test |
| That nothing publishes a port to the host | `test_deployment_requirements.py` |
| The four administrative consoles, in both directions, with a second factor and an allowlist stated for each, and the two rejected options with their reasons | `test_install_consoles.py` |
| That the panel's proxy template defines the allowlist and every router passes it first | the same test, against `ops/vps/traefik-coolify-panel.yaml` |
| That the vault's interface is not served, exactly when this page says so | the same test, against `ops/openbao/compose.yml` |
| **Whether each console's second factor is switched on** | **nobody, and nothing can. It is a setting inside each console on each server.** |
| **Which addresses you need, and what to point them at** | **nobody. Prose, kept true by hand.** |
| **Everything else about TLS and the firewall** | **nobody. Prose, kept true by hand.** |

## What has never been done

**No reverse proxy has ever been configured against this deployment from these instructions.**
This product ships no proxy configuration, and the only proxy work anybody here has done was
against one particular server for one particular panel. So the port numbers and the
requirements above are read out of the deployment and are true; the sequence as a whole has
never been walked by anybody starting from a bare machine.

**No allowlist from this page has been applied to a server from this repository.** The
`admin-allowlist` middleware was added to the panel's proxy template when the console decision
was written down, and a template is not a route.

**No tunnel has ever been started from `docker-compose.tunnel.yml`, and no sign-in has ever
been carried through `docker-compose.tunnel.identity.yml`.** The image tag and that image's
entrypoint and user were read from the registry on 2026-09-15, and nothing else about the
option has been run: not the token, not either public hostname, not the three checks, and not
whether the identity provider builds its addresses correctly from the headers Cloudflare sends.

## Task ids

M42.2.4, M37.6.1.3
