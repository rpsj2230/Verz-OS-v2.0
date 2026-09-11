# Working in this repository

Company Brain: a permission-aware layer over a company's own business data, single-tenant and
client-hosted. Read this before writing anything here.

This file was written late, on 2026-09-05, after an agent pointed out that it did not exist
and that every convention below was being restated by hand in each briefing. Everything in it
is described from what the code already does, not from what would be nice. If you find the
code disagreeing with this file, the code is the fact and this file is the bug.

---

## This repository is the template, not one company's system

**Nothing here is being built for Verz Design.** This repository is the product, and Verz will
be the first company to install it: their system is created by running the installer on their
own server, never by copying this development environment. Every company after them installs
the same product on their own server, with their own database, and owns it outright. Nobody
operates it on their behalf.

Three rules follow, and they apply to every line written here.

**No company's details go into the source, ever.** Not a company name, not a domain, not a
work address, not an API key, not a storage path, not an internal identifier. There is no
later step that strips them out: a value that has to be removed at the end is a value that
should never have been committed, and by then it is also in the git history. `M41.1` is the
sweep that refuses one, and it is meant to be green from the first commit rather than fixed
before a release.

**Anything that differs between companies is configuration, and configuration is read in one
place.** Company name, branding, domain, identity provider, model choice, storage location,
which connectors are enabled. These are values a person sets during setup, not constants in a
module. Nothing reads the environment directly.

**When something cannot be configured, that is a defect in the extension points.** The answer
is never a branch for one company or a copy of this repository. `M29` holds the plugin
interfaces; a company-specific connector is a plugin, and a genuinely new feature goes into
this repository behind a flag and ships to everyone switched off.

The test to apply while writing: **would this line still be correct on a server belonging to a
company nobody here has met?** If not, it is configuration and belongs in the setup wizard.

---

## The one invariant everything else serves

```
E_run(caller, agent) = E(caller) ∩ agent_ceiling
```

An agent is a **lens**, never a principal. It cannot see anything its caller cannot see, and
its own ceiling can only narrow that further. `EntitlementSet.intersect` is the one
implementation and everything needing a run reach calls it: `brain.gate.leash.decide` and
`brain.gate.leash.resume` on the request path, `brain.ops.automation.flow_reach` for work
with nobody present, and two console modules for what a screen may show. Do not add a second
implementation. A second copy of the central rule is a second place for it to be subtly
wrong, and the wrong copy is the one in production.

**This paragraph named `brain.gate.invoke.invoke` until 2026-09-08, and that module has no
`intersect` call in it at all.** The sentence had been copied into `console/reads.py`,
`console/reach_view.py` and the invariant test that guards the rule, so four documents agreed
with each other and none of them with the code. `reads.py` had additionally turned "two call
sites" into "two implementations", which is the drift that matters: it makes a second
implementation sound like the status quo. `tests/invariants/test_single_implementation.py`
now reads the call sites out of the source, because nothing else would have caught it.

**`intersect` evaluates the right-hand side's expiry, so it has to be told the instant.**
The left-hand side's is not decided there: it is carried out on `not_after` and asked later by
whoever calls `scope_for` on the result, with their own `now`. Only the right-hand side's is
decided inside `intersect`, and until 2026-09-08 that call had no parameter for the time and
used the process clock. The four surfaces that ask "may this reader be told this" are written
`requirement(thing).intersect(reader)`, which puts the real principal on the right, so a
reader's expiry was exactly what was being judged at the wrong instant, and it failed
permissive. Pass `now` wherever you have one. Which call sites do is pinned in
`tests/invariants/test_single_implementation.py`, along with the four that cannot.

**Entitlements are additive only.** There is no deny list anywhere and there must not be one.
Revocation is the deletion of a grant. A second source of grants (the directory sync, say)
can therefore only ever add, and that is why a union is safe.

**DENIED and ABSENT must be indistinguishable to a person.** This is the hardest rule to keep
and the easiest to break by accident:

