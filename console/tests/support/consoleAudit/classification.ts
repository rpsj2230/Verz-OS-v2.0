/**
 * What the console audit holds about the `classification` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { markApiPath, markReviewApiPath, reviewApiPath, tableApiPath } from "../../../src/pages/classificationQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Classification.tsx mark === null ? reviewApiPath(entity, row.column) : markReviewApiPath(entity, row.column)": [
    at("POST /api/v1/classifications/{entity}/columns/{column}/review", "reviewApiPath", reviewApiPath("price_list", "cost")),
    at(
      "POST /api/v1/classifications/{entity}/columns/{column}/marks/review",
      "markReviewApiPath",
      markReviewApiPath("prices", "margin"),
    ),
  ],
  "src/pages/Classification.tsx markApiPath(entity, row.column)": [
    at("PUT /api/v1/classifications/{entity}/columns/{column}/marks", "markApiPath", markApiPath("prices", "margin")),
  ],
  "src/pages/Classification.tsx tableApiPath(named)": [
    at("PUT /api/v1/classifications/{entity}/table", "tableApiPath", tableApiPath("prices")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/classifications/{entity}/columns/{column}/review": {
    row: { notApplicable: "A review is a dry run and writes nothing." },
    audit: { notApplicable: "A review changes nothing, so there is nothing to record." },
    behaviour: t("test_classification_routes", "test_the_only_writes_mounted_here_are_the_upload_and_the_mark"),
  },
  "POST /api/v1/classifications/{entity}/columns/{column}/marks/review": {
    row: { notApplicable: "A review of a mark is a dry run and writes nothing." },
    audit: { notApplicable: "A review changes nothing, so there is nothing to record." },
    behaviour: t("test_classified_tables", "test_a_mark_review_stores_nothing"),
  },
  "PUT /api/v1/classifications/{entity}/columns/{column}/marks": {
    row: t("test_classified_tables", "test_the_store_writes_and_reads_a_table_as_the_application_role", true),
    audit: t("test_classified_tables", "test_the_store_writes_and_reads_a_table_as_the_application_role", true),
    behaviour: t(
      "test_classified_tables",
      "test_applying_a_mark_stores_it_and_moves_the_epoch_when_a_derivation_changes",
    ),
  },
  "PUT /api/v1/classifications/{entity}/table": {
    row: t("test_classified_tables", "test_the_store_writes_and_reads_a_table_as_the_application_role", true),
    audit: t("test_classified_tables", "test_the_store_writes_and_reads_a_table_as_the_application_role", true),
    behaviour: t(
      "test_classified_tables",
      "test_an_administrator_uploads_a_price_list_and_is_answered_its_classification",
    ),
  },
};
