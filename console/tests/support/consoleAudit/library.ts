/**
 * What the console audit holds about the `library` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes, and the reads it makes only once somebody acts. `support/consoleAudit.ts`
 * collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { uploadPath } from "../../../src/pages/knowledgeQuery";
import {
  newVersionPath,
  passagesPath,
  promotionPath,
  solutionDecisionPath,
  SOLUTIONS_API_PATH,
  stewardPath,
  taskDonePath,
  verificationPath,
} from "../../../src/pages/knowledgeLifecycleQuery";
import { LINKS_API_PATH, queuedPath } from "../../../src/pages/knowledgeIntakeQuery";
import { at, type Proof, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

/** `tests/unit/test_knowledge_lifecycle_db.py`, which presses the lifecycle's routes against PostgreSQL. */
function lifecycle(name: string): Proof {
  return t("test_knowledge_lifecycle_db", name, true);
}

const LIFECYCLE_SUPERSEDED = lifecycle(
  "test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer",
);

const LIFECYCLE_PROMOTED = lifecycle(
  "test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves",
);

const LIFECYCLE_REVIEWED = lifecycle(
  "test_a_document_due_for_review_opens_a_task_for_its_steward_which_verifying_closes",
);

const LIFECYCLE_SOLVED = lifecycle("test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it");

const LIFECYCLE_HANDED_OVER = lifecycle("test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told");

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  // A version's text is read when a person presses Read this version on an opened document.
  "GET /api/v1/knowledge/items/{item_id}/passages": {
    screen: "/library",
    spelled: "passagesPath",
    built: passagesPath("upload.x"),
  },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Knowledge.tsx uploadPath(draft.kind, draft.level, draft.department)": [
    at("POST /api/v1/knowledge/uploads", "uploadPath", uploadPath("sop", "department", "web").split("?")[0] ?? ""),
  ],
  "src/components/KnowledgeLifecycle.tsx taskDonePath(taskId)": [
    at("POST /api/v1/knowledge/tasks/{task_id}/done", "taskDonePath", taskDonePath("steward.x")),
  ],
  "src/components/KnowledgeLifecycle.tsx verificationPath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/verification", "verificationPath", verificationPath("upload.x")),
  ],
  "src/components/KnowledgeLifecycle.tsx newVersionPath(document.item_id, instant)": [
    at(
      "POST /api/v1/knowledge/items/{item_id}/versions",
      "newVersionPath",
      newVersionPath("upload.x", "2999-01-01T12:00:00+00:00").split("?")[0] ?? "",
    ),
  ],
  "src/components/KnowledgeLifecycle.tsx promotionPath(itemId)": [
    at("POST /api/v1/knowledge/items/{item_id}/promotion", "promotionPath", promotionPath("upload.x")),
  ],
  "src/components/KnowledgeLifecycle.tsx stewardPath(document.item_id)": [
    at("POST /api/v1/knowledge/items/{item_id}/steward", "stewardPath", stewardPath("upload.x")),
  ],
  "src/components/KnowledgeLifecycle.tsx SOLUTIONS_API_PATH": [
    at("POST /api/v1/knowledge/solutions", "SOLUTIONS_API_PATH", SOLUTIONS_API_PATH),
  ],
  "src/components/KnowledgeLifecycle.tsx solutionDecisionPath(one.solution_id)": [
    at(
      "POST /api/v1/knowledge/solutions/{solution_id}/decision",
      "solutionDecisionPath",
      solutionDecisionPath("solution.x"),
    ),
  ],
  "src/pages/KnowledgeIntake.tsx LINKS_API_PATH": [at("POST /api/v1/knowledge/links", "LINKS_API_PATH", LINKS_API_PATH)],
  "src/pages/KnowledgeIntake.tsx queuedPath(place.kind, place.level, place.department)": [
    at(
      "POST /api/v1/knowledge/uploads/queued",
      "queuedPath",
      queuedPath("sop", "department", "web").split("?")[0] ?? "",
    ),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
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
  "POST /api/v1/knowledge/items/{item_id}/steward": {
    row: LIFECYCLE_HANDED_OVER,
    audit: LIFECYCLE_HANDED_OVER,
    behaviour: LIFECYCLE_HANDED_OVER,
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
