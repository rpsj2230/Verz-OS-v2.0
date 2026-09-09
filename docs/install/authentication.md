# Authentication, the staff list, and your first administrators

Two decisions on install day, and they are not independent. **Where your staff list comes from
is also what signs people in**, and asking them as two questions is how an install ends up
brokering sign-in to one directory and pulling its roster from another.

## This system holds no passwords

Sign-in goes to an identity provider, and the console receives an authorisation code back on
`/auth/callback`. On `standard` and `full` that identity provider is deployed beside this
system as its own container, with its own database and no connection string to yours: sharing
one would put the credential store and the company records it protects in one blast radius.

**On `lite` there is no identity provider at all, and the system still refuses to start without
one.** `lite` deploys the application, the pooler, the database and the cache, and nothing else.
`INSTALL_OIDC_ISSUER` has no default and stops the boot when it is unset. So a `lite` install
points at an identity provider you already run, and everything on this page about
`KEYCLOAK_ADMIN` and the realm belongs to the other two profiles.

That is worth knowing before you choose a profile, because the obvious way round it is to run
`standard`, and **`standard` and `full` cannot start today**: both compose an inference server
whose image variable is required with no default, and no image is published for that service
anywhere. Until one is, `lite` plus your own identity provider is the arrangement that works.

Three settings connect the two, and one of them refuses to start when it is unset.

| Setting | What it is |
| --- | --- |
| `INSTALL_OIDC_ISSUER` | The issuer address of your realm. No default. The system refuses to start without it, because an issuer guessed wrong is a sign-in page that authenticates against something you do not control. |
| `INSTALL_OIDC_REALM` | The realm's name. Asked for separately because the setup script needs it before the issuer exists. |
| `INSTALL_OIDC_CLIENT_ID` | What the console registers as inside that realm. |
| `INSTALL_OIDC_REDIRECT_URIS` | Where the realm will send somebody back to. No default, for the same reason: wrong here is a sign-in that completes and lands on a page you do not own. |

## Choosing the staff source

The wizard offers four on install day. Two more exist and are added afterwards from the
console, because neither is one a person picks on the first afternoon without help.

| Choice | Signs people in through | Offered by the wizard |
| --- | --- | --- |
| Google Workspace | Google | yes |
| Microsoft Entra | Microsoft | yes |
| Lark | Lark | yes |
| A spreadsheet | the realm itself, which holds the passwords | yes |
| A Google Sheet | as above | no, add it later |
| LDAP | LDAP | no, add it later |

## What each source is trusted to say, and why it matters

A roster source can assert three things, and no more. It can say **that somebody exists**, with
a name and a work address. It can say **which department they are in**, which is the scope
every grant they hold is bounded by. And it can say **which platform role they hold**.

There is deliberately no fourth. A group in a directory never maps to a capability, only to a
role, because a capability in a directory moves "who can see the margin" out of this system and
into one nobody here reviews.

| Source | Trusted by default to assert |
| --- | --- |
| A spreadsheet, or a Google Sheet | existence, and nothing else |
| Google Workspace, Microsoft Entra, Lark, LDAP | existence, department and role |
| The identity provider's own groups | existence, department and role |

**A spreadsheet may list people and may not appoint them.** That is the line, and it is about
what changing the source costs somebody rather than about the file format: a sheet is editable
by whoever holds the link, and a directory needs an administrative console and leaves a trail
in it. A sheet that could assert a role is a sheet where adding a row to a column called
"groups" makes somebody an auditor.

The default is a default and not a fixed rule. An install whose sheet is locked to two people
can raise it; an install whose directory groups are edited by a helpdesk should lower it. What
it cannot do is start permissive, which is why a source nobody has configured asserts existence
alone.

## The roles

Six, compiled into the product. A seventh is a code change, a review and a deploy, and that is
the design rather than a limitation: the set of things a person can be is part of the design of
the system, not part of its data. An editable role table looks like flexibility and is an
unreviewed permission model, because the row that granted somebody a department is
indistinguishable from the row that granted them the platform.

