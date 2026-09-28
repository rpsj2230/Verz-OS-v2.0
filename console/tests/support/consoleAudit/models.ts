/**
 * What the console audit holds about the `models` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes, and the reads it makes only once somebody acts. `support/consoleAudit.ts`
 * collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import {
  ADD_PROVIDER_API_PATH,
  REGISTER_API_PATH as PROVIDER_REGISTER_API_PATH,
  retireProviderApiPath,
  termsApiPath,
} from "../../../src/pages/providerRegisterQuery";
import { PROFILE_API_PATH, providerCheckApiPath, providerSwitchApiPath } from "../../../src/pages/modelsQuery";
import {
  RESIDENCY_API_PATH,
  residencyRetireApiPath,
  tierApiPath,
  tierResetApiPath,
} from "../../../src/pages/routingSettingsQuery";
import { credentialPath } from "../../../src/components/ProviderKeyForm";
import {
  A_SETTING_ENTRY_NO_TEST_FOLLOWS,
  at,
  type Proofs,
  type ReadAfterAnAction,
  t,
  type WriteRoute,
} from "../auditClaims";

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  "GET /api/v1/models/providers-register": { screen: "/models", spelled: "REGISTER_API_PATH", built: PROVIDER_REGISTER_API_PATH },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/components/ProviderRegister.tsx termsApiPath(asked.provider)": [
    at("PUT /api/v1/models/providers/{provider}/terms", "termsApiPath", termsApiPath("anthropic")),
  ],
  "src/components/ProviderRegister.tsx retireProviderApiPath(asked.provider)": [
    at("POST /api/v1/models/providers/{provider}/retire", "retireProviderApiPath", retireProviderApiPath("acme_llm")),
  ],
  "src/components/ProviderRegister.tsx ADD_PROVIDER_API_PATH": [
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
  "src/pages/Models.tsx providerSwitchApiPath(pending.provider)": [
    at("PUT /api/v1/models/providers/{provider}", "providerSwitchApiPath", providerSwitchApiPath("anthropic")),
  ],
  "src/pages/Models.tsx PROFILE_API_PATH": [at("PUT /api/v1/models/profile", "PROFILE_API_PATH", PROFILE_API_PATH)],
  "src/pages/Models.tsx providerCheckApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/check", "providerCheckApiPath", providerCheckApiPath("anthropic")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/models/providers/{provider}/terms": {
    row: t("test_provider_registry_routes", "test_terms_recorded_for_a_built_in_provider_write_its_first_registry_row"),
    audit: {
      none: "A provider's terms are logged and not written to the audit ledger in this release.",
      leaf: "M5.6.4",
    },
    behaviour: t(
      "test_model_calls",
      "test_a_constrained_call_skips_an_undocumented_rung_for_the_documented_one_behind_it",
    ),
  },
  "POST /api/v1/models/providers/{provider}/retire": {
    row: t("test_provider_registry_routes", "test_an_added_provider_is_retired_and_a_built_in_one_cannot_be"),
    audit: {
      none: "Retiring an added provider is logged and not written to the audit ledger in this release.",
      leaf: "M5.6.4",
    },
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
