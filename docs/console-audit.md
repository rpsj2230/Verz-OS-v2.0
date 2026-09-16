# The console audit

What an administrator would need to manage, read out of the schema, the routes and the installation values, compared with what the console serves, screen by screen, with every gap either linked to its open leaf or recorded with its reason. It is the audit `docs/admin-console.md` asks for before the console is called done.

**This page is generated and must not be edited by hand.** `console/tests/console-audit.test.ts` renders it from `console/tests/support/consoleAudit.ts` and fails when this file differs. To regenerate it after a change, run `npm run api:generate` and then `WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts` in `console/`.

## What was measured

- 23 areas, the bullets of `docs/admin-console.md` in its order.
- 61 tables, from `brain.db.Base.metadata`.
- 21 installation values, from `brain.install.INSTALLATION`.
- 91 routes under `/api/v1` and `/setup`, from the API's internal document.
- 64 console addresses, from the route table in `console/src/App.tsx`.
- 27 calls in the console that send a write, from `console/tests/support/writes.ts`, reaching 32 routes.
- 33 gaps recorded, and 3 routes no screen calls.

## Area by area

### People, roles, permissions and access control

- **Screens:** `/`, `/people`, `/people/:subject`, `/roles`, `/capabilities`, `/scopes`, `/access_review`, `/elevation`, `/sessions`, `/sign-in-links`, `/staff_sources`
- **Tables:** `auth.principal`, `auth.principal_identity`, `auth.session`, `auth.directory_role_grant`, `gate.capability_grant`, `gate.capability_pack`, `gate.capability_pack_assignment`, `gate.capability_registry`, `gate.scope`, `gate.grants_version`, `gate.policy_epoch`, `gate.review_decision`
- **Installation values:** `INSTALL_OIDC_ISSUER`, `INSTALL_OIDC_REALM`, `INSTALL_OIDC_CLIENT_ID`, `INSTALL_OIDC_REDIRECT_URIS`, `INSTALL_BROKERED_DIRECTORY`, `INSTALL_STAFF_SOURCE`, `INSTALL_STAFF_SOURCE_LOCATION`

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/navigation` | `/department` |
| `GET /api/v1/govern/access-review` | `/access_review` |
| `GET /api/v1/govern/capabilities` | `/capabilities` |
| `GET /api/v1/govern/elevation` | `/elevation` |
| `GET /api/v1/govern/people` | `/people`, `/people/:subject` |
| `GET /api/v1/govern/roles` | `/roles` |
| `GET /api/v1/govern/scopes` | `/people/:subject`, `/scopes` |
| `GET /api/v1/govern/sessions` | `/sessions` |
| `GET /api/v1/govern/sign-ins` | `/sign-in-links` |
| `GET /api/v1/govern/staff_sources` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/trial` | `/staff_sources` |
| `GET /api/v1/me` | `/` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/sessions/end` | `/sessions` |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` |
| `POST /api/v1/sign-ins` | `/sign-in-links` |

- **Gap.** A grant written from People and grants cannot be given an expiry, and the screen says so beside the form. Recorded: Buildable today: POST /api/v1/govern/grants takes not_after and the form's proposal schema has no field for it. It is left to the change reworking member grants, which is in progress beside this one and owns that form.
- **Gap.** A pack cannot be assigned or withdrawn, and a capability that arrived through a pack cannot be removed. Recorded: No route writes gate.capability_pack_assignment. brain.govern_routes.remove_grant refuses a pack's capability in the ordinary words, because withdrawing it removes every other capability in the pack.
- **Gap.** Roles, capabilities and scopes are read and never changed. Recorded: No route writes gate.scope or the role and capability registries; they are declared by the product and by migrations.
- **Gap.** Nobody can raise or grant an elevation. Recorded: No install stores an elevation yet, and the Elevation requests screen says so where the list would be.
- **Gap.** The identity provider and the staff source cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.

### Departments, teams and client configuration

