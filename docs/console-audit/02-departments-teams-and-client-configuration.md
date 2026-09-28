### Departments, teams and client configuration

- **Screens:** `/departments`, `/department`
- **Tables:** `gate.department`, `gate.team`, `gate.team_membership`, `gate.department_lead`
- **Installation values:** `INSTALL_COMPANY_NAME`, `INSTALL_PRODUCT_NAME`, `INSTALL_LOGO_URL`, `INSTALL_ACCENT_COLOUR`
- **Measured here:** 11 routes, 8 called by no screen; 2 write routes, 2 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/departments` | `/departments` |
| `POST /api/v1/govern/departments` | **no screen** |
| `POST /api/v1/govern/departments/lead` | `/departments` |
| `POST /api/v1/govern/departments/membership` | `/departments` |
| `POST /api/v1/govern/departments/rename` | **no screen** |
| `POST /api/v1/govern/departments/retirement` | **no screen** |
| `POST /api/v1/govern/departments/scopes` | **no screen** |
| `POST /api/v1/govern/departments/scopes/retirement` | **no screen** |
| `POST /api/v1/govern/departments/team` | **no screen** |
| `POST /api/v1/govern/departments/team/rename` | **no screen** |
| `POST /api/v1/govern/departments/team/retirement` | **no screen** |

- **Gap.** A department, a team or a scope cannot yet be created, renamed or retired from this screen. Recorded: brain.govern_people_routes serves the eight writes, audited by 0086's triggers, and Departments.tsx does not call them yet; the screen places people in the teams that are there and leads the departments that are there.
- **Gap.** Nothing applies the staff list's teams and leads on a schedule. Recorded: brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either. The nightly staff sync (brain.ops.staff_sync_run, since 2026-09-21) applies the roster's people and marks leavers, and not its teams or leads.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/govern/departments/lead` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
| `POST /api/v1/govern/departments/membership` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