| Role | Exists to | Typical number |
| --- | --- | --- |
| Super Admin | Own the platform: publish global agents, change the catalogue, confirm nominations, disable principals | 2 to 4 |
| Department Admin | Run one department's people and grants, bounded by that department | one or two per department |
| Member | Ask questions and use what they have been granted | everybody |
| Auditor | Read the record of what happened, without being able to change any of it | one or two |
| Connector Admin | Install and bind sources, and never read a record through one | one or two |
| Approver | Approve specific things within a specific scope | as many as the work needs |

Two of the six are meaningless without a scope. A Department Admin with no scope is a Super
Admin nobody appointed; an Approver with no scope approves anything anybody asks them to.

## Your first administrator, and your second

The wizard's administrator screen appoints one person, and they become a Super Admin.

**Appoint a second one on the first day.** The system will not let you go from two Super Admins
to one: a single Super Admin is a single point of lockout, and there is no support desk
anywhere that can let you back in, because nobody outside your organisation holds a credential
on your server. Two is the floor and the refusal fires when you try to drop below it.

**The Super Admin role confers no capabilities by itself.** It is a role, not an elevation: the
first administrator is created with a role grant and no capability grants at all, and a Super
Admin sees exactly what somebody wrote a grant for. If you were expecting the administrator
account to be able to read everything, it cannot, and that is the invariant the whole system
serves rather than an omission in the wizard.

**Emergency access is the installing partner's path and not yours.** There is a break-glass
mechanism in this system and it belongs to a partner employment rather than to a role. No code
path elevates an administrator, and none should.

## The identity provider's own accounts

On `standard` and `full`, three values are yours to set before the stack starts. None of them
is minted for you, and none of them ships with the product.

| Variable | What to do with it |
| --- | --- |
| `KEYCLOAK_ADMIN` | A username for the identity provider's temporary administrator. |
| `KEYCLOAK_ADMIN_PASSWORD` | Its password. Used once, to create your own account. |
| `KEYCLOAK_DB_PASSWORD` | The identity provider's own database. Never typed by a person after the install. |

Two pieces of housekeeping once you have your own account, and they are easy to leave undone:

1. Delete the temporary administrator.
2. Change `KEYCLOAK_ADMIN_PASSWORD` to a fresh value.

**Do not delete the variable.** The stack refuses to start without it, and it is the way back
in if every administrator is ever lost.

## Two things about the realm that have already gone wrong

Both were found by deploying the identity stack for the first time, in logs rather than in a
review, and both are fixed. They are here because the shape of each is worth recognising.

**The realm file will not import as written.** It carries explanatory comments, which is why it
is readable, and the identity provider rejects any field it does not recognise: it refused the
file outright with a message about an unrecognised field. A helper container now generates a
stripped copy for the import, using the product's own code rather than a shell one-liner, so
both the explanation and the import survive. That helper runs to completion before the identity
provider starts, because a provider that starts with no realm fails every sign-in with nothing
visible near the login page saying why.

**The provider must not be started with `--optimized`.** That flag skips its build step and
uses a configuration baked into the image, and the stock image has no such build in it. It says
so on every boot, in a warning naming the database and the health endpoint as the two options
that will not be used, and the consequence is a container that comes up against the wrong store
with nothing answering its health check, so it restart-loops for ever. Without the flag it runs
its own build at startup, which is why the health check's start period is ninety seconds rather
than thirty. A slow start beats a container that never becomes ready.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The six roles and what each is for | `test_roles.py`, against the compiled role table |
| That two Super Admins is the floor | the same test |
| What each source is trusted to assert | `test_staff_source.py`, against the trust table |
| Which four sources the wizard offers | `test_setup_wizard.py`, against the wizard's own question |
| The four identity settings and their defaults | `test_install_docs.py`, through the configuration guide |
| **Everything else on this page** | **nobody. Prose, kept true by hand.** |

## Task ids

M42.2.7
