### Usage, activity and system statistics

- **Screens:** `/usage`, `/adoption`, `/spend`, `/questions`, `/quality`, `/service-levels`, `/me`, `/company/estate`, `/company/activity`, `/company/consumption`
- **Tables:** `agent.artifact_share`, `agent.agent_request`, `auth.member_preference`, `ops.question_asked`, `ops.question_gap`, `ops.report_refresh`, `ops.spend_actual`, `obs.request_telemetry`, `ops.answer_flag`, `ops.regression_case`, `ops.quality_reading`, `ops.quality_annotation`, `ops.golden_score`, `ops.evaluation_candidate`, `ops.positive_example`, `ops.tier_decision`
- **Installation values:** none
- **Measured here:** 53 routes, 13 called by no screen; 16 write routes, 16 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/company/activity` | `/company/activity` |
| `GET /api/v1/company/consumption` | `/company/consumption` |
| `GET /api/v1/company/estate` | `/company/estate` |
| `GET /api/v1/me/agent-requests` | **no screen** |
| `GET /api/v1/me/agents/requestable` | `/me` |
| `GET /api/v1/me/agents/{agent_id}/starters` | **no screen** |
| `GET /api/v1/me/artifacts` | `/me` |
| `GET /api/v1/me/devices` | `/me` |
| `GET /api/v1/me/preferences` | `/me` |
| `GET /api/v1/me/projects` | `/me` |
| `GET /api/v1/me/projects/{project_id}` | **no screen** |
| `GET /api/v1/me/reads` | `/me` |
| `GET /api/v1/me/shared` | `/me` |
| `GET /api/v1/me/shared/{artifact_id}/download` | **no screen** |
| `GET /api/v1/me/shares` | `/me` |
| `GET /api/v1/me/skills` | `/me` |
| `GET /api/v1/me/skills/{digest}/try` | **no screen** |
| `GET /api/v1/me/stored` | `/me` |
| `GET /api/v1/me/workspace` | `/me` |
| `GET /api/v1/quality/candidates` | **no screen** |
| `GET /api/v1/quality/flags` | **no screen** |
| `GET /api/v1/quality/sample` | **no screen** |
| `GET /api/v1/report/adoption` | `/adoption` |
| `GET /api/v1/report/coverage` | `/adoption` |
| `GET /api/v1/report/quality` | `/quality` |
| `GET /api/v1/report/questions` | `/department`, `/questions` |
| `GET /api/v1/report/service-levels` | `/service-levels` |
| `GET /api/v1/report/spend` | `/spend` |
| `GET /api/v1/report/spend/cost-per-answer` | `/spend` |
| `GET /api/v1/report/spend/providers` | `/spend` |
| `GET /api/v1/report/spend/shapes` | `/spend` |
| `GET /api/v1/report/spend/stops` | `/spend` |
| `GET /api/v1/report/usage` | `/adoption`, `/department`, `/usage` |
| `POST /api/v1/me/agents/{agent_id}/request` | `/me` |
| `POST /api/v1/me/artifacts/{artifact_id}/share` | `/me` |
| `POST /api/v1/me/artifacts/{artifact_id}/unshare` | `/me` |
| `POST /api/v1/me/devices/end` | `/me` |
| `POST /api/v1/me/preferences/learning` | `/me` |
| `POST /api/v1/me/preferences/quiet-hours` | `/me` |
| `POST /api/v1/me/preferences/reach` | `/me` |
| `POST /api/v1/me/projects` | `/me` |
| `POST /api/v1/me/projects/{project_id}/archive` | `/me` |
| `POST /api/v1/me/projects/{project_id}/items` | `/ask`, `/me` |
| `POST /api/v1/me/projects/{project_id}/items/remove` | `/me` |
| `POST /api/v1/me/projects/{project_id}/rename` | `/me` |
| `POST /api/v1/me/skills` | `/me` |
| `POST /api/v1/me/skills/imports` | `/me` |
| `POST /api/v1/me/skills/{digest}/offer` | `/me` |
| `POST /api/v1/quality/annotations` | **no screen** |
| `POST /api/v1/quality/candidates/{candidate_id}/decision` | **no screen** |
| `POST /api/v1/quality/flags` | **no screen** |
| `POST /api/v1/quality/flags/{flag_id}/case` | **no screen** |
| `PUT /api/v1/company/budget` | **no screen** |

- **Gap.** Flagging an answer, annotating a day's sample and deciding a candidate have no screen: the Quality screen draws the canary run and not the findings. Recorded: brain.quality_routes serves each as a door and no page presses them yet (M28.3.1, M28.3.3, M28.4.1); a captured case, a golden score and an example are stored and read by the install checks only.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/me/agents/{agent_id}/request` | `/me` | `test_the_request_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_agent_request.py` (database, in CI) | Not applicable: A request changes nobody's access; what a department decides is written where audiences are changed. | `test_a_lead_told_every_time_fails_the_check` in `tests/unit/test_acceptance_checks_member_agent_request.py` (database, in CI) |
| `POST /api/v1/me/artifacts/{artifact_id}/share` | `/me` | `test_the_share_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_share.py` (database, in CI) | Not applicable: A share changes nobody's access; opening what was shared is written down as the read it is. | `test_a_share_with_somebody_who_cannot_open_it_fails_the_check` in `tests/unit/test_acceptance_checks_member_share.py` (database, in CI) |
| `POST /api/v1/me/artifacts/{artifact_id}/unshare` | `/me` | `test_the_share_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_share.py` (database, in CI) | Not applicable: Taking a share back changes nobody's access; it only removes a row that admitted nobody. | `test_the_share_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_share.py` (database, in CI) |
| `POST /api/v1/me/devices/end` | `/me` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_every_member_account_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_account.py` (database, in CI) |
| `POST /api/v1/me/preferences/learning` | `/me` | `test_every_member_preference_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) | Not applicable: A person's own setting about being reached changes nobody's access and is not written to the ledger. | `test_a_person_learnt_from_after_switching_it_off_fails_the_learning_check` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) |
| `POST /api/v1/me/preferences/quiet-hours` | `/me` | `test_every_member_preference_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) | Not applicable: A person's own setting about being reached changes nobody's access and is not written to the ledger. | `test_a_digest_sent_inside_quiet_hours_fails_the_held_digest_check` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) |
| `POST /api/v1/me/preferences/reach` | `/me` | `test_every_member_preference_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) | Not applicable: A person's own setting about being reached changes nobody's access and is not written to the ledger. | `test_a_card_sent_to_an_approver_who_chose_the_console_fails_the_approval_check` in `tests/unit/test_acceptance_checks_member_preferences.py` (database, in CI) |
| `POST /api/v1/me/projects` | `/me` | `test_the_project_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_projects.py` (database, in CI) | Not applicable: A project is a person's own list of their own conversations and documents; it changes nobody's access and is not written to the ledger. | `test_a_person_makes_names_fills_and_puts_away_a_project_of_their_own` in `tests/unit/test_project_routes.py` |
| `POST /api/v1/me/projects/{project_id}/archive` | `/me` | `test_the_project_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_projects.py` (database, in CI) | Not applicable: Putting one's own project away changes nobody's access and is not written to the ledger; its items stay where they are. | `test_a_person_makes_names_fills_and_puts_away_a_project_of_their_own` in `tests/unit/test_project_routes.py` |
| `POST /api/v1/me/projects/{project_id}/items` | `/ask`, `/me` | `test_the_project_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_projects.py` (database, in CI) | Not applicable: Listing one's own conversation or a document one may read in one's own project grants nothing: what a run reads is decided at its reach, every turn. | `test_a_question_naming_a_project_brings_that_projects_files_read_by_the_document_tool` in `tests/unit/test_project_context.py` |
| `POST /api/v1/me/projects/{project_id}/items/remove` | `/me` | `test_the_project_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_projects.py` (database, in CI) | Not applicable: Taking something out of one's own project changes nobody's access and is not written to the ledger. | `test_with_the_switch_off_nothing_new_is_made_and_nothing_made_is_trapped` in `tests/unit/test_project_routes.py` |
| `POST /api/v1/me/projects/{project_id}/rename` | `/me` | `test_the_project_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_member_projects.py` (database, in CI) | Not applicable: Renaming one's own project changes nobody's access and is not written to the ledger. | `test_somebody_elses_project_is_answered_as_one_never_made_on_every_route` in `tests/unit/test_project_routes.py` |
| `POST /api/v1/me/skills` | `/me` | `test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library` in `tests/unit/test_personal_skill_store.py` (database, in CI) | `test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library` in `tests/unit/test_personal_skill_store.py` (database, in CI) | `test_a_new_skill_reads_as_private_pending_and_studio_written` in `tests/unit/test_member_skill_routes.py` |
| `POST /api/v1/me/skills/imports` | `/me` | `test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library` in `tests/unit/test_personal_skill_store.py` (database, in CI) | `test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library` in `tests/unit/test_personal_skill_store.py` (database, in CI) | `test_a_skill_from_an_address_is_the_persons_own_with_an_address_origin` in `tests/unit/test_member_skill_routes.py` |
| `POST /api/v1/me/skills/{digest}/offer` | `/me` | `test_a_skill_nobody_offered_is_the_owners_alone_and_offering_puts_it_in_the_library` in `tests/unit/test_personal_skill_store.py` (database, in CI) | Not applicable: Offering a skill changes nobody's access and runs nothing: it puts the person's own skill in front of the people who read the library, and the decision they make is the ledger entry. | `test_offering_marks_the_skill_offered_once_and_says_what_happens_next` in `tests/unit/test_member_skill_routes.py` |
| `PUT /api/v1/company/budget` | **no screen** | `test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries` in `tests/unit/test_company_budget_route.py` (database, in CI) | `test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries` in `tests/unit/test_company_budget_route.py` (database, in CI) | `test_setting_the_companys_budget_is_refused_in_words_naming_the_role_and_never_to_a_stranger` in `tests/unit/test_company_routes.py` |
