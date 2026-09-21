# The console audit

What an administrator would need to manage, read out of the schema, the routes and the installation values, compared with what the console serves, screen by screen, with every gap either linked to its open leaf or recorded with its reason. It is the audit `docs/admin-console.md` asks for before the console is called done.

**This page is generated and must not be edited by hand.** `console/tests/console-audit.test.ts` renders it from `console/tests/support/consoleAudit.ts` and fails when this file differs. To regenerate it after a change, run `npm run api:generate` and then `WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts` in `console/`.

## What was measured

- 23 areas, the bullets of `docs/admin-console.md` in its order.
- 78 tables, from `brain.db.Base.metadata`.
- 24 installation values, from `brain.install.INSTALLATION`.
- 138 routes under `/api/v1` and `/setup`, from the API's internal document.
- 68 console addresses, from the route table in `console/src/App.tsx`.
- 47 calls in the console that send a write, from `console/tests/support/writes.ts`, reaching 55 routes.
- 35 gaps recorded, and 13 routes no screen calls.

## Area by area

### People, roles, permissions and access control

- **Screens:** `/`, `/people`, `/people/:subject`, `/roles`, `/capabilities`, `/scopes`, `/access_review`, `/elevation`, `/sessions`, `/sign-in-links`, `/staff_sources`
- **Tables:** `auth.principal`, `auth.principal_identity`, `auth.session`, `auth.directory_role_grant`, `gate.capability_grant`, `gate.capability_pack`, `gate.capability_pack_assignment`, `gate.capability_registry`, `gate.scope`, `gate.grants_version`, `gate.policy_epoch`, `gate.review_decision`, `gate.elevation_request`, `auth.staff_member`, `auth.staff_sync_run`
- **Installation values:** `INSTALL_OIDC_ISSUER`, `INSTALL_OIDC_REALM`, `INSTALL_OIDC_CLIENT_ID`, `INSTALL_OIDC_REDIRECT_URIS`, `INSTALL_BROKERED_DIRECTORY`, `INSTALL_STAFF_SOURCE`, `INSTALL_STAFF_SOURCE_LOCATION`, `INSTALL_BROKERED_CLIENT_ID`

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/navigation` | `/department` |
| `GET /api/v1/govern/access-review` | `/access_review` |
| `GET /api/v1/govern/capabilities` | `/capabilities` |
| `GET /api/v1/govern/data-steward` | `/people`, `/people/:subject` |
| `GET /api/v1/govern/elevation` | `/elevation` |
| `GET /api/v1/govern/packs` | `/people/:subject` |
| `GET /api/v1/govern/people` | `/people`, `/people/:subject` |
| `GET /api/v1/govern/roles` | `/roles` |
| `GET /api/v1/govern/roles/misconfigurations` | `/roles` |
| `GET /api/v1/govern/scopes` | `/people/:subject`, `/scopes` |
| `GET /api/v1/govern/sessions` | `/sessions` |
| `GET /api/v1/govern/sign-ins` | `/sign-in-links` |
| `GET /api/v1/govern/staff_sources` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/credential` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/runs` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/transfers` | `/staff_sources` |
| `GET /api/v1/govern/staff_sources/trial` | `/staff_sources` |
| `GET /api/v1/me` | `/` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` |
| `POST /api/v1/govern/access-review/decisions` | `/access_review` |
| `POST /api/v1/govern/data-steward` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/elevation/requests` | `/elevation` |
| `POST /api/v1/govern/elevation/requests/{request_id}/decision` | `/elevation` |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/packs/assignment` | `/people`, `/people/:subject` |
| `POST /api/v1/govern/sessions/end` | `/sessions` |
| `POST /api/v1/govern/sessions/end-several` | `/sessions` |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` |
| `POST /api/v1/govern/staff_sources/transfers/{agent_id}` | `/staff_sources` |
| `POST /api/v1/sign-ins` | `/sign-in-links` |
| `PUT /api/v1/govern/staff_sources/credential` | `/staff_sources` |

