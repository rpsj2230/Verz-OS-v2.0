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
//           DECIDED      nobody does it, because the owner decided it is not needed as written.
//                        Not a person's task on any week and not code anybody should write,
//                        so it is neither on the delivery checklist nor in the percentage, and
//                        it is reported as its own count beside both. `why` is required and
//                        names the decision. `export.js` writes these into `leaf_decided`
//                        rather than `leaf_acts`, so every reader of `leaf_acts` keeps meaning
//                        "a person does it" without being taught a new kind. See
//                        `brain.status.A_LEAF_DECIDED_AGAINST_IS_NEITHER_BUILDABLE_NOR_A_CLIENT_TASK`.
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

//: The kind that means "decided: not needed as written". Named once so the generators compare
//: against a constant rather than each spelling the word.
const DECIDED = "DECIDED";

//: Every kind a flag may carry. See the header for what each one means.
const KINDS = ["ACT", "UNBUILDABLE", DECIDED];

//: Leaf id to its flag. Ordered by id, which is also plan order inside a module.
const ACTS = {
  // -------------------------------------------------------- M29.1 plugin interfaces, decided
  //
  // Needs Rupash item 58, answered Option B on 2026-09-16. `brain.plugins.points` is the
  // register of every extension point and it gives these nine an answer other than PLUGIN:
  // six are UNDECIDED, two are CONFIGURATION and one is FLAG. Writing the nine protocols would
  // close nine leaves with nine files nothing calls, which is the state the register refuses
  // in A_PROTOCOL_NOTHING_IMPLEMENTS_MAKES_THE_REGISTER_COMPLETE_AND_WORSE. A point gets a
  // contract on the day a real plug-in for it exists, and is tested against that plug-in.
  "M29.1.6": {
    kind: "DECIDED",
    gate: false,
    text: "Retriever interface",
    why: "item 58, Option B. The register answers UNDECIDED: no module defines a retriever contract, and the reach predicate is what decides which rows exist for a caller. A contract is written when a real retriever plug-in exists",
  },
  "M29.1.8": {
    kind: "DECIDED",
    gate: false,
    text: "Entity resolver interface",
    why: "item 58, Option B. The register answers UNDECIDED: resolution has a cascade and no seam, and a wrong merge joins two parties' rows under one id. A contract is written when a real resolver plug-in exists",
  },
  "M29.1.9": {
    kind: "DECIDED",
    gate: false,
    text: "Verifier interface",
    why: "item 58, Option B. The register answers UNDECIDED: whether an outside party may verify is a question about who the company stands behind. A contract is written when a real verifier plug-in exists",
  },
  "M29.1.10": {
    kind: "DECIDED",
    gate: false,
    text: "Guard interface",
    why: "item 58, Option B. The register answers UNDECIDED: a guard supplied from outside can be one that passes everything. A contract is written when a real guard plug-in exists, with the rule on replacing a shipped guard decided first",
  },
  "M29.1.11": {
    kind: "DECIDED",
    gate: false,
    text: "Storage backend interface",
    why: "item 58, Option B. The register answers FLAG: files are not optional, so a further backend goes into this repository behind a flag against brain.ops.storage.StorageBackend rather than in as a plug-in",
  },
  "M29.1.13": {
    kind: "DECIDED",
    gate: false,
    text: "Identity provider interface",
    why: "item 58, Option B. The register answers CONFIGURATION: a provider supplies principals, so one from outside is a second source of grants. Which provider is used is a value set during setup",
  },
  "M29.1.14": {
    kind: "DECIDED",
    gate: false,
    text: "Approver surface interface",
    why: "item 58, Option B. The register answers UNDECIDED: an outside surface would have to prove which person approved. A contract is written when a real approver surface plug-in exists",
  },
  "M29.1.15": {
    kind: "DECIDED",
    gate: false,
    text: "Export format interface",
    why: "item 58, Option B. The register answers UNDECIDED: neither export module declares a format seam. A contract is written when a real export format plug-in exists",
  },
  "M29.1.16": {
    kind: "DECIDED",
    gate: false,
    text: "Scope pack interface",
    why: "item 58, Option B. The register answers CONFIGURATION: a pack is a source of grants by definition and entitlements are additive, so a pack from outside the company is refused. Packs are set during setup",
  },
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

  // Added 2026-09-11, from a measurement rather than from the plan. Both administrative
  // consoles on the first deployment answer from the open internet: the deployment control
  // panel returns 302 to an unauthenticated request on its own subdomain, and the identity
  // provider's admin console returns 200 at `/admin/master/console/`. A note claiming the
  // first was reachable only by tunnel was five days stale and produced a wrong
  // recommendation before anybody curled it.
  //
  // Three of the four are acts and the fourth is not: deciding where the consoles live is a
  // decision plus about an hour of proxy work, which is a commit. The owner asked for all
  // four on the list to be done when the system is about to go live rather than now, which
  // is the right call: nothing here holds client data yet, and a hardening step taken before
  // the thing it protects exists is one nobody re-checks on the day it matters.
  "M37.6.1.1": {
    kind: "ACT",
    gate: true,
    text: "Two-factor on the deployment control panel account, because its sign-in page answers from the internet and it holds every container, database and secret on the host",
    why: "a public sign-in page is fine when a guessed or stolen password is not sufficient on its own, and this one is not a console among others: it is the control plane for every container on the host, including the identity provider's own database and every environment variable in it. One credential between the internet and all of that is the single largest exposure on the box, and the fix is an authenticator scan",
  },
  "M37.6.1.2": {
    kind: "ACT",
    gate: true,
    text: "Delete the temporary identity provider administrator created at bootstrap, so an internet-facing admin sign-in is one account to guess rather than two",
    why: "the same shape as the OAuth grants two groups up: a credential left behind after it has served its purpose, on a service reachable from outside. It is worse than an unused password because nothing about an unused admin account looks different on the day it is used",
  },
  "M37.6.1.4": {
    kind: "ACT",
    gate: false,
    text: "Rotate the identity provider's bootstrap administrator password once the account it created has been deleted",
    why: "conditional on the deletion above and much smaller once it is done: with the account gone the value signs into nothing. Not gated, for the reason the two conditional acceptance leaves are not gated either, and a gate that fires when it should not is a gate somebody switches off",
  },

  // Added 2026-09-11. THIS FILE HELD NOTHING BUT M37 UNTIL NOW, and that was an omission
  // rather than a decision: every sentence at the top of this file about mixing two kinds of
  // work into one denominator applies to M38.2.1 exactly as it applied to M37, and nobody
  // had looked outside the module the file was written for.
  //
  // M38.2.1 is the release ritual performed at the end of each wave, and three of its four
  // open leaves are things a person does to a running system on a particular day. They were
  // being counted as code somebody had not got round to writing, which makes the buildable
  // figure lower than the truth and puts three items on the list of work that no commit can
  // ever remove from it.
  //
  // M38.2.2 is deliberately NOT flagged and the distinction is the useful one. Those leaves
  // are the evidence that a wave is done, and evidence is a test: M38.2.2.1 and M38.2.2.3
  // were both closed by commits that drove the whole composition end to end, and the wave-2
  // one is the model for the rest. A milestone is buildable; the ritual around it is not.
  //
  // M38.2.1.2 is also not flagged and is not buildable as written either. It reads "run the
  // full invariant suite against staging", and measured on 2026-09-11 that suite is 1305
  // tests which pass identically with and without a database, because it reads source files
  // from disk rather than asking a running system anything. The image ships no tests, by
  // design. So running it against staging either re-tests the checkout, which is worth
  // nothing, or ships a test suite into a production image, which is worse than nothing.
  //
  // Left open and unflagged on purpose. It is not an act, because nothing a person does on
  // the day would satisfy it either, and flagging it would move it onto a checklist an
  // operator is meant to be able to work through. Adding the suite to the `stack` job was
  // considered and rejected as theatre: that job and the `static` job run the same checkout,
  // so the second run would prove exactly what the first already proved while looking like
  // coverage. What the leaf is reaching for is real and is a different check, that the image
  // about to be deployed carries the source the commit says it does, which `schema_check`
  // already does for the schema and nothing does for the code. That is a leaf somebody should
  // write, and it is not this one.
  "M38.2.1.3": {
    kind: "ACT",
    gate: false,
    text: "Deploy to production",
    why: "the pipeline that does it is built, closed by the wave-zero milestone, and has deployed this repository all day. What is left is somebody deciding a particular release goes out on a particular day, which is the act, and no commit closes it",
  },
  "M38.2.1.4": {
    kind: "ACT",
    gate: false,
    text: "Smoke test: one real question answered end to end by a real person",
    why: "the leaf says a real person in as many words, and that is the whole content of it. A fixture asking the same question is the wave-one milestone, which is a different leaf and is buildable",
  },
  "M38.2.1.5": {
    kind: "ACT",
    gate: false,
    text: "Restore drill from wave three onward",
    why: "a drill is somebody restoring a real backup onto real hardware and timing it. The machinery it exercises is code and is the recovery screen leaf under M27; the drill is the act, and `brain.launch.service_level` already refuses to report a recovery figure that rests on a schedule rather than on a copy somebody made",
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
//:
//: Also refuses a kind outside the vocabulary, an UNBUILDABLE or DECIDED flag with no `why`, and
//: a DECIDED flag that gates the cutover. A misspelt kind would otherwise be exported as an act
//: nobody recognises, and a decision with no reason is a leaf somebody reopens to find out why.
//: Returns the two counts separately, because they are reported separately on both pages.
function check(textOf) {
  const wrong = [];
  for (const id of Object.keys(ACTS)) {
    const flag = ACTS[id];
    const actual = textOf(id);
    if (actual === undefined) {
      wrong.push(`${id} is flagged and names no leaf, so it is a group id or a typo`);
    } else if (actual !== flag.text) {
      wrong.push(
        `${id} is flagged against "${flag.text}" and now reads "${actual}", so a leaf ` +
          `has moved and every flag after it points at different work`
      );
    }
    if (!KINDS.includes(flag.kind)) {
      wrong.push(`${id} has kind "${flag.kind}", which is none of ${KINDS.join(", ")}`);
    }
    if (flag.kind !== "ACT" && !(flag.why || "").trim()) {
      wrong.push(`${id} is ${flag.kind} with no why, so nobody can tell what was decided`);
    }
    if (flag.kind === DECIDED && flag.gate === true) {
      wrong.push(`${id} is DECIDED and gates the cutover, and nothing waits for work nobody does`);
    }
  }
  if (wrong.length) throw new Error(`docs/wbs/acts.js:\n  ${wrong.join("\n  ")}`);
  const decided = Object.values(ACTS).filter((flag) => flag.kind === DECIDED).length;
  return { acts: Object.keys(ACTS).length - decided, decided };
}

module.exports = { ACTS, DECIDED, KINDS, NOT_GATED_ON_PURPOSE, check };
