# Authentication, the staff list, and your first administrators

Three things are settled on install day: where people sign in, where the list of who works at
your company comes from, and who administers the system first. The setup wizard asks the second
and the third, and derives a setting for the first from the second, because **choosing where your
staff list comes from is meant to be choosing what signs people in**. Asking them as two questions
is how an install ends up brokering sign-in to one directory and pulling its roster from another.
That derived setting is written today and nothing acts on it yet; the staff source section below
says exactly what is built and what is not.

## This system holds no passwords

Sign-in goes to an identity provider, and the console receives an authorisation code back on
`/auth/callback`. On `standard` and `full` that identity provider is deployed beside this
system as its own container, with its own database and no connection string to yours: sharing
one would put the credential store and the company records it protects in one blast radius.

**On `lite` there is no identity provider at all, and nobody can sign in until the system is
pointed at one.** `lite` deploys the application, the pooler, the database and the cache, and
nothing else. `INSTALL_OIDC_ISSUER` has no default. Without it the system still starts, but it
cannot check a sign-in: every page behind sign-in refuses, and `/health/ready` names `sign_in` as
not configured under `reported`. It stays 200, so the pages that need no sign-in, the setup wizard
among them, keep serving while you set it. So a `lite` install points at an identity provider you
already run, and everything on this page about `KEYCLOAK_ADMIN` and the realm belongs to the other
two profiles.

That is worth knowing before you choose a profile, because the obvious way round it is to run
`standard`, and **`standard` and `full` cannot start today**: both compose an inference server
whose image variable is required with no default, and no image is published for that service
anywhere. Until one is, `lite` plus your own identity provider is the arrangement that works.

Four settings connect the two.

| Setting | What it is |
| --- | --- |
| `INSTALL_OIDC_ISSUER` | The issuer address of your realm. No default, and no wizard screen asks for it, because an issuer guessed wrong is a sign-in page that authenticates against something you do not control. Unset, the system starts and refuses every sign-in, as above. |
| `INSTALL_OIDC_REALM` | The realm's name. Asked for separately because the setup script needs it before the issuer exists. |
| `INSTALL_OIDC_CLIENT_ID` | What the console registers as inside that realm. |
| `INSTALL_OIDC_REDIRECT_URIS` | Where the realm will send somebody back to. No default. The wizard writes it from the web address you give it, followed by `/auth/callback`, rather than asking you to type it: wrong here is a sign-in that completes and lands on a page you do not own. |

## Choosing the staff source

The wizard's staff list screen comes after the administrator screen and asks two things: **where
your staff list comes from**, and **where that list is**. It offers four choices and has to be
answered with one of them. There is no "no list" on this screen.

<!-- checked: the staff sources the wizard offers -->
| Choice | Written as `INSTALL_STAFF_SOURCE` | Written as `INSTALL_BROKERED_DIRECTORY` | Where the list is | How the screen reads it |
| --- | --- | --- | --- | --- |
| Google Workspace | `google_workspace` | `google` | needed: your primary domain | sign in, then read |
| Microsoft Entra | `microsoft_entra` | `microsoft` | needed: your tenant ID, or your tenant's domain | sign in, then read |
| Lark | `lark` | `lark` | needed: `larksuite.com` or `feishu.cn`, whichever your company signs in to | sign in, then read |
| A spreadsheet | `spreadsheet` | `none` | refused: the file is the list, so there is nowhere to point | from a CSV file you choose |

"Needed" and "refused" are the screen's own rules, checked beside the box. A directory with no
location is refused, because a source pointed nowhere reads as a company with nobody in it. A
Google domain or an Entra tenant that is not shaped like one is refused, and so is a Lark location
that is not one of Lark's two platforms, because the location decides which address your client
secret is sent to. A location given for a spreadsheet is refused because it would be written into
a setting nothing reads.

The product can read three more values of `INSTALL_STAFF_SOURCE`, and the wizard offers none of
them.

<!-- checked: the staff sources the product reads and the wizard does not offer -->
| Source | Written as | Why the wizard does not offer it |
| --- | --- | --- |
| A Google Sheet | `google_sheet` | Not one a person picks on the first afternoon without help. |
| LDAP or Active Directory | `ldap` | The same. |
| No list | `none` | The default of an install that never answered. The wizard's question has to be answered, so an install set up through the wizard never has it. |

**Choosing a Google Sheet or LDAP after setup is not built.** No screen offers it: the console's
Staff sources screen lists every source and says that choosing one cannot be done from a browser.
The wizard's answer is saved in the database, a saved value outranks the environment file, and
nothing writes that value again after the appointment. So an installed system has no supported way
to change its staff source today.

**What is written, and when.**

1. **Moving past the screen writes nothing.** The answers stay in the setup page with the rest of
   the wizard's answers until you send the review.
