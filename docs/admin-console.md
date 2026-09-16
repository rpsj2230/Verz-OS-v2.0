# What the administrative console has to be

The owner set this standard on 2026-09-16, after signing in to his own install for the first
time and finding a console that could show him a handful of screens and manage almost nothing.
It is written down here rather than left in a conversation, because the console is built by
many hands and every one of them needs the same target.

**One secure console from which an authorised administrator manages, configures, monitors and
controls the whole platform, without reaching for the server, the database, the source or a
configuration file to do anything routine.**

## The test to apply

**Could an administrator who has never read this repository do this thing, safely, from the
browser?** If the answer is "only by editing a file on the server" or "only by asking whoever
built it", the console is not finished for that thing.

The second test, and the one that has already caught this project twice: **a screen that exists
in a read module and not in a browser is not a screen**, and a control that renders but reaches
nothing is worse than no control at all. `brain.ops.console_screens` reports the first on every
run. The second is what the end-to-end check below exists to catch.

## What an administrator must be able to manage

Each line is a thing an administrator would reasonably expect to control. Where the platform
does not have the underlying mechanism yet, the console says so in words on the screen and the
gap is a task, never a disabled button with no explanation.

- People, roles, permissions and access control
- Departments, teams and client configuration
- System settings and application configuration
- AI providers, models and the routing between them
- Agents and their configuration, including templates
- Skills and tools
- Workflows and automations
- Connectors and third-party integrations
- API keys, credentials and secrets, held in the vault and never displayed
- Knowledge bases, documents and data sources
- File and object storage
- Prompts and system instructions
- Feature and module enablement
- Notifications and email
- Webhooks
- Scheduled jobs and background work
- Usage, activity and system statistics
- Logs and errors
- The audit trail: who changed what, and when
- System health and the state of every service
- Backup and recovery
- Import and export
- Version, build and deployment information

## How every screen behaves

These are the house rules for the console, and they are not decoration:

- **Nothing sensitive is displayed.** A credential is written once and never read back. A
  screen shows that a secret is held, never the secret.
- **A destructive action is confirmed**, and says what will happen and to what.
- **Validation happens before the write**, and an error says what to do about it.
- **Loading, empty and failure states are written**, not left to a blank panel. An empty list
  and an unreachable source are different sentences.
- **Success and failure are both reported**, in words a person can act on.
- **Long lists page, search, filter and sort**, and bulk actions exist where they are safe.
- **Every screen works at phone width** and under the keyboard.
- **Navigation is grouped by what an administrator is trying to do**, not by which module
  happens to serve it. One coherent platform, not a drawer of settings pages.

## What the permission model has to hold

The console decides nothing about who may see what. `brain.console.reads.permitted` is the one
answer, and it is the capability and the plane together. Two rules follow and both are already
load bearing:

- **A sensitive operation is an `admin:` capability**, which `brain.gate.admission` already
  withholds from a password-only session and from a token with no session.
- **DENIED and ABSENT stay indistinguishable.** No screen, no filter dropdown and no error
  message may tell a reader that something exists which they may not see, and no count of
  withheld rows is ever shown.

## Before any of this is called done

An audit, not an opinion:

1. Read the database schema, the modules, the routes and the settings, and list every thing an
   administrator would reasonably need to manage.
2. Compare that list against what the console actually serves, screen by screen.
3. For each gap, either build it or record it as a task with the reason.
4. **Prove the controls reach the system.** A write is followed to the row it writes, the audit
   entry it leaves, and the behaviour it changes. A control that cannot be proved end to end is
   not shipped as working.
