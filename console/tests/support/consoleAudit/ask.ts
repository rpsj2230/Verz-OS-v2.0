/**
 * What the console audit holds about the `ask` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { ATTACHMENTS_API_PATH } from "../../../src/pages/askAttachQuery";
import { ANSWER_API_PATH, MARK_API_PATH } from "../../../src/pages/askQuery";
import { uploadPath } from "../../../src/pages/knowledgeQuery";
import { correctionPath } from "../../../src/pages/threadsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

/**
 * The install check marking an answer wrong as its asker, refused to anybody else, and read back as
 * the thread's note and the learning signal's one contradiction (M9.2.4).
 */
const A_CORRECTION_IS_KEPT_AND_COUNTED = t(
  "test_acceptance_threads",
  "test_every_thread_check_passes_on_an_install_and_leaves_nothing",
  true,
);

/** The install check attaching a document its owner may read and reading it through its tool (M12.3.6). */
const AN_ATTACHED_FILE_IS_READ_BY_ITS_OWNER_ALONE = t(
  "test_acceptance_attachments",
  "test_on_a_real_database_an_attached_file_is_read_by_its_owner_alone",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
  "src/pages/Ask.tsx MARK_API_PATH": [at("POST /api/v1/answer/mark", "MARK_API_PATH", MARK_API_PATH)],
  "src/pages/Ask.tsx correctionPath(thread)": [
    at(
      "POST /api/v1/threads/{thread_id}/corrections",
      "correctionPath",
      correctionPath("3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b"),
    ),
  ],
  'src/pages/AskAttach.tsx uploadPath(kind, "personal", "")': [
    at("POST /api/v1/knowledge/uploads", "uploadPath", uploadPath("sop", "personal", "").split("?")[0] ?? ""),
  ],
  "src/pages/AskAttach.tsx ATTACHMENTS_API_PATH": [
    at("POST /api/v1/threads/attachments", "ATTACHMENTS_API_PATH", ATTACHMENTS_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/answer": {
    row: { notApplicable: "Asking a question writes no row an administrator manages." },
    audit: { notApplicable: "Asking a question is not a change to the system." },
    behaviour: { notApplicable: "The answer is the behaviour, and tests/invariants hold it." },
  },
  "POST /api/v1/answer/mark": {
    row: t("test_learning_signal", "test_a_person_marks_their_own_answer_and_no_other", true),
    audit: {
      notApplicable: "A mark changes nothing the system does; the row is its own record, naming who marked which answer and when.",
    },
    behaviour: t(
      "test_answer_route_memory",
      "test_a_person_marks_an_answer_they_were_given_with_one_action_and_no_words",
    ),
  },
  "POST /api/v1/threads/attachments": {
    row: t("test_chat_attachments", "test_a_document_is_attached_once_to_the_person_s_own_thread_or_a_new_one", true),
    audit: {
      notApplicable:
        "Attaching a document to one's own conversation changes no setting and nobody's access; the note is kept in the asker's own thread, and the document was added, and audited, by its own upload.",
    },
    behaviour: AN_ATTACHED_FILE_IS_READ_BY_ITS_OWNER_ALONE,
  },
  "POST /api/v1/threads/{thread_id}/corrections": {
    row: A_CORRECTION_IS_KEPT_AND_COUNTED,
    audit: {
      notApplicable:
        "Marking an answer in one's own conversation wrong changes no setting and nobody's access; the note is kept in the asker's own thread.",
    },
    behaviour: A_CORRECTION_IS_KEPT_AND_COUNTED,
  },
};