2. **Sending the review writes them**, in the same database transaction that appoints the first
   administrator: `INSTALL_STAFF_SOURCE`, `INSTALL_STAFF_SOURCE_LOCATION` when there is one, and
   `INSTALL_BROKERED_DIRECTORY` derived from the choice as the table shows. Either all of it is
   written with the appointment or none of it is.
3. **The check under the questions writes nothing at any point.** The next section is about it.
4. **Nothing reads the list after setup yet.** No scheduled sync is built, so choosing a source
   creates nobody, and the console's Staff sources trial says that nothing on the server can read a
   live source rather than showing an empty one.

**What `INSTALL_BROKERED_DIRECTORY` does not do yet.** The wizard writes it so that the directory
your staff list comes from is also the one people sign in through. Nothing in the product sets that
brokering up: the realm this product imports carries no Google, Microsoft or Lark identity
provider, and the only reader of the setting today is the statement the system makes about its own
privacy posture, which says whether sign-in is brokered. Until your directory is added to the realm
in the identity provider's own admin console, people sign in with accounts held in the realm
itself, whichever source you chose.

## Reading the staff list on the wizard's screen

Under the two questions is a check you can run before anything is written. It reads the list once
and shows the people a first run would add. Nobody is added and nothing is stored. You do not have
to run it to finish setup, and the file, client ID and secret you give it are not answers to the
wizard, so none of them is in the review or written at the appointment. The check asks for your
setup code first, and with a wrong code it reads nothing and contacts nobody.

**A spreadsheet** is read from a file you choose. Save it as CSV first. The first row holds the
headings, matched regardless of capitals and surrounding spaces, and every row needs an address and
a name.

<!-- checked: the headings a spreadsheet is read by -->
| Column | Found under any of these headings |
| --- | --- |
| Work address | `Work Email`, `Email`, `Email Address`, `Work Address` |
| Name | `Full Name`, `Name`, `Display Name` |
| Department | `Department`, `Dept`, `Team` |
| Groups, separated by commas | `Groups`, `Group` |
| Has left | `Left?`, `Left`, `Departed`, `Inactive` |

A department and groups are read from a spreadsheet and not believed, because a spreadsheet is
trusted to say that somebody exists and nothing else; the section on trust below says why. A
has-left cell saying `yes` marks that person as having left.

**Google Workspace, Microsoft Entra and Lark need an application your company registers with
them before anybody can sign in.** This is not something the product can do for you. A directory
only sends a person back to an address registered on the application they signed in to, and your
install has its own address, so the application has to be yours. The screen shows the return
address to register, which is your web address followed by `/first-run/staff-list`.

| Directory | What to register | What to grant it |
| --- | --- | --- |
| Google Workspace | In Google Cloud console, in a project belonging to your company, an OAuth client of the type Web application, with the return address as an authorised redirect URI. Enable the Admin SDK API in the same project. | Nothing on the client. Sign in with a Workspace administrator's account, which is what lets it read the user directory. |
| Microsoft Entra | In the Microsoft Entra admin centre, an application registration with a Web platform, the return address as a redirect URI, and a client secret. | The delegated Microsoft Graph permission `User.Read.All`, with admin consent granted for your organisation. |
| Lark | In the Lark developer console, a custom app with the return address as a redirect URL under Security settings. Copy its App ID and App Secret. | The contact permissions to read users, their email addresses, their departments and department names; a contact range covering everyone who should be listed; and a published version. |

Then paste the application's client ID and secret on the screen and press **Sign in and read the
list**. The directory's own sign-in page opens in a second window, because the setup code lives
in the setup page's memory and leaving that page would lose it. Allow pop-ups for your web
address if the window does not open.

**The secret is used for that one read and is not kept.** It is sent once, to the directory, to
exchange for a sign-in, and nothing on your server stores it. That is deliberate rather than
unfinished work: nothing in this product reads a directory on a schedule yet, and a secret kept
for a job nobody runs is a standing credential with nothing using it. When the scheduled sync
exists, it will ask for a credential it can keep in the vault.

**Groups are not read from a directory on this screen.** The check proposes who would be added and
nothing else; reading each directory's groups is the scheduled sync's work.

**What has never happened.** The sign-in and the read are written from each directory's own
documentation and tested against a stand-in; none of them has been run against a real Google,
Microsoft or Lark tenant. The first company to register an application is the first real run.

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

**The defaults are a ceiling, and nothing on an install changes them yet.** The product's reading
of a list can be given a narrower trust than the table, which is how an install whose directory
groups are edited by a helpdesk would lower it, but no setting or screen supplies one today. Trust
cannot be raised: a list read through the install's own choice that claims more than its source's
default is refused rather than trimmed, because a widening somebody configured and cannot see is
the whole failure. A source nobody has assessed asserts existence alone.

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

The wizard's administrator screen names one person. Sending the review appoints them, in one
transaction that writes them as a live person, saves every setting the wizard collected, and
writes their grants. Once anybody holds `admin:sign_in` over everything, the wizard refuses to
appoint again.

