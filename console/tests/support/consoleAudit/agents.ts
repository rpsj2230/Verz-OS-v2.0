/**
 * What the console audit holds about the `agents` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes, and the reads it makes only once somebody acts. `support/consoleAudit.ts`
 * collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { automationStartApiPath, automationStopApiPath } from "../../../src/pages/agentAutomationsQuery";
import {
  automationGalleryApiPath,
  automationInstallApiPath,
  automationPreviewApiPath,
} from "../../../src/pages/automationGalleryQuery";
import { modelPinApiPath } from "../../../src/pages/agentModelPinQuery";
import { agentMoveApiPath } from "../../../src/pages/agentLifecycleQuery";
import { at, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

/** Each lifecycle move pressed over HTTP against PostgreSQL: the row, and the ledger entry naming who. */
const LIFECYCLE_PRESSED = t(
  "test_agent_lifecycle_store",
  "test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person",
  true,
);

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  // The gallery is read when a person opens an agent's Automations section, not when its page opens.
  "GET /api/v1/agents/{agent_id}/automation-templates": {
    screen: "/agents/:agentId/:tab",
    spelled: "automationGalleryApiPath",
    built: automationGalleryApiPath("quote-helper"),
  },
  "GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview": {
    screen: "/agents/:agentId/:tab",
    spelled: "automationPreviewApiPath",
    built: automationPreviewApiPath("quote-helper", "weekly_work_summary"),
  },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/components/AgentModelPin.tsx modelPinApiPath(agentId)": [
    at("PUT /api/v1/agents/{agent_id}/model-pin", "modelPinApiPath", modelPinApiPath("quote-helper")),
  ],
  "src/components/AutomationGallery.tsx automationInstallApiPath(agentId)": [
    at("POST /api/v1/agents/{agent_id}/automations", "automationInstallApiPath", automationInstallApiPath("quote-helper")),
  ],
  "src/components/AgentAutomations.tsx path": [
    at(
      "POST /api/v1/agents/{agent_id}/automations/{automation_id}/start",
      "automationStartApiPath",
      automationStartApiPath("quote-helper", "auto_one"),
    ),
    at(
      "POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop",
      "automationStopApiPath",
      automationStopApiPath("quote-helper", "auto_one"),
    ),
  ],
  "src/pages/agents/LifecycleActs.tsx path": [
    at("POST /api/v1/agents/{agent_id}/enable", "agentMoveApiPath", agentMoveApiPath("quote-helper", "enable")),
    at("POST /api/v1/agents/{agent_id}/disable", "agentMoveApiPath", agentMoveApiPath("quote-helper", "disable")),
    at("POST /api/v1/agents/{agent_id}/archive", "agentMoveApiPath", agentMoveApiPath("quote-helper", "archive")),
    at("POST /api/v1/agents/{agent_id}/transfer", "agentMoveApiPath", agentMoveApiPath("quote-helper", "transfer")),
    at("POST /api/v1/agents/{agent_id}/duplicate", "agentMoveApiPath", agentMoveApiPath("quote-helper", "duplicate")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/agents/{agent_id}/model-pin": {
    row: t("test_agent_model_routes", "test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent"),
    audit: {
      none: "An agent's pin is logged and not written to the audit ledger in this release.",
      leaf: "M5.7.3",
    },
    behaviour: t("test_model_calls", "test_a_pinned_model_is_tried_first_even_from_another_tier"),
  },
  "POST /api/v1/agents/{agent_id}/enable": {
    row: LIFECYCLE_PRESSED,
    audit: LIFECYCLE_PRESSED,
    behaviour: t("test_agent_lifecycle_routes", "test_a_disabled_agent_is_enabled_and_the_store_is_told_who_did_it"),
  },
  "POST /api/v1/agents/{agent_id}/disable": {
    row: LIFECYCLE_PRESSED,
    audit: LIFECYCLE_PRESSED,
    behaviour: t("test_agent_lifecycle_routes", "test_disable_then_archive_each_move_the_agent_once_and_name_the_person"),
  },
  "POST /api/v1/agents/{agent_id}/archive": {
    row: LIFECYCLE_PRESSED,
    audit: LIFECYCLE_PRESSED,
    behaviour: t("test_agent_lifecycle_routes", "test_disable_then_archive_each_move_the_agent_once_and_name_the_person"),
  },
  "POST /api/v1/agents/{agent_id}/transfer": {
    row: LIFECYCLE_PRESSED,
    audit: LIFECYCLE_PRESSED,
    behaviour: t("test_agent_lifecycle_routes", "test_a_transfer_hands_the_agent_to_somebody_here_and_names_who_handed_it"),
  },
  "POST /api/v1/agents/{agent_id}/duplicate": {
    row: LIFECYCLE_PRESSED,
    audit: LIFECYCLE_PRESSED,
    behaviour: t("test_agent_lifecycle_routes", "test_a_duplicate_is_a_new_disabled_agent_from_the_same_version_with_the_same_ceiling"),
  },
  "POST /api/v1/agents/{agent_id}/automations": {
    row: t("test_automation_gallery_routes", "test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context"),
    audit: t("test_agent_automation_store", "test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither", true),
    behaviour: t("test_automation_gallery_routes", "test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context"),
  },
  "POST /api/v1/agents/{agent_id}/automations/{automation_id}/start": {
    row: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    audit: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    behaviour: t("test_automation_schedule_routes", "test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing"),
  },
  "POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop": {
    row: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    audit: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    behaviour: t("test_automation_schedule_routes", "test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot"),
  },
};
