The matcher's weights are now fitted from this install's own candidate pairs once a week. A fit is kept until a reviewer promotes it, and the online scorer then reads the promoted fit by name. This PR has no migration.

**What it does:**
- **The weekly job** (`resolution_calibration`, in-process, BATCH). It extracts the agreement patterns of the registry's candidate pairs in one SQL statement (`query.pattern_query`), fits with EM over the features present, and carries the weight in force for any feature nothing agreed on (`WeightExport.fitted`). It keeps the result as a candidate. In report-only mode it keeps nothing.
- **Promotion.** `POST /resolution/weights/promote` requires `admin:entity_merge`. It writes `reviewed_by` and `in_force` in one transaction, and `0059`'s trigger puts the change on the ledger under the reviewer's name, as a merge is recorded. A version that is not the current candidate is refused with a 409.
- **The weights in force.** `matching_store` scores and resolves with whatever is in force.
- **Drift, shown to a reviewer** on the Resolution review screen. It is in words only, with no counts of pairs.

**Who can see what.** Fit rows live in their own settings namespace. Only the worker and holders of `admin:entity_merge` can read them, and the general settings route never serves them.

**Decision (f), stated plainly:** "exports volume" is met by settings rows for the weights. The volume holds only the offline matcher's DuckDB export.

**M14.4.1 (the Splink job) is built, not proved.** It stays the offline matcher image, built by the release workflow. Nothing here claims it was seen on an install.

**Install check:** `acceptance_checks_calibration` (order 438), with four break tests:
- a fit is made over the install's pairs;
- a reviewer sees its drift in words;
- someone without the capability is refused;
- the reviewer's promote puts the fit in force in their name, and the scorer then reads it.

**Mutations:** 15 run, 14 caught. The one survivor is an equivalent mutation, on the attribution actor: the trigger records `updated_by`, so the actor written by the store is not what decides the entry. The table is in the commit message.

**Verified locally**, on top of main after #406: invariants plus the calibration test files on a fresh database, 1869 passed. `mypy --platform linux`, ruff, format and the traceability sweep are clean. The console page test was not run locally because this worktree has no `node_modules`; the console CI job runs it.

Reused: `brain.resolution.calibration`'s EM model and drift, which were written earlier and called by nothing, plus the registry's observation table, the settings store with its ledger trigger, and the review screen.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
