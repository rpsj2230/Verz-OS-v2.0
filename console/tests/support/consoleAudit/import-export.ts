/**
 * What the console audit holds about the `import-export` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { EXPORTS_API_PATH } from "../../../src/pages/dataTransferQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/DataTransfer.tsx EXPORTS_API_PATH": [at("POST /api/v1/data-transfer/exports", "EXPORTS_API_PATH", EXPORTS_API_PATH)],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/data-transfer/exports": {
    row: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    audit: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    behaviour: t("test_data_transfer_routes", "test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own"),
  },
};