- **Screens:** `/departments`, `/department`
- **Tables:** `gate.department`, `gate.team`
- **Installation values:** `INSTALL_COMPANY_NAME`, `INSTALL_PRODUCT_NAME`, `INSTALL_LOGO_URL`, `INSTALL_ACCENT_COLOUR`

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/departments` | `/departments` |

- **Gap.** A department or a team cannot be created, renamed or removed, and nobody can be placed in one. Recorded: No route and no module under src/brain writes gate.department or gate.team, so the screen reads what is there and there is no writer to call.
- **Gap.** The company's name, product name, logo and accent cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.

### System settings and application configuration

- **Screens:** `/install`, `/limits`, `/connections`, `/first-run`, `/first-run/staff-list`
- **Tables:** `ops.setting`, `ops.budget_version`
- **Installation values:** `INSTALL_LOCALES`, `INSTALL_CURRENCY`, `INSTALL_TIME_ZONE`

| Route | Called by |
| --- | --- |
| `GET /api/v1/install` | `/install` |
| `GET /api/v1/install/capacity` | `/connections` |
| `GET /api/v1/install/limits` | `/limits` |
| `GET /setup/staff-source/registration` | `/first-run` |
| `POST /setup/appointment` | `/first-run` |
| `POST /setup/sign-in` | `/first-run` |
| `POST /setup/staff-source/sign-in` | `/first-run` |
| `POST /setup/staff-source/trial` | `/first-run` |

- **Gap.** Languages, currency and time zone cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.
- **Gap.** Limits and budgets are read and never changed. Recorded: No route writes ops.budget_version or a ceiling; a limit is a release today.

### AI providers, models and the routing between them

- **Screens:** `/models`, `/routing`, `/routing/:rungId`
- **Tables:** `ops.routing_rung`, `ops.routing_tier`, `ops.model_attempt`
- **Installation values:** `INSTALL_MODEL_PROFILE`, `INSTALL_MODEL_ENDPOINT`, `INSTALL_EMBEDDING_DIMENSIONS`

| Route | Called by |
| --- | --- |
| `GET /api/v1/operate/models` | `/models` |
| `GET /api/v1/routing/rungs` | `/models`, `/routing`, `/routing/:rungId` |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` |

- **Gap.** Saving a routing rung changes its row and no answer: nothing on the answer path reads ops.routing_rung, and every question runs through brain.models.routing.seed_chain. Open leaf `M27.8.8`.
- **Gap.** A provider key cannot be written or replaced from a screen after setup. Open leaf `M27.8.8`.
- **Gap.** The model profile and endpoint cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.

### Agents and their configuration, including templates

- **Screens:** `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/agent-templates`, `/approvals`, `/approvals/:suspensionId`
- **Tables:** `agent.agent`, `agent.template_instance`, `agent.template_version`, `agent.upgrade_decline`, `agent.browser_envelope`, `gate.suspension`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/agent-templates` | `/agent-templates` |
| `GET /api/v1/agents` | `/agents`, `/department` |
| `GET /api/v1/agents/{agent_id}/workspace` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `GET /api/v1/approvals` | `/approvals` |
| `GET /api/v1/approvals/{suspension_id}` | `/approvals/:suspensionId` |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` |

- **Gap.** An agent cannot be created, and its manifest, leash and procedure cannot be edited. Recorded: components/ManifestForm.tsx and components/ProcedureCanvas.tsx are built and tested and rendered by no registered page, and no route writes agent.agent or a template version from the console.
- **Gap.** An approval decided on a running install is refused: the application builds no suspension store without a ledger writer, so every approval route answers with the process fault. Recorded: brain.app.suspension_store_for passes no ledger, deliberately, until a writer for obs.audit_entry survives a restart; tests/unit/test_approval_decisions.py holds that the lifespan builds none.

### Skills and tools

- **Screens:** `/skills`, `/skills/:name`
- **Tables:** `agent.skill`, `agent.skill_review`, `agent.skill_assignment`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/skills` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/review` | `/skills`, `/skills/:name` |

- **Gap.** A skill cannot be fetched from a repository or a link, only pasted or uploaded. Recorded: brain.tools.fetch can fetch and check a source, and agent.skill admits only an upload; nothing on an install is given the network reach a fetch needs.
- **Gap.** A skill cannot be removed from an agent from the console, only replaced by another version of it. Recorded: brain.console.agent_tabs.detach decides a removal and no route performs one; brain.skill_routes assigns and replaces.
- **Gap.** A skill that declares scripts cannot be added. Recorded: brain.tools.skills.Skill.digest covers a script's name and not its bytes, so an approval would not cover the code, and brain.tools.run_skill has no runner; brain.console.skill_library refuses one at the door.

### Workflows and automations

- **Screens:** `/agents/:agentId/:tab`
- **Tables:** `agent.automation`, `gate.automation_owner`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/agents/{agent_id}/automation-templates` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview` | `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` |

