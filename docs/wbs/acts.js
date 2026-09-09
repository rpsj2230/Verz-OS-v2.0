// Leaves no commit can close, because they are things a person does on the week of a
// migration rather than code anybody could write.
//
// The percentage on /build is the number somebody reads to know how the build is going, and
// until this file existed it was mixing two kinds of work. A code leaf closes when it is
// written. "Announce the switch before removing their bot" closes when a person announces it,
// to a specific client, on a specific day, which cannot start before there is a client. Mixed
// into one denominator the figure tops out around 86 percent and stops, and the stop does not
// mean the build stalled. Flagged, the tracker can say buildable done and acts outstanding as
// two numbers, which is what was decided on 2026-09-09.
//
// THE FLAG IS KEPT HERE AND NOT IN THE LEAF ITSELF, and that is the whole design. A leaf is a
// bare string inside a `k` array and its id is its position: `M37.2.6.5` means "the fifth key
// of the sixth group of the second task of M37" and nothing anchors it to a name. Adding a
// field to a leaf means changing the shape of every leaf, and re-shaping 1251 leaves to mark
// 33 is how a group gets inserted by accident. This file is a side table keyed by id, the same
// arrangement `schedule.js` already uses for LEAF_WAVE, and it adds nothing to the tree.
//
// A SIDE TABLE KEYED BY A POSITIONAL ID HAS ONE FAILURE AND IT IS SILENT, so every entry
// carries the leaf sentence it was written against. Insert a group above one of these and the
// id keeps resolving, to a different leaf, and every flag repoints without a word. `export.js`
// and `render.js` both compare `text` against the sentence at that id and throw rather than
// generate, so the drift is a build failure instead of a checklist that quietly lists the
// wrong work. LEAF_WAVE has no such fingerprint and is the near miss this was written after.
//
// Three fields per entry:
//
//   kind    ACT          a person does it on the week of the migration.
//           UNBUILDABLE  a person does it AND it could not be code here whoever wrote it,
//                        because the leaf names one company's own things and the first rule
//                        in CLAUDE.md is that no company's details go into this repository.
//                        Recorded rather than left looking merely undone, so nobody spends a
//                        day trying to make it fit.
//   gate    true         its absence has a security consequence, so it gates the cutover
//                        rather than only appearing on a list. `brain.migration.decommission`
//                        refuses to report a completed cutover while any of these is
//                        unrecorded. See `brain.migration.checklist.CUTOVER_GATED_ACTS`.
//   text    the leaf sentence as it read when the flag was written. The fingerprint above.
//
// WHAT IS DELIBERATELY NOT FLAGGED, because the count is derived and a derived count has to
// say what it excluded. Of the 35 open leaves in M37 on 2026-09-09, two are left buildable:
//
//   M37.3.2.4  "Adoption measured as real questions from real people, machine traffic
//              excluded". The adoption is not code and the measurement is: a metric that
//              excludes machine traffic is a definition somebody commits.
//   M37.4.1.2  "Invariant suite green, evidenced". The suite is `tests/invariants` and the
//              evidence is what a CI run produces. Showing it to a client is an act; making
//              it producible is a commit, and the commit is the leaf.
//
// A closed leaf is never flagged, and the rule is the observation rather than a convention:
// if a commit closed it, it was closable by a commit. M37's generic half is built and closed
// already, in the nine modules under `src/brain/migration/`, and what is left is the part
// that only exists on the day.
//
// Rejected: moving these leaves out of the work breakdown into a checklist of their own,
// which is the cleanest tracker and the one thing that was not acceptable. A list nothing
// gates is a list nobody reads, and these are the leaves with a security consequence. They
// stay in the breakdown, they are flagged here, and the five with a security consequence gate
// the cutover.

