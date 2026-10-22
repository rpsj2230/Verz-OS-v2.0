// Where each task stands when it is not done, and the commit each wave closed at. Edited by
// hand, and the only hand-edited status anywhere in the build.
//
// The owner asked on 2026-09-17 for every task on /build/tracker and /build to show one of
// OPEN, IN PROGRESS, READY FOR TESTING, BLOCKED (with the reason) or DONE. DONE is not in this
// file and cannot be put in it: it is computed from commits carrying `Closes:` and a proof
// trailer (`brain.status`), and a leaf a commit closed is shown as DONE whatever this file
// says. The other four are a person's statement about work in flight, which no commit can
// make, so they are typed here, dated, and nowhere else.
//
// A leaf with no entry is OPEN. Writing OPEN explicitly is allowed, for taking a leaf back
// out of IN PROGRESS with a date on it.
//
// `export.js` and `render.js` both call `check` and throw rather than generate, so an unknown
// id, an unknown status, DONE, a BLOCKED entry with no reason or an undated entry is a red
// build, and `brain.status.progress_of` refuses the same things in the exported `wbs.json`.
//
// Rejected: a text fingerprint per entry as `acts.js` carries. A flag there is permanent and
// outlives many edits above it; an entry here is short-lived and dated, and asking whoever
// moves a task to IN PROGRESS to paste its sentence is friction on the one file meant to be
// quick to edit. Ids are appended and never inserted (CLAUDE.md), which is the guard.
//
// Fields per entry:
//   status   one of STATUSES
//   why      what is happening, or for BLOCKED what it waits on; required for BLOCKED
//   updated  the day the entry was last true, YYYY-MM-DD
//
// WAVE_RECORDS is the other half, M38.2.1.1: the deployed commit at the end of each wave,
// recorded by whoever accepted the wave on staging. Release tags are cut only for client
// installs, so this record, and not a tag, is what says which commit a wave ended at.

//: Every status a person may set. DONE is deliberately absent; see the header.
const STATUSES = ["OPEN", "IN PROGRESS", "READY FOR TESTING", "BLOCKED"];

