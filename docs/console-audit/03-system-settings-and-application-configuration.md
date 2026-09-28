### System settings and application configuration

- **Screens:** `/install`, `/settings`, `/limits`, `/connections`, `/first-run`, `/first-run/staff-list`
- **Tables:** `ops.setting`, `ops.budget_version`
- **Installation values:** `INSTALL_LOCALES`, `INSTALL_CURRENCY`, `INSTALL_TIME_ZONE`
- **Measured here:** 10 routes, 0 called by no screen; 5 write routes, 4 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/install` | `/install` |
| `GET /api/v1/install/capacity` | `/connections` |
| `GET /api/v1/install/limits` | `/limits` |
| `GET /api/v1/install/settings` | `/settings` |
| `GET /setup/staff-source/registration` | `/first-run` |
| `POST /setup/appointment` | `/first-run` |
| `POST /setup/sign-in` | `/first-run` |
| `POST /setup/staff-source/sign-in` | `/first-run` |
| `POST /setup/staff-source/trial` | `/first-run` |
| `PUT /api/v1/install/settings/{name}` | `/settings` |

- **Gap.** Languages, currency and time zone cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.
- **Gap.** Limits and budgets are read and never changed. Recorded: No route writes ops.budget_version or a ceiling; a limit is a release today.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /setup/appointment` | `/first-run` | `test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish` in `tests/unit/test_setup_routes.py` | `test_the_first_administrator_is_a_live_person_holding_administration_everywhere` in `tests/unit/test_first_administrator.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/sign-in` | `/first-run` | `test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator` in `tests/unit/test_sign_in_routes.py` | `test_the_finishing_screen_binds_the_first_administrator_once_against_the_database` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/staff-source/sign-in` | `/first-run` | Not applicable: It answers the directory's own sign-in page for the setup code's holder and writes nothing. | Not applicable: Nothing changes when a sign-in page is asked for, so there is nothing to record. | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |
| `POST /setup/staff-source/trial` | `/first-run` | `test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync` in `tests/unit/test_setup_staff_routes.py` | `test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync` in `tests/unit/test_setup_staff_routes.py` | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |
| `PUT /api/v1/install/settings/{name}` | `/settings` | `test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next` in `tests/unit/test_settings_routes.py` | **None.** The route sets the audit attribution 0059's trigger reads, which BRANDING_SAVED asserts over a stub; no scratch-Postgres test yet reads the ledger entry back. | `test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next` in `tests/unit/test_settings_routes.py` |
