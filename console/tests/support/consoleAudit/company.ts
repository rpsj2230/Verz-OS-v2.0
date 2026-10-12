/**
 * What the console audit holds about the `company` module: the write its Consumption page sends,
 * mapped to the route it reaches, and the tests that follow that route to its row, its ledger entry
 * and what it changes. `support/consoleAudit.ts` collects this file and says why each claim is
 * shaped as it is.
 *
 * Task ids: none
 */

import { COMPANY_BUDGET_API_PATH } from "../../../src/pages/companyQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/company/CompanyBudgetForm.tsx COMPANY_BUDGET_API_PATH": [
    at("PUT /api/v1/company/budget", "COMPANY_BUDGET_API_PATH", COMPANY_BUDGET_API_PATH),
  ],
};

/** The company's monthly budget set twice over HTTP against PostgreSQL: two versions, two entries naming who. */
const COMPANY_BUDGET_PRESSED = t(
  "test_company_budget_route",
  "test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries",
  true,
);

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/company/budget": {
    row: COMPANY_BUDGET_PRESSED,
    audit: COMPANY_BUDGET_PRESSED,
    behaviour: t(
      "test_company_routes",
      "test_setting_the_companys_budget_is_refused_in_words_naming_the_role_and_never_to_a_stranger",
    ),
  },
};
