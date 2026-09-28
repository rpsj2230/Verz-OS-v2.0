/**
 * What the console audit holds about the `agent-templates` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { installApiPath } from "../../../src/pages/agent-templates/AgentTemplateDetailPage";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/agent-templates/AgentTemplateDetailPage.tsx installApiPath(entry.template_id, entry.version)": [
    at(
      "POST /api/v1/agent-templates/{template_id}/versions/{version}/install",
      "installApiPath",
      installApiPath("pricing_desk", 3),
    ),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/agent-templates/{template_id}/versions/{version}/install": {
    row: t("test_agent_lifecycle_routes", "test_an_installed_version_starts_disabled_and_at_shadow_on_every_target"),
    audit: t("test_agent_lifecycle_store", "test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person", true),
    behaviour: t("test_agent_lifecycle_routes", "test_an_installed_version_starts_disabled_and_at_shadow_on_every_target"),
  },
};
