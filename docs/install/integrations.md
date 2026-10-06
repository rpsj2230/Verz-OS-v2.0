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

**What it will run against.** Every one of the eleven has a rate ceiling recorded. Each is the
source's published limit rather than a number chosen here, except your own Laravel database's
and the domains connector's, for which nobody publishes one figure: each is this product's own
pace, and says so. Where the ceiling belongs to your own account rather than to a subscription,
spending it is your outage: the accounting connector's allowance is five thousand calls a day for
your whole organisation, shared with every other integration you run, and it does not refill until
midnight.

**What happens when a source renames a field.** Every source is read on a schedule at least once a
day, and each read is also the check of what the source sends. When a record that carried one of
the fields this system keeps is read again without it, and no record of the read carries it, the
source's health on the Connectors screen turns to degraded and says which field, by its name here
and never with a value. Until a later read finds the field again, a question that would read that
kind of record from the source is told the source could not be read, rather than given records with
the field missing. A field that is only ever read live, and never kept, is not judged this way,
because nothing holds what it used to be.

## The table

Every cell below except the last column is read out of the connector's manifest by
`tests/unit/test_install_docs.py`, in both directions. A connector added to this product
without a row here fails that test, and so does a row here for a connector that no longer
exists, because a row for something that is gone reads as coverage.

<!-- checked: what each connector is trusted to read -->

| Connector | Transport | Pinned at connect to | Access | What the source enforces | Rate ceiling |
| --- | --- | --- | --- | --- | --- |
| `cloudflare` | `rest` | `account` | `read_only` | `none` | `cloudflare` |
| `domains` | `rest` | `domain` | `read_only` | `none` | `domains` |
| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `freshdesk` |
| `google_analytics` | `rest` | `analytics_property` | `read_only` | `none` | `google_analytics` |
| `google_drive` | `rest` | `folder` | `read_only` | `none` | `google_drive` |
| `hubspot` | `rest` | `portal` | `read_only` | `none` | `hubspot` |
| `laravel` | `database` | `view` | `read_only` | `none` | `laravel` |
| `lark_base` | `rest` | `base_table` | `read_only` | `none` | `lark_base` |
| `lark_wiki` | `rest` | `wiki_space` | `read_only` | `none` | `lark_base` |
| `search_console` | `rest` | `search_site` | `read_only` | `none` | `search_console` |
| `slack_messages` | `rest` | `workspace` | `read_only` | `none` | `slack_messages` |
| `xero` | `rest` | `tenant` | `read_only` | `none` | `xero` |

Two rows deserve a second look.

`lark_wiki` runs against `lark_base`'s ceiling and that is deliberate. Both connectors talk to
one tenant application, and the hundred calls a minute are the tenant's, shared. Naming a
ceiling of its own would give the tenant two windows of a hundred where it has one bucket of a
hundred, and the first anybody would know is a refusal.

`freshdesk` is the one connector whose access mode is whatever binding it is handed. The other
seven either fix it read-only or refuse a write binding at connect. Bind it read-only.

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

## `cloudflare`

Your DNS provider. Pinned to one Cloudflare account by its id, and connected from the Connectors
screen with two settings and a token: the account's 32-character id, from the account's Overview
page, and the short name of the one department whose people may be granted its zones and DNS
records. Nothing is done on the server. The worker reads the account's zones every hour and each
zone's DNS records under it, and keeps a zone's id, name, status and account and a record's id,
zone, name and type; a record's content, time to live and proxying are read live when a question
needs them and never kept. A zone's security events are read live for the past hour or the past
day, never with the visitor's address or user agent.

**Create** a custom API token (My Profile, API Tokens, Create Token) with exactly three
permissions, Zone Read, DNS Read and Analytics Read, over all zones from the one account. Never a
token with DNS Write or any Edit permission, and never the Global API Key.

**A DNS change is only ever prepared.** An agent asking to change a record prepares the change for
a person to approve, and the gate holds it whatever the agent's leash says, because changing DNS
is one of the effects that always waits for a person. An approved change is not sent by this
release: sending one needs a second token with DNS Write, which is a decision for whoever owns the
install, and until then the change is made in Cloudflare by a person.

**What it does not narrow.** The token is one user's, and Cloudflare counts 1,200 calls per five
minutes across every token that user holds and the dashboard, so another integration on the same
user spends the same allowance. A zone that turns out to belong to another account stops the read
rather than being kept, so a token wider than the one account it was created for is noticed.

## `domains`

Your clients' domains: each one's registrar and expiry, and whether its site answers.

**Nothing to create and nothing to keep.** A domain's registration record is published by its
registry over RDAP, so this connector takes no key. List the domains, up to two hundred, and the
department whose people may be told about them. **Only the listed domains are ever looked up**,
whoever asks about another.

**Where a registry publishes no RDAP**, as several country-code registries do not, the answer
for that domain says so rather than guessing, and that registry is never asked. The registrar's
name is read live and kept nowhere. The pace is this product's own, thirty lookups a minute,
because registries publish no common figure.

## `freshdesk`

Your helpdesk. Pinned to one helpdesk account by its address, and connected from the Connectors
screen with two settings and a key: the helpdesk's address, ending in `.freshdesk.com`, and the
short name of the one department whose people may be granted its tickets. Nothing is done on the
server. The worker then reads the ticket list every fifteen minutes and keeps each ticket's ids,
status, priority, dates and subject, with that department on it; the body, the conversation and
the custom fields are read live when a question needs them and never kept.