- Never emit a count of hidden items. Not directly, and not by subtraction: "showing 3 of 47"
  tells the reader there are 44 things they may not see, which is 44 facts they did not have.
- A refusal message must not name what was refused. `brain.ops.denial_alerts` names the
  *shape* of a denial pattern and never the capability or the object.
- Retrieval is where this leaks most quietly. An answer that says "I cannot find that" for one
  product and answers for another has disclosed which products exist.

---

## House style

**Module docstrings explain why, and record what was rejected.** Not what the module does, the
reader can see that. Why it is shaped this way, what the cheaper design was, and what breaks if
somebody switches to it. Look at `brain/ops/limits.py`, `brain/tools/extract.py` or
`brain/ops/limit_store.py` for the register. Bold the load-bearing claims so a reader skimming
finds the argument.

**Every module docstring ends with a `Task ids:` line** naming the WBS leaves it implements.
`brain.ops.sweeps traceability` checks these against commits, and a claim with no test is
counted and printed on every run.

**Named reason constants.** A rule that a reviewer must not break gets an ALL_CAPS string
constant stating it in words, and a test asserting the property. `BOTH_LIMITS_APPLY`,
`ABUSE_DETECTION_HAS_NOWHERE_TO_REFUSE`, `REFUSED_REQUESTS_DO_NOT_EXTEND_THE_WINDOW`. The
constant is how the rule survives the person who wrote it.

**British spelling.** Behaviour, authorisation, recognised, licence (noun).

**No em dashes.** Anywhere: code, comments, docstrings, commit messages, documentation.

**Full type annotations.** mypy runs strict over `src`. `cast` is acceptable at a library
boundary where proving a structural match buys nothing; say so in a comment when you use one.

---

## Tests

**A test is named as a property sentence.** `test_a_refused_request_is_not_recorded`, not
`test_record`. Read the name aloud: it should be a claim about the system.

**Every test docstring says what breaks if the test is deleted.** This is not a formality. It
is the only thing standing between a future reader and deleting a test that looks redundant.
If you cannot write that sentence, you do not yet know what the test is for.

**A fixture with a date in it is a clock, and it will go off.** `test_memory_formation.py`
built its readers around `NOW = 2026-09-07 12:00` and gave one of them `NOW + one day`. It
passed the day it was written and failed at noon the next, with nothing about the code having
changed, and what it had found was a real defect in `EntitlementSet.intersect` that had been
there since the method existed. Two lessons and they point in opposite directions, so keep
both. The bug was real and only a clock crossing a fixture ever surfaced it, so do not
"fix" such a failure by moving the date. And a fixture that can expire is a test that reports
a defect on a schedule nobody chose, so pin dates far outside any plausible wall clock when
what you are testing is not itself about the present: `tests/unit/test_scope_and_capability.py`
uses 2019 and 2999 deliberately, and says so.

**Assert on structure, not on text that also appears nearby.** Two tests in this repository
have been satisfied by their own docstrings: `sweep_tool_registry` matched the example in its
own explanation, and a test searching for `filter="data"` passed with the flag removed because
the docstring quoted it. Assert on the full call expression, on parsed YAML, on the object,
not on a substring that a comment can supply.

**Test the positive case too.** A guard tested only by its refusals is satisfied by a function
that refuses everything. Every refusal test needs a sibling proving the thing still works.

---

## Verify by mutation, not by running the suite

This is the practice that matters most here and it is not optional for anything with a guard
in it. Running the suite proves the tests pass. It does not prove they would fail.

**Use `brain.ops.mutation`, not a shell loop.** Every one of the rules below is enforced by
that module, and every one of them was learned by getting it wrong here first:

