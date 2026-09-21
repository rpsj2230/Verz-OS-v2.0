# Handing the install back, and removing it

For the day a company leaves. The company takes every store and the audit ledger in open formats,
with a manifest it can check without any of this software, and the install is then removed part by
part until a certificate can be issued. The certificate names the date the last backup that could
still hold the data expires, and never claims more than that.

The steps run on the server, in the application container, as whoever holds the environment file.
The Settings screen (Install, then Settings, the card "Leaving: handover and uninstall") shows the
same steps for this install before anybody runs them. There is no button there on purpose.

## Before you start

- A written instruction from the company, naming who gave it. Its reference goes on every file.
- The reason, one of `contract_ended`, `client_request` or `migration`.
- A directory with room for the whole database and the object store. Not inside the object store.
- The object store connected. If it is not, the export records the buckets as not reached and the
  next step refuses, which is the point: nothing is removed that the company did not receive.

## 1. Export

```
python -m brain.ops.handover_run export /srv/handover \
  --handover-id <id> --reason contract_ended \
  --instructed-by "<role at the company>" --instruction-reference "<letter, clause>"
```

Every table in every schema is written as CSV with a header row, read inside one transaction so
the audit ledger and the rows it describes are the same moment. Every object this install holds is
written as the bytes stored. `manifest.json` lists each file with its size, row count, digest and
the store it belongs to; `SHA256SUMS` holds the same digests.

Hand the directory over. The company checks it with `sha256sum -c SHA256SUMS`.

## 2. Verify and plan

```
python -m brain.ops.handover_run verify /srv/handover
python -m brain.ops.handover_run plan /srv/handover
```

`plan` refuses unless every store was reached and every file still matches its digest, then writes
`teardown.json`: one step per store and per install part, each saying who removes it.

## 3. Remove what the command removes

Stop every service that runs the application image first (`brain-worker` only where the install
runs one), then run the command in a one-off container. The database and its pool stay up: an idle
pool holds no lock, and the command reaches the database through it.

```
docker compose stop app brain-worker
docker compose run --rm --no-deps app python -m brain.ops.handover_run remove /srv/handover --confirm <id>
```

A schema cannot be dropped while any session holds a lock on one of its tables. Each drop waits
at most 30 seconds and then refuses, naming the sessions still connected by role, application and
state; stop them and run `remove` again. What was already removed is recorded and stays removed.

Drops every schema, deletes this install's objects from every bucket (the backup bucket at its
root, which belongs to this install), and checks the scheduled work, the index and the object store
are gone. Each step is marked done only when a second look finds it gone.

## 4. Remove what the operator removes, and record each

| Part | What to do | Then |
| --- | --- | --- |
| `identity_realm` | `kcadm.sh delete realms/<INSTALL_OIDC_REALM>` | `record /srv/handover identity_realm` |
| `vault_secrets` | `bao kv metadata delete` every path under `providers/`, `webhooks/`, `connector_keys/`; `bao token revoke` the application token | `record ... vault_secrets` |
| `connector_authorisations` | revoke the grant in each source's admin console; the export's `connectors` lists them | `record ... connector_authorisations` |
| `chat_app` | delete the chat app in the Lark, Slack or Teams developer console | `record ... chat_app` |
| `network_route` | delete the proxy route, its certificate and the DNS record | `record ... network_route` |
| `runtime` | `docker compose down --volumes --rmi all`; delete a bucket made for this install only; on a database server that outlives the install, `DROP OWNED BY brain_app, brain_fastlane`, `DROP ROLE brain_app, brain_fastlane` and `DROP TABLE public.alembic_version` | `record ... runtime` and `record ... cache` |
| `install_configuration` | delete the install directory and its `.env` | `record ... install_configuration` |

`record` is `python -m brain.ops.handover_run record /srv/handover <part> --note "<how>"`. The note
is copied onto the certificate; write how the part was removed, or that it never existed on this
install, so a part that was absent is not certified as if it had been removed. It refuses a step the
command removes, because those are done by being checked, not by being said. `record` and
`certify` read only the handover directory, so once the containers are gone run them from a copy
of it on any machine with the release image:
`docker run --rm -v "$PWD/handover:/h" <image> python -m brain.ops.handover_run record /h runtime`.

## 5. Certify

```
python -m brain.ops.handover_run certify /srv/handover
```

Refused while any step is open. Writes `certificate.json` and `certificate.txt`: who instructed
it, how many items were returned and when, every store and part removed, the digest of the
manifest, and the date the last backup expires, which is the backup retention after the last step.
