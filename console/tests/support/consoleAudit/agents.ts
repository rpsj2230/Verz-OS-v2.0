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
import { agentBudgetApiPath } from "../../../src/pages/agents/AgentSpend";
import { memoryDeletionApiPath, memoryEditApiPath, promotionApiPath } from "../../../src/pages/agents/agentMemoryQuery";
import { UNDO_API_PATH } from "../../../src/pages/learningQuery";
import { agentPreviewApiPath, skillAssignApiPath, skillDetachApiPath } from "../../../src/pages/agents/agentCapabilitiesQuery";
import { agentMoveApiPath } from "../../../src/pages/agentLifecycleQuery";
import { DRAFTS_API_PATH, draftActApiPath, editAsDraftApiPath } from "../../../src/pages/agents/agentDraftsQuery";
import { at, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

/** Each lifecycle move pressed over HTTP against PostgreSQL: the row, and the ledger entry naming who. */
const LIFECYCLE_PRESSED = t(
  "test_agent_lifecycle_store",
  "test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person",
  true,
);

/** A new agent drafted, saved, checked, asked for, approved and published over HTTP against PostgreSQL. */
const DRAFT_APPROVED_PRESSED = t(
  "test_agent_draft_store",
  "test_a_new_agent_is_drafted_approved_by_a_second_person_and_every_step_is_on_the_ledger",
  true,
);
/** An agent edited as a draft and published as the next version of its own template, against PostgreSQL. */
const DRAFT_EDIT_PRESSED = t("test_agent_draft_store", "test_an_edit_published_is_the_next_version_of_the_agents_own_template", true);
const DRAFT_DECLINED_PRESSED = t(
  "test_agent_draft_store",
  "test_a_publish_sent_back_is_one_row_and_one_entry_and_makes_no_agent",
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

/** `tests/unit/test_acceptance_promotion.py`, which runs the promotion check against PostgreSQL. */
const A_RULE_IS_PROMOTED = t(
  "test_acceptance_promotion",
  "test_on_a_real_database_the_promotion_check_passes_and_leaves_nothing",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/agents/AgentCapabilities.tsx path": [
    at("POST /api/v1/skills/{digest}/assignments", "skillAssignApiPath", skillAssignApiPath("d".repeat(64))),
    at("POST /api/v1/skills/{digest}/detachments", "skillDetachApiPath", skillDetachApiPath("d".repeat(64))),
  ],
  "src/pages/agents/AgentCapabilities.tsx agentPreviewApiPath(agentId)": [
    at("POST /api/v1/agents/{agent_id}/preview", "agentPreviewApiPath", agentPreviewApiPath("quote-helper")),
  ],
  "src/pages/agents/AgentMemory.tsx memoryDeletionApiPath(agentId, one.item.memoryId)": [
    at("POST /api/v1/agents/{agent_id}/memory/{memory_id}/deletion", "memoryDeletionApiPath", memoryDeletionApiPath("quote-helper", "m1")),
  ],
  "src/pages/agents/AgentMemory.tsx memoryEditApiPath(agentId, one.item.memoryId)": [
    at("POST /api/v1/agents/{agent_id}/memory/{memory_id}/edit", "memoryEditApiPath", memoryEditApiPath("quote-helper", "m1")),
  ],
  "src/pages/agents/AgentMemory.tsx UNDO_API_PATH": [at("POST /api/v1/govern/learning/undo", "UNDO_API_PATH", UNDO_API_PATH)],
  "src/pages/agents/AgentMemory.tsx promotionApiPath(one.memoryId)": [
    at("POST /api/v1/learning/{memory_id}/promote", "promotionApiPath", promotionApiPath("lr_one")),
  ],
  "src/pages/agents/AgentSpend.tsx agentBudgetApiPath(agentId)": [
    at("PUT /api/v1/agents/{agent_id}/budget", "agentBudgetApiPath", agentBudgetApiPath("quote-helper")),
  ],
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
  "src/pages/agents/DraftStart.tsx DRAFTS_API_PATH": [at("POST /api/v1/agent-drafts", "DRAFTS_API_PATH", DRAFTS_API_PATH)],
  "src/pages/agents/DraftStart.tsx editAsDraftApiPath(from.agentId)": [
    at("POST /api/v1/agents/{agent_id}/drafts", "editAsDraftApiPath", editAsDraftApiPath("quote-helper")),
  ],
  "src/pages/agents/DraftPage.tsx draftActApiPath(draftId, verb)": [
    at("POST /api/v1/agent-drafts/{draft_id}/revisions", "draftActApiPath", draftActApiPath("d-1", "revisions")),
    at("POST /api/v1/agent-drafts/{draft_id}/check", "draftActApiPath", draftActApiPath("d-1", "check")),
    at("POST /api/v1/agent-drafts/{draft_id}/rehearse", "draftActApiPath", draftActApiPath("d-1", "rehearse")),
    at("POST /api/v1/agent-drafts/{draft_id}/procedure", "draftActApiPath", draftActApiPath("d-1", "procedure")),
    at("POST /api/v1/agent-drafts/{draft_id}/publish", "draftActApiPath", draftActApiPath("d-1", "publish")),
    at("POST /api/v1/agent-drafts/{draft_id}/approve", "draftActApiPath", draftActApiPath("d-1", "approve")),
    at("POST /api/v1/agent-drafts/{draft_id}/decline", "draftActApiPath", draftActApiPath("d-1", "decline")),
  ],
  "src/pages/agents/LifecycleActs.tsx path": [
    at("POST /api/v1/agents/{agent_id}/enable", "agentMoveApiPath", agentMoveApiPath("quote-helper", "enable")),
    at("POST /api/v1/agents/{agent_id}/disable", "agentMoveApiPath", agentMoveApiPath("quote-helper", "disable")),
    at("POST /api/v1/agents/{agent_id}/archive", "agentMoveApiPath", agentMoveApiPath("quote-helper", "archive")),
    at("POST /api/v1/agents/{agent_id}/transfer", "agentMoveApiPath", agentMoveApiPath("quote-helper", "transfer")),
    at("POST /api/v1/agents/{agent_id}/duplicate", "agentMoveApiPath", agentMoveApiPath("quote-helper", "duplicate")),
  ],
};

/** An agent's monthly budget set twice over HTTP against PostgreSQL: two versions, two entries naming who. */
const BUDGET_PRESSED = t(
  "test_agent_workspace_routes",
  "test_setting_a_budget_twice_writes_two_versions_and_two_ledger_entries",
  true,
);

/** The steward's correction and the person's delete, pressed over HTTP against PostgreSQL. */
const MEMORY_CHANGED = t(
  "test_agent_memory_routes",
  "test_the_steward_corrects_and_the_person_deletes_and_each_reaches_the_ledger",
  true,
);

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/learning/{memory_id}/promote": {
    row: A_RULE_IS_PROMOTED,
    audit: A_RULE_IS_PROMOTED,
    behaviour: A_RULE_IS_PROMOTED,
  },
  "POST /api/v1/agents/{agent_id}/memory/{memory_id}/deletion": {
    row: MEMORY_CHANGED,
    audit: MEMORY_CHANGED,
    behaviour: t("test_agent_memory_routes", "test_a_memory_the_reader_is_not_shown_cannot_be_deleted_and_is_answered_as_missing"),
  },
  "POST /api/v1/agents/{agent_id}/memory/{memory_id}/edit": {
    row: MEMORY_CHANGED,
    audit: MEMORY_CHANGED,
    behaviour: t("test_agent_memory_routes", "test_a_colleague_shown_a_memory_they_may_not_change_is_told_who_may", true),
  },
  "POST /api/v1/agents/{agent_id}/preview": {
    row: { notApplicable: "A preview writes no row: it asks the gate what one person's run would be handed and keeps nothing." },
    audit: { notApplicable: "A preview changes nothing, so there is nothing for the ledger to record." },
    behaviour: t("test_agent_capability_routes", "test_a_previewer_who_may_not_read_grants_is_answered_as_a_missing_agent"),
  },
  "PUT /api/v1/agents/{agent_id}/budget": {
    row: BUDGET_PRESSED,
    audit: BUDGET_PRESSED,
    behaviour: t("test_agent_workspace_routes", "test_a_caller_without_the_budget_role_over_the_agents_department_is_told_which_role"),
  },
  "PUT /api/v1/agents/{agent_id}/model-pin": {
    row: t("test_agent_model_routes", "test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent"),
    audit: {
      none: "An agent's pin is logged and not written to the audit ledger in this release.",
      leaf: "M5.7.3",
    },
    behaviour: t("test_model_calls", "test_a_pinned_model_is_tried_first_even_from_another_tier"),
  },
  "POST /api/v1/agent-drafts": {
    row: DRAFT_APPROVED_PRESSED,
    audit: DRAFT_APPROVED_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_new_draft_starts_from_the_blank_template_under_an_id_minted_for_it"),
  },
  "POST /api/v1/agents/{agent_id}/drafts": {
    row: DRAFT_EDIT_PRESSED,
    audit: DRAFT_EDIT_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_an_edit_starts_from_the_agent_as_it_is_and_an_instruction_change_publishes_at_once"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/revisions": {
    row: DRAFT_APPROVED_PRESSED,
    audit: DRAFT_APPROVED_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_save_is_a_new_revision_and_a_save_from_an_older_one_is_refused"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/check": {
    row: DRAFT_APPROVED_PRESSED,
    audit: DRAFT_APPROVED_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_check_that_passes_is_recorded_and_a_publish_needs_one"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/rehearse": {
    row: { notApplicable: "A rehearsal writes no row: it runs the draft through the gate at Shadow, carries nothing out and keeps nothing." },
    audit: { notApplicable: "A rehearsal changes nothing, so there is nothing for the ledger to record." },
    behaviour: t("test_agent_builder_routes", "test_a_rehearsal_says_what_it_did_not_do_and_carries_no_row"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/procedure": {
    row: { notApplicable: "Drawing a procedure keeps nothing: the server answers the skill document, and it enters the library only through the Skills page's own import and review." },
    audit: { notApplicable: "Nothing is written, so there is nothing for the ledger to record." },
    behaviour: t("test_agent_builder_routes", "test_a_procedure_over_the_drafts_own_tools_becomes_a_skill_and_another_tool_is_refused"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/publish": {
    row: DRAFT_EDIT_PRESSED,
    audit: DRAFT_EDIT_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_new_agent_reaching_nothing_publishes_on_its_authors_word_switched_off_at_shadow"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/approve": {
    row: DRAFT_APPROVED_PRESSED,
    audit: DRAFT_APPROVED_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_new_agent_that_reaches_anything_waits_for_a_second_person_who_is_not_its_author"),
  },
  "POST /api/v1/agent-drafts/{draft_id}/decline": {
    row: DRAFT_DECLINED_PRESSED,
    audit: DRAFT_DECLINED_PRESSED,
    behaviour: t("test_agent_builder_routes", "test_a_publish_sent_back_publishes_nothing_and_returns_to_its_author"),
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
