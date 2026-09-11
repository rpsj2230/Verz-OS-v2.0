# Needs Rupash

Decisions and access I cannot resolve alone. Served at `/build/needs-rupash`.

**5 items are open, and every one is an action of yours rather than work of mine.** That is
new. You answered twenty items over 2026-09-09 and 2026-09-10 and every answer has been built,
verified by mutation and pushed, so nothing on this page is waiting on a decision any more.
What is left is five things only you can do, and none of them is urgent.

**Four are one action each and all four are settings pages or a terminal.**

Item 42: the three deploy secrets exist on the repository and arrive empty, so they were saved
with empty values. Click **Update** on each of the three and re-paste. Two of the values are in
the item; only the token needs finding.

Item 49: the service identifier on your server holds the wrong value, because this page told
you to copy it from an address bar that carries three of them. One command, and the corrected
one reads the value off the server rather than having it typed in.

Item 52: two workflow files carry your server's address. One repository variable and I remove
them.

Item 51: every container defaults to the `latest` image, so an install that pins nothing is not
pinned. Three numbered steps and the first changes nothing about what runs.

**One is two pieces of housekeeping inside your identity provider.** Item 32: Keycloak is up,
healthy and signed into. A temporary account should be deleted and one password rotated. I hold
no credentials for it and should not.

**What the page looks like underneath.** Nineteen items have been answered and closed, and the
answered section keeps each decision as it was made rather than as the code turned out, with a
note appended where the facts have since moved. Two of them, 53 and 54, are the record of this
machine's Application Control policy blocking four different things over three days, and of
what fixes it, because the same policy will refuse the next unsigned binary anything installs.

# Open

## 52. Two workflow files carry your server's address, and one repository variable removes them

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


## 51. Every container defaults to `latest`, and the fix stops your automatic deploy until you set one value

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

## 49. The service identifier on your server is written, and the value in it is the wrong one

**One command, and it corrects a value my own instructions sent you to the wrong place for.**

```
ssh <your server> "docker ps --format '{{.Names}}' | sed -n 's/^app-//p' \
  | head -1 > /root/.coolify-service-uuid"
```

Then, to see it took:

```
ssh <your server> "u=\$(cat /root/.coolify-service-uuid); echo \"\$u\"; \
  test -d /data/coolify/services/\"\$u\" && echo 'that service exists' || echo WRONG"
```

**What went wrong.** This item used to tell you to copy the identifier out of Coolify's address
bar. That address holds several identifiers, one for the project, one for the environment and
one for the service, and the one you copied was not the service. Measured on your own server
on 2026-09-09: `/data/coolify/services/` holds two directories, the Brain stack and
Keycloak, and the value in the file matched neither. `docker ps` names the application
and database containers after the right one, with `app-` and `db-` in front, which is
the same identifier a second way and is what the command above reads.

**Why the wrong value is worse than an empty file.** `brain-deploy` builds
`/data/coolify/services/$UUID` and `app-$UUID` from it. With a wrong identifier the directory
does not exist and `docker inspect` prints nothing and exits non-zero, which every branch in
that script reads as "not running yet". An empty file makes it refuse and say so; a wrong one
makes it look like it is working.

**Nothing is broken today.** The scripts running on the server are the copies installed in
August with the old value compiled in, so deploys keep working exactly as they do now. The file
only starts being read when somebody reinstalls them.

**And the instruction is fixed rather than only the value.** The reliable source is the server
itself, not the browser: `ls /data/coolify/services` names the directories and
`docker ps --format '{{.Names}}' | grep '^app-'` prints the same identifier with `app-` in
front. Coolify's address bar is where I sent you and it is the one place that is ambiguous.

**And the same value belongs in GitHub.** `COOLIFY_SERVICE_UUID` should be
the same value; item 42 says where to paste it and this item says where to read it.

## 42. The three deploy secrets were saved empty, and re-entering them is the whole fix

**What you do, and it is three fields on one page.**

1. Go to `https://github.com/rpsj2230/Verz-OS-v2.0/settings/secrets/actions`.
2. Click **Update** beside `COOLIFY_URL` and paste your Coolify panel's address. It is
   the one you open the panel with, port and all, and `docker ps` on the server prints
   the same host if you would rather read it there than type it from memory.
3. Click **Update** beside `COOLIFY_SERVICE_UUID` and paste your service identifier. Read
   it off the server rather than out of Coolify's address bar, which carries three
   different identifiers and is where this page used to send you: item 49 has the one
   command that prints it, and the story of why the value you wrote first was wrong.
4. Click **Update** beside `COOLIFY_TOKEN` and paste a Coolify API token. If you no longer have
   the one from September, make a new one: in Coolify, your avatar, **Keys & Tokens**, **API
   tokens**, create one with permission to deploy, and copy it when it is shown because it is
   shown once. I do not create or hold tokens on your behalf.

The next push then calls Coolify directly and the warning stops.

**How this is known rather than guessed.** The run at 10:22 on 2026-09-09 printed, before
deciding anything:

```
what this job can see:
  secrets.COOLIFY_URL: empty
  secrets.COOLIFY_TOKEN: empty
  secrets.COOLIFY_SERVICE_UUID: empty
  vars.COOLIFY_URL: empty
  vars.COOLIFY_SERVICE_UUID: empty
```

All three exist on the repository, created 2026-09-04 at 12:12:44, :45 and :46, one second
apart. They deliver empty strings, no repository variables exist to have caught the values
instead, the repository is not a fork, it declares no deployment environments, and the workflow
file that ran is the one on `main`. A secret that exists and is empty is the only reading left,
and GitHub's API accepts an empty value without complaint even though the web form does not.
Three timestamps a second apart look like a script that set them from environment variables
that were not themselves set.

**You were right to push back on this item.** It used to say the secrets were missing and ask
you to create them. You had created them, five days earlier.

**Nothing is broken while this is open.** The timer on your server checks for a new image every
two minutes and picks up every build, which is why deploys have been working the whole time.

**A second fault was hiding behind the first**, and it is fixed. The missing-secret check was
three lines shaped `[ -z "$X" ] && missing="$missing X"`, and every `run:` block in GitHub
Actions is `bash -eo pipefail`. A whole `&&` list is the command whose exit status `-e` reads,
so the first line where the value was present would exit 1 and kill the step before it called
Coolify. It never fired, because all three have always been empty. It would have fired on the
first run after you fixed the secrets: a check that breaks at the moment it starts to matter,
invisible for as long as the fault it sits behind is there.

## 32. Two pieces of Keycloak housekeeping, and nothing is blocked by either

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

# Answered

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
right. The plan named eighteen and the code had four. It is now thirty-four, declared in
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

