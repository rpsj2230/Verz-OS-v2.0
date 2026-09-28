/**
 * What the console audit holds about the `departments` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import {
  ADD_TEAM_API_PATH,
  DISABLE_API_PATH,
  DRAW_SCOPE_API_PATH,
  ENABLE_API_PATH,
  FOUND_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  RENAME_DEPARTMENT_API_PATH,
  RENAME_TEAM_API_PATH,
  RETIRE_DEPARTMENT_API_PATH,
  RETIRE_SCOPE_API_PATH,
  RETIRE_TEAM_API_PATH,
} from "../../../src/pages/governPeopleQuery";
import { at, type Proof, type Proofs, t, type WriteRoute } from "../auditClaims";

const PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE = t(
  "test_organisation_store",
  "test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page",
  true,
);

/** The structure's eight writes (M27.11.1): each row and its ledger entry, and what each changes. */
const STRUCTURE_REACHES_THE_ROWS_AND_THE_LEDGER = t(
  "test_organisation_structure",
  "test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor",
  true,
);

const A_NEW_SCOPE_IS_GRANTABLE = t(
  "test_organisation_structure",
  "test_a_grant_over_a_newly_drawn_scope_is_written_through_the_grant_route",
  true,
);

const A_RETIREMENT_WAITS_FOR_LIVE_GRANTS = t(
  "test_organisation_structure",
  "test_a_department_is_retired_only_once_its_live_grants_move_and_then_refuses_new_ones",
  true,
);

const THE_STRUCTURE_CHANGES_AS_ASKED = t(
  "test_organisation_structure",
  "test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes",
);

function structure(behaviour: Proof): Proofs {
  return { row: STRUCTURE_REACHES_THE_ROWS_AND_THE_LEDGER, audit: STRUCTURE_REACHES_THE_ROWS_AND_THE_LEDGER, behaviour };
}

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Departments.tsx asked.path": [
    at("POST /api/v1/govern/departments/membership", "MEMBERSHIP_API_PATH", MEMBERSHIP_API_PATH),
    at("POST /api/v1/govern/departments/lead", "LEAD_API_PATH", LEAD_API_PATH),
    at("POST /api/v1/govern/departments", "FOUND_API_PATH", FOUND_API_PATH),
    at("POST /api/v1/govern/departments/rename", "RENAME_DEPARTMENT_API_PATH", RENAME_DEPARTMENT_API_PATH),
    at("POST /api/v1/govern/departments/retirement", "RETIRE_DEPARTMENT_API_PATH", RETIRE_DEPARTMENT_API_PATH),
    at("POST /api/v1/govern/departments/team", "ADD_TEAM_API_PATH", ADD_TEAM_API_PATH),
    at("POST /api/v1/govern/departments/team/rename", "RENAME_TEAM_API_PATH", RENAME_TEAM_API_PATH),
    at("POST /api/v1/govern/departments/team/retirement", "RETIRE_TEAM_API_PATH", RETIRE_TEAM_API_PATH),
    at("POST /api/v1/govern/departments/scopes", "DRAW_SCOPE_API_PATH", DRAW_SCOPE_API_PATH),
    at("POST /api/v1/govern/departments/scopes/retirement", "RETIRE_SCOPE_API_PATH", RETIRE_SCOPE_API_PATH),
    at("POST /api/v1/govern/people/disable", "DISABLE_API_PATH", DISABLE_API_PATH),
    at("POST /api/v1/govern/people/enable", "ENABLE_API_PATH", ENABLE_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/departments/membership": {
    row: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    audit: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    behaviour: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
  },
  "POST /api/v1/govern/departments/lead": {
    row: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    audit: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    behaviour: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
  },
  "POST /api/v1/govern/departments": structure(A_NEW_SCOPE_IS_GRANTABLE),
  "POST /api/v1/govern/departments/rename": structure(THE_STRUCTURE_CHANGES_AS_ASKED),
  "POST /api/v1/govern/departments/retirement": structure(A_RETIREMENT_WAITS_FOR_LIVE_GRANTS),
  "POST /api/v1/govern/departments/team": structure(THE_STRUCTURE_CHANGES_AS_ASKED),
  "POST /api/v1/govern/departments/team/rename": structure(THE_STRUCTURE_CHANGES_AS_ASKED),
  "POST /api/v1/govern/departments/team/retirement": structure(THE_STRUCTURE_CHANGES_AS_ASKED),
  "POST /api/v1/govern/departments/scopes": structure(A_NEW_SCOPE_IS_GRANTABLE),
  "POST /api/v1/govern/departments/scopes/retirement": structure(THE_STRUCTURE_CHANGES_AS_ASKED),
};