- **Gap.** An installed automation cannot be paused, changed or removed. Recorded: brain.ops.agent_automation_store installs in the reader's own name and never edits or removes, which tests/unit/test_agent_automation_store.py holds; there is no route to call.

### Connectors and third-party integrations

- **Screens:** `/connectors`
- **Tables:** `proj.record`, `er.alias`, `er.canonical`, `er.identifier`, `er.link`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/connectors` | `/connectors` |

- **Gap.** A connector cannot be connected, and its credential cannot be held from a screen. Open leaf `M42.6.5`.

### API keys, credentials and secrets, held in the vault and never displayed

- **Screens:** `/webhooks`
- **Tables:** `ops.credential_write`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/credentials` | **no screen** |
| `PUT /api/v1/credentials/{family}/{name}` | **no screen** |

- **Gap.** GET /api/v1/credentials and PUT /api/v1/credentials/{family}/{name} are served, and no screen calls either. Open leaf `M27.8.8`.

### Knowledge bases, documents and data sources

- **Screens:** `/library`, `/learning`, `/memory`, `/memory/:subject`, `/records`, `/records/:entity`, `/classification`, `/classification/:entity`, `/classification/:entity/:column`, `/artifacts`
- **Tables:** `know.item`, `know.chunk`, `mem.adaptive`, `mem.persistent`, `gate.fast_path_rule`, `gate.field_policy`
- **Installation values:** `INSTALL_VECTOR_STORE`

| Route | Called by |
| --- | --- |
| `GET /api/v1/classifications/{entity}` | `/classification/:entity`, `/classification/:entity/:column` |
| `GET /api/v1/govern/artifacts` | `/artifacts` |
| `GET /api/v1/govern/learning` | `/learning` |
| `GET /api/v1/govern/library` | `/library` |
| `GET /api/v1/govern/memory` | `/memory/:subject` |
| `GET /api/v1/records/{entity}` | `/records/:entity` |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |

- **Gap.** A document or a data source cannot be added from the console after setup. Open leaf `M42.5.9`.
- **Gap.** A learning cannot be undone and a memory cannot be corrected. Recorded: The routes say undo_is_not_writable and edit_is_not_writable on every answer: brain.estate_routes serves the reads and no write exists.
- **Gap.** A column's classification cannot be changed; a proposed change is reviewed and not applied. Recorded: brain.classification_routes mounts only the dry-run review, and tests/unit/test_classification_routes.py holds that nothing mounted there can change a classification.

### File and object storage

- **Screens:** `/storage`
- **Tables:** none
- **Installation values:** `INSTALL_OBJECT_STORE_URL`, `INSTALL_OBJECT_STORE_PREFIX`

| Route | Called by |
| --- | --- |
| `GET /api/v1/storage` | `/storage` |

- **Gap.** A bucket's retention and the store's address are read and never changed. Open leaf `M27.8.15`.

### Prompts and system instructions

- **Screens:** `/prompts`
- **Tables:** none
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/prompts` | `/prompts` |
| `POST /api/v1/govern/prompts/{agent_id}` | `/prompts` |
| `POST /api/v1/govern/prompts/{agent_id}/give-back` | `/prompts` |

No gap recorded.

### Feature and module enablement

- **Screens:** `/features`
- **Tables:** `ops.plugin_install`, `ops.plugin_version`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/install/features` | `/features` |
| `POST /api/v1/install/features/{name}` | `/features` |

- **Gap.** A plugin cannot be installed or enabled. Recorded: Nothing loads a plugin yet: the Features screen says plugins_have_no_loader, and ops.plugin_install has no writer a route calls.

### Notifications and email

- **Screens:** `/subscribers`
- **Tables:** `ops.outbox_event`, `ops.outbox_delivery`
- **Installation values:** `INSTALL_SENDER_ADDRESS`

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/subscribers` | `/subscribers` |

- **Gap.** Who is told what, and the sending address, are read and never changed. Open leaf `M27.8.11`.

### Webhooks

- **Screens:** `/webhooks`
- **Tables:** `ops.webhook_subscriber`, `ops.webhook_change`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/webhooks` | `/webhooks` |
| `POST /api/v1/webhooks/subscribers` | `/webhooks` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/secret` | `/webhooks` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off` | `/webhooks` |

- **Gap.** A registered subscriber is never sent anything. Recorded: Nothing on an install delivers a webhook yet, which the Webhooks screen says in the API's words.

