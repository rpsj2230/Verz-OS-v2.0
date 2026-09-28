/**
 * What the console audit holds about the `settings` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { savePath } from "../../../src/pages/settingsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const BRANDING_SAVED = t(
  "test_settings_routes",
  "test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next",
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Settings.tsx savePath(row.name)": [at("PUT /api/v1/install/settings/{name}", "savePath", savePath("INSTALL_COMPANY_NAME"))],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/install/settings/{name}": {
    row: BRANDING_SAVED,
    audit: {
      none: "The route sets the audit attribution 0059's trigger reads, which BRANDING_SAVED asserts over a stub; no scratch-Postgres test yet reads the ledger entry back.",
    },
    behaviour: BRANDING_SAVED,
  },
};