**The Super Admin role confers no capabilities by itself, so the appointment writes them as
grants.** No role implies a capability, Super Admin included, and the appointment stores no role
row at all. What the first administrator can do is exactly the grants in the table below, each over
everything, written by first run and recorded in the ledger. They come in three groups.

- **Running the system**: every `admin:` capability the product declares. Sign-ins, connectors,
  credentials, the stop button, budgets, routing, retention and the rest.
- **Letting the second person in**: `approve:grant`, which is the People screen's grant write,
  the Access review, and authorising a break-glass session. Without it nobody on a fresh install
  could grant anybody anything from the console.
- **Reading how the system is run**: every console screen's own read at the existence and
  configuration planes, the two plane capabilities themselves, the audit entries about
  governing the system, and the reads of the Routing and Classification pages. That says a thing
  is there and how it is set up, and never what is inside it: the routing matrix is which model
  providers are tried in what order, and a classification is which columns are confidential and
  what it takes to see one, not any row of your data.

<!-- checked: what the first administrator is granted at appointment -->
| Capability | Granted for |
| --- | --- |
| `admin:agent_instructions` | running the system |
| `admin:application_log` | running the system |
| `admin:automation` | running the system |
| `admin:budget` | running the system |
| `admin:connector` | running the system |
| `admin:credential` | running the system |
| `admin:erasure` | running the system |
| `admin:export` | running the system |
| `admin:feature` | running the system |
| `admin:field_classification` | running the system |
| `admin:halt` | running the system |
| `admin:learning` | running the system |
| `admin:legal_hold` | running the system |
| `admin:notification` | running the system |
| `admin:operations_alert` | running the system |
| `admin:operations_incident` | running the system |
| `admin:plugin` | running the system |
| `admin:retention` | running the system |
| `admin:routing_matrix` | running the system |
| `admin:schedule` | running the system |
| `admin:session` | running the system |
| `admin:sign_in` | running the system |
| `admin:skill` | running the system |
| `admin:skill_review` | running the system |
| `admin:storage` | running the system |
| `admin:webhook_subscriber` | running the system |
| `approve:grant` | letting the second person in |
| `read:agent` | reading how the system is run |
| `read:artifact` | reading how the system is run |
| `read:audit` | reading how the system is run |
| `read:audit.agent` | reading how the system is run |
| `read:audit.connector` | reading how the system is run |
| `read:audit.credential` | reading how the system is run |
| `read:audit.erasure` | reading how the system is run |
| `read:audit.grant` | reading how the system is run |
| `read:audit.leash` | reading how the system is run |
| `read:audit.legal_hold` | reading how the system is run |
| `read:audit.principal` | reading how the system is run |
| `read:audit.retention` | reading how the system is run |
| `read:audit.routing` | reading how the system is run |
| `read:audit.session` | reading how the system is run |
| `read:audit.setting` | reading how the system is run |
| `read:audit.skill` | reading how the system is run |
| `read:audit.webhook` | reading how the system is run |
| `read:backup` | reading how the system is run |
| `read:budget` | reading how the system is run |
| `read:capability` | reading how the system is run |
| `read:connection_budget` | reading how the system is run |
| `read:connector` | reading how the system is run |
| `read:console.configuration` | reading how the system is run |
| `read:console.existence` | reading how the system is run |
| `read:denial_pattern` | reading how the system is run |
| `read:document` | reading how the system is run |
| `read:evaluation` | reading how the system is run |
| `read:export` | reading how the system is run |
| `read:field_classification` | reading how the system is run |
| `read:grant` | reading how the system is run |
| `read:incident` | reading how the system is run |
| `read:knowledge_coverage` | reading how the system is run |
| `read:model_route` | reading how the system is run |
| `read:overview` | reading how the system is run |
| `read:question` | reading how the system is run |
| `read:queue` | reading how the system is run |
| `read:rate_limit` | reading how the system is run |
| `read:release` | reading how the system is run |
| `read:retention_policy` | reading how the system is run |
| `read:role` | reading how the system is run |
| `read:routing_matrix` | reading how the system is run |
| `read:run` | reading how the system is run |
| `read:scope` | reading how the system is run |
| `read:session` | reading how the system is run |
| `read:skill` | reading how the system is run |
| `read:staff_source` | reading how the system is run |
| `read:usage` | reading how the system is run |

**What the first administrator is not granted, on purpose.**

<!-- checked: what the first administrator is not granted at appointment -->
| Capability | Why not |
| --- | --- |
| `read:console.content` | The content plane is what a person or an agent was told. The screens that need it, Learning and Memory today, do not open. |
| `approve:action` | Approving a suspended action lets an agent act over data the first administrator cannot read. Approvals belong to whoever a department makes its approver. |
| `read:audit.artifact` | A publish entry names an artefact, and who may see an artefact is decided by what it was built from, which an audit grant never asks. |
| `read:audit.entity` | A merge entry names two business records, and the first administrator holds no scope over any business record. |
| `read:audit.memory` | A correction entry names a memory, and who may know a memory exists is decided by the capabilities it was formed under, which an audit grant never asks. |

