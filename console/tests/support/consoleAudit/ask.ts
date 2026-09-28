/**
 * What the console audit holds about the `ask` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { ANSWER_API_PATH } from "../../../src/pages/askQuery";
import { at, type Proofs, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/answer": {
    row: { notApplicable: "Asking a question writes no row an administrator manages." },
    audit: { notApplicable: "Asking a question is not a change to the system." },
    behaviour: { notApplicable: "The answer is the behaviour, and tests/invariants hold it." },
  },
};