- **Gap.** A grant written from People and grants cannot be given an expiry, and the screen says so beside the form. Recorded: Buildable today: POST /api/v1/govern/grants takes not_after and the form's proposal schema has no field for it. It is left to the change reworking member grants, which is in progress beside this one and owns that form.
- **Gap.** A pack cannot be assigned or withdrawn, and a capability that arrived through a pack cannot be removed. Recorded: No route writes gate.capability_pack_assignment. brain.govern_routes.remove_grant refuses a pack's capability in the ordinary words, because withdrawing it removes every other capability in the pack.
- **Gap.** Roles, capabilities and scopes are read and never changed. Recorded: No route writes gate.scope or the role and capability registries; they are declared by the product and by migrations.
- **Gap.** Nobody is sent a notice when somebody asks for an elevation or is given one. Recorded: The people to tell are the standing Super Admins, and no table records who holds a role (M1.3.2), so brain.console.elevation.client_recipients has nobody to compute; the audit ledger is the record, and the Elevation requests screen says so.
- **Gap.** The identity provider and the staff source cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.

### Departments, teams and client configuration

- **Screens:** `/departments`, `/department`
- **Tables:** `gate.department`, `gate.team`, `gate.team_membership`, `gate.department_lead`
- **Installation values:** `INSTALL_COMPANY_NAME`, `INSTALL_PRODUCT_NAME`, `INSTALL_LOGO_URL`, `INSTALL_ACCENT_COLOUR`

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/departments` | `/departments` |
| `POST /api/v1/govern/departments` | **no screen** |
| `POST /api/v1/govern/departments/lead` | `/departments` |
| `POST /api/v1/govern/departments/membership` | `/departments` |
| `POST /api/v1/govern/departments/rename` | **no screen** |
| `POST /api/v1/govern/departments/retirement` | **no screen** |
| `POST /api/v1/govern/departments/scopes` | **no screen** |
| `POST /api/v1/govern/departments/scopes/retirement` | **no screen** |
| `POST /api/v1/govern/departments/team` | **no screen** |
| `POST /api/v1/govern/departments/team/rename` | **no screen** |
| `POST /api/v1/govern/departments/team/retirement` | **no screen** |

- **Gap.** A department, a team or a scope cannot yet be created, renamed or retired from this screen. Recorded: brain.govern_people_routes serves the eight writes, audited by 0086's triggers, and Departments.tsx does not call them yet; the screen places people in the teams that are there and leads the departments that are there.
- **Gap.** Nothing applies the staff list's teams and leads on a schedule. Recorded: brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either. The nightly staff sync (brain.ops.staff_sync_run, since 2026-09-21) applies the roster's people and marks leavers, and not its teams or leads.

### System settings and application configuration

- **Screens:** `/install`, `/settings`, `/limits`, `/connections`, `/first-run`, `/first-run/staff-list`
- **Tables:** `ops.setting`, `ops.budget_version`
- **Installation values:** `INSTALL_LOCALES`, `INSTALL_CURRENCY`, `INSTALL_TIME_ZONE`

| Route | Called by |
| --- | --- |
| `GET /api/v1/install` | `/install` |
| `GET /api/v1/install/capacity` | `/connections` |
| `GET /api/v1/install/limits` | `/limits` |
| `GET /api/v1/install/settings` | `/settings` |
| `GET /setup/staff-source/registration` | `/first-run` |
| `POST /setup/appointment` | `/first-run` |
| `POST /setup/sign-in` | `/first-run` |
| `POST /setup/staff-source/sign-in` | `/first-run` |
| `POST /setup/staff-source/trial` | `/first-run` |
| `PUT /api/v1/install/settings/{name}` | `/settings` |

- **Gap.** Languages, currency and time zone cannot be changed after setup. Recorded: Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; changing one today is editing the server's environment file or the row by hand.
- **Gap.** Limits and budgets are read and never changed. Recorded: No route writes ops.budget_version or a ceiling; a limit is a release today.

### AI providers, models and the routing between them

- **Screens:** `/models`, `/routing`, `/routing/:rungId`
- **Tables:** `ops.routing_rung`, `ops.routing_tier`, `ops.model_attempt`
- **Installation values:** `INSTALL_MODEL_PROFILE`, `INSTALL_MODEL_ENDPOINT`, `INSTALL_EMBEDDING_DIMENSIONS`

| Route | Called by |
| --- | --- |
| `GET /api/v1/models/providers` | `/models` |
| `GET /api/v1/operate/models` | `/models` |
| `GET /api/v1/routing/rungs` | `/models`, `/routing`, `/routing/:rungId` |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` |
| `POST /api/v1/models/providers/{provider}/check` | `/models` |
| `PUT /api/v1/models/providers/{provider}` | `/models` |

