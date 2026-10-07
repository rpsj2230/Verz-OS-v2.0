When a name in a question belongs to more than one client the asker can read, Brain now says so in one sentence, and a reviewer is also given the review link. A record the asker may not read changes nothing in the reply, down to the byte (M14.6.5). This PR has no migration.

**What changed:**
- **Before:** two records answering to one name fell through to the model lane, which can pick one of them or add two clients' figures together, with nothing reading the answer afterwards.
- **Now:** the fast lane asks the registry which current client each held record is (`fast_lane.AmbiguityReader`, implemented on an install by `resolution.ambiguity_store.StoredAmbiguity`, following the merge pointer). If every record is linked and they resolve to two or more entities, the asker is told `UNRESOLVED_TEXT` and given no figure from either record. The outcome is recorded as `RETRIEVED_BUT_NOT_ANSWERING`.

**Why DENIED and ABSENT stay indistinguishable:** every record compared was read at the asker's own reach. A withheld record never comes back from the row plane. With one record held, the registry is not even asked, so the reply is exactly the one the asker would get if the other record did not exist. `NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS` states this, and `THE_ASKER_IS_NEVER_TOLD_WHICH_KIND_OF_NOTHING_HAPPENED` names it as its one exception, keeping its rule for withheld records.

**The review link** goes only to a reader holding `admin:entity_merge` over everything. Everybody else gets the plain sentence, whether or not a review item is open.

**Narrowed, and agreed with the coordinator:** a record the registry has not linked still falls through as before. Otherwise two rows of one service in an uploaded price list would be told as two clients.

**Not built:** naming the records themselves, which M14.8.1's text asks for. That is owner item 159.

**Install check:** `acceptance_checks_unresolved` (order 440) has three readers and four break tests:
- an asker who can read both departments gets the sentence and neither price;
- a reviewer gets the review link;
- a one-department asker gets byte-identical frames before and after the withheld row exists.

**Mutations:** 13 run, 13 caught. The table is in the commit message.

**Verified locally**, on top of main after #411: invariants plus the affected test files on a fresh database, 1848 passed. A wider related subset (every test file on the gate, answers, resolution, acceptance, tables and documents) passed 3668. `mypy --platform linux`, ruff, format and the traceability sweep are clean.

No leaf is claimed. The install check runs in CI, but this has not been seen on the owner's install.

Reused: `fast_lane.respond` and `answer_lane` (extended), `guardrails.UNRESOLVED_TEXT` and `UnresolvedNotice` (nothing called them until now), the registry, matching and merge stores, and the upload and mark steps from `acceptance_checks_tables`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
