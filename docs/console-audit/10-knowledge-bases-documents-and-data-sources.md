### Knowledge bases, documents and data sources

- **Screens:** `/library`, `/learning`, `/memory`, `/memory/:subject`, `/records`, `/records/:entity`, `/classification`, `/classification/:entity`, `/classification/:entity/:column`, `/artifacts`
- **Tables:** `know.item`, `know.chunk`, `know.steward_task`, `know.solution`, `mem.adaptive`, `mem.persistent`, `mem.learning`, `mem.correction`, `gate.fast_path_rule`, `gate.field_policy`, `agent.artifact`, `know.classified_table`, `know.classified_row`
- **Installation values:** `INSTALL_VECTOR_STORE`, `INSTALL_EMBEDDING_REVISION`
- **Measured here:** 26 routes, 1 called by no screen; 13 write routes, 13 with all three proofs; 4 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/classifications/{entity}` | `/classification/:entity`, `/classification/:entity/:column` |
| `GET /api/v1/govern/artifacts` | `/artifacts` |
| `GET /api/v1/govern/learning` | `/learning` |
| `GET /api/v1/govern/library` | `/library` |
| `GET /api/v1/govern/memory` | `/memory/:subject` |
| `GET /api/v1/knowledge/items` | `/library` |
| `GET /api/v1/knowledge/items/{item_id}` | `/library` |
| `GET /api/v1/knowledge/items/{item_id}/passages` | `/library` |
| `GET /api/v1/knowledge/solutions` | `/library` |
| `GET /api/v1/knowledge/tasks` | `/library` |
| `GET /api/v1/knowledge/uploads/options` | `/library` |
| `GET /api/v1/records/{entity}` | `/records/:entity` |
| `GET /api/v1/records/{entity}/access` | **no screen** |
| `POST /api/v1/classifications/{entity}/columns/{column}/marks/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |
| `POST /api/v1/govern/learning/undo` | `/learning` |
| `POST /api/v1/knowledge/items/{item_id}/promotion` | `/library` |
| `POST /api/v1/knowledge/items/{item_id}/steward` | `/library` |
| `POST /api/v1/knowledge/items/{item_id}/verification` | `/library` |
| `POST /api/v1/knowledge/items/{item_id}/versions` | `/library` |
| `POST /api/v1/knowledge/solutions` | `/library` |
| `POST /api/v1/knowledge/solutions/{solution_id}/decision` | `/library` |
| `POST /api/v1/knowledge/tasks/{task_id}/done` | `/library` |
| `POST /api/v1/knowledge/uploads` | `/library` |
| `PUT /api/v1/classifications/{entity}/columns/{column}/marks` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |
| `PUT /api/v1/classifications/{entity}/table` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |

- **Gap.** A data source cannot be added from the console after setup; a document can, on the Knowledge page. Open leaf `M42.5.9`.
- **Gap.** A memory cannot be edited from a screen, and a tier-two rule cannot be promoted nor a tier-three change decided. Recorded: brain.ops.memory_store writes an edit and no route offers one: the control belongs on a person's own memory tab, and the Memory screen says edit_is_not_writable. Nothing records agreement or a decision, which the Learning screen says in place of Promote and Decide.
- **Gap.** A built-in classification's column is reviewed and not applied; an uploaded table's column is marked and applied. Recorded: The shipped price list is a constant compiled into the API's process and changes with a release; brain.classification_routes applies a mark only to a table stored in know.classified_table, which tests/unit/test_classification_routes.py holds by the routes it mounts.
- **Gap.** A price list uploaded as a document on the Knowledge page is not yet offered conversion to classified rows; it is uploaded on the Classification screen. Open leaf `M7.7.3`.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/classifications/{entity}/columns/{column}/marks/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | Not applicable: A review of a mark is a dry run and writes nothing. | Not applicable: A review changes nothing, so there is nothing to record. | `test_a_mark_review_stores_nothing` in `tests/unit/test_classified_tables.py` |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | Not applicable: A review is a dry run and writes nothing. | Not applicable: A review changes nothing, so there is nothing to record. | `test_the_only_writes_mounted_here_are_the_upload_and_the_mark` in `tests/unit/test_classification_routes.py` |
| `POST /api/v1/govern/learning/undo` | `/learning` | `test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next` in `tests/unit/test_memory_store.py` (database, in CI) | `test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next` in `tests/unit/test_memory_store.py` (database, in CI) | `test_an_undo_writes_the_correction_and_the_next_reading_no_longer_recalls_the_learning` in `tests/unit/test_estate_routes.py` |
| `POST /api/v1/knowledge/items/{item_id}/promotion` | `/library` | `test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/items/{item_id}/steward` | `/library` | `test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/items/{item_id}/verification` | `/library` | `test_a_document_due_for_review_opens_a_task_for_its_steward_which_verifying_closes` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_document_due_for_review_opens_a_task_for_its_steward_which_verifying_closes` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/items/{item_id}/versions` | `/library` | `test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/solutions` | `/library` | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/solutions/{solution_id}/decision` | `/library` | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | `test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/tasks/{task_id}/done` | `/library` | `test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) | Not applicable: Marking a task read closes a notice in the reader's own list and changes nothing anybody holds; what it reports was recorded when it happened. | `test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told` in `tests/unit/test_knowledge_lifecycle_db.py` (database, in CI) |
| `POST /api/v1/knowledge/uploads` | `/library` | `test_an_administrators_upload_is_found_by_its_department_by_text_and_by_nobody_else` in `tests/unit/test_knowledge_upload_db.py` (database, in CI) | `test_an_upload_appends_one_ledger_entry_the_audit_screens_reader_finds` in `tests/unit/test_knowledge_upload_db.py` (database, in CI) | `test_a_markdown_file_is_added_to_a_department_as_its_uploader` in `tests/unit/test_knowledge_routes.py` |
| `PUT /api/v1/classifications/{entity}/columns/{column}/marks` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | `test_the_store_writes_and_reads_a_table_as_the_application_role` in `tests/unit/test_classified_tables.py` (database, in CI) | `test_the_store_writes_and_reads_a_table_as_the_application_role` in `tests/unit/test_classified_tables.py` (database, in CI) | `test_applying_a_mark_stores_it_and_moves_the_epoch_when_a_derivation_changes` in `tests/unit/test_classified_tables.py` |
| `PUT /api/v1/classifications/{entity}/table` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | `test_the_store_writes_and_reads_a_table_as_the_application_role` in `tests/unit/test_classified_tables.py` (database, in CI) | `test_the_store_writes_and_reads_a_table_as_the_application_role` in `tests/unit/test_classified_tables.py` (database, in CI) | `test_an_administrator_uploads_a_price_list_and_is_answered_its_classification` in `tests/unit/test_classified_tables.py` |