### Scheduled jobs and background work

- **Screens:** `/jobs`, `/runs`
- **Tables:** `ops.control_run`, `ops.operation`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/jobs` | `/jobs` |
| `GET /api/v1/operate/runs` | `/runs` |
| `POST /api/v1/jobs/{name}/pause` | `/jobs` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs` |
| `POST /api/v1/jobs/{name}/run` | `/jobs` |

- **Gap.** A run in progress cannot be stopped. Recorded: The route says no_run_can_be_stopped: a control runs to its end inside the worker's tick and there is nothing to signal.

### Usage, activity and system statistics

- **Screens:** `/usage`, `/adoption`, `/spend`, `/questions`, `/quality`, `/service-levels`, `/me`
- **Tables:** `ops.question_asked`, `ops.report_refresh`, `ops.spend_actual`, `obs.request_telemetry`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/me/workspace` | `/me` |
| `GET /api/v1/report/adoption` | `/adoption` |
| `GET /api/v1/report/quality` | `/quality` |
| `GET /api/v1/report/questions` | `/department`, `/questions` |
| `GET /api/v1/report/service-levels` | `/models`, `/service-levels` |
| `GET /api/v1/report/spend` | `/models`, `/spend` |
| `GET /api/v1/report/usage` | `/department`, `/usage` |

No gap recorded.

### Logs and errors

- **Screens:** `/errors`
- **Tables:** none
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/errors` | `/errors` |

- **Gap.** The process log cannot be read from the console. Open leaf `M27.8.14`.

### The audit trail: who changed what, and when

- **Screens:** `/audit`
- **Tables:** `obs.audit_entry`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/audit` | `/audit` |
| `GET /api/v1/audit/history` | `/audit` |

- **Gap.** A feature switch, a job control, an instruction edit, a rung save and a webhook change are not in the ledger. Recorded: ops.setting has no audit trigger, which migration 0004 records as a gap because the ledger has no subject kind for a setting; instructions are recorded on the install, rungs on nothing, and webhook changes in ops.webhook_change under A_CHANGE_IS_ATTRIBUTED_HERE_AND_NOT_YET_CHAINED.

### System health and the state of every service

- **Screens:** `/models`, `/runs`
- **Tables:** none
- **Installation values:** none

- **Gap.** The state of each service the install runs on, and each provider's circuit breaker, is not shown. Recorded: The Models and health screen says breaker_state_is_not_recorded, and /health/ready answers the orchestrator outside /api/v1 with no screen reading it.

### Backup and recovery

- **Screens:** `/recovery`, `/retention`
- **Tables:** `ops.retention_release`, `ops.retention_report`, `obs.legal_hold`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/retention` | `/retention` |
| `GET /api/v1/govern/retention/controls` | `/retention` |
| `GET /api/v1/install/recovery` | `/recovery` |
| `POST /api/v1/govern/legal-holds` | `/retention` |
| `POST /api/v1/govern/legal-holds/lift` | `/retention` |
| `POST /api/v1/govern/retention/release` | `/retention` |
| `POST /api/v1/govern/retention/withdrawal` | `/retention` |

- **Gap.** A recovery drill cannot be started, and a restore cannot be verified, from the console. Open leaf `M30.3.9`.

### Import and export

- **Screens:** `/import-export`
- **Tables:** `ops.data_export`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/data-transfer` | `/import-export` |
| `POST /api/v1/data-transfer/exports` | `/import-export` |

- **Gap.** Nothing can be imported, and the audit trail is the only export. Open leaf `M27.8.16`.

### Version, build and deployment information

- **Screens:** `/updates`, `/install`
- **Tables:** none
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/install/updates` | `/updates` |

No gap recorded.

## Not administered here

| What | Why it is not a gap |
| --- | --- |
| `/*` | The page drawn for an address the console does not have, which manages nothing. |
| `/ask` | Asking a question is what the console is for a person, not something an administrator manages. |
| `/auth/callback` | The end of a sign-in, drawn by the session module rather than by any screen. |
| `/signed-out` | The page a person lands on after signing out, which asks nothing and manages nothing. |
| `chat.conversation` | What a person asked and was answered belongs to them; no store queries it yet (brain.chat.threads) and usage is reported without the words. |
| `chat.message` | The same as chat.conversation: a person's own words, reported on and never managed. |
| `POST /api/v1/answer` | The answer lane behind Ask, which writes no row an administrator manages. |
| `POST /api/v1/automation/tool-call` | Called by a running automation with its owner's reach, not by a person at a screen; installing the automation is the console's part. |

