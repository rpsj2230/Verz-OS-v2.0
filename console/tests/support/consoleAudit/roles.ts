/**
 * What the console audit holds about the `roles` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import {
  APPOINTMENT_API_PATH,
  DEPUTY_API_PATH,
  GROUP_RULE_RETIREMENT_API_PATH,
  GROUP_RULES_API_PATH,
  NOMINATIONS_API_PATH,
  ROLE_REMOVAL_API_PATH,
  nominationDecisionApiPath,
} from "../../../src/pages/governQuery";
import {
  PACK_COPY_API_PATH,
  PACK_RETIREMENT_API_PATH,
  PACK_VERSION_API_PATH,
  PACKS_API_PATH,
} from "../../../src/pages/roles/PacksPage";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const GROUP_RULES_PRESSED = t(
  "test_group_sync",
  "test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger",
  true,
);

const ROLES_PRESSED = t(
  "test_role_grant",
  "test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason",
  true,
);

/** A nomination made, offered to its decider, confirmed into a role grant on the ledger (M33.1.2.3). */
const NOMINATION_CONFIRMED = t(
  "test_role_nominations",
  "test_a_third_person_confirms_a_nomination_into_a_role_grant_on_the_ledger",
  true,
);

/** Why making or declining a nomination writes no ledger entry: the row is the record. */
const A_NOMINATION_IS_ITS_OWN_RECORD =
  "A nomination grants nothing and a decline appoints nobody, so neither changes anybody's access, which is what the ledger records; each is a row of gate.role_nomination naming who proposed whom, why, and who decided. A confirmation writes its role grant, and that grant is on the ledger.";

const PACK_WRITE_REACHES_EVERYTHING = t(
  "test_govern_pack_routes",
  "test_each_pack_write_reaches_its_row_one_ledger_entry_and_every_holder",
  true,
);

const PACK_WRITTEN: Proofs = {
  row: PACK_WRITE_REACHES_EVERYTHING,
  audit: PACK_WRITE_REACHES_EVERYTHING,
  behaviour: PACK_WRITE_REACHES_EVERYTHING,
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/roles/RoleDrawers.tsx nominating ? NOMINATIONS_API_PATH : APPOINTMENT_API_PATH": [
    at("POST /api/v1/govern/roles/nominations", "NOMINATIONS_API_PATH", NOMINATIONS_API_PATH),
    at("POST /api/v1/govern/roles/appointment", "APPOINTMENT_API_PATH", APPOINTMENT_API_PATH),
  ],
  "src/pages/roles/RoleDrawers.tsx nominationDecisionApiPath(nomination.id)": [
    at(
      "POST /api/v1/govern/roles/nominations/{nomination_id}/decision",
      "nominationDecisionApiPath",
      nominationDecisionApiPath("11111111-1111-4111-8111-000000000001"),
    ),
  ],
  "src/pages/roles/RoleDrawers.tsx DEPUTY_API_PATH": [at("POST /api/v1/govern/roles/deputy", "DEPUTY_API_PATH", DEPUTY_API_PATH)],
  "src/pages/roles/RoleDrawers.tsx GROUP_RULES_API_PATH": [
    at("POST /api/v1/govern/roles/group-rules", "GROUP_RULES_API_PATH", GROUP_RULES_API_PATH),
  ],
  "src/pages/roles/RoleDrawers.tsx GROUP_RULE_RETIREMENT_API_PATH": [
    at(
      "POST /api/v1/govern/roles/group-rules/retirement",
      "GROUP_RULE_RETIREMENT_API_PATH",
      GROUP_RULE_RETIREMENT_API_PATH,
    ),
  ],
  "src/pages/roles/RoleDrawers.tsx ROLE_REMOVAL_API_PATH": [
    at("POST /api/v1/govern/roles/removal", "ROLE_REMOVAL_API_PATH", ROLE_REMOVAL_API_PATH),
  ],
  "src/pages/roles/PacksPage.tsx PACKS_API_PATH": [at("POST /api/v1/govern/packs", "PACKS_API_PATH", PACKS_API_PATH)],
  "src/pages/roles/PacksPage.tsx PACK_VERSION_API_PATH": [
    at("POST /api/v1/govern/packs/version", "PACK_VERSION_API_PATH", PACK_VERSION_API_PATH),
  ],
  "src/pages/roles/PacksPage.tsx PACK_COPY_API_PATH": [at("POST /api/v1/govern/packs/copy", "PACK_COPY_API_PATH", PACK_COPY_API_PATH)],
  "src/pages/roles/PacksPage.tsx PACK_RETIREMENT_API_PATH": [
    at("POST /api/v1/govern/packs/retirement", "PACK_RETIREMENT_API_PATH", PACK_RETIREMENT_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/packs": PACK_WRITTEN,
  "POST /api/v1/govern/packs/version": PACK_WRITTEN,
  "POST /api/v1/govern/packs/copy": PACK_WRITTEN,
  "POST /api/v1/govern/packs/retirement": PACK_WRITTEN,
  "POST /api/v1/govern/roles/appointment": {
    row: ROLES_PRESSED,
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_the_last_two_super_admins_cannot_be_reduced_to_one"),
  },
  "POST /api/v1/govern/roles/deputy": {
    row: t("test_role_grant", "test_the_guard_keeps_deputies_depth_one_and_the_table_keeps_them_bounded", true),
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_a_deputy_covers_a_standing_holder_and_never_another_deputy"),
  },
  "POST /api/v1/govern/roles/removal": {
    row: ROLES_PRESSED,
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_the_guard_refuses_a_removal_below_the_floor_and_allows_one_above_it", true),
  },
  "POST /api/v1/govern/roles/group-rules": {
    row: GROUP_RULES_PRESSED,
    audit: GROUP_RULES_PRESSED,
    behaviour: t("test_group_sync", "test_a_sign_in_writes_and_removes_synced_rows_and_the_ledger_records_both", true),
  },
  "POST /api/v1/govern/roles/group-rules/retirement": {
    row: GROUP_RULES_PRESSED,
    audit: GROUP_RULES_PRESSED,
    behaviour: GROUP_RULES_PRESSED,
  },
  "POST /api/v1/govern/roles/nominations": {
    row: NOMINATION_CONFIRMED,
    audit: { notApplicable: A_NOMINATION_IS_ITS_OWN_RECORD },
    behaviour: t("test_role_nominations", "test_nobody_nominates_themselves_and_nobody_off_the_roles_screen_nominates_at_all", true),
  },
  "POST /api/v1/govern/roles/nominations/{nomination_id}/decision": {
    row: NOMINATION_CONFIRMED,
    audit: NOMINATION_CONFIRMED,
    behaviour: t("test_role_nominations", "test_a_confirmation_crossing_the_separation_of_duties_needs_its_acknowledgement", true),
  },
};
