/**
 * What the console audit holds about the `rules` module: the writes the Quick answers screen sends,
 * mapped to the routes they reach, and the tests that follow each route to its row and to what it
 * changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it is.
 *
 * **The row is the rule store's, and the behaviour is the install's own check.** An addition and a
 * retirement go through `brain.gate.rule_store.StoredRules`, whose test adds a rule as the
 * application role, reads it back for its own department and not another's, and retires it. The
 * acceptance check calls the routes' own functions as acceptance_a's and acceptance_b's
 * administrators against PostgreSQL at head, and asks the next question through the answer route
 * after each write.
 *
 * **No ledger entry, and the reason is on the row.** A rule names its author in `created_by`, which
 * `0199` holds to the writer's own name, and its retirement is stamped by its own statement; no
 * trigger writes either to the audit ledger in this release.
 *
 * Task ids: M6.5.1
 */

import { retireApiPath, RULES_API_PATH, TRY_API_PATH } from "../../../src/pages/rulesQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const THE_INSTALLS_RULE_CHECK = t(
  "test_acceptance_dept_rules",
  "test_on_a_real_database_the_department_rule_check_passes_and_leaves_nothing_behind",
  true,
);

const A_RULE_IS_STORED_AND_RETIRED = t("test_rule_routes", "test_the_store_adds_reads_per_department_and_retires", true);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/rules/RulesPage.tsx RULES_API_PATH": [at("POST /api/v1/rules", "RULES_API_PATH", RULES_API_PATH)],
  "src/pages/rules/RulesPage.tsx TRY_API_PATH": [at("POST /api/v1/rules/test", "TRY_API_PATH", TRY_API_PATH)],
  "src/pages/rules/RulesPage.tsx retireApiPath(rule.rule_id)": [
    at("POST /api/v1/rules/{rule_id}/retire", "retireApiPath", retireApiPath("acceptance_a__rate")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/rules": {
    row: A_RULE_IS_STORED_AND_RETIRED,
    audit: {
      none: "A rule names its author on its own row, held to the writer's name by migration 0199's policy, and is not written to the audit ledger in this release.",
    },
    behaviour: THE_INSTALLS_RULE_CHECK,
  },
  "POST /api/v1/rules/test": {
    row: { notApplicable: "Trying a rule saves nothing: it matches one question against the candidate and reads at the tester's own reach." },
    audit: { notApplicable: "Trying a rule changes nothing, so there is nothing to record." },
    behaviour: t("test_rule_routes", "test_a_test_says_what_the_rule_would_answer_and_saves_nothing"),
  },
  "POST /api/v1/rules/{rule_id}/retire": {
    row: A_RULE_IS_STORED_AND_RETIRED,
    audit: {
      none: "A retirement is stamped on the rule's own row by its own statement, and is not written to the audit ledger in this release.",
    },
    behaviour: THE_INSTALLS_RULE_CHECK,
  },
};
