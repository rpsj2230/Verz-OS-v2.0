# Deploying to the VPS

Laptop → GitHub → GHCR, and the VPS pulls from GHCR.

**The server deploys itself, and that is the only automatic deploy there is.** A systemd timer on
the server checks the registry every two minutes and installs a new image when `:latest` moves.
Nothing outside the server tells it to deploy.

## Why the server pulls

Two reasons, and either would be enough.

- **No inbound access to the server.** A deploy is a connection the server opens to the registry,
  never one something else opens to the server. The deployment panel's port stays firewalled, and
  nothing about deploying asks for an address range to be let in. The ports that are open, 80 and
  443 for the people using the system and 22 for its administrators, are open for those reasons and
  would be open without deploys.
- **No deployment secrets in GitHub.** A token that can redeploy every container on the host is not
  stored in a repository's settings, where every workflow and every administrator of the repository
  can reach it.

**And the CI gate is kept.** `:latest` is moved only by the `Deploy` workflow's build job, which
runs only when CI succeeded, so the tag moving is the statement that the tests passed.

Until 2026-09-15 the workflow also had a step calling the panel's deploy API with three repository
secrets, `COOLIFY_URL`, `COOLIFY_SERVICE_UUID` and `COOLIFY_TOKEN`. They were empty on every run,
the panel is not reachable from GitHub, and every deploy that ever happened came through the timer,
so the step was removed. The three secrets are read by nothing now and can be deleted from the
repository's settings.

## What already works

Every push to `main` runs CI. If CI passes, `Deploy` builds the image and pushes it to
`ghcr.io/rpsj2230/verz-brain-v2.0`, tagged with the short commit SHA and `latest`, and signs
it. Its second job then waits up to eight minutes for the live site's `/api/status.json` to
report that commit, and **fails if it does not**, because a published image nobody pulled is
not a deploy.

Verified 2026-09-04: `ghcr.io/rpsj2230/verz-brain-v2.0:6593cf3`,
digest `sha256:131e228179c16705a9cb6c31fc15ef05a18bed91f892d0d3048e5e3d278d5f53`.

## What CI costs per merge, and why main does not reuse a pull request's result