//: Leaf id to its flag. Ordered by id, which is also plan order inside a module.
const ACTS = {
  // ---------------------------------------------------- M37.2.1 what is actually in there
  "M37.2.1.1": {
    kind: "UNBUILDABLE",
    gate: false,
    text: "Inventory the twelve house skills, named individually, since each is authored work and not a setting",
    why: "the count and the names are one company's authored estate, and a product every client installs cannot hold them",
  },
  "M37.2.1.2": {
    kind: "ACT",
    gate: false,
    text: "Inventory every agent with its connectors, skills, channels and availability, because an agent is a composition and not a prompt",
  },
  "M37.2.1.3": {
    kind: "ACT",
    gate: false,
    text: "Inventory automations, which are owned by an agent there and will be owned by an agent here",
  },
  "M37.2.1.4": {
    kind: "ACT",
    gate: false,
    text: "Export memory files, both curated and chat-extracted, with their change history",
  },
  "M37.2.1.5": {
    kind: "UNBUILDABLE",
    gate: false,
    text: "List which Lark groups each agent is installed into, since that is what staff actually see",
    why: "one company's chat groups, named. The register that holds the answer is generic; the answer is not",
  },
  "M37.2.1.6": {
    kind: "UNBUILDABLE",
    gate: false,
    text: "Record what AnyGen produced that anyone still relies on",
    why: "names the outgoing vendor and what it made for one company",
  },
  // ------------------------------------------------------------ M37.2.2 skills come across
  "M37.2.2.1": {
    kind: "UNBUILDABLE",
    gate: false,
    text: "Export verz-master-theme, verz-doc-letterhead, seo-audit and website-cro-audit first: they are in daily use and are the test of whether import works at all",
    why: "four of one company's skills by name. `brain.migration.skills` is the generic half and is built",
  },
  // ------------------------------------------------- M37.2.5 cutover where staff will notice
  "M37.2.5.1": {
    kind: "ACT",
    gate: false,
    text: "Install alongside, in one group first, with both bots present",
  },
  "M37.2.5.2": {
    kind: "ACT",
    gate: false,
    text: "Agreed period answering the same questions from both, with disagreements logged",
  },
  "M37.2.5.3": {
    kind: "ACT",
    gate: false,
    text: "Announce the switch before removing their bot, not after",
  },
  "M37.2.5.4": {
    kind: "ACT",
    gate: true,
    text: "Remove the AnyGen bot from each group in the agreed order",
    why: "a bot left in a group keeps receiving that group's messages. Removing the tenant installation is the authorisation half and this is the delivery half, and either one left undone leaves the outgoing vendor reading the client's internal chat",
  },
  "M37.2.5.5": {
    kind: "ACT",
    gate: false,
    text: "Keep their bot reachable read-only for an agreed window in case something was missed",
  },
  // ----------------------------------------------------- M37.2.6 decommissioning the account
  "M37.2.6.1": {
    kind: "ACT",
    gate: true,
    text: "Revoke every OAuth grant AnyGen holds - Gmail, Drive, Calendar, Sheets, Docs and the rest - because cancelling a subscription does not revoke them",
    why: "every grant is a live credential on somebody else's service and cancelling the subscription does not withdraw one. This is how an outgoing vendor keeps reading a client's mail after everybody believes the account is closed",
  },
  "M37.2.6.2": {
    kind: "ACT",
    gate: true,
    text: "Remove the AnyGen app from the Lark tenant, not just from the groups",
    why: "a tenant installation is a tenant-level grant. Removing the app from every group removes what staff see and leaves the scopes it was installed with, which is the same failure as an unrevoked grant one layer up",
  },
  "M37.2.6.3": {
    kind: "ACT",
    gate: false,
    text: "Export anything with retention value before the account closes, since access ends with billing",
  },
  "M37.2.6.4": {
    kind: "ACT",
    gate: false,
    text: "Cancel the subscription only after the export is verified restorable",
  },
  "M37.2.6.5": {
    kind: "ACT",
    gate: true,
    text: "Record the date access actually ended, which is a different date from the last invoice",
    why: "without it there is no evidence of when access ended, and the last invoice is the date everybody reaches for instead. It is the fact an incident review or an audit asks for, and it cannot be reconstructed afterwards",
  },
  // ----------------------------------------------------------------------- M37.3.1 the pilot
  "M37.3.1.1": {
    kind: "ACT",
    gate: false,
    text: "One department, agreed scope, named champion",
  },
  "M37.3.1.2": {
    kind: "ACT",
    gate: false,
    text: "Twenty real questions as the acceptance set",
  },
  "M37.3.1.3": {
    kind: "ACT",
    gate: false,
    text: "Daily review of every answer for the first week",
  },
  "M37.3.1.4": {
    kind: "ACT",
    gate: false,
    text: "Explicit go or no-go decision with written criteria",
  },
  // ------------------------------------------------------------- M37.3.2 departmental rollout
  "M37.3.2.1": {
    kind: "ACT",
    gate: false,
    text: "Rollout order agreed with the client",
  },
  "M37.3.2.2": {
    kind: "ACT",
    gate: false,
    text: "Per-department onboarding session",
  },
  "M37.3.2.3": {
    kind: "ACT",
    gate: false,
    text: "Per-department starter questions and knowledge seeding",
  },
  // ------------------------------------------------------------------------ M37.3.3 training
  "M37.3.3.1": {
    kind: "ACT",
    gate: false,
    text: "Staff session: what it can see, how to ask, how to correct it",
  },
  "M37.3.3.2": {
    kind: "ACT",
    gate: false,
    text: "Admin session: console walkthrough, grants, leashes, review queues",
  },
  "M37.3.3.3": {
    kind: "ACT",
    gate: false,
    text: "Recorded and left with the client",
  },
  // ---------------------------------------------------------------------- M37.4.1 acceptance
  "M37.4.1.1": {
    kind: "ACT",
    gate: false,
    text: "Acceptance criteria signed before build, not after",
  },
  "M37.4.1.3": {
    kind: "ACT",
    gate: true,
    text: "Restore drill executed in front of the client",
    why: "a backup nobody has read back is a file, which is the refusal `brain.ops.recovery` already makes about the live system and `FinalBackup.verified` makes about the last copy of the old one. In front of the client is what makes it evidence rather than a claim, and the cutover is the last moment it can be asked for",
  },
  "M37.4.1.4": {
    kind: "ACT",
    gate: false,
    text: "Security review completed if the client requires one",
  },
  "M37.4.1.5": {
    kind: "ACT",
    gate: false,
    text: "Penetration test scheduled where contractually required",
  },
  // -------------------------------------------------------------- M37.4.2 contract artifacts
  "M37.4.2.1": {
    kind: "ACT",
    gate: false,
    text: "Data processing agreement",
  },
  "M37.4.2.3": {
    kind: "ACT",
    gate: false,
    text: "Support and escalation procedure",
  },
};

