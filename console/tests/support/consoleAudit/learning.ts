/**
 * What the console audit holds about the `learning` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { UNDO_API_PATH } from "../../../src/pages/learningQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL = t(
  "test_memory_store",
  "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/learning/LearningPage.tsx UNDO_API_PATH": [at("POST /api/v1/govern/learning/undo", "UNDO_API_PATH", UNDO_API_PATH)],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/learning/undo": {
    row: UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL,
    audit: UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL,
    behaviour: t(
      "test_estate_routes",
      "test_an_undo_writes_the_correction_and_the_next_reading_no_longer_recalls_the_learning",
    ),
  },
};
