### Skills and tools

- **Screens:** `/skills`, `/skills/:name`, `/skills/:name/:view`, `/tools`, `/tools/:name`
- **Tables:** `agent.skill`, `agent.skill_review`, `agent.skill_assignment`, `agent.tool_definition`, `agent.tool_switch`, `agent.skill_category`, `agent.skill_invocation`, `agent.skill_retirement`, `agent.skill_script`, `agent.skill_detachment`, `agent.skill_export`
- **Installation values:** `INSTALL_ACCEPTANCE_SKILL_SOURCE`
- **Measured here:** 16 routes, 0 called by no screen; 12 write routes, 12 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/skills/{skill_name}/stats` | `/skills/:name` |
| `GET /api/v1/skills` | `/skills/:name`, `/skills/:name/:view` |
| `GET /api/v1/skills/library` | `/skills` |
| `GET /api/v1/tools` | `/tools`, `/tools/:name` |
| `POST /api/v1/skills` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/procedures` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/assignments` | `/agents/:agentId`, `/agents/:agentId/:tab`, `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/detachments` | `/agents/:agentId`, `/agents/:agentId/:tab`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/export` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/reinstatement` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/retirement` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/review` | `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name`, `/skills/:name/:view` |
| `POST /api/v1/tools/{name}/switch` | `/tools/:name` |

- **Gap.** A skill cannot be tried out through an agent in practice mode before it is assigned. Recorded: docs/admin-console-architecture.md 4.2 tests a skill through an agent that holds it, rehearsed at SHADOW, and no route runs a rehearsal; the Profile draws it inert with pages/skills/skillActions.ts' sentence.
- **Gap.** A skill that declares scripts cannot be added. Recorded: brain.tools.skills.Skill.digest covers a script's name and not its bytes, so an approval would not cover the code, and brain.tools.run_skill has no runner; brain.console.skill_library refuses one at the door.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/skills` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_imports_a_skill_from_a_repository_at_a_commit_and_it_waits` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/procedures` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_on_a_real_database_the_procedure_check_passes_and_leaves_nothing_behind` in `tests/unit/test_acceptance_procedures.py` (database, in CI) | `test_on_a_real_database_the_procedure_check_passes_and_leaves_nothing_behind` in `tests/unit/test_acceptance_procedures.py` (database, in CI) | `test_an_administrator_imports_a_word_procedure_and_it_waits_with_its_findings` in `tests/unit/test_skill_procedures.py` |
| `POST /api/v1/skills/{digest}/assignments` | `/agents/:agentId`, `/agents/:agentId/:tab`, `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` | `test_the_database_refuses_an_unsaid_self_decision_and_an_assignment_nobody_approved` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_categories_set_on_a_skill_are_chips_that_filter_the_skills_in_use` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/detachments` | `/agents/:agentId`, `/agents/:agentId/:tab`, `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detached_skill_is_gone_from_the_agent_and_its_assignment_is_no_longer_in_force` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/export` | `/skills/:name`, `/skills/:name/:view` | `test_on_a_real_database_an_export_is_a_row_and_a_ledger_entry_in_the_exporters_name` in `tests/unit/test_skill_export.py` (database, in CI) | `test_on_a_real_database_an_export_is_a_row_and_a_ledger_entry_in_the_exporters_name` in `tests/unit/test_skill_export.py` (database, in CI) | `test_an_administrator_exports_an_approved_version_and_another_install_takes_it_undecided` in `tests/unit/test_skill_export.py` |
| `POST /api/v1/skills/{digest}/reinstatement` | `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/retirement` | `/skills/:name`, `/skills/:name/:view` | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store` in `tests/unit/test_skill_lifecycle.py` (database, in CI) | `test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached` in `tests/unit/test_skill_lifecycle.py` |
| `POST /api/v1/skills/{digest}/review` | `/skills/:name`, `/skills/:name/:view` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name`, `/skills/:name/:view` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_edit_waits_for_review_as_a_new_version_while_the_agent_keeps_its_pin` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/tools/{name}/switch` | `/tools/:name` | `test_a_super_administrator_switches_a_tool_off_for_the_install` in `tests/unit/test_tool_routes.py` | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) |