//: Leaf id to where it stands. Ordered by id.
const PROGRESS = {
  "M27.15.72": {
    status: "READY FOR TESTING",
    why: "built: console/tests/styled-classes.test.ts compiles the component layer's stylesheet and refuses any class in the markup with no selector and no emitted utility (it found bg-surface, text-ink-3 and text-danger, which nothing defined, and two dozen unstyled hooks), and console/tests/one-failure-component.test.ts refuses a failure drawn by hand, a failure heading typed anywhere but ui/FailureNotice, and a private failure component (it found twelve writes drawing failure.message with no reference). Proved in CI: the console job (Console types, boundaries, tests, build) in .github/workflows/ci.yml runs both through npm run test. On the install: make a write fail, for example set an agent's monthly budget while holding no budget role, and read the heading, the sentence and the reference under the form.",
    updated: "2026-10-15",
  },
  "M27.15.70": {
    status: "READY FOR TESTING",
    why: "built: one component, console/src/components/kit/explanation.tsx, draws every explanation in three forms (an inert control, a sentence in place of a control, a note with its lead), and the three old drawings (UnavailableAction, NotOffered, and the soon and not-yet kinds of Note) are gone. The sentences are the server's: brain.console.explanations holds 43 of them with the route whose arrival expires each, GET /api/v1/console/explanations/{act} serves one to any signed-in reader, the same bytes for every reader, and the console types none of them (a sentence the API already sends with a row is handed in as told). console/tests/explanations.test.ts refuses a private copy of the markup, a stand-in component, a Note that leads with coming soon, a use that names an unregistered act or types its sentence, and any disabled control not on a named list of reasons (it found a disabled option on the automation form whose reason nobody could read, now drawn as a line). tests/unit/test_console_explanations.py holds every expiry against the routes the application mounts. NOT done: a few lines the console composes from data (a level that cannot answer, a run that removed nothing, a key the account does not hold) are Note kind attention, not served; and 'the reader cannot perform here' is held to the sentences the API already sends with a row, because a sentence that differed by reader would be a denial that could be told from an absence. Proved in CI: the console job and the unit job. On the install: open an agent's Profile, press the dashed Change beside Level and see nothing happen, focus it and read why; open Learning, Shadow, and read the sentence beside Promote; then ask for GET /api/v1/console/explanations/agent.level with a token and read the same sentence.",
    updated: "2026-10-15",
  },
  "M27.15.69": {
    status: "READY FOR TESTING",
    why: "built: kit EmptyList takes the act that adds a row and who does it as required props (ListPage, WholeList and DataTable take emptyAdds and emptyBy), roles come from the platform's six (kit/roles.ts, held to brain.identity.roles.Role), and console/tests/empty-lists.test.tsx mounts every page with its lists emptied, holds each empty list to an act, a who from that vocabulary and no cause, and holds every remaining bare paragraph to console/tests/support/bareEmpties.ts, where the backlog (BARE_LISTS) is now empty and what is left is states (a fact about the install, a page that is not there, a value of None). Every list the first view of a page draws is converted (about eighty). NOT reached by the render sweep: the tabs a page does not open first, which only the static checks over every EmptyList, ListPage and WholeList use cover. Which role adds a row in each list is my reading of the page, not a decision of the owner's: see the question in the report. Proved in CI: the console job runs the test through npm run test. On the install: open Connectors, Agent templates, Webhooks, Automations and People on a fresh install and read each empty message; it says what would add a row and which role may, and never why the list is empty.",
    updated: "2026-10-15",
  },
  "M27.15.62": {
    status: "BLOCKED",
    why: "part of the task text conflicts with the owner's 2026-09-18 record access view and waits on needs-rupash item 188. Built under either answer: console/tests/reach-questions.test.ts and tests/unit/test_reach_questions.py hold that every who-can-reach question the console and API offer is declared with what it is asked of, that only the record access view takes anything naming a record, that it is read for the reader before any candidate and refuses every reader the way an unknown entity is refused. Nothing asserts that no route answers who can see a named record.",
    updated: "2026-10-15",
  },
  "M27.15.52": {
    status: "READY FOR TESTING",
    why: "built: console/tests/destructive-labels.test.ts refuses any label that starts Delete, Remove, Take it out and the like (thirty-four became Withdraw, Retire, Detach, Disconnect, End membership and Supersede) and holds that the console sends no DELETE, and tests/unit/test_hard_deletes.py derives from the migrations the tables the application may delete from and holds them to the six that brain.ops.hard_deletes argues (it found obs.trace_step, granted by 0226 through a constant the old text scan could not see). Proved in CI: the console job (Console types, boundaries, tests, build) and the Unit tests shards run them. On the install: open a person's Grants view and read the button beside a grant, which says Withdraw, and an agent's Memory, which says Retire.",
    updated: "2026-10-15",
  },
  "M39.8.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M39.7.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M39.11.2": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M39.11.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M33.8.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M32.7.2": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M32.3.1.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M28.5.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M28.5.2": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M28.5.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M28.4.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.61": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.6": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.54": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.45": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.46": {
    status: "IN PROGRESS",
    why: "BUILT AND TESTED: Runs and queue lists what is running and what is owed, and now a third list, Actions waiting for a person, by state in words with what was found and the line that nothing there is sent again. NOT BUILT: resolving an unknown side effect with a confirmation naming the operation, because whether a person may resolve one at all is needs-rupash item 188 (point 5). Install proof: open Runs and queue and read the list; with nothing interrupted it says so.",
    updated: "2026-10-14",
  },
  "M27.15.49": {
    status: "BLOCKED",
    why: "Part built: saving a setting needs the settings authority over everything and is refused before the database without it (tested). The rest, an identity provider change that re-derives its redirect addresses and an embedding size that refuses a change once anything is embedded, waits on needs-rupash item 188 (point 2): both values are read-only on Settings because changing either from a browser can lock every person out, and the owner has not said whether to build the change or move it to the installer.",
    updated: "2026-10-14",
  },
  "M27.15.42": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.4": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.30": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.1": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED: opening the text of a document that sits in a department the reader does not belong to writes one ledger entry naming the document and the reader, from both the library's text route and the page a citation opens, and a failure to write it fails the opening. Seeing a document listed and reading its text were already two reads (the department's read, which People grants and withdraws). A company-wide document, a reader's own department and a refused opening write nothing. An install check calls the route and fails in both directions. Install proof: with two departments, open a document in the other one from the Knowledge page as someone who holds the read there, then find the entry in the Audit log under the document.",
    updated: "2026-10-20",
  },
  "M27.15.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.29": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.15.28": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.13.7": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.13.6": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.13.2": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.13.3": {
    status: "IN PROGRESS",
    why: "BUILT AND TESTED, behind the job_redrive switch that ships off: on Background jobs, under Jobs set aside for a person, an administrator holding the schedule's authority presses Run again, confirms a dialog that names the job, and the worker puts that one failed job back on its queue with the arguments it already had within a minute; the row then says when it did, or that the job was no longer waiting. Runs and queue also lists the actions a stopped worker left unconfirmed, by state. NOT BUILT: a person marking an unknown side effect resolved by their word, which waits on needs-rupash item 188 (point 5), because it would replace the check against the other system. Install proof once the switch is on under Features: set a test job aside, press Run again, wait a minute, read the row's answer and the audit log entry naming you.",
    updated: "2026-10-14",
  },
  "M27.13.5": {
    status: "BLOCKED",
    why: "Waits on needs-rupash item 235: nothing the product runs can start the container a backup drill needs, so a Start button would reach nothing, which item 44 and docs/admin-console.md refuse. The item names three ways to make it real and recommends one.",
    updated: "2026-10-14",
  },
  "M27.14.1": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Home and People and access in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.2": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Agents and AI in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.3": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Knowledge and data in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.4": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Channels and notifications in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.5": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Operations in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.6": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Governance in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.7": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Reports in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.14.8": {
    status: "IN PROGRESS",
    why: "PART BUILT: e2e/specs/module-cases.spec.ts proves every page of Platform (company scope only) in the browser under the situations that need no write: a slow answer is said to be loading, a fault is said under its own heading, an unreachable API under another, a search that finds nothing says so and clears, the page fits a phone (375 wide, no sideways scroll, menu behind its button), and the keyboard gets past the menu. Run once against the real console, API and database with a stand-in sign-in; CI's Browser job is the run against Keycloak. NOT BUILT: the cases that make a change (create, edit, retire, import, export, duplicate, confirmation and the audit entry each leaves), which change an install the other specs read in order and are to be added screen by screen.",
    updated: "2026-10-21",
  },
  "M27.12.8": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.12.6": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M27.10.5": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M16.7.1": {
    status: "IN PROGRESS",
    why: "Built: a change the agent learned is marked as the agent's own learning, naming the person who approved it, the Prompts screen shows it and gives it back, and the ledger names the approver; it never replaces instructions an administrator set, and it is written only while the switch 'Let what an agent learns change its instructions' is on (it ships off). What is not built is the first thing that learns an instruction change: nothing the product learns writes into an agent yet, so on an install this is proved by the check applying one change itself. To see it: after the release, open Install, Acceptance, run the checks and read the row 'what an agent taught itself is marked and can be given back'.",
    updated: "2026-10-15",
  },
  "M16.7.8": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M16.7.7": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M16.7.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M16.7.14": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M16.6.7": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M14.8.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M13.8.11": {
    status: "READY FOR TESTING",
    why: "Built: before anybody upgrades an agent, the review lists what the new version would leave missing on this install (a tool nothing provides, a connector that is not connected, a question nobody has answered), and accepting it switches the agent off with the same list, as an install does. To prove it on the install: after the release, open Install, Acceptance, run the checks and read the row 'accepting a version runs the checks an install runs', which should pass in the two newest runs. Then on an agent's Profile, with a newer version of its template on offer, read 'What this version needs on this install'.",
    updated: "2026-10-15",
  },
  "M13.9.1": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M13.9.2": {
    status: "IN PROGRESS",
    why: "Built: the form a department's administrator writes an agent in, the same one a Super Admin uses, lists only the tools and connectors that administrator's own reach holds, and says why the list is short. Not built: the same cut for skills and for the knowledge an agent draws on (knowledge is set on the agent's own page, behind that page's reach), and a name typed past the form is still not refused, it waits for a second person who holds it as before (needs-you question). To prove what is built: after the release, open Install, Acceptance, run the checks and read the row 'a department builder is offered only what their department holds'.",
    updated: "2026-10-15",
  },
  "M13.8.8": {
    status: "READY FOR TESTING",
    why: "Built: the sales, finance, support and project management templates read the sources they name, bind every tool to one an install registers, and carry the starter skills of their role (finance carries none: none of the eight is about a ledger). To prove it on the install: after the release, open Install, Acceptance, run the checks, and read the row 'the role templates declare their sources and would answer', which should pass in the two newest runs. Then on Agents, New agent, choose the Support Ticket Agent template, finish the steps, and connect Freshdesk if the page says it is waiting for it.",
    updated: "2026-10-14",
  },
  "M13.8.7": {
    status: "READY FOR TESTING",
    why: "Built: the SEO agent template (version 2) declares the analytics and search console connectors, reads the figures each reports, checks a site over HTTP and carries the SEO audit, keyword research and monthly report skills; the monthly report workflow and the channels are set where the builder links to. To prove it on the install: after the release, run the checks on Install, Acceptance and read the row 'the role templates declare their sources and would answer', which should pass in the two newest runs.",
    updated: "2026-10-14",
  },
  "M13.7.9": {
    status: "READY FOR TESTING",
    why: "Built: the Maintenance Agent template declares the ticket desk and the maintenance records source, three maintenance skills, the HTTP website check and the read-only browser, and installs read-only; its one workflow and its approval are put on the installed agent from the Automations page. To prove it on the install: after the release, run the checks on Install, Acceptance and read the row 'the role templates declare their sources and would answer', which should pass in the two newest runs. Then on Agents, New agent, choose the Maintenance Agent template.",
    updated: "2026-10-14",
  },
  "M13.8.19": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M13.8.17": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M13.8.15": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M12.4.9": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M12.4.7": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M12.4.14": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M12.4.10": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M12.3.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M11.9.17": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M11.9.16": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M11.9.12": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M11.8.9": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M10.7.8": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M10.7.7": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M10.7.6": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M10.7.3": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M1.6.18": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M1.10.5": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M1.1.9": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M1.1.8": {
    status: "READY FOR TESTING",
    why: "An install check naming this task is merged on main; it closes when the install's two newest runs both pass it.",
    updated: "2026-10-13",
  },
  "M0.7.1": {
    status: "BLOCKED",
    why: "owner decision: 7 licences await the allowlist (postgres/pgvector, ubuntu/squid, three @fontsource fonts, regex); recommended allow all",
    updated: "2026-09-21",
  },
  "M1.6.5": {
    status: "READY FOR TESTING",
    why: "Google Workspace, Entra and Lark staff lists built (PR #97); proved when the owner connects Lark as the staff source and the first sync lists people with their departments (needs-rupash 91)",
    updated: "2026-09-28",
  },
  "M1.6.13": {
    status: "READY FOR TESTING",
    why: "built (M1/people-status): People shows where the staff list puts each person and their employment type, with filters; proved on the install with M1.6.15. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (directory_routes, pages/people/PersonOverview.tsx, pages/people/peopleQuery.ts); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-09-30",
  },
  "M1.6.14": {
    status: "READY FOR TESTING",
    why: "built (M1/people-status): somebody the list says is suspended, gone or never activated, or of a type not allowed, is disabled on the next sync and their page says why; the last administrator is never kept out; proved on the install with M1.6.15",
    updated: "2026-09-30",
  },
  "M40.7.1": {
    status: "READY FOR TESTING",
    why: "built (M1/relay-to-sign-in): every release gives the sign-in realm the mail relay saved on Notifications, through the step that already signs in to Keycloak inside its container, writing only when the relay changed and leaving a realm with no relay alone; an install check compares the host the realm reported with the relay's. Not built: hiding Forgot password while no relay is set. Proved on the install when a release has run and a reserved person's Forgot password email arrives. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_accounts, ops.sign_in_mail); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M1.6.19": {
    status: "READY FOR TESTING",
    why: "built (M1/departments-from): Settings, under Staff, chooses where departments come from; managed on People the staff sync places and moves nobody; proved on the install with M1.6.21. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (directory_routes, identity.departments_from, pages/people/PersonPlacements.tsx +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-09-30",
  },
  "M1.6.20": {
    status: "READY FOR TESTING",
    why: "built (M1/departments-from): People moves several people to a department at once, each move on the ledger under the mover (migration 0170); proved on the install with M1.6.21",
    updated: "2026-09-30",
  },
  "M1.6.16": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-accounts): the staff sync makes each active person's sign-in account and sends nobody anything; proved when a release has set up the accounts client and a reserved person's Forgot password sets their password and second factor (M1.6.18). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.sign_in_accounts, identity.staff_accounts, ops.acceptance_checks_accounts +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-09-30",
  },
  "M1.6.17": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-accounts): a leaver's or suspended person's account the sync made is closed on the next sync and their Brain sessions ended; proved on the install with a reserved leaver (M1.6.18). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.sign_in_accounts, identity.staff_accounts, ops.acceptance_checks_accounts +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-09-30",
  },
  "M1.10.1": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-are-people): every active person on the staff list is made a Brain person by the staff sync without the sign-in service, joined by their address's digest; proved on the install with M1.10.3. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_accounts, ops.staff_people_run); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M1.10.2": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-are-people): Sync now on Staff sources asks the worker for the scheduled staff sync and the page says when it last and next runs; proved on the install with M1.10.3. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.features, staff_source_routes, pages/staff-sources/StaffSourcesPage.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M1.10.4": {
    status: "READY FOR TESTING",
    why: "built (M1/add-work-email): Add work email on a hand-made person's page binds their address and joins the staff list's person for it; proved on the install with M1.10.5. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (directory_routes, identity.work_email, pages/people/PersonOverview.tsx +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M1.8.3": {
    status: "READY FOR TESTING",
    why: "built (PR #98): the staff sync writes a head's audit reads over their department's people and Audit is on the department menu; proved when a department head signs in and sees only their people's activity",
    updated: "2026-09-28",
  },
  "M1.8.5": {
    status: "BLOCKED",
    why: "moved to Wave 2 (needs-rupash 97): the web part is the owner's sign-in check (needs-rupash 91, check 1); the chat part needs Wave 2's Lark chat channel. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channel_routes, channels.inbound, chat_answer); open for proof on the install or a decision, not for code",
    updated: "2026-09-28",
  },
  "M1.8.8": {
    status: "READY FOR TESTING",
    why: "moved to Wave 4 (needs-rupash 112): closes when every permissions requirement row has its proof on the install. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes, tables.requirement_check, pages/RequirementChecks.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-09-29",
  },
  "M10.1.1": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M10.1.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.1.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.1.4": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.1.5": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M10.2.1": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M10.2.2": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); proved once the owner creates the Lark app from Connect Lark and a group mention is answered while an unmentioned message is left alone",
    updated: "2026-09-28",
  },
  "M10.2.5": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.2.6": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.3.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.3.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.3.3": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M10.3.4": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, Channels screen and identity binding (CH2)",
    updated: "2026-09-28",
  },
  "M10.4.1": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.4.2": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.4.3": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.4.4": {
    status: "READY FOR TESTING",
    why: "built in the Lark channel (L1, merged d426e3d3); provable server-side with bindings the check writes, and by a person once the binding route (CH2) lands",
    updated: "2026-09-28",
  },
  "M10.4.5": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M10.5.1": {
    status: "READY FOR TESTING",
    why: "Slack is connectable (#288): signed events in, answers on the bot token with the room read like Lark's, Connect Slack from an app manifest, and an install check; the owner's workspace proves the vendor's half. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channel_routes, channels.slack, ops.acceptance_checks_channels); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.5.2": {
    status: "READY FOR TESTING",
    why: "Teams is connectable (M10/channel-teams): Bot Framework tokens verified against Microsoft's published keys, the bot's App ID and the pinned tenant, answers in the chat on a token exchanged at the tenant's login, Connect Teams from an Azure Bot, and an install check; the owner's tenant proves the vendor's half. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.teams, ops.acceptance_checks_channels); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.5.6": {
    status: "READY FOR TESTING",
    why: "email is connectable (#285) by reading an ordinary mailbox over IMAP, the first choice (#296), or by Cloudflare Email Routing; answers leave by the install's relay; install checks for both; the owner's real mail proves the vendor's half. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channel_routes, channels.adapter, channels.email +9 more); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.5.4": {
    status: "READY FOR TESTING",
    why: "Telegram is connectable (M10/channel-telegram): saving the bot's username and token registers this install's events address with Telegram, updates carry a header made from the token, answers go out with sendMessage, and an install check; the owner's bot proves the vendor's half. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.telegram, ops.acceptance_checks_channels); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.5.3": {
    status: "READY FOR TESTING",
    why: "WhatsApp is connectable (M10/channel-whatsapp): Meta's signature checked over the exact bytes, its GET check of the address answered for the verify token, a notification of several messages answered message by message, answers on a system user's access token, and an install check; the owner's number proves the vendor's half. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.whatsapp, ops.acceptance_checks_channels); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.6.1": {
    status: "READY FOR TESTING",
    why: "all seven wires are live: webhook, Lark, email (a mailbox or Cloudflare), Slack, Teams, Telegram and WhatsApp (PR #105; L1, merged d426e3d3; #285; #296; #288; M10/channel-teams; M10/channel-telegram; M10/channel-whatsapp), each with its Connect steps and an install check. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channel_routes, channels.adapter, channels.email +13 more); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M10.6.3": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M11.1.1": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a connected source's worker sync runs through the declared interface and health shows it (Xero or HubSpot)",
    updated: "2026-09-28",
  },
  "M11.1.6": {
    status: "IN PROGRESS",
    why: "connect and disconnect routes are built (C1, merged 7c54d7d8); enable and upgrade have no caller yet",
    updated: "2026-09-28",
  },
  "M11.1.7": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a changed manifest makes the next sync refuse because the digest differs",
    updated: "2026-09-28",
  },
  "M11.4.1": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a sync leaves proj.record holding source, entity type, identifiers and hot fields",
    updated: "2026-09-28",
  },
  "M11.4.2": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a manifest projecting a thirteenth field is refused at review",
    updated: "2026-09-28",
  },
  "M11.4.3": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a field failing a projectability clause is refused at manifest review",
    updated: "2026-09-28",
  },
  "M11.4.4": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a projected email, phone, address, identity number, bank or salary field is refused",
    updated: "2026-09-28",
  },
  "M11.4.5": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a projected row stores its visibility predicate and no resolved list of people",
    updated: "2026-09-28",
  },
  "M11.4.7": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a source with no change signal projects no fields",
    updated: "2026-09-28",
  },
  "M11.4.9": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M11.8.1": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when manifest review refuses a field that is not an id, join key, status, timestamp, visibility predicate or short label",
    updated: "2026-09-28",
  },
  "M11.8.2": {
    status: "READY FOR TESTING",
    why: "built in connector registries and the minimal index (C1, merged 7c54d7d8); proved when a canary planted in a recorded response is found by the index audit in no table, memory, projection or log",
    updated: "2026-09-28",
  },
  "M12.1.1": {
    status: "READY FOR TESTING",
    why: "built in the tool catalogue and switch (T1, merged 1d2566c8); proved when agent.tool_definition lists each registered tool and its check constraint enforces the name grammar",
    updated: "2026-09-28",
  },
  "M12.1.3": {
    status: "IN PROGRESS",
    why: "the leash ceiling is built and shown on Tools (PR #102); its call on the agent run path comes with Wave 3's agent runtime",
    updated: "2026-09-28",
  },
  "M12.1.4": {
    status: "READY FOR TESTING",
    why: "built in the tool catalogue and switch (T1, merged 1d2566c8); proved when each tool on Tools declares a typed or opaque result contract",
    updated: "2026-09-28",
  },
  "M12.2.1": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when a SKILL.md with bad frontmatter pasted on Skills is refused saying why",
    updated: "2026-09-28",
  },
  "M12.2.2": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when a skill imported from a GitHub repository at a pinned commit lands unreviewed. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.skill_library, ops.acceptance_checks_skills, ops.skill_fetch +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +12 more",
    updated: "2026-09-28",
  },
  "M12.2.3": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when an import from an allowlisted address lands and a non-allowlisted one is refused. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.skill_library, ops.acceptance_checks_skills, ops.skill_fetch +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +12 more",
    updated: "2026-09-28",
  },
  "M12.2.4": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when a .zip with a traversing member is refused before anything is written",
    updated: "2026-09-28",
  },
  "M12.2.5": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, skill import, review and versions (T2)",
    updated: "2026-09-28",
  },
  "M12.2.6": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when an imported skill appears in the review queue with its line diff",
    updated: "2026-09-28",
  },
  "M12.3.2": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when an edited skill waits for review as a new version while the old stays readable; the agent-pin half shows once Wave 3 creates agents",
    updated: "2026-09-28",
  },
  "M12.3.8": {
    status: "READY FOR TESTING",
    why: "built in the tool catalogue and switch (T1, merged 1d2566c8); proved when a side-effecting tool whose name reads as a sensitive effect and declares none is refused at registration",
    updated: "2026-09-28",
  },
  "M12.4.12": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when a SKILL.md whose description does not open by saying when to use it is refused at import",
    updated: "2026-09-28",
  },
  "M12.4.13": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when Skills offers category chips drawn only from skills the reader can see",
    updated: "2026-09-28",
  },
  "M12.4.3": {
    status: "READY FOR TESTING",
    why: "built in the tool catalogue and switch (T1, merged 1d2566c8); proved when a tool switched off on Tools refuses every call naming the switch, and a department admin stops only their department",
    updated: "2026-09-28",
  },
  "M12.4.6": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when an admin's approval of their own import is listed as self_approved and another person's import needs a different reviewer",
    updated: "2026-09-28",
  },
  "M2.3.1": {
    status: "BLOCKED",
    why: "moved to Wave 2 (needs-rupash 97): the web part is the owner's department checks (needs-rupash 91, checks 2 and 3); the chat part needs Wave 2's Lark chat channel",
    updated: "2026-09-28",
  },
  "M2.3.2": {
    status: "READY FOR TESTING",
    why: "moved to Wave 4 (needs-rupash 112): closes when every departments requirement row has its proof on the install. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes, tables.requirement_check, pages/RequirementChecks.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-09-29",
  },
  "M23.1.1": {
    status: "READY FOR TESTING",
    why: "rate limits live (PR #101, merged): proved when a person asking past the window on the install gets the 429 and Ask says when to ask again",
    updated: "2026-09-28",
  },
  "M23.1.2": {
    status: "READY FOR TESTING",
    why: "rate limits live (PR #101, merged): proved when a person asking past the window on the install gets the 429 and Ask says when to ask again",
    updated: "2026-09-28",
  },
  "M23.1.3": {
    status: "READY FOR TESTING",
    why: "rate limits live (PR #101, merged): proved when a person asking past the window on the install gets the 429 and Ask says when to ask again",
    updated: "2026-09-28",
  },
  "M23.1.5": {
    status: "READY FOR TESTING",
    why: "rate limits live (PR #101, merged): proved when a person asking past the window on the install gets the 429 and Ask says when to ask again",
    updated: "2026-09-28",
  },
  "M23.2.1": {
    status: "READY FOR TESTING",
    why: "rate limits live (PR #101, merged): proved when a person asking past the window on the install gets the 429 and Ask says when to ask again",
    updated: "2026-09-28",
  },
  "M23.2.2": {
    status: "READY FOR TESTING",
    why: "the hourly denial digest runs in the worker (PR #101, merged): proved when a repeatedly refused colleague produces a notice on the install",
    updated: "2026-09-28",
  },
  "M24.3.4": {
    status: "BLOCKED",
    why: "the owner's audit check on the install (needs-rupash 91, check 4)",
    updated: "2026-09-28",
  },
  "M24.3.6": {
    status: "READY FOR TESTING",
    why: "moved to Wave 5 (needs-rupash 112): closes when every observability requirement row has its proof on the install. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes, tables.requirement_check, pages/RequirementChecks.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-09-29",
  },
  "M3.2.2": {
    status: "READY FOR TESTING",
    why: "channel pipeline (PR #105, merged, migration 0114): proved on the install with the signed webhook channel, set up, refused, delivered once and switched off",
    updated: "2026-09-28",
  },
  "M3.4.2": {
    status: "READY FOR TESTING",
    why: "the risk score is written to the request row on /answer (PR #99); proved by the first question asked on the install, read back from obs.request_telemetry",
    updated: "2026-09-28",
  },
  "M3.6.3": {
    status: "READY FOR TESTING",
    why: "the lane, tier and the rule behind each are written to the request row when chosen (PR #99, migration 0113); proved by the first question asked on the install",
    updated: "2026-09-28",
  },
  "M31.2.1.4": {
    status: "READY FOR TESTING",
    why: "engine tests pass for session and transaction pooling; closing needs PgBouncer on the install (M0.3.4)",
    updated: "2026-09-21",
  },
  "M31.3.2.1": {
    status: "READY FOR TESTING",
    why: "the vault opens itself from a root-only seal key and recovery pieces are an install choice (needs-rupash 114); proved when the owner's install is moved with ops/openbao/switch-to-auto-unseal.sh and reopens by itself after a restart",
    updated: "2026-09-29",
  },
  "M31.3.2.2": {
    status: "READY FOR TESTING",
    why: "every release applies its own vault policies, engines and roles with a root-only deploy token (needs-rupash 114); proved when the first deploy after the owner's move prints the vault in-force line",
    updated: "2026-09-29",
  },
  "M31.3.2.3": {
    status: "BLOCKED",
    why: "live since d6290cb; the proof is one connector sync on the install and none is connected yet: connecting Lark (needs-rupash 91, before you start) proves it",
    updated: "2026-09-28",
  },
  "M31.3.2.4": {
    status: "BLOCKED",
    why: "live since d6290cb; the proof is the lease revoked at the end of a connector sync on the install, which waits for the first connection (needs-rupash 91)",
    updated: "2026-09-28",
  },
  "M31.3.2.5": {
    status: "BLOCKED",
    why: "live since d6290cb; a DeepSeek key was replaced on the install on 28 Sep, and the proof is that provider answering with it without a redeploy, once the worker fix of 2026-09-28 deploys (needs-rupash 98)",
    updated: "2026-09-28",
  },
  "M32.1.1.1": {
    status: "READY FOR TESTING",
    why: "Built, wired and off until switched on; the memory wait is over (needs-rupash 120, decided A on 2026-10-05: the other project's Dify, old Langfuse and old v1 worker were taken down, so the five services need 2,304 MB of about 7,000 MB available, measured read-only on 2026-10-14). To prove it on the install: open Install, Settings, set Optional services this server runs to langfuse (add presidio after a comma if the detector is wanted too), save, wait for the next update to finish, then look at the install's next acceptance run, which runs after each update, and check the install check for the trace ledger's five services passes (web, worker, column store, cache and file store each running and healthy). To undo it set the setting back to none. It closes when the install's two newest runs both pass it. PRIOR WORK: ops.overlays, ops.acceptance_checks_services, ops.wiring, docker-compose.langfuse.yml",
    updated: "2026-10-14",
  },
  "M32.1.1.2": {
    status: "READY FOR TESTING",
    why: "Built, wired and off until switched on; the memory wait is over (needs-rupash 120, decided A on 2026-10-05; about 7,000 MB available against the 2,304 MB the ledger's limits add up to, measured read-only on 2026-10-14). Each of the five services carries a hard memory limit equal to its budget, and saving a list of services that would not all fit in the memory the server last measured is refused at Settings. To prove it on the install: switch langfuse on as for M32.1.1.1, then check the install check that each of the five runs under its budgeted limit passes. It closes when the install's two newest runs both pass it. PRIOR WORK: ops.overlays, ops.acceptance_checks_services, ops.wiring, docker-compose.langfuse.yml",
    updated: "2026-10-14",
  },
  "M32.2.1.1": {
    status: "READY FOR TESTING",
    why: "Built, wired and off until switched on; the memory wait is over (needs-rupash 120, decided A on 2026-10-05; the detector's 1,536 MB fits beside the ledger's 2,304 MB in about 7,000 MB available, measured read-only on 2026-10-14). To prove it on the install: open Install, Settings, set Optional services this server runs to presidio, save, wait for the next update to finish, then look at the install's next acceptance run, which runs after each update, and check the install check that the detector finds every entity the scrub relies on passes. To undo it set the setting back to none. It closes when the install's two newest runs both pass it. The model server (M32.2.1.2) still waits on a larger server (item 120, row 2). PRIOR WORK: ops.overlays, ops.acceptance_checks_services, ops.pii, docker-compose.presidio.yml",
    updated: "2026-10-14",
  },
  "M32.2.1.2": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14): the model server is an optional service that holds one part at a time, and the entity finder is one of its parts (1,408 MiB by arithmetic, not measured). Built: the server frame; the entity part's backend (GLiNER, written from its published interface and never run against it, reading long text in overlapping windows and returning only the labels asked for); the egress leg that asks it, added beside the analyser's and only ever adding to the rules' scrub, with a longer budget of its own and the rules' scrub standing whenever the part is down, loading or unreadable; and an install check that sends the part a sentence with a three-word name. Not built: GLiNER run for real (the image is unbuilt and the checkpoint is not fetched or pinned, needs-rupash 235). The first call after the part has been idle waits on a model load longer than the leg's budget and is scrubbed by the rules alone, so a longer idle time keeps the part loaded. PRIOR WORK: ops.inference, ops.pii (the wire contract and the merge), ops.egress",
    updated: "2026-10-14",
  },
  "M38.2.1.1": {
    status: "READY FOR TESTING",
    why: "WAVE_RECORDS and /build/waves are live on staging; proved when the first wave is accepted and recorded",
    updated: "2026-09-21",
  },
  "M38.2.2.2": {
    status: "BLOCKED",
    why: "needs a provider answering on the install (needs-rupash 98) and then the owner's real-answer check (needs-rupash 91, check 5)",
    updated: "2026-09-28",
  },
  "M38.2.2.3": {
    status: "READY FOR TESTING",
    why: "the Lark channel is merged (L1, d426e3d3); the exit check also needs question-time live read (C2) and the binding route (CH2), neither on main yet. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, chat_answer, ops.acceptance_checks_chat); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #152's branch M38/acceptance-chat-and-skills (may be replayed already)",
    updated: "2026-09-28",
  },
  "M38.4.1.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, connector registries and the minimal index (C1), under the owner's rule that connectors never bulk-sync",
    updated: "2026-09-28",
  },
  "M41.3.1": {
    status: "BLOCKED",
    why: "the first release tag is cut when Wave 0 is accepted (needs-rupash 77, decided); waits for M31.3.2.3 to M31.3.2.5",
    updated: "2026-09-28",
  },
  "M5.6.1": {
    status: "BLOCKED",
    why: "Anthropic, OpenAI and DeepSeek keys are in the vault; the worker could not see the install's saved online-providers setting until the fix of 2026-09-28, and Moonshot has no key (needs-rupash 98)",
    updated: "2026-09-28",
  },
  "M5.6.3": {
    status: "BLOCKED",
    why: "a proved fallback needs two providers answering on the install, which waits for the worker fix of 2026-09-28 to deploy",
    updated: "2026-09-28",
  },
  "M5.6.5": {
    status: "READY FOR TESTING",
    why: "moved to Wave 3 (needs-rupash 112): closes when every models requirement row has its proof on the install. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes, tables.requirement_check, pages/RequirementChecks.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-09-29",
  },
  "M5.7.1": {
    status: "READY FOR TESTING",
    why: "moved to Wave 5 (needs-rupash 113): Anthropic and Moonshot answer on the install; OpenAI and DeepSeek are turned off until their accounts are funded. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (models.default_ladder, models.wire, ops.acceptance_models +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #163's branch M27/console-models-routing (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); +3 more",
    updated: "2026-09-29",
  },
  "M7.1.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.1": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14): the model server is an optional service that holds one part at a time, and the layout part is one of them (1,344 MiB by arithmetic with documents up to 25 MB, not measured). Built: the server frame (supervisor, budget, switch, settings, measured peaks); the layout part's backend, written from Docling's published interface and never run against it; and the route that sends a queued upload to it before the reader in this process, with an outage left waiting in the queue and the path the read took returned with it. An install check sends the part a one-page PDF. Not built: Docling run for real (the image is unbuilt and unpublished, needs-rupash 235); the path stored beside each passage and shown in a citation (the columns exist, nothing writes them). PRIOR WORK: knowledge.parse_layout (the contract), ops.inference",
    updated: "2026-10-14",
  },
  "M7.2.2": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.3": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14): the general reader is one part of the optional model server (a JVM, 832 MiB by arithmetic, not measured). Built: the server frame; the fallback route's rule and its use in the ingest job (a presentation goes layout then this reader, and an outage waits in the queue instead of ending the file); the part's backend, which starts Tika's server and asks it for plain text only, never metadata, written from Tika's documentation and never run against it. An install check sends it a one-page PDF. Not built: Tika run for real (the image is unbuilt, needs-rupash 235), and a check that sends it a format the layout part cannot open, which is what the leaf is for. PRIOR WORK: knowledge.parse_paths",
    updated: "2026-10-14",
  },
  "M7.2.4": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14): the scanned-page reader is one part of the optional model server (Tesseract, 576 MiB by arithmetic, not measured). Built: the server frame; the part's backend (a PDF page rendered and recognised one at a time, with a confidence for every page, written from the libraries' published interfaces and never run against them); the route that sends a scan to it last, after the layout part and the reader in this process; and the door that now accepts a photograph when this part is chosen, after the structural check judges its header (a header claiming more pixels than any page has is refused). An install check renders and recognises a one-page PDF. Not built: the libraries run for real (the image is unbuilt, needs-rupash 235), and a check of a real scan. PRIOR WORK: knowledge.parse_ocr (the contract, now wired)",
    updated: "2026-10-14",
  },
  "M7.2.5": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.6": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.ingest_queue, knowledge.parse_budget, knowledge.scanning); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #129's branch M7/links-scanning-queue (may be replayed already)",
    updated: "2026-09-29",
  },
  "M7.3.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.3.2": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.3.3": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14): the embedding part is the default and the smallest of the model server's parts (Qwen3-Embedding-0.6B at 8 bits, 1,088 MiB by arithmetic, not measured). Built: the server frame (supervisor, budget, switch, settings, measured peaks, two install checks of the frame); the embedding part's backend (written from llama.cpp's published interface and never run against it, stating the weights' own revision); the worker passing what its clients were told of the server's memory to the table, and writing it even when the job failed; the model server screen showing the revision the server holds beside the one the install declares; and an install check that the two are the same. Not built: the part run for real (the image is unbuilt and the weights are not fetched, needs-rupash 235), and so no passage embedded by it on an install. PRIOR WORK: knowledge.embed, embed_policy, embed_queue, ops.inference_client",
    updated: "2026-10-14",
  },
  "M7.3.4": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14). The queue exists and tolerates a server that is down by design: a part not loaded, a host without room and a busy server all answer as an outage, so the work waits and nothing is lost, and the product's client and the real gateway and supervisor are exercised against each other over a loopback socket in tests with the library stood in. Not yet: a batch sent to a real embedding part on an install (needs-rupash 235). PRIOR WORK: knowledge.embed_queue",
    updated: "2026-10-14",
  },
  "M7.3.5": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14). The rebuild command and the plan are built (knowledge.reembed), and the embedding part it sends to now exists; a rebuild run on an install whose server answers is what proves it, and that waits on the image (needs-rupash 235). PRIOR WORK: knowledge.embedding, knowledge.reembed",
    updated: "2026-10-14",
  },
  "M7.4.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.2": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.3": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.4": {
    status: "READY FOR TESTING",
    why: "built in knowledge lifecycle (K2, merged f0722dd3); proved when a company-wide request waits on Approvals and applies only when another holder of approve:knowledge.visibility approves",
    updated: "2026-09-28",
  },
  "M7.4.5": {
    status: "READY FOR TESTING",
    why: "built in knowledge lifecycle (K2, merged f0722dd3); proved when a newer version uploaded on a document shows the old one superseded and answers use the new one",
    updated: "2026-09-28",
  },
  "M7.4.6": {
    status: "READY FOR TESTING",
    why: "built in knowledge lifecycle (K2, merged f0722dd3); proved when a past review date makes the worker's re-verification run open the owner's task, and verifying closes it",
    updated: "2026-09-28",
  },
  "M7.4.7": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M7.5.1": {
    status: "READY FOR TESTING",
    why: "built in classified tables (K6, merged c0552331 and 9e277b69); proved when a price list CSV or XLSX uploaded on Classification has each column classified open, restricted or derived",
    updated: "2026-09-28",
  },
  "M7.5.2": {
    status: "READY FOR TESTING",
    why: "built in classified tables (K6, merged c0552331 and 9e277b69); proved when a reader without the cost grant asks a service's price and gets the sell price with cost and margin withheld",
    updated: "2026-09-28",
  },
  "M7.5.3": {
    status: "READY FOR TESTING",
    why: "built in classified tables (K6, merged c0552331 and 9e277b69); proved when a column marked, reviewed and applied on Classification leaves the change in the ledger",
    updated: "2026-09-28",
  },
  "M7.6.1": {
    status: "IN PROGRESS",
    why: "a kind is set at upload and filters the library and the search tool (PR #106); Ask has no kind picker yet",
    updated: "2026-09-28",
  },
  "M7.6.2": {
    status: "READY FOR TESTING",
    why: "built in knowledge lifecycle (K2, merged f0722dd3); proved when a captured solution waits until another admin:knowledge holder approves it, then answers as a verified approved solution",
    updated: "2026-09-28",
  },
  "M7.6.3": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.7.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.7.10": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14). Built: a scanned page under the confidence floor is left out of the index, page by page, with every later offset laid out again for what stayed; the parser hands the pages it left out to the knowledge layer (`ReadWithGaps`, `ParsedDocument.left_out_pages`) with the uploader's wording for them (`left_out_notice`), a page with no recognised word is not named; the pages are kept on the item (`know.item.parse_notice`) and said on the ticket (\"was added. Page 2 was not clear enough...\"); the blank pages of a PDF the layout part read are read by the scanned-page part and the same floor applies to them. Proved against a real PostgreSQL over answers made up for the test. Not built: the notice shown on a screen, and the scanned-page part run for real (needs-rupash 235). PRIOR WORK: knowledge.parse_ocr",
    updated: "2026-10-14",
  },
  "M7.7.11": {
    status: "IN PROGRESS",
    why: "The owner's choice is made (needs-rupash 119, 25 MB for every document type) and is the model server's default upload setting; the server's memory follows it, and a larger document makes a larger server. Built: the setting and its sizing; the worker's start-up finding that the door admits more than the server is sized for, against the ceiling the install's own parts and upload size give and said only for an install whose server reads documents; and an install check that holds the memory peaks the server has recorded against its limit. Not built: a check that sends the largest upload the install admits through a part, which would cost minutes on every update; peaks are only recorded for documents once the worker keeps them (the next piece). PRIOR WORK: knowledge.app_parse_budget",
    updated: "2026-10-14",
  },
  "M7.7.2": {
    status: "READY FOR TESTING",
    why: "a steward for every document, source and agent, and the self-grant notice on Access requests (migration 0167): proved when the install check a_steward_is_named_and_told_of_access_somebody_gave_themselves passes after deploy",
    updated: "2026-09-30",
  },
  "M7.7.3": {
    status: "IN PROGRESS",
    why: "price lists uploaded on Classification convert (K6, merged c0552331); no upload path yet offers a price-list document for conversion",
    updated: "2026-09-28",
  },
  "M7.7.8": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14). Not blocked on memory. Every vector already records its model (know.chunk.embedding_model, migration 0010) and a search never compares two models; while a rebuild runs, answers come from word search alone, which is what is built. The owner's sentence says the previous vectors keep serving, which the product decided against and put to him as needs-rupash 186 (still open; Option B builds it with a second column and one migration). PRIOR WORK: knowledge.embedding, knowledge.reembed",
    updated: "2026-10-14",
  },
  "M7.7.9": {
    status: "IN PROGRESS",
    why: "The memory wait is over by design (needs-rupash 120, redrawn 2026-10-14). Built: every block, passage and chunk row carries the path and engine that read it, set by the route and never by the reader's answer and closed to three words and a bounded name; a PDF read two ways (text pages by layout, a photographed page by the scanned-page part) is stored passage by passage saying which read each, written to know.chunk.parse_path and parse_engine (migration 0250) and checked against a real PostgreSQL and by an install check. Not built: **no citation or screen says how a passage was read yet**, which means carrying the column through retrieval, the field policy that decides what a reader is shown, DocumentCitation and its rendering, a change to the surface that decides what a reader may be told and wanting its own review. PRIOR WORK: knowledge.parse_paths, knowledge.parse_ocr",
    updated: "2026-10-14",
  },
  "M8.1.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M8.1.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M8.1.4": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M8.2.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M8.2.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
    updated: "2026-09-28",
  },
  "M8.2.4": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.abstain, gate.answer, gate.model_lane +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #117's branch M8/citations-freshness-abstention (may be replayed already); closed PR #131's branch M8/citations-freshness-abstention-r2 (may be replayed already); closed PR #143's branch M8/citations-freshness-abstention-r3 (may be replayed already); +2 more",
    updated: "2026-09-28",
  },
  "M8.3.1": {
    status: "READY FOR TESTING",
    why: "escalation (migration 0168): proved when the install check an_escalated_question_reaches_its_person_and_times_out passes after deploy",
    updated: "2026-09-30",
  },
  "M8.3.2": {
    status: "READY FOR TESTING",
    why: "escalation (migration 0168): proved when the install check an_escalated_question_reaches_its_person_and_times_out passes after deploy",
    updated: "2026-09-30",
  },
  "M8.3.4": {
    status: "READY FOR TESTING",
    why: "escalation (migration 0168): proved when the install check an_escalated_question_reaches_its_person_and_times_out passes after deploy",
    updated: "2026-09-30",
  },
  "M8.4.1": {
    status: "READY FOR TESTING",
    why: "escalation and sensitive topics (migration 0168): proved when both install checks in brain.ops.acceptance_escalation pass after deploy, and on a real channel once a queue's person is named on the Compliance screen",
    updated: "2026-09-30",
  },
  "M1.10.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_accounts); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.1.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.declaration, connectors.mcp, connectors.transports +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.1.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.custom_code, connectors.declaration, connectors.transports +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.4.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.change_signal, connectors.declaration, connectors.freshdesk +10 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.4.8": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.backfill, ops.acceptance_checks_change_signals, ops.connector_sync +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.6.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.declaration, connectors.laravel, knowledge.connector_rows +10 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M11.6.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.declaration, connectors.freshdesk +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M11.6.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, connectors.lark_base, knowledge.lark_base_rows +5 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.6.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, connectors.lark_wiki, ops.acceptance_checks_lark_wiki +5 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.6.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.ask, connectors.xero +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #142's branch M11/live-read-speed-budget (may be replayed already)",
    updated: "2026-10-06",
  },
  "M11.6.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.hubspot); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.6.7": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.google_drive, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, connectors.date_range, connectors.declaration +12 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M11.7.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.search_console, knowledge.connector_figures, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in approval_routes, connector_routes, connectors.cloudflare +16 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +7 more",
    updated: "2026-10-06",
  },
  "M11.7.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connector_routes, connectors.declaration, connectors.domains +6 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.7.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.slack_messages, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_oauth); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: PR #387 (M11/w2-google-workspace); branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M11.7.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, app, connector_routes +19 more; NOT wired: pages/CustomConnectors.route.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_freshdesk_reply); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.11": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_change_signals, ops.connector_sync, ops.connector_sync_run +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.12": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.freshdesk, ops.acceptance_freshdesk_reply, ops.connector_write_run); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M11.8.13": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.8.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_sources); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.8.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, ops.acceptance_checks_change_signals, ops.connector_sync +3 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connector_routes, connectors.declaration, connectors.oauth +17 more; NOT wired: ops.effects, pages/ConnectorConsent.route.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.federation, ops.acceptance_schema_drift, ops.connector_sync +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.8.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_live_answers, requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.10": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.11": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.13": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.14": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.15": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.declaration, connectors.google_drive, ops.acceptance_checks_change_signals +3 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.9.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_lifecycle_routes, connectors.lark_base, connectors.lark_wiki +15 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +9 more",
    updated: "2026-10-06",
  },
  "M11.9.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.freshdesk, ops.acceptance_checks_connectable, ops.connectable); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M11.9.7": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.8": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.9": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M12.2.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, tools.skills); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M12.2.8": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, ops.acceptance_checks_skill_runs, tools.skills); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M12.2.9": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, ops.sandbox, ops.sandbox_runner +2 more; NOT wired: ops.sandbox_client. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M12.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, console.skill_library, ops.skill_store +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M12.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, ops.skill_store, skill_routes +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M12.4.11": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.sandbox, ops.skill_store, tables.skill +2 more; NOT wired: ops.sandbox_client. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M12.4.15": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M12.4.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, ops.website_probe, tools.startup +1 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M12.4.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_services, ops.sandbox, ops.sandbox_runner); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.model, ops.acceptance_checks_agents, tables.agent); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.model, ops.acceptance_checks_agent_reach); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.template, ops.acceptance_checks_agents); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_routes, agents.template, gate.roster +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_upgrade_routes, agents.upgrade, ops.acceptance_checks_upgrade +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR",
    updated: "2026-10-06",
  },
  "M13.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_upgrade_routes, agents.upgrade, ops.acceptance_checks_upgrade +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR",
    updated: "2026-10-06",
  },
  "M13.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_upgrade_routes, agents.upgrade, ops.acceptance_checks_upgrade +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR",
    updated: "2026-10-06",
  },
  "M13.4.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_upgrade_routes, agents.upgrade, ops.acceptance_checks_upgrade +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR",
    updated: "2026-10-06",
  },
  "M13.5.18": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.catalogue, ops.acceptance_checks_templates); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.7.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, gate.answer, gate.caches +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-runtime-side-effects, no PR",
    updated: "2026-10-06",
  },
  "M13.7.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.model, gate.runtime, gate.stop +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-runtime-side-effects, no PR",
    updated: "2026-10-06",
  },
  "M13.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, console.agent_automations, ops.acceptance_halt +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.7.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_builder_routes, agent_lifecycle_routes, agents.install_store +17 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +7 more",
    updated: "2026-10-06",
  },
  "M13.7.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_agent_reach); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.7.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.freshdesk, gate.runtime, ops.acceptance_approved_runs +7 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M13.7.7": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.runtime, ops.runtime_effects, tools.proposed_writes); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-runtime-side-effects, no PR",
    updated: "2026-10-06",
  },
  "M13.7.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.binding, ops.acceptance_checks_binding); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.8.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.binding, agents.model, gate.runtime +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M13.8.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.runtime); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-runtime-side-effects, no PR",
    updated: "2026-10-06",
  },
  "M14.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_registry, resolution.normalise); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.3.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (resolution.cascade, resolution.guardrails); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_calibration, resolution.calibration, resolution.calibration_store +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.sweeps, resolution.calibration, resolution.matcher +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_calibration, resolution.calibration, resolution.calibration_store +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_calibration, ops.controls, ops.schedule_runner +8 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.6.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, gate.answer, gate.fast_lane +4 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M14.7.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (resolution.entities); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.7.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (resolution.entities); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.8.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_calibration, resolution.calibration_store, resolution_routes +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M15.3.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.quality, ops.acceptance_retrieval); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M15.3.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.assembly, ops.acceptance_retrieval); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M15.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, gate.caches, gate.provenance +14 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +7 more",
    updated: "2026-10-06",
  },
  "M16.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, gate.model_lane, gate.turn_context +5 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: closed PR #245's branch M16/w3-waiting (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M16.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (chat.thread_store, memory.signals); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M16.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.answer, memory.signals); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M16.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (chat.remember, chat.thread_store, gate.answer +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M16.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, memory.tiers, ops.session_memory_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.3.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.formation, memory.tiers); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already)",
    updated: "2026-10-06",
  },
  "M16.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.correction); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in learning_told, memory.digest, mine_routes +3 more; NOT wired: pages/LearningUndo.route.tsx",
    updated: "2026-10-06",
  },
  "M16.5.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.review); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.6.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in gate.answer, gate.model_lane, gate.runtime +2 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M16.6.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.turn_context); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.6.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, channel_routes, channels.inbound +6 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); closed PR #299's branch M8/w2-escalation (may be replayed already)",
    updated: "2026-10-06",
  },
  "M16.6.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in candidate_routes, chat.turns, knowledge.candidate_store +9 more; NOT wired: pages/Corrections.route.tsx. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M16.6.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in candidate_routes, knowledge.candidate_store, knowledge.candidates +5 more; NOT wired: pages/Corrections.route.tsx. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M16.7.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in candidate_routes, knowledge.candidate_store, knowledge.candidates +4 more; NOT wired: pages/Corrections.route.tsx. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M17.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/jobs.py has JobState, advance, JobRecord, next_attempt_at, worst_case_runs (test_jobs) but no table of ours: the docstring says nothing persists it. The real job rows are Procrastinate's (ops/queue.py); the Jobs screen (jobs_routes) lists scheduled controls and their runs, not JobState rows. NEXT: map the driver's job rows onto JobState in the Jobs/Live runs read, or decide the driver's own states are the job table and retire the model; then a check reading GET /jobs",
    updated: "2026-10-13",
  },
  "M17.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/queue.py enqueue_job, register_task, queue_app, run_shards; ops/worker.py drains a real queue (install_queue, run_shards); callers: knowledge_routes, knowledge_intake_routes, knowledge_lifecycle_routes, ingest_queue. Tests: test_control_task, test_jobs; ops/jobs.py says M17.1.2 is claimed in ops.queue. NEXT: write check naming M17.1.2 that enqueues a task through knowledge ingest (acceptance_ingest already uses queue_url_of) and sees the worker pick it up",
    updated: "2026-10-13",
  },
  "M17.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): queue.worker_shards allocates concurrency per traffic class; ops/worker.py starts one shard per class (run_shards, queue_pool_gaps). Per-task caps (jobs.TaskPool) are not enforced, which the jobs docstring says openly; the leaf names per-class. NEXT: write check naming M17.1.3 reading the worker's plan (worker_shards for each slot class) from the install's configuration",
    updated: "2026-10-13",
  },
  "M17.1.4": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21. Every task of ours now has a deadline (brain.ops.queue.TASK_DEADLINE_SECONDS, one heartbeat inside the staleness window): register_task cancels a task that overruns and fails the attempt with TaskDeadlineExceededError, and refuses a deadline of nothing or one past the window. Not built: a cancel control that calls jobs.interrupt over the driver's abort, which needs a screen listing the queue's jobs (M17.1.1).",
    updated: "2026-10-20",
  },
  "M17.1.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/jobs.py dead_letter_for, visible_dead_letters, DeadLetter (filtered, no count) are built; only dead_letter_summary has a consumer in console modules. No route or page lists dead letters: jobs_routes and operate_routes show scheduled controls and owed runs. NEXT: add GET /jobs/dead calling visible_dead_letters over driver rows in failed state and a Dead letters tab on the Jobs page",
    updated: "2026-10-13",
  },
  "M17.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/checkpoint_store.py install_checkpointer is called by ops/worker.py at start (schema plus row-level security) and guarded_saver exists with ownership checks (test_checkpoint_store). Nothing compiles a graph, so guarded_saver has no caller and no run saves state. NEXT: wire guarded_saver into the first graph the agent runtime compiles (orchestration/plan or gate/runtime), then a check that a run's state is read back",
    updated: "2026-10-13",
  },
  "M17.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/crash.py redrive/verify_once are called by ops/recovery_run.py (scheduled control, schedule_runner.queue_redrive) which moves recoverable jobs and operations. acceptance_checks_recovery covers it under M23.3.1 only. Tests: test_crash, invariants. NEXT: add M17.2.2 to the leaves of the recovery run check in acceptance_checks_recovery.py",
    updated: "2026-10-13",
  },
  "M17.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Operation ledger writes are durable before and after the effect (idempotency.issue_once, operation_store) and crash.side_effect_boundaries derives every boundary, used by tests/invariants/test_crash_exactly_once. There is no graph state to checkpoint at those points. NEXT: a check issuing a keyed effect and reading back both ledger states; graph-level checkpoint waits on M17.2.1 wiring",
    updated: "2026-10-13",
  },
  "M17.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Interrupted work resumes: recovery_run re-drives running and failed jobs and verify_once settles operations left UNKNOWN (ops/crash.py, controls); suspensions persist in gate/suspension_store and resume through leash.resume. acceptance_checks_recovery exists for M23.3.1. NEXT: write check naming M17.2.4: leave an operation in a mid state, run the recovery control, assert one effect and state intact",
    updated: "2026-10-13",
  },
  "M17.2.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): leash.resume re-resolves the approver's reach on every decision (approval_routes take_decision); automation_run resolves the owner's live reach at each run; jobs carry a principal and never a reach (jobs.reach_carrying_fields, crash.stored_reach_gaps). Tests: test_leash, invariants. NEXT: write check naming M17.2.5: raise a suspension, revoke the approver's grant, press approve, expect refusal",
    updated: "2026-10-13",
  },
  "M17.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): issue_once keys every send: channels (adapter, email, lark, slack, teams, telegram, whatsapp), gate/leash, ops/digest_delivery, connector_write_run, browsing/runner. ops/effects.py is the register read by tests/invariants/test_every_side_effect_is_keyed (it has no runtime caller by design). NEXT: write check naming M17.3.1: send the same keyed message twice through a channel adapter and see one send and one Repeated",
    updated: "2026-10-13",
  },
  "M17.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/idempotency.py OperationState (pending, sent, unknown, verifying, succeeded, failed) with RESUME_PLAN and advance, persisted by ops/operation_store.py and tables/operation.py (PostgresOperationLedger). Tests: test_idempotency, test_operation_store. NEXT: write check naming M17.3.2 walking one operation through its states in the install's ledger and reading it back",
    updated: "2026-10-13",
  },
  "M17.3.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): connectors/write_verification.verdict plus each connector's ReadBack declaration (hubspot, laravel, xero, freshdesk, lark, drive); ops/connector_write_run reads the record back and reports done only when FOUND (cloudflare write is the live user; acceptance_checks_cloudflare). Module docstring saying no connector writes is stale. NEXT: write check naming M17.3.3 over the cloudflare approved-write read-back (acceptance_checks_cloudflare setup)",
    updated: "2026-10-13",
  },
  "M17.3.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): write_verification.read_back_gaps refuses a connector declaring a write with no reading, and ops/idempotency.issuable_tools returns tools with read-back; WriteGrant is a separate declared grant in connectors/declaration. issuable_tools has no runtime caller (enforced by tests and declaration). NEXT: write check naming M17.3.4 reading the shipped manifests and asserting every write-declaring connector declares a ReadBack",
    updated: "2026-10-13",
  },
  "M17.3.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): tests/invariants/test_crash_exactly_once.py kills at every derived boundary over the in-memory ledger and test_idempotency CRASH_POINTS; a real process kill is not done. Install proof would use PostgresOperationLedger. NEXT: write check naming M17.3.5 that issues a keyed effect, simulates loss of the answer, resumes through crash.verify_once on the install's ledger and counts one effect",
    updated: "2026-10-13",
  },
  "M17.4.1": {
    status: "READY FOR TESTING",
    why: "built (M17/automation-start-sources) to needs-rupash 223 option B: an automation starts by a schedule or by a connector change and by nothing from outside. ops/automation_event decides what is due (per-pass and per-hour bounds, a change run once by its id), ops/automation_event_store finds changed records inside the owner's row scope and runs each as the owner through admitted_run, and the index's updated_at now moves only when a record's fields change. A webhook is refused when written and the form lists it as not offered. Behind the automation_events switch, which ships off. Proved on the install by the check a_change_starts_one_run_as_an_owner_who_may_read_it once the owner switches it on and changes a record. NOT BUILT: a condition is still not applied to a change or a schedule (needs-rupash 177); the signed inbound address is not built until a real automation needs it. PRIOR WORK: Schedule trigger built (automation_run, run_automations_now); TriggerKind existed with nothing starting a run on two of its kinds.",
    updated: "2026-10-14",
  },
  "M17.4.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Named outcome templates are built and installed paused: console/automation_gallery BUILT_IN (weekly summary, unanswered questions, source freshness) and POST install route; ops/automation_run.TASKS has one performer. Workflows as stored versioned step data from the console do not exist (see M17.6.1). NEXT: build the stored versioned workflow data (reuse builder/draft_store revisions) and the console authoring page; templates stay as they are PLAN 2026-10-12: also the data model behind New automation on the agent page (M39.9.2.1); a template with changed settings needs none of it, anything else does.",
    updated: "2026-10-13",
  },
  "M17.4.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/automation_run resolves the owner's live reach at each run through flow_reach (A_RUN_IS_ITS_OWNERS_AT_THE_INSTANT_IT_STARTS), started by schedule_runner; automation_routes.tool_call looks the owner up at every call. acceptance_checks_automation covers the tool door under M32.6 only. NEXT: write check naming M17.4.3: install an automation, revoke an owner grant, run it, assert the run's reach lacks it",
    updated: "2026-10-13",
  },
  "M17.4.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): automation_run pauses the automation with a closed reason when the owner is gone, the agent disabled or the reach lacks what the task reads; automations_routes ADOPT_PATH offers it to another person; notice automation_paused is sent (automation_paused_told). Tests: automation run tests. NEXT: write check naming M17.4.4: remove the owner's required grant, run due automations, assert paused with reason and adoptable",
    updated: "2026-10-13",
  },
  "M17.4.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): orchestration/unattended.ApprovalStep, approval_refusals and expire are built (test_orchestration_unattended) with no caller; adoption.py imports only TriggerKind from it. Installed automations have no approval step at all, so there is nothing to time out. NEXT: give automation_run an approval step and call approval_refusals and expire from it; agent approvals already lapse via leash windows",
    updated: "2026-10-13",
  },
  "M17.4.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Run history exists: console/agent_automations AutomationRun, automations_routes detail and stats, tables/automation_run. Cost per run is not recorded: RUN_COST_IS_NOT_RECORDED in automations_routes says so. unattended.CostedRun/history is unwired. NEXT: record cost per run (spend actuals joined by run id) and surface it in AutomationRun and the stats route",
    updated: "2026-10-13",
  },
  "M17.5.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/outbox.py plan_next retry and backoff, outbox_store (tables/outbox.py), ops/webhook_delivery.run_dispatch_now started by schedule_runner.outbox_dispatch; events written by automation_run, item_store, outbox_store. Tests: test_outbox, test_outbox_store. NEXT: write check naming M17.5.1: register a subscriber to a refused address, write an event, run the dispatch control, assert attempts and backoff",
    updated: "2026-10-13",
  },
  "M17.5.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): outbox.signed_request/signature_for sign each delivery in the worker alone (webhook_delivery reads the secret), sent through issue_once so a delivery is at-least-once with one effect per id. Test: test_outbox. NEXT: write check naming M17.5.2: dispatch to a local receiver, verify the signature with signature_matches and that a replay sends once",
    updated: "2026-10-13",
  },
  "M17.5.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Webhooks screen: webhook_routes (list, register, rotate secret, switch off and on, replay) over console/subscribers and ops/outbox_store, page console/src/pages/webhooks. Tests: test_subscribers, test_outbox_store. NEXT: write check naming M17.5.3: register, list, switch off and replay a subscriber through the route functions",
    updated: "2026-10-13",
  },
  "M18.1.2": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): contract.validated()/validated_or_none() refuse a result that does not match its schema (tested); merge.merge only takes ValidatedResult. No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: call contract.validated on each child's reply in the orchestrator before it is handed to merge; a failure becomes a gap, not an input",
    updated: "2026-10-13",
  },
  "M18.1.4": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): orchestration/plan.py DependencyGraph with Node cost and Edge coupling weights, read_proposal(), plan_refusals() (tested in test_orchestration_plan.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: feed it the planner proposal (M18.5.3) and pass the graph to fanout.decide",
    updated: "2026-10-13",
  },
  "M18.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): orchestration/fanout.py six Conditions evaluated by gate_inputs(), holds(), failures(), decide() before any child starts (tested in test_orchestration_fanout.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: call fanout.decide(graph, depth) in the orchestrator before dispatching children",
    updated: "2026-10-13",
  },
  "M18.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): fanout.decide returns Verdict.SINGLE_LOOP when any condition fails, the default (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: honour the verdict in the orchestrator: run the plan as one loop when SINGLE_LOOP",
    updated: "2026-10-13",
  },
  "M18.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): fanout.GateRecord holds inputs, failures and verdict with AUDIT_SURFACE and gate_record_gaps (tested). Nothing persists a record: no table, no trace field, no caller. NEXT: persist the GateRecord on the run's trace (tables or ledger) when decide() runs, then show it on the run's page",
    updated: "2026-10-13",
  },
  "M18.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): core/scope_sql.py gate.delegated_reach computes parent intersect agent intersect subtask in SQL; installed by migrations 0028, 0029, 0033 with gate.delegation. test_delegation_sql.py compares it to EntitlementSet.intersect on a real server. Nothing in the app inserts rows yet. NEXT: write check naming M18.3.1: insert a root and child delegation row in the harness and assert the stored child reach equals the Python intersect",
    updated: "2026-10-13",
  },
  "M18.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Trigger gate.delegation_narrows (core/scope_sql.py, migrations 0028 and 0033) refuses any insert or update whose reach is not a subset of its parent; 30-odd real-server tests in test_delegation_sql.py. No application code writes the table yet. NEXT: write check naming M18.3.2: via h.execute insert a widening child row and assert the database refuses it, then a narrowing row and assert accepted",
    updated: "2026-10-13",
  },
  "M18.3.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): delegation.grant_verbs_in() scans the orchestrator for grant operations and tests assert none exist (test_orchestration_delegation.py); there is no orchestrator runtime to grant anything. CI-asserted by design. NEXT: repo-only leaf: close as Proved-in-ci naming the unit job running test_orchestration_delegation.py",
    updated: "2026-10-13",
  },
  "M18.3.4": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.3.5": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.4.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): orchestration/merge.py merge() builds a MergedAnswer only from ValidatedResult inputs (tested in test_orchestration_merge.py). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: call merge from the orchestrator and return MergedAnswer to the asker as the run's answer",
    updated: "2026-10-13",
  },
  "M18.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): merge.SubtaskReport carries cost and duration per subtask into MergedAnswer (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. No route or page shows it. NEXT: expose per-subtask cost and duration on the run's answer payload and in the console run view",
    updated: "2026-10-13",
  },
  "M18.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): merge.Gap, GapCause, GapTrace state the gap when a subtask failed, and merge_refusals refuses a silent hole (tested). No module outside brain.orchestration imports it (git grep), so no run uses it; the old proxy note said wired but only docstrings mention the package. NEXT: carry the stated gap into the user-visible answer from the orchestrator",
    updated: "2026-10-13",
  },
  "M19.1.1": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 on browsing/sandbox.py and launcher.py (triage 2026-10-13 class 2): the launcher can rehearse a run (Launcher.rehearse): it makes the run's network, proxy and runner as a real run would, reads the Docker daemon's own description of them (browsing/inspection.py), removes them and counts what is left, starting no browser. The install check a_browser_sandbox_is_made_for_one_run_and_removed_with_it holds that description to the product's own expectations and reports NOT RUN, in one sentence, while browser runs are off or no launcher answers. This leaf: a gVisor container per run, named and labelled with the run id; the check requires the runner to report runtime runsc and two runs to get different names. INSTALL PROOF STEPS: 1. On the Features page switch on 'Let agents run a browser'. 2. Compose the browser overlay (docker-compose.browser.yml) on a host with gVisor as ops/browser/REHEARSAL.md sections 1 to 3 say, and confirm the browser-launcher container is healthy. 3. On the Install page press Run now and read the row a_browser_sandbox_is_made_for_one_run_and_removed_with_it: it must say Passed. NOT PROVED UNTIL a host with gVisor has run it.",
    updated: "2026-10-20",
  },
  "M19.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/browser/Dockerfile and playwright_browser.py (Playwright, Chromium) are the runner image and entry; browsing/runner.py:drive is what it calls. Playwright is not a repo dependency, no workflow builds the -browser image (release.yml builds only the app image), never run. NEXT: Add a release job that builds and signs the '-browser' image, run REHEARSAL.md sections 1 to 3, then a check that a run's runner reports chromium and playwright versions.",
    updated: "2026-10-13",
  },
  "M19.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): browsing/runner.py:drive owns the line protocol, playwright_browser.py the CDP session, wire.py:snapshot_fields serialises snapshots; test_browsing_runner.py and test_browsing_wire.py cover the decisions. The runner is never run on a Docker daemon, gVisor or Chromium (browsing/__init__.py, ops/browser/REHEARSAL.md). NEXT: Same step as M19.1.2: build the runner image, rehearse one run and check a snapshot line reaches the launcher.",
    updated: "2026-10-13",
  },
  "M19.1.4": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in page. What a run observes of a page is a tree: the snapshot a runner sends has the sequence, the origin and the nodes and no other field (the wire refuses any other), and vision_gaps finds no field a picture could arrive in on the observation types. Shown by install check a_credential_reaches_the_page_and_is_kept_nowhere over the stored transcript. The page is a stand-in; a real Chromium tree is the rehearsal. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read that row: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.1.5": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 on browsing/sandbox.py and launcher.py (triage 2026-10-13 class 2): the launcher can rehearse a run (Launcher.rehearse): it makes the run's network, proxy and runner as a real run would, reads the Docker daemon's own description of them (browsing/inspection.py), removes them and counts what is left, starting no browser. The install check a_browser_sandbox_is_made_for_one_run_and_removed_with_it holds that description to the product's own expectations and reports NOT RUN, in one sentence, while browser runs are off or no launcher answers. This leaf: a read-only root with only tmpfs writable and no bind or volume, destroyed with the run; the check requires the daemon to report exactly the declared tmpfs and nothing left behind. INSTALL PROOF STEPS: 1. On the Features page switch on 'Let agents run a browser'. 2. Compose the browser overlay (docker-compose.browser.yml) on a host with gVisor as ops/browser/REHEARSAL.md sections 1 to 3 say, and confirm the browser-launcher container is healthy. 3. On the Install page press Run now and read the row a_browser_sandbox_is_made_for_one_run_and_removed_with_it: it must say Passed. NOT PROVED UNTIL a host with gVisor has run it.",
    updated: "2026-10-20",
  },
  "M19.1.6": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 on browsing/sandbox.py and launcher.py (triage 2026-10-13 class 2): the launcher can rehearse a run (Launcher.rehearse): it makes the run's network, proxy and runner as a real run would, reads the Docker daemon's own description of them (browsing/inspection.py), removes them and counts what is left, starting no browser. The install check a_browser_sandbox_is_made_for_one_run_and_removed_with_it holds that description to the product's own expectations and reports NOT RUN, in one sentence, while browser runs are off or no launcher answers. This leaf: a network of its own per run; the check requires the daemon to report it internal and the runner on no other network. INSTALL PROOF STEPS: 1. On the Features page switch on 'Let agents run a browser'. 2. Compose the browser overlay (docker-compose.browser.yml) on a host with gVisor as ops/browser/REHEARSAL.md sections 1 to 3 say, and confirm the browser-launcher container is healthy. 3. On the Install page press Run now and read the row a_browser_sandbox_is_made_for_one_run_and_removed_with_it: it must say Passed. NOT PROVED UNTIL a host with gVisor has run it.",
    updated: "2026-10-20",
  },
  "M19.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): browsing/planning.py:plan takes only declared Goal and PlanRequest; browsing/shape.py:browsing_gaps parses the package source and fails if page content can reach a plan; test_browsing_plan.py and test_browsing_shape.py assert it. planning is used by tools/website_check.py and ops/acceptance_audit.py. NEXT: Write a check naming M19.2.1 that calls brain.browsing.shape.browsing_gaps() on the installed package and requires an empty result, plus plan() on a declared target.",
    updated: "2026-10-13",
  },
  "M19.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): browsing/envelope.py:compile_envelope and seal intersect a plan with capabilities and the skill ceiling; test_browsing_plan.py. Only ops/acceptance_audit.py calls it (to seal a sample); no route, worker or tool compiles an envelope for a real run. NEXT: Call compile_envelope from the worker-side driver (compile an envelope, send wire start_fields to browser-launcher:7300, relay the run, call session_store.start/end and recording.write; launcher.py and recording.py say 'not built'); meanwhile a check can call it over a declared target and assert compilation_only_removes.",
    updated: "2026-10-13",
  },
  "M19.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): tables/browsing.py (BrowserEnvelopeRow, migration 0041), envelope_store.put_envelope/load_envelope/record_decision and approval.raise_approval/approved exist and are tested. put_envelope is called only by ops/acceptance_audit.py; raise_approval and record_decision have no caller. NEXT: In the driver call put_envelope after compile_envelope, raise_approval through the leash, and record_decision from the approvals decide path; then a check that stores, approves and reloads one.",
    updated: "2026-10-13",
  },
  "M19.2.4": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 (triage 2026-10-13 class 2/3, now wired): migration 0275 adds agent.browser_target and agent.browser_grant; brain.browsing.declared is the codec and the stores; brain.browser_routes (admin:browser, switch browser_declarations, ships off) and a 'Websites for agents' browsers' panel on the Features page declare a website, sign an exception or an exemption, list them and take them back. Install check a_website_is_declared_and_permissions_signed_for_it_are_read goes through those routes and then asks the readers (driver.prepare_run and skill_library.browser_refusals). This leaf: the target registry with declared surface maps is stored, shown and loaded (declared.registry_of). Not yet wired: website_check and the run tool still start with an empty registry until the read tool PR loads this one. INSTALL PROOF STEPS: 1. Features page: switch on 'Declare websites for agents' browsers and sign exceptions'. 2. In the Websites panel paste a declaration of a public page of your own (a name, its origin, one surface with verbs open and read and one field) and press Declare website: it is listed. 3. Install page: Run now, and read the row a_website_is_declared_and_permissions_signed_for_it_are_read: it must say Passed. ",
    updated: "2026-10-21",
  },
  "M19.3.1": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in page. A run's policy is the envelope's: the start line carries the digest the control plane sealed, a policy rebuilt from it carries the same one, a start whose parts were edited starts nothing, and Policy is frozen with no field that invites a re-read. Install check a_browser_run_is_held_to_the_envelope_it_was_sealed_with sends one sealed envelope through driver.run_envelope to the product's own runner and shows all of it. The page is a stand-in and no container has been started (ops/browser/REHEARSAL.md is the live half). INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read the row a_browser_run_is_held_to_the_envelope_it_was_sealed_with: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.3.2": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in page. A click on an element no snapshot named is refused before the page is touched and ends the run on unknown_reference (the replay does not repeat reference checks, by design: the only trees are the container's own). Shown by install check a_browser_run_is_held_to_the_envelope_it_was_sealed_with. The page is a stand-in. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read that row: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.3.3": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in page. A navigation that lands on an origin the envelope does not allow ends the run on origin_not_allowed before anything is done there, and the replay reports the attempt. Shown by install check a_browser_run_is_held_to_the_envelope_it_was_sealed_with. The proxy half (egress_addon killing other hosts) is a unit-tested decision and runs only in a real sandbox. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read that row: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.3.4": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in page. A verb the envelope does not hold on a surface it does is refused (not_in_envelope) and a second use of a verb approved once is refused (budget_spent), neither touching the page, both reported as attempts by the replay. Shown by install check a_browser_run_is_held_to_the_envelope_it_was_sealed_with. The page is a stand-in. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read that row: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.3.5": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 on browsing/sandbox.py and launcher.py (triage 2026-10-13 class 2): the launcher can rehearse a run (Launcher.rehearse): it makes the run's network, proxy and runner as a real run would, reads the Docker daemon's own description of them (browsing/inspection.py), removes them and counts what is left, starting no browser. The install check a_browser_sandbox_is_made_for_one_run_and_removed_with_it holds that description to the product's own expectations and reports NOT RUN, in one sentence, while browser runs are off or no launcher answers. This leaf: the proxy is the only route out; the check requires the proxy on exactly the run's network and the shared egress network and the runner on neither the shared one. Whether the proxy refuses an undeclared host is proved by the live read run, not by this check. INSTALL PROOF STEPS: 1. On the Features page switch on 'Let agents run a browser'. 2. Compose the browser overlay (docker-compose.browser.yml) on a host with gVisor as ops/browser/REHEARSAL.md sections 1 to 3 say, and confirm the browser-launcher container is healthy. 3. On the Install page press Run now and read the row a_browser_sandbox_is_made_for_one_run_and_removed_with_it: it must say Passed. NOT PROVED UNTIL a host with gVisor has run it.",
    updated: "2026-10-20",
  },
  "M19.3.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): browsing/enforcer.py:recheck re-judges every returned result in the control plane; test_browsing_enforcer.py. Nothing outside browsing/ calls recheck, because the control-plane relay that would receive results is not built. NEXT: Call enforcer.recheck from the worker-side driver (compile an envelope, send wire start_fields to browser-launcher:7300, relay the run, call session_store.start/end and recording.write; launcher.py and recording.py say 'not built') on each runner record line before it is accepted or recorded.",
    updated: "2026-10-13",
  },
  "M19.4.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): browsing/credentials.py:resolve turns a placeholder into a value inside ops.secrets.borrow; test_browsing_credentials.py. Nothing outside browsing/ calls it: the tool-execution boundary for a browser action does not exist (shape.secrets_do_not_travel is a static test only). NEXT: Call credentials.resolve in the driver at the instruction-send point with a vault Bindings source (VaultRole.BROWSER_RUNNER), then a check using a vaulted test credential.",
    updated: "2026-10-13",
  },
  "M19.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): credentials.py:resolve compares the binding origin exactly with the action origin and refuses otherwise; test_browsing_credentials.py. No caller outside browsing/, so it never guards a real action. NEXT: Wire with M19.4.1; a static check can call resolve with a stub vault for a matching and a non-matching origin.",
    updated: "2026-10-13",
  },
  "M19.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): credentials.py:totp computes the code server side from the stored seed and resolve returns only the code; test_browsing_credentials.py. No caller outside browsing/ and no seed storage UI. NEXT: Wire with M19.4.1; add the vault slot for a seed and a check that a code is produced without the seed leaving the control plane.",
    updated: "2026-10-13",
  },
  "M19.4.4": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 over a stand-in vault and page. Install check a_credential_reaches_the_page_and_is_kept_nowhere sends a sealed typing step through driver.run_envelope to the product's own runner: the value reaches the page it is bound to, the lease is revoked, neither the stored transcript nor the run's result holds the value (plain or as a line escapes it), a page that shows the value back is reported as an incident and is still scrubbed, and a binding for another origin issues no lease and types nothing. Found on the way and fixed: the driver's own search of the runner's lines looked for the plain value only, so a password with a quote or a backslash in it was missed by that second check (the recording still caught it). No OpenBao and no Chromium: the vault and the page are stand-ins. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read the row a_credential_reaches_the_page_and_is_kept_nowhere: it must say Passed.",
    updated: "2026-10-21",
  },
  "M19.4.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): observation.py:Snapshot carries no picture and vision_gaps() asserts it; verification.admit_frames withholds frames beside a typed credential; tests in test_browsing_targets.py, test_browsing_grading.py, test_browsing_verification.py. No actor or judge runs, so nothing consumes either. NEXT: A static check can call vision_gaps() and admit_frames over a sample; the live half waits on the driver.",
    updated: "2026-10-13",
  },
  "M19.5.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): browsing/grading.py:build_rubric takes a goal and a declaration with no parameter a trajectory could arrive through; test_browsing_grading.py and test_browsing_shape.py assert it. Called by nothing outside browsing/. NEXT: Call build_rubric in the driver before the start line and keep it with the envelope; a static check can build one and assert it has required criteria.",
    updated: "2026-10-13",
  },
  "M19.5.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): verification.py:verify_run does the actions-only pass then the admitted-frames pass and refuses second-pass outcomes for a failed first pass; tested. grading.verification_gaps says 'no judge is built', so no outcome is produced and nothing calls verify_run. NEXT: Build the judge (model or person giving an Outcome per criterion) and call verify_run from the driver at run end.",
    updated: "2026-10-13",
  },
  "M19.5.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): grading.py:score has no parameter for the agent's claim (Claim is carried and compared, never scored); test_browsing_grading.py asserts it. Nothing outside browsing/ calls score. NEXT: Wire through verify_run in the driver; a static check can call score with a contradicting Claim and require the verdict to ignore it.",
    updated: "2026-10-13",
  },
  "M19.5.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): grading.py:score resolves every unknown or unmet outcome against the run (passes only if all required criteria are MET); test_browsing_grading.py. No caller outside browsing/ and no measured false-positive rate exists. NEXT: Wire with M19.5.2; a check can feed UNKNOWN outcomes and require passed False. A measured rate needs real runs.",
    updated: "2026-10-13",
  },
  "M19.5.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): verification.py:read_back and read_back_plan define the out-of-band read through ReadBackPort; test_browsing_verification.py. No ReadBackPort implementation exists and grading.verification_gaps says no target declares a read_back tool. NEXT: Implement a ReadBackPort that reads through the gate (a connector or tool), declare read_back on a registered surface, and call it from verify_run.",
    updated: "2026-10-13",
  },
  "M19.6.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): browsing/concurrency.py:may_open applies a per-domain row after the global admission check; test_browsing_concurrency.py. No module outside browsing/ imports it, and its docstring says the counter that fills SessionCounts is not built. NEXT: Build the counter (read started and ended sessions from browser_session) and call may_open from the driver before launch.",
    updated: "2026-10-13",
  },
  "M19.6.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): browsing/concurrency.py:may_open also applies a per-agent row; test_browsing_concurrency.py. No caller and no SessionCounts source (docstring: 'Not built: the counter'). NEXT: As M19.6.2; session_store.start/end already hold the rows a counter can read.",
    updated: "2026-10-13",
  },
  "M19.6.4": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 on browsing/sandbox.py and launcher.py (triage 2026-10-13 class 2): the launcher can rehearse a run (Launcher.rehearse): it makes the run's network, proxy and runner as a real run would, reads the Docker daemon's own description of them (browsing/inspection.py), removes them and counts what is left, starting no browser. The install check a_browser_sandbox_is_made_for_one_run_and_removed_with_it holds that description to the product's own expectations and reports NOT RUN, in one sentence, while browser runs are off or no launcher answers. This leaf: memory, processor and process caps per session; the check requires the daemon to report the caps the product sets, which are judgements not yet measured under a real page. INSTALL PROOF STEPS: 1. On the Features page switch on 'Let agents run a browser'. 2. Compose the browser overlay (docker-compose.browser.yml) on a host with gVisor as ops/browser/REHEARSAL.md sections 1 to 3 say, and confirm the browser-launcher container is healthy. 3. On the Install page press Run now and read the row a_browser_sandbox_is_made_for_one_run_and_removed_with_it: it must say Passed. NOT PROVED UNTIL a host with gVisor has run it.",
    updated: "2026-10-20",
  },
  "M19.6.5": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 on browsing/driver.py (merged behind the browser_runs switch), recording.py and concurrency.py. The halt is asked before a new session (concurrency.may_open -> admission.decide) and between every instruction of a run in flight (enforcer.stopped_now in the driver's relay). Install check browser_sessions_are_limited_and_a_halt_stops_a_run: a halt refuses a new session, and a halt raised mid-run stops the product's own runner between two instructions with its session closed and its recording kept; the runner's page is a stand-in the check holds. INSTALL PROOF: on the Install page press Run now and read that row: it must say Passed. A person-run proof against a real page waits for the live read run (later PR).",
    updated: "2026-10-21",
  },
  "M19.6.6": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 on browsing/driver.py (merged behind the browser_runs switch), recording.py and concurrency.py. Recordings were written by the driver at run end and nothing removed them. browsing/recording_sweep.py puts them under the install's object-store prefix and the retention schedule (ops/schedule_runner.retention_sweep) now removes the ones past RECORDING_RETENTION_DAYS, keeps those a legal hold names (by session, by asker or company-wide), counts undated objects, and in report-only mode removes nothing. Install check a_browser_recording_is_kept_and_removed_when_its_time_has_passed. INSTALL PROOF: with an object store connected, Install page, Run now, row a_browser_recording_is_kept_and_removed_when_its_time_has_passed says Passed (it writes and removes only objects of its own run ids). With no store connected it says Not run in one sentence.",
    updated: "2026-10-21",
  },
  "M19.6.7": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 (triage 2026-10-13 class 2/3, now wired): migration 0275 adds agent.browser_target and agent.browser_grant; brain.browsing.declared is the codec and the stores; brain.browser_routes (admin:browser, switch browser_declarations, ships off) and a 'Websites for agents' browsers' panel on the Features page declare a website, sign an exception or an exemption, list them and take them back. Install check a_website_is_declared_and_permissions_signed_for_it_are_read goes through those routes and then asks the readers (driver.prepare_run and skill_library.browser_refusals). This leaf: assigning a skill that names a browser tool to an agent whose scope reaches a declared website with an API tool in the registry is refused, naming the website and the tool, unless a live exemption names this skill and that website (console/skill_library.browser_refusals, called by assignment). INSTALL PROOF STEPS: 1. Features page: switch on 'Declare websites for agents' browsers and sign exceptions'. 2. In the Websites panel paste a declaration of a public page of your own (a name, its origin, one surface with verbs open and read and one field) and press Declare website: it is listed. 3. Install page: Run now, and read the row a_website_is_declared_and_permissions_signed_for_it_are_read: it must say Passed. 4. Sign an exemption for a skill and a website that has an API and assign it.",
    updated: "2026-10-21",
  },
  "M19.7.1": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21, not claimed. Built: browser.read_surface now has a handler (brain.browsing.read_tool) registered in tools/startup.build_registry whenever the install has a database; it reads only a surface that reads and cannot write, for a caller whose browse grant is narrowed to that website, and answers nothing in one answer for an undeclared website, no grant, a write surface, a switch that is off, no room, a halt or no launcher. StoredReadOnlyBrowser runs the read through driver.prepare_run and run_envelope and returns only the declared fields (fields_read); website_check now reads the declared websites at each call and reports a refused read as NOT_AVAILABLE; the session rows' ledger entries carry the asker's reach. Install check a_browser_read_returns_only_the_declared_fields (2306) runs the whole path over a stand-in page and then ends NOT_RUN on every install. NOT proved: no real browser has read a real page, and fields_read's rule for finding a value in a real accessibility tree is a judgement (ops/browser/REHEARSAL.md 6a). NEXT: build the -browser image in Release, run REHEARSAL.md on a runsc host, and read one page of your own.",
    updated: "2026-10-21",
  },
  "M19.7.2": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21. A browser write waits for a person through the leash: driver.prepare_run compiles the envelope, raises the card (browser.act_on_surface, bound to the envelope digest) and stores both, a different person approves it through the approvals route, and the run starts only on the stored approval (install check a_browser_write_waits_for_a_person_and_runs_are_counted). New: the card now says what changed since the last run the same asker had approved for this agent on this website, or that it is the first, in one sentence in the card's arguments and so in the digest the approval binds to (install check a_card_says_what_changed_since_the_last_approved_run). A write only runs through a scripted actor and a stand-in page: the model actor that would choose element references is not built. INSTALL PROOF STEPS: 1. Install page: Run now. 2. Read the rows a_browser_write_waits_for_a_person_and_runs_are_counted and a_card_says_what_changed_since_the_last_approved_run: both must say Passed.",
    updated: "2026-10-21",
  },
  "M19.7.3": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 (triage 2026-10-13 class 2/3, now wired): migration 0275 adds agent.browser_target and agent.browser_grant; brain.browsing.declared is the codec and the stores; brain.browser_routes (admin:browser, switch browser_declarations, ships off) and a 'Websites for agents' browsers' panel on the Features page declare a website, sign an exception or an exemption, list them and take them back. Install check a_website_is_declared_and_permissions_signed_for_it_are_read goes through those routes and then asks the readers (driver.prepare_run and skill_library.browser_refusals). This leaf: a write on a page is compiled to wait for a person at the Assisted rung unless a live, unrevoked exception names that page; the signer must be able to perform the write (autonomy.sign), the end is within ninety days, and driver.prepare_run reads the exceptions in force at the instant it compiles. INSTALL PROOF STEPS: 1. Features page: switch on 'Declare websites for agents' browsers and sign exceptions'. 2. In the Websites panel paste a declaration of a public page of your own (a name, its origin, one surface with verbs open and read and one field) and press Declare website: it is listed. 3. Install page: Run now, and read the row a_website_is_declared_and_permissions_signed_for_it_are_read: it must say Passed. 4. Sign an exception for a page that writes and read it in the list.",
    updated: "2026-10-21",
  },
  "M20.1.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (builder.compose); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_coauthor_routes, builder.coauthor, builder.compose +4 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.acceptance_checks_agents, components/GraphCanvas.tsx, components/TraceGraph.tsx +2 more; NOT wired: pages/audit/TracePage.tsx",
    updated: "2026-10-06",
  },
  "M20.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_builder_routes, builder.agent_drafts, builder.publication_store +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.4.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (builder.agent_drafts, builder.publish); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_builder_routes, builder.agent_drafts, builder.publish +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.4.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_builder_routes, builder.agent_drafts, builder.publish); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M20.5.1": {
    status: "READY FOR TESTING",
    why: "Built: a department's administrator can no longer publish an agent to the whole company or approve a knowledge item to it alone; that needs the authority held over everything, and for a department it needs the authority held in that department. The skill library is one company-wide object, so only the authority over everything decides about a skill. The publications queue offers each administrator only the requests they could decide. To prove it on the install: after the release, open Install, Acceptance, run the checks and read the row 'a department admin decides only for their department', which should pass in the two newest runs.",
    updated: "2026-10-15",
  },
  "M20.5.2": {
    status: "IN PROGRESS",
    why: "Built: behind the switch 'Hold an agent that costs more than its department allows' (ships off), publishing an agent to a department whose per-run ceiling is below what one run costs waits for that department's administrator, tells the author both figures in the install's currency, and the publish record carries the cost of each version. Not what the leaf says in two ways: the figure is the run's price from the product's own estimator (the same one the pre-flight uses) and not the median of rehearsed runs, because rehearsals record no cost yet (needs-you question); and no screen writes a department's per-run ceiling yet (M21.1.2), so on an install the hold fires only for a ceiling written some other way. The check 'a costly publish waits for a colleague in the department' proves the hold over a ceiling it writes itself.",
    updated: "2026-10-15",
  },
  "M20.5.3": {
    status: "IN PROGRESS",
    why: "Built: behind the switch 'Start an agent's draft from a description' (it ships off), New agent offers 'Describe it': the person writes what the agent is for, a draft of their own is started, and the model's suggestions for its name, summary, instructions, skills and connectors are shown beside what the draft holds, none chosen, to take as any suggestion is taken. Not what the leaf says in two ways: tools, permissions, knowledge and channels are not drafted (the product writes an agent's words and never what it may reach, and the answer says so), and a procedure is not drawn. Whether describing may put the suggestions in without a separate take is a needs-you question. To prove it: after the release, open Install, Acceptance, run the checks and read the row 'describing an agent starts a draft and applies nothing'.",
    updated: "2026-10-15",
  },
  "M21.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Ceiling stored and versioned: PUT company budget (company_routes.set_company_budget, ops.budgets.BudgetRow, test_company_routes). Hard stop is ops.budget_stop_store.budget_refusal_for in api_routes, flag budget_enforcement off (needs 169 A). alert_fractions stored, nothing fires them. NEXT: Wire alert_fractions to a notice when spend crosses one (spend.alerts_for exists but is only called by unwired preflight); then write a check naming M21.1.1 that sets a ceiling with alerts and reads the stop record.",
    updated: "2026-10-13",
  },
  "M21.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.budgets.allocate, Transfer and apply_transfers are built and unit-tested (test_budgets) but have no caller outside budgets.py; no route writes a department budget row (only company_routes and agent_workspace_routes call budget_store.append). NEXT: Add a department budget set/transfer route (beside company_routes.set_company_budget) that calls allocate/apply_transfers and budget_store.append, then a check.",
    updated: "2026-10-13",
  },
  "M21.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.budgets.user_allowances (daily and monthly, fair share) has no caller; mine_routes and member_activity only read user rows via budget_store.in_force. No route or job writes a user-level row, so no person ever has an allowance. NEXT: Call user_allowances from a route or sync that appends user rows via budget_store.append, with the fair-share cap; then write a check.",
    updated: "2026-10-13",
  },
  "M21.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Agent monthly ceiling is settable: agent_workspace_routes (BudgetLevel.AGENT, MONTH; test_agent_workspace_routes). ops.budgets.agent_ceilings (per-run and per-day) has no caller, so per-run and per-day agent ceilings are never written. NEXT: Call agent_ceilings from the agent workspace route (or a second field) so run and day rows are appended; then check naming M21.1.4.",
    updated: "2026-10-13",
  },
  "M21.1.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): tables.budget versioned rows + ops.budget_store.append/history_of, ledgered by a trigger on append (agent_workspace_routes docstring cites 0098); written by company_routes and agent_workspace_routes, tested test_budget_store. Only the company and agent levels have a writer. NEXT: Write check naming M21.1.5 that sets the company budget twice via PUT and reads both versions and the ledger row (reuse acceptance_checks_company_budget._history).",
    updated: "2026-10-13",
  },
  "M21.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.spend.estimate and preflight (lane, tier, tool count, retrieval size) are built and tested; callers are builder.rehearse and orchestration.plan only. budget_stop_store docstring rejects preflight on the request path; no live question is estimated. NEXT: Decide with owner whether to call spend.estimate in api_routes.answered_for before the lane (budget_stop_store.judged is the slot); raise as a needs item since the code deliberately chose stop-on-used-up.",
    updated: "2026-10-13",
  },
  "M21.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): A used-up budget refuses before any lane runs (api_routes.answered_for calls budget_refusal_for after the halt, before lanes), so no tokens are spent on that question; flag off (needs 169 A). Estimate-based refusal (spend.preflight) is not on the path. NEXT: Same as M21.2.1 for estimate-based refusal; for the used-up stop only the flag decision (169) and a check remain.",
    updated: "2026-10-13",
  },
  "M21.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.usage_store.UsageRecorder (installed in app.py) writes tables.spend.SpendActualRow per finished request; Actual carries principal, department, agent, model, lane; read by spend_report_view and /report/spend. Tests test_usage_store, test_spend. NEXT: Write check naming M21.2.3 that asks one question then reads the spend_actual row and /report/spend by each dimension (see acceptance_checks_console_money for the harness).",
    updated: "2026-10-13",
  },
  "M21.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.spend.correct (estimator correction from Observation actuals) is built; only ops.retune.post_launch_correction uses it, called from console.spend_view.cost_review which no route or page calls. No live estimator applies a Correction. NEXT: Run correct() from a worker job over spend_actual versus estimates and persist the Correction; wire it into estimate() on the request path (depends on M21.2.1).",
    updated: "2026-10-13",
  },
  "M21.2.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Used-up budget stop is wired (budget_stop_store.judged, records BudgetStopRow, refuses with no degradation) but flag budget_enforcement ships off (needs 169 A). Admin warning is recorded (addressed_to) and not delivered: the module says delivery is the next change. NEXT: Deliver the recorded warning through the notice channel to the admin; owner switches the flag after a week of would-have-stopped rows; then check naming M21.2.5.",
    updated: "2026-10-13",
  },
  "M21.2.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): The refused person gets SPENDING_LIMIT_REACHED (budget_stop_store), which deliberately names no budget and no person who can raise it; console.spend_view.told_about names level and period but has no caller. Leaf wording is narrowed by design with no needs item. NEXT: Raise a needs-rupash question on the narrowing, or call spend_view.told_about from the refusal path for readers entitled to it; then check.",
    updated: "2026-10-13",
  },
  "M21.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /report/spend (report_routes.spend) groups by Dimension department, principal, agent, model, lane from ops.spend_daily via spend_report_view; page console/src/pages/reports/SpendPage.tsx. Tests test_report_routes, test_spend_report_view. NEXT: Write check naming M21.3.1 reading GET /report/spend for each dimension after seeding spend rows.",
    updated: "2026-10-13",
  },
  "M21.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): report_routes.spend takes include_machine default false and the view says which it was (MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO); Actual.machine is derived. Tests test_spend_report_view, test_spend. NEXT: Write check naming M21.3.2 seeding a machine and a human row and reading /report/spend with and without include_machine.",
    updated: "2026-10-13",
  },
  "M21.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): console.spend_view.distribution and cost_per_answer (quantiles, not only mean) are built and tested (test_spend_view) but no route, page or other module calls them; SpendReportView has no distribution field. NEXT: Add the distribution to /report/spend (report_routes.spend_view_of) or a new route, then show it on SpendPage.tsx.",
    updated: "2026-10-13",
  },
  "M21.3.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Most expensive agents: /report/spend dimension=agent ordered by cost. Question shapes: ops.spend_store.question_shape_report and spend_view.shape_report/dearest built (test_question_shapes) but have no route or page caller. NEXT: Add a route over question_shape_report (reader's grant filter already inside) and a SpendPage section; then check.",
    updated: "2026-10-13",
  },
  "M21.3.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /console/department/pace (department_view_routes.PACE_PATH) uses scoped_authority.department_pace and spend_view.pace; page console/src/pages/department (departmentFigures.ts). Agent projection in console_stats_routes. Test test_department_view_routes. NEXT: Write check naming M21.3.5 that sets a department ceiling row then reads /console/department/pace (needs a department budget writer, see M21.1.2, or a direct seed row).",
    updated: "2026-10-13",
  },
  "M21.3.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): BudgetStopRow rows are written (budget_stop_store.record) with level, subject, period; spend_view.budget_stops/StopRow list them but nothing calls those. console.needs_you still says no stop is recorded (stale text). NEXT: Add a route and Spend section listing recorded stops (reader-scoped via spend_view.told_about); fix the stale needs_you UNRECORDED_HEALTH entry.",
    updated: "2026-10-13",
  },
  "M21.4.1": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No code reconciles spend to a provider invoice. models/pricing.py holds the install's own prices; no invoice figure input, tolerance or difference display found (grep invoice/reconcil in src).",
    updated: "2026-10-13",
  },
  "M22.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.ingest_queue, ops.acceptance_checks_class_pools, ops.admission +7 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M22.3.3": {
    status: "READY FOR TESTING",
    why: "Built to the capacity model's stated peak (python -m brain.ops.load_peak --profile full, which reads each profile's arrival rate and Little's-law concurrency from ops.admission.seed_profiles) and behind the load_test switch, which ships off. It refuses before sending anything unless the switch is on, every token belongs to a person in the load_test department, the operator repeats the request count, and the install has a database to keep the result in; it stops if the install sheds most of what it is sent; it keeps each run as one row in the install's own settings with no person, token or question. The install's own check a_short_peak_run_is_driven_judged_and_kept_and_leaves_nothing proves the machinery in a rolled-back transaction with no model called, and closes the leaf when the install's two newest runs both pass it. The peak run itself is the owner's decision (needs-rupash 194; item 103 says CI, not the install). Install proof, steps: (1) open the Install page's list of checks after a deploy and see that check pass; (2) only if you choose to run the peak: turn on the Features page switch for the load test, make a department called load_test with two people and a small document only it can read, then follow docs/install/scaling.md, The peak load test.",
    updated: "2026-10-14",
  },
  "M25.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.retention.HORIZONS/DataClass/Horizon, one per class, shown by GET retention controls (erasure_routes.retention_controls, kept_view); retention_policy_gaps self-checks. Tests test_retention, test_erasure_routes. No install check names it. NEXT: Write check naming M25.1.1 that reads the retention controls route and asserts every DataClass has a horizon and reason.",
    updated: "2026-10-13",
  },
  "M25.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): HORIZONS has METADATA_LEDGER at 5 years (retention.METADATA_LEDGER_RETENTION_DAYS); obs.request_telemetry is partitioned monthly by ops.ledger_partitions run on the daily schedule; detach keeps rows, drop is not built. Policy is long, as the leaf says. NEXT: Write check naming M25.1.2 reading the retention controls route for the ledger horizon and the ledger report line.",
    updated: "2026-10-13",
  },
  "M25.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Payload store = obs.trace_step, horizon 30 days (PAYLOAD_RETENTION_DAYS, test_retention) and reported daily by the sweep. But migration 0150 grants brain_app INSERT only, so PostgresSweeper.removal_rule queues those rows and never deletes them. NEXT: Build the removal: a job or role that deletes (or partitions and drops) obs.trace_step past 30 days with the release gate and hold check; then write the check.",
    updated: "2026-10-13",
  },
  "M25.1.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Trace window declared (tracing.RETENTION, 30d) and daily retention report reaches the trace store (proved for M32.1.1.3, #328). Recording lifecycle is only the recordings bucket rule (storage.BUCKETS 30d); trace_step has no DELETE grant so nothing is removed. NEXT: Same removal as M25.1.3 for traces; call browsing.recording.remove_expired from a worker (see M25.4.3); then check naming M25.1.4.",
    updated: "2026-10-13",
  },
  "M25.1.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Daily sweep: schedule_runner.run_retention_sweep -> retention_store, report stored (ops.retention_report), served by GET /govern/retention, page Retention.tsx. Report proved on install for M32.1.1.3. Tests test_retention_store, test_retention_routes. NEXT: Write check naming M25.1.5 reading GET /govern/retention for a stored report that reaches every store with a not-reached reason where applicable.",
    updated: "2026-10-13",
  },
  "M25.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.erasure.assemble and member_activity.stored_about_me (store by store, disposition per store) are built and tested but no route or page calls them; the data-transfer catalogue lists subject_access with runs=False (not available yet). NEXT: Add a subject access route over member_activity.stored_about_me wired to PostgresEraser.count_for per store (EstateEraser) and flip DataSet subject_access runs=True; then check.",
    updated: "2026-10-13",
  },
  "M25.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): The queue (erasure_store.drain_erasure_queue via schedule_runner, EstateEraser) erases rows, projection, knowledge and memory (plus session memory and own vault tokens). Cache, index, recordings and attachments are NOT reached (NO_CACHE_ERASER, NO_INDEX_ERASER, NO_OBJECT_STORE_ERASER; erasure_routes ERASING text). NEXT: Build erasers for the answer cache and retrieval index, and an object-store eraser over ops.object_store; pass them as objects= in schedule_runner; then check.",
    updated: "2026-10-13",
  },
  "M25.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.erasure.Disposition, backup_horizon and BACKUP_RETENTION_DAYS; the screen text says a backup holds the data until it rotates out (erasure_routes.ERASING, install_routes copies_kept_days); needs 60 decided option A. Tests test_erasure, test_erasure_routes. NEXT: Write check naming M25.2.3 reading the retention controls and erasure screen text for the backup window and the stated limit.",
    updated: "2026-10-13",
  },
  "M25.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.erasure.Certificate and certify (with backup horizon) are built and tested but have no caller; drain_erasure_queue stores outcome and per-store counts on ops.erasure_request only, and erasure_routes.request_view carries no certificate or horizon. NEXT: Call certify in drain_erasure_queue, persist it on the request row (migration) and return it in request_view; then check.",
    updated: "2026-10-13",
  },
  "M25.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): POST /threads/{id}/export (thread_routes, member_activity.export_my_history) records an ExportAudit-style row and hands the person their own conversation; Ask.tsx button. Merged on main (migration 0207, test_thread_export_routes). NEXT: Write check naming M25.3.1 that asks, exports own thread, and reads the export record; note the other owner's thread is refused.",
    updated: "2026-10-13",
  },
  "M25.3.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Audit-trail export demands a reason and writes an audit row (data_transfer_routes.take_export, ExportReason, ops.data_export_store; listed by GET /govern/retention/exports). The bulk store collection for eDiscovery (ops.export.bulk_export, BulkExportRequest) has no caller; catalogue bulk_collection runs=False. NEXT: Add a route that runs ops.export.bulk_export over named stores and people with reason and reference, write the ExportAudit row, set bulk_collection runs=True; then check.",
    updated: "2026-10-13",
  },
  "M25.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.export.knowledge_export keeps each item's scope and is tested (test_export) but has no caller; data_transfer catalogue knowledge runs=False (needs 108 decided: build it). NEXT: Wire knowledge_export into a data_transfer route (needs 108) reading know.item through the reader's scope; set runs=True; then check.",
    updated: "2026-10-13",
  },
  "M26.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Provisioning is done by the scheduled staff sync (ops.staff_sync_run via schedule_runner, staff_accounts_run makes accounts, staff_people_run writes members), not by identity.lifecycle.provision (no caller). Staff sources screen and routes; tests test_staff_sync_routes. Checks name M1.6.x only. NEXT: Write check naming M26.1.1 that runs a sync over a seeded roster and reads the new principal and its account row (reuse acceptance_checks_accounts.py harness).",
    updated: "2026-10-13",
  },
  "M26.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.starter_pack_store.grant_starter_packs is called by staff_sync_run and gives each joiner the Starter pack for their department (decided needs 105); role from directory groups via identity.group_sync. Tests test_starter_pack_sync. Check M1.6.20/21 touches the step. NEXT: Add M26.1.2 to the leaves of the accounts check that covers the Starter pack step (acceptance_checks_accounts.py:420) or write one reading the grant.",
    updated: "2026-10-13",
  },
  "M26.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): starter_pack_sync.starter_plan scopes the pack to the person's registered department (department_scope), applied by starter_pack_store from staff_sync_run; a mover has it moved, a leaver has it ended. Test test_starter_pack_sync. NEXT: Check naming M26.1.3 that syncs a person into a department and reads the grant's scope; reuse the accounts check harness.",
    updated: "2026-10-13",
  },
  "M26.1.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): identity.lifecycle.welcome_questions and adoption.starter_questions (three department-scoped questions) are built; only ops.guide_docs imports the latter and nothing imports guide_docs. Ask.tsx says it suggests no question before the first ask. NEXT: Serve welcome_questions from a route for the signed-in person's department, from entities that indexed, and show them on the first Ask screen (Ask.tsx empty state).",
    updated: "2026-10-13",
  },
  "M26.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Grants are read per request (gate.held_grants, disabled principal counts none) and the cache key carries the entitlement hash, so a move shows on the next request; existing check M6.5.2 (acceptance_checks_cache.py:116) shows a moved person is not served the old answer. lifecycle.Move is unwired. NEXT: Add M26.2.1 to the leaves of that M6.5.2 check, or write a check that moves a person and asks at once.",
    updated: "2026-10-13",
  },
  "M26.2.2": {
    status: "READY FOR TESTING",
    why: "built (M26/personal-agents-follow-the-owner): an install check, a_personal_agent_reaches_the_new_department_when_its_owner_moves, makes a member's personal agent, moves the member to another department through the staff sync's Starter pack step, and reads that the agent's record is the same row, that only its owner sees it before and after (a colleague who stayed never does), and that a run through it searches the new department's knowledge and none of the old one's, by the one intersection E_run(caller, agent). Nothing in the product changed: the leaf's note could not say the agent's audience record was verified, and now it is. PRIOR WORK (2026-10-13 triage): identity.lifecycle.agents_following states the rule; the check is the install's own demonstration of it. Not asked: an answer made through the agent, which needs a model (brain.ops.acceptance_checks_agent_reach asks that for an agent). PROVE ON THE INSTALL: (1) as a member in one department, make a personal agent (My workspace, with personal agents switched on); (2) ask it about a document only that department holds: it answers; (3) have an administrator move the member to another department (the staff list's department, or the person's page) and wait for the nightly sync or press Run now; (4) ask the same agent the same question: it no longer reaches that document, and a question about the new department's documents is answered; (5) a colleague who stayed in the old department still cannot find the agent. The install check does the same over reserved people and is not run until the Starter pack exists.",
    updated: "2026-10-21",
  },
  "M26.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): identity.lifecycle.reevaluate_delegations (suspend, never narrow) and Reconfirmation are built and tested but no caller; no delegation table or route exists on main (grep delegation in tables and routes). Nearest live object is an automation owner (M26.3.3). NEXT: Decide what a delegation is on this install (elevation, automation owner or a new object), then call reevaluate_delegations from the sync run when a move changes reach. 2026-10-20 BUILT UNDER OPTIONS A AND B OF NEEDS ITEM 216, DEPUTY APPOINTMENTS UNBUILT: brain.ops.mover_automations watches every live automation's reach before the staff sync's Starter pack step and again after, and pauses (owner_lost_reach, a schedule row by the roster, a ledger entry) each one whose reach after does not cover its reach before, asked through EntitlementSet.intersect with the instant; listed on the owner's and the authority holder's Automations page; started again only by the existing confirmed start, which needs somebody other than the owner. Behind the off switch mover_pauses_automations. The deputy appointment, which only option A names, is not built, and option C (a delegation as its own object) is not touched; identity.lifecycle.reevaluate_delegations is still not called because a deputy appointment is the only RoleGrant it takes. Install check a_mover_s_automation_is_paused_and_a_stayer_s_is_not (acceptance_checks_mover_automations.py). Owner decides item 216. Not claimed done.",
    updated: "2026-10-20",
  },
  "M26.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Answer cache key includes the entitlement hash (gate.answer_cache, cache_key); check M6.5.2 shows a person who moved department was refused the cached answer (acceptance_checks_cache.py:196). Test test_answer_cache. NEXT: Add M26.2.4 to that check's leaves=(...).",
    updated: "2026-10-13",
  },
  "M26.2.6": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Knowledge reach is applied at query time from the reader's grants (knowledge.search scope, starter_pack_sync moves the pack with the person); nothing reindexes on a move. Test test_starter_pack_sync and knowledge scope tests. NEXT: Check naming M26.2.6: move a person between departments with no reindex job and assert search results change; reuse the people and knowledge check helpers.",
    updated: "2026-10-13",
  },
  "M26.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): POST /govern/people/disable (principal_state_routes) sets disabled_at; migration 0003's trigger ends every session and grants go inert; the staff sync disables leavers via ops.standing_run (check M1.6.14). identity.lifecycle.disable is the unwired in-memory twin. NEXT: Write check naming M26.3.1: disable a signed-in person, assert the next request is refused and the session row ended (acceptance_checks_accounts.py has the harness).",
    updated: "2026-10-13",
  },
  "M26.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.staff_sync_run calls stop_leavers_agents in the leaver's run (M1.8.9); staff_source_routes lists agents_for_adoption and adopt; Transfers.tsx page; tests test_staff_connect, test_staff_sync_routes. Adoption is by the department admin. NEXT: Write check naming M26.3.2: mark a leaver with an agent, assert the agent is disabled and appears in transfers, adopt it.",
    updated: "2026-10-13",
  },
  "M26.3.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.automation_owner.standing_of returns AWAITING_OWNER when the owner is not active; automation_run_store.owner_live refuses an owner_gone run; automations_routes may_adopt lets a new owner take it. Check M32.6 covers other clauses. NEXT: Write check naming M26.3.3: disable the owner of a seeded automation, assert it does not run and is listed as awaiting an owner.",
    updated: "2026-10-13",
  },
  "M26.3.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): identity.lifecycle.departure_disposition (per Store) and member_activity.DeletionRoute are built but have no route or job caller; nothing applies a leaver's memory or personal knowledge disposition when the sync marks them. NEXT: Call departure_disposition from the leaver step of staff_sync_run and record each disposition; surface it on the Transfers page.",
    updated: "2026-10-13",
  },
  "M27.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_deployment, ops.telemetry, ops.trace_store +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_deployment, ops.telemetry); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.1.5": {
    status: "IN PROGRESS",
    why: "15 of the 18 request fields are filled; three are declared unfillable in brain.ops.telemetry.UNFILLABLE_TODAY. Read on 2026-10-21: the policy epoch is already computed for the cache key (api_routes.policy_epoch_of) and could travel to the row; the tool latency could be read from the invoke step's time that stage_ms already records; time to first token cannot be measured because no model answer streams, and the only figure available is the time to the first frame, which the module refuses as a different measurement under this one's name. Nothing built yet. The first token is the question for the owner: record the first frame under its own name, or leave the field empty.",
    updated: "2026-10-21",
  },
  "M27.1.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console, ops.telemetry); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.10.2": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED: the toast region is mounted once, in the shell, and a Note of kind done announces its sentence in it while the page keeps its own line (console/tests/done-notes-announce.test.tsx), which gives the thirty-eight places that say a write took effect the toast without an edit to each. The other named parts were already drawn by the pages: sidebar, header, breadcrumbs, list page, detail page, tabs, drawer, empty, loading and failed states, bulk bar and the write-once secret field. Install proof: switch a feature on or off under Features and read the message that appears at the corner of the screen as well as the line on the page.",
    updated: "2026-10-20",
  },
  "M27.11.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record, console.organisation +13 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already); +5 more",
    updated: "2026-10-06",
  },
  "M27.11.10": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in credential_routes, ops.acceptance_operations_console_6, ops.credential_catalogue +9 more; NOT wired: pages/Credentials.route.tsx. MORE ELSEWHERE, read before building: closed PR #171's branch M27/console-credentials (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.11.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_agent_console); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.11.12": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-profile-and-personal-agents): an agent's Profile lists its sources, its skills and its channels each with its state. A channel is drawn as on or as off in words and a dashed edge (AgentChannels, from the lifecycle read), a source is attached or requested with the Connectors page's health, and a skill is drawn with its review and its runs. A skill no run of the agent could use says so in a sentence from the API (brain.console.agent_behaviour.skill_standing: not in the library, waiting for review, rejected, changed since it was approved, or naming a tool the agent may not call), checked against the run path's own skills_offered; the old sentence that an assignment changes no answer was false since M27.12.1 and is gone. Skills and channels hold the same overflow list as sources, the first five and the rest behind N more. Add and remove: a skill is attached and taken off through a confirmation, a source through a draft of the agent, a channel through the Change where it answers confirmation. Install check a_pinned_skill_no_run_could_use_is_said_so_on_the_profile. To prove on the install: sign in as an administrator, open an agent's Profile; the Capabilities card lists its skills, and under them a line for any skill no run uses, for example a skill still waiting for review; the card Where it answers shows each channel as on or as off",
    updated: "2026-10-15",
  },
  "M27.11.13": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-profile-and-personal-agents), behind the agent_audience_extras switch which ships off: the Availability card shows who can find the agent (level, department, steward, whether you are included) and, to its steward and to the holder of the lifecycle authority over it, the further departments and named people it is offered to, each with a Withdraw control and, for the holder, an Offer control (a department chosen from the install's own list, a person typed by user id), each confirmed first. GET /agents/{id}/audience, POST /audience/additions and /audience/removals (brain.agent_audience_routes). A reader who answers for the agent in no way is sent no name and no sentence saying names exist, so an agent offered to nobody and to many read the same; a personal agent takes no offer; the row stays on withdrawal with who and when. Install check an_agent_is_offered_to_more_than_its_level_from_its_profile. Needs-rupash 201 question 1 (one choice or several) is still unanswered, which is why the controls are behind a switch. NOT BUILT: a ledger entry per offer (the table has no ledger trigger; its own rows say who and when). To prove on the install: Features, switch on Offer an agent to more departments and to named people; sign in as the department administrator of an agent, open its Profile, Availability: choose a department and press Offer then confirm, the agent appears for that department's members; Withdraw it and it stops appearing",
    updated: "2026-10-15",
  },
  "M27.11.14": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-profile-and-personal-agents) to the owner's recommendation on needs-rupash 201 question 2, which is not yet answered: the Learning card on the Profile carries a switch Let this agent learn from its conversations, which pauses and resumes what the agent's runs teach it (GET and POST /agents/{id}/learning, the lifecycle authority, a reason required and written to the row), each direction confirmed. Resuming lets each tier go on doing what it already checks, so it cannot let anything be learnt unchecked. The browsing switch is on the Profile as a switch that is off and cannot be pressed, with its reason, and computer use as a sentence: nothing is offered for browsing until the sealed browser has run on an install (question 2 option A). Install check an_agents_learning_is_paused_and_resumed_from_its_profile; what a pause does to what forms is acceptance_checks_signals. To prove on the install: sign in as the administrator of an agent, open its Profile, Learning from conversations: press the switch, give a reason, confirm; the card reads Paused; press it again, give a reason, confirm; it reads On",
    updated: "2026-10-15",
  },
  "M27.11.15": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_routes, console.agent_profile); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-agent-api",
    updated: "2026-10-06",
  },
  "M27.11.16": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_about_routes, console.agent_about, ops.acceptance_agent_console +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-agent-api; old backup branch recovery/from-windows-20260928-wt-overview",
    updated: "2026-10-06",
  },
  "M27.11.2": {
    status: "OPEN",
    why: "Built in the People pages: grant expiry, one grant to several people, pack assignment, disable and enable a person. Install checks cover a leaver's session, grants and automations (acceptance_checks_joiner_mover_leaver). No install check covers grant expiry, the bulk grant, the pack or reinstatement; the adoption plan and ownership transfer are agent routes not offered on the People page.",
    updated: "2026-10-21",
  },
  "M27.11.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (directory_routes, ops.acceptance_people_console, pages/Roles.tsx +12 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/role-nominations, no PR; closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.11.4": {
    status: "BLOCKED",
    why: "Waits on needs-rupash item 188, point 2: the staff source and directory sync are managed from the console (built); the identity provider and the embedding size are read-only in Settings and the owner has not said whether to build the change or move it to the installer.",
    updated: "2026-10-21",
  },
  "M27.11.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in audit.record, channels.api_keys, identity.service_account_store +8 more; NOT wired: pages/ServiceAccount.route.tsx, pages/ServiceAccount.tsx. MORE ELSEWHERE, read before building: closed PR #124's branch M27/service-accounts-page (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w1-1",
    updated: "2026-10-06",
  },
  "M27.11.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_builder_routes, agent_lifecycle_routes, agents.creation +17 more; NOT wired: pages/AgentDraft.tsx, pages/AgentDrafts.route.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M13/wire-agent-upgrade, no PR; +16 more",
    updated: "2026-10-06",
  },
  "M27.11.7": {
    status: "READY FOR TESTING",
    why: "BUILT: the Agent templates pages install a template from the gallery, withdraw a version and undo it, and save an agent as a template through the review that hoists every value out. Three install checks, each proving one clause on the install's own schema and routes, now name this leaf, so it closes when all three pass on the install's two newest runs: a built-in template installs as a disabled agent at Shadow (acceptance_checks_templates), an agent saved as a template is a draft only its author reads, reviewed with every value hoisted out and published once (acceptance_checks_templates_audience), and a withdrawn version is not offered while installed agents stay pinned (acceptance_checks_template_withdrawal). Install proof: open Agent templates, install one, withdraw a version with a reason and undo it.",
    updated: "2026-10-21",
  },
  "M27.11.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_skill_console, skill_routes, pages/Skills.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +9 more",
    updated: "2026-10-06",
  },
  "M27.11.9": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connector_routes, connectors.declaration, console.connector_detail +28 more; NOT wired: pages/Connector.route.tsx, pages/Connector.tsx, pages/Connectors.route.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +7 more",
    updated: "2026-10-06",
  },
  "M27.12.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, ops.acceptance_checks_skill_runs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.12.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.12.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in automations_routes, console.automations, ops.automation_change_store +11 more; NOT wired: pages/Automation.route.tsx, pages/Automation.tsx, pages/Automations.route.tsx. MORE ELSEWHERE, read before building: closed PR #174's branch M27/console-automations (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.12.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/operations/StopControl.tsx, pages/operations/StopPage.tsx, pages/stopQuery.ts); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #121's branch M27/halt (may be replayed already); old backup branch recovery/from-windows-20260928-wt-halt",
    updated: "2026-10-06",
  },
  "M27.12.5": {
    status: "READY FOR TESTING",
    why: "Built and wired, and now followed end to end by the install check `a_model_call_is_costed_and_a_used_up_budget_stops_the_next`: a question answered by a priced stand-in model leaves one cost in its department equal to the tokens its request row recorded at the price set. To prove it on the install: open Install, run the checks, and read that check; the leaf closes when it passes on the install's two newest runs. It says it was not run, rather than failing, on an install with no currency set. Found on the way and fixed for every install: a question the checks ask was recorded with no trace on a budget stop, which the table refused, so the stop was silently not written.",
    updated: "2026-10-21",
  },
  "M27.12.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.configuration, ops.acceptance_operations_console, ops.install_settings +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.13.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in binding_routes, ops.acceptance_checks_channel_framework, pages/Channels.tsx +12 more; NOT wired: pages/Channel.tsx, pages/Channels.route.tsx",
    updated: "2026-10-06",
  },
  "M27.15.14": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (navigation_routes, pages/operations/StopControl.tsx, pages/stopQuery.ts); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.17": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.needs_you, console_overview_figures_routes, console_overview_routes +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #157's branch M27/console-stats-overview-r3 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.15.18": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/people/PersonDetailPage.tsx, pages/people/PersonHistory.tsx, pages/people/PersonOverview.tsx +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.19": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, console.organisation, directory_routes +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.20": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (govern_routes, ops.acceptance_people_console, pages/people/PersonGrants.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.21": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (certification_export_routes, ops.acceptance_people_console_2, ops.data_export_store +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.22": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.organisation, govern_people_routes, identity.organisation_store +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #241's branch M1/staff-sync-diagnostics (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.23": {
    status: "OPEN",
    why: "Not built. The department page shows the lead, the people, the teams and the scopes; the lead history (gate.department_lead keeps ended rows), the agents addressed to the department and its knowledge coverage are not on it. Coverage today is read only by the department's head (department_view_routes) and would need a reading for an administrator of another department. Applying the staff source's organisation plan is built (ops.source_organisation) and has an install check.",
    updated: "2026-10-21",
  },
  "M27.15.24": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in audit.ledger, audit.record, console.scoped_authority +6 more; NOT wired: pages/Packs.route.tsx. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.25": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/people/PersonSessions.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.26": {
    status: "OPEN",
    why: "Not built: no route changes a service account after it is registered. Changing its end date needs an audit entry for the change, which is a trigger on auth.service_account and so a migration; the owner part waits on needs-rupash item 188, point 4. Under either answer the end date can change.",
    updated: "2026-10-21",
  },
  "M27.15.27": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.entity_stats, console_stats_routes, models.pricing +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #154's branch M21/record-usage-for-stats (may be replayed already); +9 more",
    updated: "2026-10-06",
  },
  "M27.15.31": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_builder_routes, builder.agent_drafts, ops.acceptance_skill_console +5 more; NOT wired: pages/Approvals.tsx",
    updated: "2026-10-06",
  },
  "M27.15.32": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-profile-and-personal-agents): the Profile's computer use card is the sentence the API sends (GET /agents/{id}/capabilities, computer_use, from brain.console.agent_behaviour), which says computer use is not offered because the product has no isolated desktop runner, and nothing is drawn to switch. Whether a runner exists is asked of the import machinery for the module brain.browsing.desktop and not of a constant, so the day it is added the sentence changes and the install check says not run until a person looks again; even then offered stays false until a per-agent switch is built. A reader sent no detail is drawn no card. Install check computer_use_is_not_offered_until_a_desktop_runner_exists. To prove on the install: open any agent's Profile; the card Computer use reads Not offered, with the reason, and holds no button or switch",
    updated: "2026-10-15",
  },
  "M27.15.33": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.entity_stats, console_stats_routes, models.pricing); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #154's branch M21/record-usage-for-stats (may be replayed already); +9 more",
    updated: "2026-10-06",
  },
  "M27.15.36": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.37": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (automations_routes, console.automations, ops.automation_change_store +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #174's branch M27/console-automations (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.38": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.acceptance_operations_console_4, provider_routes, routing_routes +6 more; NOT wired: pages/Matrix.tsx. MORE ELSEWHERE, read before building: closed PR #163's branch M27/console-models-routing (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.39": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connector_routes, console.connector_detail, ops.acceptance_operations_console_2 +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M27.15.40": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in knowledge.lifecycle, knowledge.lifecycle_store, knowledge_lifecycle_routes +12 more; NOT wired: pages/Knowledge.route.tsx. MORE ELSEWHERE, read before building: closed PR #160's branch M27/console-knowledge (may be replayed already); closed PR #164's branch M27/console-knowledge-r2 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.15.41": {
    status: "OPEN",
    why: "Partly: entity merges are approved or rejected from Possible duplicates and quick answers are listed. Not built: a classification applied only by a second person (CONA-39); today a mark is applied by the administrator who reviewed it, and nothing records a proposer.",
    updated: "2026-10-21",
  },
  "M27.15.43": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (binding_routes, ops.acceptance_operations_console_4, pages/channels/ChannelAbout.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.44": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, webhook_routes, pages/webhooks/WebhookActs.tsx +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M27/webhook-switch-on-and-replay, no PR",
    updated: "2026-10-06",
  },
  "M27.15.47": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in jobs_routes, ops.acceptance_operations_console_2, pages/jobsQuery.ts +3 more; NOT wired: pages/Job.tsx, pages/Jobs.route.tsx",
    updated: "2026-10-06",
  },
  "M27.15.48": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (log_routes, ops.acceptance_operations_console_5, pages/logsQuery.ts +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_agent_console, pages/people/PersonOverview.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.50": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (credential_routes, ops.acceptance_operations_console_6, ops.credential_catalogue +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M27.15.51": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install_routes, ops.acceptance_operations_console, ops.features +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.55": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.skill_library, ops.acceptance_skill_console, ops.skill_store +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M27.15.56": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.skill_library, ops.acceptance_skill_console, ops.skill_store +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M27.15.57": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skills); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.58": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connector_routes, console.connector_detail, ops.acceptance_agent_console +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M27.15.60": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_people_console_2, pages/people/PersonAccess.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.63": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_people_console_3); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.66": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_people_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connector_routes, console.connector_detail, console.entity_stats +13 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +12 more",
    updated: "2026-10-06",
  },
  "M27.15.81": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): nothing found on main or on any branch for this task",
    updated: "2026-10-06",
  },
  "M27.15.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, console.entity_stats, console_stats_routes +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); closed PR #209's branch M39/w3-agent-workspace (may be replayed already); +5 more",
    updated: "2026-10-06",
  },
  "M27.15.11": {
    status: "BLOCKED",
    why: "Conflicts with a recorded design and needs the owner: the product keeps no text of an unanswered question (brain.adoption: a log of what people asked and did not get is a search history), so a knowledge owner can be shown a department and a source and never the question. Showing a nothing-found question only when the owner's reach covers the asker's and the owner's own search finds nothing needs either the text kept or a flag worked out at the moment of asking; neither is decided.",
    updated: "2026-10-21",
  },
  "M27.15.12": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED: the Requirement checks screen names M27.15.12 as the leaf the Console area is checked for, and an install check passes only when every requirement of the register's Console area has a newest check recorded by a person that passed. Install proof, which only you can give: open Requirement checks, choose the Console area, open each requirement on its page, and record passed or failed with a sentence about what you did.",
    updated: "2026-10-20",
  },
  "M27.16.1": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED: docs/console-pages.json lists the 42 primary pages (the 41 menu entries and the page of one agent) and console/tests/console-pages.test.ts holds its statement that each is built on the page kit against the source (all 42 are). /build/pages lists which pages are rebuilt, with what each still lacks. Install proof: open /build/pages after the next deploy and read the list; it says how many pages are rebuilt and names what each of the others waits on.",
    updated: "2026-10-20",
  },
  "M27.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.needs_you, console.operate, console_overview_figures_routes +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #157's branch M27/console-stats-overview-r3 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate, operate_routes, ops.acceptance_operations_console_2 +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate, ops.acceptance_operations_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate, operate_routes, pages/liveRunsQuery.ts +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.7": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.operate, incident_routes, pages/incidentsQuery.ts +1 more; NOT wired: pages/Incidents.route.tsx",
    updated: "2026-10-06",
  },
  "M27.2.8": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.operate, pages/operations/StopPage.tsx, pages/stopQuery.ts; NOT wired: pages/Stop.route.tsx",
    updated: "2026-10-06",
  },
  "M27.3.11": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.3.12": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern_estate); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern_surfaces, govern_routes, ops.acceptance_people_console); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.3.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern_surfaces, ops.acceptance_people_console_3); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.5.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.installation, console.screens, ops.acceptance_people_console_3); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-shell",
    updated: "2026-10-06",
  },
  "M27.5.2": {
    status: "OPEN",
    why: "Read on 2026-10-21: console.reads.tagged and untagged_rows exist and are tested, and no console route builds its rows through them, because the reports built so far carry counts and names and no confidential field values. The leaf is true of the helper and unproven of any screen; it needs a screen that lists record fields to show it, and an install check on that screen.",
    updated: "2026-10-21",
  },
  "M27.5.3": {
    status: "OPEN",
    why: "Built and wired: console.reads.audience is the one intersect, called by the agent workspace capabilities. Held by unit tests that fail on a union and on a widening parameter. No install check names it yet.",
    updated: "2026-10-21",
  },
  "M27.5.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.reads); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.5.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.screens, ops.acceptance_people_console_3); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-shell",
    updated: "2026-10-06",
  },
  "M27.5.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.screens, ops.acceptance_people_console_3); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-shell",
    updated: "2026-10-06",
  },
  "M27.5.9": {
    status: "OPEN",
    why: "Built: every registered screen carries the department and person axes (tests/unit/test_screens.py) and the department filter offers only what the reader reaches (install check on M27.5.8). No install check names this leaf.",
    updated: "2026-10-21",
  },
  "M27.6.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.installation, ops.acceptance_operations_console); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.7.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, identity.bearer, identity.session_store +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.7.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.sign_in_links, identity.sign_in_binding, ops.acceptance_people_console_2 +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w03",
    updated: "2026-10-06",
  },
  "M27.7.12": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (govern_people_routes, notification_routes, ops.acceptance_operations_console_5 +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); +5 more",
    updated: "2026-10-06",
  },
  "M27.7.13": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.view, audit_routes, ops.acceptance_people_console_2 +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/train-0200, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M27.7.14": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.usage_screen, gate.finish, models.calls +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w1-7; +1 more",
    updated: "2026-10-06",
  },
  "M27.7.15": {
    status: "READY FOR TESTING",
    why: "Built and wired, and now followed end to end by the install check `a_model_call_is_costed_and_a_used_up_budget_stops_the_next`: a department whose daily ceiling is used up has a stop recorded for its next question, listed to a reader of that department's spend with whether the install enforced it, and shown to nobody in another department. The check reads the enforcement switch and never sets it, so it passes on an install with enforcement off (the stop is listed as not enforced) and on one with it on. To prove it on the install: open Install, run the checks and read that check; the leaf closes when it passes on the install's two newest runs.",
    updated: "2026-10-21",
  },
  "M27.7.17": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (report_routes, pages/adoptionQuery.ts, pages/reports/AdoptionPage.tsx); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.7.18": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.questions_view, gate.abstain, gate.answer +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928",
    updated: "2026-10-06",
  },
  "M27.7.19": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.quality_view, ops.acceptance_operations_console_3, ops.canary_run +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #84's branch M5/model-health-routing-residency (may be replayed already); old backup branch recovery/from-windows-20260928; old backup branch recovery/from-windows-20260928-wt-automation-memory; +2 more",
    updated: "2026-10-06",
  },
  "M27.7.2": {
    status: "OPEN",
    why: "Built: the Staff sources page chooses a source, tests it before saving, and asks for a trial read the worker makes with nothing applied (ops.staff_connect, ops.staff_trial). The install proof needs the owner's own staff source; it is held with the other staff-list checks (needs-rupash 126).",
    updated: "2026-10-21",
  },
  "M27.7.20": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (estate_routes); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #245's branch M16/w3-waiting (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M27.7.22": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (estate_routes, ops.memory_store, tables.learning +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #245's branch M16/w3-waiting (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.7.23": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (artifact_routes, pages/Artifacts.tsx, pages/operations/ArtifactsPage.tsx); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.7.24": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, erasure_routes, ops.acceptance_operations_console_3 +10 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M27.7.25": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install_routes, pages/Install.tsx, pages/Updates.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w0b",
    updated: "2026-10-06",
  },
  "M27.7.26": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_5, pages/Recovery.tsx); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.7.27": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install_routes, ops.acceptance_operations_console, pages/Capacity.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w0b",
    updated: "2026-10-06",
  },
  "M27.7.28": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (mine_routes, ops.acceptance_people_console_3, pages/MyWorkspace.tsx +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M27.7.29": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.department_console, console.installation, console.screens +9 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-shell",
    updated: "2026-10-06",
  },
  "M27.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (govern_routes, ops.acceptance_people_console); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #125's branch M27/people-grant-controls (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); old backup branch recovery/from-windows-20260928-wt-integrate2; +3 more",
    updated: "2026-10-06",
  },
  "M27.7.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (govern_routes, ops.acceptance_people_console, pages/governQuery.ts); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #125's branch M27/people-grant-controls (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #59's branch M1/role-grants-deputies-floor (may be replayed already); +6 more",
    updated: "2026-10-06",
  },
  "M27.7.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (govern_routes, ops.acceptance_people_console); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #125's branch M27/people-grant-controls (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); old backup branch recovery/from-windows-20260928-wt-integrate2; +3 more",
    updated: "2026-10-06",
  },
  "M27.7.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record, console.elevation +11 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already); +6 more",
    updated: "2026-10-06",
  },
  "M27.7.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record, console.organisation +11 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #80's branch M1/group-sync-break-glass-notice (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.8.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (feature_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.8.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (notification_routes, ops.acceptance_operations_console_5, ops.mail +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); closed PR #299's branch M8/w2-escalation (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.8.13": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (jobs_routes, operate_routes, ops.acceptance_operations_console_2 +7 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.8.15": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_5, storage_routes, pages/Storage.tsx +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.8.16": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (data_transfer_routes, ops.acceptance_operations_console_5, ops.data_export_store +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w04b",
    updated: "2026-10-06",
  },
  "M27.8.17": {
    status: "OPEN",
    why: "The guard exists and is green in CI (console/tests/console-audit.test.ts). Its own report on 2026-10-21 lists write routes whose audit entry or behaviour has no named proof (docs/console-audit/*.md, rows marked None: staff source sync and trial, digest destination, install settings, model prices, profile, providers, tiers, residency, notices, relay, plugins, migration register, channel test, lark app, referrals). Each is a test to write; none is written.",
    updated: "2026-10-21",
  },
  "M27.8.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_routes, approval_routes, audit_routes +31 more; NOT wired: pages/Approvals.tsx. MORE ELSEWHERE, read before building: branch M33/train-0200, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +18 more",
    updated: "2026-10-06",
  },
  "M27.8.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, ops.acceptance_agent_console, prompt_routes +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.9.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_people_console_2, ops.acceptance_people_signed_in); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.9.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.admission, ops.acceptance_people_console_2, ops.acceptance_people_signed_in +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w03",
    updated: "2026-10-06",
  },
  "M27.9.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (approval_routes, gate.suspension_store, ops.acceptance_people_console_3 +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w03",
    updated: "2026-10-06",
  },
  "M27.9.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.readable_export, data_transfer_routes, ops.acceptance_people_console_2 +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w04b",
    updated: "2026-10-06",
  },
  "M27.9.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.9.8": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED in the repository (no install step): the stale statements named in the console plan's W0.7 are corrected where they were still wrong, each behavioural one with a test: the schema count in brain.db (a test now reads the number it states), the stop-control sentence the runs route serves, the usage screen's account of what is measured, and the embedding queue's, chunk store's and streaming's statements about callers and routes that now exist. Proved by the Unit tests job.",
    updated: "2026-10-20",
  },
  "M27.9.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connector_routes, data_steward_routes, identity.data_steward +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #125's branch M27/people-grant-controls (may be replayed already); closed PR #173's branch M27/connector-test-probe (may be replayed already); old backup branch recovery/from-windows-20260928-wt-integrate2; +4 more",
    updated: "2026-10-06",
  },
  "M28.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, ops.canaries); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.canaries); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, ops.canaries); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.canaries, ops.canary_run, ops.schedule); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.feedback); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.feedback); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.sampling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M29.1.12": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry notification_sink names contract brain.ops.digest_delivery:DigestSender (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry connector names contract brain.connectors.contract:ConnectorFetch (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. Console connectors (M11.7.8) are separate. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry skill names contract brain.tools.skills:Skill (exists), tier sandbox; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.1.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry template names contract brain.agents.template:TemplateManifest (exists), tier in_process; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.1.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry model_provider names contract brain.models.driver:ModelDriver (exists), tier sidecar; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.1.7": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points entry field_classifier names contract brain.ops.pii:Recogniser (exists), tier sandbox; test_plugins_points. Nothing outside the registry imports brain.plugins and the Features page says plugins have no loader. NEXT: Wire a plugin host: a loader that reads ops.plugin_registry records and calls plugins.contract before handing the point its input; show points on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.manifest (PluginManifest, manifest_from, PLUGIN_ID_RE, refuses reach keys; core compatibility range) is built and tested (test_plugins_manifest); only ops.plugin_registry and tables.plugin import it, and no route accepts a manifest. NEXT: Add an install route that parses an uploaded manifest with manifest_from and records it via plugin_registry; then check.",
    updated: "2026-10-13",
  },
  "M29.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): Migration 0032, tables.plugin (PluginInstallRow, PluginVersionRow) and ops.plugin_registry (remember, save, records, one document per version) are built and tested (test_plugin_registry); nothing calls plugin_registry. NEXT: Call plugin_registry from a plugin install route and the Features and plugins page; then write a check naming M29.2.2.",
    updated: "2026-10-13",
  },
  "M29.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.lifecycle (install, enable, disable, upgrade, rollback, assert_transition; nothing arrives enabled) is built and tested (test_plugins_lifecycle); only ops.plugin_registry calls assert_transition, and no route or page drives a transition. NEXT: Expose transitions as routes over plugin_registry (admin authority, ledgered) and buttons on the Features and plugins page.",
    updated: "2026-10-13",
  },
  "M29.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.lifecycle models the drain (in-flight work finishes on the old version) and is tested, but there are no plugin runs to drain: no loader, and no route upgrades a plugin. NEXT: Build with M29.2.3 plus the host: count in-flight calls per plugin version and block the switch until they finish.",
    updated: "2026-10-13",
  },
  "M29.2.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.points gives each plugin point a tier (in_process, sidecar, sandbox) and structural rules (code never runs in process); tested in test_plugins_points. No host enforces a tier because no plugin is loaded. NEXT: Enforce the tier in the plugin host when it exists (sidecar or sandbox runner reuse brain.tools sandbox); until then nothing to check on an install.",
    updated: "2026-10-13",
  },
  "M29.2.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): plugins.contract checks a plugin cannot see an unredacted result it did not produce and cannot widen entitlements (uses EntitlementSet.intersect); tested in test_plugins_contract. Nothing calls it: brain.plugins has no importer outside the registry. NEXT: Call plugins.contract from the host before every plugin call; then write a check with a stand-in plugin asserting both properties.",
    updated: "2026-10-13",
  },
  "M3.7.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.catalogue); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.1.3": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): docker-compose.tunnel.yml and .tunnel.identity.yml, ops/tunnel.py (overlay_gaps, page_gaps) and deployment/release.py carry the option; docs/install/network.md explains it; test_tunnel_option.py. tunnel.py says no tunnel has ever been started from these files.",
    updated: "2026-10-13",
  },
  "M30.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/backup/brain-backup (systemd timer 02:00) takes a nightly pg_dump -Fc with a manifest; backup_manifest.py reads it. No pgBackRest, no continuous WAL, no daily incremental or weekly full: recovery.SCHEDULE says nothing in the repository runs them. NEXT: decide pgBackRest versus the nightly dump (needs-rupash item 44 option C chose the dump for now), then add a pgBackRest stanza, WAL archive_command and timers to the installer",
    updated: "2026-10-13",
  },
  "M30.3.10": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): recovery.alerts() raises BACKUP_AGED against the profile RPO from real manifests (tested); schedule_runner Runner backup_exposure has needs= and no run, controls.backup_exposure is invoked_by NOTHING, and ops/notices BACKUP_EXPOSURE says no channel is chosen. Nothing calls alerts(). NEXT: give Runner backup_exposure a run that lists manifests with backup_manifest.read_manifests, calls recovery.alerts and sends the notice to the operations alert holder; channel may need an owner decision",
    updated: "2026-10-13",
  },
  "M30.3.11": {
    status: "READY FOR TESTING",
    why: "BUILT: a rehearsal that did not verify is recorded by the drill service and is the first alert the existing report raises. PROOF ON THE INSTALL: the check a_rehearsal_that_did_not_verify_is_the_loudest_alert passes; to see it live, a failed record on the Recovery screen appears above a late copy.",
    updated: "2026-10-20",
  },
  "M30.3.2": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): Nothing backs up the object store or configuration: ops/backup/brain-backup copies the database only; no restic anywhere in src, ops or compose files. recovery.SCHEDULE declares hourly snapshots of both and says nothing runs them.",
    updated: "2026-10-13",
  },
  "M30.3.3": {
    status: "READY FOR TESTING",
    why: "BUILT: the installer refuses a default and an address that is plainly this machine, copies declare off_host on the manifest, and the Recovery screen states a copy kept on the host (brain.ops.recovery.placement_findings). PROOF ON THE INSTALL: 1. Run ops/backup/brain-install-backup with BRAIN_BACKUP_ENDPOINT set to an object store on another machine and BRAIN_BACKUP_OFF_HOST=yes. 2. Take one copy (systemctl start brain-backup.service). 3. Open Backup and recovery: no finding says the copy is on the same host. The install check the_newest_copy_is_off_the_host_under_the_clients_key passes on the next run.",
    updated: "2026-10-20",
  },
  "M30.3.4": {
    status: "READY FOR TESTING",
    why: "BUILT: brain-backup-crypt encrypts each copy to the client's public key before it leaves the machine and the manifest names the client as key holder. PROOF ON THE INSTALL: 1. Generate a key pair on the client's own machine and copy only the public file to the server. 2. Run the installer with BRAIN_BACKUP_RECIPIENT set to that file. 3. Take a copy: the bucket holds a .dump.enc and a .dump.key and no plain .dump. 4. The Recovery screen lists no finding about the key. The install check the_newest_copy_is_off_the_host_under_the_clients_key passes.",
    updated: "2026-10-20",
  },
  "M30.3.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Decided narrower by needs-rupash item 60 option A (register DEC-5): thirty daily copies and weekly to day 35. recovery.RETENTION_LADDER and backup_ladder.select decide it; the backups bucket's 35-day lifecycle (ops/seaweedfs/provision.sh) holds a superset. Tests: test_backup_ladder, test_recovery. NEXT: write check naming M30.3.5: read the backups bucket lifecycle rule equals retention.BACKUP_RETENTION_DAYS and backup_policy_gaps() is empty; a pruner is optional and was rejected for now",
    updated: "2026-10-13",
  },
  "M30.3.6": {
    status: "READY FOR TESTING",
    why: "BUILT: ops/backup/brain-drill-service with brain-drill.timer rehearses the newest copy when a week has passed or one is asked for, behind the choice in needs-rupash 235 (option B). PROOF ON THE INSTALL: 1. Run the installer with BRAIN_DRILL_SERVICE=yes. 2. Wait ten minutes or press Start a rehearsal once its switch is on. 3. A record ending .drill.json appears beside the copy and the Recovery screen shows the rehearsal. The check the_newest_rehearsal_asked_all_three_questions passes on the next run.",
    updated: "2026-10-20",
  },
  "M30.3.7": {
    status: "READY FOR TESTING",
    why: "BUILT: python -m brain.ops.drill_checks asks the loaded copy for its schema and the permission canary (a stranger refused, the owner shown, role and fast lane attributes). PROOF ON THE INSTALL: the record written by the first rehearsal lists schema_complete, smoke_query and permission_canary as asked; the check the_newest_rehearsal_asked_all_three_questions passes.",
    updated: "2026-10-20",
  },
  "M30.3.8": {
    status: "READY FOR TESTING",
    why: "BUILT: the drill service writes the record the product reads, and a verified record carries its measured recovery time. PROOF ON THE INSTALL: after a rehearsal verifies, Backup and recovery shows how long the last restore took against the profile's promise. The check a_verified_rehearsal_states_its_measured_time passes.",
    updated: "2026-10-20",
  },
  "M30.3.9": {
    status: "READY FOR TESTING",
    why: "BUILT: Start a rehearsal on Backup and recovery leaves a request for the server's drill service (POST /install/recovery/rehearsal), behind the backup_drill_requests switch which ships off; it says it asked and never that a rehearsal began. PROOF ON THE INSTALL: 1. Turn Ask the server for a restore rehearsal on under Features (this is your answer to needs-rupash 235). 2. Press Start a rehearsal and confirm. 3. Within about ten minutes the screen shows a new rehearsal record. Only a person pressing it with the drill service installed can close this leaf.",
    updated: "2026-10-20",
  },
  "M30.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/reliability.py RetryClass (safe, after verification, unsafe, needs a human), OperationClass, retry_class_for(), classification_gaps() are tested; nothing outside reliability.py calls retry_class_for (effects.py PORTS is a separate classification). NEXT: consult retry_class_for in ops.recovery_run.sweep_queue and queue verdict_for for the task name, so the class decides redrive versus person",
    updated: "2026-10-13",
  },
  "M30.4.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): 429 and malformed handling exists: models/routing.py maps 429 to FallbackTrigger.RATE_LIMITED, models/calls.py walks the ladder, gate/runtime.py counts a malformed reply as a turn; unit tests in test_model_calls, test_routing, test_agent_runtime. ops/crash.py is about worker crashes. No injection suite on an install. NEXT: write install check with a stub provider returning 429 then a malformed reply, asserting fallback and the stated stop reason through the real answer route",
    updated: "2026-10-13",
  },
  "M30.4.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Disk full is handled by name only in deployment/database.py (create, migrate, seed raise DiskFullError via reliability.is_disk_full); the request path, ledger writes and uploads do not catch it, and no test fills a disk. NEXT: call is_disk_full on answer-path writes and object store puts and return the stated refusal; add an install check with a tiny tmpfs volume",
    updated: "2026-10-13",
  },
  "M30.5.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): gate/finish.py records every request into telemetry (ops/telemetry_store.py, tables/telemetry.py RequestTelemetryRow) with lane, tokens, duration and status; GET /report/service-levels reads it (ops/service_levels.py). Tests: test_telemetry_store, test_service_levels, test_request_finish. NEXT: write check naming M30.5.2: ask a question through the answer route and assert the telemetry row carries lane, duration and status",
    updated: "2026-10-13",
  },
  "M30.5.4": {
    status: "READY FOR TESTING",
    why: "BUILT: GET /handover returns the service level statement for the install's profile or the one sentence for why it cannot be made. PROOF ON THE INSTALL: 1. Call GET /api/v1/handover as the first administrator, or read it from the console once a page draws it. 2. Before any rehearsal has verified a copy it says no restore has ever verified. 3. After a rehearsal verifies and every copy is inside the recovery point it carries the profile's recovery point, time and the time measured. The check the_statement_is_made_only_after_a_rehearsal_verified passes.",
    updated: "2026-10-20",
  },
  "M32.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.tracing); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.1.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_audit, ops.tracing, trace_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.1.2.6": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, ops.acceptance_checks_services, ops.ledger_export +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.2.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.pii); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-g4",
    updated: "2026-10-06",
  },
  "M32.3.1.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.1.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.2.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.5.2.1": {
    status: "READY FOR TESTING",
    why: "built (M32/tanstack-table-every-grid): every list and every table in the console is now drawn through TanStack Table from one feature set, and the Artifacts list, the one list that narrowed the whole estate in the browser, now pages, searches, filters and orders on the server; to prove on the install: open Knowledge and data then Artifacts, type part of an agent's name in the search box and see the list narrow to that agent's artifacts (it asks the server, so one on a later page is found), choose a kind and an order, press Show more until it goes; then open Models and see the failover matrix, the prices and the routing tables read as before, and on Custom connectors type a whole word into a field name without the cursor leaving the box",
    updated: "2026-10-14",
  },
  "M32.5.2.3": {
    status: "READY FOR TESTING",
    why: "built (M32/react-flow-keyboard-and-list): the trace graph on Audit then Trace and the agent builder's procedure canvas are both drawn through React Flow, each step takes a tab stop and is read aloud with its words and kind, a skip link jumps past the drawing, and the trace has the steps as a list under it; to prove on the install: sign in as a reader holding the trace reader role, open Audit then Trace, enter a trace id and a reason, press Tab and see each box take the focus ring, press Tab until the link Skip the drawing appears, press Enter and land on the list of steps, then open an agent's draft, go to its Procedure step and do the same",
    updated: "2026-10-14",
  },
  "M32.6.1.1": {
    status: "READY FOR TESTING",
    why: "The canvas was already built and wired (docker-compose.automation.yml, the automation overlay, ops.automation). What was missing was proof on the install, and it is merged: the install check the_canvas_runs_as_three_services_each_held_to_its_budget reads what the deploy step saw and closes the leaf when the install's two newest runs both pass it. Install proof, steps: (1) put automation in the install's optional services setting (needs-rupash 124 decided yes; it takes 896 MiB, and the deploy says in words if the server has no room); (2) deploy, and read the deploy's journal for the line saying the canvas's facts are kept for this release; (3) open the Install page's list of checks after the next run and see the check pass.",
    updated: "2026-10-14",
  },
  "M32.6.1.2": {
    status: "READY FOR TESTING",
    why: "Built and wired already; the proof was missing and is merged. The deploy step now asks docker what is running (ops/deploy/overlays/automation.observe.sh: networks, the names and never the values of the canvas's variables, routes, the proxy's hosts and its answer for a host on no list) and the install check the_canvas_has_no_way_out_but_its_proxy_and_no_foreign_secret judges it, closing the leaf when the install's two newest runs both pass it. Install proof, steps: the same three as M32.6.1.1; the second check on the Install page is the one for this task. A failure names the kind of fault in a sentence and the worker's log names the variables.",
    updated: "2026-10-14",
  },
  "M32.6.1.4": {
    status: "READY FOR TESTING",
    why: "Built and wired already: the canvas is the automation overlay and the one setting INSTALL_SERVICES switches it, a fresh install ships with none. The proof was missing and is merged: the install check the_canvas_runs_where_the_setting_names_it_and_nowhere_else is judged both ways (running where the setting names it, absent from the deploy's report where it does not) and closes the leaf when the install's two newest runs both pass it. Install proof, steps: with automation in the setting, as for M32.6.1.1, the third check passes; the other direction is what an install that has not named it shows once any other optional service reports.",
    updated: "2026-10-14",
  },
  "M33.1.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in company_routes, console.department_console, console.global_surfaces +2 more; NOT wired: pages/Company.route.tsx",
    updated: "2026-10-06",
  },
  "M33.1.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in company_routes, console.global_surfaces, pages/company/CompanyPages.tsx +1 more; NOT wired: pages/Company.route.tsx",
    updated: "2026-10-06",
  },
  "M33.1.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in company_routes, console.department_console, console.global_surfaces +2 more; NOT wired: pages/Company.route.tsx",
    updated: "2026-10-06",
  },
  "M33.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_lifecycle_routes, agents.lifecycle, console.global_surfaces +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.global_surfaces, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.global_surfaces, identity.nomination_store, nomination_routes +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/role-nominations, no PR",
    updated: "2026-10-06",
  },
  "M33.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.global_surfaces, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.role_surfaces, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (chat.turns, console.scoped_authority, identity.staff_sync +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, department_view_routes, pages/department/DepartmentHomePage.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, department_view_routes, pages/department/DepartmentHomePage.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.2.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.scoped_authority, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M33.3.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.own_things, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.3.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.own_things, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.3.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.own_things, thread_routes, pages/Ask.tsx +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/my-conversation-export, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +1 more",
    updated: "2026-10-06",
  },
  "M33.3.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.own_things, ops.acceptance_checks_role_surfaces); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.4.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern_surfaces, ops.acceptance_checks_governance); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.4.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit_routes, console.auditor, ops.acceptance_checks_role_surfaces); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/train-0200, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +2 more",
    updated: "2026-10-06",
  },
  "M33.4.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit_statistics_routes, console.auditor, pages/audit/AuditPage.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.5.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.registry, console.declaration_drift, ops.acceptance_checks_governance_2 +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.5.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.registry, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.5.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.manifest, console.role_surfaces, identity.staff_source); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.6.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.approvals, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.6.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.role_surfaces, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.7.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.elevation, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.7.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.chain_check, console.elevation, docs_routes +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/elevation-chain, no PR",
    updated: "2026-10-06",
  },
  "M33.7.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.elevation, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.7.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.elevation, ops.acceptance_checks_governance_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M33.8.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in approval_cards, approval_routes, console.approvals +4 more; NOT wired: member.approvals",
    updated: "2026-10-06",
  },
  "M34.1.1.1": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 (branch M34/adoption-wiring), not proved on an install: adoption.first_connector is now called by GET /console/connector-start (brain.adoption_coverage_routes, read behind the Connectors grant, not switched because it is drawn from the list of sources every release ships), and the Connectors list says which source to start with while nothing is connected. It picks a source whose records exist and can be opened in their own system, the widest reach first, and never one already connected. Install proof, in order: 1. Sign in as an administrator on an install where nothing is connected and open Connectors. 2. Read the line over the list: it names one source and says why. 3. Connect any source and reload: the line is gone. Not built: the setup wizard's connector step does not show it. Install check a_department_is_told_what_is_connected_for_it_alone covers the route. Reused: adoption.first_connector, ConnectorOffer, connector_catalogue.declarations.",
    updated: "2026-10-20",
  },
  "M34.1.1.2": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 (branch M34/adoption-wiring), behind the switch starter_questions_from_data (off): adoption.starter_questions is called by GET /welcome/from-your-data (brain.welcome_routes), and the same AskWelcome component that draws the fixed starter questions draws up to three more built from the kinds of record the person's own department has indexed. A kind of record is a candidate only when row_scope_for admits the person to it in their department, and the three are chosen among those, so a record kind they cannot read is never suggested and nothing is counted. Install proof, in order: 1. Turn Suggest first questions built from what a person's department has connected on at Features. 2. Sign in as a person whose department has a source connected and read, and who may read that kind of record there, and open Ask before asking anything. 3. Read the second list: each question names the system to check it in. 4. Sign in as a person without that read: no second list. Reused: adoption.starter_questions, welcome_routes, AskWelcome, knowledge.rows.row_scope_for.",
    updated: "2026-10-20",
  },
  "M34.1.1.3": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-20 (branch M34/adoption-wiring): the starter questions built from data each name the system to check the answer in (adoption.StarterQuestion.check_in, drawn by AskWelcome as 'Check the answer in <source>'), and a source with no live lookup of a record by its id contributes none. An ordinary answer is checkable through its citation (CitedDocument) and, for a record, its source; adoption.verification_targets is not called from the answer view because it ranks documents by how often answers cite them and nothing records that (see M34.2.1.1). NEXT: decide whether citations already satisfy the leaf for ordinary answers and write the check over them.",
    updated: "2026-10-20",
  },
  "M34.1.2.1": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 (branch M34/adoption-wiring), behind the switch adoption_coverage (off): adoption.coverage_report is called by GET /report/coverage (brain.adoption_coverage_routes) over the live connections, the manifests, the worker's sync state and a count of proj.record rows per department, and the Adoption page draws it: for each department the reader's usage grant admits, each source connected for it, how many records the index holds and when it was last read. A source the reader may not be told of is merged into one line that names none. Sources pinned to the whole organisation belong to no department's line and the page says so. Install proof, in order: 1. Turn Show each department what is connected for it on at Features. 2. Connect a source for a department, let the worker read it, and open Adoption as a department lead. 3. Read the line for that department: the source, a record count and the last read. 4. Sign in as a lead of another department: the first department is not shown. Reused: adoption.coverage_report, ScopeCoverage, connector_detail.department_of, adoption_view.reachable_departments.",
    updated: "2026-10-20",
  },
  "M34.1.2.2": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 (branch M34/adoption-wiring), behind the switch adoption_coverage (off), with M34.1.2.1: a department with nothing connected is a line that says Not connected, with no count and no time, and is never a zero; where nothing on the install could be suggested the line says so. Install proof: 1. With the switch on, open Adoption as an administrator. 2. Find a department with nothing connected: its line reads Not connected and names a source to authorise. 3. Connect a source for it: the line reads Connected. Reused: adoption.Coverage and ScopeCoverage.state.",
    updated: "2026-10-20",
  },
  "M34.1.2.3": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-20 (branch M34/adoption-wiring), behind the switch adoption_coverage (off), with M34.1.2.1: adoption.shopping_list is called by GET /report/coverage and the Adoption page lists what a champion can do next, the department whose questions went unanswered most first, with no percentage and no total. Install proof: 1. With the switch on, open Adoption as a department champion. 2. Read What to do next: one line per department with nothing connected or a connected source that is empty. 3. Ask a question no source covers a few times and reload: that department moves up. Reused: adoption.shopping_list, connector_demand and the question gap ledger.",
    updated: "2026-10-20",
  },
  "M34.2.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): adoption.verification_targets (five documents per department lead in week one) is built; no route, task or page uses it. knowledge.verification tasks exist separately for re-verification. NEXT: Create the week-one verification tasks from verification_targets through the knowledge tasks route when a department lead is placed.",
    updated: "2026-10-13",
  },
  "M34.2.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Chat marks (helpful or unhelpful) are wired in channels: marks.mark_line in chat_answer and read_mark in channels.inbound. The reason-bearing path channels.correction (send_with_correction, read_correction, file_correction) has no caller. NEXT: Call send_with_correction where adapters send an answer and read_correction in channels.inbound; then check naming M34.2.2.1 per channel.",
    updated: "2026-10-13",
  },
  "M34.2.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops.feedback.FlagReason.WRONG_SOURCES vs WRONG_FACT, plane_of and by_plane are built and tested (test_flag_planes); flag_answer is called only by the unwired channels.correction, and no route or console control files a flag. NEXT: Add a flag route (POST on an answer's trace with a FlagReason) and a console control, or wire channels.correction; then check.",
    updated: "2026-10-13",
  },
  "M34.2.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): adoption.connector_demand is called by console.questions_view over question_gap_store rows and served at GET /report/questions, QuestionsPage.tsx, scoped to the reader's departments. Check acceptance_people_console_3 touches the screen under other leaves. NEXT: Write check naming M34.2.2.3: ask a question no source answers, read /report/questions and assert a connector demand line.",
    updated: "2026-10-13",
  },
  "M34.3.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): adoption.visibility_summary (what it can and cannot see, plain language, from the reader's reach) is built and tested; no route or page calls it. NEXT: Serve it from a route for the signed-in person (reach-scoped) and link it from Ask or My workspace.",
    updated: "2026-10-13",
  },
  "M34.3.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): adoption.privacy_posture reads the install's configuration into plain sentences and is tested (test_adoption); no route or page calls it (locale.py names its keys only). NEXT: Serve privacy_posture on a staff-facing page or Ask help panel; reader needs no grant.",
    updated: "2026-10-13",
  },
  "M34.3.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): docs/guides/asking-well.md exists with per-department examples marker; ops.guide_docs.asking_examples and asking_gaps check it (test_guide_docs). Nothing imports guide_docs and no route serves the guide to staff. NEXT: Serve the guide from a help route that fills the examples marker with asking_examples for the reader's department.",
    updated: "2026-10-13",
  },
  "M34.3.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): 36 runbooks exist in docs/console/runbooks and launch.screen_runbook_gaps and guide_docs.runbook_gaps sweep them against the screen registry (test_guide_docs). No route or page serves them; docs_routes serves only the build pages. NEXT: Add a help route serving docs/console/runbooks per screen and a link on each console page (see M34.4.1).",
    updated: "2026-10-13",
  },
  "M34.3.3.3": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Document leaf: docs/install/update-and-rollback.md (275 lines) exists, held to the code by ops.install_docs and tests; release.py references it. Closing needs an operator to run an upgrade and a rollback on a server, or Proved-in-ci naming the guard test.",
    updated: "2026-10-13",
  },
  "M34.3.3.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Document leaf: docs/install/restore-drill.md (360 lines) exists, guarded by tests/unit/test_install_drill_page.py; the recovery screen says no control runs a drill (install_routes.NO_CONTROL_HERE_RUNS_A_REHEARSAL). The drill itself is run by hand on the server.",
    updated: "2026-10-13",
  },
  "M35.1.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): locale.MESSAGES holds en and zh-Hans (67 keys, catalogue_gaps tested) but only the setup wizard and data_steward_routes call text(); the served console draws English strings from TSX (CONSOLE_LANGUAGE en-GB) with no locale switch; enabled_locales and default_locale have no caller. NEXT: Add a locale choice (INSTALL_LOCALES) to the console shell and move console strings to the catalogue; start with Ask and Approvals; then a browser check in zh-Hans.",
    updated: "2026-10-13",
  },
  "M35.1.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): currency (locale.currency_or_unset) and time_zone are used by routes and workers; format_date, format_timestamp, format_number and format_money have no caller, and console dates use the browser default (Intl en-GB in spendQuery.ts). NEXT: Serve install-formatted dates, numbers and money from the API or a shared console formatter reading INSTALL_LOCALES; then a check on a Spend figure in zh-Hans.",
    updated: "2026-10-13",
  },
  "M35.1.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): locale.RIGHT_TO_LEFT deferral with trigger is defined, and rules_for refuses an RTL tag with its reason; but console.configuration._locales_problem swallows the LocaleError into a generic sentence, and locale_facts and triggered have no caller. NEXT: Pass the deferral's sentence through the settings refusal and report triggered() on the Install screen; then write the check (also M35.4.3).",
    updated: "2026-10-13",
  },
  "M35.1.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): knowledge.search lexical_legs and knowledge.chunk_store write know.chunk.cjk via chunk_text_fields (migration 0024); query side runs in the document search tool; ingest runs in the worker (ingest_queue.register_ingest_tasks). Test test_search. NEXT: Write check naming M35.1.2.1: ingest a Han-text document through the queue, query it in Chinese as a person who may read it, assert it is found.",
    updated: "2026-10-13",
  },
  "M35.1.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): search.chunk_text_fields tokenises every script in a chunk into cjk and detects the dominant language, and lexical_legs chooses legs per script in the question, so a mixed document is found by queries in either language. Tests test_search, test_locale. NEXT: Write check naming M35.1.2.2 ingesting a mixed English and Chinese document and asking in each language.",
    updated: "2026-10-13",
  },
  "M35.1.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): chunk_store.ingest_document writes know.chunk.language from locale.detect via chunk_text_fields (None when too little text); column from migration 0024. Test test_search. NEXT: Write check naming M35.1.2.3 that ingests one English and one Chinese document and reads know.chunk.language.",
    updated: "2026-10-13",
  },
  "M35.2.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/src/pages/Ask.tsx keeps the answer out of any live region and only progress steps use role=status; locale documents why. Tests console/tests/ask-page.test.tsx and skip-to-answer.test.tsx. Not shown under a real screen reader on an install. NEXT: Browser run on the install under a screen reader (or a console test over the served bundle) naming M35.2.1.1; no Python check can prove it.",
    updated: "2026-10-13",
  },
  "M35.2.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Ask.tsx returns focus to the skip control when the answer finishes (FOCUS_IS_RETURNED_AND_NEVER_TAKEN), the one announcement; test skip-to-answer.test.tsx. locale.announcements is unused by the console. Not observed in a browser on the install. NEXT: Same browser run as M35.2.1.1; add M35.2.1.2 to the console test's Task ids and record the install run.",
    updated: "2026-10-13",
  },
  "M35.2.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Ask.tsx SKIP_TO_ANSWER button after the form focuses the answer region; console test skip-to-answer.test.tsx exists and names the leaf. Label is English only (answer.skip_to is in the catalogue). NEXT: Browser run on the install asking a question and pressing the control; record it against M35.2.1.3.",
    updated: "2026-10-13",
  },
  "M35.2.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): 58 console files set aria-describedby and 39 aria-invalid; forms use SchemaForm with locale.form_gaps behind the setup wizard; unit tests assert labels. No test or run names M35.2.2.4 and none shows an error on the served console. NEXT: Browser run submitting an invalid value in a console form; add the leaf id to the form test's Task ids.",
    updated: "2026-10-13",
  },
  "M35.3.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Approvals.tsx and approvals/ApprovalCard.tsx with phone layout (console/tests/approvals-phone.test.tsx, approvals-page.test.tsx); POST decide route (approval_routes). Suspensions are now raised by held agent runs and knowledge promotions. Not run on a phone against the install. NEXT: Install run: raise an approval, open the console at phone width, decide it; record against M35.3.1.1.",
    updated: "2026-10-13",
  },
  "M35.3.2.2": {
    status: "READY FOR TESTING",
    why: "built (owner decision 222 A): the typical approval wait is measured through migration 0227's view gate.approval_wait (raised_at and decided_at only, no person) by ops/approval_wait.py and reaches This install as two facts, the typical wait and whether push for approvals is now worth building, decided by locale.triggered; no count of approvals is ever shown, an install with nothing decided is unknown with its reason and never zero, and GET /install is tested at the route (tests/unit/test_install_approval_wait_route.py, with a mutation table). PRIOR WORK (2026-10-13 triage): locale.PUSH_FOR_APPROVALS with Trigger.APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS and PUSH_IS_DUE_ABOVE_HOURS=4 is defined and tested; triggered() has no caller and nothing measures approval waits, so the trigger can never fire. NEXT: Build the wait measurement (see M35.4.5) and call locale.triggered from the report; that completes this leaf. PROVE ON THE INSTALL: run the acceptance run and read the result of the_approval_wait_is_measured_and_push_is_reported (it raises and approves three approvals in the acceptance department, as the Approvals route does, and leaves nothing behind); then open Install, This install, and see the typical approval wait and the push sentence, or unknown with a reason while nothing has been decided.",
    updated: "2026-10-14",
  },
  "M36.1.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Migration 0039 creates obs request telemetry partitioned by range on received_at; ops/ledger_partitions.maintain creates and detaches months in plain SQL and runs from the worker's retention_sweep runner (schedule_runner.py). Tests: test_ledger_partitions (real server in CI). NEXT: write check naming M36.1.1.1: run the retention sweep runner and read pg_inherits for the next month's partition under obs.request_telemetry",
    updated: "2026-10-13",
  },
  "M36.1.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/scaling.py partitioning_is_due is tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE calls it a person's decision. It takes a retention window and interval, not a measured row count or query latency, and GET /install/capacity does not evaluate it. NEXT: wire partitioning_is_due with the measured ledger row count and p95 into a section on GET /install/capacity; also note the trigger needs a row-count or latency input, not just the window",
    updated: "2026-10-13",
  },
  "M36.1.2.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): docker-compose.replica.yml and ops/streaming_replica.py (replica_overlay_gaps) are built and tested; docs/install/scaling.md says nobody has run the replica rehearsal. Built only when its trigger is met (ARC-B-104).",
    updated: "2026-10-13",
  },
  "M36.1.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): app.py builds app.state.console_reads from settings.read_replica_url (ops/replica_store.console_reads_for, falling back to the primary); estate, directory, govern and people routes read through ConsoleReads and console/read_replica.route_read. Tests: test_read_replica, test_replica_store. NEXT: write check naming M36.1.2.2: build ConsoleReads with a second session factory in the harness and assert a console read is served from it and an answer-path read is not",
    updated: "2026-10-13",
  },
  "M36.1.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): replica_store.measure_lag and console/read_replica.banner_for put a staleness field on estate, directory and govern route bodies (tested). The console UI renders it only on LearningPage and MemoryDetailPage; the other pages ignore the field. Not verified further. NEXT: render StalenessBanner on the pages whose routes carry it (estate, directory, people, govern); then check with a stubbed lag",
    updated: "2026-10-13",
  },
  "M36.1.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them. NEXT: wire replica_is_due with measured console read load against answer headroom into GET /install/capacity so a person sees when a replica is warranted",
    updated: "2026-10-13",
  },
  "M36.1.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): A materialised daily spend report exists: tables/spend.py, ops/spend_store.py, console/spend_report_view.py, migration 0034 and GET /report/spend. Usage, adoption, questions and quality reports still read live tables, so only one of the heaviest screens has a view. NEXT: decide which other report screens exceed two seconds (report_is_due) and materialise those; spend is done",
    updated: "2026-10-13",
  },
  "M36.1.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Runner spend_report_refresh in schedule_runner.py refreshes the spend view daily; spend_report_view carries as_of and freshness (LIVE, ageing, STALE tied to controls.MISSED_RUN_GRACE) and spendQuery.ts renders them. Tests: test_spend_report_view, test_worker_schedule. NEXT: write check naming M36.1.3.2: run the refresh runner, GET /report/spend and assert as_of and freshness LIVE; age the view and assert it reads ageing",
    updated: "2026-10-13",
  },
  "M36.1.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them. NEXT: wire report_is_due(observed_p95_ms) into the report routes' timing and into GET /install/capacity; needs a per-report latency measurement",
    updated: "2026-10-13",
  },
  "M36.1.4.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): ops/split.py with docker-compose.split*.yml (host_services, address_refusals) is built and tested in CI; docs/install/scaling.md says a split install serving a question has not been run. Needs-rupash notes M36.1.4.2 merged into M30.4.9.",
    updated: "2026-10-13",
  },
  "M36.1.4.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/scaling.py trigger predicates are tested (test_scaling.py) but nothing imports brain.ops.scaling; controls.NOT_A_SCHEDULE says each is a decision for a person asked when someone looks. GET /install/capacity (install_routes.py) does not evaluate them. NEXT: wire host_split_is_due(profile) with measured memory headroom into GET /install/capacity; resilience requirement input has no source yet",
    updated: "2026-10-13",
  },
  "M36.2.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): connectors/federation.py FanOutPlan (SourceCall, depends_on, cycle check, waves) is used by connectors/live_read.py, which runs in the answer path via ops/live_read_run and gate/live_records (app.py). Tests: test_connectors_federation and the connector acceptance checks. NEXT: write check naming M36.2.1.1: ask a question needing two independent source calls and assert the plan puts them in one wave (extend acceptance_checks_connector_framework.py)",
    updated: "2026-10-13",
  },
  "M36.2.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): live_read.py runs each wave with asyncio.gather and checks FanOutPlan.assert_within against the wall clock, so the cost is the critical path and not the sum. Tests: test_connectors_federation, test_live_read. NEXT: write check naming M36.2.1.2: two stub sources each taking a known time, assert the question's elapsed time is near the longer one, not the sum",
    updated: "2026-10-13",
  },
  "M36.2.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): live_read.py enforces CallBudget.assert_affordable and per-connector concurrency under gather (tested). Missing: a global ceiling; scaling.scaling_gaps and fanout_refusals say per-connector rows have no global row, up to the sum may be in flight, and are not called. NEXT: wire scaling.fanout_refusals and a declared global SOURCE_CALLS budget into live_read admission; then check parallel calls respect both",
    updated: "2026-10-13",
  },
  "M36.2.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): gate/screening.py screen_in_one_pass reports the same as the serial screens (tested), but nothing in the request path calls it and its docstring records the collapse does not pay (re has no multi-pattern automaton). No needs-rupash item records this narrowing. NEXT: raise a needs-rupash question to close M36.2.2.2 as measured not worth switching to, or switch the gate to screen_in_one_pass; the register row ARC-B-099 should name the decision",
    updated: "2026-10-13",
  },
  "M36.2.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): tests/unit/test_screening.py asserts the single pass reports exactly what the serial screens report across every fragment pair, corpora and generated text, plus overlapping detections; the equivalence is the proof that no coverage is lost. NEXT: repo-only leaf: close as Proved-in-ci naming the unit job running test_screening.py; no install check applies",
    updated: "2026-10-13",
  },
  "M36.2.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/scaling.py share_role, may_share, share_refusals decide whether an in-flight answer may be shared (tested); the answer path has no in-flight sharing (gate cache has none). Only connector fetches share, via federation.SingleFlight in live_read. NEXT: call scaling.share_role from the answer lane's cache lookup in gate (cache_key) so a second identical question waits for the first",
    updated: "2026-10-13",
  },
  "M36.2.3.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): scaling.may_share compares gate.cache_key parts and requires equal entitlement hash, never similarity (tested). The answer cache key itself already carries ent_hash, but nothing calls may_share, so no sharing happens. federation.flight_key omits reach on purpose. NEXT: wire may_share with M36.2.3.1; an existing cache check (ARC-A-051) already proves the key carries the hash",
    updated: "2026-10-13",
  },
  "M36.2.4.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): tests/load/test_admission_at_peak.py drives the admission controller at LOAD_TEST_TARGET (two arrivals a second for ten minutes) and ops/load_peak.py is the owner's command for a live install. Concurrency, not daily volume, is the unit. NEXT: repo-only leaf: close as Proved-in-ci naming the load test job; the live run is M36.3.1",
    updated: "2026-10-13",
  },
  "M36.2.4.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/admission.py bottleneck_ladder and FIRST_BOTTLENECK_AT_SCALE name the first limit at 10x and 100x; install_routes.capacity_plan feeds GET /install/capacity; acceptance_checks_capacity.py check capacity_is_sized_for_the_busiest_minute_and_its_first_limit asserts both 10x and 100x are named. NEXT: add M36.2.4.2 to leaves= of that existing check in acceptance_checks_capacity.py",
    updated: "2026-10-13",
  },
  "M37.1.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): inventory.py: Catalogue/Holding cover knowledge, prompts, tool definitions and conversation history, tested in test_migration_inventory.py; but nothing imports brain.migration.inventory outside the package; no table, route or page. NEXT: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route",
    updated: "2026-10-13",
  },
  "M37.1.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): inventory.py: Disposition (migrate, rebuild, retire), Decision, undecided(), contradicted(), cannot_be_carried(), tested; no caller outside the package, no store or screen. NEXT: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route",
    updated: "2026-10-13",
  },
  "M37.1.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): inventory.py: PermissionMapping, unmapped(), mapped_twice() make a mapping explicit and refuse an unmapped permission; tested; no caller outside the package, no store or screen. NEXT: add a migration store (table) plus a console route and page that record the catalogue and decisions through inventory.agree(), then write a check naming the leaf that reads that route",
    updated: "2026-10-13",
  },
  "M37.1.2.1": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: POST /migration/carry compares a pasted export with the agreed register in both directions (carry.export_gaps) and names what is promised and not delivered. NOT BUILT: the exporter itself, which is a plugin that does not exist (brain.plugins has contract and points only), so the export is pasted by the person who surveyed the old system. NEXT: define the exporter plugin point.",
    updated: "2026-10-20",
  },
  "M37.1.2.2": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: POST /migration/carry returns the plan to read every export again from its original bytes and names every vector as discarded (carry.reparse_plan, carried_vectors); there is no field for a vector. NOT BUILT: queueing the knowledge pipeline from that plan, which needs the original bytes held somewhere. NEXT: a store for the exported bytes and a call from the plan into ingest.",
    updated: "2026-10-20",
  },
  "M37.1.2.3": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: POST /migration/carry reports seeds that collapse to one name and names a name the matcher will not match on (carry.seed_gaps). NOT BUILT: writing an approved seed into the entity registry through the resolution write path. NEXT: a registry-seeding route using brain.resolution after a person approves each seed.",
    updated: "2026-10-20",
  },
  "M37.1.2.4": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: POST /migration/carry returns every catalogued conversation as archived, the ones kept for a stated reason by a named person, and an empty searchable list by construction (carry.archive). NOT BUILT: persisting the archive. NEXT: keep it in a migration record, never in knowledge search.",
    updated: "2026-10-20",
  },
  "M37.1.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): parallel.py: Period and Comparison hold an agreed window and per-question answers of both systems (tested). Nothing sends a question to both systems or records comparisons; no caller outside the package. NEXT: needs a runner that asks the old system via a plugin and records Comparison rows, plus a route; first build the store and recorder",
    updated: "2026-10-13",
  },
  "M37.1.3.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): parallel.py: disagreements(), unanswered(), unreviewed() build the comparison log views (tested). No table, route or page holds or shows the log; nothing imports parallel. NEXT: add a comparison-log table and a console page reading parallel.disagreements; then check",
    updated: "2026-10-13",
  },
  "M37.1.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): parallel.py: Criterion and Period require cutover criteria before the window opens; cutover_gaps(), may_cut_over() refuse otherwise (tested; DEC-35 row names it). No store or route; nothing imports parallel. NEXT: persist Period and Criterion with a created-at before the first Comparison, route may_cut_over to the cutover screen; then check",
    updated: "2026-10-13",
  },
  "M37.1.4.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): decommission.py: Decommission refuses read-only before cutover and archived before read-only (tested). Nothing reaches the old system and nothing outside the package imports decommission; no table, route or page. NEXT: add decommission record store and route that records timestamps through Decommission; then check",
    updated: "2026-10-13",
  },
  "M37.1.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): decommission.py: Revocation and credentials_outstanding() keep requested and confirmed apart (tested). Nothing revokes or probes a grant and nothing imports it; register row GAP2-25 names the leaf. NEXT: wire Revocation records to a console route fed by a person or a connector probe; then check",
    updated: "2026-10-13",
  },
  "M37.1.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): decommission.py: ScheduledJob and jobs_outstanding() require an observed silence window after disabling (tested). No store, route, caller outside the package. NEXT: record ScheduledJob observations through a route and show jobs_outstanding on the cutover page; then check",
    updated: "2026-10-13",
  },
  "M37.1.4.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): decommission.py: FinalBackup.may_delete_after derives retention from ops.retention.BACKUP_RETENTION_DAYS (tested). No store or route records a final backup; nothing imports the module. NEXT: wire FinalBackup record into the cutover route reading the real backup manifest (ops.backup_manifest); then check",
    updated: "2026-10-13",
  },
  "M37.2.2.2": {
    status: "READY FOR TESTING",
    why: "BUILT: POST /migration/skills/convert returns each pasted skill's description with the router preamble stripped as a draft for the reviewer, and lists the ones still written at a router. PROOF ON THE INSTALL: switch Keep a migration on under Features, paste a skill whose description begins Use the X skill to, and read the draft back. The check pasted_skills_are_converted_and_nothing_is_imported passes.",
    updated: "2026-10-20",
  },
  "M37.2.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Normal path exists: POST /skills/imports and /skills in skill_routes.py add via console/skill_library.added(), which builds an ImportedSkill unapproved; POST /skills/{digest}/review is the queue. migration.skills.arriving is a duplicate nobody calls. Tests: test_skill_library, test_skill_routes. NEXT: write check naming M37.2.2.3: import a skill by POST /skills/imports, assert it is unreviewed and not executable, then approve by POST /skills/{digest}/review as a second person (reuse acceptance_agent_console.py helpers)",
    updated: "2026-10-13",
  },
  "M37.2.2.4": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: the same route takes the real-task checks a person recorded and names every skill no task was run through and every one whose answer changed (skills.unproven). NOT BUILT: running the same task on both systems, which needs a person with the old system, and keeping the checks. NEXT: a store for behaviour checks shown on the skill review page.",
    updated: "2026-10-20",
  },
  "M37.2.2.5": {
    status: "READY FOR TESTING",
    why: "BUILT: POST /migration/skills/convert lists the pasted skills not invoked in ninety days and those never recorded as invoked, as ones to leave behind (skills.to_retire); retiring one is the existing retirement route. PROOF ON THE INSTALL: paste a skill with a last-invoked date a year old; it is listed. The check pasted_skills_are_converted_and_nothing_is_imported passes.",
    updated: "2026-10-20",
  },
  "M37.2.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Agents are only ever made from a template here: agents/install.py, agents/template.py, agent_lifecycle_routes.py install route, builder drafts; no importer of a foreign agent configuration exists on main. migration.rebuild.Rebuild is an unwired record. Tests exist for install. NEXT: write check naming M37.2.3.1: install an agent from a catalogue template via the lifecycle install route and assert it came from that template with no foreign prompt field (reuse existing install checks)",
    updated: "2026-10-13",
  },
  "M37.2.3.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): agents/model.py AgentAuthority is the explicit per-agent ceiling; agent_lifecycle_routes.py install writes one; E_run intersect applies it. migration.rebuild.authority_for (refuses empty capabilities) is unwired but the product path sets a ceiling. NEXT: write check naming M37.2.3.2: install an agent, read its authority from the agent route, assert capabilities are non-empty and a run is narrowed to them",
    updated: "2026-10-13",
  },
  "M37.2.3.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): agents/install_store.py INSTALLED_RUNG = AutonomyTier.SHADOW, builder STARTING_RUNG = SHADOW; agent_lifecycle_routes.py install writes every target at that rung (test refuses otherwise). migration.rebuild.Rebuild.write_tier unwired. NEXT: write check naming M37.2.3.3: install an agent and read its leash rungs from the leash route, assert every write target is Shadow",
    updated: "2026-10-13",
  },
  "M37.2.3.4": {
    status: "READY FOR TESTING",
    why: "BUILT: POST /migration/availability maps each pasted agent's availability to who may see it here from the mapping the person gives, names the agents whose availability nobody mapped and never defaults one, and leaves what the agent may reach to its authority. PROOF ON THE INSTALL: paste two agents with one availability unmapped; the unmapped one is named. The check availability_is_mapped_and_never_defaulted passes.",
    updated: "2026-10-20",
  },
  "M37.2.4.2": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT: POST /migration/learning re-derives each conclusion a person drew from an old memory file through the ordinary tier rules and returns the derivations (learning.re_derive). NOT BUILT: filing each derivation into the memory proposal queue, which would put a proposal in front of a reviewer. NEXT: a call from the route into agent_memory_routes' queue behind its own switch.",
    updated: "2026-10-20",
  },
  "M37.2.4.3": {
    status: "READY FOR TESTING",
    why: "BUILT: the same route refuses, by name and in the package's words, any conclusion that would change who may see what, without stopping the others. PROOF ON THE INSTALL: paste a memory file with a preference and a scope-widening conclusion; only the preference is derived. The check a_conclusion_is_re_derived_and_a_widening_is_refused passes.",
    updated: "2026-10-20",
  },
  "M37.2.4.4": {
    status: "READY FOR TESTING",
    why: "BUILT: the handover carries the sentence that the new system starts without the old one's accumulated learning and why that is the right trade, with the counts of what was carried (none until a migration re-derives something). PROOF ON THE INSTALL: GET /handover shows the learning sentence.",
    updated: "2026-10-20",
  },
  "M37.3.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Every question reaching the answer lane is recorded once by gate/finish.py via ops/question_store.record(Asked); adoption.Asked.machine calls limits.is_automated; GET /report/adoption (report_routes.py) reads it. Tests: test_adoption, test_question_store, test_request_finish. Existing check records human asks only. NEXT: write check naming M37.3.2.4: record one human and one automated-channel Asked (see asked_questions in acceptance_operations_console_3.py), read GET /report/adoption and assert only the human is counted",
    updated: "2026-10-13",
  },
  "M37.4.2.4": {
    status: "READY FOR TESTING",
    why: "BUILT: GET /handover lists the model providers whose key this process holds, each with what it is for, and says in words when it holds none. PROOF ON THE INSTALL: the list matches the providers shown with a key on the Models screen. The check the_subprocessors_are_the_providers_whose_key_is_held passes.",
    updated: "2026-10-20",
  },
  "M37.4.3.3": {
    status: "READY FOR TESTING",
    why: "BUILT: PUT /handover/owners records who owns knowledge, grants and connectors with a way to reach them, behind the handover_pack switch (ships off). PROOF ON THE INSTALL: 1. Turn Record the named owners and the review date on under Features. 2. PUT the three owners; GET /handover lists them and no gap. 3. Leave one out: the gap names it.",
    updated: "2026-10-20",
  },
  "M37.4.3.5": {
    status: "READY FOR TESTING",
    why: "BUILT: PUT /handover/review books the thirty-day review and refuses launch day or past thirty days. PROOF ON THE INSTALL: with the switch on, book a review 30 days after launch and read it back; 31 days is refused.",
    updated: "2026-10-20",
  },
  "M37.5.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/controls.py registry plus ops/schedule.py (imports CONTROLS) give the worker its schedule; tests/invariants/test_no_safety_mechanism_lacks_a_caller.py and tests/unit/test_schedule.py assert every control is scheduled or named orphan. Jobs and Live runs routes list controls (jobs_routes.py, operate_routes.py). NEXT: install check names M37.5.1.2: GET the Jobs route and assert each scheduled control from CONTROLS appears; or close it as Proved-in-ci naming the invariant job",
    updated: "2026-10-13",
  },
  "M37.5.1.3": {
    status: "READY FOR TESTING",
    why: "BUILT (under M17.7.2) and now claimed by its install check: brain.control_not_run_told tells whoever holds the operations alert, once per episode, when a safety mechanism has not run in its window. PROOF ON THE INSTALL: 1. Turn Tell whoever holds the alert when a safety mechanism has not run on under Features (it ships off). 2. The check a_mechanism_that_has_not_run_is_told_to_whoever_holds_the_alert passes on the next run (it says not run until the switch is on). 3. To see it live, stop the worker for longer than a control's window: the holder is told once in the chat tool they last used.",
    updated: "2026-10-20",
  },
  "M37.5.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): tests/invariants/test_no_safety_mechanism_lacks_a_caller.py asserts no control lacks a caller unless the registry says so; backed by controls.orphans(), call_sites(), registry_gaps(). Runs in CI on every push. NEXT: repo-only leaf: close with Proved-in-ci naming the invariants job; optional install check calling controls.registry_gaps() and asserting empty",
    updated: "2026-10-13",
  },
  "M37.5.2.1": {
    status: "READY FOR TESTING",
    why: "BUILT (under M17.7.2): the severity of each control's alert decides who is told, through alerting.route_for: everyone holding the operations alert, and the incident capability's holders too for an alert that wakes somebody, each only if they may open Incidents. PROOF ON THE INSTALL: the same check as M37.5.1.3 passes; a holder who cannot open Incidents is told nothing.",
    updated: "2026-10-20",
  },
  "M37.5.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/controls.py runbook_for(), runbook_gaps() and Control.runbook text give each alert a runbook, checked by alerting.runbook_gaps (tested). Only registry_gaps and handover_lines call them; no route or console page serves a runbook, and no alert carries it. NEXT: serve the per-control runbook on the Jobs screen or in the alert body (jobs_routes.py) via controls.runbook_for; then check",
    updated: "2026-10-13",
  },
  "M37.5.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/alerting.py escalation_path(), supplier_step(), escalation_gaps() build the ladder ending at the supplier contact setting (tested). No caller outside alerting.py and no code reads SUPPLIER_CONTACT_SETTING into a sent escalation. NEXT: wire escalation_path into the overdue alert flow after Runbook.escalate_after, with the supplier contact read from configuration",
    updated: "2026-10-13",
  },
  "M37.5.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): console/spend_view.py cost_review() renders variance(projected, measured) beside post_launch_correction (tested in test_spend_view.py) but only tests call cost_review; no route in report_routes.py or spend routes serves it. NEXT: add cost review to GET /report/spend (report_routes.py), reading the projection from the install record and thirty days of measured spend; then check",
    updated: "2026-10-13",
  },
  "M37.5.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): ops/retune.py post_launch_correction() recomputes the estimator from observed distribution, returning the prior while the window is short (tested). Called only by spend_view.cost_review, which no route serves; the spend_correction control has no runner (schedule_runner.py Runner has needs=). NEXT: give spend_correction a runner assembling estimate vs actual per period and call retune.post_launch_correction; surface via cost review route",
    updated: "2026-10-13",
  },
  "M38.2.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.install_store, memory.turn, ops.memory_store); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); closed PR #299's branch M8/w2-escalation (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M38.2.2.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (automation_schedule_routes, console.automation_schedule, ops.automation_run +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #84's branch M5/model-health-routing-residency (may be replayed already); old backup branch recovery/from-windows-20260928-wt-automation-memory; old backup branch recovery/from-windows-20260928-wt-g2; +1 more",
    updated: "2026-10-06",
  },
  "M38.3.3.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.lark, digest_routes, ops.acceptance_checks_digest +6 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_digest, ops.digest, ops.digest_run); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_digest, ops.digest, ops.digest_run); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.lark, digest_routes, ops.acceptance_checks_digest +7 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.5.4": {
    status: "IN PROGRESS",
    why: "owner-approved 2026-10-14: Built beside Done on /build, the tracker and status.json, and the proof sweep on one complete clean run with a repeat of only the failed or not-run checks; in a pull request (M38/built-and-proven-tracker), not yet on main; proved when the owner's install shows both figures and a repeat completes a clean run",
    updated: "2026-10-14",
  },
  "M39.1.1.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.workspace, ops.acceptance_checks_agent_page); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.1.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_attachment_routes, agents.attachments, audit.ledger +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M39.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_routes, ops.acceptance_checks_agent_page, components/agentWorkspaceState.ts +3 more; NOT wired: pages/Agent.tsx. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +13 more",
    updated: "2026-10-06",
  },
  "M39.1.2.2": {
    status: "OPEN",
    why: "PLAN 2026-10-12: reopened. The strip is claimed to carry Conversations, Automations, People, Knowledge, Memory, Artifacts and Settings, but the console draws only Conversations, Automations, Memory, Artifacts and Settings (AgentDetailPage.tsx SECTION_LABELS), so People and Knowledge are listed by the API and never shown. Knowledge is M39.9.1.1; People has no task of its own beyond this one and stays here. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.workspace, ops.acceptance_checks_agent_page, pages/agents/AgentDetailPage.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +12 more",
    updated: "2026-10-12",
  },
  "M39.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_agent_console, components/AgentAssembly.tsx, components/agentWorkspaceState.ts +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +13 more",
    updated: "2026-10-06",
  },
  "M39.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_link_routes, automation_paused_told, console.workspace +2 more; NOT wired: pages/Agent.tsx. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +12 more",
    updated: "2026-10-06",
  },
  "M39.1.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_routes, ops.acceptance_checks_agent_page, components/agentWorkspaceState.ts +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +14 more",
    updated: "2026-10-06",
  },
  "M39.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_capability_routes, agent_routes, console.workspace_capabilities +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #235's branch M39/w3-agent-workspace-5 (may be replayed already); closed PR #254's branch M39/w3-agent-workspace-6 (may be replayed already); closed PR #257's branch M39/w3-agent-workspace-7 (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M39.2.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_attachment_routes, agents.attachments, console.agent_tabs +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M39.2.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_capability_routes, console.workspace_capabilities, ops.acceptance_agent_console +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #235's branch M39/w3-agent-workspace-5 (may be replayed already); closed PR #254's branch M39/w3-agent-workspace-6 (may be replayed already); closed PR #257's branch M39/w3-agent-workspace-7 (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M39.2.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_capability_routes, console.workspace_capabilities, ops.acceptance_agent_console +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #235's branch M39/w3-agent-workspace-5 (may be replayed already); closed PR #254's branch M39/w3-agent-workspace-6 (may be replayed already); closed PR #257's branch M39/w3-agent-workspace-7 (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M39.2.3.5": {
    status: "READY FOR TESTING",
    why: "PLAN 2026-10-12 (agent Knowledge section, P1): the counts need storage that does not exist. ops.retrieval_event keeps no document, no question and no principal, so a per-item, per-agent count cannot be read from it; a new record of (agent, item, day, count) with no question text is needed, which is a migration (next free number is 0213, the coordinator's) behind a flag; the figure is shown beside each item in the Knowledge section (M39.9.1.1). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_capability_routes, console.agent_tabs); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #235's branch M39/w3-agent-workspace-5 (may be replayed already); closed PR #254's branch M39/w3-agent-workspace-6 (may be replayed already); closed PR #257's branch M39/w3-agent-workspace-7 (may be replayed already); +1 more",
    updated: "2026-10-12",
  },
  "M39.2.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_tabs); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M39/channel-rows, no PR; closed PR #263's branch M39/w3-agent-workspace-8 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M39.2.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_lifecycle_routes, agent_routes, console.agent_tabs +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.2.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_tabs, ops.acceptance_agent_console); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #263's branch M39/w3-agent-workspace-8 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M39.2.4.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_group_routes, channel_routes, channels.adapter +9 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M39/group-install, no PR; closed PR #263's branch M39/w3-agent-workspace-8 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M39.3.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, console.reach_view +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.3.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, console.reach_view +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.3.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, console.reach_view +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.3.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, console.reach_view +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.3.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, console.reach_view +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.4.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_memory_routes, api_routes, console.govern_estate +9 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M39.5.1.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_report +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_store +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.5.1.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_report); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.1": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.6.2.3": {
    status: "READY FOR TESTING",
    why: "PLAN 2026-10-12: partly built (the paused-automation alert #440, the failure notice #431); needs owner decision 172 on whether a pause also stops the agent's questions (recommendation: no). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (automation_paused_told, console.agent_automations, ops.automation_run +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-automation-memory",
    updated: "2026-10-12",
  },
  "M39.8.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_leash_routes, agents.leash_moves, ops.acceptance_workspace +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.8.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_workspace); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M39.8.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_workspace); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.8.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.8.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_attachment_routes, agent_roster, agents.attachments +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M39.8.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_conversation_routes, chat.remember, chat.thread_store +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M40.1.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Real sign-in is identity.oidc/principal_directory via api_routes.asking and sign_in_routes, the same directory the channels use; acceptance_people_signed_in already signs a reserved person through real asking. member.shell.sign_in itself has no caller. Test: test_member_shell. NEXT: write check naming M40.1.1.1 that signs the reserved person in via acceptance_people_signed_in and reads GET /api/v1/me",
    updated: "2026-10-13",
  },
  "M40.1.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): channels.binding mints a code only inside a live sign-in (binding_routes POST /me/channels/{name}/code) so channel and web resolve to one principal row; member.shell.one_principal is uncalled but the route enforces it. Tests: test_member_shell, binding tests. NEXT: write check naming M40.1.1.2: bind a channel via MY_CODE_PATH then assert the binding principal equals the session principal",
    updated: "2026-10-13",
  },
  "M40.1.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Idle and absolute session policy built and enforced (identity/sessions.py SESSION_IDLE, bearer checks sid). Admin sessions list exists (session_routes /govern/sessions). Member's own device list member.shell.devices/end_device has no caller and no /me route; it also takes the in-memory SessionRegistry, not StoredSessions. NEXT: add GET /me/devices and POST /me/devices/end over identity.session_store.StoredSessions with the own-session check from shell.end_device, then a check",
    updated: "2026-10-13",
  },
  "M40.1.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Recovery is Keycloak's: identity/staff_accounts and connectors/sign_in_accounts say Forgot password on the sign-in page; no credential field exists in the product. acceptance_checks_accounts forgot-password check names M40.7.1. member.shell.recovery_handoff has no caller. NEXT: add M40.1.1.4 to the leaves of the forgot-password check in acceptance_checks_accounts.py (or a check asserting the product exposes no password route)",
    updated: "2026-10-13",
  },
  "M40.1.1.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Unit test test_member_shell::test_a_channel_only_person_signs_in_on_the_web_and_holds_the_same_entitlement passes over fakes. Path is real: sign_in_binding.SignInBindings.bind plus the directory resolve the same principal. No install check. NEXT: write check: person with only a channel binding gets a token bound via SignInBindings.bind, calls GET /me, and holds the same reach as the binding path (use acceptance_people_signed_in)",
    updated: "2026-10-13",
  },
  "M40.1.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): The one SPA serves a short own-work menu (console routes ownWork: Ask, My workspace, My approvals, Records, Access requests, Referred to me) and navigation_routes returns a department console with nothing in it to a member. member.shell.member_navigation has no caller. NEXT: write check naming M40.1.2.1: GET /api/v1/navigation as a member-only reader returns no governance section",
    updated: "2026-10-13",
  },
  "M40.1.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Server side: every console route asks console.reads.permitted; member grant opens only member screens (member.shell.MemberScreen refuses governance capabilities; acceptance_checks_governance uses member_screen). serve() has no caller but the per-route check is the enforcement. Test: test_member_shell. NEXT: write check naming M40.1.2.2: as a member-only reader request several /govern/* and /console/* routes and expect the one refusal",
    updated: "2026-10-13",
  },
  "M40.1.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Phone-first approvals page: console/src/pages/approvals/ApprovalCard.tsx and ApprovalsPage.tsx (min-h-11, phone base case), tests console/tests/approvals-phone.test.tsx and phone-width.test.tsx. pages/Approvals.tsx is only the re-export. Only a browser can show it on an install. NEXT: a browser run at 375 px on the install (person-run or headless) naming M40.1.2.3; a Python check can at most assert the served bundle carries the phone rules",
    updated: "2026-10-13",
  },
  "M40.1.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): member.shell.disclosure_line is called by mine_routes (GET /me/workspace can_ask_about) and built from the grants. Test: test_member_shell, test_mine_routes. NEXT: write check naming M40.1.2.4: GET /me/workspace for two readers with different grants and compare can_ask_about",
    updated: "2026-10-13",
  },
  "M40.2.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Count of the month's questions built (mine_routes.questions_asked over ops.question_asked, shown on MyWorkspace). Corrections not separated: the view says CORRECTIONS_ARE_NOT_RECORDED, now stale because POST /threads/{id}/corrections (thread_routes, chat.thread_store.correct) records them. NEXT: count the person's corrections from the thread store in mine_routes and replace MineAskedView.corrections text with a number; member_activity.activity_this_month is the model",
    updated: "2026-10-13",
  },
  "M40.2.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /me/workspace lists agents with provision (provided vs personal) from member_activity.my_agents; MyWorkspace.tsx shows PROVISION_WORDS and how many are the person's own. Test: test_member_activity, test_mine_routes. NEXT: write check naming M40.2.1.2 over GET /me/workspace with one personal and one department agent",
    updated: "2026-10-13",
  },
  "M40.2.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): MyWorkspace learned list (mine_routes MineLearnedView from estate_routes.remembered_about, subject_memory) with Forget/Edit per item (POST /me/memory/forget, /me/memory/edit, /me/learning/undo). No separate count figure but the list length is shown. acceptance for undo exists under M16. NEXT: write check naming M40.2.1.4: form a memory from the person's words, read it on /me/workspace, forget it, read again",
    updated: "2026-10-13",
  },
  "M40.2.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /me/workspace agents rows carry provision, channels (where each runs, offered_channels at the person's run reach) and uses over 30 days (my_agents). Test: test_member_activity. NEXT: write check naming M40.2.2.1 reading GET /me/workspace for an agent used twice",
    updated: "2026-10-13",
  },
  "M40.2.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.open_workspace (calls console.workspace.resolve at the person's own reach) has no caller. MyWorkspace shows agent ids as plain code, no link. The agent page is gated on admin screens. NEXT: wire open_workspace into a /me route (or link each My agents row) so a member lands on the agent's workspace tabs; then a check",
    updated: "2026-10-13",
  },
  "M40.2.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.build_personal_agent (template materialise inside the person's own ceiling) has no caller. Agent building today is agent_builder_routes/agents.creation, which needs the admin: agent-install capability. NEXT: add a member route POST /me/agents from a template instance calling build_personal_agent; needs a store write via agents.install_store",
    updated: "2026-10-13",
  },
  "M40.2.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): PERSONAL audience is enforced: agents.model.visible_agent_ids narrows every agent route; agents.creation makes a new agent visible to its maker only; member_activity.personal_audience offers nothing wider; publication to department/company is the explicit act in agent_lifecycle_routes. Tests: test_member_activity, agent tests. NEXT: write check naming M40.2.2.4: create an agent as person A, list agents as B (absent), publish to department, B sees it",
    updated: "2026-10-13",
  },
  "M40.2.2.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.request_agent and AgentRequest are built (routes to the agent's department) with no caller and no store. access_request_routes only handles field and department requests to the data steward, not agents. NEXT: add POST /me/agents/{id}/request calling request_agent, store the request and deliver it as a notice to the department admin (reuse access_request store pattern)",
    updated: "2026-10-13",
  },
  "M40.3.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /knowledge/items (knowledge_lifecycle_routes.looked_after) lists the person's own documents with level, review date, due flag, verification and promotion state; MyWorkspace shows knowledge rows. Tests: knowledge lifecycle tests. member_library.my_library has no caller but the route does the job. NEXT: write check naming M40.3.1.1: upload as person A, read GET /knowledge/items, assert review date and verification fields",
    updated: "2026-10-13",
  },
  "M40.3.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Upload (queue_upload, add_link), replace (POST .../versions) and verify-with-next-review exist. Missing: retire (archive not built, needs a migration per knowledge_lifecycle_routes) and a review cycle at upload time (upload takes no review date). member_library.upload/replace/retire have no caller. NEXT: add a review_by field to the upload request, and a retire route over a know.supersede-style function with its migration",
    updated: "2026-10-13",
  },
  "M40.3.1.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): member_library.authored_usage is built but uncalled and no source of per-item read counts exists: knowledge.retrieval_log deliberately stores no reference, and mine_routes says nothing counts reads (VERIFICATION_AND_USE_ARE_NOT_RECORDED). NEXT: decide where per-item read counts live (item-level counter conflicts with RetrievalEvent no-reference rule); then wire authored_usage to the knowledge card",
    updated: "2026-10-13",
  },
  "M40.3.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): POST /knowledge/items/{id}/promotion (knowledge_lifecycle_routes) calls member_library.request_promotion and promotion_tier; the request waits on the Approvals screen at the blast-radius tier. acceptance_checks_lifecycle already imports member_library for related leaves. NEXT: write check naming M40.3.1.4: verify then request promotion, assert it appears on the approvals queue at tier three",
    updated: "2026-10-13",
  },
  "M40.3.1.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): knowledge_lifecycle_routes Authority.may_see and know.item row-level security decide every list; mine_routes narrows by is_own plus items_stewarded_by_the_session. Tests exist; member_library.reachable_own_items has no caller. NEXT: write check naming M40.3.1.5: a person in a department with a restricted row does not see it in GET /knowledge/items",
    updated: "2026-10-13",
  },
  "M40.3.2.1": {
    status: "READY FOR TESTING",
    why: "built (M40/member-personal-skills): GET /me/skills lists a person's own skills with where each came from (written here, a repository, an address), its version, its review state and a sentence saying what it can do now, in a My skills card on My workspace; nobody else's skills are listed and nothing is counted. Behind the personal_skills switch for adding and offering; listing is never behind it. PRIOR WORK (2026-10-13 triage): member_library.my_skills was built and uncalled; it is now the list. PROVE ON THE INSTALL: (1) as an administrator open Features and switch on 'Let a person add skills of their own and offer them to the department'; (2) as a member open My workspace, find My skills, choose Write or paste it here, paste a SKILL.md and press Add this skill; (3) the skill is listed with its version, 'written here' and the sentence 'Only you can see this'; (4) as a colleague open My workspace: your skill is not there; (5) as an administrator open Skills: it is not in the library or the queue.",
    updated: "2026-10-20",
  },
  "M40.3.2.2": {
    status: "READY FOR TESTING",
    why: "built (M40/member-personal-skills): a member adds a skill of their own by pasting or writing a SKILL.md (POST /me/skills), or brings one from a repository at a full commit or from an address the install's host list admits (POST /me/skills/imports), through the same fetcher and parser the administrator's import uses, and it is stored as theirs alone, undecided. A person holds at most 25 skills they have not offered. PRIOR WORK (2026-10-13 triage): the administrator's import routes existed behind the skill authority; member_library.add_skill had no member caller and now has. PROVE ON THE INSTALL (switch on as for M40.3.2.1): (1) paste a SKILL.md in My skills and add it; (2) choose Bring it from an address, give an https address on GitHub's raw host holding a SKILL.md, and add it: it is listed 'from an address'; (3) choose Bring it from a repository, give owner/name and the full commit: it is listed 'from a repository'; (4) paste the same file again: it is answered with the skill you already have; (5) with the switch off the form is replaced by a sentence saying so and nothing is added.",
    updated: "2026-10-20",
  },
  "M40.3.2.3": {
    status: "READY FOR TESTING",
    why: "built (M40/member-personal-skills): POST /me/skills/{digest}/offer, from an Offer to the department button that asks first, makes the person's own skill appear in the department's library and review queue, undecided, once; a colleague pressing it for a skill that is not theirs is answered exactly as for one nobody made. Nothing here approves anything. PRIOR WORK (2026-10-13 triage): member_library.submit_for_review had no caller and now has. PROVE ON THE INSTALL (switch on as for M40.3.2.1): (1) in My skills press Offer to the department on a skill and confirm; (2) the skill now reads 'Offered to the department'; (3) as an administrator open Skills: it is in the library and the queue, undecided; (4) as a second member, press nothing: their My skills does not list it.",
    updated: "2026-10-20",
  },
  "M40.3.2.4": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT (M40/member-personal-skills): a skill nobody offered is in no reading of the library (brain.ops.skill_store.library_of and one_skill carry one clause), so no administrator can list, review or assign it and no run can pin it; offered, it still needs a named person to approve the exact bytes before any agent can carry it. NOT BUILT, AND A QUESTION FOR THE OWNER: whether a person may run their own skill on their own personal agent BEFORE a reviewer has approved it (the leaf's words 'usable only by this person's own agents until approved'); today it is usable by no agent until approved, which is stronger than the leaf and narrower than it reads. member_library.attach_refusals stays unwired for that reason: its first refusal already forbids pinning an unapproved skill anywhere. The install check does not name this leaf for the same reason.",
    updated: "2026-10-20",
  },
  "M40.3.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Artifacts are listed per agent (agent_artifact_routes GET artifacts, latest, download) and estate-wide for admins (artifact_routes /govern/artifacts). member_library.produced_for_me (everything by any agent for this person) has no caller and no route. NEXT: add GET /me/artifacts calling produced_for_me over agent.artifact rows with caller_id = the person; add to MyWorkspace",
    updated: "2026-10-13",
  },
  "M40.3.3.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_library.share/open_share/Share built, no caller, no table for a share row (shape has no entitlement by design). NEXT: add a share table plus POST /me/artifacts/{id}/share calling share and GET using open_share; needs a migration number",
    updated: "2026-10-13",
  },
  "M40.4.1.1": {
    status: "READY FOR TESTING",
    why: "built: GET /me/workspace now calls member_activity.learned_about_me, so each learned line carries the evidence that produced it in the weekly message's words (mine_routes.evidence_by_memory over learning_told.SIGNAL_WORDS), a line the person wrote says so, and an inferred line with no record says no record was kept; MyWorkspace draws the evidence list. Tests: tests/unit/test_mine_routes.py, console/tests/my-workspace-page.test.tsx. To prove on the install: sign in, ask the same question twice in other words so a preference is inferred, open My workspace, and read the evidence under the inferred line; it must name what was noticed and nothing of any conversation.",
    updated: "2026-10-20",
  },
  "M40.4.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): One-click undo per item built and wired: POST /me/memory/forget and /me/learning/undo (MyWorkspace Forget, digest undo link). Undo-all: member_activity.undo_all exists but has no caller (govern_estate lists undo_all as a refused bulk word for the console). NEXT: add POST /me/memory/forget-all over StoredMemoryRecords.undo for the person's own memories and an Undo all button",
    updated: "2026-10-13",
  },
  "M40.4.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.opt_out/LearningOptOut built (states the cost), no caller, no stored flag, and the memory formation path (chat/remember, memory.turn) reads no opt-out. NEXT: store a per-person opt-out (ops.setting or table), check it in memory formation, expose POST /me/learning/opt-out",
    updated: "2026-10-13",
  },
  "M40.4.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.what_is_stored/StoredAboutMe built, no caller. thread_routes export (export_my_history) covers conversations only; /me/workspace shows five cards but not 'what is stored and where'. NEXT: add GET /me/stored calling what_is_stored and a card on MyWorkspace",
    updated: "2026-10-13",
  },
  "M40.4.2.3": {
    status: "READY FOR TESTING",
    why: "built (M40/member-deletion-from-main, behind the switch member_deletion_requests, which ships off; migration 0273 adds ops.deletion_request): a person can ask, from My workspace, for their data to be deleted. The page first lists what a deletion reaches, what only time removes and what is kept on purpose (member_activity.route over ops.retention.STORES); the ask is a record, and nothing is deleted. People who asked are listed above the erasure form on the Retention screen for whoever holds the erasure authority over everything, and filing the erasure closes the ask. Rejected: filing straight into the erasure queue as the person, which makes a mis-click an irreversible erasure; whether an install wants that is the owner's. PRIOR WORK (2026-10-13 triage): member_activity.request_deletion and route were built and uncalled. PROVE ON THE INSTALL: (1) as an administrator open Features and switch on 'Let a person ask, from their own page, for their data to be deleted'; (2) as a member open My workspace, press 'Ask for my data to be deleted', read the three lists and confirm; (3) nothing about the member changes and they can still sign in; (4) as the administrator holding the erasure authority open Retention: the member's reference is listed under 'People who asked to be deleted'; (5) file the erasure for that reference: the ask leaves the list.",
    updated: "2026-10-21",
  },
  "M40.4.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Writer side is wired and checked: ops.sensitive_read_store.SensitiveReadRecorder writes record_read ledger entries (acceptance_audit.py checks them). Member page: member_activity.who_read_my_record has no caller; GET /audit shows own entries only on the admin audit screen. NEXT: add GET /me/reads calling who_read_my_record over AuditView and a MyWorkspace card",
    updated: "2026-10-13",
  },
  "M40.5.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): GET /me/accounts and POST /me/accounts/{connector}/consent (connector_routes) give per-source, per-person OAuth consent into the person's own vault slot; acceptance_checks_oauth exercises two persons. member.connections.connect has no caller. NEXT: write check naming M40.5.1.1 or add it to the person-consent check in acceptance_checks_oauth.py",
    updated: "2026-10-13",
  },
  "M40.5.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): connector_routes MyAccountsView.told = CONNECTING_YOUR_OWN_ACCOUNT (never widens what you can see) and mine_routes ACCOUNTS_ARE_NOT_READ_HERE; reach is independent of connections by construction. Test: test_member_connections. NEXT: write check naming M40.5.1.2: GET /me/accounts text present and reach hash unchanged after a consent",
    updated: "2026-10-13",
  },
  "M40.5.1.3": {
    status: "READY FOR TESTING",
    why: "built: POST /me/accounts/{connector}/disconnect (member_accounts_routes) revokes at the vendor then removes the person's slot through ops/person_token_revoker.VaultTokenRevoker, in the order member.connections.disconnect requires; Google Workspace now declares its revocation endpoint; the application vault policy gains delete on a person's own slot only. Check: a_member_disconnects_their_account_and_the_vendor_is_told_first in ops/acceptance_checks_member_accounts.py, over a recording vendor and vault. NOT provable in CI: that the vendor stops honouring the token, and that the install's vault holds the new policy line (the release applies it). To prove on the install: after the release, connect your own Google account from My workspace, press Disconnect my Google account and confirm; the card must show Not connected, and at your Google account's third-party access page the install must no longer be listed. 2026-10-21 THE INSTALL CHECK FAILED ON THE OWNER'S INSTALL (the check stopped on OperationalError, no traceback readable). Not proved: do not read this leaf as working until the install shows the check passing. The check's whole-database token scan is the likeliest cause (a statement timeout over large tables) and is replaced by a search of the tables a disconnect or a keep writes; each database step now fails with its own sentence, so the next failure names the step. 2026-10-22 THE RUN AT 040ce92 FAILED IT AGAIN, naming the search step itself, so the seven-table text scan still outran the statement timeout (the ledger, telemetry and trace tables are large). The search now reads each table by its own time column from an hour before the run started (an index range, never a cast of a whole table) and the settings table, which has no time column and is a handful of rows, on its own; the two have their own failure sentences. Not proved until the install shows the check passing.",
    updated: "2026-10-22",
  },
  "M40.5.1.4": {
    status: "READY FOR TESTING",
    why: "built: GET /me/accounts lists a connected source that names the person's own department (and that each person does not consent to) with provenance department and no disconnect control, through member.connections.inherited; a person in another department is shown nothing. A department connection is defined here as a connected source naming a department the person holds a grant scoped to exactly (no separate department-connection object exists). Check: a_departments_connection_is_inherited_and_not_detachable in ops/acceptance_checks_member_accounts.py. To prove on the install: as a member of a department that has a source connected, open My workspace and read the Connected accounts card; the source must show as provided by the department with no button, and a member of another department must not see it.",
    updated: "2026-10-20",
  },
  "M40.5.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): GET /me/channels (binding_routes, MyChannels.tsx) lists channels switched on and bound, with bound_at. 'Primary' is not modelled: member.connections.reachability/ChannelPreference/reachable_on are uncalled and nothing stores a primary. NEXT: store a primary channel per person and surface it through reachability in my_channels view",
    updated: "2026-10-13",
  },
  "M40.5.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.ChannelPreference/wants built, no caller, no store; ops/notices.py rejects per-person preference and keeps one install-wide switch per notice kind. NEXT: add a preference store and make ops/notices senders ask wants() per person",
    updated: "2026-10-13",
  },
  "M40.5.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.channels_that_may_approve built, no caller. approval_cards sends Lark cards to every addressed binding, switched install-wide by INSTALL_LARK_CARD_APPROVALS; there is no per-approver choice. NEXT: store the approver's console-or-Lark choice and have approval_cards.send_raised honour it via channels_that_may_approve",
    updated: "2026-10-13",
  },
  "M40.5.2.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.QuietHours/may_deliver built, no caller; nothing outside the module mentions quiet hours (tell_later, learning_told, automation notices ignore them). NEXT: store quiet hours per person and call may_deliver in tell_later.tell for digests and automation notices",
    updated: "2026-10-13",
  },
  "M40.6.1.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Approvals screen does it: approval_routes GET /approvals (cards with the request rendered by gate.approval_request.render_request at the approver's reach), console Approvals page, console.approvals.card. member.approvals has no caller (effect_sentence is used by agent_profile). Tests: test_approval_routes. NEXT: write check naming M40.6.1.1 over GET /approvals for a seeded suspension (acceptance_checks_console_approvals has the setup)",
    updated: "2026-10-13",
  },
  "M40.6.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Approve and reject written to the ledger via approval_routes take_decision and audit approval entries. Amend is explicitly not offered (AMENDING_WAITS_FOR_A_REPLACEMENT_RAISED_THROUGH_THE_GATE in approval_routes). NEXT: build amend as reject plus a replacement raised through the gate, then a check; until then a check can cover approve and reject only",
    updated: "2026-10-13",
  },
  "M40.6.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Lapse is built and shown: gate.leash DEFAULT_APPROVAL_WINDOW, approval_routes lists soonest-to-lapse first, ApprovalCard shows 'Lapses'; a lapsed row is refused by take_decision. Wording of the stated default of doing nothing on the card not verified. NEXT: write check naming M40.6.1.3: raise an approval with a short window, advance, assert it lapses with no action taken; confirm the card says nothing happens",
    updated: "2026-10-13",
  },
  "M40.6.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): One decision path: approval_cards uses approval_routes.take_decision under a claim on the callback id, so a press after a console decision (or the reverse) is refused. acceptance_checks_cards (M33.8.1) exercises both surfaces on one approval. NEXT: add M40.6.1.4 to the leaves of the both-surfaces check in acceptance_checks_cards.py",
    updated: "2026-10-13",
  },
  "M41.2.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.starter, ops.starter_store); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w05c",
    updated: "2026-10-06",
  },
  "M42.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): deployment/variables.py:template_for, parse_env and variables_repository_gaps implement one file per install and refuse a fork-shaped repository; test_deployment_variables.py. Nothing calls them outside tests (docs/install/checklist.md only names one); the private repository itself is the owner's. NEXT: Wire variables_repository_gaps into a CI job template for the variables repository (or a CLI command) and publish template_for output in the release; the repository is a process step.",
    updated: "2026-10-13",
  },
  "M42.1.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): install.sh step 12 mints POSTGRES_PASSWORD, APP_ROLE_PASSWORD and BRAIN_SETUP_SECRET with openssl on the client server (wired). variables.py:shared_secrets and unminted_secrets refuse shared or weak values but nothing calls them outside tests. NEXT: Run unminted_secrets over the install's own environment in an install check and expose shared_secrets as a command for the variables repository.",
    updated: "2026-10-13",
  },
  "M42.1.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): install.sh steps 7 and 10 fetch one archive and write APP_IMAGE=<repo>:<release tag>; release.yml verifies the signed CI digest and tags it (no rebuild); installer.rebuild_gaps and release_pinning_gaps hold compose files to it in test_deployment_installer.py. NEXT: Check that reads /opt/brain/.env APP_IMAGE is a tag of the product image and equals the running container's image reference.",
    updated: "2026-10-13",
  },
  "M42.1.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): installer.release_pinning_gaps and release.update_plan pin APP_IMAGE to a named tag, refuse 'latest' (install.sh line 61), and update.sh/rollback.sh re-pin per install; test_deployment_installer.py, test_deployment_release.py. The pin lives in that install's .env. NEXT: Check that the pin is not 'latest' and that the pinned tag is one the release feed lists.",
    updated: "2026-10-13",
  },
  "M42.2.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): docs/install/install.md (fourteen pages in docs/install) is held to the installer plan by ops/install_docs.py:step_gaps, tested in test_install_docs.py; docs_routes.py serves docs; independence sweeps keep other companies' details out. NEXT: Write a check that reads the install's served guide and calls step_gaps against the installer PLAN; a clean-server walk-through is M42.4.7.",
    updated: "2026-10-13",
  },
  "M42.2.8": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): docs/install/operations.md, checklist.md and restore-drill.md describe backup, monitoring, logging and health checks; install_docs.checklist_gaps, scheduled_job_gaps and drill_procedure_gaps hold them to code (test_install_docs.py). Backup itself is not auto-scheduled (see M42.3.5). NEXT: Check naming M42.2.8 that runs the doc-gap functions on the served pages; fix scheduling separately in M42.7.4.",
    updated: "2026-10-13",
  },
  "M42.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/install/install.sh is generated by deployment/install_script.py:render_install from installer.PLAN; every step tests for done and prints 'already done, skipping'; test_install_script.py and test_deployment_installer.py hold it. NEXT: Install-time proof is running the script twice on a server; a check can read the installer markers (APP_IMAGE, starter.furnished) and compare the shipped script to render_install.",
    updated: "2026-10-13",
  },
  "M42.3.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): deployment/variables.py:template_for emits a documented template with every credential-shaped name blank and refuses undeclared names; tested. No caller outside tests: install.sh writes .env from its own template step without it. NEXT: Have install.sh step 9 (write the environment file) or the archive generate .env.example through template_for, then a check compares the shipped template to its output.",
    updated: "2026-10-13",
  },
  "M42.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): deployment/database.py has create, migrate and seed with a CLI (python -m brain.deployment.database), documented in the guide and checked by install_docs.database_command_gaps. install.sh does not call it (compose creates the database) and seed loads the demo company. NEXT: Decide the install's path (call database migrate from the installer, or retire the claim), and write a check that the CLI's migrate reports the head the install runs.",
    updated: "2026-10-13",
  },
  "M42.3.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): installer.py:health_report prints per-service healthcheck state and each component's ready_when text; no __main__ or script calls it (only docs name it), and install.sh step 23 polls /health/ready only. NEXT: Add a python -m brain.deployment.installer health command (or ops/install/health.sh) calling health_report and name it in docs/install/operations.md.",
    updated: "2026-10-13",
  },
  "M42.3.6": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/update/update.sh and rollback.sh are generated by release.render_update/render_rollback from update_plan and rollback_plan, carried in the archive (ops/update rule), tested in test_deployment_release.py; update-and-rollback.md says never run on a server. NEXT: Check reads that the pin variable in .env is a release tag and the scripts' drift test passes; the live run belongs to M42.2.10.",
    updated: "2026-10-13",
  },
  "M42.3.8": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): release.yml publishes v0.1.0 (gh release list, 2026-09-29) with notes from release.notes_from_tag_message stating the database change (DatabaseChange) and Urgency; test_deployment_release.py covers it. NEXT: Check that reads the install's release feed entry for the running tag and asserts notes with a database answer and an urgency.",
    updated: "2026-10-13",
  },
  "M42.3.9": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/version_view.py, deployment/release_feed.py (ReleaseWatch) and install_routes.py serve the running version and newest release; pages Updates.tsx and install/UpdatesPage.tsx draw it; tests test_install_routes.py, test_release_feed.py, test_version_view.py, console/tests/install-pages.test.tsx. NEXT: Write a check naming M42.3.9 that reads the updates route and requires a running version and a newer-release verdict (switched-off counts as an answer).",
    updated: "2026-10-13",
  },
  "M42.5.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/install/install.sh (29 steps: machine checks, Docker, archive, secrets, vault, pull, database, start, ready wait, furnish) is generated by deployment/install_script.py:render_install, held by test_install_script.py, published beside the archive by release.yml. NEXT: Install-time proof is M42.5.17; a check can compare the shipped script to render_install output.",
    updated: "2026-10-13",
  },
  "M42.5.10": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): setup_wizard.py:review builds a ReviewLine per setting and apply_install writes everything at once through POST /setup/appointment (setup_routes.py); console FirstRun.tsx draws the review screen; tests test_setup_wizard.py, test_setup_routes.py, test_install_settings.py. NEXT: A check cannot run it after first run (the wizard is closed); prove it on the fresh-install walk, or check review() over a sample draft.",
    updated: "2026-10-13",
  },
  "M42.5.11": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): setup_wizard.py:assert_open refuses once an administrator exists (WizardClosedError) and setup_routes.py answers an indistinguishable 404; tests in test_setup_wizard.py and test_setup_routes.py. NEXT: Write a check that, on an install with an administrator, posts to /setup/appointment and requires the same 404 body as an unknown path.",
    updated: "2026-10-13",
  },
  "M42.5.12": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): setup_wizard.py:write_draft, read_draft, discard_draft and draft_from persist a draft to a file but nothing outside setup_wizard.py calls them; setup_routes.py says resuming from setup-draft.json is not served, and console FirstRun.tsx keeps answers in page memory only. NEXT: Call write_draft from setup_routes per answered step, read it back on page load, and have FirstRun.tsx load the draft before step 1.",
    updated: "2026-10-13",
  },
  "M42.5.13": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): setup_wizard.py:problems_with validates every step (checks, _provider_rule, _staff_source_rule) and setup_routes returns a 422 by step, field and catalogue key; brain.locale.MESSAGES supplies the sentences; tests test_setup_wizard.py, console/tests/first-run.test.tsx. NEXT: A check on a finished install cannot post answers; prove by the fresh-install walk or by calling problems_with on invalid sample answers.",
    updated: "2026-10-13",
  },
  "M42.5.14": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): sign_in_routes.py POST /setup/sign-in (FINISH_PATH) binds the first administrator and signs them in; FirstRun.tsx lands in the console; vault_setup.py and install_settings.py leave nothing to configure; tests test_sign_in_routes.py, test_console_served.py, test_vault_setup.py, first-run.test.tsx. NEXT: Prove on the fresh-install walk; a check can assert that after first run the ask route answers (see M42.6.3).",
    updated: "2026-10-13",
  },
  "M42.5.15": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): install.sh prints 'step N of 29: <name>' with 'already done, skipping' and per-step fail messages naming what to do (generated from installer.PLAN via say() and fail()); tests in test_deployment_installer.py and test_install_script.py. NEXT: Check reads the shipped script and requires every step to carry a message and a failure text; a live run is M42.5.17.",
    updated: "2026-10-13",
  },
  "M42.5.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): install.sh step 12 mints POSTGRES_PASSWORD, APP_ROLE_PASSWORD and BRAIN_SETUP_SECRET with openssl rand on the server and the vault steps mint tokens; variables.is_secret_name feeds installer.value_leaks_in; test_deployment_variables.py. release.archive_gaps checks the archive for client values. NEXT: Check running variables.unminted_secrets over the install's own .env (needs wiring, see M42.1.2).",
    updated: "2026-10-13",
  },
  "M42.5.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): install.sh step 28 prints the setup code once; deployment/app_environment.py and firstrun.py hold its digest; setup_wizard.assert_unlocked and claim require it on every screen; tests test_app_environment.py and test_setup_wizard.py. NEXT: Cannot be shown after first run; prove on the fresh-install walk, or a check over assert_unlocked with a wrong code.",
    updated: "2026-10-13",
  },
  "M42.5.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/src/pages/FirstRun.tsx draws 'Step N of TOTAL_STEPS' and a Back button on each screen; setup_wizard.py:progress_for is the Python counterpart; console/tests/first-run.test.tsx reads the screens back from setup_wizard.py. NEXT: Prove on the fresh-install walk (the wizard is closed afterwards); the console test already covers the structure.",
    updated: "2026-10-13",
  },
  "M42.5.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): setup_wizard.py company step collects company_name, product_name, web_address and logo_url (an address, not an upload) into INSTALL_* settings; its docstring says 'M42.5.5 says upload' and substitutes an address. No upload route exists and no needs-rupash question records the narrowing. NEXT: Either build a logo upload (object store plus a served path) or add a docs/needs-rupash.md question and name its number in register row CON-8 or OWN3-1.",
    updated: "2026-10-13",
  },
  "M42.5.7": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): connectors/staff_directories.py and setup_staff_routes.py (registered in routers.py) offer Google Workspace, Microsoft, Lark or a spreadsheet, sign in and pull the list; console StaffListCheck.tsx and setup/staffList.ts; tests test_staff_directories.py, test_setup_staff_routes.py, first-run-staff-list.test.tsx. NEXT: A check can call the staff-source listing for the configured source; the sign-in half belongs to the fresh-install walk.",
    updated: "2026-10-13",
  },
  "M42.5.8": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): setup_wizard.py model_provider step takes a provider and key (key held in the vault) via _provider_rule; MODEL_PROFILES still lists 'local', but needs-rupash 80 decided hosted providers only (no local-only profile wanted); test_setup_wizard.py. NEXT: Check reads that the install's provider slot is held in the vault; the 'local-only' half is decided out by item 80 (register REQ-42 records it).",
    updated: "2026-10-13",
  },
  "M42.5.9": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): wizard connections step (slug list) plus console ConnectSourcesStep.tsx and ConnectSource.tsx connect sources from first run, and the Connectors pages repeat it later (connector_routes.py, ops/connector_store.py); tests console/tests/first-run.test.tsx. NEXT: Check naming M42.5.9 that lists the connector catalogue and one connection on a furnished install via connector_routes.",
    updated: "2026-10-13",
  },
  "M42.6.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): setup_routes.py POST /setup/appointment saves answers into ops.setting (Appointer.appoint); brain.install.value_of resolves them ahead of the environment; the provider key goes to the vault (vault_setup.py); tests test_setup_routes.py, test_vault_setup.py, test_vault_renewal.py. NEXT: Check that reads ops.setting for the install settings the wizard collected and that INSTALL_* values resolve without environment entries.",
    updated: "2026-10-13",
  },
  "M42.6.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/src/pages/Ask.tsx and askQuery.ts post to POST /api/v1/answer (api_routes.py:2651) and show the answer; tests console/tests/ask-page.test.tsx; the answer path is the real gate. NEXT: Write a check naming M42.6.3 that posts a question as a seeded person through /api/v1/answer and requires an answer or a worded refusal (an unreachable model server is an honest 'not run').",
    updated: "2026-10-13",
  },
  "M42.6.4": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/skill_library.py, ops/skill_store.py, skill_routes.py, tables/skill.py and pages skills/SkillForms.tsx, skillsQuery.ts add a skill, show what it reaches and assign it to an agent; tests test_skill_library.py, test_skill_routes.py, test_skill_store.py, skills-page.test.tsx. NEXT: A skill console check exists in ops/acceptance_skill_console.py; add the leaf id there if it proves add and assign, or write one naming M42.6.4.",
    updated: "2026-10-13",
  },
  "M42.6.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): connector_routes.py, ops/connector_admin.py, connector_store.py, ops/credentials.py and openbao.py hold the credential in the vault, console/connector_trust.py shows what it reads, connectors/SourceFlow.tsx draws it; tests test_connector_routes.py, test_connector_trust.py and others. NEXT: Name M42.6.5 on the connector install checks that connect, vault-hold and show trust (acceptance_checks_connectors*.py), or write one that does all three.",
    updated: "2026-10-13",
  },
  "M42.6.6": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops/install/windows/install-from-windows.ps1 and .cmd are generated and held by deployment/windows_helper.py (asks five questions, runs the documented command over ssh.exe); release.yml carries them; test_windows_helper.py. NEXT: Static check that the shipped helper equals windows_helper output; the double-click run is a person-run step on Windows.",
    updated: "2026-10-13",
  },
  "M5.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_model_routes, agent_routes, agents.model +10 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M13/wire-agent-upgrade, no PR; +24 more",
    updated: "2026-10-06",
  },
  "M6.2.2": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (cache, gate.caches); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, cache, gate.caches +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, cache, gate.caches +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, cache, gate.caches +2 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M6.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, app, gate.fast_lane +14 more; NOT wired: pages/Rules.route.tsx. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M7.1.3": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install, knowledge.ingest, knowledge.scanners +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #129's branch M7/links-scanning-queue (may be replayed already); closed PR #217's branch M7/w2-knowledge-3 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M7.1.4": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.uploads, ops.acceptance_ingest); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #217's branch M7/w2-knowledge-3 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); closed PR #232's branch M7/w2-knowledge-5 (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M7.1.5": {
    status: "READY FOR TESTING",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.ingest, knowledge.ingest_queue, knowledge.uploads +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #129's branch M7/links-scanning-queue (may be replayed already); closed PR #160's branch M27/console-knowledge (may be replayed already); closed PR #164's branch M27/console-knowledge-r2 (may be replayed already); +4 more",
    updated: "2026-10-06",
  },
  "M7.7.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.10.1": {
    status: "READY FOR TESTING",
    why: "P1. Partly built: agents/model.py has Visibility (GLOBAL, DEPARTMENT, PERSONAL) with an owner_id, and the agent page shows its audience. What is missing is the kind named as a choice at creation and on the page. REUSE agents.model.AgentAudience, agents.creation, agent_routes.",
    updated: "2026-10-12",
  },
  "M39.10.2": {
    status: "READY FOR TESTING",
    why: "P1. Partly built: agents/creation.py makes a personal agent for its maker (AgentAudience PERSONAL, owner_id) and brain.member_activity.build_personal_agent materialises one. What is missing is the builder's own flow for a person to make one and the capability rule that only an administrator may make a team agent. REUSE agents.creation, agents.authoring, member_activity.",
    updated: "2026-10-12",
  },
  "M39.10.3": {
    status: "READY FOR TESTING",
    why: "built (M39/personal-agent-oversight-and-workspace): a personal agent is listed, opened and used by its owner alone, and a reader who holds the audit capability for agents (read:audit.agent, in the scope their grant carries) is told on the Agents screen, under Personal agents under oversight, that another person's personal agent exists, whose it is and whether it runs, and is offered nothing: it is not on their roster and its page is refused as for an agent never made. No count anywhere, and the same empty answer for every other reader. Behind the switch Show personal agents to people who hold the audit capability (off). Every place that lists agents is held to the audience by a test that walks the source; a leaver's personal agent is no longer offered to whoever may adopt agents. To prove it on the install: switch the feature on, make a personal agent as one person, open Agents as a person who holds the audit capability for agents, and see it named there and not in the roster; the install check an_auditor_is_told_of_a_personal_agent_and_may_not_use_it does this with reserved people. Not seen by this task: the Usage and Spend breakdowns by agent, which name every agent to a reader of those screens, personal ones included (a question for the owner).",
    updated: "2026-10-14",
  },
  "M39.10.4": {
    status: "READY FOR TESTING",
    why: "built (M39/personal-agent-oversight-and-workspace): the owner of a personal agent attaches their own Google account to it from the agent's Profile (Your own Google account, confirmed), and takes it off the same way; the agent then reads that person's own mail, calendar and documents with their own consent and token, for them alone. A colleague, an administrator and any other agent cannot attach or ask for it (answered as for an agent never made), and a team agent never carries one however it is written: the read is now an entity the Google connector provides, so an agent that does not name the connector is not left holding it. Behind the switch Let a person attach their own Google account to their personal agent (off). The real Google sign-in is the owner's step on needs item 173: until then the install check a_persons_own_google_account_is_on_their_agent_for_them_alone passes against recorded Google answers for made-up people and the task is held. To prove it on the install after item 173: connect Google Workspace, connect your own account on My workspace, switch the feature on, attach it on your personal agent, ask it about your mail, and see a colleague get nothing of yours from any agent.",
    updated: "2026-10-14",
  },
  "M39.10.5": {
    status: "OPEN",
    why: "P2. DEPENDS on the owner's answer to needs item 189 (recommended C, built as A first). PARTLY BUILT (M39/personal-agent-oversight-and-workspace), the part that holds under every answer: a team agent can never carry a person's own Google account, however it is written or attached (agents.model.bound_connectors and the read's entity), and the install check asserts a department's agent naming Workspace is handed nothing. NOT BUILT, waiting on item 189: a shared mailbox an administrator connects for a team (options A and C), and a person's own mail reaching a team agent inside that person's private conversation only, never a room, memory or knowledge item (options B and C).",
    updated: "2026-10-14",
  },
  "M39.10.6": {
    status: "READY FOR TESTING",
    why: "P1. Install check for the first, second and third leaves, with reserved people; held if it uses a made-up mailbox.",
    updated: "2026-10-12",
  },
  "M39.10.7": {
    status: "OPEN",
    why: "P2. Browser proof of the create flow's kind choice.",
    updated: "2026-10-12",
  },
  "M39.9.1.1": {
    status: "READY FOR TESTING",
    why: "P1, the core of the Knowledge requirement. Today the API lists Knowledge as one of seven workspace tabs (console/workspace.Tab.KNOWLEDGE) and the Profile draws a read-only card of what the agent's rule reaches (AgentCapabilities.tsx KnowledgeCard: M39.2.3.1, .3, .4), but the console's tab strip draws only Conversations, Automations, Memory, Artifacts and Settings, so there is no Knowledge section and no list of items. REUSE: the workspace tab read, brain.knowledge.item (retrievable, badge), console/agent_tabs.KnowledgeScope. REMAINING: a paged read of the items this agent draws on at the reader's reach, and AgentKnowledge.tsx with its empty state. M39.1.2.2 is reopened for the missing tabs.",
    updated: "2026-10-12",
  },
  "M39.9.1.2": {
    status: "READY FOR TESTING",
    why: "P1. DEPENDS on M39.9.1.1 and on the owner's answer to needs item 176 (where an item added from an agent lives; built as recommended, company layer). REUSE: brain.knowledge.uploads.receive_upload, knowledge_intake_routes (POST /knowledge/uploads and the queued door), console/agent_tabs.plan_addition (its `reached` answer). REMAINING: an agent-scoped add route calling the door and returning plan_addition's answer, and the form. Today the card's 'Add a document or a link' only links away to /knowledge. M39.2.3.2 is reopened.",
    updated: "2026-10-12",
  },
  "M39.9.1.3": {
    status: "READY FOR TESTING",
    why: "P1. DEPENDS on M39.9.1.1 and item 176. REUSE: brain.knowledge.uploads.receive_link, POST /knowledge/links (fetched once, the company's own copy), brain.tools.fetch (address checks on every redirect), plan_addition. REMAINING: the agent-scoped add route and form, shared with M39.9.1.2.",
    updated: "2026-10-12",
  },
  "M39.9.1.4": {
    status: "READY FOR TESTING",
    why: "P1. DEPENDS on M39.9.1.2 and M39.9.1.3. REUSE: the 'Widen what it draws on, through a draft' action already on the Knowledge card (onWiden), agents/authoring drafts. REMAINING: name the unreached item beside it and make the one next step a press, never a silent change to every agent (ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT).",
    updated: "2026-10-12",
  },
  "M39.9.1.5": {
    status: "READY FOR TESTING",
    why: "P2. DEPENDS on M39.9.1.1. REUSE: the knowledge lifecycle on the Knowledge page (review dates, replace, retire) and brain.knowledge.uploads for a refetch. REMAINING: the same affordances from the agent's section, refusing for whoever may not change the item as the Knowledge page does.",
    updated: "2026-10-12",
  },
  "M39.9.1.6": {
    status: "READY FOR TESTING",
    why: "P1, a safety property. DEPENDS on M39.9.1.1. Items the reader may not read are absent with no count of what is hidden (DENIED and ABSENT are indistinguishable), and the agent's run reaches the intersection with the caller. REUSE: brain.knowledge.item.retrievable and the existing E_run machinery; REMAINING: the list read's tests and an install check that a colleague without the grant sees nothing.",
    updated: "2026-10-12",
  },
  "M39.9.1.7": {
    status: "OPEN",
    why: "P2. DEPENDS on M39.9.1.1. REUSE: the Capabilities tab's connector rows (M39.2.1.x) and skill chips (M39.2.2.x). REMAINING: show them in the Knowledge section by kind, each linking to the page that owns it, with no second copy of their data.",
    updated: "2026-10-12",
  },
  "M39.9.1.8": {
    status: "READY FOR TESTING",
    why: "P1, the proof the install must show. DEPENDS on M39.9.1.1 to M39.9.1.4 and M39.9.1.6; written as an install check (see .scratch/assign/COMMON.md): reserved people, rolled-back writes, NOT_RUN where no object store is connected.",
    updated: "2026-10-12",
  },
  "M39.9.1.9": {
    status: "OPEN",
    why: "P2. The browser proof, DEPENDS on M39.9.1.1 to M39.9.1.4. REUSE: the harness in e2e/ (two-tabs, policy specs) and console/tests/support/pageCases.",
    updated: "2026-10-12",
  },
  "M39.9.2.1": {
    status: "READY FOR TESTING",
    why: "P2. Today an agent's Automations section is a gallery of outcome templates with a one-step install, a list of this agent's automations and per-automation pause, resume, reschedule, remove and run history (M39.6.1.x, automation_gallery_routes, automations_routes, AgentAutomations), and an installed automation runs through the `automation_run` control; there is no way to start a new one that is not a template. REUSE: the gallery and install route (confirmation digest), the automation run store. REMAINING: the New automation entry, a description-in-words path and the create route; DEPENDS on M17.4.2 (outcome templates and stored, versioned workflow data) for anything beyond a template with changed settings.",
    updated: "2026-10-12",
  },
  "M39.9.2.2": {
    status: "BLOCKED",
    why: "P2. WAITS ON M17.4.1 (trigger kinds: schedule, connector event, webhook; orchestration.unattended is built but not reachable from the page) and on the condition list, which no task defines yet: the list of named conditions is a decision for needs item 177 if the owner wants it widened beyond what is built. Today a template carries a schedule only.",
    updated: "2026-10-12",
  },
  "M39.9.2.3": {
    status: "READY FOR TESTING",
    why: "built (M39/automation-instruction-within-ceiling): what an automation may use is the agent's own, read for the person writing it, and is never a list somebody typed. The tools are the agent's attached tools projected through gate/catalogue.project at the writer's reach as an automation is admitted, so a tool above the ceiling, one the writer does not reach, one detached since the manifest or one that does not exist is refused in one sentence that names only the tool they wrote; the skills are the ones the agent has attached and approved that a run would be offered (skills_offered). The form, its review, the agent's Automations card and the Automations page name them, say that anything it would write waits for a person, and say that an instruction automation cannot be started yet. The install check an_automation_names_only_what_the_agents_ceiling_lets_a_run_use names it and closes it when the install's two newest runs both pass it. To see it by hand: (1) switch New automation on and open an agent's Automations tab; (2) press New automation: What it may use lists only tools a run of an automation of yours could be handed, and Skills it would be offered lists the agent's approved skills; (3) press Review and rehearse: the review names the tools and skills, says a write waits for a person and says it cannot be started yet; (4) detach a tool on the agent's Tools tab and open New automation again: that tool is gone from the list. NOT BUILT: skills are not chosen one at a time (a run carries the agent's skills on the day it starts, which the card says), and whether an instruction may be run with nobody present is needs-rupash 210, undecided, so nothing here starts a run. Note for 210: an automation is admitted at read only (M39.6.2.1), so every tool it may name is a read tool; option A needs that admission to change first. PRIOR WORK: tool_gaps checked the name against the manifest's list only; the card already named tools and the write rule.",
    updated: "2026-10-14",
  },
  "M39.9.2.4": {
    status: "READY FOR TESTING",
    why: "P2. DEPENDS on M39.9.2.1 and M39.9.2.3. REUSE: the simulate route of gate/leash.govern and the preview step of the gallery install. REMAINING: replay the last few triggers at the owner's reach with every write simulated and nothing sent, and show the result before the switch.",
    updated: "2026-10-12",
  },
  "M39.9.2.5": {
    status: "BLOCKED",
    why: "P2. WAITS ON M39.9.2.2 (trigger kinds and conditions) and on M17.4.3 and M17.4.4 (the owner's live entitlements at each run, suspension when they lose one). Written as an install check once those exist.",
    updated: "2026-10-12",
  },
  "M39.9.2.6": {
    status: "BLOCKED",
    why: "P3. WAITS ON M39.9.2.1 to M39.9.2.4 and M39.9.2.2; the browser proof of the whole of New automation.",
    updated: "2026-10-12",
  },
  "M39.2.3.2": {
    status: "OPEN",
    why: "PLAN 2026-10-12: reopened. The domain code exists (console/agent_tabs.AddRoute and plan_addition) and the Knowledge page takes uploads and links, but nothing adds from the agent: the card links away to /knowledge and `plan_addition` is called only by an install check, so a person is never told whether the agent reaches what they added. The work is M39.9.1.2 to M39.9.1.4.",
    updated: "2026-10-12",
  },
  "M17.6.1": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.2": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.3": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.4": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.5": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.6": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.7": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.6.8": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): End-to-end workflow with two connector reads, two skills, an approval and a delivered document needs the workflow engine (M17.6.1 to M17.6.7) first; nothing runs it today.",
    updated: "2026-10-13",
  },
  "M17.7.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Monthly search report workflow needs the workflow engine (M17.6.x), a named client, report template and the owner's analytics and search console access. Connectors exist (google_analytics, search_console, acceptance_checks_search_console); the workflow and client resolve do not. Register rows OWN-75, OWN-77.",
    updated: "2026-10-13",
  },
  "M17.7.2": {
    status: "READY FOR TESTING",
    why: "built (M17/safety-alert-chat), decision 221 C: brain.control_not_run_told, started by the web process, reads each control's last success, calls controls.overdue and tells whoever holds the operations alert and may open Incidents once per episode in the chat tool they last used (the incident holders too for a mechanism that wakes somebody); when none of them has used a chat tool in seven days the address INSTALL_ALERT_EMAIL on Install, Settings is sent the same sentence through the relay. Behind the control_not_run_alerts feature, which ships off, and an install check (acceptance_checks_control_alerts) that says not run until it is on. Proved on the install when the feature is switched on and a stopped mechanism's alert reaches a reserved holder's chat once. Not covered: the sentence names the mechanism and how long, never what it guards",
    updated: "2026-10-14",
  },
  "M17.7.3": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Proof of three trigger kinds, owner suspension and adoption, run cost and the optional canvas network rule needs M17.4.1 (connector-event and webhook triggers) and M17.4.6 (cost) built first; the schedule part exists and could be proved now.",
    updated: "2026-10-13",
  },
  "M17.7.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Control-flow proof (parallel, conditional skip, retry through key, failure path, gap) needs M17.6.3 to M17.6.6 which are unbuilt.",
    updated: "2026-10-13",
  },
  "M17.7.5": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21. Install proof: sign in as an administrator, open an agent, open its Automations tab and look at the gallery. Three new cards are listed: a daily brief, drafting customer records from deals in group chats, and drafting replies to emails waiting on you. Each says what starts it and which kinds of source it uses; the two that draft say who decides before anything takes effect, and the brief says none. Open Install on one: the confirmation shows the same. None of the three can be started yet and the tab says what each still needs.",
    updated: "2026-10-20",
  },
  "M17.7.6": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-14: control_not_run now has a sender through tell_later and the mail relay (brain.control_not_run_told), so seven of the fourteen notice kinds are sent. Still unsent: evening_digest (sent by the digest destination, not through tell_later), approval_request, budget_stopped, access_request, backup_exposure, emergency_access and self_grant. Not built: an undelivered state per notice on the Notifications screen. Delivery outcomes are already kept in ops.channel_delivery (refused and unknown included) but carry no notice kind, so showing them per notice needs the kind or the intent prefix recorded beside the outcome",
    updated: "2026-10-14",
  },
  "M17.7.7": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-21, not yet proved on an install and no page draws it. brain.orchestration.workflow reads a stored, versioned definition (steps: tool, connector read, skill; named typed outputs; reads only earlier declared outputs; a condition over an output; parallel flag; retry and back-off; failure path stop, continue or handler). brain.orchestration.workflow_run runs it through a door, keeps statuses and words and no value, and says repeated failure; brain.workflow_routes writes, assigns and runs it (migration 0273, switch stored_workflows ships off) through call_piece at the asker's reach narrowed by the agent; install check acceptance_checks_workflow. Not built: a console page, a skill step's offered skills bound to the run, writes (the leash is empty so a step that changes something is stated as not offered), and the two-connector two-skill run of M17.6.8.",
    updated: "2026-10-20",
  },
  "M17.7.8": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every human approval requirement in the register, each recorded against its requirement; approval mechanics exist (approval_routes, cards, leash) but the walk is a person's on the install (register rows GAP2-02, GAP2-08, GAP2-20).",
    updated: "2026-10-13",
  },
  "M17.7.9": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): run_denial_digest_now is started each window by schedule_runner.denial_digest and sends the denial_pattern notice naming only the shape; recipients are company-wide holders (data steward), a department lead is not told. acceptance_oversight checks routing under M23.2.2 and sends nothing. NEXT: write check naming M17.7.9: run run_denial_digest_now over reserved refusals and read the kept alert for the steward with no resource named",
    updated: "2026-10-13",
  },
  "M40.7.2": {
    status: "READY FOR TESTING",
    why: "built (M40/ask-starting-points, behind the switch try_a_skill, which ships off): on the Skills page an approved skill's Try it out opens Ask with that skill to try (/ask?skill=<digest>). Ask asks GET /me/skills/{digest}/try whether it can be tried and names it, asks for an agent to run through, and sends the digest with the question for that question alone; the pin is built in memory from an approved, unchanged, unretired library row and never stored, the agent is assigned nothing, the answer cache is bypassed, and the skill is offered to the model only if every tool it names is within the run's reach (brain.api_routes.with_tried_skill, brain.gate.model_lane.skills_offered). It is the ordinary run, metered like any other. PRIOR WORK (2026-10-13 triage): the card showed 'Try it out' as an explanation of something coming soon; the rehearsal route is the reviewers' and is not a conversation. PROVE ON THE INSTALL: (1) as an administrator switch on 'Let a person try an approved skill from its card'; (2) open Skills, an approved skill, press Try it out: Ask opens saying 'Trying the skill <name>', with Talk to an agent chosen and the Ask button waiting for an agent; (3) choose an agent whose reach covers the skill's tools and ask: the answer is made with the skill's card shown to the model; (4) ask the next question without the skill: it is not carried; open the agent's Skills tab: the skill was not assigned; (5) open the address with a skill nobody approved: one sentence says it cannot be tried and the question goes as any other; (6) switch off: Try it out opens Ask with the same sentence.",
    updated: "2026-10-21",
  },
  "M40.7.3": {
    status: "READY FOR TESTING",
    why: "built (M40/ask-dictation, owner decision 220 B, browser-side only): Ask has a Dictate your question button that uses the speech recognition built into the person's browser (console/src/pages/AskDictation.tsx, askDictationCore.ts); no server route, vendor or key, and nothing is sent to our side, which a test asserts on requests. The language is the browser's own, finished phrases are appended after what was typed and stay editable, a browser with none is told so in a sentence, a blocked microphone is told how to allow it, and listening stops when the question is sent and when the page is left. PRIOR WORK (2026-10-13 triage): Attach a file to the web composer is built (AskAttach.tsx, POST /threads/attachments, M12.3.6). Dictation is not: no speech tool is registered anywhere in src. NEXT: register a speech-to-text tool; superseded by 220 B (browser-side only). Not proved in a real browser: tests drive a fake recogniser. PROVE ON THE INSTALL: (1) open Ask in Chrome or Edge on a phone and on a laptop, sign in as a member; (2) press Dictate your question, allow the microphone when asked, say a short question, press the button again; the words appear in the question box after anything already typed, and can be edited; (3) block the microphone for the site and press the button: the page says how to allow it; (4) press Ask while listening: listening stops; (5) in Firefox the page says dictation is not available and typing still works; (6) with the browser's network panel open, nothing is requested to this server while dictating. Note for the owner: Chrome and Safari do the listening through their own vendors' services, which is the browser's doing and not ours; the page says nothing is sent to this server.",
    updated: "2026-10-14",
  },
  "M40.7.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A browser proof for a member who administers nothing: needs a member-only person signed in on the install and a person or headless-browser walk of Ask, /me, approvals, accounts, memory. Waits on the owner's install (person-run demonstration) and the earlier M40 leaves.",
    updated: "2026-10-13",
  },
  "M40.7.5": {
    status: "READY FOR TESTING",
    why: "built (M40/ask-starting-points, behind the switch task_routing, which ships off): Ask offers two starting points, Start a task and Talk to an agent (console/src/pages/AskStart.tsx). Start a task names no agent; with task routing on, the gate (brain.gate.select, stage 3, still no model call) matches the question to the one agent the person may call whose name and instruction share at least two distinct words with it, and answers at the person's own reach narrowed by that agent's ceiling; a tie, or nothing shared, falls through to the default as before, and an agent the person may not call is never read. PRIOR WORK (2026-10-13 triage): Talk to an agent, select_agent and the roster existed; the web route handed select_agent no rules, no bindings and no description of any agent, so a task always went to the default. PROVE ON THE INSTALL: (1) as an administrator open Features and switch on 'Send a task started with no agent to the agent whose purpose it matches'; (2) as a member who may call an agent whose instruction names a subject (for example 'domain renewals'), open Ask: 'Start a task' is chosen and no agent picker is drawn; (3) ask a question using two words from that instruction: in Audit, the request names that agent as selected, at the classifier stage; (4) ask an unrelated question: the default answers; (5) switch the feature off: the first question is answered by the default again; (6) choose Talk to an agent and pick one: it answers, as before.",
    updated: "2026-10-21",
  },
  "M40.7.6": {
    status: "READY FOR TESTING",
    why: "built (M40/member-ask-projects, behind the switch thread_states, which ships off): each recent conversation on Ask says what became of the last thing asked: running, waiting for approval, done or failed, and a failed one says the step it stopped at, read from the person's own job, suspension and request records (brain.member_task_state, brain.ops.task_state_store). Nothing is counted and nothing of anybody else's is read. PRIOR WORK (2026-10-13 triage): the per-agent conversation list already carried answered, declined, degraded and failed; the member's own list had no state. PROVE ON THE INSTALL: (1) as an administrator open Features and switch on 'Show whether each recent conversation is running, waiting, done or failed'; (2) as a member ask a question and open Ask: the conversation reads done; (3) ask something that prepares an action needing approval: it reads waiting for approval, and after it is approved and run, done; (4) cause a failure (for example ask with the model provider stopped): it reads failed and names the step; (5) switch the feature off: the list is the same list without states.",
    updated: "2026-10-21",
  },
  "M40.7.7": {
    status: "READY FOR TESTING",
    why: "built (M40/member-ask-projects, behind the switch personal_projects, which ships off): My workspace has a My projects card (console/src/components/MyProjects.tsx) to make, open, rename, put away and fill a project with the person's own conversations and with files they add; Ask offers Ask inside a project (AskProject.tsx) and the conversation joins the project. A question inside a project reads the project's files through the registered knowledge.read_document tool at the reach the run holds (brain.project_context, wired into follow_up_for and the FollowUp the model lane already reads attachments from), never a second retrieval path, and nothing in brain.memory reads a project (a test reads the source). A file the person can no longer read stays on the list, is not read and nothing marks it. NOT wired: an agent that runs through the tool loop (brain.gate.runtime) is not handed the project's files up front; it reads documents through its own tools. PRIOR WORK: tables agent.project and agent.project_item (0233) existed with no code over them. PROVE ON THE INSTALL: (1) Features page, turn on Personal projects; (2) My workspace, My projects, make a project called Test; open it, add a conversation from the list and add a small file of your own; (3) Ask, choose Test under Ask inside a project and ask something only the file answers: the answer uses the file; (4) sign in as a colleague: they see no project of yours and a question naming its id gets an ordinary answer; (5) have an administrator take away your right to read documents, ask again inside Test: the file is on the project list and the answer does not use it; (6) put the project away: it leaves the list and a question no longer reads it; (7) turn the switch off: nothing new can be made, but you can still see, rename, empty and put away your projects.",
    updated: "2026-10-20",
  },
  "M40.7.8": {
    status: "READY FOR TESTING",
    why: "built (M40/ask-starting-points, behind the switch agent_starter_prompts, which ships off): choosing an agent on Ask shows up to three starter prompts, the example tasks written in the Examples section of the approved skills pinned to that agent (brain.member_starters, GET /me/agents/{agent_id}/starters). A prompt is offered only when the skill would be offered to a run at this person's reach through this agent (every tool within E_run, brain.gate.model_lane.skills_offered) and every department's knowledge the skill needs is within that reach; nothing is said about what was left out, and an agent the person may not run answers as one that does not exist. PRIOR WORK (2026-10-13 triage): no starter prompts existed; the inputs, skill examples and the run's reach, did. PROVE ON THE INSTALL: (1) as an administrator switch on 'Offer three starter prompts when a person opens an agent'; (2) assign an approved skill whose SKILL.md has an Examples section to an agent; (3) as a member who may run the agent, open Ask, choose Talk to an agent and pick it: the example tasks appear under 'You could ask', at most three; pressing one fills the question box and asks nothing; (4) as a member whose access does not cover a tool the skill names: no prompts appear for that skill; (5) switch off: none appear.",
    updated: "2026-10-21",
  },
  "M18.5.1": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.5.2": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.5.3": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.6.1": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): End-to-end website proposal by a coordinating agent with four specialists is unbuilt: depends on M18.5.1 to M18.5.3 and on specialist agents for website, search data, competitor and pricing, plus a single trace showing each child's reach and the fan-out verdict. Person-run proof leaf.",
    updated: "2026-10-13",
  },
  "M18.6.2": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M18.7.1": {
    status: "IN PROGRESS",
    why: "BUILT 2026-10-20, not yet proved on an install and no page draws it. Wired: brain.orchestration.coordinator runs a plan (callee allow-list refused before a child starts, each child at the asker's reach folded through the coordinator, the specialist and the subtask by chain_reach and again at every tool call by Answering.lenses, depth and per-run caps at dispatch, the global parallelism budget asked once for the widest wave, specialists in turn when fan-out is not enabled or the gate declines and never replaced by the coordinator, results checked against their contract, merged with a stated gap); brain.orchestration.planner reads a model's reply through read_proposal and FieldKind; routes in brain.coordination_routes (migration 0272, switch multi_agent_coordination ships off); install check acceptance_checks_coordination. NEXT: a console card on the agent Profile for the links, the fan-out switch and asking a coordinator, then a person watching a real request split on the install (M18.6.1).",
    updated: "2026-10-20",
  },
  "M19.8.1": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21, not claimed. Built: brain.browsing.desktop_app declares a desktop application as a target (a name, one program under /opt/desktop-apps, windows as surfaces on https://<name>.desktop.invalid) so the browser's envelope, enforcer, approval and recording govern it unchanged, and builds its sandbox (gVisor, internal network with no other member, no proxy, no secret, only the declared program) held to the browser's own container gap list; the toolkit's widgets are read as the enforcer's tree; switch desktop_runs ships off; ops/desktop/ holds a Dockerfile and a runner that were never built or run; install check a_desktop_application_runs_in_a_sandbox_with_no_way_out is NOT_RUN on every install by design. NOT built: the launcher creating a desktop sandbox, the driver relaying a desktop run, the image on a host, so no desktop has ever been started and the Profile still says computer use is not offered. NEXT: a launcher message for desktop runs and ops/desktop/REHEARSAL.md on a host with gVisor, then the second half of the check.",
    updated: "2026-10-21",
  },
  "M19.9.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): enforcer.authorise refuses an out-of-envelope action and the run ends on it (runner.py); approval.py deliberately approves the envelope up front and rejects mid-run cards (A_PERSON_APPROVES_THE_CONTRACT_BEFORE_THE_CONTAINER_STARTS). Suspend and re-approve naming the breach does not exist. NEXT: Either build a breach suspension (a new leash approval naming the refusal) or record the narrowing as a docs/needs-rupash.md question and name it in register row ARC-B-021's decision.",
    updated: "2026-10-13",
  },
  "M19.9.2": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21, not claimed. The card for a browser write now carries a readable difference from the last approved run (install check a_card_says_what_changed_since_the_last_approved_run), and the in-envelope run and the refused out-of-envelope run are shown over a stand-in page (a_browser_run_is_held_to_the_envelope_it_was_sealed_with). Still missing: suspending a run that breaches its envelope and asking again naming the breach (needs-rupash 230 decides whether a breach asks or ends), and a real run. NEXT: the owner's answer to 230, then the breach card.",
    updated: "2026-10-21",
  },
  "M19.9.3": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): sandbox.py gives each run a fresh container with read-only root, tmpfs only and no volume; sandbox_gaps refuses any volume or bind; test_browsing_sandbox.py test_every_way_out_of_the_sandbox_is_a_gap asserts it. No product code reads a staff browser profile. NEXT: Write a check naming M19.9.3 that builds sandbox_for(...), requires no gaps, then adds a volume and a bind and requires sandbox_gaps to refuse each.",
    updated: "2026-10-13",
  },
  "M19.9.4": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21, not claimed. The HTTP half (tools/website_check.py) is unchanged and the rendered-page half now has a worker behind it: website_check reads the declared websites at each call and hands a read-only surface to StoredReadOnlyBrowser (brain.browsing.read_tool), which keeps the recording under the install's prefix through the same function the retention sweep uses. Still missing: a portal login with a vault credential (credentials.resolve has no caller; needs owner decision on custody), the image and a real run. NEXT: the image, a rehearsal, then the login.",
    updated: "2026-10-21",
  },
  "M19.9.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Pieces exist (planning, envelope, approval, enforcer, grading, verification.read_back) but there is no driver, no judge, no ReadBackPort implementation and no target declares read_back; a form-filling run at Assisted cannot happen. NEXT: Needs the driver, judge and a ReadBackPort over a registered target; then a check that runs one approved form fill, a refused extra step and a read-back.",
    updated: "2026-10-13",
  },
  "M19.9.6": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT 2026-10-21, not claimed. The read handler an agent with the browse capability calls now exists and is registered (brain.browsing.read_tool, see M19.7.1) and the whole path is exercised over a stand-in page by install check a_browser_read_returns_only_the_declared_fields, which ends NOT_RUN. Still missing: the -browser image built and released, the REHEARSAL.md first build on a runsc host, and one real page fetched in the sandbox. NEXT: those three, then ask an agent to read a declared page.",
    updated: "2026-10-21",
  },
  "M19.9.7": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 (triage 2026-10-13 class 2/3, now wired): migration 0275 adds agent.browser_target and agent.browser_grant; brain.browsing.declared is the codec and the stores; brain.browser_routes (admin:browser, switch browser_declarations, ships off) and a 'Websites for agents' browsers' panel on the Features page declare a website, sign an exception or an exemption, list them and take them back. Install check a_website_is_declared_and_permissions_signed_for_it_are_read goes through those routes and then asks the readers (driver.prepare_run and skill_library.browser_refusals). This leaf: a grant is listed with who signed it and when it lapses, is a leash_change entry in the audit ledger when signed and when revoked (trigger in 0275, held to the shape of a leash change by a test), and a run compiled after the end or the revocation no longer has it. INSTALL PROOF STEPS: 1. Features page: switch on 'Declare websites for agents' browsers and sign exceptions'. 2. In the Websites panel paste a declaration of a public page of your own (a name, its origin, one surface with verbs open and read and one field) and press Declare website: it is listed. 3. Install page: Run now, and read the row a_website_is_declared_and_permissions_signed_for_it_are_read: it must say Passed. 4. Revoke the exception: it leaves the list and the Audit page shows two leash changes about the website.",
    updated: "2026-10-21",
  },
  "M19.9.8": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): grading.build_rubric and verification.verify_run exist and are tested; grading.verification_gaps states no judge is built and no target declares a read_back tool. Nothing scores a real run. NEXT: Build the judge and the read-back port, call verify_run at run end, then a check that scores a recorded run against its prior rubric.",
    updated: "2026-10-13",
  },
  "M19.9.9": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 on browsing/driver.py (merged behind the browser_runs switch), recording.py and concurrency.py. Install check browser_sessions_are_limited_and_a_halt_stops_a_run counts sessions from the rows that record them and shows a session past the global budget, a site's limit or an agent's refused with a sentence naming the site and the agent. INSTALL PROOF: Install page, Run now, row browser_sessions_are_limited_and_a_halt_stops_a_run says Passed. The live session count against real containers waits for the live read run.",
    updated: "2026-10-21",
  },
  "M19.9.10": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): compile_envelope, approval, credentials.resolve and enforcer exist as separate tested modules but no code joins them for a run; no vault credential binding source for browser targets exists; no run has happened. NEXT: Needs the driver plus Bindings backed by the vault; then a check that approves one write envelope and shows the credential absent from plan, trace and recording.",
    updated: "2026-10-13",
  },
  "M19.9.11": {
    status: "READY FOR TESTING",
    why: "BUILT 2026-10-21 on browsing/driver.py (merged behind the browser_runs switch), recording.py and concurrency.py. Same work and check as M19.6.6: recordings sit under the install's prefix and a scheduled pass removes expired ones, keeps held ones and reports undated ones. INSTALL PROOF: connect the object store, Install page, Run now, row a_browser_recording_is_kept_and_removed_when_its_time_has_passed says Passed; then read the Scheduled jobs page's retention sweep report, which now carries a line 'recordings: removed N, kept N under a hold, N with no date in their key'. Written at run end by a real run waits for the live read run.",
    updated: "2026-10-21",
  },
  "M21.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): SpendActualRow.trace_id is recorded and telemetry records tool_count; shape join is spend_store.question_shape_report (no route). Fan-out is deliberately not recorded (telemetry docstring, item 59): nothing that finishes a request fans out. NEXT: Wire shape ranking (see M21.3.4); fan-out waits until an orchestrated run finishes through a point that records width; then check.",
    updated: "2026-10-13",
  },
  "M21.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Roll-up proof (a check can be written once clauses exist) across M21.1 and M21.2; several parts are unbuilt or unwired (department and user budgets M21.1.2/3, estimate refusal M21.2.1, enforcement flag off per needs 169 A, skill-body load check). NEXT: Waits on M21.1.2, M21.1.3, M21.2.1 and the owner switching budget_enforcement on (needs 169); then record the demonstration.",
    updated: "2026-10-13",
  },
  "M21.4.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): console.workspace.Range has 7d, 30d, 90d and mtd only; no all-time range and no marking of the incomplete current day in console/src/pages/agents/AgentDashboard.tsx or agentStats.ts. NEXT: Add Range.ALL_TIME to console/workspace.py and the period selector, and a partial-day marker on the last chart bar; then check.",
    updated: "2026-10-13",
  },
  "M21.4.5": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every cost requirement recorded against its row (register proof column M21.4.3 and M21.4.5); not code.",
    updated: "2026-10-13",
  },
  "M25.4.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Sweep is report-only until released: retention_store.run_retention_sweep(report_only), POST /govern/retention/release (needs the report named, ledgered by trigger), withdrawal route, RetentionActs.tsx. Tests test_retention_routes, test_retention_store. NEXT: Write check naming M25.4.1: read the report, assert nothing removed, release via the route, assert the ledger row.",
    updated: "2026-10-13",
  },
  "M25.4.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Roll-up proof (a check can be written once clauses exist) across M25.1 to M25.3; parts are unbuilt (subject access M25.2.1, certificate M25.2.4, cache/index/object erasure M25.2.2, bulk and knowledge export M25.3.2/3, trace row removal M25.1.3). NEXT: Waits on those leaves, then a person runs the demonstration and the checks are recorded.",
    updated: "2026-10-13",
  },
  "M25.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): browsing.recording.remove_expired(backend, today, held_runs) removes recordings past 30 days and skips held runs (tested) but nothing calls it; other buckets rely on lifecycle rules which retention_store says nothing verifies; no per-object sweeper over ops.object_store. NEXT: Add an object sweeper over ops.object_store.list_objects with ages, call it from schedule_runner behind the release gate with the hold check and a removal record per object.",
    updated: "2026-10-13",
  },
  "M25.4.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every data and retention requirement recorded against its row; not code.",
    updated: "2026-10-13",
  },
  "M25.4.5": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): ops.ledger_export.LedgerShipper (app.py, destination_here) sends each finished request's masked trace to the install's Langfuse; install check a_run_sent_to_the_ledger_is_found_there_with_its_model_call (acceptance_checks_services.py:303) already proves it under M32.1.2.6. NEXT: Add M25.4.5 to that check's leaves=(...) if it asserts the payload is masked; otherwise add that assertion first.",
    updated: "2026-10-13",
  },
  "M26.2.7": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Roll-up test leaf: tests/unit/test_lifecycle.py covers the pure module, but several clauses it covers (provision, delegations, welcome) are not wired, so a test of every item above has nothing end to end to run. 2026-10-20 ROLL-UP BUILT, NOT YET ABLE TO PASS: acceptance_checks_jml_roll_up.every_mover_leaf_is_shown_clause_by_clause_in_this_run reads the checks for M26.2.1 to M26.2.6 and is not run while any has none (M26.2.5 has no install check). tests/unit/test_mover_end_to_end.py drives the staff run and asks the reach, cache key, memory, automation and knowledge rules of one mover on the state it leaves. A person runs the install checks; this closes when every clause check passes in one run.",
    updated: "2026-10-20",
  },
  "M26.4.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Roll-up proof (a check can be written once clauses exist) across joiner, mover and leaver; clauses depend on unwired parts (delegations M26.2.3, personal knowledge disposition M26.3.4, ended grant mid-run, external person end date). NEXT: Waits on M26.2.3 and M26.3.4, then a person runs it and the checks are recorded. 2026-10-20 ROLL-UP BUILT, NOT YET ABLE TO PASS: acceptance_checks_jml_roll_up.joiner_mover_leaver_is_shown_clause_by_clause_in_this_run reads the clause checks and names any clause with none: a personal agent following its owner (M26.2.2, now checked), memories of the old reach (M26.2.5), a run stopping on a revoked grant (M13.8.2, has a check), an external person's end date (M1.8.1) and a service key stopping with its owner (M1.8.2), neither of which has a check, and an owned item a person can no longer reach leaving their workspace, which no leaf names. It stays not run, never passed, until each is shown.",
    updated: "2026-10-20",
  },
  "M29.3.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Clauses have checks: new-API connector live with no release (acceptance_checks_custom_connector.py, M11.7.8); channel off refuses inbound (acceptance_operations_console_4.py:239); a console setting says when it applies (acceptance_operations_console.py:472). Not verified: vendor adapter replaced with no deploy. NEXT: Write a roll-up check naming M29.3.1 over those checks (pattern acceptance_roll_up.clauses_demonstrated); add a clause check for a replaced provider key taking effect with no deploy.",
    updated: "2026-10-13",
  },
  "M29.3.2": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every modularity requirement recorded against its row; not code.",
    updated: "2026-10-13",
  },
  "M30.4.3": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No chaos suite exists: nothing in src, tests, ops or CI matches chaos, and no script kills Postgres, provider, connector, browser or worker. Related: ops/crash.py durable_machines, ops/recovery_run.py, ops.reliability.MATRIX.",
    updated: "2026-10-13",
  },
  "M30.4.6": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): gate/runtime.py re-resolves the reach before every tool call (A_RUN_IS_JUDGED_AGAIN_AT_EVERY_TOOL_CALL) and leash.resume re-judges; tests: test_agent_runtime.py test_a_grant_revoked_mid_run_refuses_the_next_call, test_crash.py M30.4.6 cases. NEXT: write check naming M30.4.6: start a run, change policy (revoke a grant or lower the rung) mid-run, assert the next tool call is refused in the one sentence",
    updated: "2026-10-13",
  },
  "M30.4.7": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Same per-call re-resolution; test_crash.py test_a_caller_disabled_between_two_attempts_is_refused_at_the_second and test_a_reader_disabled_between_two_attempts_is_judged_at_the_instant_it_is_asked cover the rule; the request path applies EntitlementSet expiry via intersect. NEXT: write check naming M30.4.7: disable a person (directory change or session end) mid-run and assert the run's next step is refused",
    updated: "2026-10-13",
  },
  "M30.4.9": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Overlays docker-compose.split*.yml, ops/split.py (host_services, address_refusals) and docs/install/scaling.md exist and are tested; scaling.md says the rehearsal steps have not been run. Needs-rupash lists M36.1.4.2 merged into M30.4.9.",
    updated: "2026-10-13",
  },
  "M30.6.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Proof leaf for backups on an install: seven consecutive nights, a missed night alerting a person, never verified until a drill, drill checking schema, RLS and permissions, erasure horizon. Needs elapsed time on a real install and the unbuilt pieces M30.3.2, 3.3, 3.4, 3.6, 3.7, 3.10.",
    updated: "2026-10-13",
  },
  "M30.6.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): GET /report/service-levels shows per lane objective_p95_ms, p95_ms, success_rate, requests (report_routes.py, ops/service_levels.py). Missing: p50, permission and redaction latency, connector timeout in force; missed-window and aged-backup alerts unwired (M37.5.1.3, M30.3.10); worker-stop and canary delivery unbuilt. NEXT: add p50, permission and redaction latency and connector timeout to the service levels reading, wire the alert runners, then write the check",
    updated: "2026-10-13",
  },
  "M30.6.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): docs/install/network.md states Cloudflare reads every request and decrypts at its edge. No install-level residency constraint exists (residency is a model-routing setting) and nothing requires or records an administrator's acceptance before a tunnel or edge proxy is enabled. NEXT: add an acceptance record (table, route, console prompt) shown when the tunnel overlay is enabled on an install declaring a residency constraint; needs a decision on what declares one",
    updated: "2026-10-13",
  },
  "M30.6.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): docker-compose.replica.yml runs a hot standby Postgres; profile full has a one-hour RPO (reliability.RECOVERY_OBJECTIVES). Missing: object store replication off the host, a promote or failover procedure and recorded failover drill, and any gate stopping the profile being offered without them. NEXT: build object-store replication, a failover runbook and drill record, and make launch.service_level refuse an under-four-hour profile without them; needs a second server to rehearse",
    updated: "2026-10-13",
  },
  "M30.6.6": {
    status: "READY FOR TESTING",
    why: "BUILT: the statement is produced only after a verified rehearsal and every copy inside the recovery point, and otherwise refused with the reason (launch.service_level, now served). PROOF ON THE INSTALL: the same steps as M30.5.4; the refusal names the coverage nothing has copied or the missing rehearsal.",
    updated: "2026-10-20",
  },
  "M30.6.7": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Multi-part proof: backups off-host with client key, timed restore drill, worker killed mid-task, chaos suite, capacity and scaling readbacks. Chaos suite is unbuilt (M30.4.3) and backup encryption and off-host enforcement are unbuilt (M30.3.3, 3.4); the worker-kill piece has recovery_run.",
    updated: "2026-10-13",
  },
  "M30.6.8": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every hosting and delivery requirement in the register, each check recorded against its requirement; register rows cite M30.6.8 as proof for dozens of requirements.",
    updated: "2026-10-13",
  },
  "M30.6.9": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Telemetry is written for every request by gate/finish.py and GET /report/service-levels returns each lane's requests, p95 and success rate (ops/service_levels.py, report_routes.py); test_a_lane_nothing_was_asked_through_is_present_and_unmeasured. A lane with traffic carries requests above zero. NEXT: write check naming M30.6.9: ask one question, GET /report/service-levels and assert the answer lane shows requests of at least one",
    updated: "2026-10-13",
  },
  "M30.6.10": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): controls.backup_exposure (daily, WOKEN) and recovery.alerts() exist; Runner backup_exposure in schedule_runner.py has needs= and no run, so the control never runs on its cadence and alerts nobody. Includes the not-verified-last-rehearsal case via last_attempt (tested). NEXT: same wiring as M30.3.10; then the check reads the control's last run from the Jobs route and an alert addressed to the named person",
    updated: "2026-10-13",
  },
  "M34.4.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Runbooks per screen exist (36 files) with a gap sweep (launch.screen_runbook_gaps); alert runbooks via ops.controls.runbook_gaps. The incident playbook is a Python table (ops.reliability.MATRIX) nothing renders, and no help route serves any of it. NEXT: Build GET help pages serving runbooks, alert runbooks and a rendered playbook; extend the sweep to fail when a screen or alert has none.",
    updated: "2026-10-13",
  },
  "M35.2.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): Native controls, a skip link and console/scripts/check-boundaries rules run in CI; console/tests/keyboard-access.test.tsx renders pages and asserts tab order (names M35.2.2.1). jsdom only; not observed on the served console. NEXT: Browser run on the install tabbing through the shell, a list and a form; record against M35.2.2.1 (see M35.4.1).",
    updated: "2026-10-13",
  },
  "M35.2.2.2": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): A focus-visible ring is defined in the theme tokens and CI refuses outline none; keyboard-access.test.tsx asserts it in both themes (names M35.2.2.2). Not seen on the served console. NEXT: Browser run in both themes on the install; record against M35.2.2.2.",
    updated: "2026-10-13",
  },
  "M35.3.2.1": {
    status: "READY FOR TESTING",
    why: "TRIAGE 2026-10-13 class 1 (built and wired, install check missing): console/public/manifest.webmanifest and index.html link it; console_static serves unhashed files at the root; console/tests/installable-shell.test.ts asserts it (names the leaf). No service worker is claimed. NEXT: Write a check naming M35.3.2.1 that GETs /manifest.webmanifest from the install and asserts start_url, scope, icons and name; an install prompt in Chrome is the person's half.",
    updated: "2026-10-13",
  },
  "M35.4.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Needs a browser run of every console module by keyboard, with focus and errors seen. The repo has jsdom tests (keyboard-access.test.tsx, phone-width.test.tsx) and docs/console-audit but no browser job; person or agent browser run on the install.",
    updated: "2026-10-13",
  },
  "M35.4.2": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Roll-up proof; clauses unmet: console is English only (M35.1.1.1, M35.1.1.2 unwired) and a screen-reader run is a person's. Retrieval clauses (M35.1.2.x) and names for redaction (acceptance_checks_names.py) are provable by checks.",
    updated: "2026-10-13",
  },
  "M35.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): rules_for raises LocaleError carrying locale.RIGHT_TO_LEFT.reason for an RTL tag, but console.configuration._locales_problem replaces it with a generic sentence, so the console refusal does not name the deferral; setup path not verified. NEXT: Return the deferral sentence from _locales_problem and the wizard; then a browser run or a settings route check naming M35.4.3.",
    updated: "2026-10-13",
  },
  "M35.4.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every localisation and accessibility requirement recorded against its row; not code.",
    updated: "2026-10-13",
  },
  "M35.4.5": {
    status: "READY FOR TESTING",
    why: "built (owner decision 222 A): the read is migration 0227's view gate.approval_wait over gate.suspension (the two times of each decided approval, no id, person or verdict), ops/approval_wait.py gives the median over the last 90 days (never a count; nothing decided is None, shown as unknown with the reason), console/installation.approval_wait_facts words it with the push verdict from locale.triggered, install_routes serves it on GET /install, and ops/acceptance_checks_approval_wait.py is the install check. Route tests and a mutation table are in tests/unit/test_install_approval_wait_route.py. PRIOR WORK (2026-10-13 triage): Only the constants exist: locale.PUSH_IS_DUE_ABOVE_HOURS and the deferral. Suspension rows carry raise and decide times but nothing computes a typical wait or reports that push is due. NEXT: Add a read over gate.suspension (raised to decided) giving the median wait, show it on Approvals or Install, and call locale.triggered; then a check. PROVE ON THE INSTALL: as for M35.3.2.2, run the acceptance run and read the_approval_wait_is_measured_and_push_is_reported, then open Install, This install.",
    updated: "2026-10-14",
  },
  "M35.4.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): console/tests/phone-width.test.tsx asserts the cascade for every registered route at 360px (wrapping, link height) but the file says it cannot measure widths; no 44px target or 320px width measurement exists. NEXT: Add a headless browser measurement (iframe at 320px as the test's author did) over every route and assert 44px targets and no overflow; or relax to the measured figures and ask.",
    updated: "2026-10-13",
  },
  "M36.2.4.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/load_peak.judge compares each lane's p95 and success rate with reliability.LANE_OBJECTIVES (tested) and prints them; no store keeps a run's result and no screen shows it. A run needs the owner's sign-off (needs-rupash item 194). NEXT: add a table and route that record a load_peak result per run and show it beside the service level table; the first real result waits on item 194",
    updated: "2026-10-13",
  },
  "M36.3.1": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): ops/load_peak.py (python -m brain.ops.load_peak) runs the peak at a live install and judges per lane; it spends real model calls so it is the owner's command, needs-rupash item 194 asks whether to run it. It does not measure memory headroom under load.",
    updated: "2026-10-13",
  },
  "M37.7.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): migration/decommission.py CompletedCutover cannot be built while CUTOVER_GATED_ACTS are unrecorded and decommission_gaps names which (tested; DEC-35). Nothing records a cutover: no table, route or page, and nothing imports it. NEXT: build the cutover record store and route that constructs CompletedCutover and returns the refusal text naming the unrecorded act; then check reads the refusal",
    updated: "2026-10-13",
  },
  "M37.7.6": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A throwaway-install rehearsal of the whole migration (skills re-reviewed, agents at Shadow, cutover refused) is a person-run demonstration that needs the migration package wired first (M37.1.x, M37.2.x are unwired). Register DEC-35 and DEC-59 name it as proof.",
    updated: "2026-10-13",
  },
  "M37.7.8": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run demonstration of every migration requirement on an install, recorded against the requirement it proves; register rows GAP2-25 and others name it as proof. Depends on the migration package being wired and on the owner or a tester running it.",
    updated: "2026-10-13",
  },
  "M42.2.10": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): docs/install/update-and-rollback.md says neither procedure has been run on a server and 'M42.2.10 is not claimed'; update.sh and rollback.sh exist (generated, tested) but a rehearsal is a person-run event.",
    updated: "2026-10-13",
  },
  "M42.3.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/backup/brain-backup, brain-restore-drill and brain-install-backup exist and run against stand-ins (tests/unit/test_backup_scripts.py); restore-drill.md says nobody followed it on a server, the archive does not carry ops/backup, nothing schedules a drill. NEXT: Run the drill once on the owner's install, record it, and fix packaging (M42.7.4). CLAUDE.md bars 'restore' in function names under src/brain.",
    updated: "2026-10-13",
  },
  "M42.4.2": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): Nothing audits stores for another company's values: deployment/audit.py covers configuration, build inputs and git history only; ops/independence.py covers source and docs. No search over database rows, logs, uploads, object store, vector store, embeddings or caches.",
    updated: "2026-10-13",
  },
  "M42.4.3": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No credential, token, webhook, integration or default-administrator audit found: deployment.audit does not read live settings, and variables.unminted_secrets is an unwired helper for secrets only.",
    updated: "2026-10-13",
  },
  "M42.4.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A person-run event: Verz's live system installed by running the installer on its server, not migrated from development. Code half exists (install.sh, v0.1.0); register row LIVE-01 and needs-rupash 82 treat the owner's server as company one.",
    updated: "2026-10-13",
  },
  "M42.4.5": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Person-run verification on the Verz install (boots, sign-in, administrator, core answers, integrations, nothing carried over); register OWN-166 lists it as proof. Install checks cover parts but the leaf is the owner's demonstration.",
    updated: "2026-10-13",
  },
  "M42.4.6": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A measured time from bare server to first answered question is a number a person records during an install run; nothing in src records installer durations (no timer in install.sh).",
    updated: "2026-10-13",
  },
  "M42.4.7": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A second install on a throwaway server by somebody following only the documentation is a person-run demonstration (register OWN3-1 and FEAT-12.12 proof).",
    updated: "2026-10-13",
  },
  "M42.4.8": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): Turning questions asked during the two installs into documentation lines is a follow-up to M42.4.4 and M42.4.7 and has no input until they happen.",
    updated: "2026-10-13",
  },
  "M42.5.16": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No channels step exists: setup_wizard.StepId has setup_code, company, administrator, data_steward, staff_source, model_provider, connections, review, finish; channel connection exists elsewhere (channel routes, console Channels pages).",
    updated: "2026-10-13",
  },
  "M42.5.17": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A person-run demonstration on a fresh AWS instance and a fresh VPS with the time recorded (register OWN3-1 proof; needs-rupash 82 item 2).",
    updated: "2026-10-13",
  },
  "M42.6.7": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): release.yml has published v0.1.0 (2026-09-29) with image and archive, but 'fetched back on a clean machine' is a person-run step; test_deployment_release.py covers archive contents only.",
    updated: "2026-10-13",
  },
  "M42.7.1": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No install health check reports kernel virtualisation: grep for kvm and virtualisation finds only a sentence in browsing/sandbox.py; launcher.py --check reports gVisor (runsc) only, and no administrator-facing text states browser isolation.",
    updated: "2026-10-13",
  },
  "M42.7.2": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A composite install demonstration: release.yml cosign-verifies and tags the CI digest and update.sh/rollback.sh exist, but pull by digest, drain of a running workflow and rollback completing have not been run (update-and-rollback.md says never run).",
    updated: "2026-10-13",
  },
  "M42.7.3": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No notice bundling found: ops/dependency_policy.py checks licences of locked packages in CI but nothing generates a notices file from the lockfiles, puts one in the image or archive, or fails a release without one; release.INCLUDED has no notice rule.",
    updated: "2026-10-13",
  },
  "M42.7.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/backup/brain-backup, brain-restore-drill and brain-install-backup (with a systemd timer) exist, but release.INCLUDED has no ops/backup rule (restore-drill.md: the archive does not carry ops/backup) and install.sh has no step that schedules the backup. NEXT: Add an ops/backup rule to release.INCLUDED and an installer PLAN step running brain-install-backup, regenerate install.sh, then check the timer exists on an install.",
    updated: "2026-10-13",
  },
  "M42.7.5": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A state of the owner's install: standard profile, health screen showing worker, vault, object store and pooler ready, provider key in the vault. Parts have checks (acceptance_checks_vault_worker.py reads the health figure) but the leaf is about that server's configuration.",
    updated: "2026-10-13",
  },
  "M42.7.6": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A state of the owner's install: pinned to a published tag, with the Version screen showing it and the newer-release verdict. The screen is built (M42.3.9, release_feed) and v0.1.0 exists.",
    updated: "2026-10-13",
  },
  "M42.7.7": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A person demonstrates every other register requirement on an install and records each check against its requirement; register rows LIVE-08, LIVE-09, LIVE-12, LIVE-13 and CONB-44 list it as proof.",
    updated: "2026-10-13",
  },
  "M42.7.8": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): docs/install/network.md and threat-model.md describe public ports, TLS and the allowlist, and ops/security exists; no probe from outside the allowlist and no alert on the install's own certificate within fourteen days exists (ops/website_probe.py reads other sites' certificates only). NEXT: Build an external probe job and a certificate-expiry alert to a named person, then a check that reads the alert configuration; the outside-address probe itself is a person step.",
    updated: "2026-10-13",
  },
  "M27.15.34": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-reads-and-template-withdrawal): the Learning, Memory and Artifacts reads take an optional agent, cut after the reader's audience, so an agent the reader may not see answers as one that does not exist; an agent's own Memory tab no longer lists the learnings formed in plain conversations. Proved on the install with the check 'An estate read cut to an agent is its slice and hides the rest', which passes when the install's two newest runs both pass it; by hand: on Learning, Artifacts and a person's Memory page ask for one agent and see only what it formed or produced, then ask for a personal agent of somebody else and see the same answer as for one that was never made",
    updated: "2026-10-15",
  },
  "M27.15.35": {
    status: "READY FOR TESTING",
    why: "built (M27/agent-reads-and-template-withdrawal, migration 0261): an administrator withdraws a published template version with a reason and puts it back, each an inserted row and a ledger entry; a withdrawn version leaves the gallery, its install page and agents' upgrade offers while agents installed from it stay as they were; a version is saved as a signed document and a document from another install is read, then added once, signed again by this install; all behind the template_withdrawal switch, which ships off (needs-rupash 236 asks whether installs should prove origin to each other). Proved on the install with the check 'A withdrawn version is not offered and agents stay pinned'; by hand: turn the switch on in Features, open a template, withdraw its newest version with a reason, see the version before it offered and an agent made from it unchanged, then put it back from Agent templates",
    updated: "2026-10-15",
  },
  "M27.15.75": {
    status: "READY FOR TESTING",
    why: "To test it on the install: open the Install page and find the check 'the console names no font host and serves every font it ships' passing; open any console page with the browser's network tab open and see every font file come from the install's own address and none from a font service; open /font-licences.txt on the install to read the fonts' licence notices. In CI the 'Console types, boundaries, tests, build' job audits the built bundle (python -m brain.ops.bundle_audit console/dist) and the nightly Browser workflow records every font request of every page.",
    updated: "2026-10-14",
  },
  "M27.15.79": {
    status: "READY FOR TESTING",
    why: "Proved by the CI job 'Dependency audit' (python -m brain.ops.dependency_policy offline): it reads every package in the console's lock, build-time ones included, and refuses one whose licence is not on the allowed list or is not recorded. To see it refuse, open a pull request adding a console dependency under a licence the list does not name and read the job's output. Three build-time packages wait on you in needs-rupash item 238; the job prints them on every run.",
    updated: "2026-10-14",
  },
  "M27.15.83": {
    status: "BLOCKED",
    why: "Partly built, and the rest is the owner's to supply. Built: docs/reference-screens/index.json records, for each console page the reference screenshots cover, what was adapted and what was refused, and console/tests/reference-screens.test.ts holds it against the route table and the two kept rejections. Not done: the thirteen images are not in the repository. They are in the owner's workspace outside it, and the session that built this could not read or copy them. Copy them into docs/reference-screens/ and set each entry's file in index.json (needs-rupash item 237); then the leaf is ready for testing.",
    updated: "2026-10-14",
  },
  "M27.15.68": {
    status: "READY FOR TESTING",
    why: "Built on branch M27/console-lists-wizards-buttons. Prove it on the install. (1) Sign in as an administrator, open Agent templates and a published template. The Install card is now a short wizard, Step 1 of 3 or 4: its name, who can find it, where it answers (only when the version offers channels), then Check and install. Type a new name, tick For my department, press Next. (2) Go to another page, such as Agents, then come back to the same template: you are on the same step with the same answers, and a line says you are back where you left. (3) On the last step press Install: a confirmation names what will be installed, and nothing is sent until you confirm; the new agent opens disabled. Back on the template the install is blank again. (4) Press Start again part way through and it empties; sign out and sign in as somebody else and nothing the first person typed is there. (5) First run on a fresh install: enter the setup code, finish the company screen, close the tab, reopen the first-run address, enter the same code and you land on the next screen with the company answers still in the boxes. A provider key typed on its screen is not kept.",
    updated: "2026-10-14",
  },
  "M27.15.71": {
    status: "READY FOR TESTING",
    why: "Built on branch M27/console-lists-wizards-buttons. Prove it on the install. (1) On any page with both a Cancel and an act that removes or stops something (Stop, a retention hold, a review decision), the main act is the filled accent button, Cancel is the quiet button with no border, and the removing act is the red-washed danger button, each visibly different. (2) Open the console home: the figures are tiles, Needs you and Recent activity are each a card with its own heading, as on the first screen of the key screens design. The Overview already drew these; this task names the three button variants, moves every page onto them and holds that with a check.",
    updated: "2026-10-14",
  },
  "M27.16.2": {
    status: "READY FOR TESTING",
    why: "Built on branch M27/console-lists-wizards-buttons. Prove it on the install. (1) Open any page of the console and read it as an administrator would: no long unique codes, no table names, no snake_case names and no words such as API, JSON or endpoint outside the collapsed Advanced section, except on the few pages that exist to show one (tool names, the address to paste into a chat vendor, adding an API connector). (2) Stop and Rules say when something was stopped or added and not an id; a channel's set-up fields read as words such as Reply address; a list's card no longer repeats the page title under it. (3) docs/console-cleanup.md lists each removal with its reason and each page that is excused with why.",
    updated: "2026-10-14",
  },
  "M27.16.3": {
    status: "READY FOR TESTING",
    why: "Built on branch M27/console-lists-wizards-buttons. Prove it on the install. (1) Open Agents (or People, Skills, Connectors): the toolbar ends in Saved filters. Type a search, choose a filter, open Saved filters, give it a name and Save. Clear the search, reopen Saved filters and press the name: the list narrows to the same question. Reload the page and it is still there; sign in as somebody else and it is not. Audit and Logs have the same control beside their filters. (2) Every list table has Columns (hide one and it goes), Export (downloads a file of the rows shown, in the columns shown), a tick box on every row (Export selected appears), and a small panel button on each row that opens a drawer showing every column, including hidden ones. People, Sessions, Access review and the Library also offer an act on the ticked rows. (3) No list shows a total, a page count or an of N anywhere.",
    updated: "2026-10-14",
  },
  "M27.16.4": {
    status: "READY FOR TESTING",
    why: "BUILT AND TESTED: docs/screens.html draws a screen for every primary page, screens 15 to 45 being the thirty-one that had none (wireframes drawn from the built pages, example values in place of data) beside the fourteen designs it began with, and the agent page keeps screen 14. tests/unit/test_console_pages.py fails when a page has no screen, names a screen that is not drawn, or has a walk-through recorded before it has a screen. Install proof: open /build/screens and /build/pages; every page on the list links to a screen.",
    updated: "2026-10-20",
  },
  "M27.16.5": {
    status: "READY FOR TESTING",
    why: "BUILT, and it waits on you: a page counts as rebuilt on /build/pages only when a walk-through of it has passed on your install, and every row starts without one, so the count of rebuilt pages is nought. To record one, open the page on your install, find it as its screen draws it, and set that row's walked in docs/console-pages.json to the day and the release it passed on. The register refuses a walk-through for a page that is not on the shared parts or has no screen.",
    updated: "2026-10-20",
  },
  "M12.3.5": {
    status: "READY FOR TESTING",
    why: "built for Word only, behind a switch that ships off (brain.tools.document_generation, tool documents.generate_document); decks and spreadsheets wait on needs-rupash 193 and are not offered. NO PRIOR WORK existed (no note, no branch, no code). Proved on the install when: 1. Install, Features: switch on 'Let an agent produce a Word document from an approved template'. 2. Knowledge: add a document of kind Template holding a line such as 'Prepared for {{client_name}}.' and have its steward verify it. 3. Give a person, and an agent whose tools include documents.generate_document, the capabilities invoke:generated_document and read:generated_document. 4. As that person ask the agent to produce a document from the template with a value for client_name: its answer names a file, which is listed under that person's artifacts and opens in Word with the value in it. 5. Ask the same as a person in another department, and with a draft or unverified document as the template: nothing is produced and the refusal is the same sentence. Limit: the layout is rebuilt from the template's text, so the original file's styles and logo are not carried; that needs a link from each library item to its original file, which is a migration.",
    updated: "2026-10-14",
  },
  "M12.3.7": {
    status: "IN PROGRESS",
    why: "PARTLY BUILT, 2026-10-14; NO PRIOR WORK existed (no note, no branch, no code). BUILT: an outside AI service (image generation, speech to text) an install declares is registered as a tool behind a switch that ships off (brain.tools.external_ai, brain.ops.external_ai_store); its permission is its own (invoke:external_ai.<service>), it counts as sending something out and is capped at Assisted, and an agent whose ceiling does not name it is offered nothing; an install check proves that. NOT BUILT, WAITING ON THE OWNER (needs-rupash 184, open): the call itself, which needs the first service, its provider account and its key in the vault, and whether speech to text counts as a read and image generation as a draft (a loosening, not built). NEXT: when 184 is answered, build the held call and the worker's run of the approved one for that service, then flip this to READY FOR TESTING.",
    updated: "2026-10-14",
  },
};