- **Gap.** Saving a routing rung changes the chain the next model call walks and no answer: the answer lane still answers from fast-path rules and calls no model, so today only a provider check from Models and health reaches a saved rung. Open leaf `M27.8.8`.
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
| `GET /api/v1/agents/{agent_id}/about` | **no screen** |
| `GET /api/v1/agents/{agent_id}/workspace` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `GET /api/v1/approvals` | `/approvals` |
| `GET /api/v1/approvals/{suspension_id}` | `/approvals/:suspensionId` |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` |

- **Gap.** An agent cannot be created, and its manifest, leash and procedure cannot be edited. Recorded: components/ManifestForm.tsx and components/ProcedureCanvas.tsx are built and tested and rendered by no registered page, and no route writes agent.agent or a template version from the console.

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
- **Tables:** `agent.automation`, `agent.automation_run`, `agent.automation_schedule`, `gate.automation_owner`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/agents/{agent_id}/automation-templates` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automations` | `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` |

- **Gap.** An installed automation cannot be changed or removed, only started and stopped. Recorded: brain.automation_schedule_routes starts and stops one and brain.console.agent_automations.remove decides a removal that no route performs; 0067 grants an update of the next run alone.
- **Gap.** Three of the four automation templates cannot be started on any install. Recorded: brain.ops.automation_run.TASKS says what work_summary, source_freshness and approvals_waiting each still need, and the Automations tab shows that sentence instead of a Start control.

### Connectors and third-party integrations

- **Screens:** `/connectors`
- **Tables:** `ops.connector_connection`, `ops.connector_sync`, `proj.record`, `er.alias`, `er.canonical`, `er.identifier`, `er.link`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/connectors` | `/connectors` |
| `POST /api/v1/connectors` | `/connectors` |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors` |

- **Gap.** A connected source is read and kept, and no question is answered from what is kept. Recorded: No row tool is registered for a connected source's records: brain.tools.startup.classification_for is keyed on the entity alone and Xero and HubSpot both project contact, which that module records as the limit to change first. brain.ops.connector_admin.WHAT_CONNECTING_A_SOURCE_STARTS says so on the screen.
- **Gap.** HubSpot can be connected and is not read. Recorded: brain.ops.limits records no verified call ceiling for it and brain.connectors.throttle.limits_for refuses to invent one; its row carries brain.ops.connector_sync.NO_VERIFIED_CEILING.
- **Gap.** Freshdesk, Google Drive, the Laravel views, Lark Base and Lark Wiki cannot be connected from a screen. Recorded: Each needs a visibility rule, a department declaration or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each.

### API keys, credentials and secrets, held in the vault and never displayed

- **Screens:** `/webhooks`, `/vault`
- **Tables:** `ops.credential_write`, `ops.vault_access`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/credentials` | **no screen** |
| `GET /api/v1/vault` | `/vault` |
| `PUT /api/v1/credentials/{family}/{name}` | **no screen** |

- **Gap.** GET /api/v1/credentials and PUT /api/v1/credentials/{family}/{name} are served, and no screen calls either. Open leaf `M27.8.8`.

### Knowledge bases, documents and data sources

- **Screens:** `/library`, `/learning`, `/memory`, `/memory/:subject`, `/records`, `/records/:entity`, `/classification`, `/classification/:entity`, `/classification/:entity/:column`, `/artifacts`
- **Tables:** `know.item`, `know.chunk`, `mem.adaptive`, `mem.persistent`, `mem.learning`, `mem.correction`, `gate.fast_path_rule`, `gate.field_policy`, `agent.artifact`
- **Installation values:** `INSTALL_VECTOR_STORE`, `INSTALL_EMBEDDING_REVISION`

