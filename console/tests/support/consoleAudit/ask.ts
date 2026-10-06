/**
 * What the console audit holds about the `ask` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { ANSWER_API_PATH, MARK_API_PATH } from "../../../src/pages/askQuery";
import { retrievalUsesPath } from "../../../src/pages/citedDocumentQuery";
import { correctionPath, exportPath } from "../../../src/pages/threadsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

/**
 * The install check marking an answer wrong as its asker, refused to anybody else, and read back as
 * the thread's note and the learning signal's one contradiction (M9.2.4).
 */
/**
 * The install check asking through the answer route's own logging, following a citation, and
 * reading the kept place and the signal back (M15.3.4).
 */
const A_FOLLOWED_CITATION_IS_KEPT_AS_A_PLACE = t(
  "test_acceptance_answers",
  "test_every_answer_check_passes_on_an_install_and_leaves_nothing",
  true,
);

const A_CORRECTION_IS_KEPT_AND_COUNTED = t(
  "test_acceptance_threads",
  "test_every_thread_check_passes_on_an_install_and_leaves_nothing",
  true,
);

/**
 * The route test exporting a person's own conversation: the file is what the page shows, the
 * `ops.data_export` row is in their name with the digest of the bytes they received, the ledger has
 * its publish entry, and another person asking is the one 404 with nothing recorded (M33.3.1.3).
 */
const A_CONVERSATION_EXPORT_IS_RECORDED = t(
  "test_thread_export_routes",
  "test_a_person_exports_their_thread_as_the_page_shows_it_and_the_export_is_recorded",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
  "src/pages/Ask.tsx MARK_API_PATH": [at("POST /api/v1/answer/mark", "MARK_API_PATH", MARK_API_PATH)],
  "src/pages/CitedDocument.tsx retrievalUsesPath(followed.retrievalId)": [
    at(
      "POST /api/v1/retrievals/{event_id}/uses",
      "retrievalUsesPath",
      retrievalUsesPath("3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b"),
    ),
  ],
  "src/pages/Ask.tsx correctionPath(thread)": [
    at(
      "POST /api/v1/threads/{thread_id}/corrections",
      "correctionPath",
      correctionPath("3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b"),
    ),
  ],
  "src/pages/Ask.tsx exportPath(thread)": [
    at("POST /api/v1/threads/{thread_id}/export", "exportPath", exportPath("3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b")),
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
  "POST /api/v1/retrievals/{event_id}/uses": {
    row: A_FOLLOWED_CITATION_IS_KEPT_AS_A_PLACE,
    audit: {
      notApplicable:
        "A followed citation's place changes no setting and nobody's access; it is one position in a retrieval that names nobody.",
    },
    behaviour: A_FOLLOWED_CITATION_IS_KEPT_AS_A_PLACE,
  },
  "POST /api/v1/threads/{thread_id}/corrections": {
    row: A_CORRECTION_IS_KEPT_AND_COUNTED,
    audit: {
      notApplicable:
        "Marking an answer in one's own conversation wrong changes no setting and nobody's access; the note is kept in the asker's own thread.",
    },
    behaviour: A_CORRECTION_IS_KEPT_AND_COUNTED,
  },
  "POST /api/v1/threads/{thread_id}/export": {
    row: A_CONVERSATION_EXPORT_IS_RECORDED,
    audit: A_CONVERSATION_EXPORT_IS_RECORDED,
    behaviour: A_CONVERSATION_EXPORT_IS_RECORDED,
  },
};
