/**
 * What the console audit holds about the `install` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { switchPath } from "../../../src/pages/featuresQuery";
import { REHEARSALS_API_PATH } from "../../../src/pages/orchestrationQuery";
import { PLUGINS_API_PATH, verbPath } from "../../../src/pages/pluginsQuery";
import { at, type Proof, type Proofs, SETTINGS_PRESSED, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/install/FeaturesPage.tsx switchPath(row.name)": [at("POST /api/v1/install/features/{name}", "switchPath", switchPath("schedule_control"))],
  "src/pages/install/OrchestrationPanel.tsx REHEARSALS_API_PATH": [at("POST /api/v1/orchestration/weighed-plans", "REHEARSALS_API_PATH", REHEARSALS_API_PATH)],
  "src/pages/install/PluginsPanel.tsx PLUGINS_API_PATH": [at("POST /api/v1/install/plugins", "PLUGINS_API_PATH", PLUGINS_API_PATH)],
  "src/pages/install/PluginsPanel.tsx verbPath(row.plugin_id, verb)": [
    at("POST /api/v1/install/plugins/{plugin_id}/enable", "verbPath", verbPath("stand-in", "enable")),
    at("POST /api/v1/install/plugins/{plugin_id}/disable", "verbPath", verbPath("stand-in", "disable")),
    at("POST /api/v1/install/plugins/{plugin_id}/remove", "verbPath", verbPath("stand-in", "remove")),
  ],
};

const A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK = t(
  "test_acceptance_checks_plugin_registry",
  "test_every_check_passes_on_an_install_and_leaves_nothing",
  true,
);

const A_WEIGHED_PLAN_IS_FOLLOWED_BY_THE_INSTALL_CHECK = t(
  "test_acceptance_checks_orchestration_rehearsal",
  "test_every_check_passes_on_an_install_and_leaves_nothing",
  true,
);

const NO_LEDGER_ENTRY_FOR_A_WEIGHED_PLAN: Proof = {
  none: "ops.fanout_gate is its own record of who weighed which plan and when, written in the session's own name and never edited; weighing a plan changes nobody's access and no configuration, so no ledger entry is appended.",
};

const NO_PLUGIN_LEDGER_ENTRY: Proof = {
  none: "ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list.",
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/install/features/{name}": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused"),
  },
  "POST /api/v1/install/plugins": {
    row: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
    audit: NO_PLUGIN_LEDGER_ENTRY,
    behaviour: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
  },
  "POST /api/v1/install/plugins/{plugin_id}/enable": {
    row: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
    audit: NO_PLUGIN_LEDGER_ENTRY,
    behaviour: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
  },
  "POST /api/v1/install/plugins/{plugin_id}/disable": {
    row: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
    audit: NO_PLUGIN_LEDGER_ENTRY,
    behaviour: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
  },
  "POST /api/v1/install/plugins/{plugin_id}/remove": {
    row: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
    audit: NO_PLUGIN_LEDGER_ENTRY,
    behaviour: A_PLUGIN_ROW_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
  },
  "POST /api/v1/orchestration/weighed-plans": {
    row: A_WEIGHED_PLAN_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
    audit: NO_LEDGER_ENTRY_FOR_A_WEIGHED_PLAN,
    behaviour: A_WEIGHED_PLAN_IS_FOLLOWED_BY_THE_INSTALL_CHECK,
  },
};