A merge is checked twice: by the pull request's run and by the run on `main` that gates the
deploy. Measured on 2026-10-14 (GitHub's free plan runs 20 jobs at a time):

| Run | Jobs | Job-minutes | Wall clock |
| --- | --- | --- | --- |
| Pull request, task list only | 4 | about 1 | under 1 minute |
| Pull request, unit tests selected by the diff | 21 | 56 | 12 minutes |
| Pull request, whole suite (a workflow, fixture or lock file changed) | 21 to 24 | 127 to 222 | 45 to 50 minutes, queued |
| `main`, a code change | 8 | about 12 | 7 to 15 minutes, 31 to 63 on busy days when jobs queued |
| `main`, task list only | 2 | under 1 | under 1 minute |

The eight shards are 63% of a selected pull request run and 80% of a full one. `main` already
runs none of them: since 2026-09-28 it runs only the gates a deploy depends on (lint and types,
the sweeps, the install from empty, the migrations over an install-shaped database, the previous
release on the new schema, the whole stack and the tracker). So the work a merge repeats is
those eight jobs, about 12 job-minutes, which is a fifth of a selected pull request run and a
twentieth of a full one. Test selection, the nightly suite and the path filters already cut the
rest, and the pull request run is the cost worth looking at next, not main's.

**Options measured for the part that is left, and what was done with each.**

- **Reuse the pull request's result when the merged tree is identical (rejected).** Sound for
  the tree and not for the two other things `main`'s gates read. `previous_release` tests the
  build before this change, which is the pull request's base on a pull request and the push's
  `before` on `main`, so a tree match with a different base is a different test. `sweeps` and
  `docs` read the `Closes:` trailers of the squash commit's own message, which the pull request
  never saw. And the branch protection does not require a branch to be up to date (`strict:
  false`), so only 10 of the last 60 merges (17%) squashed to the tree their pull request ran,
  fewer once the base must match too. A fail-closed version would skip one job in six merges, keep
  the history-reading jobs anyway, and add a lookup in the one path that gates the server.
- **Cancel the running CI on `main` when a newer merge arrives (rejected).** `main` already
  collapses a burst: GitHub keeps one run going and only the newest waiting, and 8 of the last 30
  runs on `main` were such replaced runs (each cancelled with no job started). Cancelling the running one as well saves about ten
  job-minutes per burst and risks starving the deploy for as long as merges arrive closer
  together than a run is long, which left nothing deployed on 2026-09-28. Pull request branches
  already cancel a superseded run.
- **Skip work for task-list-only and docs-only commits (already there).** `Kind of change` skips
  every product suite for a task-list diff, and `brain.ops.ci_paths` skips four pull-request-only
  jobs by path.
- **Serialise the publish (done).** The one real hazard found while measuring. See below.

**Which commit is deployed when runs overlap.** CI runs on `main` queue in order and the newest
is never cancelled, so the newest commit's CI always runs. Each green run starts a `Deploy` of its
own commit and the server deploys whatever `:latest` points at. Until 2026-10-14 nothing ordered
those builds, so a code commit followed by a task-list commit (whose CI takes under a minute)
started two builds together and `:latest` ended on whichever finished last. The build job is now
in one concurrency group that never cancels a running build: GitHub keeps the build that is
publishing, replaces any waiting one with the newer, and runs that next. A burst of merges
publishes the commit that was already building and then `main`'s tip, which is deployed last.
The ones between show as cancelled in the Actions list before they built anything.
`tests/unit/test_ci_duplicate_work.py` holds it. What it does not cover: two `Deploy` runs created
out of order by GitHub, which the minutes between CI completions make unlikely, and the
staging-check job of a superseded commit, which waits ten minutes for a verdict the newer
deploy has overwritten and fails (seen on 2026-10-13); that is the check's design and is left as
it is.

## The target box

**Every value in this runbook that names a machine is a placeholder**, written as
`<deploy-host>`, `<deploy-uuid>` and `<deploy-url>`. They are the three variables in
`.env.example`, and `ops/deploy.sh` refuses to run until they are set rather than falling
back to any of them. This file named one deployment's server until 2026-09-09, which is a
runbook telling the next administrator to open somebody else's panel and paste their token
into it.

- `<deploy-host>` the ssh destination, as spelled in `~/.ssh/config`
- `<deploy-uuid>` the Coolify service identifier, the last path segment of that resource's URL
- `<deploy-url>` the address this deployment answers on, with its scheme

The box this was measured on at the time: Docker 29.7.2, 11.7 GiB RAM, 86 GiB free disk.

**It may be shared, and this one was.** At last check it ran 29 containers using about
4.5 GiB, including Coolify itself, a Dify stack, Langfuse, Activepieces, and an unrelated
Coolify project. Anything already on the box is live and must not be touched.

Two consequences, already handled in `docker-compose.yml`:

- Every service declares an explicit memory limit. Without one, a runaway query here
  could take down someone else's production on the same host.
- Postgres is on `expose`, not `ports`. Nothing outside this compose project reaches the
  database, which matters more than usual on a box with no firewall.

Budget for this stack: about **3.8 GiB** (app 1 GiB, Postgres 2 GiB, cache 0.5 GiB,
migrate 0.25 GiB one-shot). That leaves roughly 3 GiB headroom. Adding OpenBao, a worker
and the browser sandbox later will need a hard look at what else the box is running -
Langfuse alone documents a 25.5 GiB minimum, so it does not belong on this host.

## Steps

### 1. Give Coolify a GHCR credential

The package is private because the repo is private, so Coolify cannot pull it anonymously.

Create a classic PAT on the `rpsj2230` account with **`read:packages`** only, then in
Coolify: **Keys & Tokens → Docker Registries → Add**, registry `ghcr.io`, username
`rpsj2230`, password the PAT.

### 2. Create the project

In Coolify: **Projects → + New**, and give it a name of its own. Do not add resources to a
project that is already there; those belong to something else that is live.

Inside the new project add a **Docker Compose** resource, source this repository, compose
file `docker-compose.yml`.

### 3. Set the environment

On the resource, set:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | generate one; Coolify can do this |
| `APP_IMAGE` | `ghcr.io/rpsj2230/verz-brain-v2.0:latest` (required: the compose file has no default and refuses to deploy without it) |
| `BRAIN_ENV` | `production` |
| `BRAIN_COMMIT_SHA` | leave to the pipeline |

Set the health check path to `/health/ready`. **Not `/health/live`** - liveness only says
the process is running. A container that is up but cannot reach the database still answers
questions, from whatever it can still reach, which is how this system would start
returning wrong answers while appearing healthy.

### 4. Install the pull timer

On the server, as root, once:

1. Copy `ops/deploy/brain-autodeploy` and `ops/deploy/brain-deploy` to `/usr/local/bin/` and
   make both executable.
2. Write `<deploy-uuid>` into `/root/.coolify-service-uuid`. Both scripts refuse without it
   rather than guessing which containers are this deployment's.
3. Run `/usr/local/bin/brain-install-autodeploy`, copied from `ops/deploy/` the same way. It
   writes `brain-autodeploy.service` and `brain-autodeploy.timer` and switches the timer on.

After that, every merge to `main` that passes CI is live within a few minutes, and the
`Deploy` workflow goes red if it is not. `journalctl -u brain-autodeploy.service -n 50` is
the history, and `/var/lib/brain-deploy/heartbeat.json` says what the last check decided.

**The worker is not restarted by a merge that changes nothing it runs.** The application is
recreated by every deploy, because it serves the console and the build documents out of its
image. The worker is recreated only when the image it would move to has a different
`worker_fingerprint` in its `RELEASE.json` from the image it is running: a hash of every committed
file except those under `docs/`, `tests/`, `console/`, `e2e/`, `matcher/` and `.github/`
(`brain.ops.restart_scope`). So a merge of documents, tests, the console's source or workflows
leaves an acceptance run in progress alone. Any doubt (an image from before the fingerprint
existed, one that cannot be opened) restarts it as before, and the journal says which services
were left running (`services left running:`). To restart everything anyway, for instance to give
the worker newer documents, run `BRAIN_DEPLOY_RECREATE_ALL=1 /usr/local/bin/brain-deploy` once.
The first deploy after this ships restarts the worker once, because the image it is running has no
fingerprint to compare.

`brain-deploy` prefers to ask Coolify to deploy, on `127.0.0.1` with a token in
`/root/.coolify-deploy-token`, so the panel's own record stays true; with no token it
recreates the app with compose from Coolify's own directory. Either way the call is made on
the server, to the server.

**By hand, when you need one now.** `make deploy` runs `ops/deploy.sh` from a machine with
ssh access to the server. It uses the administrative SSH access that is already open, and
nothing automatic depends on it.

## This is not how a client is given the system

Everything above is one deployment of this product, deployed from `main` on every push. A
client is given a tag: an archive they fetch and an image their compose file pins, both
published by the `Release` workflow and neither produced by anything on this page. See
[RELEASE.md](RELEASE.md) for how a tag is cut, what it produces, how both artefacts are proved
to exist from a machine that has never seen this repository, and the two publication settings
that still stop a client install from working.

## What a normal pull request no longer proves

Decided by the owner on 2026-10-14 (the CI speed-up list, item 2), after measuring that a pull
request which fell back to the whole suite cost 127 to 222 job-minutes and 45 to 50 minutes of
wall clock, against 56 and 12 for one running only the files its diff reaches, on a plan that runs
20 jobs at a time. Nine of them queued at once took over an hour each.

**What changed.** The unit shards (`brain.ops.test_plan`, `brain.ops.test_selection`) used to run
the whole suite on a pull request when the diff touched shared test infrastructure: a `conftest.py`,
anything under `tests/fixtures`, a helper module under `tests/`, a workflow file, or the planner's
own code. They no longer do. Those are selected by what reads them:

| The diff touches | What a normal pull request now runs |
| --- | --- |
| a fixture or a helper module under `tests/` | the tests that import it, directly or through another fixture, read by text to a fixed point |
| a `conftest.py` or `__init__.py` | every test beneath its directory (a root one, which reaches everything, runs everything) |
| a workflow file | the tests that name `.github`, and the tests that walk the tree |
| the planner (`brain.ops.test_plan`, `test_selection`, `test_shards`, `guards`) | the tests that import it, as for any source module |
| `pyproject.toml` or `uv.lock` | **the whole suite, as before**: every test runs on the dependencies |
| a deleted source module, no base commit, a diff git cannot compute, a planner error | **the whole suite, as before**: the selection cannot say what it reaches |

Lint, types, the invariants and everything `main` runs are unchanged. `main`'s gates, the
`CI` workflow's triggers (a push to `main` and a pull request, with no manual dispatch) and the
trigger of `Deploy` (the `CI` workflow completing on `main`) are not touched, and
`tests/unit/test_test_selection.py` pins all three by parsing the workflows.

**What a normal pull request therefore does not prove.** That no test outside its selection is
broken by it. A change to a shared fixture is checked against the tests that import it by name; a
test that reaches a fixture some way the text does not show (a fixture named in a string, an
import built at run time) is not selected, and a workflow change is checked only by the tests that
read workflows. A merge of such a pull request reaches `main`, passes `main`'s eight gates, and
deploys. If it broke an unselected test, the first run to say so is the nightly suite, up to a day
later, and a red nightly does not un-deploy anything.

**Where the whole suite runs instead.**

1. **A merge train**: a pull request whose head branch starts with `train/`. `CI` sets
   `WHOLE_SUITE` from the branch name alone (`startsWith(github.head_ref, 'train/')`; no label and
   no comment can set it) and each shard plans its full share, so the coverage floor is held on
   it too. `ops/dev/assemble_train.py` makes one from a list of pull request numbers (see
   `ops/dev/README.md`): it merges each pull request into one branch with a merge commit, never a
   squash, refuses duplicate or gapped migration numbers, and opens the pull request with
   auto-merge off. A train is merged with a merge commit, so each original commit and its
   `Closes:` and `Proved-on-install:` lines reach `main`.
2. **Every night** at 01:41 UTC (`nightly-suite.yml`), against `main`, with the coverage floor.
3. **On demand**: the same workflow has `workflow_dispatch`, so `gh workflow run "Nightly suite"
   --ref <branch>` runs the whole suite on any branch, for instance before cutting a release.
   `CI` itself is deliberately not dispatchable: `Deploy` listens for `CI` on `main`, and a manual
   run there is a way to start a deploy by accident.

**Why that is acceptable, and what it is not.** The train and the nightly are the floor, and the
floor is real only if something uses it: **nothing forces an ordinary pull request through a
train**, so a pull request merged on its own relies on the nightly alone. The trade the owner
approved is that a rare late finding of a broken unselected test is cheaper than an hour of queue
on every pull request that touched a fixture. The way to narrow it without giving it back is to
batch pull requests that touch shared test infrastructure into a train, and to dispatch the
nightly suite before a release. A red nightly on a file a pull request did not select is the signal
to widen `brain.ops.test_selection`, not to trust it.

## What the unit shards cost, and how they are balanced

Measured on 2026-10-14 for the owner's priority that CI's wall clock is the roadblock. **A pull
request's wall clock is its slowest unit shard**, and over the last ten successful pull request
runs one shard in every run was far slower than the other seven (minutes, from the CI API, one row
per run; the slow shard was a different one in nearly every run):

| Run | Slowest shard | The other seven: median, range |
| --- | --- | --- |
| 38551283009 | 66 | 18, 15 to 23 |
| 38550419596 | 89 | 21, 13 to 23 |
| 38544768362 | 123 | 20, 12 to 44 |
| 38540690481 | 81 | 19, 17 to 25 |
| 38540026813 | 80 | 19, 13 to 25 |
| 38530768853 | 68 | 11, 6 to 23 |
| 38529837653 | 66 | 8, 4 to 17 |
| 38528623476 | 90 | 24, 14 to 40 |
| 38524660463 | 87 | 18, 16 to 32 |
| 38521443931 | 81 | 21, 12 to 26 |

**It started on the morning of 2026-10-14.** The thirteen successful pull request runs from
2026-10-13 13:49 UTC to 2026-10-14 01:59 UTC had a slowest shard of 11 to 42 minutes; all
twenty-three from 03:18 UTC on had one of 61 to 136. Between them `main` took #581 (2026-10-13
16:58 UTC), which added `gc.collect()` after every check in
`brain.ops.acceptance_run.run_suite`. The shard that took the hour was the one holding
`tests/unit/test_acceptance.py`, whose three tests that run the whole registry (573 checks, once,
twice and once) call it about 2,300 times in a process that has imported ninety test files and
records branch coverage. The log of shard 1 of run 38550419596 shows it: the first 3% of the
shard's tests done a minute in, the next 4% done 69 minutes later, and the remaining 93% in the 18
minutes after that.