```python
from pathlib import Path
from brain.ops.mutation import Mutation, verify

report = verify(
    [
        Mutation(
            label="role rules on an untrusted source are filtered, not refused",
            path="src/brain/identity/staff_source.py",
            before="if rules and Asserts.ROLE not in roster.asserts:",
            after="if False:",
            tests=("tests/unit/test_staff_source.py",),
        )
    ],
    repo=Path("."),
    carry=(),   # name anything not committed yet; mutated files are carried already
)
print(report.table())
assert not report.survivors
```

It creates its own throwaway worktree at a commit, copies the files in, mutates *there* and
removes it afterwards. There is deliberately **no parameter naming a directory**, so it cannot
be pointed at this tree. `carry` is how uncommitted files get in; note that the worktree is at
a *commit*, so a test depending on an uncommitted `pyproject.toml` change has to carry that
too, or it fails collection rather than failing the mutation.

`report.table()` is the table to paste into the commit message.

If you must do it by hand, these are the four rules the module encodes:

1. Break it deliberately in the source, **in a `git worktree`, never in this tree**.
2. Run `PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest <the test file> --no-header --disable-warnings`.
3. Confirm the **specific named test** fails, by a `FAILED path::name` line. Not "something
   failed", and not a non-zero exit: a broken import, a collection error and a syntax error all
   exit non-zero for *every* mutation, so a harness reading exit codes reports a perfect score
   at the moment it stops testing anything.
4. Restore the file **byte-identically** and verify with an md5 comparison.

And run the named tests **before** mutating. A test that was already red fails after the
mutation too, and the row says caught by a test that was never watching. One contaminated row
in a table of thirty is worse than no table, because the table is what gets quoted in the
commit message and nobody re-derives it.

**A surviving mutation means one of two things.** Either a test is missing, in which case write
it, or the mutation is genuinely equivalent, in which case say so plainly and do not invent a
test to fit it. Both outcomes have happened here and both are recorded in commit messages. What
must not happen is a survivor being quietly dropped from the table.

`PYTHONDONTWRITEBYTECODE=1` is not decoration. Back-to-back writes to one file let pytest
import a stale `.pyc`, which produces false *survivals*. It cannot produce a false catch, so
earlier passes stay sound, but a mutation run without it will lie to you in the safe direction.

**Where the guard audit has been, as of 2026-09-09.** `brain.ops.guards` mutates every `if`
in a module and reports the ones no test can reach:

```
uv run python -m brain.ops.guards src/brain/ops/admission.py            # one hop
uv run python -m brain.ops.guards src/brain/ops/admission.py 2          # widen it
uv run python -m brain.ops.guards src/brain/x.py --carry migrations/versions/0024_x.py
```

**It lived in `.scratch/` until 2026-09-09, and `.scratch/` is in `.gitignore`.** Every
sentence in this section told the reader to run a file no clone contains, which is the same
shape as a scheduled control nobody calls: correct, documented, and absent from every
direction except the one that matters. It is a module now, with tests, and the paragraphs
below are the two ways to get it wrong.

It has found roughly seventy real defects in three days and almost every one was the same
shape: a validator that is written, correct, and never once run, because every object any test
builds is valid. The list below is where it has been, which saves running it again; where it
has not been is the more useful half, and the paragraph after the list is why.

Audited with no survivors remaining: `core/redaction.py` (six real, fixed),
`identity/roles.py` (eight real and one removed as unreachable), `connectors/throttle.py`,
`launch.py`, `setup_wizard.py`, `ops/crash.py`, `ops/controls.py`, `ops/alerting.py`,
`ops/retune.py`, `ops/scaling.py`, `ops/partitioning.py`, every module under `browsing/`, and
`console/spend_view.py`, `console/model_matrix.py`, `console/approvals.py`,
`console/scoped_authority.py`, `knowledge/search.py` (three real, fixed),
`deployment/compatibility.py` (two real, fixed), `ops/install_docs.py`, `status.py` (eight
candidates, six real and two that could not fire), `audit/ledger.py` (four real, fixed),
`identity/oidc.py` (seven real, fixed), `gate/ingress.py`, `core/scope_sql.py` (ten
candidates: six real, one a second copy of a check the type already makes, three that
could not fire), `ops/pii.py` (twenty candidates: eighteen real, two that could not fire),
`identity/lifecycle.py` (twelve candidates, nine real and three the module already argues
are unreachable and kept), `resolution/merge.py` (eight real, fixed), `ops/outbox.py` (six real, fixed),
`orchestration/unattended.py` (clean, and its three interesting comprehension decisions
mutated by hand), and every module under `migration/`.

