# Integrations: what each connector is trusted to read

A connector is how this system reads one of your existing sources. The ones that ship with the
product are the ones in the table below, and none of them is switched on by an install: each is
connected deliberately, by somebody with the authority to decide which sources exist at all,
and each is pinned at that moment to one folder, one table, one account or one set of named
views.

**Nothing here is granted to a person.** A connector is a deployment unit, not a permission.
Granting one would grant everything behind it, so there is no capability anywhere in this
system for "reach through a connector", and there must not be one. What a person can see
through a source is decided by the same rule that decides everything else: an agent can see
nothing its caller cannot see.

## What "trusted to read" means, exactly

Four things, and the table below states all four from the connector's own declaration rather
than from a sentence somebody wrote beside it.

**What it is pinned to.** Every connector is scoped at connect to one named resource of one
kind. A Drive connector is pinned to one folder, not to the Drive. A Lark Base connector is
pinned to one Base and one table together, because a scope naming only the Base reaches every
table in it. Narrowing this later does not un-fetch what has already been read, which is why
it is decided at connect and never afterwards.

**Whether it can change anything.** Every connector shipped today is bound read-only, and two
of them refuse a write binding outright rather than accepting one nothing would use. A write
grant names somebody: it is a separate, deliberate decision, and no connector here has been
given one.

**What the source enforces.** This is the field to read twice, because it is the one that is
tempting to overstate. There are three honest answers. `delegated` means every call runs on the
asking person's own credentials, so the source applies its own rules to them and you get a
second, independent permission check for free. `predicate` means the source's own visibility
rule is stored and re-evaluated against the live entitlement set on every question, so somebody
moving department gets a different set of rows with nothing rewritten. `none` means the source
tells us nothing we can act on, and this system's own grants are the only permissions there
are.

**Every connector shipping today declares `none`**, and that is not an oversight. Each of them
authenticates with one shared credential, which is the honest reading of an API key, a service
account or a bot token: the source is answering as us, and it never sees the person who asked.
What stands between a person and a row in those sources is this system's own entitlements and
nothing else. Read that as a requirement on how you grant, not as a gap to be worked around.

**What it will run against.** Two of the seven have no measured rate ceiling, and the ones that
do are the source's published limit rather than a number chosen here. Where the ceiling belongs
to your own account rather than to a subscription, spending it is your outage: the accounting
connector's allowance is five thousand calls a day for your whole organisation, shared with
every other integration you run, and it does not refill until midnight.

## The table

Every cell below except the last column is read out of the connector's manifest by
`tests/unit/test_install_docs.py`, in both directions. A connector added to this product
without a row here fails that test, and so does a row here for a connector that no longer
exists, because a row for something that is gone reads as coverage.

<!-- checked: what each connector is trusted to read -->

| Connector | Transport | Pinned at connect to | Access | What the source enforces | Rate ceiling |
| --- | --- | --- | --- | --- | --- |
| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `freshdesk` |
| `google_drive` | `rest` | `folder` | `read_only` | `none` | none measured |
| `hubspot` | `rest` | `portal` | `read_only` | `none` | `hubspot` |
| `laravel` | `database` | `view` | `read_only` | `none` | none measured |
| `lark_base` | `rest` | `base_table` | `read_only` | `none` | `lark_base` |
| `lark_wiki` | `rest` | `wiki_space` | `read_only` | `none` | `lark_base` |
| `xero` | `rest` | `tenant` | `read_only` | `none` | `xero` |

Two rows deserve a second look.

`lark_wiki` runs against `lark_base`'s ceiling and that is deliberate. Both connectors talk to
one tenant application, and the hundred calls a minute are the tenant's, shared. Naming a
ceiling of its own would give the tenant two windows of a hundred where it has one bucket of a
hundred, and the first anybody would know is a refusal.

`freshdesk` is the one connector whose access mode is whatever binding it is handed. The other
six either fix it read-only or refuse a write binding at connect. Bind it read-only.

## Before you connect anything

**Create the credential at the source first, and grant it the least it can work with.**
`ops/openbao/credential-slots.md` is the register: it names the slot each connector reads, what
to grant, and what specifically not to grant, with the reason beside each refusal. Read it
before you create a key, not afterwards. The short version of every row is the same: an
administrator key can change or delete the thing you were only trying to read.

**Put the credential in the vault, never in the environment file.** A connector holds no
credential of its own. It borrows one per run against a lease and gives it back, so a rotation
needs no redeploy and there is nothing cached anywhere for a leak to reach.

**Expect to be asked for a visibility rule.** Some sources cannot tell us who may see a row.
Where that is true, whoever installs the connector supplies the rule, having read the source,
and it is checked against the fields the source exposes: a rule over a column that is not there
matches nothing, for ever, and looks exactly like a source with no records in it.

---

## `freshdesk`

Your helpdesk. Pinned to one helpdesk account by its address.

**Create** an agent API key with read scope. Not an administrator key: an administrator key can
change service levels and delete tickets.

**Know this before you rely on it.** Freshdesk's search returns at most three hundred records,
ever. Not per page: a hard ceiling on the result set, and the three-hundredth record and the
last record are reported identically. This connector stops at the ceiling deliberately and
marks the result truncated, so an answer built from a search that hit it says so rather than
reading as complete. A question like "every open high-priority ticket older than five days" is
answerable; the answer will tell you when it could not see the whole list.

