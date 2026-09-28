/**
 * The page cases for `/import-export`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const DATA_TRANSFER = {
  catalogue: [
    { key: "audit_trail", label: UNBROKEN, direction: "export", carries: UNBROKEN, runs: true, told: UNBROKEN },
    { key: "skills", label: UNBROKEN, direction: "import", carries: UNBROKEN, runs: false, told: UNBROKEN },
  ],
  reasons: ["regulatory_request"],
  exportable: true,
  exports: [
    {
      export_id: "11111111-1111-4111-8111-111111111111",
      data_set: "audit_trail",
      reason: "regulatory_request",
      reason_reference: UNBROKEN.slice(0, 64),
      produced_at: "2019-03-04T09:00:00Z",
      first_seq: 0,
      last_seq: 1,
      entries: 2,
      verified: true,
      document_digest: "a".repeat(64),
    },
  ],
  export_told: UNBROKEN,
  document_told: UNBROKEN,
  own_exports_told: UNBROKEN,
  max_entries: 50000,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Import and export. The catalogue and the exports tables scroll; the served sentences and the
  // export form sit outside them. The confirmation is held in `tests/data-transfer-page.test.tsx`.
  "/import-export": {
    address: "/import-export",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/data-transfer": DATA_TRANSFER },
  },
};
