/**
 * What the console audit holds about the `models` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes, and the reads it makes only once somebody acts. `support/consoleAudit.ts`
 * collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { rungApiPath } from "../../../src/pages/matrixQuery";
import { ADD_RUNG_API_PATH, GOLDEN_API_PATH, retireGoldenApiPath } from "../../../src/pages/matrixGateQuery";
import {
  ADD_PROVIDER_API_PATH,
  REGISTER_API_PATH as PROVIDER_REGISTER_API_PATH,
  retireProviderApiPath,
  termsApiPath,
} from "../../../src/pages/providerRegisterQuery";
import { PRICES_API_PATH } from "../../../src/pages/modelPricesQuery";
import { PROFILE_API_PATH, providerCheckApiPath, providerSwitchApiPath } from "../../../src/pages/modelsQuery";
import {
  RESIDENCY_API_PATH,
  residencyRetireApiPath,
  tierApiPath,
  tierResetApiPath,
} from "../../../src/pages/routingSettingsQuery";
import { credentialPath } from "../../../src/components/ProviderKeyForm";
import { moveStepApiPath, retireStepApiPath } from "../../../src/pages/models/modelsActions";
import {
  A_SETTING_ENTRY_NO_TEST_FOLLOWS,
  at,
  audited,
  type Proofs,
  type ReadAfterAnAction,
  t,
  type WriteRoute,
} from "../auditClaims";

/** `0140`'s registry trigger against PostgreSQL: registered, changed and retired, never the terms. */
const REGISTRY_LEDGERED = t(
  "test_models_routing_module",
  "test_a_registry_row_registered_changed_and_retired_leaves_three_entries_no_terms",
  true,
);

