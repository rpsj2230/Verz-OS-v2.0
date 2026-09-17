# The Admin Console: what exists, what it should be, and how to build it

Written on 2026-09-17 for the owner and for the engineers and agents who will build the console.
It answers the owner's request of the same day: many console functions failed with a generic
error, the interface looked out of date, and he wants one console from which an authorised
administrator runs the whole platform without the server, the database or the source.

It sits beside two documents and replaces neither. `docs/admin-console.md` is the standard every
screen is held to. `docs/console-audit.md` is generated from the code and measures what is served
today. This document is the design: the audit behind it, the information architecture, the
lifecycle of every entity, four detailed designs, the interface direction and the build plan.

**How to read it.** The owner's summary is the next section and is enough to decide from. Part 1
is the evidence. Parts 2 to 5 are the design. Part 6 is where a product rule bounds a wish. Part 7
is the build plan an agent can take a work package from.

---

## The summary

### Why so many functions failed with "I could not find that."

Measured from the code at `273092a`, in order of how much each one breaks:

1. **Every administrative action needs a second factor in the sign-in token, and the product's
   identity provider never puts one there.** `brain.gate.admission.admit` removes every `admin:`
   and `approve:` capability unless the token's `amr` claim names `mfa`, `otp` or `hwk`
   (`brain.identity.bearer.assurance_from`). `ops/keycloak/realm-export.json` has no AMR mapper
   and no authentication flow, so no console token ever carries `amr`, even when an authenticator
   code was typed. The first administrator holds 26 `admin:` capabilities and `approve:grant` on
   paper and can use none of them. Every write answers 404 "I could not find that.", which is the
   sentence the product uses for anything refused; so do the screens whose read is an `admin:` or
   `approve:` capability (Features, Storage, Notifications, Sign-in links, Access review, Logs),
   while Webhooks and Subscribers answer an empty page and Jobs, Skills, Connectors and Models
   quietly lose their controls. Nothing tells the person why, although `admission.would_lose`
   exists to. **This is read from the code and the realm file, and it is confirmed on an install in
   one step:** the Overview's Assurance chip (from `GET /api/v1/me`) reads `authenticated` rather
   than `strong`.
2. **The install is empty in the places an administrator starts.** Nothing ever inserts a
   department, a team, a scope, a capability registry row, a capability pack, a routing tier or
   rung, an agent or a signed template version (`brain.ops.starter` says "Nothing applies the
   starter set today"). So even with a second factor, a grant to a second person is refused
   (`POST /govern/grants` resolves a scope slug and none exists), the Departments, Capabilities,
   Scopes, Agents and Prompts screens are empty, and the model ladder has no rungs.
3. **Approvals fail for everybody with "Something went wrong."** `brain.app.suspension_store_for`
   is always handed no ledger writer, so all three approval routes answer 500.
4. **Some reads were never granted to the first administrator.** Two by omission:
   `read:routing_matrix` (the Routing screen answers 404 for everybody) and
   `read:field_classification` (Classification). One set on purpose: the content plane behind
   Learning and Memory, which the product keeps for whoever an administrator grants it to. And the
   audit export requires reads of the whole ledger that the product deliberately withholds, so it
   is never offered.
5. **Several controls reach nothing yet.** Nothing reads a connected source, nothing runs an
   installed automation, an assigned skill has no effect on an answer, no route runs an agent and
   the answer lane calls no model, an agent's tier is never read by routing, `ops.spend_actual` is
   never written so spend is empty, and 9 of 16 scheduled controls have no runner.

Wave 0 of the build plan fixes the first four. They are small, independent and they unblock
everything else. One question behind item 4 is the owner's to decide, and it is in Part 6.1:
**nobody on an install can grant a capability they do not hold** (`scoped_authority.may_grant`),
the first administrator deliberately holds no data and no content capability, so as built no
person can ever be granted access to the company's data or to Learning and Memory.

### The console this document proposes

Forty administrative modules in nine groups, each group an administrator's job. The owner's
reference list maps onto it in Part 2.4.

| Group | Modules |
| --- | --- |
| Home | Dashboard |
| People and access | People; Departments and teams; Roles and permissions; Access reviews and elevation; Sign-in, directory and sessions; Service accounts and API keys |
| Agents and AI | Agents; Agent templates; Skills and tools; Approvals and autonomy; Automations; Models and routing |
| Knowledge and data | Connectors; Knowledge; Learning and memory; Fields and records; Artifacts |
| Channels and notifications | Channels; Webhooks; Notifications and email |
| Operations | System health; Runs and queue; Background jobs; Logs and errors; Stop |
| Governance | Audit log; Retention, legal holds and erasure; Import and export |
| Reports | Usage and cost; Questions and gaps; Quality and canaries; Service levels |
| Platform (company console only) | Settings; Features and plugins; Limits, budgets and capacity; Secrets and credentials; Storage; Backup and recovery; Version and updates |

A person's own work (Ask, My workspace, My approvals, Records) stays a small group above these,
because an administrator is also a member.

### The biggest gaps

- The second factor never reaches the token (above), and the console never says so.
- **Agents cannot be created.** The builder is written and tested in the domain
  (`brain.builder`, `brain.agents.install`, `brain.agents.lifecycle`), the form and the canvas are
  built (`ManifestForm.tsx`, `ProcedureCanvas.tsx`), and no route or page connects them.
- **Departments, scopes, packs and the routing ladder have no writer at all.**
- **Nothing takes effect downstream of four controls:** connectors, skills, automations, spend.
- **No service accounts or API keys, no channel configuration, no stop button, no budget
  editing, no settings editing after setup, no credentials screen** (the credential routes exist
  and no page calls them).
- **Lists do not search, filter, sort or page.** Most routes take a `limit` and nothing else
  (`console/tests/long-lists.test.tsx` records each one).
- **The console does not look like its own design.** `console/src/theme/tokens.css` is a generic
  blue and grey palette; `docs/screens.html` draws warm neutrals, state colours held apart from
  the brand, IBM Plex Sans, KPI strips, cards, breadcrumbs and a grouped sidebar.

### The interface approach, in one paragraph

Keep the React console, its API client, its failure rules and its tests. Restyle it to the
structure of `docs/screens.html`, with the brand accent read from the install's own
`INSTALL_ACCENT_COLOUR` rather than written into the source (Verz sets its orange on its install;
another company sets theirs). Add a small set of shared components: a grouped sidebar with global
search, breadcrumbs, a list page with a server-side query contract, a detail page with tabs, a
drawer, a toast region and empty, loading and failure states. Build them from **shadcn/ui on its
Radix base, with Tailwind CSS v4**, which the owner chose on 2026-09-17: the components are copied
into the console, mapped onto the design's tokens and adopted page by page. Reject a packaged design
system (MUI, Ant, Mantine) because each brings its own theme engine and fights the token and lock
rules this console already enforces. Part 5.7 records the decision, its reasons and its risks.

### The plan, in waves

| Wave | Headline | Unblocks |
| --- | --- | --- |
| 0 | Make what is built reachable: second factor in the token and said on screen, approvals store, missing first-administrator reads, furnish an empty install, plain 500s | every administrative write |
| 1 | The shell: new navigation, shared list and detail components, the server list contract, the theme, global search, a browser end-to-end harness | every module page |
| 2 | Complete the modules whose domain code exists: people and organisation writes, roles and packs, access explanation, agents builder and lifecycle, templates, skills lifecycle, connectors test and key replacement, credentials, service accounts | creating and governing agents |
| 3 | Make controls take effect: skills at run time, connector reading, automations run and pause, the stop button, budgets and spend, approvals produced, leash moves, settings editing | the console changing behaviour |
| 4 | Breadth: channels, system health and alerts, queue and side effects, import, backup drills, access friction, handover | running the whole platform |

---

## Part 0. What was measured, and what was not

**The code of record is commit `273092a`, not the working tree.** On 2026-09-17 the main working
tree at `C:\Claude\Verz OS v2.0\brain` held the files of `1d25b7f` while `main` pointed six commits
later, because those commits were made from worktrees. 98 files differ, including the Logs screen,
the permission canaries, question gaps and document chunking. Every claim here about a file that
differs was read with `git show 273092a:<path>`. **Anybody running tests in that tree is testing
old code**; `git status` shows the new files as deleted.

| Measure | Value at `273092a` | Source |
| --- | --- | --- |
| Tables | 71 declared, plus `gate.delegation` with no model | `brain.tables.TABLES_IN_DEPENDENCY_ORDER`, migration 0028 |
| Migrations | 64 (0001 to 0064, no branches) | `migrations/versions` |
| Installation values | 23 | `brain.install.INSTALLATION` |
| API routes under `/api/v1` and `/setup` | 110 | `docs/console-audit.md` |
| Router modules | 38, all mounted | `brain.app.create_app` |
| Console addresses | 66 | `console/src/App.tsx` |
| Menu entries | 50 (Operate 10, Govern 23, Report 6, Use 4, Install 7) | `console/src/layout/Shell.tsx`, `pages/installQuery.ts` |
| Registered screens | 36, of which 7 have no page (queue, knowledge_coverage, incidents, halt, exports, access_friction, budget) | `brain.console.screens.SCREENS` |
| Console write calls | 39, reaching 46 routes | `console/tests/support/writes.ts` |
| Audit actions | 26, of which 6 have no durable emitter | `brain.audit.ledger.AuditAction` |
| Scheduled controls | 16, of which 9 have no runner | `brain.ops.controls.CONTROLS`, `brain.ops.schedule_runner.RUNNERS` |

**Not done, and said so.** No browser opened the console and no live install was queried; the
failure diagnosis is from code, the realm file and a test client over the real application with a
first administrator's grants (401, 404 and 500 answers measured through
`tests/fixtures/console_http.py`). The one live confirmation worth making is in Wave 0.1.

**The AnyGen screenshots could not be read.** `C:\Claude\Verz OS v2.0\_research\anygen-screenshots`
is outside the directory this session is confined to, and the confinement hook refused every read.
The concepts taken from AnyGen are therefore the ones the design of record already records in
`docs/screens.html` SCREEN 13 ("What I took from AnyGen, and what I did not"): the agent as a
container you open, capabilities as one block of connectors, skills and channels, cost on the
agent's front page, memory as a visible file with history, artifacts as first-class. Part 5.8 lists
what to check against the screenshots once they are copied under `brain/docs/reference/`.

---

## Part 1. What exists today

### 1.1 The failures, cause by cause