| Route | Called by |
| --- | --- |
| `GET /api/v1/classifications/{entity}` | `/classification/:entity`, `/classification/:entity/:column` |
| `GET /api/v1/govern/artifacts` | `/artifacts` |
| `GET /api/v1/govern/learning` | `/learning` |
| `GET /api/v1/govern/library` | `/library` |
| `GET /api/v1/govern/memory` | `/memory/:subject` |
| `GET /api/v1/records/{entity}` | `/records/:entity` |
| `GET /api/v1/records/{entity}/access` | **no screen** |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` |
| `POST /api/v1/govern/learning/undo` | `/learning` |

- **Gap.** A document or a data source cannot be added from the console after setup. Open leaf `M42.5.9`.
- **Gap.** A memory cannot be edited from a screen, and a tier-two rule cannot be promoted nor a tier-three change decided. Recorded: brain.ops.memory_store writes an edit and no route offers one: the control belongs on a person's own memory tab, and the Memory screen says edit_is_not_writable. Nothing records agreement or a decision, which the Learning screen says in place of Promote and Decide.
- **Gap.** A column's classification cannot be changed; a proposed change is reviewed and not applied. Recorded: brain.classification_routes mounts only the dry-run review, and tests/unit/test_classification_routes.py holds that nothing mounted there can change a classification.

### File and object storage

- **Screens:** `/storage`
- **Tables:** none
- **Installation values:** `INSTALL_OBJECT_STORE_URL`, `INSTALL_OBJECT_STORE_PREFIX`, `INSTALL_OBJECT_STORE_BACKEND`

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

- **Screens:** `/subscribers`, `/notifications`
- **Tables:** `ops.outbox_event`, `ops.outbox_delivery`
- **Installation values:** `INSTALL_SENDER_ADDRESS`

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/subscribers` | `/subscribers` |
| `GET /api/v1/notifications` | `/notifications` |
| `POST /api/v1/notifications/notices/{kind}` | `/notifications` |
| `POST /api/v1/notifications/relay` | `/notifications` |
| `POST /api/v1/notifications/relay/password` | `/notifications` |
| `POST /api/v1/notifications/relay/test` | `/notifications` |

- **Gap.** No notice is sent to a person yet. Recorded: Every notice but the re-verification request is composed and called by nothing, and that one reaches webhook subscribers; the Notifications screen says so per notice from brain.ops.notices, and a sender added for any of them asks its switch.
- **Gap.** INSTALL_SENDER_ADDRESS is read by nothing that sends. Recorded: The relay's sender address is saved on the Notifications screen, and the install value is only shown on the Install screen.

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

- **Gap.** No platform's webhook is received. Recorded: No route receives one, and the WhatsApp and Lark checks are not written; the Webhooks screen lists each channel's check from brain.ops.inbound_webhooks.

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
- **Tables:** `ops.question_asked`, `ops.question_gap`, `ops.report_refresh`, `ops.spend_actual`, `obs.request_telemetry`
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

- **Screens:** `/errors`, `/logs`
- **Tables:** `obs.application_log`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/errors` | `/errors` |
| `GET /api/v1/logs` | `/logs` |

- **Gap.** The background worker's own output and every debug line are not kept, and information lines are a sample. Recorded: The Logs screen says worker_output_is_not_kept, debug_is_not_kept and info_is_a_sample: the worker prints to its container rather than logging through structlog, and brain.ops.log_capture keeps warnings and above and bounds the rest.

### The audit trail: who changed what, and when

- **Screens:** `/audit`
- **Tables:** `obs.audit_entry`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/audit` | `/audit` |
| `GET /api/v1/audit/history` | `/audit` |

No gap recorded.

### System health and the state of every service

- **Screens:** `/models`, `/runs`
- **Tables:** none
- **Installation values:** none

- **Gap.** The state of each service the install runs on is not shown. Recorded: /health/ready answers the orchestrator outside /api/v1 with no screen reading it. Each rung's circuit breaker is shown, on the Models and health screen from GET /api/v1/models/providers, replayed from the attempts the executor recorded.

