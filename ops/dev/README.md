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
