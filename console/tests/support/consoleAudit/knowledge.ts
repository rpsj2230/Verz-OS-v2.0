/**
 * What the console audit holds about the `knowledge` module (`src/pages/knowledge/`, drawn at
 * `/library`, `/solutions` and `/corrections`): the writes its screens send, each mapped to the routes it reaches,
 * and the tests that follow each route to its row, its ledger entry and what it changes, and the
 * reads it makes only once somebody acts. `support/consoleAudit.ts` collects this file and says why
 * each claim is shaped as it is.
 *
 * Task ids: none
 */

import {
  agentKnowledgeLinkApiPath,
  agentKnowledgeRefetchApiPath,
  agentKnowledgeRetireApiPath,
  agentKnowledgeUploadApiPath,
} from "../../../src/pages/agents/agentKnowledgeQuery";
import { KNOWLEDGE_EXPORT_API_PATH } from "../../../src/pages/knowledge/KnowledgeExport";
import { uploadPath } from "../../../src/pages/knowledgeQuery";
import {
  archivePath,
  correctionDecisionPath,
  newVersionPath,
  passagesPath,
  promotionPath,
  publicPath,
  solutionDecisionPath,
  SOLUTIONS_API_PATH,
  stewardPath,
  taskDonePath,
  verificationPath,
} from "../../../src/pages/knowledgeLifecycleQuery";
import { LINKS_API_PATH, queuedPath } from "../../../src/pages/knowledgeIntakeQuery";
import { historyPath, VERIFICATIONS_API_PATH } from "../../../src/pages/knowledge/knowledgeDocuments";
import { at, type Proof, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

/** `tests/unit/test_knowledge_lifecycle_db.py`, which presses the lifecycle's routes against PostgreSQL. */
function lifecycle(name: string): Proof {
  return t("test_knowledge_lifecycle_db", name, true);
}

/** `tests/unit/test_knowledge_documents_db.py`, which presses the archive route against PostgreSQL. */
const LIFECYCLE_ARCHIVED = t(
  "test_knowledge_documents_db",
  "test_a_document_is_archived_by_whoever_may_act_on_it_and_then_nothing_answers_from_it",
  true,
);

const LIFECYCLE_SUPERSEDED = lifecycle(
  "test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer",
);

const LIFECYCLE_PROMOTED = lifecycle(
  "test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves",
);

const LIFECYCLE_REVIEWED = lifecycle(
  "test_a_document_due_for_review_opens_a_task_for_its_steward_which_verifying_closes",
);

/** `tests/unit/test_acceptance_corrections.py`, which runs the corrections check against PostgreSQL. */
const CORRECTION_DECIDED = t(
  "test_acceptance_corrections",
  "test_on_a_real_database_the_correction_check_passes_and_leaves_nothing",
  true,
);

const LIFECYCLE_SOLVED = lifecycle("test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it");

const LIFECYCLE_HANDED_OVER = lifecycle("test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told");

/** `tests/unit/test_public_knowledge_db.py`, which presses the marking route against PostgreSQL. */
const PUBLIC_MARKED = t(
  "test_public_knowledge_db",
  "test_a_department_admin_marks_their_own_document_and_the_ledger_names_them",
  true,
);

const PUBLIC_SCOPED = t(
  "test_public_knowledge_db",
  "test_another_departments_admin_is_told_they_decide_for_their_own_only",
  true,
);

/** `tests/unit/test_knowledge_documents_db.py`, which verifies several documents against PostgreSQL. */
const VERIFIED_SEVERAL = t(
  "test_knowledge_documents_db",
  "test_several_documents_are_verified_as_several_single_verifications",
  true,
);

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  // A document's history is read when a person opens its About view.
  "GET /api/v1/knowledge/items/{item_id}/history": {
    screen: "/library/:itemId/:view",
    spelled: "historyPath",
    built: historyPath("upload.x"),
  },
  // A version's text is read when a person presses Show the text on a document's Profile.
  "GET /api/v1/knowledge/items/{item_id}/passages": {
    screen: "/library/:itemId/:view",
    spelled: "passagesPath",
    built: passagesPath("upload.x"),
  },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/knowledge/KnowledgeExport.tsx KNOWLEDGE_EXPORT_API_PATH": [
    at("POST /api/v1/knowledge/inventory", "KNOWLEDGE_EXPORT_API_PATH", KNOWLEDGE_EXPORT_API_PATH),
  ],
  // The form is drawn on the Knowledge page and, with the agent's addresses, on an agent's Knowledge
  // section (`brain.agent_knowledge_routes`), which calls the same door.
  "src/pages/knowledge/addForms.tsx (door?.upload ?? uploadPath)(place.kind, place.level, place.department)": [
    at("POST /api/v1/knowledge/uploads", "uploadPath", uploadPath("sop", "department", "web").split("?")[0] ?? ""),
    at(
      "POST /api/v1/agents/{agent_id}/knowledge/uploads",
      "door?.upload",
      agentKnowledgeUploadApiPath("quote-helper", "sop", "department", "web").split("?")[0] ?? "",
    ),
  ],
  "src/pages/knowledge/parts.tsx taskDonePath(taskId)": [
    at("POST /api/v1/knowledge/tasks/{task_id}/done", "taskDonePath", taskDonePath("steward.x")),
  ],
  "src/pages/knowledge/actForms.tsx verificationPath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/verification", "verificationPath", verificationPath("upload.x")),
  ],
  "src/pages/knowledge/KnowledgePage.tsx VERIFICATIONS_API_PATH": [
    at("POST /api/v1/knowledge/verifications", "VERIFICATIONS_API_PATH", VERIFICATIONS_API_PATH),
  ],
  "src/pages/knowledge/actForms.tsx newVersionPath(itemId, instant)": [
    at(
      "POST /api/v1/knowledge/items/{item_id}/versions",
      "newVersionPath",
      newVersionPath("upload.x", "2999-01-01T12:00:00+00:00").split("?")[0] ?? "",
    ),
  ],
  "src/pages/knowledge/actForms.tsx promotionPath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/promotion", "promotionPath", promotionPath("upload.x")),
  ],
  "src/pages/knowledge/PublicMarkingCard.tsx publicPath(itemId)": [
    at("PUT /api/v1/knowledge/items/{item_id}/public", "publicPath", publicPath("upload.x")),
  ],
  "src/pages/knowledge/actForms.tsx stewardPath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/steward", "stewardPath", stewardPath("upload.x")),
  ],
  "src/pages/knowledge/actForms.tsx archivePath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/archive", "archivePath", archivePath("upload.x")),
  ],
  "src/pages/knowledge/SolutionsPage.tsx SOLUTIONS_API_PATH": [
    at("POST /api/v1/knowledge/solutions", "SOLUTIONS_API_PATH", SOLUTIONS_API_PATH),
  ],
  "src/pages/knowledge/SolutionsPage.tsx solutionDecisionPath(one.solutionId)": [
    at(
      "POST /api/v1/knowledge/solutions/{solution_id}/decision",
      "solutionDecisionPath",
      solutionDecisionPath("solution.x"),
    ),
  ],
  "src/pages/knowledge/CorrectionsPage.tsx correctionDecisionPath(review.candidateId)": [
    at(
      "POST /api/v1/knowledge/corrections/{candidate_id}/decision",
      "correctionDecisionPath",
      correctionDecisionPath("correction.x"),
    ),
  ],
  "src/pages/knowledge/addForms.tsx door?.link ?? LINKS_API_PATH": [
    at("POST /api/v1/knowledge/links", "LINKS_API_PATH", LINKS_API_PATH),
    at("POST /api/v1/agents/{agent_id}/knowledge/links", "door?.link", agentKnowledgeLinkApiPath("quote-helper")),
  ],
  "src/pages/agents/AgentKnowledgeActs.tsx agentKnowledgeRetireApiPath(agentId, item.itemId)": [
    at(
      "POST /api/v1/agents/{agent_id}/knowledge/{item_id}/retire",
      "agentKnowledgeRetireApiPath",
      agentKnowledgeRetireApiPath("quote-helper", "upload.x"),
    ),
  ],
  "src/pages/agents/AgentKnowledgeActs.tsx agentKnowledgeRefetchApiPath(agentId, item.itemId)": [
    at(
      "POST /api/v1/agents/{agent_id}/knowledge/{item_id}/refetch",
      "agentKnowledgeRefetchApiPath",
      agentKnowledgeRefetchApiPath("quote-helper", "upload.x"),
    ),
  ],
  "src/pages/knowledge/addForms.tsx queuedPath(place.kind, place.level, place.department)": [
    at(
      "POST /api/v1/knowledge/uploads/queued",
      "queuedPath",
      queuedPath("sop", "department", "web").split("?")[0] ?? "",
    ),
  ],
};

