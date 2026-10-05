/**
 * What the console audit holds about the `resolution` module: the write its screen sends, mapped to
 * the route it reaches, and the tests that follow that route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * **The row and the ledger are the merge store's, and the behaviour is the install's own check.**
 * `decide_review_item` merges through `review_store.merge_reviewed`, which is
 * `merge_store.merge_entities` with the reviewer named, and its test reads back the `er.merge` row
 * naming the reviewer and the review and one `entity_merge` ledger entry per side. The acceptance
 * check calls the route itself as a reviewer against PostgreSQL at head: the merge and the closed
 * `er.review_item` in the reviewer's name, a rejection's state, and the 409 for a pair already
 * decided.
 *
 * Task ids: none
 */

import { decisionApiPath } from "../../../src/pages/resolutionReviewQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const ITEM = "rev_0123456789abcdef0123456789abcdef";

const THE_INSTALLS_REVIEW_CHECK = t(
  "test_acceptance_review",
  "test_on_a_real_database_the_review_check_passes_and_nothing_is_left_behind",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/resolution/ResolutionReviewPage.tsx decisionApiPath(chosen.card.item_id)": [
    at("POST /api/v1/resolution/review/{item_id}/decision", "decisionApiPath", decisionApiPath(ITEM)),
  ],
};

const A_REVIEWED_MERGE_IS_STORED = t(
  "test_merge_store",
  "test_a_reviewed_merge_moves_one_pointer_and_records_who_when_and_on_what",
  true,
);

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/resolution/review/{item_id}/decision": {
    row: A_REVIEWED_MERGE_IS_STORED,
    audit: A_REVIEWED_MERGE_IS_STORED,
    behaviour: THE_INSTALLS_REVIEW_CHECK,
  },
};
