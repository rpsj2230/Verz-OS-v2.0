# Domain, DNS, reverse proxy, TLS and firewall

**Nothing in this deployment publishes a port.** Every service uses `expose`, which opens a
port on the compose network only, and no service in any profile uses `ports`, which is what
opens one on the machine. So a server that has run the install to completion is answering on
nothing at all from outside its own Docker network.

That is correct for the database, the cache and the pooler. It means the reverse proxy holding
your certificate is **part of the install rather than an optional extra**, and no compose file
in this product declares one. You supply it.

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
| `db` | `5432` | The pooler and the workers. Never from outside, and never from the application directly. |
| `inference-server` | `8080` | The application alone. It is handed the text of documents that have already passed the permission layer, so anything that can reach it can ask it to read them. `standard` and `full`. |
| `keycloak` | `8080` | Staff browsers, through your proxy, on the identity provider's own address. `standard` and `full`. |
| `langfuse-cache` | `6379` | The trace ledger alone. `full` only. |
| `langfuse-clickhouse` | `8123` | The trace ledger alone. `full` only. |
| `langfuse-web` | `3000` | Whoever operates this install, through your proxy, on the trace ledger's own address. Not your staff. `full` only. |
| `pgbouncer` | `5432` | The application alone. Everything the application does to the database goes through here. |
| `seaweedfs` | `8333` | The application, the workers and, on `full`, the trace ledger. `standard` and `full`. |

The application itself is deliberately not in that table, because it opens no declared port at
all. See the section above.

## Firewall

Two rules and one trap.

**Allow 80 and 443 to the proxy, and your own administrative access, and nothing else.** The
services above are on a Docker network and are not published, so there is nothing else to
allow.

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

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| Every service that opens a port has a row, and no row names one that does not | `test_install_docs.py`, against the compose files |
| The port numbers | the same test |
| That nothing publishes a port to the host | `test_deployment_requirements.py` |
| **Which addresses you need, and what to point them at** | **nobody. Prose, kept true by hand.** |
| **Everything about TLS and the firewall** | **nobody. Prose, kept true by hand.** |

## What has never been done

**No reverse proxy has ever been configured against this deployment from these instructions.**
This product ships no proxy configuration, and the only proxy work anybody here has done was
against one particular server for one particular panel. So the port numbers and the
requirements above are read out of the deployment and are true; the sequence as a whole has
never been walked by anybody starting from a bare machine.

## Task ids

M42.2.4
