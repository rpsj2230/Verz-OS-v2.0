### People, roles, permissions and access control

- **Screens:** `/people`, `/people/:subject`, `/roles`, `/capabilities`, `/scopes`, `/access_review`, `/elevation`, `/sessions`, `/sign-in-links`, `/staff_sources`, `/access-requests`, `/service-accounts`
- **Tables:** `auth.principal`, `auth.principal_identity`, `auth.session`, `auth.directory_role_grant`, `gate.capability_grant`, `gate.capability_pack`, `gate.capability_pack_assignment`, `gate.capability_registry`, `gate.scope`, `gate.grants_version`, `gate.policy_epoch`, `gate.review_decision`, `gate.elevation_request`, `auth.staff_member`, `auth.staff_sync_run`, `auth.service_account`, `auth.api_key`, `gate.access_request`, `gate.role_grant`, `auth.group_role_rule`, `gate.break_glass_notice`
- **Installation values:** `INSTALL_OIDC_ISSUER`, `INSTALL_OIDC_REALM`, `INSTALL_OIDC_CLIENT_ID`, `INSTALL_OIDC_REDIRECT_URIS`, `INSTALL_BROKERED_DIRECTORY`, `INSTALL_STAFF_SOURCE`, `INSTALL_STAFF_SOURCE_LOCATION`, `INSTALL_BROKERED_CLIENT_ID`
- **Measured here:** 55 routes, 0 called by no screen; 31 write routes, 29 with all three proofs; 5 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/access-requests` | `/access-requests` |
| `GET /api/v1/console/navigation` | `/department` |
| `GET /api/v1/govern/access-review` | `/access_review` |
| `GET /api/v1/govern/capabilities` | `/capabilities` |
| `GET /api/v1/govern/data-steward` | `/people`, `/people/:subject` |
| `GET /api/v1/govern/elevation` | `/elevation` |
| `GET /api/v1/govern/elevation/notices` | `/elevation` |
| `GET /api/v1/govern/packs` | `/people/:subject` |
| `GET /api/v1/govern/people` | `/people`, `/people/:subject` |
| `GET /api/v1/govern/roles` | `/roles` |
| `GET /api/v1/govern/roles/group-rules` | `/roles` |
| `GET /api/v1/govern/roles/holders` | `/roles` |
| `GET /api/v1/govern/roles/misconfigurations` | `/roles` |
| `GET /api/v1/govern/scopes` | `/departments`, `/people/:subject`, `/scopes` |
| `GET /api/v1/govern/service-accounts` | `/service-accounts` |
| `GET /api/v1/govern/sessions` | `/sessions` |
| `GET /api/v1/govern/sign-ins` | `/sign-in-links` |
| `GET /api/v1/govern/staff_sources` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/credential` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/guides` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/runs` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/transfers` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/trial` | `/staff_sources` |
| `GET /api/v1/me` | `/` |
| `POST /api/v1/access-requests` | `/access-requests` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` |
| `POST /api/v1/govern/access-review/decisions` | `/access_review` |
| `POST /api/v1/govern/data-steward` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/elevation/requests` | `/elevation` |
| `POST /api/v1/govern/elevation/requests/{request_id}/decision` | `/elevation` |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/grants/several` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/packs/assignment` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/people/disable` | `/departments`, `/people`, `/people/:subject` |
| `POST /api/v1/govern/people/enable` | `/departments`, `/people`, `/people/:subject` |
| `POST /api/v1/govern/roles/appointment` | `/roles` |
| `POST /api/v1/govern/roles/deputy` | `/roles` |
| `POST /api/v1/govern/roles/group-rules` | `/roles` |
| `POST /api/v1/govern/roles/group-rules/retirement` | `/roles` |
| `POST /api/v1/govern/roles/removal` | `/roles` |
| `POST /api/v1/govern/service-accounts` | `/service-accounts` |
| `POST /api/v1/govern/service-accounts/keys` | `/service-accounts` |
| `POST /api/v1/govern/service-accounts/keys/revoke` | `/service-accounts` |
| `POST /api/v1/govern/service-accounts/retire` | `/service-accounts` |
| `POST /api/v1/govern/sessions/end` | `/sessions` |
| `POST /api/v1/govern/sessions/end-several` | `/sessions` |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` |
| `POST /api/v1/govern/staff_sources/connect` | `/staff_sources` |
| `POST /api/v1/govern/staff_sources/first-sync` | `/staff_sources` |
| `POST /api/v1/govern/staff_sources/first-sync/apply` | `/staff_sources` |
| `POST /api/v1/govern/staff_sources/test` | `/staff_sources` |
| `POST /api/v1/govern/staff_sources/transfers/{agent_id}` | `/staff_sources` |
| `POST /api/v1/sign-ins` | `/sign-in-links` |
| `PUT /api/v1/govern/staff_sources/credential` | `/staff_sources` |

