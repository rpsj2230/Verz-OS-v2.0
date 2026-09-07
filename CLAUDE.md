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

And measure rather than assert. If you claim a thing is fixed, show the command and its output.
If a test fails, say so and paste it. A report that rounds up is worse than no report.
