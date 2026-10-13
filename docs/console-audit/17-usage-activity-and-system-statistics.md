### Usage, activity and system statistics

- **Screens:** `/usage`, `/adoption`, `/spend`, `/questions`, `/quality`, `/service-levels`, `/me`, `/company/estate`, `/company/activity`, `/company/consumption`
- **Tables:** `ops.question_asked`, `ops.question_gap`, `ops.report_refresh`, `ops.spend_actual`, `obs.request_telemetry`, `ops.answer_flag`, `ops.regression_case`, `ops.quality_reading`, `ops.quality_annotation`, `ops.golden_score`, `ops.evaluation_candidate`, `ops.positive_example`, `ops.tier_decision`
- **Installation values:** none
- **Measured here:** 18 routes, 8 called by no screen; 1 write routes, 1 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/company/activity` | `/company/activity` |
| `GET /api/v1/company/consumption` | `/company/consumption` |
| `GET /api/v1/company/estate` | `/company/estate` |
| `GET /api/v1/me/workspace` | `/me` |
| `GET /api/v1/quality/candidates` | **no screen** |
| `GET /api/v1/quality/flags` | **no screen** |
| `GET /api/v1/quality/sample` | **no screen** |
| `GET /api/v1/report/adoption` | `/adoption` |
| `GET /api/v1/report/quality` | `/quality` |
| `GET /api/v1/report/questions` | `/department`, `/questions` |
| `GET /api/v1/report/service-levels` | `/service-levels` |
| `GET /api/v1/report/spend` | `/spend` |
| `GET /api/v1/report/usage` | `/adoption`, `/department`, `/usage` |
| `POST /api/v1/quality/annotations` | **no screen** |
| `POST /api/v1/quality/candidates/{candidate_id}/decision` | **no screen** |
| `POST /api/v1/quality/flags` | **no screen** |
| `POST /api/v1/quality/flags/{flag_id}/case` | **no screen** |
| `PUT /api/v1/company/budget` | **no screen** |

- **Gap.** Flagging an answer, annotating a day's sample and deciding a candidate have no screen: the Quality screen draws the canary run and not the findings. Recorded: brain.quality_routes serves each as a door and no page presses them yet (M28.3.1, M28.3.3, M28.4.1); a captured case, a golden score and an example are stored and read by the install checks only.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `PUT /api/v1/company/budget` | **no screen** | `test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries` in `tests/unit/test_company_budget_route.py` (database, in CI) | `test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries` in `tests/unit/test_company_budget_route.py` (database, in CI) | `test_setting_the_companys_budget_is_refused_in_words_naming_the_role_and_never_to_a_stranger` in `tests/unit/test_company_routes.py` |
