/**
 * What the console audit holds about the `service-accounts` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import {
  ISSUE_KEY_API_PATH,
  RETIRE_ACCOUNT_API_PATH,
  REVOKE_KEY_API_PATH,
  SERVICE_ACCOUNTS_API_PATH,
} from "../../../src/pages/serviceAccountsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

/** A service account registered and keyed on real rows, its two ledger entries, and the key acting. */
const A_KEY_ACTS_AT_ITS_OWNERS_REACH = t(
  "test_service_accounts",
  "test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner",
  true,
);

/** A key revoked and an account retired on real rows, and neither found by the request path after. */
const A_RETIRED_KEY_IS_NOT_FOUND = t(
  "test_service_accounts",
  "test_a_retired_key_or_account_is_not_found_by_the_request_path",
  true,
);

const A_REVOCATION_AND_A_RETIREMENT_ARE_RECORDED = t(
  "test_service_account_audit",
  "test_a_revoked_key_and_a_retired_account_each_leave_one_entry_naming_the_owner",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/service-accounts/AccountActs.tsx SERVICE_ACCOUNTS_API_PATH": [
    at("POST /api/v1/govern/service-accounts", "SERVICE_ACCOUNTS_API_PATH", SERVICE_ACCOUNTS_API_PATH),
  ],
  "src/pages/service-accounts/AccountActs.tsx ISSUE_KEY_API_PATH": [
    at("POST /api/v1/govern/service-accounts/keys", "ISSUE_KEY_API_PATH", ISSUE_KEY_API_PATH),
  ],
  "src/pages/service-accounts/AccountActs.tsx REVOKE_KEY_API_PATH": [
    at("POST /api/v1/govern/service-accounts/keys/revoke", "REVOKE_KEY_API_PATH", REVOKE_KEY_API_PATH),
  ],
  "src/pages/service-accounts/AccountActs.tsx RETIRE_ACCOUNT_API_PATH": [
    at("POST /api/v1/govern/service-accounts/retire", "RETIRE_ACCOUNT_API_PATH", RETIRE_ACCOUNT_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/service-accounts": {
    row: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
    audit: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
    behaviour: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
  },
  "POST /api/v1/govern/service-accounts/keys": {
    row: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
    audit: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
    behaviour: A_KEY_ACTS_AT_ITS_OWNERS_REACH,
  },
  "POST /api/v1/govern/service-accounts/keys/revoke": {
    row: A_RETIRED_KEY_IS_NOT_FOUND,
    audit: A_REVOCATION_AND_A_RETIREMENT_ARE_RECORDED,
    behaviour: A_RETIRED_KEY_IS_NOT_FOUND,
  },
  "POST /api/v1/govern/service-accounts/retire": {
    row: A_RETIRED_KEY_IS_NOT_FOUND,
    audit: A_REVOCATION_AND_A_RETIREMENT_ARE_RECORDED,
    behaviour: A_RETIRED_KEY_IS_NOT_FOUND,
  },
};
