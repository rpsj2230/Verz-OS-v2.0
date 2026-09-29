/**
 * What the console audit holds about the `ask` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { ANSWER_API_PATH, MARK_API_PATH } from "../../../src/pages/askQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
  "src/pages/Ask.tsx MARK_API_PATH": [at("POST /api/v1/answer/mark", "MARK_API_PATH", MARK_API_PATH)],
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
};
