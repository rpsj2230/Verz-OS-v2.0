/**
 * What the console audit holds about the `compliance` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { BREACHES_API_PATH, breachStepApiPath, topicApiPath } from "../../../src/pages/complianceQuery";
import { at, COMPLIANCE_CASE, type Proofs, t, type WriteRoute } from "../auditClaims";

const A_PERSON_NAMED_FOR_A_TOPIC = t(
  "test_compliance_store",
  "test_naming_a_person_writes_one_route_row_and_a_setting_entry_without_the_value",
  true,
);

const BREACH_STEP_WRITTEN = t(
  "test_compliance_store",
  "test_each_breach_step_writes_its_column_and_one_breach_entry_in_the_same_transaction",
  true,
);

/** Every breach write, opening a case and each step after it, is proved by the same three tests. */
const BREACH_STEP: Proofs = {
  row: BREACH_STEP_WRITTEN,
  audit: BREACH_STEP_WRITTEN,
  behaviour: t("test_compliance_routes", "test_a_case_shows_its_clock_from_the_awareness_and_its_findings"),
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Compliance.tsx topicApiPath(asked.topic)": [
    at("PUT /api/v1/govern/compliance/topics/{topic}", "topicApiPath", topicApiPath("grievance")),
  ],
  "src/pages/Compliance.tsx path": [
    at("POST /api/v1/govern/compliance/breaches", "BREACHES_API_PATH", BREACHES_API_PATH),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/assessment",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "assessment"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/commission",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "commission"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/individuals",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "individuals"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/exception",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "exception"),
    ),
    at("POST /api/v1/govern/compliance/breaches/{case_id}/close", "breachStepApiPath", breachStepApiPath(COMPLIANCE_CASE, "close")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/govern/compliance/topics/{topic}": {
    row: A_PERSON_NAMED_FOR_A_TOPIC,
    audit: A_PERSON_NAMED_FOR_A_TOPIC,
    behaviour: t("test_compliance_routes", "test_a_sensitive_question_is_routed_to_the_person_named_for_its_topic"),
  },
  "POST /api/v1/govern/compliance/breaches": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/assessment": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/commission": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/individuals": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/exception": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/close": BREACH_STEP,
};
