### Departments, teams and client configuration

- **Screens:** `/departments`, `/department`
- **Tables:** `gate.department`, `gate.team`, `gate.team_membership`, `gate.department_lead`
- **Installation values:** `INSTALL_COMPANY_NAME`, `INSTALL_PRODUCT_NAME`, `INSTALL_LOGO_URL`, `INSTALL_ACCENT_COLOUR`
- **Measured here:** 11 routes, 0 called by no screen; 10 write routes, 10 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/departments` | `/departments` |
| `POST /api/v1/govern/departments` | `/departments` |
| `POST /api/v1/govern/departments/lead` | `/departments` |
| `POST /api/v1/govern/departments/membership` | `/departments` |
| `POST /api/v1/govern/departments/rename` | `/departments` |
| `POST /api/v1/govern/departments/retirement` | `/departments` |
| `POST /api/v1/govern/departments/scopes` | `/departments` |
| `POST /api/v1/govern/departments/scopes/retirement` | `/departments` |
| `POST /api/v1/govern/departments/team` | `/departments` |
| `POST /api/v1/govern/departments/team/rename` | `/departments` |
| `POST /api/v1/govern/departments/team/retirement` | `/departments` |

- **Gap.** Nothing applies the staff list's teams and leads on a schedule. Recorded: brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either. The nightly staff sync (brain.ops.staff_sync_run, since 2026-09-21) applies the roster's people and marks leavers, and not its teams or leads.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/govern/departments` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_a_grant_over_a_newly_drawn_scope_is_written_through_the_grant_route` in `tests/unit/test_organisation_structure.py` (database, in CI) |
| `POST /api/v1/govern/departments/lead` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
| `POST /api/v1/govern/departments/membership` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
| `POST /api/v1/govern/departments/rename` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes` in `tests/unit/test_organisation_structure.py` |
| `POST /api/v1/govern/departments/retirement` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_a_department_is_retired_only_once_its_live_grants_move_and_then_refuses_new_ones` in `tests/unit/test_organisation_structure.py` (database, in CI) |
| `POST /api/v1/govern/departments/scopes` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_a_grant_over_a_newly_drawn_scope_is_written_through_the_grant_route` in `tests/unit/test_organisation_structure.py` (database, in CI) |
| `POST /api/v1/govern/departments/scopes/retirement` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes` in `tests/unit/test_organisation_structure.py` |
| `POST /api/v1/govern/departments/team` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes` in `tests/unit/test_organisation_structure.py` |
| `POST /api/v1/govern/departments/team/rename` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes` in `tests/unit/test_organisation_structure.py` |
| `POST /api/v1/govern/departments/team/retirement` | `/departments` | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor` in `tests/unit/test_organisation_structure.py` (database, in CI) | `test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes` in `tests/unit/test_organisation_structure.py` |
