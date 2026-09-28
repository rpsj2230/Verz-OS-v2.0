/**
 * What the console audit holds about the `automations` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { changeApiPath } from "../../../src/pages/automations/automationsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

/** Every write route a screen sends, followed to the system. */
const AUTOMATION_PAUSED = t(
  "test_automation_change_store",
  "test_a_paused_automation_does_not_run_on_the_next_tick_and_the_ledger_says_who",
  true,
);

const AUTOMATION_ADOPTED_AND_RESUMED = t(
  "test_automation_change_store",
  "test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter",
  true,
);

const AUTOMATION_RESCHEDULED = t(
  "test_automation_change_store",
  "test_a_schedule_change_moves_the_next_run_and_the_runner_keeps_to_the_new_cadence",
  true,
);

const AUTOMATION_REMOVED = t(
  "test_automation_change_store",
  "test_a_removed_automation_never_runs_again_and_cannot_be_started_from_its_agent",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/automations/AutomationActs.tsx changeApiPath(detail.row.id, act)": [
    at("POST /api/v1/automations/{automation_id}/pause", "changeApiPath", changeApiPath("auto_one", "pause")),
    at("POST /api/v1/automations/{automation_id}/resume", "changeApiPath", changeApiPath("auto_one", "resume")),
    at("POST /api/v1/automations/{automation_id}/reschedule", "changeApiPath", changeApiPath("auto_one", "reschedule")),
    at("POST /api/v1/automations/{automation_id}/remove", "changeApiPath", changeApiPath("auto_one", "remove")),
    at("POST /api/v1/automations/{automation_id}/adopt", "changeApiPath", changeApiPath("auto_one", "adopt")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/automations/{automation_id}/pause": {
    row: AUTOMATION_PAUSED,
    audit: AUTOMATION_PAUSED,
    behaviour: AUTOMATION_PAUSED,
  },
  "POST /api/v1/automations/{automation_id}/resume": {
    row: AUTOMATION_ADOPTED_AND_RESUMED,
    audit: AUTOMATION_ADOPTED_AND_RESUMED,
    behaviour: AUTOMATION_ADOPTED_AND_RESUMED,
  },
  "POST /api/v1/automations/{automation_id}/reschedule": {
    row: AUTOMATION_RESCHEDULED,
    audit: AUTOMATION_RESCHEDULED,
    behaviour: AUTOMATION_RESCHEDULED,
  },
  "POST /api/v1/automations/{automation_id}/remove": {
    row: AUTOMATION_REMOVED,
    audit: AUTOMATION_REMOVED,
    behaviour: AUTOMATION_REMOVED,
  },
  "POST /api/v1/automations/{automation_id}/adopt": {
    row: AUTOMATION_ADOPTED_AND_RESUMED,
    audit: AUTOMATION_ADOPTED_AND_RESUMED,
    behaviour: t("test_automations_routes", "test_an_ownerless_automation_is_adopted_in_the_adopters_name_and_stays_paused"),
  },
};