**What it does not narrow.** The key is account-wide and there is no per-group key to ask for,
so pinning the account refuses a credential pointed at a different helpdesk and narrows nothing
inside this one.

## `google_drive`

One folder of one Drive, pinned at connect by folder id.

**Create** a service account and share the one folder with it, read-only. Do not grant
domain-wide delegation: it reads everything, for everyone, for ever, and no scope declared here
would narrow it.

**Two tools and neither returns a file's bytes.** It lists the folder and it reads a file's
metadata. Fetching contents is a separate decision with separate consequences, and this
connector is not it.

**What it does not narrow.** The folder pin is this system's restriction rather than Google's.
A service account reaches everything it has been granted, so the pin is enforced here, by
refusing a file that is not in the declared folder, rather than by Google refusing to serve it.

**No measured ceiling.** Nothing here has recorded a real exchange with Drive, so the rate
limits are Google's published figures rather than something observed. Treat the absence as
what it is: the connector will not invent a limit it has not measured.

## `hubspot`

Your CRM, pinned to one portal.

**Create** a private app token with read scopes on contacts, companies and deals. Nothing with
`write` in it, and nothing touching settings.

**Know this before you rely on it.** A CRM record is mostly a list of things this system
refuses to keep locally: an email address, a telephone number, a postal address, a contract
value. What survives into the local index of a contact has no name on it, deliberately. The
consequence is worth stating plainly rather than discovering: **any answer that names a person
is fetched live, every time**, and the fast index can count contacts and can never list them.
That is slower and it is the reason a stale copy of your CRM does not exist anywhere in this
system.

## `laravel`

Your own application database, read through views you control.

**Create** a database user with SELECT on the named views only. Not on tables. A table can gain
a column in next Tuesday's migration and a connector holding SELECT on it sees the new column
immediately: unclassified, unmapped, and on its way into an answer before anybody decided it
should be readable at all. A view is your own statement of what may be read, changed only when
you change it, reviewable by you without reading any of this system's code.

**The half this cannot enforce.** Whether the grant you created is really limited to those
views is inside your database and not visible from here. This connector refuses to ask for
anything else; it cannot stop a grant that is wider than it needs.

**No measured ceiling**, because the limit is your own database's capacity rather than a
vendor's published figure. Reads are bounded by a row count and a timeout supplied at connect.

## `lark_base`

One table of one Base.

**Create** a bot and add it to the one Base, holding read on records. Not write, and nothing
covering the whole drive.

**One Base and one table together, as a single pin.** A scope naming only the Base reaches
every table in it, and scope membership here is exact rather than a prefix match.

**The ceiling is the constraint that shapes everything.** A hundred requests a minute for your
entire organisation, permanently, shared by every question everybody asks. That is under two
calls a second. One question walking a large table to the end would spend the whole minute and
every colleague asking anything in the next sixty seconds would be refused with nothing in
their answer explaining why. So a read is given a share of the minute, stops when it is gone,
and says what it did not fetch.

**Its tool names include the entity you configure it with**, so they differ between two
installs of this same connector. That is why they are not in the table above: there is nothing
constant to check them against.

## `lark_wiki`

Named wiki spaces, and the only connector whose records are documents rather than rows.

**Create** a tenant application token with read on the wiki. Nothing that would allow editing a
document.

**A page carries its permissions across, as a rule and never as a list.** A page nobody can
open at the source must not become an answer they can read here. What is stored is the source's
visibility rule, re-evaluated against the live entitlement set every time somebody asks, so a
joiner, a mover or a leaver changes what they can see with nothing rewritten anywhere. A
resolved list of who may read a page is refused, in both the shapes it arrives in.

**It projects nothing.** Every other connector keeps a small local pointer to each record. A
wiki page has no such pointer worth keeping: the thing anybody actually wants is the body,
which is a document, and documents are handled by the knowledge layer with a citation on
every passage.

**It shares `lark_base`'s ceiling.** See the note under the table.

## `xero`

One accounting organisation's ledger.

**Create** an OAuth connection with read scopes on transactions and contacts. Nothing with
`.write`: this system answers questions about invoices, it does not raise them.

**The allowance is yours and it does not refill until midnight.** Five thousand calls a day,
per organisation, shared with every other integration you run against it. There is no plan
that raises it. A per-minute limit refills while somebody is still reading the error; a daily
one does not, so spending it before lunch means no accounting data in the building until the
reset. This connector treats the day allowance as a first-class budget for that reason, and a
refusal that carries a long wait is honoured rather than retried after five minutes.

---

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| Every connector in this product has a row and a section | `test_install_docs.py`, reading the package |
| No row or section names a connector that does not exist | the same test, in the other direction |
| The transport, the pin, the access mode, the permission posture, the ceiling | the same test, against each connector's manifest |
| **What to create at the source, and what not to grant** | `ops/openbao/credential-slots.md`, which is a register kept by hand |
| **Everything under a connector's own heading** | **nobody. It is prose, and it is kept true by hand.** |

## Task ids

M42.2.6
