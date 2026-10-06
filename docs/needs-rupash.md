# Needs Rupash

Decisions and access I cannot resolve alone. Served at `/build/needs-rupash`.

**48 items are open: 172,** whether a failing automation's pause also stops that agent's questions, **171,** whether a browser test counts as proof that a task works, **170,** which parts of an agent the builder lists as sections of its own, **169,** when to switch on spending limits that really stop requests, **167,** whether a chat room or channel belongs to exactly one agent, **166,** whether an agent's own run may send something without a person approving it, **165,** whether an administrator may choose how a connected source's own permissions are followed, **164,** whether your install runs an antivirus on uploads, **163,** the short list of what stops tasks being proved on your install, **162,** whether a new agent may be put on your website's chat widget, **161,** what "rehearsed" means before a skill can be approved, **160,** whether a department's administrator may stop one of that department's agents, **159,** what the Brain says when a client's name matches two records you can both see, **158,** whether an automation's canvas may have a step that runs an agent, **157,** one line for your install's database pooler, **156,** what your maintenance portal is, **155,** recognising the same client across your systems, **151,** connecting Slack as a source of answers, **154,** a one-time server change for the sealed sandbox, **153,** how much of a question written in Chinese is hidden before it goes to an outside model, **150,** connecting Google Drive, **148 and 149,** connecting your Laravel database and your developer's part of it, **152,** Lark Base and Wiki through Connect Lark, **143 to 146,** connecting Google Analytics, Search Console, Cloudflare and your domains, **142,** connecting WhatsApp, **141,** connecting Telegram, **140,** connecting Microsoft Teams, **139,** whether the website widget's answers are written by the model or are the published passages, **138,** whether a Laravel client record is visible to one department or several, **137,**
which of your systems holds client projects and their tickets, **136,** whether memory
disagreeing with a connected system is settled by how memory is built, **134,** connecting the Slack channel, **133,** Search Console's indexing issues, **132,** connecting the email channel, **130,** whether a staff list anybody with its link can edit makes sign-in accounts, **131,** making staff accounts work on your install, **127 to 129,** things
for you to do (switch on the Lark chat channel, connect Xero, HubSpot and Freshdesk, and let the
vault open itself), **121 to 124,** whose conversations an agent's page lists, where uploaded documents are stored, a task
that names a table library, and the automation canvas, each with my recommendation, **and 91,** the
checks only you can do on your install; it waits for the Knowledge upload grants (item 105) to land.
Each says in plain terms what it is, what I recommend, and every step.

# Open

## 172. When an automation keeps failing and is paused, should its agent's questions stop too?