/** A step moved and retired over HTTP against PostgreSQL: the rows, the roles, the records, the ledger. */
const STEP_MOVED_AND_RETIRED = t(
  "test_models_routing_module",
  "test_a_move_and_a_retirement_leave_the_rows_roles_records_and_entries_they_claim",
  true,
);

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  "GET /api/v1/models/providers-register": { screen: "/models", spelled: "REGISTER_API_PATH", built: PROVIDER_REGISTER_API_PATH },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/models/RungEditor.tsx rungApiPath(rung.id)": [at("PATCH /api/v1/routing/rungs/{rung_id}", "rungApiPath", rungApiPath("rung-1"))],
  "src/pages/models/RungEditor.tsx moveStepApiPath(rung.id)": [
    at("POST /api/v1/routing/rungs/{rung_id}/move", "moveStepApiPath", moveStepApiPath("rung-1")),
  ],
  "src/pages/models/RungEditor.tsx retireStepApiPath(rung.id)": [
    at("POST /api/v1/routing/rungs/{rung_id}/retire", "retireStepApiPath", retireStepApiPath("rung-1")),
  ],
  "src/pages/models/RoutingPage.tsx moveStepApiPath(asked.rungId)": [
    at("POST /api/v1/routing/rungs/{rung_id}/move", "moveStepApiPath", moveStepApiPath("rung-1")),
  ],
  "src/pages/models/RoutingPage.tsx retireStepApiPath(asked.rungId)": [
    at("POST /api/v1/routing/rungs/{rung_id}/retire", "retireStepApiPath", retireStepApiPath("rung-1")),
  ],
  "src/pages/models/GoldenQuestions.tsx GOLDEN_API_PATH": [
    at("POST /api/v1/routing/golden-questions", "GOLDEN_API_PATH", GOLDEN_API_PATH),
  ],
  "src/pages/models/GoldenQuestions.tsx retireGoldenApiPath(asked.row.id)": [
    at(
      "POST /api/v1/routing/golden-questions/{question_id}/retire",
      "retireGoldenApiPath",
      retireGoldenApiPath("33333333-3333-4333-8333-333333333333"),
    ),
  ],
  "src/pages/models/AddStep.tsx ADD_RUNG_API_PATH": [at("POST /api/v1/routing/rungs", "ADD_RUNG_API_PATH", ADD_RUNG_API_PATH)],
  "src/pages/models/ProviderProfile.tsx termsApiPath(row.provider)": [
    at("PUT /api/v1/models/providers/{provider}/terms", "termsApiPath", termsApiPath("anthropic")),
  ],
  "src/pages/models/ProviderDetailPage.tsx retireProviderApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/retire", "retireProviderApiPath", retireProviderApiPath("acme_llm")),
  ],
  "src/pages/models/AddProvider.tsx ADD_PROVIDER_API_PATH": [
    at("POST /api/v1/models/providers", "ADD_PROVIDER_API_PATH", ADD_PROVIDER_API_PATH),
  ],
  "src/components/ProviderKeyForm.tsx credentialPath(slot)": [
    at("PUT /api/v1/credentials/{family}/{name}", "credentialPath", credentialPath("providers/anthropic")),
  ],
  "src/components/RoutingSettings.tsx tierApiPath(asked.tier)": [
    at("PUT /api/v1/models/tiers/{tier}", "tierApiPath", tierApiPath("main")),
  ],
  "src/components/RoutingSettings.tsx tierResetApiPath(asked.tier)": [
    at("POST /api/v1/models/tiers/{tier}/reset", "tierResetApiPath", tierResetApiPath("main")),
  ],
  "src/components/RoutingSettings.tsx RESIDENCY_API_PATH": [
    at("POST /api/v1/models/residency", "RESIDENCY_API_PATH", RESIDENCY_API_PATH),
  ],
  "src/components/RoutingSettings.tsx residencyRetireApiPath(asked.row.id)": [
    at(
      "POST /api/v1/models/residency/{constraint_id}/retire",
      "residencyRetireApiPath",
      residencyRetireApiPath("44444444-4444-4444-8444-444444444444"),
    ),
  ],
  "src/pages/models/ProvidersPage.tsx providerSwitchApiPath(pending.provider)": [
    at("PUT /api/v1/models/providers/{provider}", "providerSwitchApiPath", providerSwitchApiPath("anthropic")),
  ],
  "src/components/ModelPrices.tsx PRICES_API_PATH": [at("PUT /api/v1/models/prices", "PRICES_API_PATH", PRICES_API_PATH)],
  "src/pages/models/ProvidersPage.tsx PROFILE_API_PATH": [at("PUT /api/v1/models/profile", "PROFILE_API_PATH", PROFILE_API_PATH)],
  "src/pages/models/ProvidersPage.tsx providerCheckApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/check", "providerCheckApiPath", providerCheckApiPath("anthropic")),
  ],
  "src/pages/models/ProviderDetailPage.tsx providerSwitchApiPath(pending.provider)": [
    at("PUT /api/v1/models/providers/{provider}", "providerSwitchApiPath", providerSwitchApiPath("anthropic")),
  ],
  "src/pages/models/ProviderDetailPage.tsx providerCheckApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/check", "providerCheckApiPath", providerCheckApiPath("anthropic")),
  ],
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
  "POST /api/v1/routing/rungs/{rung_id}/move": {
    row: STEP_MOVED_AND_RETIRED,
    audit: STEP_MOVED_AND_RETIRED,
    behaviour: STEP_MOVED_AND_RETIRED,
  },
  "POST /api/v1/routing/rungs/{rung_id}/retire": {
    row: STEP_MOVED_AND_RETIRED,
    audit: STEP_MOVED_AND_RETIRED,
    behaviour: STEP_MOVED_AND_RETIRED,
  },
  "POST /api/v1/routing/rungs": {
    row: t("test_routing_routes", "test_a_rung_is_added_at_the_end_of_its_tier_only_through_the_gate"),
    audit: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    behaviour: t("test_model_calls", "test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release"),
  },
  "PUT /api/v1/models/providers/{provider}/terms": {
    row: t("test_provider_registry_routes", "test_terms_recorded_for_a_built_in_provider_write_its_first_registry_row"),
    audit: REGISTRY_LEDGERED,
    behaviour: t(
      "test_model_calls",
      "test_a_constrained_call_skips_an_undocumented_rung_for_the_documented_one_behind_it",
    ),
  },
  "POST /api/v1/models/providers/{provider}/retire": {
    row: t("test_provider_registry_routes", "test_an_added_provider_is_retired_and_a_built_in_one_cannot_be"),
    audit: REGISTRY_LEDGERED,
    behaviour: t("test_model_assembly", "test_a_provider_with_no_driver_is_told_which_of_the_two_things_is_missing"),
  },
  "POST /api/v1/models/providers": {
    row: t("test_provider_registry_routes", "test_an_added_provider_has_its_key_kept_in_its_own_slot_before_its_row_is_written"),
    audit: t("test_credential_routes", "test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace"),
    behaviour: t("test_model_calls", "test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release"),
  },
  "PUT /api/v1/models/tiers/{tier}": {
    row: t("test_model_health_routes", "test_a_tier_rule_is_written_as_the_window_and_only_the_keys_the_router_reads"),
    audit: {
      none: "A tier's numbers are logged and not written to the audit ledger in this release.",
      leaf: "M5.2.2",
    },
    behaviour: t("test_model_calls", "test_a_request_is_classified_against_the_tier_table_the_ladder_read"),
  },
  "POST /api/v1/models/tiers/{tier}/reset": {
    row: t("test_model_health_routes", "test_a_reset_retires_the_row_so_the_tier_runs_at_the_product_default"),
    audit: {
      none: "Resetting a tier is logged and not written to the audit ledger in this release.",
      leaf: "M5.2.2",
    },
    behaviour: t("test_tier_rules", "test_a_tier_with_no_row_runs_at_the_compiled_numbers_and_is_not_marked_configured"),
  },
  "POST /api/v1/models/residency": {
    row: t("test_model_health_routes", "test_a_residency_constraint_is_written_with_its_scope_and_regions"),
    audit: {
      none: "A residency constraint is logged and not written to the audit ledger in this release.",
      leaf: "M5.5.1",
    },
    behaviour: t("test_model_calls", "test_a_reach_touching_a_constrained_scope_skips_the_rung_outside_its_regions"),
  },
  "POST /api/v1/models/residency/{constraint_id}/retire": {
    row: t("test_model_health_routes", "test_retiring_a_constraint_marks_it_retired_and_deletes_nothing"),
    audit: {
      none: "Retiring a residency constraint is logged and not written to the audit ledger in this release.",
      leaf: "M5.5.1",
    },
    behaviour: t("test_model_calls", "test_a_reach_with_nowhere_compliant_is_refused_and_one_elsewhere_is_answered"),
  },
  "PUT /api/v1/models/providers/{provider}": {
    row: t("test_model_service", "test_the_stores_read_the_ladder_write_attempts_by_id_and_keep_a_switch", true),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_provider_routes", "test_switching_a_provider_off_takes_its_rungs_out_of_the_next_plan_at_once"),
  },
  "PUT /api/v1/models/prices": {
    row: t("test_usage_store", "test_the_price_of_each_model_is_merged_into_its_providers_one_row", true),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_usage_store", "test_a_model_call_is_metered_once_however_often_its_request_is_recorded", true),
  },
  "PUT /api/v1/models/profile": {
    row: t("test_provider_routes", "test_where_answers_are_made_is_saved_by_the_super_administrator_ledgered_and_planned_at_once"),
    audit: {
      none: "The route sets the audit attribution 0059's trigger reads, which the row test asserts over a stub; no scratch-Postgres test yet reads the ledger entry back.",
    },
    behaviour: t("test_provider_routes", "test_where_answers_are_made_is_saved_by_the_super_administrator_ledgered_and_planned_at_once"),
  },
  "POST /api/v1/models/providers/{provider}/check": {
    row: t("test_provider_routes", "test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question"),
    audit: { notApplicable: "A check changes no setting and no record an administrator manages; it is a metered call on the request ledger, not a change to audit." },
    behaviour: t("test_provider_routes", "test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question"),
  },
};
