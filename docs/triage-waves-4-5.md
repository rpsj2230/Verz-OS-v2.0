# Triage of waves 4 and 5 (2026-10-13)

Where every open leaf of the wave 4 and wave 5 modules stands, read from code, tests and branches on main at the time of writing, so that a builder takes a module and resumes from what exists instead of starting again. Written by a read-only triage (task M38 triage); no product code was touched. Each leaf's class and evidence are also in `docs/wbs/progress.js` and so on `/build/tracker`.

Classes: 1 built and wired, only an install check is missing; 2 partly built; 3 built but not wired; 4 unbuilt; 5 not code, owner or blocked. A class is a reading of the code on 2026-10-13 and not a proof: the install decides what is done. 'not verified' in an evidence line means the reading was not finished.

## Counts per module

| Module | Leaves | Class 1 | Class 2 | Class 3 | Class 4 | Class 5 |
| --- | --- | --- | --- | --- | --- | --- |
| M17 (Wave 4) | 41 | 16 | 11 | 2 | 7 | 5 |
| M18 (Wave 4) | 21 | 3 | 0 | 12 | 6 | 0 |
| M21 (Wave 4) | 22 | 5 | 9 | 6 | 1 | 1 |
| M25 (Wave 4) | 17 | 7 | 6 | 3 | 0 | 1 |
| M26 (Wave 4) | 15 | 9 | 2 | 3 | 0 | 1 |
| M29 (Wave 4) | 14 | 1 | 0 | 12 | 0 | 1 |
| M34 (Wave 4) | 17 | 1 | 6 | 8 | 0 | 2 |
| M35 (Wave 4) | 21 | 11 | 7 | 0 | 0 | 3 |
| M40 (Wave 4) | 53 | 20 | 15 | 14 | 3 | 1 |
| M19 (Wave 5) | 47 | 2 | 34 | 10 | 1 | 0 |
| M30 (Wave 5) | 30 | 5 | 12 | 6 | 2 | 5 |
| M36 (Wave 5) | 22 | 8 | 5 | 6 | 0 | 3 |
| M37 (Wave 5) | 40 | 7 | 5 | 26 | 0 | 2 |
| M42 (Wave 5) | 52 | 25 | 6 | 4 | 5 | 12 |
| Total | 412 | 120 | 118 | 112 | 25 | 37 |

## Findings that cut across modules

Read these before taking a module. They explain why so many leaves are class 2 or 3 although an older note said "built and wired".

1. **The old proxy note ("a module names the leaf and something imports it") overstated what is wired.** Whole packages have no caller outside themselves: `brain.orchestration` (M18.1 to M18.4), `brain.migration` (M37.1 and M37.2, in-memory registers with no table, route or page), `identity/lifecycle.py` (M26: the real joiner, mover and leaver work is done by `staff_sync_run`, `starter_pack_store`, `principal_state_store` and `automation_owner`), and most of `adoption.py` (M34). For these, class 3 means a store, a route and a page still have to be built, not just a call wired.
2. **M40 leaf ids sit on the wrong module.** Many `member/*.py`, `member_activity.py` and `member_library.py` functions have no caller, while the behaviour is built elsewhere (`GET /me/workspace`, the Knowledge lifecycle routes, `GET /approvals`, `/me/accounts`, `/me/channels`, `/me/memory/*`). Those leaves are class 1 and the install check should read the real route.
3. **`orchestration/unattended.py` is a model, not the automation runtime** (M17.4). The runtime is `ops/automation_run.py`, `automation_run_store`, `console/automation_gallery` and `automations_routes`, and it supports the schedule trigger only. There is no workflow engine (M17.6); the nearest pieces are `builder/procedure.py`, `ops/automation.py` and `automation_routes.tool_call`.
4. **M19 has no worker half.** The driver that compiles an envelope, sends the start line to the browser launcher, relays the run and writes the session and recording is not built; the sandbox bodies have never been sent to a Docker daemon; no workflow builds the browser runner image. Almost every M19 leaf waits on that one driver, so install checks written first would only be checks that cannot pass.
5. **Backups are narrower than the M30 and M42 leaves say.** The only backup that runs is a nightly `pg_dump -Fc` with a manifest (`ops/backup/brain-backup`). No pgBackRest, WAL archiving, restic, encryption of a copy or off-host enforcement exists; the restore drill is run by hand; `ops/schedule_runner.py` entries for the drill and the backup exposure have `needs=` and no `run`; `recovery.alerts`, `controls.overdue` and `launch.service_level` are tested and called by nothing; backup and control alerts have no delivery channel.
6. **Enforcement and retention that ship partly empty (M21, M25).** Budget enforcement is wired but off (flag `budget_enforcement`, needs-rupash item 169, decided A). Department and user budgets can be read and never set by any route. The trace payload store has INSERT only, so the daily sweep never deletes from it; detaching a ledger partition keeps its rows; `browsing.recording.remove_expired` has no caller; cache, index, recordings and attachments are not reached by erasure; `ops/erasure.assemble` and `certify` have no caller, so there is no deletion certificate. The console draws English only (M35): the locale formatters have no caller.
7. **Narrowings with no needs-rupash item** (CLAUDE.md says a narrowing is a question): M19.9.1 (the leaf wants a new approval naming a breach mid-run; `approval.py` deliberately approves the envelope up front and ends a refused run), M42.5.5 (the wizard collects a logo address where the leaf says upload), M36.2.2.2 (`gate/screening.screen_in_one_pass` is built, its own docstring says the collapse does not pay), M40.3.1.3 (per-item usage counts conflict with a retrieval log that deliberately stores no item reference), M40.6.1.2 (amend is explicitly not offered), M21.2.6 (the refusal sentence names no budget). A builder should raise each as a numbered item rather than decide it.
8. **A function with a docstring that says it is wired is not evidence.** `mine_routes.CORRECTIONS_ARE_NOT_RECORDED` and the `write_verification` docstring are stale against main; `needs_you.py` still says no budget stop is recorded.


# Wave 4

## M17 Automation and the task lane

### M17, Class 1: built and wired, only an install check is missing (16)

- **M17.1.2** Procrastinate integration on Postgres  
  Evidence: ops/queue.py enqueue_job, register_task, queue_app, run_shards; ops/worker.py drains a real queue (install_queue, run_shards); callers: knowledge_routes, knowledge_intake_routes, knowledge_lifecycle_routes, ingest_queue. Tests: test_control_task, test_jobs; ops/jobs.py says M17.1.2 is claimed in ops.queue.  
  Next step: write check naming M17.1.2 that enqueues a task through knowledge ingest (acceptance_ingest already uses queue_url_of) and sees the worker pick it up
- **M17.1.3** Worker pool with per-class concurrency  
  Evidence: queue.worker_shards allocates concurrency per traffic class; ops/worker.py starts one shard per class (run_shards, queue_pool_gaps). Per-task caps (jobs.TaskPool) are not enforced, which the jobs docstring says openly; the leaf names per-class.  
  Next step: write check naming M17.1.3 reading the worker's plan (worker_shards for each slot class) from the install's configuration
- **M17.2.2** Our own re-drive driver for crash recovery  
  Evidence: ops/crash.py redrive/verify_once are called by ops/recovery_run.py (scheduled control, schedule_runner.queue_redrive) which moves recoverable jobs and operations. acceptance_checks_recovery covers it under M23.3.1 only. Tests: test_crash, invariants.  
  Next step: add M17.2.2 to the leaves of the recovery run check in acceptance_checks_recovery.py
- **M17.2.4** Resume after restart with state intact  
  Evidence: Interrupted work resumes: recovery_run re-drives running and failed jobs and verify_once settles operations left UNKNOWN (ops/crash.py, controls); suspensions persist in gate/suspension_store and resume through leash.resume. acceptance_checks_recovery exists for M23.3.1.  
  Next step: write check naming M17.2.4: leave an operation in a mid state, run the recovery control, assert one effect and state intact
- **M17.2.5** Entitlement re-check at every resume point  
  Evidence: leash.resume re-resolves the approver's reach on every decision (approval_routes take_decision); automation_run resolves the owner's live reach at each run; jobs carry a principal and never a reach (jobs.reach_carrying_fields, crash.stored_reach_gaps). Tests: test_leash, invariants.  
  Next step: write check naming M17.2.5: raise a suspension, revoke the approver's grant, press approve, expect refusal
- **M17.3.1** Idempotency key on every side-effecting operation  
  Evidence: issue_once keys every send: channels (adapter, email, lark, slack, teams, telegram, whatsapp), gate/leash, ops/digest_delivery, connector_write_run, browsing/runner. ops/effects.py is the register read by tests/invariants/test_every_side_effect_is_keyed (it has no runtime caller by design).  
  Next step: write check naming M17.3.1: send the same keyed message twice through a channel adapter and see one send and one Repeated
- **M17.3.2** Operation state machine: pending, sent, unknown, verifying, succeeded, failed  
  Evidence: ops/idempotency.py OperationState (pending, sent, unknown, verifying, succeeded, failed) with RESUME_PLAN and advance, persisted by ops/operation_store.py and tables/operation.py (PostgresOperationLedger). Tests: test_idempotency, test_operation_store.  
  Next step: write check naming M17.3.2 walking one operation through its states in the install's ledger and reading it back
- **M17.3.3** Verification read-back per connector  
  Evidence: connectors/write_verification.verdict plus each connector's ReadBack declaration (hubspot, laravel, xero, freshdesk, lark, drive); ops/connector_write_run reads the record back and reports done only when FOUND (cloudflare write is the live user; acceptance_checks_cloudflare). Module docstring saying no connector writes is stale.  
  Next step: write check naming M17.3.3 over the cloudflare approved-write read-back (acceptance_checks_cloudflare setup)
- **M17.3.4** Connectors without read-back restricted to read-only, declared in the manifest  
  Evidence: write_verification.read_back_gaps refuses a connector declaring a write with no reading, and ops/idempotency.issuable_tools returns tools with read-back; WriteGrant is a separate declared grant in connectors/declaration. issuable_tools has no runtime caller (enforced by tests and declaration).  
  Next step: write check naming M17.3.4 reading the shipped manifests and asserting every write-declaring connector declares a ReadBack
- **M17.3.5** Kill-after-side-effect test proving exactly-once  
  Evidence: tests/invariants/test_crash_exactly_once.py kills at every derived boundary over the in-memory ledger and test_idempotency CRASH_POINTS; a real process kill is not done. Install proof would use PostgresOperationLedger.  
  Next step: write check naming M17.3.5 that issues a keyed effect, simulates loss of the answer, resumes through crash.verify_once on the install's ledger and counts one effect
- **M17.4.3** Automation principal resolving the owner's live entitlements at each run  
  Evidence: ops/automation_run resolves the owner's live reach at each run through flow_reach (A_RUN_IS_ITS_OWNERS_AT_THE_INSTANT_IT_STARTS), started by schedule_runner; automation_routes.tool_call looks the owner up at every call. acceptance_checks_automation covers the tool door under M32.6 only.  
  Next step: write check naming M17.4.3: install an automation, revoke an owner grant, run it, assert the run's reach lacks it
- **M17.4.4** Suspension when the owner loses a required entitlement  
  Evidence: automation_run pauses the automation with a closed reason when the owner is gone, the agent disabled or the reach lacks what the task reads; automations_routes ADOPT_PATH offers it to another person; notice automation_paused is sent (automation_paused_told). Tests: automation run tests.  
  Next step: write check naming M17.4.4: remove the owner's required grant, run due automations, assert paused with reason and adoptable
- **M17.5.1** Postgres outbox with retry and backoff  
  Evidence: ops/outbox.py plan_next retry and backoff, outbox_store (tables/outbox.py), ops/webhook_delivery.run_dispatch_now started by schedule_runner.outbox_dispatch; events written by automation_run, item_store, outbox_store. Tests: test_outbox, test_outbox_store.  
  Next step: write check naming M17.5.1: register a subscriber to a refused address, write an event, run the dispatch control, assert attempts and backoff
- **M17.5.2** Signing and delivery guarantees  
  Evidence: outbox.signed_request/signature_for sign each delivery in the worker alone (webhook_delivery reads the secret), sent through issue_once so a delivery is at-least-once with one effect per id. Test: test_outbox.  
  Next step: write check naming M17.5.2: dispatch to a local receiver, verify the signature with signature_matches and that a replay sends once
- **M17.5.3** Subscriber management in the console  
  Evidence: Webhooks screen: webhook_routes (list, register, rotate secret, switch off and on, replay) over console/subscribers and ops/outbox_store, page console/src/pages/webhooks. Tests: test_subscribers, test_outbox_store.  
  Next step: write check naming M17.5.3: register, list, switch off and replay a subscriber through the route functions
- **M17.7.9** On the install the denial digest runs on its window and tells the person's department lead or data steward that someone keeps being refus...  
  Evidence: run_denial_digest_now is started each window by schedule_runner.denial_digest and sends the denial_pattern notice naming only the shape; recipients are company-wide holders (data steward), a department lead is not told. acceptance_oversight checks routing under M23.2.2 and sends nothing.  
  Next step: write check naming M17.7.9: run run_denial_digest_now over reserved refusals and read the kept alert for the steward with no resource named

### M17, Class 3: built but not wired (2)

- **M17.1.5** Dead-letter handling with an operator surface  
  Evidence: ops/jobs.py dead_letter_for, visible_dead_letters, DeadLetter (filtered, no count) are built; only dead_letter_summary has a consumer in console modules. No route or page lists dead letters: jobs_routes and operate_routes show scheduled controls and owed runs.  
  Next step: add GET /jobs/dead calling visible_dead_letters over driver rows in failed state and a Dead letters tab on the Jobs page
- **M17.4.5** Timeout and expiry on every approval step  
  Evidence: orchestration/unattended.ApprovalStep, approval_refusals and expire are built (test_orchestration_unattended) with no caller; adoption.py imports only TriggerKind from it. Installed automations have no approval step at all, so there is nothing to time out.  
  Next step: give automation_run an approval step and call approval_refusals and expire from it; agent approvals already lapse via leash windows

### M17, Class 2: partly built (11)

- **M17.1.1** Job table with state machine, attempts, and scheduling  
  Evidence: ops/jobs.py has JobState, advance, JobRecord, next_attempt_at, worst_case_runs (test_jobs) but no table of ours: the docstring says nothing persists it. The real job rows are Procrastinate's (ops/queue.py); the Jobs screen (jobs_routes) lists scheduled controls and their runs, not JobState rows.  
  Next step: map the driver's job rows onto JobState in the Jobs/Live runs read, or decide the driver's own states are the job table and retire the model; then a check reading GET /jobs
- **M17.1.4** Cancellation and timeout  
  Evidence: ops/jobs.py models interrupt, CANCELLING/ABORTED/CANCELLED and DEFAULT_TIMEOUT_SECONDS (test_jobs) but nothing calls interrupt and no timeout is enforced in ops/worker.py or queue.py; jobs_routes offers pause/resume/run now only (NO_RUN_CAN_BE_STOPPED_FROM_HERE).  
  Next step: enforce a per-task timeout in the worker and add a cancel control calling jobs.interrupt over the driver's abort, then a check
- **M17.2.1** LangGraph checkpointer on Postgres  
  Evidence: ops/checkpoint_store.py install_checkpointer is called by ops/worker.py at start (schema plus row-level security) and guarded_saver exists with ownership checks (test_checkpoint_store). Nothing compiles a graph, so guarded_saver has no caller and no run saves state.  
  Next step: wire guarded_saver into the first graph the agent runtime compiles (orchestration/plan or gate/runtime), then a check that a run's state is read back
- **M17.2.3** Checkpoint at every side-effect boundary  
  Evidence: Operation ledger writes are durable before and after the effect (idempotency.issue_once, operation_store) and crash.side_effect_boundaries derives every boundary, used by tests/invariants/test_crash_exactly_once. There is no graph state to checkpoint at those points.  
  Next step: a check issuing a keyed effect and reading back both ledger states; graph-level checkpoint waits on M17.2.1 wiring
- **M17.4.1** Trigger types: schedule, connector event, webhook  
  Evidence: Schedule trigger is built: automation_run, automation_run_store.run_automations_now started by schedule_runner, cadence from console/automation_gallery. Connector-event and webhook triggers exist only as orchestration/unattended.TriggerKind (used by adoption.channel_for_trigger); nothing starts a run on either.  
  Next step: build the two missing trigger paths (connector change event, inbound webhook) into automation_run and show all three kinds on the agent page's New automation
- **M17.4.2** Automations start from named outcome templates, while workflows are authored in the console as stored, versioned step data rather than dr...  
  Evidence: Named outcome templates are built and installed paused: console/automation_gallery BUILT_IN (weekly summary, unanswered questions, source freshness) and POST install route; ops/automation_run.TASKS has one performer. Workflows as stored versioned step data from the console do not exist (see M17.6.1).  
  Next step: build the stored versioned workflow data (reuse builder/draft_store revisions) and the console authoring page; templates stay as they are
- **M17.4.6** Run history with cost per run  
  Evidence: Run history exists: console/agent_automations AutomationRun, automations_routes detail and stats, tables/automation_run. Cost per run is not recorded: RUN_COST_IS_NOT_RECORDED in automations_routes says so. unattended.CostedRun/history is unwired.  
  Next step: record cost per run (spend actuals joined by run id) and surface it in AutomationRun and the stats route
- **M17.6.2** A workflow step can call a skill, read a connector or use a tool, and every such step runs through the gate at the run's reach, the leash...  
  Evidence: The door exists for canvas steps: automation_routes.tool_call runs one tool through the gate as the owner at flow_reach with the projected catalogue and redactor (acceptance_checks_automation, M32.6.2.2). Skill steps, a workflow runner and per-step leash and meter accounting are not built.  
  Next step: build the step executor calling the same gate path for tool, connector read and skill steps and recording each in spend
- **M17.6.7** Every finished workflow or automation run emits a success or failure signal naming the workflow, the agent and the step that failed, and ...  
  Evidence: Automation runs emit automation.run_finished via the outbox (ops/automation_run); repeated failures pause with a notice (FAILURES_BEFORE_PAUSE, automation_paused_told). Missing: workflow and failed step named in the signal, and a learning candidate on repeated step failure. Payload fields not verified.  
  Next step: add workflow id and failing step to the event and open a learning candidate through knowledge/candidates after N failures of one step
- **M17.7.2** A scheduler inside the application runs every registered scheduled control when it is due, holding a database lock so two application cop...  
  Evidence: Scheduler built: ops/schedule.py (what is owed), schedule_runner.py with pg_advisory_xact_lock per control (schedule_store), started by ops/worker. Alert for a control with no run in its window: controls.overdue has no caller and notices.py says nothing sends control_not_run.  
  Next step: call controls.overdue from the worker tick and send control_not_run through tell_later to the operations alert holder; then a check
