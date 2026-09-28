### AI providers, models and the routing between them

- **Screens:** `/models`, `/routing`, `/routing/:rungId`
- **Tables:** `ops.routing_rung`, `ops.routing_tier`, `ops.model_attempt`, `ops.model_provider`, `ops.golden_question`, `ops.routing_change`, `ops.provider_health`, `ops.chain_depth_alert`, `ops.residency_constraint`
- **Installation values:** `INSTALL_MODEL_PROFILE`, `INSTALL_MODEL_ENDPOINT`, `INSTALL_EMBEDDING_DIMENSIONS`
- **Measured here:** 21 routes, 0 called by no screen; 14 write routes, 4 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/models/providers` | `/models` |
| `GET /api/v1/models/providers-register` | `/models` |
| `GET /api/v1/operate/models` | `/models` |
| `GET /api/v1/routing/changes` | `/routing`, `/routing/:rungId` |
| `GET /api/v1/routing/golden-questions` | `/routing`, `/routing/:rungId` |
| `GET /api/v1/routing/golden-questions/askers` | `/routing` |
| `GET /api/v1/routing/rungs` | `/agents/:agentId`, `/routing`, `/routing/:rungId` |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` |
| `POST /api/v1/models/providers` | `/models` |
| `POST /api/v1/models/providers/{provider}/check` | `/models` |
| `POST /api/v1/models/providers/{provider}/retire` | `/models` |
| `POST /api/v1/models/residency` | `/models` |
| `POST /api/v1/models/residency/{constraint_id}/retire` | `/models` |
| `POST /api/v1/models/tiers/{tier}/reset` | `/models` |
| `POST /api/v1/routing/golden-questions` | `/routing`, `/routing/:rungId` |
| `POST /api/v1/routing/golden-questions/{question_id}/retire` | `/routing`, `/routing/:rungId` |
| `POST /api/v1/routing/rungs` | `/routing`, `/routing/:rungId` |
| `PUT /api/v1/models/profile` | `/models` |
| `PUT /api/v1/models/providers/{provider}` | `/models` |
| `PUT /api/v1/models/providers/{provider}/terms` | `/models` |
| `PUT /api/v1/models/tiers/{tier}` | `/models` |