`gate/leash.py` has since been re-run with the right scope, and the result is the point of the
episode recorded above. Against the twenty-four test files that import it, the audit finds
twenty-one guards and **no survivors at all**. The seven the one-file run reported were an
artefact of the scope, top to bottom, and the module they were reported against was the one
whose guards a reader would least want to doubt.

`ops/admission.py` was the last unfinished module and is now done, and it is the case that
shows the two-stage rule paying for itself in both directions. Its seven first-pass survivors
were three artefacts and four real defects: a budget with a zero mean service time, which is
the divisor in Little's law; a vendor ceiling of zero, which binds at 0x and sits at the top
of the ladder for ever; a negative demand, which sorts before every real bottleneck; and a
division-by-zero guard in `Demand.binds_at` that a passing test's docstring describes and no
test reaches, because `first_bottleneck` filters an idle source out before anything divides.
That last one is worth reading twice. It is this repository's recurring defect in its purest
form, and the docstring saying what the guard does is what made it look covered.

**And then `knowledge/search.py` was audited on the same day and had three.** That sentence
above, "the audit has now been over every module it can reach", was written a few hours before
and was false when written: the list of audited modules was a list of the ones somebody had
happened to audit, and reading it as a list of the ones that needed it is the same mistake as
reading a green test run as evidence about the code. The module it missed decides what a
reader may retrieve.

The three are the shape you now expect: a vector column of no width, and both halves of the
guard on the pattern converter. Those two are the guard on a defect that actually shipped,
where `(?:` inside a check constraint was read by SQLAlchemy as a bind parameter and rendered
as the word NULL, so the constraint that went out looked like a regex and was a different one.
The guard against it recurring was written, argued in a docstring, and reached by nothing.

So the useful record is not where the audit has been. It is that **a module nobody has audited
looks exactly like a module nobody needed to audit**, and the only way to tell is to run it.
What follows is what running it costs, which is the thing worth knowing before you start.

**Every audit above understated its own coverage, and the correction is newer than the list.**
Until 2026-09-11 `decisions_not_mutated` was blind to `match` statements in both directions: a
`case` arm is not an `ast.If`, a comprehension, an `IfExp` or a `Return` holding a `BoolOp`, so
it was neither mutated nor listed as unmutatable. A module whose decisions are arms came back
with a clean table and nothing under it, which is the one failure that function exists to
prevent, arriving through a node shape it did not know about.

It is not a rare shape here. Measured the day it was found: **53 match statements, 213 case
arms, in 31 modules under `src/brain`**, and the heaviest users are modules on the list above.
`gate/leash.py` reported four decisions it could not reach and has twenty-two;
`ops/partitioning.py` has 22 arms, `core/scope_sql.py` 19, `ops/storage.py` and
`identity/lifecycle.py` 13 each, `ops/spend.py` and `ops/admission.py` 11 each. Those audits
were run honestly and reported a number that was true about `if` statements and read as a
number about decisions.

The arms are now **listed**, so the gap is visible. They are still not mutated, so a module on
that list is audited over its `if` statements and its arms are yours to break by hand. Treat
"audited with no survivors" above as a claim about branches rather than about decisions until
somebody re-runs it and says otherwise.

