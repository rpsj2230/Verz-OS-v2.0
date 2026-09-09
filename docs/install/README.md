# Installing this system

Eight pages, written for somebody who has never met anybody who built this and is standing in
front of a bare server. Nothing in them names another company's installation.

| Page | What it covers |
| --- | --- |
| [install.md](install.md) | The whole install, step by step, from a clean server |
| [network.md](network.md) | Domain, DNS, reverse proxy, TLS and firewall |
| [configuration.md](configuration.md) | Every value you have to set, in one table |
| [integrations.md](integrations.md) | Each connector, and what it is trusted to read |
| [authentication.md](authentication.md) | Sign-in, the staff list, and your first administrators |
| [operations.md](operations.md) | Backup, monitoring, logging and health checks |
| [troubleshooting.md](troubleshooting.md) | What you are seeing, and what it is |
| [update-and-rollback.md](update-and-rollback.md) | Updating, and going back |

## Which half of this is checked

A guide that claims to be complete and is not is worse than one that says which half is checked.
So here is the boundary, exactly.

**Checked by `tests/unit/test_install_docs.py`, in both directions**, against the code and the
deployment files rather than against a second copy of them:

| Claim | Against |
| --- | --- |
| Every step of the install, and their order | the install plan the script is generated from |
| Every port this deployment opens, and its number | the compose files each profile composes |
| Every value a client must set | `.env.example`, the installer's mint step, and the compose interpolations |
| Where each value comes from | the install plan and the wizard's own questions |
| Whether each value has a default | the template and the compose interpolations |
| Every connector, with a row and a section | the connectors package, read for manifest builders |
| What each connector is pinned to, its transport, its access mode, what its source enforces, its rate ceiling | each connector's manifest |

"In both directions" is load-bearing. A missing row is found the first time somebody looks for
it. A row for a thing that no longer exists is never found at all, because it reads as coverage,
so the check refuses that too.

**Not checked, and kept true by hand:**

- Every sentence explaining what a value is for, and what to set it to
- Everything under a connector's own heading: what to create at the source, and what not to
  grant
- The whole of the authentication page, except the four settings it lists
- The whole of the troubleshooting page
- The whole of the update and rollback page
- Everything about DNS, TLS and the firewall

Three other pages hold parts of this to the code from their own side: the server sizing figures
are pinned by `test_deployment_requirements.py`, the backup schedule and the recovery figures by
`test_recovery.py` and `test_reliability.py`, and the list of scheduled mechanisms and whether
each has a caller by `test_controls.py`.

## What these pages tell you that you may not want to hear

Six things, gathered here so they are not discovered one at a time.

**You cannot run this install to completion today.** The fourth step of the installer
fetches a release archive, a workflow to publish one exists since 2026-09-10, and no release
has been tagged, so there is nothing at that address yet. A workflow that exists is not an
archive that exists. See install.md.

**After a complete install the console is reachable from nowhere.** Nothing publishes a port,
and no compose file in this product declares a reverse proxy. See network.md.

**Only `lite` can start today**, and `lite` deploys no identity provider, so it points at one
you already run. `standard` and `full` both compose an inference server whose image is required
with no default, and no image is published for that service. See authentication.md.

**Twelve of the thirteen scheduled safety mechanisms have no caller**, including the one that
takes a backup and the one that proves a backup can be restored. See operations.md.

**No update and no rollback has ever been performed on an install of this product.** See
update-and-rollback.md.

**Three of the eight pages here do not claim their leaf.** install.md, operations.md and
update-and-rollback.md each say why at the foot of the page. They are worth reading anyway; they
are not worth relying on as finished.

## Task ids

M42.2.4, M42.2.5, M42.2.6, M42.2.7, M42.2.9

M42.2.3, M42.2.8 and M42.2.10 each have a page here and none of the three is claimed. The reason
is at the foot of its own page.
