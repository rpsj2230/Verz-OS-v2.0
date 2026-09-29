### Skills and tools

- **Screens:** `/skills`, `/skills/:name`, `/skills/:name/:view`, `/tools`, `/tools/:name`
- **Tables:** `agent.skill`, `agent.skill_review`, `agent.skill_assignment`, `agent.tool_definition`, `agent.tool_switch`, `agent.skill_category`, `agent.skill_invocation`, `agent.skill_retirement`, `agent.skill_detachment`, `agent.skill_script`, `agent.skill_example`, `agent.skill_rehearsal`
- **Installation values:** `INSTALL_ACCEPTANCE_SKILL_SOURCE`
- **Measured here:** 16 routes, 0 called by no screen; 12 write routes, 12 with all three proofs; 3 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/skills/{skill_name}/stats` | `/skills/:name` |
| `GET /api/v1/skills` | `/skills/:name`, `/skills/:name/:view` |
| `GET /api/v1/skills/library` | `/skills` |
| `GET /api/v1/tools` | `/tools`, `/tools/:name` |
| `POST /api/v1/skills` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/detachments` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/exports` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/rehearsals` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/reinstatement` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/retirement` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/review` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/tools/{name}/switch` | `/tools/:name` |

- **Gap.** A skill cannot be tried out through an agent in practice mode before it is assigned. Recorded: docs/admin-console-architecture.md 4.2 tests a skill through an agent that holds it, rehearsed at SHADOW, and no route runs a rehearsal; the Profile draws it inert with pages/skills/skillActions.ts' sentence.
- **Gap.** A skill's script is approved by its bytes and checked before a run, and nothing runs it. Recorded: brain.tools.run_skill.plan_run refuses bytes other than the approved sha256, and no sandbox runner is built, so the execution tool is registered nowhere (brain.tools.run_skill.SANDBOX_PROPERTIES says which six properties a container still has to honour).
- **Gap.** A rehearsal of a skill's example tasks is a person's recorded verdict, not a model's run. Recorded: no model carries out a skill on an install yet (brain.agent_builder_routes.A_REHEARSAL_RUNS_NO_MODEL_YET), so brain.console.skill_library.A_REHEARSAL_IS_A_PERSON_S_VERDICT_UNTIL_A_MODEL_ANSWERS records who judged each example and says so on the form.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/skills` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_imports_a_skill_from_a_repository_at_a_commit_and_it_waits` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` | `test_the_database_refuses_an_unsaid_self_decision_and_an_assignment_nobody_approved` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_categories_set_on_a_skill_are_chips_that_filter_the_skills_in_use` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/detachments` | `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detached_skill_is_gone_from_the_agent_and_its_assignment_is_no_longer_in_force` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/exports` | `/skills/:name`, `/skills/:name/:view` | Not applicable: An export writes no row: it answers the approved version's words, scripts and examples as a zip, which lands on another install only when somebody adds it there. | Not applicable: An export changes nothing anybody holds, so there is nothing for the ledger to record. | `test_an_approved_skill_is_exported_through_the_route_and_reads_back_as_that_version` in `tests/unit/test_skill_packages.py` |
| `POST /api/v1/skills/{digest}/rehearsals` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_a_package_s_scripts_examples_and_rehearsals_are_stored_beside_it_and_read_back` in `tests/unit/test_skill_packages.py` (database, in CI) | `test_a_package_s_scripts_examples_and_rehearsals_are_stored_beside_it_and_read_back` in `tests/unit/test_skill_packages.py` (database, in CI) | `test_a_version_with_examples_is_rehearsed_then_approved_through_the_routes` in `tests/unit/test_skill_packages.py` |
| `POST /api/v1/skills/{digest}/reinstatement` | `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/retirement` | `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/review` | `/skills/:name`, `/skills/:name/:view` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_edit_waits_for_review_as_a_new_version_while_the_agent_keeps_its_pin` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/tools/{name}/switch` | `/tools/:name` | `test_a_super_administrator_switches_a_tool_off_for_the_install` in `tests/unit/test_tool_routes.py` | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) |