### Backup and recovery

- **Screens:** `/recovery`, `/retention`
- **Tables:** `ops.retention_release`, `ops.retention_report`, `obs.legal_hold`, `ops.erasure_request`
- **Installation values:** none

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/erasures` | `/retention` |
| `GET /api/v1/govern/retention` | `/retention` |
| `GET /api/v1/govern/retention/controls` | `/retention` |
| `GET /api/v1/govern/retention/exports` | `/retention` |
| `GET /api/v1/install/recovery` | `/recovery` |
| `POST /api/v1/govern/erasures` | `/retention` |
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
- **Tables:** `ops.deployment_record`
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

Leaf `M27.8.17`: a write is followed to the row it writes, to the audit entry it leaves, and to the behaviour it changes. 50 of 55 write routes have all three proved or not applicable, 7 of those without a live database. Every other row below says what is missing and why. A test marked database runs against a scratch Postgres, which CI provides and this machine does not.

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `PATCH /api/v1/routing/rungs/{rung_id}` | `/routing`, `/routing/:rungId` | `test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_rung_saved_on_the_routing_screen_is_the_rung_the_next_call_walks` in `tests/unit/test_provider_routes.py` (database, in CI) |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` | `test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither` in `tests/unit/test_agent_automation_store.py` (database, in CI) | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing` in `tests/unit/test_automation_schedule_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot` in `tests/unit/test_automation_schedule_routes.py` |
| `POST /api/v1/answer` | `/ask` | Not applicable: Asking a question writes no row an administrator manages. | Not applicable: Asking a question is not a change to the system. | Not applicable: The answer is the behaviour, and tests/invariants hold it. |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run` in `tests/unit/test_suspension_store.py` (database, in CI) |
| `POST /api/v1/classifications/{entity}/columns/{column}/review` | `/classification`, `/classification/:entity`, `/classification/:entity/:column` | Not applicable: A review is a dry run and writes nothing. | Not applicable: A review changes nothing, so there is nothing to record. | `test_nothing_mounted_here_can_change_a_classification` in `tests/unit/test_classification_routes.py` |
| `POST /api/v1/connectors` | `/connectors` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/data-transfer/exports` | `/import-export` | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own` in `tests/unit/test_data_transfer_routes.py` |
| `POST /api/v1/govern/access-review/decision` | `/access_review` | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) |
| `POST /api/v1/govern/access-review/decisions` | `/access_review` | `test_several_holdings_are_decided_one_at_a_time_each_by_the_single_decisions_question` in `tests/unit/test_govern_people_routes.py` | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) | `test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to` in `tests/unit/test_review_store.py` (database, in CI) |
| `POST /api/v1/govern/data-steward` | `/people`, `/people/:subject` | `test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice` in `tests/unit/test_data_steward_routes.py` (database, in CI) | `test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it` in `tests/unit/test_data_steward.py` (database, in CI) | `test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot` in `tests/unit/test_data_steward.py` (database, in CI) |
| `POST /api/v1/govern/departments/lead` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
| `POST /api/v1/govern/departments/membership` | `/departments` | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) | `test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page` in `tests/unit/test_organisation_store.py` (database, in CI) |
| `POST /api/v1/govern/elevation/requests` | `/elevation` | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) |
| `POST /api/v1/govern/elevation/requests/{request_id}/decision` | `/elevation` | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) | `test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not` in `tests/unit/test_elevation_store.py` (database, in CI) |
| `POST /api/v1/govern/erasures` | `/retention` | `test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished` in `tests/unit/test_erasure_store.py` (database, in CI) | `test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished` in `tests/unit/test_erasure_store.py` (database, in CI) | `test_the_queue_carries_a_request_out_and_writes_what_each_store_did_and_what_it_could_not` in `tests/unit/test_erasure_store.py` (database, in CI) |
| `POST /api/v1/govern/grants` | `/people`, `/people/:subject` | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/grants/removal` | `/people`, `/people/:subject` | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/learning/undo` | `/learning` | `test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next` in `tests/unit/test_memory_store.py` (database, in CI) | `test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next` in `tests/unit/test_memory_store.py` (database, in CI) | `test_an_undo_writes_the_correction_and_the_next_reading_no_longer_recalls_the_learning` in `tests/unit/test_estate_routes.py` |
| `POST /api/v1/govern/legal-holds` | `/retention` | `test_a_hold_is_placed_lifted_once_and_kept` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_hold_placed_through_the_store_keeps_its_rows_from_the_sweep_and_lifted_releases_them` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/legal-holds/lift` | `/retention` | `test_a_hold_is_placed_lifted_once_and_kept` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_hold_placed_through_the_store_keeps_its_rows_from_the_sweep_and_lifted_releases_them` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/packs/assignment` | `/people`, `/people/:subject` | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) | `test_an_assignment_reaches_the_row_the_ledger_and_the_resolver` in `tests/unit/test_govern_pack_routes.py` (database, in CI) |
| `POST /api/v1/govern/prompts/{agent_id}` | `/prompts` | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/prompts/{agent_id}/give-back` | `/prompts` | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/retention/release` | `/retention` | `test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report` in `tests/unit/test_worker_schedule.py` (database, in CI) |
| `POST /api/v1/govern/retention/withdrawal` | `/retention` | `test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked` in `tests/unit/test_retention_store.py` (database, in CI) | `test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor` in `tests/unit/test_retention_audit.py` (database, in CI) | `test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report` in `tests/unit/test_worker_schedule.py` (database, in CI) |
| `POST /api/v1/govern/sessions/end` | `/sessions` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) |
| `POST /api/v1/govern/sessions/end-several` | `/sessions` | `test_several_sessions_are_ended_one_at_a_time_each_decided_by_the_single_endings_question` in `tests/unit/test_session_routes.py` | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) | `test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request` in `tests/unit/test_session_store.py` (database, in CI) |
| `POST /api/v1/govern/sign-ins/unlink` | `/sign-in-links` | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) | `test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after` in `tests/unit/test_sign_in_links.py` (database, in CI) |
| `POST /api/v1/govern/staff_sources/transfers/{agent_id}` | `/staff_sources` | `test_taking_a_leavers_agent_moves_the_owner_and_never_the_reach` in `tests/unit/test_staff_sync_routes.py` | Not applicable: No ledger entry is written when an agent's owner moves: agent.agent has no audit trigger, so the change is logged by the route and recorded on the row alone. Recorded here as a gap rather than hidden. | `test_taking_a_leavers_agent_moves_the_owner_and_never_the_reach` in `tests/unit/test_staff_sync_routes.py` |
| `POST /api/v1/install/features/{name}` | `/features` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/pause` | `/jobs` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/run` | `/jobs` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/models/providers/{provider}/check` | `/models` | `test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question` in `tests/unit/test_provider_routes.py` | Not applicable: A check changes no setting and no record an administrator manages; it is a metered call on the request ledger, not a change to audit. | `test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question` in `tests/unit/test_provider_routes.py` |
| `POST /api/v1/notifications/notices/{kind}` | `/notifications` | `test_switching_a_notice_off_writes_its_row_with_the_writer_and_the_next_read_sees_it` in `tests/unit/test_notification_routes.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_switched_off_a_re_verification_run_records_nothing_and_switched_on_it_does` in `tests/unit/test_notices.py` (database, in CI) |
| `POST /api/v1/notifications/relay` | `/notifications` | `test_a_relay_is_saved_as_five_rows_with_its_writer_and_read_back_configured` in `tests/unit/test_notification_routes.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/notifications/relay/password` | `/notifications` | `test_a_password_is_kept_at_its_slot_recorded_and_never_answered` in `tests/unit/test_notification_routes.py` | `test_a_password_is_kept_at_its_slot_recorded_and_never_answered` in `tests/unit/test_notification_routes.py` | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/notifications/relay/test` | `/notifications` | `test_pressing_the_test_button_twice_sends_one_message` in `tests/unit/test_mail.py` | **None.** A test message is recorded in ops.operation under its key, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION. | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/sign-ins` | `/sign-in-links` | `test_binding_the_same_subject_twice_writes_one_row` in `tests/unit/test_sign_in_binding.py` (database, in CI) | `test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after` in `tests/unit/test_sign_in_binding.py` (database, in CI) |
| `POST /api/v1/skills` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name` | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` | `test_the_database_refuses_a_decision_by_the_importer_and_an_assignment_nobody_approved` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/review` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/webhooks/subscribers` | `/webhooks` | `test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_due_event_is_signed_received_verified_and_recorded_delivered` in `tests/unit/test_webhook_delivery.py` (database, in CI) |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/secret` | `/webhooks` | `test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_the_worker_reads_the_secret_at_the_path_the_console_writes_it_to` in `tests/unit/test_webhook_delivery.py` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off` | `/webhooks` | `test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out` in `tests/unit/test_webhook_store.py` (database, in CI) |
| `POST /setup/appointment` | `/first-run` | `test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish` in `tests/unit/test_setup_routes.py` | `test_the_first_administrator_is_a_live_person_holding_administration_everywhere` in `tests/unit/test_first_administrator.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/sign-in` | `/first-run` | `test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator` in `tests/unit/test_sign_in_routes.py` | `test_the_finishing_screen_binds_the_first_administrator_once_against_the_database` in `tests/unit/test_sign_in_routes.py` (database, in CI) | `test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone` in `tests/unit/test_setup_routes.py` (database, in CI) |
| `POST /setup/staff-source/sign-in` | `/first-run` | Not applicable: It answers the directory's own sign-in page for the setup code's holder and writes nothing. | Not applicable: Nothing changes when a sign-in page is asked for, so there is nothing to record. | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |
| `POST /setup/staff-source/trial` | `/first-run` | `test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync` in `tests/unit/test_setup_staff_routes.py` | `test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync` in `tests/unit/test_setup_staff_routes.py` | `test_a_directory_is_chosen_signed_in_to_and_its_list_pulled` in `tests/unit/test_setup_staff_routes.py` |
| `PUT /api/v1/govern/staff_sources/credential` | `/staff_sources` | `test_the_credential_is_replaced_into_its_slot_recorded_and_never_sent_back` in `tests/unit/test_staff_sync_routes.py` | `test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds` in `tests/unit/test_credential_writes.py` (database, in CI) | `test_a_scheduled_run_reads_lark_with_the_kept_credential_and_applies_the_plan` in `tests/unit/test_staff_sync_run.py` |
| `PUT /api/v1/install/settings/{name}` | `/settings` | `test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next` in `tests/unit/test_settings_routes.py` | **None.** The route sets the audit attribution 0059's trigger reads, which BRANDING_SAVED asserts over a stub; no scratch-Postgres test yet reads the ledger entry back. | `test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next` in `tests/unit/test_settings_routes.py` |
| `PUT /api/v1/models/providers/{provider}` | `/models` | `test_the_stores_read_the_ladder_write_attempts_by_id_and_keep_a_switch` in `tests/unit/test_model_service.py` (database, in CI) | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_switching_a_provider_off_takes_its_rungs_out_of_the_next_plan_at_once` in `tests/unit/test_provider_routes.py` |

## The rules every screen is held to

- **Loading, empty, unreachable and failed** are four different sentences on every registered address: `console/tests/screen-states.test.tsx`, with the addresses excused and why in `console/tests/support/screenStateRules.tsx`.
- **A destructive write is confirmed**, and the confirmation names what and says what will happen: `console/tests/destructive-confirmed.test.ts`, with the writes that are not destructive and why.
- **A form that writes is judged before it sends**, and a blank one says what to fill in: `console/tests/validated-before-write.test.tsx`.
- **Long lists page, search, filter and sort** through one convention, `brain.listing`, over the rows the reader may see, and a filter offers only values on rows drawn: `console/tests/long-lists.test.tsx` measures every long list against its route and records what each does not offer with its reason. Ending several sessions and deciding several review holdings are bulk acts, each item decided by the single act's own check.
