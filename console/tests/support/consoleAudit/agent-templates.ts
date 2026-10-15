/**
 * What the console audit holds about the `agent-templates` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { installApiPath } from "../../../src/pages/agent-templates/AgentTemplateDetailPage";
import { IMPORT_API_PATH, undoApiPath, withdrawalApiPath } from "../../../src/pages/agent-templates/templateTransferQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/agent-templates/AgentTemplateDetailPage.tsx installApiPath(entry.template_id, entry.version)": [
    at(
      "POST /api/v1/agent-templates/{template_id}/versions/{version}/install",
      "installApiPath",
      installApiPath("pricing_desk", 3),
    ),
  ],
  "src/pages/agent-templates/TemplateTransfer.tsx withdrawalApiPath(templateId, version)": [
    at(
      "POST /api/v1/agent-templates/{template_id}/versions/{version}/withdrawal",
      "withdrawalApiPath",
      withdrawalApiPath("pricing_desk", 2),
    ),
  ],
  "src/pages/agent-templates/TemplateTransfer.tsx undoApiPath(templateId, version)": [
    at(
      "POST /api/v1/agent-templates/{template_id}/versions/{version}/withdrawal/undo",
      "undoApiPath",
      undoApiPath("pricing_desk", 2),
    ),
  ],
  "src/pages/agent-templates/TemplateTransfer.tsx undoApiPath(one.template_id, one.version)": [
    at(
      "POST /api/v1/agent-templates/{template_id}/versions/{version}/withdrawal/undo",
      "undoApiPath",
      undoApiPath("pricing_desk", 2),
    ),
  ],
  "src/pages/agent-templates/TemplateTransfer.tsx IMPORT_API_PATH": [
    at("POST /api/v1/agent-template-imports", "IMPORT_API_PATH", IMPORT_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/agent-templates/{template_id}/versions/{version}/install": {
    row: t("test_agent_lifecycle_routes", "test_an_installed_version_starts_disabled_and_at_shadow_on_every_target"),
    audit: t("test_agent_lifecycle_store", "test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person", true),
    behaviour: t("test_agent_lifecycle_routes", "test_an_installed_version_starts_disabled_and_at_shadow_on_every_target"),
  },
  "POST /api/v1/agent-templates/{template_id}/versions/{version}/withdrawal": {
    row: t("test_template_withdrawal", "test_withdrawing_and_undoing_are_each_an_inserted_row_in_the_callers_name"),
    audit: t("test_acceptance_template_withdrawal", "test_on_a_real_database_a_version_is_withdrawn_and_returned_and_nothing_is_left", true),
    behaviour: t("test_agent_routes", "test_a_withdrawn_version_is_not_offered_and_the_one_before_it_is"),
  },
  "POST /api/v1/agent-templates/{template_id}/versions/{version}/withdrawal/undo": {
    row: t("test_template_withdrawal", "test_withdrawing_and_undoing_are_each_an_inserted_row_in_the_callers_name"),
    audit: t("test_acceptance_template_withdrawal", "test_on_a_real_database_a_version_is_withdrawn_and_returned_and_nothing_is_left", true),
    behaviour: t("test_template_withdrawal", "test_with_the_switch_off_withdrawing_exporting_and_importing_are_refused_and_an_undo_is_not"),
  },
  "POST /api/v1/agent-template-imports": {
    row: t("test_template_withdrawal", "test_an_exported_template_is_imported_by_reading_it_then_confirming_the_digest_shown"),
    audit: t("test_acceptance_template_withdrawal", "test_on_a_real_database_a_version_is_withdrawn_and_returned_and_nothing_is_left", true),
    behaviour: t("test_template_withdrawal", "test_an_import_is_refused_where_the_document_is_not_the_one_shown_or_not_what_it_says"),
  },
};
