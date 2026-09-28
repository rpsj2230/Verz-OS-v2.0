/**
 * What the console audit holds about the `routing` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { rungApiPath } from "../../../src/pages/matrixQuery";
import { ADD_RUNG_API_PATH, GOLDEN_API_PATH, retireGoldenApiPath } from "../../../src/pages/matrixGateQuery";
import { at, audited, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Matrix.tsx rungApiPath(rung.id)": [at("PATCH /api/v1/routing/rungs/{rung_id}", "rungApiPath", rungApiPath("rung-1"))],
  "src/components/MatrixGate.tsx GOLDEN_API_PATH": [
    at("POST /api/v1/routing/golden-questions", "GOLDEN_API_PATH", GOLDEN_API_PATH),
  ],
  "src/components/MatrixGate.tsx retireGoldenApiPath(asked.row.id)": [
    at(
      "POST /api/v1/routing/golden-questions/{question_id}/retire",
      "retireGoldenApiPath",
      retireGoldenApiPath("33333333-3333-4333-8333-333333333333"),
    ),
  ],
  "src/components/MatrixGate.tsx ADD_RUNG_API_PATH": [at("POST /api/v1/routing/rungs", "ADD_RUNG_API_PATH", ADD_RUNG_API_PATH)],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PATCH /api/v1/routing/rungs/{rung_id}": {
    row: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    audit: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    behaviour: t(
      "test_provider_routes",
      "test_a_rung_saved_on_the_routing_screen_is_the_rung_the_next_call_walks",
      true,
    ),
  },
  "POST /api/v1/routing/golden-questions": {
    row: t("test_routing_routes", "test_a_golden_question_is_recorded_only_as_a_principal_the_directory_holds"),
    audit: {
      none: "A golden question is a check the matrix gate asks and is logged, not written to the audit ledger; the changes it holds are recorded in ops.routing_change.",
      leaf: "M5.6.2",
    },
    behaviour: t("test_matrix_gate", "test_a_change_that_stops_the_ladder_answering_is_held_with_the_failing_question_shown"),
  },
  "POST /api/v1/routing/golden-questions/{question_id}/retire": {
    row: t("test_routing_routes", "test_a_retired_golden_question_is_marked_retired_and_asked_no_more"),
    audit: {
      none: "Retiring a golden question is logged, not written to the audit ledger.",
      leaf: "M5.6.2",
    },
    behaviour: t("test_matrix_gate", "test_a_gate_with_no_golden_questions_holds_the_change_and_says_to_record_some"),
  },
  "POST /api/v1/routing/rungs": {
    row: t("test_routing_routes", "test_a_rung_is_added_at_the_end_of_its_tier_only_through_the_gate"),
    audit: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    behaviour: t("test_model_calls", "test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release"),
  },
};