- **Gap.** A provider's terms and an added provider's retirement are logged and not on the audit ledger: the ledger's action list gains no provider entry in this release. Open leaf `M5.6.4`.
- **Gap.** The model endpoint cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` | `test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_rung_saved_on_the_routing_screen_is_the_rung_the_next_call_walks` in `tests/unit/test_provider_routes.py` (database, in CI) |
| `POST /api/v1/models/providers` | `/models` | `test_an_added_provider_has_its_key_kept_in_its_own_slot_before_its_row_is_written` in `tests/unit/test_provider_registry_routes.py` | `test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace` in `tests/unit/test_credential_routes.py` | `test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release` in `tests/unit/test_model_calls.py` |
| `POST /api/v1/models/providers/{provider}/check` | `/models` | `test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question` in `tests/unit/test_provider_routes.py` | Not applicable: A check changes no setting and no record an administrator manages; it is a metered call on the request ledger, not a change to audit. | `test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question` in `tests/unit/test_provider_routes.py` |
| `POST /api/v1/models/providers/{provider}/retire` | `/models` | `test_an_added_provider_is_retired_and_a_built_in_one_cannot_be` in `tests/unit/test_provider_registry_routes.py` | **None.** Retiring an added provider is logged and not written to the audit ledger in this release. Leaf `M5.6.4`. | `test_a_provider_with_no_driver_is_told_which_of_the_two_things_is_missing` in `tests/unit/test_model_assembly.py` |
| `POST /api/v1/models/residency` | `/models` | `test_a_residency_constraint_is_written_with_its_scope_and_regions` in `tests/unit/test_model_health_routes.py` | **None.** A residency constraint is logged and not written to the audit ledger in this release. Leaf `M5.5.1`. | `test_a_reach_touching_a_constrained_scope_skips_the_rung_outside_its_regions` in `tests/unit/test_model_calls.py` |
| `POST /api/v1/models/residency/{constraint_id}/retire` | `/models` | `test_retiring_a_constraint_marks_it_retired_and_deletes_nothing` in `tests/unit/test_model_health_routes.py` | **None.** Retiring a residency constraint is logged and not written to the audit ledger in this release. Leaf `M5.5.1`. | `test_a_reach_with_nowhere_compliant_is_refused_and_one_elsewhere_is_answered` in `tests/unit/test_model_calls.py` |
| `POST /api/v1/models/tiers/{tier}/reset` | `/models` | `test_a_reset_retires_the_row_so_the_tier_runs_at_the_product_default` in `tests/unit/test_model_health_routes.py` | **None.** Resetting a tier is logged and not written to the audit ledger in this release. Leaf `M5.2.2`. | `test_a_tier_with_no_row_runs_at_the_compiled_numbers_and_is_not_marked_configured` in `tests/unit/test_tier_rules.py` |
| `POST /api/v1/routing/golden-questions` | `/routing`, `/routing/:rungId` | `test_a_golden_question_is_recorded_only_as_a_principal_the_directory_holds` in `tests/unit/test_routing_routes.py` | **None.** A golden question is a check the matrix gate asks and is logged, not written to the audit ledger; the changes it holds are recorded in ops.routing_change. Leaf `M5.6.2`. | `test_a_change_that_stops_the_ladder_answering_is_held_with_the_failing_question_shown` in `tests/unit/test_matrix_gate.py` |
| `POST /api/v1/routing/golden-questions/{question_id}/retire` | `/routing`, `/routing/:rungId` | `test_a_retired_golden_question_is_marked_retired_and_asked_no_more` in `tests/unit/test_routing_routes.py` | **None.** Retiring a golden question is logged, not written to the audit ledger. Leaf `M5.6.2`. | `test_a_gate_with_no_golden_questions_holds_the_change_and_says_to_record_some` in `tests/unit/test_matrix_gate.py` |
| `POST /api/v1/routing/rungs` | `/routing`, `/routing/:rungId` | `test_a_rung_is_added_at_the_end_of_its_tier_only_through_the_gate` in `tests/unit/test_routing_routes.py` | `test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release` in `tests/unit/test_model_calls.py` |
| `PUT /api/v1/models/profile` | `/models` | `test_where_answers_are_made_is_saved_by_the_super_administrator_ledgered_and_planned_at_once` in `tests/unit/test_provider_routes.py` | **None.** The route sets the audit attribution 0059's trigger reads, which the row test asserts over a stub; no scratch-Postgres test yet reads the ledger entry back. | `test_where_answers_are_made_is_saved_by_the_super_administrator_ledgered_and_planned_at_once` in `tests/unit/test_provider_routes.py` |
| `PUT /api/v1/models/providers/{provider}` | `/models` | `test_the_stores_read_the_ladder_write_attempts_by_id_and_keep_a_switch` in `tests/unit/test_model_service.py` (database, in CI) | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_switching_a_provider_off_takes_its_rungs_out_of_the_next_plan_at_once` in `tests/unit/test_provider_routes.py` |
| `PUT /api/v1/models/providers/{provider}/terms` | `/models` | `test_terms_recorded_for_a_built_in_provider_write_its_first_registry_row` in `tests/unit/test_provider_registry_routes.py` | **None.** A provider's terms are logged and not written to the audit ledger in this release. Leaf `M5.6.4`. | `test_a_constrained_call_skips_an_undocumented_rung_for_the_documented_one_behind_it` in `tests/unit/test_model_calls.py` |
| `PUT /api/v1/models/tiers/{tier}` | `/models` | `test_a_tier_rule_is_written_as_the_window_and_only_the_keys_the_router_reads` in `tests/unit/test_model_health_routes.py` | **None.** A tier's numbers are logged and not written to the audit ledger in this release. Leaf `M5.2.2`. | `test_a_request_is_classified_against_the_tier_table_the_ladder_read` in `tests/unit/test_model_calls.py` |