//: Why the two conditional acceptance leaves do not gate the cutover, kept here because the
//: reason for an omission is harder to reconstruct than the reason for an inclusion.
//:
//: M37.4.1.4 and M37.4.1.5 are the security review and the penetration test, and both are
//: written "if the client requires one" and "where contractually required". A gate on a
//: conditional act refuses every cutover for every client who does not require it, and a gate
//: that fires when it should not is a gate somebody switches off, which takes the four real
//: ones with it. They are acts and they are on the checklist.
//:
//: M37.2.6.3 and M37.2.6.4 are the export before the account closes and the ordering of the
//: cancellation against it. Their absence loses data rather than leaving access open, and the
//: readable-copy half is already gated through M37.4.1.3.
const NOT_GATED_ON_PURPOSE = ["M37.4.1.4", "M37.4.1.5", "M37.2.6.3", "M37.2.6.4"];

//: Verify every flag against the leaf it names, and throw rather than generate.
//:
//: Takes a lookup rather than reading `wbs.json`, because both generators number the leaves
//: themselves and the point is to check each one's numbering rather than a third copy. Called
//: from `export.js` and from `render.js`, so a repointed id fails whichever is run first.
function check(textOf) {
  const wrong = [];
  for (const id of Object.keys(ACTS)) {
    const actual = textOf(id);
    if (actual === undefined) {
      wrong.push(`${id} is flagged as an act and names no leaf, so it is a group id or a typo`);
    } else if (actual !== ACTS[id].text) {
      wrong.push(
        `${id} is flagged against "${ACTS[id].text}" and now reads "${actual}", so a leaf ` +
          `has moved and every flag after it points at different work`
      );
    }
  }
  if (wrong.length) throw new Error(`docs/wbs/acts.js:\n  ${wrong.join("\n  ")}`);
  return Object.keys(ACTS).length;
}

module.exports = { ACTS, NOT_GATED_ON_PURPOSE, check };
