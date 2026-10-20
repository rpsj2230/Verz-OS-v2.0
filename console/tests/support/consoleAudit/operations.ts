/**
 * What the console audit holds about the `operations` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { EXPORTS_API_PATH } from "../../../src/pages/dataTransferQuery";
import { ACKNOWLEDGE_API_PATH } from "../../../src/pages/incidentsQuery";
import { actionPath, redrivePath } from "../../../src/pages/jobsQuery";
import { LEARNING_SETTINGS_API_PATH } from "../../../src/pages/learningQuery";
import { HALTS_API_PATH, RESUME_API_PATH } from "../../../src/pages/stopQuery";
import { REHEARSAL_ASK_PATH } from "../../../src/pages/installQuery";
import { TUNING_API_PATH, knobPath } from "../../../src/pages/tuningQuery";
import { at, type Proofs, SETTINGS_PRESSED, t, type WriteRoute } from "../auditClaims";

/**
 * A stop and its resume on PostgreSQL as the application role: the wordless stop's row and its
 * ledger entry naming the reach and the trace, the resume refused without words, and the row and
 * entry it leaves when it has them (M27.15.10, M27.15.15).
 */
const A_STOP_AND_ITS_RESUME_ARE_ROWS_AND_ENTRIES = t(
  "test_halt_store",
  "test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/operations/RecoveryPage.tsx REHEARSAL_ASK_PATH": [at("POST /api/v1/install/recovery/rehearsal", "REHEARSAL_ASK_PATH", REHEARSAL_ASK_PATH)],
  "src/pages/operations/StopControl.tsx HALTS_API_PATH": [at("POST /api/v1/halts", "HALTS_API_PATH", HALTS_API_PATH)],
  "src/pages/operations/StopPage.tsx HALTS_API_PATH": [at("POST /api/v1/halts", "HALTS_API_PATH", HALTS_API_PATH)],
  "src/pages/operations/StopPage.tsx RESUME_API_PATH": [at("POST /api/v1/halts/resume", "RESUME_API_PATH", RESUME_API_PATH)],
  "src/pages/operations/DataTransferPage.tsx EXPORTS_API_PATH": [at("POST /api/v1/data-transfer/exports", "EXPORTS_API_PATH", EXPORTS_API_PATH)],
  "src/pages/operations/JobActs.tsx actionPath(asked.action, asked.row.control)": [
    at("POST /api/v1/jobs/{name}/pause", "actionPath", actionPath("pause", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/resume", "actionPath", actionPath("resume", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/run", "actionPath", actionPath("run", "spend_report_refresh")),
  ],
  "src/pages/operations/JobsPage.tsx redrivePath(row.job_id)": [
    at("POST /api/v1/jobs/dead/{job_id}/redrive", "redrivePath", redrivePath("41")),
  ],
  "src/pages/operations/IncidentsPage.tsx ACKNOWLEDGE_API_PATH": [
    at("POST /api/v1/console/incidents/acknowledgement", "ACKNOWLEDGE_API_PATH", ACKNOWLEDGE_API_PATH),
  ],
  // One card, two screens: the Rate limits screen's knobs and the Learning screen's (M16.6.8).
  "src/pages/operations/LimitSettings.tsx knobPath(screen.path, knob.name)": [
    at("PUT /api/v1/install/tuning/{name}", "knobPath", knobPath(TUNING_API_PATH, "person_per_minute")),
    at("PUT /api/v1/govern/learning/settings/{name}", "knobPath", knobPath(LEARNING_SETTINGS_API_PATH, "inferred_memory_half_life_days")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/install/recovery/rehearsal": {
    row: {
      notApplicable:
        "The write is one small request object in the backup bucket and no table row, because a rehearsal must be askable on the day the database is the thing being rehearsed.",
    },
    audit: {
      none: "Asking for a rehearsal changes nobody's access and no configuration, so it has no ledger entry; the route logs who pressed it and the request names them until the server answers it.",
    },
    behaviour: t(
      "test_acceptance_checks_backup_drill",
      "test_every_check_passes_on_an_install_that_has_done_it_and_leaves_nothing",
      true,
    ),
  },
  "POST /api/v1/console/incidents/acknowledgement": {
    row: t("test_acceptance_checks_alert_ack", "test_the_check_passes_on_an_install_and_leaves_nothing", true),
    audit: {
      notApplicable:
        "An acknowledgement changes nobody's access and no configuration, so it has no ledger entry of its own: the ops.alert_acknowledgement row, written once in the presser's own name and refused any rewrite, is the record of who and when.",
    },
    behaviour: t(
      "test_acceptance_checks_alert_ack",
      "test_a_press_open_to_a_reader_of_one_department_fails_the_check",
      true,
    ),
  },
  "POST /api/v1/halts": {
    row: A_STOP_AND_ITS_RESUME_ARE_ROWS_AND_ENTRIES,
    audit: A_STOP_AND_ITS_RESUME_ARE_ROWS_AND_ENTRIES,
    behaviour: t("test_halt_store", "test_a_question_asked_while_everything_is_stopped_is_turned_away_in_the_halt_s_words", true),
  },
  "POST /api/v1/halts/resume": {
    row: A_STOP_AND_ITS_RESUME_ARE_ROWS_AND_ENTRIES,
    audit: A_STOP_AND_ITS_RESUME_ARE_ROWS_AND_ENTRIES,
    behaviour: t("test_halt_store", "test_a_resume_from_the_screen_needs_words_and_says_whose_stop_it_lifts", true),
  },
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
  "POST /api/v1/jobs/dead/{job_id}/redrive": {
    row: t("test_redrive_routes", "test_pressing_run_again_writes_the_instant_the_worker_reads_and_says_who_pressed"),
    audit: t("test_console_control_audit", "test_pressing_run_again_on_a_set_aside_job_reaches_the_row_and_the_ledger", true),
    behaviour: t("test_dead_letter", "test_a_persons_ask_puts_one_job_back_through_the_drivers_retry_and_is_answered_once", true),
  },
  "POST /api/v1/jobs/{name}/run": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused"),
  },
};
