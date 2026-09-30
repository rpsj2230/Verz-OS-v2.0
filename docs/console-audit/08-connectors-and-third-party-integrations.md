### Connectors and third-party integrations

- **Screens:** `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/channels`, `/channels/:name`, `/channels/:name/:view`
- **Tables:** `auth.binding_code`, `ops.channel`, `ops.channel_delivery`, `ops.connector_connection`, `ops.connector_sync`, `proj.record`, `er.alias`, `er.canonical`, `er.identifier`, `er.link`
- **Installation values:** `INSTALL_LARK_USES`, `INSTALL_LARK_PLATFORM`, `INSTALL_LARK_BASE`
- **Measured here:** 35 routes, 4 called by no screen; 16 write routes, 11 with all three proofs; 4 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/channels` | **no screen** |
| `GET /api/v1/channels/{name}/bindings` | `/channels/:name` |
| `GET /api/v1/channels/{name}/deliveries` | `/channels/:name/:view` |
| `GET /api/v1/channels/{name}/events` | **no screen** |
| `GET /api/v1/channels/{name}/health` | `/channels/:name`, `/channels/:name/:view` |
| `GET /api/v1/connectors` | `/`, `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/connectors/lark-app` | `/connectors`, `/staff_sources` |
| `GET /api/v1/connectors/lark-app/wiki-spaces` | **no screen** |
| `GET /api/v1/console/channels` | `/channels` |
| `GET /api/v1/console/channels/{name}` | `/channels/:name`, `/channels/:name/:view` |
| `GET /api/v1/console/channels/{name}/stats` | `/channels`, `/channels/:name` |
| `GET /api/v1/console/connectors` | `/connectors` |
| `GET /api/v1/console/connectors/{connector}` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/console/connectors/{connector}/drift` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/console/connectors/{connector}/export` | `/connectors/:connector` |
| `GET /api/v1/console/connectors/{connector}/probe` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/console/connectors/{connector}/stats` | `/connectors`, `/connectors/:connector` |
| `GET /api/v1/me/channels` | `/me` |
| `POST /api/v1/channels/{name}/bindings/unbind` | `/channels/:name`, `/channels/:name/:view` |
| `POST /api/v1/channels/{name}/events` | **no screen** |
| `POST /api/v1/channels/{name}/switch` | `/channels/:name`, `/channels/:name/:view` |
| `POST /api/v1/channels/{name}/test` | `/channels/:name`, `/channels/:name/:view` |
| `POST /api/v1/connectors` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/first-run` |
| `POST /api/v1/connectors/lark-app` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/lark-app/switch-off` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/lark-app/test` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/lark-app/wiki-spaces` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/{connector}/accept` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/{connector}/edit` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/{connector}/key` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` |
| `POST /api/v1/connectors/{connector}/probe` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/me/channels/{name}/code` | `/me` |
| `POST /api/v1/me/channels/{name}/unbind` | `/me` |
| `PUT /api/v1/channels/{name}` | `/channels/:name`, `/channels/:name/:view` |

- **Gap.** A connected source is read and kept, and no question is answered from what is kept. Recorded: No row tool is registered for a connected source's records: brain.tools.startup.classification_for is keyed on the entity alone and Xero and HubSpot both project contact, which that module records as the limit to change first. brain.ops.connector_admin.WHAT_CONNECTING_A_SOURCE_STARTS says so in the connect confirmation.
- **Gap.** HubSpot can be connected and is not read. Recorded: brain.ops.limits records no verified call ceiling for it and brain.connectors.throttle.limits_for refuses to invent one; its row carries brain.ops.connector_sync.NO_VERIFIED_CEILING.
- **Gap.** Google Drive and the Laravel views cannot be connected from a screen. Recorded: Each needs a visibility rule, a department declaration with an answerable person, or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each. Freshdesk is connected from the screen with its address and the one department that reads it (brain.connectors.freshdesk.ONE_DEPARTMENT_READS_A_CONNECTED_HELPDESK).
- **Gap.** Connect Lark switches knowledge from Wiki and Base on, and no question is answered from Lark yet. Recorded: The Lark knowledge connector that keeps the minimal index and reads pages and records live is still to be built over the settings Connect Lark writes; brain.ops.lark_connect.KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED says so on the screen.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/channels/{name}/bindings/unbind` | `/channels/:name`, `/channels/:name/:view` | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_an_administrator_lists_who_is_bound_and_unbinds_one_and_a_stranger_is_told_nothing` in `tests/unit/test_channel_binding.py` |
| `POST /api/v1/channels/{name}/switch` | `/channels/:name`, `/channels/:name/:view` | `test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_switching_one_channel_off_stops_it_receiving_and_sending_and_leaves_another_alone` in `tests/unit/test_channel_pipeline.py` |
| `POST /api/v1/channels/{name}/test` | `/channels/:name`, `/channels/:name/:view` | `test_a_test_message_is_sent_once_per_record_and_destination` in `tests/unit/test_channel_pipeline.py` | **None.** A test message is recorded in ops.operation under its key and in ops.channel_delivery with its outcome, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION. | `test_a_test_message_is_sent_once_per_record_and_destination` in `tests/unit/test_channel_pipeline.py` |
| `POST /api/v1/connectors` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/first-run` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/connectors/lark-app` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_a_save_keeps_one_credential_in_each_uses_slot_and_switches_them_on` in `tests/unit/test_lark_connect.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_after_a_save_each_use_says_where_it_stands` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/lark-app/switch-off` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_switching_a_use_off_leaves_the_others_on_and_the_key_in_the_vault` in `tests/unit/test_lark_connect.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_switching_the_chat_channel_off_switches_its_record_off_and_keeps_its_ids` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/lark-app/test` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_a_test_records_when_it_ran_and_each_verdict_and_nothing_it_was_sent` in `tests/unit/test_lark_connect.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_the_test_route_reports_each_use_and_writes_nothing` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/lark-app/wiki-spaces` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_declared_spaces_are_kept_in_the_settings_table_and_read_back` in `tests/unit/test_lark_connect.py` (database, in CI) | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_a_space_is_declared_by_its_link_or_its_id_with_the_declarer_as_steward` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/{connector}/accept` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_accepting_a_changed_declaration_keeps_its_text_and_the_ledger_names_both_digests` in `tests/unit/test_connector_store.py` (database, in CI) | `test_accepting_a_changed_declaration_keeps_its_text_and_the_ledger_names_both_digests` in `tests/unit/test_connector_store.py` (database, in CI) | `test_accepting_repins_the_declaration_and_the_source_is_read_again` in `tests/unit/test_connector_routes.py` |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/connectors/{connector}/edit` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_an_edit_leaves_two_rows_one_live_two_ledger_entries_and_no_key_write` in `tests/unit/test_connector_store.py` (database, in CI) | `test_an_edit_leaves_two_rows_one_live_two_ledger_entries_and_no_key_write` in `tests/unit/test_connector_store.py` (database, in CI) | `test_an_edit_leaves_two_rows_one_live_and_the_key_where_it_was` in `tests/unit/test_connector_routes.py` |
| `POST /api/v1/connectors/{connector}/key` | `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/staff_sources` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_replaced_key_is_a_credential_write_and_changes_no_connection` in `tests/unit/test_connector_routes.py` |
| `POST /api/v1/connectors/{connector}/probe` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_a_test_asked_for_is_made_once_with_the_workers_key_and_keeps_nothing` in `tests/unit/test_connector_probe_run.py` (database, in CI) | `test_a_press_is_on_the_ledger_and_a_test_survives_the_downgrade` in `tests/unit/test_connector_probe_run.py` (database, in CI) | `test_a_declined_key_is_recorded_on_the_sources_health_and_the_schedule_is_unmoved` in `tests/unit/test_connector_probe_run.py` (database, in CI) |
| `POST /api/v1/me/channels/{name}/code` | `/me` | `test_a_code_is_kept_spent_once_and_never_brought_back_by_the_application` in `tests/unit/test_channel_binding.py` (database, in CI) | Not applicable: A code binds nothing until its person sends it from a chat, and the binding it then makes is the channel_binding entry 0118's trigger appends; minting one changes nobody's access. | `test_a_person_mints_a_code_in_my_workspace_sends_it_and_is_answered_as_themself` in `tests/unit/test_channel_binding.py` |
| `POST /api/v1/me/channels/{name}/unbind` | `/me` | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_a_person_unbinds_their_own_chat_and_it_is_recorded_as_theirs` in `tests/unit/test_channel_binding.py` |
| `PUT /api/v1/channels/{name}` | `/channels/:name`, `/channels/:name/:view` | `test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_a_channel_is_set_up_with_its_secret_kept_in_the_vault_and_never_sent_back` in `tests/unit/test_channel_pipeline.py` |