**In plain terms:** you can now stop one agent on its own (the stop screen's agent scope), and a stop on
an agent refuses that agent's questions and its automations. Separately, when an automation fails
repeatedly the Brain pauses it, so it stops running on its schedule until a person looks. The pause
builds the same kind of stop, but today only the automation's schedule is held: the agent keeps
answering people's questions.

**Option A: a pause holds the schedule only (what is built).** A failing automation is a fault in one
job. People can still ask the agent things, and the steward is told the automation was paused.

**Option B: a pause also stops the agent's questions.** Safer if a failing automation might mean the
agent itself is misbehaving, but it takes the agent away from everybody for a fault in one job, which is
wider than a failing automation asked for, and it would stay stopped until somebody lifts it.

**My recommendation:** A. A person who wants the whole agent stopped has the stop screen for that, with
a written reason.

**What I need from you:** nothing, or reply "172: B".

## 171. Does a test that drives a real browser count as proof that a task works?

**In plain terms:** a task is only closed when a test names it, and until now the check that enforces
that read only the Python tests and the console's own tests. Four tasks about the console proving itself
in a browser (two tabs refreshing, a page leaking nothing internal) were proved by the browser tests
under `e2e/`, which the check never read, so it called them unproved and the build turned red. The
browser tests are real: they open the product in a browser and press things, which is closer to your
install than a test over stand-ins.

I have made the check read the browser tests under `e2e/specs` and `e2e/lib` (not the page stubs under
`e2e/pages`, which assert nothing), the same way it already reads the console's tests. Three deliberate
breakages of that rule were each caught by a test.

**Option A: browser tests count (what is built).** A task can be closed by a browser test that names it,
as it can by a Python test or a console test.

**Option B: they do not.** Those four tasks would need a Python test naming them, which would claim a
Python test proves something that only a browser can show.

**My recommendation:** A. A browser test is stronger evidence than a unit test, and the check still
refuses a task that no test names.

**What I need from you:** nothing, or reply "171: B".

## 170. Which parts of an agent does the builder list as sections of its own?

**In plain terms:** your plan lists eleven sections in the agent builder. Seven were built from the
start, and "Connected sources" has now been added as the eighth. Three are not built, for a reason the
builder's own rule gives: a section has to be a part of the agent's saved definition (its "manifest"),
and these are not.

- **Workflows (automations).** Automations are installed on each agent from the gallery, one at a
  time, and that already works. A "workflows" part of the definition would be a second description of
  the same thing.
- **Memory.** What an agent remembers and learns comes from its own runs, which a template cannot
  know in advance. It is already set on the agent's own Memory tab (including pausing learning).
- **Channels (where it answers).** Decided per install when the agent is published, and changed later
  from the agent's page (item 162). It is not a property of the template.

**Option A: leave them out of the builder's sections** and let the builder link to where each is
already set (the Automations gallery, the Memory tab, the publish step's channel choice). No change to
what the product stores.

**Option B: add them as parts of the definition.** A template could then carry default workflows,
memory settings and channels. It needs a change to the stored definition (a database change), and a
decision on which defaults, and it makes two places hold the same setting.

**My recommendation:** A. Each of the three is already set in exactly one place; B would add a second.

**What I need from you:** nothing, or reply "170: B".

## 169. When should spending limits start to really stop requests?

**In plain terms:** you chose how a spending limit should behave: warn first, then stop until the next
period. Departments and agents have limits stored and versioned, and your screens show allowances. But
**nothing enforces them today**: a department can spend past its limit with nothing stopping it, because
the part that decides "this request is over the limit" is built and tested and not yet called by any
request. That is the opposite of the risk you might expect, and it means no agent has ever been held at
a limit.

I am building enforcement **switched off**, as every new feature ships. While it is off, each request
that *would have been stopped* is noted (the limit and the department, never the question), and the
Spend screen shows those, so you can see what switching it on would do before it does it. When it is on,
the first request over a limit opens a stop, warns the limit's owner, and every request in that
department gets a plain sentence that a spending limit has been reached, until the next period starts.
If the Brain cannot read the limits or the spend, requests are answered as they are today: a fault in
the budget records never stops people working.

**Option A: switch it on after you have seen a week of "would have stopped" figures.** I bring you
the figures and you say when.

**Option B: switch it on as soon as it ships.** Every limit already set starts to bite at once.

**Option C: keep it off.** Limits stay warnings on the screens.

**My recommendation:** A. Switching it on blind could start refusing requests on the day it ships.

**What I need from you:** nothing yet. I will bring the figures after the first week, or reply "169: B"
or "169: C".

## 167. Does a chat room or channel belong to exactly one agent?

**In plain terms:** the Brain has the idea that a person can wire a chat room (say a Lark group) to one
agent, and that the room then answers as that agent. The code to refuse putting a second agent on a
room already taken exists (M20.4.5), but nothing stores which room belongs to which agent, so it checks
against nothing today. Where an agent may be asked (its channels, item 162) is a separate thing: many
agents can be asked in the same place.

**Option A: one room, one agent.** A room (a channel, and optionally one room in it) belongs to exactly
one agent. Publishing an agent onto a room already taken is refused, without saying which agent has it.
It needs a small table and a control to bind a room to an agent.

**Option B: by department.** A department's rooms go to its agent. A room with people from several
departments has no clear owner, so I would not choose this.

**Option C: no exclusive rooms.** Anyone may ask any agent they can see by name. A room may have a
default agent that anybody can change freely, and the refusal is dropped.

**My recommendation:** A. It is the shape the Brain's selector already resolves, and a refusal there
leaks nothing. C can be added later without undoing it. I will not build it until you answer.

**What I need from you:** reply "167: A", "167: B" or "167: C".

## 166. May an agent's own run send something without a person approving it?

**In plain terms:** agents now run with tools they can call while they answer (the agent runtime).
When an agent proposes an action that changes something outside the Brain, such as replying to a
ticket, the Brain holds it for a person to approve, and only an approved action is sent. That is how it
is built today, at every autonomy level. Your plan has agents earning higher levels through evidence,
and at the higher levels an action could be sent with no person asked each time. **No agent has earned a
higher level yet**, and a model's own words sending a real message or changing a real record with nobody
asked is a bigger step than anything else in the runtime.

**Option A: always held, for now.** A run's actions always wait for a person. Higher levels are
reconsidered once agents have a track record on your install.

**Option B: sent without approval at the higher levels.** Above the assisted level, an action the agent
proposes is sent at once, through the same record of every operation and the same checks of who may do
what. Each send is on the ledger, and you can stop any agent from the Stop screen.

**My recommendation:** A. Nothing is lost by waiting, and if you want B later it is a small change.

**What I need from you:** nothing, or reply "166: B".

## 165. May an administrator choose how a connected source's own permissions are followed?

**In plain terms:** some sources keep their own rules about who may see what (a shared folder, a
private channel). For each connected source the Brain follows those rules in one of two ways: it asks
the source about the person on every question, or it keeps a copy of the source's rule and checks it
itself. Today which way is fixed by the connector as it was written, and the screen shows it. Your plan
says an administrator *sets* it per connector (M33.5.1.3), and that choice was narrowed in the code
without asking you. The Brain's own grants always apply as well, whichever way is used.

**Option A: settable, but only towards stricter.** The screen offers the ways the connector supports,
and an administrator may switch a source to a stricter one or off the source's rules altogether
(leaving only the Brain's own grants); a way the connector cannot do is never offered. Each change is
on the ledger.

**Option B: keep it fixed by the connector.** The screen keeps saying which way it is, and changing it
means a new version of the connector.

**My recommendation:** A. It is what you asked for, and it can only ever make a source more careful.
I will not build it until you answer.

**What I need from you:** reply "165: A" or "165: B".

## 164. Should your install scan uploaded files with an antivirus?

**In plain terms:** every uploaded file is already checked for the shapes that attack a file reader
(macros, scripts, broken archives), on every install. What no install has yet is an antivirus that
recognises known malware. The Brain can use one (ClamAV, a free antivirus): set it on and every upload
is scanned, and if the scanner is down an upload is refused rather than read unscanned. **But nothing
in the product installs ClamAV yet**, so today the setting would point at nothing. One task waits on
this (M7.1.3, a known test virus is refused).

ClamAV holds its virus database in memory, commonly 1 to 1.5 GB; I would measure it on your server before you switch it on. Your server has roughly
**376 MB** of its memory budget unclaimed after the sign-in service fix, so it does not fit today
without taking memory from something else.

**Option A: add ClamAV as an optional service, switched on later.** I build it the same way as the
privacy detector (one word on Settings starts it, nothing changes until then), and you switch it on when
item 120's memory work or a larger server makes room.

**Option B: no antivirus.** Uploads keep the structural check only; the three checks are marked as not
applying to your install, and the page says what that means: a known virus inside an ordinary document
is not recognised.

**My recommendation:** A. The build costs nothing on your server until it is switched on, and every
other company that installs the Brain gets the choice too.

**What I need from you:** reply "164: A" or "164: B".

## 163. What stops tasks being proved on your install: one list

**In plain terms:** a task is only counted as done once the install's own checks for it pass, on two runs.
After the last count (#422), the checks below could not pass on your install, for reasons only you can
change. Each line is one action and points to the item with its steps. Nothing here is new to decide.

1. **Switch on the optional services (item 131, part 2).** On **Settings**, set *Optional services this
   server runs* to `presidio,langfuse` and save. That starts the privacy detector and the trace ledger,
   and the release then reports the per-kind connection pools. Unlocks 4 tasks. Item 131's server steps come first:
   reply "131: do the server steps" and I do them.
2. **Save a mail relay (items 131 and 132).** On **Notifications**, fill in *Email relay* once. Unlocks
   2 tasks: Forgot password's email and the email channel.
3. **Choose where uploaded documents are stored (item 122).** Unlocks 2 tasks.
4. **Connect your own accounts (items 126 and 128).** 27 connector tasks and 4 channel tasks have passed
   only on accounts made up for the check. Each closes once its source or channel is connected with your
   own account, in item 126's order.
5. **Add the bot to your digest group (item 127).** The evening digest has nowhere to go until then.
   Unlocks 4 tasks.
6. **Ask one real question in Lark** after item 127. Unlocks 1 task.
7. **Antivirus: item 164.**

**What I need from you:** nothing new; work down the list when you can, and tell me after each step so I
run the checks again.

## 162. May a new agent be put on your website's chat widget?

**In plain terms:** an agent now answers only on the channels switched on for it, and the switch offers
a channel only where the agent is allowed to work on it (M13.7.4 and M39.2.4.2). The console and the
API answer the person asking, in their own signed-in session, so they are offered by name. Your
website's chat widget is different: it answers visitors who are not signed in, and you decided it gives
public knowledge only and never asks anybody to log in (item 26). Nothing yet says which agents are
safe to face the public, so **the switch does not offer the widget at all**. An agent already on it
keeps it and can be switched off it; no agent can be newly put on it.

**Option A: allow it for an agent that can read only public knowledge.** The widget is offered on an
agent whose ceiling holds nothing but the knowledge you marked public, checked by the same rule that
decides what any channel may carry. An agent that can read anything more is never offered it.

**Option B: keep it as built.** The widget keeps whichever agents answer on it today, and a new one is
put there only by a change to the product.

**My recommendation:** A. It keeps item 26's promise by construction, and lets you replace the website's
agent without a release. I will not build it until you answer.

**What I need from you:** reply "162: A" or "162: B".

## 161. Before a skill is approved, its examples are rehearsed: what "rehearsed" means for now

**In plain terms:** your plan says a skill's examples are rehearsed before anyone may approve it
(M12.3.4). A skill will carry its examples inside its own file, each a task and the tools it should
need, so a new version brings its own. Approving a version will be refused until its examples have
been rehearsed against that exact version.

Today a rehearsal asks no AI model anything. It checks that an agent holding the skill can reach every
tool each example needs, for the person approving it, and records that. It does not yet judge whether
the answer an example would get is a good one.

**That is the narrowing.** Agents can now run with tools through one path (the agent runtime, being
landed now), so the next step is a rehearsal that actually runs each example and shows the approver
what it did, with nothing sent or changed. The record is built so that result can be added to it
later.

**Option A: build the reach check now, and add the real run once the agent runtime is live.**
Approval is checked for what it can be today, and the screen says what was and was not checked.

**Option B: hold approval-by-rehearsal until examples can be run for real.** Skills are approved as
today until then.

One more choice inside A: **a skill version with no examples at all is not held**, so the skills
already in the library can still be reviewed. That also means somebody could leave examples out to
skip the rehearsal. The alternative is to require at least one example on every new version.

**My recommendation:** A, and versions without examples not held for now. I am building it that way.

**What I need from you:** nothing, or reply "161: B", or "161: A, but require examples".

## 160. May a department's administrator stop one of that department's agents?

**In plain terms:** the Stop control can now stop one agent on its own (M13.7.3), as well as a
connector, a department, a person or everything. Today only an administrator for the whole company can
stop a single agent, because a stopped agent is recorded without a department, and a department's
administrator may only stop things inside their department.

**Option A: allow it.** When a department's administrator presses Stop on an agent, the Brain looks up
the agent's department at that moment and records it, so the stop is theirs to make and theirs to lift.
An agent with no department, or one shared across departments, stays a company-wide administrator's to
stop.

**Option B: keep it as built.** A department's administrator who wants an agent stopped stops their
whole department, or asks a company-wide administrator.

**My recommendation:** A. A department's administrator is the person nearest to an agent misbehaving
in their department, and stopping is the safe direction. I will not build it until you answer.

**What I need from you:** reply "160: A" or "160: B".

## 159. When a client's name matches two records you can both see, the Brain says so

**In plain terms:** ask "what does Acme owe us?" when two client records answer to "Acme" (one in
Xero, one in HubSpot, say) and the Brain has not decided whether they are the same client. Today it
gives the same sentence it gives when there is no such client at all. Your plan asks for the opposite
(M14.6.5): say that the name matches more than one client, and never add their figures together.

The rule it changes is one of the Brain's strictest: a person is never told *which kind* of nothing
happened, because "two records matched" and "nothing exists" must not be told apart when one of the
records is hidden from them. **That still holds.** The new sentence is given only when every matching
record is one the person may already read, so it tells them nothing they could not look up. If one of
the two is hidden from them, they are answered from the one they can see, exactly as if the hidden one
did not exist, and a test checks the two replies are identical.

Whoever may confirm a merge also gets a link to the "Possible duplicates" review; everybody else gets
the plain sentence.

**My recommendation:** allow it, as described. I am building it that way.

**What I need from you:** nothing, or reply "159: no" to keep the old single sentence.

## 158. May an automation's canvas have a step where an agent thinks? (optional)

**In plain terms:** every agent now runs through one path, with tools it may call while it answers
(M13.7.1). The plan says an automation "enters the same agent runtime". The automation canvas you
have today is deliberately step by step: every step does one fixed thing, and no step asks a model
anything, so a flow does the same thing every time it runs. That was decided when the canvas was
built (item 30 and item 124).

So an automation reaches an agent this way instead: **a schedule or a trigger starts an agent**, at
the reach of the person the automation runs for, and the agent's answer is what the flow produces.
Nothing changes on the canvas.

**Option A, as built: the canvas stays fixed steps, and an agent is started by a schedule or a
trigger.** A flow is predictable, and its steps can be read and checked.

**Option B: add an "ask an agent" step inside a canvas.** A flow can then decide things midway, which
also means it can do something different each time it runs, and its runs are harder to check.

**My recommendation:** A. Nothing waits on this; I am building A.

**Two things I decided for you while building, as you asked me to decide routine items** (tell me if
either is wrong):

- **Which channels an agent answers on.** An agent now answers only on the channels an administrator
  switched on for it (M13.7.4). Agents that already exist keep every channel they reach today, so
  nobody loses anything. A new agent starts with none, and the agent builder asks which channels to
  switch on, so a new agent is never silent without anybody noticing. Asking for an agent on a channel
  it is not on gets exactly the same reply as asking for an agent that does not exist.
- **Where the client-matching weights are kept.** Your decision (f) put them in the exports volume. On
  an install whose compose file Coolify stores, a release cannot add that volume to the application,
  so the weights would never be written. They are kept in the Brain's own settings instead, readable
  only by the worker and by whoever may confirm a merge. The offline matcher still writes its export to
  the volume where the full install has one.

**What I need from you:** nothing, or reply "158: B" if you want the canvas step.

## 157. One line for your install's database pooler

**In plain terms:** the Brain reaches your database through a pooler that lends out a fixed number of
connections. The pooler counted its limit per login, and the application uses two logins, so on a busy
day it could open twice the 20 connections the Brain plans for. The product now caps it at 20 across
logins (#378). **Your install does not have that cap yet, because a release never edits the copy of
the compose file Coolify keeps.** Nothing is broken today; this keeps it that way under load.

**Option A: I do it.** Over SSH, through the tunnel to Coolify, I add the one line below to the
`pgbouncer` service's `environment` in Coolify's copy, beside `DEFAULT_POOL_SIZE`, and redeploy once.
Requests wait at the pooler for a moment while it restarts.

```yaml
      MAX_DB_CONNECTIONS: "20"
```

**Option B: you do it.**

1. Open Coolify and choose the Brain application.
2. Open the compose file editor.
3. Find the `pgbouncer` service, then the line `DEFAULT_POOL_SIZE: "20"` under `environment`.
4. Below it, add the line above with the same indentation.
5. Press Save, then Redeploy.

**My recommendation:** A.

**What I need from you:** reply "157: A" or "157: B, done".

## 156. What is your "maintenance portal"?

**In plain terms:** the Maintenance Agent you asked for (Wave 3, M38.5.3 and M39.8.7) answers a
maintenance question from your uploaded maintenance knowledge and the ticket desk, and the plan names
a third source: "the maintenance portal" (M11.9.9). Nothing the Brain reads today is one, and I will
not guess what it is. It is closely tied to item 137 (where client projects live).

**Option A: maintenance records in your Laravel application.** If each website's maintenance plan,
its scheduled work and its history sit in the Laravel database, whoever looks after it adds one more
read-only view for maintenance beside the clients and staff views (and the project view, if you
choose B in item 137). I write the view for them; the Brain reads only what it shows.

**Option B: a separate system with its own web address and API.** If the portal is another product
(a maintenance or hosting dashboard with an API), it connects through the new "Add an API" screen:
you give its API description, a second person approves it, and it is read like any other source.

**Option C: there is no separate portal.** If maintenance lives in Freshdesk tickets and your uploaded
maintenance documents, the Maintenance Agent uses those two and nothing more, and I drop the third.

**My recommendation:** tell me which is true today; if it is A, choose it together with item 137's B,
so one change in Laravel adds both views.

**What I need from you:** reply "156: A", "156: B (the portal's name)" or "156: C".

## 155. Recognising the same client across your systems: two choices before it is switched on

**In plain terms:** the Brain can tell that "Acme Pte Ltd" in Xero, "ACME" in HubSpot and a Freshdesk
requester at acme are the same client, so a question about one client gathers what every connected
system knows (Wave 3, M14). The matching code is written and nothing uses it yet. Before it runs, two
choices are yours.

**1. A little more in the index.** You set the rule that connectors never copy your data: the Brain
keeps only a small index and reads the rest live when somebody asks. Matching clients needs one more
thing in that index for each record: a scrambled fingerprint of its email address, phone number or
company registration number, made with a secret key the Brain keeps in its vault. The fingerprint
cannot be turned back into the address or number, and nothing else is copied.

- **Option A:** allow the fingerprints in the index, so clients are matched in the background.
- **Option B:** no fingerprints. Clients are matched only by name, which finds far fewer and needs a
  person to confirm almost every match.

**My recommendation: A.** It keeps your rule's purpose (none of your data is copied in readable form)
and makes matching useful.

**2. Matching without a person, for the clearest cases only.** When two records share the same email
address or registration number and neither carries money (no invoices or deals), the Brain can join
them by itself, recorded and reversible with one press. Anything less certain, and anything touching
money, waits for a person.

- **Option A:** join the clearest cases automatically, with a switch to turn it off.
- **Option B:** a person confirms every match.

**My recommendation: A.** It saves confirming hundreds of obvious matches, and anything involving
money always waits for a person.

**What I decided myself (tell me if you disagree):**

- Only an Owner or an Admin may confirm or undo a match, as a new permission you can grant to others.
- The secret key for the fingerprints is created by the installer on every install.
- Each connector says in its own description which records carry money.

**What I need from you:** reply "155: 1A 2A" (my recommendation), or the options you prefer.

## 151. Connect Slack as a source (ready now)

**In plain terms:** the Brain can now answer from Slack messages, and each person is read only the
channels Slack says they are in. Nothing is kept: a message is read when asked. This is a separate
Slack app from the one that answers questions in Slack. In the console open **Knowledge and data**,
**Connectors**, **Slack**, **Connect**:

1. **Make a Slack app.** On Slack's **Your Apps** page (the console's step links to it) press
   **Create New App**, **From scratch**, name it after the Brain and pick your workspace.
2. **Give it read scopes only.** **OAuth & Permissions**, **Bot Token Scopes**: add channels:read,
   groups:read, channels:history, groups:history, users:read and users:read.email. Nothing that
   writes.
3. **Install it and invite it.** **Install to Workspace**, **Allow**. Then in each channel the Brain
   may read, type /invite and the app's name. A channel it is not in is never read.
4. **Connect it.** Type the workspace id (it starts with T, on the app's **Basic Information** page),
   the department whose people may be told what Slack holds, paste the **Bot User OAuth Token** from
   **OAuth & Permissions** and press **Connect Slack**.
5. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:slack_message`, scoped to that department, with a reason. A person is matched to their
   Slack account by their verified work email, and is read only their own channels.

Tell me "connected Slack" afterwards and I prove it on your install.

## 154. One server change for the sealed sandbox: probably no downtime

**In plain terms:** three things you asked for run code the Brain did not write: scripts inside
imported skills, the code sandbox, and connectors written as custom code. They must run sealed off,
with no internet, no access to the Brain's data and hard time and memory limits. The standard way
to seal them is gVisor, a small program Docker uses to run a container inside its own protective
layer. Your server does not have it yet (checked read-only on 2026-10-06: Ubuntu 24.04, Docker with
its standard runtime only).

Installing it is one change no release can make on its own: gVisor is installed on the server and
added to Docker's settings. Docker can usually take that by **reloading** its settings, which
restarts nothing, so there is **probably no downtime at all**. Only if the reload does not take it
does Docker need a full restart, which restarts every container on the server for about a minute,
the Brain's and your other project's (Activepieces) alike. Nothing is lost either way; they all come
back by themselves.

**Option A: yes, at a quiet time.** I install gVisor and reload Docker myself (restarting it only if
the reload is not enough), at a time you name
(for example a weekday night, Singapore time), then confirm everything is back and run the
sandbox's own check: a script that tries to reach the internet and is stopped, and one that runs
past its time and memory limits and is stopped.

**Option B: not now.** The sandbox stays off. Skills with scripts are refused with a sentence saying
this install runs no sandbox, and custom-code connectors are not offered. Everything else works.

**Memory:** the sandbox is sized at 256 MB a script, so it fits beside the personal-data detector
and Langfuse (item 120) with about 180 MB to spare. A larger limit per script would need more room.

**My recommendation: A,** at a quiet time you choose.

**What I need from you:** reply "154: A, after 11pm on a weekday" (or whichever time suits), or
"154: B". Then, on your one visit to **Install, Settings**, **Optional services this server runs**
becomes `presidio,langfuse,sandbox` instead of `presidio,langfuse`; I tell you when that is ready.

## 153. Questions written in Chinese: how much is hidden before they go to an outside model?

**In plain terms:** your requirement GAP-23 is now built (#344): before a question or passage goes
to an outside model provider, names, ID numbers, phone numbers and email addresses are replaced
with placeholders, and put back in the answer for the person who asked. Names written in Chinese
characters are hard to tell from other Chinese words, so the built-in rules treat any run of two to
four Chinese characters as a possible name. A question in English with a Chinese name in it works
well: the name is hidden and the rest is sent. But a question written entirely in Chinese reaches
the model as nothing but placeholders, and the model cannot answer it.

**Option A: keep it as it is.** Nothing that could be a name leaves your install. Questions written
in Chinese cannot be answered by an outside model.

**Option B: hide a Chinese run only where it stands alone inside non-Chinese text,** as a name does
in an English sentence. Questions written in Chinese then go through and are answered, but a
Chinese name inside Chinese text is sent to the provider as written. Once the personal-data detector
(item 120, row 1) runs with a Chinese model, it finds those names too and hides them again.

**Option C: answer questions written in Chinese only with a model running on your own server.**
Nothing leaves, and Chinese questions are answered, but only once such a model runs (it needs the
model server from item 120, row 2, which does not fit on this server today).

**My recommendation: B,** with the detector's Chinese model added once it is installed. It answers
the questions your people actually ask, and hides every name written in an English sentence today.
Until you reply, A holds, because it is the safe side: it only ever hides more.

**What I need from you:** reply "153: A", "153: B" or "153: C". It is worth knowing first whether
your staff ever ask the Brain in Chinese; if they never do, A costs nothing.

## 150. Connect Google Drive (ready now)

**In plain terms:** the Brain can now answer from the documents in one Google Drive folder and every
folder under it, reading each Google Doc's words when somebody asks and keeping only names. It reads
as a service account that can only view that folder. A subfolder shared more narrowly than its
parent, or shared by link, is left out with everything in it. In the console open **Knowledge and
data**, **Connectors**, **Google Drive**, **Connect**:

1. **Make a service account** in Google Cloud console, **IAM & Admin**, **Service Accounts**, with
   **no role** and never domain-wide delegation (item 143's can be reused).
2. **Switch on the Google Drive API**: **APIs & Services**, **Library**, **Google Drive API**,
   **Enable**.
3. **Share the one folder with it as a viewer.** In Google Drive right-click the folder, **Share**,
   paste the service account's email address, choose **Viewer**. Share nothing else with it.
4. **Make its key file** (skip if you reuse one you still have): the account, **Keys**, **Add key**,
   **Create new key**, **JSON**, **Create**.
5. **Connect it.** Paste the folder's link from Drive (or only the id after /folders/), your
   company's email domain (the part after @), the department the folder belongs to, the id of the
   person who answers for its contents (as **People** shows it), choose the key file and press
   **Connect Google Drive**.
6. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:drive_file`, scoped to that department, with a reason.

Tell me "connected Google Drive" afterwards and I prove it on your install.

## 149. Your developer's part for the Laravel database

**In plain terms:** four things in the database and its hosting, done once, before item 148.
Send this to your developer:

1. **Two views, holding only what the Brain may see.** In the application's database create
   `v_client` with the columns name, status, department, manager_id, updated_at, and `v_user` with
   display_name, department, status, updated_at. A view is the statement of what may be read and
   changes only when you change it; a new column in a table is not read until a view names it.
2. **A read-only user.** Create a database user with SELECT on those two views only: not on any
   table, and no write. Give its name and password to the owner for item 148.
3. **Let the Brain's server reach the database, on its port only.** Either allow the Brain server's
   own address (from its hosting provider) in the database's firewall or security group, or, where
   the database is on a private network, run an SSH tunnel from the Brain's server to a machine that
   reaches it and keep it running: the Brain does not start one.
4. **The certificate.** If the database's certificate is from a public authority, nothing is needed
   (the owner types verify). If it is from your own certificate authority, give the owner that
   authority's certificate to paste. Only a tunnel may go without encryption.

## 148. Connect the Laravel database (ready now)

**In plain terms:** the Brain can now answer about clients and staff from your Laravel application's
own database, through two views your developer writes and a user that can read only those views.
Every read stops at a row limit and a time limit you set. Your developer does item 149 first; then,
in the console open **Knowledge and data**, **Connectors**, **Laravel database views**, **Connect**,
and type what they give you:

1. **Database holding the views**: the database name your developer gives you.
2. **Database server's address** and **port**: as your developer or hosting provider gives them (the
   port is usually 3306). With a tunnel, the tunnel's local end.
3. **Private network**: yes only if the database is reached directly on a private network or
   through a tunnel; otherwise no.
4. **Encryption**: verify, or paste your own certificate authority's certificate if your developer
   says the database uses one. none only with private network yes and a tunnel.
5. **Who may be told a client** and **a staff record**: the rule each view is kept under, as your
   developer writes it, for example department = sales.
6. **Most rows** (up to 5000) and **longest read in seconds** (up to 30).
7. **The read-only user's name and password**, from your developer. Press **Connect Laravel database
   views**; the login goes to the vault and is never shown again.
8. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:laravel_client` and `read:laravel_user` and the fields they may see, scoped to the
   department each view's rule names, with a reason.

Tell me "connected Laravel" afterwards and I prove it on your install.

## 152. Lark Base and Lark Wiki are connected through Connect Lark, not this list

**In plain terms:** these two are not on the Connectors list's Connect buttons, because their records
and pages are read live and never synced. In the console open **Knowledge and data**,
**Connectors**, and press **Connect Lark**, which creates the Lark app, tests it, and switches on
knowledge from one Base and from the shared wiki spaces. If Connect Lark is already done on your
install, nothing more is needed here. Tell me "connected Lark" if you run it now and I prove it on
your install.

## 146. Connect Domains and hosting (ready now)

**In plain terms:** the Brain can now say when each client domain expires, who its registrar is and
whether its site answers. It needs no key: a domain's registry publishes that to anyone. Only the
domains you list are ever looked up. In the console open **Knowledge and data**, **Connectors**,
**Domains and hosting**, **Connect**:

1. **Gather the domains.** List every client domain you look after, up to two hundred.
2. **Choose the department.** Pick the one department whose people may be told about them.
3. **Connect it.** Type the domains, separated by commas or new lines, and that department's short
   name, and press **Connect Domains and hosting**. No key is asked for.
4. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:domain` and the facts they may be told (expiry, registrar, whether the site answers),
   scoped to that department, with a reason.

A domain whose registry publishes nothing (some country domains) is answered as that rather than
guessed. Tell me "connected Domains" afterwards and I prove it on your install.

## 145. Connect Cloudflare (ready now)

**In plain terms:** the Brain can now answer about your Cloudflare zones and DNS records, and read a
record's content and a zone's security events live. It reads with a token that can only read. A DNS
change is only ever prepared for a person to approve; sending an approved change needs a second
token, and that part is optional. In the console open **Knowledge and data**, **Connectors**,
**Cloudflare**, **Connect**:

1. **Make a read-only token.** In the Cloudflare dashboard open **My Profile**, **API Tokens**,
   **Create Token**, **Create Custom Token**. Give it exactly three permissions: **Zone Read**, **DNS
   Read** and **Analytics Read**. Nothing marked Edit or Write, and never the Global API Key.
2. **Limit it to one account and copy it.** Under **Zone Resources** choose **Include**, **All zones
   from an account**, and your account. **Continue to summary**, **Create Token**, and copy the token:
   Cloudflare shows it once.
3. **Copy the account's id.** On the account's **Overview** page, copy **Account ID** (32
   characters).
4. **Connect it.** On the console's last step type the account id, the short name of the department
   whose people may be told its zones and records, paste the token and press **Connect Cloudflare**.
5. **Optional, approved DNS changes.** Only if you want an approved change sent by the Brain rather
   than made by hand: make a second custom token with one permission, **DNS Edit**, over the same
   account's zones, and on the Cloudflare connector's page use **Allow approved DNS changes** to paste
   it. It sits in its own vault slot and is used only for a change a person in that department
   approved.
6. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:zone` and `read:dns_record` (and the record fields they may see, such as its content),
   scoped to that department, with a reason.

Tell me "connected Cloudflare" afterwards and I prove it on your install.

## 144. Connect Search Console (ready now)

**In plain terms:** the Brain can now answer about one verified site's clicks, impressions, top
queries and pages and sitemap problems, for any range in the last sixteen months. It reads as a
service account with restricted permission on that one site, keeps only the site's name, and reads
every figure from Google when asked. The service account made for item 143 can be reused. In the
console open **Knowledge and data**, **Connectors**, **Search Console**, **Connect**:

1. **Use or make a service account.** In Google Cloud console, **IAM & Admin**, **Service Accounts**:
   use the one from item 143, or **Create service account** with **no role** and no domain-wide
   delegation.
2. **Switch on the API.** **APIs & Services**, **Library**, search for **Google Search Console API**,
   **Enable**.
3. **Make its key file** (skip if you reuse item 143's and still have its file): the account,
   **Keys**, **Add key**, **Create new key**, **JSON**, **Create**.
4. **Add it to the one site.** In Search Console choose the verified property, **Settings**, **Users
   and permissions**, **Add user**: paste the service account's email address and choose
   **Restricted**. No other property.
5. **Connect it.** On the console's last step type the property exactly as Search Console's property
   list shows it (a domain property starts with sc-domain:), the short name of the department whose
   people may be told its figures, choose the key file and press **Connect Search Console**.
6. **Give people the read.** **People and access**, **People**, the person, **Grant a capability**:
   `read:search_site` and the figures they may see, scoped to that department, with a reason.

Tell me "connected Search Console" afterwards and I prove it on your install.

## 143. Connect Google Analytics (ready now)

**In plain terms:** the Brain can now answer "how many sessions did the site have last month" from
one Google Analytics property. It reads as a Google service account that can only view that one
property, keeps only the property's name, and reads every figure from Google when somebody asks. In
the console open **Knowledge and data**, **Connectors**, **Google Analytics**, **Connect**, which
shows each step:

1. **Make a service account.** In Google Cloud console open **IAM & Admin**, **Service Accounts**,
   **Create service account** (the console's step links to it). Name it after the Brain and give it
   **no role**. Never tick domain-wide delegation.
2. **Switch on two APIs.** In the same project open **APIs & Services**, **Library**: search for
   **Google Analytics Data API** and press **Enable**, then search for **Google Analytics Admin API**
   and press **Enable**.
3. **Make its key file.** Back in **Service Accounts**, open the account, **Keys**, **Add key**,
   **Create new key**, **JSON**, **Create**. A key file downloads; keep it only until step 6.
4. **Let it view the one property.** In Google Analytics open **Admin**, choose the property,
   **Property access management**, the plus, **Add users**: paste the service account's email
   address (it is on the account's page in Google Cloud) and give it **Viewer**. Nothing else.
5. **Copy the property's id.** Still in **Admin**, **Property details**: copy the **Property ID**,
   which is a number.
6. **Connect it.** Back on the console's last step type the **Property ID** from step 5, the short
   name of the one department whose people may be told its figures (as **People and access**,
   **Departments** shows it), choose the key file from step 3 and press **Connect Google
   Analytics**. The key file goes to the vault and is never shown again.
7. **Give people the read.** In **People and access**, **People**, open each person who should be
   told the figures and press **Grant a capability**: choose `read:analytics_property` and the figures
   they may see (each is its own grant, such as the last 28 days' sessions), the scope of that
   department, write a reason and save.

Tell me "connected Google Analytics" afterwards and I prove it on your install.

## 142. Connect WhatsApp (ready now)

**In plain terms:** people can now ask the Brain on WhatsApp, the last of the channels in item 126's
order. Only do this if your company uses WhatsApp Business. It needs a phone number used only for the
Brain, and Meta lets the Brain answer freely only within 24 hours of the person's last message. In the
console open **Channels**, **WhatsApp**, **Connect**, which shows each step:

1. **Make the Meta app and add the number.** On Meta for Developers choose **Create app**, the
   **Business** type, and add the **WhatsApp** product. Under **WhatsApp**, **API Setup**, add and
   verify the number the Brain will answer from, and copy its **Phone number ID**.
2. **Make a token that does not expire.** In Meta **Business settings**, **System users**, add one with
   the **Admin** role, **Assign assets** (the app, full control), then **Generate new token** for the
   app with expiry **Never**, ticking whatsapp_business_messaging and whatsapp_business_management.
   Copy it. (Not the temporary token on the API Setup page: it expires within a day.)
3. **Copy the app secret.** In the app's **App settings**, **Basic**, press **Show** beside **App
   secret** and copy it.
4. **Save it in the console.** Type the Phone number ID, paste the app secret and the token, and make
   up a verify word (a long random word you type here and again in step 5). Tick **Switched on** and
   press **Save set-up**. All three go to the vault and are never shown again.
5. **Point Meta at the Brain.** In Meta open **WhatsApp**, **Configuration**, **Webhook**, **Edit**:
   paste the events address the console's step shows as the **Callback URL**, the word from step 4 as
   the **Verify token**, and press **Verify and save**. Under **Webhook fields** subscribe to
   **messages**.
6. **Try it.** Write to the number from your own WhatsApp: the first answer asks you to link your
   number to your Brain account.

Tell me "connected WhatsApp" afterwards and I prove it on your install.

## 141. Connect Telegram (ready now)

**In plain terms:** people can now ask the Brain in Telegram, the next channel in item 126's order.
Only do this if your company uses Telegram. In a group the bot only answers a message that names it,
and then with a link to Ask, so nothing private lands where others read. In the console open
**Channels**, **Telegram**, **Connect**, which shows each step:

1. **Make the bot.** In Telegram open **BotFather** (the console's step links to it), send /newbot,
   give it a display name (for example Company Brain) and a username ending in bot (for example
   company_brain_bot). BotFather replies with the bot's token: keep it private.
2. **Optional: keep it out of groups.** Send BotFather /setjoingroups, pick the bot and choose
   **Disable**.
3. **Save it in the console.** Type the bot's username without the @ into **bot_id**, paste the
   token into the secret field, tick **Switched on** and press **Save set-up**. The Brain tells
   Telegram where to send messages by itself; if Telegram refuses, nothing is saved and the console
   says why. The token goes to the vault and is never shown again.
4. **Try it.** Open the bot in Telegram, press **Start** and write to it: the first answer asks you to
   link your Telegram account to your Brain account.

Tell me "connected Telegram" afterwards and I prove it on your install.

## 140. Connect Microsoft Teams (ready now)

**In plain terms:** people can now ask the Brain in Microsoft Teams, item 126's next channel. Only do
this if your company uses Teams. The Brain answers in a one-to-one chat; in a group or channel that
names it, it posts a link to Ask instead of the answer, so nothing private lands where others read.
In the console open **Channels**, **Microsoft Teams**, **Connect**, which shows each step:

1. **Create the bot in Azure.** In the Azure portal choose **Create a resource**, **Azure Bot**. Give
   it a handle (for example company-brain), pick your subscription and resource group, set **Type of
   App** to **Single Tenant** and **Creation type** to **Create new Microsoft App ID**, then **Review +
   create** and **Create**.
2. **Point it at the Brain.** Open the bot, then **Configuration**. Paste the events address the
   console's step shows into **Messaging endpoint** and press **Apply**. Copy the **Microsoft App ID**
   and the **App Tenant ID**.
3. **Make its password.** Still on **Configuration**, press **Manage Password** beside the App ID,
   then **Certificates & secrets**, **New client secret**, **Add**. Copy its **Value** (not the Secret
   ID); Azure shows it only once.
4. **Switch on Teams for the bot.** On the bot's **Channels** page choose **Microsoft Teams**, accept
   the terms and press **Apply**.
5. **Save it in the console.** Paste the App ID into **bot_id**, the tenant ID into **tenant_id** and
   the secret's value into the secret field, tick **Switched on** and press **Save set-up**. The
   secret goes to the vault and is never shown again.
6. **Give people the app.** In the Teams Developer Portal choose **New app**, then **App features**,
   **Bot**, **Enter a bot ID** (the App ID), tick **Personal** scope and save; then **Publish to your
   org**, and approve it in the Teams admin centre if your organisation asks. Open the app in Teams and
   write to it: the first answer asks you to link your Teams account to your Brain account.

Tell me "connected Teams" afterwards and I prove it on your install.

## 139. Website widget: should visitors get answers written by the model, or the published passages themselves?

**In plain terms:** the website widget (M10.7.2, #315) lets visitors to your website ask questions,
and it only ever reads documents an administrator has marked public. Today it answers with the
matching passages from those documents, word for word. Having the model write a short answer from
them reads better, but every visitor question then costs a model call, paid by you, asked by people
who are not your staff and have no budget of their own.

**Option A: passages only, for now.** No model cost, and nothing is ever said that is not already
in a public document.

**Option B: the model writes the answer** from the public passages only, under a daily spending cap
for the widget that you set in the console, and the widget falls back to passages once the cap is
reached.

**My recommendation: A now, B later.** Start with passages, watch what visitors ask for a few weeks,
and switch on B with a cap if the answers need to read better.

**What I need from you:** reply "139: A" or "139: B".

## 138. Laravel: may each client record be visible to one department, or to several?

**In plain terms:** when you connect your Laravel application's database (its steps come to this page
when it can read), you write a rule for each view saying who may see its records, for example
"department = sales": a sales person sees the clients whose department is sales. The Brain keeps one
such value per record in its small index. A rule naming several departments for one record ("visible
to sales and operations") cannot be kept that way, so it would have saved and then shown nobody
anything. It is now refused when you connect, with a sentence saying why.

**Option A: one department per record, for now.** Every client record belongs to one department, and
people in that department see it (administrators and anyone granted wider reach see more, as
everywhere else).

**Option B: several departments per record.** The index learns to keep a short list per record, so
a client shared by sales and operations is seen by both. More work, and it makes the index hold a
little more about each record.

**My recommendation: A now.** Most client records have one owning department, and B can be added the
day a real record needs two.

**What I need from you:** reply "138: A" or "138: B".

## 137. Which of your systems holds client projects and their tickets?

**In plain terms:** one memory task (M16.6.2) asks that a question about a client project is
answered with that project's current picture: the project, its client, its open tickets and its
recent decisions, read from your systems at the asker's own reach on every question and never kept
as a memory. For that the Brain has to know which of your systems is the record of a project. I will
not guess: the Laravel connection reads clients and staff today and nothing else, so nothing the
Brain reads yet is a project.

**Open tickets come from Freshdesk in every option,** once item 128 connects it, because that is
where your tickets are. Recent decisions are read from the same place as the project (its notes or
its status history), so the one choice is where a project lives.

**Option A: a Lark Base.** If your team keeps active projects in a Base, one row per project with
its client and its status, the Brain reads that table through the Lark Base connector that already
exists. You choose the Base and the table when you connect it, and nothing changes in Laravel.

**Option B: Laravel, through a new project view.** If projects live in the Laravel application (its
websites and their maintenance plans, each tied to a client), whoever looks after that database adds
one read-only view for projects beside the two it has today, and the Brain reads it the way it reads
clients. I write the view for them; it is one change on their side, and the Brain reads nothing
beyond what the view shows.

**Option C: Freshdesk alone.** If a project for your team is really the run of support tickets for
one client, Freshdesk is enough: the Brain reads a client's open tickets live from Freshdesk, and
there is no project record to connect.

**My recommendation: B, with Freshdesk for the tickets.** The Laravel application is where each
website and its maintenance plan already sit against the client the Brain reads, so a project view
joins to that client without matching names across two systems, and Freshdesk holds the tickets.
Choose A instead if day-to-day project work is tracked in a Base rather than in Laravel, because the
Brain should read the record your team actually keeps up to date. C is the smallest and answers only
"what is open for this client", not "where is this project".

**What I need from you:** reply "137: A", "137: B" or "137: C". For A, also tell me the name of the
Base. For B, tell me who looks after the Laravel database, and I send them the view. After you
choose, I build it, and it is proved when you ask about a project, change its status in that system,
and ask again: the second answer shows the change (check 9 in item 91).

## 136. When a memory and a connected system disagree: settled by how memory is built?

**In plain terms:** one memory task (M16.4.3) asks that when something the Brain remembers disagrees
with one of your connected systems, the system wins at once and the memory is demoted and flagged. I
recommend we mark it met by how memory is built, rather than build a comparison, and I need your yes
because that is narrower than what the task literally asks.

**Why the two can never disagree.** The Brain only remembers what a person says about themselves,
such as "I prefer short answers" or "I work from home on Fridays". It never keeps a value it read
from a connected system: an invoice total, a ticket's status or a client's renewal date is read from
that system each time a question needs it and is never written to memory (task M16.7.5, which a test
value proves on your install). A memory also never answers a question: it shapes how the question is
looked up and phrased, and the answer always comes from the system. So there is no remembered copy
of a system's value that could go out of date, and nothing a comparison could find.

**What building it anyway would mean.** A job that reads every memory, works out which record in
which system it is about, and compares the two. It would have to guess which record a sentence like
"I look after the retail accounts" is about, and a wrong guess demotes a true memory with nothing to
show why. I recommend against it.

**The one case to know about.** A person can say something about themselves that a system also
records, for example "I manage the retail accounts" while your CRM names someone else. The Brain
keeps it as that person's own note and still answers every question about those accounts from the
CRM, at that person's reach, so the CRM wins on every answer. When the note stops being true they
edit or forget it on **My workspace**.

**My recommendation: yes, mark M16.4.3 met by construction.**

**What I need from you:** reply "136: yes", or "136: build the comparison" if you want the job above
anyway, and I build it.

## 134. Connect the Slack channel (ready now)

**In plain terms:** people can now ask the Brain in Slack, in a direct message or by naming it in a
channel, the second channel in item 126's order. Only do this if Verz uses Slack. In the console open
**Channels**, **Slack**, **Connect Slack**, which shows each step with a picture:

1. **Create the Slack app from its manifest.** On Slack's site open **Your Apps**, click **Create New
   App**, choose **From a manifest**, pick your workspace, choose **JSON**, replace what is there with
   the manifest the console copies for you, then **Next** and **Create**. Slack saying the address is
   not verified yet is expected until the last step.
2. **Install the app and copy its bot token.** In the app's menu open **OAuth & Permissions**, click
   **Install to Workspace**, then **Allow**, and copy the **Bot User OAuth Token** (it starts with
   xoxb-).
3. **Copy the signing secret.** Open **Basic Information**, find **App Credentials**, click **Show**
   beside **Signing Secret** and copy it.
4. **Copy the app's member ID.** In Slack itself, open the app under **Apps**, click its name to open
   its profile, click the three dots and choose **Copy member ID** (it starts with U).
5. **Save them in the console.** Paste the member ID, the signing secret and the bot token into their
   fields, tick **Switched on** and press **Save set-up**. The secrets go to the vault and are never
   shown again.
6. **Let Slack check the address.** Back in the app's **Event Subscriptions**, click **Retry** beside
   the Request URL until it says **Verified**, then **Save Changes**. Now message the app: the first
   answer asks you to link your Slack account to your Brain account.

Tell me "connected Slack" afterwards and I prove it on your install.

## 133. Search Console's indexing issues: counts from the sitemaps, not a page-by-page report

**In plain terms:** your task for Search Console (M11.7.2) asks for a site's indexing issues.
Google's Search Console API has no Page indexing report: the only way to ask about one page is a
separate inspection call per page, which is slow and rationed. So the connector reports indexing
issues as the error and warning counts Google gives for each of the site's sitemaps, and the answer
says that is what it is. Everything else in the task (queries, pages, clicks and impressions, for
any range you name) is read in full.

**Option A: accept the sitemap counts,** with the answer naming them as sitemap counts.
**Option B: also inspect named pages on request,** one call per page, only when somebody asks about
specific pages, slower and within Google's daily allowance.

**My recommendation: A now.** It answers "is anything wrong with indexing" straight away, and B can
be added the day someone needs page-by-page detail.

**What I need from you:** reply "133: A" or "133: B".

## 132. Connect the email channel (ready now, with any mail provider)

**In plain terms:** people can email the Brain and get an answer back by email, the first of the
channels in item 126's order. Answers go out through the install's own mail relay. Mail comes in
either from an ordinary mailbox the Brain reads once a minute (Google, Microsoft 365, Lark Mail or
any provider with IMAP), or, if your domain's mail runs through Cloudflare, from Cloudflare Email
Routing. **Use the mailbox route unless you already use Cloudflare Email Routing:** it needs only a
mailbox.

**What you do,** in the console under **Channels**, **Email**, **Connect Email**, which shows each
step with a picture:

1. **Choose the route.** At "Is your domain's mail on Cloudflare?" choose **No: read a mailbox**.
2. **Set up the mail relay first.** Open **Notifications**, fill in **Email relay** with your mail
   provider's sending details (host, port, sender address, user name and password) and send its
   test message. These are the same details item 131 asks for, so do this once for both.
3. **Make a mailbox only the Brain uses** (for example one named ask, at your company's domain) and
   turn on IMAP for it:
   - Google Workspace: in Gmail open **Settings**, **Forwarding and POP/IMAP**, **Enable IMAP**, and
     make an app password if the mailbox signs in with two steps.
   - Microsoft 365: in the admin centre open the mailbox, then **Mail**, **Manage email apps**, and
     tick **IMAP**.
   - Write down the IMAP server your provider names (the console's step names Google's and
     Microsoft's) and port 993. Nobody should read this mailbox by hand: the Brain reads what is
     unread and marks it read, and never deletes anything.
4. **Find the name your provider stamps on arriving mail.** From your own work address send the new
   mailbox a message, open it there and choose **Show original** (or **View source**). Find the
   topmost line starting Authentication-Results: and copy the name before its first semicolon. On
   Microsoft 365 that line names nobody, so the name is simply the word exchange.
5. **Save it in the console.** Back in **Connect Email** type the mailbox's address, its IMAP
   server, port 993 and user name, the name from step 4 in **receiver**, and your staff's email
   domains in **domains**, separated by commas. Paste the mailbox's password (or its app password)
   into the secret field, tick **Switched on** and press **Save set-up**. The password goes to the
   vault and is never shown again.
6. **Try it.** Write to the mailbox from your own work address. Within a minute the Brain answers,
   and the first answer asks you to link your address to your Brain account.

**If you use Cloudflare Email Routing instead,** choose **Yes** at step 1 and follow the Cloudflare
steps the console shows: a subdomain just for the Brain, a Worker named company-brain-mail with the
script the console gives you, and a routing rule sending that address's mail to the Worker.

**What only your real mailbox proves:** that your provider stamps the name you copied, that the
password signs in, and that the answer arrives. Tell me "connected email" afterwards and I prove it
on your install.

## 130. Does a staff list anybody with its link can edit give people sign-in accounts?

**In plain terms:** item 115's B is built: the staff sync gives each active person a sign-in account
and sends nobody anything. One case I decided the safe way and need you to confirm. A spreadsheet or
a Google Sheet can be edited by anybody who has its link, so a row somebody adds would become a real
way into the Brain for whatever address they typed, as long as they can read that mailbox and press
Forgot password. Lark, Google Workspace, Microsoft Entra and LDAP are changed only by your
administrators, and they give accounts as you asked.

**Option A: only a company directory gives accounts.** A sheet still lists people, places them in
departments and marks leavers; it makes no accounts, and the Staff sources page says so. People on a
sheet are given their sign-in by an administrator in Keycloak, as today.

**Option B: a sheet gives accounts too.** Anybody who can edit the sheet can then let somebody in.
Only sensible for a sheet you have locked to one or two people.

**My recommendation: A.** It is what is built, and it matches the rule the product already keeps: a
sheet is trusted to say who exists and nothing more.

**What I need from you:** reply "130: A" or "130: B". Until then A holds, which is the safe side: B
only adds accounts.

## 131. Make staff accounts work on your install (after #281 is deployed)

**In plain terms:** item 115's accounts are built (#281): each active person on the staff list gets
a Brain account with no email sent, and gets in by pressing **Forgot password** on the sign-in page.
Two things on your install have to be in place first, one of them only you can do.

**Part 1, yours: one mail relay, typed once.** Forgot password sends its link by email through the
same mail relay the Brain uses for everything else. Open **Notifications**, fill in **Email relay**
(host, port, sender address, user name and password; your email provider's help pages list them)
and press **Send a test message**. These are the same details item 132 asks for, so do it once for
both. Nothing needs typing into Keycloak: once #311 is deployed and the deploy script in Part 2 is
installed, every release gives the sign-in service the relay itself, and a relay you change later is
picked up by the next release. If you already typed mail settings into Keycloak, the next release
replaces them with the relay's. To confirm: on the **Install** page, the check *Forgot password is
sent through the relay on Notifications* passes.

**Part 2, mine with your go-ahead: three server steps.**

The first step also lets item 120's optional services start: the personal-data detector and
Langfuse are started by the updated deploy script after each release, so they wait for this too.

- Install the updated deploy script, so releases set up the accounts client and apply their own
  vault changes (this is also item 129's prerequisite).
- Run the accounts-client setup once, which creates the sign-in service client the sync uses and
  puts its secret straight into the vault; nobody sees it.
- Add one setting the worker needs (the sign-in address, `INSTALL_OIDC_ISSUER`) to the worker in the
  hosting panel's stored configuration.

**What you do:** fill in the relay whenever suits you, and reply "131: do the server steps" for Part 2.
I tell you when both are done and the next staff sync has made the accounts; then you can tell
people: "Your account is ready. Go to the sign-in page, press Forgot password and enter your work
email."

## 129. Let the vault open itself after a restart (item 114's switch, still to do)

**In plain terms:** item 114 decided that the secrets vault opens itself when the server restarts.
The switch has not been run yet: on 30 September the vault still reported the old kind of lock
(Shamir), so if the server restarted today the vault would need three of its five key pieces typed
in before the Brain could read any key again. The pieces are safe in the root-only file the
2026-09-21 setup wrote, so nothing is lost, but a restart would stop the Brain until someone does it.

**My recommendation: let me run it for you.** It takes about two minutes, during which the vault is
unavailable, and it keeps a dated copy of the vault's data so it can be put back.

**What you do:**

1. Reply "129: do it". I run the switch over the server connection I already use, check that the
   vault reports it opens itself, and tell you it is done.
2. Afterwards, on the server as root: copy `/etc/brain-vault/seal.key` into your password manager as
   its own entry; move `/etc/brain-vault/recovery.key` into your password manager and delete that
   file; delete `/root/brain-vault-init-20260921.txt`, whose pieces open nothing after the switch.
   Keys are yours to hold: I never read or copy them.

## 128. Connect Xero, HubSpot and Freshdesk (ready now)

**In plain terms:** item 126 decided every service is made connectable from the console, one at a
time. These three are ready today. Each takes about ten minutes. In the console open
**Connectors**, press **Connect a source**, choose the service and follow its screens, which show a
picture of each step. Paste keys only into the console, never into chat.

**Xero** (invoices and contacts, read only)

1. Sign in to Xero's developer portal (developer.xero.com, **My Apps**) with an account that
   administers your organisation, and press **New app** (Xero may offer it as a custom connection).
   Name it "Company Brain". Give it exactly two scopes, `accounting.transactions.read` and
   `accounting.contacts.read`, and nothing ending in `.write`.
2. Press **Authorise** for the one Xero organisation the Brain should read, then copy that
   organisation's id (Xero may call it the tenant id) and the key Xero issues.
3. In the console, on Connect Xero's last screen, paste the organisation id and the key and press
   **Connect Xero**.

**HubSpot** (companies, contacts and deals, read only)

1. In HubSpot, press the settings gear at the top right, then **Integrations**, **Private Apps**
   (HubSpot may list it under **Development**, **Legacy apps**), and press **Create a private app**.
   Name it "Company Brain".
2. On the **Scopes** tab tick `crm.objects.companies.read`, `crm.objects.contacts.read` and
   `crm.objects.deals.read`, and nothing with "write" in it or touching settings. Press **Create
   app**, confirm, and copy the access token.
3. In the console, on Connect HubSpot's last screen, paste the HubSpot account id (shown in the
   account's settings) and the token, and press **Connect HubSpot**.
4. Give people the read: **People and access**, **People**, the person, **Grant a capability**:
   `read:hubspot_company`, `read:hubspot_contact` and `read:hubspot_deal`, and the fields they may
   see (a deal's amount is its own grant).

**Freshdesk** (tickets, read live)

1. Choose the Freshdesk agent the Brain reads as: someone who sees the tickets it should answer
   about and no more, and never an administrator.
2. Sign in to Freshdesk as that agent, press the profile picture at the top right, open **Profile
   settings**, and press **View API key**. Copy it.
3. In the console, on Connect Freshdesk's last screen, type your helpdesk's address (ending
   `.freshdesk.com`), the short name of the one department whose people may be granted its
   tickets, paste the key, and press **Connect Freshdesk**.

**Two memory tasks are proved by connecting Freshdesk:** M16.2.6 (a ticket reopened soon after it
was resolved is counted as a sign the answer did not help) and the second half of M16.3.2 (a link
between a person and a client is learned automatically only when a fixed identifier, such as the
email address on that client's tickets, backs it). Both read what changed in Freshdesk since the
last look, and I check both on your install once you tell me "connected Freshdesk".

**After each one,** press **Test** on its card, then tell me "connected Xero" (or whichever). I
prove it on your install and close its tasks. The next services (Google Drive, then Laravel, then
the chat channels) are added here as each becomes connectable.

## 127. Switch on the Lark app's chat channel, then add the bot to your digest group

**In plain terms:** on 30 September the Brain's Lark app did not appear under **Add bot**, because
it was connected for the staff list only. The bot, its permissions and its events belong to the
**Chat channel** use, which the console walks you through. This is also what lets the evening digest
(item 125), approval cards (items 117 and 118) and linked people's questions reach Lark.

**What you do:**

1. In the console, open **Connectors** and find the Lark card. Press **Manage Lark**, then **Add a
   use to Lark**, tick **Chat channel**, and continue.
2. **Turn on the bot.** In Lark's developer console, open your app, go to **Add Features** (or
   **Features**), choose **Bot** and turn it on. This is the setting that was missing.
3. **Add the permissions.** Press **Copy all permissions** in the console. Then in Lark, open
   **Permissions & Scopes**, click **Batch import**, paste and confirm. Every permission is read-only
   except `im:message:send_as_bot`, which lets the bot send its own replies.
4. **Copy the two keys, then save.** In Lark, open **Events & Callbacks**, then the **Encryption
   Strategy** tab. If the Encrypt Key is empty, click **Reset** to make one. Paste the **Encrypt
   Key** and **Verification Token** into the console and press **Save the chat channel now**. Do
   this before step 5, because Lark checks the address as soon as it is entered.
5. **Point Lark's events at your install.** Still in **Events & Callbacks**, open **Event
   Configuration**, choose **Request URL**, paste the events address the console shows you, and
   save; Lark should show it as verified. Then click **Add Events**, find **Message received**
   (`im.message.receive_v1`), tick it and add it.
6. **Release a new version.** In Lark, open **Version Management & Release**, then **Create a
   version**: use a version number such as 1.0.3, set who can use it to All members, then **Submit
   for release**. It must be approved, as with 1.0.2.
7. Back in the console, press **Test connection**, then **Save and switch on**.

After that, open your "Brain daily" group, go to **Settings**, **Bots**, **Add bot**, and the
Brain's app will appear.

**Later, when I tell you approval cards are live (item 117):** in the Lark Admin console confirm that
two-step verification is required for all members, then in the Brain's console open **Install**,
**Settings**, the **Lark** section, and set **Approve from Lark cards** to on.

## 124. Switch on the automation canvas?

**In plain terms:** the automation canvas is an optional drawing board for fixed, step-by-step
automations (a trigger, then set steps, with no model deciding what happens next). It runs in a
sandboxed container of its own that needs about 512 MiB of memory, and memory on your server is
the question in item 120. Three install tasks wait on it being switched on (M32.6.1.1, M32.6.1.2
and M32.6.1.4); everything behind it is built and tested.

**Option A: not now.** Its three install tasks move to Wave 4, and it is switched on once item 120
leaves room. **Option B: switch it on now**, and it takes 512 MiB from what item 120 is sharing out.

**My recommendation: A.** Nothing you have asked for today needs it, and memory is the scarcest
thing on the server.

**What I need from you:** reply "124: A" or "124: B".

## 123. May a task that names a table library be marked done by what it is for?

**In plain terms:** task M32.5.2.1 says every grid in the console uses a particular table library
(TanStack Table) with paging and filtering on the server. The console's own table deliberately
does not use that library, to keep the pages small and fast, and every list does page and filter
on the server, which is your requirement GAP2-24 and is tested. The library was a means; the
paging is the end.

**My recommendation: yes.** The task is marked decided by what it is for, and the requirement it
serves stays exactly as it is.

**What I need from you:** reply "123: yes", or "123: no" if you want the library used.

## 122. Where are your uploaded documents stored?

**In plain terms:** your requirement LIVE-01 says your install runs an object store: the place
uploaded files, exports and backups are kept as files. Yours has none yet, so four tasks wait on it
(M32.3.1.1 to M32.3.2.2), and everything else about it is built and tested. The product supports
three kinds.

**Option A: on your own server (SeaweedFS).** Your documents never leave your server. It needs
about 256 MiB of memory, which is part of item 120's picture. **Option B: Cloudflare R2**, a
bucket in a Cloudflare account, which costs a little each month and uses no memory on your server,
but your documents are then held by Cloudflare. **Option C: Amazon S3**, the same as B at Amazon.

**My recommendation: A.** The Brain is built so that your data stays on your server, and 256 MiB
is small beside the rest of item 120.

**What you do:** reply "122: A", and I add it to the server myself over the connection I already
use, then tell you when the Health page shows it ready. For B or C, reply with the letter and I
give you the steps to create the bucket and paste its key into the console.

## 121. On an agent's page, whose conversations are listed?

**In plain terms:** each agent's page is getting a Conversations list. Today every conversation
belongs to one person: the Brain keeps a separate thread for each person, even when several people
talk to the same agent in one Lark group, and nobody can see anybody else's. Your reference design
(the AnyGen screenshot, requirement ANY-028) shows the list "narrowed to threads related to me",
which implies the full list includes other people's conversations too. That would be a privacy
change, so it is yours to decide.

**Option A: each person sees only their own conversations with the agent.** Exactly how the Brain
works today. The "related to me" filter is not needed, because everything listed is already yours.

**Option B: the agent's owner and administrators also see that other people's conversations
happened**: who, when, and whether the agent failed, but never the question or the answer. Useful
for spotting an agent that keeps failing. The words stay private because another person's answer
was built from what *they* may see, which may be more than the viewer may.

What is **not** offered: showing other people's questions and answers. It would let anyone who can
open an agent's page read answers built from somebody else's access, which breaks the rule that
nobody sees through the Brain what they could not see themselves.

**My recommendation: A now**, and B later if you want owners to watch an agent's failures.

**What I need from you:** reply "121: A" or "121: B". Until then the list is built as A, which is
safe either way: B only ever adds to it.

## 91. Checks only you can do on your install (about 75 minutes, one sitting)

**In plain terms:** some requirements are about how the Brain behaves for real people, so the proof
is you trying each one and recording what you saw on **Install > Requirement checks** (open the
area, choose the requirement, press **Record a check**, write what you did and saw, press **Record
the check**). **Recommendation: do this after item 98 and after
connecting Lark,** because the department checks need your real departments and checks 5 and 6
need a model to answer. Tell me "checks done" and I close the tasks from your records.

**Before you start (once):**

1. Connect Lark as your staff source: **Govern > Staff sources**, choose **Lark**, and follow the
   steps on that screen from creating the Lark app onwards. When the first sync finishes, your
   departments appear on **Govern > Departments and teams**. This also proves M1.6.5, and Wave 0's
   M31.3.2.3 and M31.3.2.4: the first sync borrows its key from the vault for that run only and
   hands it back at the end, which is the last thing Wave 0 needs from you.
2. Pick two colleagues in two different Lark departments (or create two test accounts in Lark, one
   in each). In Keycloak, open your realm, **Users > Add user**, and create each with the same work
   email as in Lark. On **Credentials**, set a password with **Temporary** off.

**The checks:**

1. **Sign-in (M1.8.5, web part).** Sign out and in again through Keycloak: you land in the console.
   As a test person with a password only, open **Govern > Roles**: you are refused. Leave a session
   idle past its limit and see it end. Use "Forgot password" on the sign-in page and see the email.
2. **Department isolation (M2.3.1, web part).** As yourself, on **Knowledge**, add a small document
   at the first department's reach. As the person in that department, ask about it on **Ask**: the
   answer uses it. As the person in the other department, ask the same: you are told there is
   nothing, exactly as if it did not exist. (Adding a document from **Knowledge** is built early in
   Wave 2 and waits on item 105; I will tell you when it is live, so leave checks 2, 4 and 5 until
   then.)
3. **Department admin limits (M2.3.1).** On **Govern > Roles**, make the first person department
   admin for their department. As them, try to grant something in the other department: refused.
   Try to publish an agent company-wide: it waits for your approval on **Approvals**.
4. **Audit (M24.3.4).** On **Govern > Audit**, find the grant from check 3 and the document from
   check 2. Press **Verify the ledger**: it verifies.
5. **A real answer (M38.2.2.2).** As the first person, ask a question the document answers. The
   answer cites it; the other person gets nothing for the same question.
6. **Models (M5.6.5).** On **Models and health**, press **Check** on each provider with a key: each
   says it answered. Download the provider register and see each provider's region and terms.
7. **The remaining rows (M1.8.8, M2.3.2, M24.3.6).** On **Requirement checks**, open the
   Permissions, Departments and Observability areas. Each row still "Not checked yet" says what it
   needs; try it and record it.
8. **Health of the vault and the worker (M32.7.2).** On **Overview**, read the health strip, then
   open **Govern > Staff sources**: the secrets vault and the worker both show healthy and the last
   Lark sync shows when it ran. Record what you see.

**Memory and learning (checks 9 to 12, about 30 minutes more).** These are built in pieces over
Wave 3. Each check says which of its parts wait; I tell you when each is on your install, as for
check 2, and the rest can be done now. Use the two test people from "Before you start".

9. **Memory (M16.7.7).** Record what you saw against the Memory area on **Requirement checks**.

- Step 1. As the first person, on **Ask**, send "Remember that I prefer answers as short bullet
  points". Then ask a question the document from check 2 answers: the answer comes as bullet
  points.
- Step 2. As the other person, ask the same question: the answer is not in bullet points. A
  preference belongs to the person who said it.
- Step 3. As the first person, open **My workspace**: the preference is listed in their own words.
- Step 4. As yourself, on **People > Roles and permissions > Roles**, take away the first person's
  department role. As them, open **My workspace** again: the preference is no longer listed. Give
  the role back: it is listed again.
- Step 5. On **My workspace**, press **Edit** on the preference, change it to "numbered steps" and
  save. Ask again: the answer is numbered. Press **Forget** and ask again: the answer is ordinary
  prose. The preference is gone from **My workspace**, and, as yourself, from **Knowledge >
  Learning and memory > Memory** for that person.
- Waits, and I tell you when each is live: a conversation's working memory ending when its thread
  does (start a new conversation and the earlier one's details are not carried over); a project's
  picture reflecting a change in its system on the next question (item 137 decides which system);
  a memory disagreeing with a connected system (item 136 decides whether this is settled by
  construction); and the trace of an answer naming which kinds of context it used and which it
  left out.

10. **The learning loop (M16.7.8).** Record what you saw against the Learning area on **Requirement
checks**.

- Step 1. Under an answer on **Ask**, press **Not helpful**. Ask the same question again: the answer
  is the same. On **Knowledge > Learning and memory > Learning**, "How answers were marked" has
  counted it, and nothing under "Applied automatically" or "In shadow" has changed. A mark is
  counted and changes nothing by itself.
- Step 2. Ask something no document or connected system answers. It appears on **Reports >
  Questions and gaps** as a knowledge gap.
- Waits, and I tell you when each is live: a correction that gives the right answer being held as a
  protected learning for review; the same correction from two conversations becoming one learning
  with both as evidence; a reviewer approving it on **Learning** and it being applied once; the
  weekly digest listing it with an undo; and a failed workflow step and an evaluation each opening
  a learning for review.

11. **Every learning requirement (M16.7.9).** On **Requirement checks**, open the Learning area.
For each row still "Not checked yet", read what it needs, try it, and press **Record a check** with
what you did and saw. Rows that need a part still waiting in check 10 stay "Not checked yet" until I
tell you it is live.

12. **Every memory requirement (M16.7.11).** The same on the Memory area. Check 9 covers most rows:
record it against each row it demonstrates rather than repeating it. For "a memory a person stated
is recalled however old it is", send as the first person "Remember that I like a one-line summary
at the top of every answer", and a week or more later ask them anything: the answer still starts
with a one-line summary. Record that against the row.

The chat parts of checks 1 and 2 (binding a Lark identity with a code, the same reach in chat)
cannot be done until Wave 2 builds the Lark chat channel; both moved there with item 97.

# Answered

13. **Every knowledge requirement (M7.7.7), about 25 minutes.** Record against the Knowledge area.
Use the two test people from "Before you start".

- Step 1. **Add and ask (OWN-31, FEAT-5.1, FEAT-1.4, ARC-A-057).**
  1. As yourself, open **Knowledge** and press **Add**.
  2. Upload a short Word or PDF document, at the first person's department.
  3. As the first person, ask a question on **Ask** that the document answers. The answer cites
     the document, says when it was read, and carries a trace reference.
  4. Record this against each of those rows.
- Step 2. **Uploading never widens (ARC-A-124, FEAT-5.6, FEAT-5.5).**
  1. As the other person, ask the same question. You are told there is nothing, exactly as if the
     document did not exist.
  2. As yourself, open the document on **Knowledge** and widen it to the company.
  3. As the other person, ask again. Now it answers.
  4. Put the visibility back.
- Step 3. **A link as knowledge (FEAT-5.3, ANY-039).** On **Knowledge**, press **Add**, choose
  **From a link**, and give the address of a public page with text on it. Then ask a question the
  page answers.
- Step 4. **Owner, verified date and review date (FEAT-5.9, ARC-A-119, FEAT-5.10, CONA-37, GAP2-31).**
  1. On the document, set yourself as owner, mark it verified today, and set a review date of
     tomorrow.
  2. Ask the question again: the answer shows the verification badge.
  3. The day after, ask again. The badge says the document is due for re-verification, and you
     are reminded.
  4. Then supersede it with a new version, and archive the old one. The old version no longer
     answers.
- Step 5. **The price list (ARC-A-126, FEAT-5.7, OWN-163).**
  1. On **Knowledge > Price list**, add one row with a sell price and a cost.
  2. As a person with no cost grant, ask the cost of that item. You are told what an absent
     record is told.
  3. Ask its sell price: it answers.
- Step 6. **Unanswered questions (RWD-05).**
  1. Ask something no document answers.
  2. As the document's owner, open **Reports > Questions and gaps**. The question is listed.
- **What still waits, and I tell you when each is live:**
  - Scanned pages, tables in PDFs, layout and OCR notes in citations, and large documents (GAP-02,
    GAP3-04, GAP3-05, GAP3-06, FEAT-5.2, ARC-A-116). These need the model server, row 2 of item
    120.
  - Embedding by meaning and the rebuild when the embedding model changes (GAP-03, DEC-13,
    FEAT-5.11). These need the same server.
  - A person's library of files produced for them (ANY-010) and templates used to produce
    documents (OWN-29). These need the artifact store.
- **The rest.** For each Knowledge row still "Not checked yet", read what it needs, try it and
  record it. Rows that need a part still waiting stay "Not checked yet" until I tell you.

14. **Every connectors requirement (M11.8.13), about 30 minutes.** Record against the Connectors
area. Use one source you have a key for. Freshdesk or Xero is quickest, and Google Drive if you
have set up its service account (item 150).

- Step 1. **Connect, scoped, read-only (CON-14, ARC-A-139, FEAT-4.2, FEAT-4.3, ARC-A-140, CONB-10).**
  1. Open **Connectors** and choose the source. Before connecting, read what it says it reads,
     its access mode in words, the key it asks for and its ceiling.
  2. Connect it to one narrow slice: one folder, one helpdesk or one organisation. Leave every
     write switched off.
  3. Its details say it reads only, and that writing is a separate grant.
- Step 2. **The key is never shown back (ARC-A-084, FEAT-4.5, OWN-167, CONB-11).**
  1. Open the connector's details. They say a key is held, and when and by whom it was written,
     but never the key itself.
  2. Download its connection record (**Export**). It holds no key (CONA-36).
- Step 3. **Test and health (CON-62, CONB-12, CON-61, CON-64).**
  1. Press **Test**. It says the source answered, and shows no business rows.
  2. The connector's health shows the last read and its time.
- Step 4. **Live answers at the asker's reach (FEAT-1.2, OWN2-1, GAP-04, OWN-12, OWN-13).**
  1. As yourself, grant the first person the source's read on its steward card.
  2. As them, ask about one record by its number on **Ask**. The answer gives the value and cites
     the record, the field and when it was read.
  3. As the other person, ask the same. You are told there is nothing.
- Step 5. **Replace the key, disconnect and reconnect (CON-63, FEAT-4.4, CONB-13).**
  1. Press **Replace key** and paste a new key. The next test answers with no restart.
  2. Disconnect. The confirmation says the key stays held in the vault.
  3. Reconnect. The history shows both connections.
- Step 6. **Each source you connect (OWN-9 to OWN-20, OWN2-C1 to OWN2-C12).** For each source you
  connect, record its own row ("can be connected and read") and its "ready as soon as it is
  connected" row with what you asked and saw.
- **What still waits, and I tell you when each is live:**
  - Writes approved and read back (GAP-35, OWN-24, ARC-B-144, GAP2-14).
  - MCP and custom-code connectors (ARC-A-138, FEAT-4.1, OWN-21, ARC-A-142, FEAT-4.7). Custom code
    needs the script sandbox.
  - The nightly schema-drift check (REQ-33).
  - Deleted records (GAP-06) and token refresh without you (GAP-07).
- **The rest.** As in check 13.

15. **Every tools requirement (M12.4.15), about 15 minutes now, more as the browser lands.**
Record against the Tools area.

- Step 1. **The catalogue (CONA-32, FEAT-3.7, FEAT-3.8, ARC-A-141).**
  1. On **Skills > Tools**, every tool is listed with its capability and side effect.
  2. Open an agent's profile. Only the tools assigned to it are offered to its runs.
  3. Each tool says whose identity it runs as.
- Step 2. **A website is working (ARC-B-027, OWN-104, the HTTP half).**
  1. As yourself, grant the first person `read:website_check` scoped to one website host that you
     own.
  2. In an automation step, or once the agent runtime offers it, ask whether that site is working.
     The answer gives the status, any redirects, the days until its certificate expires, and the
     response time.
  3. Ask about a host outside the grant. It is refused.
- **What still waits, and I tell you when each is live:**
  - The read-only browser, browser writes, the browser scheduler, the independent judge and the
    signed exceptions (ARC-A-007, ARC-A-008, FEAT-9.x, ARC-B-012 to ARC-B-026, ARC-B-148, GAP-26,
    GAP3-07 to GAP3-10, OWN-97). These need the browser worker.
  - Skill scripts and code in a sandbox (FEAT-3.6, OWN-96). These need the script sandbox: the
    deploy agent's overlay, switched on in the installation settings.
  - Artifacts an agent produces (GAP-28, OWN-101).
  - Computer use (CONA-25, ARC-B-028, OWN-98, OWN-106, ANY-022). This is deferred by your own
    requirement until the browser checks are done.
- **The rest.** As in check 13.

## 120. Memory on your server - DECIDED 2026-10-05: A, take down Dify, the old Langfuse and the old v1 worker

**Your answer, 2026-10-05:** "Option A: take down Dify, the old Langfuse and the old v1 worker."

**What happens now:** I take the three down on the server myself (their data stays on disk and one command brings each back), measure the memory again, and give the freed room to row 1 (the personal-data detector) and row 3 (Langfuse with the file store). Row 2, the model server, waits: it does not fit beside row 1 on this server.

**In plain terms:** four things the Brain needs are waiting for memory on your server. Together
they need **7,424 MB**, and up to 2,048 MB more if you choose option B in item 119. Your server has
**248 MB** that nothing has claimed. This is the one memory question: how to make room, and which
of the four gets it first. (The automation canvas in item 124 would need another 512 MB, and I
recommend it waits.)

**What is waiting, in the order I would give it memory:**

| | What | Memory | What it unblocks |
|---|---|---|---|
| 1 | **The personal-data detector** (Presidio) | 1,536 MB | Your requirement GAP-23: before a question or passage goes to an outside model, names, ID numbers, phone numbers and email addresses in it are replaced with placeholders, and put back in the answer. Today text goes to the model provider as written. How it works is settled; only the memory is yours to decide. Task M32.2.1.1 |
| 2 | **The model server**, with the document worker and the file store | 3,840 MB (3,072 + 512 + 256) | Ten document tasks: tables and page layout in PDFs, scanned pages, Excel and PowerPoint, and search by meaning (M7.2.1, M7.2.3, M7.2.4, M7.2.6, M7.3.3, M7.3.4, M7.3.5, M7.7.8, M7.7.9, M7.7.10). Also the rest of GAP-23: the model server finds the names and details the detector's standard rules miss (M32.2.1.2). Also item 119's option A. The file store is item 122's option A |
| 3 | **Langfuse**, the screen engineers use to inspect each model call | 2,048 MB | M32.1.1.1 and M32.1.1.2. The Brain already records every call in its own ledger; Langfuse adds the screen. It keeps its files in the file store from row 2 (256 MB more if row 2 is not there) |
| 4 | **More memory for the Brain's program**, so it reads larger uploads itself | 512 to 2,048 MB | Item 119's option B. Not needed once row 2 runs, which reads every file people may upload |

**Why that order.** Row 1 first: it is a requirement you set, it is unmet on every question asked
today, and it is the cheapest. Row 2 next: eleven tasks, and the rest of GAP-23. Row 3 after: it
helps engineers, and the Brain already keeps its own record of every call. Row 4 last, and I would
not spend memory on it: row 2 does the same job and reads far larger files.

**What I measured (29 and 30 September), read-only, on the live server.** The machine has 11,960
MB. The figure that decides this is not what is free at this moment but what each container is
allowed to take, because a container can take its allowance the moment it gets busy. Those
allowances add up to 11,456 MB:

| Whose | Containers | Allowed |
|---|---|---|
| The Company Brain | 9: the program, its database, cache, worker, two connection poolers, the vault, and Keycloak with its database | 5,440 MB |
| Your other project: Dify | 10 | 3,712 MB |
| Your other project: the old Langfuse | 2 | 1,280 MB |
| Your other project: the old v1 worker (`verz-brain-worker-1`) | 1 | 1,024 MB |

The other project's three rows are the same 6,016 MB as in item 25. Two more have no allowance and
use real memory: Activepieces (827 MB) and Coolify with its proxy (about 600 MB), about 1,430 MB
together. The server keeps 256 MB for itself, so 11,960 less 11,456 less 256 leaves the 248 MB
above. It is also using 1,233 MB of its 2,047 MB of swap, which means it has already run short of
real memory at some point. None of the four rows has run on your server yet, so their figures are
the product's own sizes; I measure each one once it runs.

**Which of the other project's containers are in use.** Lines each wrote to its log in the last 24
hours: Dify's API 0, the old Langfuse 0, the old v1 worker 1 (a timeout warning), Activepieces
17,414. So Activepieces is in use and I leave it out of every option below. v1's nightly Laravel
sync is a separate run at 02:15, allowed 768 MB for the few minutes it runs, and does not use the
old worker.

**Option A: take down Dify, the old Langfuse and the old v1 worker.** That frees their 6,016 MB, so
6,264 MB is unclaimed; after what Activepieces and Coolify really use, about 4,830 MB is there. That
is room for rows 1 and 3 with the file store (3,840 MB, about 990 to spare), or for row 2 alone (the
same 3,840), but **not rows 1 and 2 together**: 5,376 MB would be about 550 MB short on a server
that is already using swap. It costs nothing and can be undone: their data stays on disk, and one
command brings each back. Only you know whether anything of v1 still needs them.

**Option B: a larger server, for example 24 GB instead of 12.** About 12,000 MB more. Rows 1 to 3
all fit with about 3,400 MB to spare even without A, and the other project is untouched. It costs a
monthly fee and a restart of a few minutes while your provider resizes it.

**Option C: nothing now.** The fourteen tasks above move to a later wave and GAP-23 stays unmet.
Until then the console reads plain text, Markdown, PDF and Word as text only (item 119 says how
large), and Excel and PowerPoint are not accepted.

**My recommendation: A now, then B.** A is free and makes room today for the detector (row 1), so
GAP-23 is met for everything but the names only the model server finds, and for Langfuse (row 3).
B then makes room for the model server (row 2) beside them, with a margin, so the ten document tasks
run without pushing the server into swap. If you would rather not pay for a larger server, reply A
alone: rows 1 and 3 go ahead and row 2 waits. If you are not sure about v1, choose B alone rather
than C. Building every one of these is my work and needs nothing more from you than the room.

**What I need from you:** reply "120: A then B", "120: A", "120: B" or "120: C".

For A (about five minutes):

1. On your Mac, open **Terminal**.
2. Type `ssh verz-vps` and press Return. You are now on your server.
3. Take down Dify: type `cd /opt/verz-dify/dify/docker && docker compose down` and press Return. It
   stops and removes Dify's ten containers. Its data stays in that folder.
4. Take down the old Langfuse: type `cd /opt/verz-langfuse && docker compose down` and press Return.
5. Stop the old v1 worker, and only the worker: type `cd /opt/verz-brain/infra/vps && docker compose
   stop worker` and press Return. The nightly Laravel sync in the same folder carries on as before.
6. Type `exit` and press Return.
7. Tell me "120: A done". I measure the server again and record the new figure in the product's
   budget, so each service is sized against what is really there.

To undo any of it later, run `docker compose up -d` in the same folder (or `docker compose start
worker` for step 5).

For B:

1. Sign in to the control panel of the company you rent the server from.
2. Open this server (6 cores, 12 GB of memory, 193 GB of disk) and choose the option to upgrade or
   resize its plan.
3. Choose a plan with 24 GB of memory. Keep the same disk and the same address.
4. Confirm. The server restarts, and the Brain is offline for those few minutes.
5. Tell me "120: B done". I measure the server again, as for A.

## 119. How large a file may people upload - DECIDED 2026-10-05: C now, then A once row 2 of item 120 runs

**Your answer, 2026-10-05:** "My recommendation: C now, then A once row 2 of item 120 runs."

**In plain terms:** the door to Knowledge accepts PDFs up to 50 MB, Word files up to 25 MB, and plain
text and Markdown up to 5 MB. The console cannot read files anywhere near that size today, because it
reads them inside the Brain's own program, which has little memory to spare. Two things are for you to
choose: how the console reads larger files now, and the size limit once the model server (item 120,
row 2) runs.

**What was measured (29 September), read-only.** The Brain's program is allowed 1,024 MB. It runs four
copies of itself so it can answer several people at once. Each copy holds up to 218 MB at its peak,
which is when the four start together, and the process that looks after them holds 82 MB, so the
program has used at most 955 MB. Almost all of that is the program's own memory; less than 1 MB is
file cache. Reading a file takes several times its size (the product's rule is four times for text,
six for a PDF, eight for Word), and each of the four copies may be reading a file at the same moment.

**What changes on its own with the next release.** Two fixes in the product need nothing from you:

- Until now the Brain checked each file against the wrong budget, so a large PDF could have run the
  program out of memory (pull request 265). It now checks against the program's own spare memory:
  48 MB, shared among the four copies, so **12 MB for each file**. The console then reads **text and
  Markdown up to 3 MB, PDFs up to 2 MB and Word files up to 1.5 MB**, and refuses anything larger
  with a message asking for it to be split.
- The program chose how many copies to start from its memory, allowing 180 MB a copy when each really
  needs 218. So "just give it more memory" was unsafe until now: at 1,536 MB it would have started
  seven copies, which need about 1,608 MB at start, and it would have been killed every time it
  started. Each copy is now sized at 220 MB (pull request 269), so more memory is safe, but it buys
  little, as option B shows.

**Question 1: how should the console read larger files?**

**Option A: send larger files to the document worker.** The document worker is a separate part built
for exactly this, with 448 MB to read one file, which is enough for everything the door accepts:
**text 5 MB, PDF 50 MB, Word 25 MB.** It needs row 2 of item 120 (512 MB for the worker and 256 MB for
the file store) and some building by me to hand it the console's uploads.

**Option B: give the program more memory.** More memory makes it start more copies, up to ten (the
most its database connections allow), and each copy may read a file at the same moment, so each gets
only a share of what is added:

| The program's memory | Copies | Room for one file | Largest PDF | Largest Word | Largest text |
|---|---|---|---|---|---|
| 1,024 MB (today) | 4 | 12 MB | 2.0 MB | 1.5 MB | 3.0 MB |
| 1,536 MB | 6 | 20 MB | 3.3 MB | 2.5 MB | 5 MB |
| 2,048 MB | 8 | 24 MB | 4.0 MB | 3.0 MB | 5 MB |
| 3,072 MB | 10 | 77 MB | 12.9 MB | 9.7 MB | 5 MB |

Text stops at 5 MB because that is the door's own limit. The extra memory is row 4 of item 120.

**Option C: read one file at a time across the whole program.** One file gets all 48 MB instead of a
quarter: **text 5 MB, PDF 8 MB, Word 6 MB**, with no memory and no server change. The cost is that two
people adding documents at the same moment wait for each other, a few seconds each. A small build for
me.

**My recommendation: C now, then A once row 2 of item 120 runs.** C quadruples the largest PDF this
week at no cost, and uploads are rare enough that a few seconds' wait is seldom noticed. A then reads
everything the door accepts. B is the poorest use of memory: 2,048 MB more buys PDFs of 12.9 MB, while
A's 768 MB reads PDFs of 50.

**Question 2: the size limit once the model server runs.** The model server (item 120, row 2) reads
PDFs with their tables and scanned pages, and Excel and PowerPoint. As sized it has 64 MB to read one
file, which is a PDF of about 10 MB or an Office file of about 8 MB. Reading bigger files means a
bigger model server:

- **25 MB for every document type:** it grows by 136 MB, to 3,208 MB. Word and Excel stay where they
  are; PDF and PowerPoint come down from 50.
- **Keep 50 MB:** it grows by 336 MB, to 3,408 MB.
- **10 MB (8 MB for Office files):** no extra memory, and ordinary PDFs of 15 to 30 MB are refused.

**My recommendation: 25 MB.** One figure for every document is easy for people to remember, it covers
nearly all everyday documents, and it costs the least memory of the choices that do not refuse
ordinary files.

**What I need from you:** reply "119: C, 25", or your choice for each question (A, B or C, and a size
in MB). Nothing on your server changes for either answer.

## 168. What a brand-new install ships with - DECIDED 2026-10-06: A, accept both

**In plain terms:** your plan says a new install is loaded with "the six roles, standard permission
sets, the standard agents and sensible defaults" (M41.2.7). Today a fresh install is furnished with the
roles, the standard permission sets and a company-wide scope, and the built-in agent templates are
there to install from the gallery. Two things in that sentence are done differently, and that was
decided inside the code rather than asked of you:

1. **The four "sensible defaults" are not written anywhere.** They are: sessions close after 30 minutes
   untouched, no session lasts longer than 10 hours, every action with a side effect needs a person's
   approval until somebody raises that, and new knowledge is visible to the uploader's department and
   no wider. Nothing reads them as settings: the first two are fixed in the sign-in code (your item
   19), the third is how the autonomy levels already behave, and the fourth is how knowledge is
   already filed. So writing them down would create four settings that change nothing.
2. **No agent is installed at the start.** The built-in templates are there (signed when the product
   starts), and installing one is a step somebody takes from the gallery, at the Shadow level, so a
   new install does not start with an agent already answering people.

**Option A: accept both.** A new install ships with the roles, permission sets, scope and templates;
the four defaults are how the product already behaves, and the Settings page says so in a short note.
Nobody has an agent answering before they choose one.

**Option B: build them.** The four defaults become settings the product reads (so a company can change
them without a release), and the install ships with one standard agent per template, installed at the
Shadow level and answering nobody until promoted.

**My recommendation:** A, with the note on the Settings page. B costs a good deal and adds risk
(session length is a security setting) for no behaviour you do not already have.

**Decided 2026-10-06: "168: A".** A new install ships with the roles, permission sets, scope and
templates. The four defaults stay how the product already behaves, and the Settings page says so in a
short note (built). Nobody has an agent answering before they choose one.


## 135. Google Drive: Viewer or Editor on the folder - DECIDED 2026-09-30: A, Viewer

**In plain terms:** when you connect Google Drive (item 126's list; its steps come to this page when
it can read), you share one folder with an account made just for the Brain. The Brain promises that
a file shared outside your company is never read. The catch: Google only tells an account who a file
is shared with if that account is allowed to share the file itself, and a Viewer is not. So with
Viewer access the Brain cannot see, for most files, whether they have been shared outside.

**Option A: Viewer on the folder.** If the Brain's key file ever leaked, whoever held it could read
that one folder and change nothing.
- A file whose sharing Google does not show is treated as the folder's, because you chose to share
  the folder.
- A file Google does show as shared by link or shared outside is never read.
- A file with its own, narrower permissions is never read (a Viewer can see that much).
- So the promise becomes "a file shared outside your company is left out wherever Google shows its
  sharing".

**Option B: Editor on the folder.** Every file's sharing is visible, so "a file shared outside is
never read" holds for every file. The Brain still only ever asks Google to read, so it cannot change
anything itself, but a leaked key file could be used to change or delete files in that folder.

**My recommendation: A.** The folder is already your decision about what the Brain may read, and a
key that can only read is the safer thing to keep on a server. A is what is being built; switching
to B later is one small change and one step in the guide.

**Your answer, 2026-09-30:** "135: A".

**What that means:** the Brain's Google account is a Viewer on the one folder. Files Google shows
as shared by link or outside your company, and files with their own narrower permissions, are never
read; a file whose sharing Google does not show is read as the folder's. Drive's connect steps come
to this page when it can read.

## 125. Where the evening build digest is sent - DECIDED 2026-09-30: a group with just you, on any channel

**Your answer, 2026-09-30:** "I will go with your recommendation which is a new group with just you
in it, so the digest never lands in a chat other people use for work. But you also need to consider
that currently you connected so you are sending it to Lark but when you connect other Channels then
where will you send the Digest?"

**What that means, and how it is built:** the digest is not tied to Lark. Where it goes is one
setting in the console, **Send the evening digest to**, which offers every channel connected at the
time and a conversation in it: a Lark group today, and a Slack channel, a Teams channel or an email
address once those are connected (item 126). You change it whenever you like, it is off until
somebody chooses, and the change is recorded with your name. Every company that installs the Brain
chooses its own in the same place.

**What you do:**

1. **Switch on the Lark app's chat channel first**, or the app does not appear under Add bot (you
   found this on 2026-09-30: the app was set up for the staff list only). In the console open
   **Connectors**, press **Manage Lark** on the Lark card, then **Add a use to Lark**, tick **Chat
   channel**, and follow its screens: turn on the app's **Bot** feature in Lark, batch-import the
   permissions, paste the **Encrypt Key** and **Verification Token** and save, point Lark's
   **Request URL** at the address the console shows and add the **Message received** event,
   release a new version and have it approved, then **Test connection** and **Save and switch on**.
   This also lets linked people ask the Brain in Lark.
2. In Lark, create a group chat with just you in it, for example "Brain daily".
3. Open the group's settings, choose **Bots**, then **Add bot**, and pick the Brain's Lark app.
4. When the digest is built I tell you, and you choose that group under **Send the evening digest
   to** in the console. Nothing to reply with now.

## 126. Every service connectable from the console, one at a time - DECIDED 2026-09-30

**Your answer, 2026-09-30:** "You need to do all one by one so that I can login to console and connect
them through step by step instructions/screens provided in the backend console itself."

So every service in the list is made connectable from **Connectors**, **Connect a source**, with its
own step screens, one at a time, and I tell you each time one is ready. You connect it yourself and
paste its key only into the console. **The order:**

1. **Ready now:** Xero, HubSpot, Freshdesk (steps below, and on their Connect screens).
2. **Next:** Google Drive, then your Laravel system (task M11.7.7: their last step moves from the
   server into the console).
3. **Then the channels:** email, Slack, Microsoft Teams, Telegram, WhatsApp (task M10.6.1 wires each
   one end to end, and each gets its own Connect screens).
4. **Then the new sources:** Google Workspace, Google Analytics, Google Search Console, Cloudflare,
   your domain registrar and hosting, and Slack as a source.

After you connect one, press **Test** on its card and tell me "connected Xero" (or whichever); I prove
it on your install and close its tasks.

**Ready now: Xero, HubSpot and Freshdesk.**

Each takes about ten minutes. In the console open **Connectors**, press
**Connect a source**, choose the service, and follow its screens, which show a picture of each step;
the same steps in words:

**Xero** (invoices and contacts, read only)

1. Sign in to Xero's developer portal (developer.xero.com, **My Apps**) with an account that
   administers your organisation, and press **New app** (Xero may offer it as a custom connection).
   Name it "Company Brain". Give it exactly two scopes, `accounting.transactions.read` and
   `accounting.contacts.read`, and nothing ending in `.write`.
2. Press **Authorise** for the one Xero organisation the Brain should read, then copy that
   organisation's id (Xero may call it the tenant id) and the key Xero issues.
3. In the console, on Connect Xero's last screen, paste the organisation id and the key and press
   **Connect Xero**. The key goes straight to the vault and is never shown again.

**HubSpot** (contacts and deals, read only)

1. In HubSpot, press the settings gear at the top right, then **Integrations**, **Private Apps**
   (HubSpot may list it under **Development**, **Legacy apps**), and press **Create a private app**.
   Name it "Company Brain".
2. On the **Scopes** tab tick `crm.objects.contacts.read` and `crm.objects.deals.read` and nothing
   with "write" in it or touching settings. Press **Create app**, confirm, and copy the access token.
3. In the console, on Connect HubSpot's last screen, paste the HubSpot account id (shown in the
   account's settings) and the token, and press **Connect HubSpot**.

**Freshdesk** (tickets, read live)

1. Choose the Freshdesk agent the Brain reads as: someone who sees the tickets it should answer
   about and no more, and never an administrator.
2. Sign in to Freshdesk as that agent, press the profile picture at the top right, open **Profile
   settings**, and press **View API key**. Copy it.
3. In the console, on Connect Freshdesk's last screen, type your helpdesk's address (ending
   `.freshdesk.com`), the short name of the one department whose people may be granted its
   tickets, paste the key, and press **Connect Freshdesk**.

After each one, press **Test** on its card, then tell me "126: connected Xero" (or whichever), and
I prove it on your install and close its tasks.


## 118. An approval card reaches the approver in Lark as soon as it is raised - DECIDED 2026-09-29: B

**In plain terms:** the approver in Lark used to see a card only after writing "approve" to the
Brain's bot, because the Brain kept only a fingerprint of each person's Lark identity and no address
it could send to. **Your answer, 2026-09-29:** "B: store each linked person's Lark address so the
card can be sent straight away."

What is being built:

1. **Each linked person's Lark address is kept** beside the fingerprint, treated as personal data:
   removed when the person is erased, never shown on a screen.
2. **The card is sent to the approver the moment the approval is raised**, in their own Lark chat.
   Whether pressing it decides the approval is item 117's setting.
3. The same stored address is what signing in with Lark (item 115, option A) will use later.

The decision is applied to every channel that carries a person's own address (Lark, Slack and
email), because items 125 and 126 made delivery channel-agnostic.

**What you do:** nothing.

## 116. Who may see the records in a Lark Base - DECIDED 2026-09-29: the Brain's own roles and permissions

**In plain terms:** the Lark Base connector reads your Base tables so the Brain can answer from them,
and somebody has to decide who may see which table's records. **Your answer, 2026-09-29:** "It should
be based on Roles & permission that we have in the brain system in Backend Console."

What that means: **option A.** A Base table is governed exactly like every other source. An
administrator or data steward grants a department or a person access to a table, and to its columns,
on the Brain's own screens, and every grant is recorded. Lark's own sharing is not consulted, so the
answer never depends on how a table happens to be shared in Lark. Nobody sees a Base table's records
until they are granted.

**What you do:** after the Lark Base connection is live, grant each table on the console as you do any
other source. I will tell you when it is ready and where.

## 115. How the people on your Lark staff list become Brain users - DECIDED 2026-09-29: B now, A next, and no emails sent

**In plain terms:** the staff sync reads your people from Lark and places them in departments, but it
created no Brain accounts, so none of them could sign in. **Your answer, 2026-09-29:** "I will go with
your recommendation: B now, A next. B gets your people onto the Brain soonest and suits any company.
A then gives Lark companies one-click sign-in without passwords." **And then:** "do remember not to
send the Link to them ... they need to click Forget Password on the login page and then they will get
the link. I don't want to send the bulk email to all. Only those who click forget password will get
the link."

What is being built, in this order:

1. **B, now: the sync creates each active person's Brain account, and sends nobody anything.** No
   invitation and no bulk email, ever. A person who wants to start presses **Forgot password** on the
   sign-in page, enters their work email, and only then gets a link to set their password; at their
   first sign-in they set up their second factor. Suspended people and leavers get no account;
   outsourced people get none unless an administrator allows their employment type. When someone
   leaves or is suspended in Lark, the next sync closes their account. It works the same for any
   company, whatever its staff source.
2. **Then the work this was holding up:** each person's status and employment type on People,
   suspended and outsourced people kept out of the Brain, and the choice of where departments come
   from (Lark's, or your own with people assigned to them).
3. **A, next: sign in with Lark**, as a second way in for companies whose staff list is Lark, with no
   password. It uses each person's stored Lark address (item 118).

**What you will need to do:** tell people their account is ready and to use **Forgot password** on
the sign-in page the first time; People will show that sentence ready to copy. If the sign-in
service has no email settings on your install, Forgot password cannot send its link, and the staff
source's page will say so and tell you what to fill in.

## 117. Approving by pressing a button on a Lark card - DECIDED 2026-09-29: yes, once Lark requires two-step verification

**In plain terms:** you asked that approvals be decided only in the console or on Lark cards
(OWN-147), and that approving needs a sign-in with a second factor (DEF-06). On a Lark card the Brain
checks that the press came from the Lark account linked to the person the card was made for, and for
the same action, but it cannot tell whether that person signed in to Lark with two-step verification.
**Your answer, 2026-09-29: "Yes, you can proceed with your recommendation"**, which was to switch
approving from Lark cards on once your company's Lark requires two-step verification for everyone.

What that means, and what was built:

1. **Every install ships with the setting "Approve from Lark cards" off.** While it is off a card shows
   the request and a link to decide it in the console, where the second factor is asked for.
2. **Switching it on is an audited administrator change**, and its help text says in plain words that
   a card press relies on the company's own Lark sign-in.
3. **DEF-06 now records this as its decision:** a card press approves without the Brain's own second
   factor only while that setting is on.

**What you do, once, after the approval cards are live (I will tell you when):**

1. In the Lark Admin console, open the security settings and find two-step verification. Check that it
   is required for all members, not merely available. If it is not, turn the requirement on there first.
2. Tell me "Lark two-step is required", and I switch **Approve from Lark cards** on for your install, or
   show you where it is on the console's settings.

**Reversible:** switch the setting off and every approval goes back to the console.

## 114. The vault opens itself, and every release keeps it up to date - DECIDED 2026-09-29

**In plain terms:** the secrets vault used to need three of five key pieces after every restart,
and a release that changed what the application may read waited until three people made a root
token. On 29 September two such changes waited and the pieces could not be found. **Your answer,
2026-09-29: "okay build them".** What was decided, and built:

1. **The vault opens itself when the server starts**, from a key file only root on the server can
   read (`/etc/brain-vault/seal.key`). A restart or a reboot needs nobody.
2. **Every release applies its own vault policies, engines and roles during its deploy**, with a
   deploy token kept root-only beside the seal key, reads each back, and stops the deploy loudly if
   one did not take. No people, no pieces. The deploy token cannot widen its own policy.
3. **Recovery pieces are an optional emergency spare, chosen at install**: one recovery key by
   default, written to a root-only file for you to move into your password manager; five pieces,
   any three, still offered with `--recovery-split`. A recovery key never opens the vault; it makes
   a root token in an emergency.
4. **Nothing you see shows a key.** The console stays write-only.

**The trade-off you accepted:** anyone with root on the server can open the vault. On one server
that person can already read the running application's memory, where every key the vault hands out
ends up, so the pieces bought a ceremony at every restart rather than protection. **Reversible:**
say so and the vault moves back to pieces held by people (a rekey and a seal migration the other
way, with the recovery key).

**What was measured on the way, and changed the plan for your server.** OpenBao 2.4.1 refuses to
recreate a token under an id beginning `s.`, which every token it mints has, so a new vault beside
the old one could never take over the application's and the worker's tokens; those live in your
hosting panel's stored settings, which were not to change. The move is therefore made in place: the
same vault, the same tokens and secrets, with only what locks its data changed. That needs three of
its unseal pieces, and they exist in the file the 2026-09-21 setup wrote. Without pieces there is no
in-place move; the rebuild (a new vault, secrets copied across, new tokens written into the hosting
panel) is not built, because it changes the one thing that was not to change. Ask for it if a vault
ever loses its pieces.

**What you do, once (about two minutes of the vault being unavailable):** on the server, as root,
from the copy of this release's `ops/openbao` directory the pull request says where to find, run
`bash switch-to-auto-unseal.sh --pieces-file <the 2026-09-21 setup file>`. It proves the pieces
before changing anything, keeps a dated copy of the vault's data under `/root/brain-vault-backups`,
and ends with a short summary. Then: copy `/etc/brain-vault/seal.key` into your password manager as
its own entry, move `/etc/brain-vault/recovery.key` into it and delete that file, and delete the
setup file too: after the move its pieces open nothing. `--rollback` puts everything back while the
dated copy exists. Rehearsed end to end on throwaway containers on your server on 2026-09-29, never
touching the running vault. `ops/openbao/UNSEAL.md` is the plain-words guide.

## 113. "Each of the four providers answers" waits until OpenAI and DeepSeek are used again - DECIDED 2026-09-29

M5.7.1 names all four providers and asks that each answers on the install. On 2026-09-29 Anthropic and
Moonshot answered; OpenAI refused with 429 and DeepSeek with 402 (no balance). **Your answer, 2026-09-29:**
"you can ignore them as I will deactivate them for now and will use it later". Both were turned off on
Models and health the same day, so M5.6.1 (every provider that is switched on answers) closes on Anthropic
and Moonshot, and M5.7.1 moves to Wave 5, when the other two are funded and switched on again. Nothing is
removed; reversible: switch them on and it moves back.

## 112. The four "every requirement in an area is demonstrated" tasks move to their proofs' wave - DECIDED 2026-09-29

M1.8.8 (permissions), M2.3.2 (departments), M5.6.5 (models) and M24.3.6 (observability) each close only
when every requirement row of their area has its proof on the install. Measured on 2026-09-29, none of
the 188 rows had all its proof tasks done, and most of those proofs are later waves' work (69 of the 80
permissions rows are proved in Wave 3). They sat in Wave 1, where nobody could finish them. **Your
answer, 2026-09-29: "yes move them".** Models moves to Wave 3, permissions and departments to Wave 4,
observability to Wave 5, the wave of each area's last proof. Nothing is removed from the programme and
the total is unchanged; reversible: say so and they move back.

## 111. Promoting knowledge company-wide still takes two people - DECIDED 2026-09-29

K2: a Super Admin cannot approve their own promotion of knowledge to company-wide, so an install with
one Super Admin cannot promote anything until a second is named. The two-person rule stays. Decided by
default on 2026-09-29 under the owner's standing approval; reversible: say so and it is undone.

## 110. Freshdesk reads into one department in Wave 2 - DECIDED 2026-09-29

M11.9.6: in Wave 2 one department reads a whole Freshdesk helpdesk. Mapping each Freshdesk group to its
own department waits for the row-plane work. Accepted for Wave 2. Decided by default on 2026-09-29
under the owner's standing approval; reversible: say so and it is undone.

## 109. A Starter pack an administrator removes stays removed - DECIDED 2026-09-29

A follow-up to item 105: when an administrator removes a Starter pack the staff sync gave someone, the
removal is recorded, so the next sync does not give it back while the directory still places that
person in the department. Build it; it needs a migration. Decided by default on 2026-09-29 under the
owner's standing approval; reversible: say so and it is undone.

## 108. Archiving knowledge and exporting its inventory - DECIDED 2026-09-29

M27.15.40: a migration lets an archive write go past `know.item`'s policy, and a data set on
`ops.data_export` exports the knowledge inventory. Build it. Decided by default on 2026-09-29 under the
owner's standing approval; reversible: say so and it is undone.

## 107. Test connection on Connectors records its probe - DECIDED 2026-09-29

M27.15.8: a migration gives the worker's attempt table a "probed" outcome, and the worker runs a probe
when asked, so one throttled test is recorded on the source's health. Build it. Decided by default on
2026-09-29 under the owner's standing approval; reversible: say so and it is undone.

## 98. The Moonshot key - DONE 2026-09-28

All four keys are in the vault: Anthropic, OpenAI and DeepSeek from 16:01 to 16:03 SGT and Moonshot at
16:09. A Test on the Models screen had Claude answer (claude-sonnet-5). The other three answer once the
failover matrix names them, which waits on a golden question the Brain can answer (item 105's grants).

## 106. Company-wide documents reach everyone - DECIDED 2026-09-28

A right to read document text in a department also reads company-wide documents and the person's own
personal ones, so company-wide means everyone. Nothing belonging to another department becomes readable.

## 105. Who reads uploaded documents - DECIDED 2026-09-28

Every person the staff sync brings in gets the Starter pack for their own department automatically;
administrators still add or remove anything on Govern > Roles. Uploads are checked for being a genuine,
safe file; an antivirus comes with the scanning package later in Wave 2.

## 104. A reference under every answer - DECIDED 2026-09-28

Every answer shows a short reference, and a Super Admin can look that reference up to see its risk
score, level, model and why each was chosen. No screen lists everybody's questions.

## 103. A second install and the load test run in CI - DECIDED 2026-09-28

Replied "Use CLI", read as the recommended "use CI": M12.3.1 and M12.4.9 use a scratch install built
inside CI, and M22.3.3's load test runs there, never on the company's install.

## 102. Which accounts some connectors use - DECIDED 2026-09-28

As recommended: Teams and Telegram are proved on a free Microsoft 365 developer tenant and a test
Telegram bot; Google Drive only for now; M11.4.8's backfill fills the small index only. The maintenance
portal is a Laravel system on MySQL.

## 101. Duplicate tasks merged - DECIDED 2026-09-28

M12.4.16 into M12.4.11; M7.7.5 and M10.7.5 into M10.7.2; M11.9.1 into M11.8.1; M11.9.2 into M11.5.1;
M12.4.1 into M12.3.8; M8.3.3 into M10.7.1; M8.1.3 into M11.4.9; M22.2.4 into M7.1.5; M11.5.3 into
M22.1.1; M9.1.4 into M25.3.1; M23.2.3 into M21.3.2; M27.13.4 into M12.2.2. M11.2.2 is proved by the
first connector sync that proves M31.3.2.3 and M31.3.2.4.

Eleven more were merged on 2026-09-28 under the blanket approval for exact duplicates in Waves 3 to 5:
M27.15.59 into M27.15.8; M13.8.16 into M13.8.19; M36.1.4.2 into M30.4.9; M40.4.2.2 into M33.3.1.3;
M40.2.1.3 into M33.3.1.5; M14.4.3 into M14.3.5; M16.3.3 into M16.7.3; M39.4.2.5 into M16.7.13;
M30.5.3 into M27.7.16; M27.4.1 into M27.7.18; M18.1.1 into M18.5.3.

## 100. The agent halves move to Wave 3 - DECIDED 2026-09-28

M11.9.3 to M11.9.14, M11.8.8, M10.7.3, M12.2.5, M12.2.7, M12.2.8, M12.3.3, M12.4.8, M12.4.10, M8.2.4,
M8.3.5, M11.8.10, M12.4.2 and Wave 1's M5.7.3 move to Wave 3 whole, as item 97 did: their Wave 2 parts
are built now and each closes when its agent part is proved. M38.2.2.3 now reads "a real question
answered live in Lark from a connected source".

## 99. How connected systems answer questions - DECIDED 2026-09-28

Connectors keep a small index and read everything else live when asked, borrowing the source's key for
that one question (the vault's rules are reloaded once, with three unseal pieces). Drive and Wiki text
is searched live, never copied or embedded. Answers must stay fast: live reads run in parallel under a
time budget, and a slow source is cut off and named rather than making the person wait.

## 97. The chat parts of two install checks move to Wave 2 - DECIDED 2026-09-28

M1.8.5 (sign-in) and M2.3.1 (department scoping) moved to Wave 2, which builds the Lark chat
channel their chat steps need. Their web steps stay in item 91.

## 85. Your AI provider keys - DONE 2026-09-28 (three of four)

The Anthropic, OpenAI and DeepSeek keys were saved into the vault from the console between 08:01
and 08:03 UTC, which proves M5.1.2. No Moonshot key arrived; item 98 has the last steps.

## 96. Directory groups grant roles only - DECIDED 2026-09-22

Roles and permissions are managed in the admin console. Staff are synced from the source into the
console, and roles are assigned to them there. A directory group can be mapped to a role, never to
a permission pack, so nothing edited in another system hands out access here.

## 95. Two tasks moved to the wave that builds what they need - DECIDED 2026-09-22

M3.2.2 (ignoring a chat message delivered twice) moved to Wave 2; M3.7.2 (sharing the provider's
tool cache) moved to Wave 3.

## 93. The LDAP library is allowed - DECIDED 2026-09-22

`ldap3` is allowed on the same terms as the database driver, so Active Directory can be chosen as
a staff source (M1.6.6).

## 89. LDAP / Active Directory - DECIDED: build it ready to use

Not needed for your install, but built so a later company with Active Directory can choose it and
connect. The adapter is built and tested; item 93 asks to allow its library.

## 87. Where the daily audit fingerprint is kept - DONE 2026-09-21

The private repository `rpsj2230/brain-audit-anchor` holds it, written by a deploy key that can
reach nothing else. GitHub refuses branch protection on a private repository without GitHub Pro,
so the daily job itself checks that the last fingerprint is still there.

## 94. The application's database password - DONE 2026-09-21

You replaced it with letters and digits only; the application and the post-deploy checks both
connect with it, and every check passed.

## 90. Lark staff list - DECIDED: built into the Connect Lark flow

The Lark contact permissions and the staff-list connection are part of the Connect Lark flow
below; nothing to do in Lark by hand.

## 88. A leaver's agents - DECIDED: they stop until a new owner accepts

## 86. How the Brain calls AI providers - DECIDED: direct calls

The Brain calls each provider directly, with retries, timeouts and fallbacks in the product; no
LiteLLM. M5.1.1 is recorded as decided.

## 81. Connecting Lark - DECIDED: a Connect Lark flow in the console

You have not created a Lark app yet, and you do not need to by hand. The console gets a Connect
Lark flow that walks you from creating the app in Lark's developer console, screen by screen, to
choosing what it is used for (staff list, knowledge from Wiki and Base, chat channel), pasting its
App ID and Secret into the vault, testing each use, and switching them on. Knowledge follows your
rule: a small index, content read live, never bulk-copied. Being built now.

## 84. The server's swap file and the vault - DECIDED: accepted for now

You accepted the unencrypted swap file for now; turn it off or encrypt it at the next server change.

## 92. The department audit task that contradicted your decision (M24.3.5) - DECIDED by item 48

M24.3.5 asked for option B of item 48; you chose option A on 2026-09-09, so it is recorded as
decided as not needed as written.

## 75. A secrets vault on your install - DONE 2026-09-21

The vault runs beside the Brain in its own project, so a redeploy never locks it. It is opened,
its audit logs are on, the three role policies and the seven connector key slots are defined, and
the application and worker each have a token that carries only their own policy. Every readiness
part now reports ready, the vault included. Move the five unseal pieces into your password manager
and delete the file, as I described in chat.

## 77. Your other GitHub repositories - DECIDED: out of scope

The product lives only in `rpsj2230/Verz-OS-v2.0`. Your other repositories are left alone and not
raised again, so M41.3.2 is decided as not needed as written.

## 83. The Maintenance agent in Lark (M38.5.3) - DECIDED: end of Wave 3

It needs connectors, knowledge and agents, which Waves 2 and 3 build, so it moves there.

## 74. The application's own limited database login - DONE 2026-09-21

You set the password and the variable. The application now answers as `brain_app` through the
pooler, and the console Overview shows "database login: ready". A `$` in the password was removed
on its way into the container until you ticked **Is Literal?**; the install guide now warns about it.

## 73. A Coolify API key for me - DONE 2026-09-21

The key (with read:sensitive) is saved on your server. PgBouncer and the database memory setting
are live, and every application connection comes through the pooler. The worker and the secrets
vault (item 75) are being added next.

## 72. The GitHub switch for the post-deploy checks - DONE 2026-09-21

`POST_DEPLOY_CHECKS` is `on`. Each Deploy run now waits for the server's verdict on the security
checks and goes red if one fails.

## 82. Wave 0's last three questions - DECIDED

1. **Your server is your first company's production install,** not a staging copy. Every later
   company (Company B, C, ...) gets its own server set up with the installer. So M38.1.4.2 and
   M38.1.4.3 (a separate staging project and a production that deploys after it) are decided as not
   needed as written. Every release is still gated by CI, the health gate, rollback and the checks
   after each deploy.
2. **The starter pack (M41.2.7) moves to Wave 3,** where the signing key it needs is built. Your
   installer requirement is recorded as OWN3-1: any AWS instance or VPS, a clean simple interface,
   connectors and channels connected during setup, and the Brain ready when it finishes. Two tasks
   were added for it: a channels step in the wizard (M42.5.16) and a full run on a fresh AWS
   instance and a fresh VPS (M42.5.17).
3. **Automatic rollback (M38.1.3.4)** is proved by the CI test that fails if the rollback is removed.

2026-09-29: the owner pulled the signing key forward; built in #187.

## 80. A local model for the local-only profile - DECIDED: hosted providers only

You use Claude (Anthropic), OpenAI, DeepSeek and Moonshot Kimi; no local-only profile is needed.
M41.1.6 is recorded as decided. Provider keys are asked for in Wave 1 (M5.7.1).

## 79. Sign in to staging in Claude's browser pane - DONE

## 78. The Lark wiki connector stores no page - DECIDED: my recommendation

Checking now with the Lark command-line tool, read-only, whether a real wiki page carries the
permission field; the fix follows from what it shows.

## 77. Release tags and the full profile - DECIDED: my recommendation

The first release tag is cut when Wave 0 is accepted. The full profile (M0.4.2) moves to Wave 1,
beside the redactor that uses presidio. Archiving v1 is item 77 above.

## 76. How GitHub reaches the staging database - DECIDED: it does not

You said to do what is best. Not a self-hosted runner: the repository is public, and a runner on
your server would run code from anyone's pull request. The server runs the invariant checks itself
after each deploy, beside the security checks it already runs, and reports only passed or failed.

## 75. A secrets vault on staging - DECIDED: yes

I set it up once item 73's key is saved, because it changes Coolify's stored settings.

## 71. Four unfixed Debian findings - DECIDED: accepted until 2026-10-21

## 70. Seven licences - DECIDED: all seven allowed

## 63. A second login factor in the consoles - DONE

You have Google Authenticator set up.

## 69. Make the repository private and protect main - DEFERRED by you, on purpose

You keep the repository public for now and will make it private and protect main yourself later.
Recorded as your own step (M0.1.1, M38.1.1.5), off Wave 0's build count. Not raised again.

## 68. The owner's architecture review - DECIDED

**Recorded 2026-09-17, from your review of the architecture.** You approved the changes and the six
decisions below.

**In plain words.** This item is where those decisions are written down, so that nobody building
from here follows an older rule that the code still states. Nothing in the code changes in this
item. Where the code writes down a rule that a decision overturns, the rule is named below by file
and name, and it changes when the work that needs it is built, together with its tests.

**The changes.**

- **An agent's reach only ever narrows.** An agent sees what the person asking can see, cut down
  further by the agent's own ceiling, and never more. The channels and connectors listed on an agent
  are compiled into that ceiling rather than checked on their own.
- **A connector attached to an agent is a setting, not a second permission system.** Attaching one
  decides what the agent may use. Who may see what is still decided in one place.
- **Pricing stays as table rows,** classified like every other row.
- **Several agents working together is built last.** Workflow steps that run side by side come
  first.
- **One context assembler, reading the stores that already exist.** Project context and a person's
  own context are read again every time, never kept from an earlier request.
- **Computer use is a last resort.** Website checks use plain web requests and a browser that only
  reads.
- **Approvals happen only in the console or on Lark cards.**
- **A thumbs up or down is counted, and changes nothing on its own.**
- **Depth before breadth.** One complete maintenance agent working on your install comes first.

**The decisions.**

- **D1. A workflow may contain model steps and skill steps,** and they run only through the one
  agent runtime, so they are leashed, permitted, approved and audited like any agent run. This
  overturns `DETERMINISTIC_ONLY` in `ops/automation.py`, which keeps anything needing judgement out
  of a flow, and `NodeKind` in `builder/compose.py`, whose five kinds of node leave no place for
  one.
- **D2. A specialist that another agent hands work to runs at the asking person's reach intersected
  with the specialist's own ceiling,** and only along delegation links an administrator has set.
  This overturns `EVERY_HOP_ONLY_NARROWS` and `AN_AGENT_IS_NEVER_THE_CALLER` in
  `orchestration/delegation.py`, and the fold `chain_reaches` computes there, which narrow the
  specialist's reach by the ceiling of every agent on the way to it.
- **D3. Connector keys live in the vault,** deployed with the worker on the install.
- **D4. The two-person rule stays for irreversible actions, and an administrator may approve a
  skill they imported,** with that approval recorded. This overturns
  `NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED` in `console/skill_library.py`, which refuses the person
  who added a skill whatever they hold.
- **D5. A correction may carry the right answer.** It is held as a learning candidate, with
  permissions like any other record, until it is approved. This overturns `Correction` in
  `chat/turns.py`, which has no field for the corrected content on purpose, and
  `A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED` in `ops/feedback.py`, which keeps a flag to a
  closed list with no free text.
- **D6. Computer use is deferred.** Browser checks come first.

**Until that work is built,** a reader who meets one of the rules named above should read it as the
rule this item replaced, not as the current decision.

## 67. Nobody on an install could ever be given a read of the company's data: where does the first one come from? - DECIDED: Option A, a data steward is named in setup

**Your answer, 2026-09-17:** "go with option A. Name a data steward in setup (recommended)".

**In plain words.** Nobody can grant a permission they do not hold themselves, and the first
administrator holds every permission for running the system and none for reading the company's
data, on purpose. Both rules are right, and together they meant that on every install nobody
could ever be given a read of a client, a deal or anything a connected source holds. The admin
console architecture (Part 6.1) put three ways out to you.

**Option A (chosen): a data steward named in setup.** The setup wizard now has a screen after the
administrator's that names one person as the data steward. That person is granted the right to
grant and the console's content plane over everything, and every connected source's reads as the
source is connected. Everybody else's reads of your data are granted by the steward, or by somebody
the steward granted. The steward is somebody other than the administrator unless you choose, on
that screen, to make the administrator the steward as well, and every grant is in the audit trail
against whoever made the appointment.

**Option B: grants from directory roles.** Not built: it needs the directory sync runner, and a
spreadsheet staff list cannot say who holds which role.

**Option C: let a company-wide granter grant anything.** Rejected: it breaks the rule that a grant
never exceeds its granter, which is what makes handing out permissions safe.

**What changed for an install set up before today, your staging install included.** Nothing is
appointed there, so the People screen now carries a Data steward card. At the next start your
administrator account is granted the one new permission that card needs. Open People, and in the
Data steward card either name another person or appoint yourself as the administrator and the data
steward. Sign in with your second factor first; the card does not appear without it. A steward is
named once, and the console does not replace one.

## 66. One setting in Coolify so the Brain can check Keycloak sign-ins - DONE: readiness reports sign-in ready

**What you do: add one environment variable in Coolify. Nothing is broken while it waits, but nobody
can sign in to the Brain until it exists.**

**In plain words.** The Brain now checks every sign-in against Keycloak for real. To do that it has
to know which Keycloak realm to trust, and your Brain service in Coolify does not have that setting
yet. Without it the site keeps working exactly as today, and every sign-in is refused.

1. Open Coolify the way you normally do, and open the **Company Brain** service.
2. Go to **Environment Variables**.
3. Add a new variable. Name: `INSTALL_OIDC_ISSUER`. Value: the address of your Keycloak realm, which
   is your Keycloak address followed by `/realms/brain`, starting with `https://` and with no slash at
   the end. I give you the exact value in chat, so your server's address stays out of these files.
4. Click **Save**, then **Deploy**.
5. Tell me when it has deployed. I then check, read-only, that the Brain reports sign-in as ready.

**Why it is safe to do now.** The Brain only reads this value. If it is wrong, the site still stays
up and sign-in simply stays refused, and the readiness page names sign-in as the part that is not
ready.

**Done 2026-09-16.** You set it on both services. Measured read-only: the app container carries
the issuer, and `/health/ready` reports `sign_in` true.

## 65. One line to change in Coolify's copy of the compose file - DONE

**What you do: replace one line of text in a text box in Coolify. Nothing is broken while it waits.**

**What the "code" is.** Coolify keeps the list of containers for your Brain as a block of text,
which it calls the compose file. You edit it in a text box on a Coolify page, like editing a
document. The line below is a line of that text, not a file on your computer and not something to
run. The `${...}` part is how that text says "use the value of the setting called `APP_IMAGE`".

1. Open Coolify the way you normally do.
2. Open the **Company Brain** service.
3. Click the **Configuration** tab, then **Edit Compose File**. A text box opens.
4. Press **Ctrl+F** in the text box and search for `APP_IMAGE`. The first match is on a line that
   starts with `image:`, under the `app:` block, and looks like this (your address after `:-` may
   differ slightly):

   ```
       image: ${APP_IMAGE:-ghcr.io/rpsj2230/verz-brain-v2.0:latest}
   ```

5. Select that whole line and replace it with this line, keeping the same spaces at the start:

   ```
       image: ${APP_IMAGE:?set APP_IMAGE to the image and release tag this install runs}
   ```

   The only real change is `:-` followed by an address becoming `:?` followed by a message. The old
   line means "if `APP_IMAGE` is empty, quietly use the latest image". The new line means "if
   `APP_IMAGE` is empty, refuse to start and show this message".
6. If the search finds more lines starting with `image: ${APP_IMAGE:-`, replace each the same way.
7. Click **Save**, then **Deploy**.
8. When it finishes, open your Brain address with `/health/ready` added to the end. It should answer.

**If the deploy fails**, open **Edit Compose File** again, put the old line back, save and deploy,
and tell me. That returns everything to how it is now.

**Done 2026-09-16.** The app container runs with `APP_IMAGE` named, so nothing starts on an image
nobody chose.

## 52. Two workflow files carry your server's address, and one repository variable removes them - DONE

**What you do, and it is one value in a settings page.**

1. Go to `https://github.com/rpsj2230/Verz-OS-v2.0/settings/variables/actions`.
2. Click **New repository variable**.
3. Name it `BRAIN_URL`. The value is the address this system answers on, the one you
   type to reach the console, with no path after it.
4. Tell me, and I remove the address from both workflow files.

Step 3 changes nothing about what runs: it is exactly what the fallback in the file already
resolves to. Step 4 is what makes the fallback unnecessary, and until step 3 exists, removing
it would stop the audit anchor, which is the one safety mechanism in this system that has
always run.

**Why this exists.** You asked what a duplicate of this repository would carry to another
client. Measured on 2026-09-09, the answer is: no credentials, and your server's address.

No credentials, and that is checked rather than asserted. Every commit on every branch was
scanned for credential-shaped assignments. Two matches, both harmless: an invented company name
used as a canary in two tests, with the comment above it saying so, and a placeholder that says
it is not real. No environment file has ever been committed.

The address, in two places. `.github/workflows/anchor.yml` carries
this deployment's own address as a fallback for `vars.BRAIN_URL`, and
`.github/workflows/deploy.yml` carries it hardcoded as the address a deploy waits on. Setting
the variable removes the first; the second becomes the same variable.

**And the bigger half, which is not a settings page.** Three older commits carry the same host
in files that have since been cleaned: `.env.example`, `ops/keycloak/realm-export.json` and
`ops/deploy.sh`. A commit cannot be un-made, so a copy of this repository carries them however
tidy the working tree is.

My recommendation is to leave the history alone. It is a hostname and an address, not a
credential, the machine is firewalled to three ports, and rewriting history breaks every clone
and every commit identifier already published. The answer is not to clean the history: it is
that **a client should never receive a copy of this repository.**

That is already how the installer is written. `install.sh` fetches one archive of one tag and
never clones, precisely so a client never receives `.github/` or any history, and
`docs/install/install.md` says under "What you cannot do today" that no such archive is
published yet. Until it is, a copy of this repository is the only way the files reach a server,
which is why your question had teeth. Publishing that archive is `M42.3.8` and it is being
built now, with a check that fails if a client value ever reaches it.

**Your answer, 2026-09-16:** go with the recommendation. The step above is yours, because my GitHub access can read this repository but cannot change its settings. Tell me when the variable exists and I remove the address from both workflow files.

**Done 2026-09-16.** You made the `BRAIN_URL` repository variable, and both workflows now read it
alone. `anchor.yml` takes no anchor when it is unset, and `deploy.yml` fails rather than passing
quietly. The audit's list of files carrying a client value is empty, and it stays a guard.

## 64. The record matcher needs three more permissive licences allowed before its image can be built - DONE: 0BSD, Zlib and CC0-1.0 are allowed

**What you decide: one letter. I recommend Option A.**

**In plain words.** Your answer to item 55 is built: the record matcher runs in its own image,
and it has been run for real against a test export. The image cannot be built yet, because it
checks the licence of every package it installs against the same list of allowed licences the main
application uses, and one package fails that check.

That package is **numpy**, the standard number-crunching library nearly every data tool depends on.
Its licence statement names five licences at once: `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND
CC0-1.0`. Two of those are already allowed. The other three are not on the list yet:

- **0BSD** (Zero-Clause BSD): use it for anything, with no conditions at all, not even keeping a
  copyright notice. It asks less of you than MIT, which is already allowed.
- **Zlib**: use it for anything; do not claim you wrote it, and mark changed copies as changed.
- **CC0-1.0**: the author gives up their rights, as close to public domain as the law allows.

None of the three is copyleft: none requires sharing your own source code, and none places any
condition on the software built with it. They are all less demanding than licences the list already
accepts.

**Option A (recommended): add 0BSD, Zlib and CC0-1.0 to the allowed list.** The matcher's image then
builds, and so does anything else that depends on numpy. The list still refuses copyleft licences
such as GPL, which is what it exists to catch.

**Option B: allow them for the matcher's image only.** The main application's list stays as it is.
It is narrower, and it means two lists that can drift apart, which is the kind of second copy this
system avoids.

**Option C: leave the list alone.** The matcher stays built and tested but cannot be packaged, until
you decide otherwise.

**Why A.** These three licences ask less than MIT, which is already allowed, so refusing them protects
nothing, and one list is easier to trust than two.

**One licence of the same kind was added while this waits, and you can undo it.** Checking sign-in
tokens on the server needed the standard `cryptography` library, which brings in a helper called
**cffi** licensed **MIT-0**: MIT without even the duty to keep the copyright notice. It is on the
allowed list now, because without it the application's own image would not build. If you answer B or
C, say so and I will take MIT-0 off the list again and find another way to check tokens.

**Your answer, 2026-09-15:** Option A. Built the same day: the three are on the allowed list in
`brain.ops.sweeps`, beside MIT-0, with a test holding numpy's own expression allowed and GPL still
refused.

## 62. Keycloak shows "Starting" on your server: the cause is found and fixed, and two settings in Coolify finish it - DONE: Keycloak is up and healthy

**Your result, 2026-09-16:** after the variable and the compose lines were added in Coolify and the service restarted, `keycloak` reported **Up (healthy)**, `keycloak-db` **Up (healthy)** and `keycloak-realm` **Exited (0)**. Sign-in works, and the repository fix keeps it working through the next restart.

**What you do: add one variable and two lines in Coolify, then redeploy the Keycloak service.**

**What your two commands showed.** `keycloak` was **Created** and had never run,
`keycloak-db` was **Up (healthy)**, and `keycloak-realm` had **Exited (1)**. Keycloak starts only
after `keycloak-realm` finishes writing its sign-in settings file, so when that step fails,
Keycloak waits for ever. The logs came back empty because the command picked the Keycloak
container, which had never started.

**The cause, reproduced here.** Since a change on 2026-09-09, the settings step needs one value,
`INSTALL_OIDC_REDIRECT_URIS`: the address sign-in returns to. The compose file never passed that
step any settings at all, so it failed on every start. It stayed hidden until your stack restarted.
The repository is fixed, and a test now fails if a future setting that step reads is left out.

**What you do in Coolify.** Coolify keeps its own copy of the compose file, so the fix does not
reach your server by itself.

1. Open the **Keycloak** service, go to **Environment Variables**, and add:
   - Name: `INSTALL_OIDC_REDIRECT_URIS`
   - Value: the address you open the console at, followed by `/auth/callback` (for example `https://<your console address>/auth/callback`)

   One address only: the settings step refuses a second one.
2. Open the service's **Docker Compose** edit view. In the `keycloak-realm:` section, directly
   above its `volumes:` line, add these two lines, indented exactly like `volumes:`:

   ```
       environment:
         INSTALL_OIDC_REDIRECT_URIS: ${INSTALL_OIDC_REDIRECT_URIS:?set INSTALL_OIDC_REDIRECT_URIS}
   ```

3. Save, then **Deploy** or **Restart** the service.
4. Check, in PowerShell: `ssh verz-vps`, then on the server:

   ```
   sudo docker ps -a --filter name=keycloak --format '{{.Names}}  {{.Status}}'
   ```

   `keycloak-realm` should say **Exited (0)** and `keycloak` should say **Up**. If `keycloak-realm`
   says **Exited (1)** again, run `sudo docker logs keycloak-realm-iii3i6yyvra7tvzr5s6vhwod` and send
   me what it prints.

## 58. Nine "plug-in points" in the plan: build empty sockets for them now, or mark them as not needed yet - DECIDED: Option B, the nine plug-in points are marked as not needed yet

**Your answer, 2026-09-16:** Option B. The nine tasks are being marked decided, so the tracker stops counting them as unfinished work. A plug-in point gets built the day a real replacement part needs one.

**What you decide: one letter. I recommend Option B.**

**In plain words.** The plan lists nine places where somebody could one day swap in their own
part of the system: a different search engine, a different login provider, a different way of
exporting data, and six more like them. Making a place "pluggable" means writing down the exact
shape a replacement part must have, like the shape of a socket.

Nobody has built a replacement part for any of the nine. The code already has one list that
decides which places are allowed to be plug-in points, and it answers these nine:

- **Six of them should not get a socket yet.** A socket that nothing plugs into makes the system
  look more flexible than it is, and it still has to be kept working. The list says: write the
  socket on the day a real replacement part exists, and use that part to test it.
- **The other three are already handled as settings, not plug-ins.** For example, which login
  provider you use is a choice made during setup. Calling it a plug-in would suggest an outside
  developer can replace it with their own code, which is not true.

**Option A: build all nine sockets now.** Nine tasks close on the tracker, and you own nine
empty sockets that nothing uses and somebody has to maintain.

**Option B (recommended): record the list's answer as the decision.** The nine tasks are marked
"decided, not needed as written", the same way the 39 client tasks were taken out of the
percentage, so they stop showing as unfinished work. A socket gets built the day a real
replacement part needs one.

**Option C: leave all nine open** until a client asks for one. Nothing is built either way, but
the nine stay on the tracker as unfinished for as long as nobody asks.

**Why B.** The answer already exists in the code, it avoids building things nobody uses, and the
tracker then counts only real work.

## 61. Should the administrative consoles stay on public addresses or move behind an SSH tunnel? - DECIDED: Option B, the administrative consoles stay on public addresses

**Your answer, 2026-09-16:** Option B: public addresses, protected by a second login factor and an IP allowlist. This is being written into the install documentation, which is what M37.6.1.3 asks for.

**What you decide: one letter. I recommend Option A.**

M37.6.1.3 asks for this decision to be made and written down. It is a decision about each client's
server, not code, so it cannot be answered from the repository.

**The consoles in question** are the ones that control the server rather than the product: the
deployment panel (Coolify), the identity provider's admin console (Keycloak), the secrets vault's
interface (OpenBao) and the tracing dashboard (Langfuse). Each of them, if reached, hands over
every container, every account or every secret. The product's own sign-in page and the Brain
console that staff use are not part of this question: those have to be reachable by the people
who use them.

**Option A (recommended): administrative consoles behind an SSH tunnel, on every install.** They
listen only on the server's own loopback address, and an administrator reaches one with a single
`ssh -L` command. Nothing about them answers from the internet, so a leaked password or an
unpatched login page is not reachable by anybody without the server's SSH key. Your own server
already works this way for the deployment panel on port 8000, so the pattern is proven here.

**Option B: public addresses, protected by a second factor and an IP allowlist.** Easier for a
client whose IT team has no SSH habit. But it puts the most powerful login pages on the internet
and depends on two protections being configured correctly on every install, for ever.

**Option C: decide per client.** Each install chooses during setup. Honest to the fact that clients
differ, and it means the product has to document and test both, and the weaker choice is the one
somebody picks under time pressure.

**Why A.** The consoles are used a few times a month by one or two people, and the cost of a
tunnel is one command for them. The cost of exposing them is the whole server. The installer would
bind them to loopback by default and print the tunnel command at the end of setup.

## 42. Deploying from GitHub needs three secrets, but your server already deploys itself, so I recommend removing that step instead - DECIDED: Option A, the GitHub deploy step is removed

**Your answer, 2026-09-16:** Option A. The GitHub step that needed three secrets is being removed, and the server's own two-minute check is recorded as how this system deploys. No secrets are needed.

**What you decide: one letter. I recommend Option A, and it needs nothing from you.**

**In plain words.** New code reaches your server in two ways, and only one of them has ever
worked:

- **Your server deploys itself.** A timer on the server checks for a newly built version every two
  minutes and installs it. Every deploy so far has come this way.
- **GitHub also tries to tell your deployment panel (Coolify) to deploy.** That step has never
  worked. It needs three secrets that were saved empty, and the panel is not reachable from the
  internet anyway, because its port is firewalled, which is correct (see item 61).

You asked me to re-enter the three secrets myself. I am not able to type passwords, tokens or other
secrets into GitHub on anyone's behalf, including with your permission, so that fix would have to
be yours. There is a better fix that needs no secret at all.

**Option A (recommended): remove the GitHub step.** I delete it from the deploy workflow and
record the server's own two-minute check as the way this system deploys. No secrets are stored in
GitHub, the deployment panel stays private, and nothing changes about how deploys actually happen
today. This is also what the plan asks for in M30.2.4, "pull-based deployment so the server needs
no inbound access".

**Option B: keep the GitHub step and make it work.** You would have to open the deployment panel
to GitHub and re-enter the three secrets yourself:

1. Go to `https://github.com/rpsj2230/Verz-OS-v2.0/settings/secrets/actions`.
2. Click **Update** beside `COOLIFY_URL` and paste your Coolify panel's address.
3. Click **Update** beside `COOLIFY_SERVICE_UUID` and paste the identifier item 49 prints.
4. Click **Update** beside `COOLIFY_TOKEN` and paste a Coolify API token (Coolify, your avatar,
   **Keys & Tokens**, **API tokens**, create one with deploy permission, copy it when shown).

**Why A.** It already works, it needs no secret, and it keeps the most powerful console on your
server off the internet.

## 49. The service identifier on your server is written, and the value in it is the wrong one - DONE: the service identifier on your server is correct

**Your answer, 2026-09-16:** you ran the steps, and the check printed `that service exists`.

**What you do: paste three lines, in this order. It takes about a minute.**

**Where to run it.** On your own computer, in PowerShell.

1. Connect to your server. In PowerShell, paste this and press Enter:

   ```
   ssh verz-vps
   ```

   The prompt changes to your server's. Everything below runs there, not on your computer.

2. Write the correct identifier. Paste this and press Enter:

   ```
   sudo docker ps --format '{{.Names}}' | sed -n 's/^app-//p' | head -1 | sudo tee /root/.coolify-service-uuid
   ```

   It prints one line of letters and numbers. That is the identifier, now saved.

3. Check it. Paste this and press Enter:

   ```
   u=$(sudo cat /root/.coolify-service-uuid); echo "$u"; sudo test -d /data/coolify/services/"$u" && echo 'that service exists' || echo WRONG
   ```

   It should end with `that service exists`. If it says `WRONG`, stop and tell me what it printed.

4. Type `exit` and press Enter to leave the server.

Then tell me what step 3 printed.

**What went wrong.** This item used to tell you to copy the identifier out of Coolify's address
bar. That address holds several identifiers (the project, the environment and the service), and
the one copied was not the service. The server's own container names carry the right one, which
is what step 2 reads.

**Why a wrong value is worse than an empty file.** `brain-deploy` builds its paths from this
value. With a wrong one, every check it makes reads as "not running yet", so it looks like it is
working when it is not. An empty file makes it refuse and say so.

**Nothing is broken today.** The deploy scripts on the server were installed with the old value
built in, so deploys keep working. The file only matters when those scripts are reinstalled.

## 60. The backup ladder the plan asks for keeps copies for a year, and every erasure certificate promises 35 days - DECIDED: Option A, the backup ladder fits inside the 35-day promise

**Your answer, 2026-09-16:** Option A. Being built now.

**What you decide: one letter. I recommend Option A.**

M30.3.5 asks for thirty daily, twelve weekly and twelve monthly backups. Kept that way, the oldest
copy is 372 days old. But `BACKUP_RETENTION_DAYS` is 35, the backups bucket expires copies at 35
days, and `brain.ops.erasure.backup_horizon` uses that number to tell a person when their deleted
data is beyond backup reach. A 372-day ladder would make every one of those certificates false.
`brain.ops.recovery` already refuses the ladder for this reason, and the selection that keeps the
tiers is built with a guard: it refuses the full ladder unless a caller states a horizon of at
least 372 days. Nothing prunes backups today except the bucket's own 35-day rule.

**Option A (recommended): keep the 35-day promise, and change the ladder to fit inside it.**
Thirty daily copies plus weekly copies to day 35. An erasure is honoured within five weeks, which is
the promise a data protection reviewer will read, and a fault noticed at month end can still be
restored from before it began, which was the reason for 35 days in the first place.

**Option B: keep the full ladder, and change the promise to 372 days.** A year of recovery points,
and every certificate then says a deletion reaches backups after a year. That is lawful if said
plainly, and it is a harder answer to give a client whose staff asked to be forgotten.

**Option C: keep both, by erasing from backups.** Rewrite retained copies when someone is erased.
It is the most work by far, and it makes the backup a thing that changes after it was taken, which
undermines what a backup is for.

**Why A.** The 35 days is already a promise the product makes in writing; the ladder is a line in a
plan. When the two disagree, the promise wins, and the plan's line is the one that should move.

## 59. "Most expensive question shapes" needs one field that links a cost to the request it paid for - DECIDED: Option B, each cost links to the request it paid for

**Your answer, 2026-09-16:** Option B. Being built now.

**What you decide: one letter. I recommend Option B.**

M21.3.4 asks for the most expensive agents and question shapes. The agents half exists:
`brain.console.spend_view.dearest` lists them. The question-shapes half cannot be built honestly,
because nothing records a question's shape next to what it cost. Measured on 2026-09-15: the spend
record `brain.ops.spend.Actual` has no such field, and the only table of spend rows,
`ops.spend_actual`, mirrors it. The trace ledger's `tool_count` is never set, and a fan-out plan
exists only while a request is being estimated. So there is no join from "this cost" to "a question
that fanned out to five sources", and inventing a shape field without deciding what shape means
would produce a report nobody could check.

**Option A: record the shape on every spend row.** Add fan-out and tool count to `Actual` and its
table. It is the simplest join, and it copies facts the trace already owns into a second place,
where they will drift.

**Option B (recommended): link each spend row to its trace, and read the shape from the trace.**
Add one field, the trace id, to `Actual` and its table. The trace ledger then records the shape of
the request that produced it, and the report joins the two. The shape stays in one place, and the
same link answers other questions later, such as "what did this refused request cost".

**Option C: drop question shapes from the leaf.** The agents half is closed as it stands, and the
report never ranks questions.

**Why B.** One field, no copied facts, and a join that can be tested end to end. The cost is that the
trace ledger has to start recording tool count and fan-out, which is small work once you choose it.

## 56. When an automation runs with nobody present, it has to run as somebody, and nothing says who - DECIDED: Option A, an automation runs as the person who owns it

**Your answer, 2026-09-16:** Option A. This unblocks M32.6.1.3, the piece that lets automation steps call this system's tools, which is queued to be built.

**What you decide: one letter. I recommend Option A.**

An automation runs after its trigger fires: on a schedule, on a new record, sometimes long after
the person who built it has gone home. Every rule in this system says what a person may do, so a
step an automation takes has to be taken as somebody, and today nothing says who. That single
gap is what stops M32.6.1.3, the piece that lets automation steps call this system's tools
through the gate, from being built.

**Option A (recommended): it runs as the person who owns it, narrowed by the automation's own
limit.** It can never do more than its owner may do, and never more than the automation
declares. When the owner leaves or loses a permission, the automation loses it at the same
moment, because removing a permission here is deleting a grant and there is no second copy
anywhere to forget. An automation whose owner has gone would stop and ask for a new owner
rather than carry on. `brain.ops.automation.flow_reach` already computes exactly this
narrowing: it takes the person as a parameter, and this decision is who that person is.

**Option B: a credential issued to the trigger.** The automation carries its own key. It keeps
working when people leave, which is the risk as much as the benefit: nobody's departure ever
narrows it, and a copied key works without anybody behind it.

**Option C: a service account with permissions of its own.** Tidy, and what most automation
tools do. It is also a holder of permissions that is not a person, which this system is built
not to have: an agent here is a lens over somebody's permissions and never a holder of its
own, and a service account is exactly a holder nobody is responsible for.

**Why A.** It is the only option where "who is responsible for what this automation did" has a
person as its answer, and where removing a person's access removes everything acting for them
without a list to remember. The cost is real and worth accepting: an automation stops when its
owner leaves, and somebody has to adopt it. That is a failure you see. B and C fail in ways you
do not.

## 55. The record matcher needs two new packages, and I recommend they live in their own image - DECIDED: Option A, the record matcher gets its own offline image

**Your answer, 2026-09-16:** Option A. This unblocks M14.4.1, which is queued to be built.

**What you decide: one letter. I recommend Option A.**

When two systems both hold the same client, this system has to decide whether the two records
are one company. The rest of that work is built and tested in `brain.resolution`, including the
arithmetic a probabilistic matcher performs. What M14.4.1 asks for is the matcher itself:
Splink, run over an export held in DuckDB. Neither package is a dependency today, and adding
them is the same kind of decision you made in item 31 about the model stack.

**Option A (recommended): a separate offline image**, the way the models run beside the
application rather than inside it. It would read an export and produce match suggestions for a
person to confirm, and it would never run on the path that answers a question, so
`tests/invariants/test_no_ml_on_the_request_path.py` stays true without anybody remembering it.

**Option B: add both packages to the application image.** The least wiring, and every install
then carries a matcher it may never use, inside the process that serves every request.

**Option C: not yet.** Probabilistic matching earns its place when a client has enough
duplicated records that exact rules miss them, and no install has that data yet. Nothing is
lost by waiting, and A is still the shape when you want it.

**Why A.** It keeps the line you drew in item 31: heavy analysis lives beside the application,
never inside it. If you would rather see real duplicates first, C costs nothing today.

## 51. Every container defaults to `latest`, and the fix stops your automatic deploy until you set one value - DONE on your side: APP_IMAGE is already set

**Your answer, 2026-09-16:** the value is already there. My step, making the compose files require the variable rather than default it, follows.

**The decision.** Should an install that sets nothing run whatever `latest` points at, or should
it refuse to start until somebody names a version? One of those is what you have today.

**Recommendation: change it, and set the value on your server first.** The steps are in order
and the second one is the one that matters.

1. Open Coolify, go to the Company Brain resource, and look at its environment variables. If
   `APP_IMAGE` is not there, add it, with the value `ghcr.io/rpsj2230/verz-brain-v2.0:latest`
   for now. That is exactly what the compose file resolves to today, so this step changes
   nothing about what runs.
2. Tell me, and I will change the compose files so the variable is required rather than
   defaulted. Nothing breaks, because step 1 put the value where the compose file reads it.
3. From then on, holding a version back is one edit in Coolify: set `APP_IMAGE` to
   `ghcr.io/rpsj2230/verz-brain-v2.0:<the tag you want>` instead of `latest`.

**What is already fixed, so you know what is left.** One install's containers used to be
selected by two different variables, `APP_IMAGE` and `BRAIN_IMAGE`. The container that imports
your identity settings read the second one, so a client who pinned the first left that one on
its own default and the realm importer could be a different build from the application it was
built beside. The configuration guide even told the reader to keep the two equal by hand, which
is a version pin that depends on somebody remembering. That is done: one variable now, and
setting it holds the whole install back.

A third variable, `STAGING_IMAGE`, is deliberately still separate, and the first attempt at
this unified that one too. Staging is where a candidate release is tried before your live
server takes it, so a staging stack that reads the same variable as production can only ever
run what production already runs, which is not a staging stack. A test that had been written
for a different reason caught it. Nothing there needs you.

**One figure moved as a side effect and it is worth a sentence.** The realm importer runs the
same image as the application, and while the two named it through different variables the
sizing table counted it as a second image to download. The `standard` profile's disk figure
drops from 38 GiB to 36 and `full` from 50 to 48. Nothing got smaller; the old figures included
a pull that does not happen.

**Why I did not just do the rest.** Two reasons, and the second is the one I would want to
know.

The first is yours: your server deploys automatically when a new image is published, and it
finds that image through the default. Making the variable required stops that deploy until the
value exists, and I do not change your live server.

The second is a real trade in the code. The image's name lives inside the default. Take the
default away and the compose file no longer says which image the service runs, so the check
that found the three-variable problem in the first place cannot see this product's containers
any more and goes quiet. I tried it, watched that check go blind, and put it back. Step 1 above
is what makes the change safe without losing the check, because the value moves to the place
the check does not need to read.

**What happens if you do nothing.** Your installs follow `latest`. That is fine while there is
one install and you are the person publishing the images. It stops being fine at the second
client, because "hold this client back on last month's release" is then a fork rather than a
setting, which is the thing M42.1.4 exists to prevent.

## 57. The GitHub repository is public, and the work breakdown says it should be private - CLOSED: you will make the repository private later

**Your answer, 2026-09-16:** closed, and you will change the visibility later. M0.1.1 stays open on the tracker until the repository is actually private, because that is what the task says.

**What you decide: one letter. I recommend Option A.**

Measured on 2026-09-14 with the GitHub API: `rpsj2230/Verz-OS-v2.0` reports `visibility: public`.
Anybody on the internet can read the whole product, every commit message, and the history item 52
describes, which carries your server's hostname in three older commits. M0.1.1, the first leaf
of the work breakdown, says "private GitHub repo, branch protection, CODEOWNERS". CODEOWNERS is
done. The other two are settings only the repository owner can change, and my token can read the
repository but cannot administer it, so I cannot tell whether `main` has branch protection: that
setting answers "not found" to anybody without admin rights. No rulesets are visible.

**Option A (recommended): make it private and protect `main`.**
1. Go to `https://github.com/rpsj2230/Verz-OS-v2.0/settings`.
2. At the bottom, under **Danger Zone**, click **Change visibility**, choose **Make private**, and
   confirm by typing the repository name.
3. Go to `https://github.com/rpsj2230/Verz-OS-v2.0/settings/branches`, click **Add classic
   branch protection rule**, type `main` as the branch name pattern, tick **Require status checks
   to pass before merging** and choose the `CI` checks, then click **Create**.
4. Tell me, and I check both from here and close M0.1.1 honestly.

Private repositories on a free personal plan still run GitHub Actions, within a monthly minutes
allowance, so CI and the deploy keep working. Step 3's status check does not block pushes made
directly to `main` unless you also tick the setting that includes administrators; leave that
unticked until you want it, because every change so far has been pushed straight to `main`.

**Option B: keep it public on purpose.** Reasonable if the product is meant to be open. Then say
so, and I reword M0.1.1 rather than leave a first leaf that is false.

**Why A.** Nothing here was written to be published. Item 52 already argues that a client should
never receive a copy of this repository, and a public repository is a copy anybody can take.

## 32. Two pieces of Keycloak housekeeping, and nothing is blocked by either - CLOSED: the admin account stays

**Your answer, 2026-09-16:** no need to delete anything, so this is closed. The password change goes with it.

**Keycloak is up.** Measured on 2026-09-09: its own container and its own database
container have both been healthy for two days. The three passwords
are set, the realm imported, and you have signed in. Everything this item originally asked for
is done and the rest of it has moved to the answered section.

**Two steps remain and both are yours.**

1. **Delete the temporary `admin` account** now that your own administrator exists. It was
   created to make the first one and it is a second way in that nobody needs.
2. **Change `KEYCLOAK_ADMIN_PASSWORD` in Coolify to a fresh value.** It was used once to create
   your account, so it is a credential that has been through a setup process and is written in
   at least one place it should not stay.

**Do not delete that variable.** The stack refuses to start without it, and it is the way back
in if every administrator is ever lost. Change the value, keep the name.

I cannot check either of these for you without administrator credentials for your identity
provider, which I do not hold and should not.

## 34. The embedding model is 1024 dimensions and the corpus column is 1536 - DECIDED: narrowed, and the width is a setting now

**Built 2026-09-11, on the recommendation below.** You asked what I recommended rather than
picking from the three options, and "proceed with the remaining" was the authorisation. Both
halves are in: the column is `VECTOR(1024)`, which is what the model item 31 chose produces,
and the width is a declared install setting rather than a number.

**The second half is the one that matters, and it un-blocks this item rather than answering
it.** A hardcoded 1024 is the same defect as a hardcoded 1536 one number later: this
repository is the product every client installs, and a client running a different inference
model needs a different width. Compiled in, that client is a fork. As a setting, any smaller
model that also produces 1024 needs no schema change at all, and one that produces a different
width is one value at install time. That is why the item could stay open for so long without
anybody being wrong: choosing a width before choosing a model spends the same migration twice,
and now it does not.

**Reversible today and not tomorrow, which is why it was worth doing now.** Changing a column
width normally means re-embedding every chunk. No chunk has ever been embedded, so it cost
one migration and nothing else, and that stops being true on the day the first real document is
ingested.

Two refusals came with it. A width above the ceiling pgvector will index is refused when it is
read, because the alternative is a column that stores and an index that does not. And the
migration refuses to change the width once the column holds anything, as a `DO` block rather
than a Python guard, because `alembic upgrade --sql` renders a migration to a script somebody
runs by hand against production and a Python guard renders to nothing at all. The script would
carry the `ALTER` and not the refusal, which is the one combination that loses a corpus.

**If you want a different width, say so and it is one value rather than a migration.** The
three options below are what the decision looked like before, and the first of them is what was
built.

---

**This blocked local embedding, and it was a schema decision rather than a setting.**

The knowledge corpus stores a vector per chunk in a column declared `VECTOR(1536)`. That width
was chosen for a hosted model, `text-embedding-3-small`, before item 31 decided that embedding
would run locally behind the inference server. The model that decision names,
Qwen3-Embedding-0.6B, produces 1024 dimensions. Its published truncation only shortens a
vector, so no setting on the far side turns 1024 into 1536.

**Nothing is quietly wrong in the meantime.** The width is part of the column's type, so
PostgreSQL refuses a vector of the wrong size on insert rather than storing something
meaningless, and the code now reports the disagreement in words before anything is sent. The
figure of 1024 is from the published model card and has not been verified here, because no
weights have been pulled on this host; if it is wrong, the check reads the real width off the
server's own response rather than believing what we asked for.

**Update, 2026-09-07: the check that says this now runs, and it did not before.** The function
comparing the two widths was written, correct and never called: its own docstring said so and
named the place it belonged. It is wired in now, so `python -m brain.ops.worker --check` prints
the disagreement, which means the answer to this question stops depending on somebody
remembering the question.

It prints and does not refuse, and that took a second change worth knowing about. Everything
that check's new home reports is a reason a worker must not start, and this is not one: a
column that disagrees with the model means every embedding job fails and means nothing at all
for the rest of the queue. Refusing to boot over it would take the whole queue down to protect
one leg, and would replace the operator's real problem, "no queue driver is installed", with a
schema decision they cannot make at three in the morning. So the worker now has two lists: what
stops it, and what is wrong that starting will not fix. This is the first entry in the second.

Nothing here changes the decision or its cost. The one thing it changes is that the window
where deciding is nearly free is now visible from the command line rather than only from this
document.

Three ways out, and the cost is different in each.

- **Narrow the column to 1024 and re-embed.** A migration that alters the column and rebuilds
  the vector index, plus a re-embed of every chunk. Today that second cost is nearly nothing,
  because no chunk has ever been embedded. It stops being nearly nothing the moment the first
  real document is ingested, which is the argument for deciding this now rather than later.
- **Serve a wider local model.** The larger models in the same family are wider still, and
  pgvector will index at most 2,000 dimensions whatever it will store, so this route means a
  different family rather than a bigger Qwen3.
- **Keep the column at 1536 and keep embedding hosted.** Honest, and it gives back the reason
  item 31 chose to run models locally in the first place.

**Recommendation, added 2026-09-09 because you asked for one: narrow to 1024, and make the
width a setting rather than a number.** Both halves, and the second is the one that matters.

Narrow to 1024 because that is what the model item 31 chose produces, and because the re-embed
that would normally make this expensive costs nothing today: no chunk has ever been embedded.
That window closes the day the first real document is ingested.

Make it a setting because a hardcoded 1024 is the same defect as a hardcoded 1536, one number
later. This repository is the product every client installs, and CLAUDE.md's rule is that
anything differing between companies is configuration read in one place. A client running a
different inference model needs a different width, and if the width is compiled in, that client
is a fork. So `brain.install` gains a declared setting, the migration reads it, and 1024 is its
default rather than its value.

That also answers the objection this item has been carrying, which was yours and was right:
choosing a column width before choosing the model spends the same migration twice. With the
width as a setting it does not. Any smaller model that also produces 1024 needs no schema
change at all, and one that produces a different width is one value at install time. So this
stops being blocked on items 25 and 31.

One guard comes with it, because a setting that can be changed later is a setting somebody will
change later: altering the width after installation is a re-embed of everything, so it refuses
unless the corpus is empty and says why.

**What I need from you is one sentence: yes to that, or one of the three below instead.**

---


## 54. Windows blocked Python itself for about an hour - DONE: you installed the signed one

**Closed 2026-09-11, in about ten minutes from you reading it.** You ran the `winget` line, I
rebuilt the project's environment against that copy, and every gate works again: the suite,
mypy, both formatting checks, all three sweeps, the mutation harness and the git hooks. The
three pieces of work that were waiting are verified, mutated and committed.

**The PostgreSQL half of the same fix failed, and that is item 53 rather than this one.** You
ran `winget install --id PostgreSQL.PostgreSQL.17` and the installer exited 1, with Windows
reporting that it had blocked `initdb.exe`. So the same policy that blocked the Python
interpreter also blocks the binaries inside PostgreSQL's own installer, and the database
driver is still unavailable here: eight tests fail and sixteen files cannot be collected, all
on one import, all of them run by CI against a real database on every commit. Do not retry
that install; it will fail the same way. Item 53 carries what is left.

**Two things worth keeping from the hour.** The mutation harness broke, because the throwaway
worktree it runs in has no environment and `uv` went looking for an interpreter of its own,
which was the blocked one. Fixing that turned up something better: the harness had been
letting a subprocess choose the interpreter, so a mutation run was evidence about an
environment nobody had looked at rather than the one the caller verified in. It names the
interpreter now.

And the first attempt at that fix was wrong in a way one test caught. Pointing it at this
project's virtual environment made the subprocess import the code from the main tree rather
than from the worktree, so every mutation would have come back as a survivor and the harness
would have reported a perfect score at the moment it stopped testing anything. Nineteen of the
twenty tests in that file passed; the one that failed was the one written to notice exactly
that.

**What it cost.** About an hour, no work lost, and nothing committed unverified. I did not
force the commit through with `--no-verify` while the hooks were down: every push here
deploys, and bypassing the gate that checks task claims is not a habit worth starting in order
to land a document.

**What you do, and it is one command.** Kept below because the same policy can block the next
unsigned binary anything installs, and this is the fix for the class rather than the instance.

```
winget install --id Python.Python.3.13 --source winget --accept-package-agreements
```

**Why that one.** The installer from python.org is signed by the Python Software Foundation,
and a signed binary is what Smart App Control admits without argument. The copy being blocked
is the one `uv` downloads and manages itself, which is unsigned, and that is the whole of the
difference.

**What is broken right now.** Every check on this machine. Not the code: the tools.

```
uv run python -c "print('ok')"
  Unable to create process using '...\.venv\Scripts\python.exe':
  An Application Control policy has blocked this file.
```

The same for the interpreter that virtual environment was built from, so there is no Python on
this machine at all. The test suite, mypy, both formatting gates, all three sweeps and the
mutation harness are unavailable, and so are `git commit` and `git push`, because the commit
hook and the pre-push hook both run Python. The repository is fine and `main` is green; I
simply cannot run anything against it.

**This is item 53 again and it has got worse, which that item said it would.** Yesterday the
same policy blocked one library the database driver loads, for about four hours, and then
stopped on its own. It closed with the sentence "it can happen again, to this file or to the
next unsigned one a package installs, and it will present the same way: a gate failing with no
gate having an opinion." It happened again inside a day, and this time it is the interpreter
rather than a library, so nothing runs at all rather than four fifths of it.

**What is waiting on this.** Three pieces of work are finished and sitting uncommitted,
roughly four thousand three hundred lines with their tests: the embedding column width as an
install setting (item 34), the budget ceiling and the department admin screens (item 38), and
the console's running-version indicator (M42.3.9). I will not commit any of them until I can
run their tests and mutate their guards, because a change nobody has run is a draft, and this
repository's whole practice is that a suite passing is not evidence and a mutation table is.

**Options.**

- **Install the signed Python, which is the recommendation.** One command, it switches nothing
  off, and it fixes the class rather than this instance: every unsigned tool `uv` fetches later
  is subject to the same block, and a signed interpreter is not.
- Wait for it to clear on its own, as item 53 did. It may. Nothing can be built or verified
  meanwhile, and there is no way to tell how long, because what changes is a reputation signal
  held by Microsoft rather than anything on your machine.
- Turn Smart App Control off. It is one setting and I would argue against it hard: on this
  version of Windows it cannot be turned back on without reinstalling the operating system, so
  it trades a five-minute fix for a permanent reduction in what the machine refuses to run.

**What this does not affect.** CI runs the full suite against a real database on every commit,
so nothing that reaches `main` is unchecked whatever happens here. The live system is
untouched.


## 53. Windows blocked the database driver - DONE: a zip, no installer, and the whole suite runs

**Closed for good on 2026-09-11, and the fix is not the one this item recommended.** The
recommendation was to install PostgreSQL's client libraries with `winget`. You ran that and it
exited 1, because Smart App Control refused `initdb.exe` from inside the installer: the policy
blocks the executables the installer runs, so the install never completes and there is no
point retrying it.

What works is the same libraries without an installer. The binaries-only archive from the same
publisher unzips to a directory and runs nothing, and `C:\pgsql\bin` is now on your user PATH.
`libpq.dll` is unsigned and loads anyway, which is the distinction that had not been drawn
until it was tested: the policy refuses **executables it is asked to start**, and this is a
library a process loads. That is why the driver's own `pq.cp313-win_amd64.pyd` stayed blocked
while this one does not, and it is worth remembering the next time something here is refused.

**Measured immediately afterwards: 10,940 passed, 4 skipped, nothing failing and nothing
uncollectable.** That is the whole suite for the first time in three days. Before it: 10,239
passing with 8 failures and 16 files that could not be collected, all on one import.

Nothing was switched off and nothing about Smart App Control changed.

**The earlier half of this item is still worth reading**, because the first episode resolved
itself and that is what made the second one predictable. On 2026-09-09 the same policy blocked
the same driver for about four hours and then stopped, with nothing installed and nothing
changed. The likeliest reading was that the file had gained reputation, which is how the policy
is designed to work, and this item closed saying it could happen again to the next unsigned
binary anything installs. It happened the following morning to the Python interpreter itself,
which is item 54.

**Closed 2026-09-10, and nobody did anything.** The driver imports again, the whole suite runs, and Smart App Control is still on and still enforcing: measured after the fact,
`VerifiedAndReputablePolicyState` is unchanged. Reinstalling the package had not helped while it was blocked, and nothing was installed to fix it.

**So the likeliest reading is that the file gained reputation**, which is how Smart App Control is designed to work: an unsigned binary with no history is refused until enough machines have run it without incident. That means it can happen again, to this file or to the next unsigned one a package installs, and it will present the same way: a gate failing with no gate having an opinion.

**Nothing is needed from you and the recommendation stands if it recurs.** Install the signed PostgreSQL client libraries rather than switching the policy off, which on this version of Windows cannot be switched back on. The three steps are below, unchanged, and they are worth doing pre-emptively if you would rather not lose four hours of local test coverage the next time.

**What it cost, measured rather than guessed.** For about four hours, sixteen test files could not be collected and eight tests failed, all on one import. 9,978 tests, all 1,305 invariants, mypy, both ruff gates and every sweep stayed green throughout, and CI runs the blocked files against a real database on every commit, so nothing shipped unchecked. Six changes were committed during the window and every one of them was verified by mutation.


**What you do, and it is one install with nothing switched off.**

1. Open a terminal and run this. It installs PostgreSQL's own client libraries, which are
   signed by the PostgreSQL Global Development Group and therefore not blocked:

   ```
   winget install --id PostgreSQL.PostgreSQL.17 --silent
   ```

2. Add its `bin` directory to your PATH. In the same terminal, as administrator:

   ```
   setx /M PATH "$env:PATH;C:\Program Files\PostgreSQL\17\bin"
   ```

3. Close every terminal and open a new one, then tell me. I check it in one command and
   carry on.

If you would rather not install PostgreSQL, say so and I will work around it: the eight
failures and fifteen collection errors are all one import, so I can keep building and run the
affected files on the next machine that can.

**What happened.** Partway through 2026-09-09 the local test suite stopped being able to
import `psycopg`, the library the system talks to PostgreSQL with:

```
ImportError: no pq wrapper available.
- couldn't import psycopg 'binary' implementation: DLL load failed while importing pq:
  An Application Control policy has blocked this file.
- couldn't import psycopg 'python' implementation: libpq library not found
```

Measured: Smart App Control is on and enforcing on this machine
(`VerifiedAndReputablePolicyState : 1`, user-mode code integrity enforcement `2`). It blocks
unsigned binaries that have no reputation yet, and the driver ships an unsigned DLL that a
package install writes fresh, so it has none. Reinstalling the package does not help, and I
tried: a freshly written copy of an unsigned file is exactly what the policy refuses.

This is the same trap `CLAUDE.md` already records for `mypy`, where the same policy
intermittently refused a freshly written shim and it presented as a gate failing with no gate
having an opinion. It has moved from an executable to a library, which is worse, because a
library failing takes twenty-three test files with it.

**What it costs today.** 9,978 tests still pass, all 1,305 invariants pass, and mypy, both
ruff gates and every sweep are green. Eight tests fail and fifteen files cannot be collected,
and every one of those is this import: they are the files that touch the database driver.
Nothing is wrong with the code; the machine cannot load the driver.

**Why the recommendation is not to switch the policy off.** Smart App Control on Windows 11
cannot be switched back on once it is off, short of reinstalling Windows. It is protecting the
whole machine, and this is one library. Installing a signed copy of the same library changes
nothing about your security posture and is undoable with an uninstall.

**Options.**

- **Install the signed client libraries, which is the recommendation.** Three steps above,
  about five minutes, and nothing is weakened. The driver has a pure-Python implementation
  that works as soon as it can find a signed `libpq`, and there is none on this machine today,
  which is why the second line of that error appears at all.
- Turn Smart App Control off. It would work, it is one setting, and it is a one-way door on
  this version of Windows. I would not.
- Leave it. The tests that cannot run are the ones about the database driver and the pooler,
  which are also the ones CI runs against a real PostgreSQL on every commit, so nothing ships
  unchecked. What is lost is the ability to catch those failures here rather than in CI, which
  is minutes rather than seconds and is a real cost when a change touches the schema.


## 33. "Shadow-pinned thirty days" - which of the two things does it mean? - DECIDED: both readings, with a confidence measure gating the switch

**Your decision, 2026-09-09, and it is a third answer rather than one of the two.**
Both readings, with a measurement between them:

- The agent stays supervised and is reviewed at thirty days, which is reading one.
- The review is not only a person's impression. There is a measure of how much the agent
  understood and a confidence level derived from it.
- **Below 90 percent confidence the shadow period extends** so the agent can raise it. Only at
  90 percent or above does supervision end.

So the pin never expires on a timer, which was the danger in reading two, and it does not
depend on somebody remembering to look, which was the weakness in reading one. You called this
one important and it is: it is the difference between an agent that is trusted because it
earned it and one that is trusted because a month passed.

**Small, and it decides a safety property rather than a feature.**

Your work breakdown lists two agents with a supervision constraint in their titles:

- **SEM Agent**, shadow-pinned, human commits budget changes
- **AR and Renewal Chaser**, shadow-pinned **thirty days**

The first is built. "A human commits budget changes" is something the system can refuse: the
agent may prepare a change and may not apply one, and that is enforced by the gate rather
than by asking the agent nicely in its instructions.

The second I did not build, because the system cannot currently express it and I do not want
to guess which of two very different things you meant.

**Reading one: review after thirty days.** The agent stays supervised. After a month somebody
looks at what it did and decides whether to trust it further. Nothing changes on its own.

**Reading two: becomes autonomous after thirty days.** The pin expires. On day thirty-one the
agent starts chasing customers for money without anybody watching, because a timer ran out.

I would build the first and would want to argue with you before building the second. An agent
that gains authority on a date nobody diarised is the one kind of change that happens when
nobody is paying attention, which is exactly when you would want it not to.

**Either way there is a small piece of work**, because today a supervision level has no time
attached to it at all. Reading one needs a review date and a reminder. Reading two needs an
expiry, and I would want it to be loud rather than silent.

No rush: the chaser is one of twenty-three agent templates and six are written so far.

---


## 35. You renamed the GitHub repository, and it stopped the deploy - DONE: nothing outstanding, and the image keeps the name it has

**Closed 2026-09-09.** You confirmed it is fixed, and the one decision left was
cosmetic: the image is still called `verz-brain-v2.0` while the repository is called
`Verz-OS-v2.0`. It keeps the name it has, which was the recommendation. If the mismatch ever
starts to bother you it is ten minutes and one deploy, and it has to be done in one step.

**Fixed already, in about twenty minutes, and there is one small decision left for you.**

You renamed the repository from `verz-brain-v2.0` to `Verz-OS-v2.0` this afternoon. The build
that ran straight afterwards failed:

    invalid tag "ghcr.io/rpsj2230/Verz-OS-v2.0:79204c6": repository name must be lowercase

The pipeline was naming the container image after the repository, so renaming one renamed the
other, and container image names may not contain capital letters. Meanwhile the server pulls
the image by its old name, written into three files.

**The lucky part.** Your new name has capital letters in it, so this arrived as a failed build
half a minute after the push. Had you renamed it to something lowercase, the build would have
worked, published the image somewhere nothing looks, reported success, and left the server
running the old one with every check green. That is the failure you had in August, when
production sat fourteen commits behind and nothing said so.

The image name is now written out rather than derived, four files that name it are held equal
by a test, and production is live on the current commit again. Nothing is outstanding.

**The decision.** The image is still called `verz-brain-v2.0` while the repository is called
`Verz-OS-v2.0`. Two options:

1. **Leave it.** The image name is an internal address that only the pipeline and the server
   use. Nothing is wrong with it, and it costs nothing. My recommendation.
2. **Rename the image to match.** Tidier to read, and it has to be done in one step: publish
   under the new name and change what the server pulls at the same moment, or the server
   spends that deploy pulling something that is no longer published. Ten minutes and a
   deploy, and worth doing only if the mismatch will bother you every time you see it.

**One thing to know for next time**, not a complaint: a rename is the kind of change that
looks free and reaches the build, the registry and the server. If you tell me before or just
after, I can have the three files moved in the same minute rather than finding it in a red
build.

---


## 36. The WBS names promptfoo for evaluation and I used pytest - say if you want the tool - DECIDED: as recommended

**Your decision, 2026-09-09: as recommended.**

**Nothing is blocked. This is a deviation from your wording, flagged so it is your call rather
than mine.**

M28.1.1 reads "promptfoo driven through our gate, never against a bare model". I built the
harness in Python, in `tests/invariants/test_golden_through_the_gate.py`, and did not use
promptfoo.

The reasoning. promptfoo drives a provider: you give it a thing that takes a prompt and
returns a completion. What has to be driven here is not a provider, it is an entitled request
pipeline that needs a different principal for every case, because the whole point of the
corpus is that the same question asked by three people must produce three different answers.
Wiring promptfoo to that means writing a custom provider in JavaScript that shells into
Python once per case, which puts a second language and a subprocess between the corpus and
the gate, and buys nothing the Python harness does not already do. The invariants suite is
already its own CI step and CI already gates Deploy, so the blocking half of M28.1.4 came for
free.

What I kept is the part of the leaf that matters: the phrase "never against a bare model".
Every question goes through `answer_lane`, which runs the projection, the row read at the
caller's own reach, the redaction and the abstention classifier. A test asserts structurally
that this module imports no model driver, so a faster path that asked a provider directly
cannot be added quietly.

**Say the word and I will add promptfoo as a second front end over the same harness.** The
case for it is real: it is a tool your team may already know, and its report format is nicer
than pytest's. The case against is a second thing to keep in step with the corpus.

**One thing worth knowing that this turned up, and I am fixing it separately.** Asking the
golden corpus of the real system for the first time showed that no persona in the synthetic
company can read a record at all. Reaching a row needs `read:client` and reading a column
needs `read:client.name`, and the two are deliberately separate grants; the fixture grants
only columns. So the twenty golden questions have been describing a company nobody could read
from, and nothing noticed because the only tests of the corpus checked the corpus's own shape.
It is asserted as a test now so it cannot go quiet again. Fixing it widens what every persona
reaches and about seven thousand tests take their reach from that fixture, so it is a change
on its own rather than a side effect of building the harness.

---


## 37. Keycloak is unpleasant to administer, and the reason is a screen we have not built - DECIDED: as recommended

**Your decision, 2026-09-09: as recommended.**

**Nothing is blocked and no work stops on this. You asked why we use Keycloak at all, having
found it horrible to manage users and roles in. The honest answer has two halves.**

**The half where you are right.** Keycloak's admin console is genuinely dense. Two realms that
look alike, groups and roles and clients that overlap, and a layout that assumes you already
know its vocabulary. Nobody enjoys it.

**The half that matters more: you are not supposed to be in there.** The design was always
that Keycloak is plumbing you open twice, once to bootstrap and once if you are ever locked
out. Everything routine was meant to happen elsewhere:

- Staff arrive from your existing directory rather than being typed in.
  `brain.identity.directory` is written and tested for that and is wired to nothing.
- Day-to-day people and grants happen on a Company Brain screen, M27.3.1, which does not
  exist. The console has five pages and none of them is that one.
- Joining, moving and leaving happen through `brain.identity.lifecycle`, written today, also
  wired to nothing.

So the pain you hit is real and it is pointing at three missing pieces of *our* system rather
than at the wrong choice of dependency. Switching identity providers would not remove it,
because the thing you were doing by hand in Keycloak is the thing that should not be done by
hand anywhere.

**Why an identity provider at all.** The whole permission model rests on knowing who is
asking, provably, from a token the gate can check without calling anything. That is OIDC. The
alternative is writing passwords, sessions, resets, lockout, multi-factor and their audit
trail ourselves, which is a large security-critical surface and a bad trade at any size.

**Why Keycloak specifically.** It is self-hosted, which your single-tenant client-hosted
requirement needs. It has no per-seat cost, which matters at 126 staff and more later. It
speaks OIDC and SAML and federates to LDAP and Active Directory, which is what a client with
their own directory will ask for. And its whole configuration exports as one file, which is
why `ops/keycloak/realm-export.json` is reviewed in the repository rather than clicked into
existence.

**The honest alternatives, if you want to reconsider.** Authentik has a considerably friendlier
admin interface and is also self-hosted and free. Zitadel is lighter and has a better API.
Both are younger with smaller communities, which for the component holding your credentials is
a real consideration rather than a formality. Auth0, Clerk and WorkOS are far easier to run and
break the client-hosted requirement while charging per seat.

**My recommendation: keep Keycloak and build the screen.** The switch costs a few days and
buys a nicer version of a console you should stop opening. The same few days spent on M27.3.1
and wiring the directory sync removes the need to open any identity console at all, and that
work is needed whichever provider sits underneath.

**What I would want from you if you disagree**: say so and I will cost the migration properly
rather than guess. I have not measured Authentik's footprint on your server and would not
quote one without doing so.

---


## 38. The console will have thirty-four screens, and four of them are decisions - DECIDED: all four, and a department admin gets every screen the requirements call for

**Your decisions, 2026-09-09.**

1. **Over budget: warn the department admin, and refuse further questions until the next
   period.** Both, in that order.
2. The stop button: as recommended.
3. **Not four screens.** A department admin gets every screen the requirements call for, and
   the four I had scoped were a scoping error rather than a decision. The screen list is
   re-derived from the requirements.
4. The filter dropdown: as recommended.

**Nothing is blocked. This is a design record to disagree with now rather than after it is
built.** You said the nine screens I described could not be the whole console, and you were
right. The plan named eighteen and the code had four. It is now thirty-five, declared in
`brain/console/screens.py` with tests holding every one of them to the rules below, and the
roadmap under M27 lists them all.

Your five specific asks were already in the plan at M33 and had reached neither the screen list
nor any code. They are now in both: company overview, everything filterable by department and
person, all activity, budget and spend, and a global stop button.

**Four things there are decisions rather than mechanics.**

**One: budget is separate from usage, and budget is a limit.** "Usage and tokens" tells you
what was spent. "Budget and spend" is a ceiling with something that happens when it is
reached. What should happen? Warn the person and carry on; warn their department admin; refuse
further questions until the next period; or refuse only the expensive lanes and leave cheap
answers working. **My recommendation is the last**, because a hard stop at a budget turns a
cost control into an outage. Nothing is built until you pick.

**Two: the stop button stops instantly and needs nobody's approval.** One capability, no
confirmation dialogue, no second signature, because a stop button that can fail is not one. The
paperwork sits on the *resume*: restarting a system somebody halted needs a written reason, and
it says out loud when one person is overriding another. A halt also survives a restart and has
no expiry, so it ends when a person ends it and never on its own. Tell me if you want that
reversed anywhere.

**Three: four screens do not exist for a department admin.** Their rows are narrower
everywhere, which is automatic. But four screens are about the deployment rather than the work
in it, and at a department's scope each is either empty or a leak: backup and recovery, this
install, rate limits, and capacity. Department admins keep everything else, including a stop
button for their own department.

**Four: a filter dropdown is a disclosure and is treated as one.** Every screen can be narrowed
by department and by person, as you asked. That means every screen carries a department
dropdown, and filled from the department table it would name every department in the company to
somebody whose rows were carefully scoped. The options are intersected with what the reader can
already reach. You may find you cannot filter by a department you know exists. That is this,
working.


## 39. Which staff list is the real one, and may it set roles - DECIDED: every source selectable per client, and the staff list does not set roles

**Your decision, 2026-09-09, and the first half changes the shape of the answer rather
than picking one of the options.** There is no single Verz staff list to name, because this
repository is the master that gets duplicated per client: company A may take its staff list
from a Google Sheet, company B from Google Workspace, company C from something else. So every
source stays selectable at deploy time, and choosing one is a setup decision on the client's
own install rather than a constant here.

That is the right shape and it is not extra work: it is what `M29`'s plugin interfaces are
for, and CLAUDE.md's rule that anything differing between companies is configuration reaches
exactly this case.

**Question two: keep the default.** The staff list lists people; roles are set in the console.
Safest, and the extra work is per joiner rather than ongoing.

**Nothing is blocked today. This decides what gets built first and it needs two short
answers.** You asked for the staff list to be pluggable: spreadsheet, Google Sheet, Google
Workspace, Microsoft, Lark, or anything else. That is designed and in the plan as M1.6, twelve
leaves. Building all six adapters before we know which one you use is a month spent on five we
may never run.

**Question one: where does the Verz staff list actually live today?** Not where it could live.
Where the current, correct list of who works there is: the one somebody updates when a person
joins. A Google Sheet is a perfectly good answer.

**Question two, and this one has a security consequence.** A source declares what it is
trusted to assert, and there are three things it can assert: that a person exists, which
department they are in, and what platform role they hold. By default a spreadsheet or a Google
Sheet may assert **only that a person exists**.

A sheet anybody with the link can edit is a fine answer to "who works here" and a catastrophic
answer to "who is a Super Admin": one edit to one cell and somebody has appointed themselves,
with the edit history in a document nobody reviews. A Workspace group is different, because
changing it needs the admin console and leaves a trail there.

So if your staff list is a sheet, the consequence is: **people arrive automatically, and their
department and role are set by you in the console.** A few clicks per joiner rather than none.

**Your options.**

- **A. Keep the default.** The sheet lists people; roles are set in the console. Safest, and
  the extra work is per joiner rather than ongoing.
- **B. Trust the sheet with departments too, but not roles.** Reasonable if the sheet has a
  department column that is kept accurate. Departments bound what people can see, so this is a
  real widening, though a much smaller one than roles.
- **C. Trust the sheet with roles as well.** Only sensible if the sheet is locked to two or
  three named editors. Say so and I will configure it that way and write down who those
  editors are, so an auditor can see the argument.

The default is A and it is what will be built if you say nothing. It can change later, per
source, without a migration.


## 40. A second copy of the rule that decides who can see what - DECIDED: delete it

**Built 2026-09-10.** Both are deleted, every rendering property their tests asserted
moved to `compile_where` intact, and the invariant was widened to catch a renamed copy by what
its code does rather than by its name: building a JSON column expression at all, or emitting a
bound comparison while also reading the clause grammar. Written back as `Clause.as_filter`, with
no test naming `to_sql`, a second renderer is caught.

One line of the evidence above no longer reproduces and is left as written rather than quietly
corrected. The `IN`-with-a-bare-string divergence was measured before an unreachable branch was
removed from `compile_where` earlier the same day, so the two now agree on that input. The other
three were re-measured and stand, and the decision rested on all four.

**Your decision, 2026-09-09: delete it**, on the recommendation below.

The recommendation, recorded because you asked why the item did not carry one: delete
`Scope.to_sql` and `Clause.to_sql`. Nothing in the application calls them, measured again on
the day; the two already disagree with `compile_where` on a real input; and they are the less
safe of the pair, because `to_sql` hard-codes `row_data ->> field` so it cannot use a promoted
column and never calls `assert_conjunctive`, which is the check that stops a scope widening
instead of narrowing. Keeping a second answer to "who may see what" that skips the widening
check is exactly what the single-implementation invariant exists to prevent, and the next
person needing scope SQL finds it first because it is a method on the object they are already
holding.

`brain.core.scope.Scope.to_sql` and `Clause.to_sql` render a scope into SQL. So does
`brain.core.scope_sql.compile_where`, which is the one everything uses, and the repository has
an invariant forbidding a second implementation of a central rule for a reason it states
plainly: each copy is reasonable in isolation, they drift, and the one that drifts is
discovered by a permission being wrong rather than by a test.

The two already disagree. Measured:

```
Scope.to_sql   -> ("(row_data ->> 'department' = ANY(:s0))", {'s0': ['a', 'b', 'c']})
compile_where  -> refused: department in: needs a tuple of strings; a bare string becomes one
```

`to_sql` also hard-codes `row_data ->> '<field>'`, so it cannot use a promoted column, and it
never calls `assert_conjunctive`, which is the check that stops a scope widening rather than
narrowing.

The invariant did not catch it because it guards the *name* `compile_where`, and this one is
called `to_sql`.

**Nothing in the application calls it.** Only two test files do. So it is loaded rather than
live, and the risk is the next person who needs scope SQL finding it first.

**What I need is one sentence: delete it, or keep it.** Deleting it means changing the two
test files that use it and widening the invariant to catch a renamed copy. Keeping it means
saying what it is for, because right now it is a second answer to the most important question
this system asks.

---


## 41. Four services connect straight to the application database and nothing budgets them - DECIDED: the four bounds below, and a refusal so an understatement cannot repeat

**Built 2026-09-10, and the arithmetic above has moved.** The four are declared, so the
database's demand is 50 rather than 20 and 47 connections are spare rather than 77. The worst
case behind the pooler is 1312 MiB against a 2048 MiB container rather than the 832 MiB the
written reason claimed, and that text moved with it.

The refusal is in the list that stops a worker starting rather than the list of things that are
wrong but starting will not fix, and the argument is in the code: an unbounded pool is not one
leg of the queue, it is every client of that database including the administrator, and by the
time anybody reads a finding the connections are held.

**Your decision, 2026-09-09: go with the recommendation.** You also asked why there was
no recommendation in the first place, and that was my mistake rather than a judgement about
the question. The numbers, with the provenance of each:

| Service | Bound | Where the number comes from |
| --- | --- | --- |
| `langfuse-web` | `connection_limit=5` | A trace interface, not on the request path. Five serves a browser. |
| `langfuse-worker` | `connection_limit=5` | Batched ingestion with one writer. |
| `brain-worker` | 15 | Ten is measured: `make_worker_engine` keeps five plus five overflow. Five for the queue connection. |
| `brain-parse-worker` | 5 | A queue connection and nothing else. |

Thirty against the seventy-seven currently unbudgeted, leaving forty-seven spare on a database
that admits ninety-seven.

**And the part that matters more than the numbers.** A worker refuses to start when a queue
driver is present and its pool size is undeclared. That turns "we guessed five and the driver
opens twenty" from a silent understatement into a refusal, and a silent understatement is what
caused the outage this item is about.

**This is the shape of the Keycloak outage, on the database that holds the company records.**

On 2026-09-07 Keycloak opened every connection its database would give it and held all thirty
idle. The next connection was refused, and the next connection was an administrator trying to
find out why. The fix was a bounded pool and a budget that fails a test when a client's pool
and a server's ceiling stop agreeing.

That budget checks the clients we *declared*. It cannot see one nobody declared, and an
undeclared client is exactly what saturated Keycloak's. Reading the compose files rather than
the declaration turned up four:

- `langfuse-web` and `langfuse-worker`, through Prisma, with no connection limit on the URL
- `brain-worker`, through both its queue URL and its checkpointer URL
- `brain-parse-worker`, through its queue URL

Every one of them bypasses PgBouncer for a good reason: the queue needs LISTEN and the
checkpointer needs server-side prepared statements, and the pooler in transaction mode
supports neither. Which is what makes them the case that matters. **The services that most
need budgeting are precisely the ones the pooler is not bounding.**

The arithmetic today: `db` admits 97 connections, the declared demand is 20, and 77 are
unbudgeted. Its declared ceiling costs 2112 MiB against a 2048 MiB container, and that is
affordable only because PgBouncer holds real connections to twenty. These four are outside
that.

**Nothing is broken today** because none of the four is running: Langfuse is not deployed and
both workers exit because no queue driver is installed. So this is a decision to take before
they start rather than a fault to fix. It is reported by a check with a test pinning the exact
set, so a fifth cannot arrive unnoticed.

**Part of this is already measured, and I stopped short of declaring it for a reason worth
knowing.** `brain.session.make_worker_engine` keeps a pool of five connections plus five
overflow, so the checkpointer half of each worker opens at most ten. That is a real limit
already in the code.

It is not the whole of a worker, though. Each one also holds a queue connection, and that pool
belongs to the queue driver, which is not installed, so nobody can say what it opens. Writing
"brain-worker: 10" into the budget would look complete and be an understatement, and an
understated connection budget is precisely what caused the outage this item is about. So the
measured half is recorded here and nothing is declared until the other half exists.

The other two are Langfuse's, and they are the ones that need you: Prisma takes a
`connection_limit` on the URL and nobody has chosen a number, and the same two services also
point at a database nothing creates, which is number 2 of item 43. Those are one change.

**What I need is a bound for each.** Prisma takes `connection_limit` on the URL; the workers
take a pool size. I can pick numbers that fit the budget and write them in, and I have not,
because the two worker figures interact with the slot allocation you already approved and the
Langfuse ones interact with whether Langfuse is deployed at all, which is item 25.

---


## 43. Three things in the deployment files that break a fresh install - DECIDED: Option A on all three

**Built 2026-09-10. The `full` profile is down from five blockers to two**, and neither
of the two is one of these three. The settings four containers mount are created by an install
step, per file, so an update never overwrites an edited egress allowlist. The trace ledger's
database and role are created between the database starting and everything else, only on a
profile that runs it, with the password piped to standard input rather than passed on a command
line. And the object store is described once: the trace ledger's file names it with an empty
body, which contributes nothing to a merge, so there is no second copy for a test to hold equal.

The two blockers left on `full` are a component that is budgeted and has no service at all, and
the reverse proxy, which is a requirement on the server rather than a file in this repository.

**Your decision, 2026-09-09: Option A on each of the three.** The settings file is
created during install, the trace ledger's database is created during install, and the file
store is described once in its own deployment file with the tracing file referring to it.

**None of this affects what is running today.** All three are in parts of the system that are
not switched on yet. They break the day somebody turns them on, which is why they are worth
half an hour now rather than an evening later.

### 1. Four containers read a settings file that will not be there

Four containers are told to read a small settings file that sits next to the deployment file
in the repository. The server does not have the repository. Coolify stores its own copy of the
deployment file in its database and writes it out on its own, so when the container looks for
that file it finds an empty folder, shrugs, and starts anyway. Three of the four then run with
no settings at all and say nothing about it.

The four are: the trace database (its memory limit), the automation sandbox (the list of
addresses it is allowed to reach, which is the thing stopping it reaching anything else), the
file store (its access credentials) and the file store's setup script.

**We have already solved this once.** Keycloak had the same problem last week: its
configuration file is now baked into the image we build, and a tiny helper container copies it
into place at startup. It works and it is tested.

- **Option A, recommended: do the same for all four.** About an hour. It is a pattern we have
  already used, so there is nothing to invent, and it removes a class of failure rather than
  four instances of one.
- **Option B: leave them and remember.** Free today. The cost is that the automation sandbox's
  address list is the one keeping it from reaching the internet, and "remember" is not a
  security control.

I recommend A, and I can do it without you. **Say the word and it is done.**

### 2. The trace ledger connects to a database nobody creates

Two of the tracing containers are pointed at a database called `langfuse`, and the database
server only ever creates one called `brain`. On a fresh install they would fail to start, and
the message would be about a missing database rather than about the real problem, which is
that nothing was ever told to make it.

- **Option A, recommended: create it during install.** A few lines. It also gives the tracing
  system its own database, which is what you want anyway: it means a problem there cannot
  reach your company records.
- **Option B: point them at the `brain` database.** Fewer lines, and it puts the tracing
  system's tables beside your business data with one login covering both. I would not.

This one is tangled with item 41, because the same two containers also need a limit on how
many connections they open. **Both are one change if we do them together.**

### 3. The file store is described twice, differently

The file store appears in two deployment files with different settings. One of them switches
on its access-control layer and the other does not. Which one wins depends on the order the
files happen to be listed in, which is not something either file says.

- **Option A, recommended: describe it once, in the file store's own deployment file**, and
  have the tracing file refer to it. Half an hour.
- **Option B: make the two copies identical.** Faster now, and they drift apart again the
  first time somebody edits one.

### What I need from you

**One word on each, or one word for all three.** If you say "do all three", I will do them and
you will see them on the build page. There is no cost to you beyond the time, none of it
touches what is running, and I would not be asking except that item 41 and number 2 above are
the same change and I would rather do it once.

---


## 44. Nothing takes a backup of your database, and the shelf for one is already built - DECIDED: Option C, the nightly dump now and the restore drill with M30

**Built 2026-09-10, and the sentence "nothing writes to it" is no longer true.** The
copy runs nightly at 02:00 on a timer, writes to the bucket that was already waiting, and writes
a small manifest beside the artefact describing what it actually did. The record of a copy must
not live only inside the thing being copied: a row saying the database was backed up at 02:00 is
in the database the copy exists to replace.

**What you run, once, as root on the server:** `ops/backup/brain-install-backup`. It discovers
the database container, the bucket and the object store from the running system rather than
taking them as arguments, for the reason item 49 cost a wrong value.

The last paragraph of this item stands unchanged and is the important one: a copy nobody has
read back is a file, not a backup. Nothing reads one back, deliberately, and that is M30.

**Your decision, 2026-09-09: Option C, A now and B later.** In your words, the nightly
dump is not wasted work when M30 arrives: it becomes the thing M30's restore drill restores
from.

Everything around a backup exists. There is a `backups` bucket on the file store, it is set to
keep things for 35 days, it is set to keep old versions, and the reason for the 35 days is
written down: one full monthly cycle plus a few days, so a fault noticed at month end can still
be restored from before it started. The erasure certificates even do arithmetic on that number
so they can tell somebody which of their data a deletion has not reached yet.

**Nothing writes to it.** I checked the whole repository for anything that takes a database
dump or restores one, and the only place `pg_restore` appears is in a guard whose job is to
refuse an installation step that tries to load somebody else's data. So the shelf is there, it
is labelled, and it is empty.

This is planned work: it is module M30, "Hosting, delivery and recovery", which sits in wave 5
and has none of its 37 tasks done. So nothing has gone wrong. But the plan puts it a long way
out, and in the meantime the answer to "what happens if the database is lost" is "everything is
lost", and I would rather you knew that tonight than in wave 5.

**How bad is it right now.** Not very, and I want to be accurate rather than alarming. What is
in that database today is seeded demonstration data, the build tracker, and configuration. It
is not yet your company's records. The day that changes is the day this becomes urgent, and
that day is a decision you make rather than one that arrives by surprise.

**What I would need from you, and the options.**

- **Option A, recommended: I write the nightly dump now and you run one command.** A dump on a
  timer on the server, written to the bucket that is already waiting for it, roughly fifteen
  minutes of work. It needs one thing from you because it touches the live server rather than
  this repository: I would give you a single command to paste into the VPS, and you would paste
  it. I have not done it unasked because a change to what runs on your production host at three
  in the morning is not mine to make while you are asleep.
- **Option B: wait for wave 5 and do it properly.** M30 covers backup, restore, a verified
  restore drill and a recovery runbook, which is the whole thing rather than half of it. This
  is the right answer if real data does not land in that database before wave 5.
- **Option C: do A now and B later.** The nightly dump is not wasted work when M30 arrives; it
  becomes the thing M30's restore drill restores from.

I recommend C. The dump is cheap, it stops the worst outcome, and it does not duplicate
anything wave 5 will build.

**One thing worth saying plainly.** A backup nobody has restored is not a backup, it is a file.
The console screen for "last verified restore" is deliberately not built, because a screen
showing a backup timestamp under that heading would be the field somebody checks before
deciding not to worry. There is a test in the repository that walks every module and asserts
nothing is named for restoring anything; it passes today, and it is written so that it fails on
the day somebody adds a restore, which is the day that screen should be written.

**Since, on 2026-09-14.** The screen is built, as `brain.console.recovery_view`, and the test's
pin moved with it rather than being dropped: only `brain.ops.backup_manifest` may construct a
drill record or decide what one proved. Nothing restores a copy yet, so on a real install the
panel can say only "never verified" or "nothing copied", which is the alarm this paragraph
asked for rather than the reassurance it warned about.

---


## 45. "Which agents have read my HR record" is a question the system cannot answer - DECIDED: Option A

**Your decision, 2026-09-09: Option A.**

One task on the plan asks for a page where a member can see which agents have read their HR
record. It is a good thing to be able to show somebody. The system cannot answer it today, and
the reason is a design decision that was made deliberately and is worth you knowing about.

**What is recorded today.** Two different things are kept, on purpose, and neither is a list of
who read what.

- The **audit ledger** records things that change what somebody may do: a permission granted, a
  permission taken away, a leash moved, an emergency access session opened. It is kept for five
  years, it holds no content at all, and it is deliberately a short list of eight kinds of
  event. None of the eight is "somebody read something".
- The **trace record** holds one row per request: who asked, which model answered, how long it
  took, how many things were redacted. It holds names and counts and never a value, and it is
  kept for a month. It can tell you that somebody asked a question; it cannot tell you which
  rows came back.

So "who has read my HR record" falls between them. Nothing is broken and nothing was
forgotten: a system that logged every read of every row would be keeping a second copy of who
looked at what, forever, which is its own privacy problem and its own storage bill.

**What answering it would take, and what each costs.**

- **Option A, recommended: answer it for a narrow, high-sensitivity set rather than for
  everything.** Personnel records are the case the task actually names, and they are a small
  slice of the data. A read log scoped to that slice is affordable, is the thing people
  genuinely ask about, and does not turn every ordinary lookup into a permanent record. It
  needs one new kind of audit event and a decision from you about which record types count as
  sensitive enough to log.
- **Option B: log every read of every row.** Complete, and the honest cost is that the log
  becomes the largest thing in the database and is itself a map of who is interested in whom.
  I would not do this.
- **Option C: leave it, and say so on the page.** The member's page tells them plainly that
  reads are not logged and what is logged instead. This is the cheapest and it is a real
  answer rather than a blank space, and it is the right choice if nobody has actually asked
  for the read log.

I recommend A, and the decision I need from you is one line: **which record types are sensitive
enough that every read of them should be written down.** My starting suggestion would be
personnel records and anything carrying a salary, and nothing else.

**Why this is on your list rather than mine.** The two costs are the kind you would notice and
I would not: a permanent record of who looked at whom is a privacy position, and the storage it
takes is a bill. Neither is a coding question.

---


## 46. Your client agreement will promise a recovery point and a recovery time. These are the numbers, and I need you to pick which set - DECIDED: Option A

**2026-09-10: reading the code to record your choice turned up a fault worth knowing
about.** The statement refused three ways and the recovery-point refusal compared your promise
against the backup *schedule*, which is a declaration of what ought to be copied and which
nothing had ever executed. Measured: the schedule answered 3600 seconds against `lite`'s promise
of 86400, so it passed comfortably on a system that had never been backed up once.

A schedule is an intention and a copy is a fact. There is a fourth refusal now: for every
coverage the schedule covers, the newest copy that actually exists has to be inside the stated
recovery point, and a coverage with no copy at all is reported as unbounded rather than as a
large number. That only became possible because item 44's manifests can be read back.

**This item is still open in the way that matters and that is correct.** No drill has verified a
restore, so all three options still produce a refusal rather than a document. Signing the `lite`
figures becomes real on the day a drill runs, and both halves of the promise will then rest on
something observed.

**Your decision, 2026-09-09: Option A.**

**One line from you, and there is no work behind it.** A client agreement carries two figures:
how much work may be lost if the system has to be restored from a backup (the recovery point),
and how long it may be down while that happens (the recovery time). Until today both existed in
the code as defaults and nothing turned them into a document anybody signs. Now something does,
and the first document it produces is the one Verz hands its first client.

**Where the numbers come from.** The system offers three deployment profiles, and each carries
its own pair. These are not my estimates; they are what is written in the code today, with the
reason beside each one:

| Profile | Recovery point | Recovery time | Why |
| --- | --- | --- | --- |
| `lite` | 24 hours | 8 hours | Four containers on one host, and no second host to restore onto, so the recovery time is however long it takes somebody to build one |
| `standard` | 4 hours | 4 hours | The workers and the file store are running, so a restore has somewhere to go and the time is replaying archived data rather than provisioning a machine |
| `full` | 1 hour | 2 hours | The tightest figures the system offers, and they need a standby host that already exists |

`lite` is what an install that never says otherwise runs, and it is what the example
environment file sets. I have not read the value off your server, because I do not touch it
while you are asleep; if it says something else, the row above changes and the
recommendation below does not.

**The backup schedule is already better than the promise, and I would not promise the
difference.** The copies are scheduled to run every hour at worst, and the database's write
log every minute, so the exposure on paper is one hour rather than twenty-four. It is tempting
to write the better number into the agreement. I recommend against it: a recovery point is a
promise about the slowest copy on the worst day, and the gap between one hour and twenty-four
is the margin that absorbs a failed backup nobody noticed for a day. Promise the profile's
figure, keep the margin, and let the client be pleasantly surprised.

**Options.**

- **Option A, recommended: sign the `lite` figures, 24 hours and 8 hours.** They are what one
  host with no standby can actually deliver, and eight hours is honest about the fact that the
  recovery time includes somebody building a machine. Costs nothing and needs no change to
  what runs.
- **Option B: sign the `standard` figures, 4 hours and 4 hours.** This is a real promise and it
  requires the install to be on the standard profile, which means the worker, the file store
  and the trace database running rather than the four containers. If you want to sell a
  four-hour recovery, this is the smallest install that supports it.
- **Option C: sign the `full` figures, 1 hour and 2 hours.** Needs a second host standing by,
  paid for whether or not it is ever used. Worth it for a client whose finance system is in
  here and not otherwise.

I recommend A for the first install and B as the shape of the paid tier: the difference between
them is a second host and about an hour of setup, and it is a much easier conversation to have
as an upgrade than as a promise you have to walk back.

**One thing that blocks all three, and it is item 44.** The code refuses to produce a service
level statement at all until a restore drill has actually verified, because a recovery time
nobody has measured is a number somebody chose. Nothing takes a backup yet, so nothing has ever
been restored, so today every one of the three options above produces a refusal rather than a
document. That is deliberate and it is the right behaviour. It also means item 44 comes first:
answer that one and this one becomes real.

---


## 47. Eleven of the thirteen safety mechanisms in the system have never been switched on, and I need one decision about where scheduled work runs - DECIDED: Option A, a scheduler inside the application container

**Your decision, 2026-09-09: Option A.** The policy half is built and pushed:
`brain.ops.schedule` says which of the thirteen are owed a run and which of them this process
may start. Twelve of the thirteen are its; the audit anchor keeps its external timer, because
a second caller would give the one working control two.

The retention sweep is held to report-only until you release it, which is the promise made at
the bottom of this item and is now a property the type enforces rather than an intention.

**The finding.** The system has thirteen mechanisms that only work if something runs them on a
schedule: pruning data past its retention window, the permission canaries, the restore drill,
the backup exposure alert, the refusal digest, the staff directory sync, knowledge
re-verification, entity resolution calibration, redriving stuck jobs, resuming interrupted
side effects, the model health probes, and the spend estimator correction. Eleven of them have
no caller anywhere. Each one is written, tested, documented, and nothing has ever run it.

**One of the twelve moved on 2026-09-09 and the move is smaller than it sounds.** The spend
estimator correction now has a caller: the cost review section of the usage screen asks for it.
That takes it out of the list of mechanisms nothing calls and puts it in a shorter list of
mechanisms whose caller is a screen nobody opens on a schedule. It is one link of the chain
rather than the chain, and the registry says so rather than counting it as wired.

The thirteenth is the audit anchor, and it works: a GitHub Actions timer calls a web address in
the system every day, and that publishes the tamper-evident seal on the audit trail. It is the
one that runs, and it is the reason I can tell you the others do not: the check that found
them had to get the working one right first.

**How bad is this right now.** Not bad, and I want to be accurate. Nothing has degraded,
because none of these has ever run and there is no client data in the system yet. The reason
it is worth waking up to is the direction it goes: **the console screens being built now will
say the estate is protected.** A retention screen that shows a 30-day window is telling the
truth about the policy and nothing about whether a single row has ever been deleted. That gap
between what a screen says and what is happening is the failure mode, and it arrives quietly
on the day somebody trusts the screen.

There is now a check that goes red if a mechanism that was wired stops being wired, or if the
written record and the code disagree in either direction. It is deliberately not red today:
a check that fails the day it lands is a check somebody switches off.

**What I need from you: where should scheduled work run.** This is a decision about your
server rather than about the code, which is why it is here.

- **Option A, recommended: a small scheduler inside the application container.** Every one of
  the thirteen already has a function that answers "is this due", so the scheduler is a loop
  that asks each of them and puts a job on the queue. No new container, no host configuration,
  and it works on the small deployment profile, which is the one you are running. It needs a
  lock so that two copies of the app do not both run the same sweep, and the database already
  provides the kind of lock that does this. About a day of work, and it ships with the product,
  so every client after you gets it by installing.
- **Option B: more GitHub Actions timers, like the audit anchor.** Nothing changes on your
  server and the pattern is proven, because one of these already works that way. I recommend
  against it beyond the anchor, and the reason is the whole shape of this product: a
  client-hosted system whose safety mechanisms are triggered from our GitHub account is a
  system we operate on their behalf. The client cannot see the schedule, cannot change it, and
  loses it if the relationship ends. It is the right answer for exactly one thing, publishing a
  seal to a repository we hold, and the wrong answer for every other one.
- **Option C: timers on the server itself.** Standard, reliable, and it puts the schedule
  outside the product, so every client installs it by hand from a runbook and their thirteen
  timers drift from ours. It also means the installer has to write files as root.

I recommend A, and leaving the audit anchor where it is until A has been running long enough
to trust.

**One thing to know either way.** Turning these on is not free of consequences: the retention
sweep deletes things. That is its job, and the first time it runs on a system that has been
accumulating rows since installation it will delete a great deal at once. When we wire it, it
runs in a dry-run mode first and reports what it would remove, and you look at that report
before it is allowed to remove anything. I will not turn that one on silently.

---


## 48. A department head cannot read their own department's activity, and the fix is one line from you - DECIDED: Option A

**Your decision, 2026-09-09: Option A.**

**The finding.** An audit entry records four things a permission can be written against: what
happened, what kind of thing it happened to, which thing, and who did it. It does not record a
department. A department head's permissions are written against their department, so their
audit permissions match no entry at all, and their activity page is empty. Not filtered:
empty. I found this while building that page, and the page would have been empty for every
reader it exists for while passing every test, because a test fixture uses a company-wide
permission and never notices.

I ran both halves rather than reasoning about them. A reader whose audit permission is scoped
to a department sees nought rows. The same reader with the same permission scoped to a named
person sees that person's rows and nobody else's. So the recommendation below is not a theory
about what the permission model could do; it is what it does today.

Two tasks on the plan are blocked by it: all-activity with department filters, and the
department head's own activity view. A third, usage and tokens by department, is blocked by
the same shape in a different table.

**Why I have not just fixed it.** The obvious fix is to record the department on every audit
entry, and that is a decision about the record this system keeps longest. Today an audit row
says what somebody did. With a department on it, the sequence of rows says where they worked
and when they moved, kept for as long as the audit trail is kept, which is years. That is a
different thing to hold about a person, and it is not mine to decide at two in the morning.

**Options.**

- **Option A, recommended: write a department head's audit permissions against the people
  rather than against the department.** Permissions can already name a set of people, and the
  staff directory already knows who is in a department, so the grant becomes "may read the
  audit trail for these fifteen people" and is rewritten by the directory sync when somebody
  joins or leaves. Nothing new is retained, no column is added, and the permission says
  exactly whose activity that head may read, which is a thing you can review on a screen.

  Two costs, and the second is the one I would want you to hear. It goes briefly stale between
  a transfer and the next sync. And audit permissions are per kind of thing rather than one
  permission: there is one for entries about people, one for entries about grants, one for
  agents, connectors, sessions and so on, eight in all. So a department head is eight grants
  rather than one, and whoever writes them has to decide which of the eight a head should
  have. That is a real question and it is a better one than the one this item is about,
  because the answer is a list you can read.
- **Option B: record the department on every audit entry.** Every department view then works
  directly and simply, including the two blocked tasks. The cost is the one above: the audit
  trail becomes a record of where each person worked over time. There is a second, quieter
  cost, which is that a department written at the time of the event will disagree with the
  org chart after somebody transfers, so the system would then have two answers to "which
  department was that", and the code would have to say which one every screen means.
- **Option C: leave it and say so.** Department heads read grants, budgets, knowledge coverage
  and their people's work, and do not read the audit trail; the audit trail is for the auditor
  and the super administrator. This is a defensible product decision rather than a fault, and
  it costs nothing.

I recommend A. It answers the question without changing what is kept, and the thing it
produces, a permission that names the people it covers, is easier to review than a permission
that names a department and relies on a column agreeing with it.

**Nothing is broken today.** Nobody is being shown data they should not see; the failure is in
the other direction, and there is no client data in the ledger yet. The department budget page
does work and shipped tonight, because a budget is written against a department and does not
have this problem.

---


## 50. Thirty of the remaining tasks are things people do on the week of a migration, and the percentage counts them as if I could build them - DECIDED: a generated checklist, and the security ones gate the cutover

**Your decision, 2026-09-09, and it is neither of the options as I wrote them.** You
asked for the third option, the separate checklist, and said the objection to it had to go
rather than the option: the percentage must reflect buildable work *and* there must be no
security hole. Those are separable and I had folded them together, so this is the version that
does both.

1. The thirty leaves are flagged in the work breakdown as work for people, so the tracker
   reports buildable done and acts outstanding as two numbers.
2. `docs/delivery-checklist.md` is **generated** from those flags rather than written, so it
   cannot go short and cannot drift. A flagged leaf missing from it fails the test suite.
3. The subset with a security consequence, revoking OAuth grants, recording the date access
   actually ended, the restore drill, gates the **cutover**: `brain.migration.decommission`
   refuses to report a completed cutover while any of them is unrecorded. That is the answer
   to "a list nothing gates is a list nobody reads", and it gates the day rather than the
   build.
4. The four leaves naming one company's own skills and Lark groups stay recorded as
   unbuildable here, because a product every client installs cannot hold them.

**The decision.** The tracker says 1045 of 1251 tasks are done. Thirty of the 206 that are
left cannot be done by writing code, by me or by anybody: they are acts. "Announce the switch
before removing their bot." "Revoke every OAuth grant." "Record the date access actually
ended." "Twenty real questions as the acceptance set." "Restore drill executed in front of the
client." Every one of those has to happen and none of them is a commit.

They are all in M37, and they are the reason that module has stayed the largest open block all
week while I have closed twenty-two leaves inside it. What I should do about the tracker is
your call, and there are three options below.

**Why it matters rather than being tidy-up.** The percentage is the number you look at to know
how the build is going, and it is currently mixing two things that behave differently. Code
tasks close when I write them. These close when a person does something on a specific day with
a specific client, which cannot start before there is a client to do it with. So the number
will keep rising until it reaches about 86 percent and then stop, and the stop will not mean
the build stalled.

**Three of the thirty are worse than uncountable, they are unbuildable on purpose.** Four
leaves name one company's things: twelve house skills by count, four skills by name, which
Lark groups each agent sits in, and what the outgoing vendor produced that people still rely
on. This repository is the product every client installs, and the first rule in `CLAUDE.md` is
that no company's details go in the source. Those four cannot be code here without breaking
that rule, and I have not tried to make them fit.

**What I did instead, so you can see the shape.** The generic half of the same work is now
built and tested: what the old system holds and what happens to each item, what is carried and
what is re-derived, the parallel-running period and its cutover criteria, the decommission, the
agent rebuild, the skills and the learning. Nine modules, none of which names a vendor or a
company. The parts that are left are the parts that only exist on the day.

**Options.**

- **Mark them in the work breakdown as work for people, and show two numbers.** The tracker
  would say something like "1045 of 1221 buildable, plus 30 to do on the week". One flag per
  leaf in `docs/wbs/*.js`, an afternoon, and it makes the percentage mean one thing again.
  This is the recommendation: the work stays visible, which matters because forgetting to
  revoke an OAuth grant is how an outgoing vendor keeps reading a client's email.
- Leave it. Nothing breaks, the number tops out below a hundred, and you and I both know why.
  This is a real option if you would rather I spend the afternoon on something else, and I
  would rather that too if you have a preference for what.
- Move them out of the work breakdown into a separate delivery checklist. Cleanest tracker,
  and the risk is the one thing I would not accept: a list nothing gates is a list nobody
  reads, and these thirty are exactly the ones with a security consequence.

**One thing I will do either way**, because it costs nothing: the four leaves that name a
company's things are recorded here as unbuildable rather than left looking merely undone, so
nobody spends a day trying to make them fit.


## 31. Wave 2's last seven jobs - DECIDED: Option A, models behind the inference server

**Decided 2026-09-06: Option A.** The parsing and name-recognition models go behind the same
inference server that embedding was always going to use. Every Brain container stays small,
and there is one place that loads models instead of three.

What that means in practice: the ~1.5 GB machine-learning stack measured below never enters
our own image. The Brain sends a document or a piece of text over the network and gets back
what was extracted. The inference server needs its own memory, which is why this waited on 25,
and 25 is now answered: removing your other project frees about 2.4 GB, comfortably more than
this needs.

**Correction, 2026-09-06, after sizing it: 2.4 GB is not comfortably more than this needs.**
The sentence above was written before anybody added the three models up, and the arithmetic
says otherwise. Nothing about the decision changes; what changes is that it has a price, and
the price is bigger than the room 25 frees.

| what has to be resident | how much | where the figure comes from |
|---|---|---|
| Qwen3-Embedding-0.6B, for embedding | 1,152 MB | 0.6 billion parameters at 2 bytes each, which is the precision the published weights are in |
| GLiNER, for the names patterns cannot see | 832 MB | about 0.21 billion parameters at 4 bytes each |
| Docling's layout and table models, for parsing | 512 MB | a judgement. Docling publishes no single parameter count and we have never installed it |
| Python, PyTorch, the tokenisers and the web server | 512 MB | a judgement, and the figure most likely to be wrong |
| **the container** | **3,072 MB** | the four above, plus 64 MB for one request at a time |

**None of those five numbers has been measured**, and that is stated rather than glossed:
there is no such server on this machine and no weights downloaded, so there is nothing here
to measure. The first two are arithmetic from published parameter counts, which is a floor
rather than a result. The third and fourth are judgements.

What it does to the budget: the `standard` profile now wants 3,328 MB more than it has, where
before the inference server it wanted 256 MB more. Removing your other project frees 2,402 MB,
so **roughly 926 MB short even after that is done**. Sizing the container smaller to make the
sum work would produce a container that is killed with three models half loaded, which on a
shared machine is somebody else's outage rather than ours.

Three ways out, none urgent, because there is no image to deploy yet:

1. **A second machine.** The cleanest, and it also answers the trace ledger in 25.
2. **A smaller embedding model.** Qwen3-Embedding-0.6B is the largest of the three by some
   way. A smaller one costs answer quality on retrieval and I can measure how much before you
   decide.
3. **Int8 weights.** Roughly halves the two computed figures. It costs some accuracy, and for
   GLiNER specifically it can move where a detected name starts and ends by a character, which
   matters because a half-redacted name identifies a person as well as a whole one does.

Nothing is blocked on you today. This is here so the number is on the record before somebody
tries to deploy it and finds out on the machine.

The original analysis is kept below because the measurements are what made the choice.

---

## 29. The console address - DONE: your existing address, now registered

**You were right, and it is done.** The address this deployment already answers on is exactly the
address, and it is now registered in the realm. Nothing further is needed from you today.

**Why your instinct was correct.** The console is not a separate system, it is the screen on
top of the one already running at that address. Keeping both on one address is the better
arrangement rather than merely the convenient one: the browser treats a different hostname as
a different site, so a separate address would need cross-origin permissions configured for
every call the console makes, and the sign-in token would be crossing a boundary it does not
have to cross.

**What is registered**, exact paths rather than a wildcard, because Keycloak will hand a
sign-in code to any address on this list and a wildcard means any path on that host:

    <this system's address>/auth/callback                  where sign-in returns to
    <this system's address>/signed-out                     where sign-out returns to
    http://localhost:5173/auth/callback                    development only

**The one thing to know for when you buy a domain.** Those addresses live in
`ops/keycloak/realm-export.json`. When the real domain replaces the sslip.io one, all three
entries change together, or sign-in completes at Keycloak and then fails on the way back. The
symptom is "login is broken" and the cause is one line in a file nobody would think to open.
Tell me the domain and it is a two-minute change; there is now a test that fails if the file
and the console ever disagree about these paths.

---

## 30. How the automation canvas reaches the Brain - DECIDED: Option A, no extra cost

**Decided 2026-09-06: Option A. To answer your question directly: no, there is no additional
cost and no additional server.**

A Docker network is not a machine. It is a named route between containers that already exist,
declared in a few lines of the compose file. It uses no memory, no disk and no money. Nothing
new is deployed and nothing is exposed to the internet.

What it buys is that the automation canvas can reach the Brain and nothing else, while still
having no route out to the internet. Option B would have sent that traffic out to the public
address and back in, which works and spends part of the reason the sandbox exists.

---

## 25. Server capacity - PARTLY DONE: you freed real memory, and the number that binds has not moved

**Re-measured on the live host 2026-09-06, after you said you had deleted resources under
the other project. Some of this is good news and one part of it is not, so here is both.**

**What your cleanup actually did.** Seven containers are gone: 24 running now, 31 before.
Free memory went from 5,641 MB in use to **8,469 MB available**. That is real and it is
worth having.

**What did not change, and it is the one that decides the answer.** Every container that
went was one with no memory limit set. The containers that reserve memory are all still
there, and they still reserve **9,600 MB of the 11,960 MB on the machine**, which is the
same figure as before you started.

That distinction matters more than it sounds. Free memory is what is spare at this instant.
A declared limit is a promise the kernel keeps: it is memory another container is entitled
to take the moment it gets busy, whether or not it is using it now. This system sizes itself
against the promises, not against the instant, because sizing against the instant is how a
deployment works all week and kills a neighbour on the one day the neighbour is busy.

**Here is where all 9,600 MB sits, measured container by container.**

| Whose | Containers | Reserved |
|---|---|---|
| The Dify stack | 10 (api, worker, web, db, weaviate, sandbox, plugin daemon, redis, nginx, ssrf proxy) | **3,712 MB** |
| Langfuse, the old copy | 2 (server, db) | **1,280 MB** |
| The old Brain worker | 1 (`verz-brain-worker-1`) | **1,024 MB** |
| The Company Brain, live | 3 (app, database, cache) | 3,584 MB |

Plus `verzbrain-activepieces`, which reserves nothing and is using 748 MB, the largest
single consumer on the box.

**So the total still to remove is 6,016 MB of reservations plus that 748 MB.** All of it
belongs to the old project. None of it is the Company Brain.

**What each removal buys, in order of size.**

1. **The Dify stack, 3,712 MB.** The single biggest block, and ten containers.
2. **The old Brain worker, 1,024 MB.** It is the v1 project's, not this one's. This system's
   own worker is a separate thing and is not in that table.
3. **Old Langfuse, 1,280 MB.** This one has a caveat: the full feature set includes a
   Langfuse of its own, so removing the old copy frees the memory and the new one will ask
   for some of it back. Still worth doing, because the new one is sized and the old one is
   not.
4. **Old Activepieces, about 750 MB.** Reserves nothing, so removing it does not change the
   9,600, but it frees the most memory of any single container.

**What it unlocks, computed rather than estimated.** Remove the 6,016 MB above and the cap
rises to 11,704 MB, which leaves 7,736 MB after the live services and the host's reserve.

| | Wants | Today | With the other project gone |
|---|---|---|---|
| The main feature set | 5,760 MB | short by 4,040 MB | **fits, with 1,976 MB spare** |
| The full set, tracing included | 8,320 MB | short by 6,672 MB | short by 584 MB |

**So removing the other project solves the main feature set outright.** That is the answer
to this item. The full set, which adds the tracing stack, is still 584 MB short afterwards,
and that is a separate and much smaller decision than the one this page has been carrying.

**A correction, because I got this wrong an hour ago.** The first version of this section
said everything would fit with room over. It does not: the full set is still 584 MB short.
I only know that because a test I wrote at the same time recomputes it, and it failed on the
sentence I had just written. The arithmetic now lives in
`test_removing_the_other_project_is_what_makes_the_full_set_fit`, so this table cannot go
stale without the suite going red.

**I have lowered our own cap rather than raised it, and I would rather explain that now than
have you find it.** The cap was 6,400 MB, and while your neighbours reserve 6,016 MB on an
11,960 MB machine, 6,400 was never a number the machine could honour: the two together
promise 12,416 MB of a box that has 11,960. Nothing was checking it, because the only test on
that number recalculated it from itself and was green whatever it said. It is now 5,688 MB,
which is what the measurement leaves, and it is computed from the machine rather than typed
beside it. This makes the shortfall bigger on paper and it does not make anything smaller in
reality: nothing deployed changes, because the profile in use is the base one either way.
When those containers go the cap rises to 11,704 on the same arithmetic, and that is one
commit.

**Nothing is blocked on this.** Everything currently being built fits inside the cap as it
stands.

---

**The paid options, kept for the record, since they are what this page said before.**

| Option | Cost | What you give up |
|---|---|---|
| Use a hosted tracing service instead of running one | A subscription, roughly the price of a small server | Your traces sit on somebody else's infrastructure. They contain no client data by design, but they do show what your staff asked |
| A second small server just for tracing | Another VPS, similar to what you pay now | Nothing functionally; one more machine to keep patched |
| Run without full tracing | Nothing | When an answer is wrong, "why" gets much harder to establish. This is the thing that makes an AI system auditable |
| Move your other project off this box | Depends where it goes | Nothing here, but it is work on the other project |

---

---

## 28. Production restarts every few minutes - DONE, and it was a leftover timer of mine

**Fixed and verified on 2026-09-06.** You told me to run the command, I ran it, and the
recreates stopped.

**The evidence, before and after.** In the ninety minutes before the fix, `brain-deploy`
ran 21 times and deployed on all 21, recreating the container every time. No new images were
being published in that window, so every one of those was pointless and every one dropped
whatever was in flight. The last was at 02:41:22. `sudo systemctl disable --now
brain-deploy.timer` ran at 02:57, and there has not been another since. `brain-autodeploy`
is untouched and still deploying real changes.

Still worth doing when convenient, and not urgent: delete `/usr/local/bin/brain-deploy`, so
that the next person reading that directory does not find two scripts that look
interchangeable and re-enable the wrong one.

The diagnosis below is kept because it was wrong first, and the way it was wrong is the
useful part.

---

**Corrected on 2026-09-06. The earlier diagnosis on this page was wrong, and it was wrong
because I checked one of two things that could have caused it.** What follows replaces it.

**Nothing is broken and nothing is lost.** The app is healthy and serving the right commit,
and every recreate passes its health check within about eight seconds. But it is being
recreated every three minutes and is briefly unreachable each time, which drops in-flight
requests.

**The cause: there are two deploy timers on your server, and the old one redeploys
unconditionally.**

| Timer | Interval | Behaviour |
|---|---|---|
| `brain-autodeploy.timer` | 2 min | Correct. Compares the pulled image against the running one and does nothing when they match. |
| `brain-deploy.timer` | 3 min | **The problem.** Pulls and recreates the container every single run, whether or not anything changed. |

`brain-deploy` is the older script, the one with the redeploy-loop bug. I rewrote it as
`brain-autodeploy` and installed that. **I never disabled the old timer,** so both have been
running side by side ever since, and the old one has been recreating production every three
minutes.

**How I know, rather than inferring it.** The recreate is logged by the process that did it.
At 08:28:39 `brain-deploy.service` started; at 08:28:42 it logged `pulling` and `deploying`;
at 08:28:42 to 08:28:44 it logged `Recreate`, `Recreated`, `Starting`, `Started` against the
app container; Docker's own event stream shows the matching create/kill/die/destroy/start
burst at 08:28:43. Across the same window `brain-autodeploy` ran twice, at 08:27:07 and
08:29:17, and deployed nothing both times.

**Why the previous answer was wrong.** It blamed Coolify healing an exited one-shot `migrate`
container, and its evidence line said "my own deploy timer logged no deploys across the same
window, so it is not me". That check was real, and it looked at `brain-autodeploy`. It never
occurred to me to ask whether there was a second timer. There was, it was also mine, and it
was the one doing it. The `migrate` service is not involved: the current compose has no
`migrate` service at all.

**The fix is one command, and it is reversible.**

```
sudo systemctl disable --now brain-deploy.timer
```

`brain-autodeploy.timer` already does the job properly and is unaffected. It deployed
tonight's work correctly seven times, most recently `db2a227`, healthy in eight seconds. If
anything goes wrong, `sudo systemctl enable --now brain-deploy.timer` puts the old one back.

**Why I have not run it.** Changing systemd units on your production host is outside what I
am permitted to do unattended, and the guard that stopped me is the right guard. It is one
command and the diagnosis above is measured, so it should take you a minute.

**Worth doing afterwards, and not urgent:** remove `/usr/local/bin/brain-deploy` as well, so
the next person reading `/usr/local/bin` does not find two scripts that look
interchangeable and re-enable the wrong one.

---


## 26. The chat widget on a client's marketing site - DECIDED: public knowledge only, no login

**Decided 2026-09-06.** In your words: public users get public knowledge only, a Super Admin
or Department Admin decides what counts as public knowledge, and there is no login for a
visitor to chat with the widget.

**What that means in this system, and it fits the existing model rather than bending it.**
An anonymous widget session holds exactly one grant, over knowledge explicitly marked
public, and nothing else. Entitlements here are additive only, so a stranger still holds
nothing by default: the difference is that one narrow grant now exists to be held, instead
of none.

Three consequences worth reading before this is built, because they are the parts that go
wrong quietly:

**Marking something public is a one-way door in practice.** Once an answer has been given to
the internet it has been given, and un-marking the source afterwards does not retrieve it.
So the marking action is going to be audited, and it is going to name the person who did it,
in the same way a grant does.

**Public is a property of the knowledge, never of the question.** The widget cannot be
allowed to reach a general search that then filters for public items, because the filter
becomes the only thing standing between a stranger and everything else. The reach is
computed the same way it is for staff, and a public grant simply resolves to a narrow scope.
That is the whole reason this fits: it is the same code path, with a smaller set.

**A department admin can only publish their own department's knowledge.** Their role already
requires a scope, and this is exactly what that scope is for. A Super Admin has no such
limit, which is the distinction between the two roles here.

**Rate limiting and abuse become load-bearing rather than hygiene**, because the widget is
now a service anybody on the internet can call. M23 already carries the widget session
minting and abuse guard, and it stops being an optional refinement the moment this ships.

Not yet built: the public marking itself, the audit row for it, and the anonymous grant.
Those are wave 3 and 4 work and they now have a decision to be built against.

---

**Nothing is blocked.** The plumbing is being built either way, and it is safe by default
today: an anonymous visitor currently holds nothing, so the widget can mint a session and
that session can ask nothing. Your answer decides what, if anything, that session is allowed
to reach.

**The situation.** The plan has a chat widget embedded on a client's public website. Whoever
loads that page is a stranger: not signed in, not an employee, possibly a competitor, a
bot, or a journalist. The rest of this system answers "what may this person see" by looking
up what they hold. A stranger holds nothing, and the way this platform is built, nothing
means nothing: entitlements are additive only, so an anonymous caller sees exactly what has
been explicitly granted to anonymous callers, and no such grant exists.

**So the widget works and answers nothing, unless you decide otherwise.** That is a
deliberate safe default rather than an oversight, and it is where it will stay until you
choose.

**The three shapes it could take, and what each costs:**

1. **Lead capture only.** The widget collects a question and a contact address and creates
   a task for a human. It answers nothing itself. Cost: it is a contact form with a chat
   interface. Benefit: no exposure of any kind, and it is the only option with no way to be
   wrong.
2. **Public knowledge only.** A specific, small, explicitly published set of content is
   granted to anonymous callers: opening hours, service descriptions, published pricing. The
   agent may answer from that and nothing else. Cost: somebody has to decide, per client,
   what is public, and be right. The risk is not the answer, it is the *retrieval*: a
   question is a probe, and an answer that says "I cannot find that" for one product and
   answers for another has told a competitor which products exist.
3. **Identify first, then answer.** The widget asks who they are and verifies it, typically
   by emailing a link. After that they are an ordinary principal with ordinary entitlements
   and nothing here is special. Cost: friction on a marketing site, which is where friction
   costs the most.

**My recommendation: 1 for the first client, with 2 available per client afterwards.** The
reason is not caution for its own sake. Option 2 needs a person to correctly classify a body
of content as public, on a page where being wrong is visible to everybody including
competitors, and the first client is the worst place to learn what that classification
process needs to be. Option 3 is a real product and belongs in a later wave.

**What I need:** which of the three, and for option 2, who at the client decides what is
public.

**What is being built meanwhile:** the session minting and its abuse guard (M10.5.5,
M23.1.4), which are needed under all three options. A widget on a public site is an
unauthenticated endpoint that mints credentials, so it is rate-limited per origin and capped
on live sessions per origin, and an anonymous session expires much sooner than a signed-in
one.

---


## 24. When a source is down, should the answer name it? - DECIDED: keep it as built

**Decided 2026-09-06: go with the recommendation. No code changes.** The answer names a
source only when that person could already see it in their own tool list; everyone else is
told part of the answer is unavailable, and the full list goes to the operator's log.

The reasoning is kept below because the cost is real and somebody will meet it: a
narrowly-permissioned person gets a vaguer message and has to ask. When that happens, the
person they ask can read the log, and that is the intended path rather than a workaround.

---

**Nothing is blocked. I have built the safe reading and this is a question about whether to
loosen it.**

The plan says that when the Brain cannot reach one of your systems, the answer should say
which one. That is obviously good service: "I could not reach Xero" is a better answer than
"something went wrong", because you know whether to wait or to ask somebody.

**The problem is who else is asking.** The same sentence, sent to somebody who has no access
to Xero at all, tells them Xero exists and that you connect to it. Ask about invoices and
learn there is an accounting system; ask about tickets and learn there is a helpdesk. A
person with no permissions anywhere could map every system you run, one question at a time,
without ever seeing a single record.

That is the same rule the rest of the system already follows: an answer never says "I looked
in the finance ledger and found nothing", because the sentence gives away the ledger.

**What I have built.** The answer names a source only when that person could already see it
in their own tool list. Everything else becomes "part of this answer is unavailable", and
the full list of what failed goes to the operator's log, where you and whoever is on support
can read it.

| | Names every failed source | Names only what they can already see |
|---|---|---|
| A person with full access | Sees exactly what is down | Sees exactly what is down |
| A person with narrow access | Learns which systems exist | Told part of the answer is unavailable |
| Somebody probing | Can map your whole estate | Learns nothing |
| Your support team | Reads it in the answer | Reads it in the log |

**My recommendation: keep it as built.** The cost is that a narrowly-permissioned person
gets a vaguer message and has to ask, and the person they ask can see the log. The cost the
other way is a map of your systems available to anybody who can type a question.

This only becomes a real difference once there are people using it with narrow permissions,
which is wave 4. Worth deciding before then rather than during.

---

---


## 27. Automatic deploys have never worked, and the pipeline said they had - DONE

**Closed 2026-09-05. Deploys are automatic and verified.** You ran the installer, the timer
fired on install, deployed, and reported the app healthy at schema revision 0007. Next check
was scheduled two minutes later. Nothing further is needed from you.

**What was wrong.** The deploy step checked for three Coolify secrets, did not find them,
printed `Coolify secrets not set - skipping deploy` and exited *successfully*. The next step
then printed **"Deployed"**. So every run looked like a deploy on the summary page and was a
no-op. Your server ran commit `d58b3ce` at 24.1% while the work was at 31.3%: roughly a
hundred tasks finished, tested, pushed and not live.

**How it works now, and why it is not what you were asked for.** You were going to give me a
Coolify URL for GitHub to call. I did not use it. That port is private only because your
firewall allows 22, 80 and 443, and letting GitHub reach it means allowlisting GitHub's
Actions ranges: thousands of them, changed without notice, and anybody with a GitHub account
can run a job from one. That would put the panel controlling every container, database
included, in front of a large slice of the internet to save about a minute of latency.

So the server watches instead. A timer checks every two minutes whether the `:latest` image
has moved and deploys when it has. The CI gate survives, which is the part worth checking
rather than assuming: that tag is only moved by the Deploy workflow, which runs after CI
passes, so the tag moving is itself the statement that the gate passed.

**Two things stop this failing silently the way the last one did.** The deploy script waits
for the container to report healthy before reporting success, and the Deploy workflow polls
the live site for eight minutes and fails unless it reports the commit that run published. A
trigger is not an outcome, and the previous version only ever checked the trigger.

**One mistake of mine in the middle of this**, recorded because it is the same class as the
bug: my first install command named `/usr/local/bin/brain-install-autodeploy`, which had
never been installed, because writing it was blocked as a privileged change. I listed the
steps I could not do and did not check that the ones I could had actually happened. You hit
the error. Checking that a file exists after claiming to install it costs one command.

**Your Coolify token is still unused and still optional.** With it on the server the deploy
goes through Coolify's API so its UI stays truthful about what is running; without it the
deploy uses Coolify's own compose file, which is what runs today. The two commands are in
this repository at `ops/deploy/brain-deploy`.

---

## 23. Should the client's audit trail show your deployment history? - DECIDED: leave the two chains separate

**Nothing is blocked. I have built it the safe way and this is a question about whether to
open it up.**

Every deploy is now recorded: the time, the version, whether it worked, and which tasks
went out in it. The record cannot be edited afterwards without that being detectable.

**The question is where it lives.** There are two records in this system:

| | The permission trail | The deployment trail |
|---|---|---|
| What it holds | Who could see what, who was refused, who granted whom access | What version went out and when |
| Who can read it | Your staff, filtered by their own permissions; a client can ask for their own | Nobody yet: it is for you and whoever runs the servers |
| Where it goes | Into the compliance export you would hand an auditor | Nowhere outward |

Today they are separate. A deploy does not appear in anybody's audit view and does not
appear in a compliance export.

**Why I kept them apart.** The permission trail is built around people: every entry is
about a person, an agent or a record, and the whole design assumes you can ask "everything
that ever happened to this person". A deployment is about none of those. Putting it in
would mean anybody who can read the full audit trail also reads your release history, and
that a compliance export handed to a client contains your engineering activity. Neither
is obviously wrong; both should be your choice rather than a side effect.

**What you would gain by merging them.** One timeline. An auditor asking "did the code
change between these two permission decisions" could answer it from one place instead of
lining up two records by time.

**My recommendation: leave them separate, and revisit if a client ever asks.** The cost of
being wrong in this direction is a slightly awkward query for an auditor. The cost the
other way is client-visible information you did not intend to publish, and unpublishing it
is harder than publishing it.

Nothing to do unless you disagree.

---

---

## 22. The plan says production deploys only tested releases. You asked for every push. - DECIDED: every push deploys, no tagging

**These are both reasonable and they cannot both happen. I have kept yours running and am
not changing it without you saying so.**

On 5 September you asked whether deploys should be automatic and answered yes. They are:
every push to the main branch builds an image, and the server picks it up within three
minutes.

The build plan says something different for production: deploy only from a tagged release
that has passed staging. That is the safer arrangement and it is slower by design.

**What each one costs.**

| | Every push (what runs today) | Only tested releases (what the plan says) |
|---|---|---|
| How fast a fix reaches you | Three minutes | When somebody tags a release |
| What reaches production | Whatever passed the automated checks | Only what also ran against a real database with real migrations |
| When it goes wrong | The rollback puts the previous version back automatically | It mostly does not get that far |
| Who has to do something | Nobody | Somebody tags, and somebody looks at staging |

**Why this is worth deciding now rather than later.** Right now nothing is behind the
permission gate and no client data is in the system, so a bad deploy costs three minutes of
a page being down. That stops being true the moment real connector credentials go in.

**My recommendation, and it is a middle option rather than either column.** Keep every push
deploying automatically, and add staging *in front of it* rather than instead: the push
deploys to staging, the full test suite runs there against a real database, and production
follows automatically only if that passes. You keep the three minutes; the difference is
that the three minutes now includes a real migration against a real Postgres, which is the
one thing the current automated checks cannot do.

That is roughly a day of work and it needs no decision from you beyond "yes, do that".

**What exists already:** the staging stack is built and its isolation is tested. It is not
deployed yet, and it uses about 1.4 GB on a server with 6.4 GB free, which is comfortable
alongside your other project on the same box.

---

---

## 21. Where do role grants that came from the directory live? - DECIDED: directory-sourced grants get their own table, owned by the sync

**A smaller decision inside the same area, recorded so it is not made by accident.**

Roles can be granted two ways: a person gives somebody a role, or the role arrives because
of a group they are in, synced from the company directory.

Every role grant currently requires a named grantor and a reason, because the review of those
two fields is the only thing that ever removes a grant that should not have been made. A row
that arrived from a directory has no human grantor.

**What I did:** recorded the grantor as the identity provider itself. It satisfies the field
and it quietly puts unreviewed rows in the same table as reviewed ones, where a person
scanning for mistakes cannot tell them apart.

**The options:** keep them together and add a column saying where each came from, or keep
directory-sourced grants in their own table that the sync owns and can also remove from.

**My recommendation:** the second. The sync needs to be able to take a role away when
somebody leaves a group, and a process that can delete rows a person created is a worse
thing to build than a process that owns its own table.

**BUILT (2026-09-05).** `auth.directory_role_grant`, migration 0006, with the reconciliation
in `brain.identity.directory`. The sync may delete anything in that table and nothing else,
and that is structural rather than careful: the reconciler's signature has no parameter a
hand-made grant fits into, and a guard refuses any future reconciler whose annotations admit
one. A check inside the function would be removable by whoever adds the feature that needs
it; a parameter that does not exist has to be added first, which is a diff with a reviewer
on it.

**The natural key is (person, role, group), not a generated id.** Two groups both conferring
Approver are two rows, so leaving one group keeps the role. A generated id would let the same
assertion be stored twice, and then removal would delete one row, report the role removed,
and leave the person holding it from the other.

**This is the first DELETE permission granted anywhere in the system**, and it is scoped to
this one table. There is a test whose only job is to fail if any future migration grants
DELETE on anything else, so it does not become a precedent by being copied.

**One thing I got wrong in the brief, worth recording.** I told the agent to wire the union
into the entitlement resolver. That resolver structurally refuses to see a role at all, which
is a rule from earlier in the build, and the agent pushed back rather than breaking it. The
union belongs in the role path and that is where it is. I verified the pushback before
accepting it.

**A near-miss worth stating because it looks like a bug and is not.** Two spellings of a
group name reconcile as a delete plus an insert every run. In the vault holder list (item 17)
I normalised exactly this, because those names are typed by a person and two spellings are
one pair of hands. Here they are not: Keycloak treats `Sales` and `sales` as two groups, so
folding them would merge two sources of one role, and leaving one group would then remove a
role the other still justifies. Exact comparison is correct here. Same-looking problem,
opposite answer.

**Still not built, and not part of this:** the hand-made `role_grant` table (M1.3.2). Only
the type exists. Every docstring in this change says so, so nobody mistakes the new table for
it.

---

---

## 20. Two designs for what a person's ID is, and they contradict each other - DECIDED: keep the indirection; the architecture line is wrong

**Not urgent, but it gets expensive the moment the identity provider is wired in.**

The architecture says a person's ID in the Brain *is* the ID Keycloak gives them. It also
specifies a separate table mapping identities to people. Those cannot both be load-bearing:
if the ID is the Keycloak one, the mapping table has nothing to do.

**Why it matters.** If a person's ID is the one Keycloak issued, then replacing Keycloak, or
migrating a client onto their own identity provider, rewrites every ID in the system, and
every audit row and every grant that references one.

**What I built:** the indirection. The Brain gives people its own IDs, and a table says which
external identity maps to which person. A token says which record to look up rather than
being the record.

**My recommendation:** keep the indirection and correct the architecture line. The cost is
one join. The alternative's cost is a migration nobody can do safely once there is audit
history.

**No action needed if you agree.**

**BUILT (2026-09-05).** The line is corrected in two places, because the wrong idea was
written twice. `docs/architecture.html` gave a principal's representation as "uuid from
Keycloak"; it now says the id is minted here and the provider's subject maps to it. The
comment on `PrincipalRow.id` claimed the id "arrives from the identity provider" while
giving `c_0447` as the example, which is not a Keycloak subject: that comment now states
the indirection and the migration it protects.

The code was already right and already proved right. `test_a_known_subject_resolves_to_the
_principal_the_directory_holds` uses a Keycloak-shaped uuid for the subject and `u_priya`
for the principal id, so an implementation that shortcut the lookup and returned the
subject fails that test today. Nothing to change beyond the two comments.

---

---

## 19. How long should somebody stay signed in? - CONFIRMED: 10 hours absolute, 30 minutes idle

**A number I picked, and nobody has confirmed.**

A session expires two ways. It ends after a period of no activity, and it ends absolutely
after a fixed time no matter how active somebody is, because a session that renews forever
is a permanent credential.

I set the absolute limit to **10 hours** and the idle limit to **30 minutes**. Ten hours
covers a working day with room, so almost nobody is signed out mid-task; thirty minutes
idle means a laptop left open in a cafe is not an open door for the afternoon.

**What it costs if it is wrong.** Too short and people re-authenticate several times a day,
which trains them to click through anything that asks. Too long and a stolen laptop is
useful for as long as the number says.

**What I need:** confirm 10 hours and 30 minutes, or give me two other numbers.

**One caution.** The absolute limit is written in two places: the code and the Keycloak realm
configuration. They have to stay in step, or people get logouts that look random. When you
change it, tell me rather than editing one of them.

**BUILT (2026-09-05).** That caution is now a gate rather than a request. Six tests in
`tests/unit/test_realm_config.py` read the realm export and the Python constants and refuse
to let them drift, and I broke each one to check it bites:

| What I changed | Caught by |
| --- | --- |
| Realm alone extended to a full day | the ten-hour agreement test |
| Realm alone doubles the idle window | the thirty-minute agreement test |
| Code alone extended to twelve hours | the ten-hour agreement test |
| Code alone relaxes idle to 45 minutes | the thirty-minute agreement test |
| Offline sessions lose their bound | the offline-session test |
| A client session set to outlive its sign-in | the client-session test |
| Token lifespan doubled to ten minutes | the effective-window test |
| Remember-me switched on with a week of its own | the remember-me test |

Three findings worth your time.

**The stated thirty minutes was never the true number.** A token minted just before somebody
walks away keeps working until it expires, so the real gap between the last action and the
last possible request is idle plus token lifespan: 35 minutes, not 30. That is a rounding
error and I have left it, but the test now bounds the *effective* window rather than the
token lifespan on its own.

**The existing token test did not catch a doubled token lifespan.** It caps the lifespan at
900 seconds, and 600 passes it. That ceiling alone would permit a fifty percent overshoot on
the idle policy. The two tests bound different things and neither implies the other.

**Offline sessions had one boolean between them and never expiring.**
`offlineSessionMaxLifespanEnabled` defaults to false, and false means an offline token
outlives the laptop it was issued to. It is set correctly and is now asserted.

---

---

## 17. Who holds the keys to the secrets vault? - DECIDED: five pieces, any three open it; both configurable, and the root token revoked

**Not a design question. A physical-custody question only you can answer, and it has to be
settled before the vault goes in rather than after.**

Connector credentials, provider keys and database passwords will live in a secrets vault
(OpenBao). It starts **sealed**: on every restart it is a locked box that cannot read its
own contents until somebody opens it with the unseal keys.

Those keys get split into several pieces, and a set number of pieces are needed to open it.
The point of splitting them is that no single person can open the vault alone, and no single
person losing their piece locks everyone out.

**What I need from you, three answers:**

1. **How many pieces, and how many needed to open?** My recommendation for a 126-person
   company with a small technical team: **five pieces, any three open it.** Three people
   have to agree, and you survive losing two.
2. **Who holds a piece?** Name five people. They should not all be reachable through the
   same laptop, the same phone or the same building. At least one should be someone who is
   never on call, so a piece exists outside the group that would be handling an incident.
3. **Where does the root token go after setup?** It can do anything, including undo every
   policy. Standard practice is to revoke it once normal access is configured, so nothing
   holds unlimited power permanently. I recommend revoking it.

**Why it cannot wait.** Everything about the vault is reversible except this. Deploy it,
put real credentials in, then decide custody, and you now have to re-key a live system while
it is holding the keys to your client data.

**What happens meanwhile:** I am building everything around the vault that does not need
it running, and the tasks that need real keys are already scheduled for go-live rather than
now. Nothing is blocked.

**BUILT (2026-09-05).** `src/brain/ops/vault_quorum.py` holds the split, and
`ops/openbao/UNSEAL.md` now derives its `bao operator init` command from that module rather
than repeating the numbers. Both directions of drift are tested: changing the module without
the runbook fails, and editing the runbook without the module fails.

**One disagreement with your wording, stated rather than quietly ignored.** You asked for the
setting to be "in the backend as well where we can select the options". It is a reviewed
constant in source, not a database row a screen can save, and here is why. The split is
fixed at `bao operator init`; changing it afterwards is `bao operator rekey` with three of
the current five people present. A save button would therefore report success for a change
that did not happen. Second, a row would put the policy governing the vault that holds the
database password inside that database, which makes it unreadable during exactly the
incident that needs it. A console screen can read and display this policy; what it cannot
honestly offer is a save button.

**Seven refusals at construction, and one of them is not in your list.** Beyond the
arithmetic (threshold above shares, of one, or equal to shares) and the holder count, the
policy refuses a list where every holder is on call. Your point 2 asked for at least one
holder outside the on-call group; that was prose, and it is now a refusal.

**A hole found in the duplicate-holder check, after it had been written and tested.** It
compared holder ids exactly, which is the right field and the wrong comparison: `r.jones`
beside `R.Jones` is one pair of hands and two strings, so five slots were accepted and a
declared three-of-five was really a two-of-four. Ids are now compared stripped and
case-folded.

**Root token: revoked, as recommended.** The rejected alternative is recorded in the module.
A sealed envelope protects the paper and not the token: it still bypasses every policy, the
audit device logs its use as an ordinary accessor with no field marking it root, and it was
already in the scrollback when init printed it. `bao operator generate-root` covers the
emergency, needs the same three people, and leaves a record.

**Still needs you, and it is not blocking anything.** The five holder slots read UNASSIGNED.
Naming them is one edit to a list in that module, and until it happens the setup command
exits non-zero rather than initialising a vault whose five pieces belong to nobody in
particular. Tell me five names and whether each is in the on-call rotation, and I will fill
them in; or fill them in yourself at the top of `vault_quorum.py`.

---

---

## 16. Two different things both mean "can approve", and nothing says which wins - DECIDED: the permission decides

**The plain problem: a person can look approved and not be, or be approved and not look it.**

There are two separate ways the system knows someone can sign something off:

1. **The Approver role**, which is a job title on the platform.
2. **An approve permission**, which is a specific right over specific things, like approving
   a payment for one department.

Right now those two do not talk to each other. Somebody can hold the Approver role and no
approve permission, in which case the role does nothing. Or hold an approve permission and
not the role, in which case the role is never consulted. Neither situation is an error, and
neither looks wrong on a screen.

**Why it matters:** whoever configures this will reasonably assume that giving someone the
Approver role lets them approve things. It does not, and nothing tells them.

**My recommendation:** the permission decides, always. The role is a label for the console
to filter on, not an authority. That matches the rule the rest of the system already
follows, that no role implies a permission, including Super Admin. What is missing is a
check that the two agree, so an Approver with no approve permission shows up as a
misconfiguration rather than a silent nothing.

**No action needed from you if you agree** with that, and I will add the consistency check.

---

---

## 15. How long should an emergency access session last? - DECIDED: 4 hours, set per grant

**The plain problem: someone needs to get into something urgently, out of hours, and we
need to let them without leaving the door open afterwards.**

"Break-glass" is the emergency override. Somebody with the right to use it opens a session,
gets access they would not normally have, and the system records it loudly and tells other
people it happened. It is for the 2am case where a client site is down and the one person
who can fix it does not have the access.

**It has to expire on its own**, because nobody remembers to close these. The specification
says "time-boxed" and never says how long.

**I chose four hours** and I want you to confirm it or change it. My reasoning: four hours
is one working session, so it covers a real incident; and a session opened at 11pm and
forgotten has expired before anyone starts work the next morning.

| Option | What it covers | What it costs |
|---|---|---|
| 1 hour | A quick fix | Someone mid-incident has to reopen it, and reopening becomes routine |
| **4 hours** (recommended) | A full incident, out of hours | Occasionally someone reopens once |
| 24 hours | Anything | It stops being an emergency and becomes an admin account with an awkward name |

**Just tell me a number.** Everything else about it is built.

---

---

## 14. An approval card can show the approver something they are not allowed to see - ACCEPTED: fix with the approval work

**Not a decision, a gap I am recording so it is not forgotten.**

When an agent wants to do something that needs sign-off, it renders a card showing what is
about to happen, and a person approves it. That card is currently built using the
permissions of the person who *asked*, not the person *approving*.

So if a junior asks for something, and a manager with narrower access to that particular
client approves it, the card can show the manager a value they would not be able to look up
themselves.

Nothing is broken yet, because approvals are not wired to a screen. It needs fixing before
they are, and it belongs with the approval work rather than here.

---

---

**FIXED (2026-09-06), not merely deferred.** The card-building code is written and this gap
is closed by its shape rather than by a check somebody has to remember.

The obvious design was the bug. `card_for(suspension)` rendering the suspended action's
artefact is exactly the leak: that artefact was built from what the *asker* could see and it
carries values. So the builder takes no suspension at all. It takes a body plus the
*approver's* own entitlements, and refuses unless the body was built at the approver's
reach. What survives of the original request is a suspension id and an action digest: two
identifiers, and no value from anybody's data.

Two further guards fell out of it. The card records who it was rendered for and refuses a
press from anybody else, which closes the same leak in the other direction: a card
forwarded to a colleague is inert. And a structural test pins the card's field list, so an
`artefact` field cannot quietly return later for a caller who wants a richer card.

I verified this myself rather than accepting the report: I broke the approver-reach
comparison and confirmed the named test fails.

**What is still true from the original note.** Approvals are still not wired to a screen, so
nothing was ever exposed. The difference is that when they are wired, the leak cannot be
reintroduced by writing the natural code.

---

**REOPENED 2026-10-06: the gap came back, and is being fixed again.** A check written on 2026-10-06
found that the approval screens built since then show the approver the requester's whole request,
values included: the console's Approvals card since 2026-09-09, and the Lark card since #258
(2026-09-30). The guard described above was still there and still passing, but the request travelled
in a free-form part of the card the guard did not look at, and the reach check compared a value the
caller asserted rather than one it worked out. Nobody was shown anything: agent actions do not reach
approvers on your install yet, and no sources are connected. The fix renders every approval at the
approver's own reach on both screens, shows locked any field the approver cannot read, and extends
the guard to the whole card, with a check on your install that proves it. Nothing for you to do.

## 13. Can a leash rule say "supervise everywhere except maintenance"? - DECIDED: strictest wins

**The plain problem: today it cannot, and the safe choice I made is probably not the one
you would expect.**

A leash decides whether an agent does something by itself, shows a person first, or only
pretends. You set it per agent, per thing it touches, per part of the business.

When two of your rules both apply to one action, something has to decide which wins. I made
**the stricter one win**, because that is how every other permission in this system behaves
and it fails safely.

**What that costs you.** You cannot write "this agent needs supervision everywhere, except
in maintenance where it can just get on with it". The company-wide rule wins and the
maintenance exception never applies. To get that behaviour you would write the narrow rules
one by one and leave the broad one off.

**The alternative** is most-specific-wins, which reads more naturally and is how most people
expect settings to work. The cost is real: a company-wide "supervise everything" rule could
then be cancelled by somebody adding a narrower row, and working out what an agent may
actually do stops being a lookup and becomes a question of which rule is more specific.

**My recommendation:** keep strictest-wins. It is the same rule as everywhere else in the
system, and "the safe setting cannot be quietly overridden" is worth more than the
convenience. If you want the exception style, say so now rather than after leashes are
configured, because changing it later silently loosens every rule already written.

---

---

## 12. The opaque escape hatch depends on a promise the redaction module cannot keep - DECIDED: the rule goes to the channel adapters (M10.1.5)

M4.1.6 allows a payload to skip redaction entirely, for genuinely untypeable data. It is
guarded three ways: it needs its own capability, it flags the trace, and the answer is
labelled as unredacted.

**The label is the part that protects the person reading it**, and the redaction module
cannot make it survive. It attaches a label to the payload; a channel adapter that simply
does not render that label reintroduces the whole risk, silently, and every test in M4 goes
on passing.

**My recommendation:** make it a rule in M16, where the channel adapters live, that a
payload carrying a label renders that label or refuses to send. That turns "the adapter
remembered" into "the adapter cannot forget".

**No decision needed if you agree** - I will write it into M16 when I get there. It is here
because it is the kind of dependency that gets lost between two modules, and the failure is
invisible from either side.

---

---

## 11. A hidden count can still be worked out by subtraction - DECIDED: add the policy column

**This is a hole in a rule we already promise**, so it needs an owner rather than a
preference.

The system must never tell anyone how many things it hid from them. "3 results hidden" is
precisely the fact a person is not entitled to. The redaction walker enforces that
strictly: no placeholder, no null, no shortened list carrying its old length.

**But a count can survive as an ordinary field.** Imagine a client record showing
`ticket_count: 40` beside a list of tickets, where the asker may only see the 12 in their
own department. The list arrives correctly filtered to 12. The count says 40. The asker
subtracts and knows there are 28 tickets they cannot see, which is the number we said we
would never tell them.

Nothing inside the walker can catch this. It sees two fields, both legitimately visible on
their own, and cannot know that one counts the other.

**My recommendation:** a rule in the field policy rather than in code. A field that counts
a collection is marked as counting it, and becomes invisible whenever that collection is
filtered for this asker. It costs one column in the policy and a check at mask time.

**The alternative** is to accept it, on the grounds that the asker learns a number and not
a record. I do not think that holds: the whole point of the rule is that the number itself
is the disclosure, and a person who can see "28 hidden" for every client can map the shape
of the business without reading a single record they are not entitled to.

**What I need from you:** agreement that this is worth the column, and I will add the task.
It is roughly a day, and it is much cheaper now than after connectors start defining
projections.

---

---

## 10. What happens when even the largest model runs out of room? - DECIDED: trim retrieval and retry

**The gap.** Tier escalation is defined as upward only: a request too large for `small`
moves to `main`, and one too large for `main` moves to `heavy`. The specification never says
what happens when `heavy` overflows too.

**Why I did not just pick one.** The three plausible answers have very different
consequences for the person asking:

| Option | What the person gets | The problem with it |
|---|---|---|
| Truncate the context | An answer | An answer built on silently dropped evidence, which is the failure mode the whole design exists to prevent |
| Refuse | "That question is too large" | Honest, but a dead end with no path forward |
| Trim retrieval and retry | An answer, from fewer sources, and told so | More work, and it belongs in retrieval rather than routing |

**My recommendation:** the third. The real fix is upstream - if a question needs more
context than the largest model has, retrieval gathered too much, and routing is the wrong
layer to paper over it.

**For now** the classifier surfaces `context_overflows` as a fact rather than acting on it,
so nothing silently truncates. Something has to own the path before M8 ships.

---

---

## 9. Should a refusal make the system try a different AI model? - DECIDED: no

**The plain problem: if one AI says "I will not answer that", should we keep asking other
AIs until one says yes?**

The system uses several AI models. When one fails, it automatically tries the next. The
reasons to try the next one are all versions of *"this model is unwell right now"*: it did
not respond, it timed out, it was overloaded, it crashed.

The original design listed one more reason: **the model refused on its own content rules.**
I deliberately left that one out, and this is the one place the code knowingly departs from
the design document.

**Why. Two reasons.**

**First, it usually just wastes the person's time.** A refusal is not about the model being
unwell, it is about the question. So the next model refuses too, and the next. The person
waits three times as long for the same no.

**Second, and this is the real issue: when a different model does say yes, what actually
happened is that the system shopped around until something agreed.**

A concrete example. Someone asks the system to draft a letter about a staff member that
touches on their medical leave. Model A declines. If we automatically try B, then C, then D,
the answer your company gives depends on which AI happened to be running well that
afternoon. Same question on Tuesday and Thursday, different answers, and nobody can explain
why.

That is the same problem the design already rejects elsewhere: never retry simply because
you did not like the answer.

**What happens instead in my version:** the system says "I will not answer that", once,
honestly, and it is recorded.

**Decided 5 September: keep it excluded.** The architecture's routing table now says so outright rather than carrying an open question, and a refusal goes to the abstention path in M8 to be answered once and honestly.

---

---

## 8. Where does the audit anchor live? - DECIDED: a private GitHub repo

**The plain problem: someone could delete the last few days of the security log and nothing
would notice.**

The audit log records who gave whom access to what, and who looked at what. It is the thing
you would hand a client or a regulator to prove the system behaved.

It is built so **old entries cannot be edited**. Think of a receipt book where every page
writes down a summary of the page before it. Tear out page 50 and page 51 no longer matches,
so the tampering is obvious.

**But you can still tear off the last few pages.** If someone deletes the newest twenty
entries, everything remaining still matches perfectly. The book has no idea how long it was
meant to be. And the newest entries are exactly the ones someone covering their tracks would
want gone.

**The fix is simple.** Every so often, write down "we are up to entry 1,240" somewhere the
person who administers the database cannot reach. Later, if the log only goes up to 1,220,
you know twenty entries went missing. Without that note, there is no way to tell.

**What you are deciding: where that note gets written.**

| Where | Cost | What it protects against |
|---|---|---|
| **A second server you already own** (recommended to start) | Nothing | Someone who compromises the app or the database |
| A write-once cloud storage bucket | A few dollars a month | The above, plus a rogue administrator, plus you |
| A public timestamping service | Free | The above, plus arguments about *when* something happened |

**My recommendation:** start with the second server, because you already have one and it
costs nothing. Move to write-once storage before signing any client contract that makes a
promise about audit records.

**Where this stands today:** the log can prove nobody edited it. It cannot prove nobody
deleted the recent part. The code for checking against a note is already written and tested;
what does not exist is the place to keep the note.

---

---

## 7. The audit view will want to show a capability, and the ledger redacts it - DECIDED: capabilities allowed in the ledger

**The conflict.** The ledger's redaction rule is an allowlist: a value survives only if it
is a field name, a list of field names, a digest, or a boolean. A capability string like
`read:client.name` does not pass, so it is redacted.

But M24.1.5 is the client-visible audit view, and that screen will almost certainly want to
render "Aaron granted Wei Ling `read:client.name` on 4 September". Today the ledger cannot
tell it that.

**Why the ledger is strict.** It proves *that the reach changed*; the grant table says
*what the reach now is*. Splitting them means a leaked ledger export does not also hand
over the permission map.

**My recommendation:** allow capability strings in the ledger. They are not personal data,
they are already in the grant table, and an audit view that cannot say what was granted is
not an audit view. I would add them to the allowlist as a named exception rather than
loosening the rule generally.

**Decide before M24.1.5 is built**, not after. Retrofitting means either a migration over
the ledger or a screen that reads two sources and hopes they agree.

---

---

## 6. The audit ledger cannot record before-and-after values - DECIDED: field names only

**The conflict.** M24.1.4 asks the ledger to record "actor, timestamp, before and after
state, reason". But before-and-after state *is* field values, and the architecture says
values never enter the ledger. Both cannot hold.

**What I built.** Changed field *names* only. The entry says "Aaron changed
`hosting_expiry` and `status` on client 447", not what they changed them to.

I considered hashing the values instead and rejected it. A five-digit salary has about
90,000 possible values, so its hash is a lookup table away from being the salary itself.
A hash of a low-entropy value is not a redaction.

**What this costs you.** An auditor asking "what was the value before Aaron changed it"
cannot be answered from the ledger. It can be answered from the source system's own
history, if that system keeps one.

**My recommendation:** accept field names only, and reword M24.1.4. The ledger's job is to
prove *who* and *when* and *that something changed*. Making it also the value archive turns
the longest-retained table in the system into the most sensitive one.

**If you disagree**, the alternative is a separate value-history table with its own
retention and its own access rules, which is real work and belongs in M25, not M24.

---

---

## 5. Coolify's stale compose - LEFT AS IS, as you asked

Three changes remain unapplied there: the `migrate` service removed, PgBouncer added, and
`BRAIN_COMMIT_SHA` dropped.

The consequences while it stays stale, so they are not a surprise later:

| What happens | Why it does not matter yet |
|---|---|
| A `migrate` container is created on every deploy | Exits 0. The app migrates itself under an advisory lock |
| The app talks to Postgres directly | No connection pooling. Fine at this scale, and the code is ready for the pooler |
| `/health/ready` reports `commit: unknown` | The image knows its own commit; the stale compose overrides it |

None of it blocks anything. The current file is `docker-compose.yml` in the repo whenever
you want to paste it across.

---

## 4. Automatic deploys - NOW GENUINELY ON

You said "I see you have done this as well". It was not done, and it is worth being precise
about why it looked done: the Deploy workflow's Coolify step printed `secrets not set` and
exited **0** by design, so a missing secret would not resemble a broken pipeline. Every
deploy until today was me running `ops/deploy.sh` by hand. A green run looked like a ship.

**It is automatic now.** A systemd timer on the VPS checks the registry every three minutes
and deploys when the published image changes.

Pulled rather than pushed, deliberately: every other route gives something outside the
server a way in - a Coolify token over plain HTTP, or an SSH key held by GitHub. This way
nothing new reaches the box and no credential leaves it.

It compares the digest the registry serves against what the container is running. Comparing
tags is useless, since `:latest` always equals `:latest`, and comparing build times trusts
a clock.

**cosign is installed and the signature is verified before the container starts** - a
signature checked after the thing is live is checked too late. Verified by hand: the
certificate binds the running image to
`.github/workflows/deploy.yml@refs/heads/main` in your repository.

History: `ssh <your server> journalctl -u brain-deploy -n 50`

---

---

## 3. Langfuse - no action, and a correction

You said to go ahead and install it. **It is already installed and running** on the box:
`verz-langfuse-server` and `verz-langfuse-db`, up several days. My note was not asking
whether to install it; it was flagging that it runs well under its documented minimum of
11 vCPU and 25.5 GiB, on a box with 11.7 GiB in total.

You are right that this is fine at your traffic. Nothing to do.

Connecting *our* system to it is separate work and belongs in **M27**, wave 3, with the
rest of observability. It is in the plan already.

---

---

## 2. AnyGen - DECIDED: replace

M37 now carries a second migration. **29 tasks, finish moves 6 Oct to 7 Oct.** One day to
replace an entire second system.

- **The twelve house skills come across, not rewritten.** `verz-master-theme`,
  `verz-doc-letterhead`, `seo-audit`, `website-cro-audit` go first - in daily use, and the
  real test of whether import works at all.
- **Agents are rebuilt.** AnyGen has no ceiling and no leash, so there is nothing to carry
  over; each starts at Shadow on writes regardless of how it behaved there.
- **Their adaptive learning does not transfer.** One toggle over an opaque store has no
  honest mapping onto four tiers with a review queue. Memory files are read as evidence and
  tier-one preferences re-derived; anything widening a scope is discarded.
- **Decommissioning a SaaS is not decommissioning a server.** Cancelling the subscription
  does not revoke the OAuth grants it holds on Gmail, Drive, Calendar, Sheets and Docs.
  Access ends with billing, so exports are verified restorable first.

---

---

## 1. Coolify on plain HTTP - FIXED

You said leave it, but fix it if I could. I could.

**The panel is now on its own subdomain** with a real Let's Encrypt
certificate, valid to 3 December. **Plain HTTP on port 8000 is closed.**

I was wrong about something here, and being wrong changed the answer. I had told you
sslip.io could not get a real certificate, having tested one of your apps and found
Traefik's self-signed default. That app was simply configured for `http://`;
This deployment's own address has had a genuine Let's Encrypt certificate all along. No
domain purchase was needed after all.

Two details worth keeping:

- **`ufw deny 8000` would have done nothing.** Docker publishes the port to `0.0.0.0` and
  inserts its own iptables rules ahead of ufw, so the packet never reaches ufw. The block
  lives in the `DOCKER-USER` chain, which Docker leaves alone for exactly this.
- **The rule survives a reboot** via a small systemd unit. Worth knowing: the pre-existing
  block on port 5003, belonging to your other project, does **not** - nothing persists it,
  so it disappears on the next restart. That is yours to decide about; I left it alone
  rather than quietly managing another project's firewall.

The ufw rule I removed was labelled `TEMPORARY - Coolify UI, close when GitHub source is
connected`, so this was always the intent.

To reopen the plain port if you ever need it:
`iptables -D DOCKER-USER -p tcp -m conntrack --ctorigdstport 8000 -j DROP`

Everything is in `ops/vps/`.

---

---