Nor is any read of the company's data. What a person may read of that comes from grants somebody
writes for them. **If you were expecting the administrator account to be able to read everything,
it cannot**, and that is the invariant the whole system serves rather than an omission in the
wizard.

**A capability added in a later release is granted at the next start, and one you take away stays
away.** An administrator appointed before a capability existed does not hold it, so every start
grants each first administrator whatever of the table above they do not already hold at any scope.
It never grants a capability first run has granted them before, because a revoked grant looks
exactly like a missing one and granting it again would undo the revocation at every restart. It
only touches a live person holding an `admin:sign_in` over everything that first run wrote; an
administrator you made by hand keeps exactly what you gave them.

### Signing in, and what a sign-in grants

After the appointment the finishing screen asks you to sign in through the identity provider, and
binds that sign-in to the first administrator. It does that once: it is open only while no sign-in
is bound anywhere on the install. Every later sign-in is bound by an administrator holding
`admin:sign_in` over everything, and nobody binds their own.

**Binding a sign-in grants that person their own workspace, and nothing else.** Each binding
writes one grant, in the binding's own transaction.

<!-- checked: what binding a sign-in grants -->
| Capability | Over | Granted by |
| --- | --- | --- |
| `read:member.*` | their own things | whoever bound the sign-in |

That opens every member screen, My workspace among them, and no console screen and no workspace
tab. On the finishing screen the binder is first run, so once signed in the first administrator
holds the appointment's grants and this one. A person who already holds a live `read:member.*`
keeps the one they have. A member grant you take away is not given back by a retry or a restart
for the same binding; binding the person again is a new binding and a new grant. A sign-in bound
before binding granted a workspace is granted one at the next start.

**Appoint a second administrator on the first day.** A single administrator is a single point of
lockout, and there is no support desk anywhere that can let you back in, because nobody outside
your organisation holds a credential on your server. The wizard appoints once, so the second is
made by the first: on the People screen, grant them what they need, which can be anything you hold
over no wider a scope than you hold it, `admin:sign_in` over everything included, and then bind
their sign-in.

**What stops you dropping below one.** The Sign-in links screen refuses to unlink the last
administrator who can sign in, and counts under a lock, so two administrators unlinking each other
at once are one unlink and one refusal. The product's role rules also set a floor of two Super
Admins and refuse a role removal below it, but the appointment stores no role row and nothing on an
install calls that rule yet, so the unlink refusal is the one you will meet.

**Emergency access is the installing partner's path and not yours.** There is a break-glass
mechanism in this system and it belongs to a partner employment rather than to a role: a partner
holds nothing standing, and authorising a session for one needs `approve:grant`. No code path
elevates an administrator, and none should. Nothing on an install stores or opens a break-glass
session yet; the Elevation screen shows the rules a session would be held to, with no control.

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

## A second factor, which every administration screen needs

**Every `admin:` and `approve:` screen needs a sign-in that used a second factor.** A password
alone signs you in, and the console's Overview then shows **Assurance: authenticated**. Every
administration screen answers such a sign-in with "I could not find that", whatever grants you
hold. A sign-in with a password and a one-time code shows **Assurance: strong**, and those screens
open.

The system reads the methods from the sign-in token's `amr` claim. The realm this product
imports writes `pwd` there for the password step and `otp` for the one-time code step. Only
`otp` counts as a second factor.

**A realm imported before this release writes nothing there, so nobody on it can reach an
administration screen.** Upgrading does not fix that: the identity provider imports the realm
file only when no realm of that name exists, and it skips the import on every later start. So
an existing realm is changed by hand, once, with the steps below. They add exactly what a fresh
import now contains and change nothing else.

### Turning on a one-time code for your own account

A new account is asked to set one up at its first sign-in. If yours was not, or you skipped it:

1. Open `https://<KEYCLOAK_HOSTNAME>/realms/brain/account`, replacing `<KEYCLOAK_HOSTNAME>`
   with the value of that setting on your server, and `brain` with `INSTALL_OIDC_REALM` if you
   changed it.
2. Sign in with your password.
3. Choose **Account security**, then **Signing in**.
4. Under **Two-factor authentication**, choose **Set up Authenticator application**.
5. Scan the code with an authenticator app on your phone, type the six digits it shows, give the
   device a name, and choose **Submit**.

### Adding the second factor to a realm imported before this release

Run these on the server, as somebody who can use `docker`. Each command is typed in full, with
the parts in angle brackets replaced as described in that step. No password is typed on a
command line: step 3 prompts for it.

