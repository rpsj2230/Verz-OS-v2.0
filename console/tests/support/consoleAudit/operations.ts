/**
 * What the console audit holds about the `operations` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { EXPORTS_API_PATH } from "../../../src/pages/dataTransferQuery";
import { actionPath } from "../../../src/pages/jobsQuery";
import { LEARNING_SETTINGS_API_PATH } from "../../../src/pages/learningQuery";
import { TUNING_API_PATH, knobPath } from "../../../src/pages/tuningQuery";
import { at, type Proofs, SETTINGS_PRESSED, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/operations/DataTransferPage.tsx EXPORTS_API_PATH": [at("POST /api/v1/data-transfer/exports", "EXPORTS_API_PATH", EXPORTS_API_PATH)],
  "src/pages/operations/JobActs.tsx actionPath(asked.action, asked.row.control)": [
    at("POST /api/v1/jobs/{name}/pause", "actionPath", actionPath("pause", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/resume", "actionPath", actionPath("resume", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/run", "actionPath", actionPath("run", "spend_report_refresh")),
  ],
  // One card, two screens: the Rate limits screen's knobs and the Learning screen's (M16.6.8).
  "src/pages/operations/LimitSettings.tsx knobPath(screen.path, knob.name)": [
    at("PUT /api/v1/install/tuning/{name}", "knobPath", knobPath(TUNING_API_PATH, "person_per_minute")),
    at("PUT /api/v1/govern/learning/settings/{name}", "knobPath", knobPath(LEARNING_SETTINGS_API_PATH, "inferred_memory_half_life_days")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/install/tuning/{name}": {
    row: t("test_tuning", "test_saving_a_window_writes_its_row_as_the_person_and_the_next_request_counts_against_it"),
    audit: t("test_acceptance_capacity", "test_on_a_real_database_the_capacity_checks_pass_or_say_why_not_and_leave_nothing_behind", true),
    behaviour: t("test_tuning", "test_every_reload_of_saved_settings_holds_the_saved_limits_and_names_a_changed_one", true),
  },
  "PUT /api/v1/govern/learning/settings/{name}": {
    row: t("test_learning_settings", "test_saving_a_half_life_writes_its_row_as_the_person_and_the_next_recall_decays_at_it"),
    audit: t("test_acceptance_learning", "test_on_a_real_database_every_learning_check_passes_and_leaves_nothing_behind", true),
    behaviour: t("test_learning_settings", "test_a_held_half_life_is_the_rate_every_recall_decays_an_inference_at"),
  },
  "POST /api/v1/data-transfer/exports": {
    row: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    audit: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    behaviour: t("test_data_transfer_routes", "test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own"),
  },
  "POST /api/v1/jobs/{name}/pause": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started"),
  },
  "POST /api/v1/jobs/{name}/resume": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started"),
  },
  "POST /api/v1/jobs/{name}/run": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused"),
  },
};
