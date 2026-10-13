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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "BLOCKED",
    why: "waits on memory for Langfuse: 2,048 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 3). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_services, ops.overlays, ops.wiring +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M32.1.1.2": {
    status: "BLOCKED",
    why: "waits on memory for Langfuse: 2,048 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 3). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_services, ops.overlays, ops.wiring); open for proof on the install or a decision, not for code",
    updated: "2026-09-30",
  },
  "M32.2.1.1": {
    status: "BLOCKED",
    why: "waits on memory for the personal-data detector: 1,536 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 1). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_services, ops.overlays, ops.pii); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-g4",
    updated: "2026-09-30",
  },
  "M32.2.1.2": {
    status: "BLOCKED",
    why: "waits on memory for the model server that serves GLiNER: 3,840 MB wanted with its worker and file store, 248 MB unclaimed, measured 2026-09-30 (needs-rupash 120, row 2). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.inference, ops.pii); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-g4",
    updated: "2026-09-30",
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
    status: "IN PROGRESS",
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
    status: "OPEN",
    why: "moved to Wave 3 (needs-rupash 112): closes when every models requirement row has its proof on the install. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes, tables.requirement_check, pages/RequirementChecks.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-09-29",
  },
  "M5.7.1": {
    status: "OPEN",
    why: "moved to Wave 5 (needs-rupash 113): Anthropic and Moonshot answer on the install; OpenAI and DeepSeek are turned off until their accounts are funded. PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (models.default_ladder, models.wire, ops.acceptance_models +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #163's branch M27/console-models-routing (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); +3 more",
    updated: "2026-09-29",
  },
  "M7.1.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.1": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.inference; NOT wired: knowledge.parse_layout. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928",
    updated: "2026-09-29",
  },
  "M7.2.2": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.3": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.parse_paths); open for proof on the install or a decision, not for code",
    updated: "2026-09-29",
  },
  "M7.2.4": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: knowledge.parse_ocr name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-09-29",
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
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.embed, knowledge.embed_policy, knowledge.embed_queue +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928",
    updated: "2026-09-29",
  },
  "M7.3.4": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.embed_queue); open for proof on the install or a decision, not for code",
    updated: "2026-09-29",
  },
  "M7.3.5": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.embedding); open for proof on the install or a decision, not for code",
    updated: "2026-09-29",
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
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.7.11": {
    status: "BLOCKED",
    why: "waits on the owner's choice of upload limit, which sizes the model server; the model server reads 64 MB a document as sized (needs-rupash 119). PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.app_parse_budget); open for proof on the install or a decision, not for code",
    updated: "2026-09-29",
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
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.7.9": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_accounts); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.declaration, connectors.mcp, connectors.transports +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.custom_code, connectors.declaration, connectors.transports +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.4.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.change_signal, connectors.declaration, connectors.freshdesk +10 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.4.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.backfill, ops.acceptance_checks_change_signals, ops.connector_sync +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.6.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.declaration, connectors.laravel, knowledge.connector_rows +10 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M11.6.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.declaration, connectors.freshdesk +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M11.6.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, connectors.lark_base, knowledge.lark_base_rows +5 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.6.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, connectors.lark_wiki, ops.acceptance_checks_lark_wiki +5 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.6.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.ask, connectors.xero +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #142's branch M11/live-read-speed-budget (may be replayed already)",
    updated: "2026-10-06",
  },
  "M11.6.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.hubspot); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.6.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.google_drive, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, connectors.date_range, connectors.declaration +12 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M11.7.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.search_console, knowledge.connector_figures, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in approval_routes, connector_routes, connectors.cloudflare +16 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +7 more",
    updated: "2026-10-06",
  },
  "M11.7.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connector_routes, connectors.declaration, connectors.domains +6 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M11.7.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (api_routes, connectors.slack_messages, knowledge.connector_rows +2 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.7.6": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_change_signals, ops.connector_sync, ops.connector_sync_run +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M11.8.12": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.freshdesk, ops.acceptance_freshdesk_reply, ops.connector_write_run); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +5 more",
    updated: "2026-10-06",
  },
  "M11.8.13": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.8.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_sources); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.8.4": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.13": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.14": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.15": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in connectors.declaration, connectors.google_drive, ops.acceptance_checks_change_signals +3 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M11.9.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_lifecycle_routes, connectors.lark_base, connectors.lark_wiki +15 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +9 more",
    updated: "2026-10-06",
  },
  "M11.9.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.freshdesk, ops.acceptance_checks_connectable, ops.connectable); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M11.9.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M11.9.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_connectable); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M12.2.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, tools.skills); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M12.2.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, ops.acceptance_checks_skill_runs, tools.skills); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M12.2.9": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.sandbox, ops.skill_store, tables.skill +2 more; NOT wired: ops.sandbox_client. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M12.4.15": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M12.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, ops.website_probe, tools.startup +1 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +4 more",
    updated: "2026-10-06",
  },
  "M12.4.5": {
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (resolution.entities); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.7.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (resolution.entities); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M14.8.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_calibration, resolution.calibration_store, resolution_routes +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M15.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.quality, ops.acceptance_retrieval); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M15.3.3": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (memory.signals); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M16.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (chat.thread_store, memory.signals); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +3 more",
    updated: "2026-10-06",
  },
  "M16.2.4": {
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    why: "TRIAGE 2026-10-13 class 2 (partly built): ops/jobs.py models interrupt, CANCELLING/ABORTED/CANCELLED and DEFAULT_TIMEOUT_SECONDS (test_jobs) but nothing calls interrupt and no timeout is enforced in ops/worker.py or queue.py; jobs_routes offers pause/resume/run now only (NO_RUN_CAN_BE_STOPPED_FROM_HERE). NEXT: enforce a per-task timeout in the worker and add a cancel control calling jobs.interrupt over the driver's abort, then a check",
    updated: "2026-10-13",
  },
  "M17.1.5": {
    status: "IN PROGRESS",
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
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Schedule trigger is built: automation_run, automation_run_store.run_automations_now started by schedule_runner, cadence from console/automation_gallery. Connector-event and webhook triggers exist only as orchestration/unattended.TriggerKind (used by adoption.channel_for_trigger); nothing starts a run on either. NEXT: build the two missing trigger paths (connector change event, inbound webhook) into automation_run and show all three kinds on the agent page's New automation PLAN 2026-10-12: also reached from the agent page's New automation (M39.9.2.2); the trigger kinds must be selectable and shown there.",
    updated: "2026-10-13",
  },
  "M17.4.2": {
    status: "IN PROGRESS",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.contract); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in orchestration.contract; NOT wired: orchestration.merge",
    updated: "2026-10-06",
  },
  "M18.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.contract); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.plan); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.fanout name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M18.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.fanout name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M18.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.fanout name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M18.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (core.scope_sql, orchestration.delegation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (core.scope_sql, orchestration.delegation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.delegation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.delegation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.delegation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M18.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.merge name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M18.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.merge name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M18.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: orchestration.merge name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M19.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.launcher, browsing.sandbox); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.runner); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.runner, browsing.wire); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.observation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.launcher, browsing.sandbox); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.1.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.launcher, browsing.sandbox); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.observation, browsing.planning; NOT wired: browsing.shape",
    updated: "2026-10-06",
  },
  "M19.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.envelope); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.approval, browsing.envelope_store, tables.browsing); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.targets); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.egress_addon, browsing.enforcer, browsing.envelope); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.egress_addon, browsing.sandbox); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.3.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.credentials; NOT wired: browsing.shape",
    updated: "2026-10-06",
  },
  "M19.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.credentials); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.credentials); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.credentials); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.4.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.grading, browsing.observation; NOT wired: browsing.verification",
    updated: "2026-10-06",
  },
  "M19.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.grading; NOT wired: browsing.shape",
    updated: "2026-10-06",
  },
  "M19.5.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.observation; NOT wired: browsing.verification",
    updated: "2026-10-06",
  },
  "M19.5.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer, browsing.grading); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.5.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.grading; NOT wired: browsing.verification",
    updated: "2026-10-06",
  },
  "M19.5.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in browsing.grading, browsing.targets; NOT wired: browsing.verification",
    updated: "2026-10-06",
  },
  "M19.6.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: browsing.concurrency name it and nothing imports it. Wire it (route, page or caller); do not rewrite. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.6.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: browsing.concurrency name it and nothing imports it. Wire it (route, page or caller); do not rewrite. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.6.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.sandbox, browsing.sessions); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.6.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.enforcer, browsing.sessions); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.6.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.recording); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.6.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.skill_gate, browsing.targets); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M19.7.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.sessions); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.7.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.approval, browsing.enforcer, browsing.sessions); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M19.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (browsing.autonomy); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-gate_wt",
    updated: "2026-10-06",
  },
  "M20.1.1": {
    status: "OPEN",
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
    status: "OPEN",
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
  "M21.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budget_stop, ops.budgets, ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budgets); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budgets); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budgets); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budget_store, ops.budgets, tables.budget); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-10-06",
  },
  "M21.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.spend, tables.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view, ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view, ops.spend); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view, gate.answer, gate.finish +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #117's branch M8/citations-freshness-abstention (may be replayed already); closed PR #131's branch M8/citations-freshness-abstention-r2 (may be replayed already); closed PR #142's branch M11/live-read-speed-budget (may be replayed already); +7 more",
    updated: "2026-10-06",
  },
  "M21.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.3.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_view); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M21.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (models.pricing); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M22.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.ingest_queue, ops.acceptance_checks_class_pools, ops.admission +7 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M22.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.admission; NOT wired: ops.scaling",
    updated: "2026-10-06",
  },
  "M25.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retention); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retention); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retention); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retention, ops.trace_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retention, ops.retention_store, retention_routes +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.erasure); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.erasure); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.erasure); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.erasure); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.export); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.export); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M25.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.export); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle, identity.starter_pack_sync, ops.staff_sync_run +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle, identity.starter_pack_sync, ops.staff_sync_run +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle, identity.starter_pack_sync, ops.starter_pack_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.record, identity.lifecycle, ops.staff_sync_run +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); closed PR #241's branch M1/staff-sync-diagnostics (may be replayed already); closed PR #75's branch M1/staff-source-connect-leaver-stop (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M26.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M26.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (identity.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.answer, gate.finish, models.metering +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w1-5b; +1 more",
    updated: "2026-10-06",
  },
  "M27.1.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console, ops.telemetry); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.10.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_routes, components/kit/ConfirmDialog.tsx, components/kit/DetailPage.tsx +50 more; NOT wired: components/kit/index.ts, components/ui/badge.tsx, components/ui/card.tsx +8 more. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M13/wire-agent-upgrade, no PR; +23 more",
    updated: "2026-10-06",
  },
  "M27.11.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record, console.organisation +13 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #126's branch M27/departments-page-writes (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already); +5 more",
    updated: "2026-10-06",
  },
  "M27.11.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in credential_routes, ops.acceptance_operations_console_6, ops.credential_catalogue +9 more; NOT wired: pages/Credentials.route.tsx. MORE ELSEWHERE, read before building: closed PR #171's branch M27/console-credentials (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.11.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_agent_console); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.11.15": {
    status: "OPEN",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.govern, directory_routes, govern_routes +10 more; NOT wired: pages/People.tsx. MORE ELSEWHERE, read before building: closed PR #125's branch M27/people-grant-controls (may be replayed already); closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.11.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (directory_routes, ops.acceptance_people_console, pages/Roles.tsx +12 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M33/role-nominations, no PR; closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.11.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in audit.record, channels.api_keys, identity.service_account_store +8 more; NOT wired: pages/ServiceAccount.route.tsx, pages/ServiceAccount.tsx. MORE ELSEWHERE, read before building: closed PR #124's branch M27/service-accounts-page (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w1-1",
    updated: "2026-10-06",
  },
  "M27.11.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_builder_routes, agent_lifecycle_routes, agents.creation +17 more; NOT wired: pages/AgentDraft.tsx, pages/AgentDrafts.route.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M13/wire-agent-upgrade, no PR; +16 more",
    updated: "2026-10-06",
  },
  "M27.11.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_lifecycle_routes, agent_routes, agents.creation +8 more; NOT wired: pages/AgentTemplate.route.tsx, pages/AgentTemplate.tsx. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +9 more",
    updated: "2026-10-06",
  },
  "M27.11.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_skill_console, skill_routes, pages/Skills.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +9 more",
    updated: "2026-10-06",
  },
  "M27.11.9": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in automations_routes, console.automations, ops.automation_change_store +11 more; NOT wired: pages/Automation.route.tsx, pages/Automation.tsx, pages/Automations.route.tsx. MORE ELSEWHERE, read before building: closed PR #174's branch M27/console-automations (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.12.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/operations/StopControl.tsx, pages/operations/StopPage.tsx, pages/stopQuery.ts); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #121's branch M27/halt (may be replayed already); old backup branch recovery/from-windows-20260928-wt-halt",
    updated: "2026-10-06",
  },
  "M27.12.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, console.agent_profile, models.calls +11 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); closed PR #459's branch M21/budget-stops (may be replayed already)",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (navigation_routes, pages/operations/StopControl.tsx, pages/stopQuery.ts); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.17": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.needs_you, console_overview_figures_routes, console_overview_routes +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #157's branch M27/console-stats-overview-r3 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.15.18": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/people/PersonDetailPage.tsx, pages/people/PersonHistory.tsx, pages/people/PersonOverview.tsx +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already); closed PR #295's branch M1/departments-from (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.19": {
    status: "OPEN",
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
  "M27.15.24": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in audit.ledger, audit.record, console.scoped_authority +6 more; NOT wired: pages/Packs.route.tsx. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.25": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/people/PersonSessions.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.26": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (service_account_routes, pages/ServiceAccounts.tsx, pages/service-accounts/AccountActs.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #124's branch M27/service-accounts-page (may be replayed already); closed PR #180's branch M27/console-platform (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.15.27": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.entity_stats, console_stats_routes, models.pricing +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #154's branch M21/record-usage-for-stats (may be replayed already); +9 more",
    updated: "2026-10-06",
  },
  "M27.15.31": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in agent_builder_routes, builder.agent_drafts, ops.acceptance_skill_console +5 more; NOT wired: pages/Approvals.tsx",
    updated: "2026-10-06",
  },
  "M27.15.33": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.entity_stats, console_stats_routes, models.pricing); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #144's branch M27/console-stats-overview (may be replayed already); closed PR #148's branch M27/console-stats-overview-r2 (may be replayed already); closed PR #154's branch M21/record-usage-for-stats (may be replayed already); +9 more",
    updated: "2026-10-06",
  },
  "M27.15.36": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_operations_console_2); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.37": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in knowledge.lifecycle, knowledge.lifecycle_store, knowledge_lifecycle_routes +12 more; NOT wired: pages/Knowledge.route.tsx. MORE ELSEWHERE, read before building: closed PR #160's branch M27/console-knowledge (may be replayed already); closed PR #164's branch M27/console-knowledge-r2 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.15.41": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/classification/ClassificationPage.tsx); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.43": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (binding_routes, ops.acceptance_operations_console_4, pages/channels/ChannelAbout.tsx +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.15.44": {
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
  "M27.16.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in access_request_routes, audit_routes, automations_routes +255 more; NOT wired: pages/AccessReview.route.tsx, pages/AgentTemplate.route.tsx, pages/AgentTemplate.tsx +36 more. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M27/webhook-switch-on-and-replay, no PR; +28 more",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.operate, operate_routes, pages/liveRunsQuery.ts +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.2.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.operate, incident_routes, pages/incidentsQuery.ts +1 more; NOT wired: pages/Incidents.route.tsx",
    updated: "2026-10-06",
  },
  "M27.2.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.operate, pages/operations/StopPage.tsx, pages/stopQuery.ts; NOT wired: pages/Stop.route.tsx",
    updated: "2026-10-06",
  },
  "M27.3.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.govern); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #169's branch M27/console-people-org (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.3.12": {
    status: "OPEN",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.reads); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.5.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.reads); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.5.5": {
    status: "OPEN",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.screens); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-shell",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.budget_stop_store, report_routes, tables.budget_stop +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #459's branch M21/budget-stops (may be replayed already)",
    updated: "2026-10-06",
  },
  "M27.7.17": {
    status: "OPEN",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.staff_source_guide, ops.staff_connect, ops.staff_trial +8 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); closed PR #241's branch M1/staff-sync-diagnostics (may be replayed already); closed PR #75's branch M1/staff-source-connect-leaver-stop (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M27.7.20": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (estate_routes); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #245's branch M16/w3-waiting (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M27.7.22": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (estate_routes, ops.memory_store, tables.learning +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #245's branch M16/w3-waiting (may be replayed already); closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M27.7.23": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (artifact_routes, pages/Artifacts.tsx, pages/operations/ArtifactsPage.tsx); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M27.7.24": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, erasure_routes, ops.acceptance_operations_console_3 +10 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M27.7.25": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install_routes, pages/Install.tsx, pages/Updates.tsx +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w0b",
    updated: "2026-10-06",
  },
  "M27.7.26": {
    status: "OPEN",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #163's branch M27/console-models-routing (may be replayed already)",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.canaries); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_skill_pins, ops.canaries); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.canaries, ops.canary_run, ops.schedule); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.feedback); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.feedback); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M28.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.sampling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M29.1.12": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.1.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.manifest); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in tables.plugin; NOT wired: ops.plugin_registry",
    updated: "2026-10-06",
  },
  "M29.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.lifecycle); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (plugins.points); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M29.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in plugins.contract; NOT wired: plugins",
    updated: "2026-10-06",
  },
  "M3.7.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.catalogue); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.release, ops.tunnel); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.backup_manifest, ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.backup_manifest, ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.recovery; NOT wired: ops.backup_ladder",
    updated: "2026-10-06",
  },
  "M30.3.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.recovery); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.3.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in console.recovery_view, install_routes; NOT wired: ops.backup_ladder",
    updated: "2026-10-06",
  },
  "M30.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.reliability); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.crash); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M30.4.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.reliability; NOT wired: deployment.database",
    updated: "2026-10-06",
  },
  "M30.5.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.answer, gate.finish, ops.reliability +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #117's branch M8/citations-freshness-abstention (may be replayed already); closed PR #131's branch M8/citations-freshness-abstention-r2 (may be replayed already); closed PR #142's branch M11/live-read-speed-budget (may be replayed already); +7 more",
    updated: "2026-10-06",
  },
  "M30.5.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (launch, ops.reliability); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.tracing); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_audit, ops.tracing, trace_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.1.2.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, ops.acceptance_checks_services, ops.ledger_export +3 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.2.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.pii); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-g4",
    updated: "2026-10-06",
  },
  "M32.3.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.3.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.object_store, ops.storage); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.5.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, components/DataTable.tsx, components/paging.ts +2 more; NOT wired: pages/Records.tsx. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-1; old backup branch recovery/from-windows-20260928-wt-w1-2; old backup branch recovery/from-windows-20260928-wt-w1-2a",
    updated: "2026-10-06",
  },
  "M32.5.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in components/GraphCanvas.tsx, components/ProcedureCanvas.tsx, components/TraceGraph.tsx +4 more; NOT wired: pages/Audit.route.tsx, pages/audit/TracePage.tsx",
    updated: "2026-10-06",
  },
  "M32.6.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.automation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.6.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.automation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M32.6.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.automation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.1.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.1.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.2.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.adapter, channels.correction, channels.lark); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.2.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.feedback); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.2.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.3.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.3.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.3.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.guide_docs name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M34.3.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.guide_docs name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M34.3.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.install_docs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M34.3.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.install_docs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.search); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.search, locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.2.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M35.2.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/Ask.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #117's branch M8/citations-freshness-abstention (may be replayed already); closed PR #131's branch M8/citations-freshness-abstention-r2 (may be replayed already); closed PR #143's branch M8/citations-freshness-abstention-r3 (may be replayed already); +7 more",
    updated: "2026-10-06",
  },
  "M35.2.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-ui-foundation",
    updated: "2026-10-06",
  },
  "M35.3.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in approval_routes, gate.suspension_store, tables.suspension +3 more; NOT wired: pages/Approvals.tsx. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-w03",
    updated: "2026-10-06",
  },
  "M35.3.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (locale); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-ui-foundation",
    updated: "2026-10-06",
  },
  "M36.1.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.ledger_partitions, ops.partitioning, tables.telemetry); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.1.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.replica_store, ops.streaming_replica); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.read_replica, ops.replica_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.read_replica, ops.replica_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.1.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_report_view, ops.spend_store, tables.spend); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M36.1.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.spend_report_view, ops.spend_store, tables.spend); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already)",
    updated: "2026-10-06",
  },
  "M36.1.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.1.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.split); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.1.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.federation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.2.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.federation); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.2.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.2.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.screening); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.2.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (gate.screening); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.2.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.2.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: ops.scaling name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M36.2.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.admission); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M36.2.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.admission); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.1.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (migration.inventory); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.1.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (migration.inventory); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.1.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (migration.inventory); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.carry name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.carry name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.carry name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.carry name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.parallel name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.parallel name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.parallel name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.decommission name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.decommission name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.decommission name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.1.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.decommission name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.skills name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.skills name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.skills name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.skills name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.rebuild name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.rebuild name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.rebuild name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.rebuild name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.learning name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.learning name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.2.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: migration.learning name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M37.3.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (adoption, console.adoption_view, gate.finish +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #154's branch M21/record-usage-for-stats (may be replayed already); closed PR #167's branch M38/migration-train-0118-0138-0139 (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w1-8",
    updated: "2026-10-06",
  },
  "M37.4.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (launch); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.4.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (launch); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.4.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (launch); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.controls, ops.schedule); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.controls, ops.schedule_runner, ops.schedule_store +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #84's branch M5/model-health-routing-residency (may be replayed already); old backup branch recovery/from-windows-20260928; old backup branch recovery/from-windows-20260928-wt-automation-memory; +2 more",
    updated: "2026-10-06",
  },
  "M37.5.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.controls); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.alerting); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.alerting, ops.controls); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.alerting); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retune); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M37.5.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.retune); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.2.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agents.install_store, memory.turn, ops.memory_store); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #252's branch M6/w3-fastlane-role (may be replayed already); closed PR #255's branch M16/w3-confirmed (may be replayed already); closed PR #299's branch M8/w2-escalation (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M38.2.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (automation_schedule_routes, console.automation_schedule, ops.automation_run +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #84's branch M5/model-health-routing-residency (may be replayed already); old backup branch recovery/from-windows-20260928-wt-automation-memory; old backup branch recovery/from-windows-20260928-wt-g2; +1 more",
    updated: "2026-10-06",
  },
  "M38.3.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.lark, digest_routes, ops.acceptance_checks_digest +6 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_digest, ops.digest, ops.digest_run); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_checks_digest, ops.digest, ops.digest_run); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M38.3.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (channels.lark, digest_routes, ops.acceptance_checks_digest +7 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.1.1.1": {
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_report +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_store +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.5.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.agent_output, ops.acceptance_workspace, ops.artifact_report); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +4 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.5.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_artifact_routes, console.agent_output, ops.acceptance_workspace +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.6.2.3": {
    status: "OPEN",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.acceptance_workspace); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; branch M39/channel-rows, no PR; +10 more",
    updated: "2026-10-06",
  },
  "M39.8.5": {
    status: "OPEN",
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
    status: "IN PROGRESS",
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
    status: "IN PROGRESS",
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
    status: "IN PROGRESS",
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
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_library.my_skills/PersonalSkill/origin_of (source, version, review state) are built; only origin_of has callers (agent_routes). The skills library routes (skill_routes GET /skills/library) are the administrator's and show every skill, not a member's personal ones. NEXT: add GET /me/skills calling my_skills over ops.skill_store rows owned by the person",
    updated: "2026-10-13",
  },
  "M40.3.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Import from repository at a commit, from a URL, pasted SKILL.md, zip and procedure files exist (skill_routes POST /skills, /skills/imports, /skills/procedures) but behind skill_library.may_add, an administrator's write. member_library.add_skill is called only from skill_routes/acceptance. No member-scoped personal import. NEXT: let a member add a personal skill: route calling add_skill at the person's own ownership, with a personal-state row",
    updated: "2026-10-13",
  },
  "M40.3.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_library.submit_for_review/Submission built, no caller. Skill review queue exists (POST /skills/{digest}/review, may_review) for administrators. NEXT: add POST /me/skills/{id}/submit calling submit_for_review and moving the row to the department's review queue in ops.skill_store",
    updated: "2026-10-13",
  },
  "M40.3.2.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_library.attach_refusals (personal skill only for own agents until approved) has no caller. Admin side: skill_library.assignment refuses an unapproved skill via attach_skill/pin_skill, but no personal-skill state exists. NEXT: wire attach_refusals into skill_library.assignment and the personal agent builder once personal skills are stored",
    updated: "2026-10-13",
  },
  "M40.3.3.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Artifacts are listed per agent (agent_artifact_routes GET artifacts, latest, download) and estate-wide for admins (artifact_routes /govern/artifacts). member_library.produced_for_me (everything by any agent for this person) has no caller and no route. NEXT: add GET /me/artifacts calling produced_for_me over agent.artifact rows with caller_id = the person; add to MyWorkspace",
    updated: "2026-10-13",
  },
  "M40.3.3.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_library.share/open_share/Share built, no caller, no table for a share row (shape has no entitlement by design). NEXT: add a share table plus POST /me/artifacts/{id}/share calling share and GET using open_share; needs a migration number",
    updated: "2026-10-13",
  },
  "M40.4.1.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): MyWorkspace shows each learned statement with stated/inferred and confidence; the weekly digest (learning_told) names signal kinds as evidence. member_activity.learned_about_me (statement plus evidence) has no caller, so the page shows no evidence. NEXT: call learned_about_me from mine_routes and add evidence (signal kinds) to MineLearnedView",
    updated: "2026-10-13",
  },
  "M40.4.1.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): One-click undo per item built and wired: POST /me/memory/forget and /me/learning/undo (MyWorkspace Forget, digest undo link). Undo-all: member_activity.undo_all exists but has no caller (govern_estate lists undo_all as a refused bulk word for the console). NEXT: add POST /me/memory/forget-all over StoredMemoryRecords.undo for the person's own memories and an Undo all button",
    updated: "2026-10-13",
  },
  "M40.4.1.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.opt_out/LearningOptOut built (states the cost), no caller, no stored flag, and the memory formation path (chat/remember, memory.turn) reads no opt-out. NEXT: store a per-person opt-out (ops.setting or table), check it in memory formation, expose POST /me/learning/opt-out",
    updated: "2026-10-13",
  },
  "M40.4.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.what_is_stored/StoredAboutMe built, no caller. thread_routes export (export_my_history) covers conversations only; /me/workspace shows five cards but not 'what is stored and where'. NEXT: add GET /me/stored calling what_is_stored and a card on MyWorkspace",
    updated: "2026-10-13",
  },
  "M40.4.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member_activity.request_deletion/route (maps to ops.erasure stores) built, no caller. Erasure queue exists for admins (erasure_routes POST /govern/erasures needs admin:erasure; deletion_rows lets the subject read their own). No member self-request route. NEXT: add POST /me/deletion-request filing into the erasure queue as a request (not an erase) and showing route()'s four lists",
    updated: "2026-10-13",
  },
  "M40.4.2.4": {
    status: "IN PROGRESS",
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
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): member.connections.disconnect (revoke first, refuse on failure) built but no TokenRevoker implementation exists and no route; MyAccounts.tsx has no disconnect control. Vault slot connector_person_oauth_slot exists to delete. NEXT: implement a vault-backed TokenRevoker (vendor revoke then slot delete), add DELETE /me/accounts/{connector}, then a check",
    updated: "2026-10-13",
  },
  "M40.5.1.4": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.inherited/personally_connected built, no caller; /me/accounts lists only sources the person may connect, with no provenance field, so department-provided connections are not shown as inherited. NEXT: add provenance to MyAccountView from inherited() and render inherited ones without a disconnect control",
    updated: "2026-10-13",
  },
  "M40.5.2.1": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): GET /me/channels (binding_routes, MyChannels.tsx) lists channels switched on and bound, with bound_at. 'Primary' is not modelled: member.connections.reachability/ChannelPreference/reachable_on are uncalled and nothing stores a primary. NEXT: store a primary channel per person and surface it through reachability in my_channels view",
    updated: "2026-10-13",
  },
  "M40.5.2.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.ChannelPreference/wants built, no caller, no store; ops/notices.py rejects per-person preference and keeps one install-wide switch per notice kind. NEXT: add a preference store and make ops/notices senders ask wants() per person",
    updated: "2026-10-13",
  },
  "M40.5.2.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 3 (built, not wired): member.connections.channels_that_may_approve built, no caller. approval_cards sends Lark cards to every addressed binding, switched install-wide by INSTALL_LARK_CARD_APPROVALS; there is no per-approver choice. NEXT: store the approver's console-or-Lark choice and have approval_cards.send_raised honour it via channels_that_may_approve",
    updated: "2026-10-13",
  },
  "M40.5.2.4": {
    status: "IN PROGRESS",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.variables, ops.install_settings, setup_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.variables); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.install_docs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.2.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.install_docs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.variables); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in ops.install_docs; NOT wired: deployment.database",
    updated: "2026-10-06",
  },
  "M42.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.release); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.release); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.3.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.screens, console.version_view, deployment.release_feed +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-w0b",
    updated: "2026-10-06",
  },
  "M42.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.install_script, deployment.installer); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-g4",
    updated: "2026-10-06",
  },
  "M42.5.10": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.install_settings, setup_routes, setup_wizard); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #180's branch M27/console-platform (may be replayed already); old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-steward",
    updated: "2026-10-06",
  },
  "M42.5.11": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_wizard); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-steward",
    updated: "2026-10-06",
  },
  "M42.5.12": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_routes, setup_wizard); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-steward",
    updated: "2026-10-06",
  },
  "M42.5.13": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_wizard); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-steward",
    updated: "2026-10-06",
  },
  "M42.5.14": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console_static, deployment.vault_setup, ops.install_settings +6 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +11 more",
    updated: "2026-10-06",
  },
  "M42.5.15": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.5.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.installer, deployment.variables); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.5.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.app_environment, deployment.installer, firstrun +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w0e",
    updated: "2026-10-06",
  },
  "M42.5.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_wizard); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.5.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_wizard); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.5.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.staff_directories, setup_staff_routes, components/StaffListCheck.tsx +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-integrate2; old backup branch recovery/from-windows-20260928-wt-steward; old backup branch recovery/from-windows-20260928-wt-w03; +1 more",
    updated: "2026-10-06",
  },
  "M42.5.8": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (setup_wizard); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M42.5.9": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (components/ConnectSource.tsx, pages/FirstRun.tsx, pages/connectorsQuery.ts +1 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +8 more",
    updated: "2026-10-06",
  },
  "M42.6.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.app_environment, deployment.install_script, deployment.installer +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M16/w3-learning-tables, no PR; +12 more",
    updated: "2026-10-06",
  },
  "M42.6.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (pages/Ask.tsx, pages/askQuery.ts); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #117's branch M8/citations-freshness-abstention (may be replayed already); closed PR #131's branch M8/citations-freshness-abstention-r2 (may be replayed already); closed PR #143's branch M8/citations-freshness-abstention-r3 (may be replayed already); +7 more",
    updated: "2026-10-06",
  },
  "M42.6.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.skill_library, ops.skill_store, skill_routes +3 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +14 more",
    updated: "2026-10-06",
  },
  "M42.6.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.record, connector_routes +15 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M12/w2-skill-packages, no PR; branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; +21 more",
    updated: "2026-10-06",
  },
  "M42.6.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (deployment.windows_helper); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M5.7.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_model_routes, agent_routes, agents.model +10 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/w3-actions-stack, no PR; branch M13/w3-runtime-side-effects, no PR; branch M13/wire-agent-upgrade, no PR; +24 more",
    updated: "2026-10-06",
  },
  "M6.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (cache, gate.caches); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, cache, gate.caches +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (app, cache, gate.caches +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M6.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in app, cache, gate.caches +2 more; NOT wired: ops.effects",
    updated: "2026-10-06",
  },
  "M6.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in api_routes, app, gate.fast_lane +14 more; NOT wired: pages/Rules.route.tsx. MORE ELSEWHERE, read before building: branch M16/w3-learning-tables, no PR; branch M39/channel-rows, no PR; branch M39/group-install, no PR; +6 more",
    updated: "2026-10-06",
  },
  "M7.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (install, knowledge.ingest, knowledge.scanners +5 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #129's branch M7/links-scanning-queue (may be replayed already); closed PR #217's branch M7/w2-knowledge-3 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); +2 more",
    updated: "2026-10-06",
  },
  "M7.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.uploads, ops.acceptance_ingest); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #217's branch M7/w2-knowledge-3 (may be replayed already); closed PR #219's branch M7/w2-knowledge-4 (may be replayed already); closed PR #232's branch M7/w2-knowledge-5 (may be replayed already); +1 more",
    updated: "2026-10-06",
  },
  "M7.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (knowledge.ingest, knowledge.ingest_queue, knowledge.uploads +7 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #129's branch M7/links-scanning-queue (may be replayed already); closed PR #160's branch M27/console-knowledge (may be replayed already); closed PR #164's branch M27/console-knowledge-r2 (may be replayed already); +4 more",
    updated: "2026-10-06",
  },
  "M7.7.7": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (requirement_check_routes); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M39.10.1": {
    status: "OPEN",
    why: "P1. Partly built: agents/model.py has Visibility (GLOBAL, DEPARTMENT, PERSONAL) with an owner_id, and the agent page shows its audience. What is missing is the kind named as a choice at creation and on the page. REUSE agents.model.AgentAudience, agents.creation, agent_routes.",
    updated: "2026-10-12",
  },
  "M39.10.2": {
    status: "OPEN",
    why: "P1. Partly built: agents/creation.py makes a personal agent for its maker (AgentAudience PERSONAL, owner_id) and brain.member_activity.build_personal_agent materialises one. What is missing is the builder's own flow for a person to make one and the capability rule that only an administrator may make a team agent. REUSE agents.creation, agents.authoring, member_activity.",
    updated: "2026-10-12",
  },
  "M39.10.3": {
    status: "OPEN",
    why: "P1. DEPENDS on M39.10.1. Audience scope for PERSONAL is the owner (agents/model.py scope_for); check that every list, the gallery and the oversight view follow it, with no count of hidden agents.",
    updated: "2026-10-12",
  },
  "M39.10.4": {
    status: "OPEN",
    why: "P1. DEPENDS on M11.7.6 and needs item 173's steps done by the owner. Google Workspace is read per person with that person's own token (brain.connectors, My workspace); what is missing is attaching that connection to a personal agent and refusing anyone else.",
    updated: "2026-10-12",
  },
  "M39.10.5": {
    status: "OPEN",
    why: "P2. DEPENDS on the owner's answer to needs item 189 (recommended C, built as A first). A team agent has no personal Google connection; a shared mailbox is a connection an administrator makes; a person's own mail in a private conversation only, never a room, memory or knowledge item.",
    updated: "2026-10-12",
  },
  "M39.10.6": {
    status: "OPEN",
    why: "P1. Install check for the first, second and third leaves, with reserved people; held if it uses a made-up mailbox.",
    updated: "2026-10-12",
  },
  "M39.10.7": {
    status: "OPEN",
    why: "P2. Browser proof of the create flow's kind choice.",
    updated: "2026-10-12",
  },
  "M39.9.1.1": {
    status: "OPEN",
    why: "P1, the core of the Knowledge requirement. Today the API lists Knowledge as one of seven workspace tabs (console/workspace.Tab.KNOWLEDGE) and the Profile draws a read-only card of what the agent's rule reaches (AgentCapabilities.tsx KnowledgeCard: M39.2.3.1, .3, .4), but the console's tab strip draws only Conversations, Automations, Memory, Artifacts and Settings, so there is no Knowledge section and no list of items. REUSE: the workspace tab read, brain.knowledge.item (retrievable, badge), console/agent_tabs.KnowledgeScope. REMAINING: a paged read of the items this agent draws on at the reader's reach, and AgentKnowledge.tsx with its empty state. M39.1.2.2 is reopened for the missing tabs.",
    updated: "2026-10-12",
  },
  "M39.9.1.2": {
    status: "OPEN",
    why: "P1. DEPENDS on M39.9.1.1 and on the owner's answer to needs item 176 (where an item added from an agent lives; built as recommended, company layer). REUSE: brain.knowledge.uploads.receive_upload, knowledge_intake_routes (POST /knowledge/uploads and the queued door), console/agent_tabs.plan_addition (its `reached` answer). REMAINING: an agent-scoped add route calling the door and returning plan_addition's answer, and the form. Today the card's 'Add a document or a link' only links away to /knowledge. M39.2.3.2 is reopened.",
    updated: "2026-10-12",
  },
  "M39.9.1.3": {
    status: "OPEN",
    why: "P1. DEPENDS on M39.9.1.1 and item 176. REUSE: brain.knowledge.uploads.receive_link, POST /knowledge/links (fetched once, the company's own copy), brain.tools.fetch (address checks on every redirect), plan_addition. REMAINING: the agent-scoped add route and form, shared with M39.9.1.2.",
    updated: "2026-10-12",
  },
  "M39.9.1.4": {
    status: "OPEN",
    why: "P1. DEPENDS on M39.9.1.2 and M39.9.1.3. REUSE: the 'Widen what it draws on, through a draft' action already on the Knowledge card (onWiden), agents/authoring drafts. REMAINING: name the unreached item beside it and make the one next step a press, never a silent change to every agent (ADDING_AN_ITEM_IS_NOT_THE_SAME_AS_REACHING_IT).",
    updated: "2026-10-12",
  },
  "M39.9.1.5": {
    status: "OPEN",
    why: "P2. DEPENDS on M39.9.1.1. REUSE: the knowledge lifecycle on the Knowledge page (review dates, replace, retire) and brain.knowledge.uploads for a refetch. REMAINING: the same affordances from the agent's section, refusing for whoever may not change the item as the Knowledge page does.",
    updated: "2026-10-12",
  },
  "M39.9.1.6": {
    status: "OPEN",
    why: "P1, a safety property. DEPENDS on M39.9.1.1. Items the reader may not read are absent with no count of what is hidden (DENIED and ABSENT are indistinguishable), and the agent's run reaches the intersection with the caller. REUSE: brain.knowledge.item.retrievable and the existing E_run machinery; REMAINING: the list read's tests and an install check that a colleague without the grant sees nothing.",
    updated: "2026-10-12",
  },
  "M39.9.1.7": {
    status: "OPEN",
    why: "P2. DEPENDS on M39.9.1.1. REUSE: the Capabilities tab's connector rows (M39.2.1.x) and skill chips (M39.2.2.x). REMAINING: show them in the Knowledge section by kind, each linking to the page that owns it, with no second copy of their data.",
    updated: "2026-10-12",
  },
  "M39.9.1.8": {
    status: "OPEN",
    why: "P1, the proof the install must show. DEPENDS on M39.9.1.1 to M39.9.1.4 and M39.9.1.6; written as an install check (see .scratch/assign/COMMON.md): reserved people, rolled-back writes, NOT_RUN where no object store is connected.",
    updated: "2026-10-12",
  },
  "M39.9.1.9": {
    status: "OPEN",
    why: "P2. The browser proof, DEPENDS on M39.9.1.1 to M39.9.1.4. REUSE: the harness in e2e/ (two-tabs, policy specs) and console/tests/support/pageCases.",
    updated: "2026-10-12",
  },
  "M39.9.2.1": {
    status: "OPEN",
    why: "P2. Today an agent's Automations section is a gallery of outcome templates with a one-step install, a list of this agent's automations and per-automation pause, resume, reschedule, remove and run history (M39.6.1.x, automation_gallery_routes, automations_routes, AgentAutomations), and an installed automation runs through the `automation_run` control; there is no way to start a new one that is not a template. REUSE: the gallery and install route (confirmation digest), the automation run store. REMAINING: the New automation entry, a description-in-words path and the create route; DEPENDS on M17.4.2 (outcome templates and stored, versioned workflow data) for anything beyond a template with changed settings.",
    updated: "2026-10-12",
  },
  "M39.9.2.2": {
    status: "BLOCKED",
    why: "P2. WAITS ON M17.4.1 (trigger kinds: schedule, connector event, webhook; orchestration.unattended is built but not reachable from the page) and on the condition list, which no task defines yet: the list of named conditions is a decision for needs item 177 if the owner wants it widened beyond what is built. Today a template carries a schedule only.",
    updated: "2026-10-12",
  },
  "M39.9.2.3": {
    status: "OPEN",
    why: "P2. DEPENDS on M39.9.2.1. REUSE: the agent's ceiling and leash (gate/leash, runtime side effects held for a person, #466) and the automation principal rule (M39.6.2.1). REMAINING: name the skills and tools an automation may use on its card and refuse an instruction that exceeds the agent's ceiling.",
    updated: "2026-10-12",
  },
  "M39.9.2.4": {
    status: "OPEN",
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
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No workflow definition store: searched src for workflow, step data and versioned steps. Neighbours: builder/procedure.py (drawn procedure to SKILL.md, acyclic, MAX_STEPS), builder/draft_store (revisions), ops/automation.StepKind (canvas flows), automation_run store. Register rows OWN-63, OWN-64, OWN-75.",
    updated: "2026-10-13",
  },
  "M17.6.2": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): The door exists for canvas steps: automation_routes.tool_call runs one tool through the gate as the owner at flow_reach with the projected catalogue and redactor (acceptance_checks_automation, M32.6.2.2). Skill steps, a workflow runner and per-step leash and meter accounting are not built. NEXT: build the step executor calling the same gate path for tool, connector read and skill steps and recording each in spend",
    updated: "2026-10-13",
  },
  "M17.6.3": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No named, schema-checked step outputs: nothing in src models step outputs or a reads-only-earlier rule (searched workflow, outputs, schema near automation and builder).",
    updated: "2026-10-13",
  },
  "M17.6.4": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No step conditions or skipped-with-reason records. builder/procedure.py has a scope-predicate conditional for drawn skills, and ops/automation.StepKind has branch for the canvas, but neither records a skipped step.",
    updated: "2026-10-13",
  },
  "M17.6.5": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No parallel step support: searched for parallel and fan-in; orchestration/fanout.py is multi-agent fan-out with a budget, not workflow steps with a gap-recording join.",
    updated: "2026-10-13",
  },
  "M17.6.6": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No per-step retry limit or failure path. Reusable parts exist: jobs.next_attempt_at and retry_gaps (backoff), idempotency.issue_once (retry only through the key), outbox.plan_next; none is attached to workflow steps.",
    updated: "2026-10-13",
  },
  "M17.6.7": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Automation runs emit automation.run_finished via the outbox (ops/automation_run); repeated failures pause with a notice (FAILURES_BEFORE_PAUSE, automation_paused_told). Missing: workflow and failed step named in the signal, and a learning candidate on repeated step failure. Payload fields not verified. NEXT: add workflow id and failing step to the event and open a learning candidate through knowledge/candidates after N failures of one step",
    updated: "2026-10-13",
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
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Scheduler built: ops/schedule.py (what is owed), schedule_runner.py with pg_advisory_xact_lock per control (schedule_store), started by ops/worker. Alert for a control with no run in its window: controls.overdue has no caller and notices.py says nothing sends control_not_run. NEXT: call controls.overdue from the worker tick and send control_not_run through tell_later to the operations alert holder; then a check",
    updated: "2026-10-13",
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
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): Gallery ships weekly_work_summary, unanswered_questions and source_freshness (console/automation_gallery BUILT_IN); no daily brief, no deal capture from group chats, no drafted email replies. Reuse: ops/digest_delivery (evening digest), channels/email, hubspot connector, automation_run.TASKS.",
    updated: "2026-10-13",
  },
  "M17.7.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): tell_later.tell is the one sender (person's last-used channel or mail relay) and six notice kinds use it; ops/notices.py lists 14 kinds and 'no channel is chosen yet, so nothing sends it' for the rest. The Notifications screen shows sent_by but no undelivered state per notice. NEXT: give each remaining notice kind a sender through tell_later and record failed deliveries for the Notifications screen to show as undelivered",
    updated: "2026-10-13",
  },
  "M17.7.7": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No workflow assignment exists, so no refusal of an unassigned workflow through an agent; depends on M17.6.1's workflow data and an agent-workflow link in the agent manifest or install.",
    updated: "2026-10-13",
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
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): Skills page shows 'Try it out' as UnavailableAction with 'Coming soon' (console/src/pages/skills/skillActions.ts tryOut). Rehearsal route exists for reviewers (skill_routes POST /skills/{digest}/rehearsals) but is not a conversation.",
    updated: "2026-10-13",
  },
  "M40.7.3": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Attach a file to the web composer is built (console/src/pages/AskAttach.tsx, thread_routes POST /threads/attachments, M12.3.6). Dictation is not: no speech tool is registered anywhere in src. NEXT: register a speech-to-text tool in the tool registry, add a record control on Ask that posts audio and fills the text; keep the transcription at the person's reach",
    updated: "2026-10-13",
  },
  "M40.7.4": {
    status: "BLOCKED",
    why: "TRIAGE 2026-10-13 class 5 (not code, owner or blocked): A browser proof for a member who administers nothing: needs a member-only person signed in on the install and a person or headless-browser walk of Ask, /me, approvals, accounts, memory. Waits on the owner's install (person-run demonstration) and the earlier M40 leaves.",
    updated: "2026-10-13",
  },
  "M40.7.5": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Talk to an agent is built: Ask page agent picker (askQuery agent field, gate.select.select_agent, gate.roster). 'Start a task' as a distinct entry and gate routing a task to a callable agent is not: without an agent /answer uses the default agent at the person's own reach. NEXT: add a start-a-task entry on Ask posting without an agent, and a gate step choosing a callable agent from the roster; then a check",
    updated: "2026-10-13",
  },
  "M40.7.6": {
    status: "IN PROGRESS",
    why: "TRIAGE 2026-10-13 class 2 (partly built): Per-agent conversation list carries run state answered/declined/degraded/failed (console/agent_conversations.py, tables.chat.RunState). The member's own GET /threads has no state and nothing reads job or suspension records for running or waiting; no failed-step text. NEXT: extend ThreadSummaryView with state read from ops.jobs and gate.suspension_store plus the failing step",
    updated: "2026-10-13",
  },
  "M40.7.7": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No personal project: no table or route groups threads and files (searched tables, thread_routes, chat/). Attachments exist per thread only (thread_routes ATTACHMENTS_PATH).",
    updated: "2026-10-13",
  },
  "M40.7.8": {
    status: "OPEN",
    why: "TRIAGE 2026-10-13 class 4 (unbuilt): No starter prompts: searched src and console for starter/suggested question, only Ask page exists. Inputs exist: agent skills (skill pins) and the knowledge reach.",
    updated: "2026-10-13",
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