**A condition inside a comprehension is invisible to the audit, and there are usually more of
them than there are `if` statements.** The audit walks `ast.If`. A filter in a list
comprehension, an `or` fallback on a return and a conditional expression are none of them an
`ast.If` and none of them is mutated, so a module can come back with a clean table and half its
decisions unwatched. `brain.ops.guards.decisions_not_mutated` lists every one it could not
address and the command prints them under the table, which is the difference between a gap and
a silence. `migration/skills.py` has five `if` statements and five comprehension filters;
`knowledge/search.py`'s `lexical_legs` has no `if` statement at all and two decisions, a filter
and a fallback. Mutate those by hand, and count the decisions rather than the rows before
believing a survivor count of zero.

**Mutate the constants too, not only the branches.** This is the sibling of the docstring rule
above and it caught three separate authors on 2026-09-06, in one afternoon. A test that asserts
`answer == SOME_CONSTANT` while importing `SOME_CONSTANT` from the module under test compares
the constant against itself: change its value and both sides move together, and the test is
green for every value it could possibly hold.

- `hubspot.CEILING_NAME` repointed from `"hubspot"` to `"freshdesk"` passed its whole ceiling
  test, because the test branches on `connector_ceiling(CEILING_NAME)` and Freshdesk has a
  measured row. The connector would have run against another source's verified rate limit with
  `ceiling_is_verified()` flipping to True to say so.
- `throttle.RETRY_AFTER_WHEN_UNSTATED` dropped from 300 seconds to 1 second passed the two
  tests written for it that same hour.

Assert a constant against something outside itself: another module's measured value, a second
constant it must relate to, or the property that makes the figure right. `RETRY_AFTER_WHEN_UNSTATED
>= MAX_BACKOFF_SECONDS` and `CEILING_NAME == CONNECTOR_NAME` are both stated that way now.

**A test that builds the value the function under test produces has not tested that function.**
`lark_wiki.restriction_of` reads a vendor payload into a three-way verdict. Every test built a
node with the verdict already set and asked what the consumer did with it, so the branch that
reads "this node has its own permissions" could return "inherits the space" with the suite
green. When a producer and a consumer sit either side of a value, one test for each is two
tests for the consumer unless you write the producer's from the raw payload.

---

## Commits

- The subject line says what changed for a reader, not which files moved.
- The body argues. Why this shape, what was rejected, what a mutation found, what is still not
  done and why. These messages are the design record; there is no other one.
- `Closes: M12.2.4, M12.2.6` claims WBS leaves. One id per leaf, and only leaves you can point
  at a test for.
- **Do not claim a leaf that is already closed.** `ops/hooks/commit-msg` calls
  `brain.ops.conventions.already_closed` and warns; it is advisory rather than blocking, and it
  has caught this twice.
- **Claim honestly.** If an agent built something and you did not verify it, say so. If six
  leaves need a service you could not reach, list them and the reason.

---

## Environment traps, all of which have cost time here

**The shell is PowerShell 5.1** for anything handed to the user. `&&` is a parser error there.
Run commands yourself rather than handing them over.

**Heredocs mangle backslashes.** Writing a Python script through `cat <<'PY'` has collapsed
`\\` to `\` and produced `re.PatternError: unterminated character set` more than once. For
anything containing a backslash, use the Write tool, or `chr(92)`.

**`ruff format` is a push gate.** A file written by a script that does string replacement
skips the habit of formatting, and the pre-push hook catches it after the commit. Run
`uv run python -m ruff format --check` before committing.

**Python writes CRLF.** `Path.write_text` without `newline="\n"` inserts CRLF on this machine,
which dirties a clean tree and has broken a shell script on the server.

**And a green test run is not evidence about what you staged.** On 2026-09-08 an agent's
module and its test file passed together at 21:08, were staged at 21:10, and the commit was
red: between the two the agent had renamed a constant in the test and had not yet renamed it
in the module. `git add` takes the working tree at the moment it runs, which is a different
moment from the one the tests were run in, and two minutes was enough. The clean-worktree
check caught it, the commit was unpushed and the repair was an amend. Waiting for the agent's
completion notification is the cheap version of this.

**Never stage a file another agent is editing.** `git add` takes the working tree, not your
edits, so staging a shared file commits whatever anybody else has written into it. This has
now happened once with `src/brain/tables/__init__.py` and `tests/unit/test_tables.py`: a
commit registering the memory tables also carried an in-flight registration of
`brain.tables.fast_lane`, whose module was untracked, so the commit imported a module it did
not contain and seven tests failed on a clean checkout of it.

The pre-push worktree check is what caught it, which is that guard doing exactly its job. The
repair is worth knowing because the obvious two attempts both failed: editing the file on disk
and re-staging races the other agent, who added four more references between the first attempt
and the second. Rewrite the committed blob instead and never open the working tree:

```
git show HEAD:<path>            # the committed version
                                # strip the other agent's block from that text