- **Gap.** A pack cannot be assigned or withdrawn, and a capability that arrived through a pack cannot be removed. Recorded: No route writes gate.capability_pack_assignment. brain.govern_routes.remove_grant refuses a pack's capability in the ordinary words, because withdrawing it removes every other capability in the pack.
- **Gap.** Roles, capabilities and scopes are read and never changed. Recorded: No route writes gate.scope or the role and capability registries; they are declared by the product and by migrations.
- **Gap.** A break-glass notice to the standing Super Admins is shown on their Elevation screen and is not sent by email or chat, and nobody is told when somebody only asks. Recorded: Nothing records a Super Admin's email address or chat identity for a notice to be sent to: auth.principal holds no address and principal_identity holds digests. The notice is written in the approval's transaction to gate.break_glass_notice and read by its recipient; a request is not an elevation until it is approved.
- **Gap.** The identity provider and the staff source cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.
- **Gap.** A service account's end date and owner cannot be changed from Service accounts: no route writes auth.service_account after registration, so a new account is registered instead. Open leaf `M27.15.26`.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/access-requests` | `/access-requests` | `test_a_request_is_stored_and_its_owner_reads_it_back_as_the_application_role` in `tests/unit/test_access_request_store.py` (database, in CI) | Not applicable: A request changes nothing anybody holds: it is a row addressed to its owner, and a decision is a grant written on the Roles screen, which is recorded there. | `test_the_owner_reads_the_requests_addressed_to_them_and_nobody_else_does` in `tests/unit/test_access_request_routes.py` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) |
| `POST /api/v1/govern/access-review/decisions` | `/access_review` | `test_several_holdings_are_decided_one_at_a_time_each_by_the_single_decisions_question` in `tests/unit/test_govern_people_routes.py` | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) |
| `POST /api/v1/govern/data-steward` | `/people`, `/people/:subject` | `test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice` in `tests/unit/test_data_steward_routes.py` (database, in CI) | `test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it` in `tests/unit/test_data_steward.py` (database, in CI) | `test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot` in `tests/unit/test_data_steward.py` (database, in CI) |
| `POST /api/v1/govern/elevation/requests` | `/elevation` | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) |
| `POST /api/v1/govern/elevation/requests/{request_id}/decision` | `/elevation` | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/grants/several` | `/people`, `/people/:subject` | `test_a_grant_to_several_is_written_for_everybody_or_for_nobody_against_postgresql` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_to_several_is_written_for_everybody_or_for_nobody_against_postgresql` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/packs/assignment` | `/people`, `/people/:subject` | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) |
| `POST /api/v1/govern/people/disable` | `/departments`, `/people`, `/people/:subject` | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) |
| `POST /api/v1/govern/people/enable` | `/departments`, `/people`, `/people/:subject` | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) | `test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants` in `tests/unit/test_principal_state.py` (database, in CI) |
| `POST /api/v1/govern/roles/appointment` | `/roles` | `test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason` in `tests/unit/test_role_grant.py` (database, in CI) | `test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason` in `tests/unit/test_role_grant.py` (database, in CI) | `test_the_last_two_super_admins_cannot_be_reduced_to_one` in `tests/unit/test_role_grant.py` |
| `POST /api/v1/govern/roles/deputy` | `/roles` | `test_the_guard_keeps_deputies_depth_one_and_the_table_keeps_them_bounded` in `tests/unit/test_role_grant.py` (database, in CI) | `test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason` in `tests/unit/test_role_grant.py` (database, in CI) | `test_a_deputy_covers_a_standing_holder_and_never_another_deputy` in `tests/unit/test_role_grant.py` |
| `POST /api/v1/govern/roles/group-rules` | `/roles` | `test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger` in `tests/unit/test_group_sync.py` (database, in CI) | `test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger` in `tests/unit/test_group_sync.py` (database, in CI) | `test_a_sign_in_writes_and_removes_synced_rows_and_the_ledger_records_both` in `tests/unit/test_group_sync.py` (database, in CI) |
| `POST /api/v1/govern/roles/group-rules/retirement` | `/roles` | `test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger` in `tests/unit/test_group_sync.py` (database, in CI) | `test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger` in `tests/unit/test_group_sync.py` (database, in CI) | `test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger` in `tests/unit/test_group_sync.py` (database, in CI) |
| `POST /api/v1/govern/roles/removal` | `/roles` | `test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason` in `tests/unit/test_role_grant.py` (database, in CI) | `test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason` in `tests/unit/test_role_grant.py` (database, in CI) | `test_the_guard_refuses_a_removal_below_the_floor_and_allows_one_above_it` in `tests/unit/test_role_grant.py` (database, in CI) |
| `POST /api/v1/govern/service-accounts` | `/service-accounts` | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) |
| `POST /api/v1/govern/service-accounts/keys` | `/service-accounts` | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) | `test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner` in `tests/unit/test_service_accounts.py` (database, in CI) |
| `POST /api/v1/govern/service-accounts/keys/revoke` | `/service-accounts` | `test_a_retired_key_or_account_is_not_found_by_the_request_path` in `tests/unit/test_service_accounts.py` (database, in CI) | **None.** Revoking a key sets its deleted_at and records no credential write, so brain.identity.service_account_store.revoke_key leaves no ledger entry naming who revoked it. | `test_a_retired_key_or_account_is_not_found_by_the_request_path` in `tests/unit/test_service_accounts.py` (database, in CI) |
| `POST /api/v1/govern/service-accounts/retire` | `/service-accounts` | `test_a_retired_key_or_account_is_not_found_by_the_request_path` in `tests/unit/test_service_accounts.py` (database, in CI) | **None.** Retiring an account sets deleted_at on it and its keys and records no credential write, so brain.identity.service_account_store.retire leaves no ledger entry naming who retired it. | `test_a_retired_key_or_account_is_not_found_by_the_request_path` in `tests/unit/test_service_accounts.py` (database, in CI) |
| `POST /api/v1/govern/sessions/end` | `/sessions` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) |
| `POST /api/v1/govern/sessions/end-several` | `/sessions` | `test_several_sessions_are_ended_one_at_a_time_each_decided_by_the_single_endings_question` in `tests/unit/test_session_routes.py` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) |
| `POST /api/v1/govern/staff_sources/connect` | `/staff_sources` | `test_connecting_keeps_the_credential_in_its_slot_saves_two_settings_and_echoes_nothing` in `tests/unit/test_staff_connect.py` | `test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds` in `tests/unit/test_credential_writes.py` (database, in CI) | `test_a_source_saved_on_the_screen_is_the_source_the_worker_reads_with_no_server_edit` in `tests/unit/test_staff_sync_run.py` |
| `POST /api/v1/govern/staff_sources/first-sync` | `/staff_sources` | Not applicable: The first sync's dry run reads the directory and the roster and writes nothing. | Not applicable: A dry run is not a change to the system, so there is nothing to record. | `test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed` in `tests/unit/test_staff_connect.py` |
| `POST /api/v1/govern/staff_sources/first-sync/apply` | `/staff_sources` | `test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed` in `tests/unit/test_staff_connect.py` | Not applicable: Applying the first sync is the nightly run started now, and a run is recorded on its own row in auth.staff_sync_run, which the screen lists; no ledger member records a roster run. | `test_the_night_that_marks_a_leaver_stops_their_agents_and_nobody_elses` in `tests/unit/test_staff_sync_store.py` (database, in CI) |
| `POST /api/v1/govern/staff_sources/test` | `/staff_sources` | Not applicable: A connection test keeps nothing: no setting, no credential and no member is written. | Not applicable: A connection test is not a change to the system, so there is nothing to record. | `test_the_test_route_keeps_nothing_and_never_sends_the_secret_back` in `tests/unit/test_staff_connect.py` |
| `POST /api/v1/govern/staff_sources/transfers/{agent_id}` | `/staff_sources` | `test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach` in `tests/unit/test_staff_sync_routes.py` | `test_the_owner_change_trigger_writes_the_details_the_recorder_writes` in `tests/unit/test_staff_connect.py` | `test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach` in `tests/unit/test_staff_sync_routes.py` |
| `POST /api/v1/sign-ins` | `/sign-in-links` | `test_binding_the_same_subject_twice_writes_one_row` in `tests/unit/test_sign_in_binding.py` (database, in CI) | `test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after` in `tests/unit/test_sign_in_binding.py` (database, in CI) |
| `PUT /api/v1/govern/staff_sources/credential` | `/staff_sources` | `test_the_credential_is_replaced_into_its_slot_recorded_and_never_sent_back` in `tests/unit/test_staff_sync_routes.py` | `test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds` in `tests/unit/test_credential_writes.py` (database, in CI) | `test_a_scheduled_run_reads_lark_with_the_kept_credential_and_applies_the_plan` in `tests/unit/test_staff_sync_run.py` |