**What was done, and what was left alone.**

1. **The file's tests no longer collect garbage.** An autouse fixture replaces only
   `acceptance_run`'s own name for `gc`; `tests/unit/test_acceptance_suite_memory.py` still holds
   that the product collects after every check, because that call fixed a real incident on an
   install and is right for the worker.
2. **The shards are balanced on recorded durations.** `ops/ci/test-timings.json` holds seconds per
   test file, `brain.ops.test_shards` and `brain.ops.test_plan` deal the files greedily by it, and a
   file with no record is weighed by its lines at the median rate the recorded files show (so a new
   file lands somewhere sensible, and no record at all is the old split). It was balanced by lines
   before, which cannot see a file that costs an hour.
3. **The three registry tests are units of their own** (`brain.ops.test_timings.CARVED_OUT`), so a
   shard that gets the rest of the file gets a `--deselect` for each carved test that runs
   elsewhere. Each makes a scratch database of its own, so they are independent. Slicing the
   registry across jobs is not possible: the roll-up checks read what earlier checks of the same
   run came to.
4. **The record is kept fresh from CI.** Every shard, here and in the nightly suite, uploads its
   JUnit report as `timing-shard-N`. To refresh after a nightly:
   `gh run download <nightly run id> -p 'timing-shard-*' -D /tmp/timings` then
   `uv run python -m brain.ops.test_timings refresh /tmp/timings`, and commit
   `ops/ci/test-timings.json`. The refresh names any file that alone outweighs a shard's even
   share (`OVERSIZED`), which no assignment can balance around, and
   `tests/unit/test_test_timings.py` holds the checked-in record to having none.