- **M17.7.6** Every notice the product composes is delivered to the person it names through their bound channel or the configured email relay, and a no...  
  Evidence: tell_later.tell is the one sender (person's last-used channel or mail relay) and six notice kinds use it; ops/notices.py lists 14 kinds and 'no channel is chosen yet, so nothing sends it' for the rest. The Notifications screen shows sent_by but no undelivered state per notice.  
  Next step: give each remaining notice kind a sender through tell_later and record failed deliveries for the Notifications screen to show as undelivered

### M17, Class 5: not code, owner or blocked (5)

- **M17.6.8** A workflow that reads two connectors, calls two skills, waits for an approval and delivers a document runs end to end on the install and ...  
  Evidence: End-to-end workflow with two connector reads, two skills, an approval and a delivered document needs the workflow engine (M17.6.1 to M17.6.7) first; nothing runs it today.  
  Waits on: waits on M17.6.1 to M17.6.7; then an install run recorded as one trace
- **M17.7.1** The monthly search report workflow runs on the install for a named client: it resolves the client, reads the period's analytics and searc...  
  Evidence: Monthly search report workflow needs the workflow engine (M17.6.x), a named client, report template and the owner's analytics and search console access. Connectors exist (google_analytics, search_console, acceptance_checks_search_console); the workflow and client resolve do not. Register rows OWN-75, OWN-77.  
  Waits on: waits on M17.6.x and the owner supplying a named client and report template
- **M17.7.3** Automations are proved on an install: a scheduled, a connector-event and a webhook automation each run as their owner from a named templa...  
  Evidence: Proof of three trigger kinds, owner suspension and adoption, run cost and the optional canvas network rule needs M17.4.1 (connector-event and webhook triggers) and M17.4.6 (cost) built first; the schedule part exists and could be proved now.  
  Waits on: waits on M17.4.1 and M17.4.6; the canvas part needs the owner to enable docker-compose.automation.yml
- **M17.7.4** Workflow control flow is proved on an install: a workflow with two parallel skill steps, a conditional step that is skipped, a step that ...  
  Evidence: Control-flow proof (parallel, conditional skip, retry through key, failure path, gap) needs M17.6.3 to M17.6.6 which are unbuilt.  
  Waits on: waits on M17.6.1 to M17.6.6
- **M17.7.8** Every human approval requirement in the requirements register is demonstrated on an install by a person, and each check is recorded again...  
  Evidence: Person-run demonstration of every human approval requirement in the register, each recorded against its requirement; approval mechanics exist (approval_routes, cards, leash) but the walk is a person's on the install (register rows GAP2-02, GAP2-08, GAP2-20).  
  Waits on: owner or coordinator-run walk on the install after the approval leaves land; record each in the requirement checks screen

### M17, Class 4: unbuilt (7)

- **M17.6.1** An administrator can define a multi-step workflow from the console as stored, versioned data, and an agent assigned that workflow runs it...  
  Evidence: No workflow definition store: searched src for workflow, step data and versioned steps. Neighbours: builder/procedure.py (drawn procedure to SKILL.md, acyclic, MAX_STEPS), builder/draft_store (revisions), ops/automation.StepKind (canvas flows), automation_run store. Register rows OWN-63, OWN-64, OWN-75.  
  Build: build workflow table (steps, versions) with a console editor and an agent assignment; reuse draft_store revisions, procedure.py bounds and the automation_run scheduler
- **M17.6.3** A workflow step's output is named and schema-checked, and a later step can read only outputs that earlier steps declared  
  Evidence: No named, schema-checked step outputs: nothing in src models step outputs or a reads-only-earlier rule (searched workflow, outputs, schema near automation and builder).  
  Build: design in the workflow data model of M17.6.1: declared output schema per step and a compile-time check that a step reads only earlier outputs
- **M17.6.4** A workflow step can run only when a condition over earlier named outputs holds, and a skipped step is recorded as skipped with the condit...  
  Evidence: No step conditions or skipped-with-reason records. builder/procedure.py has a scope-predicate conditional for drawn skills, and ops/automation.StepKind has branch for the canvas, but neither records a skipped step.  
  Build: add condition over named outputs to the workflow step model and record 'skipped' with the deciding condition in the run trace
- **M17.6.5** Workflow steps declared parallel start together, and the step that combines them runs only after each has finished or been recorded as a gap  
  Evidence: No parallel step support: searched for parallel and fan-in; orchestration/fanout.py is multi-agent fan-out with a budget, not workflow steps with a gap-recording join.  
  Build: reuse orchestration/fanout budget and gap recording for a join step in the workflow executor
- **M17.6.6** Each workflow step carries its own retry limit and backoff, a side-effecting step is retried only through its idempotency key, and a step...  
  Evidence: No per-step retry limit or failure path. Reusable parts exist: jobs.next_attempt_at and retry_gaps (backoff), idempotency.issue_once (retry only through the key), outbox.plan_next; none is attached to workflow steps.  
  Build: attach retry limit, backoff and an on_failure edge to step data and drive retries through issue_once with the step's key
- **M17.7.5** The automation gallery ships a daily brief, capture of deals from group chats into the customer records held as drafts, and drafted email...  
  Evidence: Gallery ships weekly_work_summary, unanswered_questions and source_freshness (console/automation_gallery BUILT_IN); no daily brief, no deal capture from group chats, no drafted email replies. Reuse: ops/digest_delivery (evening digest), channels/email, hubspot connector, automation_run.TASKS.  
  Build: add three templates and performers declaring trigger, connectors and approval step; daily brief reuses the evening digest, deals and replies need drafts held for a person
- **M17.7.7** An agent runs only the workflows assigned to it, and a request that would start any other workflow through it is refused before the first...  
  Evidence: No workflow assignment exists, so no refusal of an unassigned workflow through an agent; depends on M17.6.1's workflow data and an agent-workflow link in the agent manifest or install.  
  Build: design with M17.6.1: agent holds a list of workflow ids; the runner refuses others before step one

## M18 Multi-agent execution

### M18, Class 1: built and wired, only an install check is missing (3)

- **M18.3.1** Child grant computed in SQL as parent intersect agent intersect subtask  
  Evidence: core/scope_sql.py gate.delegated_reach computes parent intersect agent intersect subtask in SQL; installed by migrations 0028, 0029, 0033 with gate.delegation. test_delegation_sql.py compares it to EntitlementSet.intersect on a real server. Nothing in the app inserts rows yet.  
  Next step: write check naming M18.3.1: insert a root and child delegation row in the harness and assert the stored child reach equals the Python intersect
- **M18.3.2** Database trigger rejecting any non-subset delegation row  
  Evidence: Trigger gate.delegation_narrows (core/scope_sql.py, migrations 0028 and 0033) refuses any insert or update whose reach is not a subset of its parent; 30-odd real-server tests in test_delegation_sql.py. No application code writes the table yet.  
  Next step: write check naming M18.3.2: via h.execute insert a widening child row and assert the database refuses it, then a narrowing row and assert accepted
- **M18.3.3** Orchestrator has no grant verb, asserted  
  Evidence: delegation.grant_verbs_in() scans the orchestrator for grant operations and tests assert none exist (test_orchestration_delegation.py); there is no orchestrator runtime to grant anything. CI-asserted by design.  
  Next step: repo-only leaf: close as Proved-in-ci naming the unit job running test_orchestration_delegation.py

### M18, Class 3: built but not wired (12)

- **M18.1.2** Subtask contract: objective, output schema, tool hints, scope predicate  
  Evidence: orchestration/contract.py SubtaskContract (objective, output schema as FieldSpec, tool hints, scope predicate) and subtask_ceiling() are tested in test_orchestration_contract.py. No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: build the orchestrator runtime that calls it: a coordinating-agent step in the run path (gate/runtime or a new orchestration runner) fed by the M18.5.3 planner and the M18.5.1 callee links
- **M18.1.3** Schema validation on every subtask result, failure rather than merge input  
  Evidence: contract.validated()/validated_or_none() refuse a result that does not match its schema (tested); merge.merge only takes ValidatedResult. No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: call contract.validated on each child's reply in the orchestrator before it is handed to merge; a failure becomes a gap, not an input
- **M18.1.4** Prose explicitly disallowed as a subtask contract  
  Evidence: contract.py has no prose field kind and contract_gaps() refuses a contract that would let free prose be the output (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: build the orchestrator runtime that calls it: a coordinating-agent step in the run path (gate/runtime or a new orchestration runner) fed by the M18.5.3 planner and the M18.5.1 callee links
- **M18.2.1** Dependency graph with cost and coupling weights  
  Evidence: orchestration/plan.py DependencyGraph with Node cost and Edge coupling weights, read_proposal(), plan_refusals() (tested in test_orchestration_plan.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: feed it the planner proposal (M18.5.3) and pass the graph to fanout.decide
- **M18.2.2** Six arithmetic conditions evaluated before any child starts  
  Evidence: orchestration/fanout.py six Conditions evaluated by gate_inputs(), holds(), failures(), decide() before any child starts (tested in test_orchestration_fanout.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: call fanout.decide(graph, depth) in the orchestrator before dispatching children
- **M18.2.3** Collapse to a single loop as the default when any condition fails  
  Evidence: fanout.decide returns Verdict.SINGLE_LOOP when any condition fails, the default (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: honour the verdict in the orchestrator: run the plan as one loop when SINGLE_LOOP
- **M18.2.4** Gate inputs and verdict recorded for audit  
  Evidence: fanout.GateRecord holds inputs, failures and verdict with AUDIT_SURFACE and gate_record_gaps (tested). Nothing persists a record: no table, no trace field, no caller.  
  Next step: persist the GateRecord on the run's trace (tables or ledger) when decide() runs, then show it on the run's page
- **M18.3.4** Depth cap of two and per-run concurrency cap of eight  
  Evidence: delegation.depth_of(), chain_refusals(), concurrency_refusals() hold depth two and eight children (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: call chain_refusals and concurrency_refusals when the orchestrator creates each child
- **M18.3.5** Global parallelism budget across all runs  
  Evidence: delegation.fan_out_request() builds an ops.admission request per run and global_ceiling() reads the central budget (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: submit fan_out_request to ops.admission before children start; refuse or queue when the global budget is spent
- **M18.4.1** Merge step writing the final answer from validated inputs  
  Evidence: orchestration/merge.py merge() builds a MergedAnswer only from ValidatedResult inputs (tested in test_orchestration_merge.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: call merge from the orchestrator and return MergedAnswer to the asker as the run's answer
- **M18.4.2** Per-subtask cost and duration surfaced to the user  
  Evidence: merge.SubtaskReport carries cost and duration per subtask into MergedAnswer (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. No route or page shows it.  
  Next step: expose per-subtask cost and duration on the run's answer payload and in the console run view
- **M18.4.3** Partial-failure handling with a stated gap  
  Evidence: merge.Gap, GapCause, GapTrace state the gap when a subtask failed, and merge_refusals refuses a silent hole (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package.  
  Next step: carry the stated gap into the user-visible answer from the orchestrator

### M18, Class 4: unbuilt (6)

- **M18.5.1** A coordinating agent can hand a subtask only to agents an administrator allowed it to call, and a call to any other agent is refused befo...  
  Evidence: No coordinator concept exists: no table or route holds which agents an administrator allowed an agent to call (agent_link_routes.py is deep links only), and no call-another-agent step is in the run path. Reuse: delegation.Hop and chain_refusals.  
  Build: build an agent-to-agent callee allow-list (table, admin route, console tab) and a call-agent tool in the gate refusing any agent not on it before the child starts
- **M18.5.2** A specialist agent handed a subtask reads through its own knowledge, skills and connectors within the asker's reach, and the coordinator ...  
  Evidence: No specialist runs on a subtask: nothing hands a subtask to an agent. Pieces exist: EntitlementSet.intersect via ops.automation.flow_reach (commit 4f1f1d6 fold test), delegation.child_hops, contract.validated.  
  Build: build the specialist run: child run at flow_reach(asker, specialist ceiling) using the specialist's own knowledge, skills and connectors, returning only a validated result
- **M18.5.3** A planner step asks a model for subtasks and their dependencies, and its proposal passes the existing proposal checks before any child runs  
  Evidence: No planner step: nothing asks a model for subtasks and dependencies. plan.read_proposal() and plan_refusals() are built to check a proposal but nothing produces or calls one; needs-rupash lists M18.1.1 merged into M18.5.3.  
  Build: build a planner prompt step in the orchestrator that calls the model, parses with plan.read_proposal, and runs plan_refusals before any child
- **M18.6.1** A request to analyse a client's website and prepare an improvement proposal runs on the install as a coordinating agent handing website, ...  
  Evidence: End-to-end website proposal by a coordinating agent with four specialists is unbuilt: depends on M18.5.1 to M18.5.3 and on specialist agents for website, search data, competitor and pricing, plus a single trace showing each child's reach and the fan-out verdict. Person-run proof leaf.  
  Build: blocked on M18.5.x and the orchestrator runtime; then rehearse on an install and record the checks
- **M18.6.2** An agent spawns parallel subtasks or workers only when fan-out is enabled on it by its department admin, and a run of an agent without it...  
  Evidence: No fan-out grant on an agent: nothing in tables/agent*, agents/model.py or the department admin console holds a fan-out switch, and no run records a reason for running single loop. fanout.Verdict.SINGLE_LOOP exists unwired.  
  Build: add a fan-out flag per agent set by its department admin (agents/model.py, route, console), have the orchestrator read it and record the single-loop reason on the run
- **M18.7.1** The cost check may run a coordinator's specialist agents one after another, but never replaces a specialist's work with the coordinator's...  
  Evidence: Not built: fanout.Verdict has only SINGLE_LOOP and PARALLEL, and nothing says SINGLE_LOOP for a coordinator means running specialists in sequence rather than the coordinator doing their work. No orchestrator exists to hold the rule (register OWN2-5).  
  Build: when the orchestrator exists, define SINGLE_LOOP as sequential specialist calls and add a test that the coordinator never answers a subtask itself

## M21 Cost, budgets and metering

### M21, Class 1: built and wired, only an install check is missing (5)

- **M21.1.5** All levels as versioned, audited rows  
  Evidence: tables.budget versioned rows + ops.budget_store.append/history_of, ledgered by a trigger on append (agent_workspace_routes docstring cites 0098); written by company_routes and agent_workspace_routes, tested test_budget_store. Only the company and agent levels have a writer.  
  Next step: Write check naming M21.1.5 that sets the company budget twice via PUT and reads both versions and the ledger row (reuse acceptance_checks_company_budget._history).
- **M21.2.3** Post-hoc accounting against principal, department, agent, model and lane  
  Evidence: ops.usage_store.UsageRecorder (installed in app.py) writes tables.spend.SpendActualRow per finished request; Actual carries principal, department, agent, model, lane; read by spend_report_view and /report/spend. Tests test_usage_store, test_spend.  
  Next step: Write check naming M21.2.3 that asks one question then reads the spend_actual row and /report/spend by each dimension (see acceptance_checks_console_money for the harness).
- **M21.3.1** Spend by department, user, agent, model and lane  
  Evidence: GET /report/spend (report_routes.spend) groups by Dimension department, principal, agent, model, lane from ops.spend_daily via spend_report_view; page console/src/pages/reports/SpendPage.tsx. Tests test_report_routes, test_spend_report_view.  
  Next step: Write check naming M21.3.1 reading GET /report/spend for each dimension after seeding spend rows.
- **M21.3.2** Machine traffic excluded and labelled  
  Evidence: report_routes.spend takes include_machine default false and the view says which it was (MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO); Actual.machine is derived. Tests test_spend_report_view, test_spend.  
  Next step: Write check naming M21.3.2 seeding a machine and a human row and reading /report/spend with and without include_machine.
- **M21.3.5** Budget consumption against pace  
  Evidence: GET /console/department/pace (department_view_routes.PACE_PATH) uses scoped_authority.department_pace and spend_view.pace; page console/src/pages/department (departmentFigures.ts). Agent projection in console_stats_routes. Test test_department_view_routes.  
  Next step: Write check naming M21.3.5 that sets a department ceiling row then reads /console/department/pace (needs a department budget writer, see M21.1.2, or a direct seed row).

### M21, Class 3: built but not wired (6)

- **M21.1.2** Department budget as a share, with explicit transfer only  
  Evidence: ops.budgets.allocate, Transfer and apply_transfers are built and unit-tested (test_budgets) but have no caller outside budgets.py; no route writes a department budget row (only company_routes and agent_workspace_routes call budget_store.append).  
  Next step: Add a department budget set/transfer route (beside company_routes.set_company_budget) that calls allocate/apply_transfers and budget_store.append, then a check.
- **M21.1.3** User daily and monthly allowance with a fair-share cap  
  Evidence: ops.budgets.user_allowances (daily and monthly, fair share) has no caller; mine_routes and member_activity only read user rows via budget_store.in_force. No route or job writes a user-level row, so no person ever has an allowance.  
  Next step: Call user_allowances from a route or sync that appends user rows via budget_store.append, with the fair-share cap; then write a check.
- **M21.2.1** Pre-flight cost estimate from lane, tier, tool count and retrieval size  
  Evidence: ops.spend.estimate and preflight (lane, tier, tool count, retrieval size) are built and tested; callers are builder.rehearse and orchestration.plan only. budget_stop_store docstring rejects preflight on the request path; no live question is estimated.  
  Next step: Decide with owner whether to call spend.estimate in api_routes.answered_for before the lane (budget_stop_store.judged is the slot); raise as a needs item since the code deliberately chose stop-on-used-up.
- **M21.2.4** Estimator correction from actuals  
  Evidence: ops.spend.correct (estimator correction from Observation actuals) is built; only ops.retune.post_launch_correction uses it, called from console.spend_view.cost_review which no route or page calls. No live estimator applies a Correction.  
  Next step: Run correct() from a worker job over spend_actual versus estimates and persist the Correction; wire it into estimate() on the request path (depends on M21.2.1).
- **M21.3.3** Cost per answer with the distribution, not only the mean  
  Evidence: console.spend_view.distribution and cost_per_answer (quantiles, not only mean) are built and tested (test_spend_view) but no route, page or other module calls them; SpendReportView has no distribution field.  
  Next step: Add the distribution to /report/spend (report_routes.spend_view_of) or a new route, then show it on SpendPage.tsx.
- **M21.3.6** Every budget refusal with the budget that caused it  
  Evidence: BudgetStopRow rows are written (budget_stop_store.record) with level, subject, period; spend_view.budget_stops/StopRow list them but nothing calls those. console.needs_you still says no stop is recorded (stale text).  
  Next step: Add a route and Spend section listing recorded stops (reader-scoped via spend_view.told_about); fix the stale needs_you UNRECORDED_HEALTH entry.

### M21, Class 2: partly built (9)

- **M21.1.1** Company budget with hard ceiling and alert thresholds  
  Evidence: Ceiling stored and versioned: PUT company budget (company_routes.set_company_budget, ops.budgets.BudgetRow, test_company_routes). Hard stop is ops.budget_stop_store.budget_refusal_for in api_routes, flag budget_enforcement off (needs 169 A). alert_fractions stored, nothing fires them.  
  Next step: Wire alert_fractions to a notice when spend crosses one (spend.alerts_for exists but is only called by unwired preflight); then write a check naming M21.1.1 that sets a ceiling with alerts and reads the stop record.
- **M21.1.4** Per-agent per-run and per-day ceilings  
  Evidence: Agent monthly ceiling is settable: agent_workspace_routes (BudgetLevel.AGENT, MONTH; test_agent_workspace_routes). ops.budgets.agent_ceilings (per-run and per-day) has no caller, so per-run and per-day agent ceilings are never written.  
  Next step: Call agent_ceilings from the agent workspace route (or a second field) so run and day rows are appended; then check naming M21.1.4.
- **M21.2.2** Refusal before tokens are spent  
  Evidence: A used-up budget refuses before any lane runs (api_routes.answered_for calls budget_refusal_for after the halt, before lanes), so no tokens are spent on that question; flag off (needs 169 A). Estimate-based refusal (spend.preflight) is not on the path.  
  Next step: Same as M21.2.1 for estimate-based refusal; for the used-up stop only the flag decision (169) and a check remain.
- **M21.2.5** At a budget limit the request is refused with no silent degradation to a cheaper tier, and at a department ceiling the department admin i...  
  Evidence: Used-up budget stop is wired (budget_stop_store.judged, records BudgetStopRow, refuses with no degradation) but flag budget_enforcement ships off (needs 169 A). Admin warning is recorded (addressed_to) and not delivered: the module says delivery is the next change.  
  Next step: Deliver the recorded warning through the notice channel to the admin; owner switches the flag after a week of would-have-stopped rows; then check naming M21.2.5.
- **M21.2.6** Message naming which budget was hit and who can raise it  
  Evidence: The refused person gets SPENDING_LIMIT_REACHED (budget_stop_store), which deliberately names no budget and no person who can raise it; console.spend_view.told_about names level and period but has no caller. Leaf wording is narrowed by design with no needs item.  
  Next step: Raise a needs-rupash question on the narrowing, or call spend_view.told_about from the refusal path for readers entitled to it; then check.
- **M21.3.4** Most expensive agents and question shapes  
  Evidence: Most expensive agents: /report/spend dimension=agent ordered by cost. Question shapes: ops.spend_store.question_shape_report and spend_view.shape_report/dearest built (test_question_shapes) but have no route or page caller.  
  Next step: Add a route over question_shape_report (reader's grant filter already inside) and a SpendPage section; then check.
- **M21.4.2** Every spend row carries the trace id of the request it paid for, the trace records the request's tool count and fan-out, and the most exp...  
  Evidence: SpendActualRow.trace_id is recorded and telemetry records tool_count; shape join is spend_store.question_shape_report (no route). Fan-out is deliberately not recorded (telemetry docstring, item 59): nothing that finishes a request fans out.  
  Next step: Wire shape ranking (see M21.3.4); fan-out waits until an orchestrated run finishes through a point that records width; then check.
- **M21.4.3** Budgets are proved on an install: company, department, person and agent limits are set in the console, a request whose estimate exceeds a...  
  Evidence: Roll-up proof (a check can be written once clauses exist) across M21.1 and M21.2; several parts are unbuilt or unwired (department and user budgets M21.1.2/3, estimate refusal M21.2.1, enforcement flag off per needs 169 A, skill-body load check).  
  Next step: Waits on M21.1.2, M21.1.3, M21.2.1 and the owner switching budget_enforcement on (needs 169); then record the demonstration.
- **M21.4.4** The agent usage chart offers an all-time range beside seven, thirty and ninety days and month to date, and marks the incomplete current d...  
  Evidence: console.workspace.Range has 7d, 30d, 90d and mtd only; no all-time range and no marking of the incomplete current day in console/src/pages/agents/AgentDashboard.tsx or agentStats.ts.  
  Next step: Add Range.ALL_TIME to console/workspace.py and the period selector, and a partial-day marker on the last chart bar; then check.

### M21, Class 5: not code, owner or blocked (1)

- **M21.4.5** Every cost requirement in the requirements register is demonstrated on an install by a person, and each check is recorded against the req...  
  Evidence: Person-run demonstration of every cost requirement recorded against its row (register proof column M21.4.3 and M21.4.5); not code.  
  Waits on: Waits on M21.4.3 and the owner or a person running the checks.

### M21, Class 4: unbuilt (1)

- **M21.4.1** Metered spend for a billing period is reported per provider key in the provider's own units and reconciles with that provider's invoice w...  
  Evidence: No code reconciles spend to a provider invoice. models/pricing.py holds the install's own prices; no invoice figure input, tolerance or difference display found (grep invoice/reconcil in src).  
  Build: Build: per provider key billing-period total from spend_actual in provider units, an owner-entered invoice figure, tolerance setting, and a difference line on the Spend screen. Reuse models.pricing and spend_daily.

## M25 Retention, deletion, export, DSAR

### M25, Class 1: built and wired, only an install check is missing (7)

- **M25.1.1** Retention policy per data class  
  Evidence: ops.retention.HORIZONS/DataClass/Horizon, one per class, shown by GET retention controls (erasure_routes.retention_controls, kept_view); retention_policy_gaps self-checks. Tests test_retention, test_erasure_routes. No install check names it.  
  Next step: Write check naming M25.1.1 that reads the retention controls route and asserts every DataClass has a horizon and reason.
- **M25.1.2** Metadata ledger long retention  
  Evidence: HORIZONS has METADATA_LEDGER at 5 years (retention.METADATA_LEDGER_RETENTION_DAYS); obs.request_telemetry is partitioned monthly by ops.ledger_partitions run on the daily schedule; detach keeps rows, drop is not built. Policy is long, as the leaf says.  
  Next step: Write check naming M25.1.2 reading the retention controls route for the ledger horizon and the ledger report line.
- **M25.1.5** Automated enforcement with a report  
  Evidence: Daily sweep: schedule_runner.run_retention_sweep -> retention_store, report stored (ops.retention_report), served by GET /govern/retention, page Retention.tsx. Report proved on install for M32.1.1.3. Tests test_retention_store, test_retention_routes.  
  Next step: Write check naming M25.1.5 reading GET /govern/retention for a stored report that reaches every store with a not-reached reason where applicable.
- **M25.2.3** Backup deletion policy and its honest limits  
  Evidence: ops.erasure.Disposition, backup_horizon and BACKUP_RETENTION_DAYS; the screen text says a backup holds the data until it rotates out (erasure_routes.ERASING, install_routes copies_kept_days); needs 60 decided option A. Tests test_erasure, test_erasure_routes.  
  Next step: Write check naming M25.2.3 reading the retention controls and erasure screen text for the backup window and the stated limit.
- **M25.3.1** Conversation export per user  
  Evidence: POST /threads/{id}/export (thread_routes, member_activity.export_my_history) records an ExportAudit-style row and hands the person their own conversation; Ask.tsx button. Merged on main (migration 0207, test_thread_export_routes).  
  Next step: Write check naming M25.3.1 that asks, exports own thread, and reads the export record; note the other owner's thread is refused.
- **M25.4.1** The retention sweep first runs as a dry run that reports what it would delete, and deletes nothing until a person releases it from the co...  
  Evidence: Sweep is report-only until released: retention_store.run_retention_sweep(report_only), POST /govern/retention/release (needs the report named, ledgered by trigger), withdrawal route, RetentionActs.tsx. Tests test_retention_routes, test_retention_store.  
  Next step: Write check naming M25.4.1: read the report, assert nothing removed, release via the route, assert the ledger row.
- **M25.4.5** A configured trace destination receives redacted traces from an install, proved end to end.  
  Evidence: ops.ledger_export.LedgerShipper (app.py, destination_here) sends each finished request's masked trace to the install's Langfuse; install check a_run_sent_to_the_ledger_is_found_there_with_its_model_call (acceptance_checks_services.py:303) already proves it under M32.1.2.6.  
  Next step: Add M25.4.5 to that check's leaves=(...) if it asserts the payload is masked; otherwise add that assertion first.

### M25, Class 3: built but not wired (3)

- **M25.2.1** Subject access request assembling every store: rows, projections, memory, traces, recordings, backups  
  Evidence: ops.erasure.assemble and member_activity.stored_about_me (store by store, disposition per store) are built and tested but no route or page calls them; the data-transfer catalogue lists subject_access with runs=False (not available yet).  
  Next step: Add a subject access route over member_activity.stored_about_me wired to PostgresEraser.count_for per store (EstateEraser) and flip DataSet subject_access runs=True; then check.
- **M25.2.4** Deletion certificate with what was removed and when  
  Evidence: ops.erasure.Certificate and certify (with backup horizon) are built and tested but have no caller; drain_erasure_queue stores outcome and per-store counts on ops.erasure_request only, and erasure_routes.request_view carries no certificate or horizon.  
  Next step: Call certify in drain_erasure_queue, persist it on the request row (migration) and return it in request_view; then check.
- **M25.3.3** Knowledge export preserving scope metadata  
  Evidence: ops.export.knowledge_export keeps each item's scope and is tested (test_export) but has no caller; data_transfer catalogue knowledge runs=False (needs 108 decided: build it).  
  Next step: Wire knowledge_export into a data_transfer route (needs 108) reading know.item through the reader's scope; set runs=True; then check.

### M25, Class 2: partly built (6)

- **M25.1.3** Payload store thirty-day expiry  
  Evidence: Payload store = obs.trace_step, horizon 30 days (PAYLOAD_RETENTION_DAYS, test_retention) and reported daily by the sweep. But migration 0150 grants brain_app INSERT only, so PostgresSweeper.removal_rule queues those rows and never deletes them.  
  Next step: Build the removal: a job or role that deletes (or partitions and drops) obs.trace_step past 30 days with the release gate and hold check; then write the check.
- **M25.1.4** Trace and recording lifecycle  
  Evidence: Trace window declared (tracing.RETENTION, 30d) and daily retention report reaches the trace store (proved for M32.1.1.3, #328). Recording lifecycle is only the recordings bucket rule (storage.BUCKETS 30d); trace_step has no DELETE grant so nothing is removed.  
  Next step: Same removal as M25.1.3 for traces; call browsing.recording.remove_expired from a worker (see M25.4.3); then check naming M25.1.4.
- **M25.2.2** Deletion propagating to cache, index, memory and projection  
  Evidence: The queue (erasure_store.drain_erasure_queue via schedule_runner, EstateEraser) erases rows, projection, knowledge and memory (plus session memory and own vault tokens). Cache, index, recordings and attachments are NOT reached (NO_CACHE_ERASER, NO_INDEX_ERASER, NO_OBJECT_STORE_ERASER; erasure_routes ERASING text).  
  Next step: Build erasers for the answer cache and retrieval index, and an object-store eraser over ops.object_store; pass them as objects= in schedule_runner; then check.
- **M25.3.2** Bulk export for eDiscovery with an audit row and a required reason  
  Evidence: Audit-trail export demands a reason and writes an audit row (data_transfer_routes.take_export, ExportReason, ops.data_export_store; listed by GET /govern/retention/exports). The bulk store collection for eDiscovery (ops.export.bulk_export, BulkExportRequest) has no caller; catalogue bulk_collection runs=False.  
  Next step: Add a route that runs ops.export.bulk_export over named stores and people with reason and reference, write the ExportAudit row, set bulk_collection runs=True; then check.
- **M25.4.2** Retention and erasure are proved on an install: the retention sweep reports a dry run and removes nothing until released, a subject acces...  
  Evidence: Roll-up proof (a check can be written once clauses exist) across M25.1 to M25.3; parts are unbuilt (subject access M25.2.1, certificate M25.2.4, cache/index/object erasure M25.2.2, bulk and knowledge export M25.3.2/3, trace row removal M25.1.3).  
  Next step: Waits on those leaves, then a person runs the demonstration and the checks are recorded.
- **M25.4.3** A per-object sweep removes every stored artifact past its retention class's window, records each removal, and leaves an object under a le...  
  Evidence: browsing.recording.remove_expired(backend, today, held_runs) removes recordings past 30 days and skips held runs (tested) but nothing calls it; other buckets rely on lifecycle rules which retention_store says nothing verifies; no per-object sweeper over ops.object_store.  
  Next step: Add an object sweeper over ops.object_store.list_objects with ages, call it from schedule_runner behind the release gate with the hold check and a removal record per object.

### M25, Class 5: not code, owner or blocked (1)

- **M25.4.4** Every data and retention requirement in the requirements register is demonstrated on an install by a person, and each check is recorded a...  
  Evidence: Person-run demonstration of every data and retention requirement recorded against its row; not code.  
  Waits on: Waits on M25.4.2 and a person running the checks.

## M26 Joiner, mover, leaver

### M26, Class 1: built and wired, only an install check is missing (9)

- **M26.1.1** Provisioning from the identity provider  
  Evidence: Provisioning is done by the scheduled staff sync (ops.staff_sync_run via schedule_runner, staff_accounts_run makes accounts, staff_people_run writes members), not by identity.lifecycle.provision (no caller). Staff sources screen and routes; tests test_staff_sync_routes. Checks name M1.6.x only.  
  Next step: Write check naming M26.1.1 that runs a sync over a seeded roster and reads the new principal and its account row (reuse acceptance_checks_accounts.py harness).
- **M26.1.2** Role and starter capability pack assignment  
  Evidence: ops.starter_pack_store.grant_starter_packs is called by staff_sync_run and gives each joiner the Starter pack for their department (decided needs 105); role from directory groups via identity.group_sync. Tests test_starter_pack_sync. Check M1.6.20/21 touches the step.  
  Next step: Add M26.1.2 to the leaves of the accounts check that covers the Starter pack step (acceptance_checks_accounts.py:420) or write one reading the grant.
- **M26.1.3** Department assignment with scope  
  Evidence: starter_pack_sync.starter_plan scopes the pack to the person's registered department (department_scope), applied by starter_pack_store from staff_sync_run; a mover has it moved, a leaver has it ended. Test test_starter_pack_sync.  
  Next step: Check naming M26.1.3 that syncs a person into a department and reads the grant's scope; reuse the accounts check harness.
- **M26.2.1** Entitlement re-resolution on the next request  
  Evidence: Grants are read per request (gate.held_grants, disabled principal counts none) and the cache key carries the entitlement hash, so a move shows on the next request; existing check M6.5.2 (acceptance_checks_cache.py:116) shows a moved person is not served the old answer. lifecycle.Move is unwired.  
  Next step: Add M26.2.1 to the leaves of that M6.5.2 check, or write a check that moves a person and asks at once.
- **M26.2.4** Cached answers unreachable by construction  
  Evidence: Answer cache key includes the entitlement hash (gate.answer_cache, cache_key); check M6.5.2 shows a person who moved department was refused the cached answer (acceptance_checks_cache.py:196). Test test_answer_cache.  
  Next step: Add M26.2.4 to that check's leaves=(...).
- **M26.2.6** Knowledge access changing with no reindex  
  Evidence: Knowledge reach is applied at query time from the reader's grants (knowledge.search scope, starter_pack_sync moves the pack with the person); nothing reindexes on a move. Test test_starter_pack_sync and knowledge scope tests.  
  Next step: Check naming M26.2.6: move a person between departments with no reindex job and assert search results change; reuse the people and knowledge check helpers.
- **M26.3.1** Immediate disable with session termination  
  Evidence: POST /govern/people/disable (principal_state_routes) sets disabled_at; migration 0003's trigger ends every session and grants go inert; the staff sync disables leavers via ops.standing_run (check M1.6.14). identity.lifecycle.disable is the unwired in-memory twin.  
  Next step: Write check naming M26.3.1: disable a signed-in person, assert the next request is refused and the session row ended (acceptance_checks_accounts.py has the harness).
- **M26.3.2** Owned agents flagged for adoption  
  Evidence: ops.staff_sync_run calls stop_leavers_agents in the leaver's run (M1.8.9); staff_source_routes lists agents_for_adoption and adopt; Transfers.tsx page; tests test_staff_connect, test_staff_sync_routes. Adoption is by the department admin.  
  Next step: Write check naming M26.3.2: mark a leaver with an agent, assert the agent is disabled and appears in transfers, adopt it.
- **M26.3.3** Automations suspended  
  Evidence: ops.automation_owner.standing_of returns AWAITING_OWNER when the owner is not active; automation_run_store.owner_live refuses an owner_gone run; automations_routes may_adopt lets a new owner take it. Check M32.6 covers other clauses.  
  Next step: Write check naming M26.3.3: disable the owner of a seeded automation, assert it does not run and is listed as awaiting an owner.

### M26, Class 3: built but not wired (3)

- **M26.1.4** Welcome path with three department-scoped starter questions  
  Evidence: identity.lifecycle.welcome_questions and adoption.starter_questions (three department-scoped questions) are built; only ops.guide_docs imports the latter and nothing imports guide_docs. Ask.tsx says it suggests no question before the first ask.  
  Next step: Serve welcome_questions from a route for the signed-in person's department, from entities that indexed, and show them on the first Ask screen (Ask.tsx empty state).
- **M26.2.3** Delegations re-evaluated and suspended rather than narrowed  
  Evidence: identity.lifecycle.reevaluate_delegations (suspend, never narrow) and Reconfirmation are built and tested but no caller; no delegation table or route exists on main (grep delegation in tables and routes). Nearest live object is an automation owner (M26.3.3).  
  Next step: Decide what a delegation is on this install (elevation, automation owner or a new object), then call reevaluate_delegations from the sync run when a move changes reach.
- **M26.3.4** Personal knowledge and memory disposition policy  
  Evidence: identity.lifecycle.departure_disposition (per Store) and member_activity.DeletionRoute are built but have no route or job caller; nothing applies a leaver's memory or personal knowledge disposition when the sync marks them.  
  Next step: Call departure_disposition from the leaver step of staff_sync_run and record each disposition; surface it on the Transfers page.

### M26, Class 2: partly built (2)

- **M26.2.2** Personal agents following the person  
  Evidence: Personal agents follow the person by construction: E_run is the caller's reach intersected with the agent ceiling (gate.leash.decide), so a moved owner's agent reaches the new department. lifecycle.agents_following has no caller. Not verified that a personal agent's audience record updates on a move.  
  Next step: Check naming M26.2.2: move an owner, call their personal agent, assert old-department knowledge is not reached; fix the agent audience if it fails.
- **M26.4.1** Joiner, mover and leaver handling is proved on an install: a person moved between departments loses the old department's knowledge, agent...  
  Evidence: Roll-up proof (a check can be written once clauses exist) across joiner, mover and leaver; clauses depend on unwired parts (delegations M26.2.3, personal knowledge disposition M26.3.4, ended grant mid-run, external person end date).  
  Next step: Waits on M26.2.3 and M26.3.4, then a person runs it and the checks are recorded.

### M26, Class 5: not code, owner or blocked (1)

- **M26.2.7** Test covering every one of the above  
  Evidence: Roll-up test leaf: tests/unit/test_lifecycle.py covers the pure module, but several clauses it covers (provision, delegations, welcome) are not wired, so a test of every item above has nothing end to end to run.  
  Waits on: Waits on M26.1.4, M26.2.3 and M26.4.1 wiring; then write the end-to-end test.

## M29 Extension points

### M29, Class 1: built and wired, only an install check is missing (1)

- **M29.3.1** Modularity is proved on an install: a connector for a new API and a new channel record are added and switched off from the console with n...  
  Evidence: Clauses have checks: new-API connector live with no release (acceptance_checks_custom_connector.py, M11.7.8); channel off refuses inbound (acceptance_operations_console_4.py:239); a console setting says when it applies (acceptance_operations_console.py:472). Not verified: vendor adapter replaced with no deploy.  
  Next step: Write a roll-up check naming M29.3.1 over those checks (pattern acceptance_roll_up.clauses_demonstrated); add a clause check for a replaced provider key taking effect with no deploy.

### M29, Class 3: built but not wired (12)

- **M29.1.2** Connector and tool provider interface  
  Evidence: plugins.points entry connector names contract brain.connectors.contract:ConnectorFetch (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. Console connectors (M11.7.8) are separate.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.1.3** Skill interface  
  Evidence: plugins.points entry skill names contract brain.tools.skills:Skill (exists), tier sandbox; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.1.4** Template interface  
  Evidence: plugins.points entry template names contract brain.agents.template:TemplateManifest (exists), tier in_process; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.1.5** Model provider interface  
  Evidence: plugins.points entry model_provider names contract brain.models.driver:ModelDriver (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.1.7** Field classifier interface  
  Evidence: plugins.points entry field_classifier names contract brain.ops.pii:Recogniser (exists), tier sandbox; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.1.12** Notification sink interface  
  Evidence: plugins.points entry notification_sink names contract brain.ops.digest_delivery:DigestSender (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader.  
  Next step: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.
- **M29.2.1** Manifest schema: identity, version, required capabilities, config schema, core compatibility range  
  Evidence: plugins.manifest (PluginManifest, manifest_from, PLUGIN_ID_RE, refuses reach keys; core compatibility range) is built and tested (test_plugins_manifest); only ops.plugin_registry and tables.plugin import it, and no route accepts a manifest.  
  Next step: Add an install route that parses an uploaded manifest with manifest_from and records it via plugin_registry; then check.
- **M29.2.2** Registry tables  
  Evidence: Migration 0032, tables.plugin (PluginInstallRow, PluginVersionRow) and ops.plugin_registry (remember, save, records, one document per version) are built and tested (test_plugin_registry); nothing calls plugin_registry.  
  Next step: Call plugin_registry from a plugin install route and the Features and plugins page; then write a check naming M29.2.2.
- **M29.2.3** Install, enable, disable, upgrade, rollback  
  Evidence: plugins.lifecycle (install, enable, disable, upgrade, rollback, assert_transition; nothing arrives enabled) is built and tested (test_plugins_lifecycle); only ops.plugin_registry calls assert_transition, and no route or page drives a transition.  
  Next step: Expose transitions as routes over plugin_registry (admin authority, ledgered) and buttons on the Features and plugins page.
- **M29.2.4** Drain on upgrade so in-flight work finishes on the old version  
  Evidence: plugins.lifecycle models the drain (in-flight work finishes on the old version) and is tested, but there are no plugin runs to drain: no loader, and no route upgrades a plugin.  
  Next step: Build with M29.2.3 plus the host: count in-flight calls per plugin version and block the switch until they finish.
- **M29.2.5** Isolation tier per point: in-process, sidecar, sandbox  
  Evidence: plugins.points gives each plugin point a tier (in_process, sidecar, sandbox) and structural rules (code never runs in process); tested in test_plugins_points. No host enforces a tier because no plugin is loaded.  
  Next step: Enforce the tier in the plugin host when it exists (sidecar or sandbox runner reuse brain.tools sandbox); until then nothing to check on an install.
- **M29.2.6** Core contract test: a plugin cannot see an unredacted result it did not produce, and cannot widen entitlements  
  Evidence: plugins.contract checks a plugin cannot see an unredacted result it did not produce and cannot widen entitlements (uses EntitlementSet.intersect); tested in test_plugins_contract. Nothing calls it: brain.plugins has no importer outside the registry.  
  Next step: Call plugins.contract from the host before every plugin call; then write a check with a stand-in plugin asserting both properties.

### M29, Class 5: not code, owner or blocked (1)

- **M29.3.2** Every modularity requirement in the requirements register is demonstrated on an install by a person, and each check is recorded against t...  
  Evidence: Person-run demonstration of every modularity requirement recorded against its row; not code.  
  Waits on: Waits on M29.3.1 and a person running the checks.

## M34 Onboarding and adoption

### M34, Class 1: built and wired, only an install check is missing (1)

- **M34.2.2.3** Unanswered question log as the connector roadmap  
  Evidence: adoption.connector_demand is called by console.questions_view over question_gap_store rows and served at GET /report/questions, QuestionsPage.tsx, scoped to the reader's departments. Check acceptance_people_console_3 touches the screen under other leaves.  
  Next step: Write check naming M34.2.2.3: ask a question no source answers, read /report/questions and assert a connector demand line.

### M34, Class 3: built but not wired (8)

- **M34.1.1.1** First connector chosen so a real question is answerable before any document is uploaded  
  Evidence: adoption.first_connector (picks the connector that answers a real question before any upload) is built and tested (test_adoption) but nothing outside adoption.py calls it; no setup or Connectors page recommends a first connector.  
  Next step: Call first_connector from the setup wizard's connector step or the Connectors screen's empty state, over ConnectorOffer rows from the manifests.
- **M34.1.1.2** Three department-scoped starter questions generated from what actually indexed  
  Evidence: adoption.starter_questions (three department-scoped questions from entities that actually indexed) is built; its only importer is ops.guide_docs, which nothing imports. Ask.tsx suggests no question before the first ask.  
  Next step: Serve starter_questions from a route for the signed-in person's department (reader-scoped) and render them in the Ask empty state.
- **M34.1.2.1** Per-scope statement: record counts and last sync  
  Evidence: adoption.coverage_report/ScopeCoverage (records and last sync per department and source) is built; no route or page calls it. Connectors screens show per-source status, not a per-scope statement; department_view_routes coverage is knowledge freshness.  
  Next step: Add a per-department coverage route over connector sync state feeding adoption.coverage_report and show it on Adoption or Departments.
- **M34.1.2.3** Shopping list for the champion rather than a progress bar  
  Evidence: adoption.shopping_list (actions for the champion, not a progress bar) is built and tested; nothing outside adoption.py calls it (locale.py only names its two work kinds).  
  Next step: Add it to the Adoption page for a champion, fed by coverage_report; reader-scoped.
- **M34.2.1.1** Each department lead verifies five documents in week one  
  Evidence: adoption.verification_targets (five documents per department lead in week one) is built; no route, task or page uses it. knowledge.verification tasks exist separately for re-verification.  
  Next step: Create the week-one verification tasks from verification_targets through the knowledge tasks route when a department lead is placed.
- **M34.2.2.2** Wrong-sources feedback distinct from wrong-answer, so retrieval and reasoning bugs separate  
  Evidence: ops.feedback.FlagReason.WRONG_SOURCES vs WRONG_FACT, plane_of and by_plane are built and tested (test_flag_planes); flag_answer is called only by the unwired channels.correction, and no route or console control files a flag.  
  Next step: Add a flag route (POST on an answer's trace with a FlagReason) and a console control, or wire channels.correction; then check.
- **M34.3.1.1** What it can and cannot see, in plain language  
  Evidence: adoption.visibility_summary (what it can and cannot see, plain language, from the reader's reach) is built and tested; no route or page calls it.  
  Next step: Serve it from a route for the signed-in person (reach-scoped) and link it from Ask or My workspace.
- **M34.3.1.2** The privacy posture stated openly  
  Evidence: adoption.privacy_posture reads the install's configuration into plain sentences and is tested (test_adoption); no route or page calls it (locale.py names its keys only).  
  Next step: Serve privacy_posture on a staff-facing page or Ask help panel; reader needs no grant.

### M34, Class 2: partly built (6)

- **M34.1.1.3** Answers verifiable against a system the client already trusts  
  Evidence: Answers carry citations to the source record (provenance, cited_document_routes, CitedDocument.tsx). adoption.verification_targets, which picks what a person can check in a system they already trust, has no caller.  
  Next step: Call verification_targets from the answer view so each answer names where to verify it, or confirm citations already satisfy the leaf and write the check over them.
- **M34.1.2.2** Explicit not-connected state per department  
  Evidence: adoption.Coverage.NOT_CONNECTED per department is unwired; the Connectors dashboard already shows a source as Not connected (ConnectorDashboard.tsx NOT_CONNECTED_TITLE) but per source, not per department.  
  Next step: Show the per-department state through coverage_report (see M34.1.2.1).
- **M34.2.2.1** Correction path in every channel  
  Evidence: Chat marks (helpful or unhelpful) are wired in channels: marks.mark_line in chat_answer and read_mark in channels.inbound. The reason-bearing path channels.correction (send_with_correction, read_correction, file_correction) has no caller.  
  Next step: Call send_with_correction where adapters send an answer and read_correction in channels.inbound; then check naming M34.2.2.1 per channel.
- **M34.3.1.3** How to ask well, with examples from their own department  
  Evidence: docs/guides/asking-well.md exists with per-department examples marker; ops.guide_docs.asking_examples and asking_gaps check it (test_guide_docs). Nothing imports guide_docs and no route serves the guide to staff.  
  Next step: Serve the guide from a help route that fills the examples marker with asking_examples for the reader's department.
- **M34.3.2.1** Runbook per console screen  
  Evidence: 36 runbooks exist in docs/console/runbooks and launch.screen_runbook_gaps and guide_docs.runbook_gaps sweep them against the screen registry (test_guide_docs). No route or page serves them; docs_routes serves only the build pages.  
  Next step: Add a help route serving docs/console/runbooks per screen and a link on each console page (see M34.4.1).
- **M34.4.1** The runbooks for every console screen and every alert, and the incident playbook, are served from the install's own help pages, and a swe...  
  Evidence: Runbooks per screen exist (36 files) with a gap sweep (launch.screen_runbook_gaps); alert runbooks via ops.controls.runbook_gaps. The incident playbook is a Python table (ops.reliability.MATRIX) nothing renders, and no help route serves any of it.  
  Next step: Build GET help pages serving runbooks, alert runbooks and a rendered playbook; extend the sweep to fail when a screen or alert has none.

### M34, Class 5: not code, owner or blocked (2)

- **M34.3.3.3** Upgrade and rollback procedure  
  Evidence: Document leaf: docs/install/update-and-rollback.md (275 lines) exists, held to the code by ops.install_docs and tests; release.py references it. Closing needs an operator to run an upgrade and a rollback on a server, or Proved-in-ci naming the guard test.  
  Waits on: Waits on a person rehearsing upgrade and rollback on the install, or a Proved-in-ci line.
- **M34.3.3.4** Restore drill procedure  
  Evidence: Document leaf: docs/install/restore-drill.md (360 lines) exists, guarded by tests/unit/test_install_drill_page.py; the recovery screen says no control runs a drill (install_routes.NO_CONTROL_HERE_RUNS_A_REHEARSAL). The drill itself is run by hand on the server.  
  Waits on: Waits on a person running the drill on the install (needs-rupash style server step); record via the drill record the screen reads.

## M35 Localisation and accessibility

### M35, Class 1: built and wired, only an install check is missing (11)

- **M35.1.2.1** CJK tokenisation for lexical search so Chinese queries do not silently retrieve worse  
  Evidence: knowledge.search lexical_legs and knowledge.chunk_store write know.chunk.cjk via chunk_text_fields (migration 0024); query side runs in the document search tool; ingest runs in the worker (ingest_queue.register_ingest_tasks). Test test_search.  
  Next step: Write check naming M35.1.2.1: ingest a Han-text document through the queue, query it in Chinese as a person who may read it, assert it is found.
- **M35.1.2.2** Mixed-language document handling  
  Evidence: search.chunk_text_fields tokenises every script in a chunk into cjk and detects the dominant language, and lexical_legs chooses legs per script in the question, so a mixed document is found by queries in either language. Tests test_search, test_locale.  
  Next step: Write check naming M35.1.2.2 ingesting a mixed English and Chinese document and asking in each language.
- **M35.1.2.3** Language detection on ingest recorded as metadata  
  Evidence: chunk_store.ingest_document writes know.chunk.language from locale.detect via chunk_text_fields (None when too little text); column from migration 0024. Test test_search.  
  Next step: Write check naming M35.1.2.3 that ingests one English and one Chinese document and reads know.chunk.language.
- **M35.2.1.1** Screen-reader-safe streaming: no naive aria-live on a token stream  
  Evidence: console/src/pages/Ask.tsx keeps the answer out of any live region and only progress steps use role=status; locale documents why. Tests console/tests/ask-page.test.tsx and skip-to-answer.test.tsx. Not shown under a real screen reader on an install.  
  Next step: Browser run on the install under a screen reader (or a console test over the served bundle) naming M35.2.1.1; no Python check can prove it.
- **M35.2.1.2** Announce on completion, not on every token  
  Evidence: Ask.tsx returns focus to the skip control when the answer finishes (FOCUS_IS_RETURNED_AND_NEVER_TAKEN), the one announcement; test skip-to-answer.test.tsx. locale.announcements is unused by the console. Not observed in a browser on the install.  
  Next step: Same browser run as M35.2.1.1; add M35.2.1.2 to the console test's Task ids and record the install run.
- **M35.2.1.3** Skip-to-answer control  
  Evidence: Ask.tsx SKIP_TO_ANSWER button after the form focuses the answer region; console test skip-to-answer.test.tsx exists and names the leaf. Label is English only (answer.skip_to is in the catalogue).  
  Next step: Browser run on the install asking a question and pressing the control; record it against M35.2.1.3.
- **M35.2.2.1** Keyboard navigation across the console  
  Evidence: Native controls, a skip link and console/scripts/check-boundaries rules run in CI; console/tests/keyboard-access.test.tsx renders pages and asserts tab order (names M35.2.2.1). jsdom only; not observed on the served console.  
  Next step: Browser run on the install tabbing through the shell, a list and a form; record against M35.2.2.1 (see M35.4.1).
- **M35.2.2.2** Visible focus states  
  Evidence: A focus-visible ring is defined in the theme tokens and CI refuses outline none; keyboard-access.test.tsx asserts it in both themes (names M35.2.2.2). Not seen on the served console.  
  Next step: Browser run in both themes on the install; record against M35.2.2.2.
- **M35.2.2.4** Form labels and error association  
  Evidence: 58 console files set aria-describedby and 39 aria-invalid; forms use SchemaForm with locale.form_gaps behind the setup wizard; unit tests assert labels. No test or run names M35.2.2.4 and none shows an error on the served console.  
  Next step: Browser run submitting an invalid value in a console form; add the leaf id to the form test's Task ids.
- **M35.3.1.1** Console usable on a phone for approvals at minimum  
  Evidence: Approvals.tsx and approvals/ApprovalCard.tsx with phone layout (console/tests/approvals-phone.test.tsx, approvals-page.test.tsx); POST decide route (approval_routes). Suspensions are now raised by held agent runs and knowledge promotions. Not run on a phone against the install.  
  Next step: Install run: raise an approval, open the console at phone width, decide it; record against M35.3.1.1.
- **M35.3.2.1** Installable shell  
  Evidence: console/public/manifest.webmanifest and index.html link it; console_static serves unhashed files at the root; console/tests/installable-shell.test.ts asserts it (names the leaf). No service worker is claimed.  
  Next step: Write a check naming M35.3.2.1 that GETs /manifest.webmanifest from the install and asserts start_url, scope, icons and name; an install prompt in Chrome is the person's half.

### M35, Class 2: partly built (7)

- **M35.1.1.1** English and Simplified Chinese interface strings  
  Evidence: locale.MESSAGES holds en and zh-Hans (67 keys, catalogue_gaps tested) but only the setup wizard and data_steward_routes call text(); the served console draws English strings from TSX (CONSOLE_LANGUAGE en-GB) with no locale switch; enabled_locales and default_locale have no caller.  
  Next step: Add a locale choice (INSTALL_LOCALES) to the console shell and move console strings to the catalogue; start with Ask and Approvals; then a browser check in zh-Hans.
- **M35.1.1.2** Locale-aware dates, numbers and currency  
  Evidence: currency (locale.currency_or_unset) and time_zone are used by routes and workers; format_date, format_timestamp, format_number and format_money have no caller, and console dates use the browser default (Intl en-GB in spendQuery.ts).  
  Next step: Serve install-formatted dates, numbers and money from the API or a shared console formatter reading INSTALL_LOCALES; then a check on a Spend figure in zh-Hans.
- **M35.1.1.3** Right-to-left readiness deferred with a stated trigger  
  Evidence: locale.RIGHT_TO_LEFT deferral with trigger is defined, and rules_for refuses an RTL tag with its reason; but console.configuration._locales_problem swallows the LocaleError into a generic sentence, and locale_facts and triggered have no caller.  
  Next step: Pass the deferral's sentence through the settings refusal and report triggered() on the Install screen; then write the check (also M35.4.3).
- **M35.3.2.2** Push for approvals, deferred with a stated trigger  
  Evidence: locale.PUSH_FOR_APPROVALS with Trigger.APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS and PUSH_IS_DUE_ABOVE_HOURS=4 is defined and tested; triggered() has no caller and nothing measures approval waits, so the trigger can never fire.  
  Next step: Build the wait measurement (see M35.4.5) and call locale.triggered from the report; that completes this leaf.
- **M35.4.3** Choosing a right-to-left locale in the console or at setup is refused with a sentence naming the deferral, proved in the browser  
  Evidence: rules_for raises LocaleError carrying locale.RIGHT_TO_LEFT.reason for an RTL tag, but console.configuration._locales_problem replaces it with a generic sentence, so the console refusal does not name the deferral; setup path not verified.  
  Next step: Return the deferral sentence from _locales_problem and the wizard; then a browser run or a settings route check naming M35.4.3.
- **M35.4.5** The install measures how long each approval waited before a decision, and when the typical wait passes the stated hours the console repor...  
  Evidence: Only the constants exist: locale.PUSH_IS_DUE_ABOVE_HOURS and the deferral. Suspension rows carry raise and decide times but nothing computes a typical wait or reports that push is due.  
  Next step: Add a read over gate.suspension (raised to decided) giving the median wait, show it on Approvals or Install, and call locale.triggered; then a check.
- **M35.4.6** At phone width every touch target is at least 44px and no element is wider than 320px, across every console page  
  Evidence: console/tests/phone-width.test.tsx asserts the cascade for every registered route at 360px (wrapping, link height) but the file says it cannot measure widths; no 44px target or 320px width measurement exists.  
  Next step: Add a headless browser measurement (iframe at 320px as the test's author did) over every route and assert 44px targets and no overflow; or relax to the measured figures and ask.

### M35, Class 5: not code, owner or blocked (3)

- **M35.4.1** Each console module is proved in the browser operable by keyboard alone, with visible focus and every form error associated with its fiel...  
  Evidence: Needs a browser run of every console module by keyboard, with focus and errors seen. The repo has jsdom tests (keyboard-access.test.tsx, phone-width.test.tsx) and docs/console-audit but no browser job; person or agent browser run on the install.  
  Waits on: Waits on a browser run over the install after M35.2.2.x are exercised; a person or the owner's browser tools record it.
- **M35.4.2** Language and assistive use are proved on an install: a Chinese query and a mixed-language document retrieve correctly, local names and id...  
  Evidence: Roll-up proof; clauses unmet: console is English only (M35.1.1.1, M35.1.1.2 unwired) and a screen-reader run is a person's. Retrieval clauses (M35.1.2.x) and names for redaction (acceptance_checks_names.py) are provable by checks.  
  Waits on: Waits on M35.1.1.1 and M35.1.1.2, then a person runs it under a screen reader.
- **M35.4.4** Every localisation and accessibility requirement in the requirements register is demonstrated on an install by a person, and each check i...  
  Evidence: Person-run demonstration of every localisation and accessibility requirement recorded against its row; not code.  
  Waits on: Waits on M35.4.1 to M35.4.3 and a person running them.

## M40 Member self-service application

### M40, Class 1: built and wired, only an install check is missing (20)

- **M40.1.1.1** Single sign-on through Keycloak with the same identity the channels use  
  Evidence: Real sign-in is identity.oidc/principal_directory via api_routes.asking and sign_in_routes, the same directory the channels use; acceptance_people_signed_in already signs a reserved person through real asking. member.shell.sign_in itself has no caller. Test: test_member_shell.  
  Next step: write check naming M40.1.1.1 that signs the reserved person in via acceptance_people_signed_in and reads GET /api/v1/me
- **M40.1.1.2** Channel identity and web identity resolved to one principal, never two  
  Evidence: channels.binding mints a code only inside a live sign-in (binding_routes POST /me/channels/{name}/code) so channel and web resolve to one principal row; member.shell.one_principal is uncalled but the route enforces it. Tests: test_member_shell, binding tests.  
  Next step: write check naming M40.1.1.2: bind a channel via MY_CODE_PATH then assert the binding principal equals the session principal
- **M40.1.1.4** Password reset and recovery handled by the identity provider, not by us  
  Evidence: Recovery is Keycloak's: identity/staff_accounts and connectors/sign_in_accounts say Forgot password on the sign-in page; no credential field exists in the product. acceptance_checks_accounts forgot-password check names M40.7.1. member.shell.recovery_handoff has no caller.  
  Next step: add M40.1.1.4 to the leaves of the forgot-password check in acceptance_checks_accounts.py (or a check asserting the product exposes no password route)
- **M40.1.1.5** Explicit test that a channel-only user can sign in and sees the same entitlement  
  Evidence: Unit test test_member_shell::test_a_channel_only_person_signs_in_on_the_web_and_holds_the_same_entitlement passes over fakes. Path is real: sign_in_binding.SignInBindings.bind plus the directory resolve the same principal. No install check.  
  Next step: write check: person with only a channel binding gets a token bound via SignInBindings.bind, calls GET /me, and holds the same reach as the binding path (use acceptance_people_signed_in)
- **M40.1.2.1** Member navigation distinct from the admin console and much shorter  
  Evidence: The one SPA serves a short own-work menu (console routes ownWork: Ask, My workspace, My approvals, Records, Access requests, Referred to me) and navigation_routes returns a department console with nothing in it to a member. member.shell.member_navigation has no caller.  
  Next step: write check naming M40.1.2.1: GET /api/v1/navigation as a member-only reader returns no governance section
- **M40.1.2.2** No administrative surface reachable by URL guessing, enforced server side  
  Evidence: Server side: every console route asks console.reads.permitted; member grant opens only member screens (member.shell.MemberScreen refuses governance capabilities; acceptance_checks_governance uses member_screen). serve() has no caller but the per-route check is the enforcement. Test: test_member_shell.  
  Next step: write check naming M40.1.2.2: as a member-only reader request several /govern/* and /console/* routes and expect the one refusal
- **M40.1.2.3** Responsive down to a phone since approvals arrive on phones  
  Evidence: Phone-first approvals page: console/src/pages/approvals/ApprovalCard.tsx and ApprovalsPage.tsx (min-h-11, phone base case), tests console/tests/approvals-phone.test.tsx and phone-width.test.tsx. pages/Approvals.tsx is only the re-export. Only a browser can show it on an install.  
  Next step: a browser run at 375 px on the install (person-run or headless) naming M40.1.2.3; a Python check can at most assert the served bundle carries the phone rules
- **M40.1.2.4** Entitlement disclosure line rendered from the real entitlement set, never hand-written  
  Evidence: member.shell.disclosure_line is called by mine_routes (GET /me/workspace can_ask_about) and built from the grants. Test: test_member_shell, test_mine_routes.  
  Next step: write check naming M40.1.2.4: GET /me/workspace for two readers with different grants and compare can_ask_about
- **M40.2.1.2** Agents this person can call, split between department-provided and self-built  
  Evidence: GET /me/workspace lists agents with provision (provided vs personal) from member_activity.my_agents; MyWorkspace.tsx shows PROVISION_WORDS and how many are the person's own. Test: test_member_activity, test_mine_routes.  
  Next step: write check naming M40.2.1.2 over GET /me/workspace with one personal and one department agent
- **M40.2.1.4** Count of things learned about this person, each reversible  
  Evidence: MyWorkspace learned list (mine_routes MineLearnedView from estate_routes.remembered_about, subject_memory) with Forget/Edit per item (POST /me/memory/forget, /me/memory/edit, /me/learning/undo). No separate count figure but the list length is shown. acceptance for undo exists under M16.  
  Next step: write check naming M40.2.1.4: form a memory from the person's words, read it on /me/workspace, forget it, read again
- **M40.2.2.1** List with source, where each one runs and how often this person used it  
  Evidence: GET /me/workspace agents rows carry provision, channels (where each runs, offered_channels at the person's run reach) and uses over 30 days (my_agents). Test: test_member_activity.  
  Next step: write check naming M40.2.2.1 reading GET /me/workspace for an agent used twice
- **M40.2.2.4** Personal agent visible to nobody else unless explicitly shared  
  Evidence: PERSONAL audience is enforced: agents.model.visible_agent_ids narrows every agent route; agents.creation makes a new agent visible to its maker only; member_activity.personal_audience offers nothing wider; publication to department/company is the explicit act in agent_lifecycle_routes. Tests: test_member_activity, agent tests.  
  Next step: write check naming M40.2.2.4: create an agent as person A, list agents as B (absent), publish to department, B sees it
- **M40.3.1.1** Items this person uploaded with visibility scope, verification date and review due  
  Evidence: GET /knowledge/items (knowledge_lifecycle_routes.looked_after) lists the person's own documents with level, review date, due flag, verification and promotion state; MyWorkspace shows knowledge rows. Tests: knowledge lifecycle tests. member_library.my_library has no caller but the route does the job.  
  Next step: write check naming M40.3.1.1: upload as person A, read GET /knowledge/items, assert review date and verification fields
- **M40.3.1.4** Request promotion to company-wide, routed as a tier three decision  
  Evidence: POST /knowledge/items/{id}/promotion (knowledge_lifecycle_routes) calls member_library.request_promotion and promotion_tier; the request waits on the Approvals screen at the blast-radius tier. acceptance_checks_lifecycle already imports member_library for related leaves.  
  Next step: write check naming M40.3.1.4: verify then request promotion, assert it appears on the approvals queue at tier three
- **M40.3.1.5** Never shows an item outside this person's entitlement, including their own department's restricted rows  
  Evidence: knowledge_lifecycle_routes Authority.may_see and know.item row-level security decide every list; mine_routes narrows by is_own plus items_stewarded_by_the_session. Tests exist; member_library.reachable_own_items has no caller.  
  Next step: write check naming M40.3.1.5: a person in a department with a restricted row does not see it in GET /knowledge/items
- **M40.5.1.1** Personal account connections with per-source consent  
  Evidence: GET /me/accounts and POST /me/accounts/{connector}/consent (connector_routes) give per-source, per-person OAuth consent into the person's own vault slot; acceptance_checks_oauth exercises two persons. member.connections.connect has no caller.  
  Next step: write check naming M40.5.1.1 or add it to the person-consent check in acceptance_checks_oauth.py
- **M40.5.1.2** Explicit copy stating that connecting an account never widens what the person may see  
  Evidence: connector_routes MyAccountsView.told = CONNECTING_YOUR_OWN_ACCOUNT (never widens what you can see) and mine_routes ACCOUNTS_ARE_NOT_READ_HERE; reach is independent of connections by construction. Test: test_member_connections.  
  Next step: write check naming M40.5.1.2: GET /me/accounts text present and reach hash unchanged after a consent
- **M40.6.1.1** Envelope approvals awaiting this person, with what will happen stated before the fact  
  Evidence: Approvals screen does it: approval_routes GET /approvals (cards with the request rendered by gate.approval_request.render_request at the approver's reach), console Approvals page, console.approvals.card. member.approvals has no caller (effect_sentence is used by agent_profile). Tests: test_approval_routes.  
  Next step: write check naming M40.6.1.1 over GET /approvals for a seeded suspension (acceptance_checks_console_approvals has the setup)
- **M40.6.1.3** Expiry on an unanswered approval with a stated default of doing nothing  
  Evidence: Lapse is built and shown: gate.leash DEFAULT_APPROVAL_WINDOW, approval_routes lists soonest-to-lapse first, ApprovalCard shows 'Lapses'; a lapsed row is refused by take_decision. Wording of the stated default of doing nothing on the card not verified.  
  Next step: write check naming M40.6.1.3: raise an approval with a short window, advance, assert it lapses with no action taken; confirm the card says nothing happens
- **M40.6.1.4** Same approval reachable from Lark and from the web without double action  
  Evidence: One decision path: approval_cards uses approval_routes.take_decision under a claim on the callback id, so a press after a console decision (or the reverse) is refused. acceptance_checks_cards (M33.8.1) exercises both surfaces on one approval.  
  Next step: add M40.6.1.4 to the leaves of the both-surfaces check in acceptance_checks_cards.py

### M40, Class 3: built but not wired (14)

- **M40.2.2.2** Open an agent into the same workspace surface, bounded to what this person may see  
  Evidence: member_activity.open_workspace (calls console.workspace.resolve at the person's own reach) has no caller. MyWorkspace shows agent ids as plain code, no link. The agent page is gated on admin screens.  
  Next step: wire open_workspace into a /me route (or link each My agents row) so a member lands on the agent's workspace tabs; then a check
- **M40.2.2.3** Build a personal agent from a template within the person's own ceiling  
  Evidence: member_activity.build_personal_agent (template materialise inside the person's own ceiling) has no caller. Agent building today is agent_builder_routes/agents.creation, which needs the admin: agent-install capability.  
  Next step: add a member route POST /me/agents from a template instance calling build_personal_agent; needs a store write via agents.install_store
- **M40.2.2.5** Request an agent the person cannot yet call, routed to the department admin  
  Evidence: member_activity.request_agent and AgentRequest are built (routes to the agent's department) with no caller and no store. access_request_routes only handles field and department requests to the data steward, not agents.  
  Next step: add POST /me/agents/{id}/request calling request_agent, store the request and deliver it as a notice to the department admin (reuse access_request store pattern)
- **M40.3.2.1** Personal skills with source, version and review state  
  Evidence: member_library.my_skills/PersonalSkill/origin_of (source, version, review state) are built; only origin_of has callers (agent_routes). The skills library routes (skill_routes GET /skills/library) are the administrator's and show every skill, not a member's personal ones.  
  Next step: add GET /me/skills calling my_skills over ops.skill_store rows owned by the person
- **M40.3.2.3** Submit to the department library for review  
  Evidence: member_library.submit_for_review/Submission built, no caller. Skill review queue exists (POST /skills/{digest}/review, may_review) for administrators.  
  Next step: add POST /me/skills/{id}/submit calling submit_for_review and moving the row to the department's review queue in ops.skill_store
- **M40.3.2.4** Personal skills usable only by this person's own agents until approved  
  Evidence: member_library.attach_refusals (personal skill only for own agents until approved) has no caller. Admin side: skill_library.assignment refuses an unapproved skill via attach_skill/pin_skill, but no personal-skill state exists.  
  Next step: wire attach_refusals into skill_library.assignment and the personal agent builder once personal skills are stored
- **M40.3.3.3** Share with a colleague only where that colleague's entitlement already covers the contents  
  Evidence: member_library.share/open_share/Share built, no caller, no table for a share row (shape has no entitlement by design).  
  Next step: add a share table plus POST /me/artifacts/{id}/share calling share and GET using open_share; needs a migration number
- **M40.4.1.4** Opt out of personal learning entirely, with the cost stated honestly  
  Evidence: member_activity.opt_out/LearningOptOut built (states the cost), no caller, no stored flag, and the memory formation path (chat/remember, memory.turn) reads no opt-out.  
  Next step: store a per-person opt-out (ops.setting or table), check it in memory formation, expose POST /me/learning/opt-out
- **M40.4.2.1** What is stored about this person and where, in plain language  
  Evidence: member_activity.what_is_stored/StoredAboutMe built, no caller. thread_routes export (export_my_history) covers conversations only; /me/workspace shows five cards but not 'what is stored and where'.  
  Next step: add GET /me/stored calling what_is_stored and a card on MyWorkspace
- **M40.4.2.3** Deletion request routed to the retention policy rather than performed silently  
  Evidence: member_activity.request_deletion/route (maps to ops.erasure stores) built, no caller. Erasure queue exists for admins (erasure_routes POST /govern/erasures needs admin:erasure; deletion_rows lets the subject read their own). No member self-request route.  
  Next step: add POST /me/deletion-request filing into the erasure queue as a request (not an erase) and showing route()'s four lists
- **M40.5.1.4** Department-provided connections shown as inherited and not disconnectable here  
  Evidence: member.connections.inherited/personally_connected built, no caller; /me/accounts lists only sources the person may connect, with no provenance field, so department-provided connections are not shown as inherited.  
  Next step: add provenance to MyAccountView from inherited() and render inherited ones without a disconnect control
- **M40.5.2.2** Per-channel notification preferences  
  Evidence: member.connections.ChannelPreference/wants built, no caller, no store; ops/notices.py rejects per-person preference and keeps one install-wide switch per notice kind.  
  Next step: add a preference store and make ops/notices senders ask wants() per person
- **M40.5.2.3** An approver's routing preference for envelope decisions chooses only between the console and a Lark card, never WhatsApp or email  
  Evidence: member.connections.channels_that_may_approve built, no caller. approval_cards sends Lark cards to every addressed binding, switched install-wide by INSTALL_LARK_CARD_APPROVALS; there is no per-approver choice.  
  Next step: store the approver's console-or-Lark choice and have approval_cards.send_raised honour it via channels_that_may_approve
- **M40.5.2.4** Quiet hours honoured by automations and digests  
  Evidence: member.connections.QuietHours/may_deliver built, no caller; nothing outside the module mentions quiet hours (tell_later, learning_told, automation notices ignore them).  
  Next step: store quiet hours per person and call may_deliver in tell_later.tell for digests and automation notices

### M40, Class 2: partly built (15)

- **M40.1.1.3** Session policy, idle timeout and device list  
  Evidence: Idle and absolute session policy built and enforced (identity/sessions.py SESSION_IDLE, bearer checks sid). Admin sessions list exists (session_routes /govern/sessions). Member's own device list member.shell.devices/end_device has no caller and no /me route; it also takes the in-memory SessionRegistry, not StoredSessions.  
  Next step: add GET /me/devices and POST /me/devices/end over identity.session_store.StoredSessions with the own-session check from shell.end_device, then a check
- **M40.2.1.1** Questions asked this month with corrections separated out  
  Evidence: Count of the month's questions built (mine_routes.questions_asked over ops.question_asked, shown on MyWorkspace). Corrections not separated: the view says CORRECTIONS_ARE_NOT_RECORDED, now stale because POST /threads/{id}/corrections (thread_routes, chat.thread_store.correct) records them.  
  Next step: count the person's corrections from the thread store in mine_routes and replace MineAskedView.corrections text with a number; member_activity.activity_this_month is the model
- **M40.3.1.2** Upload, replace and retire with the review cycle set at upload time  
  Evidence: Upload (queue_upload, add_link), replace (POST .../versions) and verify-with-next-review exist. Missing: retire (archive not built, needs a migration per knowledge_lifecycle_routes) and a review cycle at upload time (upload takes no review date). member_library.upload/replace/retire have no caller.  
  Next step: add a review_by field to the upload request, and a retire route over a know.supersede-style function with its migration
- **M40.3.1.3** Usage count so an author can see whether anything reads what they wrote  
  Evidence: member_library.authored_usage is built but uncalled and no source of per-item read counts exists: knowledge.retrieval_log deliberately stores no reference, and mine_routes says nothing counts reads (VERIFICATION_AND_USE_ARE_NOT_RECORDED).  
  Next step: decide where per-item read counts live (item-level counter conflicts with RetrievalEvent no-reference rule); then wire authored_usage to the knowledge card
- **M40.3.2.2** Author in the studio, import from a repository or paste a URL  
  Evidence: Import from repository at a commit, from a URL, pasted SKILL.md, zip and procedure files exist (skill_routes POST /skills, /skills/imports, /skills/procedures) but behind skill_library.may_add, an administrator's write. member_library.add_skill is called only from skill_routes/acceptance. No member-scoped personal import.  
  Next step: let a member add a personal skill: route calling add_skill at the person's own ownership, with a personal-state row
- **M40.3.3.1** Everything produced for this person by any agent  
  Evidence: Artifacts are listed per agent (agent_artifact_routes GET artifacts, latest, download) and estate-wide for admins (artifact_routes /govern/artifacts). member_library.produced_for_me (everything by any agent for this person) has no caller and no route.  
  Next step: add GET /me/artifacts calling produced_for_me over agent.artifact rows with caller_id = the person; add to MyWorkspace
- **M40.4.1.1** Plain-language list of every preference learned, with the evidence that produced it  
  Evidence: MyWorkspace shows each learned statement with stated/inferred and confidence; the weekly digest (learning_told) names signal kinds as evidence. member_activity.learned_about_me (statement plus evidence) has no caller, so the page shows no evidence.  
  Next step: call learned_about_me from mine_routes and add evidence (signal kinds) to MineLearnedView
- **M40.4.1.2** One-click undo per item and an undo-all control  
  Evidence: One-click undo per item built and wired: POST /me/memory/forget and /me/learning/undo (MyWorkspace Forget, digest undo link). Undo-all: member_activity.undo_all exists but has no caller (govern_estate lists undo_all as a refused bulk word for the console).  
  Next step: add POST /me/memory/forget-all over StoredMemoryRecords.undo for the person's own memories and an Undo all button
- **M40.4.2.4** Which agents have read my HR record, from the audit ledger  
  Evidence: Writer side is wired and checked: ops.sensitive_read_store.SensitiveReadRecorder writes record_read ledger entries (acceptance_audit.py checks them). Member page: member_activity.who_read_my_record has no caller; GET /audit shows own entries only on the admin audit screen.  
  Next step: add GET /me/reads calling who_read_my_record over AuditView and a MyWorkspace card
- **M40.5.1.3** Disconnect with immediate token revocation  
  Evidence: member.connections.disconnect (revoke first, refuse on failure) built but no TokenRevoker implementation exists and no route; MyAccounts.tsx has no disconnect control. Vault slot connector_person_oauth_slot exists to delete.  
  Next step: implement a vault-backed TokenRevoker (vendor revoke then slot delete), add DELETE /me/accounts/{connector}, then a check
- **M40.5.2.1** Which channels this person is reachable on and which is primary  
  Evidence: GET /me/channels (binding_routes, MyChannels.tsx) lists channels switched on and bound, with bound_at. 'Primary' is not modelled: member.connections.reachability/ChannelPreference/reachable_on are uncalled and nothing stores a primary.  
  Next step: store a primary channel per person and surface it through reachability in my_channels view
- **M40.6.1.2** Approve, reject and amend, each written to the ledger  
  Evidence: Approve and reject written to the ledger via approval_routes take_decision and audit approval entries. Amend is explicitly not offered (AMENDING_WAITS_FOR_A_REPLACEMENT_RAISED_THROUGH_THE_GATE in approval_routes).  
  Next step: build amend as reject plus a replacement raised through the gate, then a check; until then a check can cover approve and reject only
- **M40.7.3** The web composer accepts an attached file and dictated speech, and dictation is transcribed through the registered speech tool at the per...  
  Evidence: Attach a file to the web composer is built (console/src/pages/AskAttach.tsx, thread_routes POST /threads/attachments, M12.3.6). Dictation is not: no speech tool is registered anywhere in src.  
  Next step: register a speech-to-text tool in the tool registry, add a record control on Ask that posts audio and fills the text; keep the transcription at the person's reach
- **M40.7.5** The member application offers two starting points, start a task and talk to an agent, and a task started without an agent is routed by th...  
  Evidence: Talk to an agent is built: Ask page agent picker (askQuery agent field, gate.select.select_agent, gate.roster). 'Start a task' as a distinct entry and gate routing a task to a callable agent is not: without an agent /answer uses the default agent at the person's own reach.  
  Next step: add a start-a-task entry on Ask posting without an agent, and a gate step choosing a callable agent from the roster; then a check
- **M40.7.6** The member's recent tasks and threads each show their state, running, waiting for approval, done or failed, read from the job and suspens...  
  Evidence: Per-agent conversation list carries run state answered/declined/degraded/failed (console/agent_conversations.py, tables.chat.RunState). The member's own GET /threads has no state and nothing reads job or suspension records for running or waiting; no failed-step text.  
  Next step: extend ThreadSummaryView with state read from ops.jobs and gate.suspension_store plus the failing step

### M40, Class 5: not code, owner or blocked (1)

- **M40.7.4** The member application is proved in the browser for a member who administers nothing: their agents, knowledge, skills, artifacts, memory,...  
  Evidence: A browser proof for a member who administers nothing: needs a member-only person signed in on the install and a person or headless-browser walk of Ask, /me, approvals, accounts, memory. Waits on the owner's install (person-run demonstration) and the earlier M40 leaves.  
  Waits on: owner or coordinator-run browser walk on the install after the M40 wiring leaves land

### M40, Class 4: unbuilt (3)

- **M40.7.2** A person can try an approved skill from its card, which opens a conversation with that skill pinned, run through the one agent runtime at...  
  Evidence: Skills page shows 'Try it out' as UnavailableAction with 'Coming soon' (console/src/pages/skills/skillActions.ts tryOut). Rehearsal route exists for reviewers (skill_routes POST /skills/{digest}/rehearsals) but is not a conversation.  
  Build: build POST giving a thread with the skill pinned to the agent run via /answer (api_routes) at the person's reach, reusing Ask page, thread_routes and skill pins; remove the unavailable action
- **M40.7.7** A person can create a personal project grouping their threads and uploaded files, and a run inside it reads those files as project contex...  
  Evidence: No personal project: no table or route groups threads and files (searched tables, thread_routes, chat/). Attachments exist per thread only (thread_routes ATTACHMENTS_PATH).  
  Build: design a project table (needs migration number) with thread_id and attachment links, read its files as context in /answer at the person's reach, never as memory
- **M40.7.8** Opening an agent shows three starter prompts drawn from that agent's skills and the knowledge the person may reach, and never offers one ...  
  Evidence: No starter prompts: searched src and console for starter/suggested question, only Ask page exists. Inputs exist: agent skills (skill pins) and the knowledge reach.  
  Build: build a route GET /agents/{id}/starters over the agent's pinned skills and answerable knowledge at the person's reach (reuse Ask roster and knowledge search); refuse any the run could not answer

# Wave 5

## M19 Browser and computer use

### M19, Class 1: built and wired, only an install check is missing (2)

- **M19.2.1** Planner that never reads page content, asserted by test  
  Evidence: browsing/planning.py:plan takes only declared Goal and PlanRequest; browsing/shape.py:browsing_gaps parses the package source and fails if page content can reach a plan; test_browsing_plan.py and test_browsing_shape.py assert it. planning is used by tools/website_check.py and ops/acceptance_audit.py.  
  Next step: Write a check naming M19.2.1 that calls brain.browsing.shape.browsing_gaps() on the installed package and requires an empty result, plus plan() on a declared target.
- **M19.9.3** A browser run starts from an empty profile in its own container and cannot attach to or import a staff member's browser profile, cookies ...  
  Evidence: sandbox.py gives each run a fresh container with read-only root, tmpfs only and no volume; sandbox_gaps refuses any volume or bind; test_browsing_sandbox.py test_every_way_out_of_the_sandbox_is_a_gap asserts it. No product code reads a staff browser profile.  
  Next step: Write a check naming M19.9.3 that builds sandbox_for(...), requires no gaps, then adds a volume and a bind and requires sandbox_gaps to refuse each.

### M19, Class 3: built but not wired (10)

- **M19.2.2** Envelope compilation: plan intersected with capabilities and skill ceiling  
  Evidence: browsing/envelope.py:compile_envelope and seal intersect a plan with capabilities and the skill ceiling; test_browsing_plan.py. Only ops/acceptance_audit.py calls it (to seal a sample); no route, worker or tool compiles an envelope for a real run.  
  Next step: Call compile_envelope from the worker-side driver (compile an envelope, send wire start_fields to browser-launcher:7300, relay the run, call session_store.start/end and recording.write; launcher.py and recording.py say 'not built'); meanwhile a check can call it over a declared target and assert compilation_only_removes.
- **M19.2.3** Envelope storage and approval record  
  Evidence: tables/browsing.py (BrowserEnvelopeRow, migration 0041), envelope_store.put_envelope/load_envelope/record_decision and approval.raise_approval/approved exist and are tested. put_envelope is called only by ops/acceptance_audit.py; raise_approval and record_decision have no caller.  
  Next step: In the driver call put_envelope after compile_envelope, raise_approval through the leash, and record_decision from the approvals decide path; then a check that stores, approves and reloads one.
- **M19.3.6** Second independent check in the control plane on every returned result  
  Evidence: browsing/enforcer.py:recheck re-judges every returned result in the control plane; test_browsing_enforcer.py. Nothing outside browsing/ calls recheck, because the control-plane relay that would receive results is not built.  
  Next step: Call enforcer.recheck from the worker-side driver (compile an envelope, send wire start_fields to browser-launcher:7300, relay the run, call session_store.start/end and recording.write; launcher.py and recording.py say 'not built') on each runner record line before it is accepted or recorded.
- **M19.4.1** Placeholder resolution at the tool-execution boundary  
  Evidence: browsing/credentials.py:resolve turns a placeholder into a value inside ops.secrets.borrow; test_browsing_credentials.py. Nothing outside browsing/ calls it: the tool-execution boundary for a browser action does not exist (shape.secrets_do_not_travel is a static test only).  
  Next step: Call credentials.resolve in the driver at the instruction-send point with a vault Bindings source (VaultRole.BROWSER_RUNNER), then a check using a vaulted test credential.
- **M19.4.2** Origin binding so a secret only substitutes on its own domain  
  Evidence: credentials.py:resolve compares the binding origin exactly with the action origin and refuses otherwise; test_browsing_credentials.py. No caller outside browsing/, so it never guards a real action.  
  Next step: Wire with M19.4.1; a static check can call resolve with a stub vault for a matching and a non-matching origin.
- **M19.4.3** TOTP generation server-side from a stored seed  
  Evidence: credentials.py:totp computes the code server side from the stored seed and resolve returns only the code; test_browsing_credentials.py. No caller outside browsing/ and no seed storage UI.  
  Next step: Wire with M19.4.1; add the vault slot for a seed and a check that a code is produced without the seed leaving the control plane.
- **M19.5.1** Rubric generated from the goal before seeing the trajectory  
  Evidence: browsing/grading.py:build_rubric takes a goal and a declaration with no parameter a trajectory could arrive through; test_browsing_grading.py and test_browsing_shape.py assert it. Called by nothing outside browsing/.  
  Next step: Call build_rubric in the driver before the start line and keep it with the envelope; a static check can build one and assert it has required criteria.
- **M19.5.3** Agent's own success claim ignored  
  Evidence: grading.py:score has no parameter for the agent's claim (Claim is carried and compared, never scored); test_browsing_grading.py asserts it. Nothing outside browsing/ calls score.  
  Next step: Wire through verify_run in the driver; a static check can call score with a contradicting Claim and require the verdict to ignore it.
- **M19.5.4** Tuned for low false-positive rate, accepting false negatives  
  Evidence: grading.py:score resolves every unknown or unmet outcome against the run (passes only if all required criteria are MET); test_browsing_grading.py. No caller outside browsing/ and no measured false-positive rate exists.  
  Next step: Wire with M19.5.2; a check can feed UNKNOWN outcomes and require passed False. A measured rate needs real runs.
- **M19.6.7** Skill loader refusing a browser skill where an API tool exists, unless exempted with a named approver and expiry  
  Evidence: browsing/skill_gate.py:load_gaps and may_load refuse a browser skill when a registered API tool exists unless an Exemption names an approver and expiry (max 90 days); test_browsing_sessions.py. No skill import or load path imports skill_gate.  
  Next step: Call may_load from the skill import/pin path (tools/skills.py, ops/skill_store.py) with the target registry and an exemption source; exemption storage is also missing.

### M19, Class 2: partly built (34)

- **M19.1.1** Ephemeral gVisor container per run  
  Evidence: browsing/sandbox.py:sandbox_for and sandbox_gaps build and re-check the gVisor (runsc) bodies; launcher.py creates and removes them; docker-compose.browser.yml deploys browser-launcher (opt-in, health = runsc present). Nothing calls the launcher; no body ever sent to a daemon.  
  Next step: Build the worker-side driver (compile an envelope, send wire start_fields to browser-launcher:7300, relay the run, call session_store.start/end and recording.write; launcher.py and recording.py say 'not built'), run ops/browser/REHEARSAL.md on a runsc host, then write a check reading launcher health and a labelled run's runtime.
- **M19.1.2** Playwright for Python with Chromium  
  Evidence: ops/browser/Dockerfile and playwright_browser.py (Playwright, Chromium) are the runner image and entry; browsing/runner.py:drive is what it calls. Playwright is not a repo dependency, no workflow builds the -browser image (release.yml builds only the app image), never run.  
  Next step: Add a release job that builds and signs the '-browser' image, run REHEARSAL.md sections 1 to 3, then a check that a run's runner reports chromium and playwright versions.
- **M19.1.3** Worker owning the CDP session and snapshot serialisation  
  Evidence: browsing/runner.py:drive owns the line protocol, playwright_browser.py the CDP session, wire.py:snapshot_fields serialises snapshots; test_browsing_runner.py and test_browsing_wire.py cover the decisions. The runner is never run on a Docker daemon, gVisor or Chromium (browsing/__init__.py, ops/browser/REHEARSAL.md).  
  Next step: Same step as M19.1.2: build the runner image, rehearse one run and check a snapshot line reaches the launcher.
- **M19.1.4** Accessibility-tree snapshots rather than screenshots  
  Evidence: browsing/observation.py:Snapshot has no picture field; wire.snapshot_from_accessibility builds it from the accessibility tree and playwright_browser.py supplies the tree; test_browsing_targets.py. Never run in a browser; no control-plane caller consumes snapshots.  
  Next step: After the driver exists, check a read-only run returns a tree snapshot and no image field; observation.vision_gaps() is the static half to name now.
- **M19.1.5** tmpfs-only writable layer, destroyed at run end, never reused  
  Evidence: sandbox.py declares a read-only root, tmpfs home/tmp/shm charged to the memory cap and no volumes (sandbox_gaps refuses one); launcher.py teardown removes the set; test_browsing_sandbox.py and test_browsing_launcher.py. Bodies never sent to a daemon.  
  Next step: Write a check that builds sandbox_for(...), requires sandbox_gaps()==() and a mutated body refused; the live half waits on the driver and REHEARSAL.md.
- **M19.1.6** Per-run network namespace  
  Evidence: sandbox.py gives each run an internal network named from the run id with the egress proxy as the only other member (egress_network_body); launcher.py removes it at teardown; test_browsing_sandbox.py, test_browsing_deployment.py. Never created on a daemon.  
  Next step: Static half as M19.1.5; live half is REHEARSAL.md plus the missing driver.
- **M19.2.4** Target registry with declared surface maps  
  Evidence: browsing/targets.py has Target, Surface (declared verbs, read_back) and TargetRegistry with tests. Nothing stores targets: no table, route or console page declares one; website_check defaults to an empty registry and acceptance_audit builds one in memory.  
  Next step: Add a browser_target table, route and console page (or a setup step) to declare targets and surfaces, then load the registry from it into website_check and the driver.
- **M19.3.1** Enforcer with policy compiled at container start and immutable after  
  Evidence: browsing/enforcer.py:Policy is frozen and compiled once by compile_policy from the sealed envelope; wire.policy_of reads it at runner start; egress_addon receives its origins at proxy creation; test_browsing_enforcer.py. Runs only inside a container that has never started.  
  Next step: After the driver and rehearsal, check a run's policy digest equals its envelope digest; static half: enforcer.policy_gaps() and enforcement_gaps().
- **M19.3.2** Reference validation against the snapshot just produced  
  Evidence: browsing/enforcer.py:authorise refuses an element reference absent from the snapshot just produced (observation.is_current); runner.py calls it per instruction; test_browsing_enforcer.py. Inside the runner only; never run.  
  Next step: Check via a rehearsed run that a stale or invented reference is refused; static half is the unit test over authorise.
- **M19.3.3** Origin allowlist check per action  
  Evidence: enforcer.authorise checks the action origin against the policy and Target.allows_origin; egress_addon.py kills any other host at the proxy; test_browsing_enforcer.py, test_browsing_plan.py, test_browsing_sandbox.py. Runs inside the never-started sandbox.  
  Next step: Live check needs the driver and a runsc host; a static check can call egress_addon's decision over an undeclared origin.
- **M19.3.4** Write verb and count checks against the envelope  
  Evidence: enforcer.authorise holds the envelope's verbs and per-verb counts in Spend and refuses an undeclared write verb or an extra use; test_browsing_enforcer.py. Used by runner.py only; no run has happened.  
  Next step: As M19.3.3: needs the driver; static half can call authorise over a sealed sample envelope.
- **M19.3.5** mitmproxy sidecar as the sole route out  
  Evidence: sandbox.py makes a mitmproxy container (EGRESS_IMAGE mitmproxy 11.1.3, unverified against a registry) the only member with a route out; egress_addon.py is the addon; test_browsing_sandbox.py covers its decisions. The proxy has never been started.  
  Next step: Pull and pin the proxy image, rehearse per REHEARSAL.md, then a check that a runner cannot reach an undeclared host.
- **M19.4.4** Outbound scrubbing from message history  
  Evidence: credentials.py:scrub_outbound is live on the request path via ops/log_capture.py (Logs screen) and gate/screening.py; scrub_history is used only by browsing/recording.py. No browser run's message history is scrubbed in practice because no run exists.  
  Next step: Call scrub_history over each run's message history in the driver and treat a hit as an incident; log_capture already gives a check target.
- **M19.4.5** Vision disabled so a credential cannot be read off a screenshot  
  Evidence: observation.py:Snapshot carries no picture and vision_gaps() asserts it; verification.admit_frames withholds frames beside a typed credential; tests in test_browsing_targets.py, test_browsing_grading.py, test_browsing_verification.py. No actor or judge runs, so nothing consumes either.  
  Next step: A static check can call vision_gaps() and admit_frames over a sample; the live half waits on the driver.
- **M19.5.2** Two-pass scoring: actions only, then with screenshots  
  Evidence: verification.py:verify_run does the actions-only pass then the admitted-frames pass and refuses second-pass outcomes for a failed first pass; tested. grading.verification_gaps says 'no judge is built', so no outcome is produced and nothing calls verify_run.  
  Next step: Build the judge (model or person giving an Outcome per criterion) and call verify_run from the driver at run end.
- **M19.5.5** Out-of-band read-back from the system of record where possible  
  Evidence: verification.py:read_back and read_back_plan define the out-of-band read through ReadBackPort; test_browsing_verification.py. No ReadBackPort implementation exists and grading.verification_gaps says no target declares a read_back tool.  
  Next step: Implement a ReadBackPort that reads through the gate (a connector or tool), declare read_back on a registered surface, and call it from verify_run.
- **M19.6.2** Per-domain concurrency limit  
  Evidence: browsing/concurrency.py:may_open applies a per-domain row after the global admission check; test_browsing_concurrency.py. No module outside browsing/ imports it, and its docstring says the counter that fills SessionCounts is not built.  
  Next step: Build the counter (read started and ended sessions from browser_session) and call may_open from the driver before launch.
- **M19.6.3** Per-agent limit  
  Evidence: browsing/concurrency.py:may_open also applies a per-agent row; test_browsing_concurrency.py. No caller and no SessionCounts source (docstring: 'Not built: the counter').  
  Next step: As M19.6.2; session_store.start/end already hold the rows a counter can read.
- **M19.6.4** Memory and CPU caps per session  
  Evidence: sandbox.py:Caps sets memory (swap equal), pids and CPU quota for runner and proxy and refuses tmpfs sizes that leave no memory floor; test_browsing_sandbox.py, test_browsing_sessions.py. Figures are marked judgements; bodies never sent to a daemon.  
  Next step: Static check on sandbox_gaps with caps; measure real figures in the REHEARSAL.md run.
- **M19.6.5** Global kill switch  
  Evidence: sessions.py:may_start consults ops.admission.decide so a halt refuses a new session; enforcer.stopped_now stops a running one at safe points; tests in test_browsing_enforcer.py, test_browsing_sessions.py. brain.ops.halt is live but no run exists to stop and no worker calls may_start.  
  Next step: Call may_start in the driver and enforcer.stopped_now in the relay loop; a check can then halt and see a start refused with RefusalKind.HALTED.
- **M19.6.6** Full session recording with retention policy  
  Evidence: browsing/recording.py has record, write, transcript_digest, recording_gaps and remove_expired (window = ops.retention.RECORDING_RETENTION_DAYS, holds kept, undated keys counted); test_browsing_recording.py. Docstring: no worker calls record/write, no scheduled caller of remove_expired, nothing written to the object store.  
  Next step: Hand an S3Backend (ops/object_store.py) to recording.write at run end in the driver and add a remove_expired job to ops/schedule_runner.py.
- **M19.7.1** Read-only capability shipped first  
  Evidence: browsing/sessions.py defines READ_SURFACE (ToolDefinition), surface_scope and capability_gaps; ops/starter.py seeds BROWSE_SURFACE; test_browsing_sessions.py pins read-first ordering. No handler is registered, so no agent can run the tool (docstring: 'No handler is registered here').  
  Next step: Register a handler in tools/startup.py that sends the read run to the driver; website_check's ReadOnlyBrowser seam is the same missing half.
- **M19.7.2** Write capability behind envelope approval  
  Evidence: sessions.py:ACT_ON_SURFACE is the one write tool; approval.py raises the envelope as a leash suspension, console/approvals.py renders its terms, envelope_store and enforcer.compile_policy bind it by digest; tests in test_browsing_approval.py, _enforcer.py, _sessions.py. No caller raises an approval or runs the write.  
  Next step: Call approval.raise_approval and approved in the driver start path; add a readable envelope diff to the approval card (none exists).
- **M19.7.3** Assisted ceiling on writes unless a per-surface exception is signed  
  Evidence: browsing/autonomy.py:SurfaceException, sign and runs_unattended cap writes at Assisted unless a signed exception exists, applied in envelope.compile_envelope; test_browsing_autonomy.py. Docstring: nowhere to keep an exception and recording it as a leash change is not wired.  
  Next step: Add an exception store, a console grant screen and an audit-ledger leash_change entry (shared with M19.9.7), and pass stored exceptions to compile_envelope.
- **M19.9.1** A browser action outside its approved envelope suspends the run and sends a new approval naming the breach, and actions inside the envelo...  
  Evidence: enforcer.authorise refuses an out-of-envelope action and the run ends on it (runner.py); approval.py deliberately approves the envelope up front and rejects mid-run cards (A_PERSON_APPROVES_THE_CONTRACT_BEFORE_THE_CONTAINER_STARTS). Suspend and re-approve naming the breach does not exist.  
  Next step: Either build a breach suspension (a new leash approval naming the refusal) or record the narrowing as a docs/needs-rupash.md question and name it in register row ARC-B-021's decision.
- **M19.9.2** Browser approval is proved on an install: a read-only website check runs without approval, a planned browser write is shown once as a rea...  
  Evidence: Read-only website check exists and is wired (tools/website_check.py, app.py HttpsProber); envelope approval primitives exist (approval.py). No readable diff of an envelope on the card and no in-envelope or out-of-envelope run, so approve-once and ask-again cannot be shown.  
  Next step: Needs the driver plus an envelope diff in the approval card; then a check that runs a read, an approved write and a breach and records each.
- **M19.9.4** Website and portal reading is proved on an install: asked whether a live website is working, an agent checks it over HTTP, opens the rend...  
  Evidence: HTTP half is built and wired (tools/website_check.py, ops/website_probe.py). Missing: rendered-page read in the sandbox (launcher never called), portal login with a vault credential (credentials.resolve has no caller), recording kept under retention, target registration.  
  Next step: Depends on the driver, REHEARSAL.md proof and target storage; then one install check over a declared test site plus the HTTP check.
- **M19.9.5** A browser write is proved on an install: one multi-step form-filling task against a registered target runs at the Assisted rung only afte...  
  Evidence: Pieces exist (planning, envelope, approval, enforcer, grading, verification.read_back) but there is no driver, no judge, no ReadBackPort implementation and no target declares read_back; a form-filling run at Assisted cannot happen.  
  Next step: Needs the driver, judge and a ReadBackPort over a registered target; then a check that runs one approved form fill, a refused extra step and a read-back.
- **M19.9.6** The browser sandbox runs on an install, and an agent whose ceiling holds the browser tools opens a page in it.  
  Evidence: docker-compose.browser.yml and launcher --check give a launcher whose health is gVisor present; agent browser tools are defined (sessions.READ_SURFACE) but no handler is registered, so no agent opens a page in the sandbox. Never run on a daemon.  
  Next step: Run the REHEARSAL.md first build on a runsc host, build the driver and register the read handler, then check an agent with the browse capability fetches one page.
- **M19.9.7** An administrator grants a per-surface browser write exception or a browser-over-API exemption from the console with an approver and expir...  
  Evidence: autonomy.SurfaceException and skill_gate.Exemption are value types with sign and expiry rules (test_browsing_autonomy.py). No store, no console screen or route for an administrator to grant one, no ledger leash_change entry, no listing until lapse.  
  Next step: Build a table, routes and a console page for grants with approver and expiry, write the audit leash_change on grant, pass live grants into compile_envelope and may_load.
- **M19.9.8** On the install a browser run's outcome is scored by a judge from its actions and admitted frames against the rubric fixed before the run,...  
  Evidence: grading.build_rubric and verification.verify_run exist and are tested; grading.verification_gaps states no judge is built and no target declares a read_back tool. Nothing scores a real run.  
  Next step: Build the judge and the read-back port, call verify_run at run end, then a check that scores a recorded run against its prior rubric.
- **M19.9.9** On the install open browser sessions are counted as they start and end, and a session over the global, per-website or per-agent limit wai...  
  Evidence: sessions.may_start (global admission budget) and concurrency.may_open (domain, agent) decide with reasons; concurrency docstring: the counter that records sessions as they start and end is not built, and nothing calls either decision.  
  Next step: Build the counter from browser_session rows (session_store.start/end), call both decisions from the driver, then a check that fills a limit and sees a refusal naming it.
- **M19.9.10** On the install an agent's browser write to an allowlisted site is compiled into an envelope, approved by a person, signs in with a vaulte...  
  Evidence: compile_envelope, approval, credentials.resolve and enforcer exist as separate tested modules but no code joins them for a run; no vault credential binding source for browser targets exists; no run has happened.  
  Next step: Needs the driver plus Bindings backed by the vault; then a check that approves one write envelope and shows the credential absent from plan, trace and recording.
- **M19.9.11** Browser session recordings on the install are written to the object store at run end, and a scheduled job removes expired ones, keeps hel...  
  Evidence: recording.write and remove_expired are built and tested, with the recordings bucket in ops/storage.py and RECORDING_RETENTION_DAYS; no caller writes a recording at run end and no scheduled job calls remove_expired.  
  Next step: Call recording.write in the driver and register a scheduled remove_expired in ops/schedule_runner.py (holds from the legal hold store); then a check that writes, ages and sweeps.

### M19, Class 4: unbuilt (1)

- **M19.8.1** An agent can operate an allowlisted desktop application inside an isolated virtual desktop, with every action recorded, every write held ...  
  Evidence: Nothing found by subject (desktop, virtual desktop, computer use, xvfb) in src or ops; only register rows (ARC-B-028, OWN-98, CONA-25) name it, as 'deferred behind browser checks'.  
  Build: Build after the browser run is proved on an install; reuse the sandbox, launcher, enforcer, envelope and recording patterns with a desktop runner image. Sequence behind M19.9.4 and M19.9.5.

## M30 Hosting, delivery and recovery

### M30, Class 1: built and wired, only an install check is missing (5)

- **M30.3.5** Retention: thirty daily, twelve weekly, twelve monthly  
  Evidence: Decided narrower by needs-rupash item 60 option A (register DEC-5): thirty daily copies and weekly to day 35. recovery.RETENTION_LADDER and backup_ladder.select decide it; the backups bucket's 35-day lifecycle (ops/seaweedfs/provision.sh) holds a superset. Tests: test_backup_ladder, test_recovery.  
  Next step: write check naming M30.3.5: read the backups bucket lifecycle rule equals retention.BACKUP_RETENTION_DAYS and backup_policy_gaps() is empty; a pruner is optional and was rejected for now
- **M30.4.6** Policy change during an active task  
  Evidence: gate/runtime.py re-resolves the reach before every tool call (A_RUN_IS_JUDGED_AGAIN_AT_EVERY_TOOL_CALL) and leash.resume re-judges; tests: test_agent_runtime.py test_a_grant_revoked_mid_run_refuses_the_next_call, test_crash.py M30.4.6 cases.  
  Next step: write check naming M30.4.6: start a run, change policy (revoke a grant or lower the rung) mid-run, assert the next tool call is refused in the one sentence
- **M30.4.7** User disabled during an active task  
  Evidence: Same per-call re-resolution; test_crash.py test_a_caller_disabled_between_two_attempts_is_refused_at_the_second and test_a_reader_disabled_between_two_attempts_is_judged_at_the_instant_it_is_asked cover the rule; the request path applies EntitlementSet expiry via intersect.  
  Next step: write check naming M30.4.7: disable a person (directory change or session end) mid-run and assert the run's next step is refused
- **M30.5.2** Measurement wired to the ledger  
  Evidence: gate/finish.py records every request into telemetry (ops/telemetry_store.py, tables/telemetry.py RequestTelemetryRow) with lane, tokens, duration and status; GET /report/service-levels reads it (ops/service_levels.py). Tests: test_telemetry_store, test_service_levels, test_request_finish.  
  Next step: write check naming M30.5.2: ask a question through the answer route and assert the telemetry row carries lane, duration and status
- **M30.6.9** After a person asks a question on the install, the Service levels screen counts that request in its lane within the window, and a lane wi...  
  Evidence: Telemetry is written for every request by gate/finish.py and GET /report/service-levels returns each lane's requests, p95 and success rate (ops/service_levels.py, report_routes.py); test_a_lane_nothing_was_asked_through_is_present_and_unmeasured. A lane with traffic carries requests above zero.  
  Next step: write check naming M30.6.9: ask one question, GET /report/service-levels and assert the answer lane shows requests of at least one

### M30, Class 3: built but not wired (6)

- **M30.3.10** Alert on backup age exceeding the profile RPO  
  Evidence: recovery.alerts() raises BACKUP_AGED against the profile RPO from real manifests (tested); schedule_runner Runner backup_exposure has needs= and no run, controls.backup_exposure is invoked_by NOTHING, and ops/notices BACKUP_EXPOSURE says no channel is chosen. Nothing calls alerts().  
  Next step: give Runner backup_exposure a run that lists manifests with backup_manifest.read_manifests, calls recovery.alerts and sends the notice to the operations alert holder; channel may need an owner decision
- **M30.3.11** Louder alert on a failed verification  
  Evidence: recovery.alerts() ranks VERIFICATION_FAILED above BACKUP_AGED and last_attempt covers a drill that ran and did not verify (tested). Same gap: backup_exposure runner has no run, no drill records are written, no channel sends it.  
  Next step: same wiring as M30.3.10 plus the drill record writer (M30.3.8) so a failed verification exists to alert on
- **M30.4.2** Operation classification: safe to retry, unsafe, retry after verification, needs a human  
  Evidence: ops/reliability.py RetryClass (safe, after verification, unsafe, needs a human), OperationClass, retry_class_for(), classification_gaps() are tested; nothing outside reliability.py calls retry_class_for (effects.py PORTS is a separate classification).  
  Next step: consult retry_class_for in ops.recovery_run.sweep_queue and queue verdict_for for the task name, so the class decides redrive versus person
- **M30.5.4** RPO and RTO per profile written into the client agreement  
  Evidence: launch.service_level() builds the profile's RPO and RTO statement and refuses it without a verified drill (tested in test_launch.py, register DEC-31); reliability.RECOVERY_OBJECTIVES says nothing writes it into an agreement. Nothing calls service_level; no route or document serves it.  
  Next step: expose launch.service_level through a route on the handover or recovery page that renders the statement or its refusal reason
- **M30.6.6** The service level statement is produced only after a restore drill verified a copy and the newest copy is inside the promised recovery po...  
  Evidence: launch.service_level() is produced only with a verified Drill and a newest copy inside the RPO, otherwise raises with the reason (four refusals, tested in test_launch.py, DEC-31). Nothing calls it and no route serves the statement or its refusal.  
  Next step: same route as M30.5.4; the check asks for the statement on an install with no verified drill and expects the stated reason
- **M30.6.10** On the install the backup exposure control runs on its cadence and alerts a named person when the newest verified copy is older than the ...  
  Evidence: controls.backup_exposure (daily, WOKEN) and recovery.alerts() exist; Runner backup_exposure in schedule_runner.py has needs= and no run, so the control never runs on its cadence and alerts nobody. Includes the not-verified-last-rehearsal case via last_attempt (tested).  
  Next step: same wiring as M30.3.10; then the check reads the control's last run from the Jobs route and an alert addressed to the named person

### M30, Class 2: partly built (12)

- **M30.3.1** pgBackRest with continuous WAL archiving, daily incremental, weekly full  
  Evidence: ops/backup/brain-backup (systemd timer 02:00) takes a nightly pg_dump -Fc with a manifest; backup_manifest.py reads it. No pgBackRest, no continuous WAL, no daily incremental or weekly full: recovery.SCHEDULE says nothing in the repository runs them.  
  Next step: decide pgBackRest versus the nightly dump (needs-rupash item 44 option C chose the dump for now), then add a pgBackRest stanza, WAL archive_command and timers to the installer
- **M30.3.3** Off-host destination, mandatory  
  Evidence: recovery.destination_gaps() refuses an on-host destination (tested) but nothing calls it; brain-install-backup defaults the endpoint to the install's own SeaweedFS container, so copies stay on the host unless an operator sets another endpoint. Manifest has no off_host field.  
  Next step: require an off-host endpoint in brain-install-backup and the setup wizard, record it in the manifest, and call destination_gaps from the recovery panel route
- **M30.3.4** Encryption at rest with a client-held key  
  Evidence: recovery.KeyHolder and destination_gaps() refuse platform-held or no key (tested) but brain-backup and brain-install-backup contain no encryption step at all and the manifest records no key holder; nothing calls destination_gaps.  
  Next step: add client-held-key encryption (age or gpg public key from setup) to brain-backup before upload, record key holder in the manifest, surface in recovery panel
- **M30.3.6** Weekly automated restore into a scratch container  
  Evidence: ops/backup/brain-restore-drill loads one copy into a named scratch database and compares counts and migration head; docs/install/restore-drill.md. Run by hand: schedule_runner Runner restore_drill has needs= and no run; no timer; it does not create the scratch container or write the drill record.  
  Next step: give Runner restore_drill a run that fetches the newest copy, drives the script, writes the drill record to the backups bucket, started weekly by the worker
- **M30.3.7** Smoke query and permission canary against the restored copy  
  Evidence: recovery.Check has SCHEMA_COMPLETE, SMOKE_QUERY, PERMISSION_CANARY as required checks (tested); brain-restore-drill does row counts and migration head only and says the schema check, RLS sweep and canary are manual steps in the drill document.  
  Next step: extend the drill runner to run schema, smoke and permission canary checks on the scratch copy and record each CheckRun in the drill record
- **M30.3.8** Measured RTO recorded from the drill  
  Evidence: recovery.verification_of() refuses an RTO on an unverified drill and backup_manifest.read_drills() reads drill records (tested); nothing writes a drill record, the script leaves it to the person, so the install records no measured RTO.  
  Next step: have the drill runner time the restore and write the drill record; then GET /install/recovery shows the measured RTO against the profile target
- **M30.3.9** Console recovery panel with last backup, last verified restore and a one-click drill  
  Evidence: GET /install/recovery (install_routes.py) and console RecoveryPage show last backup, last verified restore, last attempt and drill due via console/recovery_view.py; tested. No one-click drill: install_routes.py says it is a write nothing performs. backup_ladder unwired.  
  Next step: add a POST drill route starting the drill runner (M30.3.6) under admin capability, and a Start rehearsal button on RecoveryPage
- **M30.4.4** Malformed responses and 429 injection  
  Evidence: 429 and malformed handling exists: models/routing.py maps 429 to FallbackTrigger.RATE_LIMITED, models/calls.py walks the ladder, gate/runtime.py counts a malformed reply as a turn; unit tests in test_model_calls, test_routing, test_agent_runtime. ops/crash.py is about worker crashes. No injection suite on an install.  
  Next step: write install check with a stub provider returning 429 then a malformed reply, asserting fallback and the stated stop reason through the real answer route
- **M30.4.5** Disk-full behaviour  
  Evidence: Disk full is handled by name only in deployment/database.py (create, migrate, seed raise DiskFullError via reliability.is_disk_full); the request path, ledger writes and uploads do not catch it, and no test fills a disk.  
  Next step: call is_disk_full on answer-path writes and object store puts and return the stated refusal; add an install check with a tiny tmpfs volume
- **M30.6.2** Operations are proved on an install: the service levels screen shows each lane's measured p50 and p95, permission and redaction latency a...  
  Evidence: GET /report/service-levels shows per lane objective_p95_ms, p95_ms, success_rate, requests (report_routes.py, ops/service_levels.py). Missing: p50, permission and redaction latency, connector timeout in force; missed-window and aged-backup alerts unwired (M37.5.1.3, M30.3.10); worker-stop and canary delivery unbuilt.  
  Next step: add p50, permission and redaction latency and connector timeout to the service levels reading, wire the alert runners, then write the check
- **M30.6.4** Enabling an edge proxy or tunnel on an install that declares a residency constraint states that encryption then ends at the provider's ed...  
  Evidence: docs/install/network.md states Cloudflare reads every request and decrypts at its edge. No install-level residency constraint exists (residency is a model-routing setting) and nothing requires or records an administrator's acceptance before a tunnel or edge proxy is enabled.  
  Next step: add an acceptance record (table, route, console prompt) shown when the tunnel overlay is enabled on an install declaring a residency constraint; needs a decision on what declares one
- **M30.6.5** An install on a profile with a recovery point under four hours replicates its object store off the host and has a standby database it fai...  
  Evidence: docker-compose.replica.yml runs a hot standby Postgres; profile full has a one-hour RPO (reliability.RECOVERY_OBJECTIVES). Missing: object store replication off the host, a promote or failover procedure and recorded failover drill, and any gate stopping the profile being offered without them.  
  Next step: build object-store replication, a failover runbook and drill record, and make launch.service_level refuse an under-four-hour profile without them; needs a second server to rehearse

### M30, Class 5: not code, owner or blocked (5)

- **M30.1.3** Cloudflare Tunnel option for zero inbound ports  
  Evidence: docker-compose.tunnel.yml and .tunnel.identity.yml, ops/tunnel.py (overlay_gaps, page_gaps) and deployment/release.py carry the option; docs/install/network.md explains it; test_tunnel_option.py. tunnel.py says no tunnel has ever been started from these files.  
  Waits on: waits on the owner: a Cloudflare account and tunnel token on a real server, then a person starts it and records zero inbound ports
- **M30.4.9** Two-box split rehearsed without application change  
  Evidence: Overlays docker-compose.split*.yml, ops/split.py (host_services, address_refusals) and docs/install/scaling.md exist and are tested; scaling.md says the rehearsal steps have not been run. Needs-rupash lists M36.1.4.2 merged into M30.4.9.  
  Waits on: waits on a second server for a person to run the split rehearsal and record it against ARC-B-153
- **M30.6.1** Backups are proved on an install: a copy lands off-host with its manifest every night for seven consecutive nights, a missed night raises...  
  Evidence: Proof leaf for backups on an install: seven consecutive nights, a missed night alerting a person, never verified until a drill, drill checking schema, RLS and permissions, erasure horizon. Needs elapsed time on a real install and the unbuilt pieces M30.3.2, 3.3, 3.4, 3.6, 3.7, 3.10.  
  Waits on: waits on M30.3.x work above and then seven nights on the owner's install with an off-host destination and key; a person records the checks
- **M30.6.7** Recovery and resilience are proved on an install: backups land off the host encrypted with the client's key, a restore drill is timed aga...  
  Evidence: Multi-part proof: backups off-host with client key, timed restore drill, worker killed mid-task, chaos suite, capacity and scaling readbacks. Chaos suite is unbuilt (M30.4.3) and backup encryption and off-host enforcement are unbuilt (M30.3.3, 3.4); the worker-kill piece has recovery_run.  
  Waits on: waits on M30.3.x and M30.4.3 and a person running it on an install
- **M30.6.8** Every hosting and delivery requirement in the requirements register is demonstrated on an install by a person, and each check is recorded...  
  Evidence: Person-run demonstration of every hosting and delivery requirement in the register, each check recorded against its requirement; register rows cite M30.6.8 as proof for dozens of requirements.  
  Waits on: waits on the owner or a tester running the demonstrations on an install

### M30, Class 4: unbuilt (2)

- **M30.3.2** restic for object store and configuration  
  Evidence: Nothing backs up the object store or configuration: ops/backup/brain-backup copies the database only; no restic anywhere in src, ops or compose files. recovery.SCHEDULE declares hourly snapshots of both and says nothing runs them.  
  Build: build ops/backup/brain-backup-files using restic into the same manifest format (Coverage.OBJECT_STORE and CONFIGURATION), reusing backup_manifest.read_manifests and brain-install-backup
- **M30.4.3** Chaos suite: kill Postgres, provider, connector, browser, worker  
  Evidence: No chaos suite exists: nothing in src, tests, ops or CI matches chaos, and no script kills Postgres, provider, connector, browser or worker. Related: ops/crash.py durable_machines, ops/recovery_run.py, ops.reliability.MATRIX.  
  Build: build a rehearsal script under ops/ for a throwaway install that kills each component and reads recovery from the install and jobs routes, plus in-process provider and connector fault injection in acceptance checks

## M36 Scaling triggers and performance

### M36, Class 1: built and wired, only an install check is missing (8)

- **M36.1.1.1** Monthly partitions of the metadata ledger, created and detached by the worker in plain SQL  
  Evidence: Migration 0039 creates obs request telemetry partitioned by range on received_at; ops/ledger_partitions.maintain creates and detaches months in plain SQL and runs from the worker's retention_sweep runner (schedule_runner.py). Tests: test_ledger_partitions (real server in CI).  
  Next step: write check naming M36.1.1.1: run the retention sweep runner and read pg_inherits for the next month's partition under obs.request_telemetry
- **M36.1.2.2** Console reads routed to the replica  
  Evidence: app.py builds app.state.console_reads from settings.read_replica_url (ops/replica_store.console_reads_for, falling back to the primary); estate, directory, govern and people routes read through ConsoleReads and console/read_replica.route_read. Tests: test_read_replica, test_replica_store.  
  Next step: write check naming M36.1.2.2: build ConsoleReads with a second session factory in the harness and assert a console read is served from it and an answer-path read is not
- **M36.1.3.2** Refresh schedule and staleness display  
  Evidence: Runner spend_report_refresh in schedule_runner.py refreshes the spend view daily; spend_report_view carries as_of and freshness (LIVE, ageing, STALE tied to controls.MISSED_RUN_GRACE) and spendQuery.ts renders them. Tests: test_spend_report_view, test_worker_schedule.  
  Next step: write check naming M36.1.3.2: run the refresh runner, GET /report/spend and assert as_of and freshness LIVE; age the view and assert it reads ageing
- **M36.2.1.1** Dependency graph over independent source calls  
  Evidence: connectors/federation.py FanOutPlan (SourceCall, depends_on, cycle check, waves) is used by connectors/live_read.py, which runs in the answer path via ops/live_read_run and gate/live_records (app.py). Tests: test_connectors_federation and the connector acceptance checks.  
  Next step: write check naming M36.2.1.1: ask a question needing two independent source calls and assert the plan puts them in one wave (extend acceptance_checks_connector_framework.py)
- **M36.2.1.2** Fan-out with one critical path rather than a sum  
  Evidence: live_read.py runs each wave with asyncio.gather and checks FanOutPlan.assert_within against the wall clock, so the cost is the critical path and not the sum. Tests: test_connectors_federation, test_live_read.  
  Next step: write check naming M36.2.1.2: two stub sources each taking a known time, assert the question's elapsed time is near the longer one, not the sum
- **M36.2.2.3** Verify no detection coverage is lost  
  Evidence: tests/unit/test_screening.py asserts the single pass reports exactly what the serial screens report across every fragment pair, corpora and generated text, plus overlapping detections; the equivalence is the proof that no coverage is lost.  
  Next step: repo-only leaf: close as Proved-in-ci naming the unit job running test_screening.py; no install check applies
- **M36.2.4.1** Peak concurrency test rather than daily volume  
  Evidence: tests/load/test_admission_at_peak.py drives the admission controller at LOAD_TEST_TARGET (two arrivals a second for ten minutes) and ops/load_peak.py is the owner's command for a live install. Concurrency, not daily volume, is the unit.  
  Next step: repo-only leaf: close as Proved-in-ci naming the load test job; the live run is M36.3.1
- **M36.2.4.2** Documented first bottleneck at ten and one hundred times  
  Evidence: ops/admission.py bottleneck_ladder and FIRST_BOTTLENECK_AT_SCALE name the first limit at 10x and 100x; install_routes.capacity_plan feeds GET /install/capacity; acceptance_checks_capacity.py check capacity_is_sized_for_the_busiest_minute_and_its_first_limit asserts both 10x and 100x are named.  
  Next step: add M36.2.4.2 to leaves= of that existing check in acceptance_checks_capacity.py

### M36, Class 3: built but not wired (6)

- **M36.1.1.4** Trigger: ledger row count or query latency threshold  
  Evidence: ops/scaling.py partitioning_is_due is tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE calls it a person's decision. It takes a retention window and interval, not a measured row count or query latency, and GET /install/capacity does not evaluate it.  
  Next step: wire partitioning_is_due with the measured ledger row count and p95 into a section on GET /install/capacity; also note the trigger needs a row-count or latency input, not just the window
- **M36.1.2.4** Trigger: console queries affecting answer latency  
  Evidence: ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them.  
  Next step: wire replica_is_due with measured console read load against answer headroom into GET /install/capacity so a person sees when a replica is warranted
- **M36.1.3.3** Trigger: a report exceeding two seconds  
  Evidence: ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them.  
  Next step: wire report_is_due(observed_p95_ms) into the report routes' timing and into GET /install/capacity; needs a per-report latency measurement
- **M36.1.4.3** Trigger: RAM pressure or a resilience requirement  
  Evidence: ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them.  
  Next step: wire host_split_is_due(profile) with measured memory headroom into GET /install/capacity; resilience requirement input has no source yet
- **M36.2.3.1** Identical in-flight requests share one execution  
  Evidence: ops/scaling.py share_role, may_share, share_refusals decide whether an in-flight answer may be shared (tested); the answer path has no in-flight sharing (gate cache has none). Only connector fetches share, via federation.SingleFlight in live_read.  
  Next step: call scaling.share_role from the answer lane's cache lookup in gate (cache_key) so a second identical question waits for the first
- **M36.2.3.2** Entitlement equality required before sharing, never similarity  
  Evidence: scaling.may_share compares gate.cache_key parts and requires equal entitlement hash, never similarity (tested). The answer cache key itself already carries ent_hash, but nothing calls may_share, so no sharing happens. federation.flight_key omits reach on purpose.  
  Next step: wire may_share with M36.2.3.1; an existing cache check (ARC-A-051) already proves the key carries the hash

### M36, Class 2: partly built (5)

- **M36.1.2.3** Replication lag monitoring with a staleness banner  
  Evidence: replica_store.measure_lag and console/read_replica.banner_for put a staleness field on estate, directory and govern route bodies (tested). The console UI renders it only on LearningPage and MemoryDetailPage; the other pages ignore the field. Not verified further.  
  Next step: render StalenessBanner on the pages whose routes carry it (estate, directory, people, govern); then check with a stubbed lag
- **M36.1.3.1** Views for the heaviest report screens  
  Evidence: A materialised daily spend report exists: tables/spend.py, ops/spend_store.py, console/spend_report_view.py, migration 0034 and GET /report/spend. Usage, adoption, questions and quality reports still read live tables, so only one of the heaviest screens has a view.  
  Next step: decide which other report screens exceed two seconds (report_is_due) and materialise those; spend is done
- **M36.2.1.3** Per-source and global budgets still enforced under parallelism  
  Evidence: live_read.py enforces CallBudget.assert_affordable and per-connector concurrency under gather (tested). Missing: a global ceiling; scaling.scaling_gaps and fanout_refusals say per-connector rows have no global row, up to the sum may be in flight, and are not called.  
  Next step: wire scaling.fanout_refusals and a declared global SOURCE_CALLS budget into live_read admission; then check parallel calls respect both
- **M36.2.2.2** Collapse into a single pass where semantics allow  
  Evidence: gate/screening.py screen_in_one_pass reports the same as the serial screens (tested), but nothing in the request path calls it and its docstring records the collapse does not pay (re has no multi-pattern automaton). No needs-rupash item records this narrowing.  
  Next step: raise a needs-rupash question to close M36.2.2.2 as measured not worth switching to, or switch the gate to screen_in_one_pass; the register row ARC-B-099 should name the decision
- **M36.2.4.3** Results recorded against the SLO table  
  Evidence: ops/load_peak.judge compares each lane's p95 and success rate with reliability.LANE_OBJECTIVES (tested) and prints them; no store keeps a run's result and no screen shows it. A run needs the owner's sign-off (needs-rupash item 194).  
  Next step: add a table and route that record a load_peak result per run and show it beside the service level table; the first real result waits on item 194

### M36, Class 5: not code, owner or blocked (3)

- **M36.1.2.1** Streaming replica configuration  
  Evidence: docker-compose.replica.yml and ops/streaming_replica.py (replica_overlay_gaps) are built and tested; docs/install/scaling.md says nobody has run the replica rehearsal. Built only when its trigger is met (ARC-B-104).  
  Waits on: waits on the owner's server: starting the replica overlay once the trigger is met, a person records the rehearsal
- **M36.1.4.1** Application and browser on one host, database and object store on the other  
  Evidence: ops/split.py with docker-compose.split*.yml (host_services, address_refusals) is built and tested in CI; docs/install/scaling.md says a split install serving a question has not been run. Needs-rupash notes M36.1.4.2 merged into M30.4.9.  
  Waits on: waits on a second server for a person to run the two-host split (same step as M30.4.9)
- **M36.3.1** A load test at the company's declared peak concurrency runs against the owner's install on its own host, records latency per lane against...  
  Evidence: ops/load_peak.py (python -m brain.ops.load_peak) runs the peak at a live install and judges per lane; it spends real model calls so it is the owner's command, needs-rupash item 194 asks whether to run it. It does not measure memory headroom under load.  
  Waits on: waits on the owner's answer to item 194 and tokens for test people; also add memory headroom sampling and a finding output before go-live

## M37 Migration, launch and handover

### M37, Class 1: built and wired, only an install check is missing (7)

- **M37.2.2.3** Re-review every imported skill through the normal queue rather than trusting it because it worked before  
  Evidence: Normal path exists: POST /skills/imports and /skills in skill_routes.py add via console/skill_library.added(), which builds an ImportedSkill unapproved; POST /skills/{digest}/review is the queue. migration.skills.arriving is a duplicate nobody calls. Tests: test_skill_library, test_skill_routes.  
  Next step: write check naming M37.2.2.3: import a skill by POST /skills/imports, assert it is unreviewed and not executable, then approve by POST /skills/{digest}/review as a second person (reuse acceptance_agent_console.py helpers)
- **M37.2.3.1** Rebuild each agent from a template rather than importing its configuration, because their model has no ceiling and no leash to carry across  
  Evidence: Agents are only ever made from a template here: agents/install.py, agents/template.py, agent_lifecycle_routes.py install route, builder drafts; no importer of a foreign agent configuration exists on main. migration.rebuild.Rebuild is an unwired record. Tests exist for install.  
  Next step: write check naming M37.2.3.1: install an agent from a catalogue template via the lifecycle install route and assert it came from that template with no foreign prompt field (reuse existing install checks)
- **M37.2.3.2** Set an explicit ceiling per agent, which AnyGen never had  
  Evidence: agents/model.py AgentAuthority is the explicit per-agent ceiling; agent_lifecycle_routes.py install writes one; E_run intersect applies it. migration.rebuild.authority_for (refuses empty capabilities) is unwired but the product path sets a ceiling.  
  Next step: write check naming M37.2.3.2: install an agent, read its authority from the agent route, assert capabilities are non-empty and a run is narrowed to them
- **M37.2.3.3** Start every rebuilt agent at Shadow on writes regardless of how it behaved there  
  Evidence: agents/install_store.py INSTALLED_RUNG = AutonomyTier.SHADOW, builder STARTING_RUNG = SHADOW; agent_lifecycle_routes.py install writes every target at that rung (test refuses otherwise). migration.rebuild.Rebuild.write_tier unwired.  
  Next step: write check naming M37.2.3.3: install an agent and read its leash rungs from the leash route, assert every write target is Shadow
- **M37.3.2.4** Adoption measured as real questions from real people, machine traffic excluded  
  Evidence: Every question reaching the answer lane is recorded once by gate/finish.py via ops/question_store.record(Asked); adoption.Asked.machine calls limits.is_automated; GET /report/adoption (report_routes.py) reads it. Tests: test_adoption, test_question_store, test_request_finish. Existing check records human asks only.  
  Next step: write check naming M37.3.2.4: record one human and one automated-channel Asked (see asked_questions in acceptance_operations_console_3.py), read GET /report/adoption and assert only the human is counted
- **M37.5.1.2** CI assertion that each control appears in the scheduler  
  Evidence: ops/controls.py registry plus ops/schedule.py (imports CONTROLS) give the worker its schedule; tests/invariants/test_no_safety_mechanism_lacks_a_caller.py and tests/unit/test_schedule.py assert every control is scheduled or named orphan. Jobs and Live runs routes list controls (jobs_routes.py, operate_routes.py).  
  Next step: install check names M37.5.1.2: GET the Jobs route and assert each scheduled control from CONTROLS appears; or close it as Proved-in-ci naming the invariant job
- **M37.5.1.4** Explicit test that no safety mechanism lacks a caller  
  Evidence: tests/invariants/test_no_safety_mechanism_lacks_a_caller.py asserts no control lacks a caller unless the registry says so; backed by controls.orphans(), call_sites(), registry_gaps(). Runs in CI on every push.  
  Next step: repo-only leaf: close with Proved-in-ci naming the invariants job; optional install check calling controls.registry_gaps() and asserting empty

### M37, Class 3: built but not wired (26)

- **M37.1.1.1** Catalogue what the current Company Brain holds: knowledge, prompts, tool definitions, conversation history  
  Evidence: inventory.py: Catalogue/Holding cover knowledge, prompts, tool definitions and conversation history, tested in test_migration_inventory.py; but nothing imports brain.migration.inventory outside the package; no table, route or page.  
  Next step: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route
- **M37.1.1.2** Decide per item: migrate, rebuild or retire  
  Evidence: inventory.py: Disposition (migrate, rebuild, retire), Decision, undecided(), contradicted(), cannot_be_carried(), tested; no caller outside the package, no store or screen.  
  Next step: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route
- **M37.1.1.3** Map old permissions onto the new capability model, explicitly rather than by assumption  
  Evidence: inventory.py: PermissionMapping, unmapped(), mapped_twice() make a mapping explicit and refuse an unmapped permission; tested; no caller outside the package, no store or screen.  
  Next step: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route
- **M37.1.2.2** Re-parse and re-embed rather than copying vectors, since embeddings are model-specific  
  Evidence: carry.py: reparse_plan() and carried_vectors() refuse to reuse vectors and name each re-parse from original-bytes digest (tested). No caller feeds the ingest pipeline from reparse_plan; nothing imports carry.  
  Next step: call carry.reparse_plan from a migration route that queues knowledge ingest for each Reparse; then check names the leaf
- **M37.1.2.3** Entity registry seeded from existing client records  
  Evidence: carry.py: EntitySeed (no access field) and seed_gaps() report name collisions via resolution.normalise_name (tested). Nothing writes a seed into the entity registry and nothing imports carry.  
  Next step: wire seed_gaps then a registry-seeding route using the brain.resolution entity write path; then check
- **M37.1.2.4** Historical conversations archived, not imported, unless there is a stated reason  
  Evidence: carry.py: archive(agreed, imports) returns an Archive with searchable empty by construction (tested). No store holds an archive and nothing calls it.  
  Next step: persist Archive in a migration table behind a route, never into knowledge search; then check that an archived conversation is not retrievable
- **M37.1.3.2** Answer comparison log with disagreements surfaced  
  Evidence: parallel.py: disagreements(), unanswered(), unreviewed() build the comparison log views (tested). No table, route or page holds or shows the log; nothing imports parallel.  
  Next step: add a comparison-log table and a console page reading parallel.disagreements; then check
- **M37.1.3.3** Cutover criteria agreed in writing before the period starts  
  Evidence: parallel.py: Criterion and Period require cutover criteria before the window opens; cutover_gaps(), may_cut_over() refuse otherwise (tested; DEC-35 row names it). No store or route; nothing imports parallel.  
  Next step: persist Period and Criterion with a created-at before the first Comparison, route may_cut_over to the cutover screen; then check
- **M37.1.4.1** Old system read-only, then archived  
  Evidence: decommission.py: Decommission refuses read-only before cutover and archived before read-only (tested). Nothing reaches the old system and nothing outside the package imports decommission; no table, route or page.  
  Next step: add decommission record store and route that records timestamps through Decommission; then check
- **M37.1.4.2** Credential revocation on every connector the old system held  
  Evidence: decommission.py: Revocation and credentials_outstanding() keep requested and confirmed apart (tested). Nothing revokes or probes a grant and nothing imports it; register row GAP2-25 names the leaf.  
  Next step: wire Revocation records to a console route fed by a person or a connector probe; then check
- **M37.1.4.3** Scheduled jobs disabled and verified stopped  
  Evidence: decommission.py: ScheduledJob and jobs_outstanding() require an observed silence window after disabling (tested). No store, route, caller outside the package.  
  Next step: record ScheduledJob observations through a route and show jobs_outstanding on the cutover page; then check
- **M37.1.4.4** Final backup retained per the retention policy  
  Evidence: decommission.py: FinalBackup.may_delete_after derives retention from ops.retention.BACKUP_RETENTION_DAYS (tested). No store or route records a final backup; nothing imports the module.  
  Next step: wire FinalBackup record into the cutover route reading the real backup manifest (ops.backup_manifest); then check
- **M37.2.2.2** Convert the description convention, since theirs are written as router prompts beginning "Use the X skill to"  
  Evidence: migration/skills.py: proposed_description() strips the 'Use the X skill to' preamble and router_descriptions() lists the rest (tested). Skill import route POST /skills/imports (skill_routes.py) does not call it; nothing imports migration.skills.  
  Next step: call proposed_description/router_descriptions from the skills import path in skill_routes.py (or console/skill_library.read_package) as a draft shown to the reviewer; then check
- **M37.2.2.5** Retire any skill that has not been invoked in ninety days rather than carrying it over  
  Evidence: migration/skills.py: to_retire(skills, now, after_days=90) lists skills not invoked in ninety days (tested). Retirement exists as POST /skills/{digest}/retirement and per-skill last_used in console_stats_routes, but nothing calls to_retire.  
  Next step: call to_retire over the imported foreign skill list from the migration page (needs last_invoked_at from the export) and route each to /skills/{digest}/retirement
- **M37.2.4.2** Read the memory files as evidence and re-derive tier one preferences rather than importing beliefs wholesale  
  Evidence: migration/learning.py: ForeignMemory and re_derive() build a proposal through memory.tiers.propose and refuse session, promoted and gated changes (tested). Nothing imports migration.learning; the proposal queue exists (agent_memory_routes.py).  
  Next step: wire re_derive into a migration route that files each Derivation into the existing memory proposal queue; then check
- **M37.2.4.3** Discard anything that would widen a scope, since it was never approved by anyone under our rules  
  Evidence: migration/learning.py: re_derive() refuses any change in CHANGES_WHAT_ANYBODY_MAY_SEE (tested). No caller outside the package, so nothing is discarded in practice.  
  Next step: same wiring as M37.2.4.2; check asserts a scope-widening derivation is refused by the route
- **M37.2.4.4** State plainly in the handover that the new system starts without their accumulated learning, and why that is the right trade  
  Evidence: migration/learning.py: learning_note() renders THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING from derivations (tested). launch.assemble handover pack does not include it and nothing imports learning.  
  Next step: add the learning note as a section of the handover pack (launch.assemble) and serve it; then check reads it
- **M37.4.2.4** Subprocessor list covering every model provider used  
  Evidence: launch.py subprocessors() derives the list from provider slots that hold a key (ops.provider_keys.PROVIDER_SLOTS) and refuses an undeclared slot; tested in test_launch.py. Nothing outside launch.py calls it; no route or screen serves the subprocessor list.  
  Next step: expose launch.subprocessors() through a route on the data or handover page and render it; then check that a provider with a key appears and one without does not
- **M37.4.3.3** Named client owner for knowledge, grants and connectors  
  Evidence: launch.py Owner/owner_gaps() refuses a handover pack where knowledge, grants or connectors lack a named client owner (tested). No caller outside launch.py; no table, route or page records owners (data steward appointment is a separate leaf).  
  Next step: add a handover owners table and route feeding launch.owner_gaps, or reuse the data steward record; then check
- **M37.4.3.5** Thirty-day post-launch review booked at handover  
  Evidence: launch.py review_gaps(launched_on, review_booked_for) refuses a review not within thirty days (tested). No caller outside launch.py; nothing books the review (no calendar, task or table).  
  Next step: record the review date in the handover route and surface review_gaps on the handover page; then check
- **M37.5.1.3** Alert when a scheduled job has not run within its window  
  Evidence: ops/controls.py overdue() builds the alert (tested), and ops/notices.py lists CONTROL_NOT_RUN with 'No channel is chosen for it yet, so nothing sends it'. Nothing calls controls.overdue; worker and schedule_runner do not.  
  Next step: call controls.overdue from a scheduled runner using schedule_store last-run times and deliver via the notice sender to the operations alert holder; the channel choice may need a needs-rupash item
- **M37.5.2.2** Runbook per alert  
  Evidence: ops/controls.py runbook_for(), runbook_gaps() and Control.runbook text give each alert a runbook, checked by alerting.runbook_gaps (tested). Only registry_gaps and handover_lines call them; no route or console page serves a runbook, and no alert carries it.  
  Next step: serve the per-control runbook on the Jobs screen or in the alert body (jobs_routes.py) via controls.runbook_for; then check
- **M37.5.2.3** Escalation path to us where the client cannot resolve it  
  Evidence: ops/alerting.py escalation_path(), supplier_step(), escalation_gaps() build the ladder ending at the supplier contact setting (tested). No caller outside alerting.py and no code reads SUPPLIER_CONTACT_SETTING into a sent escalation.  
  Next step: wire escalation_path into the overdue alert flow after Runbook.escalate_after, with the supplier contact read from configuration
- **M37.5.3.1** Measured spend against the projection after thirty days  
  Evidence: console/spend_view.py cost_review() renders variance(projected, measured) beside post_launch_correction (tested in test_spend_view.py) but only tests call cost_review; no route in report_routes.py or spend routes serves it.  
  Next step: add cost review to GET /report/spend (report_routes.py), reading the projection from the install record and thirty days of measured spend; then check
- **M37.5.3.3** Budget thresholds retuned with real distribution rather than assumptions  
  Evidence: ops/retune.py post_launch_correction() recomputes the estimator from observed distribution, returning the prior while the window is short (tested). Called only by spend_view.cost_review, which no route serves; the spend_correction control has no runner (schedule_runner.py Runner has needs=).  
  Next step: give spend_correction a runner assembling estimate vs actual per period and call retune.post_launch_correction; surface via cost review route
- **M37.7.5** A migration cutover cannot be recorded complete while revoking the old system's authorisations, recording the date its access ended or th...  
  Evidence: migration/decommission.py CompletedCutover cannot be built while CUTOVER_GATED_ACTS are unrecorded and decommission_gaps names which (tested; DEC-35). Nothing records a cutover: no table, route or page, and nothing imports it.  
  Next step: build the cutover record store and route that constructs CompletedCutover and returns the refusal text naming the unrecorded act; then check reads the refusal

### M37, Class 2: partly built (5)

- **M37.1.2.1** Knowledge and asset export from the old system  
  Evidence: carry.py: Export record and export_gaps(agreed, exports) check what arrived against the agreed catalogue (tested). The exporter itself is a plugin that does not exist (src/brain/plugins has contract/points only); nothing calls carry.  
  Next step: define the exporter plugin point in brain.plugins, then route carry.export_gaps from a migration page; check names the leaf once an export can be handed over
- **M37.1.3.1** Both systems answering the same questions for an agreed period  
  Evidence: parallel.py: Period and Comparison hold an agreed window and per-question answers of both systems (tested). Nothing sends a question to both systems or records comparisons; no caller outside the package.  
  Next step: needs a runner that asks the old system via a plugin and records Comparison rows, plus a route; first build the store and recorder
- **M37.2.2.4** Diff behaviour on a real task before and after import, not just that the file parses  
  Evidence: migration/skills.py: BehaviourCheck and unproven() name skills with no real task run and answers that changed (tested). No store, route or caller; needs both systems to run the same task, which is person-run.  
  Next step: build a store and route for BehaviourCheck records and show unproven() on the skill review page; the comparison itself needs a person with the old system
- **M37.2.3.4** Map their Availability onto our availability, and their absent authority onto our entitlement, separately - conflating the two is the mis...  
  Evidence: agents/model.py has AgentAudience and AgentAuthority as separate fields, so the native model keeps availability and entitlement apart. The foreign mapping migration.rebuild.audience_for (refuses an unmapped availability) is unwired and takes a per-company mapping.  
  Next step: wire audience_for into a migration rebuild route that takes the person's mapping; native separation can be checked now by installing an agent and reading audience and authority separately
- **M37.5.2.1** Alert routing and severity definitions  
  Evidence: ops/alerting.py Severity, Route, route_for(), routing_gaps() and controls.py use route_for for each control's runbook (tested in test_alerting.py). No delivery path: notices CONTROL_NOT_RUN and BACKUP_EXPOSURE say no channel is chosen, so no alert is routed to anyone.  
  Next step: wire alert delivery: resolve route_for's role to people and send via a channel (ops.notices sender); likely needs an owner decision on the channel

### M37, Class 5: not code, owner or blocked (2)

- **M37.7.6** A migration is rehearsed on a throwaway install: skills are imported and re-reviewed, agents are rebuilt from templates at Shadow with no...  
  Evidence: A throwaway-install rehearsal of the whole migration (skills re-reviewed, agents at Shadow, cutover refused) is a person-run demonstration that needs the migration package wired first (M37.1.x, M37.2.x are unwired). Register DEC-35 and DEC-59 name it as proof.  
  Waits on: waits on wiring of the migration package (classes 3 above) and on a person running the rehearsal on a spare install
- **M37.7.8** Every migration requirement in the requirements register is demonstrated on an install by a person, and each check is recorded against th...  
  Evidence: Person-run demonstration of every migration requirement on an install, recorded against the requirement it proves; register rows GAP2-25 and others name it as proof. Depends on the migration package being wired and on the owner or a tester running it.  
  Waits on: waits on M37.1.x and M37.2.x wiring, then on a person running it

## M42 Client deployment template

### M42, Class 1: built and wired, only an install check is missing (25)

- **M42.1.3** One published image deployed by tag, never rebuilt per client  
  Evidence: install.sh steps 7 and 10 fetch one archive and write APP_IMAGE=<repo>:<release tag>; release.yml verifies the signed CI digest and tags it (no rebuild); installer.rebuild_gaps and release_pinning_gaps hold compose files to it in test_deployment_installer.py.  
  Next step: Check that reads /opt/brain/.env APP_IMAGE is a tag of the product image and equals the running container's image reference.
- **M42.1.4** Release pinning per client, so one client can hold a version back without forking  
  Evidence: installer.release_pinning_gaps and release.update_plan pin APP_IMAGE to a named tag, refuse 'latest' (install.sh line 61), and update.sh/rollback.sh re-pin per install; test_deployment_installer.py, test_deployment_release.py. The pin lives in that install's .env.  
  Next step: Check that the pin is not 'latest' and that the pinned tag is one the release feed lists.
- **M42.2.3** Step-by-step install from a clean server, written so it needs no reference to the Verz install  
  Evidence: docs/install/install.md (fourteen pages in docs/install) is held to the installer plan by ops/install_docs.py:step_gaps, tested in test_install_docs.py; docs_routes.py serves docs; independence sweeps keep other companies' details out.  
  Next step: Write a check that reads the install's served guide and calls step_gaps against the installer PLAN; a clean-server walk-through is M42.4.7.
- **M42.2.8** Backup, monitoring, logging and health-check configuration  
  Evidence: docs/install/operations.md, checklist.md and restore-drill.md describe backup, monitoring, logging and health checks; install_docs.checklist_gaps, scheduled_job_gaps and drill_procedure_gaps hold them to code (test_install_docs.py). Backup itself is not auto-scheduled (see M42.3.5).  
  Next step: Check naming M42.2.8 that runs the doc-gap functions on the served pages; fix scheduling separately in M42.7.4.
- **M42.3.1** Install script, idempotent and safe to run twice  
  Evidence: ops/install/install.sh is generated by deployment/install_script.py:render_install from installer.PLAN; every step tests for done and prints 'already done, skipping'; test_install_script.py and test_deployment_installer.py hold it.  
  Next step: Install-time proof is running the script twice on a server; a check can read the installer markers (APP_IMAGE, starter.furnished) and compare the shipped script to render_install.
- **M42.3.6** Update script pinning a release tag, and a rollback script re-pinning the previous one  
  Evidence: ops/update/update.sh and rollback.sh are generated by release.render_update/render_rollback from update_plan and rollback_plan, carried in the archive (ops/update rule), tested in test_deployment_release.py; update-and-rollback.md says never run on a server.  
  Next step: Check reads that the pin variable in .env is a release tag and the scripts' drift test passes; the live run belongs to M42.2.10.
- **M42.3.8** A published release for every fix, with plain-English notes stating what changed, whether it changes the database, and how urgent it is  
  Evidence: release.yml publishes v0.1.0 (gh release list, 2026-09-29) with notes from release.notes_from_tag_message stating the database change (DatabaseChange) and Urgency; test_deployment_release.py covers it.  
  Next step: Check that reads the install's release feed entry for the running tag and asserts notes with a database answer and an urgency.
- **M42.3.9** The console shows the running version and whether a newer release exists, because nothing else reminds a client IT team to update  
  Evidence: console/version_view.py, deployment/release_feed.py (ReleaseWatch) and install_routes.py serve the running version and newest release; pages Updates.tsx and install/UpdatesPage.tsx draw it; tests test_install_routes.py, test_release_feed.py, test_version_view.py, console/tests/install-pages.test.tsx.  
  Next step: Write a check naming M42.3.9 that reads the updates route and requires a running version and a newer-release verdict (switched-off counts as an answer).
- **M42.5.1** install.sh: one command on a fresh server that checks the machine, installs what is missing, downloads the release, builds the database a...  
  Evidence: ops/install/install.sh (29 steps: machine checks, Docker, archive, secrets, vault, pull, database, start, ready wait, furnish) is generated by deployment/install_script.py:render_install, held by test_install_script.py, published beside the archive by release.yml.  
  Next step: Install-time proof is M42.5.17; a check can compare the shipped script to render_install output.
- **M42.5.2** Every password, key and secret generated on the client server during install, never defaulted and never shipped in the template  
  Evidence: install.sh step 12 mints POSTGRES_PASSWORD, APP_ROLE_PASSWORD and BRAIN_SETUP_SECRET with openssl rand on the server and the vault steps mint tokens; variables.is_secret_name feeds installer.value_leaks_in; test_deployment_variables.py. release.archive_gaps checks the archive for client values.  
  Next step: Check running variables.unminted_secrets over the install's own .env (needs wiring, see M42.1.2).
- **M42.5.3** A setup code printed once by the installer and required by the first wizard screen, so whoever loads the page first cannot claim the system  
  Evidence: install.sh step 28 prints the setup code once; deployment/app_environment.py and firstrun.py hold its digest; setup_wizard.assert_unlocked and claim require it on every screen; tests test_app_environment.py and test_setup_wizard.py.  
  Next step: Cannot be shown after first run; prove on the fresh-install walk, or a check over assert_unlocked with a wrong code.
- **M42.5.4** Setup wizard in the console: numbered steps with visible progress, step 3 of 10, and a back button on every screen  
  Evidence: console/src/pages/FirstRun.tsx draws 'Step N of TOTAL_STEPS' and a Back button on each screen; setup_wizard.py:progress_for is the Python counterpart; console/tests/first-run.test.tsx reads the screens back from setup_wizard.py.  
  Next step: Prove on the fresh-install walk (the wizard is closed afterwards); the console test already covers the structure.
- **M42.5.7** Wizard step: staff source, choosing between Google Workspace, Microsoft, Lark or a spreadsheet, signing in and pulling the list  
  Evidence: connectors/staff_directories.py and setup_staff_routes.py (registered in routers.py) offer Google Workspace, Microsoft, Lark or a spreadsheet, sign in and pull the list; console StaffListCheck.tsx and setup/staffList.ts; tests test_staff_directories.py, test_setup_staff_routes.py, first-run-staff-list.test.tsx.  
  Next step: A check can call the staff-source listing for the configured source; the sign-in half belongs to the fresh-install walk.
- **M42.5.8** Wizard step: AI provider, either their own key or a local-only profile with no external provider  
  Evidence: setup_wizard.py model_provider step takes a provider and key (key held in the vault) via _provider_rule; MODEL_PROFILES still lists 'local', but needs-rupash 80 decided hosted providers only (no local-only profile wanted); test_setup_wizard.py.  
  Next step: Check reads that the install's provider slot is held in the vault; the 'local-only' half is decided out by item 80 (register REQ-42 records it).
- **M42.5.9** Wizard step: optional data source connections, skippable and repeatable later from the console  
  Evidence: wizard connections step (slug list) plus console ConnectSourcesStep.tsx and ConnectSource.tsx connect sources from first run, and the Connectors pages repeat it later (connector_routes.py, ops/connector_store.py); tests console/tests/first-run.test.tsx.  
  Next step: Check naming M42.5.9 that lists the connector catalogue and one connection on a furnished install via connector_routes.
- **M42.5.10** Wizard step: review everything before any of it is written, because a wizard that commits each screen as it goes cannot be corrected  
  Evidence: setup_wizard.py:review builds a ReviewLine per setting and apply_install writes everything at once through POST /setup/appointment (setup_routes.py); console FirstRun.tsx draws the review screen; tests test_setup_wizard.py, test_setup_routes.py, test_install_settings.py.  
  Next step: A check cannot run it after first run (the wizard is closed); prove it on the fresh-install walk, or check review() over a sample draft.
- **M42.5.11** The wizard becomes unreachable the moment the first administrator exists, so the install path cannot be replayed by anybody who finds the...  
  Evidence: setup_wizard.py:assert_open refuses once an administrator exists (WizardClosedError) and setup_routes.py answers an indistinguishable 404; tests in test_setup_wizard.py and test_setup_routes.py.  
  Next step: Write a check that, on an install with an administrator, posts to /setup/appointment and requires the same 404 body as an unknown path.
- **M42.5.13** Every step validates before it advances and says what is wrong in words the person can act on  
  Evidence: setup_wizard.py:problems_with validates every step (checks, _provider_rule, _staff_source_rule) and setup_routes returns a 422 by step, field and catalogue key; brain.locale.MESSAGES supplies the sentences; tests test_setup_wizard.py, console/tests/first-run.test.tsx.  
  Next step: A check on a finished install cannot post answers; prove by the fresh-install walk or by calling problems_with on invalid sample answers.
- **M42.5.14** A finishing screen that hands the person straight into the console already signed in, with nothing further to configure before the system...  
  Evidence: sign_in_routes.py POST /setup/sign-in (FINISH_PATH) binds the first administrator and signs them in; FirstRun.tsx lands in the console; vault_setup.py and install_settings.py leave nothing to configure; tests test_sign_in_routes.py, test_console_served.py, test_vault_setup.py, first-run.test.tsx.  
  Next step: Prove on the fresh-install walk; a check can assert that after first run the ask route answers (see M42.6.3).
- **M42.5.15** Installer output legible to a person: what it is doing, how far through it is, and what to do if a step fails  
  Evidence: install.sh prints 'step N of 29: <name>' with 'already done, skipping' and per-step fail messages naming what to do (generated from installer.PLAN via say() and fail()); tests in test_deployment_installer.py and test_install_script.py.  
  Next step: Check reads the shipped script and requires every step to carry a message and a failure text; a live run is M42.5.17.
- **M42.6.2** The setup wizard writes what it collects, so a first install needs no hand-edited environment file for the values it asks for  
  Evidence: setup_routes.py POST /setup/appointment saves answers into ops.setting (Appointer.appoint); brain.install.value_of resolves them ahead of the environment; the provider key goes to the vault (vault_setup.py); tests test_setup_routes.py, test_vault_setup.py, test_vault_renewal.py.  
  Next step: Check that reads ops.setting for the install settings the wizard collected and that INSTALL_* values resolve without environment entries.
- **M42.6.3** A question can be asked and its answer read in the console, so an install proves itself end to end before any channel is connected  
  Evidence: console/src/pages/Ask.tsx and askQuery.ts post to POST /api/v1/answer (api_routes.py:2651) and show the answer; tests console/tests/ask-page.test.tsx; the answer path is the real gate.  
  Next step: Write a check naming M42.6.3 that posts a question as a seeded person through /api/v1/answer and requires an answer or a worded refusal (an unreachable model server is an honest 'not run').
- **M42.6.4** Console screens for skills: add a skill, see what it is trusted to reach, and assign it to an agent  
  Evidence: console/skill_library.py, ops/skill_store.py, skill_routes.py, tables/skill.py and pages skills/SkillForms.tsx, skillsQuery.ts add a skill, show what it reaches and assign it to an agent; tests test_skill_library.py, test_skill_routes.py, test_skill_store.py, skills-page.test.tsx.  
  Next step: A skill console check exists in ops/acceptance_skill_console.py; add the leaf id there if it proves add and assign, or write one naming M42.6.4.
- **M42.6.5** Console screens for connectors: connect one, hold its credential in the vault, and see what it is trusted to read  
  Evidence: connector_routes.py, ops/connector_admin.py, connector_store.py, ops/credentials.py and openbao.py hold the credential in the vault, console/connector_trust.py shows what it reads, connectors/SourceFlow.tsx draws it; tests test_connector_routes.py, test_connector_trust.py and others.  
  Next step: Name M42.6.5 on the connector install checks that connect, vault-hold and show trust (acceptance_checks_connectors*.py), or write one that does all three.
- **M42.6.6** A helper for a person who does not use a terminal: it asks for the server address and runs the one install command there  
  Evidence: ops/install/windows/install-from-windows.ps1 and .cmd are generated and held by deployment/windows_helper.py (asks five questions, runs the documented command over ssh.exe); release.yml carries them; test_windows_helper.py.  
  Next step: Static check that the shipped helper equals windows_helper output; the double-click run is a person-run step on Windows.

### M42, Class 3: built but not wired (4)

- **M42.1.1** Per-client variables in a separate private repository, one file per install, documented field by field  
  Evidence: deployment/variables.py:template_for, parse_env and variables_repository_gaps implement one file per install and refuse a fork-shaped repository; test_deployment_variables.py. Nothing calls them outside tests (docs/install/checklist.md only names one); the private repository itself is the owner's.  
  Next step: Wire variables_repository_gaps into a CI job template for the variables repository (or a CLI command) and publish template_for output in the release; the repository is a process step.
- **M42.3.2** Environment template generator that refuses to emit a value it cannot explain  
  Evidence: deployment/variables.py:template_for emits a documented template with every credential-shaped name blank and refuses undeclared names; tested. No caller outside tests: install.sh writes .env from its own template step without it.  
  Next step: Have install.sh step 9 (write the environment file) or the archive generate .env.example through template_for, then a check compares the shipped template to its output.
- **M42.3.4** Health-check script a person runs after deploying and can read the output of  
  Evidence: installer.py:health_report prints per-service healthcheck state and each component's ready_when text; no __main__ or script calls it (only docs name it), and install.sh step 23 polls /health/ready only.  
  Next step: Add a python -m brain.deployment.installer health command (or ops/install/health.sh) calling health_report and name it in docs/install/operations.md.
- **M42.5.12** A resumable install: closing the browser halfway continues where it stopped rather than starting the server again  
  Evidence: setup_wizard.py:write_draft, read_draft, discard_draft and draft_from persist a draft to a file but nothing outside setup_wizard.py calls them; setup_routes.py says resuming from setup-draft.json is not served, and console FirstRun.tsx keeps answers in page memory only.  
  Next step: Call write_draft from setup_routes per answered step, read it back on page load, and have FirstRun.tsx load the draft before step 1.

### M42, Class 2: partly built (6)

- **M42.1.2** Secrets minted per install and never copied between clients, enforced by a check that refuses a shared value  
  Evidence: install.sh step 12 mints POSTGRES_PASSWORD, APP_ROLE_PASSWORD and BRAIN_SETUP_SECRET with openssl on the client server (wired). variables.py:shared_secrets and unminted_secrets refuse shared or weak values but nothing calls them outside tests.  
  Next step: Run unminted_secrets over the install's own environment in an install check and expose shared_secrets as a command for the variables repository.
- **M42.3.3** Database create, migrate and seed scripts  
  Evidence: deployment/database.py has create, migrate and seed with a CLI (python -m brain.deployment.database), documented in the guide and checked by install_docs.database_command_gaps. install.sh does not call it (compose creates the database) and seed loads the demo company.  
  Next step: Decide the install's path (call database migrate from the installer, or retire the claim), and write a check that the CLI's migrate reports the head the install runs.
- **M42.3.5** Backup and restore scripts, with the restore verified rather than assumed  
  Evidence: ops/backup/brain-backup, brain-restore-drill and brain-install-backup exist and run against stand-ins (tests/unit/test_backup_scripts.py); restore-drill.md says nobody followed it on a server, the archive does not carry ops/backup, nothing schedules a drill.  
  Next step: Run the drill once on the owner's install, record it, and fix packaging (M42.7.4). CLAUDE.md bars 'restore' in function names under src/brain.
- **M42.5.5** Wizard step: company name, logo upload and web address  
  Evidence: setup_wizard.py company step collects company_name, product_name, web_address and logo_url (an address, not an upload) into INSTALL_* settings; its docstring says 'M42.5.5 says upload' and substitutes an address. No upload route exists and no needs-rupash question records the narrowing.  
  Next step: Either build a logo upload (object store plus a served path) or add a docs/needs-rupash.md question and name its number in register row CON-8 or OWN3-1.
- **M42.7.4** The release archive carries the backup and restore scripts and the installer schedules the nightly backup, so an install made from a rele...  
  Evidence: ops/backup/brain-backup, brain-restore-drill and brain-install-backup (with a systemd timer) exist, but release.INCLUDED has no ops/backup rule (restore-drill.md: the archive does not carry ops/backup) and install.sh has no step that schedules the backup.  
  Next step: Add an ops/backup rule to release.INCLUDED and an installer PLAN step running brain-install-backup, regenerate install.sh, then check the timer exists on an install.
- **M42.7.8** Probed from an address outside the allowlist, the install answers only on its public ports with valid TLS, every administrative console r...  
  Evidence: docs/install/network.md and threat-model.md describe public ports, TLS and the allowlist, and ops/security exists; no probe from outside the allowlist and no alert on the install's own certificate within fourteen days exists (ops/website_probe.py reads other sites' certificates only).  
  Next step: Build an external probe job and a certificate-expiry alert to a named person, then a check that reads the alert configuration; the outside-address probe itself is a person step.

### M42, Class 5: not code, owner or blocked (12)

- **M42.2.10** Update procedure and rollback procedure, both rehearsed rather than written  
  Evidence: docs/install/update-and-rollback.md says neither procedure has been run on a server and 'M42.2.10 is not claimed'; update.sh and rollback.sh exist (generated, tested) but a rehearsal is a person-run event.  
  Waits on: Waits on the owner (or a person) rehearsing update and rollback on a real install and recording it; register rows FEAT-12.12, GAP2-30 and LIVE-07 depend on it.
- **M42.4.4** Verz is client number one: their live system is installed from the template by running the installer on their server, not migrated from t...  
  Evidence: A person-run event: Verz's live system installed by running the installer on its server, not migrated from development. Code half exists (install.sh, v0.1.0); register row LIVE-01 and needs-rupash 82 treat the owner's server as company one.  
  Waits on: Waits on the owner running the installer on the Verz production server and recording it; nothing to build.
- **M42.4.5** Verify on that install: it boots, sign-in works, the administrator works, core features answer and integrations configure, with nothing c...  
  Evidence: Person-run verification on the Verz install (boots, sign-in, administrator, core answers, integrations, nothing carried over); register OWN-166 lists it as proof. Install checks cover parts but the leaf is the owner's demonstration.  
  Waits on: Waits on M42.4.4 and the owner's walk of the install.
- **M42.4.6** Record the measured time from bare server to first answered question, because that number is what the template is for  
  Evidence: A measured time from bare server to first answered question is a number a person records during an install run; nothing in src records installer durations (no timer in install.sh).  
  Waits on: Waits on M42.4.4 and M42.5.17; optionally add timestamps to install.sh output so the figure is read rather than clocked.
- **M42.4.7** A second install on a throwaway server as a fictitious client, run start to finish by somebody following only the documentation, because ...  
  Evidence: A second install on a throwaway server by somebody following only the documentation is a person-run demonstration (register OWN3-1 and FEAT-12.12 proof).  
  Waits on: Waits on a person and a throwaway server after M42.4.4; no code to build.
- **M42.4.8** Every question asked during those two installs becomes a line in the documentation, since a question asked twice is a missing step  
  Evidence: Turning questions asked during the two installs into documentation lines is a follow-up to M42.4.4 and M42.4.7 and has no input until they happen.  
  Waits on: Waits on M42.4.7; then edit docs/install and re-run the install_docs gap tests.
- **M42.5.17** The installer is run start to finish on a fresh AWS instance and on a fresh VPS, each ending with the company's Brain answering a questio...  
  Evidence: A person-run demonstration on a fresh AWS instance and a fresh VPS with the time recorded (register OWN3-1 proof; needs-rupash 82 item 2).  
  Waits on: Waits on the owner or a person with two throwaway servers; nothing to build.
- **M42.6.7** The first real release is published and fetched back on a clean machine, so the image and the archive are known to exist rather than know...  
  Evidence: release.yml has published v0.1.0 (2026-09-29) with image and archive, but 'fetched back on a clean machine' is a person-run step; test_deployment_release.py covers archive contents only.  
  Waits on: Waits on a person fetching the v0.1.0 archive and pulling the image by tag on a clean machine and recording it (register RWD-03, LIVE-07).
- **M42.7.2** The release lifecycle is proved on an install: a CI-built, signed image that passed lint, types, tests, canaries and the licence check is...  
  Evidence: A composite install demonstration: release.yml cosign-verifies and tags the CI digest and update.sh/rollback.sh exist, but pull by digest, drain of a running workflow and rollback completing have not been run (update-and-rollback.md says never run).  
  Waits on: Waits on a person rehearsing a release on an install (M42.2.10); individual claims can be broken into checks afterwards.
- **M42.7.5** The owner's install runs the standard profile, and the System health screen shows the worker, the vault, the object store and the connect...  
  Evidence: A state of the owner's install: standard profile, health screen showing worker, vault, object store and pooler ready, provider key in the vault. Parts have checks (acceptance_checks_vault_worker.py reads the health figure) but the leaf is about that server's configuration.  
  Waits on: Waits on the owner's install being on that profile and the owner confirming; whether the health screen shows the pooler is not verified.
- **M42.7.6** The owner's install is pinned to a published release tag rather than the latest image, and the Version screen shows that tag and whether ...  
  Evidence: A state of the owner's install: pinned to a published tag, with the Version screen showing it and the newer-release verdict. The screen is built (M42.3.9, release_feed) and v0.1.0 exists.  
  Waits on: Waits on the owner re-pinning staging to v0.1.0 via update.sh; then screenshot or check the Version screen.
- **M42.7.7** Every other requirement in the requirements register is demonstrated on an install by a person, and each check is recorded against the re...  
  Evidence: A person demonstrates every other register requirement on an install and records each check against its requirement; register rows LIVE-08, LIVE-09, LIVE-12, LIVE-13 and CONB-44 list it as proof.  
  Waits on: Waits on the owner and the acceptance run; nothing to build beyond the requirement-area proof reading already in PR 495.

### M42, Class 4: unbuilt (5)

- **M42.4.2** Audit the database, logs, uploads, object store, vector store, embeddings and caches  
  Evidence: Nothing audits stores for another company's values: deployment/audit.py covers configuration, build inputs and git history only; ops/independence.py covers source and docs. No search over database rows, logs, uploads, object store, vector store, embeddings or caches.  
  Build: Build a read-only sweep over each store for foreign hostnames and company names, reusing deployment.audit.client_values_in and the independence shapes; run it on the fresh install.
- **M42.4.3** Audit credentials, tokens, webhooks, third-party integrations and default administrator accounts  
  Evidence: No credential, token, webhook, integration or default-administrator audit found: deployment.audit does not read live settings, and variables.unminted_secrets is an unwired helper for secrets only.  
  Build: Build an audit listing every credential slot, token, webhook subscription and administrator account on an install and refusing defaults; reuse variables.unminted_secrets and the vault slot list.
- **M42.5.16** Wizard step: chat and email channels, each connected and sent a test message before the finish, skippable and repeatable later from the c...  
  Evidence: No channels step exists: setup_wizard.StepId has setup_code, company, administrator, data_steward, staff_source, model_provider, connections, review, finish; channel connection exists elsewhere (channel routes, console Channels pages).  
  Build: Add a skippable StepId.CHANNELS in setup_wizard.py and console/src/setup/wizard.ts that connects a channel and sends a test message, reusing the channel connect and test-send routes behind the console Channels page.
- **M42.7.1** The install health check reports whether the host exposes kernel virtualisation, and the browser isolation stated to the administrator is...  
  Evidence: No install health check reports kernel virtualisation: grep for kvm and virtualisation finds only a sentence in browsing/sandbox.py; launcher.py --check reports gVisor (runsc) only, and no administrator-facing text states browser isolation.  
  Build: Add a host probe (/dev/kvm present, Engine.runtimes) to the launcher health and the System health screen and have the console state isolation from that result; reuse launcher.runtimes.
- **M42.7.3** The release image and archive carry the licence notice of every bundled third-party component and font, generated from the lockfiles, and...  
  Evidence: No notice bundling found: ops/dependency_policy.py checks licences of locked packages in CI but nothing generates a notices file from the lockfiles, puts one in the image or archive, or fails a release without one; release.INCLUDED has no notice rule.  
  Build: Build a notices generator from the uv and npm lockfiles (reuse dependency_policy readers), bundle it in the image and archive, and fail release.yml when it is missing or a component lacks one.