1. Find the identity provider's container name:

   ```
   docker ps --filter "ancestor=quay.io/keycloak/keycloak:26.0" --format "{{.Names}}"
   ```

   Use the name it prints as `<keycloak-container>` below. If it prints more than one, this
   server runs more than one identity provider, and the one to use is the one belonging to this
   install. On Coolify, opening the Terminal of this install's `keycloak` service does the same
   as step 2.

2. Open a shell inside it:

   ```
   docker exec -it <keycloak-container> bash
   ```

3. Sign the admin tool in. `<admin-user>` is an administrator of the identity provider's
   `master` realm: the `KEYCLOAK_ADMIN` account, or the account you replaced it with. It asks
   for that account's password.

   ```
   /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user <admin-user>
   ```

4. Check that the realm signs people in through the flow called `browser`:

   ```
   /opt/keycloak/bin/kcadm.sh get realms/brain --fields browserFlow --format csv --noquotes
   ```

   It should print `browser`. If it names another flow, stop here: somebody has
   changed how this realm signs people in, and the steps below would change a flow nobody uses.

5. List the realm's client scopes and copy the id on the `brain-identity` row. Use it as
   `<scope-id>` below.

   ```
   /opt/keycloak/bin/kcadm.sh get client-scopes -r brain --fields id,name --format csv --noquotes
   ```

6. Add the mapper that writes the claim into every token the console receives:

   ```
   /opt/keycloak/bin/kcadm.sh create client-scopes/<scope-id>/protocol-mappers/models -r brain -f - <<'EOF'
   {"name": "amr", "protocol": "openid-connect", "protocolMapper": "oidc-amr-mapper",
    "config": {"id.token.claim": "false", "access.token.claim": "true", "introspection.token.claim": "true"}}
   EOF
   ```

7. List the steps of the `browser` flow:

   ```
   /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r brain --fields id,providerId,authenticationConfig --format csv --noquotes
   ```

   Copy the id on the `auth-username-password-form` row as `<password-step-id>`, and the id on the
   `auth-otp-form` row as `<code-step-id>`. The last column of both rows should be empty. If
   either already shows a value, stop and read that configuration with
   `/opt/keycloak/bin/kcadm.sh get authentication/config/<that-value> -r brain` before changing
   anything, because somebody has configured that step already.

8. Give the password step its reference:

   ```
   /opt/keycloak/bin/kcadm.sh create authentication/executions/<password-step-id>/config -r brain -f - <<'EOF'
   {"alias": "password-method-reference", "config": {"default.reference.value": "pwd", "default.reference.maxAge": "36000"}}
   EOF
   ```

9. Give the one-time code step its reference:

   ```
   /opt/keycloak/bin/kcadm.sh create authentication/executions/<code-step-id>/config -r brain -f - <<'EOF'
   {"alias": "otp-method-reference", "config": {"default.reference.value": "otp", "default.reference.maxAge": "36000"}}
   EOF
   ```

   `36000` is ten hours in seconds, the longest a session may live. **Do not leave it out.** Without
   it the identity provider counts the reference as expiring the second it was earned, so no token
   carries it and nothing changes.

10. Read back what you changed. The first command should now show a value in the last column of
    both rows from step 7. The second should list a row reading `amr,oidc-amr-mapper`.

    ```
    /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r brain --fields providerId,authenticationConfig --format csv --noquotes
    /opt/keycloak/bin/kcadm.sh get client-scopes/<scope-id>/protocol-mappers/models -r brain --fields name,protocolMapper --format csv --noquotes
    ```

11. Leave the container with `exit`. Nothing needs restarting.

### Confirming it worked

1. In the console, choose **Sign out**. Closing the tab is not enough: the identity provider's
   session has to end, or the next sign-in skips the code.
2. Sign in again. Enter your password, then the six digits from your authenticator app when asked.
   If you are not asked for a code, your account has none yet: do the steps under "Turning on a
   one-time code for your own account" above, then sign out and in again.
3. Open **Overview**. It should read **Assurance: strong**, and the administration screens now open.

**Setting up a code is not the same as using one.** The session in which you set one up is still a
password-only session, so the Overview still reads **authenticated** until you sign out and sign in
again with the code. That is expected, and step 1 above is why it is there.

## When the Account Console says "Something went wrong"

**On a realm imported before this release, the identity provider's Account Console refuses
everybody.** It opens, and then shows "Something went wrong" and "HTTP 403 Forbidden". So nobody
can set up a one-time code there, and without a code nobody can open an administration screen.

The cause is in the realm, not in any account. The Account Console signs in as a client of the
identity provider's own called `account-console`, and the realm this product used to import gave
that client no way to put a person's account roles into its sign-in token. The Account Console's
server checks those roles and refuses a token without them. A realm imported from this release
carries them. An existing realm is changed by hand, once, with the steps below. They add one
setting to `account-console` and change nothing about the console, the API or any sign-in to them.

### Setting up a person's one-time code without the Account Console

This works on any realm, repaired or not. It asks the person to set up a code the next time they
sign in.