//: Wave number to the deployed commit it closed at: {commit, recorded, note}. Empty until a
//: wave is accepted on staging.
const WAVE_RECORDS = {
  // Accepted by the owner on 2026-09-29 ("yes, cut the release"); v0.1.0 names this commit.
  "0": {
    commit: "dd6a23a9bc45f5fdada93069ac88fc60b4a5bcc6",
    recorded: "2026-09-29",
    note: "Foundation accepted on staging; first release v0.1.0 cut from this commit",
  },
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const SHA = /^[0-9a-f]{7,40}$/;

function check(textOf, waveNames) {
  const wrong = [];
  for (const id of Object.keys(PROGRESS)) {
    const entry = PROGRESS[id];
    if (textOf(id) === undefined) wrong.push(`${id} names no leaf, so it is a group id or a typo`);
    if (entry.status === "DONE") {
      wrong.push(`${id} is set to DONE by hand, and DONE comes only from a commit with proof`);
    } else if (!STATUSES.includes(entry.status)) {
      wrong.push(`${id} has status "${entry.status}", which is none of ${STATUSES.join(", ")}`);
    }
    if (entry.status === "BLOCKED" && !(entry.why || "").trim()) {
      wrong.push(`${id} is BLOCKED with no reason, and a block nobody can read is not actionable`);
    }
    if (!DAY.test(entry.updated || "")) wrong.push(`${id} has no updated date as YYYY-MM-DD`);
  }
  for (const wave of Object.keys(WAVE_RECORDS)) {
    const rec = WAVE_RECORDS[wave];
    if (waveNames[wave] === undefined) wrong.push(`wave ${wave} is recorded and is not a wave`);
    if (!SHA.test(rec.commit || "")) wrong.push(`wave ${wave} records "${rec.commit}", not a commit`);
    if (!DAY.test(rec.recorded || "")) wrong.push(`wave ${wave} has no recorded date as YYYY-MM-DD`);
  }
  if (wrong.length) throw new Error(`docs/wbs/progress.js:\n  ${wrong.join("\n  ")}`);
}

module.exports = { STATUSES, PROGRESS, WAVE_RECORDS, check };
