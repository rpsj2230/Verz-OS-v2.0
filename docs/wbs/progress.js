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
    status: "BLOCKED",
    why: "the owner records the remaining permissions rows on Requirement checks (needs-rupash 91, check 7)",
    updated: "2026-09-28",
  },
  "M10.1.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.1.5": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.2.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.3.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.4.5": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.6.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M10.6.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
    updated: "2026-09-28",
  },
  "M12.1.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, tool catalogue and switch (T1): in PR #102",
    updated: "2026-09-28",
  },
  "M12.1.3": {
    status: "IN PROGRESS",
    why: "the leash ceiling is built and shown on Tools (PR #102); its call on the agent run path comes with Wave 3's agent runtime",
    updated: "2026-09-28",
  },
  "M12.1.4": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, tool catalogue and switch (T1): in PR #102",
    updated: "2026-09-28",
  },
  "M12.3.8": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, tool catalogue and switch (T1): in PR #102",
    updated: "2026-09-28",
  },
  "M12.4.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, tool catalogue and switch (T1): in PR #102",
    updated: "2026-09-28",
  },
  "M2.3.1": {
    status: "BLOCKED",
    why: "moved to Wave 2 (needs-rupash 97): the web part is the owner's department checks (needs-rupash 91, checks 2 and 3); the chat part needs Wave 2's Lark chat channel",
    updated: "2026-09-28",
  },
  "M2.3.2": {
    status: "BLOCKED",
    why: "the owner records the remaining departments rows on Requirement checks (needs-rupash 91, check 7)",
    updated: "2026-09-28",
  },
  "M23.1.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.1.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.1.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.1.5": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.2.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.2.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M23.2.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, rate limits live (A1): in PR #101",
    updated: "2026-09-28",
  },
  "M24.3.4": {
    status: "BLOCKED",
    why: "the owner's audit check on the install (needs-rupash 91, check 4)",
    updated: "2026-09-28",
  },
  "M24.3.6": {
    status: "BLOCKED",
    why: "the owner records the remaining observability rows on Requirement checks (needs-rupash 91, check 7)",
    updated: "2026-09-28",
  },
  "M3.2.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, channel pipeline (CH1): built, being finished (audit of channel changes, route mounted)",
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
    status: "BLOCKED",
    why: "the owner's models check on the install (needs-rupash 91, check 6), once the providers answer (needs-rupash 98)",
    updated: "2026-09-28",
  },
  "M5.7.1": {
    status: "READY FOR TESTING",
    why: "Models and health shows all four providers with Add key, Test and Turn off (PR #100); proved when each answers on the install (needs-rupash 98)",
    updated: "2026-09-28",
  },
  "M5.7.3": {
    status: "BLOCKED",
    why: "built (PR #100): the agent page shows a pinned model as step 1 with the level's steps behind it; proving it needs an agent, which Wave 3 creates (needs-rupash 100)",
    updated: "2026-09-28",
  },
  "M7.1.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.2.5": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.3.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.3.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.4.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.5.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, classified tables and price lists (K6): in PR #103; the answer path joins after the rate limits PR",
    updated: "2026-09-28",
  },
  "M7.5.2": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, classified tables and price lists (K6): in PR #103; the answer path joins after the rate limits PR",
    updated: "2026-09-28",
  },
  "M7.5.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, classified tables and price lists (K6): in PR #103; the answer path joins after the rate limits PR",
    updated: "2026-09-28",
  },
  "M7.6.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.6.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.7.1": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, knowledge upload (K1): built, uploads being added to the audit ledger; reading needs a knowledge grant (needs-rupash 105)",
    updated: "2026-09-28",
  },
  "M7.7.3": {
    status: "IN PROGRESS",
    why: "Wave 2 batch 1, classified tables and price lists (K6): in PR #103; the answer path joins after the rate limits PR",
    updated: "2026-09-28",
  },
};

//: Wave number to the deployed commit it closed at: {commit, recorded, note}. Empty until a
//: wave is accepted on staging.
const WAVE_RECORDS = {};

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
