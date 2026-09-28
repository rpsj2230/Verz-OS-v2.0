/**
 * What the console audit holds about the `people` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { STEWARD_API_PATH } from "../../../src/pages/dataStewardQuery";
import { DISABLE_API_PATH, ENABLE_API_PATH } from "../../../src/pages/governPeopleQuery";
import {
  GRANTS_API_PATH,
  PACK_ASSIGNMENT_API_PATH,
  REMOVAL_API_PATH,
  SEVERAL_GRANTS_API_PATH,
} from "../../../src/pages/governQuery";
import { at, audited, type Proofs, t, type WriteRoute } from "../auditClaims";

const GRANTS_PRESSED = audited("test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach");

const SEVERAL_PRESSED = audited("test_a_grant_to_several_is_written_for_everybody_or_for_nobody_against_postgresql");

const DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN = t(
  "test_principal_state",
  "test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/People.tsx REMOVAL_API_PATH": [at("POST /api/v1/govern/grants/removal", "REMOVAL_API_PATH", REMOVAL_API_PATH)],
  "src/pages/People.tsx GRANTS_API_PATH": [at("POST /api/v1/govern/grants", "GRANTS_API_PATH", GRANTS_API_PATH)],
  "src/pages/People.tsx SEVERAL_GRANTS_API_PATH": [
    at("POST /api/v1/govern/grants/several", "SEVERAL_GRANTS_API_PATH", SEVERAL_GRANTS_API_PATH),
  ],
  "src/pages/People.tsx disable ? DISABLE_API_PATH : ENABLE_API_PATH": [
    at("POST /api/v1/govern/people/disable", "DISABLE_API_PATH", DISABLE_API_PATH),
    at("POST /api/v1/govern/people/enable", "ENABLE_API_PATH", ENABLE_API_PATH),
  ],
  "src/components/DataStewardCard.tsx STEWARD_API_PATH": [
    at("POST /api/v1/govern/data-steward", "STEWARD_API_PATH", STEWARD_API_PATH),
  ],
  "src/pages/People.tsx PACK_ASSIGNMENT_API_PATH": [
    at("POST /api/v1/govern/packs/assignment", "PACK_ASSIGNMENT_API_PATH", PACK_ASSIGNMENT_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/people/disable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/people/enable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/grants/removal": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  "POST /api/v1/govern/grants": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  // Each row of a grant to several is the single grant's insert, so its ledger entry is the one the
  // single grant's database test follows; what is its own is that all of them land or none do.
  "POST /api/v1/govern/grants/several": {
    row: SEVERAL_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: SEVERAL_PRESSED,
  },
  "POST /api/v1/govern/data-steward": {
    row: t(
      "test_data_steward_routes",
      "test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice",
      true,
    ),
    audit: t("test_data_steward", "test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it", true),
    behaviour: t(
      "test_data_steward",
      "test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot",
      true,
    ),
  },
  "POST /api/v1/govern/packs/assignment": {
    row: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    audit: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    behaviour: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
  },
};
