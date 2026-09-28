/**
 * What the console audit holds about the `jobs` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { actionPath } from "../../../src/pages/jobsQuery";
import { at, type Proofs, SETTINGS_PRESSED, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Jobs.tsx actionPath(asked.action, asked.row.control)": [
    at("POST /api/v1/jobs/{name}/pause", "actionPath", actionPath("pause", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/resume", "actionPath", actionPath("resume", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/run", "actionPath", actionPath("run", "spend_report_refresh")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
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