## Every write the console sends, followed to the system

Leaf `M27.8.17`: a write is followed to the row it writes, to the audit entry it leaves, and to the behaviour it changes. 17 of 32 write routes have all three proved or not applicable, 4 of those without a live database. Every other row below says what is missing and why. A test marked database runs against a scratch Postgres, which CI provides and this machine does not.

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` | **None.** Only a stub session is asserted, which proves the update committed and not the row it left. | **None.** No trigger records a rung change: migration 0003 creates ops.routing_rung with none. | **None.** Nothing on the answer path reads ops.routing_rung, so a saved rung changes no answer. Leaf `M27.8.8`. |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` | `test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither` in `tests/unit/test_agent_automation_store.py` (database, in CI) | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` |
| `POST /api/v1/answer` | `/ask` | Not applicable: Asking a question writes no row an administrator manages. | Not applicable: Asking a question is not a change to the system. | Not applicable: The answer is the behaviour, and tests/invariants hold it. |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` | `test_an_approver_in_reach_approves_once_and_one_ledger_entry_records_it` in `tests/unit/test_approval_decisions.py` | `test_an_approver_in_reach_approves_once_and_one_ledger_entry_records_it` in `tests/unit/test_approval_decisions.py` | **None.** In-process the decision leaves the queue (test_approval_decisions.py::test_a_decided_approval_leaves_the_queue_and_its_card_no_longer_opens), but on a running install brain.app.suspension_store_for builds no store, so the decision a person presses is refused and changes nothing. |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | Not applicable: A review is a dry run and writes nothing. | Not applicable: A review changes nothing, so there is nothing to record. | `test_nothing_mounted_here_can_change_a_classification` in `tests/unit/test_classification_routes.py` |
| `POST /api/v1/data-transfer/exports` | `/import-export` | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own` in `tests/unit/test_data_transfer_routes.py` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. What that cost is recorded: row-level security refused every removal on every install until d2cfb32, and the stub session saw a commit each time. | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. | **None.** Only a stub session is asserted, which proves the statement committed and not the row. The row, the trigger's entry and what the holder then reaches are Postgres facts, and no test drives this route against a scratch database yet. |
| `POST /api/v1/govern/legal-holds` | `/retention` | `test_a_hold_is_placed_lifted_once_and_kept` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | **None.** The sweep is tested against holds written with raw SQL and holds built in memory, and nothing places a hold through the store and then runs the sweep over it. |
| `POST /api/v1/govern/legal-holds/lift` | `/retention` | `test_a_hold_is_placed_lifted_once_and_kept` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | **None.** Nothing lifts a hold through the store and then shows the sweep reaching what it held. |
| `POST /api/v1/govern/prompts/{agent_id}` | `/prompts` | `test_an_edit_is_written_to_the_install_and_changes_what_the_agent_is_given` in `tests/unit/test_prompt_routes.py` | **None.** An edit is recorded on the install it changes, who set it and when, and not in the ledger: brain.prompt_routes writes no audit entry. | `test_an_edit_is_written_to_the_install_and_changes_what_the_agent_is_given` in `tests/unit/test_prompt_routes.py` |
| `POST /api/v1/govern/prompts/{agent_id}/give-back` | `/prompts` | `test_giving_instructions_back_restores_the_templates_and_is_not_behind_the_feature` in `tests/unit/test_prompt_routes.py` | **None.** An edit is recorded on the install it changes, who set it and when, and not in the ledger: brain.prompt_routes writes no audit entry. | `test_giving_instructions_back_restores_the_templates_and_is_not_behind_the_feature` in `tests/unit/test_prompt_routes.py` |
| `POST /api/v1/govern/retention/release` | `/retention` | `test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report` in `tests/unit/test_worker_schedule.py` (database, in CI) |
| `POST /api/v1/govern/retention/withdrawal` | `/retention` | `test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report` in `tests/unit/test_worker_schedule.py` (database, in CI) |
| `POST /api/v1/govern/sessions/end` | `/sessions` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) |
| `POST /api/v1/install/features/{name}` | `/features` | `test_switching_a_feature_on_writes_its_row_and_the_next_read_sees_it` in `tests/unit/test_features.py` | **None.** ops.setting has no audit trigger, which migration 0004 records as a gap: the ledger has no subject kind for a setting, so the switch is attributed on its own row and nowhere else. | `test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/pause` | `/jobs` | `test_pausing_writes_the_row_the_tick_reads_and_the_list_says_who_paused_it` in `tests/unit/test_jobs_routes.py` | **None.** ops.setting has no audit trigger, which migration 0004 records as a gap: the ledger has no subject kind for a setting, so the switch is attributed on its own row and nowhere else. | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs` | `test_resuming_is_not_behind_the_feature_so_a_switch_turned_off_traps_nothing` in `tests/unit/test_jobs_routes.py` | **None.** ops.setting has no audit trigger, which migration 0004 records as a gap: the ledger has no subject kind for a setting, so the switch is attributed on its own row and nowhere else. | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/run` | `/jobs` | `test_running_now_writes_the_instant_the_request_was_admitted` in `tests/unit/test_jobs_routes.py` | **None.** ops.setting has no audit trigger, which migration 0004 records as a gap: the ledger has no subject kind for a setting, so the switch is attributed on its own row and nowhere else. | `test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/sign-ins` | `/sign-in-links` | `test_binding_the_same_subject_twice_writes_one_row` in `tests/unit/test_sign_in_binding.py` (database, in CI) | `test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after` in `tests/unit/test_sign_in_binding.py` (database, in CI) |
| `POST /api/v1/skills` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name` | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` | `test_the_database_refuses_a_decision_by_the_importer_and_an_assignment_nobody_approved` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/review` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/webhooks/subscribers` | `/webhooks` | `test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept` in `tests/unit/test_webhook_routes.py` | **None.** A webhook change is attributed in ops.webhook_change and not chained into the ledger: brain.ops.webhook_store.A_CHANGE_IS_ATTRIBUTED_HERE_AND_NOT_YET_CHAINED. | **None.** Nothing on an install delivers a webhook yet, so no behaviour follows from a subscriber or its secret. |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/secret` | `/webhooks` | `test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused` in `tests/unit/test_webhook_routes.py` | **None.** A webhook change is attributed in ops.webhook_change and not chained into the ledger: brain.ops.webhook_store.A_CHANGE_IS_ATTRIBUTED_HERE_AND_NOT_YET_CHAINED. | **None.** Nothing on an install delivers a webhook yet, so no behaviour follows from a subscriber or its secret. |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off` | `/webhooks` | `test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused` in `tests/unit/test_webhook_routes.py` | **None.** A webhook change is attributed in ops.webhook_change and not chained into the ledger: brain.ops.webhook_store.A_CHANGE_IS_ATTRIBUTED_HERE_AND_NOT_YET_CHAINED. | `test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out` in `tests/unit/test_webhook_store.py` (database, in CI) |
| `POST /setup/appointment` | `/first-run` | `test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish` in `tests/unit/test_setup_routes.py` | `test_the_first_administrator_is_a_live_person_holding_administration_everywhere` in `tests/unit/test_first_administrator.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/sign-in` | `/first-run` | `test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator` in `tests/unit/test_sign_in_routes.py` | `test_the_finishing_screen_binds_the_first_administrator_once_against_the_database` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/staff-source/sign-in` | `/first-run` | Not applicable: It answers the directory's own sign-in page for the setup code's holder and writes nothing. | Not applicable: Nothing changes when a sign-in page is asked for, so there is nothing to record. | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |
| `POST /setup/staff-source/trial` | `/first-run` | Not applicable: A read of a staff list writes nothing: nobody is added, and the client secret it signs in with is not kept. | Not applicable: A read changes nothing an administrator manages, so there is nothing to record. | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |

## The rules every screen is held to

- **Loading, empty, unreachable and failed** are four different sentences on every registered address: `console/tests/screen-states.test.tsx`, with the addresses excused and why in `console/tests/support/screenStateRules.tsx`.
- **A destructive write is confirmed**, and the confirmation names what and says what will happen: `console/tests/destructive-confirmed.test.ts`, with the writes that are not destructive and why.
- **A form that writes is judged before it sends**, and a blank one says what to fill in: `console/tests/validated-before-write.test.tsx`.
- **Long lists** are measured rather than claimed, and what each does not offer is recorded with its reason: `console/tests/long-lists.test.tsx`. Leaf `M27.8.6` stays open: most routes take a limit and nothing else.