| # | Cause | What the administrator sees | Evidence | Fixed in |
| --- | --- | --- | --- | --- |
| F1 | `admin` and `approve` verbs need `STRONG` assurance; assurance is read only from `amr`; the realm emits no `amr` | 404 "I could not find that." on every write and on every screen read through an `admin:` or `approve:` capability; empty pages or missing controls elsewhere. The registry's navigation for that reader loses Stop and Access review, but the company menu is a constant in `Shell.tsx`, so Access review is still listed and answers 404 when opened | `gate/admission.py` `ASSURANCE_VERBS`; `identity/bearer.py` `assurance_from`, `SECOND_FACTOR_METHODS`; `api_routes.channel_for`; `ops/keycloak/realm-export.json` (client scope `brain-identity` has sub, groups, department and audience mappers only) | W0.1, W0.2 |
| F2 | No scope, department, team, registry row, pack, routing rung, agent or signed template exists on an install | a grant to anybody is refused (unknown scope slug is a 404); Departments, Capabilities, Scopes, Agents and Prompts are empty; the model ladder is empty | `govern_routes.add_grant` (scope slug resolved against live `gate.scope`); `ops/starter.py` "Nothing applies the starter set today"; no INSERT into those tables anywhere in `src` | W0.5, W2.1 |
| F3 | Approvals store never built | 500 "Something went wrong." on the Approvals screen, for everybody | `app.suspension_store_for(..., ledger=None)`; `approval_routes._require_source`, `_require_store` | W0.3 |
| F4 | Reads never granted to the first administrator | 404 on Routing, Classification, Learning, Memory; the audit export is never offered | `identity/first_administrator.py` `OVERSIGHT` lacks `read:routing_matrix`, `read:field_classification`; `read:console.content` withheld on purpose; `data_transfer.reads_the_whole_ledger` needs `read:audit_read` and three withheld audit kinds | W0.4 |
| F5 | Two feature switches ship off | Prompts cannot be edited, jobs cannot be paused or run, with a sentence rather than a generic error | `ops/features.py` `PROMPT_EDITING`, `SCHEDULE_CONTROL` | W0.6 (link to Features) |
| F6 | No vault or object store on a lite install | sentences (409, 503) on credential, relay password, webhook and connector writes; Storage and Recovery say nothing is connected | `credential_routes`, `webhook_routes`, `object_store_at_start` | reported, not a defect |
| F7 | Plain 500 with no error body | "Internal Server Error" text | `GET /report/spend` with `until <= since` raises `SpendReportViewError` (not a `BrainError`); unwrapped database errors in `notification_routes`, `feature_routes`, `provider_routes.switch` | W0.6 |
| F8 | Controls that reach nothing yet | the write succeeds and nothing changes | `ops/connector_admin.NOTHING_READS_A_CONNECTED_SOURCE_YET`; `automation_gallery.NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET`; skills: `tools/skills.offered_cards` and `EffectiveAgent.skill_pins` called only by the Skills screen; `ops/spend_store.record` has no caller; an agent's `tier` is never passed as `models/routing.RoutingRequest.requested_tier`; no route runs an agent, and the answer lane calls no model (`prompt_routes` answers `no_model_is_called_yet`) | Wave 3 |
| F9 | A sign-in bound to nobody | the console signs in, is refused with one 401 sentence, forgets the session and signs in again, until three attempts in sixty seconds stop it with "your account may not have been added" | `app.handle_token_refused`; `console/src/api/client.ts` (a 401 forgets the session); `auth/session.ts` attempt counter | B1, B5 (bind from the person's page; say on the first-run finish who binds the next person) |
| F10 | Two tabs refreshing one session | one tab is signed out | refresh tokens cannot be reused and the refresh lock is per tab (`console/README.md`, "Known gap: the cross-tab refresh race") | W1.2 (a cross-tab lock) |

**Why a person could not tell F1 from a broken screen.** The product answers a refused request and
a missing record with one sentence, which is right (Part 6, rule R1). What it also does is keep the
reason a person could act on, their own sign-in strength, out of every screen: `/api/v1/me` returns
`assurance` and the Overview shows it as a chip with no explanation. Telling a person what their
own sign-in cannot do is allowed (`admission.would_lose`'s docstring says so) and discloses nothing
about any record.

### 1.2 What an install holds on the day it is set up

| Table | Written by | Effect on the console |
| --- | --- | --- |
| `gate.scope`, `gate.department`, `gate.team` | nothing | no department to place anybody in, no scope to grant over |
| `gate.capability_registry`, `gate.capability_pack`, `gate.capability_pack_assignment` (insert) | nothing | the Capabilities vocabulary is empty; packs cannot be assigned |
| `gate.field_policy` | nothing | classification is read from code constants, not the table |
| `ops.routing_tier`, `ops.routing_rung` (insert) | nothing | no rung to call, check or edit |
| `agent.agent`, `agent.template_instance` (insert) | nothing | no agent, so Agents, Prompts, skill assignment and automations have nothing to act on |
| `agent.template_version`, `agent.upgrade_decline` | nothing | the catalogue shows the 23 built-in manifests from code, unsigned, and none can be installed |
| `auth.directory_role_grant` | nothing (plan only) | nobody's role is recorded |
| `er.*`, `chat.*`, `gate.delegation` | nothing | not administered today |
| `ops.spend_actual`, `ops.budget_version`, `ops.plugin_*`, `agent.browser_envelope`, `gate.suspension` (insert), `know.item` and `know.chunk` (insert) | a writer exists and nothing calls it | spend empty, budgets unwritable, no approvals to decide, knowledge empty |

`ops.control_run` has row-level security policies and no `GRANT` to `brain_app` in any migration;
its writer runs in the worker as the owner.

### 1.3 Console pages today

Verdicts: **works** (reachable and does what it says), **partial** (reachable, something named is
missing), **broken** (refuses or faults for the first administrator on a normal install),
**empty** (works, and nothing on an install can put rows in it), **duplicated** (the same subject
as another page).

| Address | Menu group and label | Reads | Writes | Verdict and why |
| --- | --- | --- | --- | --- |
| `/` | Operate: Overview | `GET /me` | none | partial: shows who is asking; none of SCREEN 1's KPIs, departments, "needs you" or activity is served |
| `/department` | (department console) | navigation, agents, questions, usage | none | partial: same shape, narrowed |
| `/runs` | Operate: Live runs | `GET /operate/runs` | none | works (read only) |
| `/jobs` | Operate: Scheduled jobs | `GET /jobs` | pause, resume, run | broken for writes (F1, F5) |
| `/errors` | Operate: Errors | `GET /errors` | none | works; duplicated with Logs |
| `/logs` | Operate: Logs | `GET /logs` | none | broken (F1: read is `admin:application_log`) |
| `/models` | Operate: Models and health | providers, operate/models, rungs, spend, service levels | provider switch, check | broken for writes (F1); empty ladder (F2) |
| `/routing`, `/routing/:rungId` | Operate: Routing | `GET /routing/rungs` | `PATCH` rung | broken for everybody (F4); duplicated with Models |
| `/connectors` | Operate: Connectors | `GET /connectors` | connect, disconnect | broken for writes (F1); partial (F8); misplaced under Operate |
| `/webhooks` | Operate: Webhooks | `GET /webhooks` | register, replace secret, switch off | broken (F1: empty list, no controls) |
| `/notifications` | Operate: Notifications and email | `GET /notifications` | notice switch, relay, password, test | broken (F1) |
| `/people`, `/people/:subject` | Govern: People and grants | people, scopes | grant, remove grant | broken for writes (F1, F2); no grant expiry field although the route takes `not_after` |
| `/departments` | Govern: Departments and teams | departments | membership, lead | empty (F2); broken for writes (F1) |
| `/sessions` | Govern: Sessions | sessions | end session | broken for writes (F1) |
| `/sign-in-links` | Govern: Sign-in links | sign-ins | bind, unlink | broken (F1): **the second person cannot be let in** |
| `/access_review` | Govern: Access review | access review | keep, remove | broken (F1) |
| `/elevation` | Govern: Elevation requests | elevation | request, decide | partial: requests file; decisions broken (F1) |
| `/staff_sources` | Govern: Staff sources | staff sources, trial | none | partial: the trial always says it cannot read (`staff_trial_source` never attached) |
| `/roles` | Govern: Roles | roles | none | works: the six compiled roles |
| `/capabilities` | Govern: Capabilities | capabilities | none | empty (F2) |
| `/scopes` | Govern: Scopes | scopes | none | empty (F2) |
| `/agents`, `/agents/:agentId/:tab` | Govern: Agents and leashes | agents, workspace, automation gallery | install automation | empty (F2); builder unmounted |
| `/skills`, `/skills/:name` | Govern: Skills and templates | skills | add, review, assign | broken for writes (F1); assign has no agent (F2); no run-time effect (F8) |
| `/agent-templates` | Govern: Agent templates | templates | none | partial: 23 built-in cards, nothing installable |
| `/prompts` | Govern: Prompts | prompts | edit, give back | empty (F2), switched off (F5); duplicated with an agent's instructions |
| `/library` | Govern: Knowledge | library | none | empty (ingestion has no caller) |
| `/learning` | Govern: Learning | learning | undo | broken (F4) |
| `/memory`, `/memory/:subject` | Govern: Memory | memory | none | broken (F4) |
| `/artifacts` | Govern: Artifacts | artifacts | none | empty |
| `/retention` | Govern: Retention and erasure | retention, controls, erasures, exports | release, withdraw, hold, lift, erase | broken for writes (F1) |
| `/audit` | Govern: Audit | audit, history | none | works: the only list with filters and a cursor |
| `/import-export` | Govern: Import and export | data transfer | export | broken (F4: never exportable) |
| `/subscribers` | Govern: Subscribers and notifications | subscribers | none | broken (F1: empty); duplicated with Webhooks and Notifications |
| `/classification/...` | Govern: Classification | classification | review (dry run) | broken (F4) |
| `/questions` | Report: Questions and gaps | questions | none | works |
| `/usage` | Report: Usage and cost | usage | none | partial: cost empty (F8) |
| `/quality` | Report: Quality and canaries | quality | none | works (canaries every 12 hours; findings go to worker stderr) |
| `/service-levels` | Report: Service levels | service levels | none | works |
| `/spend` | Report: Spend | spend | none | empty (F8), plain 500 on a reversed window (F7); duplicated with Usage |
| `/adoption` | Report: Adoption | adoption | none | works |
| `/ask` | Use: Ask | `POST /answer` | none | partial: fast lane only; the administrator holds no data grants, by design |
| `/me` | Use: My workspace | me/workspace | none | works |
| `/approvals`, `/approvals/:id` | Use: Approvals | approvals | decide | broken (F3) |
| `/records`, `/records/:entity` | Use: Records | records | none | partial: 404 for every entity with no row tool or grant |
| `/install` | Install: This install | install | none | works; duplicated with Version |
| `/updates` | Install: Version and updates | updates | none | works (read only) |
| `/recovery` | Install: Backup and recovery | recovery | none | partial: needs the object store |
| `/limits` | Install: Rate limits | limits | none | partial: live windows always unread |
| `/connections` | Install: Capacity | capacity | none | works (arithmetic; deployed memory unknown) |
| `/features` | Install: Features | features | switch | broken (F1) |
| `/storage` | Install: Storage | storage | none | broken (F1) |
| `/first-run`, `/first-run/staff-list` | not in menu | setup routes | appointment, sign-in | works (closes after setup) |

### 1.4 API routes, by router

Full per-route tables were produced for this document and are summarised here; the generated
`docs/console-audit.md` carries every path. **Authority** names the capability a route asks.
**Writes** names the table and how the audit entry is written.

| Router (`src/brain/`) | Routes | Authority | Writes and audit | Notable limits |
| --- | --- | --- | --- | --- |
| `govern_routes` | people, roles, capabilities, scopes, grants, grant removal | screen reads; `approve:grant` for writes (and the granted capability itself over the scope, `scoped_authority.may_grant`) | `gate.capability_grant` insert and `deleted_at`; trigger 0003 (ent_hash and trace fall back to zeros and `tx.<xid>`) | limit only; a pack's capability cannot be removed singly |
| `govern_people_routes` | departments, membership, lead, elevation (list, request, decide), access review (list, decide), subscribers | `approve:grant`; elevation list open to all | `gate.team_membership`, `gate.department_lead`, `gate.elevation_request`, `gate.review_decision`; triggers 0052, 0062 | limit only |
| `session_routes` | sessions, end, sign-in links, unlink | `read:session`, `admin:session`, `admin:sign_in` over everything | `auth.session.ended_at`, `auth.principal_identity.deleted_at`; triggers 0047, 0050 | unlink of the last administrator is a 409 |
| `sign_in_routes` | `POST /api/v1/sign-ins`, `POST /setup/sign-in` | `admin:sign_in` over everything; setup code | `auth.principal_identity`, member grant; triggers | |
| `setup_routes`, `setup_staff_routes` | appointment, staff source registration, sign-in, trial | setup code | principal, settings, grants in one transaction | closed after the first administrator |
| `staff_source_routes` | staff sources, trial | `read:staff_source` | none | trial never attached |
| `audit_routes` | audit, history | per entry `read:audit.<kind>` | none | action, kind, actor, period, order, cursor |
| `estate_routes` | library, learning, undo, memory | `read:document`; content plane; `admin:learning` | `mem.correction`; trigger 0061 | library limit only |
| `erasure_routes`, `retention_routes` | controls, erasures, exports log, report, release, withdrawal, holds, lift | `admin:erasure`, `admin:retention`, `admin:legal_hold` over everything | `ops.erasure_request`, `ops.retention_release`, `obs.legal_hold`; triggers 0054, 0060 | 404 refusals name their reason after authority passes |
| `classification_routes` | classification, column review | `read:field_classification`, `admin:field_classification` | none (a dry run) | |
| `agent_routes` | agents, workspace, templates | audience; `read:agent`; skills screen for templates | none | cap 500 |
| `approval_routes` | queue, card, decision | the action's own capability over its row | none: store absent (F3) | |
| `automation_gallery_routes`, `automation_routes` | gallery, preview, install; `POST /automation/tool-call` | `admin:automation`; automation credential | `agent.automation` (starts paused); trigger 0055 | server-recomputed confirmation digest |
| `skill_routes` | skills, add, review, assign | `admin:skill`, `admin:skill_review` over everything | `agent.skill`, `skill_review`, `skill_assignment`, instance overlay; trigger 0056 | upload and paste only |
| `connector_routes` | connectors, connect, disconnect | `read:connector`; `admin:connector` over the source | vault key, `ops.credential_write`, `ops.connector_connection`; triggers 0054, 0057 | xero and hubspot only |
| `credential_routes` | credentials, set credential | `admin:credential` over everything | vault, `ops.credential_write`; trigger 0054 | provider slots only; **no page calls either route** |
| `provider_routes`, `routing_routes` | providers, switch, check; rungs, edit rung | `admin:routing_matrix`; `read:routing_matrix` (never granted) | `ops.setting provider.*`, `ops.routing_rung`; trigger 0059 | four rung fields editable, no add or reorder |
| `prompt_routes` | prompts, edit, give back | `admin:agent_instructions`; `prompt_editing` switch | instance overlay and `agent.persona`; trigger 0059 | optimistic hash |
| `install_routes`, `feature_routes`, `storage_routes` | install, updates, recovery, limits, capacity; features, switch; storage | screen reads; `admin:feature`, `admin:storage` over everything | `ops.setting feature.*`; trigger 0059 | all read only except the switch |
| `jobs_routes`, `error_routes`, `log_routes`, `operate_routes` | jobs, pause, resume, run; errors; logs; runs, models | `admin:schedule`; `admin:application_log`; screen reads | `ops.setting schedule.*`; trigger 0059 | logs has level, event, window, cursor |
| `webhook_routes`, `notification_routes` | webhooks, register, secret, switch off; notifications, notice switch, relay, password, test | `admin:webhook_subscriber`, `admin:notification` over everything | subscriber, vault, `ops.webhook_change`, `ops.setting notice.*`, `mail.*`; triggers 0054, 0059 | the test send writes `ops.operation`, no audit entry |
| `data_transfer_routes`, `artifact_routes` | data transfer, export; artifacts | `admin:export` plus the whole ledger; `read:artifact` | `ops.data_export`; trigger 0053 | audit trail is the only data set |
| `report_routes` | service levels, spend, adoption, usage, questions, quality | row by row, no refusal | none | window parameters only |
| `navigation_routes`, `mine_routes`, `api_routes`, `docs_routes` | navigation, my workspace, me, records, answer; build pages | per reader; `docs_routes` unauthenticated build pages | none | `/api/audit/anchor` anchors an empty in-memory chain |

**HTTP methods.** Three routes use `PUT` or `PATCH`; none uses `DELETE`. CORS allows only `GET`
and `POST`, which does not matter because the console is served from the API's own origin
(`brain.console_static`) and `BRAIN_CORS_ORIGINS` is empty by default.

### 1.5 Tables and relationships

Ten schemas (`brain.db.SCHEMAS`: auth, gate, agent, know, mem, obs, proj, er, ops, chat). Every
table enables row-level security in the migration that creates it; none uses `FORCE`, which the
worker relies on.

```
auth.principal ──< principal_identity (sign-in links)      gate.scope (predicate, slug)
      │        ──< session                                     ▲ value, not a key
      │        ──< directory_role_grant (roles from IdP)   gate.department ──< gate.team
      │                                                         │                 │
      ├──< gate.capability_grant (capability, scope JSON,       └──< department_lead
      │        granted_by, reason, not_after, deleted_at)       team_membership >─┘
      ├──< gate.capability_pack_assignment >── gate.capability_pack
      ├──< gate.elevation_request ── grant_id ──> capability_grant (when approved)
      └──< (values) review_decision, suspension, automation_owner, spend, artifacts

agent.template_version (template_id, version: insert only, signed)
      ▲ composite key
agent.template_instance (id = agent slug, pin, overlay, field owners, effective document)
      ·· same value ··  agent.agent (persona, tier, audience, ceiling, disabled_at, archived_at)
agent.skill ──< skill_review ──< skill_assignment (agent_id value, replaces_digest)
agent.automation (agent_id, runs_as_id values, next_run_at null = paused)
gate.automation_owner (credential digest, declared tools, ceiling)   no key between the two
ops.connector_connection (one live row per source, digest pinned)   no agent column
know.item ── document_id value ──< know.chunk (owner, department, visibility copied)
mem.persistent / mem.adaptive  <── mem.learning, mem.correction (values)
ops.routing_tier ·· tier value ·· ops.routing_rung ──< ops.model_attempt
ops.webhook_subscriber ──< outbox_delivery >── outbox_event;  ──< webhook_change
ops.retention_report ──< retention_release;  obs.legal_hold;  ops.erasure_request
ops.setting (install.*, feature.*, provider.*, notice.*, mail.*, schedule.*)
obs.audit_entry (hash chained, append only, written by triggers)
```

**How an agent relates to everything else.** An agent's reach is its `scope` and `capabilities`
built in memory into an `EntitlementSet` for principal `agent:<id>` (`agents.model.
entitlement_ceiling`) and intersected with the caller; it is never a grant row. Skills attach by
assignment rows and by the manifest's `skills` path; connectors by the manifest's `connectors` and
tool lists; knowledge by the scope predicate over each chunk's owner, department and visibility.
Actors are values everywhere, so a record outlives the person it names.

**Lifecycle markers, which the console's "delete" must use.** `deleted_at` on 17 tables (grants,
identities, principals, scopes, departments, teams, settings, rungs and others);
`disabled_at`/`archived_at` on agents; `ended_at` on sessions, memberships and leads;
`disconnected_at` on connections; `deactivated_at` on subscribers; `released_at` on holds;
`withdrawn_at` on releases; insert-only facts everywhere else. Hard deletes exist only in erasure
(`auth.directory_role_grant`), log trimming (`obs.application_log`), telemetry partition moves and
the demo seed.

### 1.6 Read modules, stores and services

| Layer | Modules | What the console should know about them |
| --- | --- | --- |
| Screen registry and permission | `console/screens.py`, `console/reads.py` (`permitted`), `console/department_console.py` | the menu is the API's answer; a screen needs its capability and a plane over a containing scope |
| Operate and reports | `console/operate.py` (`tile`, honest counting), `usage_view`, `usage_screen`, `spend_view`, `spend_report_view`, `service_level_view`, `quality_view`, `questions_view`, `adoption_view` | a figure is shown only to a reader who could open the screen it counts |
| Governance | `console/govern.py` (people, catalogue, role holders, certify, sessions, friction), `govern_surfaces.py`, `govern_estate.py`, `organisation.py`, `elevation.py`, `scoped_authority.py`, `role_surfaces.py`, `global_surfaces.py`, `subscribers.py`, `staff_source_view.py`, `sign_in_links.py`, `auditor.py` | `role_holders`, `global_surfaces` acts (confirm nomination, disable principal, halt) have no route |
| Agents | `console/workspace.py` (7 tabs, 2 populated), `agent_tabs.py` (`detach`), `agent_output.py`, `agent_automations.py`, `automation_gallery.py`, `reach_view.py` (ceiling, run preview through the real gate, leash matrix, memory revisions), `workspace_capabilities.py`, `skill_library.py`, `own_things.py` | `reach_view` is the access explanation already written |
| Install | `console/installation.py`, `version_view.py`, `recovery_view.py`, `model_matrix.py`, `connector_trust.py`, `read_replica.py` | every fact is measured, declared or absent |
| Stores (write) | `ops/*_store.py`: organisation, elevation, review, session, sign-in binding, first administrator, skill, connector, credential write, webhook, outbox, setting, install settings, retention, erasure, data export, memory, agent automation, artifact, log, question, question gap, telemetry, schedule, operation | each sets the actor, reach hash and trace for its trigger where it calls `attributed_to` |
| Domain with no store or route | `brain.builder` (drafts, form, compose, procedure, rehearse, publish, coauthor), `agents/install`, `agents/lifecycle`, `agents/authoring`, `agents/upgrade`, `identity/lifecycle` (joiners, movers, leavers, disable, adopt), `identity/packs`, `identity/sessions.ServiceAccount`, `channels/api_keys`, `ops/halt`, `ops/budget_store`, `ops/budget_stop`, `ops/alerting`, `ops/denial_alerts`, `ops/handover`, `ops/starter` | the largest source of buildable console function |

### 1.7 Capabilities, and what the first administrator holds

**Grammar.** `verb:noun[.field]`, verbs `read`, `write`, `invoke`, `approve`, `admin`, a trailing
`.*` the only wildcard, scopes a conjunction of clauses, no deny anywhere
(`core/entitlement.py`, `core/scope.py`). Three console planes nest: existence, configuration,
content (`read:console.<plane>`).

**Granted at appointment** (`identity/first_administrator.py`, every grant over everything):
26 `admin:` capabilities (`ADMINISTRATION`), `approve:grant` (`GOVERNANCE`), and 45 reads
(`OVERSIGHT`: every screen's read at the existence and configuration planes, the two plane
capabilities, `read:audit` and 14 audit kinds). Reconciled at every start without re-granting a
revoked capability (`identity/administration_reconciliation.py`).

**Withheld on purpose**, with the product's reasons: `read:console.content`, `read:learning`,
`read:memory` (content is what a person or agent was told), `approve:action` (approving lets an
agent act over data the administrator cannot read), `read:audit.entity`, `.artifact`, `.memory`.
**Withheld by omission** and to be granted (W0.4): `read:routing_matrix`,
`read:field_classification`.

**Roles** are six compiled values (`identity/roles.py`: Super Admin, Department Admin, Member,
Auditor, Connector Admin, Approver). **No role implies a capability**, and no table records who
holds a role (`role_grant`, M1.3.2, was not built; `auth.directory_role_grant` is directory-sourced
and has no scope).

### 1.8 Audit actions

26 actions (`audit/ledger.py AuditAction`). Durable entries are written by database triggers
(migrations 0003, 0047, 0050, 0052 to 0062). **No durable emitter for** `deny`, `leash_change`,
`entity_merge`, `break_glass`, `approval` and `record_read`. Four gaps worth a console owner's
attention: routes that do not call `attributed_to` leave an entry whose reach hash is zeros and
whose trace is `tx.<xid>` (`govern_routes` grant writes, `retention_routes` release, provider
switch, notification writes, webhook switch-off); the approval decision is recorded only in memory;
the relay test message has no audit entry by design (`mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION`);
the audit anchor route anchors an empty chain.

### 1.9 Background controls

| Control | Cadence | Runs today |
| --- | --- | --- |
| retention_sweep | daily | yes, report only until released |
| canary_run | 12 hours | yes; findings to the worker's stderr only |
| knowledge_reverification | daily | yes; nags recorded, nobody told |
| outbox_dispatch | 1 minute | yes |
| spend_report_refresh | daily | yes, over an empty table |
| erasure_queue | 15 minutes | yes |
| restore_drill, backup_exposure, denial_digest, directory_sync, resolution_calibration, queue_redrive, side_effect_resume, model_health_probes, spend_correction | various | **no runner** |
| audit_anchor | 6 hours | called by a GitHub Actions timer on a route that reads nothing |

Pause, resume and run now are `ops.setting` rows the tick reads; a run in progress cannot be
stopped (`jobs_routes`: `no_run_can_be_stopped`).

### 1.10 The owner's list, measured

| Owner's item | Today | Evidence |
| --- | --- | --- |
| Dashboard | partial | `/` reads `GET /me` only; `console/operate.tile` is written and unserved |
| Organisations / Companies | not applicable as tenancy; company settings missing after setup | single tenant by design (`CLAUDE.md`); wizard-only `INSTALL_COMPANY_NAME` etc. |
| Departments | empty and partial | no writer for `gate.department` or `gate.team` |
| Users | partial, writes broken | `/people`; F1, F2; no create, disable, import |
| Roles and permissions | partial, duplicated across three pages | Roles, Capabilities, Scopes; no role holders; packs unwritable |
| Agents | empty, creation missing | no insert into `agent.agent`; builder unmounted |
| Agent templates | partial | 23 unsigned built-ins listed, nothing installable |
| Skills | partial, writes broken, no run-time effect | `skill_routes`; F1, F8 |
| Connectors / Integrations | partial, writes broken, nothing reads | `connector_routes`; F1, F8; channels missing |
| Knowledge / Documents / Data sources | empty | `chunk_store.ingest_document` has no caller |
| Workflows / Automations | partial | install only (paused); no pause, edit, remove, runner |
| AI providers / Models | partial, writes broken, empty ladder | `provider_routes`, `routing_routes`; F1, F2, F4 |
| Prompts / System configuration | prompts empty and switched off; system configuration missing | `prompt_routes`; no settings writer |
| API configuration | missing | no service account or API key table; credential routes unused |
| Webhooks | broken (F1) | `webhook_routes` |
| Notifications | broken (F1), duplicated | Notifications and Subscribers |
| Storage | broken (F1), read only | `storage_routes` |
| Usage / Credits / Limits | usage partial; credits not applicable; limits read only; budgets missing | `report_routes`, `install_routes.limits`, `ops/budget_store.append` has no caller |
| Logs | broken (F1) | `log_routes` |
| Audit logs | works | `audit_routes` |
| System health | missing | `/health/ready` has no screen; registry `incidents` has no page |
| Background jobs | partial | `jobs_routes`; F1, F5; 9 controls with no runner |
| Settings | missing | wizard only |
| Import / Export | export broken (F4), import missing | `data_transfer_routes` |
| Backup / Recovery | partial | `recovery` read; no drill control |
| Version / Deployment | works (read), duplicated | `/install` and `/updates` |

---

## Part 2. The information architecture

### 2.1 Principles

1. **Grouped by what an administrator is trying to do**, not by the module that serves it
   (`docs/admin-console.md`). Nine groups, each a job: who can do what; what the AI can do; what
   it knows; how it talks to the outside; is it healthy; is it compliant; how is it used; how is
   the server set up.
2. **One module per entity, one entity per module.** Where two pages today show one subject
   (Errors and Logs, Models and Routing, Notifications and Subscribers, Usage and Spend, This install
   and Version, Roles, Capabilities and Scopes, Sessions and Sign-in links), they become one module
   with tabs.
3. **The container and the inventory are different pages, and both exist.** SCREEN 13: the agent
   is the container you open; Skills, Knowledge and Connectors are the company-wide inventories.
   An agent's Skills tab is the inventory filtered to one agent, calling the same routes.
4. **The menu is the API's answer.** `GET /api/v1/console/navigation` already decides which
   console a reader gets. The new groups become a registry concept in `brain.console.screens`, so
   the company menu stops being a constant in `Shell.tsx`. A screen whose subject is the
   installation stays off the department console.
5. **Honest equivalents over imitations.** Where the owner's list names something this
   single-tenant, grant-based product does not have (organisations, credits, role-to-permission
   editing, a model per agent), the module says what the product has instead.
6. **Every module states what it cannot do yet, on the screen**, in the shape the Connectors and
   Features screens already use (a named constant, served as a field).

### 2.2 The map

```
Use (a person's own work):  Ask · My workspace · My approvals · Records

Home
  A1 Dashboard
People and access
  B1 People                         B4 Access reviews and elevation
  B2 Departments and teams          B5 Sign-in, directory and sessions
  B3 Roles and permissions          B6 Service accounts and API keys
Agents and AI
  C1 Agents                         C4 Approvals and autonomy
  C2 Agent templates                C5 Automations
  C3 Skills and tools               C6 Models and routing
Knowledge and data
  D1 Connectors    D2 Knowledge    D3 Learning and memory    D4 Fields and records    D5 Artifacts
Channels and notifications
  E1 Channels      E2 Webhooks     E3 Notifications and email
Operations
  F1 System health    F2 Runs and queue    F3 Background jobs    F4 Logs and errors    F5 Stop
Governance
  G1 Audit log     G2 Retention, legal holds and erasure     G3 Import and export
Reports
  H1 Usage and cost    H2 Questions and gaps    H3 Quality and canaries    H4 Service levels
Platform (company console only)
  I1 Settings    I2 Features and plugins    I3 Limits, budgets and capacity    I4 Secrets and credentials
  I5 Storage     I6 Backup and recovery     I7 Version and updates
```

The Stop control (F5) is also a permanent button in the shell header for a reader holding
`admin:halt`, because a stop somebody has to navigate to is slower than one on every page.

### 2.3 Module specifications

Each module: **Entity** (tables), **Belongs / separate**, **Relationships**, **Manages**,
**Permissions**, **Depends on**, **List**, **Detail**, **Actions**. "To build" marks what does not
exist; everything else is served today.

#### A1 Dashboard

- **Entity:** none of its own; tiles from the screens it summarises.
- **Belongs:** health strip (readiness, halts in force, budget stops), "Needs you" (each queue the
  reader can open: approvals, access review, elevation, skill reviews, tier-three learning, publish
  approvals, unbound sign-ins, knowledge past review), activity (audit), period and department
  filter. **Separate:** every figure's detail lives on its module.
- **Permissions:** `read:overview`; each tile by `console/operate.tile` (a figure only to a reader
  who could open the screen that counts it, withheld rather than narrowed where it has no narrower
  version). Department console: `/department`, same shape.
- **Depends on:** a new `GET /api/v1/console/overview` over `operate.tile` (to build).
- **Actions:** open a queue; press Stop (header).

#### B1 People

- **Entity:** `auth.principal`, with `principal_identity`, `session`, `capability_grant`,
  `capability_pack_assignment`, `team_membership`, `department_lead`, `elevation_request`.
- **Belongs:** the directory of principals and one person's page. **Separate:** roles and the
  capability vocabulary (B3), organisation structure (B2), sessions across everybody (B5), service
  accounts (B6).
- **Manages:** grants (with expiry), pack assignments, placements, disabling a leaver, reinstating,
  adopting what a leaver owned, binding a sign-in.
- **Permissions:** `read:grant` to list; `approve:grant` over a containing scope to grant, and the
  granted capability itself over that scope (`scoped_authority.may_grant`); `admin:sign_in` to
  bind; disabling is `approve:grant` (`global_surfaces`).
- **Depends on:** scopes existing (W0.5, W2.1); the second factor (W0.1).
- **List:** name, primary department, employment, standing (live, disabled), second factor seen in
  last session, number of grants the reader may see (not of all). Search by name; filter by
  department and standing from `screens.offerable`; sort by name or last sign-in; cursor.
- **Detail tabs:** Overview; **Access** (Part 4.4); Grants; Sign-ins and sessions; Placements;
  Owned agents and automations; History (ledger entries about the person).
- **Actions:** grant (to build: expiry field, pack); remove grant (confirmed); bulk grant (to
  build: one route over a set, all or nothing); disable as a leaver (to build over
  `identity/lifecycle.disable`, showing what will stop and what needs adopting); reinstate (to
  build; named `reinstate` in code, see R10); transfer ownership (to build over
  `lifecycle.adopt`); bind sign-in (exists, moved here from Sign-in links).

#### B2 Departments and teams

- **Entity:** `gate.department`, `gate.team`, `gate.scope` (a department's predicate),
  `department_lead`, `team_membership`.
- **Belongs:** the company's internal structure, the scopes grants are bounded by. **Separate:**
  a grant (B1), a role (B3).
- **Manages:** create, rename, retire a department and its scope; create, rename, retire a team;
  appoint and stand down a lead; place and remove people.
- **Permissions:** `approve:grant` over the department (`organisation.ORGANISING_AUTHORITY`);
  creating a department to build under the same authority held over everything.
- **Depends on:** a writer for `gate.department`, `gate.team` and `gate.scope` with audit triggers
  (to build; 0062 audits memberships and leads only).
- **List:** departments as a tree with teams; lead; people placed (a count only of people the
  reader may see). **Detail:** members, lead history, the scope predicate in words, agents whose
  audience is the department, knowledge coverage.
- **Actions:** create, rename, retire (confirmed, refused while live grants are bounded by its
  scope unless moved), appoint lead, place, remove.

#### B3 Roles and permissions

- **Entity:** the six compiled roles (`identity/roles.py`), `gate.capability_registry`,
  `gate.capability_pack`, `gate.scope`, role holders (to build: `role_grant` with scope, M1.3.2).
- **Belongs:** the vocabulary of who a person can be and what can be granted. **Separate:** who
  holds a grant (B1), the explanation of one person's access (B1 Access tab).
- **Manages:** packs (create, version, retire, assign); role appointments with scope (to build);
  the capability registry is product-declared and shown, not edited.
- **Permissions:** `read:role`, `read:capability`, `read:scope`; writing a pack or a role
  appointment `approve:grant` over everything (Super Admin confirms nominations,
  `global_surfaces`).
- **List tabs:** Roles (what each exists to do, holders); Capabilities (vocabulary, holders by
  scope); Packs; Scopes.
- **Actions:** create a pack, assign a pack (to build: `capability_pack_assignment` insert),
  appoint a role within a scope (to build). **Not offered: editing what a role grants**, because a
  role grants nothing (R3).

#### B4 Access reviews and elevation

- **Entity:** `gate.review_decision`, `gate.elevation_request`, denial patterns
  (`ops/denial_alerts`).
- **Belongs:** periodic certification, break-glass requests and decisions, access friction.
- **Permissions:** `approve:grant` (review, decide); anybody may request an elevation.
- **List tabs:** Review queue (keep or remove, never your own grant); Elevation requests (reason,
  hours up to 4, lapse); Access friction (to build: the registry's `access_friction` screen, shapes
  of refusal patterns and never the capability or record).
- **Actions:** keep, remove, request, approve, deny. All exist; all need W0.1.

#### B5 Sign-in, directory and sessions

- **Entity:** installation values `INSTALL_OIDC_*`, `INSTALL_BROKERED_DIRECTORY`,
  `INSTALL_STAFF_SOURCE*`; `auth.session`; `auth.principal_identity`.
- **Belongs:** how people sign in and arrive: identity provider summary, second-factor policy and
  status, staff source and its sync, unbound sign-ins, active sessions, session policy (10 hours
  absolute, 30 minutes idle, `identity/sessions.py`). **Separate:** a person's own sessions (B1
  tab).
- **Manages:** end a session; bind and unlink a sign-in; choose and trial the staff source; apply a
  sync plan (to build: `directory_sync` runner and a reviewed apply); change identity provider
  values (to build, restart-required, see I1).
- **Permissions:** `read:session`, `admin:session`, `admin:sign_in`, `read:staff_source`.
- **Actions:** end session, unlink (409 for the last administrator), bind, trial source, apply
  sync (to build), "sign in again with your authenticator" (W0.2).

#### B6 Service accounts and API keys

- **Entity:** to build: `auth.service_account` (owner, declared ceiling, `not_after`) and
  `auth.api_key` (handle, digest, account, expiry), over `identity/sessions.ServiceAccount` and
  `channels/api_keys`; automation credentials in `gate.automation_owner`.
- **Belongs:** every non-person caller: service accounts, their keys, automation credentials.
- **Rules carried:** a service account resolves its owner's live entitlements narrowed by its
  ceiling and has no grants of its own; a key is shown once; at most two live keys per account;
  revocation deletes the key row and the ledger keeps the record (`channels/api_keys`); the API
  channel never carries `approve` or `admin`.
- **Permissions:** to build: `admin:service_account` over the owner's scope; the owner must hold
  what the ceiling names.
- **Actions:** create account, issue key (shown once), rotate, revoke (confirmed), change owner,
  expire.

#### C1 Agents

- **Entity:** `agent.agent`, `agent.template_instance`, drafts (to build:
  `agent.manifest_draft`, `agent.manifest_revision`), `agent.skill_assignment`, `agent.automation`,
  `agent.artifact`, memory, spend.
- **Belongs:** the roster and the agent as a container. **Separate:** the template catalogue (C2),
  the company skill inventory (C3), approvals across agents (C4), automations across agents (C5).
- **Manages:** create from a template or from scratch, edit through drafts and publish, enable,
  disable, archive, duplicate, transfer ownership, availability, ceiling, leash, instructions,
  skills, knowledge scope, connectors expected, automations, version and upgrade.
- **Permissions:** audience decides who sees it (`agents/model.visible_to`); `read:agent` for the
  ceiling; writes by a new `admin:agent` over the agent's department (to build), with publish
  widening needing a second approver (`builder/publish.approvers_needed`); instructions
  `admin:agent_instructions`; leash moves `approve:action` over the target
  (`scoped_authority.may_move_rung`).
- **List:** name, department audience, owner, state, tier, leash summary per operation, template
  and version, runs and cost (30 days). Search, filter by department, state, template; sort.
- **Detail tabs:** Overview (SCREEN 13: assembly block of connectors, skills, knowledge, channels,
  model chain; availability beside ceiling; preview as a person; spend); Instructions; Skills;
  Knowledge and connectors; Leash; Automations; Memory; Artifacts; Runs and cost; Versions; Settings.
- **Actions:** Part 4.1.

#### C2 Agent templates

- **Entity:** `agent.template_version` (signed, insert only), `agent.upgrade_decline`, built-ins
  in `agents/catalogue.py`.
- **Belongs:** the catalogue, a template's versions, readiness against this install, authoring a
  template from an agent, visibility. **Separate:** an installed agent (C1).
- **Permissions:** today the Skills screen's read (`agent_routes`); to build: publishing a
  template `admin:agent` over everything; sharing beyond the install per `authoring.TemplateVisibility`.
- **Actions:** Part 4.1, template table.

#### C3 Skills and tools

- **Entity:** `agent.skill`, `skill_review`, `skill_assignment`, detachment and retirement (to
  build); the frozen tool registry (`tools/startup.build_registry`).
- **Belongs:** the company skill library, the review queue, assignments, the tool catalogue.
  **Separate:** a skill on one agent (C1 tab, same routes).
- **Permissions:** `read:skill`; `admin:skill` to add and assign; `admin:skill_review` to decide
  (never your own import).
- **List tabs:** Library; Needs review; Retired; Tools (to build: a read of the registry, which no
  route lists).
- **Actions:** Part 4.2.

#### C4 Approvals and autonomy

- **Entity:** `gate.suspension`, publish approvals (to build), leash promotion evidence
  (`agents/supervision.py`), circuit-breaker demotions (`reach_view.breaker_trips`).
- **Belongs:** every decision a person must take before an agent may act: suspended actions,
  second approvals for a widened publish, leash promotions. **Separate:** access decisions (B4).
- **Permissions:** the action's own capability over its row (`role_surfaces.pending_for`); the
  first administrator holds no `approve:action` by design (R8).
- **Actions:** approve, reject with a reason code (exists, faults today, W0.3); promote or demote a
  rung with evidence (to build, W3.8).

#### C5 Automations

- **Entity:** `agent.automation`, `gate.automation_owner`.
- **Belongs:** every automation on every agent: owner it runs as, trigger, ceiling, next run,
  state. **Separate:** product scheduled jobs (F3), which are not automations.
- **Permissions:** `admin:automation` over the install row; runs as its owner (owner decision 56).
- **Actions:** install from the gallery (exists, lands paused); resume, pause, change schedule,
  remove (to build: insert-only `agent.automation_change`, because the table is SELECT and INSERT
  only); adopt an ownerless automation (`automation_owner_store.adopt`, no route).

#### C6 Models and routing

- **Entity:** providers (`ops.setting provider.*`), provider keys (vault), `ops.routing_tier`,
  `ops.routing_rung`, `ops.model_attempt`, circuit breakers.
- **Belongs:** providers (switch, key held, check), lanes and tiers, the chain each tier walks,
  health from real attempts, spend by lane. **Separate:** key entry (I4 owns the write form; this
  module links to it), house rules (shown on C1 Instructions).
- **Permissions:** `read:model_route`, `read:routing_matrix` (W0.4); `admin:routing_matrix` over
  everything.
- **Actions:** switch provider, check, edit rung (four fields), add or retire a rung and reorder
  (to build, insert-only positions), reset a breaker (not offered: breakers are replayed from
  attempts and a reset would be a second state).

#### D1 Connectors

Part 4.3.

#### D2 Knowledge

- **Entity:** `know.item`, `know.chunk`, the embedding queue.
- **Belongs:** documents and their stewardship (owner, visibility, verified, review due,
  superseded), coverage by department, ingestion and embedding status. **Separate:** a live source
  (D1).
- **Permissions:** `read:document` at the existence plane (the admin sees that an item exists and
  how widely it reaches, never its contents); publishing wider is
  `approve:knowledge.visibility`.
- **Actions:** upload (to build: route over `chunk_store.ingest_document`, owner-reach chunking);
  verify, set review date, supersede, archive (to build over `know.item.state`); promote
  visibility (to build, gated).

#### D3 Learning and memory

- **Entity:** `mem.persistent`, `mem.adaptive`, `mem.learning`, `mem.correction`.
- **Belongs:** the four learning tiers, undo, memory revisions per person or agent. Content plane.
- **Permissions:** `read:learning`, `read:memory`, `read:console.content`, `admin:learning`.
  Withheld from the first administrator on purpose; the module says who may hold it.
- **Actions:** undo tier one (exists); promote tier two and decide tier three (to build; nothing
  records agreement yet); edit a memory (to build on a person's own memory tab, per
  `console-audit`).

#### D4 Fields and records

- **Entity:** `gate.field_policy` and code classifications, `gate.fast_path_rule`, `er.*`,
  `proj.record`.
- **Belongs:** what each field requires to be read, fast-lane rules, entity merges.
  **Separate:** reading records (Use: Records).
- **Actions:** review a proposed classification (exists, dry run); apply a classification (to
  build, gated by a second person); list fast-path rules (to build, read); review merges (to build).

#### D5 Artifacts

- **Entity:** `agent.artifact`. List at the existence plane; re-downloading re-checks the
  requester. Also an agent tab.

#### E1 Channels

- **Entity:** to build: `ops.channel_binding` (surface, workspace or tenant identifiers, secret
  slot, state), over `channels/*` adapters and `ops/inbound_webhooks.INBOUND`.
- **Belongs:** Lark, Slack, Teams, Telegram, WhatsApp, email, the web widget: whether each is
  configured, its inbound verification check, the verbs it may carry
  (`admission.CHANNEL_VERBS`), rooms and their floor. **Separate:** outbound webhooks (E2).
- **Actions:** configure, write secret, test inbound verification, switch off (all to build).

#### E2 Webhooks

- **Entity:** `ops.webhook_subscriber`, `ops.webhook_change`, `ops.outbox_delivery`.
- **Actions:** register, replace secret, switch off (exist); switch back on (to build, as a new
  registration of the same id is refused: a `reactivated` change row); replay an exhausted
  delivery (to build).

#### E3 Notifications and email

- **Entity:** notices (`ops/notices.NoticeKind`, 13), `ops.setting notice.*`, `mail.*`, relay
  password in the vault, subscribers view.
- **Actions:** switch a notice, configure relay, keep password, send test (exist); per notice the
  screen says whether anything sends it (1 of 13 today).

#### F1 System health

- **Entity:** readiness checks (`app.ready`), worker heartbeat, vault seal state, object store,
  identity provider, circuit breakers, halts, budget stops, alerts (`ops/alerting.py`).
- **Permissions:** to build a read on the registry's `incidents` screen (`read:incident`),
  company console only.
- **Actions:** none that change state except acknowledging an alert (to build).

#### F2 Runs and queue

- **Entity:** live runs, the queue, `ops.operation` side effects.
- **Actions:** resolve a side effect in `unknown` (to build over `ops/crash`, `idempotency`);
  redrive a dead letter (to build).

#### F3 Background jobs

- **Entity:** `CONTROLS`, `ops.control_run`, `ops.setting schedule.*`.
- **Actions:** pause, resume, run now (exist); the page states which controls have no runner.

#### F4 Logs and errors

- **Entity:** `obs.application_log`, failed control runs, failed requests.
- **Tabs:** Logs (level, event, window, cursor); Errors (jobs, requests by trace id).

#### F5 Stop

- **Entity:** to build: `ops.halt` (insert-only halts and resumes) over `ops/halt.Halt`.
- **Rules carried:** stop is unilateral with no confirmation step; resume needs a stated reason and
  names whom it overrides; no expiry; unknown state is halted; admission refuses new work
  (`ops/admission.decide`); a halt may be announced to anybody refused by it.
- **Actions:** stop everything, stop one connector (the enforced axis today; department, agent and
  person axes are reported by `halt_gaps` until enforced), resume with reason.

#### G1 Audit log

- Exists: filters by action, kind, actor, period, order, cursor; per-subject history. To build:
  filter by agent id, export of the entries the reader may read (W0.4).

#### G2 Retention, legal holds and erasure

- Exists: report, release and withdrawal, holds and lifting, erasure requests and the queue, the
  export log. Needs W0.1 only.

#### G3 Import and export

- **Exists:** audit trail export. **To build:** knowledge import (D2), staff list import (B5),
  skill and template import (C2, C3), further export sets, client handover (`ops/handover.py`).

#### H1 to H4 Reports

- **H1 Usage and cost:** usage, spend (tab), adoption (tab); spend becomes real in W3.5.
- **H2 Questions and gaps**, **H3 Quality and canaries** (canary findings persisted rather than
  stderr, W4.7), **H4 Service levels**: exist.

#### I1 Settings

- **Entity:** `ops.setting install.*` via `brain.install.value_of`.
- **Belongs:** company name, product name, logo, accent colour, web address, locales, currency, time
  zone, sender address, model profile and endpoint, embedding revision, identity provider values.
- **Rules carried:** a saved value is loaded at start (`install_settings.refresh`), so the screen
  says which changes need a restart and of which service; `INSTALL_EMBEDDING_DIMENSIONS` refuses a
  change once anything is embedded; an identity provider change re-derives the redirect URIs.
- **Permissions:** to build: `admin:setting` over everything.

#### I2 Features and plugins

- Features: exists. Plugins: read-only statement; owner decision 58 marked the plug-in points not
  needed yet, so no loader is planned.

#### I3 Limits, budgets and capacity

- Rate limits (read, constants), budgets (to build: append over `budget_store.append`, versioned,
  warning then hard stop per owner decision 38), capacity (read).

#### I4 Secrets and credentials

- **Entity:** vault slots and `ops.credential_write`.
- **Belongs:** every slot: provider keys, relay password, connector keys, webhook secrets, object
  store key; held or not, when written, by whom, whether an environment variable outranks it; vault
  state (absent, sealed, reachable).
- **Actions:** write or replace (write-only form, never read back; exists for provider slots via
  `PUT /credentials`, to widen to the others).

#### I5 Storage, I6 Backup and recovery, I7 Version and updates

- Storage: buckets, retention, counts (exists). Backup: copies and last verified restore (exists),
  drill control (to build). Version: running commit, release, image, update available, the
  install facts from `/install` merged in (exists, read only; applying an update stays a host
  script).

### 2.4 Where each item on the owner's list ends up

| Owner's item | Decision | Ends up in |
| --- | --- | --- |
| Dashboard | kept | A1 |
| Organisations / Companies | **not applicable as tenancy.** One install is one company, with its own server and database. The honest equivalents: the company's identity and branding (I1 Settings) and its internal structure (B2 Departments and teams) | I1, B2 |
| Departments | kept, with teams | B2 |
| Users | renamed People, because service accounts are separate | B1, B6 |
| Roles and permissions | consolidated from three pages; permissions are granted on the person, not on the role | B3 (vocabulary), B1 (grants) |
| Agents | kept, as a container | C1 |
| Agent templates | kept | C2 |
| Skills | kept, with the tool catalogue | C3 |
| Connectors / Integrations | **split**: data sources are D1; conversation surfaces are E1 Channels; outbound events are E2 Webhooks | D1, E1, E2 |
| Knowledge / Documents / Data sources | **split**: documents are D2; data sources are D1 | D2, D1 |
| Workflows / Automations | kept as Automations; a "workflow" drawn step by step is an agent's procedure in the builder | C5, C1 |
| AI providers / Models | consolidated with Routing | C6 |
| Prompts / System configuration | **split**: an agent's instructions are an agent tab (the Prompts page becomes a filtered index there); house rules are shown there read-only; system configuration is Settings | C1, I1 |
| API configuration | **split**: machine callers are B6; keys and secrets are I4 | B6, I4 |
| Webhooks | kept; inbound verification moves to Channels | E2, E1 |
| Notifications | consolidated with Subscribers | E3 |
| Storage | kept | I5 |
| Usage / Credits / Limits | **split**: usage and spend are H1; limits and budgets are I3. **Credits are not applicable**: nobody sells this install credits; the equivalent is a money budget per company, department, person or agent | H1, I3 |
| Logs | consolidated with Errors | F4 |
| Audit logs | kept | G1 |
| System health | new module | F1 |
| Background jobs | kept | F3 |
| Settings | new module | I1 |
| Import / Export | kept; import is added per entity where it is imported | G3 |
| Backup / Recovery | kept | I6 |
| Version / Deployment | consolidated with This install | I7 |

### 2.5 Consolidations and moves from today's menu

| Today | Change | Why |
| --- | --- | --- |
| Errors, Logs | one module F4 | one question: what went wrong |
| Models and health, Routing | one module C6 | the chain is the model configuration |
| Notifications and email (Operate), Subscribers and notifications (Govern) | one module E3 | one subject in two groups |
| Usage and cost, Spend, Adoption | one module H1 | one report with three views |
| This install, Version and updates | one module I7 | install facts are version facts |
| Roles, Capabilities, Scopes | one module B3 | the vocabulary of access |
| Sessions, Sign-in links, Staff sources | one module B5 | how people arrive and stay signed in |
| Access review, Elevation requests | one module B4 | access decisions |
| Rate limits, Capacity | one module I3, with budgets | ceilings |
| Prompts | an index inside C1 | an instruction belongs to an agent |
| Memory (Govern), Learning | one module D3 | one store, two views |
| Connectors, Webhooks, Notifications, Routing under Operate | moved to Knowledge and data, Channels and notifications, Agents and AI | they are configuration, not operation |
| Agents, Skills, Templates, Prompts under Govern | moved to Agents and AI | governing agents is one job |
| Storage under Install | stays in Platform | the store is the server's |
| "Skills and templates" label on Skills | corrected to "Skills and tools" | templates have their own entry |

### 2.6 Administrative functions the owner did not list

| Function | Module | State |
| --- | --- | --- |
| Identity provider and sign-in settings | B5, I1 | read only in env and wizard; to build |
| Second factor policy, status and step-up | B5, shell | missing; W0.1, W0.2 |
| Sessions and session policy | B5 | end exists; policy shown |
| Sign-in links (binding a person's sign-in) | B1, B5 | exists |
| Staff source and directory sync | B5 | trial only; runner missing |
| Joiners, movers, leavers; adopting a leaver's agents and automations | B1 | domain only (`identity/lifecycle`) |
| Service accounts, API keys, automation credentials | B6, C5 | domain only |
| Capability packs | B3 | tables only |
| Role appointments with scope | B3 | missing (M1.3.2) |
| Access review, elevation (break glass) | B4 | exists |
| Access friction (denial patterns) | B4 | domain only |
| Approvals of suspended actions | C4 | faults (F3) |
| Publish approval by a second person | C4 | domain only (`builder/publish`) |
| Leashes, autonomy tiers, promotion evidence, circuit-breaker demotions | C1, C4 | domain only |
| Rehearsal (preview a run as a person, at shadow) | C1 | domain only |
| Agent availability versus ceiling | C1 | read (`reach_view`) |
| Template authoring, signing, sharing, upgrade offers | C2 | domain only |
| Provider checks and circuit breakers | C6 | exists |
| Channels (Lark, Slack, Teams, Telegram, WhatsApp, email, widget) | E1 | adapters only |
| Outbound delivery replay | E2 | missing |
| Quality canaries (permission canaries) | H3 | runs; findings not kept |
| Retention, legal holds, erasure | G2 | exists |
| Client handover | G3 | domain only |
| Release check and updates | I7 | read only |
| Rate limits, budgets, budget stops, capacity | I3 | read; budgets domain only |
| Feature switches | I2 | exists |
| Secrets and credentials, vault state | I4 | routes exist, no page |
| Installation settings | I1 | wizard only |
| Stop button | F5, header | domain only |
| Alerts and incidents | F1 | domain only |
| Side-effect resolution and dead letters | F2 | domain only |
| Field classification, fast-path rules, entity merges | D4 | dry-run review only |
| Knowledge stewardship (verify, review due, supersede, promote) | D2 | domain and table |
| Starter set (furnishing an empty install) | I1 (one action) and the installer plan | declared, never applied |
| Backup drills | I6 | missing |
| Trace destination (Langfuse) | I1 | settings exist, nothing exports |

---

## Part 3. The lifecycle matrix

**Codes.** **E** exists and works once W0 lands; **P** partial (note says what is missing); **M**
missing, to build; **N** not applicable (note says why). "Once W0 lands" matters: most E cells are
refused today by F1.

Columns: Lst list, Srch search, Filt filter, Sort, Page pagination, View detail, Crt create, Edit,
Arch archive or delete, Rest restore (named reinstate in code), En/D enable or disable, Dup
duplicate, Imp import, Exp export, Bulk, Val validation before write, Conf confirmation, Fb
feedback, Perm permission enforced, Aud audit history.

### 3.1 Home and People and access

| Module | Lst | Srch | Filt | Sort | Page | View | Crt | Edit | Arch | Rest | En/D | Dup | Imp | Exp | Bulk | Val | Conf | Fb | Perm | Aud |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 Dashboard | N | M | M | N | N | P | N | N | N | N | N | N | N | M | N | N | N | P | E | P |
| B1 People | P | M | M | M | M | E | M | N | M | M | M | N | M | M | M | E | E | P | E | P |
| B2 Departments and teams | P | P | M | M | M | P | M | M | M | M | N | N | M | M | N | E | E | P | E | P |
| B3 Roles and permissions | E | M | M | M | N | P | M | M | M | M | N | M | N | M | N | M | M | P | E | M |
| B4 Access reviews and elevation | P | P | P | M | M | P | E | N | N | N | N | N | N | M | M | E | E | P | E | E |
| B5 Sign-in, directory and sessions | P | P | P | P | M | P | E | M | E | M | N | N | M | N | M | E | E | P | E | E |
| B6 Service accounts and API keys | M | M | M | M | M | M | M | M | M | N | M | N | N | N | N | M | M | M | M | M |

**A P under Srch, Filt or Sort on B2, B4, B5, D2, D5, E2, E3 and the reports means narrowing in
the browser over one bounded page**, which those screens already say in words
(`governPeopleQuery.A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`) and `console/tests/long-lists.test.tsx`
records. It is not a search of everything the reader may see, and the server list contract (W1.3)
replaces it.

Notes:
- **A1.** List N: a dashboard is not a list. View P: shows the caller only; tiles to build. Filter
  M: the period and department axes the registry declares. Export M: the "Export" of SCREEN 2's
  unanswered questions. Feedback P: states written, KPIs absent. Audit P: activity feed to serve.
- **B1.** List P: limit only, no cursor. Create M: a person arrives from the identity provider and
  staff source; a manual person for installs with no source is to build. Edit N: name, department
  and employment are owned by the source; local edits would be overwritten by the next sync, so the
  screen names the source instead. Arch M: disable as a leaver. Dup N: people are not copied; "grant
  the same as" is a bulk grant. Import M: staff list apply. Bulk M: a grant route over a set. Feedback
  P: inline notices, no toasts. Audit P: grant entries carry zeroed reach hash and trace (routes skip
  `attributed_to`).
- **B2.** View P: tree exists, detail missing. Crt, Edit, Arch M: no writer for department, team,
  scope. En/D N: a department is live or retired. Dup N. Import M: from the staff source's
  organisation plan (`identity/organisation_sync`). Bulk N: placements are single confirmed acts
  until a route takes a set.
- **B3.** Lst E: roles. Crt M: packs and role appointments. Edit M: packs; roles themselves N
  (compiled, R3). Dup M: copy a pack. Imp N: vocabulary is product-declared. Val and Conf M: for the
  pack writes. Aud M: packs have no trigger yet.
- **B4.** Srch P: access review narrows by choice over one page. Crt E: an elevation request. Edit,
  Arch, Rest N: decisions are facts. Exp M: a certification report.
- **B5.** Srch P: sessions narrow by choice. Crt E: bind a sign-in. Edit M: identity provider and
  staff source values after setup. Arch E: end session, unlink. Rest M: re-link after unlink is a
  new bind today. Imp M: staff list. Bulk M: end all sessions of one person (a leaver) is one act on
  a set.
- **B6.** Everything M: no table. Rest N: a revoked key is deleted by design; issue a new one. Imp,
  Exp N: secrets are never exported.

### 3.2 Agents and AI

| Module | Lst | Srch | Filt | Sort | Page | View | Crt | Edit | Arch | Rest | En/D | Dup | Imp | Exp | Bulk | Val | Conf | Fb | Perm | Aud |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 Agents | P | M | M | M | M | P | M | P | M | N | M | M | M | M | N | P | P | P | E | P |
| C2 Agent templates | P | M | M | M | M | P | M | M | M | M | N | M | M | M | N | P | M | P | P | M |
| C3 Skills and tools | P | M | M | M | M | E | E | N | M | M | M | N | P | M | N | E | P | P | E | E |
| C4 Approvals and autonomy | P | M | M | M | M | P | N | N | N | N | N | N | N | N | N | E | P | P | E | P |
| C5 Automations | P | M | M | M | M | P | E | M | M | M | M | M | N | N | N | E | E | P | E | E |
| C6 Models and routing | E | N | M | N | N | P | M | P | M | M | E | N | N | M | N | E | P | P | P | E |

Notes:
- **C1.** List P: roster capped at 500, no search. View P: workspace has 7 tabs, 2 populated. Crt
  M: builder routes. Edit P: instructions only (feature-gated); everything else through drafts. Arch
  M: `lifecycle.archive`, terminal. Rest N: archived is terminal by design (`AgentState`); disabled
  is the reversible state. En/D M: `lifecycle.enable`, `disable`. Dup M: a draft from the effective
  manifest. Imp M: a manifest file through the leak scan. Exp M: the manifest document. Bulk N:
  agents change one at a time through the publish gate. Val P: server validators exist, no route.
  Conf P: automation install confirmed; publish confirmation to build. Aud P: instructions and skill
  assignment audited; publish, lifecycle and leash moves to build (`leash_change` has no emitter).
- **C2.** List P: 23 built-ins and published, cap 500. Crt M: author from an agent or from blank.
  Edit M: a new version. Arch M: withdraw a version (insert-only row). Rest M: undo a withdrawal.
  En/D N: a version is a fact; visibility and withdrawal are the controls. Dup M: `authoring.author`.
  Imp M: signed template document. Val P: manifest validators. Perm P: borrows the Skills screen's
  read. Aud M: `publish` action exists, no emitter for templates.
- **C3.** Crt E: upload or paste. Edit N: a skill is its bytes; a change is a new import and a
  version replacement. Arch M: retirement row. Rest M: reinstatement row. En/D M: retire and
  reinstate at library level, detach at agent level (Part 4.2). Dup N: identical bytes are one row
  by digest. Imp P: upload and paste only; repository and link to build. Conf P: review decision is
  one act; detach and retire confirmations to build.
- **C4.** List P: faults today (F3), and nothing produces a suspension. Crt, Edit, Arch N: an
  approval is raised by a run, decided once. Conf P: a decision is its own confirmation; promotions
  to build. Aud P: `approval` has no durable emitter (W0.3).
- **C5.** Crt E: install from gallery, lands paused. Edit M: schedule and guards (change rows). Arch
  M: remove (change row). Rest M: reinstall the same template. En/D M: resume and pause. Dup M:
  install the same template for another owner. Imp, Exp, Bulk N: automations come from the gallery.
- **C6.** Srch N: a chain is short and ordered. Sort N: tier and position order is the chain. Page
  N: bounded by tiers. View P: rung detail exists on the matrix; provider detail thin. Crt M: add a
  rung. Edit P: four fields. Arch M: retire a rung. Rest M. En/D E: provider switch and rung
  `enabled`. Exp M: routing configuration. Perm P: `read:routing_matrix` never granted (W0.4).

### 3.3 Knowledge and data, Channels and notifications

| Module | Lst | Srch | Filt | Sort | Page | View | Crt | Edit | Arch | Rest | En/D | Dup | Imp | Exp | Bulk | Val | Conf | Fb | Perm | Aud |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 Connectors | E | N | M | N | N | P | E | M | E | E | N | N | N | M | N | E | E | P | E | E |
| D2 Knowledge | P | P | P | P | M | M | M | M | M | M | N | N | M | M | M | M | M | P | E | M |
| D3 Learning and memory | P | M | M | M | M | P | N | M | E | N | N | N | N | M | N | E | E | P | E | E |
| D4 Fields and records | P | M | M | M | M | P | N | M | M | M | N | N | M | M | N | E | M | P | P | M |
| D5 Artifacts | P | P | P | P | M | M | N | N | N | N | N | N | N | P | N | N | N | P | E | M |
| E1 Channels | M | N | N | N | N | M | M | M | M | M | M | N | N | N | N | M | M | M | M | M |
| E2 Webhooks | E | P | P | M | M | P | E | P | E | M | P | N | N | N | N | E | E | P | E | E |
| E3 Notifications and email | E | N | P | N | N | P | N | E | N | N | E | N | N | N | N | E | E | P | E | P |

Notes:
- **D1.** Srch, Sort, Page N: at most one live row per source, a short list. View P: trust sentences
  exist; health always empty. Edit M: disconnect and connect in one transaction (Part 4.3). Arch E:
  disconnect. Rest E: connect again (a new row). En/D N: connected or not; a pause is a halt on the
  connector (F5). Dup N: one live row per source. Imp N: keys are typed, not imported. Exp M: the
  connection record without keys.
- **D2.** Filt P: grouping by department only. Everything that writes M: ingestion has no route.
  En/D N: an item's states are draft, published, superseded, archived. Dup N. Bulk M: re-verify many.
- **D3.** Crt N: memory forms from conversations. Edit M: a person's own memory edit. Arch E: undo
  (a correction row). Rest N: an undone learning is re-learned, not restored. Aud E: `memory` action.
- **D4.** Crt N: classifications come from code and connectors. Edit M: apply a reviewed proposal.
  Conf M: a second person applies. Perm P: `read:field_classification` never granted.
- **D5.** Crt, Edit N: produced by runs. Exp P: re-download re-checks the requester. Aud M:
  `read:audit.artifact` withheld; a publish entry exists for exports only.
- **E1.** Srch, Filt, Sort, Page N: seven surfaces. Dup, Imp, Exp, Bulk N.
- **E2.** Edit P: secret only; endpoint and kinds are a new registration. Rest M: switch back on.
  En/D P: switch off only. Srch, Filt, Sort, Page M: the list is short today and grows with
  subscribers.
- **E3.** Crt N: notices are product-declared. Arch, Rest N. Aud P: the test message has no audit
  entry by design.

### 3.4 Operations, Governance, Reports, Platform

| Module | Lst | Srch | Filt | Sort | Page | View | Crt | Edit | Arch | Rest | En/D | Dup | Imp | Exp | Bulk | Val | Conf | Fb | Perm | Aud |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1 System health | M | N | N | N | N | M | N | N | N | N | N | N | N | N | N | N | N | M | M | N |
| F2 Runs and queue | P | M | P | N | M | M | N | N | N | N | N | N | N | N | N | N | M | P | E | M |
| F3 Background jobs | E | N | N | N | N | P | N | N | N | N | E | N | N | N | N | E | P | P | E | E |
| F4 Logs and errors | E | P | E | N | E | P | N | N | N | N | N | N | N | M | N | E | N | P | E | N |
| F5 Stop | M | N | N | N | N | M | M | N | N | N | M | N | N | N | N | M | N | M | M | M |
| G1 Audit log | E | M | E | P | E | E | N | N | N | N | N | N | N | P | N | E | N | E | E | E |
| G2 Retention, holds, erasure | E | M | M | M | M | P | E | N | E | N | N | N | N | E | N | E | E | P | E | E |
| G3 Import and export | P | N | N | N | N | P | P | N | N | N | N | N | M | P | N | E | E | P | P | E |
| H1 to H4 Reports | E | P | P | P | P | P | N | N | N | N | N | N | N | M | N | P | N | P | E | N |
| I1 Settings | P | N | N | N | N | P | N | M | N | N | N | N | N | M | N | M | M | M | M | P |
| I2 Features and plugins | E | N | N | N | N | E | N | N | N | N | E | N | N | N | N | E | P | P | E | E |
| I3 Limits, budgets, capacity | P | N | M | N | N | P | M | M | N | N | N | N | N | M | N | M | M | P | E | M |
| I4 Secrets and credentials | M | N | N | N | N | M | P | P | N | N | N | N | N | N | N | E | M | M | E | E |
| I5 Storage | E | N | N | N | N | E | N | N | N | N | N | N | N | N | N | N | N | P | E | N |
| I6 Backup and recovery | E | N | N | N | N | E | M | N | N | N | N | N | N | N | N | N | M | P | E | M |
| I7 Version and updates | E | N | N | N | N | E | N | N | N | N | P | N | N | N | N | N | N | P | E | N |

Notes:
- **F1.** Nothing served beyond `/health/ready` outside the API prefix. Srch and the like N: a fixed
  set of services.
- **F2.** Filt P: running and waiting split by grant. Sort N: newest first is the meaning. Conf M:
  resolving an unknown side effect is irreversible.
- **F3.** En/D E: pause and resume. View P: last run only, no history page. Conf P: pause confirmed;
  run now is not destructive.
- **F4.** Srch P: event substring. Sort N: newest first is the meaning. Aud N: reading a log is not a
  change.
- **F5.** Everything M: not persisted, no route. Conf N on stop by owner decision 38 (unilateral);
  resume takes a reason, which is its confirmation.
- **G1.** Srch M: no free text over entry details, by design today. Sort P: newest or oldest. Exp P:
  never offered to the first administrator (F4).
- **G2.** Crt E: holds and erasure requests. Arch E: lift, withdraw. Rest N: a lifted hold is a new
  hold. Exp E: the export log.
- **G3.** Lst P: own exports only. Crt P: audit trail only. Imp M. Perm P: F4.
- **H.** Srch, Sort and Page P: Usage searches, sorts and pages its people in the browser. Filt P:
  window and dimension only. Page P also: adoption's limit. Exp M: SCREEN 2's export of
  unanswered questions. Val P: spend's reversed window is a plain 500 (F7).
- **I1.** List and View P: `/install` shows values. Edit M. Aud P: the `setting` trigger already
  records any `ops.setting` write.
- **I2.** Conf P: a switch is confirmed for features that stop something. Plugins: N across the
  board by owner decision 58.
- **I3.** Crt and Edit M: budgets (append-only versions). Arch N: a budget is superseded by a new
  version. Aud M: `ops.budget_version` has no trigger yet.
- **I4.** Crt P and Edit P: provider slots only, and no page. Arch N: a credential is overwritten,
  never deleted (vault policy grants no delete).
- **I6.** Crt M: record a drill. Conf M: starting a drill.
- **I7.** En/D P: the release check switch is environment-only.

---

## Part 4. Four designs against the real entities

Every design keeps one sentence true: `E_run(caller, agent) = E(caller) ∩ agent_ceiling`, computed
only by `EntitlementSet.intersect`. Nothing in the console computes a reach, and every preview calls
the real gate or is not shown.

### 4.1 Creating an agent, from a template and from scratch

**What the code already decides, and what connects it to nothing.**

| Step | Domain code | Missing |
| --- | --- | --- |
| Pick a template | `agents/catalogue.py` (23 manifests), `agents/template.TemplateManifest`, `SignedManifest`, `verify` | signed rows: nothing writes `agent.template_version`, and `brain.agents.install` needs a signing key |
| Start from scratch | `agents/template.blank_template`, `hand_built`, `agents/install.begin_hand_built` | route |
| Fill in the manifest | `builder/compose.Section` (seven), `builder/form` (one JSON Schema per section from `TemplateManifest.model_json_schema()`), `ManifestForm.tsx` | schema route (`form_document` unserved); page |
| Save as you go | `builder/drafts` (a save is a new revision; only the latest publishes; somebody else's draft does not exist) | table: `MemoryDraftStore` only |
| Draw a procedure | `builder/procedure`, `compose.assert_drawable`, `ProcedureCanvas.tsx` | route, page |
| Check | `drafts.validity`, `agents/authoring.scan` (company details in a document) | route |
| Rehearse | `builder/rehearse.rehearse` (real gate, world unplugged, SHADOW, as a named person whose reach must be theirs; no rows returned) | route; the model lane it needs is partial, and cassette replay (M20.3.2) is open |
| Publish | `builder/publish.decide` (a widened ceiling demotes to SHADOW and needs a second approver), `binding_collisions`, `record_publish` (paths, never values) | route; approval surface |
| Install and complete | `agents/template.install`, `materialise`, `agents/install.complete` (an incomplete install is disabled; an unbound connector pins SHADOW) | route |
| Enable, disable, archive, transfer | `agents/lifecycle` | routes |
| Upgrade | `agents/upgrade`, `agent.upgrade_decline` | routes |

**The flow.**

```
Agents > New agent
  ├─ From a template ─> Catalogue (search; filter by department, by "needs a connector
  │                     this install lacks", by installed)
  │                        └─> Template: what it carries, what it asks for, readiness
  │                            per skill and connector (approved, connected, missing),
  │                            versions  ─> Install as draft
  └─ From scratch ────> Blank manifest ─> draft
                                   │
Draft (every save is a revision; nothing here is live)
  1 Identity    name, summary, owner, department audience
  2 Behaviour   instructions (persona), placeholders, model tier
  3 Knowledge   scope predicate; connectors expected
  4 Skills      approved skills, pinned by digest
  5 Tools       tools chosen; capabilities DERIVED from the tools, never typed
  6 Leash       rung per target, maximum side effect (starts at SHADOW)
  7 Tests       golden set
                                   │
Check      validators per section, company-detail scan, what is missing to complete
Rehearse   as a named person, at SHADOW, through the real gate: tools reached and steps,
           never rows; detail follows the People screen's own grant
Publish    same or narrower ceiling: publishes; widened: SHADOW plus a second approver
           (C4), never the author
                                   │
Agent      enabled, SHADOW on every write until a rung is promoted with evidence
```

**Where each of the owner's fields lands.**

| Owner asked for | Where | Note |
| --- | --- | --- |
| Information | Identity: `identity.display_name`, `summary`; audience on `AgentAudience` | the slug is fixed at creation |
| Instructions and behaviour | Behaviour: `persona`, `placeholders` | house rules every agent opens with are product text, shown and not edited (`prompt_routes`) |
| Model and provider | Behaviour: `tier` (small, main, heavy) | **an agent chooses a tier, not a model.** Which provider answers a tier is the routing ladder shared by every agent (C6); a per-agent model would be a second routing system. The Overview shows the chain the tier walks. **Honest limit today:** nothing passes the tier to `RoutingRequest.requested_tier`, so the field is stored and not yet obeyed; the form says so until W3.1 wires it |
| Prompts | Behaviour, and the existing instruction override on an installed agent | one editor; the Prompts page becomes an index of it |
| Skills | Skills: `SkillRef` name and digest | only approved skills are offered (4.2) |
| Connectors and tools | Knowledge (`connectors`, a readiness declaration) and Tools (`authority.allowed_tools`, `required_tools`) | capabilities derived from tools (`compose.derive`); a typed list is intent, reported and not honoured |
| Knowledge sources | Knowledge: `authority.scope` | a predicate over rows, not a list of documents |
| Permissions | the ceiling: scope, capabilities, allowed tools, maximum side effect | a ceiling narrows a caller; it grants nothing (R5) |
| Test | Tests and Rehearse | honest limit: no route runs an agent and the answer lane calls no model. What can be offered truthfully now is `agents/install.rehearse_golden_set`: whether a run starts, what it reaches and at which rung, as two different people, with no judgement of the answer. The button is labelled for exactly that |
| Edit | a new draft from the current version, then publish | a published version is never edited in place |
| Duplicate | a draft from this agent's effective manifest, new slug, audience not copied | the publish gate applies as for a new agent |
| Enable and disable | `lifecycle.enable`, `disable` | archive is terminal |
| Version | template version pinned by the instance; a local edit is a recorded divergence (`FieldOwner`) | upgrade offers and declines exist |

**Template actions.**

| Action | Design |
| --- | --- |
| Browse, search, filter | `agent.template_version` plus built-ins, filtered by department, readiness, installed |
| Details | the manifest by section and a readiness block |
| Required and optional skills and connectors | skills required by digest; connectors expected and allowed to be absent (SCREEN 5); readiness per item |
| Intended permissions | the ceiling shown as **requested, not granted**, whole or as a lock by the reader's `read:capability` (`reach_view.CEILING_DISCLOSURE`) |
| Create an agent | `template.install` then `install.complete`, as a draft somebody finishes (placeholders, audience) |
| Customise, save, edit | overlay fields (`set_field`, `clear_field`); sealed paths (`guardrails.leash`, `guardrails.max_side_effect`, `identity.published_by`, `template_id`, `version`) shown locked with the reason |
| Duplicate | `authoring.author`, scanned for company details before it can publish |
| Enable and disable | **not a template lifecycle.** A version is an insert-only fact; the controls are visibility (`TemplateVisibility`) and withdrawing a version from the catalogue (an insert-only row, to build) |
| Version | publishing appends `version + 1`; installed agents see an upgrade offer; a decline is recorded |

**Seeding the catalogue.** The built-ins must become signed rows once per install (W0.5), signed
with an install signing key held in the vault, never touching a company-authored template. Without
it nothing can be installed. An install with no vault (the lite profile) has nowhere to keep a
signing key, so installing a template is unavailable there and the catalogue says so rather than
signing with a key kept somewhere weaker (`credentials.NO_VAULT_IS_NOT_A_REASON_TO_USE_A_TABLE`).

### 4.1a The agent profile page

**Why this section exists.** On 2026-09-17 the owner reviewed the shadcn/ui spike's agent page and
found it missed connectors and other key things. He sent AnyGen's agent page as the reference, to be
adapted and not copied. This section maps every element of that page onto this product's real
entities, routes and state, adds what AnyGen lacks and this product must show, and records the
rebuilt page. The mapping was measured against `e3e2ec9`, `origin/main` on 2026-09-17, which is 16
commits past the Part 0 code of record `273092a`. Where the two differ, the row says so; the
differences that matter here are agent automations with start and stop, memory formation code,
connector reading by the worker and paged lists. The AnyGen images were described in the owner's
brief and not read, for the reason Part 0 gives.

**The shape: two views of one agent, and the tabs beside them.** Today `AgentWorkspace.tsx` puts
the tab strip on the left and a Dashboard or Profile switch in a right-hand pane (`PANES`,
`FIRST_PANE = "dashboard"`). The reference makes that switch the page's first level, and so does
this design. `/agents/{id}` opens the Profile, `/agents/{id}/dashboard` the Dashboard, and each tab
`tab_strip` returns for the reader (permitted and populated, never a count) keeps its own address
under `/agents/{id}/{tab}`, reached from a Sections menu beside the switch. The property
`agent-workspace.test.tsx` holds, that switching views loses no tab state, is restated over the two
views in the same commit, and `FIRST_PANE` becomes `profile`.

**How to read the tables.** Routes are under `/api/v1`. "Workspace" means
`GET /agents/{agent_id}/workspace` (`WorkspaceView`), which admits a caller by the agent's audience
(`visible_agent_ids`) and gives one 404 for a missing agent and a hidden one. Status is **exists** (a
route serves it and it takes effect), **partial** (served in part, or served and not yet in effect),
**missing** (domain code or a column may exist, but no route) or **not offered** (the product has no
such thing). The last column says what a reader who may not see the element gets, which is always
what an agent without that element gets (R1, R2).

**The reference, element by element.**

| # | AnyGen element | This product's entity or field | Read today by | Changed by | Status | Permission | When the reader may not see it |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Dashboard and Profile switch, top left | two views of one agent: `AgentWorkspace` `PANES` | nothing of its own; the views draw the workspace | navigation only | exists as a right-hand pane; partial as the page's first level | the audience, to open the agent at all | the agent is absent: the 404 a missing agent gets |
| 2 | Avatar | initials of `AgentRecord.display_name`. There is no image field and none is proposed, because an uploaded image is a file an install must store and scan | workspace `agent.display_name` | never changed on its own | exists | audience | as row 1 |
| 3 | Agent name | `AgentRecord.display_name`; the slug is fixed at creation | workspace | a draft and the publish gate (W2.6) | exists to read; missing to change | audience; changing needs `admin:agent` over the agent's department (to build) | as row 1 |
| 4 | Settings cog | the Settings tab (`Tab.SETTINGS`, `read:agent`) and the lifecycle actions | workspace `tabs` (Settings is in `POPULATED_HERE`) | edit instructions: `POST /govern/prompts/{agent_id}` and `.../give-back` (`admin:agent_instructions`; editing, not giving back, needs the feature `prompt_editing`). Enable, disable, archive, transfer, duplicate, edit as a draft: none, because `agents.lifecycle` has no route (W2.6) | partial | the Settings read to see the menu; each item its own authority | no cog: a reader without the Settings tab has nothing to open, and a disabled cog would say there is something |
| 5 | "Add to (chat app) groups" | installing the agent into a shared conversation: `console/agent_tabs.install_to_group`, answered at the floor of everybody present (`channels/room.plan`) | none | none. No adapter declares `Feature.GROUP_INSTALL`, so `install_to_group` refuses on every surface, and no table stores a channel for an agent (E1, W4.1). Which groups one company's agent sits in is install data and never source (`docs/needs-rupash.md`) | missing | to build with E1: an authority over the channel binding. Installing into a room grants the room nothing (`INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM`) | until W4.1 a disabled control with its reason, the same for everybody; afterwards absent without the channel authority |
| 6 | "Credits used 379 >" | spend over a period: `HeadlineView` (`spend_minor`, `runs`, `basis`, a `range` of 30 days) from `ops.spend_actual` through `console/workspace.headline`. The link opens H1 Usage and cost (`GET /report/spend?dimension=agent`). "Credits" is not this product's word (2.4) | workspace `headline` | an agent budget: `ops/budget_store.append` exists with no route (W3.5) | partial. **Nothing writes `ops.spend_actual`** at either commit (`spend_store.record` has no caller), so every install reads 0.00 and 0 runs. The page says "not recorded yet" rather than drawing nought (`A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`), which needs a served statement that calls are not metered. No money response carries a currency (`INSTALL_CURRENCY` exists and `locale.currency()` has no caller), so the figure has no sign | everybody's runs with the budget screen's read held unrestricted (`basis_for`); otherwise the reader's own runs, labelled as theirs. The link needs `read:usage` | never withheld: the narrower basis is the reader's own figure, labelled. The link is absent without `read:usage` |
| 7 | "Skills 12" | the number of pinned skills sent (`WorkspaceView.skills`) | workspace | assigning, row 12 | partial: counted from what is sent, and no skill is read by a run (row 12) | the Settings read and the Skills screen read (`read:skill`) | no figure, rather than nought. A count of the pins sent is a count of what was shown |
| 8 | "Days on board 23" | days since `agent.created_at` (`AgentRow` has it through `TimestampMixin`); for an installed agent `template_instance.created_at` is the install. Labelled "Days since created", because an agent is not staff | none. `AgentRecord` has no creation field, `record_of` does not copy it, and `AgentHeaderView` sends none | never changed | missing on the wire; the column exists | audience. A date names nobody, which is why it can travel where the builder (`created_by`) cannot | as row 1 |
| 9 | Description paragraph | `identity.summary` of the effective manifest | workspace `agent.summary` | a draft and the publish gate (W2.6) | exists; null for an agent with no install that constructs | audience | no paragraph |
| 10 | "Adaptive learning" card with a switch | memory formation and the learning review: `brain.memory` (`tiers.Tier` session, automatic, promoted, gated; `formation`; `review`; `digest.undo`) and the Learning screen | `GET /govern/learning` (`read:learning`); `GET /govern/memory?subject=` (`read:memory`, by person) | undo: `POST /govern/learning/undo` (`admin:learning`). A per-agent switch: none | partial, and **the switch is not offered as drawn.** New at `e3e2ec9`, `memory/turn.py` and `StoredFormations.after_turn` form a person's memories from an answered turn, and nothing on a running install calls `after_turn` yet. `mem.persistent` and `mem.adaptive` are keyed by person with no agent column; only `mem.learning.agent_id` names an agent. No manifest field, feature or setting switches learning, per agent or for the install. A single on and off switch is the memory-poisoning path SCREEN 13 rejects, so the card shows the four tiers, what each may change, and a link to the review. A per-agent pause would be new (a field `after_turn` reads) and may only narrow | the tier text is product text for the audience; the review link needs `read:learning`, on the content plane and withheld from the first administrator by design | the card's product text still shows; the review link is absent |
| 11 | Capabilities: Connectors, round icons, "7+", "+" | the connectors the manifest declares, as `ConnectorRow`: `Presence.ATTACHED` (a tool from the source is in `allowed_tools`) or `REQUESTED` (named, no tool bound), narrowed to sources the reader could be told about (`reachable_sources`). `ICONS_ON_THE_ROW = 5`, and the overflow is counted over the reader's own rows. The install's own state (connected, and new at `e3e2ec9` last read and next read) is `ops.connector_connection` and `ops.connector_sync` | workspace `connectors` (`shown`, `overflow`); `GET /connectors` for connected and last read (`read:connector`) | "+": none. An agent's connectors change through its manifest, a draft and the publish gate (W2.6); `agents.install.bind_tool` runs only inside `install.complete`, which has no route. Connecting a source for the whole install is `POST /connectors` (`admin:connector` over that source), a different act on the Connectors screen | partial. The row exists. The "7+" list needs the rows past the strip, which the workspace does not send (to build). New at `e3e2ec9` the worker reads a connected source on its interval, and no question is answered from what it keeps (`WHAT_CONNECTING_A_SOURCE_STARTS`); only xero and hubspot can be connected from the console (`ops/connectable.py`) | the row: audience and `reachable_sources`. Connected and last read: `read:connector` | a source the reader cannot reach makes no row and is not in the overflow (`AN_OVERFLOW_COUNTS_WHAT_IS_OFF_THE_ROW_AND_NEVER_WHAT_IS_OUT_OF_REACH`). No row says "restricted", and none carries a health word (`AN_UNPROBED_CONNECTOR_IS_NOT_A_HEALTHY_ONE`) |
| 12 | Capabilities: Skills, pill chips, "6+" with a chevron, "+" | pinned skills (`SkillRef` name and digest) on the effective manifest, from `agent.skill_assignment` | workspace `skills` | "+": `POST /skills/{digest}/assignments` with `agent_id` in the body (the Skills screen read, `admin:skill` over a scope admitting the agent, the agent in the caller's audience, an approved digest). Removing a chip: none, detachment is W2.8 | partial. **An assigned skill has no effect at run time.** Nothing in the answer path reads an assignment: `offered_cards` and `body_of` have no caller, `SkillScriptTool` is never built, `build_registry` registers no skill, and the model lane new at `e3e2ec9` reads none. The page says so on the row and beside the Skills figure until W3.1. The served sentence 4.2 names, `A_SKILL_IS_ASSIGNED_AND_NOT_YET_READ_BY_A_RUN`, does not exist yet and is added with W2.8 | the Settings read and `read:skill` | no row and no figure. No chip reads "approved" (`A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`) |
| 13 | Capabilities: Channels, icons, "+" | the surfaces a run could be carried on: `offered_channels` at `E_run(caller, agent)` over the six adapters (email, lark, slack, teams, telegram, whatsapp), each with `rendering_profile` (card, attachment, plain) | workspace `channels` | "+": none. `agent_tabs.channel_rows` and `enable` are logic with no table; `ops.channel_binding` and the E1 screen are W4.1 | partial: offered, never "enabled" | audience; computed at the run's reach, so two readers can see different rows | a surface that may not carry what this reader's run could reach is absent, not greyed |
| 14 | "Availability" card: authorised users can find it and add it to groups | `AgentAudience`: `level` (`Visibility` personal, department, company), `owner_id` (the steward), `department` (one, and only at the department level). Discovery, never authority (`AUDIENCE_IS_NOT_AUTHORITY`) | workspace `agent.owner_id`; roster `department`; no route sends `level` | none. `agents.lifecycle.publish` (widening to company, `approve:agent.visibility`) and `transfer_ownership` exist with no route; any other audience change is a draft (W2.6) | partial | the card: audience. The level word: the Settings read (to add to the workspace). Changing: `admin:agent`; widening to company: `approve:agent.visibility` | the level is not shown; the steward and department still are, because the workspace and roster already tell every audience member |
| 15 | Availability: Users, chips, "+" | **nothing: there is no per-agent list of people.** At the personal level the audience is the steward alone, at department everybody placed in it, at company everybody. So "Users" honestly means the steward, and who else can find the agent is a level, not a list | steward: workspace `owner_id` | "+": not offered. A named allow-list would be a new `AgentAudience` shape, and it is what SCREEN 13's "Users added individually" draws with nothing behind it. If the owner wants one, it stays discovery and grants nothing | not offered (the steward exists) | audience | listing the people a department level reaches is not offered: it would hand a directory and a count of a department to a reader with no `read:grant` over it. That question belongs to the People tab (`Tab.PEOPLE`, `read:grant`), which no route populates |
| 16 | Availability: Departments, a chip with "x", "+" | `AgentAudience.department` | roster `department` | "x": none, because removing it changes the level (a draft, W2.6). "+": not offered, because an audience holds exactly one department; a second is a new audience shape, not a missing button (`AgentViewer` takes a set, the record does not) | partial | audience | absent for personal and company agents, whose record holds none |
| 17 | "Browser use" card with a switch | `brain/browsing` (M19): a planner that cannot read the page, a policy fixed for the run, credentials injected at the tool boundary and never given to the model, a rubric written before the run; a gVisor sandbox started by `launcher`; capabilities `read:browser_surface` and `write:browser_surface`; table `agent.browser_envelope` | none | none: no route, no feature switch and no field on an agent. Putting the browser capabilities in a ceiling would do nothing, because no handler is registered | missing: written and tested, never run ("the runner is specified and has never run"). Part 7 has no package for it, which is a WBS decision | when built, browser use is the agent's ceiling holding the browser tools, set through the publish gate, never a switch beside the ceiling | today a disabled switch with its reason, the same for everybody; when built, the card goes where the ceiling goes. Never a person's own signed-in session (SCREEN 13) |
| 18 | "Computer use" card with a switch | **nothing.** No module, table, route, capability or WBS leaf operates a desktop, its windows, keyboard or mouse. The only mentions are M19's title, "Browser and computer use", with no desktop leaf under it, and a docstring in `core/envelope.py` naming desktop as a surface | none | none | **not offered** | none | no switch, because a switch that does nothing is fake functionality. One sentence says the product does not offer it and why: an agent acts through tools that pass the gate, and a desktop operator acts with whatever the machine's session holds, which is SCREEN 13's objection to riding a person's session, made larger. Offering it is the owner's decision, not a missing button |

**What AnyGen lacks and this product shows.**

| Element | Entity or field | Read today by | Changed by | Status | Permission | Where it sits |
| --- | --- | --- | --- | --- | --- | --- |
| Leash, the autonomy rung | `gate/leash.Leash` entries (agent, target, scope, and a rung `AutonomyTier` shadow, assisted or autonomous) with `MISSING_ENTRY_RUNG = SHADOW`, sealed at `guardrails.leash`; `console/reach_view.leash_matrix` and `rung_history` | none: no route serves the leash | lowering: an insert-only `agent.leash_change` (W3.8). Raising: a publish with `may_raise` evidence, allowed by `may_move_rung` (`approve:action` over the entry's scope) | missing | the Settings read to see; `approve:action` to move | header chip (the widest rung, "leash up to"); Profile, "Model and autonomy" card, per target; Leash history tab (`rung_history`, breaker demotions) |
| The ceiling in plain words | `AgentAuthority`: `scope`, `capabilities` (with `records_implied_by`), `allowed_tools`, `required_tools`, `max_side_effect` (`SideEffect` none, draft, write, send, money) | roster `ceiling` (the scope predicate as JSON, for the Agents screen read); `reach_view.ceiling_block` has no route | a draft and the publish gate; a widened ceiling publishes at Shadow and waits for a second approver who is not the author (`builder/publish.decide`) | missing as words: nothing renders an agent's ceiling as sentences. The parts exist: `member/approvals.effect_sentence` for a side effect, `ops/starter.described_by_grammar` for a capability | `read:agent` for the card; capability names whole or as the lock by `read:capability` (`CEILING_DISCLOSURE`); "Preview as a person" through `reach_view.run_preview` (`PREVIEW_DISCLOSURE`, no route, W2.3) | Profile, "Permissions" card |
| Model tier | `AgentRecord.tier` (`Tier` small, main, heavy; `DEFAULT_TIER` main) and the chain the tier walks (`ops.routing_rung`) | tier: no route. Chain: `GET /routing/rungs` (`read:routing_matrix`) | tier: a draft (W2.6). Rungs: `PATCH /routing/rungs/{rung_id}` (`admin:routing_matrix`), shared by every agent | partial: **stored and not obeyed.** At `e3e2ec9` `gate/model_lane` builds a `RoutingRequest` with no `requested_tier` and says no agent is on that path (W3.1) | the Settings read; the chain `read:routing_matrix` | Profile, "Model and autonomy" card; the chain links to C6 |
| Owner and steward | one field. `AgentAudience.owner_id` is the steward, who answers for the agent now; `AgentRecord.created_by` is the builder, history that never moves. Neither is 6.1's data steward, a person appointed to grant data capabilities | workspace `agent.owner_id` (audience) and `agent.created_by` (the Settings read only, `THE_BUILDER_TRAVELS_WITH_THE_AUDIT_AND_THE_STEWARD_TRAVELS_WITH_THE_AGENT`) | transfer: `agents.lifecycle.transfer_ownership`, no route (W2.6); `identity/lifecycle.adopt` calls it for a leaver | partial | as read | header subline ("steward"); Profile, "Availability" card ("Steward", "Built by") |
| Template and version | `template_instance` (template id and version, content digest, overlay, field owners); `divergent_parts`; upgrade offers in `agents/upgrade` (`UpgradeBadge`) | workspace `agent.template_id` and `template_version`, and with the Settings read `composition` and `divergent` | accepting or declining an upgrade: none (W2.7); `agent.upgrade_decline` has no writer | partial | audience for the lineage; the Settings read for the composition | header subline ("from Queue triager v2"); Versions tab (`CompositionDiff.tsx`, the upgrade offer) |
| Enabled, disabled, archived | `AgentRecord.state`, derived from `disabled_at` and `archived_at`; archived is terminal and beats disabled | none: no route sends a state word | `agents.lifecycle.enable`, `disable`, `archive`, no route (W2.6) | missing on the wire | the Settings read. A member of the audience is not told a state, for `runnable_agent_ids`' reason: nobody is told why an agent they used yesterday is not chosen today | header state pill for a Settings reader; no pill otherwise |
| Approvals waiting | `gate.suspension`, which carries `agent_id` | `GET /approvals`, paged at `e3e2ec9`, with no agent filter; `ApprovalCardView` carries no agent id. Deciding is `POST /approvals/{suspension_id}/decision` | decided by a person, once | missing for this page: the queue answers 500 until W0.3 (`suspension_store_for` is handed no ledger), and nothing stores a suspension (`put_suspension` has no caller, W3.6) | the action's own capability over its row (`pending_for`); the first administrator holds no `approve:action` (R8) | Dashboard figure and list, counting only cards this reader could decide; absent, not nought, for a reader who could decide none |
| Automations | `agent.automation`, `gate.automation_owner`, and new at `e3e2ec9` `agent.automation_run` with a worker runner | `GET /agents/{agent_id}/automations` (new at `e3e2ec9`); the gallery `GET /agents/{agent_id}/automation-templates` (`read:queue`) | install `POST /agents/{agent_id}/automations` (`admin:automation`); start and stop `POST /agents/{agent_id}/automations/{automation_id}/start` and `.../stop` (`admin:automation`; stopping also the person it runs as) | exists at `e3e2ec9`; changing a schedule and removing are still to build | the Automations tab read (`read:queue`) | Dashboard "Automations" block; Automations tab |
| Recent runs | nothing per agent. `obs.request_telemetry.agent_version` is always null because `POST /answer` answers as the caller with no agent; `ops.model_attempt` names no agent; spend rows are never written; `agent.automation_run` covers automations only | none | none | missing: no route runs an agent and none lists an agent's runs | who asked and what: the Conversations tab read (`read:question`, content plane); cost on the budget basis | Dashboard "Recent runs"; Conversations tab |
| Instructions | the persona and its install overlay | `GET /govern/prompts` (the Settings read) | `POST /govern/prompts/{agent_id}` and `.../give-back` (`admin:agent_instructions`; editing needs the feature `prompt_editing`) | partial: the override is stored and served, and at `e3e2ec9` the answer lane uses its own `ANSWER_LANE_PERSONA`, so no run reads an agent's persona yet | as changed | Instructions tab; the Settings menu |
| History | ledger entries about this agent: `compose_change`, `instructions`, `leash_change` (no emitter), `approval` | `GET /audit?q={agent_id}` (`read:audit`; `q` is new at `e3e2ec9` and is a text search, not a subject filter); `GET /audit/history` is fixed to permission actions | written by the acts themselves | partial: no subject filter (G1), and publish, lifecycle and leash moves have no emitter | `read:audit` | History tab; absent without the grant |

Knowledge (the scope predicate, `read:document`), Memory (`GET /govern/memory` is by person, so no
route serves an agent's memory) and Artifacts (`GET /govern/artifacts`, with no agent filter, and
nothing keeps an artifact yet) stay tabs, as C1 lists them.

**Every "+" and "x" on the page, and every other control.**

| Control | Calls | On the page |
| --- | --- | --- |
| Dashboard and Profile switch; Sections menu | navigation | live |
| Settings cog: Open settings; Edit instructions | navigation; `POST /govern/prompts/{agent_id}` | live |
| Settings cog: Edit as a draft, Duplicate, Transfer stewardship, Enable or Disable, Archive | none | disabled items marked "not built yet", W2.6 |
| Add to a chat group | none | disabled, W4.1 |
| Spend figure's link | opens H1 over `GET /report/spend?dimension=agent` | live for `read:usage` |
| Connectors "+" | none (a manifest edit through a draft) | disabled, W2.6 |
| Connectors "N more" | none: needs the rows past the strip | opens the list, which says those rows are not sent yet |
| Skills "+" | `POST /skills/{digest}/assignments` | live, beside the sentence that a run does not read an assignment |
| Skills "N more" | none: every pin is already sent | live |
| Remove a skill ("x") | none | not drawn: detachment is W2.8, said in the list |
| Channels "+" | none | disabled, W4.1 |
| Availability: Change level; Transfer; remove the department ("x") | none | disabled, W2.6 |
| Availability: add a department ("+") | none | disabled, with the reason that an audience holds one department |
| Availability: add people ("+") | none | not drawn: not offered (row 15) |
| Learning: a per-agent pause | none | not drawn: would be new. The review link is live for `read:learning` |
| Browser use switch | none | disabled, with its reason (M19) |
| Computer use | none | no control: a sentence (row 18) |
| Permissions: Change the ceiling; Preview as a person | none | disabled, W2.6 and W2.3 |
| Model and autonomy: Change a rung | none | disabled, W3.8 |
| Dashboard: an automation's Start and Stop | `POST /agents/{agent_id}/automations/{automation_id}/start` and `.../stop` | live at `e3e2ec9` |
| Dashboard: Approvals link | opens C4 over `GET /approvals` | live; the queue faults until W0.3 |

**The rules the page keeps.** A control whose route does not exist is `aria-disabled`, drawn dashed,
does nothing when pressed, and its tooltip names what is missing and the package that adds it; the
rebuilt page carries ten, and pressing each was measured to change the address and open a dialog in
none of them. A thing the product does not offer is a sentence, never a disabled switch. A figure
nothing stores reads "not recorded yet", never nought. No number on the page counts what the reader
cannot see: the connector overflow is over the reader's own rows, the Skills figure over the pins
sent, approvals over the cards the reader could decide. Channels and connectors are computed at
`E_run`, never at the ceiling, and the page computes no reach of its own.

**What the API has to add for this page** (W2.6 unless named): `created_at` on `AgentHeaderView`;
for a Settings reader, the lifecycle state, the audience level, the tier, the leash entries and the
ceiling in words, with capability names under `CEILING_DISCLOSURE`; the connector rows past the
strip; a served statement that model calls are not metered (until W3.5), so the headline is not read
as nought; the sentence `A_SKILL_IS_ASSIGNED_AND_NOT_YET_READ_BY_A_RUN` (W2.8); an agent id on
approval cards, with a filter (W3.6); and a subject filter on `GET /audit` (G1).

**The rebuilt page.** Built on the base 5.7 records, in the spike under
`.scratch/ui-spike/app-radix/` (`src/pages/agents/AgentDetailPage.tsx`, `AgentProfile.tsx`,
`AgentDashboard.tsx`, `profile-parts.tsx`, `profile-data.ts`), which is outside version control.
Every figure, person and skill name is a marked example; the connector and channel names are the
product's own connector and adapter keys, drawn with generic bundled icons and no brand logos. The
screenshots were taken with headless Chrome by `.scratch/ui-spike/tools/shoot-profile.mjs`, with no
request leaving the local server, no console error, and a 375-pixel page measuring 375 wide.

| Screen | File under `.scratch/ui-spike/shots/` |
| --- | --- |
| Profile, desktop, light | `radix-agent-profile-desktop-light.png` |
| Profile, desktop, dark | `radix-agent-profile-desktop-dark.png` |
| Dashboard, desktop, light | `radix-agent-dashboard-desktop-light.png` |
| Profile, phone, 375 wide | `radix-agent-profile-phone-375.png` |
| Connectors overflow open | `radix-agent-capabilities-overflow-desktop.png` |

### 4.2 The skills model

**What a skill is.** A folder with `SKILL.md` and optional scripts, identified by the digest over
every field a reviewer read. Three insert-only tables (migration 0056): the bytes as they arrived,
a decision by somebody who did not import them, and an assignment of approved bytes to an agent.

**The finding that decides this module: a skill has no effect at run time today.** Assignment writes
a row and changes the manifest; nothing in the answer path reads it (`tools/skills.offered_cards`,
`body_of` and `EffectiveAgent.skill_pins` are called only by the Skills screen; `SkillScriptTool` is
never constructed; `build_registry` registers none). Until W3.1 lands, every assignment on the
screen carries a served sentence, `A_SKILL_IS_ASSIGNED_AND_NOT_YET_READ_BY_A_RUN`, in the shape of
`NOTHING_READS_A_CONNECTED_SOURCE_YET`.

**Lifecycle, with nothing updated or deleted.**

| State | Recorded as | Authority |
| --- | --- | --- |
| Imported | `agent.skill` | `admin:skill` |
| Approved or rejected | `agent.skill_review`, decider is not the importer (a key) | `admin:skill_review` |
| Assigned | `agent.skill_assignment`, key requires an approved decision | `admin:skill` over the agent |
| Replaced by a version | assignment with `replaces_digest` | as assigned |
| Detached (to build) | insert-only `agent.skill_detachment` naming the assignment; current assignments are those with no later detachment or replacement | as assigned |
| Retired (to build; the owner's "archive") | insert-only `agent.skill_retirement`; a retired digest cannot be newly assigned; live assignments are listed for detachment, never removed silently | `admin:skill` |
| Reinstated | a later insert-only reinstatement row | `admin:skill` |

**Enable and disable** are retire and reinstate at the library and detach at the agent. A third
switch would be a second answer to whether an agent uses a skill.

**Import.** Upload and paste work, and the table admits only `source_kind = 'upload'`. A repository
or link import (W4.4) widens that check and gives `brain.tools.fetch` a network egress rule; until
then the screen says why. A skill with scripts is refused at the door because the digest covers a
script's name and not its bytes; the fix is to digest the bytes first.

**Test.** A skill is tested through an agent that holds it: rehearse at SHADOW as a named person. A
standalone skill runner would be a second runtime with no gate in front of it
(`compose.A_CODE_NODE_IS_A_SECOND_RUNTIME_WITH_NO_GATE_IN_FRONT_OF_IT`).

**Which agents use it.** Current assignments only (not history), narrowed to agents the reader may
see, paged by cursor, no count beyond the page.

**Dependencies and validation.** A skill declares tools (`agent.skill.tools`). Before an assignment
is written, each tool is checked against the agent's `allowed_tools`, and a tool outside the ceiling
is shown as **requested, not in this agent's ceiling** (SCREEN 13's Xero row). The check does not
widen the ceiling; widening is a manifest edit through the publish gate.

### 4.3 The connectors model: available, connected, reading

| Layer | Source of truth | Meaning |
| --- | --- | --- |
| Available | `ops/connectable.py` (total over `brain.connectors`: each manifest builder is connectable or carries its `NOT_FROM_THE_CONSOLE` reason) | what this release could read: xero and hubspot from the console; freshdesk, google_drive, laravel, lark_base, lark_wiki need a visibility rule, a department declaration or a key file |
| Connected | `ops.connector_connection` (one live row per source; disconnect marks the row; reconnect is a new row; `digest` pins the manifest agreed to) | what this install agreed to read, with a key written once to `connector_keys/<source>` |
| Reading | a runner that syncs, projects or probes | **does not exist** (`NOTHING_READS_A_CONNECTED_SOURCE_YET`), and no vault role may read a connector key |

The screen never merges the three. A connected source that nothing reads says exactly that and is
never drawn "healthy".

| Action | Design |
| --- | --- |
| List available | each source: what it reads, access mode in words (`console/connector_trust`), the key it asks for, verified ceiling or "not measured" |
| List connected | who, when, pinned digest, and "what this source declares has changed since you agreed" when today's manifest digest differs |
| Details | trust sentences, credential held and when written (never the value), ceiling, agents whose manifest names it, skills whose tools come from it |
| Connect | exists (settings validated by the connection class's own refusal) |
| Test connection | to build: one probe through the connector's client under its throttle, recorded in a probe table, never returning business rows; needs a vault role that may read the key (W3.2) |
| Edit configuration | disconnect and connect in one transaction, because the settings are what the digest was pinned over; an in-place edit would change what was agreed to without agreement |
| Replace key | a credential write to `connector_keys/<source>` (the policy already allows update); to build as a slot on I4 and a button here |
| Reconnect | connect after disconnect: a new row, history kept |
| Disconnect | exists, confirmed; the key stays in the vault because policy grants no delete, which the confirmation says |
| Status and health | from the reading layer once it exists; health functions exist for five connectors and are never called |
| Permissions | `read:connector` to list; `admin:connector` over the source to change |
| Secrets | never displayed: held, since when, written by whom |

### 4.4 Who can access what, and why

Three questions with three different answers, and the console never merges them:

1. **What does this person hold?** Grants: capability, scope, who granted it, when, why, when it
   lapses; packs expanded (`identity/packs.expand`); elevations with their lapse. Additive only;
   no deny row exists and none is drawn.
2. **What may they use from here, now?** `gate/admission.admit`: holdings narrowed by channel and by
   the strength of this sign-in. `admission.would_lose` lists what is held and unusable here.
3. **What does a run through this agent reach for them?** `E(caller) ∩ agent_ceiling`, shown only
   through `console/reach_view.run_preview`, which calls the real gate.

**The Access tab on a person's page.**

| Block | Content | Guard |
| --- | --- | --- |
| Holds | every grant grouped by origin: granted by a person, from a pack, from an elevation (with lapse), from the directory | `read:grant` over the person's department; capability names only with the Capabilities screen's grant (`govern.people`) |
| Roles | platform roles held and the scope bounding each, with the sentence that a role grants nothing | role holders (to build) |
| Usable from the console | for the person themselves: which of their verbs need a second factor in this sign-in. For an administrator viewing somebody else: the verbs the console carries and the assurance each needs, never a list derived from that person's grants | `would_lose` for self only |
| Placements | departments, teams, lead appointments | `read:grant` |
| Through an agent | pick an agent: its ceiling (whole or a lock) beside the preview of this person's run | `CEILING_DISCLOSURE` (`read:capability`), `PREVIEW_DISCLOSURE` (the People screen's read) |
| History | grant, revoke, elevation, certification and session entries about this person | `read:audit.grant`, `.principal`, `.session` |

**The reverse question, "who can reach X and why", is asked of a capability and a scope, never of a
record.** On a capability's page (B3): every holder, the scope of each grant and its origin. Asking
it of a record ("who can see this invoice") is not offered, because the answer confirms the record
exists to anybody allowed to ask about the capability, and it is exactly the leak R1 forbids. The
capability question gives an administrator the same governing information.

**What this model never shows.** A count of withheld rows or screens, "3 of 47", a department in a
filter the reader cannot reach (`screens.offerable`), the reason a record was refused, a deny.

---

## Part 5. The interface direction

### 5.1 The shell

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ [logo] Company Brain  │  Search (Ctrl K)  ····················  [Stop] [theme] [you ▾] │
├───────────────┬───────────────────────────────────────────────────────────────┤
│ USE           │ People and access › People › Wei Ling Tan                      │
│  Ask          │ ┌───────────────────────────────────────────────────────────┐ │
│  My workspace │ │ Wei Ling Tan   Member · Maintenance      [Grant] [More ▾] │ │
│ HOME          │ │ Overview  Access  Grants  Sign-ins  Placements  History   │ │
│  Dashboard    │ ├───────────────────────────────────────────────────────────┤ │
│ PEOPLE ▾      │ │  tab content: cards, tables, facts                         │ │
│  People  ●    │ │                                                            │ │
│  Departments  │ └───────────────────────────────────────────────────────────┘ │
│  ...          │                                          toast region (polite) │
└───────────────┴───────────────────────────────────────────────────────────────┘
```

- **Sidebar:** nine collapsible groups from the API's navigation answer; the active item marked as
  SCREEN 1 draws it (a wash and an inset rail); no count badges (a number in the frame is where a
  count of the unopenable leaks, `Shell.tsx`'s own argument), with counts on the Dashboard's "Needs
  you" instead, each figure governed by `operate.tile`. **At phone width the menu stays visible**:
  `tests/phone-width.test.tsx` and `approvals-phone.test.tsx` hold that `nav.shell__nav` precedes
  `main` and is never hidden, which is the right property (a hidden menu with a broken toggle is no
  navigation at all). The design of record's `display:none` below 900px is the part of
  `screens.html` not to follow. With forty entries a scrolling strip stops being usable, so W1.1
  replaces it with a visible "Menu" button as the first control after the skip link that opens every
  group, and changes those two tests in the same commit to hold the new property (the button is
  visible, precedes `main`, reaches every entry, and returns focus), never by deleting them.
- **Header:** global search, the Stop button for `admin:halt` holders, theme, the signed-in person
  and their sign-in strength with "Sign in again with your authenticator" when it is not strong.
- **Global search:** menu entries always; entities (people, agents, skills, connectors, templates)
  from a new `GET /api/v1/console/search` that asks each module's own read, returns no totals and
  returns the same empty answer for "no match" and "not permitted".
- **Breadcrumbs:** group, module, entity, tab. From the route table, not typed per page.

### 5.2 Page patterns

| Pattern | Use for | Built from |
| --- | --- | --- |
| List page | every module list | `DataTable` (TanStack, no client paging) in a toolbar with search, filters, sort and a cursor pager bound to the server list contract (W1.3) |
| Detail page with tabs | an entity with several aspects (person, agent, connector, skill, template) | a new `DetailPage` with header facts (`Facts`), actions menu, tabs as child routes so each tab has an address |
| Drawer | a short create or edit that keeps the list in view (grant, register webhook, connect a source) | shadcn/ui `Sheet` (a Radix dialog) with focus returned to the opener |
| In-page confirmation | a destructive act on one row | the existing `ConfirmAction` (in place, focus to the safe choice, Escape cancels), kept |
| Wizard | agent creation, template install, first run | the seven builder sections as steps with a persistent draft, `ManifestForm` per step |
| Empty, loading, unreachable, failed | every page | `FailureNotice`, `Notice`, and the four sentences `tests/screen-states.test.tsx` already holds, plus an empty state that says what would put a row here and who may |
| Toast | the result of a write, beside the inline result | a new `ToastRegion` (`aria-live="polite"`, never the only place a failure is reported, never carrying a value that is withheld elsewhere) |
| Bulk bar | only where a route takes a set | selection on the table, a bar with the act, one confirmation listing what will change; absent where writes are one row at a time (`long-lists.test.tsx`'s `ONE_ROW_AT_A_TIME`) |
| Explanation panel | "cannot do this yet" and "why you cannot do this here" | the served sentence constants rendered by one `Explained` component |

### 5.3 Why it looks out of date, measured

- **The palette is not the design's.** `tokens.css` is cool grey with a `#1a56db` blue accent;
  `screens.html` is warm neutrals with state colours held apart from the brand.
- **One button style.** `.button` has no primary, quiet or danger variant.
- **No KPI tiles, no "Needs you" list, no activity feed, no cards with headed sections**, all of
  which SCREEN 1 draws; the Overview is a single "You" card.
- **Breadcrumbs are plain text on 19 pages** and absent on the rest; filters are native selects
  inside forms rather than a filter row.
- **Classes used in markup with no CSS rule:** `roster` (23 uses), `confirm`, `confirm__question`,
  `hint`, `form__problems`, `agent-template-carries`.
- **About 19 pages carry a private copy of a failure component** instead of `ui/FailureNotice`.
- **Fifty flat-ish menu entries** in five groups, with configuration filed under Operate.

### 5.4 The tests a redesign keeps, or changes on purpose

These hold rules rather than habits, so a redesign keeps them green or changes them in the same
commit with the replacement property written down:

| Test or guard | What it holds that the redesign must respect |
| --- | --- |
| `scripts/check-boundaries.mjs` | no token parsing, no role checks in the browser, no `fetch` outside the client, `localStorage` only for the theme (so global search keeps no recent-search history), no `type="password"`, no positive `tabIndex`, no click handler on a non-control |
| `bundle-split.test.ts` | `@tanstack/react-table`, `@rjsf/*`, `@xyflow/react` unreachable statically from `main.tsx`: **every module page that mounts `DataTable` is a lazy route**, and the form libraries the template brings (`react-hook-form`, `zod`) are added to the same check |
| `destructive-confirmed.test.ts` | a destructive write is reachable only through an element literally named `ConfirmAction`: a drawer that removes something still confirms through it |
| `validated-before-write.test.tsx` | a fixed table of forms per writing file: each new form is added to it |
| `long-lists.test.tsx` | the `MISSING` table must match the page exactly: each server search, filter, sort or pager that lands removes its entry |
| `screen-states*.test.tsx` | four distinct sentences per registered address; every new route needs a page case |
| `phone-width`, `approvals-phone` | the menu is never hidden at phone width (see 5.1 for the planned change); touch targets at least 44px; nothing wider than 320px |
| `shell-navigation`, `department-console`, `test_console_design.py` | menu rows as `{ to, label }` literals under group headings; the first three groups are Operate, Govern, Report today, so W1.1 changes the design of record and this test together |
| `theme.test.ts`, `status-primitives`, `lock` | no colour literal outside `tokens.css`; one `.badge` and `.chip` selector shape; the lock is one `span.lock` reading "Restricted" with no child icon, so the design's padlock glyph is not drawn and only its colours are adopted |
| `api-errors.test.tsx` | a `Notice` is `role="status"` and `class="notice"` with no severity variants, so a toast is a separate region and never a coloured notice |
| `tests/unit/test_locale.py` | 4.5:1 contrast for every text and tone pair in both themes, and equal colour counts light and dark |

### 5.5 What to keep, what to add

**Keep:** `api/client.ts` and `api/errors.ts` (one client, failures as values, no interpretation of
a 404); `useResource`, `useServerPage`, `paging.ts`; `DataTable`; `ConfirmAction`; `SchemaForm` and
`formSchema.ts` (the lock replaces a withheld field whole); `ManifestForm`, `ProcedureCanvas`,
`GraphCanvas`, `TraceGraph` (mount them); `AgentWorkspace`, `AgentHeader`, `AgentAssembly`,
`CompositionDiff`, `AutomationGallery`, `ConnectSource`, `StaffListCheck`, `Facts`, `cells`; `ui/`
(`Badge`, `Chip`, `Status`, `Lock`, `Notice`, `FailureNotice`, `tone`); the theme's three states;
`scripts/check-boundaries.mjs`; every test that holds a rule (screen states, destructive confirmed,
validated before write, long lists, bundle split, keyboard access, phone width, console audit).

**Add:** `layout/Sidebar`, `layout/HeaderBar`, `layout/Breadcrumbs`, `layout/CommandSearch`,
`components/ListPage`, `components/ListToolbar` (search, filters from `offerable`, sort),
`components/DetailPage`, `components/Tabs`, `components/Drawer`, `components/ToastRegion`,
`components/EmptyState`, `components/Explained`, `components/KpiStrip` and `components/Card`
(SCREEN 1's `.kpis` and `.card`), `components/BulkBar`, `components/SecretField` (write-only, never
prefilled, never echoed, cleared from state as soon as the request leaves; written once from the
pattern `ConnectSource.tsx`, `Notifications.tsx` and `Webhooks.tsx` each repeat today:
`type="text"`, `autoComplete="off"`, `spellCheck={false}`, because `check-boundaries.mjs` refuses a
password input).

### 5.6 The theme: the design of record, with the brand read from the install

`docs/screens.html` is the design of record and its structure becomes the product's tokens:
warm neutrals (`--ground`, `--panel`, `--sunk`, `--line`, `--ink`, `--body`, `--dim`, `--faint`),
state colours held apart from the brand (`--ok`, `--warn`, `--crit` with washes), the lock's own
colour (`--lock`, `--lock-w`), IBM Plex Sans for the interface and IBM Plex Mono for figures, and
the dark values twice as `tokens.css` already argues.

**The Verz orange is Verz's install configuration, not the product's.** `CLAUDE.md`: no company's
details go into the source, and branding is configuration read in one place. The accent is
`INSTALL_ACCENT_COLOUR` (served in the console's runtime configuration), and the rules
`screens.html` states for Verz orange become rules over any accent: used as a fill carrying dark or
light text chosen by measured contrast, darkened when used as text on the light ground until it
passes 4.5:1, never used to encode state. Verz sets `#F47936` on its install and sees the design it
approved; another company sees its own colour with the same structure. The fonts are bundled in the
image under their open font licence rather than fetched from a third party at page load, because an
install may have no route to one (`screens.html` names IBM Plex and never loads it, so the design as
drawn has only ever been seen in system fonts).

**Contrast has to be computed for an accent nobody chose in advance.** `tests/unit/test_locale.py`
checks the fixed tokens at 4.5:1; a runtime accent cannot be checked that way. So the derivation
(text colour on the accent fill, and the darkened accent used as text) is one tested function served
with the runtime configuration, and its test runs it over a pale, a mid and a dark accent in both
themes. The design's own figures are the worked example: `#F47936` as text on white fails and is
darkened to `#B75315`, which passes.

### 5.7 A component library: shadcn/ui on Radix, decided by the owner on 2026-09-17

**Decision (owner, 2026-09-17): shadcn/ui on its Radix base, with Tailwind CSS v4, is the console's
component and template layer, adopted page by page.** It replaces this section's earlier
recommendation, React Aria Components as unstyled primitives with no design system. The owner asked
for a modern, enterprise-grade interface built from pre-made templates with the Verz palette in
mind; a comparison of nine candidates and a working spike of the two strongest followed. Both were
built under `.scratch/` (`ui_template_choice.md`, `ui-spike/`), which is outside version control,
so the reasons and risks that decide the choice are recorded here rather than pointed at.

**What is adopted, and how.** shadcn/ui's components and blocks, and its data table on TanStack
Table v9, copied into `console/` rather than installed as a package. satnaing/shadcn-admin (MIT) is
a reference for the patterns it adds (bulk action bar, settings layout, error pages, command menu)
and is not adopted as an application, because its router, table version and authentication are not
this console's. The design of record's tokens are mapped onto shadcn's CSS variables, Tailwind's
default palette is removed so a class can only name a token, and the accent stays install
configuration (5.6). The existing stylesheets sit in a `legacy` cascade layer, so an old page keeps
its look and a new component is not overridden by its element selectors; a page leaves that layer
when it moves with its module package in wave 2. There is no big-bang reskin, and no purchase: every
part is MIT, ISC, Apache-2.0 or OFL-1.1.

**The three reasons.**

1. **It is the largest pool of pre-made admin material that fits the console's pins as they stand.**
   The spike built a list page, a detail page and a validated create sheet on React 19.1.0, Vite
   6.4.3, react-router-dom 6.30.6 and TanStack Table 9.2.4 without changing one of them, and the set
   ships a sidebar, command palette, breadcrumbs, sheet, alert dialog, toasts, tabs and empty states.
2. **Theming is CSS variables throughout**, so the design's palette and a runtime accent work without
   forking a component. In the spike every colour on screen came from the tokens, one build drew
   the Verz orange from install configuration and a teal from another, and the generated components
   held three colour literals, all one overlay, which were replaced.
3. **The code is copied in, so the console's rules are enforced inside it.** The spike removed a
   cookie write, fixed a checkbox that drew a tick for "some selected", stripped every total from the
   data table (R2) and added focus return to a dialog opened from state, each in a few lines of its
   own copy. A packaged design system would have needed a wrapper or a fork for each.

| Option | Verdict | Why |
| --- | --- | --- |
| **shadcn/ui, Radix base, Tailwind v4** | **adopted** | the three reasons above; `check-boundaries.mjs` ran clean over the spike and no request left the local server |
| shadcn/ui, React Aria base | the fallback base | the same components, but few pre-made templates paste into it, it measured heavier (Agents route 103.80 kB gzipped against 73.49 kB), and its grid rows take focus, which `keyboard-access.test.tsx` refuses as written. Its locale-aware date fields are its real advantage, and one such control can sit beside the Radix base where a module needs it |
| React Aria Components with no template (this section's earlier recommendation) | superseded | unstyled primitives answer accessibility and leave every page to be designed by hand, which is the opposite of what the owner asked for |
| MUI, Ant Design, Mantine | rejected | each has its own theme engine or runtime styling that fights `tokens.css` and the lock rule; Ant Design Pro builds with umi rather than Vite; no maintained Vite admin template for Mantine |
| TailAdmin, Refine, Tailwind Plus Catalyst | rejected | TailAdmin hard-codes colours and hand-rolls dialogs with no focus management; Refine sends telemetry by default and replaces the data layer the console keeps; Catalyst's licence does not plainly allow a product many companies install and own, so it is not bought without Tailwind Labs' written answer |

**The risks, and what each costs.**

- **The four jsdom layout tests move with the first restyled page.** `phone-width.test.tsx`,
  `approvals-phone.test.tsx`, `status-primitives.test.tsx` and the stylesheet half of
  `theme.test.ts` read the console's own stylesheets, and Tailwind utilities are not in a stylesheet
  they can see, so a page styled by utility classes would pass or fail them for reasons unrelated to
  how it renders. In the commit that restyles the first page they are re-pointed at CSS compiled by
  Tailwind for the rendered class names, or their layout claims move to the W1.6 browser harness.
  Done later, the console loses its phone-width and colour guarantees silently.
- **A second styling vocabulary beside the tokens**, which was this section's objection to shadcn.
  The tokens stay the only values; the cost is that a class naming no token renders no colour and
  fails silently, so a colour-class check joins `check-boundaries.mjs`.
- **The first load gets heavier**: about 80 kB gzipped over React and the router, plus about 25 kB of
  CSS, before the command palette and the toaster are made lazy.
- **Copied code is ours to maintain.** An upstream fix arrives by diffing, not by upgrading, and each
  local change (the cookie, focus return, the indeterminate checkbox) is re-applied by hand.
  `shadcn eject` runs before the dependency list is committed, so the CLI is not a build dependency.
- **Radix moves more slowly than React Aria or Base UI.** shadcn/ui ships the same components on all
  three, so a later change of base is component by component rather than a redesign, but the React
  Aria base has a different component API.
- **The Content-Security-Policy keeps `style-src 'unsafe-inline'`**, because the toaster and the scroll
  lock inject style elements, or moves to nonces.

**Rules carried across unchanged.** `check-boundaries.mjs` runs over every copied component and gains
a rule refusing `document.cookie`; `ConfirmAction` wraps the alert dialog, with focus starting on the
safe choice and returning to the opener; the data table registers no client row model and prints no
total; the lock stays the one `span.lock`, restyled from the tokens; every page mounting the table
stays a lazy route. The agent profile page in 4.1a was rebuilt on this base as its first worked page.

### 5.8 What to check against the AnyGen screenshots

Once the 14 images are copied under `brain/docs/reference/anygen/`, compare and adapt (never copy):
the template gallery card (what facts sit on a card before opening it); the agent creation stepper
(section order and where "test" sits); the agent page's capability block (how connectors, skills and
channels are added and removed in place); connector cards (connected versus available, how status is
shown); how cost appears on an agent. The design of record already rejects three AnyGen behaviours
and this console keeps those rejections: a single on/off adaptive learning toggle, no leash, and a
browser operator riding the user's own session.

---

## Part 6. Product rules that bound the owner's wishes

| # | Rule | Where it is | What it means for the console |
| --- | --- | --- | --- |
| R1 | DENIED and ABSENT are indistinguishable | `CLAUDE.md`; `app.handle_brain_error` | a refusal never says "no permission"; filters, search and dropdowns never name what the reader cannot reach. **Allowed:** telling a person what their own sign-in cannot do, and announcing a halt (`ops/halt.A_HALT_DISCLOSES_NOTHING_ABOUT_WHAT_ANYBODY_MAY_SEE`) |
| R2 | No count of hidden items | `CLAUDE.md`; `console/paging.A_PAGE_NEVER_CARRIES_A_COUNT` | lists page by cursor with no totals; the Dashboard shows a figure only to a reader who could open what it counts |
| R3 | Entitlements are additive; no role implies a capability | `CLAUDE.md`; `identity/roles.py` | no deny rules, no "remove this capability from a role", no role permission editor; revocation retires a grant; a pack's capability cannot be removed singly |
| R4 | Nothing hard-deletes where retirement applies | `db.SoftDeleteMixin`; migration grants | every "delete" in the interface is retire, end, disconnect, switch off, withdraw, detach or supersede, and says which; hard deletes only where designed (API key revocation, log trimming, erasure) |
| R5 | An agent is a lens, never a principal | `CLAUDE.md` | nothing grants an agent a permission; a template's permissions are requests; a ceiling only narrows |
| R6 | No company's details in the source | `CLAUDE.md` | the Verz palette is install configuration; no seed carries an install's rows |
| R7 | Screens about the installation are not offered at department scope | `console/screens.py` | the Platform group is company console only |
| R8 | Approving an agent's action is not an administrator's by default | `first_administrator` withholds `approve:action` | Approvals is for approvers a department appoints; the administrator appoints them |
| R9 | `approve` and `admin` need the console channel and a second factor | `gate/admission.py` | W0.1 makes that achievable rather than weakening it; the API channel never carries either |
| R10 | No function or class under `src/brain` is named with "restore" except `recovery.last_verified_restore` | `CLAUDE.md`, `tests/unit/test_installation.py` | the un-archive action is `reinstate` in code; the interface may still say "Restore" only for backups |
| R11 | A new feature ships switched off | `ops/features.py` | a control behind a switch links to Features when off, never a bare refusal |
| R12 | A filter dropdown is a disclosure | `screens.offerable` | filter options come from the reader's reach, not from a table |
| R13 | A halt is unilateral and has no expiry; resuming takes a reason | owner decision 38; `ops/halt.py` | no confirmation on Stop; a reason field on Resume |
| R14 | Budgets warn and then stop until the next period | owner decision 38; `ops/budget_stop.py` | the budget screen shows stops in force and when each ends |
| R15 | The nine plug-in points are not needed yet | owner decision 58 | Plugins is a read-only statement |
| R16 | Single tenant | `CLAUDE.md` | no organisation switcher; company settings instead |
| R17 | A credential is written once and never read back | `ops/credentials.py` | write-only fields; no reveal, no copy |
| R18 | WBS ids are positional | `CLAUDE.md` | new console work is appended as M27.9 onward and new leaves at the end of a group, never inserted |
| R19 | Nobody grants a capability they do not hold | `console/scoped_authority.may_grant` (M33.2.2.2) | a grant form offers only capabilities the granter holds over the scope; see 6.1 for where the first data capability comes from |

### 6.1 A decision only the owner can make: where the first data capability comes from

**The finding.** `may_grant` requires a granter to hold both `approve:grant` and the capability
itself over the scope. The first administrator is granted every `admin:` capability and no data or
content capability, on purpose (`AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA`). Elevation
approval asks `may_grant` too. The only other grant writers are the appointment, sign-in binding
(a person's own workspace) and the staff sync's department-head audit reads, whose runner does not
exist. So on a fresh install **no path, console or otherwise, can ever give anybody `read:client.*`,
`read:console.content` or any capability a connected source declares.** The rule is right, and the
bootstrap is missing.

**Options.**

| Option | What it does | Cost |
| --- | --- | --- |
| A. A data steward named at first run | the wizard names a second role-holder (may be the same person only if the installer says so explicitly), granted `approve:grant` and the content plane over everything; when a source is connected, the capabilities its manifest declares are granted to the steward over everything by the connect store, in the same transaction, audited | one wizard step and one store change; keeps "the administrator reads no data" true; concentrates data reach in a named, audited person |
| B. Grants from directory roles | the staff sync grants a department's starter pack to whoever the directory names as its department admin | needs the `directory_sync` runner and a pack per department; a spreadsheet source cannot assert roles, so installs without a directory have no path |
| C. Relax `may_grant` for `approve:grant` over everything | a company-wide granter may grant anything declared | breaks M33.2.2.2's property that a grant never exceeds its granter, which is the rule that makes delegation safe; rejected |

**Recommendation: A, with B added when the directory sync lands.** A is the smallest change that
keeps every existing property true, and it makes the separation between governing the system and
reading its data a named, visible appointment rather than an accident of who installed it. It is a
Wave 0 dependency for any real use of People: W0.5 furnishes scopes, and this decides who can grant
over them.

---

## Part 7. The build plan

**How to take a package.** Each package lists its files, entities, routes and tests, and can be
built by one agent in a clean worktree. Packages in one wave are independent unless a dependency is
named. Every package ends with the checks in `CLAUDE.md` ("Before you say something is done"), a
mutation run over any guard it adds, the console audit regenerated
(`WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts`), and its WBS leaves appended.
**Verify on a clean worktree at a commit, never in the shared tree** (Part 0).

### Wave 0: make what is built reachable

| Package | What | Files and entities | Tests |
| --- | --- | --- | --- |
| **W0.1** Second factor in the token | Add Keycloak's AMR protocol mapper to the realm's own client scope and a browser flow whose password and OTP steps carry reference values, so a token carries `amr` (`["pwd","otp"]`). Keep `CONFIGURE_TOTP` as a default required action. **First confirm on the staging install**: decode a console access token, or read `assurance` on `GET /api/v1/me`; `authenticated` confirms F1. Commit trailers `Found-on: staging` and `Generic-because: every realm import has no AMR mapper, so no install can exercise an admin verb` | `ops/keycloak/realm-export.json`, `brain.ops.realm_import`, `docs/install/authentication.md` (say that administration needs an authenticator) | a realm test that the scope carries the mapper and the flow the references; an integration test in CI that starts Keycloak from the export, signs a TOTP user in and asserts `amr` holds `otp`; route test that the same token opens `GET /install/features` |
| **W0.2** Say what a weak sign-in costs | Serve, on `/me`, the verbs the caller holds and cannot use here (from `admission.would_lose`, reduced to verbs); a shell banner and a "sign in again with your authenticator" action (OIDC `prompt=login`) | `api_routes.CallerView`, `console/src/layout/Shell.tsx`, `auth/session.ts` | property: the answer names only the caller's own verbs; a console test that the banner appears at `authenticated` and not at `strong`; no refusal elsewhere changes wording |
| **W0.3** Approvals store | Add `verdict` and `reason_code` to `gate.suspension`, a trigger writing the `approval` entry, and build `StoredSuspensions` with a trigger-backed writer; correct `suspension_store_for`'s docstring | migration 0065, `tables/suspension.py`, `gate/suspension_store.py`, `app.py` | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` (database); the three routes answer 200 with an empty queue |
| **W0.4** Missing reads | Grant `read:routing_matrix` and `read:field_classification` in `OVERSIGHT` (reconciliation grants them at next start); change the audit export to export the entries the exporter may read, stating that in the document, with no count of the rest | `identity/first_administrator.py`, `docs/install/authentication.md` table, `ops/data_transfer.py`, `data_export_store.py` | reconciliation test that the new reads arrive and a revoked one stays away; export property test that an entry the reader may not see is absent and uncounted |
| **W0.5** Furnish an install | Apply `ops/starter.py` once: capability registry rows for every declared capability, starter packs, a company-wide scope, routing tiers and rungs for the chosen model profile, built-in templates signed with an install signing key in the vault. As an installer plan step with `already_done`, and as a Settings action for an install set up before it existed. Never in a migration | `ops/starter.py`, `deployment/installer.py`, new `ops/starter_store.py`, `ops/credentials.py` (signing key slot), `agents/template.publish` | `test_furnishing_twice_writes_nothing_the_second_time`; `test_furnishing_never_writes_a_person_or_a_demo_row`; route test that a grant over the company scope succeeds after furnishing |
| **W0.6** Honest failures | A reversed spend window is a 422; wrap database errors in the notification, feature and provider writes as `Failed`; the console renders a feature-off sentence with a link to Features | `console/spend_report_view.py`, `report_routes.py`, `notification_routes.py`, `feature_routes.py`, `provider_routes.py`, `pages/Prompts.tsx`, `pages/Jobs.tsx` | route tests for each status; `screen-states` case for switched off |
| **W0.7** Stale statements | `suspension_store_for`, `docs_routes.audit_anchor` (read `obs.audit_entry`), `retention_store` ("no table grants DELETE"), `channels/api_keys` ("no REST API"), `db.SCHEMAS` comment, route writes that skip `attributed_to` | named files | a test per behavioural change; docstrings only otherwise |

### Wave 1: the shell and the list contract

| Package | What | Files and entities | Tests |
| --- | --- | --- | --- |
| **W1.1** Navigation | Groups become a registry field in `brain.console.screens` and the API serves the company menu too; update `docs/screens.html` SCREEN 1 and SCREEN 2 menus first (the design of record moves before the code), then `brain.ops.console_design` compares the new groups | `console/screens.py`, `department_console.py`, `navigation_routes.py`, `Shell.tsx`, `navigationQuery.ts`, `docs/screens.html` | `shell-navigation`, `department-console`, `console_design` report with no gaps; department console never offered Platform |
| **W1.2** Shared components | Sidebar with the phone-width Menu button, header, breadcrumbs, list page, toolbar, detail page, tabs, drawer, toast region, empty state, explanation panel, KPI strip, card, button variants, bulk bar, secret field; the 19 private failure components replaced by `ui/FailureNotice`; CSS for the six classes that have none; a cross-tab refresh lock (F10); built on shadcn/ui and Radix with Tailwind v4 (5.7), the existing stylesheets held in a `legacy` cascade layer; every page mounting `DataTable` made a lazy route | `console/src/layout/*`, `components/*`, `styles/app.css`, `auth/session.ts`, `package.json` | a test per component for keyboard, focus return, phone width; `bundle-split` extended to the template's form libraries; the four jsdom layout tests re-pointed in the commit that restyles the first page (5.7); `phone-width` and `approvals-phone` changed to the Menu-button property in the same commit (5.1) |
| **W1.3** Server list contract | One query model: `cursor`, `q`, repeated `filter`, `sort` from a declared set; options from `screens.offerable`; never a total. Applied first to people, sessions, access review, elevation, agents, skills, templates, connectors, library, webhooks | `brain/api.py` (a `ListQuery` dependency), each named route, `console/src/components/useServerPage.ts` | cursor stability under inserts; a filter value outside the reader's reach answers exactly as a value that does not exist; `long-lists.test.tsx` entries removed as each lands |
| **W1.4** Theme | Tokens restructured to the design of record; accent from `INSTALL_ACCENT_COLOUR` via the runtime configuration document (`/api/console.js`) with contrast-chosen text; bundled IBM Plex | `theme/tokens.css`, `styles/app.css`, `console_static.py`, `config.ts`, `brain.locale` | `theme.test.ts` for three states; `test_locale.py` still green over the fixed tokens; a contrast test over the accent derivation with a pale, a mid and a dark accent in both themes |
| **W1.5** Global search | `GET /api/v1/console/search?q=` over each module's own read | new `search_routes.py`, `layout/CommandSearch.tsx` | "no match" and "not permitted" are one answer; results narrowed per module; no counts |
| **W1.6** Browser end-to-end harness | Playwright in CI against `docker-compose.lite.yml` plus Keycloak from the export, a TOTP user, the furnished install; a page object per module; run on the ubuntu runner (and locally with the installed, signed Chrome channel, because Windows Application Control refuses unsigned browser builds) | `console/e2e/*`, `.github/workflows/ci.yml` (a decision the README says has not been made: this package asks for it) | the per-module plan below |

### Wave 2: complete the modules whose domain exists

| Package | What | Files and entities | Tests |
| --- | --- | --- | --- |
| **W2.1** Departments, teams, scopes | Create, rename, retire with audit triggers | `identity/organisation_store.py`, new migration (triggers on `gate.department`, `gate.team`, `gate.scope`), `govern_people_routes.py`, `pages/Departments.tsx` | row, ledger, behaviour (a grant over the new scope works; a retired department refuses a new grant) |
| **W2.2** People lifecycle | Grant expiry; bulk grant over a set; pack assignment; disable as a leaver with the adoption plan; reinstate; transfer ownership; manual person where no staff source | `govern_routes.py`, `identity/lifecycle.py`, `identity/packs.py`, `pages/People.tsx` | expiry lapses at the instant; a bulk grant is all or nothing; a disabled person's next request is refused and their automations stop |
| **W2.3** Roles, packs, access explanation | Role appointments with scope (M1.3.2), pack create and assign, the Access tab (Part 4.4), capability holders | new `tables/role_grant.py`, migration, `console/govern.role_holders` route, `reach_view` routes, `pages/People.tsx` Access tab | a role appointment grants nothing; the preview equals the real gate's projection for three personas; no count of withheld holders |
| **W2.4** Sign-in and directory | Identity provider values read, change with restart notice; staff source change; `directory_sync` runner applying a reviewed plan; second-factor status | `install_routes.py`, `identity/staff_sync.py`, `ops/schedule_runner.py`, `pages/SignIn*.tsx` | a spreadsheet source cannot assert a role; a plan applied twice changes nothing |
| **W2.5** Service accounts and API keys | Tables, routes, screen | new `tables/service_account.py`, migration, `channels/api_keys.py` store, `service_account_routes.py` | key shown once and never again; two live keys at most; a key past its account's expiry refused; the API channel never admits `admin` |
| **W2.6** Agents | Draft tables; routes for form document, draft save, check, rehearse (reports what it cannot run until the model lane answers), publish with second approver, install complete, enable, disable, archive, duplicate, transfer; mount `ManifestForm` and `ProcedureCanvas`; the agent detail tabs | new `tables/manifest_draft.py`, migration, `builder_routes.py`, `agent_routes.py`, `pages/AgentNew.tsx`, `pages/Agent.tsx` | a save is a revision; a widened ceiling publishes at SHADOW awaiting a second person who is not the author; a rehearsal returns no rows; an archived agent cannot be enabled |
| **W2.7** Templates | Install from a signed version; author from an agent through the leak scan; visibility; withdraw a version | `agents/install.py`, `agents/authoring.py`, `agent_routes.py`, `pages/AgentTemplates.tsx` | a sealed path cannot be overlaid; a document with a company name is refused until dispositioned |
| **W2.8** Skills lifecycle | Detachment and retirement rows, current assignments, dependency check against the ceiling, search and filter, the "not yet read by a run" sentence | migration, `tables/skill.py`, `ops/skill_store.py`, `skill_routes.py`, `pages/Skills.tsx` | a retired digest cannot be assigned; a detached skill is absent from current assignments and present in history; a tool outside the ceiling is reported and not granted |
| **W2.9** Connectors | Replace key; edit as disconnect plus connect in one transaction; declaration drift | `connector_routes.py`, `ops/connector_store.py`, `pages/Connectors.tsx` | an edit leaves two rows and one live; a key replacement leaves a credential entry and no connection change |
| **W2.10** Credentials | Screen over the existing routes; slots widened to relay, connector, object store | `credential_routes.py`, `ops/credentials.py`, new `pages/Credentials.tsx` | no response or log line carries a value (M27.8.7); an environment variable outranking a slot is said |

### Wave 3: make the controls take effect

| Package | What | Files and entities | Tests |
| --- | --- | --- | --- |
| **W3.1** Agents run: skills and tier obeyed | A route runs an agent through `gate/leash.decide`; the run reads current skill assignments and offers skill cards within the run's reach; the agent's tier is passed as `RoutingRequest.requested_tier`. Depends on the model lane answering | `tools/skills.py`, `gate/answer.py`, `agents/template.EffectiveAgent`, `models/routing.py` | a run of an agent with an assigned skill is offered it; a detached one is not; a caller without a tool the skill needs is not offered it; a heavy-tier agent walks the heavy chain |
| **W3.2** Connector reading | A runner that probes and syncs connected sources; a vault role for the worker to read `connector_keys`; health recorded | `ops/schedule_runner.py`, `ops/openbao/policies/worker.hcl`, `connectors/*` health | probe records health; a disconnected source is not read; the key never reaches a log |
| **W3.3** Automations | Runner; pause, resume, change, remove as change rows; adopt ownerless | new `agent.automation_change`, `ops/agent_automation_store.py`, routes, `pages/Automations.tsx` | a paused automation does not run on the next tick; an ownerless one stops and waits |
| **W3.4** Stop | `ops.halt` table, stop and resume routes, header button, admission reading the persisted state, fail closed | migration, `ops/halt.py` store, `halt_routes.py`, `layout/HeaderBar.tsx` | a halt survives a restart; an unreachable halt store is halted; resume without a reason is refused; the refusal names the halt and not its reason |
| **W3.5** Budgets and spend | Model calls write `ops.spend_actual`; budget versions appended from the console; stops visible | `ops/model_service.py`, `ops/spend_store.py`, `ops/budget_store.py`, `budget_routes.py`, `pages/Limits.tsx` | a call is metered once; a budget change is a new version with a trigger entry; a stop ends at the period boundary in the install's time zone |
| **W3.6** Approvals produced | The leash suspends an action and `put_suspension` is called; approver appointment | `gate/leash.py`, `gate/suspension_store.py` | a SHADOW-to-ASSISTED action raises a card an approver in reach decides once |
| **W3.7** Settings editing | `install.*` writes with validation and restart notices | `install_routes.py`, `ops/install_settings.py`, `pages/Settings.tsx` | a saved value outranks the environment at next start; dimensions refuse a change once embedded |
| **W3.8** Leash moves | The leash lives only at the sealed manifest path `guardrails.leash`, which an install cannot overlay, and rungs compose by intersection, so the two directions are built differently and that asymmetry is the design. **Lowering** is an insert-only row in a new `agent.leash_change` that `Leash.rung_for` intersects with the manifest's leash, needs no evidence and takes effect at once. **Raising** is a publish of a new version whose `guardrails.leash` is higher, admitted only with `reach_view.may_raise` evidence (clean runs, agreement, a named approver, a second approver for send or money effects) through the publish gate. History shows both; circuit-breaker demotions arrive as lowering rows | new migration and `tables/leash.py`, `reach_view.may_raise`, `scoped_authority.may_move_rung`, `agents/supervision.py`, `builder/publish.py`, new `leash_routes.py`, `leash_change` trigger | a lowering row can never raise a rung; a raise without evidence is refused; a missing entry is still SHADOW; each move leaves a `leash_change` entry |

### Wave 4: breadth

| Package | What |
| --- | --- |
| **W4.1** Channels | `ops.channel_binding`, inbound routes with the written verifications (Slack, Teams, Telegram), Lark and WhatsApp verification written, E1 screen |
| **W4.2** System health and alerts | F1 over readiness, worker heartbeat, vault state, object store, identity provider, breakers, halts; an alert sink for `ops/alerting` |
| **W4.3** Queue and side effects | F2: queue screen, `ops.operation` unknown states resolved, dead letters redriven; `queue_redrive`, `side_effect_resume` runners |
| **W4.4** Import | knowledge upload over `chunk_store.ingest_document`; skill import from a repository with an egress rule; template document import |
| **W4.5** Backup drills | `restore_drill` runner recording a drill (named to respect R10), a start control on I6 |
| **W4.6** Access friction and canaries | `denial_digest` runner, B4 friction tab, canary findings persisted and shown on H3 |
| **W4.7** Handover and export sets | `ops/handover.py` routes; export sets beyond the audit trail |

### The end-to-end test plan

**One checklist, applied to every module by the browser harness (W1.6)** against a furnished install
with a TOTP administrator, a department admin, a member, an auditor and an approver. Each line names
what is asserted, not what is clicked.

| Case | Assertion |
| --- | --- |
| List | the first page renders rows the reader may see and nothing else; no total anywhere |
| Search | a term returns matching rows; a term naming something outside the reader's reach returns what a term naming nothing returns |
| Filter | options are the reader's reach (`offerable`); a crafted option outside it answers as an unknown value |
| Sort | order holds across two pages |
| Pagination | the cursor survives an insert between pages without a duplicate or a gap |
| View | the detail opens by address (deep link) and after a reload |
| Create | the row exists, the ledger entry names the actor, reach hash and trace, and the behaviour changes (named per module) |
| Edit and save | the new value is read back; a stale version (hash or revision) is refused with the sentence to reload |
| Verify | the behaviour the write promised is observed downstream (a grant opens a record, a paused job is not started, a switched-off webhook receives nothing) |
| Delete or archive | the marker column is set, the row is not removed, and the list's default view hides it while history shows it |
| Restore (reinstate) | the marker clears or a reinstatement row exists, and behaviour returns |
| Import or export | the round trip preserves what the format promises and drops withheld fields, stated in the document |
| Validation | an invalid form is refused before sending with what to fix; the same payload sent directly is refused by the route |
| Duplicates | a second identical create is refused or is a no-op, as the store declares, and says which |
| Permission restrictions | each persona sees exactly its menu; a refused action answers as an absent one; the department admin never sees Platform |
| Session issues | an ended session refuses the next request and the console returns to sign-in; a token without a second factor shows the banner and no administrative write succeeds |
| Empty, loading, failure | four different sentences: empty, loading, unreachable (network cut), failed (server fault) |
| Dependency failures | vault absent, object store absent, identity provider down, database read-only: each module's sentence, never a blank panel or a raw 500 |
| Destructive confirmations | the confirmation names the thing and the consequence; Escape and the safe button change nothing |
| Responsive | at 375px wide every action is reachable, the sidebar is a drawer, tables scroll inside their card and the page does not |
| Keyboard | every action is reachable by keyboard; focus returns to the opener after a drawer or confirmation |
| Security | no secret in any response, log line or DOM after a write; no count of hidden items in any response; headers (`x-frame-options`, `nosniff`, referrer) present |
| Audit logging | the Audit screen filtered by the entity shows the entry for each write in this run |

**Module-specific cases**, in addition to the checklist:

| Module | Cases |
| --- | --- |
| B1 People | grant with expiry lapses at the instant; removing a pack's capability is refused with the pack named; disabling a leaver ends sessions, stops automations and lists agents for adoption |
| B2 Departments | retiring a department with live grants is refused until they move; a new department's scope is grantable immediately |
| B3 Roles | appointing a role grants no capability; a pack assignment widens exactly the pack |
| B4 Access | nobody certifies their own grant; an approved elevation lapses within four hours |
| B5 Sign-in | unlinking the last administrator is refused; a spreadsheet staff source cannot appoint a role |
| B6 API keys | a key is shown once; a third live key is refused; a key cannot approve |
| C1 Agents | a template install with an unbound connector stays SHADOW; a widened publish waits for a second person; a duplicate does not copy audience; archive is terminal |
| C2 Templates | a sealed path is locked; a leak scan blocks a company name; withdrawing a version hides it from new installs and leaves installed agents pinned |
| C3 Skills | the importer cannot approve; a retired skill cannot be assigned; the run-time sentence is shown until W3.1 |
| C4 Approvals | a card out of reach is absent; a decided card cannot be decided twice; the decision survives a restart |
| C5 Automations | installs paused; resume starts it on the next tick; removal stops it and keeps history |
| C6 Models | switching a provider off removes its rungs from the next plan; a check is one metered call |
| D1 Connectors | the key never renders; edit leaves a disconnected and a live row; drift is shown after a manifest change |
| D2 Knowledge | an uploaded document is chunked under the owner's reach and a member outside it cannot retrieve it |
| E2 Webhooks | a delivery is signed and verifiable with the replaced secret, not the old one |
| E3 Notifications | a switched-off notice sends nothing; the test message sends once per configuration |
| F3 Jobs | pause holds across a restart; run now starts while paused |
| F5 Stop | stop refuses new work at once; resume without a reason is refused; the halt survives a restart |
| G1 Audit | filters combine; an export contains only what the exporter may read, uncounted |
| G2 Retention | a legal hold keeps rows from the sweep; an erasure request is filed once per open person |
| I1 Settings | a change needing a restart says so and takes effect after it |
| I4 Credentials | an environment variable outranking a slot is shown; no value in any response |

---

## Appendix: evidence index

| Subject | Files |
| --- | --- |
| Admission and assurance | `src/brain/gate/admission.py`, `src/brain/identity/bearer.py`, `src/brain/api_routes.py` (`channel_for`, `asking`, `CallerView`), `ops/keycloak/realm-export.json` |
| First administrator | `src/brain/identity/first_administrator.py`, `administration_reconciliation.py`, `docs/install/authentication.md` |
| Screens and permission | `src/brain/console/screens.py`, `reads.py`, `department_console.py`, `console/src/layout/Shell.tsx` |
| Empty install | `src/brain/ops/starter.py`, `src/brain/deployment/installer.py`, `migrations/versions/0014_agent.py`, `0016_template.py` |
| Approvals | `src/brain/app.py` (`suspension_store_for`), `approval_routes.py`, `gate/suspension_store.py` |
| Builder and agents | `src/brain/builder/*`, `src/brain/agents/*`, `console/src/components/ManifestForm.tsx`, `ProcedureCanvas.tsx` |
| Skills | `src/brain/tables/skill.py`, `migrations/versions/0056_skill_library.py`, `src/brain/tools/skills.py`, `console/skill_library.py`, `skill_routes.py` |
| Connectors | `src/brain/ops/connectable.py`, `connector_admin.py`, `connector_store.py`, `tables/connector_connection.py`, `console/connector_trust.py` |
| Access explanation | `src/brain/console/reach_view.py`, `scoped_authority.py`, `govern.py`, `identity/packs.py` |
| Halt, budgets, alerts | `src/brain/ops/halt.py`, `budget_stop.py`, `budget_store.py`, `alerting.py`, `denial_alerts.py` |
| Service accounts and keys | `src/brain/identity/sessions.py`, `src/brain/channels/api_keys.py`, `tables/automation.py` |
| Controls | `src/brain/ops/controls.py`, `schedule_runner.py`, `worker.py`, `features.py` |
| Lists | `console/tests/long-lists.test.tsx`, `console/src/components/DataTable.tsx`, `paging.ts`, `useServerPage.ts` |
| Design | `docs/screens.html`, `console/src/theme/tokens.css`, `console/README.md`, `src/brain/ops/console_design.py` |
| Owner decisions | `docs/needs-rupash.md` items 37, 38, 56, 58, 63 |
