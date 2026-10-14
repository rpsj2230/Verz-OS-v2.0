# Developer tools

Scripts for the people building this product. None of them runs on an install and none of
them is shipped to one.

## keep_prs_fresh.py: keep open pull requests up to date

When the default branch moves, every open pull request behind it goes stale. A stale one
stops auto-merge, and one that would now conflict gets no CI at all. This tool merges the
default branch into each stale pull request that merges cleanly, and only reports the ones
that would conflict.

**It has to run on your machine, not in GitHub Actions.** A branch updated with the
workflow's own token does not start CI on that branch, so the pull request would sit with no
checks. An update made with your own `gh` login does start CI.

### Run it

You need the GitHub CLI signed in as yourself (`gh auth status`). The repository and its
default branch are read from `gh`, so nothing is configured.

```
uv run python ops/dev/keep_prs_fresh.py                  # dry run: says what it would do
uv run python ops/dev/keep_prs_fresh.py --apply          # update the stale, clean branches
uv run python ops/dev/keep_prs_fresh.py --apply --loop 300   # repeat every five minutes
```

Press Ctrl-C to stop a loop. `--max-updates N` changes how many branches one pass updates
(default 3); the rest are listed as deferred and taken on the next pass.

### What it does and does not do

| Pull request | What happens |
| --- | --- |
| behind, and merges cleanly | `gh pr update-branch <n>`: a merge commit, never a rebase, never a force push |
| would conflict | named with the files both sides changed (an estimate), and **not touched** |
| draft, from a fork, aimed at another branch | skipped |
| labelled `hold` | skipped |
| title or description says "do not update" (any spacing or punctuation) | skipped |
| already up to date, or GitHub has not yet worked out whether it merges | skipped |

It never pushes to the default branch, never merges or closes anything, never turns
auto-merge on or off, and reads no secret: it uses the `gh` login already on the machine.

To keep a branch out of it, add the `hold` label or write `do not update` in the pull
request's title or description.

### Why it caps the updates in one pass

Every update starts a CI run, and CI queues at about twenty jobs a run. Updating thirty
branches at once makes a queue, not speed. Three per pass, lowest pull request number first,
keeps the oldest moving.

### The tests

`tests/unit/test_keep_prs_fresh.py` holds the decision (`decide`), the cap (`plan`) and, with
a fake `gh`, the exact commands a pass runs.

```
uv run python -m pytest tests/unit/test_keep_prs_fresh.py --no-header --disable-warnings
```

## assemble_train.py: merge several pull requests into one train

An ordinary pull request runs lint, types, the invariants and the test files its diff reaches,
and not the whole suite (`ops/DEPLOY.md`, "What a normal pull request no longer proves"). The
whole suite runs on a pull request whose branch starts with `train/`, and every night. This tool
makes that branch from a list of pull request numbers, so the whole suite is paid for once for
all of them instead of once each.

### Run it

You need the GitHub CLI signed in as yourself (`gh auth status`) and a clean working tree. List
the pull requests in the order they should merge:

```
uv run python ops/dev/assemble_train.py 590 592 594          # dry run: says what it would do
uv run python ops/dev/assemble_train.py 590 592 594 --apply  # make the train
```

`--remote NAME` names a remote other than `origin`. The repository and its default branch are
read from `gh`, so nothing is configured.

### What `--apply` does, in order

1. Refuses the list if it is empty or repeats a number, and any pull request that is not open,
   is a draft, comes from a fork, is aimed at another branch or is itself a train.
2. Fetches the default branch and reads the migration numbers on it and the ones each pull
   request adds. **It refuses before anything is merged** if two pull requests carry the same
   number, one reuses a number already on the default branch, or the new numbers do not continue
   exactly from the default branch's highest.
3. Creates `train/<date>-<n>` from the default branch (`n` is the lowest free number that day,
   counting the remote), then fetches each pull request's head and merges it with
   `git merge --no-ff`, in the order given. Each original commit and its `Closes:` and
   `Proved-on-install:` lines therefore reach the default branch; nothing is squashed or rebased.
4. Reads the migration numbers again from what was actually merged.
5. Pushes the train branch (a plain push of `train/...`, never a force and never the default
   branch) and opens **one** pull request for it with auto-merge off. Its description lists every
   pull request, the migration numbers in order, and says the whole suite runs on it.
6. Puts the checkout back on the branch (or commit) it started on.

It never merges the train, never turns auto-merge on and never reads a secret.

### When a pull request conflicts

It stops at the first one, prints the pull request and the files in conflict, aborts the merge,
returns the checkout to where it was and deletes the local train branch. Nothing was pushed.
Fix the conflict on that pull request (or drop it from the list) and run the tool again. It
exits 1 for a conflict or a refusal and 0 for a dry run or a train made.

### Merging the train

Merge the train pull request with a **merge commit, never a squash**: a squash puts every
original commit's trailers into one message and the rest are lost. The pull requests it carried
are usually marked merged by GitHub when it lands; if one is not, close it by hand. The tool
warns, without refusing, when the repository does not allow merge commits.

### The tests

`tests/unit/test_assemble_train.py` holds the decisions, the exact `git` and `gh` commands of a
full run (no squash, no rebase, no force, one push, only of a `train/` branch, no `gh pr merge`)
and two runs against real `git` and a local bare repository: one that makes a train and one that
hits a conflict and must leave nothing behind.

```
uv run python -m pytest tests/unit/test_assemble_train.py --no-header --disable-warnings
```
