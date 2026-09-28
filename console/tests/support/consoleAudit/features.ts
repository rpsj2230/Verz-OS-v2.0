/**
 * What the console audit holds about the `features` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { switchPath } from "../../../src/pages/featuresQuery";
import { at, type Proofs, SETTINGS_PRESSED, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Features.tsx switchPath(row.name)": [at("POST /api/v1/install/features/{name}", "switchPath", switchPath("schedule_control"))],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/install/features/{name}": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused"),
  },
};