**What is measured, and what is not.** The coverage floor reads every shard's data exactly as
before, so no test was taken out of coverage and no gate was loosened. The check names are
unchanged: of the required checks only `Unit tests and coverage` is a unit-suite job (branch
protection on `main`, read on 2026-10-14), the shard jobs are not required by name, and nothing
here renames either. The selection is unchanged. What a recorded duration costs is that it is a
number from one run on one runner: a test that gets slower is found by the next refresh and not by
the next shard, and a refresh that finds a file above a shard's share is the cue to speed it up or
split it.

## What is generated, and where each file gets made

`docs/wbs.json`, `docs/tracker.html` and `docs/wave-windows.json` are generated from `docs/wbs/*.js`
and are **not committed** (2026-10-19). Committing them made every pull request that touched a task
conflict with every other one, in files nobody had edited by hand, and a conflicted pull request
gets no CI. A pull request changes the sources only and must not `git add` the three files; they
are in `.gitignore`. `docs/status.json` was already generated and ignored.

| Where | How the files get there |
| --- | --- |
| The unit shards, the invariants, coverage, the nightly suite, the pre-push hook | `tests/conftest.py` makes them before collection, in 0.2 seconds, from the sources in the checkout |
| `brain.ops.sweeps traceability` (CI sweeps job, pre-push) | makes them itself before reading the plan |
| The `Tracker matches the WBS` job | `python3 src/brain/ops/wbs_generate.py`, which fails with the scripts' own reason when a source is refused; warns if a pull request still tracks the files |
| The console job and the full-stack job | the same command, as a step before the console tests and before `docker build` |
| The image Deploy builds | `deploy.yml` runs `export.js` and `render.js` before the build, as it always did |
| A developer | `uv run python -m brain.ops.wbs_generate` |