1. Open the identity provider's administration console: the address of your sign-in page, with
   the path replaced by `/admin/`. Sign in as an administrator of the `master` realm.
2. In the realm list at the top of the left-hand menu, choose `brain`.
3. Choose **Users**, then choose the person's username.
4. On the **Details** tab, open **Required user actions** and choose **Configure OTP**.
5. Choose **Save**.
6. The person signs in. After their password they are shown a code to scan with an authenticator
   app, and they type the six digits it shows.
7. The person signs out and signs in again, this time entering the code. As "Setting up a code is
   not the same as using one" above explains, only that second sign-in counts as a second factor.

### Repairing the Account Console on a realm imported before this release

Run these on the server, as somebody who can use `docker`. Every command is typed exactly as it is
written: nothing in it needs replacing, and the ids are found by the commands themselves. No
password is typed on a command line: step 3 asks for it.

1. Check there is exactly one identity provider container on this server:

   ```
   docker ps --filter "ancestor=quay.io/keycloak/keycloak:26.0" --format "{{.Names}}"
   ```

   It should print one name. If it prints more than one, do not use step 2: open the Terminal of
   this install's `keycloak` service in Coolify instead, which puts you in the right container,
   and carry on at step 3.

2. Open a shell inside it:

   ```
   docker exec -it "$(docker ps --filter "ancestor=quay.io/keycloak/keycloak:26.0" --format "{{.Names}}")" bash
   ```

3. Sign the admin tool in. The username is the temporary administrator's, which the container
   already knows; it asks for that account's password. If you have deleted the temporary
   administrator, as this page advises, type your own administrator's username in place of
   `"$KC_BOOTSTRAP_ADMIN_USERNAME"`.

   ```
   KC=/opt/keycloak/bin/kcadm.sh
   $KC config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME"
   ```

   `localhost:8080` is the identity provider's own address inside its container, so it is the same
   on every server.

4. Find the two clients' ids:

   ```
   CONSOLE=$($KC get clients -r brain --fields id,clientId --format csv --noquotes | grep -E ',account-console$' | cut -d, -f1)
   ACCOUNT=$($KC get clients -r brain --fields id,clientId --format csv --noquotes | grep -E ',account$' | cut -d, -f1)
   echo "account-console: $CONSOLE"
   echo "account: $ACCOUNT"
   ```

   Each line should end in one id. If either is empty, stop: this realm has no Account Console to
   repair.

5. Read what `account-console` already has:

   ```
   $KC get clients/$CONSOLE/protocol-mappers/models -r brain --fields name,protocolMapper --format csv --noquotes
   $KC get clients/$CONSOLE/scope-mappings/clients/$ACCOUNT -r brain --fields name --format csv --noquotes
   $KC get roles/default-roles-brain/composites/clients/$ACCOUNT -r brain --fields name --format csv --noquotes
   ```

   The first should list `audience resolve,oidc-audience-resolve-mapper` and no row ending in
   `oidc-usermodel-client-role-mapper`. The second should list `manage-account` and `view-groups`.
   The third should list `manage-account` and `view-profile`. If the second or third lists neither
   `manage-account` nor `view-profile`, stop: somebody has changed who may use the Account Console,
   and the step below would not be enough.

6. Add the setting that writes a person's account roles into the Account Console's token. Type
   the quotes around `EOF` as shown; they keep the shell from changing `${client_id}`, which the
   identity provider fills in itself.

   ```
   $KC create clients/$CONSOLE/protocol-mappers/models -r brain -f - <<'EOF'
   {"name": "account roles", "protocol": "openid-connect", "protocolMapper": "oidc-usermodel-client-role-mapper",
    "config": {"usermodel.clientRoleMapping.clientId": "account", "claim.name": "resource_access.${client_id}.roles",
               "jsonType.label": "String", "multivalued": "true", "access.token.claim": "true",
               "id.token.claim": "false", "introspection.token.claim": "true"}}
   EOF
   ```

7. Only if the first list in step 5 had no `audience resolve` row, add it too:

   ```
   $KC create clients/$CONSOLE/protocol-mappers/models -r brain -f - <<'EOF'
   {"name": "audience resolve", "protocol": "openid-connect", "protocolMapper": "oidc-audience-resolve-mapper",
    "config": {"access.token.claim": "true", "introspection.token.claim": "true"}}
   EOF
   ```

8. Read it back. It should now list both `audience resolve,oidc-audience-resolve-mapper` and
   `account roles,oidc-usermodel-client-role-mapper`.

   ```
   $KC get clients/$CONSOLE/protocol-mappers/models -r brain --fields name,protocolMapper --format csv --noquotes
   ```

9. Leave the container with `exit`. Nothing needs restarting.

Then open the Account Console again, or reload it if it is still open. It should show the person's
details rather than "Something went wrong". If it still does not, sign out of it and sign in again,
so it is given a token minted after the change. From there, "Turning on a one-time code for your
own account" above works as written.

