/**
 * What the console audit holds about the `skills` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import {
  assignPath,
  categoriesPath,
  detachPath,
  IMPORT_PATH,
  reinstatementPath,
  retirementPath,
  reviewPath,
  SKILLS_API_PATH,
  versionsPath,
} from "../../../src/pages/skillsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/skills/SkillForms.tsx SKILLS_API_PATH": [at("POST /api/v1/skills", "SKILLS_API_PATH", SKILLS_API_PATH)],
  "src/pages/skills/SkillForms.tsx IMPORT_PATH": [at("POST /api/v1/skills/imports", "IMPORT_PATH", IMPORT_PATH)],
  "src/pages/skills/SkillForms.tsx versionsPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/versions", "versionsPath", versionsPath("d".repeat(64))),
  ],
  "src/pages/skills/SkillForms.tsx categoriesPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/categories", "categoriesPath", categoriesPath("d".repeat(64))),
  ],
  "src/pages/skills/SkillProfile.tsx reviewPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/review", "reviewPath", reviewPath("d".repeat(64))),
  ],
  "src/pages/skills/SkillForms.tsx assignPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/assignments", "assignPath", assignPath("d".repeat(64))),
  ],
  "src/pages/skills/SkillProfile.tsx retired ? reinstatementPath(one.digest) : retirementPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/reinstatement", "reinstatementPath", reinstatementPath("d".repeat(64))),
    at("POST /api/v1/skills/{digest}/retirement", "retirementPath", retirementPath("d".repeat(64))),
  ],
  "src/pages/skills/SkillProfile.tsx detachPath(pin.digest)": [
    at("POST /api/v1/skills/{digest}/detachments", "detachPath", detachPath("d".repeat(64))),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/skills": {
    row: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    audit: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/skills/imports": {
    row: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    audit: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    behaviour: t("test_skill_routes", "test_an_administrator_imports_a_skill_from_a_repository_at_a_commit_and_it_waits"),
  },
  "POST /api/v1/skills/{digest}/versions": {
    row: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    audit: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    behaviour: t("test_skill_routes", "test_an_edit_waits_for_review_as_a_new_version_while_the_agent_keeps_its_pin"),
  },
  "POST /api/v1/skills/{digest}/categories": {
    row: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    audit: t("test_skill_store", "test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger", true),
    behaviour: t("test_skill_routes", "test_categories_set_on_a_skill_are_chips_that_filter_the_skills_in_use"),
  },
  "POST /api/v1/skills/{digest}/review": {
    row: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    audit: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/skills/{digest}/assignments": {
    row: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
    audit: t("test_skill_store", "test_the_database_refuses_an_unsaid_self_decision_and_an_assignment_nobody_approved", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/skills/{digest}/retirement": {
    row: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    audit: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    behaviour: t("test_skill_lifecycle", "test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached"),
  },
  "POST /api/v1/skills/{digest}/reinstatement": {
    row: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    audit: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    behaviour: t("test_skill_lifecycle", "test_a_retired_version_is_refused_to_new_agents_and_its_holders_are_listed_not_detached"),
  },
  "POST /api/v1/skills/{digest}/detachments": {
    row: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    audit: t("test_skill_lifecycle", "test_a_detachment_and_a_retirement_each_write_rows_and_entries_through_the_store", true),
    behaviour: t("test_skill_lifecycle", "test_a_detached_skill_is_gone_from_the_agent_and_its_assignment_is_no_longer_in_force"),
  },
};
