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
  ROLE_REMOVAL_API_PATH,
} from "../../../src/pages/governQuery";
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

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/RoleControls.tsx path": [
    at("POST /api/v1/govern/roles/appointment", "APPOINTMENT_API_PATH", APPOINTMENT_API_PATH),
    at("POST /api/v1/govern/roles/deputy", "DEPUTY_API_PATH", DEPUTY_API_PATH),
  ],
  "src/pages/GroupRules.tsx GROUP_RULES_API_PATH": [
    at("POST /api/v1/govern/roles/group-rules", "GROUP_RULES_API_PATH", GROUP_RULES_API_PATH),
  ],
  "src/pages/GroupRules.tsx GROUP_RULE_RETIREMENT_API_PATH": [
    at(
      "POST /api/v1/govern/roles/group-rules/retirement",
      "GROUP_RULE_RETIREMENT_API_PATH",
      GROUP_RULE_RETIREMENT_API_PATH,
    ),
  ],
  "src/pages/RoleControls.tsx ROLE_REMOVAL_API_PATH": [
    at("POST /api/v1/govern/roles/removal", "ROLE_REMOVAL_API_PATH", ROLE_REMOVAL_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
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
};