/** Why an agent's add routes have no database test of their own yet. */
const THE_DOOR_IS_PRESSED_ELSEWHERE =
  "This address calls the Knowledge page's own door function with the same request, and that door's row and ledger entry are followed by its own database tests; no database test presses this address yet. The install check for the agent's Knowledge section (M39.9.1.8) does.";

/** `tests/unit/test_agent_knowledge_finish_db.py`, which presses the section's routes against PostgreSQL. */
function finishing(name: string): Proof {
  return t("test_agent_knowledge_finish_db", name, true);
}

const RETIRED = finishing("test_a_retired_document_leaves_the_section_and_every_search_at_once_and_stays_on_file");
const FETCHED_AGAIN = finishing(
  "test_a_link_is_fetched_again_only_when_a_person_asks_and_the_newer_page_replaces_the_old",
);

/** `tests/unit/test_knowledge_export_routes.py`, which presses the inventory export against PostgreSQL. */
const INVENTORY_RECORDED = t(
  "test_knowledge_export_routes",
  "test_the_inventory_is_recorded_with_its_ledger_entry_and_matches_the_file_handed_over",
  true,
);

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/knowledge/inventory": {
    row: INVENTORY_RECORDED,
    audit: INVENTORY_RECORDED,
    behaviour: t(
      "test_knowledge_export_routes",
      "test_the_inventory_holds_the_documents_the_list_shows_that_reader_and_states_their_scope",
      true,
    ),
  },
  "POST /api/v1/agents/{agent_id}/knowledge/{item_id}/retire": { row: RETIRED, audit: RETIRED, behaviour: RETIRED },
  "POST /api/v1/agents/{agent_id}/knowledge/{item_id}/refetch": {
    row: FETCHED_AGAIN,
    audit: FETCHED_AGAIN,
    behaviour: FETCHED_AGAIN,
  },
  "POST /api/v1/agents/{agent_id}/knowledge/uploads": {
    row: { none: THE_DOOR_IS_PRESSED_ELSEWHERE, leaf: "M39.9.1.8" },
    audit: { none: THE_DOOR_IS_PRESSED_ELSEWHERE, leaf: "M39.9.1.8" },
    behaviour: t(
      "test_agent_knowledge_add",
      "test_a_file_added_outside_the_rule_is_added_and_said_not_to_be_drawn_on_with_the_clause",
    ),
  },
  "POST /api/v1/agents/{agent_id}/knowledge/links": {
    row: { none: THE_DOOR_IS_PRESSED_ELSEWHERE, leaf: "M39.9.1.8" },
    audit: { none: THE_DOOR_IS_PRESSED_ELSEWHERE, leaf: "M39.9.1.8" },
    behaviour: t(
      "test_agent_knowledge_add",
      "test_a_link_is_fetched_once_through_the_checked_door_and_answered_the_same_way",
    ),
  },
  "POST /api/v1/knowledge/uploads": {
    row: t(
      "test_knowledge_upload_db",
      "test_an_administrators_upload_is_found_by_its_department_by_text_and_by_nobody_else",
      true,
    ),
    audit: t(
      "test_knowledge_upload_db",
      "test_an_upload_appends_one_ledger_entry_the_audit_screens_reader_finds",
      true,
    ),
    behaviour: t("test_knowledge_routes", "test_a_markdown_file_is_added_to_a_department_as_its_uploader"),
  },
  "POST /api/v1/knowledge/items/{item_id}/verification": {
    row: LIFECYCLE_REVIEWED,
    audit: LIFECYCLE_SUPERSEDED,
    behaviour: LIFECYCLE_REVIEWED,
  },
  "POST /api/v1/knowledge/items/{item_id}/versions": {
    row: LIFECYCLE_SUPERSEDED,
    audit: LIFECYCLE_SUPERSEDED,
    behaviour: LIFECYCLE_SUPERSEDED,
  },
  "POST /api/v1/knowledge/items/{item_id}/promotion": {
    row: LIFECYCLE_PROMOTED,
    audit: LIFECYCLE_PROMOTED,
    behaviour: LIFECYCLE_PROMOTED,
  },
  "POST /api/v1/knowledge/items/{item_id}/archive": {
    row: LIFECYCLE_ARCHIVED,
    audit: LIFECYCLE_ARCHIVED,
    behaviour: LIFECYCLE_ARCHIVED,
  },
  "POST /api/v1/knowledge/items/{item_id}/steward": {
    row: LIFECYCLE_HANDED_OVER,
    audit: LIFECYCLE_HANDED_OVER,
    behaviour: LIFECYCLE_HANDED_OVER,
  },
  "PUT /api/v1/knowledge/items/{item_id}/public": {
    row: PUBLIC_MARKED,
    audit: PUBLIC_MARKED,
    behaviour: PUBLIC_SCOPED,
  },
  "POST /api/v1/knowledge/tasks/{task_id}/done": {
    row: LIFECYCLE_HANDED_OVER,
    audit: {
      notApplicable:
        "Marking a task read closes a notice in the reader's own list and changes nothing anybody holds; what it reports was recorded when it happened.",
    },
    behaviour: LIFECYCLE_HANDED_OVER,
  },
  "POST /api/v1/knowledge/solutions": {
    row: LIFECYCLE_SOLVED,
    audit: LIFECYCLE_SOLVED,
    behaviour: LIFECYCLE_SOLVED,
  },
  "POST /api/v1/knowledge/solutions/{solution_id}/decision": {
    row: LIFECYCLE_SOLVED,
    audit: LIFECYCLE_SOLVED,
    behaviour: LIFECYCLE_SOLVED,
  },
  "POST /api/v1/knowledge/corrections/{candidate_id}/decision": {
    row: CORRECTION_DECIDED,
    audit: CORRECTION_DECIDED,
    behaviour: CORRECTION_DECIDED,
  },
  "POST /api/v1/knowledge/verifications": {
    row: VERIFIED_SEVERAL,
    audit: VERIFIED_SEVERAL,
    behaviour: VERIFIED_SEVERAL,
  },
  "POST /api/v1/knowledge/links": {
    row: t(
      "test_knowledge_intake_db",
      "test_a_page_added_by_link_is_found_by_its_department_by_text_and_by_nobody_else",
      true,
    ),
    audit: t("test_knowledge_intake_db", "test_a_page_added_by_link_appends_the_ledger_entry_an_upload_does", true),
    behaviour: t("test_knowledge_intake_routes", "test_an_administrator_adds_a_page_by_its_link_for_one_department"),
  },
  "POST /api/v1/knowledge/uploads/queued": {
    row: t(
      "test_knowledge_intake_db",
      "test_a_queued_file_is_read_by_the_worker_job_and_found_by_its_department",
      true,
    ),
    audit: t(
      "test_knowledge_intake_db",
      "test_a_queued_files_ledger_entry_names_its_uploader_their_reach_and_its_trace",
      true,
    ),
    behaviour: t(
      "test_knowledge_intake_routes",
      "test_a_queued_file_is_kept_ticketed_and_queued_and_never_parsed_in_the_request",
    ),
  },
};
