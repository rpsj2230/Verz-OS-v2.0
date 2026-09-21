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
  "M0.1.1": {
    kind: "ACT",
    gate: false,
    text: "Private GitHub repo, branch protection, CODEOWNERS on the three core files",
    why: "owner's decision 2026-09-21: the repository stays public on purpose for now and he makes it private and protects main himself before go-live; not to be raised again until then",
  },
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
  // -------------------------------------------------- duplicates merged, 2026-09-17
  //
  // The tracker audit against the owner's install (docs/tracker-audit-2026-09-17.md) found leaves
  // that restate another leaf. The owner approved merging them on 2026-09-17. Ids are positional,
  // so a duplicate is retired here rather than deleted, and the leaf it merged into carries the work.
  "M1.6.11": {
    kind: "DECIDED",
    gate: false,
    text: "Console page to choose, configure and test a staff source before it runs",
    why: "Merged into M27.7.2, which asks for the same outcome: Staff source: choose it, configure it and try it before it runs. Owner approved merging duplicates on 2026-09-17.",
  },
  "M2.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Predicate evaluator compiling to a SQL where clause",
    why: "Merged into M0.2.2, which asks for the same outcome: Scope model as jsonb predicate, evaluator, conjunction-only composition. Owner approved merging duplicates on 2026-09-17.",
  },
  "M2.1.3": {
    kind: "DECIDED",
    gate: false,
    text: "Conjunction-only grammar validator so a scope can never widen",
    why: "Merged into M0.2.2, which asks for the same outcome: Scope model as jsonb predicate, evaluator, conjunction-only composition. Owner approved merging duplicates on 2026-09-17.",
  },
  "M2.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Scope composition for multi-scope principals",
    why: "Merged into M0.2.2, which asks for the same outcome: Scope model as jsonb predicate, evaluator, conjunction-only composition. Owner approved merging duplicates on 2026-09-17.",
  },
  "M2.2.3": {
    kind: "DECIDED",
    gate: false,
    text: "Department creation wizard with starter scopes",
    why: "Merged into M27.11.1, which asks for the same outcome: Departments, teams and scopes created, renamed and retired from the console, each change audited. Owner approved merging duplicates on 2026-09-17.",
  },
  "M6.2.1": {
    kind: "DECIDED",
    gate: false,
    text: "Answer cache keyed on entitlement hash and epochs",
    why: "Merged into M3.5.1, which asks for the same outcome: Key from question, entitlement hash, agent config hash, policy epoch, source epochs. Owner approved merging duplicates on 2026-09-17.",
  },
  "M6.3.6": {
    kind: "DECIDED",
    gate: false,
    text: "Cache hits shown as instant with the reason",
    why: "Merged into M3.5.3, which asks for the same outcome: Hit surfaced to the user with its age. Owner approved merging duplicates on 2026-09-17.",
  },
  "M6.4.1": {
    kind: "DECIDED",
    gate: false,
    text: "Static tool prefix ordering for provider cache sharing",
    why: "Merged into M3.7.2, which asks for the same outcome: Static tool prefix with deferred loading so the provider cache is shared. Owner approved merging duplicates on 2026-09-17.",
  },
  "M8.2.3": {
    kind: "DECIDED",
    gate: false,
    text: "Not-entitled path indistinguishable from nothing-found",
    why: "Merged into M4.3.3, which asks for the same outcome: Permission-denied indistinguishable from nothing-found at record level. Owner approved merging duplicates on 2026-09-17.",
  },
  "M9.2.2": {
    kind: "DECIDED",
    gate: false,
    text: "Locked-field rendering",
    why: "Merged into M4.3.1, which asks for the same outcome: Structural lock rendering, identical for every viewer. Owner approved merging duplicates on 2026-09-17.",
  },
  "M12.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Required capability per tool",
    why: "Merged into M0.2.6, which asks for the same outcome: ToolDefinition: name, args schema, result contract, required capability, side effect, identity mode. Owner approved merging duplicates on 2026-09-17.",
  },
  "M12.1.6": {
    kind: "DECIDED",
    gate: false,
    text: "Registry sweep in CI",
    why: "Merged into M0.5.6, which asks for the same outcome: Registry sweep: tool naming grammar. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Agent enable, disable and archive",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.1.5": {
    kind: "DECIDED",
    gate: false,
    text: "Ownership transfer when a creator leaves",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.1": {
    kind: "DECIDED",
    gate: false,
    text: "Six-step wizard generated from the manifest JSON Schema",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Connector binding step with readiness indicators",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.3": {
    kind: "DECIDED",
    gate: false,
    text: "Placeholder collection: SOP, price list, escalation contact",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.4": {
    kind: "DECIDED",
    gate: false,
    text: "Golden-set run as the installing principal",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.5": {
    kind: "DECIDED",
    gate: false,
    text: "Golden-set run as a low-privilege fixture user",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.6": {
    kind: "DECIDED",
    gate: false,
    text: "Incomplete state with an amber badge listing what is missing",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.3.7": {
    kind: "DECIDED",
    gate: false,
    text: "Pin to Shadow when required connectors are absent",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.1": {
    kind: "DECIDED",
    gate: false,
    text: "Save any agent as a private template",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.2": {
    kind: "DECIDED",
    gate: false,
    text: "Literal extraction and parameter hoisting",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.3": {
    kind: "DECIDED",
    gate: false,
    text: "Leak report with accept or redact on every unclassified literal",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.4": {
    kind: "DECIDED",
    gate: false,
    text: "Publish blocked until every item is dispositioned",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.5": {
    kind: "DECIDED",
    gate: false,
    text: "Memory never exported under any setting",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M13.6.6": {
    kind: "DECIDED",
    gate: false,
    text: "Visibility: private, organisation, catalogue",
    why: "Merged into M27.11.7, which asks for the same outcome: Agent templates installed, authored from an agent through the leak scan, and withdrawn. Owner approved merging duplicates on 2026-09-17.",
  },
  "M19.6.1": {
    kind: "DECIDED",
    gate: false,
    text: "Global browser concurrency limit",
    why: "Merged into M22.1.1, which asks for the same outcome: Global budgets: concurrent model calls, source calls per connector, browser sessions, long-running tasks, document jobs, embedding jobs, tokens per minute. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Draft, save and version handling",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.3.1": {
    kind: "DECIDED",
    gate: false,
    text: "Run against the real gate, leash and redactor",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Cassette replay so no real side effect fires",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.3.3": {
    kind: "DECIDED",
    gate: false,
    text: "Per-persona rehearsal showing what each user would see",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.3.4": {
    kind: "DECIDED",
    gate: false,
    text: "Measured cost per run from the rehearsal",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M20.4.3": {
    kind: "DECIDED",
    gate: false,
    text: "Grant-widening demotes to Shadow and requires a second approver",
    why: "Merged into M27.11.6, which asks for the same outcome: Agents created from a template or from scratch through saved drafts, a rehearsal and a publish a second person approves, then enabled, disabled, archived, duplicated and handed over. Owner approved merging duplicates on 2026-09-17.",
  },
  "M23.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Widget session minting with an abuse guard",
    why: "Merged into M10.5.5, which asks for the same outcome: Web widget with session minting and abuse guard. Owner approved merging duplicates on 2026-09-17.",
  },
  "M26.2.5": {
    kind: "DECIDED",
    gate: false,
    text: "Memories tagged with the old capability set no longer replayed",
    why: "Merged into M16.4.4, which asks for the same outcome: Entitlement expiry: memories stop matching when capabilities change. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.1": {
    kind: "DECIDED",
    gate: false,
    text: "People and grants",
    why: "Merged into M27.7.3, which asks for the same outcome: People: who is here, what each holds, and the reach that follows from it. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.3": {
    kind: "DECIDED",
    gate: false,
    text: "Roles: the six, what each is for, and who holds it",
    why: "Merged into M27.7.5, which asks for the same outcome: Roles: the six, what each is for, and who holds it. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.4": {
    kind: "DECIDED",
    gate: false,
    text: "Capability catalogue: everything that can be granted at all",
    why: "Merged into M27.7.6, which asks for the same outcome: The capability catalogue: everything that can be granted at all. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.5": {
    kind: "DECIDED",
    gate: false,
    text: "Staff sources: where the staff list is linked from and what each may assert",
    why: "Merged into M27.7.2, which asks for the same outcome: Staff source: choose it, configure it and try it before it runs. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.6": {
    kind: "DECIDED",
    gate: false,
    text: "Access review: each department admin recertifies what their people hold",
    why: "Merged into M27.7.9, which asks for the same outcome: Access review: each department lead recertifies what their people hold. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.8": {
    kind: "DECIDED",
    gate: false,
    text: "Sessions, with a control to end one, because revoking a grant does not close a session",
    why: "Merged into M27.7.10, which asks for the same outcome: Sessions, with a control to end one, because revoking a grant does not close a session. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.9": {
    kind: "DECIDED",
    gate: false,
    text: "Exports: what left the building and who took it",
    why: "Merged into M27.7.24, which asks for the same outcome: Exports, retention and erasure, with the deletion queue. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.10": {
    kind: "DECIDED",
    gate: false,
    text: "Retention and erasure, with the deletion queue",
    why: "Merged into M27.7.24, which asks for the same outcome: Exports, retention and erasure, with the deletion queue. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.14": {
    kind: "DECIDED",
    gate: false,
    text: "Knowledge library across every department, with per-item visibility scope",
    why: "Merged into M27.7.20, which asks for the same outcome: Knowledge library across every department, with per-item visibility scope. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.15": {
    kind: "DECIDED",
    gate: false,
    text: "Learning review across every department, tiers separated and tier one undoable",
    why: "Merged into M27.7.21, which asks for the same outcome: Learning review across every department, tiers separated and tier one undoable. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.16": {
    kind: "DECIDED",
    gate: false,
    text: "Artifacts produced, with provenance and retention",
    why: "Merged into M27.7.23, which asks for the same outcome: Artifacts produced, with provenance and retention. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.3.17": {
    kind: "DECIDED",
    gate: false,
    text: "Memory viewer with change history",
    why: "Merged into M27.7.22, which asks for the same outcome: Memory viewer with change history. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.4.2": {
    kind: "DECIDED",
    gate: false,
    text: "Usage and tokens by person, department, model and agent",
    why: "Merged into M27.7.14, which asks for the same outcome: Usage and tokens by person, department, model and agent. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.4.3": {
    kind: "DECIDED",
    gate: false,
    text: "Budgets and spend limits, and what happens at the ceiling",
    why: "Merged into M27.7.15, which asks for the same outcome: Spend, budgets and what happens at the ceiling. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.4.4": {
    kind: "DECIDED",
    gate: false,
    text: "Quality and canaries",
    why: "Merged into M27.7.19, which asks for the same outcome: Quality and the permission canaries. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.6.2": {
    kind: "DECIDED",
    gate: false,
    text: "Backup, last verified restore and the recovery drill",
    why: "Merged into M27.7.26, which asks for the same outcome: Backup, last verified restore and the recovery drill. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.6.3": {
    kind: "DECIDED",
    gate: false,
    text: "Rate limits and what is currently being throttled",
    why: "Merged into M27.7.27, which asks for the same outcome: Rate limits and capacity: what is throttled now, and connections, memory and pools against what is deployed. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.6.4": {
    kind: "DECIDED",
    gate: false,
    text: "Capacity: connections, memory and pool sizes against what is deployed",
    why: "Merged into M27.7.27, which asks for the same outcome: Rate limits and capacity: what is throttled now, and connections, memory and pools against what is deployed. Owner approved merging duplicates on 2026-09-17.",
  },
  "M27.8.12": {
    kind: "DECIDED",
    gate: false,
    text: "Webhooks, managed from the console",
    why: "Merged into M17.5.3, which asks for the same outcome: Subscriber management in the console. Owner approved merging duplicates on 2026-09-17.",
  },
  "M28.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Golden corpus of real questions per persona",
    why: "Merged into M0.6.4, which asks for the same outcome: Golden questions: twenty questions across three personas with known answers. Owner approved merging duplicates on 2026-09-17.",
  },
  "M29.1.1": {
    kind: "DECIDED",
    gate: false,
    text: "Channel adapter interface",
    why: "Merged into M10.1.1, which asks for the same outcome: Channel adapter interface with normalise, send, capabilities. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Per-install variables file in a separate private repo",
    why: "Merged into M42.1.1, which asks for the same outcome: Per-client variables in a separate private repository, one file per install, documented field by field. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.1.5": {
    kind: "DECIDED",
    gate: false,
    text: "Secrets minted per install, never copied between clients",
    why: "Merged into M42.1.2, which asks for the same outcome: Secrets minted per install and never copied between clients, enforced by a check that refuses a shared value. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.1": {
    kind: "DECIDED",
    gate: false,
    text: "GitHub Actions: lint, types, tests, migrations, canaries",
    why: "Merged into M38.1.2.1, which asks for the same outcome: Actions workflow: lint, type check, unit tests, invariant suite, schema sweeps. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.2": {
    kind: "DECIDED",
    gate: false,
    text: "Container image build and signing",
    why: "Merged into M38.1.2.4, which asks for the same outcome: Image signing. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.3": {
    kind: "DECIDED",
    gate: false,
    text: "Registry publication",
    why: "Merged into M38.1.2.5, which asks for the same outcome: Push to the registry. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.5": {
    kind: "DECIDED",
    gate: false,
    text: "Per-client release pinning",
    why: "Merged into M42.1.4, which asks for the same outcome: Release pinning per client, so one client can hold a version back without forking. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.7": {
    kind: "DECIDED",
    gate: false,
    text: "Rollback by re-pinning the previous tag",
    why: "Merged into M42.3.6, which asks for the same outcome: Update script pinning a release tag, and a rollback script re-pinning the previous one. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.2.8": {
    kind: "DECIDED",
    gate: false,
    text: "Install checklist covering platform project files, temporary CLI state, git remotes and scheduled jobs",
    why: "Merged into M42.3.7, which asks for the same outcome: Deployment checklist: pre-deployment, server, application, database, environment, integrations, security, testing, go-live and post-deployment. Owner approved merging duplicates on 2026-09-17.",
  },
  "M30.4.8": {
    kind: "DECIDED",
    gate: false,
    text: "Kill after every side-effect boundary with exactly-once verification",
    why: "Merged into M17.3.5, which asks for the same outcome: Kill-after-side-effect test proving exactly-once. Owner approved merging duplicates on 2026-09-17.",
  },
  "M31.2.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Separate session-mode engine for the worker",
    why: "Merged into M0.3.5, which asks for the same outcome: PgBouncer session-mode pool for the worker, for LISTEN and NOTIFY. Owner approved merging duplicates on 2026-09-17.",
  },
  "M31.3.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Every variable documented in the example file",
    why: "Merged into M0.4.3, which asks for the same outcome: Documented environment example with every variable explained. Owner approved merging duplicates on 2026-09-17.",
  },
  "M32.4.1.1": {
    kind: "DECIDED",
    gate: false,
    text: "Procrastinate on Postgres for the job queue",
    why: "Merged into M17.1.2, which asks for the same outcome: Procrastinate integration on Postgres. Owner approved merging duplicates on 2026-09-17.",
  },
  "M32.4.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "LangGraph checkpointer configuration",
    why: "Merged into M17.2.1, which asks for the same outcome: LangGraph checkpointer on Postgres. Owner approved merging duplicates on 2026-09-17.",
  },
  "M32.4.1.3": {
    kind: "DECIDED",
    gate: false,
    text: "Our re-drive driver for crash recovery",
    why: "Merged into M17.2.2, which asks for the same outcome: Our own re-drive driver for crash recovery. Owner approved merging duplicates on 2026-09-17.",
  },
  "M33.1.1.4": {
    kind: "DECIDED",
    gate: false,
    text: "Global kill switch",
    why: "Merged into M27.12.4, which asks for the same outcome: The stop button halts the install from the console and the halt survives a restart. Owner approved merging duplicates on 2026-09-17.",
  },
  "M33.1.2.5": {
    kind: "DECIDED",
    gate: false,
    text: "Self-grant path that writes a loud audit event and notifies the steward",
    why: "Merged into M27.5.5, which asks for the same outcome: Super Admin self-grant writes a loud audit event and notifies the steward. Owner approved merging duplicates on 2026-09-17.",
  },
  "M33.6.1.1": {
    kind: "DECIDED",
    gate: false,
    text: "Pending approvals within their own entitlement",
    why: "Merged into M27.3.7, which asks for the same outcome: Approvals queue: what is waiting on a human. Owner approved merging duplicates on 2026-09-17.",
  },
  "M33.7.1.1": {
    kind: "DECIDED",
    gate: false,
    text: "Zero standing entitlement",
    why: "Merged into M1.2.4, which asks for the same outcome: Partner principal with zero standing entitlement. Owner approved merging duplicates on 2026-09-17.",
  },
  "M34.2.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Verification badge visible in answers",
    why: "Merged into M7.4.7, which asks for the same outcome: Verification badge surfaced in the answer. Owner approved merging duplicates on 2026-09-17.",
  },
  "M34.2.1.3": {
    kind: "DECIDED",
    gate: false,
    text: "Re-verification nag on the review date",
    why: "Merged into M7.4.6, which asks for the same outcome: Scheduled job opening re-verification tasks from review_by. Owner approved merging duplicates on 2026-09-17.",
  },
  "M34.3.2.3": {
    kind: "DECIDED",
    gate: false,
    text: "Incident playbook per failure mode",
    why: "Merged into M30.4.1, which asks for the same outcome: Failure-mode matrix covering every component. Owner approved merging duplicates on 2026-09-17.",
  },
  "M34.3.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Per-client variables reference",
    why: "Merged into M42.2.5, which asks for the same outcome: Configuration guide: every value a new client must set, in one table, with where each comes from. Owner approved merging duplicates on 2026-09-17.",
  },
  "M35.3.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Approval cards readable without horizontal scroll",
    why: "Merged into M35.3.1.1, which asks for the same outcome: Console usable on a phone for approvals at minimum. Owner approved merging duplicates on 2026-09-17.",
  },
  "M36.1.1.2": {
    kind: "DECIDED",
    gate: false,
    text: "Partition by month with automatic creation",
    why: "Merged into M36.1.1.1, which asks for the same outcome: Monthly partitions of the metadata ledger, created and detached by the worker in plain SQL. Owner approved merging duplicates on 2026-09-17.",
  },
  "M36.1.1.3": {
    kind: "DECIDED",
    gate: false,
    text: "Retention detach and archive rather than delete",
    why: "Merged into M36.1.1.1, which asks for the same outcome: Monthly partitions of the metadata ledger, created and detached by the worker in plain SQL. Owner approved merging duplicates on 2026-09-17.",
  },
  "M37.4.2.2": {
    kind: "DECIDED",
    gate: false,
    text: "Service level statement with the RPO and RTO from the chosen profile",
    why: "Merged into M30.5.4, which asks for the same outcome: RPO and RTO per profile written into the client agreement. Owner approved merging duplicates on 2026-09-17.",
  },
  "M37.4.3.1": {
    kind: "DECIDED",
    gate: false,
    text: "Runbook per console screen",
    why: "Merged into M34.3.2.1, which asks for the same outcome: Runbook per console screen. Owner approved merging duplicates on 2026-09-17.",
  },
  "M37.4.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Incident playbook per failure mode",
    why: "Merged into M30.4.1, which asks for the same outcome: Failure-mode matrix covering every component. Owner approved merging duplicates on 2026-09-17.",
  },
  "M37.5.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Estimator correction from actuals",
    why: "Merged into M21.2.4, which asks for the same outcome: Estimator correction from actuals. Owner approved merging duplicates on 2026-09-17.",
  },
  "M38.1.1.5": {
    kind: "ACT",
    gate: false,
    text: "CODEOWNERS forcing review on the gate, the redactor and the catalogue projection",
    why: "owner's decision 2026-09-21: the repository stays public on purpose for now and he makes it private and protects main himself before go-live; not to be raised again until then",
  },
  "M38.1.2.2": {
    kind: "DECIDED",
    gate: false,
    text: "Migration forward and rollback against a production-shaped snapshot",
    why: "Merged into M0.5.3, which asks for the same outcome: Migration forward and rollback against production-shaped data. Owner approved merging duplicates on 2026-09-17.",
  },
  "M39.3.1.5": {
    kind: "DECIDED",
    gate: false,
    text: "Preview computed by the real gate, never by a separate estimation path",
    why: "Merged into M39.3.1.4, which asks for the same outcome: Worked preview: pick a person, see exactly what their run of this agent would return. Owner approved merging duplicates on 2026-09-17.",
  },
  "M40.2.1.5": {
    kind: "DECIDED",
    gate: false,
    text: "Recent threads continued from any channel, so web and Lark are one history",
    why: "Merged into M9.1.2, which asks for the same outcome: Thread continuity across channels. Owner approved merging duplicates on 2026-09-17.",
  },
  "M40.3.3.2": {
    kind: "DECIDED",
    gate: false,
    text: "Re-download re-checked against current entitlement",
    why: "Merged into M39.5.1.5, which asks for the same outcome: Re-download re-checks the requester entitlement rather than trusting the original link. Owner approved merging duplicates on 2026-09-17.",
  },
  "M40.4.1.3": {
    kind: "DECIDED",
    gate: false,
    text: "Weekly digest delivered in the person's own channel with the same controls",
    why: "Merged into M16.5.1, which asks for the same outcome: Weekly digest of tier one and two learning with one-click undo. Owner approved merging duplicates on 2026-09-17.",
  },
  "M40.6.1.5": {
    kind: "DECIDED",
    gate: false,
    text: "Mobile layout treated as the primary case for approvals",
    why: "Merged into M35.3.1.1, which asks for the same outcome: Console usable on a phone for approvals at minimum. Owner approved merging duplicates on 2026-09-17.",
  },
  // ------------------------------------------ acts found by the requirement trace, 2026-09-18
  "M37.7.1": {
    kind: "ACT",
    gate: false,
    text: "The company names its data steward on the people screen and the steward grants each pilot department's staff their starter reads, recorded in the audit trail",
  },
  "M37.7.2": {
    kind: "ACT",
    gate: false,
    text: "The company switches on a second sign-in factor for every account on the identity provider's admin console and every other administrative console of the install, and records that each one asks for it",
  },
  "M30.6.3": {
    kind: "ACT",
    gate: false,
    text: "The company sets its own time targets in seconds for first output and for a complete answer in each lane before go-live, and they are recorded as the targets the service levels screen measures against",
  },
  "M37.7.3": {
    kind: "ACT",
    gate: false,
    text: "The company's administrator creates the ticket desk and chat workspace credentials with the scopes the integration guide lists and enters them on the connectors screen, never in a file or a message",
  },
  "M37.7.4": {
    kind: "ACT",
    gate: false,
    text: "The company's workspace administrator installs the product's chat app with the scopes the channel guide lists, adds it to the pilot groups and creates the directory app the staff source signs in with",
  },
  "M37.7.7": {
    kind: "ACT",
    gate: false,
    text: "Commission a penetration test of the owner's install before the first company data is connected, and record each finding with its fix or accepted risk",
  },
  "M41.1.6": {
    kind: "DECIDED",
    gate: false,
    text: "Model and provider choice as configuration, including a local-only profile with no external provider",
    why: "owner 2026-09-21, item 80: installs use hosted providers (Claude, OpenAI, DeepSeek, Moonshot Kimi); no local-only profile is needed. Provider and model choice is already configuration (Routing screen)",
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
