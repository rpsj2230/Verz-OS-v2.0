Entity resolution lands as one stack, together with the two migration PRs it depends on, so CI runs once instead of three or four times.

**Contains, and replaces:**
- #255: confirmed memories (0163, now revising 0178)
- #252: the fast lane reads as `brain_fastlane` (0162)
- #391: the join-key pepper

Those three PRs are closed as contained once this one is open.

**The M14 stack:**
- **The join-key pepper.** It is created once, by the installer, in a vault slot nothing can write over. The web process and the worker both read it through one reader.
- **The entity registry (0182).** Every record a connector declares for resolution is registered: a canonical entity, its names, its hashed join keys, its link, and its comparison row. The entity type and the money flag are declared on each connector's `ConnectorDeclaration`, beside its Ask rows. Tests check that every declared entity exists in its connector's manifest and that discovery is never empty (anchored on Xero).
- **Merge and unmerge (0183).** A merge records who, when, its evidence and its pre-image. An unmerge reverses it on the ledger, and an old id still resolves through the forwarding pointer.
- **The online cascade.** Every newly registered record is compared with its candidates, scored in the database, and each pair is either merged, held for a person, or left alone. Five reasons hold a match: money, a name-only match, a cap, a collision, and unattended merging being switched off. Unattended merging is off on every install (item 155).
- **The review queue (0184) and the Resolution review screen.** A reviewer who holds `admin:entity_merge` sees the pairs waiting, with the evidence written in sentences, and merges or rejects each one in their own name.

**Migration order:** 0154 → 0179 → 0178 → 0163 → 0162 → 0182 → 0183 → 0184, with a single head. **Auto-merge is off** because this PR carries migrations.

**Decision (f), stated plainly:** "exports volume" is met by settings rows for the weights. The volume is used only for the offline matcher's DuckDB export. The weights themselves arrive in the calibration PR, which follows this one.

**One interaction with main, fixed here:** 0179 copies `local_id` into `proj.record_retired`. The merge store's scan for entity-keyed columns outside `er` caught it, and three tests failed. `A_RETIRED_ROW_KEEPS_THE_ID_IT_WAS_RETIRED_WITH` now names that column. The copy is insert-only and resolves to the survivor through the pointer, so a merge leaves it as it is. Taking the entry back out turns those three tests red again.

**Verified locally:**
- On a fresh database: the invariants plus the 43 test files this branch touches. 2716 passed and 3 failed (the three above). After the fix and a final merge of main once #357 had merged: 2719 passed, 0 failed.
- `mypy --platform linux`, ruff, format and the traceability sweep are all clean.
- The mutation tables are in each commit's message.

No leaf is claimed. The install checks (`acceptance_checks_registry`, `_entity_merge`, `_matching` and `_review`) run in CI. None of these leaves has yet been seen working on the owner's install.

Reused: `brain.resolution`'s canonical model, cascade, query, merge and guardrails modules, which were written earlier and called by nothing; this stack wires them to tables, the worker and a screen. Also reused: the connector declarations, the vault slot pattern, and the console kit.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