A reader that finds a file missing says so in one sentence naming that command
(`GeneratedFileMissing`), so an absent plan never reads as an empty one. The mechanism, and the
designs rejected (a bot committing the output to main, and keeping the diff job), are in the
docstring of `src/brain/ops/wbs_generate.py`. The runners rely on the `node` that `ubuntu-latest`
ships; the files need nothing newer than Node 20.

A pull request branched before this change goes dirty when it merges, because main deleted files it
modified. Merge `origin/main`, run `git rm --cached -f docs/wbs.json docs/tracker.html
docs/wave-windows.json`, commit and push.

Still committed, each for a reason: `docs/console-audit/` is rendered by the console's own
toolchain from the live API schema and is already split one file per area; `docs/delivery-checklist.md`
changes only with `docs/wbs/acts.js` (once in the last 600 commits) and a test holds it to the
generator; `ops/install/install.sh`, `ops/update/*.sh`, `ops/openbao/apply-release.sh` and
`docker-compose.full.yml` are what a client install runs, so they have to be in the repository.

## Rollback

Images are tagged by commit SHA, so rolling back is redeploying an older tag - set
`APP_IMAGE` to `ghcr.io/rpsj2230/verz-brain-v2.0:<sha>` and redeploy. Nothing needs
rebuilding, and the SHA in `/health/ready` says exactly what is running.

## What is deliberately not automated

Creating the Coolify project and its tokens is a manual step on purpose. Both require
credentials on the account holder's own infrastructure, and a pipeline that could mint
them would be a pipeline that could also point production somewhere else.