**What is checked and what is not.** That a realm imported from this release gives the Account
Console the roles and audience its server checks, that the product's own clients are given no role
claims by it, and that the realm declares every client and role this needs, are held by
`test_keycloak_realm.py` against the realm file. The commands above were written from the identity
provider's 26.0 source and admin documentation, and have not been run against a server.

## When a new password is never asked for

**On a realm imported before this release, the identity provider skips most of what it is asked
to make a person do.** What people see:

- Somebody given a temporary password signs straight in and is never asked to choose their own, so
  the password an administrator typed stays theirs.
- On an install that sends email, a forgotten-password link finishes without asking for a new
  password, and the old one is still the one that works.
- In the Account Console, under **Signing in**, **Update** beside a password and **Delete** beside a
  one-time code both come back to the same page with nothing changed.
- Somebody an administrator asked to verify their email or update their profile is never asked.

The cause is in the realm, not in any account. Each of those is a *required action*, and the
identity provider runs one only if the realm registers it: any other is skipped, with a warning in
its log and nothing on the screen. The realm this product used to import registered two, **Configure
OTP** and **Delete Account**, and Delete Account is off. A realm imported from this release
registers the eleven the identity provider registers on a realm it creates itself, with the same
settings, and still puts only one of them in front of every new account: the one-time code.

**It also turns off the realm's email check, and step 5 below does the same.** That setting was on
and did nothing, because the step it needs was not registered. Once **Verify Email** is registered,
the setting stops every person whose address is not marked verified at their next sign-in until
they click a link in an email, and this product does not set up the identity provider's email. So
with the setting on, nobody could finish signing in.

### Registering the required actions on a realm imported before this release

Run these on the server, as somebody who can use `docker`. Every command is typed exactly as it is
written: nothing in it needs replacing. No password is typed on a command line: step 3 asks for it.

1. Check there is exactly one identity provider container on this server:

   ```
   docker ps --filter "ancestor=quay.io/keycloak/keycloak:26.0" --format "{{.Names}}"
   ```

   It should print one name. If it prints more than one, do not use step 2: open the Terminal of
   this install's `keycloak` service in Coolify instead, which puts you in the right container,
   and carry on at step 3.

2. Open a shell inside it:

   ```
   docker exec -it "$(docker ps --filter "ancestor=quay.io/keycloak/keycloak:26.0" --format "{{.Names}}")" bash
   ```

3. Sign the admin tool in. It asks for the temporary administrator's password. If you have deleted
   the temporary administrator, as this page advises, type your own administrator's username in
   place of `"$KC_BOOTSTRAP_ADMIN_USERNAME"`.

   ```
   KC=/opt/keycloak/bin/kcadm.sh
   $KC config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME"
   ```

4. Read what the realm registers now:

   ```
   $KC get authentication/required-actions -r brain --fields alias,enabled,defaultAction,priority --format csv --noquotes
   ```

   On a realm imported before this release it prints two rows, `CONFIGURE_TOTP,true,true,10` and
   `delete_account,false,false,60`. If it prints more, somebody has registered some by hand. Step 6
   leaves every action already registered as it is and registers only the rest.

5. Turn off the realm's email check:

   ```
   $KC get realms/brain --fields verifyEmail --format csv --noquotes
   $KC update realms/brain -s verifyEmail=false
   ```

   The first command prints `true` on a realm imported before this release. Leave the second out
   only if this install already sends email from the identity provider and you want every person to
   verify their address: each person whose address is not marked verified is then asked to at their
   next sign-in.

6. Register every action the realm does not have yet. Each entry in the list is the action, the
   name the admin console shows for it, whether it is on, and its place in the order, all as the
   identity provider sets them on a realm it creates:

   ```
   REGISTERED=$($KC get authentication/required-actions -r brain --fields alias --format csv --noquotes)
   for ENTRY in \
     "TERMS_AND_CONDITIONS|Terms and Conditions|false|20" \
     "UPDATE_PASSWORD|Update Password|true|30" \
     "UPDATE_PROFILE|Update Profile|true|40" \
     "VERIFY_EMAIL|Verify Email|true|50" \
     "delete_account|Delete Account|false|60" \
     "webauthn-register|Webauthn Register|true|70" \
     "webauthn-register-passwordless|Webauthn Register Passwordless|true|80" \
     "VERIFY_PROFILE|Verify Profile|true|90" \
     "delete_credential|Delete Credential|true|100" \
     "update_user_locale|Update User Locale|true|1000"
   do
     ALIAS=$(echo "$ENTRY" | cut -d'|' -f1)
     NAME=$(echo "$ENTRY" | cut -d'|' -f2)
     ENABLED=$(echo "$ENTRY" | cut -d'|' -f3)
     PRIORITY=$(echo "$ENTRY" | cut -d'|' -f4)
     if echo "$REGISTERED" | grep -q -E "^$ALIAS\$"; then
       echo "already registered: $ALIAS"
     else
       $KC create authentication/register-required-action -r brain -s "providerId=$ALIAS" -s "name=$NAME" &&
       $KC update "authentication/required-actions/$ALIAS" -r brain -s "enabled=$ENABLED" -s defaultAction=false -s "priority=$PRIORITY" &&
       echo "registered: $ALIAS"
     fi
   done
   ```

   Every entry should print `registered:` or `already registered:`. Registering puts an action on,
   last in the order, and the second command then gives it the identity provider's own setting and
   place, which is why terms and conditions and account deletion end up off. If an entry prints an
   error instead, read it before going on: `Required Action Provider with given providerId not
   found` on the two `webauthn` entries means this server has security keys turned off, and those
   two can be left unregistered.

