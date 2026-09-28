/**
 * What the console audit holds about the `requirement-checks` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { CHECKS_API_PATH } from "../../../src/pages/requirementChecksQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/RequirementChecks.tsx CHECKS_API_PATH": [
    at("POST /api/v1/requirements/checks", "CHECKS_API_PATH", CHECKS_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/requirements/checks": {
    row: t("test_requirement_check_routes", "test_the_store_keeps_every_check_and_reads_back_the_newest_per_requirement", true),
    audit: {
      none: "A check is an append-only row attributed to the person who recorded it, and is not written to the ledger: brain.tables.requirement_check argues why.",
    },
    behaviour: t(
      "test_requirement_check_routes",
      "test_a_check_is_recorded_as_the_person_asking_on_the_running_release_and_read_back",
    ),
  },
};