git hash-object -w --stdin      # write the corrected blob
git update-index --cacheinfo 100644,<sha>,<path>
git commit --amend --no-edit
```

Amending rather than fixing forward, because every push to main deploys, so a broken commit in
the history is a failed deployment rather than an untidy log.

**mypy type checks the platform it is running on, so a green local run says nothing about the
container.** It narrows `sys.platform` to a literal and then declines to warn about a block a
platform check excludes. That courtesy covers the guarded block and **not the statements
downstream of it**, so a function branching on the platform is checked in halves: Windows
checks one, the ubuntu runner checks the other, and each is silent about the half it skipped.

On 2026-09-11 `brain.ops.worker._loop_factory` was written `if sys.platform != "win32": return
None` with the Windows branch after it. Local mypy said `Success: no issues found in 681 source
files`; CI said `Statement is unreachable` and exited 1. CI gates Deploy, so production sat on
the previous commit and the only symptom was a task list that had stopped updating. Inverting
the condition fixes Linux and breaks Windows, measured both ways: the asymmetry is in mypy's
narrowing rather than in which branch comes first.

So **branch on `os.name`, which mypy does not narrow at all**, and both branches are then
checked on both platforms, which is more checking than either `sys.platform` form bought. And
the gates now judge the platform this ships on: `ops/hooks/pre-push` passes `--platform
"$SHIPS_ON"` on both its mypy runs, `make types` passes `--platform linux`, `make types-here`
is the native run for debugging a development machine, and
`test_the_local_type_gates_judge_the_platform_the_runner_does` holds all of that against the
`runs-on` of whichever job in `ci.yml` actually runs mypy. To reproduce the runner by hand:

```
uv run python -m mypy --platform linux
```

**pytest addopts already contains `-q`.** Passing another one makes it `-qq` and suppresses the
summary line, so a green run prints no count at all.

**"pre-push: all gates green" does not mean the unit suite ran.** `ops/hooks/pre-push` runs
`ruff`, `mypy`, `pytest tests/invariants` and the sweeps, and deliberately not `tests/unit`:
it is built to take seconds, and its own comment says so. CI runs the unit suite separately.
So a green push can still be a red CI, and it has been: a change to `docs/needs-rupash.md`
made five questions open while `docs/architecture.html` still said four, and
`test_architecture_doc.py` is a unit test. Run `uv run python -m pytest --no-header --disable-warnings`
yourself before pushing anything that touches a document, a fixture or a count. The hook is a
fast filter, not the gate.

**No function or class under `src/brain` may have "restore" in its name** unless it is
`recovery.last_verified_restore`. `tests/unit/test_installation.py` pins that, and the reason
is in `docs/needs-rupash.md` item 44: a console field labelled "last verified restore" beside
a backup timestamp is the field somebody checks before deciding not to worry, and the test is
written so it goes red on the day somebody adds a restore, which is the day that screen should
be written. It cost an agent a red test on 2026-09-09 for a wizard helper called `restore`
that had nothing to do with backups. Call it something else.

**`ruff` reads the word "noqa" inside an ordinary comment as a directive.** Reword rather than
explain a suppression using that word.

**WBS task ids are positional, so a group is appended and never inserted.** `M27.5.5` means
"the fifth leaf of the fifth task group of M27", and nothing anchors it to a name. Adding
`Install screens` as M27's fifth group on 2026-09-07 silently repointed every `M27.5.x` claim
in `brain/console/reads.py` at four leaves about backups. The traceability sweep caught only
the one id that fell off the end (`M27.5.5`, reported as naming a group); the other four
matched real leaves and would have shipped as a correct-looking, wrong claim. The same edit to
M1 moved `Entitlement system` from `M1.4` to `M1.5`. Append a new group to the end of `tasks`,
append a new leaf to the end of `s`, and run `node docs/wbs/export.js`, `node docs/wbs/render.js`
and the traceability sweep afterwards, reading the "names a group" note rather than only the
`ok:` line.

**Mutation testing is not safe in a working tree another agent is reading.** The harness writes
a deliberately broken source file, runs pytest and restores it. On 2026-09-07 a second agent
read `ops/telemetry.py` inside that window, saw the mutant, concluded a stray mutation had
survived, wrote a test whose docstring said so, and wrote the mutant line back into the module.
Both agents were behaving correctly. This is now closed by construction: `brain.ops.mutation`
owns its worktree and has no parameter you could point at this tree. Use it.

**A mutation run is only as honest as the tests you pass it, and the failure is silent and
flattering.** `Mutation.tests` names the files to run. Name too few and every guard the other
files cover comes back SURVIVED, and a survivor reads as a gap in the code rather than a gap
in the run.

That is not hypothetical and it was expensive. On 2026-09-08 an audit that mutates every `if`
in a module was pointed at `gate/leash.py` with `tests/unit/test_leash.py` alone, for a module
nineteen test files exercise. It reported seven unreachable guards, three of them security
checks on the resume path, and the report was written up and briefed to an agent before
anybody re-measured. Four were real. Three were already covered by
`tests/invariants/test_leash_invariants.py` and the run had simply not been shown it.

**Worked out from the import graph does not mean the transitive closure**, and this is the
other half of the rule. Followed to a fixed point, `ops/admission.py` is reachable from
eighty-five modules and a hundred and five test files, because one hop lands in `ops/limits.py`
and two more land in `brain.app`, which imports the estate. Thirty-three guards against a
hundred and five files is the whole suite thirty-three times over, so it does not get run, and
a scope nobody runs is worth less than a narrow one somebody does. One hop gave forty-two
files, which took minutes and caught three of the seven candidates. `brain.ops.guards.reaching`
takes the depth as an argument for exactly this reason: widen it when a survivor is still
standing, not before.

So: **for a module anything else imports, work the test set out from the import graph rather
than guessing it**, and print the set. A cheap first pass against one file is fine and is what
makes auditing a module affordable at all, but a first-pass survivor is a candidate and never
a finding. Re-check it against every test file that imports the module before writing a word
about it. Passing a larger depth is that second stage, and the console modules' nineteen real
findings the same day are what the first stage is worth when its scope happens to be right:
each of those has exactly one test file, so there was nothing else to miss.

---

## Layout

| Path | What lives there |
| --- | --- |
| `src/brain/core/` | Principals, entitlements, redaction, field policy. The invariant's home. |
| `src/brain/gate/` | The request pipeline: ingress, identify, entitle, screen, cache, route, invoke. |
| `src/brain/identity/` | OIDC, roles, sessions, the directory sync. |
| `src/brain/ops/` | Limits, admission, tracing, sweeps, delivery, the vault. Operational concerns. |
| `src/brain/tools/` | The tool registry, skills, archive extraction, importing from elsewhere. |
| `src/brain/channels/` | Channel adapters and the room floor. |
| `src/brain/tables/` | SQLAlchemy models. Ten schemas; see `brain.db.SCHEMAS`. |
| `src/brain/console/` | Every administrative surface. Each one decides what a reader may see and writes nothing. |
| `src/brain/orchestration/` | Multi-agent runs: the fold that narrows a reach at every hop, and the fan-out budget. |
| `src/brain/migration/` | Moving a company off the system it already runs. Seven modules, and every one is a refusal: only knowledge carries across, a vector never does, an entity seed has nowhere to hold the old system's access, and a rebuilt agent starts at Shadow. |
| `src/brain/browsing/` | An agent with hands. Four refusals: the planner cannot read the page, the policy cannot change mid-run, the credential never reaches the model, the rubric predates the run. |
| `migrations/versions/` | Alembic. Every new table enables row-level security. |
| `docs/wbs/*.js` | The work breakdown. `docs/wbs.json` is compiled from it. |
| `docs/needs-rupash.md` | Decisions only the owner can make. Served at `/build/needs-rupash`. |
| `ops/` | Keycloak realm, OpenBao policies and runbooks, git hooks. |

**Nothing that decides policy owns a client.** `brain.ops.limits` holds the sliding-window
algorithm and no connection; `brain.ops.limit_store` holds the Valkey side and no policy;
`brain.cache` is the same split. The reason is testability of the case that is always wrong:
you cannot test a window boundary through a module that opens a socket.

---

## Before you say something is done

- `uv run python -m pytest --no-header --disable-warnings`
- `uv run python -m mypy`
- `uv run python -m ruff check src tests`
- `uv run python -m ruff format --check src tests migrations`
- `uv run python -m brain.ops.sweeps traceability`

**`uv run python -m <tool>`, not `uv run <tool>`, and the difference is not style.** `uv run
mypy` spawns the console shim uv writes into the environment, and on this machine Windows
Application Control intermittently refuses a freshly written unsigned executable in a
temporary directory: `Failed to spawn: mypy ... (os error 4551)`. It is intermittent, which is
worse than consistent, because it presents as a gate failing with no gate having an opinion.
Running the interpreter uv already trusts and importing the tool as a module spawns nothing
new. `brain.ops.mutation` and `ops/hooks/pre-push` both carry the same fix for the same
reason, and the harness one presented as a flaky test in the module whose whole job is to be
believed.

**That policy is the same one behind four separate blocks over three days, and the rule that
predicts them took until 2026-09-11 to see: it refuses what Windows is asked to *start*, and
not a library a process loads.** Everything it stopped was started or loaded as an image: the
console shims above, the uv-managed CPython in `%APPDATA%\uv\python`, `initdb.exe` from inside
PostgreSQL's installer, and `pq.cp313-win_amd64.pyd`, which is psycopg's driver and is an
extension module. What it does not stop is `libpq.dll` from PostgreSQL's binaries-only zip,
which is equally unsigned and loads through ctypes without complaint.

So the two fixes that work are a signed interpreter (`winget install --id Python.Python.3.13`,
then rebuild the venv from it) and that zip unpacked to `C:\pgsql` with its `bin` on PATH.
`winget install --id PostgreSQL.PostgreSQL.17` does **not** work and will not: the installer
exits 1 because the policy refuses the binaries it runs.

**And anything that makes a throwaway worktree has to name its interpreter.** A fresh worktree
has no environment, so uv goes looking for one and finds the managed copy that is blocked. Both
`brain.ops.mutation` and `ops/hooks/pre-push` now pass `--python` derived from
`sys.base_prefix`. That is right on its own terms as well as being the fix: a mutation run is
evidence about the environment the caller verified in, and letting a subprocess choose made it
evidence about one nobody had looked at. Pointing it at `sys.executable` instead is the trap
next door, and it is worse: the venv's editable install resolves `brain` to the **main tree**,
so the mutated file in the worktree is never read and every mutation comes back SURVIVED. One
test in `test_mutation.py` catches that and nothing else does.

And measure rather than assert. If you claim a thing is fixed, show the command and its output.
If a test fails, say so and paste it. A report that rounds up is worse than no report.
