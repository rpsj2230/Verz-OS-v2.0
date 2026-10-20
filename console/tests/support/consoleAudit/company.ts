/**
 * What the console audit holds about the `company` module: the write its Consumption page sends,
 * mapped to the route it reaches, and the tests that follow that route to its row, its ledger entry
 * and what it changes. `support/consoleAudit.ts` collects this file and says why each claim is
 * shaped as it is.
 *
 * Task ids: none
 */

import {
  COMPANY_BUDGET_API_PATH,
  DEPARTMENT_BUDGETS_API_PATH,
  DEPARTMENT_TRANSFER_API_PATH,
  departmentAllowancesPath,
  departmentRunCeilingPath,
} from "../../../src/pages/companyQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/company/CompanyBudgetForm.tsx COMPANY_BUDGET_API_PATH": [
    at("PUT /api/v1/company/budget", "COMPANY_BUDGET_API_PATH", COMPANY_BUDGET_API_PATH),
  ],
  "src/pages/company/DepartmentBudgets.tsx DEPARTMENT_BUDGETS_API_PATH": [
    at("PUT /api/v1/company/budget/departments", "DEPARTMENT_BUDGETS_API_PATH", DEPARTMENT_BUDGETS_API_PATH),
  ],
  "src/pages/company/DepartmentBudgets.tsx DEPARTMENT_TRANSFER_API_PATH": [
    at("POST /api/v1/company/budget/departments/transfer", "DEPARTMENT_TRANSFER_API_PATH", DEPARTMENT_TRANSFER_API_PATH),
  ],
  "src/pages/company/DepartmentBudgets.tsx departmentRunCeilingPath(department)": [
    at("PUT /api/v1/departments/{department}/budget/run-ceiling", "departmentRunCeilingPath(department)", departmentRunCeilingPath("{department}")),
  ],
  "src/pages/company/DepartmentBudgets.tsx departmentAllowancesPath(department)": [
    at("POST /api/v1/departments/{department}/budget/allowances", "departmentAllowancesPath(department)", departmentAllowancesPath("{department}")),
  ],
};

/** The company's monthly budget set twice over HTTP against PostgreSQL: two versions, two entries naming who. */
const COMPANY_BUDGET_PRESSED = t(
  "test_company_budget_route",
  "test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries",
  true,
);

/** The whole department-budget path over HTTP against PostgreSQL: versions, the ledger and the lines read back. */
const DEPARTMENT_BUDGETS_PRESSED = t(
  "test_department_budget_routes",
  "test_a_department_is_funded_moved_ceilinged_and_given_allowances_on_the_database",
  true,
);

/** The allocation and the transfer refused to a department's own administrator, before any row is read. */
const COMPANY_MONEY_REFUSED = t(
  "test_department_budget_routes",
  "test_moving_company_money_needs_the_authority_over_everything_and_reads_nothing",
);

/** A department's ceiling and allowances refused to another department's administrator in a stranger's words. */
const ANOTHER_DEPARTMENT_REFUSED = t(
  "test_department_budget_routes",
  "test_another_departments_ceiling_is_refused_in_the_words_a_stranger_gets",
);

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/company/budget/departments": {
    row: DEPARTMENT_BUDGETS_PRESSED,
    audit: DEPARTMENT_BUDGETS_PRESSED,
    behaviour: COMPANY_MONEY_REFUSED,
  },
  "POST /api/v1/company/budget/departments/transfer": {
    row: DEPARTMENT_BUDGETS_PRESSED,
    audit: DEPARTMENT_BUDGETS_PRESSED,
    behaviour: COMPANY_MONEY_REFUSED,
  },
  "PUT /api/v1/departments/{department}/budget/run-ceiling": {
    row: DEPARTMENT_BUDGETS_PRESSED,
    audit: DEPARTMENT_BUDGETS_PRESSED,
    behaviour: ANOTHER_DEPARTMENT_REFUSED,
  },
  "POST /api/v1/departments/{department}/budget/allowances": {
    row: DEPARTMENT_BUDGETS_PRESSED,
    audit: DEPARTMENT_BUDGETS_PRESSED,
    behaviour: ANOTHER_DEPARTMENT_REFUSED,
  },
  "PUT /api/v1/company/budget": {
    row: COMPANY_BUDGET_PRESSED,
    audit: COMPANY_BUDGET_PRESSED,
    behaviour: t(
      "test_company_routes",
      "test_setting_the_companys_budget_is_refused_in_words_naming_the_role_and_never_to_a_stranger",
    ),
  },
};
