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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.jobs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.jobs, ops.queue, ops.worker); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.jobs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.jobs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.jobs); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.checkpoint_store); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.crash); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.crash); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.crash); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.crash); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in channels.adapter, channels.email, channels.lark +9 more; NOT wired: ops.effects. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-w1-6",
    updated: "2026-10-06",
  },
  "M17.3.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.idempotency); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (connectors.write_verification, ops.idempotency); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.3.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.idempotency); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.3.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.idempotency); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.4.6": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (orchestration.unattended); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.5.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.outbox, ops.outbox_store, ops.webhook_delivery +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.5.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (ops.outbox); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M17.5.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.subscribers, ops.outbox, ops.outbox_store +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.workspace, ops.acceptance_checks_agent_page, pages/agents/AgentDetailPage.tsx); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: branch M13/wire-agent-upgrade, no PR; branch M16/w3-learning-tables, no PR; branch M33/train-0200, no PR; +12 more",
    updated: "2026-10-06",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (agent_capability_routes, console.agent_tabs); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: closed PR #235's branch M39/w3-agent-workspace-5 (may be replayed already); closed PR #254's branch M39/w3-agent-workspace-6 (may be replayed already); closed PR #257's branch M39/w3-agent-workspace-7 (may be replayed already); +1 more",
    updated: "2026-10-06",
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
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (automation_paused_told, console.agent_automations, ops.automation_run +2 more); open for proof on the install or a decision, not for code. MORE ELSEWHERE, read before building: old backup branch recovery/from-windows-20260928-wt-automation-memory",
    updated: "2026-10-06",
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
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (console.reads, member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.1.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in pages/approvals/ApprovalsPage.tsx; NOT wired: pages/Approvals.tsx",
    updated: "2026-10-06",
  },
  "M40.1.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.shell); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.2.2.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.1.5": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.3.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.3.3.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_library); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member_activity); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.4.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (audit.ledger, audit.reads, audit.record +1 more); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.2.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.2.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.2.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.5.2.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT AND WIRED on main (member.connections); open for proof on the install or a decision, not for code",
    updated: "2026-10-06",
  },
  "M40.6.1.1": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: member.approvals name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M40.6.1.2": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): PARTLY WIRED: wired in audit.ledger, audit.record, console.approvals; NOT wired: member.approvals",
    updated: "2026-10-06",
  },
  "M40.6.1.3": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: member.approvals name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
  },
  "M40.6.1.4": {
    status: "OPEN",
    why: "PRIOR WORK (checked 2026-10-07, branches of the last 8 weeks): BUILT, NOT WIRED: member.approvals name it and nothing imports it. Wire it (route, page or caller); do not rewrite",
    updated: "2026-10-06",
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