**Create** an agent API key with read scope. Not an administrator key: an administrator key can
change service levels and delete tickets. The key sees what its agent sees, so choose an agent who
sees the tickets this system should answer about and no more.

**Know this before you rely on it.** Freshdesk's search returns at most three hundred records,
ever. Not per page: a hard ceiling on the result set, and the three-hundredth record and the
last record are reported identically. This connector stops at the ceiling deliberately and
marks the result truncated, so an answer built from a search that hit it says so rather than
reading as complete. A question like "every open high-priority ticket older than five days" is
answerable; the answer will tell you when it could not see the whole list.

**What it does not narrow.** The key is account-wide and there is no per-group key to ask for,
so pinning the account refuses a credential pointed at a different helpdesk and narrows nothing
inside this one. Inside this system, one department reads the whole helpdesk: a rule sending each
Freshdesk group to a different department is not something a connection can hold yet.

## `google_analytics`

One Google Analytics property, pinned at connect by its property id.

**Create** a service account, switch on the Google Analytics Data API and Admin API in its
project, create a JSON key for it, and add its address to the one property as a Viewer. Do not
grant domain-wide delegation: it reads the property as itself and needs nothing more. The key
file is exchanged for a token that carries `analytics.readonly` and nothing else, for one read
at a time, and never kept.

**It keeps the property and never its figures.** The index holds the property's id, its name
and when it was created and last changed. Sessions, users and conversions are read from Google
when somebody asks, for yesterday or the last 7, 28 or 90 days, and are never stored anywhere
here.

**What it does not narrow.** One department reads the property: the one named at connect, whose
people are then granted it by somebody holding it. A property several departments share is read
by the one named.

## `google_drive`

One folder of one Drive, pinned at connect by folder id or link, connected on the Connectors
screen with the department it belongs to and the person answerable for it.

**Create** a service account, share the one folder with it as a viewer, and choose its key file on
the form. Do not grant domain-wide delegation: it reads everything, for everyone, for ever, and no
scope declared here would narrow it. The key file is exchanged for a `drive.readonly` token for
each read and is never sent.

**What it keeps and what it reads.** The worker walks the folder and every subfolder under it
every hour into the index: each file's and folder's name, type, dates and sharing verdict, never a
word of a file. A question reads the words of the few files whose names hold its words, live, only
for a reader granted the folder's files in its department: a Google Doc exported as plain text and
a plain-text file as it is. A shortcut is never followed. A pass that reaches its bound before the
tree's end is marked degraded and starts from the folder again on the next pass.

**What is never read.** A file Google shows as shared by link or outside your domain, a file in
the bin, and a file or subfolder whose access was limited below its folder's, with everything in
it. A viewer is not shown how each
file is shared, so a file whose sharing Google does not show is read as the folder's (decided by
the owner, needs-rupash 135).

**Its ceiling** is Google's documented quota, 325,000 units a minute per user of the project,
recorded at the dearest call a read makes. A project owner may ask for more on the Cloud console's
Quotas page.

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

**Where the database is, you say.** The server's address and port have no default. Let this
system's server reach the database on that port only: allow the server's own address in the
database's firewall or security group, or, where the database is on a private network, run an
SSH tunnel from this system's server to a machine that reaches it and give the tunnel's local end
with the private network setting at yes. An address inside a private network is refused unless
that setting says so, by the same rule every other source's address passes.

**This product's own pace, not a measured ceiling**, because the limit is your own database's
capacity rather than a vendor's published figure: thirty bounded reads a minute across the worker
and every question together. Every read is also bounded by the row count and the timeout you
give at connect, in a read-only session, one connection per read.

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

## `search_console`

One Search Console property, pinned at connect by its name as Search Console lists it: an address
ending in a slash, or `sc-domain:` and a domain.

**Create** a service account (the Google Analytics one will do), switch on the Search Console API
in its project, create a JSON key for it, and add its address to the one property as a user with
restricted permission. Do not grant domain-wide delegation. The key file is exchanged for a token
that carries `webmasters.readonly` and nothing else, for one read at a time, and never kept.

**It keeps the site and never its figures.** The index holds the site's name and the permission
the account has on it. Clicks and impressions for the last 7, 28 or 90 days, the top query and page
for the last 28 days and the sitemaps' errors and warnings are read from Google when somebody asks,
four calls made at once, and are never stored anywhere here.

**What it does not narrow.** One department reads the site: the one named at connect. Indexing
issues are the sitemaps' own counts, because the API offers no page-indexing report to read.

## `slack_messages`

Your Slack workspace, read as a source for answers. This is not the Slack channel, which answers
questions asked in Slack; it is a separate app with its own token.

**Create** a Slack app for your workspace with these bot scopes and no others: `channels:read`,
`groups:read`, `channels:history`, `groups:history`, `users:read`, `users:read.email`. Nothing
that writes, and no user token: a user token is one person's whole account and reads as them.
Invite the app to each channel it may read; a channel it is not in is never read.

**What is kept, and what is read.** The index keeps each channel's name and whether it is
private, and each member as the digest of their confirmed work email. No message, no member
list and no address is stored. On every question, the asker is matched to their Slack account
by that digest, Slack is asked which of the app's channels they are in, and only those channels'
recent messages are read, for that asker alone. **A private channel the asker is not in is never
read for them, however well it matches.**

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
