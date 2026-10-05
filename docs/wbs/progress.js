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
    why: "built (M1/people-status): People shows where the staff list puts each person and their employment type, with filters; proved on the install with M1.6.15",
    updated: "2026-09-30",
  },
  "M1.6.14": {
    status: "READY FOR TESTING",
    why: "built (M1/people-status): somebody the list says is suspended, gone or never activated, or of a type not allowed, is disabled on the next sync and their page says why; the last administrator is never kept out; proved on the install with M1.6.15",
    updated: "2026-09-30",
  },
  "M40.7.1": {
    status: "READY FOR TESTING",
    why: "built (M1/relay-to-sign-in): every release gives the sign-in realm the mail relay saved on Notifications, through the step that already signs in to Keycloak inside its container, writing only when the relay changed and leaving a realm with no relay alone; an install check compares the host the realm reported with the relay's. Not built: hiding Forgot password while no relay is set. Proved on the install when a release has run and a reserved person's Forgot password email arrives",
    updated: "2026-09-30",
  },
  "M1.6.16": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-accounts): the staff sync makes each active person's sign-in account and sends nobody anything; proved when a release has set up the accounts client and a reserved person's Forgot password sets their password and second factor (M1.6.18)",
    updated: "2026-09-30",
  },
  "M1.6.17": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-accounts): a leaver's or suspended person's account the sync made is closed on the next sync and their Brain sessions ended; proved on the install with a reserved leaver (M1.6.18)",
    updated: "2026-09-30",
  },
  "M1.10.1": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-are-people): every active person on the staff list is made a Brain person by the staff sync without the sign-in service, joined by their address's digest; proved on the install with M1.10.3",
    updated: "2026-09-30",
  },
  "M1.10.2": {
    status: "READY FOR TESTING",
    why: "built (M1/staff-are-people): Sync now on Staff sources asks the worker for the scheduled staff sync and the page says when it last and next runs; proved on the install with M1.10.3",
    updated: "2026-09-30",
  },
  "M1.8.3": {
    status: "READY FOR TESTING",
    why: "built (PR #98): the staff sync writes a head's audit reads over their department's people and Audit is on the department menu; proved when a department head signs in and sees only their people's activity",
    updated: "2026-09-28",
  },
  "M1.8.5": {
    status: "BLOCKED",
    why: "moved to Wave 2 (needs-rupash 97): the web part is the owner's sign-in check (needs-rupash 91, check 1); the chat part needs Wave 2's Lark chat channel",
    updated: "2026-09-28",
  },
  "M1.8.8": {
    status: "OPEN",
    why: "moved to Wave 4 (needs-rupash 112): closes when every permissions requirement row has its proof on the install",
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
    why: "Slack is connectable (#288): signed events in, answers on the bot token with the room read like Lark's, Connect Slack from an app manifest, and an install check; the owner's workspace proves the vendor's half",
    updated: "2026-09-30",
  },
  "M10.5.2": {
    status: "READY FOR TESTING",
    why: "Teams is connectable (M10/channel-teams): Bot Framework tokens verified against Microsoft's published keys, the bot's App ID and the pinned tenant, answers in the chat on a token exchanged at the tenant's login, Connect Teams from an Azure Bot, and an install check; the owner's tenant proves the vendor's half",
    updated: "2026-09-30",
  },
  "M10.5.6": {
    status: "READY FOR TESTING",
    why: "email is connectable (#285) by reading an ordinary mailbox over IMAP, the first choice (#296), or by Cloudflare Email Routing; answers leave by the install's relay; install checks for both; the owner's real mail proves the vendor's half",
    updated: "2026-09-30",
  },
  "M10.5.4": {
    status: "READY FOR TESTING",
    why: "Telegram is connectable (M10/channel-telegram): saving the bot's username and token registers this install's events address with Telegram, updates carry a header made from the token, answers go out with sendMessage, and an install check; the owner's bot proves the vendor's half",
    updated: "2026-09-30",
  },
  "M10.5.3": {
    status: "READY FOR TESTING",
    why: "WhatsApp is connectable (M10/channel-whatsapp): Meta's signature checked over the exact bytes, its GET check of the address answered for the verify token, a notification of several messages answered message by message, answers on a system user's access token, and an install check; the owner's number proves the vendor's half",
    updated: "2026-09-30",
  },
  "M10.6.1": {
    status: "READY FOR TESTING",
    why: "all seven wires are live: webhook, Lark, email (a mailbox or Cloudflare), Slack, Teams, Telegram and WhatsApp (PR #105; L1, merged d426e3d3; #285; #296; #288; M10/channel-teams; M10/channel-telegram; M10/channel-whatsapp), each with its Connect steps and an install check",
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
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when a skill imported from a GitHub repository at a pinned commit lands unreviewed",
    updated: "2026-09-28",
  },
  "M12.2.3": {
    status: "READY FOR TESTING",
    why: "built in skill import, review and versions (T2, merged d654f1f4); proved when an import from an allowlisted address lands and a non-allowlisted one is refused",
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
    why: "moved to Wave 4 (needs-rupash 112): closes when every departments requirement row has its proof on the install",
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
    why: "moved to Wave 5 (needs-rupash 112): closes when every observability requirement row has its proof on the install",
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
    why: "waits on memory for Langfuse: 2,048 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 3)",
    updated: "2026-09-30",
  },
  "M32.1.1.2": {
    status: "BLOCKED",
    why: "waits on memory for Langfuse: 2,048 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 3)",
    updated: "2026-09-30",
  },
  "M32.2.1.1": {
    status: "BLOCKED",
    why: "waits on memory for the personal-data detector: 1,536 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-30 (needs-rupash 120, row 1)",
    updated: "2026-09-30",
  },
  "M32.2.1.2": {
    status: "BLOCKED",
    why: "waits on memory for the model server that serves GLiNER: 3,840 MB wanted with its worker and file store, 248 MB unclaimed, measured 2026-09-30 (needs-rupash 120, row 2)",
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
    why: "the Lark channel is merged (L1, d426e3d3); the exit check also needs question-time live read (C2) and the binding route (CH2), neither on main yet",
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
    why: "moved to Wave 3 (needs-rupash 112): closes when every models requirement row has its proof on the install",
    updated: "2026-09-29",
  },
  "M5.7.1": {
    status: "OPEN",
    why: "moved to Wave 5 (needs-rupash 113): Anthropic and Moonshot answer on the install; OpenAI and DeepSeek are turned off until their accounts are funded",
    updated: "2026-09-29",
  },
  "M7.1.1": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.1": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.2.2": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.3": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.2.4": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.2.5": {
    status: "READY FOR TESTING",
    why: "knowledge upload (PR #106, merged, migration 0115): proved when a document uploaded for one department answers that department and nobody else, which needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.6": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
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
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.3.4": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
    updated: "2026-09-29",
  },
  "M7.3.5": {
    status: "BLOCKED",
    why: "waits on memory for the model server: 3,840 MB wanted, 248 MB unclaimed on the shared host, measured 2026-09-29 (needs-rupash 120)",
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
    why: "waits on the owner's choice of upload limit, which sizes the model server; the model server reads 64 MB a document as sized (needs-rupash 119)",
    updated: "2026-09-29",
  },
  "M7.7.2": {
    status: "IN PROGRESS",
    why: "a steward per document is built (K2, merged f0722dd3); connected sources and agents have no steward yet",
    updated: "2026-09-28",
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
    why: "Wave 2 batch 2, citations, freshness and abstention on Ask (R2)",
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