7. Read it back:

   ```
   $KC get authentication/required-actions -r brain --fields alias,enabled,defaultAction,priority --format csv --noquotes
   ```

   It should print these eleven rows. Only `CONFIGURE_TOTP` has `true` in the third column.

   ```
   CONFIGURE_TOTP,true,true,10
   TERMS_AND_CONDITIONS,false,false,20
   UPDATE_PASSWORD,true,false,30
   UPDATE_PROFILE,true,false,40
   VERIFY_EMAIL,true,false,50
   delete_account,false,false,60
   webauthn-register,true,false,70
   webauthn-register-passwordless,true,false,80
   VERIFY_PROFILE,true,false,90
   delete_credential,true,false,100
   update_user_locale,true,false,1000
   ```

8. Leave the container with `exit`. Nothing needs restarting.

**What changes for the people on this realm.** Whatever was asked of somebody and skipped until now
is asked at their next sign-in: a person still on a temporary password chooses their own, and a
person an administrator asked to verify an email or update a profile is asked to. A person whose
account has no first name, last name or email is asked for them once, because **Verify Profile**
holds every account to the identity provider's user profile, which requires all three unless
somebody has changed it. A person with nothing outstanding and a complete profile signs in as
before.

To confirm it worked, open the Account Console, choose **Account security**, then **Signing in**,
and choose **Update** beside your password. It now shows a form for a new password rather than
coming straight back to the page. Leaving that form without submitting it changes nothing.

**What is checked and what is not.** That a realm imported from this release registers every
required action the identity provider registers on a realm it creates, with its settings, puts only
the one-time code in front of every new account, and does not ask everybody to verify an email it
has no mail server to send, is held by `test_keycloak_realm.py` against the realm file. The commands
above were written from the identity provider's 26.0 source and admin documentation, and have not
been run against a server.

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
| That the role rules refuse a removal below two Super Admins | the same test; nothing on an install calls that rule yet |
| That the last administrator who can sign in cannot be unlinked | `test_sign_in_links.py` and `test_session_routes.py` |
| What each source is trusted to assert | `test_staff_source.py`, against the trust table |
| Which four sources the wizard offers, what each writes, whether each needs a location, and which are signed in to | `test_authentication_guide.py`, by answering the wizard's own screen and reading its settings, and by asking the trial route's own source reader |
| Which sources the product reads and the wizard does not offer | `test_authentication_guide.py`, against the selectable sources |
| The headings a spreadsheet is read by | `test_authentication_guide.py`, by reading a sheet under each heading |
| That a directory is chosen, signed in to and read, and a spreadsheet chosen and read, before anything is written | `test_setup_staff_routes.py`, against a stand-in directory |
| What to register at each directory, as the screen shows it | **nobody. The table above is kept true by hand against `brain.connectors.staff_directories.REGISTRATION`.** |
| Which capabilities the first administrator is granted and for what, and which they are not | `test_authentication_guide.py`, against `GRANTED_AT_APPOINTMENT`; that the appointment writes exactly that set is `test_first_administrator.py`, against a database, in CI |
| That a capability taken away from the first administrator is not given back at a start | `test_administration_reconciliation.py`, against a database, in CI |
| The grant a binding writes | `test_authentication_guide.py`, against the statement the binding executes; what it opens is `test_plane_scope.py` |
| The four identity settings and their defaults | `test_install_docs.py`, through the configuration guide |
| That a sign-in with a one-time code is counted as a second factor, a password alone is not, and both last the session | `test_keycloak_realm.py`, against the realm file and the code that reads the token |
| The commands for adding the second factor to a realm imported before this release | **nobody. They were written from the identity provider's 26.0 source and admin documentation and have not been run against a server.** |
| That a realm imported from this release registers every required action the identity provider registers itself, with its settings, and puts only the one-time code in front of everybody | `test_keycloak_realm.py`, against the realm file |
| The commands for registering the required actions on a realm imported before this release | **nobody. They were written from the identity provider's 26.0 source and admin documentation and have not been run against a server.** |
| **Everything else on this page** | **nobody. Prose, kept true by hand.** |

## Task ids

M42.2.7, M42.5.7
